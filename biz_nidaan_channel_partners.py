"""
NidaanPartner — CHANNEL PARTNERS (CP).

A Channel Partner is an agent who sends us business but deliberately does NOT want to appear as a
Nidaan subscriber. They ask one of our staff to file the claim; we still need to know who
introduced it so commission can be settled and referrals tracked.

The control that matters here is the approval gate. A CP is a name that money will eventually be
paid against, so a sub-admin can PROPOSE one but only a super-admin can approve it, and we record
WHICH super-admin did — an unapproved CP is invisible in the claim form, so it can never quietly
appear on a claim. A super-admin creating one approves it in the same act (recorded as such).
"""
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.cp")
DB_PATH = db.DB_PATH

STATUSES = ("pending", "approved", "rejected", "disabled")


def _clean_phone(v: str) -> str:
    d = "".join(ch for ch in (v or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else d


def _clean_email(v: str) -> str:
    v = (v or "").strip().lower()
    return v if ("@" in v and "." in v.split("@")[-1]) else ""


async def list_partners(*, approved_only: bool = False) -> list[dict]:
    """All CPs (admin view), or only the selectable ones (staff view)."""
    q = "SELECT * FROM nidaan_channel_partners"
    params: tuple = ()
    if approved_only:
        q += " WHERE status='approved'"
    q += " ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, name COLLATE NOCASE"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(q, params)).fetchall()
    return [dict(r) for r in rows]


async def get_partner(cp_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT * FROM nidaan_channel_partners WHERE cp_id=?", (cp_id,))).fetchone()
    return dict(r) if r else None


async def create_partner(*, name: str, email: str = "", phone: str = "", company: str = "",
                         notes: str = "", by_staff_id: Optional[int] = None,
                         by_name: str = "", is_super_admin: bool = False) -> dict:
    """Add a CP. A super-admin's own entry is approved on creation (and recorded as approved by
    them); anyone else's starts PENDING and cannot be selected until a super-admin approves."""
    name = (name or "").strip()[:120]
    if not name:
        return {"ok": False, "error": "name_required"}
    email, phone = _clean_email(email), _clean_phone(phone)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        dup = await (await conn.execute(
            "SELECT cp_id FROM nidaan_channel_partners WHERE LOWER(name)=LOWER(?) "
            "AND status<>'rejected'", (name,))).fetchone()
        if dup:
            return {"ok": False, "error": "duplicate"}
        status = "approved" if is_super_admin else "pending"
        cur = await conn.execute(
            """INSERT INTO nidaan_channel_partners
                 (name, email, phone, company, notes, status, created_by_staff_id,
                  created_by_name, approved_by_staff_id, approved_by_name, approved_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)""",
            (name, email, phone, (company or "").strip()[:120], (notes or "").strip()[:500],
             status, by_staff_id, (by_name or "")[:80],
             by_staff_id if is_super_admin else None,
             (by_name or "")[:80] if is_super_admin else "",
             None if not is_super_admin else __import__("datetime").datetime.utcnow()
             .strftime("%Y-%m-%d %H:%M:%S")))
        await conn.commit()
        return {"ok": True, "cp_id": cur.lastrowid, "status": status}


async def set_status(cp_id: int, status: str, *, by_staff_id: Optional[int] = None,
                     by_name: str = "") -> bool:
    """Approve / reject / disable a CP. Approval stamps WHO authorised it."""
    if status not in STATUSES:
        return False
    async with aiosqlite.connect(DB_PATH) as conn:
        if status == "approved":
            cur = await conn.execute(
                "UPDATE nidaan_channel_partners SET status='approved', approved_by_staff_id=?, "
                "approved_by_name=?, approved_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP "
                "WHERE cp_id=?", (by_staff_id, (by_name or "")[:80], cp_id))
        else:
            cur = await conn.execute(
                "UPDATE nidaan_channel_partners SET status=?, updated_at=CURRENT_TIMESTAMP "
                "WHERE cp_id=?", (status, cp_id))
        await conn.commit()
        return cur.rowcount > 0


async def update_partner(cp_id: int, **fields) -> bool:
    """Edit a CP's details. Editing does NOT re-open approval — status is changed only through
    set_status, so a detail tweak can't silently un-approve or self-approve a partner."""
    allowed = {"name", "email", "phone", "company", "notes"}
    sets, vals = [], []
    for k, v in (fields or {}).items():
        if k not in allowed or v is None:
            continue
        if k == "email":
            v = _clean_email(v)
        elif k == "phone":
            v = _clean_phone(v)
        else:
            v = str(v).strip()[:500]
        sets.append(f"{k}=?")
        vals.append(v)
    if not sets:
        return False
    vals.append(cp_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            f"UPDATE nidaan_channel_partners SET {', '.join(sets)}, updated_at=CURRENT_TIMESTAMP "
            f"WHERE cp_id=?", vals)
        await conn.commit()
        return cur.rowcount > 0


async def pending_count() -> int:
    async with aiosqlite.connect(DB_PATH) as conn:
        r = await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_channel_partners WHERE status='pending'")).fetchone()
    return int(r[0]) if r else 0
