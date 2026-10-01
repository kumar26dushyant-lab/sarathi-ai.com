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
                      body: str = "", media_id: str = "", status: str = "", error: str = "",
                      sender: str = "", sender_name: str = "", staff_id: str = "",
                      send_class: str = "") -> bool:
    """Write one row to the WA message log. Idempotent on wa_message_id (inbound dedup).

    `sender` records WHO produced an outbound message — bot | human | campaign | journey |
    system — so the inbox can show a staffer plainly whether the AI or a colleague replied.
    Inbound is always the customer. Unset outbound defaults to 'bot': every existing caller is
    an automation, so the label stays honest without touching those call sites.
    """
    if not sender:
        sender = "customer" if direction == "in" else "bot"
    if direction == "out" and sender == "human":
        # A person from our team answered: the bot's "someone will reach out" count starts again.
        try:
            import biz_nidaan_bot_hold as _hold
            await _hold.reset("wa:" + (msisdn or ""))
        except Exception:  # noqa: BLE001
            pass
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
                    body, media_id, status, error, sender, sender_name, staff_id, send_class)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (direction, msisdn, claim_id, wa_message_id or "", msg_type or "", template_name or "",
                 (body or "")[:4000], media_id or "", status or "", (error or "")[:300],
                 sender[:20], (sender_name or "")[:80], str(staff_id or "")[:20],
                 (send_class or "")[:16]))
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
    """Create/update a complainant WA contact. Only non-None fields are changed."""
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


async def _mark_stop(msisdn: str, *, stopped: bool, source: str) -> None:
    """Record WHEN someone stopped (or started again) and how, so a screen can say it in words
    instead of showing a bare status. Best-effort: never let this break the reply itself."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE nidaan_wa_contacts SET stopped_at=?, stop_source=? WHERE msisdn=?",
                (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if stopped else None,
                 source if stopped else "", msisdn))
            await conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.info("could not stamp the STOP on %s: %s", msisdn, e)


async def in_session_window(msisdn: str) -> bool:
    """True if the complainant messaged us within the last 24h (free-form/text is allowed)."""
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
        await _mark_stop(msisdn, stopped=True, source="reply_stop")
        try:
            # Sent as 'consent' so the guard lets it reach someone who has just opted out: the
            # one message a stopped person must still get is the one confirming they stopped.
            # It also says what they will NOT lose — their claim carries on either way.
            with wa.sending_as("consent"):
                await wa.send_text(msisdn, "Theek hai — aapko ab WhatsApp par claim updates nahi "
                                           "bhejenge. Aapka claim chalu rahega aur hum aapse call "
                                           "ya email par sampark karenge. Dobara WhatsApp par "
                                           "updates chahiye to kabhi bhi START bhejein.")
        except Exception:
            pass
        return
    if t in _START_WORDS:
        await upsert_contact(msisdn, opted_in=True, status="active", opt_source="reply_yes")
        await _mark_stop(msisdn, stopped=False, source="reply_start")
        try:
            with wa.sending_as("consent"):
                await wa.send_text(msisdn, "Ho gaya — aapko WhatsApp par claim updates dobara "
                                           "milenge. Band karne ke liye kabhi bhi STOP bhejein.")
        except Exception:
            pass
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


async def _on_inbound_media(msisdn: str, media_id: str, mime: str, wamid: str,
                            filename: str = "", caption: str = "") -> None:
    """A complainant sent a FILE (a document). PHASE 1 HANDOFF — the intelligent pipeline goes here:
      1. download_media → 2. right-doc + quality check (Gemini vision, against the doc we asked for)
      3. normalize_to_pdf + segment → 4. name per convention → 5. mark_doc_received / nudge if wrong
      6. sync the checklist (single source of truth) → 7. guided next-step reply.
    Routed to the orchestrator's guided pipeline: right-doc + quality gate → convert → save →
    mark checklist → ask next. A file that matches no claim is KEPT in "Files to sort"
    (biz_nidaan_wa_unsorted) - it used to be dropped with only a bell to say it had come."""
    import biz_nidaan_wa_unsorted as _sort
    # A STAFF member forwarding a customer's papers, with the claim number in the caption
    # (founder, 1 Oct: forwarding allowed from any staff number). Filed on that claim if they may
    # work on it; otherwise kept to sort. Without a claim number it goes the normal way below.
    staff = await _sort.staff_for(msisdn)
    if staff and _sort.claim_number(caption):
        try:
            res = await _sort.staff_forward(staff, msisdn, media_id, mime, filename=filename,
                                            caption=caption, wamid=wamid)
            await wa.send_text(msisdn, _sort.staff_reply(res))
        except Exception as e:  # noqa: BLE001
            logger.warning("staff forward failed: %s", e)
        return
    try:
        import biz_nidaan_wa_orchestrator as _orch
        res = await _orch.handle_inbound_document(msisdn, media_id, mime, filename=filename)
        if res.get("ok") or res.get("error") not in ("no_claim", None):
            return   # handled (accepted, nudged, or human-takeover)
    except Exception as e:  # noqa: BLE001
        logger.info("orchestrator media handoff failed: %s", e)
    # No claim matched: KEEP it, tell the sender once, tell the person on WhatsApp duty once.
    try:
        import biz_nidaan_wa_identity as _ident
        who = await _ident.resolve(msisdn)
    except Exception:  # noqa: BLE001
        who = {}
    kept = await _sort.keep(msisdn, media_id, mime, filename=filename, caption=caption, wamid=wamid,
                            sender_role=("staff" if staff else (who.get("role") or "unknown")),
                            sender_name=((staff or {}).get("name") or who.get("name") or ""))
    try:
        import biz_nidaan_wa_orchestrator as _orch
        if await _orch._reserve_reply(msisdn, 30):
            await wa.send_text(msisdn, _sort.sender_ack(staff=bool(staff), lang=await _orch._lang(msisdn)))
    except Exception as e:  # noqa: BLE001
        logger.info("file ack failed: %s", e)
    try:
        if await _sort.notice_due(msisdn):
            import biz_nidaan_notifications as _nnot
            await _nnot.notify_staff_inapp(
                await _admin_ids(), "\U0001f4ce A file arrived on WhatsApp - it needs a claim",
                "From %s (%s). It is kept in WhatsApp → Files to sort: open it and attach it to "
                "the right claim.%s" % (
                    msisdn, kept.get("status") == "not_stored" and "NOT stored: " + kept.get("reason", "")
                    or ((staff or {}).get("name") or who.get("name") or who.get("role") or "unknown number"),
                    ""),
                event_key="wa.doc_received", email=False)
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
    """Who should hear about a WhatsApp event.

    Every admin, PLUS whoever is on WhatsApp duty today. The rostered person is the one who will
    actually answer it — leaving them out meant the alert went to people who were not working the
    inbox, while the person who was got nothing.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        rows = await (await conn.execute(
            "SELECT staff_id FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') "
            "AND status='active' AND deleted_at IS NULL")).fetchall()
    ids = [r[0] for r in rows]
    try:
        import biz_nidaan as _n
        for sid in await _n.on_duty_rep_ids("whatsapp"):
            if sid not in ids:
                ids.append(sid)
    except Exception as e:  # noqa: BLE001
        logger.warning("on-duty WhatsApp lookup failed: %s", e)
    return ids


