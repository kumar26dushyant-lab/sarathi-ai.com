"""End-to-end test for DPDP account-erasure (right-to-delete).

Covers: request (soft-delete + billing cancel) → undo → re-request → hard purge
(execute_account_erasure) → sweep with backdated grace. Asserts PII is gone,
document files removed, the account is anonymised, and the financial
(subscription) record is RETAINED. Self-cleaning.

Run on the server:
  cd /opt/sarathi && PYTHONPATH=/opt/sarathi venv/bin/python _tools/test_account_erasure.py
"""
import asyncio, os, sys
import aiosqlite
try:
    from dotenv import load_dotenv
    load_dotenv("/opt/sarathi/biz.env")
except Exception:
    pass
os.environ["NIDAAN_DELETION_GRACE_DAYS"] = "7"

import biz_database as db
import biz_nidaan as nidaan
import biz_nidaan_doc_checklist as ck

EMAIL = "_erasure_test@example.invalid"


async def _col(aid, c):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(f"SELECT {c} FROM nidaan_accounts WHERE account_id=?", (aid,))).fetchone()
        return r[c] if r else None


async def _count(table, where, args):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        try:
            r = await (await conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args)).fetchone()
            return r[0]
        except Exception:
            return -1


async def run():
    res = []
    # setup
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM nidaan_accounts WHERE email=?", (EMAIL,))
        cur = await conn.execute(
            "INSERT INTO nidaan_accounts(owner_name,firm_name,email,phone,status) "
            "VALUES('Erase Test','EraseCo',?,'9000002000','active')", (EMAIL,))
        acc = cur.lastrowid
        await conn.execute("INSERT INTO nidaan_subscriptions(account_id,plan,amount_paid,status) "
                           "VALUES(?,'silver',150000,'active')", (acc,))
        await conn.commit()
    cid, _ = await nidaan.submit_claim(account_id=acc, user_id=None, claim_type="health",
        insured_name="Erase Insured", insured_phone="9000002001", disputed_amount=100000,
        payment_status="unpaid_lead", skip_eligibility=True)
    await ck.seed_checklist_for_claim(cid, "health")
    # a real doc (row + file)
    docs_dir = __import__("pathlib").Path(nidaan.__file__).parent / "uploads" / "nidaan-docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    fname = f"_erase_{cid}.pdf"; (docs_dir / fname).write_bytes(b"%PDF-1.4 x")
    await nidaan.save_claim_document(account_id=acc, stored_name=fname, original_name="x.pdf",
        file_size=10, mime_type="application/pdf", claim_id=cid)

    # ── request deletion (soft) ──
    r = await nidaan.request_account_deletion(acc)
    res.append(("status -> deletion_pending", (await _col(acc, "status")) == "deletion_pending"))
    res.append(("deletion_requested_at set", bool(await _col(acc, "deletion_requested_at"))))
    res.append(("subscription cancelled (billing stop)", (await _count("nidaan_subscriptions", "account_id=? AND status='active'", (acc,))) == 0))

    # ── undo ──
    undone = await nidaan.cancel_account_deletion(acc)
    res.append(("undo works -> active", undone and (await _col(acc, "status")) == "active"))

    # ── re-request + hard purge ──
    await nidaan.request_account_deletion(acc)
    out = await nidaan.execute_account_erasure(acc)
    res.append(("erasure deleted the file", not (docs_dir / fname).exists()))
    res.append(("claims purged", (await _count("nidaan_claims", "account_id=?", (acc,))) == 0))
    res.append(("documents purged", (await _count("nidaan_claim_documents", "account_id=?", (acc,))) == 0))
    res.append(("checklist purged", (await _count("nidaan_claim_doc_checklist", "claim_id=?", (cid,))) == 0))
    res.append(("subscriber_prefs purged", (await _count("nidaan_subscriber_prefs", "account_id=?", (acc,))) == 0))
    res.append(("account anonymised (name)", (await _col(acc, "owner_name")) == "[deleted]"))
    res.append(("account anonymised (email)", str(await _col(acc, "email")).startswith("deleted_")))
    res.append(("status -> deleted + deleted_at", (await _col(acc, "status")) == "deleted" and bool(await _col(acc, "deleted_at"))))
    res.append(("FINANCIAL record RETAINED", (await _count("nidaan_subscriptions", "account_id=?", (acc,))) >= 1))

    # ── sweep with backdated grace ──
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM nidaan_accounts WHERE email=?", (EMAIL,))
        cur = await conn.execute("INSERT INTO nidaan_accounts(owner_name,email,phone,status,deletion_requested_at) "
            "VALUES('Sweep Me','_erase_sweep@example.invalid','9000002002','deletion_pending', datetime('now','-8 days'))")
        acc2 = cur.lastrowid; await conn.commit()
    swept = await nidaan.run_account_erasure_sweep()
    res.append(("sweep purges past-grace account", (await _col(acc2, "status")) == "deleted"))

    # cleanup
    async with aiosqlite.connect(db.DB_PATH) as conn:
        for a in (acc, acc2):
            await conn.execute("DELETE FROM nidaan_subscriptions WHERE account_id=?", (a,))
            await conn.execute("DELETE FROM nidaan_accounts WHERE account_id=?", (a,))
        await conn.commit()
    try: (docs_dir / fname).unlink(missing_ok=True)
    except Exception: pass

    p = sum(1 for _, ok in res if ok)
    for n, ok in res: print(f"  [{'PASS' if ok else 'FAIL'}] {n}")
    print(f"\nRESULT: {p}/{len(res)} " + ("PASS" if p == len(res) else "FAIL"))
    return p == len(res)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
