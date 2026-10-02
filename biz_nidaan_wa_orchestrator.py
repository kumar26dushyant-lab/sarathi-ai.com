"""
NidaanPartner claimant-WhatsApp ORCHESTRATOR — the guided document-collection brain.

Ties together: the doc checklist (single source of truth), the message composer, Gemini vision
(right-doc + quality gate), the PDF pipeline (normalize_to_pdf), and the WhatsApp send/receive.

Flow (guided, one document at a time):
  complainant messages us (opens 24h session) → we match them to their claim by phone → greet +
  ask for the NEXT pending document → they send a photo/PDF → we verify it's the RIGHT doc and
  legible (Gemini) → if wrong/blurry, a specific nudge; if good, convert→PDF, save to the claim,
  mark the checklist, and ask for the next one → when all in, a "complete" message. Every step is
  recorded on the claim activity timeline.

In-session (complainant replied within 24h) uses free-form text — testable NOW. Business-INITIATED
messages (cold outreach, daily reminders when the session is closed) need approved templates;
that path is marked and no-ops cleanly until the templates exist.
"""
from __future__ import annotations

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
            # The COMPLAINANT first - they are who we ask for documents, so they are who
            # replies. This matched insured_phone only, so a complainant who is not the insured
            # would write back and land on no claim at all.
            r = await (await c.execute(
                "SELECT claim_id FROM nidaan_claims WHERE "
                "REPLACE(REPLACE(COALESCE(complainant_phone,''),' ',''),'-','') LIKE ? "
                "OR REPLACE(REPLACE(COALESCE(insured_phone,''),' ',''),'-','') LIKE ? "
                "ORDER BY claim_id DESC LIMIT 1", (f"%{d10}", f"%{d10}"))).fetchone()
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


async def _contact_paused(msisdn: str) -> bool:
    """Is a human holding THIS conversation? Keyed on the number, not the claim.

    Takeover used to live only on nidaan_wa_claim_settings, so a chat with no claim attached —
    a prospect, a branch, a subscriber asking a question — could never mute the bot, and the AI
    kept replying over the staffer who had just been handed the conversation. A WhatsApp
    conversation is one msisdn, so that is what ownership hangs off.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT bot_paused FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
        return bool(r and dict(r).get("bot_paused"))
    except Exception:
        return False   # never let a read error silence the bot on a live conversation


async def _human_holds(msisdn: str, claim_id=None) -> bool:
    """True if either the conversation or its claim is under human takeover."""
    if await _contact_paused(msisdn):
        return True
    return bool(claim_id) and (await _awaiting(claim_id)) == "__human__"


async def pause_bot(msisdn: str, *, by: str = "support", paused: bool = True) -> None:
    """Hand this conversation to a human (or give it back to the bot). Idempotent."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute("INSERT OR IGNORE INTO nidaan_wa_contacts (msisdn) VALUES (?)", (msisdn,))
            if paused:
                await c.execute("UPDATE nidaan_wa_contacts SET bot_paused=1, paused_by=?, "
                                "paused_at=CURRENT_TIMESTAMP WHERE msisdn=?", (by[:40], msisdn))
            else:
                await c.execute("UPDATE nidaan_wa_contacts SET bot_paused=0, paused_by='', "
                                "paused_at=NULL WHERE msisdn=?", (msisdn,))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("pause_bot(%s) failed: %s", msisdn, e)


async def _recent_history(msisdn: str, turns: int = 8, hours: int = 48) -> str:
    """The last few turns with this number, oldest first, for the conversation brain.

    Without it the model meets every customer for the first time, every time - which is how the
    founder collected three different introductions to his own company in half an hour.

    Bounded on purpose: a long history costs tokens and latency on every inbound, and anything
    older than a couple of days is a different conversation rather than context for this one.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            rows = [dict(r) for r in await (await c.execute(
                "SELECT direction, COALESCE(body,'') AS body FROM nidaan_wa_messages "
                "WHERE msisdn=? AND COALESCE(body,'') <> '' "
                "AND created_at >= datetime('now', ?) "
                "ORDER BY created_at DESC LIMIT ?",
                (msisdn, "-%d hours" % int(hours), int(turns)))).fetchall()]
    except Exception as e:  # noqa: BLE001
        logger.info("history lookup failed for %s: %s", msisdn, e)
        return ""
    rows.reverse()
    out = []
    for r in rows:
        who = "Customer" if r["direction"] == "in" else "Us"
        out.append("%s: %s" % (who, (r["body"] or "").replace("\n", " ")[:220]))
    return "\n".join(out)


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


async def _recent_outbound(msisdn: str, minutes: int = 120) -> bool:
    """Did we message this number within `minutes`? A generic throttle that — unlike the
    document one — never touches the claim's awaiting-document state."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            r = await (await c.execute(
                "SELECT 1 FROM nidaan_wa_contacts WHERE msisdn=? AND last_outbound_at IS NOT NULL "
                "AND last_outbound_at > datetime('now', ?)",
                (msisdn, f"-{int(minutes)} minutes"))).fetchone()
        return bool(r)
    except Exception:
        return False


async def _reserve_reply(msisdn: str, minutes: int = 120) -> bool:
    """Take the one reply this number may get in `minutes` - atomically. True means send it.

    Checking "did we message them recently?" and then sending let two messages arriving in the
    same second both pass the check: claim #245 got the same reply twice. One UPDATE decides, so
    only one arrival - in any web worker - wins the slot. The contact row exists by now (every
    inbound message upserts it first)."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "UPDATE nidaan_wa_contacts SET last_outbound_at=CURRENT_TIMESTAMP WHERE msisdn=? "
                "AND (last_outbound_at IS NULL OR last_outbound_at <= datetime('now', ?))",
                (msisdn, f"-{int(minutes)} minutes"))
            await c.commit()
            return cur.rowcount == 1
    except Exception:  # noqa: BLE001 - unsure means do not send a second copy
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


async def _link_contact(msisdn: str, claim: dict, *, they_wrote: bool = True) -> None:
    """Tie a number to its claim. Consent is recorded only when THEY wrote to us - a staff member
    starting a conversation is not the complainant agreeing to hear from us, and opted_in is what
    puts a number in a campaign's audience (1 Oct review)."""
    try:
        import biz_nidaan_wa_flow as _flow
        if they_wrote:
            await _flow.upsert_contact(msisdn, claim_id=claim.get("claim_id"),
                                       account_id=claim.get("account_id"), opted_in=True,
                                       opt_source="claimant_msg")
        else:
            await _flow.upsert_contact(msisdn, claim_id=claim.get("claim_id"),
                                       account_id=claim.get("account_id"))
    except Exception:
        pass