# Meta's failure codes that staff actually meet, in words they can act on. Anything else keeps
# Meta's own title, so a new code is never dropped - only not yet translated.
_FAIL_WORDS = {
    131047: "more than 24 hours since they last wrote - only an approved template can reach them",
    131026: "this number cannot receive WhatsApp messages (not on WhatsApp, or a very old app)",
    131049: "WhatsApp held it back - they have had many business messages recently",
    131050: "they have turned off marketing messages from businesses",
    131056: "too many messages to this person in a short time",
    130429: "we sent too fast and WhatsApp slowed us down",
    131042: "a payment problem on our WhatsApp account",
    131031: "our WhatsApp account is locked",
    132000: "the template's fill-in values did not match it",
    132001: "that template does not exist in this language",
    132015: "that template is paused by WhatsApp",
    132016: "that template is disabled by WhatsApp",
}


def failure_reason(status: dict) -> str:
    """'131047 - more than 24 hours since ...' from a failed receipt. '' if it carries none.

    The receipt is webhook input: the code must be a number, the text is cut short, and nothing
    in it is trusted beyond being stored and shown to staff.
    """
    errs = (status or {}).get("errors")
    e = errs[0] if isinstance(errs, list) and errs and isinstance(errs[0], dict) else {}
    try:
        code = int(e.get("code"))
    except (TypeError, ValueError):
        code = 0
    title = " ".join(str(e.get("title") or e.get("message") or "").split())[:100]
    words = _FAIL_WORDS.get(code) or title
    if not code and not words:
        return ""
    return ("%s - %s" % (code, words) if code else words)[:160]


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
                    # A file's media id is kept on its row: an unmatched file used to be dropped
                    # with no way back to it. With the id, staff can still fetch it from Meta
                    # (media stays there about 30 days) while it is sorted to the right claim.
                    _media = (m.get(mtype) or {}) if mtype in ("image", "document", "audio", "video") else {}
                    _mbody = (m.get("text", {}) or {}).get("body", "") or " ".join(
                        x for x in ((_media.get("filename") or ""), (_media.get("caption") or "")) if x)
                    if not await log_message(direction="in", msisdn=msisdn, wa_message_id=wamid,
                                             msg_type=mtype, status="received",
                                             media_id=str(_media.get("id") or "")[:120],
                                             body=_mbody[:1000]):
                        continue  # duplicate wamid — already processed
                    await upsert_contact(msisdn, mark_inbound=True)
                    handled += 1
                    # Two blue ticks, immediately. Before the reply is composed, because a
                    # complainant chasing a rejected claim reads "delivered, not read" as
                    # "nobody is there". Never allowed to delay or block the reply itself.
                    try:
                        await wa.mark_read(wamid)
                    except Exception:  # noqa: BLE001
                        pass
                    # THE PHONE ANSWERING, NOT A PERSON (claim #245, 30 Sep): an away message or a
                    # business greeting is kept on the claim, plainly labelled - and it is not a
                    # reply to a query, not proof of the mobile, and not answered by the bot.
                    if mtype == "text":
                        try:
                            import biz_nidaan_wa_autoreply as _auto
                            _body = (m.get("text") or {}).get("body", "")
                            if await _auto.looks_automatic(msisdn, _body):
                                await _auto.note(msisdn, _body)
                                continue
                        except Exception as _ae:  # noqa: BLE001 - unsure: treat as a person
                            logger.info("auto-reply hook failed: %s", _ae)
                    # A reply to a query we sent this complainant: tell the super admins and the
                    # person who asked, with what they said. Never allowed to break the inbox.
                    try:
                        import biz_nidaan_buckets as _bkq
                        _t = (m.get("text") or {}).get("body", "") if mtype == "text" else (
                            (m.get("button") or {}).get("text", "") if mtype == "button" else "")
                        await _bkq.on_query_reply(msisdn, mtype, _t)
                    except Exception as _qe:  # noqa: BLE001
                        logger.info("query reply hook failed: %s", _qe)
                    # A message from a claim's mobile PROVES that mobile; a confirmation code
                    # replied here confirms it and is answered, not passed to the bot.
                    try:
                        import biz_nidaan_contact_verify as _cv
                        await _cv.note_inbound(msisdn)
                        if mtype == "text":
                            _cid = await _cv.confirm_whatsapp_reply(
                                msisdn, (m.get("text") or {}).get("body", ""))
                            if _cid:
                                await wa.send_text(msisdn, (
                                    "\u2705 Aapka mobile number claim NP-%s ke liye confirm ho gaya. "
                                    "Dhanyavaad!\n\u2705 आपका मोबाइल नंबर क्लेम NP-%s के लिए कन्फ़र्म "
                                    "हो गया। धन्यवाद!" % (_cid, _cid)))
                                continue
                    except Exception as _ce:  # noqa: BLE001 - never allowed to break the inbox
                        logger.info("contact proof hook failed: %s", _ce)
                    if mtype == "text":
                        await _on_inbound_text(msisdn, (m.get("text") or {}).get("body", ""))
                    elif mtype in ("image", "document", "audio", "video"):
                        media = m.get(mtype) or {}
                        await _on_inbound_media(msisdn, media.get("id", ""), media.get("mime_type", ""), wamid,
                                                filename=media.get("filename", ""),
                                                caption=media.get("caption", ""))
                    elif mtype == "button":
                        await _on_inbound_text(msisdn, (m.get("button") or {}).get("text", ""))
                    elif mtype == "interactive":
                        _i = m.get("interactive") or {}
                        _br = (_i.get("button_reply") or _i.get("list_reply") or {})
                        await _on_inbound_text(msisdn, _br.get("title", "") or _br.get("id", ""))
                # Delivery/read statuses for our outbound. A FAILED one keeps its reason.
                for s in (val.get("statuses") or []):
                    try:
                        st = str(s.get("status", ""))[:20]
                        why = failure_reason(s) if st == "failed" else ""
                        async with aiosqlite.connect(DB_PATH) as conn:
                            if why:
                                await conn.execute(
                                    "UPDATE nidaan_wa_messages SET status=?, error=? "
                                    "WHERE wa_message_id=?", (st, why, str(s.get("id", ""))))
                            else:
                                await conn.execute(
                                    "UPDATE nidaan_wa_messages SET status=? WHERE wa_message_id=?",
                                    (st, str(s.get("id", ""))))
                            await conn.commit()
                    except Exception:
                        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("handle_inbound_payload failed: %s", e)
    return {"handled": handled}
