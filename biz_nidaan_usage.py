# -*- coding: utf-8 -*-
"""Which ops screens are really used - so a tab is retired on evidence, never on a guess.

Founder, 1 Oct: "a lot of garbage tabs are there with no use ... we should find out inactive codes
and remove them after checking twice or thrice to be sure". Nothing recorded which screen anyone
opened, so "no one uses it" could only be a guess. This counts opens per staff member, per screen,
per day (IST) - a number, nothing else: no claim, no customer, no time of day.

report() is what a super-admin reads before any tab is archived.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.usage")
DB_PATH = db.DB_PATH
IST = timezone(timedelta(hours=5, minutes=30))
PANEL_RE = re.compile(r"^[a-z0-9_]{1,24}$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS nidaan_ui_opens (
    day       TEXT NOT NULL,
    staff_id  INTEGER NOT NULL,
    panel     TEXT NOT NULL,
    n         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, staff_id, panel)
);
"""


async def opened(staff_id: int, panel: str) -> bool:
    panel = (panel or "").strip().lower()
    if not staff_id or not PANEL_RE.match(panel):
        return False
    day = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.executescript(SCHEMA)
            await c.execute(
                "INSERT INTO nidaan_ui_opens (day, staff_id, panel, n) VALUES (?,?,?,1) "
                "ON CONFLICT(day, staff_id, panel) DO UPDATE SET n=n+1", (day, int(staff_id), panel))
            await c.commit()
        return True
    except Exception as e:  # noqa: BLE001 - counting never gets in anyone's way
        logger.info("ui open count failed: %s", e)
        return False


async def report(days: int = 14) -> list[dict]:
    """Per screen over the last `days`: opens, people, last day used."""
    since = (datetime.now(IST) - timedelta(days=int(days))).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        await c.executescript(SCHEMA)
        return [dict(r) for r in await (await c.execute(
            "SELECT panel, SUM(n) AS opens, COUNT(DISTINCT staff_id) AS people, MAX(day) AS last_day "
            "FROM nidaan_ui_opens WHERE day>=? GROUP BY panel ORDER BY opens DESC", (since,))).fetchall()]
