# -*- coding: utf-8 -*-
"""Adding or removing a Channel Partner on a claim that already exists - with approval.

Founder, 30 Sep (claim #226): "my business raised claims have option to select CP, if they forget
to add CP while raising any claim then they should have an option to add CP later ... It should
come for superadmin approval and once one of the superadmin approved then that CP can be added ...
with add, we need option to delete too with approval, we need to start thinking from both sides."

A CP on a claim decides who is credited - and, in time, who is paid. So nobody changes it on
their own: a staff member ASKS (add an approved CP, or remove the one there, with a reason), any
super-admin approves or rejects, and only an approval changes the claim. Every step goes on the
claim's timeline with names, and the person who asked hears the answer.

Rules:
  * only My Business claims (raised by a staff member under their SP- code) carry a CP today, so
    only those can be changed here;
  * add only when the claim has no CP; remove only the CP it has. To change one, remove it, then
    add the other - two decisions, both on the record;
  * the CP being added must be approved - the same gate as raising a claim with one;
  * one open request per claim at a time; the asker (or a super-admin) can withdraw it;
  * on approval everything is checked again, because a claim can change while a request waits.
"""
from __future__ import annotations

import logging

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.claim_cp")
DB_PATH = db.DB_PATH
SUPER = "super_admin"

SCHEMA = """
CREATE TABLE IF NOT EXISTS nidaan_claim_cp_requests (
    req_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id        INTEGER NOT NULL,
    action          TEXT NOT NULL,
    cp_id           INTEGER NOT NULL,
    cp_name         TEXT NOT NULL DEFAULT '',
    reason          TEXT NOT NULL DEFAULT '',
    requested_by    INTEGER,
    requested_name  TEXT NOT NULL DEFAULT '',
    requested_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status          TEXT NOT NULL DEFAULT 'pending',
    decided_by      INTEGER,
    decided_name    TEXT NOT NULL DEFAULT '',
    decided_at      TIMESTAMP,
    decision_note   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cpreq_claim ON nidaan_claim_cp_requests(claim_id, req_id);
CREATE INDEX IF NOT EXISTS idx_cpreq_status ON nidaan_claim_cp_requests(status);
"""


class CPError(Exception):
    """A refusal, in words the person can act on."""


async def _conn():
    c = await aiosqlite.connect(DB_PATH)
    c.row_factory = aiosqlite.Row
    await c.executescript(SCHEMA)
    return c


async def _claim(c, claim_id: int):
    r = await (await c.execute(
        "SELECT claim_id, branch_code, origin, channel_partner_id, associate_referrer, archived, "
        "status FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    return dict(r) if r else None


def _my_business(cl: dict) -> bool:
    return (cl.get("branch_code") or "").strip().upper().startswith("SP-")


async def _timeline(claim_id: int, summary: str, actor: str) -> None:
    try:
        import biz_nidaan as _n
        await _n.record_claim_activity(claim_id, "cp_change", channel="web", actor=actor or "staff",
                                       summary=summary[:400])
    except Exception as e:  # noqa: BLE001
        logger.warning("cp timeline failed for %s: %s", claim_id, e)


async def _tell(ids, title: str, body: str, *, event_key: str, claim_id: int) -> None:
    try:
        import biz_nidaan_notifications as nn
        ids = [i for i in ids if i]
        if ids:
            await nn.notify_staff_inapp(ids, title, body, event_key=event_key, claim_id=int(claim_id),
                                        email=False)
    except Exception as e:  # noqa: BLE001 - the decision stands; it is on the claim either way
        logger.warning("cp note failed: %s", e)


async def state(claim_id: int) -> dict:
    """What the claim screen shows: the CP now, an open request, and the recent history."""
    c = await _conn()
    try:
        cl = await _claim(c, claim_id)
        if not cl:
            return {"ok": False}
        cp = None
        if cl.get("channel_partner_id"):
            r = await (await c.execute("SELECT cp_id, name, company, status FROM nidaan_channel_partners "
                                       "WHERE cp_id=?", (cl["channel_partner_id"],))).fetchone()
            cp = dict(r) if r else {"cp_id": cl["channel_partner_id"],
                                    "name": cl.get("associate_referrer") or ""}
        hist = [dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_claim_cp_requests WHERE claim_id=? ORDER BY req_id DESC LIMIT 6",
            (int(claim_id),))).fetchall()]
    finally:
        await c.close()
    return {"ok": True, "eligible": _my_business(cl), "cp": cp,
            "pending": next((h for h in hist if h["status"] == "pending"), None), "history": hist}


