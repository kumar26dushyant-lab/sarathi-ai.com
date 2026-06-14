"""End-to-end test for ₹499 funnel Step 7b — DPDP lead retention.

Verifies the two-stage lifecycle: pre-notice at (RETENTION-NOTICE) days, then a
secure purge of the lead's documents at RETENTION days, plus idempotency. Asserts
on DB state + the always-written dashboard notification rows (so it passes without
a live WhatsApp number / SMTP).

Run on the server:
  cd /opt/sarathi && PYTHONPATH=/opt/sarathi venv/bin/python _tools/test_step7_retention.py
"""
import asyncio
import os
import sys
import aiosqlite

try:
    from dotenv import load_dotenv
    load_dotenv("/opt/sarathi/biz.env")
except Exception:
    pass

# Deterministic window for the test.
os.environ["NIDAAN_LEAD_RETENTION_DAYS"] = "30"
os.environ["NIDAAN_LEAD_NOTICE_DAYS"] = "7"   # notice at day 23

import biz_database as db
import biz_nidaan as nidaan
import biz_nidaan_doc_checklist as ck
import biz_nidaan_retention as ret

EMAIL = "_step7_retention@example.invalid"


async def _set_age(claim_id, days):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claims SET created_at=datetime('now', ?) WHERE claim_id=?",
            (f"-{days} days", claim_id))
        await conn.commit()


async def _col(claim_id, col):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(f"SELECT {col} FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
        return r[col] if r else None


async def _notif(claim_id, event_key):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        r = await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_notifications WHERE claim_id=? AND event_key=? AND channel='dashboard'",
            (claim_id, event_key))).fetchone()
        return r[0]


async def _doc_count(claim_id):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        r = await (await conn.execute("SELECT COUNT(*) FROM nidaan_claim_documents WHERE claim_id=?", (claim_id,))).fetchone()
        return r[0]


async def run():
    results = []
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM nidaan_accounts WHERE email=?", (EMAIL,))
        cur = await conn.execute(
            "INSERT INTO nidaan_accounts(owner_name,firm_name,email,phone,status) "
            "VALUES('Step7 Ret','',?,'9000000999','active')", (EMAIL,))
        acc = cur.lastrowid
        await conn.commit()

    cid, _ = await nidaan.submit_claim(
        account_id=acc, user_id=None, claim_type="health",
        insured_name="Ret Test", insured_phone="9000001000",
        disputed_amount=300000, payment_status="unpaid_lead", skip_eligibility=True)
    await ck.seed_checklist_for_claim(cid, "health")

    # Add one real document (row + file on disk) + mark a checklist item received.
    ret._DOCS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"_rettest_{cid}.pdf"
    (ret._DOCS_DIR / fname).write_bytes(b"%PDF-1.4 test")
    doc_id = await nidaan.save_claim_document(
        account_id=acc, stored_name=fname, original_name="rejection.pdf",
        file_size=13, mime_type="application/pdf", claim_id=cid)
    pend = await ck.pending_required_docs(cid, "health")
    if pend:
        await ck.mark_doc_received(cid, pend[0]["key"], via=ck.VIA_DASHBOARD, doc_id=doc_id)

    # ── Stage 1: age = 25 days (past notice@23, before purge@30) → pre-notice only
    await _set_age(cid, 25)
    await ret.run_lead_retention()
    results.append(("pre-notice stamped (lead_notice_at set)", bool(await _col(cid, "lead_notice_at"))))
    results.append(("deletion-notice message recorded", await _notif(cid, "funnel.lead_deletion_notice") == 1))
    results.append(("documents NOT yet deleted", await _doc_count(cid) == 1))
    results.append(("file still on disk", (ret._DOCS_DIR / fname).exists()))

    # ── Stage 2: age = 31 days → purge
    await _set_age(cid, 31)
    await ret.run_lead_retention()
    results.append(("lead_purged_at set", bool(await _col(cid, "lead_purged_at"))))
    results.append(("document rows deleted", await _doc_count(cid) == 0))
    results.append(("file removed from disk", not (ret._DOCS_DIR / fname).exists()))
    results.append(("purge confirmation recorded", await _notif(cid, "funnel.lead_data_purged") == 1))
    # checklist received reset
    st = await ck.checklist_status(cid, "health")
    results.append(("checklist received reset to 0", st["received_required"] == 0))
    # claim row preserved (still a lead in ops)
    results.append(("claim row preserved as lead", (await _col(cid, "payment_status")) == "unpaid_lead"))

    # ── Idempotency: another sweep changes nothing
    await ret.run_lead_retention()
    results.append(("purge is idempotent (still 1 confirmation)", await _notif(cid, "funnel.lead_data_purged") == 1))

    # cleanup
    async with aiosqlite.connect(db.DB_PATH) as conn:
        for tbl in ("nidaan_notifications", "nidaan_claim_doc_checklist",
                    "nidaan_claim_documents", "nidaan_claim_status_log", "nidaan_tasks", "nidaan_claims"):
            try:
                await conn.execute(f"DELETE FROM {tbl} WHERE claim_id=?", (cid,))
            except Exception:
                pass
        await conn.execute("DELETE FROM nidaan_subscriber_prefs WHERE account_id=?", (acc,))
        await conn.execute("DELETE FROM nidaan_accounts WHERE account_id=?", (acc,))
        await conn.commit()
    try:
        (ret._DOCS_DIR / fname).unlink(missing_ok=True)
    except Exception:
        pass

    passed = sum(1 for _, ok in results if ok)
    for name, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\nRESULT: {passed}/{len(results)} " + ("PASS" if passed == len(results) else "FAIL"))
    return passed == len(results)


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(run()) else 1)
