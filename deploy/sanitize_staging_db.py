#!/usr/bin/env python3
"""Sanitize a COPY of the production DB for the staging environment.

Usage:  python sanitize_staging_db.py /opt/sarathi-staging/sarathi_staging.db

Anonymizes personal data (phones, emails, names), blanks external payment /
provider IDs + in-DB secrets, and clears volatile/outbound queues. Column lists
are EXPLICIT (derived from the live schema) so non-PII lookalikes
(phone_verified, email_enabled, password_hash, tokens_in, …) are left intact.
Idempotent-ish: safe to re-run. NEVER run this against the production DB.
"""
import sqlite3, sys, os

if len(sys.argv) != 2:
    sys.exit("usage: sanitize_staging_db.py <staging_db_path>")
DB = sys.argv[1]
if DB.rstrip("/").endswith("sarathi_biz.db") or "staging" not in DB:
    sys.exit(f"REFUSING: '{DB}' does not look like a staging db (must contain 'staging').")
if not os.path.exists(DB):
    sys.exit(f"no such db: {DB}")

# (table, column) → transform kind
PHONE = [
    ("affiliate_referrals","referred_phone"),("affiliates","phone"),
    ("agents","phone"),("agents","wa_phone"),("customers","phone"),
    ("customers","whatsapp"),("leads","phone"),("leads","whatsapp"),
    ("marketing_sends","phone"),("nidaan_accounts","phone"),
    ("nidaan_claims","insured_phone"),("nidaan_notifications","recipient_phone"),
    ("nidaan_official_instances","phone_number"),("nidaan_payment_links","customer_phone"),
    ("nidaan_per_claim_purchase","insured_phone"),("nidaan_per_claim_purchase","advisor_phone"),
    ("nidaan_quick_tasks","complainant_phone"),("nidaan_staff","phone"),
    ("support_tickets","contact_phone"),("tenants","phone"),("tenants","brand_phone"),
    ("wa_agent_conversations","sender_phone"),("wa_agent_devices","agent_phone"),
    ("wa_conversations","customer_phone"),("wa_instances","phone_number"),
]
EMAIL = [
    ("affiliates","email"),("agents","email"),("customers","email"),("leads","email"),
    ("nidaan_accounts","email"),("nidaan_admins","email"),("nidaan_branches","contact_email"),
    ("nidaan_claims","insured_email"),("nidaan_notifications","recipient_email"),
    ("nidaan_payment_links","customer_email"),("nidaan_per_claim_purchase","insured_email"),
    ("nidaan_per_claim_purchase","advisor_email"),("nidaan_staff","email"),
    ("nidaan_staff","notify_email"),("nidaan_users","email"),
    ("support_tickets","contact_email"),("tenants","email"),("tenants","brand_email"),
]
NAME = [
    ("agents","firm_name"),("nidaan_accounts","owner_name"),("nidaan_accounts","firm_name"),
    ("nidaan_claims","insured_name"),("nidaan_payment_links","customer_name"),
    ("nidaan_per_claim_purchase","insured_name"),("support_tickets","contact_name"),
    ("tenants","firm_name"),("tenants","owner_name"),("wa_agent_devices","agent_name"),
    ("wa_conversations","customer_name"),
]
BLANK = [  # external ids + in-db secrets → ''
    ("affiliate_commissions","payment_id"),("nidaan_claims","l2_payment_id"),
    ("nidaan_gst_ledger","razorpay_payment_id"),("nidaan_payment_links","razorpay_payment_id"),
    ("nidaan_per_claim_purchase","razorpay_order_id"),("nidaan_per_claim_purchase","razorpay_subscription_id"),
    ("nidaan_plans_config","razorpay_plan_id"),("nidaan_refunds","razorpay_order_id"),
    ("nidaan_refunds","razorpay_payment_id"),("nidaan_refunds","razorpay_refund_id"),
    ("nidaan_subscriptions","razorpay_subscription_id"),("nidaan_subscriptions","razorpay_payment_id"),
    ("processed_payments","razorpay_payment_id"),("sarathi_refunds","razorpay_payment_id"),
    ("sarathi_refunds","razorpay_refund_id"),("sarathi_refunds","razorpay_order_id"),
    ("tenants","razorpay_sub_id"),("customers","portfolio_token"),
    ("tenants","wa_access_token"),("tenants","wa_verify_token"),("tenants","tg_bot_token"),
    ("tenants","wa_phone_id"),("wa_agent_devices","token_hash"),
]
CLEAR = ["auth_otp","otp_store","nidaan_tg_login","wa_send_queue","wa_pending_reply","wa_brain_locks"]

con = sqlite3.connect(DB)
have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
def cols(t): return {r[1] for r in con.execute(f"PRAGMA table_info({t})")} if t in have else set()

n = 0
def upd(t, c, expr):
    global n
    if t in have and c in cols(t):
        r = con.execute(f"UPDATE {t} SET {c}={expr} WHERE {c} IS NOT NULL AND {c}!=''")
        n += r.rowcount

for t, c in PHONE:  upd(t, c, "'9' || substr('000000000'||rowid, -9)")
for t, c in EMAIL:  upd(t, c, "'user' || rowid || '@staging.local'")
for t, c in NAME:   upd(t, c, "'Test ' || rowid")
for t, c in BLANK:  upd(t, c, "'staged-' || rowid")  # unique fake: removes real value, no UNIQUE collision

cleared = []
for t in CLEAR:
    if t in have:
        con.execute(f"DELETE FROM {t}")
        cleared.append(t)

con.commit()
con.execute("VACUUM")
con.commit()
con.close()
print(f"sanitized {DB}: {n} PII/id cells rewritten; cleared {len(cleared)} volatile tables: {', '.join(cleared)}")
