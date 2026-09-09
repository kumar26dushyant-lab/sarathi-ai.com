"""
NidaanPartner — WHATSAPP INBOX.

The WhatsApp panel used to show one flat table of the last 25 messages across every number, so a
staffer could not tell who was talking to whom, whether the AI or a colleague had replied, or
whether anyone was handling a customer at all. This module turns that log into CONVERSATIONS.

Three things it makes explicit, because ops has to see them at a glance:

  • WHO IS SPEAKING — every outbound row now carries a sender (bot / human / campaign / journey).
    A staffer opening a chat can see immediately that the AI answered, and what it said.
  • WHO OWNS THE CHAT — takeover is per CONVERSATION (msisdn), not per claim. A prospect or a
    branch has no claim to hang takeover off, and used to keep getting AI replies after being
    handed to a human. Taking over mutes the bot on the number itself.
  • WHETHER WE CAN STILL REPLY — WhatsApp only allows free-form messages for 24 hours after the
    customer's last message. Outside that window a reply silently fails, so the window (and the
    time left in it) is surfaced before anyone types.

Read paths are defensive: a broken row must never take the inbox down. Write paths are narrow and
audited — sending as the business is a real-world action, so every human send is attributed to the
real staff member, even under impersonation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.wa.inbox")
DB_PATH = db.DB_PATH

# WhatsApp's customer-service window: free-form text is only deliverable for 24h after the
# customer's last inbound message. Anything older needs an approved template.
SESSION_HOURS = 24
_PREVIEW = 120        # characters of the last message shown in the conversation list


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(str(ts)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _window(last_inbound_at) -> dict:
    """{open, minutes_left, expires_at} for the 24h free-form window."""
    t = _parse(last_inbound_at)
    if not t:
        return {"open": False, "minutes_left": 0, "expires_at": ""}
    exp = t + timedelta(hours=SESSION_HOURS)
    left = int((exp - datetime.utcnow()).total_seconds() // 60)
    return {"open": left > 0, "minutes_left": max(0, left),
            "expires_at": exp.strftime("%Y-%m-%d %H:%M:%S")}


def _verified_now(role, until) -> dict:
    """Is this conversation inside a live verified session? Shown so a staffer knows whether the
    person on the other end actually proved who they are before anything private was discussed."""
    if not role or not until:
        return {"ok": False, "role": ""}
    try:
        if datetime.strptime(str(until)[:19], "%Y-%m-%d %H:%M:%S") <= datetime.utcnow():
            return {"ok": False, "role": ""}
    except Exception:
        return {"ok": False, "role": ""}
    return {"ok": True, "role": role, "until": str(until)}


async def conversations(*, limit: int = 60, scope: str = "all") -> list[dict]:
    """One row per number, newest activity first.

    scope: all | unread | human (a person owns it) | bot (the AI is handling it) | stopped
    """
    limit = max(1, min(int(limit or 60), 200))
    sql = """
        SELECT c.msisdn, c.display_name, c.claim_id, c.account_id, c.language, c.status,
               c.opted_in, c.bot_paused, c.paused_by, c.assigned_to, c.assigned_name,
               c.verified_role, c.verified_name, c.verified_until,
               c.last_inbound_at, c.last_outbound_at, c.last_read_at,
               (SELECT body      FROM nidaan_wa_messages m WHERE m.msisdn=c.msisdn
                 ORDER BY m.wam_row_id DESC LIMIT 1) last_body,
               (SELECT direction FROM nidaan_wa_messages m WHERE m.msisdn=c.msisdn
                 ORDER BY m.wam_row_id DESC LIMIT 1) last_dir,
               (SELECT sender    FROM nidaan_wa_messages m WHERE m.msisdn=c.msisdn
                 ORDER BY m.wam_row_id DESC LIMIT 1) last_sender,
               (SELECT msg_type  FROM nidaan_wa_messages m WHERE m.msisdn=c.msisdn
                 ORDER BY m.wam_row_id DESC LIMIT 1) last_type,
               (SELECT created_at FROM nidaan_wa_messages m WHERE m.msisdn=c.msisdn
                 ORDER BY m.wam_row_id DESC LIMIT 1) last_at,
               (SELECT COUNT(*)  FROM nidaan_wa_messages m WHERE m.msisdn=c.msisdn
                 AND m.direction='in'
                 AND (c.last_read_at IS NULL OR m.created_at > c.last_read_at)) unread
        FROM nidaan_wa_contacts c
        ORDER BY COALESCE(
            (SELECT created_at FROM nidaan_wa_messages m WHERE m.msisdn=c.msisdn
              ORDER BY m.wam_row_id DESC LIMIT 1), c.created_at) DESC
        LIMIT ?"""
    out: list[dict] = []
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            rows = await (await c.execute(sql, (limit,))).fetchall()
    except Exception as e:  # noqa: BLE001
        logger.warning("conversations query failed: %s", e)
        return []
    for r in rows:
        d = dict(r)
        body = (d.get("last_body") or "").strip()
        if not body and d.get("last_type") in ("image", "document", "audio", "video"):
            body = {"image": "📷 Photo", "document": "📄 File",
                    "audio": "🎤 Voice note", "video": "🎬 Video"}.get(d["last_type"], "Attachment")
        d["preview"] = body[:_PREVIEW]
        d["window"] = _window(d.get("last_inbound_at"))
        d["owner"] = "human" if d.get("bot_paused") else "bot"
        d["verified"] = _verified_now(d.get("verified_role"), d.get("verified_until"))
        d.pop("last_body", None)
        out.append(d)
    if scope == "unread":
        out = [x for x in out if (x.get("unread") or 0) > 0]
    elif scope == "human":
        out = [x for x in out if x.get("bot_paused")]
    elif scope == "bot":
        out = [x for x in out if not x.get("bot_paused") and x.get("status") != "stopped"]
    elif scope == "stopped":
        out = [x for x in out if x.get("status") == "stopped"]
    elif scope == "verified":
        out = [x for x in out if (x.get("verified") or {}).get("ok")]
    return out


async def thread(msisdn: str, *, limit: int = 200) -> dict:
    """Full conversation with one number: contact state + messages oldest-first."""
    msisdn = (msisdn or "").strip()
    limit = max(1, min(int(limit or 200), 500))
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        contact = await (await c.execute(
            "SELECT * FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
        rows = await (await c.execute(
            "SELECT wam_row_id, direction, msg_type, template_name, body, media_id, status, "
            "error, sender, sender_name, claim_id, created_at "
            "FROM nidaan_wa_messages WHERE msisdn=? ORDER BY wam_row_id DESC LIMIT ?",
            (msisdn, limit))).fetchall()
    ct = dict(contact) if contact else {"msisdn": msisdn}
    ct["window"] = _window(ct.get("last_inbound_at"))
    ct["owner"] = "human" if ct.get("bot_paused") else "bot"
    ct["verified"] = _verified_now(ct.get("verified_role"), ct.get("verified_until"))
    msgs = [dict(r) for r in rows][::-1]     # oldest first — reads like a chat
    # Who is this number, in business terms? Best-effort; never blocks the thread.
    who = {}
    try:
        import biz_nidaan_wa_identity as _ident
        who = await _ident.resolve(msisdn) or {}
    except Exception:
        who = {}
    return {"contact": ct, "messages": msgs,
            "identity": {"name": who.get("name") or ct.get("display_name") or "",
                         "role": who.get("role") or "",
                         "account_id": who.get("account_id"),
                         "branch_code": who.get("branch_code") or ""},
            # The brief a staffer needs to answer well without opening three other screens.
            "context": await case_context(msisdn, ct.get("claim_id"))}


async def mark_read(msisdn: str) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute("UPDATE nidaan_wa_contacts SET last_read_at=CURRENT_TIMESTAMP "
                            "WHERE msisdn=?", ((msisdn or "").strip(),))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("mark_read failed: %s", e)


async def set_owner(msisdn: str, *, human: bool, by_id: str = "", by_name: str = "") -> dict:
    """Take the conversation over from the bot, or hand it back.

    Taking over also assigns it, so the list always answers "who has this?". Handing back clears
    the assignment — an unowned chat with the bot running is the normal resting state.
    """
    msisdn = (msisdn or "").strip()
    if not msisdn:
        return {"ok": False, "error": "no_number"}
    try:
        import biz_nidaan_wa_orchestrator as _orch
        await _orch.pause_bot(msisdn, by=(by_name or by_id or "staff"), paused=human)
    except Exception as e:  # noqa: BLE001
        logger.warning("set_owner pause failed: %s", e)
        return {"ok": False, "error": "could_not_set"}
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            if human:
                await c.execute("UPDATE nidaan_wa_contacts SET assigned_to=?, assigned_name=? "
                                "WHERE msisdn=?", (str(by_id)[:20], (by_name or "")[:80], msisdn))
            else:
                await c.execute("UPDATE nidaan_wa_contacts SET assigned_to='', assigned_name='' "
                                "WHERE msisdn=?", (msisdn,))
            await c.commit()
    except Exception:
        pass
    # If this number is collecting documents for a claim, keep the claim-level flag in step so the
    # reminder sweep and the inbox never disagree about who is driving the conversation.
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT claim_id FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
        cid = (dict(r).get("claim_id") if r else None)
        if cid:
            async with aiosqlite.connect(DB_PATH) as c:
                await c.execute("INSERT OR IGNORE INTO nidaan_wa_claim_settings (claim_id) VALUES (?)", (cid,))
                await c.execute("UPDATE nidaan_wa_claim_settings SET human_takeover=?, takeover_by=?, "
                                "updated_at=CURRENT_TIMESTAMP WHERE claim_id=?",
                                (1 if human else 0, (by_name or "")[:40], cid))
                await c.commit()
    except Exception:
        pass
    return {"ok": True, "owner": "human" if human else "bot"}


async def send_human(msisdn: str, text: str, *, staff_id: str = "", staff_name: str = "") -> dict:
    """Send a staffer's own reply on WhatsApp, attributed to them.

    Refuses outside the 24h window rather than firing a send that WhatsApp will drop — a reply the
    customer never receives, shown in ops as sent, is worse than a clear refusal.
    """
    msisdn = (msisdn or "").strip()
    text = (text or "").strip()
    if not msisdn or not text:
        return {"ok": False, "error": "Nothing to send."}
    if len(text) > 4000:
        text = text[:4000]

    import biz_nidaan_wa_flow as _flow
    import biz_nidaan_whatsapp as _wa

    # Consent and the reply window are checked FIRST. Whether WhatsApp happens to be connected
    # must never be what decides if we honour someone's STOP.
    ct = await _flow.get_contact(msisdn) or {}
    if (ct.get("status") or "") == "stopped":
        return {"ok": False, "error": "This person sent STOP — we must not message them."}
    win = _window(ct.get("last_inbound_at"))
    if not win["open"]:
        return {"ok": False, "error": "The 24-hour reply window has closed. "
                                      "WhatsApp only allows an approved template now — "
                                      "use a campaign template to reach them.",
                "window": win}
    if not _wa.is_configured():
        return {"ok": False, "error": "WhatsApp is not connected yet."}

    # The send layer logs the message itself; this just tells it who is speaking.
    with _wa.sending_as("human", staff_name, staff_id):
        res = await _wa.send_text(msisdn, text)
    ok = bool(res.get("ok", True)) and not res.get("error")
    if not ok:
        return {"ok": False, "error": str(res.get("error") or "WhatsApp rejected the message.")}
    try:
        await _flow.upsert_contact(msisdn, mark_outbound=True)
    except Exception:
        pass
    # A person replying by hand IS the takeover — otherwise the bot answers the next inbound and
    # the customer hears two voices.
    if not ct.get("bot_paused"):
        await set_owner(msisdn, human=True, by_id=staff_id, by_name=staff_name)
    await mark_read(msisdn)
    return {"ok": True, "owner": "human"}


async def counters() -> dict:
    """Small header numbers for the inbox: what needs a person right now."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute("""
                SELECT COUNT(*) total,
                       COALESCE(SUM(bot_paused=1),0) with_human,
                       COALESCE(SUM(status='stopped'),0) stopped,
                       COALESCE(SUM(EXISTS(SELECT 1 FROM nidaan_wa_messages m
                            WHERE m.msisdn=c.msisdn AND m.direction='in'
                              AND (c.last_read_at IS NULL OR m.created_at > c.last_read_at))),0) unread
                FROM nidaan_wa_contacts c""")).fetchone()
        return dict(r) if r else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("counters failed: %s", e)
        return {}


# ── what the staffer needs on screen to actually help ────────────────────────
# Answering a WhatsApp message well means knowing, in the same glance: which case this is, how
# far it has got, what we are waiting for, which documents are still missing, and whether any
# money is outstanding. Without that the staffer opens three other screens, or worse, answers
# from memory. Everything here is read-only and best-effort — a missing piece degrades to
# "not known" rather than taking the thread down.

async def case_context(msisdn: str, claim_id=None) -> dict:
    """A one-glance brief on the person behind this conversation."""
    out: dict = {"claims": [], "account": None}
    d10 = "".join(ch for ch in (msisdn or "") if ch.isdigit())[-10:]
    if not d10:
        return out
    like = f"%{d10}"
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            rows = [dict(r) for r in await (await c.execute(
                "SELECT claim_id, account_id, claim_type, insured_name, complainant_name, "
                "insurer_name, policy_no, disputed_amount, status, review_outcome, "
                "l2_payment_status, branch_code, assigned_to_staff_id, created_at "
                "FROM nidaan_claims WHERE COALESCE(archived,0)=0 AND ("
                "  REPLACE(REPLACE(COALESCE(complainant_phone,''),' ',''),'-','') LIKE ? OR "
                "  REPLACE(REPLACE(COALESCE(insured_phone,''),' ',''),'-','') LIKE ?) "
                "ORDER BY claim_id DESC LIMIT 5", (like, like))).fetchall()]

            # If the conversation is pinned to a claim the number does not carry, include it too.
            if claim_id and not any(r["claim_id"] == claim_id for r in rows):
                extra = await (await c.execute(
                    "SELECT claim_id, account_id, claim_type, insured_name, complainant_name, "
                    "insurer_name, policy_no, disputed_amount, status, review_outcome, "
                    "l2_payment_status, branch_code, assigned_to_staff_id, created_at "
                    "FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
                if extra:
                    rows.insert(0, dict(extra))

            staff_names: dict = {}
            sids = [r["assigned_to_staff_id"] for r in rows if r.get("assigned_to_staff_id")]
            if sids:
                ph = ",".join("?" * len(sids))
                for sr in await (await c.execute(
                        f"SELECT staff_id, name FROM nidaan_staff WHERE staff_id IN ({ph})",
                        sids)).fetchall():
                    staff_names[dict(sr)["staff_id"]] = dict(sr)["name"]

            for r in rows:
                cid = r["claim_id"]
                # Documents: the single most common reason a claimant is messaging us.
                try:
                    dr = await (await c.execute(
                        "SELECT COUNT(*) total, COALESCE(SUM(received),0) done "
                        "FROM nidaan_claim_doc_checklist WHERE claim_id=? AND required=1",
                        (cid,))).fetchone()
                    dd = dict(dr) if dr else {}
                    done, total = int(dd.get("done") or 0), int(dd.get("total") or 0)
                except Exception:
                    done, total = 0, 0
                missing = []
                if total and done < total:
                    try:
                        mr = await (await c.execute(
                            "SELECT doc_key FROM nidaan_claim_doc_checklist "
                            "WHERE claim_id=? AND required=1 AND COALESCE(received,0)=0 LIMIT 4",
                            (cid,))).fetchall()
                        missing = [dict(x)["doc_key"] for x in mr]
                    except Exception:
                        missing = []
                out["claims"].append({
                    "claim_id": cid,
                    "claim_type": r.get("claim_type") or "",
                    "insured_name": r.get("insured_name") or "",
                    "complainant_name": r.get("complainant_name") or "",
                    "insurer": r.get("insurer_name") or "",
                    "policy_no": r.get("policy_no") or "",
                    "amount": r.get("disputed_amount") or 0,
                    "status": r.get("status") or "",
                    "review_outcome": r.get("review_outcome") or "",
                    "l2_paid": (r.get("l2_payment_status") or "") == "paid",
                    "branch_code": r.get("branch_code") or "",
                    "handler": staff_names.get(r.get("assigned_to_staff_id")) or "",
                    "docs": {"done": done, "total": total, "missing": missing},
                    "created_at": r.get("created_at"),
                })

            # Their account and plan, if this number belongs to one.
            ar = await (await c.execute(
                "SELECT account_id, owner_name, email, phone FROM nidaan_accounts "
                "WHERE deleted_at IS NULL AND "
                "REPLACE(REPLACE(COALESCE(phone,''),' ',''),'-','') LIKE ? LIMIT 1",
                (like,))).fetchone()
            if ar:
                a = dict(ar)
                sub = await (await c.execute(
                    "SELECT plan, status, substr(current_period_end,1,10) ends "
                    "FROM nidaan_subscriptions WHERE account_id=? AND status='active' "
                    "ORDER BY sub_id DESC LIMIT 1", (a["account_id"],))).fetchone()
                out["account"] = {
                    "account_id": a["account_id"], "name": a.get("owner_name") or "",
                    "email": a.get("email") or "",
                    "plan": (dict(sub).get("plan") if sub else ""),
                    "plan_ends": (dict(sub).get("ends") if sub else ""),
                }
    except Exception as e:  # noqa: BLE001
        logger.warning("case_context failed for %s: %s", msisdn, e)
    return out
