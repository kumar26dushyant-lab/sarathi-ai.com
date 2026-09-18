# -*- coding: utf-8 -*-
"""Run every journey against a COPY of live data. Exit non-zero if any cannot complete.

    python -m journeys.run [--app DIR] [--db PATH] [--json] [--quiet]

That exit code is the whole point: a deploy whose journeys cannot complete does not go live.

Two refusals are built in, and neither can be switched off from the command line, because both
guard against the mistakes that actually happened rather than imagined ones:

  1. It will not start unless NIDAAN_NO_OUTBOUND=1. A test of mine sent three real emails to a
     stranger on 18 Sep because that guard was disabled to observe transport selection.
  2. It will not start if ANY loaded module still points at the live database. Every biz_nidaan_*
     module copies db.DB_PATH at IMPORT time, so one late import silently writes to production.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile

DEFAULT_APP = "/opt/sarathi"
DEFAULT_DB = "/opt/sarathi/sarathi_biz.db"


def _die(msg: str) -> "NoReturn":       # noqa: F821
    print("journeys: %s" % msg, file=sys.stderr)
    raise SystemExit(2)


def _copy_db(src: str) -> str:
    if not os.path.exists(src):
        _die("no database at %s" % src)
    tmp = tempfile.mkdtemp(prefix="journeys-")
    dst = os.path.join(tmp, "journey.db")
    shutil.copy(src, dst)
    for ext in ("-wal", "-shm"):
        if os.path.exists(src + ext):
            shutil.copy(src + ext, dst + ext)
    return dst


def _assert_no_live_db(live: str, copy: str) -> None:
    """Nothing loaded may still be pointing at production."""
    live_real = os.path.realpath(live)
    offenders = []
    for name, mod in list(sys.modules.items()):
        p = getattr(mod, "DB_PATH", None)
        if isinstance(p, str) and p and os.path.realpath(p) == live_real:
            offenders.append(name)
    if offenders:
        _die("these modules still point at the LIVE database, refusing to run: %s"
             % ", ".join(sorted(offenders)))


async def _subjects(db_path: str) -> dict:
    """Real rows to exercise, so a journey is never a toy."""
    import aiosqlite
    out = {"claim_id": None, "branch_row": None}
    async with aiosqlite.connect(db_path) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT cl.claim_id FROM nidaan_claims cl JOIN nidaan_claimant_portal p "
            "ON p.claim_id = cl.claim_id ORDER BY cl.claim_id DESC LIMIT 1")).fetchone()
        if not r:
            r = await (await c.execute(
                "SELECT claim_id FROM nidaan_claims ORDER BY claim_id DESC LIMIT 1")).fetchone()
        out["claim_id"] = int(dict(r)["claim_id"]) if r else None
        b = await (await c.execute(
            "SELECT branch_code, COALESCE(contact_email,'') AS contact_email, "
            "COALESCE(contact_phone,'') AS contact_phone FROM nidaan_branches "
            "WHERE status='active' AND COALESCE(contact_email,'')!='' LIMIT 1")).fetchone()
        out["branch_row"] = dict(b) if b else None
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(prog="journeys.run")
    ap.add_argument("--app", default=DEFAULT_APP, help="application code to test")
    ap.add_argument("--overlay", default="", help="directory of CHANGED modules, tried before "
                                                  "--app (how a build is checked before deploy)")
    ap.add_argument("--db", default=DEFAULT_DB, help="live database to copy")
    ap.add_argument("--json", action="store_true", help="print the tally as JSON")
    ap.add_argument("--quiet", action="store_true", help="only show failing steps")
    args = ap.parse_args()

    if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
        _die("refusing to run with outbound enabled. Set NIDAAN_NO_OUTBOUND=1.")

    copy = _copy_db(args.db)
    # BEFORE any application import: biz_nidaan reads this env var, and every other module
    # copies db.DB_PATH at import time.
    os.environ["DB_PATH"] = copy

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # Last inserted wins, so build the list back-to-front: the app, then the overlay on top of it.
    # The overlay is FORCED to the front even if the path is already on sys.path - it usually is,
    # because the journeys package normally lives in the same tree as the code being tested, and
    # skipping it there silently tests the deployed code instead of the change. That exact mistake
    # cost a run on 19 Sep and reported a fix as broken.
    for p in (here, args.app):
        if p and p not in sys.path:
            sys.path.insert(0, p)
    if args.overlay:
        ov = os.path.abspath(args.overlay)
        sys.path = [p for p in sys.path if os.path.abspath(p) != ov]
        sys.path.insert(0, ov)
    if os.path.isdir(args.app):
        os.chdir(args.app)

    import biz_database as db
    db.DB_PATH = copy

    import biz_nidaan as nidaan
    nidaan.DB_PATH = copy
    import biz_nidaan_claimant as claimant
    claimant.DB_PATH = copy
    import biz_nidaan_claim_access as access
    access.DB_PATH = copy
    import biz_nidaan_buckets as buckets
    buckets.DB_PATH = copy
    import biz_nidaan_doc_request as docreq
    docreq.DB_PATH = copy
    import biz_auth as auth

    _assert_no_live_db(args.db, copy)

    from journeys import paths
    from journeys.harness import render

    ctx = dict(await _subjects(copy))
    if not ctx["claim_id"]:
        _die("this database has no claims to exercise")
    ctx.update({"db": copy, "nidaan": nidaan, "claimant": claimant, "access": access,
                "buckets": buckets, "docreq": docreq, "auth": auth})

    print("journeys — %d to run against a copy of %s" % (len(paths.ALL), os.path.basename(args.db)))
    print("code under test: %s\n" % args.app)

    results = [await j.run(ctx) for j in paths.ALL]
    tally = render(results, verbose=not args.quiet)
    if args.json:
        print(json.dumps(tally))

    shutil.rmtree(os.path.dirname(copy), ignore_errors=True)
    return 1 if tally["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
