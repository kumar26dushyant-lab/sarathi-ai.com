# =============================================================================
#  biz_marketing.py — AI Marketing Studio
#  Sarathi-AI · May 2026
# =============================================================================
#
#  Generates branded marketing content (images + scenario videos) for insurance
#  and wealth-management advisors. Content is stored in the dashboard library,
#  pushed to the advisor's Telegram bot for review, and optionally auto-posted
#  to WhatsApp Status on a scheduler.
#
#  Targeted festival wishes: detects lead religion from name → sends appropriate
#  festival greetings as individual WhatsApp DMs (rate-limited bulk send).
#
#  Plan gating:
#    Solo    → images only
#    Team    → images + videos
#    Enterprise → images + videos + watermark removed
#
# =============================================================================
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import textwrap
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import aiosqlite

logger = logging.getLogger("sarathi.marketing")

# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------
_BASE_DIR = Path(__file__).parent
DB_PATH = os.getenv("DB_PATH", str(_BASE_DIR / "sarathi_biz.db"))
MARKETING_DIR = _BASE_DIR / "uploads" / "marketing"
MARKETING_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
#  Indian Festival Calendar 2026
#  Each entry: {"date": "YYYY-MM-DD", "name": str, "religion": str,
#               "greeting_hi": str, "greeting_en": str}
#  religion: "all" | "hindu" | "muslim" | "sikh" | "christian" | "jain"
# ---------------------------------------------------------------------------
FESTIVAL_CALENDAR_2026: list[dict] = [
    # ── National (all religions) ────────────────────────────────────────────
    {"date": "2026-01-26", "name": "Republic Day",          "religion": "all",
     "greeting_en": "Happy Republic Day! 🇮🇳",
     "greeting_hi": "गणतंत्र दिवस की शुभकामनाएं! 🇮🇳"},
    {"date": "2026-08-15", "name": "Independence Day",      "religion": "all",
     "greeting_en": "Happy Independence Day! 🇮🇳",
     "greeting_hi": "स्वतंत्रता दिवस की हार्दिक शुभकामनाएं! 🇮🇳"},
    {"date": "2026-10-02", "name": "Gandhi Jayanti",        "religion": "all",
     "greeting_en": "Happy Gandhi Jayanti! 🙏",
     "greeting_hi": "गांधी जयंती की शुभकामनाएं! 🙏"},
    {"date": "2026-11-14", "name": "Children's Day",        "religion": "all",
     "greeting_en": "Happy Children's Day! 🧒",
     "greeting_hi": "बाल दिवस की शुभकामनाएं! 🧒"},
    {"date": "2026-04-14", "name": "Ambedkar Jayanti",      "religion": "all",
     "greeting_en": "Happy Ambedkar Jayanti! 🙏",
     "greeting_hi": "डॉ. आंबेडकर जयंती की शुभकामनाएं! 🙏"},

    # ── Hindu ───────────────────────────────────────────────────────────────
    {"date": "2026-01-14", "name": "Makar Sankranti",       "religion": "hindu",
     "greeting_en": "Happy Makar Sankranti! 🪁",
     "greeting_hi": "मकर संक्रांति की हार्दिक शुभकामनाएं! 🪁"},
    {"date": "2026-01-14", "name": "Pongal",                "religion": "hindu",
     "greeting_en": "Happy Pongal! 🌾",
     "greeting_hi": "पोंगल की शुभकामनाएं! 🌾"},
    {"date": "2026-02-17", "name": "Maha Shivaratri",       "religion": "hindu",
     "greeting_en": "Happy Maha Shivaratri! 🕉️",
     "greeting_hi": "महाशिवरात्रि की हार्दिक शुभकामनाएं! 🕉️"},
    {"date": "2026-03-03", "name": "Holi",                  "religion": "hindu",
     "greeting_en": "Happy Holi! 🎨🌈",
     "greeting_hi": "होली की हार्दिक शुभकामनाएं! 🎨🌈"},
    {"date": "2026-03-19", "name": "Gudi Padwa / Ugadi",    "religion": "hindu",
     "greeting_en": "Happy Gudi Padwa & Ugadi! 🏮",
     "greeting_hi": "गुड़ी पड़वा और उगादि की शुभकामनाएं! 🏮"},
    {"date": "2026-03-26", "name": "Ram Navami",            "religion": "hindu",
     "greeting_en": "Happy Ram Navami! 🙏",
     "greeting_hi": "राम नवमी की हार्दिक शुभकामनाएं! 🙏"},
    {"date": "2026-04-14", "name": "Baisakhi",              "religion": "hindu",
     "greeting_en": "Happy Baisakhi! 🌾",
     "greeting_hi": "बैसाखी की शुभकामनाएं! 🌾"},
    {"date": "2026-04-14", "name": "Vishu / Puthandu",      "religion": "hindu",
     "greeting_en": "Happy Vishu & Tamil New Year! 🌸",
     "greeting_hi": "विशु और पुथंडु की शुभकामनाएं! 🌸"},
    {"date": "2026-08-03", "name": "Raksha Bandhan",        "religion": "hindu",
     "greeting_en": "Happy Raksha Bandhan! 🪡",
     "greeting_hi": "रक्षाबंधन की हार्दिक शुभकामनाएं! 🪡"},
    {"date": "2026-08-16", "name": "Janmashtami",           "religion": "hindu",
     "greeting_en": "Happy Janmashtami! 🪶🦚",
     "greeting_hi": "जन्माष्टमी की हार्दिक शुभकामनाएं! 🪶🦚"},
    {"date": "2026-09-21", "name": "Ganesh Chaturthi",      "religion": "hindu",
     "greeting_en": "Happy Ganesh Chaturthi! 🐘",
     "greeting_hi": "गणेश चतुर्थी की हार्दिक शुभकामनाएं! 🐘"},
    {"date": "2026-10-01", "name": "Navratri begins",       "religion": "hindu",
     "greeting_en": "Happy Navratri! 🪔",
     "greeting_hi": "नवरात्रि की हार्दिक शुभकामनाएं! 🪔"},
    {"date": "2026-10-10", "name": "Dussehra",              "religion": "hindu",
     "greeting_en": "Happy Dussehra! Vijay ho! 🏹",
     "greeting_hi": "दशहरे की हार्दिक शुभकामनाएं! विजय हो! 🏹"},
    {"date": "2026-10-29", "name": "Diwali",                "religion": "hindu",
     "greeting_en": "Happy Diwali! May this festival of lights bring joy and prosperity! 🪔✨",
     "greeting_hi": "दीपावली की हार्दिक शुभकामनाएं! आपके जीवन में खुशियों का प्रकाश हो! 🪔✨"},
    {"date": "2026-10-30", "name": "Govardhan Puja",        "religion": "hindu",
     "greeting_en": "Happy Govardhan Puja! 🙏",
     "greeting_hi": "गोवर्धन पूजा की शुभकामनाएं! 🙏"},
    {"date": "2026-10-31", "name": "Bhai Dooj",             "religion": "hindu",
     "greeting_en": "Happy Bhai Dooj! 🤝",
     "greeting_hi": "भाई दूज की शुभकामनाएं! 🤝"},
    {"date": "2026-11-04", "name": "Chhath Puja",           "religion": "hindu",
     "greeting_en": "Happy Chhath Puja! 🌅",
     "greeting_hi": "छठ पूजा की हार्दिक शुभकामनाएं! 🌅"},

    # ── Muslim ──────────────────────────────────────────────────────────────
    {"date": "2026-03-20", "name": "Eid ul-Fitr",           "religion": "muslim",
     "greeting_en": "Eid Mubarak! 🌙⭐ Wishing you joy, peace and blessings.",
     "greeting_hi": "ईद मुबारक! 🌙⭐ खुशी, अमन और बरकत की दुआएं।"},
    {"date": "2026-05-27", "name": "Eid ul-Adha",           "religion": "muslim",
     "greeting_en": "Eid ul-Adha Mubarak! 🌙 May Allah accept your prayers.",
     "greeting_hi": "ईद उल-अज़हा मुबारक! 🌙 अल्लाह आपकी दुआएं कबूल फरमाए।"},
    {"date": "2026-07-17", "name": "Muharram",              "religion": "muslim",
     "greeting_en": "Islamic New Year Mubarak! 🌙",
     "greeting_hi": "इस्लामिक नव वर्ष की मुबारकबाद! 🌙"},
    {"date": "2026-09-25", "name": "Milad-un-Nabi",         "religion": "muslim",
     "greeting_en": "Happy Milad-un-Nabi! 🌙 Peace and blessings upon the Prophet.",
     "greeting_hi": "मिलाद-उन-नबी मुबारक! 🌙"},

    # ── Sikh ────────────────────────────────────────────────────────────────
    {"date": "2026-01-05", "name": "Guru Gobind Singh Jayanti", "religion": "sikh",
     "greeting_en": "Happy Guru Gobind Singh Jayanti! 🙏",
     "greeting_hi": "गुरु गोबिंद सिंह जयंती की शुभकामनाएं! 🙏"},
    {"date": "2026-04-14", "name": "Baisakhi (Sikh)",       "religion": "sikh",
     "greeting_en": "Happy Baisakhi! Waheguru Ji Ka Khalsa, Waheguru Ji Ki Fateh! 🌾",
     "greeting_hi": "बैसाखी की शुभकामनाएं! वाहेगुरु जी का खालसा! 🌾"},
    {"date": "2026-11-05", "name": "Guru Nanak Jayanti",    "religion": "sikh",
     "greeting_en": "Happy Gurpurab! Waheguru Ji Ka Khalsa! 🙏",
     "greeting_hi": "गुरपर्व की शुभकामनाएं! 🙏"},

    # ── Christian ───────────────────────────────────────────────────────────
    {"date": "2026-04-05", "name": "Easter",                "religion": "christian",
     "greeting_en": "Happy Easter! He is Risen! ✝️🌸",
     "greeting_hi": "ईस्टर की शुभकामनाएं! ✝️🌸"},
    {"date": "2026-12-25", "name": "Christmas",             "religion": "christian",
     "greeting_en": "Merry Christmas! 🎄✨ Wishing you joy and peace.",
     "greeting_hi": "क्रिसमस की शुभकामनाएं! 🎄✨"},

    # ── Jain ────────────────────────────────────────────────────────────────
    {"date": "2026-04-13", "name": "Mahavir Jayanti",       "religion": "jain",
     "greeting_en": "Happy Mahavir Jayanti! 🙏 Jai Jinendra.",
     "greeting_hi": "महावीर जयंती की शुभकामनाएं! 🙏 जय जिनेन्द्र।"},
    {"date": "2026-09-05", "name": "Paryushana",            "religion": "jain",
     "greeting_en": "Happy Paryushana! Michhami Dukkadam 🙏",
     "greeting_hi": "पर्युषण की शुभकामनाएं! मिच्छामि दुक्कडम् 🙏"},

    # ── New Year ────────────────────────────────────────────────────────────
    {"date": "2026-01-01", "name": "New Year",              "religion": "all",
     "greeting_en": "Happy New Year 2026! 🎉 Wishing you great health, wealth and happiness.",
     "greeting_hi": "नव वर्ष 2026 की हार्दिक शुभकामनाएं! 🎉 खुशियों भरा साल हो।"},
]

