"""Reconcile payments that arrived while the Razorpay webhook was disabled.

Run on production:
    cd /opt/sarathi
    sudo -u sarathi /opt/sarathi/venv/bin/python _tools/razorpay_webhook_reconcile.py

What it does
============
1. Calls Razorpay GET /payments with a `from`/`to` window covering the last
   72 hours (covers the documented 24h failure window with margin).
2. For each captured Sarathi payment (notes.tenant_id present) — checks our
   tenants table; if subscription_status isn't 'active', logs a TODO.
3. For each captured Nidaan order payment (notes.product == "nidaan") —
   checks nidaan_subscriptions; if the order_id isn't already activated,
   calls nidaan.activate_from_order_payment().
4. Prints a summary at the end; makes NO destructive changes except the
   Nidaan activation (which is idempotent).
"""
import asyncio
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, "/opt/sarathi")

import httpx

import biz_database as db
import biz_nidaan as nidaan


async def main() -> int:
    rzp_key_id = os.getenv("RAZORPAY_KEY_ID", "")
    rzp_secret = os.getenv("RAZORPAY_KEY_SECRET", "")
    if not rzp_key_id or not rzp_secret:
        print("FATAL: RAZORPAY_KEY_ID/SECRET not in env")
        return 2

    # 72h window — covers the 24h documented failure plus margin.
    now = datetime.utcnow()
    frm = int((now - timedelta(hours=72)).timestamp())
    to  = int(now.timestamp())
    print(f"Reconciliation window: {datetime.utcfromtimestamp(frm)} → "
          f"{datetime.utcfromtimestamp(to)} UTC")

    payments = []
    async with httpx.AsyncClient(auth=(rzp_key_id, rzp_secret), timeout=30.0) as client:
        # Razorpay API pagination
        skip = 0
        while True:
            r = await client.get("https://api.razorpay.com/v1/payments",
                                  params={"from": frm, "to": to,
                                          "count": 100, "skip": skip})
            if r.status_code != 200:
                print(f"FATAL: Razorpay payments fetch {r.status_code}: {r.text[:200]}")
                return 3
            d = r.json()
            items = d.get("items", [])
            payments.extend(items)
            print(f"  fetched {len(items)} (total {len(payments)})")
            if len(items) < 100:
                break
            skip += 100

    print(f"\nTotal payments in window: {len(payments)}")

    # Classify
    nidaan_payments = []
    sarathi_payments = []
    other_payments = []
    for p in payments:
        if p.get("status") != "captured":
            continue
        notes = p.get("notes") or {}
        if notes.get("product") == "nidaan":
            nidaan_payments.append(p)
        elif notes.get("tenant_id"):
            sarathi_payments.append(p)
        else:
            other_payments.append(p)

    print(f"  Nidaan captured:  {len(nidaan_payments)}")
    print(f"  Sarathi captured: {len(sarathi_payments)}")
    print(f"  Other / no notes: {len(other_payments)}")

    # ── Nidaan reconciliation ────────────────────────────────────────────────
    nidaan_activated = 0
    nidaan_already = 0
    nidaan_skipped = 0
    for p in nidaan_payments:
        notes = p.get("notes") or {}
        account_id = notes.get("nidaan_account_id")
        plan = notes.get("nidaan_plan")
        order_id = p.get("order_id", "")
        amount = int(p.get("amount", 0))
        payment_id = p.get("id", "")
        if not account_id or not plan or not order_id:
            nidaan_skipped += 1
            print(f"  SKIP nidaan payment {payment_id} — missing notes "
                  f"(account_id={account_id}, plan={plan}, order={order_id})")
            continue
        try:
            already = await nidaan.activate_from_order_payment(
                order_id, int(account_id), plan, amount,
                razorpay_payment_id=payment_id)
            if already:
                nidaan_already += 1
                print(f"  ✓ already-activated nidaan order {order_id} "
                      f"account={account_id} plan={plan}")
            else:
                nidaan_activated += 1
                print(f"  ✅ ACTIVATED nidaan order {order_id} "
                      f"account={account_id} plan={plan} amount=₹{amount//100}")
        except Exception as e:
            nidaan_skipped += 1
            print(f"  ERROR activating order {order_id}: {e}")

    # ── Sarathi reconciliation ──────────────────────────────────────────────
    # Just REPORT the Sarathi state — actual activation logic for Sarathi
    # tenants is more complex (it depends on the event type, not just the
    # payment). We don't auto-mutate; we surface what needs review.
    sarathi_review = []
    for p in sarathi_payments:
        notes = p.get("notes") or {}
        tid = notes.get("tenant_id")
        try:
            tenant = await db.get_tenant(int(tid)) if tid else None
        except Exception:
            tenant = None
        tenant_state = tenant.get("subscription_status") if tenant else "unknown"
        sarathi_review.append({
            "payment_id": p.get("id"), "tenant_id": tid,
            "amount": p.get("amount", 0) // 100,
            "tenant_state": tenant_state,
            "created_at": datetime.utcfromtimestamp(p.get("created_at", 0)),
        })

    if sarathi_review:
        print("\nSarathi payments — manual review queue (no auto-changes made):")
        for r in sarathi_review:
            flag = "⚠️" if r["tenant_state"] != "active" else "✓"
            print(f"  {flag} payment={r['payment_id']} tenant={r['tenant_id']} "
                  f"₹{r['amount']} sub_status={r['tenant_state']} "
                  f"at={r['created_at']}")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("RECONCILIATION SUMMARY")
    print("=" * 50)
    print(f"Nidaan activated this run: {nidaan_activated}")
    print(f"Nidaan already activated:  {nidaan_already}")
    print(f"Nidaan skipped/errored:    {nidaan_skipped}")
    print(f"Sarathi rows for review:   {len(sarathi_review)}")
    print(f"Other captured (no notes): {len(other_payments)}")
    if other_payments:
        print("\nOther captured payments (may not be ours — visible for sanity):")
        for p in other_payments[:5]:
            print(f"  {p.get('id')} ₹{p.get('amount',0)//100} "
                  f"at={datetime.utcfromtimestamp(p.get('created_at',0))} "
                  f"contact={p.get('contact','')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
