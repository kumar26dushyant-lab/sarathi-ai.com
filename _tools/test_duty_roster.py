# -*- coding: utf-8 -*-
'''Bucket duty reaches someone who is actually there (founder, 30 Sep: "ensure bucket duty on
staff feature works properly").

What was wrong, and what these checks defend:
  * someone on a full day's approved leave still got the bucket's alerts - and because the list was
    not empty, the admins never heard either; now their cover gets them, or the admins do;
  * working from home and half days are not absence - they stay on duty;
  * archived staff showed as "On duty" on the roster screen;
  * an inactive staff member could be rostered;
  * on a fresh database the roster had no `duty` column at all.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_duty_roster.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="duty_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_buckets as bk                     # noqa: E402
bk.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    await db.init_db()
    await bk.ensure_seeded()
    today = nid._now_ist().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DBP) as c:
        for sid, name, status, deleted in ((1, "Asha", "active", None), (2, "Cover Person", "active", None),
                                           (3, "Gone", "inactive", "2026-09-01"), (4, "Home", "active", None),
                                           (5, "Half", "active", None)):
            await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status, "
                            "deleted_at) VALUES (?,?,?,?,'team_member',?,?)",
                            (sid, name, "s%d@example.invalid" % sid, "x", status, deleted))
        for sid in (1, 3, 4, 5):
            await c.execute("INSERT INTO nidaan_support_reps (staff_id, start_date, end_date, duty) "
                            "VALUES (?,?,?,'live_cases')", (sid, today, today))
        await c.execute("INSERT INTO nidaan_leave_requests (staff_id, start_date, end_date, status, "
                        "request_kind, cover_staff_id) VALUES (1,?,?,'approved','leave',2)", (today, today))
        await c.execute("INSERT INTO nidaan_leave_requests (staff_id, start_date, end_date, status, "
                        "request_kind) VALUES (4,?,?,'approved','wfh')", (today, today))
        await c.execute("INSERT INTO nidaan_leave_requests (staff_id, start_date, end_date, status, "
                        "request_kind, half_period) VALUES (5,?,?,'approved','leave','am')", (today, today))
        await c.commit()

    ids = sorted(await nid.on_duty_rep_ids("live_cases"))
    check("someone on a full day's leave is off duty, and their cover takes it", 1 not in ids and 2 in ids, ids)
    check("working from home stays on duty", 4 in ids, ids)
    check("a half day stays on duty", 5 in ids, ids)
    check("archived staff are never on duty", 3 not in ids, ids)

    rows = {r["staff_id"]: r for r in await nid.list_support_reps("live_cases")}
    check("the roster screen does not show archived staff as on duty", rows[3]["on_duty"] is False, rows[3])
    check("...and says who is on leave", rows[1]["on_leave"] is True and rows[1]["on_duty"] is False, rows[1])
    try:
        await nid.add_support_rep(3, today, today, duty="live_cases")
        check("an inactive staff member cannot be rostered", False)
    except ValueError as e:
        check("an inactive staff member cannot be rostered", str(e) == "bad_staff", str(e))

    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_leave_requests SET cover_staff_id=NULL WHERE staff_id=1")
        await c.execute("DELETE FROM nidaan_support_reps WHERE staff_id IN (4,5)")
        await c.commit()
    check("with nobody left, the list is empty - so the admins get it",
          await nid.on_duty_rep_ids("live_cases") == [], await nid.on_duty_rep_ids("live_cases"))


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