# Religion keyword patterns for name-based detection
_RELIGION_PATTERNS: list[tuple[str, list[str]]] = [
    ("muslim", [
        r"\b(faruq|farooq|ahmed|ahmad|mohammed|mohammad|muhammad|ali|raza|khan|"
        r"shaikh|sheikh|siddiqui|siddiquee|ansari|qureshi|pathan|memon|"
        r"asif|akram|iqbal|mirza|hashmi|aslam|saleem|naved|tariq|"
        r"imran|usman|zubair|adnan|waqar|faisal|rizwan|wasim|"
        r"fatima|zainab|ayesha|khadija|amina|salma|samreen|"
        r"sana|nida|bushra|ruksar|rukhsar|shabana|nasreen)\b"
    ]),
    ("sikh", [
        r"\b(singh|kaur|preetinder|harpreet|manpreet|gurpreet|jaspreet|"
        r"simranjit|balwinder|kulwinder|navdeep|paramjit|amarjit|"
        r"jasmine|jasmeen|prabhjot|sukhwinder|ravinder)\b"
    ]),
    ("christian", [
        r"\b(john|george|thomas|joseph|james|peter|paul|"
        r"michael|david|robert|stephen|xavier|sebastian|"
        r"mary|maria|rose|grace|rachel|sarah|ruth|elizabeth|"
        r"fernandes|dsouza|d'souza|pereira|lobo|rodrigues|"
        r"mathew|mathews|varghese|chacko|kurien|antony)\b"
    ]),
    ("jain", [
        r"\b(jain|mehta|shah|sethi|bothra|surana|singhvi|"
        r"oswal|agarwal|parikh|savla|doshi|sheth|sanghvi|"
        r"maheshwari|lodha|bhandari|chordia)\b"
    ]),
]


def detect_religion_from_name(name: str) -> str:
    """Return religion tag for a lead name: muslim/sikh/christian/jain/hindu.
    Falls back to 'hindu' (majority default for India)."""
    if not name:
        return "hindu"
    lower = name.lower()
    for religion, patterns in _RELIGION_PATTERNS:
        for pattern in patterns:
            if re.search(pattern, lower, re.IGNORECASE):
                return religion
    return "hindu"


def get_festivals_for_date(target_date: date, prefs: list[str]) -> list[dict]:
    """Return all festivals on target_date that match the tenant's religion prefs."""
    ds = target_date.strftime("%Y-%m-%d")
    return [
        f for f in FESTIVAL_CALENDAR_2026
        if f["date"] == ds and (f["religion"] in prefs or "all" in prefs or f["religion"] == "all")
    ]


def get_festivals_for_lead(lead_name: str) -> list[dict]:
    """Return all upcoming festivals relevant to a lead's detected religion."""
    religion = detect_religion_from_name(lead_name)
    today = date.today().strftime("%Y-%m-%d")
    return [
        f for f in FESTIVAL_CALENDAR_2026
        if f["date"] >= today and (f["religion"] == religion or f["religion"] == "all")
    ][:5]  # next 5 relevant festivals


def get_all_festivals(prefs: Optional[list[str]] = None) -> list[dict]:
    """Return full festival list, filtered by religion prefs if provided."""
    if not prefs:
        return FESTIVAL_CALENDAR_2026
    today = date.today().strftime("%Y-%m-%d")
    return [
        f for f in FESTIVAL_CALENDAR_2026
        if f["date"] >= today and (f["religion"] in prefs or f["religion"] == "all")
    ]


# ---------------------------------------------------------------------------
#  Content Text Generation (Gemini)
# ---------------------------------------------------------------------------
_CUSTOM_CONTENT_PROMPT = """
You are a marketing copywriter for an Indian insurance and wealth management advisor.
Write a compelling WhatsApp marketing post about: {topic}
Firm: {firm_name}
Language: {lang_label}

Rules:
- 3-4 lines maximum
- Tone: professional, empathetic, not pushy
- Include ONE emotional hook, ONE key fact or statistic (India-specific)
- End with a soft call to action
- NO hashtags
- Under 250 characters total

Reply with ONLY the message text. No title, no quotes, no explanation.
"""

