# -*- coding: utf-8 -*-
'''What a payment must cost - one answer, checked before every charge and again after.

Founder, 29 Sep: "how can we prevent all payment endpoints to talk same rather different amount?
... is our payment bot watching all payments carefully before they are initiating?"

What these checks defend:

  * one price for each purpose, from the shared rules, with GST on top - never a guess;
  * a wrong amount is REFUSED before Razorpay is asked, and the super admins are told;
  * a price that cannot be worked out refuses too (fail closed);
  * EVERY function in the code that asks Razorpay for money runs the check - a new payment path
    that forgets it fails this test, which is the only way "all endpoints in sync" survives the
    next person adding one;
  * after the money moves, the guardian flags a payment whose base or GST is not the price.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_pricing.py
'''
import ast
import asyncio
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_root = tempfile.mkdtemp(prefix="pricing_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_nidaan as nid                            # noqa: E402
import biz_nidaan_pricing as pr                     # noqa: E402
import biz_nidaan_notifications as nn               # noqa: E402
import biz_nidaan_pay_guard as pg                   # noqa: E402

nid.DB_PATH = pg.DB_PATH = db.DB_PATH

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SETTINGS = {"gst_enabled": "1", "gst_rate": "18", "gst_home_state": "",
            "review_fee_low": "499", "review_fee_high": "2000", "review_fee_threshold": "1000000",
            "branch_l2_fee": "499", "branch_charge_policy": "l2_only"}


async def f_setting(key, default=None):
    return SETTINGS.get(key, default)


async def f_plan(plan):
    return {"silver": {"price_paise": 49900, "active": 1}}.get(plan)


async def f_l2(claim_id):
    return {"fee": 2000 if claim_id == 9 else 499, "charge_required": True}


TOLD = []


async def f_notify(ids, subject, body, event_key="", email=True, **kw):
    TOLD.append({"subject": subject, "body": body, "key": event_key})
    return len(ids)


async def f_admins():
    return [{"staff_id": 1}]


nid.get_ops_setting = f_setting
nid.get_plan_cfg = f_plan
nid.branch_l2_fee_for_claim = f_l2
nn.notify_staff_inapp = f_notify
nn._super_admin_staff = f_admins


async def main():
    print("\nOne price per purpose, GST on top\n")
    e = await pr.expected(pr.L2_FEE, claim_id=5)
    check("Level-2 fee: Rs 499 + 18% = Rs 588.82", e["total_paise"] == 58882, e)
    e = await pr.expected(pr.L2_FEE, claim_id=9)
    check("...the higher tier for a large claim: Rs 2000 + 18% = Rs 2360", e["total_paise"] == 236000, e)
    e = await pr.expected(pr.REVIEW_FEE, disputed_amount=200000)
    check("review fee below the threshold: Rs 588.82", e["total_paise"] == 58882, e)
    e = await pr.expected(pr.REVIEW_FEE, disputed_amount=5000000)
    check("review fee above the threshold: Rs 2360", e["total_paise"] == 236000, e)
    e = await pr.expected(pr.SUBSCRIPTION, plan="silver")
    check("a plan at its configured price: Silver Rs 588.82", e["total_paise"] == 58882, e)
    SETTINGS["gst_enabled"] = "0"
    e = await pr.expected(pr.L2_FEE, claim_id=5)
    check("GST switched off: the base alone", e["total_paise"] == 49900, e)
    SETTINGS["gst_enabled"] = "1"

    print("\nWhat cannot be priced is not charged\n")
    for label, call in (("an unknown purpose", pr.expected("free_money")),
                        ("a Level-2 fee with no claim", pr.expected(pr.L2_FEE)),
                        ("a plan with no price", pr.expected(pr.SUBSCRIPTION, plan="nope")),
                        ("a custom link with no amount", pr.expected(pr.CUSTOM))):
        try:
            await call
            check(label + " is refused", False)
        except pr.PriceMismatch:
            check(label + " is refused", True)

    print("\nThe guard before every charge\n")
    TOLD.clear()
    await pr.guard(pr.L2_FEE, 58882, claim_id=5)
    check("the right amount passes, silently", not TOLD, TOLD)
    try:
        await pr.guard(pr.L2_FEE, 49900, claim_id=5)
        check("a charge WITHOUT GST is refused", False)
    except pr.PriceMismatch:
        check("a charge WITHOUT GST is refused", True)
    check("...and the super admins are told what was stopped",
          TOLD and TOLD[0]["key"] == "payment.price_guard" and "588.82" in TOLD[0]["body"]
          and "499" in TOLD[0]["body"], TOLD)
    TOLD.clear()

    async def boom(*a, **k):
        raise RuntimeError("db gone")
    nid.branch_l2_fee_for_claim = boom
    try:
        await pr.guard(pr.L2_FEE, 58882, claim_id=5)
        check("a price that cannot be checked is refused (fail closed)", False)
    except pr.PriceMismatch:
        check("a price that cannot be checked is refused (fail closed)", True)
    nid.branch_l2_fee_for_claim = f_l2

    print("\nEvery function that asks Razorpay for money runs the check\n")
    # Kept on purpose, each with its reason. Anything else that charges must be guarded.
    EXEMPT = {
        "_create_rzp_payment_link": "the wrapper itself - its callers are checked",
        "_send_customer_retry_link": "re-offers the exact amount of a failed, already-guarded attempt",
        "ensure_nidaan_plans": "no callers (checked below) - kept only as history",
    }
    charging = re.compile(r'\.post\(\s*f?"https://api\.razorpay\.com/v1/(orders|subscriptions|plans)"')
    unguarded, seen = [], []
    for path in ("sarathi_biz.py", "biz_nidaan.py"):
        src = io.open(path, encoding="utf-8").read()
        tree = ast.parse(src)
        lines = src.splitlines()          # once: get_source_segment re-splits the file per call
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = "\n".join(lines[node.lineno - 1:node.end_lineno])
            asks = bool(charging.search(body)) or ("_create_rzp_payment_link(" in body
                                                  and node.name != "_create_rzp_payment_link")
            if not asks:
                continue
            seen.append(node.name)
            if node.name in EXEMPT:
                continue
            if "_price_ok(" not in body and "_pr.guard(" not in body:
                unguarded.append("%s:%s" % (path, node.name))
    check("the charging functions are found (the scan is not blind)", len(seen) >= 10, seen)
    check("every one of them runs the price check", not unguarded, unguarded)
    both = io.open("sarathi_biz.py", encoding="utf-8").read() + io.open("biz_nidaan.py", encoding="utf-8").read()
    check("the exempt ensure_nidaan_plans really has no callers",
          len(re.findall(r"ensure_nidaan_plans\(", both)) == 1)

    print("\nAfter the money moves: the guardian checks the price\n")
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript("""
        CREATE TABLE nidaan_payments (pay_id INTEGER PRIMARY KEY, source TEXT, claim_id INTEGER,
            account_id INTEGER, plan TEXT, base_paise INTEGER, gst_paise INTEGER,
            total_paise INTEGER, status TEXT DEFAULT 'captured',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO nidaan_payments (pay_id, source, claim_id, base_paise, gst_paise, total_paise)
            VALUES (1, 'branch_l2', 5, 49900, 8982, 58882),
                   (2, 'branch_l2', 5, 49900, 0, 49900),
                   (3, 'per_claim_review', NULL, 45000, 8100, 53100);
        INSERT INTO nidaan_payments (pay_id, source, account_id, plan, base_paise, gst_paise, total_paise)
            VALUES (4, 'subscription', 7, 'silver', 49900, 9000, 58900),
                   (5, 'subscription_renewal', 7, 'silver', 49900, 100, 50000);
        """)
        await c.commit()

    async def f_since():
        return "2000-01-01 00:00:00"
    pg._since = f_since
    findings, ran = [], set()
    await pg._check_prices(findings, ran)
    keys = {f["key"] for f in findings}
    check("a correct payment raises nothing", "price:1" not in keys, keys)
    check("a Level-2 fee taken WITHOUT GST is flagged", "price:2" in keys, keys)
    check("a review at a base nobody configured is flagged", "price:3" in keys, keys)
    check("GST rounded the old way (Rs 90 not Rs 89.82) is flagged", "price:4" in keys, keys)
    check("a renewal is not price-checked (its mandate is grandfathered)", "price:5" not in keys, keys)
    check("the check reports that it ran", "price" in ran)

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
