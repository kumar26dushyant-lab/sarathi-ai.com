"""
biz_nidaan_wa_flow.py — WhatsApp onboarding conversation logic for Nidaan.

Handles the language-selection + welcome/save-number + consent opt-in flow,
trilingual (English / हिंदी / मराठी). This module is PURE LOGIC + TEMPLATES:
- It generates the messages to send.
- It decides what to do next given the inbound text and the contact's state.
It does NOT touch the DB or send anything — the inbound handler calls
`decide_onboarding_action()` and executes the returned action. This keeps it
unit-testable in isolation (Phase 2 discipline, mirrors Phase 1).

Design rules (from NIDAAN_WHATSAPP_JOURNEY_SPEC.md):
- First contact gets the welcome in ALL THREE languages at once, so a
  non-English speaker can still understand how to pick (reply 1/2/3).
- "change language" (in any language) re-sends the picker, anytime.
- Advisor-managed customers must opt-in (YES) before transactional messages;
  the consent line names BOTH advisor name AND firm name.
- Everything here is template-driven — zero AI, zero free-prose (anti-hallucination).
"""
from __future__ import annotations

import re
from typing import Optional

LANGS = ("en", "hi", "mr")
DEFAULT_LANG = "en"

# ── Verify-trust line (reused) ───────────────────────────────────────────────
_VERIFY = {
    "en": "🔒 Doubt this is really us? Verify our official numbers on nidaanpartner.com and in your dashboard (Support).",
    "hi": "🔒 शक है कि यह सच में हम हैं? हमारे आधिकारिक नंबर nidaanpartner.com पर और अपने डैशबोर्ड (सपोर्ट) में जाँचें।",
    "mr": "🔒 हे खरंच आम्हीच आहोत का शंका आहे? आमचे अधिकृत नंबर nidaanpartner.com वर आणि तुमच्या डॅशबोर्डमध्ये (सपोर्ट) तपासा.",
}


# ── 1. Trilingual welcome + save-number + language picker ────────────────────
def render_welcome() -> str:
    """First message to a brand-new contact. All three languages at once."""
    return (
        "🙏 *Namaste · नमस्ते · नमस्कार!*\n\n"
        "This is the official WhatsApp of *Nidaan – The Legal Consultants* "
        "(NidaanPartner.com).\n"
        "📌 Please *SAVE this number* so our updates always reach you safely.\n\n"
        "*Choose your language · अपनी भाषा चुनें · तुमची भाषा निवडा:*\n"
        "Reply *1* → English\n"
        "उत्तर *2* → हिंदी\n"
        "उत्तर *3* → मराठी\n\n"
        + _VERIFY["en"] + "\n"
        + _VERIFY["hi"] + "\n"
        + _VERIFY["mr"]
    )


# ── 2. Language-set acknowledgement (after they pick) ────────────────────────
_LANG_ACK = {
    "en": ("✅ Language set to *English*. You can change it anytime by replying "
           "*change language*.\n\n" + _VERIFY["en"]),
    "hi": ("✅ भाषा *हिंदी* सेट कर दी गई। आप कभी भी *change language* या "
           "*भाषा बदलें* लिखकर इसे बदल सकते हैं।\n\n" + _VERIFY["hi"]),
    "mr": ("✅ भाषा *मराठी* सेट केली. तुम्ही कधीही *change language* किंवा "
           "*भाषा बदला* लिहून ती बदलू शकता.\n\n" + _VERIFY["mr"]),
}


def render_lang_ack(lang: str) -> str:
    return _LANG_ACK.get(lang, _LANG_ACK["en"])