_SCENARIO_PROMPTS = {
    "scenario_insurance": {
        "en": (
            "Write a compelling 3-4 line WhatsApp marketing message for an insurance advisor "
            "sharing a real-life story: A person faced huge out-of-pocket medical bills because "
            "they had no health insurance or insufficient coverage. The message should create "
            "emotional impact and end with a subtle call to action about reviewing their insurance coverage. "
            "Tone: empathetic, professional, not salesy. No hashtags. Under 200 characters."
        ),
        "hi": (
            "एक बीमा सलाहकार के लिए WhatsApp मार्केटिंग संदेश लिखें (3-4 लाइनें): "
            "एक व्यक्ति को बीमा न होने के कारण अचानक बीमारी में लाखों रुपये खर्च करने पड़े। "
            "भावनात्मक प्रभाव डालें, अंत में बीमा की समीक्षा का सुझाव दें। "
            "पेशेवर, दिल को छूने वाला, बेचने वाला नहीं। 200 अक्षर से कम।"
        ),
        "mr": (
            "एका विमा सल्लागारासाठी WhatsApp मार्केटिंग संदेश लिहा (3-4 ओळी): "
            "एका व्यक्तीला आरोग्य विमा नसल्यामुळे अचानक आजारात लाखो रुपये खर्च करावे लागले. "
            "भावनिक परिणाम साधा आणि शेवटी विमा आढाव्याचा सौम्य संदेश द्या. "
            "व्यावसायिक, संवेदनशील, विक्री नाही. 200 अक्षरांच्या आत."
        ),
    },
    "scenario_investment": {
        "en": (
            "Write a compelling 3-4 line WhatsApp marketing message for a wealth management advisor: "
            "A person kept all savings in a bank FD for 20 years and got modest returns, while someone "
            "who started SIP in mutual funds built significant wealth over the same period. "
            "Show the contrast without naming specific funds. Call to action: start a systematic "
            "investment review. Tone: educational, not pushy. Under 200 characters."
        ),
        "hi": (
            "एक वेल्थ मैनेजमेंट सलाहकार के लिए WhatsApp संदेश (3-4 लाइनें): "
            "एक व्यक्ति ने 20 साल बचत खाते में पैसे रखे, दूसरे ने SIP शुरू की — "
            "20 साल बाद दोनों की संपत्ति का फर्क देखें। "
            "शैक्षिक, प्रेरक, सलाह देने वाला। 200 अक्षर से कम।"
        ),
        "mr": (
            "एका वेल्थ मॅनेजमेंट सल्लागारासाठी WhatsApp संदेश (3-4 ओळी): "
            "एका व्यक्तीने 20 वर्षे बँकेच्या FD मध्ये पैसे ठेवले, दुसऱ्याने SIP सुरू केली — "
            "20 वर्षांनंतर दोघांच्या संपत्तीतील फरक पहा. "
            "शैक्षणिक, प्रेरक, सल्ला देणारा. 200 अक्षरांच्या आत."
        ),
    },
    "tip": {
        "en": (
            "Write a short, practical financial tip (2-3 lines) for an insurance or wealth advisor "
            "to share with clients on WhatsApp. Topic: one of [term insurance, health insurance, "
            "emergency fund, SIP, life goals planning, nominee update]. "
            "Conversational, actionable. Under 180 characters."
        ),
        "hi": (
            "एक बीमा/वेल्थ सलाहकार के लिए एक व्यावहारिक वित्तीय टिप (2-3 लाइनें) लिखें। "
            "विषय: [टर्म बीमा, स्वास्थ्य बीमा, आपातकालीन फंड, SIP, नॉमिनी अपडेट] में से एक। "
            "बातचीत की शैली में, उपयोगी। 180 अक्षर से कम।"
        ),
        "mr": (
            "एका विमा/वेल्थ सल्लागारासाठी एक व्यावहारिक आर्थिक टिप (2-3 ओळी) लिहा. "
            "विषय: [टर्म विमा, आरोग्य विमा, आपत्कालीन निधी, SIP, नॉमिनी अपडेट] पैकी एक. "
            "संवादात्मक, उपयुक्त. 180 अक्षरांच्या आत."
        ),
    },
    "product_pitch": {
        "en": (
            "Write a 3-4 line WhatsApp message for an insurance advisor promoting their advisory services. "
            "Highlight: personalized financial planning, claims support, and peace of mind. "
            "End with a soft call to action (WhatsApp/call for a free review). "
            "Professional, warm. Under 200 characters."
        ),
        "hi": (
            "एक बीमा सलाहकार की सेवाओं को promote करने के लिए WhatsApp संदेश (3-4 लाइनें): "
            "व्यक्तिगत वित्तीय योजना, क्लेम सहायता, मन की शांति। "
            "अंत में मुफ्त परामर्श के लिए कहें। पेशेवर, मधुर। 200 अक्षर से कम।"
        ),
        "mr": (
            "एका विमा सल्लागाराच्या सेवांची जाहिरात करण्यासाठी WhatsApp संदेश (3-4 ओळी): "
            "वैयक्तिक आर्थिक नियोजन, क्लेम सहाय्य, मनःशांती. "
            "शेवटी मोफत सल्ल्यासाठी विचारा. व्यावसायिक, उबदार. 200 अक्षरांच्या आत."
        ),
    },
}


def _clean_caption(text: str) -> str:
    """Strip LLM artifacts so they never reach the poster: preambles
    ('Here's a draft:', 'यहाँ एक मसौदा है:'), character/word counts
    ('(कुल 189 अक्षर)', '(total 189 characters)'), labels, and markdown."""
    if not text:
        return ""
    s = text.strip().replace("```", "").replace("**", "").replace("__", "")
    # Strip leading preamble lines (English + Hindi), up to a few of them.
    preamble = re.compile(
        r"^\s*(here(?:'s| is)\b[^:\n]*:|sure[!,. ]+|okay[!,. ]+|draft\s*:|caption\s*:|"
        r"post\s*:|option\s*\d*\s*:|यहाँ[^:\n]*:|यह\s+रहा[^:\n]*:|कैप्शन\s*:|प्रस्तुत[^:\n]*:|"
        r"प्रस्तावित[^:\n]*:)\s*", re.IGNORECASE)
    for _ in range(3):
        nxt = preamble.sub("", s).strip()
        if nxt == s:
            break
        s = nxt
    # Remove character/word counts anywhere (brackets) and at the end (any script).
    s = re.sub(r"[\(\[\{][^)\]\}]*?\b\d{1,4}\s*(?:characters?|chars?|words?|अक्षर|शब्द|कैरेक्टर)\b[^)\]\}]*?[\)\]\}]",
               "", s, flags=re.IGNORECASE)
    s = re.sub(r"[—\-–]?\s*(?:total\s*|कुल\s*)?\b\d{1,4}\s*(?:characters?|chars?|words?|अक्षर|शब्द)\b\.?\s*$",
               "", s, flags=re.IGNORECASE | re.MULTILINE)
    s = re.sub(r"(?:character|word|कैरेक्टर|अक्षर|शब्द)\s*count\s*[:\-]?\s*\d{1,4}",
               "", s, flags=re.IGNORECASE)
    s = re.sub(r"\n{3,}", "\n\n", s).strip().strip('"').strip("'").strip()
    return s


async def generate_content_text(content_type: str, lang: str = "en",
                                festival: Optional[dict] = None,
                                tenant_name: str = "",
                                custom_topic: str = "") -> tuple[str, str]:
    """Generate marketing copy using Gemini. Returns (title, body_text)."""
    try:
        import biz_ai as ai
        lang_key = lang if lang in ("hi", "mr") else "en"
        if content_type == "festival" and festival:
            # Festival greetings: fall back hi→en if mr missing
            greeting = festival.get(f"greeting_{lang_key}",
                                    festival.get("greeting_hi" if lang_key == "mr" else "greeting_en",
                                                 festival.get("greeting_en", "")))
            body = greeting
            if tenant_name:
                sep = "\n" if lang_key in ("hi", "mr") else "\n\n"
                body = f"{greeting}{sep}— {tenant_name}"
            return festival["name"], body

        if content_type == "custom" and custom_topic:
            lang_label = {"hi": "Hindi", "mr": "Marathi"}.get(lang_key, "English")
            prompt = _CUSTOM_CONTENT_PROMPT.format(
                topic=custom_topic,
                firm_name=tenant_name or "Sarathi",
                lang_label=lang_label,
            )
            body = await ai._ask_gemini(prompt)
            body = body.strip().strip('"').strip()
            title = custom_topic[:60]
            return title, body

        prompts = _SCENARIO_PROMPTS.get(content_type, _SCENARIO_PROMPTS["tip"])
        prompt = prompts.get(lang_key, prompts["en"])
        if tenant_name:
            prompt += f" The advisor's firm name is '{tenant_name}'."

        body = await ai._ask_gemini(prompt)
        body = _clean_caption(body)
        title_map = {
            "scenario_insurance": {
                "en": "The True Cost of Not Having Insurance",
                "hi": "बीमा न होने की सच्चाई",
                "mr": "विमा नसल्याची खरी किंमत",
            },
            "scenario_investment": {
                "en": "Why Your Savings Account May Not Be Enough",
                "hi": "बचत खाता पर्याप्त नहीं",
                "mr": "तुमचे बचत खाते पुरेसे नसेल",
            },
            "tip": {
                "en": "Quick Financial Tip",
                "hi": "वित्तीय सुझाव",
                "mr": "आर्थिक सूचना",
            },
            "product_pitch": {
                "en": "Your Trusted Insurance Advisor",
                "hi": "आपका विश्वसनीय सलाहकार",
                "mr": "तुमचा विश्वासू विमा सल्लागार",
            },
        }
        title = title_map.get(content_type, {}).get(lang_key, "Marketing Content")
        return title, body
    except Exception as e:
        logger.warning("Content text generation failed: %s", e)
        return "Marketing Content", "Protect what matters most. Connect with your advisor today."


# ---------------------------------------------------------------------------
#  Image Generation (Pillow)
# ---------------------------------------------------------------------------
# ── Font paths: separate Latin and Devanagari (Hindi/Marathi) ──────────────
_LATIN_BOLD = next((p for p in [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/arial.ttf",
] if Path(p).exists()), None)
_LATIN_REG = next((p for p in [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "C:/Windows/Fonts/arial.ttf",
] if Path(p).exists()), None)
_DEVA_BOLD = next((p for p in [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    "C:/Windows/Fonts/Nirmala.ttf",
] if Path(p).exists()), None)
_DEVA_REG = next((p for p in [
    "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
    "C:/Windows/Fonts/Nirmala.ttf",
] if Path(p).exists()), None)
_FONT_CACHE: dict = {}


