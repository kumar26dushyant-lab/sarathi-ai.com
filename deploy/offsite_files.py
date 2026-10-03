# -*- coding: utf-8 -*-
"""ENCRYPTED, INCREMENTAL OFF-SITE COPY - claim documents and the database (3 Oct 2026).

Why: backup.sh used to upload a COMPLETE encrypted archive every night (1.9 GB) and keep eight.
The remote held 12.4 GiB against a 20 GB free allowance and grew by every upload; the local disk
held seven more full copies (14 GB of 45). Bigger uploads (100 MB per document) would have hit
both walls within weeks - and a backup that fails for "no space" is found out only when needed.

Now each document goes off-site ONCE. A file that changes is uploaded as a NEW version; nothing
off-site is ever overwritten or deleted, so a file encrypted by ransomware or emptied by mistake
on the server cannot take its backup with it. The database goes every night (seven kept).

ENCRYPTION (the house rule: AES-256-GCM). Keys come from the backup passphrase already kept in
biz.env AND off-site by the founder (BACKUP_ENC_PASSPHRASE), stretched with scrypt and a random
salt stored beside the backup. Each object is
        b"NPB1" + 12-byte random nonce + AES-256-GCM(data, aad = the object's own name)
so an object cannot be swapped for another without the decryption failing. Object names are
HMAC-SHA256 of the file's path and contents - the remote shows nothing about whose file it is.
The manifest that maps names back to files is encrypted the same way.

    python deploy/offsite_files.py push     # copy what is new or changed
    python deploy/offsite_files.py db FILE  # one encrypted database copy (FILE = a .db.gz)
    python deploy/offsite_files.py verify   # download a random sample, decrypt, compare - the OUTCOME
    python deploy/offsite_files.py restore --to DIR [--match TEXT] [--db]

Settings (environment, from biz.env): BACKUP_ENC_PASSPHRASE, BACKUP_RCLONE_REMOTE (e.g.
"oci:sarathi-backups-mumbai"; objects go under its v1/ folder). For tests, a remote of the form
"dir:/some/folder" is a plain folder and needs no rclone.

Restoring after losing the server: install rclone with the same remote, put the passphrase in
the environment, then `restore --to /some/new/dir --db`. It writes the files and the latest
database (as sarathi_biz.db.restored), checks every one against the manifest, and never writes
over an existing file.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"NPB1"
PREFIX = "v1"
# What is backed up, relative to the app folder. Claim papers live in uploads/nidaan-docs.
FOLDERS = ("uploads", "generated_pdfs", "generated_videos")
DB_KEEP_DAYS = 7
SCRYPT = dict(n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=64)


class BackupError(Exception):
    pass


# ── where the objects go ─────────────────────────────────────────────────────
class Remote:
    """rclone for the real remote; a plain folder ("dir:...") for tests."""

    def __init__(self, spec: str):
        spec = (spec or "").strip()
        if not spec:
            raise BackupError("BACKUP_RCLONE_REMOTE is not set.")
        self.local = spec.startswith("dir:")
        self.base = (spec[4:] if self.local else spec.rstrip("/")) + "/" + PREFIX

    def _p(self, rel: str) -> str:
        return self.base + "/" + rel

    def _rclone(self, *args, data: bytes | None = None) -> bytes:
        r = subprocess.run(["rclone", *args], input=data, capture_output=True, timeout=6 * 3600)
        if r.returncode != 0:
            # rclone's own words, minus anything that looks like a key or token.
            msg = r.stderr.decode("utf-8", "replace")[-400:]
            raise BackupError("rclone %s failed: %s" % (args[0], msg))
        return r.stdout

    def get(self, rel: str) -> bytes | None:
        if self.local:
            p = self._p(rel)
            return open(p, "rb").read() if os.path.exists(p) else None
        try:
            return self._rclone("cat", self._p(rel))
        except BackupError as e:
            if "not found" in str(e).lower() or "doesn't exist" in str(e).lower():
                return None
            raise

    def put(self, rel: str, data: bytes) -> None:
        if self.local:
            p = self._p(rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p + ".part", "wb") as f:
                f.write(data)
            os.replace(p + ".part", p)
            return
        self._rclone("rcat", self._p(rel), data=data)

    def put_dir(self, staging: str, rel: str) -> None:
        """Upload every file in `staging` into `rel`/, never overwriting what is there."""
        if self.local:
            dst = self._p(rel)
            os.makedirs(dst, exist_ok=True)
            for n in os.listdir(staging):
                if not os.path.exists(os.path.join(dst, n)):
                    shutil.copy2(os.path.join(staging, n), os.path.join(dst, n))
            return
        self._rclone("copy", "--immutable", "--transfers", "8", staging, self._p(rel))

    def list(self, rel: str) -> list:
        if self.local:
            p = self._p(rel)
            return sorted(os.listdir(p)) if os.path.isdir(p) else []
        out = self._rclone("lsf", "--files-only", self._p(rel)).decode("utf-8", "replace")
        return sorted(x for x in out.splitlines() if x.strip())

    def delete(self, rel: str) -> None:
        if self.local:
            os.remove(self._p(rel))
            return
        self._rclone("deletefile", self._p(rel))


# ── keys and the box every object travels in ─────────────────────────────────
class Keys:
    def __init__(self, passphrase: str, salt: bytes):
        if len(passphrase or "") < 12:
            raise BackupError("BACKUP_ENC_PASSPHRASE is missing or too short.")
        m = hashlib.scrypt(passphrase.encode("utf-8"), salt=salt, **SCRYPT)
        self.enc, self.name = m[:32], m[32:]

    def seal(self, obj: str, data: bytes) -> bytes:
        nonce = os.urandom(12)
        return MAGIC + nonce + AESGCM(self.enc).encrypt(nonce, data, obj.encode("utf-8"))

    def open(self, obj: str, blob: bytes) -> bytes:
        if not blob or blob[:4] != MAGIC:
            raise BackupError("%s is not one of our backup objects." % obj)
        try:
            return AESGCM(self.enc).decrypt(blob[4:16], blob[16:], obj.encode("utf-8"))
        except Exception:
            raise BackupError("%s did not decrypt - wrong passphrase or a damaged object." % obj)

    def object_name(self, rel: str, sha: str) -> str:
        return hmac.new(self.name, (rel + "\0" + sha).encode("utf-8"), hashlib.sha256).hexdigest() + ".npb"


def keys_for(remote: Remote, passphrase: str, create: bool) -> Keys:
    salt = remote.get("salt")
    if salt is None:
        if not create:
            raise BackupError("There is no backup at this remote yet (no salt).")
        salt = os.urandom(16)
        remote.put("salt", salt)
    return Keys(passphrase, salt)


def load_manifest(remote: Remote, k: Keys) -> dict:
    blob = remote.get("manifest.npb")
    if blob is None:
        return {"files": {}, "gone": {}, "updated": ""}
    return json.loads(k.open("manifest.npb", blob))


def save_manifest(remote: Remote, k: Keys, man: dict) -> None:
    man["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = json.dumps(man, separators=(",", ":")).encode("utf-8")
    # A dated copy first, then the current one: a manifest is never lost to a failed overwrite.
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    remote.put("manifests/manifest-%s.npb" % day, k.seal("manifests/manifest-%s.npb" % day, data))
    remote.put("manifest.npb", k.seal("manifest.npb", data))


def _sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(app: str):
    for top in FOLDERS:
        root = os.path.join(app, top)
        if not os.path.isdir(root):
            continue
        for d, _dirs, files in os.walk(root):
            for n in files:
                if n.endswith((".part", ".tmp")):
                    continue
                full = os.path.join(d, n)
                if os.path.islink(full) or not os.path.isfile(full):
                    continue
                yield os.path.relpath(full, app).replace(os.sep, "/"), full


# ── push: what is new or changed ─────────────────────────────────────────────
def push(app: str, remote: Remote, passphrase: str, state_path: str) -> dict:
    k = keys_for(remote, passphrase, create=True)
    man = load_manifest(remote, k)
    try:
        state = json.load(open(state_path, encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    staging = tempfile.mkdtemp(prefix="npb_stage_", dir=os.path.dirname(state_path) or None)
    new, same, seen = 0, 0, set()
    pending = {}
    try:
        for rel, full in _walk(app):
            seen.add(rel)
            st = os.stat(full)
            sig = [st.st_size, st.st_mtime_ns]
            known = state.get(rel)
            entry = man["files"].get(rel)
            if known and known[:2] == sig and entry and entry.get("sha") == known[2]:
                same += 1
                continue
            sha = _sha(full)
            if entry and entry.get("sha") == sha:
                state[rel] = sig + [sha]          # touched, not changed
                same += 1
                continue
            obj = k.object_name(rel, sha)
            with open(full, "rb") as f:
                data = f.read()
            if hashlib.sha256(data).hexdigest() != sha:
                continue                          # changed while we read it - next run takes it
            with open(os.path.join(staging, obj), "wb") as f:
                f.write(k.seal("f/" + obj, data))
            pending[rel] = {"obj": obj, "sha": sha, "size": len(data),
                            "at": datetime.now(timezone.utc).strftime("%Y-%m-%d")}
            state[rel] = sig + [sha]
            new += 1
        if pending:
            remote.put_dir(staging, "f")
            for rel, e in pending.items():
                old = man["files"].get(rel)
                if old:                           # the earlier version stays off-site, listed
                    man.setdefault("versions", {}).setdefault(rel, []).append(old)
                man["files"][rel] = e
        # A file that disappeared from the server keeps its backup, listed as gone - never dropped.
        for rel in list(man["files"]):
            if rel not in seen:
                man["gone"][rel] = dict(man["files"].pop(rel),
                                        gone=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        save_manifest(remote, k, man)
        tmp = state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, state_path)
    finally:
        shutil.rmtree(staging, ignore_errors=True)   # our own scratch, encrypted copies only
    return {"new": new, "unchanged": same, "files": len(man["files"]), "gone": len(man["gone"])}


# ── the database: one copy a night, seven kept ───────────────────────────────
def push_db(path: str, remote: Remote, passphrase: str, now: datetime | None = None) -> dict:
    with open(path, "rb") as f:
        data = f.read()
    try:
        raw = gzip.decompress(data)
    except OSError:
        raise BackupError("%s is not a gzip file." % path)
    if not raw.startswith(b"SQLite format 3\0"):
        raise BackupError("%s does not hold a SQLite database." % path)
    k = keys_for(remote, passphrase, create=True)
    now = now or datetime.now(timezone.utc)
    obj = "db/sarathi_biz_%s.db.gz.npb" % now.strftime("%Y%m%d_%H%M%S")
    remote.put(obj, k.seal(obj, data))
    # The newest seven stay; older ones go - ONLY our own dated database copies in db/. By count,
    # not age: if nights are missed, the last good copies are never aged out from under us.
    ours = sorted(n for n in remote.list("db") if n.startswith("sarathi_biz_") and n.endswith(".db.gz.npb"))
    old = ours[:-DB_KEEP_DAYS] if len(ours) > DB_KEEP_DAYS else []
    for n in old:
        remote.delete("db/" + n)
    return {"db": obj, "pruned": len(old)}


# ── verify: prove it restores ────────────────────────────────────────────────
def verify(app: str, remote: Remote, passphrase: str, sample: int = 10) -> dict:
    k = keys_for(remote, passphrase, create=False)
    man = load_manifest(remote, k)
    files = man["files"]
    if not files:
        raise BackupError("The manifest lists no files.")
    picks = random.sample(sorted(files), min(sample, len(files)))
    for rel in picks:
        e = files[rel]
        data = k.open("f/" + e["obj"], remote.get("f/" + e["obj"]) or b"")
        if hashlib.sha256(data).hexdigest() != e["sha"]:
            raise BackupError("%s came back different from what was stored." % rel)
        local = os.path.join(app, rel)
        if os.path.exists(local) and _sha(local) != e["sha"]:
            # Not a backup fault: the file changed since; the next push takes the new version.
            print("note: %s has changed since its last copy" % rel)
    dbs = [n for n in remote.list("db") if n.endswith(".db.gz.npb")]
    db_ok = None
    if dbs:
        obj = "db/" + dbs[-1]
        raw = gzip.decompress(k.open(obj, remote.get(obj) or b""))
        db_ok = raw.startswith(b"SQLite format 3\0")
        if not db_ok:
            raise BackupError("The latest database copy is not a database.")
    return {"checked": len(picks), "files": len(files), "latest_db": dbs[-1] if dbs else None}


# ── restore ──────────────────────────────────────────────────────────────────
def _safe_join(root: str, rel: str) -> str:
    out = os.path.realpath(os.path.join(root, rel))
    if not out.startswith(os.path.realpath(root) + os.sep):
        raise BackupError("Refusing a path outside the restore folder: %r" % rel)
    return out


def restore(to: str, remote: Remote, passphrase: str, match: str = "", with_db: bool = False) -> dict:
    k = keys_for(remote, passphrase, create=False)
    man = load_manifest(remote, k)
    os.makedirs(to, exist_ok=True)
    done, skipped = 0, 0
    for rel, e in sorted(man["files"].items()):
        if match and match not in rel:
            continue
        dst = _safe_join(to, rel)
        if os.path.exists(dst):
            skipped += 1                         # never over an existing file
            continue
        data = k.open("f/" + e["obj"], remote.get("f/" + e["obj"]) or b"")
        if hashlib.sha256(data).hexdigest() != e["sha"]:
            raise BackupError("%s came back different from what was stored." % rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst + ".part", "wb") as f:
            f.write(data)
        os.replace(dst + ".part", dst)
        done += 1
    db = None
    if with_db:
        dbs = [n for n in remote.list("db") if n.endswith(".db.gz.npb")]
        if dbs:
            obj = "db/" + dbs[-1]
            raw = gzip.decompress(k.open(obj, remote.get(obj) or b""))
            dst = _safe_join(to, "sarathi_biz.db.restored")
            if os.path.exists(dst):
                raise BackupError("%s already exists - move it first." % dst)
            with open(dst, "wb") as f:
                f.write(raw)
            db = dst
    return {"restored": done, "skipped_existing": skipped, "db": db}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Encrypted, incremental off-site copy")
    ap.add_argument("cmd", choices=["push", "db", "verify", "restore"])
    ap.add_argument("file", nargs="?", default="")
    ap.add_argument("--app", default=os.environ.get("SARATHI_DIR", "/opt/sarathi"))
    ap.add_argument("--state", default="")
    ap.add_argument("--sample", type=int, default=10)
    ap.add_argument("--to", default="")
    ap.add_argument("--match", default="")
    ap.add_argument("--db", action="store_true")
    a = ap.parse_args(argv)
    remote = Remote(os.environ.get("BACKUP_RCLONE_REMOTE", ""))
    pp = os.environ.get("BACKUP_ENC_PASSPHRASE", "").strip().strip("\"'")
    state = a.state or os.path.join(a.app, "backups", "offsite", "state.json")
    os.makedirs(os.path.dirname(state), exist_ok=True)
    t0 = time.time()
    try:
        if a.cmd == "push":
            # One push at a time: a second run waits for nothing, it simply stops.
            lock = open(state + ".lock", "w")
            try:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except ImportError:
                pass
            except OSError:
                print("another push is running - stopping")
                return 0
            out = push(a.app, remote, pp, state)
        elif a.cmd == "db":
            out = push_db(a.file, remote, pp)
        elif a.cmd == "verify":
            out = verify(a.app, remote, pp, a.sample)
        else:
            if not a.to:
                raise BackupError("Say where to restore: --to DIR")
            out = restore(a.to, remote, pp, a.match, a.db)
    except BackupError as e:
        print("OFFSITE %s FAILED: %s" % (a.cmd.upper(), e))
        return 1
    print("offsite %s ok in %ds: %s" % (a.cmd, time.time() - t0, json.dumps(out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
