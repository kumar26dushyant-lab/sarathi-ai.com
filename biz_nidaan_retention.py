"""DPDP retention for ₹499 unpaid leads.

We keep a free lead's uploaded documents only while the lead is live. After a
grace window we securely delete them — but send a trust-building heads-up FIRST
(per the DPDP Act 2023 principle of data minimisation + fair notice). The claim
row itself is kept (as a lead in the ops pipeline); only the personal documents
are removed.

Lifecycle, driven by run_lead_retention() (called daily by the scheduler):
  day (RETENTION-NOTICE):  pre-notice sent  -> sets lead_notice_at
  day  RETENTION:          documents purged -> sets lead_purged_at + confirmation

Tunable via env: NIDAAN_LEAD_RETENTION_DAYS (default 30), NIDAAN_LEAD_NOTICE_DAYS
(default 7 = notice this many days before the purge).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.retention")

_DOCS_DIR = Path(__file__).parent / "uploads" / "nidaan-docs"


def _retention_days() -> int:
    try:
        return max(1, int(os.getenv("NIDAAN_LEAD_RETENTION_DAYS", "30")))
    except ValueError:
        return 30


def _notice_days() -> int:
    try:
        return max(0, int(os.getenv("NIDAAN_LEAD_NOTICE_DAYS", "7")))
    except ValueError:
        return 7


async def _claim_doc_names(conn, claim_id: int) -> list[str]:
    rows = await (await conn.execute(
        "SELECT stored_name FROM nidaan_claim_documents WHERE claim_id=?", (claim_id,))).fetchall()
    return [r[0] for r in rows if r[0]]


async def run_lead_retention() -> dict:
    """One sweep: send pre-notices, then purge expired leads' documents.
    Idempotent — lead_notice_at / lead_purged_at gate each stage. Returns counts."""
    retention = _retention_days()
    notice = _notice_days()
    notice_after = max(0, retention - notice)  # send the heads-up at this age
    notified = purged = 0

    import biz_nidaan_notifications as _nnot  # lazy: avoid import cycle

    # ── Stage 1: pre-notice (only to leads that actually have documents to lose)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        due = await (await conn.execute(
            """SELECT claim_id, account_id FROM nidaan_claims
               WHERE payment_status='unpaid_lead'
                 AND lead_purged_at IS NULL AND lead_notice_at IS NULL
                 AND created_at <= datetime('now', ?)""",
            (f"-{notice_after} days",))).fetchall()
        purge_on = (datetime.utcnow() + timedelta(days=notice)).strftime("%d %b %Y")
        for r in due:
            try:
                if not await _claim_doc_names(conn, r["claim_id"]):
                    # No documents → no deletion notice; still stamp so we don't recheck daily.
                    await conn.execute("UPDATE nidaan_claims SET lead_notice_at=CURRENT_TIMESTAMP WHERE claim_id=?", (r["claim_id"],))
                    continue
                await _nnot.on_lead_deletion_notice(r["claim_id"], r["account_id"], purge_on)
                await conn.execute("UPDATE nidaan_claims SET lead_notice_at=CURRENT_TIMESTAMP WHERE claim_id=?", (r["claim_id"],))
                notified += 1
            except Exception as e:
                logger.warning("lead retention notice failed for claim %s: %s", r["claim_id"], e)
        await conn.commit()

    # ── Stage 2: purge documents past the full retention window
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        expired = await (await conn.execute(
            """SELECT claim_id, account_id FROM nidaan_claims
               WHERE payment_status='unpaid_lead' AND lead_purged_at IS NULL
                 AND created_at <= datetime('now', ?)""",
            (f"-{retention} days",))).fetchall()
        for r in expired:
            cid = r["claim_id"]
            try:
                names = await _claim_doc_names(conn, cid)
                for n in names:
                    try:
                        (_DOCS_DIR / n).unlink(missing_ok=True)
                    except Exception as fe:
                        logger.warning("could not delete file %s: %s", n, fe)
                await conn.execute("DELETE FROM nidaan_claim_documents WHERE claim_id=?", (cid,))
                # Reset the checklist so the lead could re-upload if they return.
                await conn.execute(
                    "UPDATE nidaan_claim_doc_checklist SET received=0, received_via=NULL, received_doc_id=NULL WHERE claim_id=?",
                    (cid,))
                await conn.execute("UPDATE nidaan_claims SET lead_purged_at=CURRENT_TIMESTAMP WHERE claim_id=?", (cid,))
                await conn.commit()
                if names:  # only tell people whose docs we actually deleted
                    try:
                        await _nnot.on_lead_data_purged(cid, r["account_id"])
                    except Exception as ne:
                        logger.warning("purge confirmation failed for claim %s: %s", cid, ne)
                    purged += 1
            except Exception as e:
                logger.warning("lead retention purge failed for claim %s: %s", cid, e)

    if notified or purged:
        logger.info("Lead retention sweep: %d notice(s), %d purge(s)", notified, purged)
    return {"notified": notified, "purged": purged}
