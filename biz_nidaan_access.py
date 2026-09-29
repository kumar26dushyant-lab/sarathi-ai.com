# -*- coding: utf-8 -*-
"""Is this person still allowed in? One answer for every NidaanPartner login.

A signed token only proves who someone WAS when they logged in. Founder, 30 Sep: "once access
changed or any user of nidaanpartner.com deleted or disabled they should not have access for
anything." So every request also asks the database whether the account, the Authorized Partner or
the staff member is still open - read per request, remembered for 30 seconds per worker.

  acct    - a subscriber / customer account: open while 'active', and while 'deletion_pending'
            (the grace window in which they can undo the deletion). Any other status - suspended,
            deleted, merged, or one nobody has thought of yet - is shut. An allowlist, not a list
            of bans, so a new status fails closed.
  branch  - an Authorized Partner: open only while 'active'.
  staff   - a staff member: open only while 'active' and not archived.

Fails CLOSED. A row that cannot be read is "no" - the request could not have done its work
anyway - and that "no" is not remembered, so the next request simply asks again. (The staff check
used to let everyone in on a read error.)
"""
from __future__ import annotations

import logging
import sqlite3
import time

logger = logging.getLogger("nidaan.access")

# None = the database biz_nidaan uses (it honours the DB_PATH environment variable), read at
# call time - the same file the old staff check read. Tests point this at their own copy.
DB_PATH = None
TTL = 30.0
ACCT_OPEN = ("active", "deletion_pending")
_cache: dict = {}


def clear() -> None:
    _cache.clear()


def still_open(kind: str, key) -> bool:
    if key in (None, "") or kind not in ("acct", "branch", "staff"):
        return False
    now = time.monotonic()
    hit = _cache.get((kind, key))
    if hit and (now - hit[1]) < TTL:
        return hit[0]
    try:
        if DB_PATH:
            path = DB_PATH
        else:
            import biz_nidaan as _n
            path = _n.DB_PATH
        conn = sqlite3.connect(path, timeout=3)
        try:
            if kind == "acct":
                row = conn.execute("SELECT status, deleted_at FROM nidaan_accounts "
                                   "WHERE account_id=?", (int(key),)).fetchone()
                ok = bool(row) and row[1] is None and (row[0] or "active") in ACCT_OPEN
            elif kind == "branch":
                row = conn.execute("SELECT status FROM nidaan_branches WHERE branch_code=?",
                                   (str(key).strip().upper(),)).fetchone()
                ok = bool(row) and row[0] == "active"
            else:
                row = conn.execute("SELECT status, deleted_at FROM nidaan_staff WHERE staff_id=?",
                                   (int(key),)).fetchone()
                ok = bool(row) and row[1] is None and row[0] == "active"
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        logger.warning("access re-check failed (%s): %s", kind, type(e).__name__)
        return False
    _cache[(kind, key)] = (ok, now)
    return ok
