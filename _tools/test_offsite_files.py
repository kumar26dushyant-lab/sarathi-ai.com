# -*- coding: utf-8 -*-
'''The encrypted, incremental off-site copy (deploy/offsite_files.py) - 3 Oct 2026.

Uses a plain folder as the "remote", so it runs anywhere. What it proves:
  - each file goes once; a second run sends nothing
  - a changed file is a NEW version and the old one stays; a deleted file keeps its backup
  - nothing readable off-site: contents are AES-256-GCM, names reveal nothing
  - an object swapped or damaged off-site is caught; the wrong passphrase gets nothing
  - restore gives back exactly what was stored, and never writes over a file
  - the database copy is checked before it goes, and only our own dated copies are pruned

    PYTHONPATH=. py -3.14 _tools/test_offsite_files.py
'''
import gzip
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "deploy"))
import offsite_files as of  # noqa: E402

FAILED = 0
PP = "correct horse battery staple 2026"   # a test passphrase, not a real one


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


def write(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)


base = tempfile.mkdtemp(prefix="offsite_")
app, rem_dir = os.path.join(base, "app"), os.path.join(base, "remote")
state = os.path.join(app, "backups", "offsite", "state.json")
os.makedirs(os.path.dirname(state))
write(os.path.join(app, "uploads", "nidaan-docs", "a1b2.pdf"), b"%PDF-1.4 RAMESH KUMAR discharge summary" * 50)
write(os.path.join(app, "uploads", "nidaan-docs", "c3d4.jpg"), os.urandom(20000))
write(os.path.join(app, "uploads", "photos", "staff", "face.png"), os.urandom(3000))
write(os.path.join(app, "generated_pdfs", "letter.pdf"), b"%PDF-1.4 letter")
write(os.path.join(app, "sarathi_biz.db"), b"not part of the file copy")
remote = of.Remote("dir:" + rem_dir)

print("\n-- first copy --")
r = of.push(app, remote, PP, state)
check("every file goes off-site", r["new"] == 4 and r["files"] == 4, r)
objs = os.listdir(os.path.join(rem_dir, "v1", "f"))
check("...as four objects", len(objs) == 4, objs)
check("the database file is not swept into the documents copy",
      not any("sarathi_biz" in k for k in of.load_manifest(remote, of.keys_for(remote, PP, False))["files"]))
blob_all = b"".join(open(os.path.join(rem_dir, "v1", "f", o), "rb").read() for o in objs)
check("nothing readable off-site: no file contents", b"RAMESH" not in blob_all and b"discharge" not in blob_all)
check("...and the names say nothing about the files", all(len(o) == 68 and o.endswith(".npb") for o in objs)
      and not any("a1b2" in o or "face" in o for o in objs), objs)
man_raw = open(os.path.join(rem_dir, "v1", "manifest.npb"), "rb").read()
check("the list of files is encrypted too", b"nidaan-docs" not in man_raw and man_raw[:4] == b"NPB1")

print("\n-- the next night --")
r = of.push(app, remote, PP, state)
check("a second run sends nothing", r["new"] == 0 and r["unchanged"] == 4, r)

doc = os.path.join(app, "uploads", "nidaan-docs", "a1b2.pdf")
write(doc, b"ENCRYPTED BY RANSOMWARE")
r = of.push(app, remote, PP, state)
check("a changed file goes as a NEW version", r["new"] == 1, r)
check("...and the old version is still off-site", len(os.listdir(os.path.join(rem_dir, "v1", "f"))) == 5)
man = of.load_manifest(remote, of.keys_for(remote, PP, False))
check("...listed, so it can be got back", len(man.get("versions", {}).get("uploads/nidaan-docs/a1b2.pdf", [])) == 1)

os.remove(os.path.join(app, "generated_pdfs", "letter.pdf"))
r = of.push(app, remote, PP, state)
check("a file deleted on the server keeps its backup, listed as gone", r["gone"] == 1
      and len(os.listdir(os.path.join(rem_dir, "v1", "f"))) == 5, r)

