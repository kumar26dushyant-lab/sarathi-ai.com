"""
NidaanPartner claimant-WhatsApp ORCHESTRATOR — the guided document-collection brain.

Ties together: the doc checklist (single source of truth), the message composer, Gemini vision
(right-doc + quality gate), the PDF pipeline (normalize_to_pdf), and the WhatsApp send/receive.

Flow (guided, one document at a time):
  claimant messages us (opens 24h session) → we match them to their claim by phone → greet +
  ask for the NEXT pending document → they send a photo/PDF → we verify it's the RIGHT doc and
  legible (Gemini) → if wrong/blurry, a specific nudge; if good, convert→PDF, save to the claim,
  mark the checklist, and ask for the next one → when all in, a "complete" message. Every step is
  recorded on the claim activity timeline.

In-session (claimant replied within 24h) uses free-form text — testable NOW. Business-INITIATED
messages (cold outreach, daily reminders when the session is closed) need approved templates;
that path is marked and no-ops cleanly until the templates exist.
"""
from __future__ import annotations

import os
import json
import uuid
import logging
from pathlib import Path

import aiosqlite

import biz_database as db
import biz_nidaan as _n
import biz_nidaan_doc_checklist as _ck
import biz_nidaan_whatsapp as _wa
import biz_nidaan_wa_messages as _msg
import biz_doc_splitter as _split

logger = logging.getLogger("nidaan.wa.orch")
DB_PATH = db.DB_PATH
DOCS_DIR = Path(__file__).parent / "uploads" / "nidaan-docs"


