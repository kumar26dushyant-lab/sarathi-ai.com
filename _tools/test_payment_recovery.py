"""If the webhook never delivers, does the guardian get the money into our books by itself?

23 Sep: a customer paid Rs 588.82 by UPI. Razorpay captured it. Our system had nothing - no
ledger row, no subscription, "PAID (LTV) Rs 0" on his own account page. Two failures had to
coincide and both did: a UPI payment switches app, so the browser that was meant to call verify
is gone by the time the money moves; and the Razorpay webhook had not delivered for twelve hours.

The guardian already DETECTED this ("Money taken, not in our ledger") and did nothing about it,
which needs a person awake to be worth anything.

This deletes the recovered row on a COPY of the live database and runs the real reconcile against
the real Razorpay account, which must put it back.

    NIDAAN_NO_OUTBOUND=1 python3 _tools/test_payment_recovery.py
"""
import asyncio
import os
import shutil
import sys
import tempfile

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

LIVE = "/opt/sarathi/sarathi_biz.db"
PAY = "pay_TfPq2skEiSuArv"
ACCOUNT = 157

db = os.path.join(tempfile.mkdtemp(prefix="pg_"), "copy.db")
shutil.copy(LIVE, db)
for e in ("-wal", "-shm"):
    if os.path.exists(LIVE + e):
        shutil.copy(LIVE + e, db + e)

os.environ["DB_PATH"] = db
OV = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(OV)
sys.path = [q for q in sys.path if os.path.abspath(q) not in (OV, "/opt/sarathi")]
sys.path.insert(0, "/opt/sarathi")
sys.path.insert(0, ROOT)

import aiosqlite                                       # noqa: E402
import biz_database as _db; _db.DB_PATH = db           # noqa: E402,E702
import biz_nidaan as _n; _n.DB_PATH = db               # noqa: E402,E702
import biz_nidaan_pay_guard as pg; pg.DB_PATH = db     # noqa: E402,E702

assert pg.__file__.startswith(ROOT), "ABORT: testing the DEPLOYED guard, not the change"

P = F = 0


def check(label, ok, detail=""):
    global P, F
    if ok:
        P += 1
        print("  PASS  " + label)
    else:
        F += 1
        print("  FAIL  " + label + (("  " + str(detail)) if detail else ""))


async def rows():
    async with aiosqlite.connect(db) as c:
        r = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_payments WHERE razorpay_payment_id=?", (PAY,))).fetchone()
        s = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_subscriptions WHERE account_id=?", (ACCOUNT,))).fetchone()
    return r[0], s[0]


async def main():
    print("\nPut the copy back into the broken state\n")
    async with aiosqlite.connect(db) as c:
        await c.execute("DELETE FROM nidaan_payments WHERE razorpay_payment_id=?", (PAY,))
        await c.execute("DELETE FROM nidaan_subscriptions WHERE account_id=?", (ACCOUNT,))
        await c.commit()
    n, s = await rows()
    check("the payment is gone from our books", (n, s) == (0, 0), (n, s))

    print("\nRun the guardian against the REAL Razorpay account\n")
    findings = []
    ran = set()
    await pg._check_reconcile(findings, ran)
    keys = [f.get("key", "") for f in findings]
    print("     findings: %s" % (", ".join(k[:46] for k in keys) or "none"))

    n, s = await rows()
    check("the payment is back in the ledger", n == 1, n)
    check("and the subscription is active again", s == 1, s)
    check("it reported the recovery rather than doing it silently",
          any(k.startswith("recovered_payment:") for k in keys), keys)
    check("and did NOT leave a 'money taken, not recorded' alarm standing",
          not any(k.startswith("paid_not_recorded:%s" % PAY) for k in keys), keys)

    print("\nRunning it again must not take the money twice\n")
    findings2 = []
    await pg._check_reconcile(findings2, set())
    n2, s2 = await rows()
    check("still exactly one ledger row", n2 == 1, n2)
    check("still exactly one subscription", s2 == 1, s2)
    check("and nothing is reported the second time",
          not any(str(k.get("key", "")).startswith(("recovered_payment:", "paid_not_recorded:"))
                  for k in findings2),
          [k.get("key") for k in findings2])

    print("\n%d passed, %d failed" % (P, F))
    return 1 if F else 0


sys.exit(asyncio.run(main()))
