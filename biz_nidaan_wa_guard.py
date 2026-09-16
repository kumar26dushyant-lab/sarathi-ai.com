# =============================================================================
#  biz_nidaan_wa_guard.py — how often we are allowed to speak first
# =============================================================================
#
#  The founder's rule, in his words: "we no need to bombardment of messages and
#  also we need to provide user to stop receiving messages option to safeguard
#  our whatsapp number" — and then the numbers: "2 messages are enough and 5 a
#  week per complainant, but for only reasonable messages not unnecessary
#  messages."
#
#  So this module answers ONE question, at the one place every Nidaan WhatsApp
#  send passes through (`biz_nidaan_whatsapp._post`): may we send this, now, to
#  this person — and does it need the STOP footer?
#
#  What is capped and what is not, and why:
#
#    human        a staff member typing a reply to a person      NEVER capped
#                 A colleague answering someone is not bombardment. Capping it
#                 would mean a complainant asks a question and we sit silent.
#
#    conversation the bot replying inside the 24h window the      burst guard only
#                 complainant opened by messaging US
#                 Document collection is a back-and-forth THEY started: "here is
#                 the discharge summary" → "got it, now the policy copy". Two a
#                 day would break the founder's other priority (a strong
#                 document-collection process). A burst guard still stands in the
#                 way of a runaway loop, which is what actually endangers our
#                 number.
#
#    initiated    us speaking first — journey messages, reminders  2/day, 5/week
#                 to someone not in session, campaign sends
#                 This is the bombardment the founder means, and the only class
#                 the caps apply to.
#
#    consent      the STOP/START confirmation itself               always sent
#                 Someone who just said STOP must still be told it worked.
#
#    critical     money and access — a failed payment, an          not capped,
#                 authorisation someone is waiting on              but counted
#
#  Business contacts (staff, branch partners) are not capped: these are working
#  messages between colleagues, not marketing to a customer.
#
#  FAIL-OPEN, deliberately: if this module cannot read the database it lets the
#  message through. A guard that silences the platform when a query fails is a
#  worse outage than one extra message. STOP is still enforced by the callers
#  and re-checked here whenever the read succeeds.
# =============================================================================
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.wa.guard")

DB_PATH = db.DB_PATH

# ── the founder's numbers ────────────────────────────────────────────────────
CAP_DAY = 2          # "2 messages are enough"
CAP_WEEK = 5         # "and 5 a week per complainant"
FOOTER_EVERY = 3     # the STOP line rides along every 3rd message we start
CONV_BURST_DAY = 12  # runaway-loop guard on conversation replies (not a policy cap)

_UNCAPPED_ROLES = ("staff", "branch")
_NEVER_HELD = ("human", "consent")


def _s(v) -> str:
    return str(v or "").strip().lower()


# ── the STOP line ────────────────────────────────────────────────────────────
# It says the CONSEQUENCE (what they stop getting), not just the word. "Reply
# STOP" on its own reads like fine print; a person deserves to know that the
# claim updates are what goes quiet — and that we will still reach them another
# way, so stopping WhatsApp never means losing their claim.
_FOOTER = {
    "en": ("\n\n— Reply STOP to stop these WhatsApp updates about your claim. "
           "You would then get no claim updates here; we would still call or email you. "
           "Reply START any time to turn them back on."),
    "hi": ("\n\n— ये WhatsApp अपडेट बंद करने के लिए STOP लिखकर भेजें। "
           "फिर आपके क्लेम के अपडेट यहाँ नहीं आएँगे; हम कॉल या ईमेल से संपर्क करते रहेंगे। "
           "दोबारा चालू करने के लिए कभी भी START भेजें।"),
    "hinglish": ("\n\n— Ye WhatsApp updates band karne ke liye STOP bhejein. "
                 "Phir aapke claim ke updates yahan nahi aayenge; hum call ya email se "
                 "sampark karte rahenge. Dobara chalu karne ke liye kabhi bhi START bhejein."),
}


def footer_text(lang: str) -> str:
    return _FOOTER.get(_s(lang) or "hinglish", _FOOTER["hinglish"])


async def _contact(msisdn: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT msisdn, claim_id, language, status, verified_role, last_inbound_at "
            "FROM nidaan_wa_contacts WHERE msisdn=?", (msisdn,))).fetchone()
    return dict(r) if r else {}


async def _counts(msisdn: str) -> dict:
    """What we have already started with this person. Only messages that actually went out
    count — one we never managed to deliver did not use up their patience."""
    async with aiosqlite.connect(DB_PATH) as c:
        row = await (await c.execute(
            """SELECT
                 COALESCE(SUM(send_class='initiated'   AND created_at >= datetime('now','-1 day')),0)  AS day_init,
                 COALESCE(SUM(send_class='initiated'   AND created_at >= datetime('now','-7 day')),0)  AS week_init,
                 COALESCE(SUM(send_class='conversation' AND created_at >= datetime('now','-1 day')),0) AS day_conv,
                 COALESCE(SUM(send_class='initiated'),0)                                               AS ever_init
               FROM nidaan_wa_messages
               WHERE msisdn=? AND direction='out' AND status='sent'""", (msisdn,))).fetchone()
    return {"day_init": int(row[0] or 0), "week_init": int(row[1] or 0),
            "day_conv": int(row[2] or 0), "ever_init": int(row[3] or 0)}