# ── helpers ──────────────────────────────────────────────────────────────────
async def _claim_for_msisdn(msisdn: str) -> dict | None:
    """Which claim is this number collecting for? Prefer an explicit wa_contacts link, else match
    by insured_phone (last 10 digits), preferring a claim that still has pending docs."""
    d10 = "".join(ch for ch in (msisdn or "") if ch.isdigit())[-10:]
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        link = await (await c.execute(
            "SELECT claim_id FROM nidaan_wa_contacts WHERE msisdn=? AND claim_id IS NOT NULL",
            (msisdn,))).fetchone()
        cid = link["claim_id"] if link else None
        if not cid and d10:
            r = await (await c.execute(
                "SELECT claim_id FROM nidaan_claims WHERE REPLACE(REPLACE(insured_phone,' ',''),'-','') "
                "LIKE ? ORDER BY claim_id DESC LIMIT 1", (f"%{d10}",))).fetchone()
            cid = r["claim_id"] if r else None
        if not cid:
            return None
        row = await (await c.execute(
            "SELECT claim_id, insured_name, insured_phone, insured_email, claim_type, account_id "
            "FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone()
    return dict(row) if row else None


async def _lang(msisdn: str) -> str:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute("SELECT language FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
    return (r["language"] if r and r["language"] else "hinglish")


async def _set_awaiting(claim_id: int, doc_key: str) -> None:
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute("INSERT OR IGNORE INTO nidaan_wa_claim_settings (claim_id) VALUES (?)", (claim_id,))
        await c.execute("UPDATE nidaan_wa_claim_settings SET awaiting_doc_key=?, updated_at=CURRENT_TIMESTAMP "
                        "WHERE claim_id=?", (doc_key or "", claim_id))
        await c.commit()


async def _awaiting(claim_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute("SELECT awaiting_doc_key, human_takeover FROM nidaan_wa_claim_settings "
                                   "WHERE claim_id=?", (claim_id,))).fetchone()
    if r and r["human_takeover"]:
        return "__human__"
    return (r["awaiting_doc_key"] if r and r["awaiting_doc_key"] else "")


async def _has_spoken(msisdn: str) -> bool:
    """Have we ever sent this number anything? Drives greet-once."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT last_outbound_at FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
        return bool(r and (dict(r).get("last_outbound_at") or ""))
    except Exception:
        return False


async def _asked_recently(claim_id: int, doc_key: str, minutes: int = 90) -> bool:
    """True if we already asked for this exact document within `minutes` — stops the bot
    repeating the identical request every time the customer says anything."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT awaiting_doc_key, last_reminder_at FROM nidaan_wa_claim_settings "
                "WHERE claim_id=? AND last_reminder_at IS NOT NULL "
                "AND last_reminder_at > datetime('now', ?)",
                (claim_id, f"-{int(minutes)} minutes"))).fetchone()
        return bool(r and (dict(r).get("awaiting_doc_key") or "") == doc_key)
    except Exception:
        return False


async def _mark_asked(claim_id: int) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute("UPDATE nidaan_wa_claim_settings SET last_reminder_at=CURRENT_TIMESTAMP "
                            "WHERE claim_id=?", (claim_id,))
            await c.commit()
    except Exception:
        pass


async def _set_takeover(claim_id: int, by: str = "support") -> None:
    """Bot goes quiet on this claim — a human has it now."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute("INSERT OR IGNORE INTO nidaan_wa_claim_settings (claim_id) VALUES (?)", (claim_id,))
            await c.execute("UPDATE nidaan_wa_claim_settings SET human_takeover=1, takeover_by=?, "
                            "updated_at=CURRENT_TIMESTAMP WHERE claim_id=?", (by[:40], claim_id))
            await c.commit()
    except Exception:
        pass


async def _link_contact(msisdn: str, claim: dict) -> None:
    try:
        import biz_nidaan_wa_flow as _flow
        await _flow.upsert_contact(msisdn, claim_id=claim.get("claim_id"),
                                   account_id=claim.get("account_id"), opted_in=True,
                                   opt_source="claimant_msg")
    except Exception:
        pass


def _send_ctx(claim: dict, done: int, total: int, doc=None, next_doc=None, **extra) -> dict:
    ctx = {"name": (claim.get("insured_name") or "").split(" ")[0],
           "insured_name": claim.get("insured_name") or "", "claim_id": claim.get("claim_id"),
           "done": done, "total": total}
    if doc:
        ctx["doc_label"] = doc.get("hi") or doc.get("en") or ""
    if next_doc:
        ctx["next_label"] = next_doc.get("hi") or next_doc.get("en") or ""
    ctx.update(extra)
    return ctx


# ── outbound guided asks (free-form; in-session) ─────────────────────────────
async def ask_next(claim_id: int, msisdn: str, *, greeted: bool = True, force: bool = False) -> dict:
    """Ask for the next pending document, or send the completion message if all are in."""
    claim = await _claim_for_msisdn(msisdn) if not isinstance(claim_id, dict) else claim_id
    if not claim:
        return {"ok": False, "error": "no_claim"}
    lang = await _lang(msisdn)
    ctype = claim.get("claim_type") or ""
    pending = await _ck.pending_required_docs(claim_id, ctype)
    total = len(_ck.doc_template_for(ctype)) or 0
    done = max(0, total - len(pending))
    if not pending:
        await _wa.send_text(msisdn, _msg.compose("docs_complete", lang, _send_ctx(claim, done, total)))
        await _set_awaiting(claim_id, "")
        await _activity(claim_id, "docs_complete", "All required documents received (WhatsApp).")
        return {"ok": True, "complete": True}
    doc = pending[0]
    # Don't repeat the identical request every time they write — that is what made the bot
    # look broken. `force=True` (they said "ok, send it") always re-asks.
    if not force and await _asked_recently(claim_id, doc["key"]):
        return {"ok": True, "skipped": "asked_recently", "asked": doc["key"]}
    await _set_awaiting(claim_id, doc["key"])
    await _wa.send_text(msisdn, _msg.compose("doc_reminder", lang, _send_ctx(claim, done, total, doc=doc)))
    await _mark_asked(claim_id)
    await _activity(claim_id, "doc_reminder", f"Asked for: {doc.get('en')} ({done}/{total})", channel="whatsapp")
    return {"ok": True, "asked": doc["key"]}


async def start_or_continue(msisdn: str, *, force_ask: bool = False) -> dict:
    """A claimant messaged us. Match to their claim, greet ONCE ever, then ask the next doc."""
    claim = await _claim_for_msisdn(msisdn)
    if not claim:
        return {"ok": False, "error": "no_claim"}
    await _link_contact(msisdn, claim)
    lang = await _lang(msisdn)
    # Greet only on the very first message we ever send this number. Re-greeting on every
    # inbound is what spammed the same welcome over and over.
    if not await _has_spoken(msisdn):
        try:
            await _wa.send_text(msisdn, _msg.compose("welcome", lang, _send_ctx(claim, 0, 0)))
        except Exception:
            pass
    return await ask_next(claim["claim_id"], msisdn, force=force_ask)


# ── inbound document pipeline ────────────────────────────────────────────────
async def classify_document(pdf_bytes: bytes, expected_label: str) -> dict:
    """Gemini vision: is this the expected document, and is it legible? Best-effort — on any
    failure we ACCEPT (fail-open) so a Gemini hiccup never blocks a genuine document."""
    try:
        import biz_ai
        client = biz_ai._get_client()
        if not client:
            return {"is_expected": True, "legible": True, "looks_like": "", "reason": "no_ai"}
        from google.genai import types as gt
        prompt = (
            f"A claimant was asked to send their '{expected_label}' for an insurance claim. "
            "Look at the attached document and answer STRICTLY as JSON: "
            '{"is_expected": <true if this IS that document type, else false>, '
            '"looks_like": "<what document it actually appears to be, short>", '
            '"legible": <true if clear/complete enough to read and process, false if blurry/cropped/dark/partial>, '
            '"reason": "<one short reason>"}')
        resp = await client.aio.models.generate_content(
            model=os.getenv("DOCSPLIT_MODEL", "gemini-2.5-flash"),
            contents=[gt.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt],
            config=gt.GenerateContentConfig(response_mime_type="application/json"))
        v = json.loads(resp.text) or {}
        return {"is_expected": bool(v.get("is_expected", True)), "legible": bool(v.get("legible", True)),
                "looks_like": str(v.get("looks_like", ""))[:60], "reason": str(v.get("reason", ""))[:120]}
    except Exception as e:  # noqa: BLE001
        logger.info("classify_document failed (accepting): %s", e)
        return {"is_expected": True, "legible": True, "looks_like": "", "reason": "classify_error"}


async def _save_wa_doc(account_id, claim_id: int, doc_key: str, pdf_bytes: bytes) -> int | None:
    try:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        stored = f"{uuid.uuid4().hex}.pdf"
        (DOCS_DIR / stored).write_bytes(pdf_bytes)
        return await _n.save_claim_document(
            account_id=account_id, stored_name=stored,
            original_name=f"NP-{claim_id}_{doc_key}.pdf", file_size=len(pdf_bytes),
            mime_type="application/pdf", claim_id=claim_id, source="claimant")
    except Exception as e:  # noqa: BLE001
        logger.warning("_save_wa_doc failed claim=%s: %s", claim_id, e)
        return None


# Lifecycle event → approved-template name. Fill these in once templates are approved in Meta;
# until then a COLD (out-of-session) send logs "needs template" rather than failing loudly.
JOURNEY_TEMPLATES = {
    "welcome": "np_welcome",
    "intro_value": "np_intro_value",
    "claim_registered": "np_claim_registered",
    "thank_you_payment": "np_payment_thanks",
    "payment_failed": "np_payment_failed",
    "doc_reminder": "np_doc_reminder",
}

# Meta template language code for a contact's stored language. We authored en + hi variants;
# hinglish (Hindi-first audience) maps to the Devanagari hi template for the cold first-touch,
# while the in-session free-form message stays true Hinglish.
_TMPL_LANG = {"hi": "hi", "en": "en", "hinglish": "hi"}


def _reg_no(ctx: dict) -> str:
    cid = ctx.get("claim_id")
    return ctx.get("reg_no") or (f"NP-{int(cid):04d}" if cid else "")


def _template_params(event: str, ctx: dict) -> list:
    """Ordered {{1}},{{2}}… values for each approved template. Order MUST match the template body."""
    name = ctx.get("name") or "ji"
    if event == "claim_registered":       # {{1}}=name {{2}}=ref {{3}}=insured
        return [name, _reg_no(ctx), ctx.get("insured_name") or name]
    if event == "thank_you_payment":      # {{1}}=name {{2}}=amount {{3}}=ref
        return [name, str(ctx.get("amount") or ""), _reg_no(ctx)]
    if event == "doc_reminder":           # {{1}}=name {{2}}=ref {{3}}=doc
        return [name, _reg_no(ctx), ctx.get("doc_label") or "document"]
    return [name]                          # welcome / intro_value / payment_failed → {{1}}=name


async def wa_journey(claim_id: int, event: str, extra: dict | None = None,
                     skip_phones: list | None = None) -> dict:
    """Send a lifecycle WhatsApp message to the claim's COMPLAINANT (welcome / intro_value /
    claim_registered / thank_you_payment / payment_failed). In-session → free-form text; cold →
    approved template (logs 'needs template' until they exist). Records on the claim timeline. Safe.

    skip_phones: numbers another path already messages (e.g. the subscriber WhatsApp confirmation);
    if the complainant is one of them we DON'T send a second WhatsApp to the same phone."""
    try:
        if not _wa.is_configured():
            return {"ok": False, "error": "not_configured"}
        # Master switch — the founder turns the live complainant journey on/off from the WA panel.
        if str(await _n.get_ops_setting("wa_journey_enabled", "1")) not in ("1", "true", "True"):
            return {"ok": False, "error": "journey_disabled"}
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT claim_id, complainant_name, complainant_phone, complainant_email, insured_name, "
                "insured_phone, claim_type FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
        if not r:
            return {"ok": False, "error": "no_claim"}
        claim = dict(r)
        phone = (claim.get("complainant_phone") or claim.get("insured_phone") or "").strip()
        if not phone:
            return {"ok": False, "error": "no_phone"}
        msisdn = _wa.normalize_msisdn(phone)
        # De-dup: don't send a second WhatsApp to a number another path already messages.
        if skip_phones:
            _skip = {_wa.normalize_msisdn(p) for p in skip_phones if (p or "").strip()}
            if msisdn in _skip:
                return {"ok": False, "error": "dedup_same_phone"}
        # Consent: never message a complainant who replied STOP.
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            _ct = await (await c.execute(
                "SELECT status FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
        if _ct and dict(_ct).get("status") == "stopped":
            return {"ok": False, "error": "opted_out"}
        lang = await _lang(msisdn)
        ctx = {"name": (claim.get("complainant_name") or claim.get("insured_name") or "").split(" ")[0],
               "claim_id": claim_id, "insured_name": claim.get("insured_name") or ""}
        if extra:
            ctx.update(extra)
        text = _msg.compose(event, lang, ctx)
        import biz_nidaan_wa_flow as _flow
        if await _flow.in_session_window(msisdn):
            res = await _wa.send_text(msisdn, text)
        else:
            tmpl = JOURNEY_TEMPLATES.get(event, "")
            if tmpl:
                comps = _wa.body_params(*_template_params(event, ctx))
                res = await _wa.send_template(msisdn, tmpl, _TMPL_LANG.get(lang, "hi"), comps)
            else:
                res = {"ok": False, "error": "needs_template"}
        await _activity(claim_id, f"wa_{event}", summary=(
            f"WhatsApp {event} → complainant" + ("" if res.get("ok") else
            (" (queued — needs approved template)" if res.get("error") == "needs_template" else
             f" (not sent: {res.get('error')})"))))
        return res
    except Exception as e:  # noqa: BLE001
        logger.warning("wa_journey %s failed claim=%s: %s", event, claim_id, e)
        return {"ok": False, "error": str(e)[:120]}


async def start_for_claim(claim_id: int, *, by: str = "system") -> dict:
    """Ops-triggered start: greet the claimant + ask the first pending doc. Free-form delivers only
    inside a 24h session; a cold start needs an approved template (returns needs_template hint)."""
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT insured_phone FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    if not r or not (r["insured_phone"] or "").strip():
        return {"ok": False, "error": "no_phone"}
    msisdn = _wa.normalize_msisdn(r["insured_phone"])
    res = await start_or_continue(msisdn)
    await _activity(claim_id, "doc_collection_start", f"WhatsApp doc-collection started by {by}")
    return res


async def handle_inbound_document(msisdn: str, media_id: str, mime: str) -> dict:
    """A claimant sent a file. Right-doc + quality gate → convert → save → mark → ask next."""
    claim = await _claim_for_msisdn(msisdn)
    if not claim:
        return {"ok": False, "error": "no_claim"}
    claim_id = claim["claim_id"]
    lang = await _lang(msisdn)
    ctype = claim.get("claim_type") or ""
    awaiting = await _awaiting(claim_id)
    if awaiting == "__human__":
        return {"ok": False, "error": "human_takeover"}
    # Which doc did we ask for? (If none tracked, use the next pending.)
    pending = await _ck.pending_required_docs(claim_id, ctype)
    if not pending:
        await _wa.send_text(msisdn, _msg.compose("docs_complete", lang, _send_ctx(claim, 1, 1)))
        return {"ok": True, "complete": True}
    doc = next((d for d in pending if d["key"] == awaiting), pending[0])
    total = len(_ck.doc_template_for(ctype)) or 0
    # Download + normalise to PDF.
    dl = await _wa.download_media(media_id)
    if not dl.get("ok"):
        await _wa.send_text(msisdn, _msg.compose("doc_quality", lang,
                            _send_ctx(claim, total - len(pending), total, doc=doc, reason="could not open the file")))
        return {"ok": False, "error": "download_failed"}
    ext = ".pdf" if "pdf" in (mime or "") else (".jpg" if "jpe" in (mime or "") or "jpg" in (mime or "") else ".png" if "png" in (mime or "") else ".bin")
    try:
        pdf_bytes, pages, _skipped = _split.normalize_to_pdf([(f"in{ext}", dl["content"])])
    except Exception as e:  # noqa: BLE001
        logger.info("normalize_to_pdf failed: %s", e)
        pdf_bytes = None
    if not pdf_bytes:
        await _wa.send_text(msisdn, _msg.compose("doc_quality", lang,
                            _send_ctx(claim, total - len(pending), total, doc=doc, reason="unsupported format")))
        return {"ok": False, "error": "convert_failed"}
    # Gemini right-doc + quality gate.
    v = await classify_document(pdf_bytes, doc.get("en") or doc.get("hi") or "document")
    if not v["is_expected"]:
        await _wa.send_text(msisdn, _msg.compose("doc_wrong", lang,
                            _send_ctx(claim, total - len(pending), total, doc=doc, looks_like=v.get("looks_like") or "")))
        await _activity(claim_id, "doc_rejected", f"Wrong doc for {doc.get('en')} (looked like {v.get('looks_like')})", channel="whatsapp", direction="in")
        return {"ok": False, "error": "wrong_doc"}
    if not v["legible"]:
        await _wa.send_text(msisdn, _msg.compose("doc_quality", lang,
                            _send_ctx(claim, total - len(pending), total, doc=doc, reason=v.get("reason") or "not clear")))
        await _activity(claim_id, "doc_rejected", f"Poor quality for {doc.get('en')}: {v.get('reason')}", channel="whatsapp", direction="in")
        return {"ok": False, "error": "poor_quality"}
    # Good → save + mark + ask next.
    doc_id = await _save_wa_doc(claim.get("account_id"), claim_id, doc["key"], pdf_bytes)
    await _ck.mark_doc_received(claim_id, doc["key"], via="whatsapp", doc_id=doc_id)
    await _activity(claim_id, "doc_received", f"Received {doc.get('en')} via WhatsApp", channel="whatsapp", direction="in")
    # Received-ok + next ask.
    pending2 = await _ck.pending_required_docs(claim_id, ctype)
    nxt = pending2[0] if pending2 else None
    done = max(0, total - len(pending2))
    await _wa.send_text(msisdn, _msg.compose("doc_received_ok", lang, _send_ctx(claim, done, total, doc=doc, next_doc=nxt)))
    if nxt:
        await _set_awaiting(claim_id, nxt["key"])
    else:
        await _set_awaiting(claim_id, "")
        await _wa.send_text(msisdn, _msg.compose("docs_complete", lang, _send_ctx(claim, done, total)))
        await _activity(claim_id, "docs_complete", "All required documents received (WhatsApp).")
    return {"ok": True, "received": doc["key"], "remaining": len(pending2)}


async def handle_inbound_text(msisdn: str, text: str) -> dict:
    """A claimant sent text. READ IT FIRST, then respond like a person would.

    Previously this ignored the message entirely and re-sent welcome + the same document ask
    every single time. Now the conversation brain decides: answer the question, continue the
    guided document flow, decline once (abuse / off-topic), or hand off to a human."""
    claim = await _claim_for_msisdn(msisdn)
    if not claim:
        return {"ok": False, "error": "no_claim"}
    claim_id = claim["claim_id"]
    if await _awaiting(claim_id) == "__human__":
        return {"ok": False, "error": "human_takeover"}   # a human owns this chat — stay quiet
    lang = await _lang(msisdn)
    await _link_contact(msisdn, claim)

    import biz_nidaan_wa_brain as _brain
    d = await _brain.decide(text, lang)
    action, reply = d.get("action"), d.get("reply") or ""
    await _activity(claim_id, "wa_inbound", f"Customer: {(text or '')[:120]}", direction="in")

    if action == "continue_docs":
        # They're ready to send — always re-state the exact document (force past the throttle).
        return await start_or_continue(msisdn, force_ask=True)

    if action == "refuse":
        # Decline ONCE. If they were already declined and still haven't asked something
        # sensible, stay silent rather than argue.
        if await _asked_recently(claim_id, "__refused__", minutes=180):
            return {"ok": True, "action": "refuse", "muted": True}
        await _wa.send_text(msisdn, reply or _brain.refusal_text(lang))
        await _set_awaiting(claim_id, "__refused__")
        await _mark_asked(claim_id)
        await _activity(claim_id, "wa_refused", f"Declined off-scope/abusive message ({d.get('reason','')})")
        return {"ok": True, "action": "refuse"}

    if action == "handoff":
        await _wa.send_text(msisdn, reply or _brain.handoff_text(lang))
        await _handoff_to_support(claim, msisdn, text, lang, reason=d.get("reason", ""))
        return {"ok": True, "action": "handoff"}

    # action == "answer" — a natural reply, then a gentle (throttled) nudge for the pending doc.
    await _wa.send_text(msisdn, reply)
    await _activity(claim_id, "wa_answer", f"Answered: {reply[:120]}")
    await ask_next(claim_id, msisdn)          # throttled — won't repeat if just asked
    return {"ok": True, "action": "answer"}


async def _handoff_to_support(claim: dict, msisdn: str, text: str, lang: str, reason: str = "") -> None:
    """Open (or extend) a Support thread in ops with the WhatsApp message, escalate it to a
    human, and mute the bot on this claim so it never talks over the person taking it."""
    claim_id = claim.get("claim_id")
    try:
        th = await _n.create_support_thread(
            name=(claim.get("complainant_name") or claim.get("insured_name") or "WhatsApp customer"),
            contact=msisdn, account_id=claim.get("account_id"), channel="whatsapp", lang=lang)
        tid = th.get("thread_id")
        # Carry the WhatsApp conversation into the thread so staff have the context.
        await _n.add_support_message(tid, "customer", (text or "")[:2000])
        await _n.add_support_message(
            tid, "ai", f"[auto] Handed off from the WhatsApp bot — {reason or 'needs a human'}. "
                       f"Claim #NP-{claim_id}. Reply to the customer on WhatsApp {msisdn}.")
        await _n.set_support_status(tid, "escalated")
        await _set_takeover(claim_id, by="support")
        await _activity(claim_id, "wa_handoff", f"Handed to Support (thread #{tid}) — {reason or 'needs a human'}")
        try:
            import biz_nidaan_notifications as _nnot
            await _nnot.on_support_escalated(tid)
        except Exception:
            pass
    except Exception as e:  # noqa: BLE001
        logger.warning("WhatsApp support handoff failed for claim %s: %s", claim_id, e)


async def _activity(claim_id: int, kind: str, summary: str, *, channel: str = "whatsapp", direction: str = "out") -> None:
    try:
        await _n.record_claim_activity(claim_id, kind, channel=channel, direction=direction,
                                       actor=("claimant" if direction == "in" else "bot"), summary=summary)
    except Exception:
        pass
