"""One-shot: process refund for account 9 (sub_id 3) — Policy A precedent.

Run on production:
    cd /opt/sarathi
    sudo -u sarathi /opt/sarathi/venv/bin/python _tools/refund_account_9.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/opt/sarathi")

import biz_nidaan as nidaan


async def main() -> int:
    rzp_key_id = os.getenv("RAZORPAY_KEY_ID", "")
    rzp_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not rzp_key_id or not rzp_secret:
        print("FATAL: RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not in env")
        return 2

    eligible, reason, sub = await nidaan.check_refund_eligibility(sub_id=3)
    print(f"Eligibility: {eligible}  reason={reason}")
    print(f"Sub row: account_id={sub.get('account_id')} plan={sub.get('plan')} "
          f"amount=₹{sub.get('amount_paid')} status={sub.get('status')} "
          f"order_id={sub.get('razorpay_subscription_id')} "
          f"payment_id={sub.get('razorpay_payment_id') or '(legacy: will resolve)'}")
    if not eligible:
        print(f"NOT eligible: {reason}")
        return 1

    order_id = sub.get("razorpay_subscription_id", "")
    payment_id = sub.get("razorpay_payment_id", "")
    if not payment_id and order_id:
        payment_id = await nidaan.find_payment_id_via_razorpay(order_id, rzp_key_id, rzp_secret)
        print(f"Resolved payment_id from order: {payment_id}")

    if not payment_id:
        print("FAIL: cannot resolve a payment_id to refund against")
        return 3

    amount_rupees = int(sub.get("amount_paid", 0))
    amount_paise = amount_rupees * 100

    refund_id = await nidaan.create_refund_row(
        sub_id=3, account_id=sub["account_id"], amount=amount_rupees,
        razorpay_order_id=order_id, razorpay_payment_id=payment_id,
        reason="Policy A backfill — user cancelled within window, 0 claims, "
               "manual refund via _tools script")
    print(f"Created refund row: refund_id={refund_id} amount=₹{amount_rupees}")
    await nidaan.update_refund_status(refund_id, "processing")

    result = await nidaan.issue_razorpay_refund(
        payment_id, amount_paise, rzp_key_id, rzp_secret,
        notes={"sub_id": "3", "account_id": str(sub["account_id"]),
               "reason": "policy_a_backfill"})
    print(f"Razorpay response: {result}")

    if result.get("ok"):
        await nidaan.update_refund_status(refund_id, "processed",
                                          razorpay_refund_id=result.get("refund_id", ""))
        print(f"✅ PROCESSED — Razorpay refund_id={result.get('refund_id')}")
        return 0

    await nidaan.update_refund_status(refund_id, "failed",
                                      last_error=result.get("error", "")[:500])
    print(f"❌ FAILED: {result.get('error')}")
    return 4


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
