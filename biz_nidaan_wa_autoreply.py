# -*- coding: utf-8 -*-
"""Was that WhatsApp message written by a person, or by their phone?

Claim #245, 30 Sep: our "claim registered" message went to the complainant's number, and within
seconds two AUTOMATIC replies came back - a WhatsApp Business greeting ("this message is sent to
you from New India Insurance, Badwani ...") and an away message ("Thank you for your message.
We're unavailable right now"). The bot answered each one, twice, to a machine; and the contact
proof counted the away message as "the complainant wrote to us from this number" - nobody had.

A message is treated as automatic when:
  * it reads like an away message or a business greeting, or
  * the same text has come from this number before (greetings repeat word for word).

Not timing: a person with WhatsApp open answers within seconds too, and treating them as their
phone would leave a real question unanswered. Unsure always means "a person".

What happens to an automatic message: it is kept and shown on the claim, plainly labelled; the bot
does not answer it; it is not proof of the mobile. A person replying a minute later is treated
normally.
"""
from __future__ import annotations

import logging
import re

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.wa.autoreply")
DB_PATH = db.DB_PATH

_PHRASES = re.compile(
    r"(unavailable right now|will respond as soon as|will (get back|reply) to you|"
    r"thank(s| you) for (your message|contacting|reaching out|messaging)|"
    r"currently (away|unavailable|out of office)|out of office|auto[- ]?reply|automated (message|reply)|"
    r"our (office|business) hours|we are closed|"
    r"से भेजा गया है|अभी उपलब्ध नहीं|जल्द ही (जवाब|संपर्क)|संपर्क करने के लिए धन्यवाद)", re.I)


def reads_automatic(text: str) -> bool:
    return bool(_PHRASES.search(text or ""))


async def looks_automatic(msisdn: str, text: str) -> bool:
    """True when this inbound message is most likely the phone answering, not a person."""
    if reads_automatic(text):
        return True
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            body = (text or "").strip()
            if body:
                # Earlier copies of the same words from this number (this message itself is
                # already logged, so more than one row means it has come before).
                n = (await (await c.execute(
                    "SELECT COUNT(*) FROM nidaan_wa_messages WHERE msisdn=? AND direction='in' "
                    "AND TRIM(COALESCE(body,''))=?", (msisdn, body))).fetchone())[0]
                if n > 1:
                    return True
        return False
    except Exception as e:  # noqa: BLE001 - unsure means "a person": the bot answers as before
        logger.info("auto-reply check failed for %s: %s", msisdn[-4:], e)
        return False


async def note(msisdn: str, text: str) -> None:
    """Put the automatic message on the claim's timeline, in words staff understand."""
    try:
        import biz_nidaan_wa_orchestrator as _o
        claim = await _o._claim_for_msisdn(msisdn)
        if claim:
            import biz_nidaan as _n
            await _n.record_claim_activity(
                claim["claim_id"], "wa_auto_reply", channel="whatsapp", direction="in",
                actor="claimant",
                summary="Automatic reply from the complainant's phone (not a person, so the bot "
                        "did not answer and it does not confirm the number): %s" % (text or "")[:140])
    except Exception as e:  # noqa: BLE001
        logger.info("auto-reply note failed: %s", e)
