"""Unit test for resolve_inbound_identity (WhatsApp Journey Phase 1).

Uses a throwaway temp SQLite DB with minimal fixtures — does NOT touch prod data.
Run on the server:  /opt/sarathi/venv/bin/python /tmp/test_inbound_identity.py
"""
import asyncio
import os
import tempfile
import aiosqlite

import biz_database as db
import biz_nidaan_inbound as inbound


async def _setup(path):
    async with aiosqlite.connect(path) as conn:
        await conn.execute("""
            CREATE TABLE nidaan_accounts (
                account_id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_name TEXT, phone TEXT
            )""")
        await conn.execute("""
            CREATE TABLE nidaan_claims (
                claim_id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER, insured_name TEXT, insured_phone TEXT,
                stage TEXT DEFAULT 'intimated', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""")
        # Fixtures:
        # A1: advisor account, phone 9000000001
        await conn.execute("INSERT INTO nidaan_accounts(account_id,owner_name,phone) VALUES (1,'Advisor A','+91 90000 00001')")
        # A2: self-service insured account, phone 9000000002
        await conn.execute("INSERT INTO nidaan_accounts(account_id,owner_name,phone) VALUES (2,'Self Insured','9000000002')")
        # Claim 10: under advisor A1, insured (customer) phone 9000000009 (≠ advisor)
        await conn.execute("INSERT INTO nidaan_claims(claim_id,account_id,insured_name,insured_phone,stage) VALUES (10,1,'Mr Customer','90000-00009','intimated')")
        # Claim 11: under self-service A2, insured phone == account phone 9000000002
        await conn.execute("INSERT INTO nidaan_claims(claim_id,account_id,insured_name,insured_phone,stage) VALUES (11,2,'Self Insured','9000000002','review')")
        # Claim 12: CLOSED claim under A1 for the same customer — must be ignored
        await conn.execute("INSERT INTO nidaan_claims(claim_id,account_id,insured_name,insured_phone,stage) VALUES (12,1,'Mr Customer','9000000009','closed')")
        # Claim 13: same customer phone 9000000009 ALSO under a different advisor acct 1 -> still acct 1; make an ambiguity case:
        await conn.execute("INSERT INTO nidaan_accounts(account_id,owner_name,phone) VALUES (3,'Advisor B','9000000003')")
        await conn.execute("INSERT INTO nidaan_claims(claim_id,account_id,insured_name,insured_phone,stage) VALUES (14,3,'Mr Customer','9000000009','intimated')")
        await conn.commit()


async def main():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db.DB_PATH = path  # point the resolver at our temp DB
    try:
        await _setup(path)
        passed = failed = 0

        def check(name, got, want):
            nonlocal passed, failed
            ok = got == want
            passed += ok
            failed += (not ok)
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}: got={got} want={want}")

        # 1. Advisor (account holder) messages
        r = await inbound.resolve_inbound_identity("9000000001")
        check("advisor role", r["role"], inbound.ROLE_ACCOUNT_HOLDER)
        check("advisor account_id", r["account_id"], 1)
        check("advisor active claims (10 only, not closed 12)", sorted(r["claim_ids"]), [10])

        # 2. Self-service insured (account holder == insured)
        r = await inbound.resolve_inbound_identity("9000000002")
        check("self-service role=account_holder", r["role"], inbound.ROLE_ACCOUNT_HOLDER)
        check("self-service account_id", r["account_id"], 2)
        check("self-service claims", sorted(r["claim_ids"]), [11])

        # 3. Customer (insured ≠ account holder) under TWO advisors → ambiguous
        r = await inbound.resolve_inbound_identity("9000000009")
        check("customer role", r["role"], inbound.ROLE_CUSTOMER)
        check("customer active claims (10 & 14, not closed 12)", sorted(r["claim_ids"]), [10, 14])
        check("customer ambiguous accounts", r["ambiguous_account_ids"], [1, 3])
        check("customer account_id None when ambiguous", r["account_id"], None)

        # 4. Unknown number
        r = await inbound.resolve_inbound_identity("9999999999")
        check("unknown role", r["role"], inbound.ROLE_UNKNOWN)
        check("unknown account_id", r["account_id"], None)

        # 5. Empty
        r = await inbound.resolve_inbound_identity("")
        check("empty role", r["role"], inbound.ROLE_UNKNOWN)

        print(f"\n{'='*50}\n  {passed} passed, {failed} failed\n{'='*50}")
        return failed
    finally:
        os.unlink(path)


if __name__ == "__main__":
    rc = asyncio.run(main())
    raise SystemExit(1 if rc else 0)
