"""An alarm that is still true is said once, not 95 times. And a WORSE one is never held.

On 22 Sep the founder's inbox carried the same two alarms 95 and 44 times in a single day, word
for word. The dangerous way to fix that is a blanket "one an hour": it would hold the alarm that
says two subsystems are down behind the one that said one was.

So the test that matters most here is not "does it hold a repeat" - it is "does a CHANGED alarm
still go straight through". Both are checked, against a copy of the live database.

    NIDAAN_NO_OUTBOUND=1 python3 _tools/test_alarm_repeat.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

LIVE = "/opt/sarathi/sarathi_biz.db"
db_path = os.path.join(tempfile.mkdtemp(prefix="al_"), "copy.db")
shutil.copy(LIVE, db_path)
for e in ("-wal", "-shm"):
    if os.path.exists(LIVE + e):
        shutil.copy(LIVE + e, db_path + e)

os.environ["DB_PATH"] = db_path
OV = os.path.dirname(os.path.abspath(__file__))
sys.path = [q for q in sys.path if os.path.abspath(q) not in (OV, "/opt/sarathi")]
sys.path.insert(0, "/opt/sarathi")
sys.path.insert(0, os.path.dirname(OV))

import aiosqlite                                       # noqa: E402
import biz_database as db; db.DB_PATH = db_path        # noqa: E402,E702
import biz_nidaan as _n; _n.DB_PATH = db_path          # noqa: E402,E702
import biz_nidaan_alarm_policy as ap                   # noqa: E402

assert ap.__file__.startswith(os.path.dirname(OV)), "ABORT: testing the DEPLOYED module"

P = F = 0


def check(label, ok, detail=""):
    global P, F
    if ok:
        P += 1
        print("  PASS  " + label)
    else:
        F += 1
        print("  FAIL  " + label + (("  " + str(detail)) if detail else ""))


WEBHOOK = ("\U0001f6d1 PAYMENT — guardian",
           "No Razorpay webhook has reached us in 24 hours. Check the webhook URL and secret.")


async def main():
    print("\nThe two alarms that flooded 22 Sep\n")

    # 1. said once
    held = await ap._repeat_held("payment.guardian", *WEBHOOK)
    check("the first time, it goes out", held == "", held)

    # 2. and then held, however many times the sweep runs
    sent_again = 0
    for _ in range(12):
        if await ap._repeat_held("payment.guardian", *WEBHOOK) == "":
            sent_again += 1
    check("twelve more sweeps send NOTHING (was: twelve more emails)", sent_again == 0,
          "%d got through" % sent_again)

    print("\nBut a CHANGED alarm is never held behind the older, milder one\n")
    worse = await ap._repeat_held(
        "health.subsystem", "\U0001f6a8 Health Alert",
        "2 critical issue(s) detected: WhatsApp Cloud API, Email Radar")
    check("a different body goes straight through", worse == "", worse)
    milder = await ap._repeat_held(
        "health.subsystem", "\U0001f6a8 Health Alert", "1 critical issue(s) detected")
    check("and so does a different count again", milder == "", milder)

    print("\nThe hold is a wait, not a silence\n")
    # Move the remembered send back beyond the window and it speaks again.
    import hashlib
    d = hashlib.sha256(("payment.guardian|%s|%s" % WEBHOOK).encode()).hexdigest()[:24]
    async with aiosqlite.connect(db_path) as c:
        await c.execute(
            "UPDATE nidaan_alert_dedup SET last_at=datetime('now','-7 hours') WHERE alert_key=?",
            ("alarmrep:" + d,))
        await c.commit()
    again = await ap._repeat_held("payment.guardian", *WEBHOOK)
    check("after the window it says it again", again == "", again)

    print("\nHeld repeats are counted, not thrown away\n")
    async with aiosqlite.connect(db_path) as c:
        c.row_factory = aiosqlite.Row
        row = await (await c.execute(
            "SELECT sent_count FROM nidaan_alert_dedup WHERE alert_key=?",
            ("alarmrep:" + d,))).fetchone()
    check("the row remembers how often it fired", row and int(row["sent_count"]) >= 13,
          dict(row) if row else None)

    print("\nThe founder can turn the hold off without a deploy\n")
    await _n.set_ops_setting(ap.REPEAT_HOURS_SETTING, "0")
    off = await ap._repeat_held("payment.guardian", *WEBHOOK)
    check("0 hours means every alarm goes out, as before", off == "", off)
    await _n.set_ops_setting(ap.REPEAT_HOURS_SETTING, "")

    print("\nAnd an alarm it cannot remember is DELIVERED, never swallowed\n")
    _real = db.DB_PATH
    db.DB_PATH = "/nonexistent/path/does-not-exist.db"
    try:
        broken = await ap._repeat_held("payment.guardian", "x", "y")
    finally:
        db.DB_PATH = _real
    check("a broken table delivers rather than hides", broken == "", broken)

    print("\n%d passed, %d failed" % (P, F))
    return 1 if F else 0


sys.exit(asyncio.run(main()))