def _looks_like_junk(name: str) -> bool:
    """A name nobody would answer to ("OLKL;L;L;L;L;L;", "asdf", "....") - worth a warning."""
    n = (name or "").strip()
    if len(n) < 2:
        return True
    letters = sum(ch.isalpha() for ch in n)
    return letters < 0.7 * len(n.replace(" ", "")) or any(ch in n for ch in ";{}[]<>|\\/=_")


def _doc_label(doc: dict, lang: str) -> str:
    """Document name in the SAME script as the message. Hinglish is Roman-script, so it takes the
    English label — mixing Roman sentences with a Devanagari document name reads badly."""
    if not doc:
        return ""
    if lang == "hi":
        return doc.get("hi") or doc.get("en") or ""
    return doc.get("en") or doc.get("hi") or ""


def _send_ctx(claim: dict, done: int, total: int, doc=None, next_doc=None,
              lang: str = "hinglish", **extra) -> dict:
    ctx = {"name": (claim.get("insured_name") or "").split(" ")[0],
           "insured_name": claim.get("insured_name") or "", "claim_id": claim.get("claim_id"),
           "done": done, "total": total}
    if doc:
        ctx["doc_label"] = _doc_label(doc, lang)
    if next_doc:
        ctx["next_label"] = _doc_label(next_doc, lang)
    ctx.update(extra)
    return ctx


# ── outbound guided asks (free-form; in-session) ─────────────────────────────
async def ask_next(claim_id: int, msisdn: str, *, greeted: bool = True, force: bool = False) -> dict:
    """Ask for the next pending document, or send the completion message if all are in."""
    # A staffer holding this chat must not have the reminder loop asking for documents behind
    # their back — the customer would see two voices at once. Checked before anything else.
    if await _human_holds(msisdn, claim_id if not isinstance(claim_id, dict) else None):
        return {"ok": False, "error": "human_takeover"}
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
    _ctx = _send_ctx(claim, done, total, doc=doc, lang=lang)
    try:
        import biz_nidaan_wa_remind as _remind
        if await _remind.enabled():
            _ctx["offer_line"] = _remind.text("offer", lang)
    except Exception:  # noqa: BLE001 - the ask goes out without the offer rather than not at all
        pass
    sent = await _wa.send_text(msisdn, _msg.compose("doc_reminder", lang, _ctx))
    # Only a message that actually went counts as asked. This used to mark the claim asked and
    # write "Asked for: X" whatever happened - so a refused message read on the timeline as a
    # delivered one, and the retry then skipped itself as "asked recently".
    if not (sent or {}).get("ok"):
        await _activity(claim_id, "doc_reminder",
                        f"WhatsApp NOT delivered — {doc.get('en')}: {(sent or {}).get('error') or 'refused'}",
                        channel="whatsapp")
        return {"ok": False, "error": (sent or {}).get("error") or "send_failed",
                "asked": doc["key"]}
    await _mark_asked(claim_id)
    await _activity(claim_id, "doc_reminder", f"Asked for: {doc.get('en')} ({done}/{total})", channel="whatsapp")
    return {"ok": True, "asked": doc["key"]}


async def _tell_staff_inbound(claim_id, msisdn: str, text: str) -> None:
    """Tell the people on this claim that the complainant has replied — Telegram + bell.

    Founder, 24 Sep: "if anything we get from customer/complainant side on a particular claim
    through whatsapp, updates should be going to our related staff on telegram."

    Before this, an inbound message wrote one line to the activity timeline and nothing else. On
    a claim waiting for a document, the wait was however long it took somebody to look.

    Never email (claim traffic does not go to staff by email) and never require an acknowledgement
    (a day of "the customer said ok" popups teaches people to dismiss popups unread). Failure here
    must never break the reply the customer is waiting on, so it is caught and logged.
    """
    if not claim_id:
        return          # not tied to a claim yet - there is nobody specific to tell
    try:
        import biz_nidaan_notifications as _nnot
        body = ('💬 The complainant replied on WhatsApp about claim #%s:\n"%s"\n\n'
                'Open: /nidaan/ops?claim=%s' % (claim_id, (text or "").strip()[:140] or "(no text — an attachment)",
                                                claim_id))
        await _nnot.notify_claim_watchers(
            claim_id, "💬 WhatsApp reply on claim #%s" % claim_id, body,
            event_key="claim.wa_inbound", email=False, require_ack=False)
    except Exception as e:  # noqa: BLE001
        logger.warning("could not tell staff about the WhatsApp reply on claim %s: %s", claim_id, e)

async def start_or_continue(msisdn: str, *, force_ask: bool = False) -> dict:
    """A complainant messaged us. Match to their claim, greet ONCE ever, then ask the next doc."""
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
# The claimant document pipeline used to start here, with a Gemini call asking "is this the
# document we asked for, and can you read it?". Both halves are gone: no claim document leaves
# this server (founder, 28 Sep), and nothing is judged automatically any more. What arrives is
# stored by biz_nidaan_doc_intake and a staff member says what it is. See that module's docstring.


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
    # NOT np_payment_thanks. That template reads "Your payment of ₹{{2}} is confirmed", which
    # tells a complainant what their BRANCH paid us - on 18 Sep someone charged ₹1,200 by their
    # channel partner was shown ₹588 by us. np_claim_registered carries no money at all and says
    # the right thing: your claim is registered and we have started. (founder, 18 Sep)
    "thank_you_payment": "np_claim_registered",
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
    # Both of these now ride np_claim_registered: {{1}}=name {{2}}=ref {{3}}=insured. No money.
    if event in ("claim_registered", "thank_you_payment"):
        return [name, _reg_no(ctx), ctx.get("insured_name") or name]
    if event == "doc_reminder":           # {{1}}=name {{2}}=ref {{3}}=doc
        return [name, _reg_no(ctx), ctx.get("doc_label") or "document"]
    return [name]                          # welcome / intro_value / payment_failed → {{1}}=name


