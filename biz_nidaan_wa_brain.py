"""
NidaanPartner WhatsApp — CONVERSATION BRAIN.

The guided doc-collection flow used to reply to EVERY inbound message with the same welcome +
document ask, no matter what the person actually said. This module reads the message first and
decides what a human would do:

  answer         → a short, natural reply from what we're allowed to say
  continue_docs  → they're ready to send the document; run the guided flow
  refuse         → abusive / clearly out-of-scope; decline ONCE, politely, then stay quiet
  handoff        → needs a human → open a Support thread (ops → Support) and hand over

ANTI-HALLUCINATION (locked policy): the AI may explain the SERVICE. It must never state this
claim's status/stage/timeline, give legal opinion, predict an outcome, quote amounts, dates or
policy specifics, or invent which documents are needed — those come from templates/DB only.
Anything needing claim-specific facts is a `handoff`, never a guess.
"""
from __future__ import annotations

import os
import json
import logging

logger = logging.getLogger("nidaan.wa.brain")

# What the assistant is allowed to explain, in its own words.
SERVICE_FACTS = """
NidaanPartner (nidaanpartner.com) helps people whose insurance claim was REJECTED, delayed,
short-paid or disputed. Nidaan – The Legal Consultants LLP is the legal firm behind it.
- We handle: health/mediclaim, life, accident, motor and other general insurance claims.
- How it works: you share the claim papers on WhatsApp or the dashboard, our team reviews the
  case, tells you honestly whether it can be fought, and then pursues it with the insurer.
- We work in Hindi, Hinglish and English — the customer picks.
- We ask for documents one at a time so it stays simple.
- A paid expert review is available; the team confirms any fee before anything is charged.
"""

_ACTIONS = ("answer", "continue_docs", "refuse", "handoff")

_SYSTEM = """You are the WhatsApp assistant for NidaanPartner, an Indian insurance-claim support
service. You are talking to a real customer on WhatsApp. Reply the way a warm, competent Indian
support person would: short (1-3 sentences), natural, no corporate padding, no bullet lists.

WHAT YOU KNOW (the ONLY things you may assert):
{facts}

WHO YOU ARE TALKING TO (verified by their WhatsApp number — treat as authenticated):
{context}

HARD RULES — breaking these is a serious failure:
- You may tell them what is in "WHO YOU ARE TALKING TO" above, in your own warm words. That is
  already written in the wording we are willing to share.
- NEVER go beyond it: no legal advice, no predicting whether a claim will succeed, no settlement
  amounts, no policy numbers, no internal notes or colleague names, no dates we haven't given you.
- If they ask something about their case that is NOT covered above, choose "handoff".
- If the block above is empty, you do not know who they are — never discuss any specific case;
  help them generally and choose "handoff" if they push for case details.
- Do not invent anything.

Decide ONE action:
- "continue_docs": they are ready to send / are asking which document to send / said yes-ok-send.
- "answer": a general question about the service, OR a question about their own case that the
  verified block above already answers.
- "refuse": abusive, sexual, threatening, spam, or clearly nothing to do with insurance claims.
- "handoff": they want a human, are unhappy, ask for case details not covered above, or anything
  you cannot answer safely.

LANGUAGE — this matters:
- The customer's current language is "{lang}". Write your reply in THAT language unless they ask
  to change it.
- If they ask to talk in a specific language ("can you talk in english", "hindi me baat karo",
  "English please"), set "set_lang" to "en", "hi" or "hinglish" AND write the reply in that new
  language. Otherwise set "set_lang" to "".
- "hi" = Hindi in Devanagari script. "hinglish" = Hindi written in Roman/English letters.
  "en" = plain English. Never mix scripts inside one reply.

Reply STRICTLY as JSON:
{{"action":"<one of continue_docs|answer|refuse|handoff>","reply":"<the message to send, in the
customer's language; empty string if action is continue_docs>","set_lang":"<en|hi|hinglish or
empty>","reason":"<3-6 words>"}}
"""