def _has_devanagari(text: str) -> bool:
    """True if text contains any Devanagari char (Hindi/Marathi/Sanskrit)."""
    return any(0x0900 <= ord(c) <= 0x097F for c in text or "")


def _font_for(text: str, size: int, bold: bool = True):
    """Pick the right font based on the script in `text`. Devanagari fonts don't
    carry full Latin glyphs and vice versa, so we route by content."""
    from PIL import ImageFont
    size = max(int(size), 10)
    if _has_devanagari(text):
        path = _DEVA_BOLD if bold else _DEVA_REG
    else:
        path = _LATIN_BOLD if bold else _LATIN_REG
    if not path:
        return ImageFont.load_default()
    key = (path, size)
    f = _FONT_CACHE.get(key)
    if f is None:
        f = ImageFont.truetype(path, size)
        _FONT_CACHE[key] = f
    return f


# Legacy wrappers — kept so existing calls compile. They default to Latin
# script unless caller passes text via _font_for. Going forward use _font_for.
def _load_font(size: int):
    return _font_for("", size, bold=True)


def _load_font_regular(size: int):
    return _font_for("", size, bold=False)


# ── Emoji stripping — Pillow doesn't render color emoji well, and the
# Gemini output frequently includes them in headlines. Strip them upstream.
import re as _re
_EMOJI_RE = _re.compile(
    "[" "\U0001F300-\U0001F5FF" "\U0001F600-\U0001F64F" "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F" "\U0001F900-\U0001F9FF" "\U0001FA00-\U0001FAFF"
    "\U00002600-\U000027BF" "\U0001F1E6-\U0001F1FF" "]+", flags=_re.UNICODE)


def _strip_emojis(s: str) -> str:
    """Remove emoji glyphs to avoid 'box' rendering in Pillow."""
    if not s:
        return s
    return _EMOJI_RE.sub("", s).replace("  ", " ").strip()


# ── Photo templates (static/templates/marketing/) ─────────────────────────
_TEMPLATE_DIR = Path(__file__).parent / "static" / "templates" / "marketing"

# Map content_type → default template slug. Imagen-generated templates are
# preferred (imagen_<slug>); the older user-supplied templates remain as
# backwards-compatible aliases via _resolve_template_path().
_TEMPLATE_DEFAULT = {
    "scenario_insurance": "imagen_health_hospital_bill",
    "scenario_investment": "imagen_invest_growth_chart",
    "tip": "imagen_invest_sip_chai",
    "product_pitch": "imagen_claim_handshake_advisor",
    "festival": "imagen_festival_diwali",
    "custom": "imagen_advisor_meeting_with_couple",
}

