# =============================================================================
#  biz_nidaan_stats.py — how the two work screens are actually performing
# =============================================================================
#
#  The founder asked for "a simple analytics how our processes are performing in
#  terms of numbers" on top of L2 Claims and Consolidation, and approved the
#  shape before anything was built.
#
#  Two rules this module follows:
#
#  1. Every number answers "is this moving?", not "how much have we done?".
#     The two that matter most are the OLDEST thing waiting and the count STUCK,
#     because those name the claims going quiet. Everything else is context.
#
#  2. A number we cannot derive honestly is not shown. There is no estimate and
#     no placeholder here: if the data cannot answer it, the line is absent.
#
#  All of it is SQL over indexed columns on at most a few hundred open claims —
#  one round trip per screen, nothing computed in the browser.
# =============================================================================
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.stats")

STUCK_DAYS = 14          # a claim in one bucket this long is not moving
WEEK = "-7 days"

# A claim is "open" for these numbers if it is not archived and not finished with.
_OPEN = "COALESCE(c.archived,0)=0 AND COALESCE(c.status,'') NOT IN ('closed','withdrawn')"
# In the line = it has a bucket. Handed over but not started shows as "to start".
_IN_LINE = "COALESCE(c.pipeline_stage,'') <> ''"


async def _one(conn, sql: str, args: tuple = ()) -> float:
    row = await (await conn.execute(sql, args)).fetchone()
    return (row[0] if row and row[0] is not None else 0)


async def l2_claims() -> dict:
    """The queue waiting to be handed over: what is in it, how old, and what left it."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        waiting_where = (
            "FROM nidaan_claims c WHERE %s AND c.review_outcome='can_fight' "
            "AND c.l2_handover_at IS NULL AND COALESCE(c.pipeline_stage,'')=''" % _OPEN)

        waiting = int(await _one(conn, "SELECT COUNT(*) " + waiting_where))
        oldest = int(await _one(conn,
            "SELECT MAX(CAST(julianday('now') - julianday(c.created_at) AS INT)) " + waiting_where))
        docs_done = int(await _one(conn,
            "SELECT COUNT(*) " + waiting_where + " AND c.docs_complete_at IS NOT NULL"))

        handed_week = int(await _one(conn,
            "SELECT COUNT(*) FROM nidaan_claims c WHERE c.l2_handover_at >= datetime('now', ?)",
            (WEEK,)))
        sent_back_week = int(await _one(conn,
            "SELECT COUNT(DISTINCT target_id) FROM nidaan_audit_log "
            "WHERE action='l2.handover_undo' AND created_at >= datetime('now', ?)", (WEEK,)))
        # How long a claim waits before it is handed over, over the last 90 days of handovers.
        avg_days = await _one(conn,
            "SELECT AVG(julianday(c.l2_handover_at) - julianday(c.created_at)) "
            "FROM nidaan_claims c WHERE c.l2_handover_at IS NOT NULL "
            "AND c.l2_handover_at >= datetime('now','-90 days')")

    return {
        "waiting": waiting,
        "oldest_days": oldest,
        "docs_complete": docs_done,
        "handed_this_week": handed_week,
        "sent_back_this_week": sent_back_week,
        "avg_days_to_hand_over": round(float(avg_days), 1) if avg_days else None,
    }


async def consolidation() -> dict:
    """The line itself: where the work is sitting, what moved, and what has gone quiet."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        in_line = int(await _one(conn,
            "SELECT COUNT(*) FROM nidaan_claims c WHERE %s AND %s" % (_OPEN, _IN_LINE)))
        to_start = int(await _one(conn,
            "SELECT COUNT(*) FROM nidaan_claims c WHERE %s AND c.l2_handover_at IS NOT NULL "
            "AND COALESCE(c.pipeline_stage,'')=''" % _OPEN))
        moved_week = int(await _one(conn,
            "SELECT COUNT(DISTINCT target_id) FROM nidaan_audit_log "
            "WHERE action='bucket.move' AND created_at >= datetime('now', ?)", (WEEK,)))
        stuck = int(await _one(conn,
            "SELECT COUNT(*) FROM nidaan_claims c WHERE %s AND %s "
            "AND c.pipeline_stage_at IS NOT NULL "
            "AND julianday('now') - julianday(c.pipeline_stage_at) > ?" % (_OPEN, _IN_LINE),
            (STUCK_DAYS,)))

        # Per bucket: how many sit there, and how long they have sat on average. Ordered by the
        # line's own order so it reads like the process, not alphabetically.
        rows = await (await conn.execute(
            """SELECT c.pipeline_stage AS key, COUNT(*) AS n,
                      AVG(julianday('now') - julianday(c.pipeline_stage_at)) AS avg_days,
                      MAX(CAST(julianday('now') - julianday(c.pipeline_stage_at) AS INT)) AS oldest
                 FROM nidaan_claims c
                WHERE %s AND %s
                GROUP BY c.pipeline_stage""" % (_OPEN, _IN_LINE))).fetchall()
        counts = {r["key"]: dict(r) for r in rows}

        order = await (await conn.execute(
            "SELECT bucket_key, name_en, sort_order FROM nidaan_buckets "
            "WHERE active=1 ORDER BY sort_order")).fetchall()

    buckets = []
    for b in order:
        k = b["bucket_key"]
        hit = counts.get(k) or {}
        buckets.append({
            "key": k,
            "name": b["name_en"],
            "n": int(hit.get("n") or 0),
            "avg_days": round(float(hit["avg_days"]), 1) if hit.get("avg_days") else None,
            "oldest_days": int(hit["oldest"]) if hit.get("oldest") else None,
        })

    return {
        "in_line": in_line,
        "to_start": to_start,
        "moved_this_week": moved_week,
        "stuck": stuck,
        "stuck_days": STUCK_DAYS,
        "buckets": buckets,
    }


