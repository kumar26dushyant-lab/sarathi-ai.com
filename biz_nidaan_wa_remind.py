# -*- coding: utf-8 -*-
"""The complainant chooses when we remind them about documents - on WhatsApp.

Founder, 29 Sep: "if user is busy so we can ask for time and our smart bot nudge them on that
time for documents ... user share details (our bot should understand the details well), if
details are not clear then our bot should nudge user for more clarity and nudging schedule
confirmation ... keep it simple."

So, three steps and no cleverness:

  1. UNDERSTAND. "kal shaam 7 baje", "Sunday 10am", "रविवार सुबह", "2 ghante baad" - read here,
     locally, by rules. No AI: a reply on a claim is the complainant's words, and they stay on
     our server.
  2. ASK WHEN UNCLEAR. A day with no time, a time at 3am, a date two months out: we ask again, in
     their language, with an example. Twice unclear and a person takes over - the bot does not
     argue with somebody about their own calendar.
  3. CONFIRM BEFORE BOOKING. "I'll remind you on Sunday 4 Oct, 10:00 am - reply YES." Only a yes
     books it, and it is booked into the SAME schedule staff use (biz_nidaan_wa_schedule), so it
     stops by itself when the documents arrive, goes through the same caps and STOP list, falls
     back to the approved template past the 24-hour window, and nudges a person when it fires.

It is OFF until a super-admin turns it on (WhatsApp panel), because it answers inside the live
conversation - and nothing new speaks to complainants unannounced.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.wa.remind")

DB_PATH = db.DB_PATH
IST = timezone(timedelta(hours=5, minutes=30))
SETTING = "wa_remind_ask_enabled"
MAX_DAYS_AHEAD = 30          # further than this, the documents matter more than the calendar
STATE_HOURS = 24             # an offer or a question older than this is forgotten
MAX_UNCLEAR = 2              # then a person takes over
BY_NAME = "Complainant (WhatsApp)"

# ── the words ────────────────────────────────────────────────────────────────
_WEEKDAYS = [
    # Monday = 0, as datetime.weekday()
    ("monday", "mon", "somvar", "somwar", "सोमवार"),
    ("tuesday", "tue", "tues", "mangalvar", "mangalwar", "मंगलवार"),
    ("wednesday", "wed", "budhvar", "budhwar", "बुधवार"),
    ("thursday", "thu", "thur", "thurs", "guruvar", "guruwar", "brihaspativar", "गुरुवार",
     "बृहस्पतिवार"),
    ("friday", "fri", "shukravar", "shukrawar", "शुक्रवार"),
    ("saturday", "sat", "shanivar", "shaniwar", "शनिवार"),
    ("sunday", "sun", "ravivar", "raviwar", "itwar", "itvaar", "itwaar", "रविवार", "इतवार"),
]
_DAY_WORD = {w: i for i, names in enumerate(_WEEKDAYS) for w in names}
_REL_DAY = {"aaj": 0, "aj": 0, "today": 0, "आज": 0,
            "kal": 1, "tomorrow": 1, "tmrw": 1, "tmr": 1, "कल": 1,
            "parso": 2, "parson": 2, "परसों": 2, "परसो": 2}
# Part of the day: (default hour, the hours that mean pm when said with it)
_PART = {
    "subah": (10, "am"), "morning": (10, "am"), "सुबह": (10, "am"), "savere": (10, "am"),
    "dopahar": (14, "pm"), "dopaher": (14, "pm"), "afternoon": (14, "pm"), "दोपहर": (14, "pm"),
    "shaam": (18, "pm"), "sham": (18, "pm"), "evening": (18, "pm"), "शाम": (18, "pm"),
    "raat": (20, "pm"), "rat": (20, "pm"), "night": (20, "pm"), "रात": (20, "pm"),
}
_INTENT = re.compile(
    r"remind|reminder|yaad|याद|busy|बिज़ी|बिजी|later|baad\s*m(e|ein|ai)|बाद\s*में|"
    r"abhi\s*nahi|अभी\s*नहीं|time\s*nahi|free\s*ho|फ्री", re.I)
_YES = {"haan", "han", "ha", "haa", "hn", "hanji", "haanji", "yes", "y", "yep", "ok", "okay",
        "okk", "theek", "thik", "theekhai", "thikhai", "sahi", "ji", "done", "confirm", "pakka",
        "हाँ", "हां", "हा", "जी", "ठीक", "सही", "पक्का", "👍"}
_NO = {"nahi", "nahin", "no", "na", "nope", "galat", "cancel", "नहीं", "ना", "गलत", "नही"}
# Words that may sit around a time without meaning anything else.
_FILLER = {"ko", "pe", "par", "me", "mein", "baje", "bje", "please", "pls", "plz", "ji", "sir",
           "madam", "mam", "mujhe", "muje", "karna", "kar", "dena", "do", "dijiye", "dijie",
           "dilana", "dilaye", "dila", "dilaiye", "at", "on", "by", "the", "next", "agle",
           "agla", "is", "iss", "this", "around", "lagbhag", "tak", "ke", "ki", "ka", "se",
           "baad", "o'clock", "oclock", "clock", "hours", "hour", "ghante", "ghanta", "min",
           "mins", "minute", "minutes", "in", "after", "bajkar", "bajke", "time", "samay",
           "को", "पे", "पर", "में", "बजे", "जी", "मुझे", "दीजिए", "दिलाइए", "तक", "के", "की",
           "का", "से", "बाद", "घंटे", "मिनट", "अगले", "इस", "समय", "टाइम", "and", "aur", "और",
           "am", "pm", "a.m.", "p.m.", "hi", "hello", "namaste", "नमस्ते"}


def _norm(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[,!?;\"'()\[\]]+", " ", t)
    return " ".join(t.split())[:300]


def _is(text: str, words: set) -> bool:
    t = _norm(text).replace(" ", "")
    if t in words:
        return True
    toks = _norm(text).split()
    return bool(toks) and len(toks) <= 4 and toks[0] in words


def is_yes(text: str) -> bool:
    return _is(text, _YES) and not _is(text, _NO)


def is_no(text: str) -> bool:
    return _is(text, _NO)


def has_intent(text: str) -> bool:
    return bool(_INTENT.search(text or ""))


# ── understanding a time ─────────────────────────────────────────────────────
def parse_when(text: str, now: Optional[datetime] = None) -> dict:
    """What moment does this reply name? Pure - `now` is IST and can be supplied by a test.

    Returns {"kind": ...}:
      "at"        {"at": datetime IST}         - a clear moment
      "need_time" {"day": date}                - a day, but no time ("Sunday")
      "none"                                   - no day and no time in it at all
    `words` counts what is left once the time words are taken out, so a caller can tell
    "Sunday 10 baje" (all time) from a sentence that merely mentions a day.
    """
    now = now or datetime.now(IST)
    t = _norm(text)
    toks = t.split()
    used = set()

    # Relative: "2 ghante baad", "in 3 hours", "30 min", "2 घंटे बाद"
    # (?<!\d): "1000 hours" must not be read as "000 hours".
    m = re.search(r"(?<!\d)(\d{1,4})\s*(ghante|ghanta|hours?|hrs?|घंटे|घंटा)(?![a-z])", t)
    if m:
        return {"kind": "at", "at": (now + timedelta(hours=int(m.group(1)))).replace(second=0,
                                                                                    microsecond=0),
                "words": _left(toks, m.group(0))}
    m = re.search(r"(?<!\d)(\d{1,4})\s*(min|mins|minutes?|minat|मिनट)(?![a-z])", t)
    if m:
        return {"kind": "at", "at": (now + timedelta(minutes=int(m.group(1)))).replace(
            second=0, microsecond=0), "words": _left(toks, m.group(0))}

    # The day
    day_offset, weekday = None, None
    for i, w in enumerate(toks):
        if w in _REL_DAY and day_offset is None:
            day_offset = _REL_DAY[w]
            used.add(i)
        elif w in _DAY_WORD and weekday is None:
            weekday = _DAY_WORD[w]
            used.add(i)
    if "day after tomorrow" in t:
        day_offset = 2

    # The part of the day
    part = None
    for i, w in enumerate(toks):
        if w in _PART:
            part = _PART[w]
            used.add(i)
            break

    # The hour: "10:30", "10.30", "7pm", "7 pm", "7 baje", "7 बजे"
    hour = minute = None
    ampm = None
    m = (re.search(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", t)
         or re.search(r"\b(\d{1,2})\s*(am|pm|a\.m\.|p\.m\.)", t)
         or re.search(r"\b(\d{1,2})\s*(baje|bje|बजे|o'?clock)", t))
    if m:
        hour = int(m.group(1))
        g2 = m.group(2) if m.lastindex and m.lastindex >= 2 else None
        if g2 and g2.isdigit():
            minute = int(g2)
            ampm = (m.group(3) or "").replace(".", "") or None
        elif g2 and g2.replace(".", "") in ("am", "pm"):
            ampm = g2.replace(".", "")
        minute = minute or 0
        if hour > 23 or minute > 59:
            hour = minute = None
    elif part is None:
        # A bare number next to a day ("Sunday 10") is an hour.
        m2 = re.search(r"\b(\d{1,2})\b", t) if (day_offset is not None or weekday is not None) \
            else None
        if m2 and 1 <= int(m2.group(1)) <= 12:
            hour, minute = int(m2.group(1)), 0

    if hour is not None:
        if ampm == "pm" and hour < 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        elif ampm is None and hour <= 12:
            if part and part[1] == "pm" and hour < 12:
                # "shaam 7" is 19:00, "dopahar 2" is 14:00, "raat 9" is 21:00 - but "dopahar 12"
                # is noon.
                hour = hour + 12 if hour < 12 else hour
            elif part is None and 1 <= hour <= 7:
                hour += 12            # "7 baje" said about documents means evening, not 7am
    elif part is not None:
        hour, minute = part[0], 0

    has_day = day_offset is not None or weekday is not None
    if hour is None and not has_day:
        return {"kind": "none", "words": len(toks)}

    # Which date
    if day_offset is not None:
        date = (now + timedelta(days=day_offset)).date()
    elif weekday is not None:
        ahead = (weekday - now.weekday()) % 7
        date = (now + timedelta(days=ahead)).date()
    else:
        date = now.date()

    if hour is None:
        return {"kind": "need_time", "day": date, "words": _left_idx(toks, used)}

    at = datetime(date.year, date.month, date.day, hour, minute or 0, tzinfo=IST)
    if at <= now:
        # "7 baje" said at 8pm means tomorrow; "Sunday 10am" said on Sunday at noon means next week
        at += timedelta(days=7 if (weekday is not None and day_offset is None) else 1)
    return {"kind": "at", "at": at, "words": _left_idx(toks, used, drop_numbers=True)}


def _left(toks: list, matched: str) -> int:
    rest = [w for w in toks if w not in matched.split() and w not in _FILLER]
    return len(rest)


def _left_idx(toks: list, used: set, drop_numbers: bool = True) -> int:
    rest = []
    for i, w in enumerate(toks):
        if i in used or w in _FILLER or w in _PART:
            continue
        if drop_numbers and re.fullmatch(r"[\d:.]+(am|pm)?", w):
            continue
        rest.append(w)
    return len(rest)


# ── what we say ──────────────────────────────────────────────────────────────
_WD = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "hinglish": ["Somvar", "Mangalvar", "Budhvar", "Guruvar", "Shukravar", "Shanivar", "Ravivar"],
    "hi": ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"],
}
_MON = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "hinglish": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov",
                 "Dec"],
    "hi": ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर",
           "नवंबर", "दिसंबर"],
}


def _lang(l: Optional[str]) -> str:
    l = (l or "hinglish").strip().lower()
    return l if l in ("hinglish", "hi", "en") else "hinglish"


def say_when(at: datetime, lang: str) -> str:
    """'Sunday 4 Oct, 10:00 am' / 'Ravivar 4 Oct, subah 10:00 baje' / 'रविवार 4 अक्टूबर, सुबह 10:00 बजे'."""
    l = _lang(lang)
    at = at.astimezone(IST)
    day = "%s %d %s" % (_WD[l][at.weekday()], at.day, _MON[l][at.month - 1])
    h, mi = at.hour, at.minute
    if l == "en":
        return "%s, %d:%02d %s" % (day, (h % 12) or 12, mi, "am" if h < 12 else "pm")
    part = ("subah" if h < 12 else "dopahar" if h < 16 else "shaam" if h < 20 else "raat")
    part_hi = {"subah": "सुबह", "dopahar": "दोपहर", "shaam": "शाम", "raat": "रात"}[part]
    h12 = (h % 12) or 12
    if l == "hi":
        return "%s, %s %d:%02d बजे" % (day, part_hi, h12, mi)
    return "%s, %s %d:%02d baje" % (day, part, h12, mi)


def text(kind: str, lang: str, **kw) -> str:
    l = _lang(lang)
    T = {
        "ask": {
            "hinglish": ("Zaroor 🙏 Kab yaad dilaun? Din aur samay likhiye — jaise *kal shaam 7 "
                         "baje* ya *Ravivar subah 10 baje*."),
            "hi": ("ज़रूर 🙏 कब याद दिलाऊँ? दिन और समय लिखिए — जैसे *कल शाम 7 बजे* या *रविवार सुबह "
                   "10 बजे*।"),
            "en": ("Of course 🙏 When should I remind you? Write a day and a time — like "
                   "*tomorrow 7 pm* or *Sunday 10 am*."),
        },
        "need_time": {
            "hinglish": "Theek hai 🙏 Us din kitne baje yaad dilaun? Jaise *subah 10 baje* ya *shaam 7 baje*.",
            "hi": "ठीक है 🙏 उस दिन कितने बजे याद दिलाऊँ? जैसे *सुबह 10 बजे* या *शाम 7 बजे*।",
            "en": "Sure 🙏 What time that day? Like *10 am* or *7 pm*.",
        },
        "quiet": {
            "hinglish": ("Itni raat ya itni subah hum message nahi bhejte 🙏 Subah %d se raat %d "
                         "ke beech ka koi samay bataiye." % (kw.get("start", 8), (kw.get("end", 21) % 12) or 12)),
            "hi": ("इतनी रात या इतनी सुबह हम मैसेज नहीं भेजते 🙏 सुबह %d से रात %d के बीच का कोई समय "
                   "बताइए।" % (kw.get("start", 8), (kw.get("end", 21) % 12) or 12)),
            "en": ("We do not message that late or that early 🙏 Please pick a time between %d am "
                   "and %d pm." % (kw.get("start", 8), (kw.get("end", 21) % 12) or 12)),
        },
        "too_far": {
            "hinglish": ("Itna aage ka reminder nahi rakh sakte 🙏 Agle %d din mein koi din "
                         "bataiye — documents jitni jaldi aayenge, aapka case utna jaldi "
                         "*fast-track* hoga." % MAX_DAYS_AHEAD),
            "hi": ("इतना आगे का रिमाइंडर नहीं रख सकते 🙏 अगले %d दिन में कोई दिन बताइए — दस्तावेज़ "
                   "जितनी जल्दी आएँगे, आपका केस उतनी जल्दी *फ़ास्ट-ट्रैक* होगा।" % MAX_DAYS_AHEAD),
            "en": ("That is too far ahead for a reminder 🙏 Please pick a day in the next %d days "
                   "— the sooner the documents come, the sooner your case is *fast-tracked*."
                   % MAX_DAYS_AHEAD),
        },
        "propose": {
            "hinglish": ("Main aapko *%s* ko yaad dilaunga. Sahi hai to *HAAN* likhiye, ya "
                         "doosra samay bataiye." % kw.get("when", "")),
            "hi": ("मैं आपको *%s* याद दिलाऊँगा। सही है तो *हाँ* लिखिए, या दूसरा समय बताइए।"
                   % kw.get("when", "")),
            "en": ("I will remind you on *%s*. Reply *YES* if that is right, or tell me another "
                   "time." % kw.get("when", "")),
        },
        "booked": {
            "hinglish": ("✅ Pakka. *%s* ko main aapko documents ke liye yaad dilaunga. Tab tak jo "
                         "document ready ho, yahin bhej sakte hain — aapka case *fast-track* "
                         "rahega. 🙏" % kw.get("when", "")),
            "hi": ("✅ पक्का। *%s* मैं आपको दस्तावेज़ों के लिए याद दिलाऊँगा। तब तक जो दस्तावेज़ तैयार हो, "
                   "यहीं भेज सकते हैं — आपका केस *फ़ास्ट-ट्रैक* रहेगा। 🙏" % kw.get("when", "")),
            "en": ("✅ Done. I will remind you about the documents on *%s*. Until then, send "
                   "anything that is ready right here — it keeps your case *fast-tracked*. 🙏"
                   % kw.get("when", "")),
        },
        "declined": {
            "hinglish": "Koi baat nahi 🙏 Kab yaad dilaun? Din aur samay likhiye.",
            "hi": "कोई बात नहीं 🙏 कब याद दिलाऊँ? दिन और समय लिखिए।",
            "en": "No problem 🙏 When should I remind you? Write a day and a time.",
        },
        "give_up": {
            "hinglish": "Main theek se samajh nahi paaya 🙏 Hamari team aapse khud baat karke samay tay kar legi.",
            "hi": "मैं ठीक से समझ नहीं पाया 🙏 हमारी टीम आपसे ख़ुद बात करके समय तय कर लेगी।",
            "en": "I did not quite understand 🙏 Our team will talk to you and set the time.",
        },
        "failed": {
            "hinglish": "Abhi reminder set nahi ho paaya 🙏 Hamari team aapse sampark karegi.",
            "hi": "अभी रिमाइंडर सेट नहीं हो पाया 🙏 हमारी टीम आपसे संपर्क करेगी।",
            "en": "I could not set the reminder just now 🙏 Our team will contact you.",
        },
        # The line added to the bot's document ask, so people know they can say "later".
        "offer": {
            "hinglish": "⏰ Abhi busy hain? Bas likhiye kab yaad dilaun — jaise *Ravivar subah 10 baje*.",
            "hi": "⏰ अभी व्यस्त हैं? बस लिखिए कब याद दिलाऊँ — जैसे *रविवार सुबह 10 बजे*।",
            "en": "⏰ Busy right now? Just tell me when to remind you — like *Sunday 10 am*.",
        },
    }
    return T[kind][l]


# ── state: what we last asked this number ────────────────────────────────────
async def enabled() -> bool:
    try:
        import biz_nidaan as _n
        return str(await _n.get_ops_setting(SETTING, "0")) in ("1", "true", "True")
    except Exception:  # noqa: BLE001 - unreadable means off: nothing new speaks unannounced
        return False


async def _get(msisdn: str) -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT * FROM nidaan_wa_remind_state WHERE msisdn=? AND state IN "
                "('asked','proposed') AND updated_at > datetime('now', ?)",
                (msisdn, "-%d hours" % STATE_HOURS))).fetchone()
        return dict(r) if r else {}
    except Exception as e:  # noqa: BLE001
        logger.info("remind state unreadable for a number: %s", e)
        return {}


async def _put(msisdn: str, claim_id: int, state: str, proposed_utc: str = "",
               tries: int = 0) -> None:
    """One row per number, updated in place - finished states are kept, never deleted."""
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "INSERT INTO nidaan_wa_remind_state (msisdn, claim_id, state, proposed_utc, tries, "
            "updated_at) VALUES (?,?,?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(msisdn) DO UPDATE SET "
            "claim_id=excluded.claim_id, state=excluded.state, "
            "proposed_utc=excluded.proposed_utc, tries=excluded.tries, "
            "updated_at=CURRENT_TIMESTAMP",
            (msisdn, int(claim_id), state[:20], (proposed_utc or "")[:25], int(tries)))
        await c.commit()


async def _quiet_hours() -> tuple:
    try:
        import biz_nidaan as _n
        return (int(await _n.get_ops_setting("wa_quiet_end_ist", "8")),
                int(await _n.get_ops_setting("wa_quiet_start_ist", "21")))
    except Exception:  # noqa: BLE001
        return 8, 21


async def _book(claim_id: int, at_utc: str) -> dict:
    """Into the same schedule staff use, replacing an earlier one the complainant set."""
    import biz_nidaan_wa_schedule as sch
    at = datetime.strptime(at_utc, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).astimezone(IST)
    try:
        for s in await sch.listing(claim_id):
            if s.get("status") == "active" and s.get("created_by_name") == BY_NAME:
                await sch.set_status(s["sch_id"], "cancelled", by=BY_NAME)
    except Exception as e:  # noqa: BLE001
        logger.info("claim %s: could not retire an earlier complainant reminder: %s", claim_id, e)
    return await sch.create(claim_id, when_date=at.strftime("%Y-%m-%d"),
                            when_time=at.strftime("%H:%M"), repeat="once",
                            note="", by=BY_NAME, by_id=None)


# ── the conversation ─────────────────────────────────────────────────────────
async def handle(msisdn: str, claim_id: int, text_in: str, lang: str,
                 now: Optional[datetime] = None) -> Optional[str]:
    """The reply, if this message is about WHEN to be reminded. None means "not ours" - the
    normal conversation carries on as if this module did not exist.

    Only called where the charter allows asking for documents, and only when switched on.
    """
    now = now or datetime.now(IST)
    try:
        import biz_nidaan_wa_flow as _flow
        if _norm(text_in) in _flow._STOP_WORDS:
            return None
    except Exception:  # noqa: BLE001
        pass
    st = await _get(msisdn)
    state = st.get("state") or ""
    tries = int(st.get("tries") or 0)
    parsed = parse_when(text_in, now)

    # Waiting for a yes to a time we proposed.
    if state == "proposed":
        if is_yes(text_in) and st.get("proposed_utc"):
            if st["proposed_utc"] <= now.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"):
                await _put(msisdn, claim_id, "asked", tries=0)
                return text("ask", lang)
            res = await _book(claim_id, st["proposed_utc"])
            if not res.get("ok"):
                await _put(msisdn, claim_id, "failed")
                return text("failed", lang)
            await _put(msisdn, claim_id, "booked", st["proposed_utc"])
            at = datetime.strptime(st["proposed_utc"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc)
            return text("booked", lang, when=say_when(at, lang))
        if is_no(text_in) and parsed["kind"] == "none":
            await _put(msisdn, claim_id, "asked", tries=0)
            return text("declined", lang)
        if parsed["kind"] == "none":
            # Something else entirely. Do not trap them in our question: forget it and let the
            # ordinary conversation answer.
            await _put(msisdn, claim_id, "dropped")
            return None
        # Otherwise they gave another time - fall through and propose that one instead.

    ours = state in ("asked", "proposed") or has_intent(text_in) or (
        parsed["kind"] != "none" and parsed.get("words", 99) <= 1)
    if not ours:
        return None

    if parsed["kind"] == "none":
        if state == "asked" and not has_intent(text_in) and len(_norm(text_in).split()) > 3:
            await _put(msisdn, claim_id, "dropped")
            return None
        if state == "asked":
            tries += 1
            if tries >= MAX_UNCLEAR:
                await _put(msisdn, claim_id, "gave_up", tries=tries)
                return text("give_up", lang)
            await _put(msisdn, claim_id, "asked", tries=tries)
            return text("ask", lang)
        if has_intent(text_in):
            await _put(msisdn, claim_id, "asked", tries=0)
            return text("ask", lang)
        return None

    if parsed["kind"] == "need_time":
        await _put(msisdn, claim_id, "asked", tries=tries)
        return text("need_time", lang)

    at = parsed["at"]
    # The bigger problem first: a date six weeks out is wrong whatever the hour.
    if at > now + timedelta(days=MAX_DAYS_AHEAD):
        await _put(msisdn, claim_id, "asked", tries=tries)
        return text("too_far", lang)
    start, end = await _quiet_hours()
    if not (start <= at.hour < end):
        await _put(msisdn, claim_id, "asked", tries=tries)
        return text("quiet", lang, start=start, end=end)
    if at < now + timedelta(minutes=10):
        at = now + timedelta(minutes=10)
    at_utc = at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    await _put(msisdn, claim_id, "proposed", at_utc, tries=tries)
    return text("propose", lang, when=say_when(at, lang))