# ── 3. Consent opt-in (advisor-managed customers; names advisor + firm) ──────
_CONSENT = {
    "en": ("Nidaan – The Legal Consultants is handling your insurance claim on "
           "behalf of *{who}*.\n\nReply *YES* to receive case updates here, or "
           "*STOP* to opt out.\n\n" + _VERIFY["en"]),
    "hi": ("Nidaan – The Legal Consultants आपके बीमा क्लेम को *{who}* की ओर से "
           "संभाल रहा है।\n\nयहाँ अपडेट पाने के लिए *YES* लिखें, या बाहर निकलने "
           "के लिए *STOP*।\n\n" + _VERIFY["hi"]),
    "mr": ("Nidaan – The Legal Consultants तुमचा विमा दावा *{who}* यांच्या वतीने "
           "हाताळत आहे.\n\nइथे अपडेट्स मिळवण्यासाठी *YES* लिहा, किंवा बाहेर "
           "पडण्यासाठी *STOP* लिहा.\n\n" + _VERIFY["mr"]),
}


def _format_who(advisor_name: str = "", firm_name: str = "") -> str:
    a = (advisor_name or "").strip()
    f = (firm_name or "").strip()
    if a and f:
        return f"{a}, {f}"
    return a or f or "your advisor"


def render_consent(lang: str, advisor_name: str = "", firm_name: str = "") -> str:
    who = _format_who(advisor_name, firm_name)
    tmpl = _CONSENT.get(lang, _CONSENT["en"])
    return tmpl.format(who=who)


# ── 4. Consent acknowledgements ──────────────────────────────────────────────
_CONSENT_YES_ACK = {
    "en": "✅ Thank you! You'll now receive updates about your claim here. Our team will reach out shortly.",
    "hi": "✅ धन्यवाद! अब आपको अपने क्लेम के अपडेट यहाँ मिलेंगे। हमारी टीम जल्द संपर्क करेगी।",
    "mr": "✅ धन्यवाद! आता तुम्हाला तुमच्या दाव्याचे अपडेट्स इथे मिळतील. आमची टीम लवकरच संपर्क करेल.",
}
_CONSENT_STOP_ACK = {
    "en": "You've opted out and won't receive further WhatsApp updates. Reply *START* anytime to resume.",
    "hi": "आपने ऑप्ट-आउट कर दिया है और अब WhatsApp अपडेट नहीं मिलेंगे। फिर से शुरू करने के लिए कभी भी *START* लिखें।",
    "mr": "तुम्ही ऑप्ट-आउट केले आहे आणि यापुढे WhatsApp अपडेट्स मिळणार नाहीत. पुन्हा सुरू करण्यासाठी कधीही *START* लिहा.",
}


def render_consent_yes_ack(lang: str) -> str:
    return _CONSENT_YES_ACK.get(lang, _CONSENT_YES_ACK["en"])


def render_consent_stop_ack(lang: str) -> str:
    return _CONSENT_STOP_ACK.get(lang, _CONSENT_STOP_ACK["en"])


# ── Parsers (all template-driven, no AI) ─────────────────────────────────────
_LANG_WORDS = {
    "en": {"1", "english", "eng", "अंग्रेज़ी", "अंग्रेजी", "इंग्रजी", "इंग्लिश"},
    "hi": {"2", "hindi", "हिंदी", "हिन्दी"},
    "mr": {"3", "marathi", "मराठी"},
}


def parse_language_choice(text: str) -> Optional[str]:
    """Map a reply to a language code, or None if it isn't a language pick."""
    if not text:
        return None
    t = text.strip().lower()
    # exact-ish token match (handles "1", "2", "3", or the word)
    # strip common punctuation
    t_clean = re.sub(r"[^\wऀ-ॿ]+", "", t)
    for lang, words in _LANG_WORDS.items():
        if t_clean in words or t in words:
            return lang
    return None


_CHANGE_LANG_PATTERNS = [
    r"change\s*(the\s*)?lang", r"\blanguage\s*change\b", r"switch\s*lang",
    r"भाषा\s*बदल", r"भाषा\s*चेंज", r"भाषा\s*बदला", r"भाषा\s*बदलो",
]