def _in_session(contact: dict) -> bool:
    """True if they messaged US in the last 24h — i.e. this is their conversation, not ours."""
    from datetime import datetime
    last = str(contact.get("last_inbound_at") or "")[:19]
    if not last:
        return False
    try:
        return (datetime.utcnow() - datetime.strptime(last, "%Y-%m-%d %H:%M:%S")).total_seconds() < 24 * 3600
    except Exception:
        return False


def classify(sender: str, *, in_session: bool, role: str = "") -> str:
    s = _s(sender)
    if s in ("human", "consent", "critical"):
        return s
    if _s(role) in _UNCAPPED_ROLES:
        return "business"
    if s == "campaign":                       # a blast is us speaking first, session or not
        return "initiated"
    return "conversation" if in_session else "initiated"


async def decide(msisdn: str, msg_type: str, sender: str) -> dict:
    """{send, cls, reason, footer, claim_id} — the whole decision, in one call."""
    out = {"send": True, "cls": "initiated", "reason": "", "footer": "", "claim_id": None}
    msisdn = (msisdn or "").strip()
    if not msisdn:
        return out
    try:
        ct = await _contact(msisdn)
    except Exception as e:  # noqa: BLE001 — fail open: never silence the platform on a read error
        logger.warning("wa guard could not read contact %s (allowing send): %s", msisdn, e)
        return out

    cls = classify(sender, in_session=_in_session(ct), role=ct.get("verified_role") or "")
    out["cls"] = cls
    out["claim_id"] = ct.get("claim_id")

    # Someone who said STOP hears from us only about the stopping itself.
    if _s(ct.get("status")) == "stopped" and cls not in ("consent",):
        out["send"] = False
        out["reason"] = "opted_out"
        return out

    if cls in _NEVER_HELD or cls == "business":
        return out

    try:
        n = await _counts(msisdn)
    except Exception as e:  # noqa: BLE001
        logger.warning("wa guard could not count sends for %s (allowing): %s", msisdn, e)
        return out

    if cls == "conversation":
        if n["day_conv"] >= CONV_BURST_DAY:
            out["send"] = False
            out["reason"] = "conversation_burst_guard"
        return out

    if cls == "critical":
        return out                              # counted by its own class, never held

    if n["day_init"] >= CAP_DAY:
        out["send"] = False
        out["reason"] = "cap_day"
        return out
    if n["week_init"] >= CAP_WEEK:
        out["send"] = False
        out["reason"] = "cap_week"
        return out

    # The STOP line rides along every 3rd message we start — and the very first one, so nobody
    # ever learns about it only after the fourth. Templates carry their own approved wording and
    # cannot be appended to, so it goes on free-form text.
    if _s(msg_type) == "text" and n["ever_init"] % FOOTER_EVERY == 0:
        out["footer"] = footer_text(ct.get("language") or "hinglish")
    return out


async def note_held(msisdn: str, claim_id: Optional[int], reason: str, body: str) -> None:
    """A message we chose NOT to send is still something staff must be able to see, so it goes
    on the claim's own timeline. It is deliberately NOT written into the WhatsApp thread: that
    thread is what was actually exchanged, and a held message was not."""
    why = {"cap_day": "already had 2 messages from us today",
           "cap_week": "already had 5 messages from us this week",
           "opted_out": "replied STOP — we must not message them",
           "conversation_burst_guard": "too many automated replies in 24h (loop guard)"}.get(
        reason, reason)
    logger.info("wa held (%s) to %s: %s", reason, msisdn, (body or "")[:80])
    if not claim_id:
        return
    try:
        import biz_nidaan_wa_orchestrator as _orch
        await _orch._activity(claim_id, "wa_held",
                              summary="WhatsApp message held — %s" % why, direction="out")
    except Exception as e:  # noqa: BLE001
        logger.info("could not record a held WhatsApp message on claim %s: %s", claim_id, e)


async def summary(msisdn: str) -> dict:
    """What a screen needs to show about this number: stopped? how much have we used up?"""
    try:
        ct = await _contact(msisdn)
        n = await _counts(msisdn)
    except Exception:  # noqa: BLE001
        return {}
    return {"stopped": _s(ct.get("status")) == "stopped",
            "language": ct.get("language") or "hinglish",
            "today": n["day_init"], "week": n["week_init"],
            "cap_day": CAP_DAY, "cap_week": CAP_WEEK,
            "left_today": max(0, CAP_DAY - n["day_init"]),
            "left_week": max(0, CAP_WEEK - n["week_init"])}
