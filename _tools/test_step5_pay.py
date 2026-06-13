"""End-to-end test for ₹499 funnel Step 5 — claim payment + review start.

Simulates a valid Razorpay signature (HMAC of order|payment with the live
secret) so the pay-verify path is exercised WITHOUT a real Razorpay charge.
"""
import asyncio
import hashlib
import hmac
import os
import sys
import aiosqlite

try:
    from dotenv import load_dotenv
    load_dotenv("/opt/sarathi/biz.env")
except Exception:
    pass

import biz_database as db
import biz_nidaan as nidaan
import biz_nidaan_doc_checklist as ck

EMAIL = "_step5_pay_test@example.invalid"


async def setup(complete: bool):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM nidaan_accounts WHERE email=?", (EMAIL,))
        cur = await conn.execute(
            "INSERT INTO nidaan_accounts(owner_name,firm_name,email,phone,status) "
            "VALUES('Step5 Test','',?,'9000000333','active')", (EMAIL,))
        acc = cur.lastrowid
        await conn.commit()
    # free-lead claim
    cid, _ = await nidaan.submit_claim(
        account_id=acc, user_id=None, claim_type="health",
        insured_name="Pay Test", insured_phone="9000000444",
        disputed_amount=400000, payment_status="unpaid_lead", skip_eligibility=True)
    await ck.seed_checklist_for_claim(cid, "health")
    if complete:
        for d in await ck.pending_required_docs(cid, "health"):
            await ck.mark_doc_received(cid, d["key"], via=ck.VIA_DASHBOARD, doc_id=None)
    token = nidaan.create_nidaan_token(acc, EMAIL, "")
    print(f"ACCOUNT_ID={acc}")
    print(f"CLAIM_ID={cid}")
    print(f"TOKEN={token}")


def paysig(order, pay):
    secret = os.environ.get("RAZORPAY_KEY_SECRET", "")
    sig = hmac.new(secret.encode(), f"{order}|{pay}".encode(), hashlib.sha256).hexdigest()
    print(sig)


async def verify_paid(claim_id):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        c = await (await conn.execute(
            "SELECT payment_status, paid_at FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
        t = await (await conn.execute(
            "SELECT COUNT(*) n FROM nidaan_tasks WHERE claim_id=?", (claim_id,))).fetchone()
        print(f"payment_status={c['payment_status']} paid_at={'set' if c['paid_at'] else 'NULL'} review_tasks={t['n']}")
        ok = c["payment_status"] == "paid" and c["paid_at"] and t["n"] >= 1
        print("RESULT:", "PASS" if ok else "FAIL")


async def cleanup(acc):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cids = [r[0] for r in await (await conn.execute(
            "SELECT claim_id FROM nidaan_claims WHERE account_id=?", (acc,))).fetchall()]
        for cid in cids:
            for tbl in ("nidaan_claim_doc_checklist", "nidaan_claim_status_log", "nidaan_tasks", "nidaan_claims"):
                try:
                    await conn.execute(f"DELETE FROM {tbl} WHERE claim_id=?", (cid,))
                except Exception:
                    pass
        await conn.execute("DELETE FROM nidaan_accounts WHERE account_id=?", (acc,))
        await conn.commit()
        print(f"cleaned account {acc} + {len(cids)} claim(s)")


if __name__ == "__main__":
    p = sys.argv[1]
    if p == "setup":
        asyncio.run(setup(sys.argv[2] == "complete"))
    elif p == "paysig":
        paysig(sys.argv[2], sys.argv[3])
    elif p == "verify_paid":
        asyncio.run(verify_paid(int(sys.argv[2])))
    elif p == "cleanup":
        asyncio.run(cleanup(int(sys.argv[2])))
