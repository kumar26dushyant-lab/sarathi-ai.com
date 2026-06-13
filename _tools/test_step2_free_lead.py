"""End-to-end test for ₹499 funnel Step 2 — free-lead claim submission.

Creates a throwaway Nidaan account with NO subscription, mints a real token,
and prints the token + account_id so a curl can hit the live endpoint. Then
verifies the DB. Cleans up.

Run on server (sources biz.env for JWT secret):
  cd /opt/sarathi && set -a && . ./biz.env && set +a && \
  PYTHONPATH=/opt/sarathi venv/bin/python /tmp/test_step2_free_lead.py <phase>
phases: token | verify <claim_id> | cleanup <account_id>
"""
import asyncio
import sys
import aiosqlite

# Load env the SAME way the app does (python-dotenv handles CRLF) so JWT_SECRET
# matches the running service — bash `. ./biz.env` breaks on Windows CRLF.
try:
    from dotenv import load_dotenv
    load_dotenv("/opt/sarathi/biz.env")
except Exception:
    pass

import biz_database as db
import biz_nidaan as nidaan
import biz_nidaan_doc_checklist as ck

TEST_EMAIL = "_step2_test_lead@example.invalid"


async def make_token():
    async with aiosqlite.connect(db.DB_PATH) as conn:
        # clean any prior test row
        await conn.execute("DELETE FROM nidaan_accounts WHERE email=?", (TEST_EMAIL,))
        cur = await conn.execute(
            "INSERT INTO nidaan_accounts(owner_name, firm_name, email, phone, status) "
            "VALUES ('Step2 Test','', ?, '9000000111', 'active')", (TEST_EMAIL,))
        account_id = cur.lastrowid
        await conn.commit()
    # no subscription, no per-claim purchase → must become an unpaid_lead
    token = nidaan.create_nidaan_token(account_id, TEST_EMAIL, "")
    print(f"ACCOUNT_ID={account_id}")
    print(f"TOKEN={token}")


async def verify(claim_id):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT claim_id, claim_type, payment_status, status FROM nidaan_claims WHERE claim_id=?", (claim_id,))
        c = await cur.fetchone()
        if not c:
            print("FAIL: claim not found"); return
        print(f"claim {c['claim_id']}: type={c['claim_type']} payment_status={c['payment_status']} status={c['status']}")
        cur = await conn.execute("SELECT doc_key, required, received FROM nidaan_claim_doc_checklist WHERE claim_id=? ORDER BY doc_key", (claim_id,))
        rows = await cur.fetchall()
        print(f"checklist rows seeded: {len(rows)}")
        for r in rows:
            print(f"   - {r['doc_key']}: required={r['required']} received={r['received']}")
        # assertions
        ok = (c["payment_status"] == "unpaid_lead") and (len(rows) > 0)
        print("RESULT:", "PASS" if ok else "FAIL")


async def cleanup(account_id):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("SELECT claim_id FROM nidaan_claims WHERE account_id=?", (account_id,))
        cids = [r[0] for r in await cur.fetchall()]
        for cid in cids:
            await conn.execute("DELETE FROM nidaan_claim_doc_checklist WHERE claim_id=?", (cid,))
            await conn.execute("DELETE FROM nidaan_claim_status_log WHERE claim_id=?", (cid,))
            await conn.execute("DELETE FROM nidaan_claims WHERE claim_id=?", (cid,))
        await conn.execute("DELETE FROM nidaan_accounts WHERE account_id=?", (account_id,))
        await conn.commit()
        print(f"cleaned account {account_id} + {len(cids)} claim(s)")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "token"
    if phase == "token":
        asyncio.run(make_token())
    elif phase == "verify":
        asyncio.run(verify(int(sys.argv[2])))
    elif phase == "cleanup":
        asyncio.run(cleanup(int(sys.argv[2])))
