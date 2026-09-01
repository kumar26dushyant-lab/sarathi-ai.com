"""
NidaanPartner CRM (marketing/sales) — leads pipeline + timeline logic.

The AI "team lead" layer (comment-aware next-step suggestions, voice) builds on this; this module
is the deterministic core: create/list/update leads, move stages, assign, comment, follow-ups,
convert. Every mutation writes to the per-lead timeline. Never raises silently on logging.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.crm")
DB_PATH = db.DB_PATH

# Default pipeline (configurable later via ops settings).
STAGES = ["new", "contacted", "interested", "demo", "negotiation", "won", "lost"]
STAGE_LABELS = {
    "new": "New", "contacted": "Contacted", "interested": "Interested", "demo": "Demo",
    "negotiation": "Negotiation", "won": "Won", "lost": "Lost",
}
OPEN_STAGES = ["new", "contacted", "interested", "demo", "negotiation"]


async def _log(conn, lead_id: int, kind: str, body: str = "", by_staff_id=None,
               by_name: str = "", meta: str = "") -> None:
    await conn.execute(
        "INSERT INTO nidaan_crm_activity (lead_id, kind, body, by_staff_id, by_name, meta) "
        "VALUES (?,?,?,?,?,?)", (lead_id, kind, (body or "")[:2000], by_staff_id, by_name or "", meta or ""))


async def create_lead(*, name: str, phone: str = "", email: str = "", company: str = "",
                      city: str = "", source: str = "", owner_staff_id=None, interest: str = "",
                      notes: str = "", next_action: str = "", next_followup_at: str = "",
                      created_by_staff_id=None, created_by_name: str = "") -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_crm_leads
               (name, phone, email, company, city, source, owner_staff_id, interest, notes,
                next_action, next_followup_at, created_by_staff_id, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (name.strip(), phone.strip(), email.strip(), company.strip(), city.strip(),
             source.strip(), owner_staff_id, interest.strip(), notes.strip(),
             next_action.strip(), (next_followup_at or None), created_by_staff_id))
        lead_id = cur.lastrowid
        await _log(conn, lead_id, "created", f"Lead created: {name}", created_by_staff_id, created_by_name)
        if owner_staff_id:
            await _log(conn, lead_id, "assign", f"Assigned to staff #{owner_staff_id}", created_by_staff_id, created_by_name)
        await conn.commit()
    return lead_id


async def list_leads(*, stage: str = "", owner_staff_id=None, search: str = "",
                     archived: bool = False, mine_staff_id=None, limit: int = 500) -> list:
    q = "SELECT l.*, s.name AS owner_name FROM nidaan_crm_leads l " \
        "LEFT JOIN nidaan_staff s ON s.staff_id = l.owner_staff_id WHERE 1=1"
    args: list = []
    q += " AND COALESCE(l.archived,0)=?"; args.append(1 if archived else 0)
    if stage:
        q += " AND l.stage=?"; args.append(stage)
    if owner_staff_id is not None:
        q += " AND l.owner_staff_id=?"; args.append(owner_staff_id)
    if mine_staff_id is not None:
        q += " AND (l.owner_staff_id=? OR l.created_by_staff_id=?)"; args.extend([mine_staff_id, mine_staff_id])
    if search:
        q += " AND (l.name LIKE ? OR l.phone LIKE ? OR l.email LIKE ? OR l.company LIKE ?)"
        s = f"%{search}%"; args.extend([s, s, s, s])
    q += " ORDER BY (l.next_followup_at IS NULL), l.next_followup_at ASC, l.updated_at DESC LIMIT ?"
    args.append(limit)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await conn.execute(q, tuple(args))).fetchall()]


async def get_lead(lead_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT l.*, s.name AS owner_name FROM nidaan_crm_leads l "
            "LEFT JOIN nidaan_staff s ON s.staff_id=l.owner_staff_id WHERE l.lead_id=?", (lead_id,))).fetchone()
        if not r:
            return None
        lead = dict(r)
        lead["activity"] = [dict(a) for a in await (await conn.execute(
            "SELECT * FROM nidaan_crm_activity WHERE lead_id=? ORDER BY created_at DESC, act_id DESC LIMIT 200",
            (lead_id,))).fetchall()]
    return lead


async def update_lead(lead_id: int, *, by_staff_id=None, by_name: str = "", **fields) -> bool:
    """Update allowed fields; logs stage/assign/followup changes to the timeline."""
    allowed = {"name", "phone", "email", "company", "city", "source", "stage", "owner_staff_id",
               "next_action", "next_followup_at", "interest", "notes", "lost_reason", "archived"}
    sets, args, logs = [], [], []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await (await conn.execute("SELECT * FROM nidaan_crm_leads WHERE lead_id=?", (lead_id,))).fetchone()
        if not cur:
            return False
        cur = dict(cur)
        for k, v in fields.items():
            if k not in allowed:
                continue
            if str(cur.get(k) or "") == str(v or ""):
                continue
            sets.append(f"{k}=?"); args.append(v)
            if k == "stage":
                logs.append(("stage", f"Stage → {STAGE_LABELS.get(str(v), v)}"))
            elif k == "owner_staff_id":
                logs.append(("assign", f"Reassigned to staff #{v}"))
            elif k == "next_followup_at":
                logs.append(("followup", f"Next follow-up set: {v}"))
        if not sets:
            return True
        sets.append("updated_at=CURRENT_TIMESTAMP")
        await conn.execute(f"UPDATE nidaan_crm_leads SET {', '.join(sets)} WHERE lead_id=?",
                           tuple(args) + (lead_id,))
        for kind, body in logs:
            await _log(conn, lead_id, kind, body, by_staff_id, by_name)
        await conn.commit()
    return True


async def add_comment(lead_id: int, body: str, *, by_staff_id=None, by_name: str = "",
                      kind: str = "comment") -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nidaan_crm_activity (lead_id, kind, body, by_staff_id, by_name) VALUES (?,?,?,?,?)",
            (lead_id, kind, (body or "")[:2000], by_staff_id, by_name or ""))
        await conn.execute("UPDATE nidaan_crm_leads SET updated_at=CURRENT_TIMESTAMP WHERE lead_id=?", (lead_id,))
        await conn.commit()
        return cur.lastrowid


async def convert_lead(lead_id: int, account_id: Optional[int] = None, *, by_staff_id=None,
                       by_name: str = "") -> bool:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_crm_leads SET stage='won', converted_account_id=COALESCE(?,converted_account_id), "
            "updated_at=CURRENT_TIMESTAMP WHERE lead_id=?", (account_id, lead_id))
        await _log(conn, lead_id, "won", "Marked WON" + (f" → account #{account_id}" if account_id else ""),
                   by_staff_id, by_name)
        await conn.commit()
    return True


async def pipeline_counts(*, mine_staff_id=None) -> dict:
    q = "SELECT stage, COUNT(*) n FROM nidaan_crm_leads WHERE COALESCE(archived,0)=0"
    args: list = []
    if mine_staff_id is not None:
        q += " AND owner_staff_id=?"; args.append(mine_staff_id)
    q += " GROUP BY stage"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = {r["stage"]: r["n"] for r in await (await conn.execute(q, tuple(args))).fetchall()}
    return {s: rows.get(s, 0) for s in STAGES}


async def due_followups(*, owner_staff_id=None, within_hours: int = 0) -> list:
    """Open leads whose follow-up is due (past, or within `within_hours`). For the daily bot digest."""
    now = datetime.utcnow()
    cutoff = now.strftime("%Y-%m-%d %H:%M:%S") if within_hours == 0 else \
        (now.replace(microsecond=0)).strftime("%Y-%m-%d %H:%M:%S")
    q = ("SELECT l.lead_id, l.name, l.phone, l.stage, l.next_action, l.next_followup_at, l.owner_staff_id "
         "FROM nidaan_crm_leads l WHERE COALESCE(l.archived,0)=0 AND l.stage IN "
         "('new','contacted','interested','demo','negotiation') AND l.next_followup_at IS NOT NULL "
         "AND l.next_followup_at<=?")
    args: list = [cutoff]
    if owner_staff_id is not None:
        q += " AND l.owner_staff_id=?"; args.append(owner_staff_id)
    q += " ORDER BY l.next_followup_at ASC"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await conn.execute(q, tuple(args))).fetchall()]