_FALLBACK = {
    "hinglish": "Main aapki baat samajh gaya. Hamari team aapse jaldi baat karegi. 🙏",
    "hi": "मैं आपकी बात समझ गया। हमारी टीम आपसे जल्दी बात करेगी। 🙏",
    "en": "I've noted your message. Our team will get back to you shortly. 🙏",
}
_REFUSE = {
    "hinglish": ("Maaf kijiye — main sirf insurance claim se judi baat me madad kar sakta hoon. "
                 "Apne claim ke baare me poochhiye, main zaroor help karunga. 🙏"),
    "hi": ("माफ़ कीजिए — मैं सिर्फ़ इंश्योरेंस क्लेम से जुड़ी बात में मदद कर सकता हूँ। "
           "अपने क्लेम के बारे में पूछिए, मैं ज़रूर मदद करूँगा। 🙏"),
    "en": ("Sorry — I can only help with insurance-claim matters. Ask me about your claim and "
           "I'll gladly help. 🙏"),
}
_HANDOFF = {
    "hinglish": "Main aapko hamari team se jod raha hoon — wo jaldi hi aapse yahin baat karenge. 🙏",
    "hi": "मैं आपको हमारी टीम से जोड़ रहा हूँ — वे जल्दी ही आपसे यहीं बात करेंगे। 🙏",
    "en": "I'm connecting you with our team — they'll reply to you right here shortly. 🙏",
}


def refusal_text(lang: str) -> str:
    return _REFUSE.get(lang, _REFUSE["hinglish"])


def handoff_text(lang: str) -> str:
    return _HANDOFF.get(lang, _HANDOFF["hinglish"])


async def decide(text: str, lang: str = "hinglish", *, history: str = "",
                 context: str = "", handoff_only: bool = False) -> dict:
    """Classify the inbound message and draft a natural reply. Never raises.

    Fail-safe: if the AI is unavailable or returns junk we HAND OFF to a human rather than
    guessing — silence or a wrong answer on a claim is worse than a person picking it up."""
    t = (text or "").strip()
    if not t:
        return {"action": "handoff", "reply": handoff_text(lang), "reason": "empty message"}
    try:
        import biz_ai
        client = biz_ai._get_client()
        if not client:
            return {"action": "handoff", "reply": handoff_text(lang), "reason": "no ai"}
        from google.genai import types as gt
        ctx = context or "(we do not know who this is yet)"
        if handoff_only:
            ctx += ("\nIMPORTANT: one of their cases has reached an outcome that a person must "
                    "deliver. If they ask about that case, choose \"handoff\" — do not narrate it.")
        prompt = _SYSTEM.format(facts=SERVICE_FACTS, lang=lang, context=ctx) + \
            (f"\n\nRecent conversation:\n{history}\n" if history else "") + \
            f"\n\nCustomer's message: {t}"
        resp = await client.aio.models.generate_content(
            model=os.getenv("WA_BRAIN_MODEL", "gemini-2.5-flash"),
            contents=[prompt],
            config=gt.GenerateContentConfig(response_mime_type="application/json"))
        v = json.loads(resp.text) or {}
        action = str(v.get("action", "")).strip().lower()
        if action not in _ACTIONS:
            action = "handoff"
        reply = str(v.get("reply", "")).strip()[:900]
        if action == "answer" and not reply:
            action, reply = "handoff", handoff_text(lang)
        if action == "refuse" and not reply:
            reply = refusal_text(lang)
        set_lang = str(v.get("set_lang", "")).strip().lower()
        if set_lang not in ("en", "hi", "hinglish"):
            set_lang = ""
        if action == "handoff" and not reply:
            reply = handoff_text(set_lang or lang)
        return {"action": action, "reply": reply, "set_lang": set_lang,
                "reason": str(v.get("reason", ""))[:60]}
    except Exception as e:  # noqa: BLE001
        logger.info("wa brain decide failed (handing off): %s", e)
        return {"action": "handoff", "reply": handoff_text(lang), "set_lang": "", "reason": "ai error"}