async def both() -> dict:
    return {"l2": await l2_claims(), "consolidation": await consolidation()}


# ── Reviewed, and waiting to be paid for ─────────────────────────────────────
# The gap between "we told them they have a case" and "they paid us to fight it". A claim sits
# here because of something a PERSON has to do — ring them, explain the fee, chase the branch —
# and until now it sat inside All Claims looking like every other claim, which is how 17 winnable
# cases came to be waiting an average of nine days with nobody counting.
#
# The founder asked for the dates as well as the list (19 Sep): "their dates and timeline captures
# there for everything when a claim started, when it's review delivered, when payment is done."
# Those three dates turn "it is pending" into "it has been nine days since we told them".

async def awaiting_fee(limit: int = 300) -> dict:
    """Claims whose review has been delivered but whose Level-2 fee is not covered.

    Coverage means the same three things it means everywhere else — an L2 fee paid, a paid claim,
    or a live subscription — so this screen and the handover gate can never disagree about whether
    a claim has been paid for. That disagreement was NP-112.
    """
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            """
            SELECT claim_id, COALESCE(complainant_name,'') AS complainant_name,
                   COALESCE(insured_name,'')  AS insured_name,
                   COALESCE(insurer_name,'')  AS insurer_name,
                   COALESCE(disputed_amount,0) AS disputed_amount,
                   COALESCE(review_outcome,'') AS review_outcome,
                   COALESCE(branch_code,'')    AS branch_code,
                   created_at, review_delivered_at, paid_at, l2_paid_at,
                   COALESCE(payment_status,'')    AS payment_status,
                   COALESCE(l2_payment_status,'') AS l2_payment_status
            FROM nidaan_claims
            WHERE review_delivered_at IS NOT NULL
              AND COALESCE(archived,0)=0
              AND COALESCE(status,'') NOT IN ('closed','withdrawn')
              AND LOWER(COALESCE(l2_payment_status,'')) <> 'paid'
              AND LOWER(COALESCE(payment_status,'')) NOT IN ('paid','subscription')
            ORDER BY review_delivered_at ASC LIMIT ?
            """, (int(limit),))).fetchall()]

    out, winnable = [], 0
    for r in rows:
        # A claim we said had NO case is not a claim to chase a fee for. It is listed, clearly
        # marked, so nobody rings that person by mistake.
        fightable = (r["review_outcome"] == "can_fight")
        if fightable:
            winnable += 1
        out.append({
            "claim_id": r["claim_id"],
            "who": r["complainant_name"] or r["insured_name"],
            "insurer": r["insurer_name"],
            "amount": r["disputed_amount"],
            "outcome": r["review_outcome"],
            "fightable": fightable,
            "branch_code": r["branch_code"],
            "started_at": str(r["created_at"] or ""),
            "review_delivered_at": str(r["review_delivered_at"] or ""),
            "paid_at": str(r["l2_paid_at"] or r["paid_at"] or ""),
            "days_since_review": _days(r["review_delivered_at"]),
            "days_since_start": _days(r["created_at"]),
        })
    return {"ok": True, "waiting": len(out), "winnable": winnable,
            "disputed_total": sum(int(r["amount"] or 0) for r in out if r["fightable"]),
            "rows": out}


def _days(ts):
    if not ts:
        return None
    from datetime import datetime as _dt
    raw = str(ts)[:19].replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return max(0, (_dt.utcnow() - _dt.strptime(raw if fmt != "%Y-%m-%d" else raw[:10],
                                                       fmt)).days)
        except ValueError:
            continue
    return None