def is_change_language_command(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    return any(re.search(p, t) for p in _CHANGE_LANG_PATTERNS)


_YES_WORDS = {"yes", "y", "haan", "हाँ", "हां", "हो", "ok", "okay", "start", "सुरू"}
_STOP_WORDS = {"stop", "no", "नहीं", "नको", "बंद", "unsubscribe"}


def is_consent_yes(text: str) -> bool:
    if not text:
        return False
    t = re.sub(r"[^\wऀ-ॿ]+", "", text.strip().lower())
    return t in _YES_WORDS


def is_consent_stop(text: str) -> bool:
    if not text:
        return False
    t = re.sub(r"[^\wऀ-ॿ]+", "", text.strip().lower())
    return t in _STOP_WORDS


# ── Decision function (the brain the inbound handler calls) ───────────────────
# Action codes returned to the caller:
ACT_SEND_WELCOME = "send_welcome"        # send render_welcome(); contact is new / no lang
ACT_SET_LANG = "set_lang"                # persist `lang`, send ack (+ maybe consent next)
ACT_RESEND_PICKER = "resend_picker"      # "change language" — re-send welcome/picker
ACT_SEND_CONSENT = "send_consent"        # advisor-managed, not opted in — ask consent
ACT_SET_CONSENT_YES = "set_consent_yes"  # persist opt-in, send ack
ACT_SET_CONSENT_STOP = "set_consent_stop"  # persist opt-out, send ack
ACT_PROCEED = "proceed"                  # fully onboarded — let normal claim/doc logic run


def decide_onboarding_action(
    *,
    has_lang: bool,
    lang: Optional[str],
    opted_in: bool,
    is_advisor_managed: bool,
    inbound_text: str,
    advisor_name: str = "",
    firm_name: str = "",
) -> dict:
    """Pure decision: given the contact's onboarding state + their inbound text,
    return {action, lang?, message?}. The caller persists state + sends message.

    `has_lang`           — is a comm_lang already stored for this contact?
    `lang`               — the stored/just-chosen language (used for rendering)
    `opted_in`           — has this contact given WhatsApp consent?
    `is_advisor_managed` — True if the contact is a CUSTOMER under an advisor
                           (needs explicit consent). Self-service = False.
    """
    text = (inbound_text or "").strip()
    cur_lang = lang if lang in LANGS else DEFAULT_LANG

    # (A) "change language" — honoured anytime, before anything else.
    if is_change_language_command(text):
        return {"action": ACT_RESEND_PICKER, "message": render_welcome()}

    # (B) No language chosen yet → either they're picking now, or send welcome.
    if not has_lang:
        choice = parse_language_choice(text)
        if choice:
            # Persist language; decide whether consent is needed next.
            need_consent = is_advisor_managed and not opted_in
            msg = render_lang_ack(choice)
            if need_consent:
                msg = msg + "\n\n" + render_consent(choice, advisor_name, firm_name)
            return {
                "action": ACT_SET_LANG,
                "lang": choice,
                "needs_consent_next": need_consent,
                "message": msg,
            }
        # Not a language pick → (re)send the trilingual welcome + picker.
        return {"action": ACT_SEND_WELCOME, "message": render_welcome()}

    # (C) Language set. Advisor-managed customer who hasn't opted in → consent.
    if is_advisor_managed and not opted_in:
        if is_consent_yes(text):
            return {"action": ACT_SET_CONSENT_YES, "lang": cur_lang,
                    "message": render_consent_yes_ack(cur_lang)}
        if is_consent_stop(text):
            return {"action": ACT_SET_CONSENT_STOP, "lang": cur_lang,
                    "message": render_consent_stop_ack(cur_lang)}
        # Re-ask consent.
        return {"action": ACT_SEND_CONSENT, "lang": cur_lang,
                "message": render_consent(cur_lang, advisor_name, firm_name)}

    # (D) Fully onboarded — let the normal claim/document handler take over.
    return {"action": ACT_PROCEED, "lang": cur_lang}
