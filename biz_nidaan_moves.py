# -*- coding: utf-8 -*-
"""Where each claim went, from which bucket, and who moved it - one row per move.

Founder, 30 Sep: the end-of-day summary must say "how many claims move from one bucket to another,
and who did it". Until now a move overwrote the claim's current bucket and left only a sentence in
the remarks ("Live Cases -> moved to Pending Draft"), so a report had to parse English. This is the
structured record: claim, from, to, kind, staff id and name, time.

Written by the four functions every bucket change goes through (biz_nidaan_buckets.move,
start_l2, undo_handover, biz_nidaan_case_state.move_stage). "l2_claims" stands for the Level-2
waiting list, before a claim has a bucket. A failure to record never stops the move itself.
"""
from __future__ import annotations

import logging

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.moves")
DB_PATH = db.DB_PATH
L2_WAITING = "l2_claims"

SCHEMA = """
CREATE TABLE IF NOT EXISTS nidaan_bucket_move_log (
    move_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id  INTEGER NOT NULL,
    from_key  TEXT NOT NULL DEFAULT '',
    to_key    TEXT NOT NULL DEFAULT '',
    kind      TEXT NOT NULL DEFAULT 'forward',   -- forward | back | park | resume | start | undo | auto
    staff_id  INTEGER,                           -- NULL for the system
    actor     TEXT NOT NULL DEFAULT '',
    moved_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bmovelog_at ON nidaan_bucket_move_log(moved_at);
CREATE INDEX IF NOT EXISTS idx_bmovelog_claim ON nidaan_bucket_move_log(claim_id, move_id);
"""


async def record(claim_id: int, from_key: str, to_key: str, *, kind: str = "forward",
                 staff_id: int = 0, actor: str = "") -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.executescript(SCHEMA)
            await c.execute(
                "INSERT INTO nidaan_bucket_move_log (claim_id, from_key, to_key, kind, staff_id, actor) "
                "VALUES (?,?,?,?,?,?)",
                (int(claim_id), (from_key or "")[:40], (to_key or "")[:40], (kind or "")[:12],
                 int(staff_id) if staff_id else None, (actor or "")[:80]))
            await c.commit()
    except Exception as e:  # noqa: BLE001 - the move stands whether or not the record did
        logger.warning("bucket move record failed for %s: %s", claim_id, e)


async def between(start_utc: str, end_utc: str) -> list[dict]:
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            await c.executescript(SCHEMA)
            return [dict(r) for r in await (await c.execute(
                "SELECT * FROM nidaan_bucket_move_log WHERE moved_at>=? AND moved_at<? "
                "ORDER BY move_id", (start_utc, end_utc))).fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.warning("bucket moves read failed: %s", e)
        return []