# Known template ids (filename without extension, .png) — case-tolerant lookup
def _resolve_template_path(slug: str):
    """Return Path to template image if it exists, else None.
    Tries both 'slug.png' and 'template_slug.png' (we mixed naming)."""
    if not slug or not _TEMPLATE_DIR.exists():
        return None
    candidates = [
        _TEMPLATE_DIR / f"{slug}.png",
        _TEMPLATE_DIR / f"template_{slug}.png",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _default_template_for(content_type: str) -> str:
    return _TEMPLATE_DEFAULT.get(content_type, "")


_PEXELS_SEED = {
    "scenario_insurance": "Indian family worried about hospital bill",
    "scenario_investment": "Indian businessman investment growth chart",
    "tip": "Indian financial advisor consulting",
    "product_pitch": "Indian insurance advisor handshake client",
    "festival": "Indian family Diwali celebration lights",
    "custom": "Indian family financial planning",
}


def _pexels_query_for(content_type: str, hint_text: str) -> str:
    """Build a Pexels search query from content_type + a short hint of the title."""
    seed = _PEXELS_SEED.get(content_type, "Indian family financial planning")
    # Strip emojis from hint and clip to keep query focused
    hint = (hint_text or "").strip()
    hint = "".join(c for c in hint if c.isalnum() or c.isspace()).strip()
    hint = " ".join(hint.split()[:5])
    return f"{seed} {hint}".strip()


def list_available_templates() -> list[dict]:
    """Return currently-installed templates for the dashboard picker.
    Imagen-generated templates come first (preferred), then legacy templates."""
    if not _TEMPLATE_DIR.exists():
        return []
    imagen_items = []
    legacy_items = []
    for p in sorted(_TEMPLATE_DIR.glob("*.png")):
        slug = p.stem
        if slug.startswith("template_"):
            slug = slug[len("template_"):]
        item = {
            "id": slug,
            "filename": p.name,
            "url": f"/static/templates/marketing/{p.name}",
        }
        if slug.startswith("imagen_"):
            imagen_items.append(item)
        else:
            legacy_items.append(item)
    return imagen_items + legacy_items


IMAGE_FORMATS = {
    "whatsapp_status": (1080, 1920),   # 9:16 vertical — WhatsApp Status
    "instagram_square": (1080, 1080),  # 1:1 square — Instagram / WhatsApp post
    "linkedin_banner": (1200, 627),    # LinkedIn post / Facebook cover
}


async def generate_image(
    tenant_id: int,
    content_type: str,
    title: str,
    body_text: str,
    firm_name: str = "",
    agent_name: str = "",
    marketing_photo_path: str = "",
    marketing_logo_path: str = "",
    watermark: bool = True,
    lang: str = "en",
    image_format: str = "whatsapp_status",
    brand_accent: str = "",
    template_id: str = "",
) -> Optional[str]:
    """
    Generate a branded marketing image.
    image_format: whatsapp_status (1080×1920) | instagram_square (1080×1080) | linkedin_banner (1200×627)
    brand_accent: hex color from tenant brand kit (overrides default accent per content_type)
    template_id: filename slug under static/templates/marketing/ — if provided, uses that photo
                 as the background (blurred+darkened) instead of the flat gradient.
    Returns the relative path under uploads/marketing/, or None on failure.
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter

        # Strip emojis from any Gemini-generated text (Pillow can't render color glyphs)
        title = _strip_emojis(title or "")
        body_text = _strip_emojis(body_text or "")

        # Keep captions tight so they always fit the text band (no overflow onto
        # the photo / footer). The full caption is still saved as body_text for
        # WhatsApp/Telegram; only the on-image copy is trimmed.
        _max_on_image = 240 if image_format == "whatsapp_status" else (190 if image_format == "instagram_square" else 260)
        body_on_image = body_text
        if len(body_on_image) > _max_on_image:
            cut = body_on_image[:_max_on_image].rsplit(" ", 1)[0].rstrip(".,;:—- ")
            body_on_image = (cut or body_on_image[:_max_on_image]) + "…"

        dims = IMAGE_FORMATS.get(image_format, IMAGE_FORMATS["whatsapp_status"])
        W, H = dims

        # ── Accent color: brand kit overrides content-type default ─────────
        _default_accents = {
            "scenario_insurance": "#ef4444",
            "scenario_investment": "#22c55e",
            "tip": "#3b82f6",
            "product_pitch": "#8b5cf6",
            "festival": "#f59e0b",
            "custom": "#0ea5e9",
        }
        accent_color = brand_accent if brand_accent and brand_accent.startswith("#") else \
                       _default_accents.get(content_type, "#3b82f6")

        # ── Background: explicit template_id > Pexels search > default per type ──
        tpl_path = None
        if template_id:
            tpl_path = _resolve_template_path(template_id)
        if not tpl_path:
            # Try Pexels stock photo using title/topic as search hint
            try:
                import biz_pexels as pex
                if pex.is_enabled():
                    pex_query = _pexels_query_for(content_type, title or body_text or "")
                    pex_path = await pex.fetch_for_query(
                        pex_query,
                        orientation=("portrait" if image_format == "whatsapp_status"
                                     else "square" if image_format == "instagram_square"
                                     else "landscape"),
                    )
                    if pex_path and Path(pex_path).exists():
                        tpl_path = pex_path
            except Exception as pe:
                logger.debug("Pexels fallback failed: %s", pe)
        if not tpl_path:
            # Fall back to the built-in default template for this content type
            tpl_id = _default_template_for(content_type)
            tpl_path = _resolve_template_path(tpl_id) if tpl_id else None
        if tpl_path:
            bg = Image.open(tpl_path).convert("RGB")
            # Cover-crop to canvas dims
            bg_ratio = bg.width / bg.height
            target_ratio = W / H
            if bg_ratio > target_ratio:
                new_h = H
                new_w = int(H * bg_ratio)
            else:
                new_w = W
                new_h = int(W / bg_ratio)
            bg = bg.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - W) // 2
            top = (new_h - H) // 2
            bg = bg.crop((left, top, left + W, top + H))
            # Soft blur for readability, then darken bands for text
            bg = bg.filter(ImageFilter.GaussianBlur(radius=3))
            img = bg
            # Darken top + bottom for header/footer text legibility
            overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            od = ImageDraw.Draw(overlay)
            # Top band — covers logo + badge
            for y in range(0, int(H * 0.20)):
                a = int(160 * (1 - y / max(1, int(H * 0.20))))
                od.line([(0, y), (W, y)], fill=(0, 0, 0, a))
            # Middle text scrim — strong, near-uniform band so body copy stays
            # readable over any background photo (feathered top/bottom edges only).
            mid_top = int(H * 0.26)
            mid_bot = int(H * 0.74)
            feather = max(1, int((mid_bot - mid_top) * 0.18))
            for y in range(mid_top, mid_bot):
                d_top = y - mid_top
                d_bot = mid_bot - y
                edge = min(d_top, d_bot)
                a = 185 if edge >= feather else int(185 * (edge / feather))
                od.line([(0, y), (W, y)], fill=(10, 15, 30, a))
            # Bottom band — covers name + disclaimer + watermark
            for y in range(int(H * 0.75), H):
                a = int(220 * ((y - H * 0.75) / max(1, H * 0.25)))
                od.line([(0, y), (W, y)], fill=(0, 0, 0, min(a, 220)))
            img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        else:
            img = Image.new("RGB", (W, H), color="#0f172a")
        draw = ImageDraw.Draw(img)

        # Top gradient strip (accent color) — only when no photo template
        if not tpl_path:
            for y in range(0, 220):
                alpha = int(220 * (1 - y / 220))
                r, g, b = int(accent_color[1:3], 16), int(accent_color[3:5], 16), int(accent_color[5:7], 16)
                blended = tuple(int(c * alpha / 255 + 0x0f * (1 - alpha / 255)) for c in (r, g, b))
                draw.line([(0, y), (W, y)], fill=blended)

        # ── Advisor logo top-left (or "Your logo here" placeholder) ──────────
        logo_h = int(110 * _scale_w if (_scale_w := W / 1080) else 110)
        logo_h = max(60, min(logo_h, 140))
        logo_rendered = False
        if marketing_logo_path and Path(marketing_logo_path).exists():
            try:
                logo = Image.open(marketing_logo_path).convert("RGBA")
                # Scale by height, preserve aspect ratio, cap width at 360
                ratio = logo.width / max(logo.height, 1)
                new_w = min(int(logo_h * ratio), 360)
                logo = logo.resize((new_w, logo_h), Image.LANCZOS)
                img.paste(logo, (60, 50), logo)
                logo_rendered = True
            except Exception as le:
                logger.debug("Marketing logo load failed: %s", le)
        if not logo_rendered:
            # Placeholder: dashed-rectangle box "Your logo here" — nudges advisor to upload
            box_w, box_h = 260, logo_h
            x0, y0 = 60, 50
            # Draw subtle rounded rectangle outline
            for i in range(2):
                draw.rectangle([(x0 + i, y0 + i), (x0 + box_w - i, y0 + box_h - i)],
                               outline="#ffffff55", width=1)
            placeholder_lbl = {"hi": "अपना लोगो यहाँ", "mr": "तुमचा लोगो येथे"}.get(lang, "Your logo here")
            font_ph = _font_for(placeholder_lbl, 20, bold=False)
            draw.text((x0 + 14, y0 + (box_h // 2) - 12), placeholder_lbl,
                      fill="#ffffff88", font=font_ph)
        # Small co-brand on far-right top corner
        cobrand_txt = "by Sarathi AI"
        font_cobrand = _font_for(cobrand_txt, 18, bold=False)
        draw.text((W - 180, 64), cobrand_txt, fill="#ffffff55", font=font_cobrand)

        # ── Content type badge (localized + no emojis to avoid box rendering) ──
        _badge_by_type = {
            "scenario_insurance": {"en": "Insurance Awareness", "hi": "बीमा जागरूकता", "mr": "विमा जागरूकता"},
            "scenario_investment": {"en": "Wealth Insight", "hi": "धन-संपत्ति", "mr": "संपत्ती"},
            "tip": {"en": "Financial Tip", "hi": "वित्तीय सुझाव", "mr": "आर्थिक सूचना"},
            "product_pitch": {"en": "Advisory Services", "hi": "सलाहकार सेवाएं", "mr": "सल्लागार सेवा"},
            "festival": {"en": "Festival Wishes", "hi": "त्योहार की शुभकामनाएं", "mr": "सणाच्या शुभेच्छा"},
            "custom": {"en": "Marketing", "hi": "मार्केटिंग", "mr": "मार्केटिंग"},
        }.get(content_type, {"en": "Marketing", "hi": "मार्केटिंग", "mr": "मार्केटिंग"})
        badge_text = _badge_by_type.get(lang, _badge_by_type["en"])
        font_badge = _font_for(badge_text, 36, bold=False)
        badge_y = 50 + logo_h + 18   # always sit clear below the logo / placeholder box
        draw.text((60, badge_y), badge_text, fill=accent_color, font=font_badge)

        # ── Decorative accent line ───────────────────────────────────────────
        accent_line_y = badge_y + 56
        draw.rectangle([(60, accent_line_y), (160, accent_line_y + 6)], fill=accent_color)

        # Scale font sizes based on canvas dimensions
        _scale = min(W, H) / 1080
        title_font_size = max(int(72 * _scale), 28)
        body_font_size  = max(int(52 * _scale), 22)
        title_y = int(280 * (H / 1920)) if image_format == "whatsapp_status" else int(H * 0.18)
        title_y = max(title_y, accent_line_y + 34)   # never collide with the badge/accent line
        body_y  = int(580 * (H / 1920)) if image_format == "whatsapp_status" else int(H * 0.35)
        title_wrap_width = 20 if image_format == "whatsapp_status" else (30 if image_format == "instagram_square" else 40)
        body_wrap_width  = 28 if image_format == "whatsapp_status" else (34 if image_format == "instagram_square" else 55)

        # ── Title (white with a dark outline → readable on any background) ────
        font_title = _font_for(title, title_font_size, bold=True)
        title_wrapped = textwrap.fill(title, width=title_wrap_width)
        draw.text((60, title_y), title_wrapped, fill="#ffffff", font=font_title,
                  stroke_width=3, stroke_fill="#0a0f1e")

        # ── Body text (pure white + outline; uses the trimmed on-image copy) ──
        font_body = _font_for(body_on_image, body_font_size, bold=False)
        body_wrapped = textwrap.fill(body_on_image, width=body_wrap_width)
        draw.text((60, body_y), body_wrapped, fill="#ffffff", font=font_body,
                  stroke_width=2, stroke_fill="#0a0f1e")

        # ── Agent photo (circular, bottom-right) ─────────────────────────────
        photo_loaded = False
        if marketing_photo_path and Path(marketing_photo_path).exists():
            try:
                photo = Image.open(marketing_photo_path).convert("RGBA")
                photo = photo.resize((220, 220), Image.LANCZOS)
                # Circular mask
                mask = Image.new("L", (220, 220), 0)
                from PIL import ImageDraw as ID2
                ID2.Draw(mask).ellipse((0, 0, 220, 220), fill=255)
                photo_circle = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
                photo_circle.paste(photo, (0, 0), mask)
                px, py = W - 280, H - 360
                img.paste(photo_circle, (px, py), photo_circle)
                # White ring → makes the advisor's face stand out (trust cue).
                draw.ellipse([(px - 4, py - 4), (px + 224, py + 224)],
                             outline="#ffffff", width=6)
                photo_loaded = True
            except Exception as pe:
                logger.debug("Marketing photo load failed: %s", pe)

        if not photo_loaded:
            # Placeholder circle with initials
            cx, cy = W - 170, H - 250
            r = 100
            draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill="#1e3a5f")
            initials = "".join(w[0].upper() for w in (agent_name or firm_name or "SA").split()[:2])
            # ASCII only for initials — always Latin font
            font_ini = _font_for("ABC", 72, bold=True)
            draw.text((cx - 40, cy - 45), initials, fill="#60a5fa", font=font_ini)

        # ── Agent / firm info (bottom) ────────────────────────────────────────
        name_font_size = max(int(54 * _scale), 20)
        firm_font_size = max(int(40 * _scale), 16)
        footer_offset  = int(340 * (H / 1920)) if image_format == "whatsapp_status" else int(H * 0.22)
        primary_name = agent_name or firm_name or ""
        font_name = _font_for(primary_name, name_font_size, bold=True)
        draw.text((60, H - footer_offset), primary_name, fill="#ffffff", font=font_name,
                  stroke_width=2, stroke_fill="#0a0f1e")
        if firm_name and agent_name and firm_name.strip().lower() != agent_name.strip().lower():
            font_firm = _font_for(firm_name, firm_font_size, bold=False)
            draw.text((60, H - int(footer_offset * 0.79)), firm_name, fill="#cbd5e1", font=font_firm,
                      stroke_width=1, stroke_fill="#0a0f1e")

        # ── Soft IRDAI disclaimer band (small, neutral, advisor-onus) ─────────
        disclaimer_map = {
            "en": "General awareness post. Please consult your advisor before making a financial decision.",
            "hi": "सामान्य जानकारी के लिए। कोई भी वित्तीय निर्णय लेने से पहले अपने सलाहकार से सलाह लें।",
            "mr": "सामान्य माहितीसाठी. आर्थिक निर्णय घेण्यापूर्वी आपल्या सल्लागाराचा सल्ला घ्या.",
        }
        disclaimer_txt = disclaimer_map.get(lang, disclaimer_map["en"])
        disclaim_font_size = max(int(22 * _scale), 12)
        font_disclaim = _font_for(disclaimer_txt, disclaim_font_size, bold=False)
        disclaim_wrap = 60 if image_format == "whatsapp_status" else (75 if image_format == "instagram_square" else 110)
        disclaim_wrapped = textwrap.fill(disclaimer_txt, width=disclaim_wrap)
        disclaim_y = H - int(footer_offset * 0.62)
        draw.text((60, disclaim_y), disclaim_wrapped, fill="#c7d2fe" if tpl_path else "#64748b", font=font_disclaim)

        # ── Watermark ─────────────────────────────────────────────────────────
        if watermark:
            wm_txt = "Made with Sarathi AI"
            font_wm = _font_for(wm_txt, 28, bold=False)
            draw.text((W - 300, H - 50), wm_txt,
                      fill="#ffffff40", font=font_wm)

        # ── Save ─────────────────────────────────────────────────────────────
        today_str = date.today().strftime("%Y%m%d")
        fmt_tag = image_format.replace("whatsapp_status", "wa").replace("instagram_square", "ig").replace("linkedin_banner", "li")
        filename = f"mkt_{tenant_id}_{content_type}_{fmt_tag}_{today_str}_{int(datetime.now().timestamp())}.png"
        save_path = MARKETING_DIR / filename
        img.save(str(save_path), "PNG", optimize=True)
        return f"uploads/marketing/{filename}"

    except ImportError:
        logger.error("Pillow not installed — cannot generate marketing images")
        return None
    except Exception as e:
        logger.error("Image generation failed: %s", e, exc_info=True)
        return None


# ---------------------------------------------------------------------------
#  Content Pipeline: generate text + image together
# ---------------------------------------------------------------------------
async def generate_content(
    tenant_id: int,
    content_type: str,
    lang: str = "en",
    festival: Optional[dict] = None,
    firm_name: str = "",
    agent_name: str = "",
    marketing_photo_path: str = "",
    marketing_logo_path: str = "",
    watermark: bool = True,
    custom_topic: str = "",
    image_format: str = "whatsapp_status",
    brand_accent: str = "",
    template_id: str = "",
) -> dict:
    """
    Full content generation pipeline.
    Returns: {title, body_text, image_path, content_type, festival_name, religion_tag}
    """
    title, body_text = await generate_content_text(
        content_type, lang, festival=festival, tenant_name=firm_name,
        custom_topic=custom_topic,
    )
    image_path = await generate_image(
        tenant_id, content_type, title, body_text,
        firm_name=firm_name, agent_name=agent_name,
        marketing_photo_path=marketing_photo_path,
        marketing_logo_path=marketing_logo_path,
        watermark=watermark, lang=lang,
        image_format=image_format,
        brand_accent=brand_accent,
        template_id=template_id,
    )
    return {
        "title": title,
        "body_text": body_text,
        "image_path": image_path,
        "content_type": content_type,
        "language": lang,
        "image_format": image_format,
        "festival_name": festival["name"] if festival else None,
        "religion_tag": festival["religion"] if festival else "all",
        "custom_topic": custom_topic or None,
    }


# ---------------------------------------------------------------------------
#  DB helpers for marketing_content
# ---------------------------------------------------------------------------
async def save_content(tenant_id: int, content: dict) -> int:
    """Insert a generated content record. Returns content_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO marketing_content
               (tenant_id, content_type, title, body_text, image_path, video_path,
                festival_name, religion_tag, language, generated_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id,
             content.get("content_type", "tip"),
             content.get("title", ""),
             content.get("body_text", ""),
             content.get("image_path", ""),
             content.get("video_path", ""),
             content.get("festival_name"),
             content.get("religion_tag", "all"),
             content.get("language", "en"),
             date.today().isoformat()),
        )
        await conn.commit()
        return cursor.lastrowid


