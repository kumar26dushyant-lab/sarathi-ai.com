# -*- coding: utf-8 -*-
'''Every morning: yesterday's payments at Razorpay against our books - and it says so.

Founder, 29 Sep: "our intelligent bot should confirm payment from razorpay ledger and update
everyday or at schedule time". The guardian speaks only when something is wrong; this is the
message that says the numbers were checked and matched - or exactly what did not.

What these checks defend:

  * matched BY PAYMENT ID, so two windows cut at different moments cannot fake a mismatch;
  * a payment taken at Razorpay and missing from our books is NAMED, as is an amount that differs;
  * Sarathi's payments (same Razorpay account) and failed attempts are not counted;
  * a payment recorded by hand is listed as such - Razorpay cannot vouch for it;
  * Razorpay unreachable is said plainly, never reported as "all match";
  * one report per day, whatever restarts - and a crash before sending repeats it, never skips it.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_pay_daily.py
'''
import asyncio
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_root = tempfile.mkdtemp(prefix="paydaily_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_nidaan as nid                            # noqa: E402
import biz_nidaan_pay_daily as pd                   # noqa: E402
import biz_nidaan_notifications as nn               # noqa: E402

nid.DB_PATH = db.DB_PATH

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_payments (id INTEGER PRIMARY KEY AUTOINCREMENT, razorpay_payment_id TEXT,
    total_paise INTEGER, source TEXT, verified INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_ops_settings (key TEXT PRIMARY KEY, value TEXT, updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
INSERT INTO nidaan_payments (razorpay_payment_id, total_paise, source, created_at) VALUES
    ('pay_AAAAAA111111', 58882, 'subscription', '2026-09-28 04:00:00'),
    ('pay_BBBBBB222222', 58882, 'branch_l2',    '2026-09-28 06:00:00'),
    ('pay_CCCCCC333333', 50000, 'branch_l2',    '2026-09-28 07:00:00');
INSERT INTO nidaan_payments (razorpay_payment_id, total_paise, source, verified, created_at) VALUES
    ('', 49900, 'per_claim_review', 0, '2026-09-28 08:00:00');
"""

DAY = date(2026, 9, 28)


def pay(pid, amount, status="captured", product="nidaan-subscription"):
    return {"id": pid, "amount": amount, "status": status, "notes": {"product": product}}


TOLD = []


async def f_notify(ids, subject, body, event_key="", email=True, **kw):
    TOLD.append({"ids": list(ids), "subject": subject, "body": body, "key": event_key,
                 "email": email})
    return len(ids)


async def f_admins():
    return [{"staff_id": 1}, {"staff_id": 2}]


nn.notify_staff_inapp = f_notify
nn._super_admin_staff = f_admins


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    print("\nThe IST day\n")
    frm, to, ua, ub = pd.day_bounds(DAY)
    check("an IST day starts at 18:30 UTC the evening before",
          ua == "2026-09-27 18:30:00" and ub == "2026-09-28 18:30:00", (ua, ub))

    print("\nAll matching\n")
    good = [pay("pay_AAAAAA111111", 58882), pay("pay_BBBBBB222222", 58882),
            pay("pay_CCCCCC333333", 50000),
            pay("pay_SARATHI00001", 99900, product="sarathi-ai-crm"),
            pay("pay_FAILED000001", 58882, status="failed")]
    r = await pd.check_day(DAY, payments=good)
    check("matched by payment id", r["match"] and r["count"] == 3 and r["booked"] == 3, r)
    check("Sarathi's payments and failed attempts are not counted",
          r["total_paise"] == 58882 * 2 + 50000, r["total_paise"])
    check("a payment recorded by hand is listed as such", r["by_hand"] == [(49900, "per_claim_review")],
          r["by_hand"])
    subj, body = pd.message(r)
    check("the message says it matched", "all match" in subj, subj)
    check("...with counts and money in rupees", "Rs 1,677.64" in body and "3 payment(s)" in body,
          body)
    check("...by type", "Level-2 fee 2" in body and "Subscription 1" in body, body)
    check("...and the hand-recorded one", "Recorded by hand" in body, body)

    print("\nSomething does not match\n")
    bad = good + [pay("pay_MISSING00042", 58882)]
    bad[1] = pay("pay_BBBBBB222222", 60000)
    r = await pd.check_day(DAY, payments=bad)
    check("a payment taken at Razorpay and missing from our books is named",
          not r["match"] and [m["id"] for m in r["missing"]] == ["pay_MISSING00042"], r)
    check("an amount that differs is named",
          [m["id"] for m in r["differs"]] == ["pay_BBBBBB222222"], r["differs"])
    subj, body = pd.message(r)
    check("the message says it does NOT match, and what",
          "does not match" in subj and "NOT in our books" in body and "Amount differs" in body,
          (subj, body))
    check("...naming the payment by its last digits, not the full id",
          "00042" in body and "pay_MISSING00042" not in body, body)

    print("\nRazorpay unreachable\n")
    r = await pd.check_day(DAY, payments=[], ok=False)
    subj, body = pd.message(r)
    check("never reported as 'all match'", not r["match"] and "could not reach" in subj, subj)

    print("\nOnce a day\n")
    TOLD.clear()

    async def f_day(day):
        return good, True
    pd.razorpay_day = f_day
    res = await pd.run_daily(date(2026, 9, 29))
    check("it reports yesterday to the super admins, on Telegram and the bell, not email",
          res.get("day") == "2026-09-28" and TOLD and TOLD[0]["ids"] == [1, 2]
          and TOLD[0]["email"] is False and TOLD[0]["key"] == "payment.daily_check", (res, TOLD))
    res2 = await pd.run_daily(date(2026, 9, 29))
    check("a second run the same day (a restart) sends nothing",
          res2.get("skipped") and len(TOLD) == 1, (res2, len(TOLD)))
    TOLD.clear()

    async def f_boom(*a, **k):
        raise RuntimeError("telegram down")
    nn.notify_staff_inapp = f_boom
    try:
        await pd.run_daily(date(2026, 9, 30))
    except RuntimeError:
        pass
    nn.notify_staff_inapp = f_notify
    res3 = await pd.run_daily(date(2026, 9, 30))
    check("a failure before sending repeats the report next time, never skips it",
          res3.get("day") == "2026-09-29" and len(TOLD) == 1, (res3, TOLD))

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
