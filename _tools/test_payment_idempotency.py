# -*- coding: utf-8 -*-
'''One charge, one ledger row - whichever road it arrives by.

Found 26 Sep 2026. A subscription activation reaching us by webhook keyed itself on the Razorpay
PAYMENT id; the same activation reaching us by api_fetch keyed itself on the SUBSCRIPTION id.
record_payment() is idempotent on the key, so neither found the other and both inserted.
Fourteen subscriptions carried two rows each. Revenue read Rs 11,776 too high - 13.6% - while
Razorpay reported paid_count=1 for every one of them. Nobody was charged twice; we counted once
too often.

The check that matters most here is the one for the fix that was NOT made: changing the key shape
would have left every existing row unmatched, so the next late webhook would have written a
THIRD row. The keys therefore stay exactly as they are and the existence check got smarter - and
that is asserted, by writing a row the old way and then arriving the other way.

    py -3.14 _tools/test_payment_idempotency.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite                 # noqa: E402
import biz_database as db        # noqa: E402
import biz_nidaan as nidaan      # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="payidem-"), "t.db")
db.DB_PATH = DB
nidaan.DB_PATH = DB

SUB = "sub_TbrKgjAlHTEnv0"
PAY = "pay_TbrKtEao6fxoXf"


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def rows(**where):
    q = "SELECT pay_id, dedup_key, source, total_paise FROM nidaan_payments"
    conds, args = [], []
    for k, v in where.items():
        conds.append("%s=?" % k)
        args.append(v)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    async with aiosqlite.connect(DB) as c:
        c.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await c.execute(q, args)).fetchall()]


async def main():
    await db.init_db()
    print("\nOne charge, one row\n")

    # ── the exact sequence that cost Rs 11,776 ──────────────────────────────
    a = await nidaan.record_payment(source="subscription", total_paise=58800,
                                    razorpay_subscription_id=SUB, account_id=132,
                                    dedup_key=SUB, verify_method="api_fetch", verified=True)
    b = await nidaan.record_payment(source="subscription", total_paise=58882,
                                    razorpay_subscription_id=SUB, razorpay_payment_id=PAY,
                                    account_id=132, dedup_key=PAY, verify_method="webhook",
                                    verified=True)
    got = await rows(source="subscription")
    check("the activation is recorded once", a is True)
    check("the SAME activation arriving the other way is refused", b is False,
          "wrote %d rows: %s" % (len(got), [r["dedup_key"] for r in got]))
    check("...so the ledger holds exactly one row", len(got) == 1, got)

    # and the other way round, which is the order that actually happened live
    await nidaan.record_payment(source="subscription", total_paise=58882,
                                razorpay_subscription_id="sub_OTHER",
                                razorpay_payment_id="pay_OTHER", account_id=140,
                                dedup_key="pay_OTHER", verify_method="webhook", verified=True)
    again = await nidaan.record_payment(source="subscription", total_paise=58800,
                                        razorpay_subscription_id="sub_OTHER", account_id=140,
                                        dedup_key="sub_OTHER", verify_method="api_fetch")
    check("payment-id first, subscription-id second, is also refused", again is False,
          await rows(razorpay_subscription_id="sub_OTHER"))

    # ── THE TRAP the obvious fix would have created ─────────────────────────
    # A row already in the ledger under the OLD key shape must still be recognised, or the
    # next late webhook writes a third row and the cure is worse than the disease.
    async with aiosqlite.connect(DB) as c:
        await c.execute(
            "INSERT INTO nidaan_payments (dedup_key, source, razorpay_subscription_id, "
            "account_id, total_paise, status) VALUES (?,?,?,?,?,?)",
            ("sub:85:11", "subscription", "sub_LEGACY", 85, 58800, "captured"))
        await c.commit()
    third = await nidaan.record_payment(source="subscription", total_paise=58882,
                                        razorpay_subscription_id="sub_LEGACY",
                                        razorpay_payment_id="pay_LATE", account_id=85,
                                        dedup_key="pay_LATE", verify_method="webhook")
    check("a row stored under the OLD synthetic key is still recognised", third is False,
          await rows(razorpay_subscription_id="sub_LEGACY"))
    check("...so a late webhook cannot write a third row",
          len(await rows(razorpay_subscription_id="sub_LEGACY")) == 1)

    # ── the siblings, because the same key pattern is in all three ──────────
    await nidaan.record_payment(source="branch_l2", total_paise=58882, claim_id=214,
                                dedup_key="l2:214", verify_method="manual")
    dup_l2 = await nidaan.record_payment(source="branch_l2", total_paise=58882, claim_id=214,
                                         razorpay_payment_id="pay_L2", dedup_key="pay_L2",
                                         verify_method="signature")
    check("one Level-2 fee per claim, by either road", dup_l2 is False,
          await rows(source="branch_l2"))

    await nidaan.record_payment(source="per_claim_review", total_paise=58882, claim_id=300,
                                dedup_key="claim499:300", verify_method="manual")
    dup_499 = await nidaan.record_payment(source="per_claim_review", total_paise=58882,
                                          claim_id=300, razorpay_payment_id="pay_499",
                                          dedup_key="pay_499", verify_method="webhook")
    check("one Rs499 review per claim, by either road", dup_499 is False,
          await rows(source="per_claim_review"))

    # ── what must STILL be allowed, or the fix breaks the business ──────────
    n1 = await nidaan.record_payment(source="branch_l2", total_paise=58882, claim_id=213,
                                     razorpay_payment_id="pay_213", dedup_key="pay_213")
    check("a DIFFERENT claim's Level-2 fee still records - this is the false alarm case",
          n1 is True, await rows(source="branch_l2"))

    r1 = await nidaan.record_payment(source="subscription_renewal", total_paise=58882,
                                     razorpay_subscription_id=SUB, razorpay_payment_id="pay_M1",
                                     dedup_key="pay_M1", account_id=132)
    r2 = await nidaan.record_payment(source="subscription_renewal", total_paise=58882,
                                     razorpay_subscription_id=SUB, razorpay_payment_id="pay_M2",
                                     dedup_key="pay_M2", account_id=132)
    check("MONTHLY RENEWALS on the same subscription still record - they are meant to recur",
          r1 is True and r2 is True, await rows(source="subscription_renewal"))

    # A row already marked duplicate must not block the real one from being written.
    async with aiosqlite.connect(DB) as c:
        await c.execute("INSERT INTO nidaan_payments (dedup_key, source, claim_id, total_paise, "
                        "status) VALUES (?,?,?,?,?)", ("l2:999", "branch_l2", 999, 58882,
                                                       "duplicate"))
        await c.commit()
    ok999 = await nidaan.record_payment(source="branch_l2", total_paise=58882, claim_id=999,
                                        razorpay_payment_id="pay_999", dedup_key="pay_999")
    check("a row already marked 'duplicate' does not block the real one", ok999 is True)

    # ── the placeholder, and the real payment that completes it ─────────────
    # Live data, 5 of the 14: a `subscription` row from the activation path (no payment id,
    # GST rounded to Rs 589.00) and a `subscription_renewal` row from the webhook FOUR SECONDS
    # later carrying the real Rs 588.82. Matching on `source` would never have caught it.
    P = "sub_PLACEHOLDER"
    await nidaan.record_payment(source="subscription", total_paise=58900, base_paise=49900,
                                razorpay_subscription_id=P, account_id=200,
                                dedup_key=P, verify_method="api_fetch", verified=True)
    before = await rows(razorpay_subscription_id=P)
    check("the activation writes a placeholder row", len(before) == 1
          and before[0]["total_paise"] == 58900, before)

    late = await nidaan.record_payment(source="subscription_renewal", total_paise=58882,
                                       base_paise=49900, gst_paise=8982,
                                       razorpay_subscription_id=P,
                                       razorpay_payment_id="pay_REAL", account_id=200,
                                       dedup_key="pay_REAL", verify_method="webhook",
                                       verified=True)
    after = await rows(razorpay_subscription_id=P)
    check("a renewal seconds later does NOT become a second row - across sources",
          late is False and len(after) == 1, after)
    async with aiosqlite.connect(DB) as c:
        c.row_factory = aiosqlite.Row
        row = dict(await (await c.execute(
            "SELECT * FROM nidaan_payments WHERE razorpay_subscription_id=?", (P,))).fetchone())
    check("...the surviving row now carries the REAL payment id",
          row["razorpay_payment_id"] == "pay_REAL", row["razorpay_payment_id"])
    check("...and the REAL amount, not the rounded placeholder figure",
          row["total_paise"] == 58882, row["total_paise"])
    check("...and is keyed on the payment, so a repeat webhook is a no-op",
          row["dedup_key"] == "pay_REAL", row["dedup_key"])
    repeat = await nidaan.record_payment(source="subscription_renewal", total_paise=58882,
                                         razorpay_subscription_id=P,
                                         razorpay_payment_id="pay_REAL", account_id=200,
                                         dedup_key="pay_REAL")
    check("...proven: sending the same webhook again changes nothing",
          repeat is False and len(await rows(razorpay_subscription_id=P)) == 1)

    # A genuine renewal a month later, once there is no placeholder left, must still record.
    nxt = await nidaan.record_payment(source="subscription_renewal", total_paise=58882,
                                      razorpay_subscription_id=P,
                                      razorpay_payment_id="pay_NEXTMONTH", account_id=200,
                                      dedup_key="pay_NEXTMONTH")
    check("next month's real renewal still records",
          nxt is True and len(await rows(razorpay_subscription_id=P)) == 2)

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "one charge, one row - and renewals still recur"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
