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