# Nothing about money reaches a party. A branch pays us one figure and charges the complainant
# another; disclosing ours exposes their margin and is not ours to disclose. Stripping it HERE,
# at the one door every lifecycle message goes through, means a caller cannot reintroduce the
# leak by passing an amount - which is exactly how it happened the first time.
_MONEY_KEYS = ("amount", "amount_rupees", "fee", "price", "plan", "plan_name", "paid")


def _strip_money(ctx: dict) -> dict:
    return {k: v for k, v in (ctx or {}).items() if k not in _MONEY_KEYS}


# The welcome and "your claim is registered" are said ONCE per claim. The 20-minute alert sweep
# re-ran the claim-raised path and every Rs 499 website claim got "claim registered" twice
# (found 2 Oct). A failed attempt may be retried; a send stuck for 10 minutes may be retaken.
JOURNEY_ONCE = {"welcome", "intro_value", "claim_registered", "thank_you_payment", "welcome_email"}
JOURNEY_WINDOW_MIN = {"payment_failed": 15}     # two failed UPI tries in a minute: one message


async def _journey_reserve(claim_id: int, event: str) -> bool:
    once, win = event in JOURNEY_ONCE, JOURNEY_WINDOW_MIN.get(event)
    if not (once or win):
        return True
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "CREATE TABLE IF NOT EXISTS nidaan_journey_sends (claim_id INTEGER NOT NULL, event TEXT NOT NULL,"
            " state TEXT NOT NULL DEFAULT 'sending', at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            " PRIMARY KEY (claim_id, event))")
        cur = await c.execute(
            "INSERT OR IGNORE INTO nidaan_journey_sends (claim_id, event, state) VALUES (?,?,'sending')",
            (int(claim_id), event))
        if cur.rowcount != 1:
            if once:
                cur = await c.execute(
                    "UPDATE nidaan_journey_sends SET state='sending', at=CURRENT_TIMESTAMP"
                    " WHERE claim_id=? AND event=? AND (state='failed'"
                    " OR (state='sending' AND at < datetime('now','-10 minutes')))", (int(claim_id), event))
            else:
                cur = await c.execute(
                    "UPDATE nidaan_journey_sends SET state='sending', at=CURRENT_TIMESTAMP"
                    " WHERE claim_id=? AND event=? AND at < datetime('now', ?)",
                    (int(claim_id), event, f"-{int(win)} minutes"))
        await c.commit()
        return cur.rowcount == 1


async def _journey_done(claim_id: int, event: str, ok: bool) -> None:
    if event not in JOURNEY_ONCE and event not in JOURNEY_WINDOW_MIN:
        return
    async with aiosqlite.connect(DB_PATH) as c:
        if ok:
            await c.execute("UPDATE nidaan_journey_sends SET state='sent' WHERE claim_id=? AND event=?",
                            (int(claim_id), event))
        else:
            # failed: free to try again (a windowed event is not held back by a send that never went)
            await c.execute("UPDATE nidaan_journey_sends SET state='failed', at=datetime('now','-1 day')"
                            " WHERE claim_id=? AND event=?", (int(claim_id), event))
        await c.commit()


async def wa_journey(claim_id: int, event: str, extra: dict | None = None,
                     skip_phones: list | None = None) -> dict:
    """The lifecycle message, signed by the claim's Authorized Partner if it came through one."""
    import biz_nidaan_ap_sign as _aps
    with _aps.about(claim_id=claim_id):
        return await _wa_journey(claim_id, event, extra, skip_phones)