print("\n-- proving it restores --")
v = of.verify(app, remote, PP, sample=50)
check("verify downloads, decrypts and matches every sampled file", v["checked"] == 3, v)
try:
    of.verify(app, remote, "a different passphrase entirely", sample=50)
    bad = False
except of.BackupError:
    bad = True
check("the wrong passphrase gets nothing", bad)

out = os.path.join(base, "restored")
r = of.restore(out, remote, PP)
check("restore brings back every current file", r["restored"] == 3, r)
check("...exactly as stored", open(os.path.join(out, "uploads", "nidaan-docs", "c3d4.jpg"), "rb").read()
      == open(os.path.join(app, "uploads", "nidaan-docs", "c3d4.jpg"), "rb").read())
r = of.restore(out, remote, PP)
check("restoring again never writes over a file", r["restored"] == 0 and r["skipped_existing"] == 3, r)
try:
    of._safe_join(out, "../../etc/passwd")
    esc = False
except of.BackupError:
    esc = True
check("a path outside the restore folder is refused", esc)

print("\n-- damage off-site is caught --")
f_dir = os.path.join(rem_dir, "v1", "f")
# Damage objects the CURRENT list points at (names are random, so "the first two" may be old versions).
cur = sorted(e["obj"] for e in of.load_manifest(remote, of.keys_for(remote, PP, False))["files"].values())
a, b = os.path.join(f_dir, cur[0]), os.path.join(f_dir, cur[1])
da, db_ = open(a, "rb").read(), open(b, "rb").read()
open(a, "wb").write(db_)                       # swap two objects
try:
    of.verify(app, remote, PP, sample=50)
    caught = False
except of.BackupError:
    caught = True
open(a, "wb").write(da)
check("an object swapped for another does not decrypt", caught)
open(b, "wb").write(db_[:-1] + bytes([db_[-1] ^ 1]))   # flip one bit
try:
    of.verify(app, remote, PP, sample=50)
    caught = False
except of.BackupError:
    caught = True
open(b, "wb").write(db_)
check("a single damaged byte is caught", caught)

print("\n-- the database --")
dbp = os.path.join(base, "t.db")
c = sqlite3.connect(dbp); c.execute("CREATE TABLE t (x)"); c.commit(); c.close()
gz = dbp + ".gz"
open(gz, "wb").write(gzip.compress(open(dbp, "rb").read()))
now = datetime(2026, 10, 3, 2, 0, tzinfo=timezone.utc)
for d in range(10):
    of.push_db(gz, remote, PP, now=now - timedelta(days=9 - d))
left = os.listdir(os.path.join(rem_dir, "v1", "db"))
check("seven nightly database copies are kept, older ones go", len(left) == 7, sorted(left))
check("...and nothing outside the database folder was touched",
      len(os.listdir(os.path.join(rem_dir, "v1", "f"))) == 5 and os.path.exists(os.path.join(rem_dir, "v1", "manifest.npb")))
junk = os.path.join(base, "junk.gz")
open(junk, "wb").write(gzip.compress(b"hello"))
try:
    of.push_db(junk, remote, PP)
    refused = False
except of.BackupError:
    refused = True
check("a file that is not a database is refused before it goes", refused)
r = of.restore(os.path.join(base, "restored2"), remote, PP, with_db=True)
check("restore can bring back the latest database, as a separate file",
      r["db"] and open(r["db"], "rb").read().startswith(b"SQLite format 3\0"), r)

print("\n-- settings --")
try:
    of.Keys("short", b"0" * 16)
    weak = False
except of.BackupError:
    weak = True
check("a missing or short passphrase stops it", weak)
try:
    of.Remote("")
    nore = False
except of.BackupError:
    nore = True
check("no remote set stops it", nore)

shutil.rmtree(base, ignore_errors=True)
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