async def request_change(claim_id: int, action: str, *, cp_id: int = 0, reason: str = "",
                         staff: dict) -> dict:
    action = (action or "").strip().lower()
    reason = (reason or "").strip()
    if action not in ("add", "remove"):
        raise CPError("Choose add or remove.")
    if len(reason) < 5:
        raise CPError("Please say why - one line is enough. The super-admin decides from it.")
    who = (staff.get("name") or "staff")[:80]
    c = await _conn()
    try:
        cl = await _claim(c, claim_id)
        if not cl or cl.get("archived") or (cl.get("status") or "") in ("closed", "withdrawn"):
            raise CPError("That claim is closed or does not exist.")
        if not _my_business(cl):
            raise CPError("A Channel Partner can only be set on a My Business claim.")
        if await (await c.execute("SELECT 1 FROM nidaan_claim_cp_requests WHERE claim_id=? "
                                  "AND status='pending'", (int(claim_id),))).fetchone():
            raise CPError("There is already a request waiting on this claim.")
        if action == "add":
            if cl.get("channel_partner_id"):
                raise CPError("This claim already has a Channel Partner. Ask to remove it first.")
            r = await (await c.execute("SELECT cp_id, name, status FROM nidaan_channel_partners "
                                       "WHERE cp_id=?", (int(cp_id or 0),))).fetchone()
            if not r or r["status"] != "approved":
                raise CPError("Choose an approved Channel Partner.")
            cp_id, cp_name = r["cp_id"], r["name"]
        else:
            if not cl.get("channel_partner_id"):
                raise CPError("This claim has no Channel Partner to remove.")
            cp_id = cl["channel_partner_id"]
            r = await (await c.execute("SELECT name FROM nidaan_channel_partners WHERE cp_id=?",
                                       (cp_id,))).fetchone()
            cp_name = (r["name"] if r else "") or (cl.get("associate_referrer") or "")
        cur = await c.execute(
            "INSERT INTO nidaan_claim_cp_requests (claim_id, action, cp_id, cp_name, reason, "
            "requested_by, requested_name) VALUES (?,?,?,?,?,?,?)",
            (int(claim_id), action, int(cp_id), cp_name[:120], reason[:400],
             staff.get("staff_id"), who))
        await c.commit()
        req_id = cur.lastrowid
    finally:
        await c.close()
    await _timeline(claim_id, "%s asked to %s Channel Partner %s - waiting for a super-admin. "
                              "Reason: %s" % (who, action, cp_name, reason), who)
    try:
        import biz_nidaan_notifications as nn
        admins = [a["staff_id"] for a in await nn._super_admin_staff()]
    except Exception:  # noqa: BLE001
        admins = []
    await _tell(admins, "\U0001f91d Approve a Channel Partner change on NP-%s?" % claim_id,
                "%s asks to %s Channel Partner %s on claim NP-%s.\nReason: %s\n\nOpen the claim to "
                "approve or reject. / क्लेम खोलकर मंज़ूर या अस्वीकार करें।"
                % (who, action, cp_name, claim_id, reason), event_key="cp.claim_request", claim_id=claim_id)
    return {"ok": True, "req_id": req_id}