async def _wa_journey(claim_id: int, event: str, extra: dict | None = None,
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
        ctx = _strip_money(ctx)            # a party never hears a figure from us
        text = _msg.compose(event, lang, ctx)
        import biz_nidaan_wa_flow as _flow
        # A failed payment is about their money and blocks their claim: it is never held back by
        # the "how often may we speak first" cap. Everything else in the journey is.
        _as = "critical" if event == "payment_failed" else "journey"
        if not await _journey_reserve(claim_id, event):
            return {"ok": False, "error": "already_sent"}
        if await _flow.in_session_window(msisdn):
            with _wa.sending_as(_as):
                res = await _wa.send_text(msisdn, text)
        else:
            tmpl = JOURNEY_TEMPLATES.get(event, "")
            if tmpl:
                comps = _wa.body_params(*_template_params(event, ctx))
                with _wa.sending_as(_as):
                    import biz_nidaan_wa_lang as _wl
                    res = await _wa.send_template(msisdn, tmpl, _TMPL_LANG.get(_wl.base(lang), "hi"), comps)
            else:
                res = {"ok": False, "error": "needs_template"}
        await _journey_done(claim_id, event, bool(res.get("ok")))
        await _activity(claim_id, f"wa_{event}", summary=(
            f"WhatsApp {event} → complainant" + ("" if res.get("ok") else
            (" (queued — needs approved template)" if res.get("error") == "needs_template" else
             f" (not sent: {res.get('error')})"))))
        return res
    except Exception as e:  # noqa: BLE001
        logger.warning("wa_journey %s failed claim=%s: %s", event, claim_id, e)
        return {"ok": False, "error": str(e)[:120]}


async def start_for_claim(claim_id: int, *, by: str = "system", preview: bool = False) -> dict:
    """Staff pressed "Start WhatsApp collection". Ask the COMPLAINANT for the first missing document.

    Two cases, because Meta allows two different kinds of message:
      * they have written to us in the last 24 hours -> the guided, one-document-at-a-time chat
      * they have not -> the APPROVED np_doc_reminder template, naming the first missing document.
        Free text to a cold number is refused outright; the template is the only way in. When
        they reply, the 24-hour window opens and the guided chat takes over from their answer.

    Returns exactly what happened, including when nothing was delivered, so the screen can say so.
    """
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, complainant_name, complainant_phone, insured_name, insured_phone, "
            "claim_type, account_id FROM nidaan_claims WHERE claim_id=?", (claim_id,))).fetchone()
    if not r:
        return {"ok": False, "error": "no_claim"}
    claim = dict(r)
    # The complainant first, exactly as the document window and every other message does.
    phone = (claim.get("complainant_phone") or claim.get("insured_phone") or "").strip()
    who = (claim.get("complainant_name") or claim.get("insured_name") or "").strip()
    if not phone:
        return {"ok": False, "error": "no_phone"}
    msisdn = _wa.normalize_msisdn(phone)
    masked = "…" + msisdn[-4:]

    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        ct = await (await c.execute(
            "SELECT status FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
    if ct and dict(ct).get("status") == "stopped":
        if not preview:
            await _activity(claim_id, "doc_collection_start",
                            f"WhatsApp not started by {by} — {who or 'the complainant'} replied STOP")
        return {"ok": False, "error": "opted_out", "to": masked, "who": who}

    pending = await _ck.pending_required_docs(claim_id, claim.get("claim_type") or "")
    if not pending:
        return {"ok": False, "error": "nothing_pending", "to": masked, "who": who}

    # A person is handling this chat by hand: the bot does not start talking over them - on
    # EITHER path (the template path used to skip this check).
    async with aiosqlite.connect(DB_PATH) as c:
        bp = await (await c.execute(
            "SELECT COALESCE(bot_paused,0), COALESCE(assigned_name,'') FROM nidaan_wa_contacts WHERE msisdn=?",
            (msisdn,))).fetchone()
    if bp and int(bp[0] or 0):
        return {"ok": False, "error": "human_takeover", "to": masked, "who": who,
                "handler": bp[1] or ""}

    import biz_nidaan_wa_flow as _flow
    in_session = await _flow.in_session_window(msisdn)
    first = (pending[0].get("en") or pending[0]["key"])
    if preview:
        # What WOULD happen - nothing is sent and nothing is recorded.
        try:
            import biz_nidaan_contact_verify as _cv
            st = (await _cv.status(await _cv._claim(claim_id))).get("phone") or {}
            phone_ok = bool(st.get("verified"))
        except Exception:  # noqa: BLE001
            phone_ok = False
        warn = []
        if _looks_like_junk(who):
            warn.append("The complainant's name looks wrong (\"%s\") - correct it on the claim first; "
                        "the message greets them by it." % (who or "blank"))
        if not phone_ok:
            warn.append("This mobile number has not been confirmed by the complainant yet.")
        return {"ok": True, "preview": True, "mode": "chat" if in_session else "template",
                "to": masked, "who": who, "first_doc": first, "pending": len(pending),
                "docs": [(d.get("en") or d["key"]) for d in pending], "warnings": warn}

    # Tie this number to THIS claim, so whatever they send back lands here - whichever of the
    # claim's two phone numbers it was. A staff start is not their consent.
    try:
        await _link_contact(msisdn, claim, they_wrote=in_session)
    except Exception:
        pass

    if in_session:
        res = await start_or_continue(msisdn, force_ask=True)
        mode = "chat"
    else:
        doc = pending[0]
        # Remember what we asked for, so a photo sent in reply is filed against the right paper.
        await _set_awaiting(claim_id, doc["key"])
        res = await wa_journey(claim_id, "doc_reminder",
                               {"doc_label": doc.get("en") or doc["key"]})
        mode = "template"
        if (res or {}).get("ok"):
            await _mark_asked(claim_id)

    ok = bool((res or {}).get("ok"))
    await _activity(claim_id, "doc_collection_start",
                    ("WhatsApp doc-collection started by %s — asked %s (%s) for: %s"
                     % (by, who or "the complainant", masked, first)) if ok else
                    ("WhatsApp doc-collection NOT started by %s — %s" % (by, (res or {}).get("error"))))
    return {"ok": ok, "mode": mode, "to": masked, "who": who, "first_doc": first,
            "pending": len(pending), "error": (res or {}).get("error")}


_FILE_NOTICE: dict = {}      # claim_id -> when staff were last told a file arrived during takeover


async def handle_inbound_document(msisdn: str, media_id: str, mime: str,
                                  filename: str = "") -> dict:
    """A complainant sent a file. Take it, split it, match what we can, say one thing.

    This used to judge every inbound file as ONE document against ONE expected line: a 40-page PDF
    holding the whole case was classified as "not the discharge summary" and the sender was told
    they had sent the wrong thing. Worse, if nothing was outstanding the file was thanked for and
    never stored at all. biz_nidaan_doc_intake now does the real work - see its docstring for the
    rules - and this function only decides what to SAY.
    """
    claim = await _claim_for_msisdn(msisdn)
    if not claim:
        return {"ok": False, "error": "no_claim"}
    claim_id = claim["claim_id"]
    lang = await _lang(msisdn)
    ctype = claim.get("claim_type") or ""
    # A PERSON HOLDS THIS CHAT: the bot keeps quiet - but the file is still the customer's
    # document and is saved to the claim. It used to be dropped: on 30 Sep Brajesh Gupta (NP-123)
    # sent eight files - discharge summary, claim form, bills - after his chat was handed to a
    # person, and none of them reached the claim. Now they are stored, and the person handling
    # the chat is told what arrived so they can answer him.
    human = (await _awaiting(claim_id) == "__human__") or await _contact_paused(msisdn)

    dl = await _wa.download_media(media_id)
    if not dl.get("ok") and human:
        await _tell_staff_inbound(claim_id, msisdn, "[a file that could not be downloaded - "
                                  "please ask them to send it again]")
        return {"ok": False, "error": "download_failed"}
    if not dl.get("ok"):
        # Our end could not fetch it. That is ours to own, not theirs to fix.
        await _wa.send_text(msisdn, _msg.compose("doc_quality", lang, _send_ctx(
            claim, 0, 0, doc={"en": "that file"}, lang=lang,
            reason="it did not come through to us")))
        return {"ok": False, "error": "download_failed"}

    name = "upload.pdf"
    m = (mime or "").lower()
    if "zip" in m:
        name = "upload.zip"
    elif "pdf" not in m:
        name = "upload.jpg" if ("jpe" in m or "jpg" in m) else (
            "upload.png" if "png" in m else "upload.bin")
    # The sender's own file name is the best clue to what it is - keep it (safe characters only).
    _fn = _re.sub(r"[^A-Za-z0-9 ._()-]", "", (filename or "").strip())[:90].strip(" .")
    if _fn and "." in _fn and _fn.rsplit(".", 1)[1].lower() == name.rsplit(".", 1)[1]:
        name = _fn

    import biz_nidaan_doc_intake as _intake
    res = await _intake.accept(claim_id, claim.get("account_id"), [(name, dl["content"])],
                              claim_type=ctype, source="whatsapp")
    if human:
        # Saved (or refused by the checks) - either way the person on the chat decides what to say.
        # One notice per claim per few minutes: eight files in a row are one event, not eight pings.
        import time as _time
        _now = _time.monotonic()
        if not res.get("ok") or _now - _FILE_NOTICE.get(claim_id, 0) > 300:
            _FILE_NOTICE[claim_id] = _now
            await _tell_staff_inbound(claim_id, msisdn, "[sent files on WhatsApp - saved to the claim's "
                                      "documents; latest: %s%s]" % (
                                          name, "" if res.get("ok") else " (could not be opened - ask again)"))
        return {"ok": bool(res.get("ok")), "stored": res.get("stored") or 0, "held_by_person": True,
                "error": "" if res.get("ok") else (res.get("error") or "unreadable")}
    if not res.get("ok"):
        await _wa.send_text(msisdn, _msg.compose("doc_quality", lang, _send_ctx(
            claim, 0, 0, doc={"en": "that file"}, lang=lang,
            reason="we could not open it — please send it as a photo or PDF")))
        return {"ok": False, "error": res.get("error") or "unreadable"}

    pending = res.get("pending") or []
    ctx = dict(_send_ctx(claim, 0, res.get("total") or 0))
    ctx.update({
        "stored": res.get("stored") or 0,
        "ticked": [t["label"] or t["key"] for t in res.get("ticked") or []],
        "unclear": [u["label"] or u["key"] for u in res.get("unclear") or []],
        "pending": [d.get("en") or d["key"] for d in pending],
    })
    # ONE message for the whole batch, whatever arrived inside it.
    await _wa.send_text(msisdn, _msg.compose("doc_batch", lang, ctx))

    # Keep the "what are we waiting for" pointer honest for the rest of the conversation.
    await _set_awaiting(claim_id, pending[0]["key"] if pending else "")
    if not pending:
        await _activity(claim_id, "docs_complete", "All required documents received (WhatsApp).")
    return {"ok": True, "stored": res.get("stored") or 0,
            "received": [t["key"] for t in res.get("ticked") or []],
            "unsorted": len(res.get("unsorted") or []), "remaining": len(pending)}


# ── the case email account, when it arrives on WhatsApp ──────────────────────
# The complainant is asked to create an email account for the case and send it with its password.
# ClaimShield keeps both on the case and our gist form has the same two fields, so when it comes in
# on WhatsApp it belongs in those fields - not in a chat log somebody has to go hunting through.
# We take it only when the claim is actually WAITING for it, so an ordinary message that happens to
# mention an address is never mistaken for credentials.
import re as _re

_EMAIL_RE = _re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PWD_HINT = _re.compile(r"(?:password|pass|pwd|पासवर्ड|paswrd)\s*[:\-=]?\s*(\S+)", _re.I)

_GOT_IT = {
    "en": "Got it — the email and password are saved on your claim, and used only to write to "
          "the insurance company and the authorities. When your case is over you can change the "
          "password or delete the account.",
    "hi": "मिल गया — ईमेल और "
          "पासवर्ड आपके क्लेम "
          "पर सुरक्षित हैं, और "
          "इनका उपयोग केवल बीमा "
          "कंपनी और अधिकारियों "
          "को लिखने में होगा। "
          "केस पूरा होने पर आप "
          "पासवर्ड बदल या आईडी "
          "डिलीट कर सकते हैं।",
    "hinglish": "Mil gaya — email aur password aapke claim par safe hain, aur inka upyog sirf "
                "insurance company aur authorities ko likhne mein hoga. Case poora hone par aap "
                "password badal sakte hain ya ID delete kar sakte hain.",
}


async def _capture_case_email(claim_id, text: str, lang: str, msisdn: str) -> dict:
    """Take the case email + password off a WhatsApp message and put them on the claim."""
    if not claim_id:
        return {}
    t = (text or "").strip()
    m = _EMAIL_RE.search(t)
    if not m:
        return {}
    try:
        import biz_nidaan_doc_checklist as _ck
        pending = {d["key"] for d in await _ck.pending_required_docs(claim_id, "")}
        row = None
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            row = await (await c.execute(
                "SELECT claim_type FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
        ctype = dict(row or {}).get("claim_type") or ""
        pending = {d["key"] for d in await _ck.pending_required_docs(claim_id, ctype)}
    except Exception:  # noqa: BLE001
        return {}
    email = m.group(0)
    # WAITING FOR IT, OR BEING CORRECTED. The checklist stops asking once the credentials arrive,
    # and the old rule stopped listening at the same moment - so a complainant writing back to fix
    # a typo in the address was read and thrown away without a word. Every letter to the insurer
    # goes from this mailbox; a wrong address is not a small thing to swallow.
    was = ""
    try:
        import biz_nidaan_buckets as _bk0
        was = ((await _bk0.claim_fields(claim_id)).get("case_email") or "").strip()
    except Exception:  # noqa: BLE001
        was = ""
    correcting = bool(was) and was.lower() != email.lower()
    if "mail_credentials" not in pending and not correcting:
        return {}

    pwd = ""
    hint = _PWD_HINT.search(t)
    if hint:
        pwd = hint.group(1)
    else:
        # No "password:" label - take the other word on the line, which is how people send it.
        rest = [w for w in _re.split(r"[\s,;\n]+", t.replace(email, " ")) if len(w) >= 4]
        pwd = rest[0] if rest else ""
    if not pwd:
        return {}

    saved = True
    try:
        import biz_nidaan_buckets as _bk
        who = "complainant (WhatsApp)"
        r1 = await _bk.set_field(claim_id, "case_email", email, actor=who)
        r2 = await _bk.set_field(claim_id, "case_email_password", pwd, actor=who)
        # These two never lock (biz_nidaan_buckets.NEVER_LOCK): they are not findings somebody
        # signed off, they are how we write to the insurer, and they must stay correctable at the
        # point they are used. So a refusal here means something genuinely went wrong.
        saved = bool(r1.get("ok")) and bool(r2.get("ok"))
    except Exception as e:  # noqa: BLE001
        logger.warning("could not save the case email on claim %s: %s", claim_id, e)
        saved = False

    if saved:
        try:
            import biz_nidaan_doc_checklist as _ck2
            await _ck2.set_doc_received(claim_id, "mail_credentials", True,
                                        by="complainant (WhatsApp)")
        except Exception:
            pass
    if saved:
        # The password is on the claim now; the chat copy of the message keeps everything but it,
        # so it is not in the inbox, its preview, or the history the AI reads later.
        try:
            async with aiosqlite.connect(DB_PATH) as _c:
                await _c.execute(
                    "UPDATE nidaan_wa_messages SET body=REPLACE(body, ?, '••••••••') WHERE msisdn=? "
                    "AND direction='in' AND INSTR(body, ?)>0 AND INSTR(body, ?)>0 "
                    "AND created_at >= datetime('now','-1 day')", (pwd, msisdn, pwd, email))
                await _c.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("could not hide the password in the chat copy (claim %s): %s", claim_id, e)
    # The password never goes into the summary line - a claim's own timeline is read by everybody.
    if saved and correcting:
        note = ("Complainant CORRECTED the case email on WhatsApp — now %s (it was %s). "
                "The password was sent again too and has been updated; it is not shown here."
                % (email, was))
    elif saved:
        note = ("Complainant sent the case email (%s) and its password on WhatsApp — saved "
                "on the claim, password hidden" % email)
    else:
        note = ("Complainant sent the case email (%s) and a password on WhatsApp, but it could "
                "not be saved — please put them on the claim by hand." % email)
    await _activity(claim_id, "case_email", note, direction="in")
    try:
        with _wa.sending_as("critical"):
            await _wa.send_text(msisdn, _GOT_IT.get(lang, _GOT_IT["hinglish"]))
        await _touch_outbound(msisdn)
    except Exception:
        pass
    return {"ok": True, "captured": True, "action": "case_email_saved"}


async def handle_inbound_text(msisdn: str, text: str) -> dict:
    """A complainant sent text. READ IT FIRST, then respond like a person would.

    Previously this ignored the message entirely and re-sent welcome + the same document ask
    every single time. Now the conversation brain decides: answer the question, continue the
    guided document flow, decline once (abuse / off-topic), or hand off to a human."""
    import biz_nidaan_wa_auth as _auth
    import biz_nidaan_wa_brain as _brain
    import biz_nidaan_wa_charter as _charter
    import biz_nidaan_wa_identity as _ident

    claim = await _claim_for_msisdn(msisdn)
    claim_id = claim["claim_id"] if claim else None
    lang = await _lang(msisdn)

    # Who is this NUMBER likely to be? A record match makes them a candidate, not an authenticated
    # person — numbers get recycled and phones get shared, and what sits behind these roles is
    # other people's claims. Nothing private is released until they enter a code we email to the
    # address on the account.
    ident = await _ident.resolve(msisdn)
    sess = await _auth.session(msisdn)
    verified = bool(sess)
    sc = await _ident.safe_context(ident, verified=verified)

    # Under human takeover the bot must not talk over the staffer - but the customer must not be
    # left talking to nobody either. Founder, 1 Oct: tell them our office hours and that someone
    # will reach out; at most three times while they wait, then silent (biz_nidaan_bot_hold).
    if await _human_holds(msisdn, claim_id):
        import biz_nidaan_bot_hold as _hold
        _n_hold, _txt = await _hold.message_for("wa:" + msisdn, lang)
        if _txt:
            with _wa.sending_as("hold"):          # not an answer - the sweep still sees the wait
                await _wa.send_text(msisdn, _txt)
            await _activity(claim_id, "wa_ack", "Told them our office hours and that our team will "
                            "reach out (%d of %d) - the case is with a person." % (_n_hold, _hold.MAX_HOLDS))
        return {"ok": True, "action": "human_takeover_ack"}

    # ── identity verification ────────────────────────────────────────────────
    _t = (text or "").strip()
    # 1. They sent the code we emailed them.
    if not verified:
        _code = _auth.looks_like_code(_t)
        if _code:
            res = await _auth.try_verify(msisdn, _code, lang)
            await _wa.send_text(msisdn, res.get("message") or "")
            await _touch_outbound(msisdn)
            await _activity(claim_id, "wa_verify",
                            "Identity verified on WhatsApp" if res.get("ok")
                            else f"Verification failed ({res.get('reason')})", direction="in")
            if res.get("ok"):
                # Verified mid-conversation: pick straight up where they left off rather than
                # making them repeat themselves.
                if claim:
                    await _link_contact(msisdn, claim)
                    await ask_next(claim_id, msisdn)
                return {"ok": True, "action": "verified"}
            return {"ok": True, "action": "verify_failed"}

        # 2. They asked for a code, or asked something only a verified person may hear.
        if _wants_code(_t) or (ident.get("role") != "unknown" and _asks_private(_t)):
            res = await _auth.request_code(msisdn, ident, lang)
            await _wa.send_text(msisdn, res.get("message") or "")
            await _touch_outbound(msisdn)
            await _activity(claim_id, "wa_verify_sent",
                            f"Verification code emailed ({res.get('masked') or res.get('reason')})")
            return {"ok": True, "action": "verify_requested"}

    # Nothing we can tie to a person → let the caller run the prospect/sales reply.
    if not claim and ident.get("role") == "unknown":
        return {"ok": False, "error": "no_claim"}

    if claim:
        await _link_contact(msisdn, claim)
        # The case email account, if that is what they just sent. Checked BEFORE the brain reads
        # the message: this is the one reply that is not a question, and it has to land on the
        # claim rather than be answered.
        got = await _capture_case_email(claim_id, text, lang, msisdn)
        if got.get("captured"):
            return got

    # ── the charter ─────────────────────────────────────────────────────────
    # IS THIS A PERSON? Asked before the model, because reaching the AI is the expensive part and
    # an automatic reply is what makes flooding worth doing. The message is still logged above
    # and staff are still told; only the bot stops answering.
    _flood = await _charter.flood(msisdn)
    if not _flood.get("ok"):
        await _activity(claim_id, "wa_flood",
                        "Stopped replying — %s" % _flood.get("reason", "too much traffic"))
        # Told once, not per message: an alert per message would simply relay the flood.
        if not await _recent_outbound(msisdn, 180):
            await _handoff_to_support(claim, msisdn, text, lang,
                                      reason="unusual traffic: %s" % _flood.get("reason", ""),
                                      identity=ident)
            await _touch_outbound(msisdn)
        return {"ok": True, "action": "flood_guard", "reason": _flood.get("reason")}

    # WHAT MAY THIS CONVERSATION RECEIVE? Past document collection the bot is not a document
    # collector any more, and nothing about the claim goes out over WhatsApp - except an answer
    # to a question we asked (founder: "after consolidation we also have questions/queries ...
    # those communication should not be restricted").
    _st = await _charter.stance(claim_id, verified=verified)
    if _st["stance"] == _charter.STANCE_QUIET and claim:
        # There IS a claim and they are verified, but the bot has no business discussing it.
        # Acknowledge and put a person on it rather than going silent - silence is what
        # dead-ended the conversation the founder complained about on 23 Sep.
        await _activity(claim_id, "wa_inbound", f"Customer: {(text or '')[:120]}", direction="in")
        # Office hours, someone will reach out - at most three times, then silent. Staff hear about
        # the wait ONCE, when it starts; the unanswered sweep says the rest (two notices in all).
        import biz_nidaan_bot_hold as _hold
        _n_hold, _txt = await _hold.message_for("wa:" + msisdn, lang)
        if _n_hold == 1:
            # The start of a wait is this chat's first of two staff notices - in office hours
            # only; at night the customer has been told when we open and the sweep raises it then.
            # Information for the claim's own people - in office hours, once per wait. It does NOT
            # use up the chat's two notices: those are the handover alert and the 3-hour
            # escalation (re-review, 1 Oct - spending one here left the super-admins unwarned).
            if await _n.is_within_business_hours():
                await _tell_staff_inbound(claim_id, msisdn, text)
        await _handoff_to_support(claim, msisdn, text, lang, reason=_st["reason"], identity=ident,
                                  alert=(_n_hold == 1))
        if _txt:
            # Last, so the bot's message is the last thing the customer reads. Labelled 'hold': it
            # is not an answer, so the unanswered sweep still sees that a person owes them one.
            with _wa.sending_as("hold"):
                await _wa.send_text(msisdn, _txt)
        await _activity(claim_id, "wa_charter", "The bot did not discuss the claim — %s" % _st["reason"])
        return {"ok": True, "action": "charter_quiet", "reason": _st["reason"]}

    # WHAT WAS ALREADY SAID. `decide()` has always accepted history and this call never passed
    # any, so every message was answered as if it were the first one. The founder sent "Hi",
    # "Hi", "Hello" on 23 Sep and was introduced to the company three times, in three different
    # wordings - the model was writing a fresh greeting each time because, as far as it could
    # tell, it had never met him. A person who has just been told who we are does not need
    # telling again; they need answering.
    # WHEN SHOULD WE REMIND THEM? The complainant picks the moment (founder, 29 Sep). Only where
    # documents may be asked for, and only when switched on. None means "this message is not
    # about that" and the conversation carries on exactly as before; so does any error here.
    if claim and _st.get("may_send_docs"):
        try:
            import biz_nidaan_wa_remind as _remind
            _r = await _remind.handle(msisdn, claim_id, text, lang) \
                if await _remind.enabled() else None
        except Exception as e:  # noqa: BLE001
            logger.warning("remind-time handling failed, answering normally: %s", e)
            _r = None
        if _r:
            await _activity(claim_id, "wa_inbound", f"Customer: {(text or '')[:120]}",
                            direction="in")
            await _tell_staff_inbound(claim_id, msisdn, text)
            await _wa.send_text(msisdn, _r)
            await _touch_outbound(msisdn)
            await _activity(claim_id, "wa_remind", f"Reminder time: {_r[:120]}")
            return {"ok": True, "action": "remind_time"}

    d = await _brain.decide(text, lang, history=await _recent_history(msisdn),
                            context=sc.get("text", ""),
                            handoff_only=bool(sc.get("handoff_only")),
                            public_mode=not verified)
    action, reply = d.get("action"), d.get("reply") or ""
    # If they asked to switch language, REMEMBER it — every later reply, document ask and
    # reminder now uses it, until they ask to change again.
    if d.get("set_lang") and d["set_lang"] != lang:
        lang = d["set_lang"]
        try:
            import biz_nidaan_wa_flow as _flow
            await _flow.upsert_contact(msisdn, language=lang)
            await _activity(claim_id, "wa_lang", f"Customer switched language → {lang}")
        except Exception:
            pass
    await _activity(claim_id, "wa_inbound", f"Customer: {(text or '')[:120]}", direction="in")
    await _tell_staff_inbound(claim_id, msisdn, text)

    if action == "continue_docs" and claim:
        # Only where the charter allows documents. The model can be talked into "send me your
        # papers" on a claim that finished collecting months ago.
        if not _st.get("may_send_docs"):
            await _activity(claim_id, "wa_charter",
                            "Did not ask for documents — %s" % _st["reason"])
            return {"ok": True, "action": "charter_quiet", "reason": _st["reason"]}
        # They're ready to send — always re-state the exact document (force past the throttle).
        return await start_or_continue(msisdn, force_ask=True)

    if action == "refuse":
        # Decline ONCE, then stay quiet until they ask something sensible (a sensible question
        # comes back as "answer", not "refuse", so it is never muted).
        if await _recent_outbound(msisdn, 180):
            return {"ok": True, "action": "refuse", "muted": True}
        # Always our own copy here — a decline must be consistently polite and in THEIR language
        # (the model sometimes answers a Hinglish message in English).
        await _wa.send_text(msisdn, _brain.refusal_text(lang))
        await _touch_outbound(msisdn)
        await _activity(claim_id, "wa_refused", f"Declined off-scope/abusive message ({d.get('reason','')})")
        return {"ok": True, "action": "refuse"}

    if action == "handoff":
        _hand = reply or _brain.handoff_text(lang)
        if not verified:
            _hand, _b = await _auth.guard_public_reply(msisdn, _hand, lang)
        await _wa.send_text(msisdn, _hand)
        await _touch_outbound(msisdn)
        await _handoff_to_support(claim, msisdn, text, lang, reason=d.get("reason", ""),
                                  identity=ident)
        return {"ok": True, "action": "handoff"}

    # action == "answer" — a natural reply, then (for a claim) a gentle throttled document nudge.
    # Last line of defence: an unverified conversation must not receive private detail even if the
    # model was talked into writing some. A blocked reply is replaced, not trimmed.
    if not verified:
        reply, _blocked = await _auth.guard_public_reply(msisdn, reply, lang)
        if _blocked:
            await _activity(claim_id, "wa_guard", f"Blocked a reply containing {_blocked} (unverified)")
    await _wa.send_text(msisdn, reply)
    await _touch_outbound(msisdn)
    await _activity(claim_id, "wa_answer", f"Answered: {reply[:120]}")
    if not claim:
        return {"ok": True, "action": "answer", "role": ident.get("role")}
    if _st.get("may_send_docs"):
        await ask_next(claim_id, msisdn)      # throttled — won't repeat if just asked
    return {"ok": True, "action": "answer"}


# Words that mean "tell me about MY case/account" — the point where public mode is not enough.
# Deliberately broad: over-triggering costs one verification step, under-triggering costs a leak.
_PRIVATE_WORDS = (
    "my claim", "mera claim", "meri claim", "claim status", "status", "kya hua", "update",
    "kahan tak", "kitna", "how much", "settlement", "paisa", "payment", "refund", "policy",
    "my case", "mera case", "document", "kagaz", "papers", "account", "subscription", "plan",
    "branch", "commission", "payout", "leads", "customers", "mere customer", "मेरा", "स्थिति",
    "क्लेम", "भुगतान", "खाता",
)
_CODE_WORDS = ("code", "otp", "verify", "verification", "kod", "कोड", "ओटीपी")


def _wants_code(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(w == t or (w in t and len(t) <= 40) for w in _CODE_WORDS)


def _asks_private(text: str) -> bool:
    """Would answering this need something only a verified person may hear?"""
    t = (text or "").lower()
    return any(w in t for w in _PRIVATE_WORDS)


async def _handoff_to_support(claim, msisdn: str, text: str, lang: str, reason: str = "",
                              identity: dict | None = None, alert: bool = True) -> None:
    """Open a Support thread in ops with the WhatsApp message, escalate it to a human, and (for a
    claim) mute the bot so it never talks over the person taking it. Works for a subscriber or
    branch too, where there is no single claim to attach."""
    claim = claim or {}
    ident = identity or {}
    claim_id = claim.get("claim_id")
    try:
        who = (claim.get("complainant_name") or claim.get("insured_name")
               or ident.get("name") or "WhatsApp customer")
        # One WhatsApp number = one open conversation. Every handoff used to open a NEW thread,
        # so a customer who asked twice appeared twice in the support inbox. Safe to match on the
        # msisdn here: WhatsApp proves number possession.
        _open = await _n.find_open_support_thread(contact=msisdn, channel="whatsapp")
        if _open:
            tid = _open.get("thread_id")
        else:
            th = await _n.create_support_thread(
                name=who, contact=msisdn,
                account_id=(claim.get("account_id") or ident.get("account_id")),
                channel="whatsapp", lang=lang)
            tid = th.get("thread_id")
        # Carry the WhatsApp conversation into the thread so staff have the context.
        await _n.add_support_message(tid, "customer", (text or "")[:2000])
        _ref = f"Claim #NP-{claim_id:04d}." if claim_id else \
            f"Role: {ident.get('role') or 'unknown'}{(' ' + ident.get('branch_code')) if ident.get('branch_code') else ''}."
        await _n.add_support_message(
            tid, "ai", f"[auto] Handed off from the WhatsApp bot — {reason or 'needs a human'}. "
                       f"{_ref} Reply to the customer on WhatsApp {msisdn}.")
        await _n.set_support_status(tid, "escalated")
        # Mute the bot on the CONVERSATION as well as the claim. Without this a prospect or a
        # branch (no claim to hang takeover off) kept getting AI replies after being handed over.
        await pause_bot(msisdn, by="support")
        if claim_id:
            await _set_takeover(claim_id, by="support")
        await _activity(claim_id, "wa_handoff", f"Passed to the support team (chat #{tid}) for a person to answer — {reason or 'needs a person'}")
        if alert:   # once per wait - every further message used to alert again
            try:
                import biz_nidaan_notifications as _nnot
                await _nnot.on_support_escalated(tid)
            except Exception:
                pass
    except Exception as e:  # noqa: BLE001
        logger.warning("WhatsApp support handoff failed for claim %s: %s", claim_id, e)


async def _touch_outbound(msisdn: str) -> None:
    """Record that we just messaged this number (drives the generic throttle)."""
    try:
        import biz_nidaan_wa_flow as _flow
        await _flow.upsert_contact(msisdn, mark_outbound=True)
    except Exception:
        pass


async def _activity(claim_id, kind: str, summary: str, *, channel: str = "whatsapp", direction: str = "out") -> None:
    if not claim_id:
        return   # a subscriber/branch conversation with no claim attached — nothing to pin it to
    try:
        await _n.record_claim_activity(claim_id, kind, channel=channel, direction=direction,
                                       actor=("claimant" if direction == "in" else "bot"), summary=summary)
    except Exception:
        pass