async def get_library(tenant_id: int, page: int = 1, limit: int = 20) -> list[dict]:
    """Get paginated marketing content library for a tenant."""
    offset = (page - 1) * limit
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM marketing_content
               WHERE tenant_id = ?
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (tenant_id, limit, offset),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def mark_sent_wa_status(content_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE marketing_content SET sent_wa_status = 1 WHERE content_id = ?",
            (content_id,))
        await conn.commit()


async def mark_sent_tg(content_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE marketing_content SET sent_tg = 1 WHERE content_id = ?",
            (content_id,))
        await conn.commit()


async def get_content_by_id(content_id: int, tenant_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM marketing_content WHERE content_id = ? AND tenant_id = ?",
            (content_id, tenant_id))
        row = await cursor.fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
#  WhatsApp Status posting via Evolution API
# ---------------------------------------------------------------------------
async def post_to_wa_status(instance_name: str, image_path: str,
                            caption: str = "") -> dict:
    """
    Post an image to the advisor's WhatsApp Status (Story).
    Uses Evolution API POST /status/send/{instance}.
    """
    try:
        import biz_whatsapp_evolution as wa_evo
        return await wa_evo.send_status_image(instance_name, image_path, caption)
    except Exception as e:
        logger.error("WA Status post failed: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
#  Targeted DM: bulk send festival wishes to selected leads (rate-limited)
# ---------------------------------------------------------------------------
async def send_targeted_dm(
    instance_name: str,
    lead_phones: list[str],
    message: str,
    image_path: Optional[str] = None,
    delay_seconds: float = 4.0,
) -> dict:
    """
    Send a personalized WhatsApp DM to a list of leads (rate-limited).
    Returns {"sent": int, "failed": int, "errors": list}.
    Sends one message every `delay_seconds` to avoid spam detection.
    """
    import biz_whatsapp_evolution as wa_evo

    sent = 0
    failed = 0
    errors = []

    for phone in lead_phones:
        try:
            if image_path:
                # Build public URL for the image
                base_url = os.getenv("SARATHI_BASE_URL", "https://sarathi.in")
                media_url = f"{base_url}/{image_path}"
                result = await wa_evo.send_media(
                    instance_name, phone, media_url,
                    caption=message, media_type="image",
                )
            else:
                result = await wa_evo.send_text(instance_name, phone, message)

            if "error" in result:
                failed += 1
                errors.append({"phone": phone[-4:], "error": result["error"]})
            else:
                sent += 1
        except Exception as e:
            failed += 1
            errors.append({"phone": phone[-4:], "error": str(e)})

        # Rate limiting — pause between messages
        await asyncio.sleep(delay_seconds)

    return {"sent": sent, "failed": failed, "errors": errors}


# ---------------------------------------------------------------------------
#  Telegram push: send generated content to advisor's Telegram bot chat
# ---------------------------------------------------------------------------
async def push_to_telegram(agent_telegram_id: str, content: dict,
                           image_full_path: Optional[str] = None) -> bool:
    """Push generated content to the advisor's Telegram bot chat for review."""
    try:
        import biz_reminders as rem
        title = content.get("title", "")
        body = content.get("body_text", "")
        msg = f"📢 *New Marketing Content Ready*\n\n*{title}*\n\n{body}\n\n_Review and post when ready._"

        if image_full_path and Path(image_full_path).exists():
            # Send photo with caption
            import biz_reminders as rem
            await rem._send_telegram_photo(agent_telegram_id, image_full_path, caption=msg)
        else:
            await rem._send_telegram(agent_telegram_id, msg)
        return True
    except Exception as e:
        logger.warning("Telegram push for marketing failed: %s", e)
        return False


# ---------------------------------------------------------------------------
#  Templated video generation (Creatomate)  — Phase 1, paid external API
#  Renders a short branded video from a Creatomate template. Sits behind env
#  keys and degrades gracefully (clear error) when not configured. The cost is
#  contained by the per-plan video caps in DAILY_CAPS.
#  Setup (one-time, by the operator):
#    1. Create a video template in the Creatomate dashboard with named elements:
#       Title, Body, Image, Logo, Brand-Color.
#    2. Put CREATOMATE_API_KEY and CREATOMATE_TEMPLATE_ID in biz.env.
# ---------------------------------------------------------------------------
def video_configured() -> bool:
    return bool(os.getenv("CREATOMATE_API_KEY", "").strip()
                and os.getenv("CREATOMATE_TEMPLATE_ID", "").strip())


async def generate_video(tenant_id: int, title: str, body_text: str,
                         image_url: str = "", logo_url: str = "",
                         brand_accent: str = "", template_id: str = "",
                         timeout_s: int = 150) -> dict:
    """Render a branded short video via Creatomate.
    Returns {'video_path': str} on success or {'error': str, 'code': str}."""
    key = os.getenv("CREATOMATE_API_KEY", "").strip()
    tmpl = (template_id or os.getenv("CREATOMATE_TEMPLATE_ID", "")).strip()
    if not (key and tmpl):
        return {"error": "Video generation isn't set up yet.", "code": "not_configured"}

    modifications: dict = {"Title": title or "", "Body": body_text or ""}
    if image_url:   modifications["Image"] = image_url
    if logo_url:    modifications["Logo"] = logo_url
    if brand_accent: modifications["Brand-Color"] = brand_accent

    import httpx
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post("https://api.creatomate.com/v1/renders",
                                  headers=headers,
                                  json={"template_id": tmpl, "modifications": modifications})
            if r.status_code not in (200, 201, 202):
                return {"error": f"Creatomate error {r.status_code}: {r.text[:180]}"}
            data = r.json()
            render = data[0] if isinstance(data, list) and data else data
            render_id = render.get("id")
            status = render.get("status")
            url = render.get("url")

            waited = 0
            while status in ("planned", "waiting", "transcribing", "rendering") and waited < timeout_s:
                await asyncio.sleep(3); waited += 3
                pr = await client.get(f"https://api.creatomate.com/v1/renders/{render_id}", headers=headers)
                if pr.status_code == 200:
                    j = pr.json(); status = j.get("status"); url = j.get("url") or url
            if status != "succeeded" or not url:
                return {"error": f"Video render didn't finish in time (status={status}).", "code": "timeout"}

            video_dir = _BASE_DIR / "static" / "marketing" / "videos"
            video_dir.mkdir(parents=True, exist_ok=True)
            fname = f"v_{tenant_id}_{int(datetime.now().timestamp())}.mp4"
            dl = await client.get(url, timeout=120)
            (video_dir / fname).write_bytes(dl.content)
            return {"video_path": f"static/marketing/videos/{fname}", "render_id": render_id}
    except Exception as e:
        logger.error("Creatomate video failed: %s", e)
        return {"error": f"Video generation failed: {e}", "code": "exception"}


async def set_video_path(content_id: int, tenant_id: int, video_path: str) -> None:
    """Attach a rendered video to an existing content row (poster → video)."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE marketing_content SET video_path=? WHERE content_id=? AND tenant_id=?",
                (video_path, content_id, tenant_id))
            await conn.commit()
    except Exception as e:
        logger.error("set_video_path failed: %s", e)


# ---------------------------------------------------------------------------
#  Plan helpers
# ---------------------------------------------------------------------------
def can_generate_video(plan: str) -> bool:
    """Team and Enterprise plans can generate videos."""
    return plan in ("team", "team_annual", "enterprise", "enterprise_annual")


def has_watermark(plan: str) -> bool:
    """Enterprise plans can remove watermark."""
    return plan not in ("enterprise", "enterprise_annual")


# ---------------------------------------------------------------------------
#  Daily generation caps  (cost + server-load control)
#  Posters render locally (Pillow) ≈ free, so their caps are generous; videos
#  hit a paid external API, so their caps are tight. Usage is counted from the
#  existing marketing_content table (no extra table needed).
# ---------------------------------------------------------------------------
DAILY_CAPS = {
    "trial":             {"posters": 2,  "videos": 0},
    "individual":        {"posters": 4,  "videos": 0},
    "individual_annual": {"posters": 4,  "videos": 0},
    "team":              {"posters": 10, "videos": 2},
    "team_annual":       {"posters": 10, "videos": 2},
    "enterprise":        {"posters": 25, "videos": 5},
    "enterprise_annual": {"posters": 25, "videos": 5},
}


def caps_for(plan: str) -> dict:
    return DAILY_CAPS.get(plan, DAILY_CAPS["trial"])


async def daily_usage(tenant_id: int, day: Optional[str] = None) -> dict:
    """Count posters (image-only) and videos this tenant generated today."""
    if day is None:
        day = datetime.now().strftime("%Y-%m-%d")
    posters = videos = 0
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            async with conn.execute(
                "SELECT "
                "COALESCE(SUM(CASE WHEN video_path IS NULL OR video_path='' THEN 1 ELSE 0 END),0), "
                "COALESCE(SUM(CASE WHEN video_path IS NOT NULL AND video_path<>'' THEN 1 ELSE 0 END),0) "
                "FROM marketing_content WHERE tenant_id=? AND generated_date=?",
                (tenant_id, day)) as cur:
                row = await cur.fetchone()
                if row:
                    posters, videos = int(row[0] or 0), int(row[1] or 0)
    except Exception as e:
        logger.error("daily_usage failed: %s", e)
    return {"posters": posters, "videos": videos}


async def check_daily_cap(tenant_id: int, plan: str, want_video: bool) -> dict:
    """Gate a generation request against the plan's daily cap.
    Returns {allowed, reason, remaining{posters,videos}, caps, used}."""
    caps = caps_for(plan)
    used = await daily_usage(tenant_id)
    kind = "videos" if want_video else "posters"
    limit = int(caps.get(kind, 0))
    allowed = used.get(kind, 0) < limit
    reason = ""
    if not allowed:
        if want_video and limit == 0:
            reason = "Video generation isn't included in your plan — upgrade to Team or Enterprise."
        else:
            reason = f"You've used today's {limit} {kind}. Come back tomorrow, or upgrade for a higher daily limit."
    remaining = {k: max(0, int(caps.get(k, 0)) - used.get(k, 0)) for k in ("posters", "videos")}
    return {"allowed": allowed, "reason": reason, "remaining": remaining,
            "caps": caps, "used": used}


# ---------------------------------------------------------------------------
#  Daily Auto-Post Scheduler
# ---------------------------------------------------------------------------
async def run_marketing_auto_post(now: Optional[datetime] = None) -> int:
    """
    Called every minute from the scheduler loop.
    For each tenant with auto-post enabled, checks whether the current time
    falls within their configured posting window (5-min tolerance) and, if
    they haven't already posted today, generates + pushes to WA Status.

    Returns the number of posts successfully sent.
    """
    if now is None:
        now = datetime.now()

    today_str = now.strftime("%Y-%m-%d")
    current_minutes = now.hour * 60 + now.minute
    sent_count = 0

    # Only scan during daylight hours to avoid spurious runs
    if not (6 <= now.hour <= 22):
        return 0

    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            # Fetch tenants + their primary connected WA instance + owner telegram
            async with conn.execute("""
                SELECT
                    t.tenant_id, t.firm_name AS name, t.plan,
                    t.marketing_lang, t.marketing_festival_prefs,
                    t.marketing_autopost_time, t.marketing_photo_path,
                    t.marketing_logo_path,
                    t.marketing_watermark, t.owner_telegram_id,
                    (SELECT evolution_instance FROM wa_instances
                     WHERE tenant_id = t.tenant_id AND status = 'connected'
                     ORDER BY instance_id LIMIT 1) AS evolution_instance
                FROM tenants t
                WHERE t.marketing_enabled = 1
                  AND t.marketing_autopost_enabled = 1
            """) as cur:
                tenants = [dict(r) for r in await cur.fetchall()]
    except Exception as e:
        logger.error("Auto-post: failed to fetch tenants: %s", e)
        return 0

    for tenant in tenants:
        tenant_id = tenant["tenant_id"]
        try:
            # ── Time-window check ──────────────────────────────────────
            time_str = (tenant.get("marketing_autopost_time") or "08:00").strip()
            try:
                h, m = map(int, time_str.split(":"))
                target_minutes = h * 60 + m
            except Exception:
                target_minutes = 8 * 60  # default 08:00

            if not (target_minutes <= current_minutes < target_minutes + 5):
                continue  # not time yet for this tenant

            # ── Duplicate guard ────────────────────────────────────────
            async with aiosqlite.connect(DB_PATH) as conn:
                async with conn.execute(
                    "SELECT COUNT(*) FROM marketing_content "
                    "WHERE tenant_id = ? AND generated_date = ? AND sent_wa_status = 1",
                    (tenant_id, today_str),
                ) as cur:
                    row = await cur.fetchone()
                    already_sent = (row[0] if row else 0) > 0

            if already_sent:
                logger.info("Auto-post: tenant %d already posted today — skip", tenant_id)
                continue

            # ── Pick content type ──────────────────────────────────────
            prefs = json.loads(tenant.get("marketing_festival_prefs") or '["all","hindu"]')
            festivals_today = get_festivals_for_date(now.date(), prefs)

            if festivals_today:
                festival = festivals_today[0]
                content_type = "festival"
            else:
                # Rotate content type by weekday so it varies daily
                content_types = [
                    "scenario_insurance", "tip", "scenario_investment",
                    "tip", "product_pitch", "tip", "scenario_insurance",
                ]
                content_type = content_types[now.weekday()]
                festival = None

            lang = tenant.get("marketing_lang") or "en"
            tenant_name = tenant.get("name") or "Sarathi"

            logger.info("Auto-post: generating '%s' for tenant %d (%s)", content_type, tenant_id, tenant_name)

            # ── Generate content ───────────────────────────────────────
            content = await generate_content(
                tenant_id=tenant_id,
                content_type=content_type,
                lang=lang,
                festival=festival,
                firm_name=tenant_name,
                marketing_photo_path=tenant.get("marketing_photo_path") or "",
                marketing_logo_path=tenant.get("marketing_logo_path") or "",
                watermark=bool(tenant.get("marketing_watermark", 1)),
            )

            if not content or not content.get("content_id"):
                logger.warning("Auto-post: content generation failed for tenant %d", tenant_id)
                continue

            # ── Post to WhatsApp Status ────────────────────────────────
            instance = tenant.get("evolution_instance") or ""
            if instance and content.get("image_path"):
                caption = f"{content['title']}\n\n{content['body_text'][:300]}"
                ok = await post_to_wa_status(instance, content["image_path"], caption)
                if ok:
                    await mark_sent_wa_status(content["content_id"])
                    sent_count += 1
                    logger.info("Auto-post: tenant %d → WA Status ✓", tenant_id)
                else:
                    logger.warning("Auto-post: WA Status send failed for tenant %d", tenant_id)
            else:
                logger.warning("Auto-post: no connected WA instance or image for tenant %d", tenant_id)

            # ── Push to Telegram for review (non-blocking) ─────────────
            tg_id = str(tenant.get("owner_telegram_id") or "").strip()
            if tg_id and content.get("image_path"):
                image_full = str(MARKETING_DIR / content["image_path"])
                try:
                    await push_to_telegram(tg_id, content, image_full)
                except Exception:
                    pass  # Telegram is best-effort

        except Exception as e:
            logger.error("Auto-post: error for tenant %d: %s", tenant_id, e, exc_info=True)

    return sent_count


# ---------------------------------------------------------------------------
#  Phase 2 — Off-peak daily batch pre-generation (server-load smoothing)
#  Runs once in the early morning: pre-generates each enabled tenant's daily
#  poster SERIALLY (no concurrency spike) and pushes it to their Telegram for
#  review. Own-number WhatsApp delivery stays on-demand from the dashboard.
# ---------------------------------------------------------------------------
async def run_marketing_daily_batch(now: Optional[datetime] = None) -> int:
    """Pre-generate the day's poster for every marketing-enabled tenant, one at
    a time (load-safe). Skips tenants who already have content today and any who
    are over their daily cap. Returns how many were generated."""
    if now is None:
        now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    made = 0
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            async with conn.execute("""
                SELECT t.tenant_id, t.firm_name AS name, t.plan, t.marketing_lang,
                       t.marketing_festival_prefs, t.marketing_photo_path,
                       t.marketing_logo_path, t.marketing_watermark,
                       t.owner_telegram_id, t.brand_accent
                FROM tenants t
                WHERE t.marketing_enabled = 1 AND t.marketing_autopost_enabled = 1
            """) as cur:
                tenants = [dict(r) for r in await cur.fetchall()]
    except Exception as e:
        logger.error("Daily batch: fetch tenants failed: %s", e)
        return 0

    for tenant in tenants:
        tid = tenant["tenant_id"]
        try:
            # Skip if anything was already generated today (dedupe vs on-demand / auto-post).
            used = await daily_usage(tid, today_str)
            if (used.get("posters", 0) + used.get("videos", 0)) > 0:
                continue
            plan = tenant.get("plan") or "trial"
            cap = await check_daily_cap(tid, plan, want_video=False)
            if not cap["allowed"]:
                continue

            # Festival-aware content type, else rotate by weekday so it varies.
            try:
                prefs = json.loads(tenant.get("marketing_festival_prefs") or '["all","hindu"]')
            except Exception:
                prefs = ["all", "hindu"]
            fests = get_festivals_for_date(now.date(), prefs)
            if fests:
                festival, ctype = fests[0], "festival"
            else:
                rot = ["scenario_insurance", "tip", "scenario_investment",
                       "tip", "product_pitch", "tip", "scenario_insurance"]
                ctype, festival = rot[now.weekday()], None

            content = await generate_content(
                tenant_id=tid, content_type=ctype,
                lang=tenant.get("marketing_lang") or "en", festival=festival,
                firm_name=tenant.get("name") or "Sarathi",
                marketing_photo_path=tenant.get("marketing_photo_path") or "",
                marketing_logo_path=tenant.get("marketing_logo_path") or "",
                watermark=bool(tenant.get("marketing_watermark", 1)),
                brand_accent=tenant.get("brand_accent") or "")
            if not content or not content.get("image_path"):
                continue
            await save_content(tid, content)
            made += 1

            tg = str(tenant.get("owner_telegram_id") or "").strip()
            if tg and content.get("image_path"):
                try:
                    await push_to_telegram(tg, content, str(_BASE_DIR / content["image_path"]))
                except Exception:
                    pass  # best-effort
        except Exception as e:
            logger.error("Daily batch: tenant %d failed: %s", tid, e)
        await asyncio.sleep(2)  # spread the load across the morning window

    if made:
        logger.info("Daily batch: pre-generated %d daily posters", made)
    return made


# ---------------------------------------------------------------------------
#  Phase 2 — Marketing analytics (for the dashboard stats panel)
# ---------------------------------------------------------------------------
async def get_marketing_stats(tenant_id: int) -> dict:
    """Return generation/delivery counts for the analytics panel."""
    stats = {"generated_total": 0, "generated_30d": 0, "videos_total": 0,
             "sent_wa_status": 0, "sent_tg": 0, "sent_dm": 0,
             "by_type": [], "last7": []}
    try:
        from datetime import timedelta
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            d30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            async with conn.execute(
                "SELECT "
                "COUNT(*) AS total, "
                "COALESCE(SUM(CASE WHEN video_path IS NOT NULL AND video_path<>'' THEN 1 ELSE 0 END),0) AS vids, "
                "COALESCE(SUM(sent_wa_status),0) AS wa, COALESCE(SUM(sent_tg),0) AS tg, "
                "COALESCE(SUM(CASE WHEN generated_date >= ? THEN 1 ELSE 0 END),0) AS d30 "
                "FROM marketing_content WHERE tenant_id=?", (d30, tenant_id)) as cur:
                r = await cur.fetchone()
                if r:
                    stats["generated_total"] = int(r["total"] or 0)
                    stats["videos_total"] = int(r["vids"] or 0)
                    stats["sent_wa_status"] = int(r["wa"] or 0)
                    stats["sent_tg"] = int(r["tg"] or 0)
                    stats["generated_30d"] = int(r["d30"] or 0)
            # By content type
            async with conn.execute(
                "SELECT content_type, COUNT(*) AS n FROM marketing_content "
                "WHERE tenant_id=? GROUP BY content_type ORDER BY n DESC LIMIT 8", (tenant_id,)) as cur:
                stats["by_type"] = [{"type": row["content_type"], "n": int(row["n"])} for row in await cur.fetchall()]
            # Last 7 days series
            for i in range(6, -1, -1):
                day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                async with conn.execute(
                    "SELECT COUNT(*) FROM marketing_content WHERE tenant_id=? AND generated_date=?",
                    (tenant_id, day)) as cur:
                    row = await cur.fetchone()
                    stats["last7"].append({"date": day[5:], "n": int(row[0] or 0) if row else 0})
            # DM sends (best-effort; table may not exist on older installs)
            try:
                async with conn.execute(
                    "SELECT COUNT(*) FROM marketing_sends WHERE tenant_id=?", (tenant_id,)) as cur:
                    row = await cur.fetchone()
                    stats["sent_dm"] = int(row[0] or 0) if row else 0
            except Exception:
                pass
    except Exception as e:
        logger.error("get_marketing_stats failed: %s", e)
    return stats