async def decide(req_id: int, approve: bool, *, note: str = "", staff: dict) -> dict:
    if (staff.get("role") or "") != SUPER:
        raise CPError("Only a super-admin can decide this.")
    note = (note or "").strip()
    if not approve and len(note) < 3:
        raise CPError("Say why it is rejected - the person who asked will read it.")
    who = (staff.get("name") or "super-admin")[:80]
    c = await _conn()
    try:
        r = await (await c.execute("SELECT * FROM nidaan_claim_cp_requests WHERE req_id=?",
                                   (int(req_id),))).fetchone()
        if not r:
            raise CPError("That request does not exist.")
        req = dict(r)
        if req["status"] != "pending":
            raise CPError("That request has already been %s." % req["status"])
        cl = await _claim(c, req["claim_id"])
        if approve:
            # Everything again: the claim or the partner may have changed while this waited.
            if not cl or cl.get("archived") or not _my_business(cl):
                raise CPError("The claim can no longer take a Channel Partner.")
            if req["action"] == "add":
                if cl.get("channel_partner_id"):
                    raise CPError("The claim got a Channel Partner meanwhile - reject this one.")
                p = await (await c.execute("SELECT name, status FROM nidaan_channel_partners "
                                           "WHERE cp_id=?", (req["cp_id"],))).fetchone()
                if not p or p["status"] != "approved":
                    raise CPError("That Channel Partner is no longer approved.")
                await c.execute("UPDATE nidaan_claims SET channel_partner_id=?, associate_referrer=? "
                                "WHERE claim_id=?", (req["cp_id"], p["name"], req["claim_id"]))
            else:
                if int(cl.get("channel_partner_id") or 0) != int(req["cp_id"]):
                    raise CPError("The claim's Channel Partner changed meanwhile - reject this one.")
                await c.execute("UPDATE nidaan_claims SET channel_partner_id=NULL, associate_referrer='' "
                                "WHERE claim_id=?", (req["claim_id"],))
        await c.execute(
            "UPDATE nidaan_claim_cp_requests SET status=?, decided_by=?, decided_name=?, "
            "decided_at=CURRENT_TIMESTAMP, decision_note=? WHERE req_id=? AND status='pending'",
            ("approved" if approve else "rejected", staff.get("staff_id"), who, note[:400], int(req_id)))
        await c.commit()
    finally:
        await c.close()
    verb = "added" if req["action"] == "add" else "removed"
    if approve:
        summary = "Channel Partner %s %s - approved by %s (asked by %s)%s" % (
            req["cp_name"], verb, who, req["requested_name"], (" - " + note) if note else "")
    else:
        summary = "Request to %s Channel Partner %s rejected by %s - %s" % (
            req["action"], req["cp_name"], who, note)
    await _timeline(req["claim_id"], summary, who)
    await _tell([req.get("requested_by")],
                ("✅ Channel Partner %s on NP-%s" % (verb, req["claim_id"])) if approve else
                ("❌ Channel Partner change rejected on NP-%s" % req["claim_id"]),
                summary, event_key="cp.claim_decided", claim_id=req["claim_id"])
    return {"ok": True, "status": "approved" if approve else "rejected"}


async def withdraw(req_id: int, *, staff: dict) -> dict:
    who = (staff.get("name") or "staff")[:80]
    c = await _conn()
    try:
        r = await (await c.execute("SELECT * FROM nidaan_claim_cp_requests WHERE req_id=?",
                                   (int(req_id),))).fetchone()
        if not r or r["status"] != "pending":
            raise CPError("There is no open request to withdraw.")
        req = dict(r)
        if req["requested_by"] != staff.get("staff_id") and (staff.get("role") or "") != SUPER:
            raise CPError("Only the person who asked, or a super-admin, can withdraw it.")
        await c.execute("UPDATE nidaan_claim_cp_requests SET status='withdrawn', decided_by=?, "
                        "decided_name=?, decided_at=CURRENT_TIMESTAMP WHERE req_id=?",
                        (staff.get("staff_id"), who, int(req_id)))
        await c.commit()
    finally:
        await c.close()
    await _timeline(req["claim_id"], "%s withdrew the request to %s Channel Partner %s" % (
        who, req["action"], req["cp_name"]), who)
    return {"ok": True}


async def claim_of(req_id: int) -> int:
    c = await _conn()
    try:
        r = await (await c.execute("SELECT claim_id FROM nidaan_claim_cp_requests WHERE req_id=?",
                                   (int(req_id),))).fetchone()
        return int(r["claim_id"]) if r else 0
    finally:
        await c.close()
