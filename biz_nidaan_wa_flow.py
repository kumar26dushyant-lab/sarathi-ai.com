"""
NidaanPartner claimant-WhatsApp FLOW logic — inbound handling + opt-in + message log.

Phase 0 (this file, foundation): parse Meta webhook payloads, dedup on wamid, log every
message, track the 24h session window, and handle opt-in keywords (STOP / START / language).
Documents that arrive are logged and ops is alerted; the intelligent doc pipeline (quality +
right-doc verification + PDF/naming + checklist update + guided next-step) lands in Phase 1 at
the marked handoff (`_on_inbound_media`). Never raises to the webhook.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import aiosqlite

import biz_database as db
import biz_nidaan_whatsapp as wa

logger = logging.getLogger("nidaan.wa.flow")
DB_PATH = db.DB_PATH

_STOP_WORDS = {"stop", "unsubscribe", "band karo", "band karein", "roko", "mat bhejo"}
_START_WORDS = {"start", "yes", "haan", "haँ", "ha", "ok", "okay", "start karo"}
_LANG_WORDS = {"english": "en", "eng": "en", "hindi": "hi", "हिंदी": "hi",
               "hinglish": "hinglish", "roman": "hinglish"}


async def log_message(*, direction: str, msisdn: str, claim_id: Optional[int] = None,
                      wa_message_id: str = "", msg_type: str = "", template_name: str = "",
                      body: str = "", media_id: str = "", status: str = "", error: str = "") -> bool:
    """Write one row to the WA message log. Idempotent on wa_message_id (inbound dedup)."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            if wa_message_id:
                ex = await (await conn.execute(
                    "SELECT 1 FROM nidaan_wa_messages WHERE wa_message_id=?", (wa_message_id,))).fetchone()
                if ex:
                    return False
            await conn.execute(
                """INSERT INTO nidaan_wa_messages
                   (direction, msisdn, claim_id, wa_message_id, msg_type, template_name,
                    body, media_id, status, error)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (direction, msisdn, claim_id, wa_message_id or "", msg_type or "", template_name or "",
                 (body or "")[:4000], media_id or "", status or "", (error or "")[:300]))
            await conn.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("log_message failed: %s", e)
        return False


async def get_contact(msisdn: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT * FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
    return dict(r) if r else None


async def upsert_contact(msisdn: str, *, claim_id: Optional[int] = None, account_id: Optional[int] = None,
                         opted_in: Optional[bool] = None, opt_source: str = "", language: Optional[str] = None,
                         status: Optional[str] = None, mark_inbound: bool = False,
                         mark_outbound: bool = False) -> None:
    """Create/update a claimant WA contact. Only non-None fields are changed."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("INSERT OR IGNORE INTO nidaan_wa_contacts (msisdn) VALUES (?)", (msisdn,))
        sets, args = [], []
        if claim_id is not None:      sets.append("claim_id=?");   args.append(claim_id)
        if account_id is not None:    sets.append("account_id=?"); args.append(account_id)
        if opted_in is not None:
            sets.append("opted_in=?"); args.append(1 if opted_in else 0)
            if opted_in:
                sets.append("opted_in_at=?"); args.append(now)
        if opt_source:                sets.append("opt_source=?"); args.append(opt_source)
        if language:                  sets.append("language=?");   args.append(language)
        if status:                    sets.append("status=?");     args.append(status)
        if mark_inbound:              sets.append("last_inbound_at=?");  args.append(now)
        if mark_outbound:             sets.append("last_outbound_at=?"); args.append(now)
        if sets:
            await conn.execute(f"UPDATE nidaan_wa_contacts SET {', '.join(sets)} WHERE msisdn=?",
                               tuple(args) + (msisdn,))
        await conn.commit()


async def in_session_window(msisdn: str) -> bool:
    """True if the claimant messaged us within the last 24h (free-form/text is allowed)."""
    c = await get_contact(msisdn)
    if not c or not c.get("last_inbound_at"):
        return False
    try:
        last = datetime.strptime(str(c["last_inbound_at"])[:19], "%Y-%m-%d %H:%M:%S")
        return (datetime.utcnow() - last).total_seconds() < 24 * 3600
    except Exception:
        return False


async def _claim_for_msisdn(msisdn: str) -> Optional[int]:
    c = await get_contact(msisdn)
    return c.get("claim_id") if c else None


async def _on_inbound_text(msisdn: str, text: str) -> None:
    """Handle a text reply. Phase 0: opt-in keywords + language switch. Phase 1 will route the
    rest into the Gemini conversational doc-collection layer."""
    t = (text or "").strip().lower()
    if t in _STOP_WORDS:
        await upsert_contact(msisdn, opted_in=False, status="stopped")
        try:
            await wa.send_text(msisdn, "Theek hai — aapko ab WhatsApp par updates nahi bhejenge. "
                                       "Dobara chalu karne ke liye START bhejein.")
        except Exception:
            pass
        return
    if t in _START_WORDS:
        await upsert_contact(msisdn, opted_in=True, status="active", opt_source="reply_yes")
        return
    if t in _LANG_WORDS:
        await upsert_contact(msisdn, language=_LANG_WORDS[t])
        try:
            import biz_nidaan_wa_orchestrator as _orch
            await _orch.start_or_continue(msisdn)   # re-ask in the new language
        except Exception:
            pass
        return
    # Record cold/unknown numbers as CRM leads (no-op for known customers). Non-blocking.
    await maybe_capture_lead(msisdn)
    # Guided doc-collection: match the number to its claim, greet + ask the next pending doc.
    res = {}
    try:
        import biz_nidaan_wa_orchestrator as _orch
        res = await _orch.handle_inbound_text(msisdn, text) or {}
    except Exception as e:  # noqa: BLE001
        logger.info("orchestrator text handoff failed: %s", e)
        return
    # NOBODY should be left on read. If the number isn't linked to a claim, answer anyway:
    # the first time with the full value message (what we do + what we need to know), and
    # after that with a short "we're on it" nudge. Free-form is fine — they just wrote to us,
    # so the 24h session is open and no template is required.
    if not res.get("ok") and res.get("error") == "no_claim":
        await _reply_unlinked(msisdn)
    return


async def _reply_unlinked(msisdn: str) -> None:
    """Reply to an inbound from a number we have no claim for, and alert ops on first contact."""
    try:
        import biz_nidaan_wa_messages as _msg
        c = await get_contact(msisdn) or {}
        lang = (c.get("language") or "hinglish")
        first_touch = not (c.get("last_outbound_at") or "")
        body = _msg.compose("intro_value" if first_touch else "human_followup", lang, {"name": ""})
        if body:
            await wa.send_text(msisdn, body)
            await upsert_contact(msisdn, mark_outbound=True)
        if first_touch:
            try:
                import biz_nidaan_notifications as _nnot
                await _nnot.notify_staff_inapp(
                    await _admin_ids(), "💬 New WhatsApp enquiry",
                    f"A new number {msisdn} messaged NidaanPartner on WhatsApp. It has been recorded "
                    f"as a CRM lead and auto-answered — pick it up in CRM.",
                    event_key="wa.new_enquiry", email=False)
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        logger.info("unlinked WhatsApp reply failed for %s: %s", msisdn, e)


async def _on_inbound_media(msisdn: str, media_id: str, mime: str, wamid: str) -> None:
    """A claimant sent a FILE (a document). PHASE 1 HANDOFF — the intelligent pipeline goes here:
      1. download_media → 2. right-doc + quality check (Gemini vision, against the doc we asked for)
      3. normalize_to_pdf + segment → 4. name per convention → 5. mark_doc_received / nudge if wrong
      6. sync the checklist (single source of truth) → 7. guided next-step reply.
    Routed to the orchestrator's guided pipeline: right-doc + quality gate → convert → save →
    mark checklist → ask next. Falls back to an ops alert only if no claim matches the number."""
    try:
        import biz_nidaan_wa_orchestrator as _orch
        res = await _orch.handle_inbound_document(msisdn, media_id, mime)
        if res.get("ok") or res.get("error") not in ("no_claim", None):
            return   # handled (accepted, nudged, or human-takeover)
    except Exception as e:  # noqa: BLE001
        logger.info("orchestrator media handoff failed: %s", e)
    # No matching claim (or orchestrator error) — don't lose it: alert ops.
    claim_id = await _claim_for_msisdn(msisdn)
    try:
        import biz_nidaan_notifications as _nnot
        await _nnot.notify_staff_inapp(
            await _admin_ids(), "📎 Claimant sent a document on WhatsApp",
            f"A document arrived from {msisdn}" + (f" (claim #{claim_id})" if claim_id else "")
            + " but it could not be auto-matched to a claim — review in ops.",
            event_key="wa.doc_received", email=False, claim_id=claim_id)
    except Exception:
        pass


async def maybe_capture_lead(msisdn: str, name: str = "") -> None:
    """Record an inbound WhatsApp number as a CRM lead when it's NOT already a known customer
    (no linked claim, no linked account) and not already a lead. Gated by ops setting
    `wa_lead_capture_enabled` (default on). Best-effort, never raises."""
    try:
        import biz_nidaan as _n
        if str(await _n.get_ops_setting("wa_lead_capture_enabled", "1")) not in ("1", "true", "True"):
            return
        c = await get_contact(msisdn)
        if c and (c.get("claim_id") or c.get("account_id")):
            return   # already a customer — not a cold lead
        import biz_nidaan_crm as _crm
        existing = await _crm.list_leads(search=msisdn, limit=1)
        if existing:
            return   # already captured
        await _crm.create_lead(
            name=(name or "").strip() or f"WhatsApp {msisdn[-4:]}", phone=msisdn,
            source="whatsapp", interest="Inbound WhatsApp enquiry",
            notes="Auto-captured from an inbound WhatsApp message.", created_by_name="WhatsApp bot")
        logger.info("wa lead captured: %s", msisdn)
    except Exception as e:  # noqa: BLE001
        logger.debug("wa lead capture skipped for %s: %s", msisdn, e)


async def _admin_ids() -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        rows = await (await conn.execute(
            "SELECT staff_id FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') "
            "AND status='active' AND deleted_at IS NULL")).fetchall()
    return [r[0] for r in rows]


async def handle_inbound_payload(payload: dict) -> dict:
    """Parse a Meta webhook POST body. Handles message + status events. Idempotent, never raises."""
    handled = 0
    try:
        for entry in (payload.get("entry") or []):
            for ch in (entry.get("changes") or []):
                val = ch.get("value") or {}
                # Inbound messages
                for m in (val.get("messages") or []):
                    msisdn = wa.normalize_msisdn(m.get("from", ""))
                    wamid = m.get("id", "")
                    mtype = m.get("type", "")
                    if not await log_message(direction="in", msisdn=msisdn, wa_message_id=wamid,
                                             msg_type=mtype, status="received",
                                             body=(m.get("text", {}) or {}).get("body", "")):
                        continue  # duplicate wamid — already processed
                    await upsert_contact(msisdn, mark_inbound=True)
                    handled += 1
                    if mtype == "text":
                        await _on_inbound_text(msisdn, (m.get("text") or {}).get("body", ""))
                    elif mtype in ("image", "document", "audio", "video"):
                        media = m.get(mtype) or {}
                        await _on_inbound_media(msisdn, media.get("id", ""), media.get("mime_type", ""), wamid)
                    elif mtype == "button":
                        await _on_inbound_text(msisdn, (m.get("button") or {}).get("text", ""))
                    elif mtype == "interactive":
                        _i = m.get("interactive") or {}
                        _br = (_i.get("button_reply") or _i.get("list_reply") or {})
                        await _on_inbound_text(msisdn, _br.get("title", "") or _br.get("id", ""))
                # Delivery/read statuses for our outbound
                for s in (val.get("statuses") or []):
                    try:
                        async with aiosqlite.connect(DB_PATH) as conn:
                            await conn.execute(
                                "UPDATE nidaan_wa_messages SET status=? WHERE wa_message_id=?",
                                (s.get("status", ""), s.get("id", "")))
                            await conn.commit()
                    except Exception:
                        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("handle_inbound_payload failed: %s", e)
    return {"handled": handled}
