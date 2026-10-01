# -*- coding: utf-8 -*-
"""What every customer-facing bot says while a person is not yet on the conversation.

Founder, 1 Oct: "when any customer/complainant facing bot - homepage bot, dashboard bot, whatsapp
automation bot - if human is not available between 6pm to next day 10 am or within office hours,
our bot should message ... our office timings are 10am to 6pm IST, someone will connect with you
from our team, we appreciate your patience ... instead of transferring to human and leave it as it
is ... last message should be from our bot ... for any unnecessary discussion our bot should say
about office timings and ensure someone will reach out, this message 3 times if user is not okay
to leave the chat and then silent."

One module, so the homepage chat, the dashboard chat and WhatsApp say the same thing:

  * the office hours come from the Support screen setting (biz_nidaan.get_business_hours) - one
    place to change them, never written into a sentence;
  * out of hours the message says we are closed and WHEN someone will reach out (today at 10 am,
    tomorrow, on Monday); in hours it says someone will reach out shortly;
  * at most MAX_HOLDS messages per waiting conversation, and not two within a minute (a burst of
    messages gets one answer). After that the bot is silent - the conversation is not lost, the
    person on duty has it. The count starts again when a person from our team replies.

Not a claim-status channel: the message never mentions a claim, an amount or a document.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.bot_hold")
DB_PATH = db.DB_PATH
IST = timezone(timedelta(hours=5, minutes=30))
MAX_HOLDS = 3
MIN_GAP_SECONDS = 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS nidaan_bot_holds (
    conv_key  TEXT PRIMARY KEY,          -- wa:<msisdn> | sup:<thread_id>
    sent      INTEGER NOT NULL DEFAULT 0,
    last_at   TIMESTAMP
);
"""

_DAY = {"en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
        "hi": ("सोम", "मंगल", "बुध", "गुरु", "शुक्र", "शनि", "रवि"),
        "hinglish": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}
_DAY_FULL = {"en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
             "hi": ("सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"),
             "hinglish": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}


def _lang(lang: str) -> str:
    lang = (lang or "en").lower()
    return "hi" if lang.startswith("hi") and lang != "hinglish" else (
        "hinglish" if lang == "hinglish" else "en")


def _clock(hhmm: str, lang: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    if lang == "hi":
        return "%d%s बजे" % ((h % 12) or 12, (":%02d" % m) if m else "")
    return "%d%s %s" % ((h % 12) or 12, (":%02d" % m) if m else "", "am" if h < 12 else "pm")


def _days(days: list, lang: str) -> str:
    d = sorted(days)
    names = _DAY[lang]
    if d and d == list(range(d[0], d[-1] + 1)) and len(d) > 2:
        return "%s–%s" % (names[d[0]], names[d[-1]])
    return ", ".join(names[x] for x in d)


def hours_line(cfg: dict, lang: str) -> str:
    lang = _lang(lang)
    return "%s, %s–%s IST" % (_days(cfg["days"], lang), _clock(cfg["start"], lang),
                              _clock(cfg["end"], lang))


def next_open(cfg: dict, now: datetime, lang: str) -> str:
    """'today at 10 am' / 'tomorrow at 10 am' / 'on Monday at 10 am' - in their language."""
    lang = _lang(lang)
    at = _clock(cfg["start"], lang)
    for add in range(0, 8):
        day = now + timedelta(days=add)
        if day.weekday() not in cfg["days"]:
            continue
        if add == 0 and now.strftime("%H:%M") >= cfg["start"]:
            continue
        if add == 0:
            return {"en": "today at %s", "hi": "आज %s", "hinglish": "aaj %s"}[lang] % at
        if add == 1:
            return {"en": "tomorrow at %s", "hi": "कल %s", "hinglish": "kal %s"}[lang] % at
        name = _DAY_FULL[lang][day.weekday()]
        return {"en": "on %s at %s", "hi": "%s को %s", "hinglish": "%s ko %s"}[lang] % (name, at)
    return {"en": "on the next working day", "hi": "अगले कार्य-दिवस", "hinglish": "agle working day"}[lang]


def compose(n: int, *, open_now: bool, cfg: dict, lang: str, now: datetime | None = None) -> str:
    """The n-th holding message (1..MAX_HOLDS)."""
    lang = _lang(lang)
    now = now or datetime.now(IST)
    hrs = hours_line(cfg, lang)
    last = n >= MAX_HOLDS
    if open_now:
        body = {
            "en": "Thank you for writing to NidaanPartner 🙏 Someone from our team will reach out to "
                  "you shortly — your message is saved with us. We appreciate your patience.\n"
                  "Office hours: %s." % hrs,
            "hi": "NidaanPartner को लिखने के लिए धन्यवाद 🙏 हमारी टीम से कोई जल्द ही आपसे संपर्क करेगा — "
                  "आपका संदेश हमारे पास सुरक्षित है। आपके धैर्य के लिए धन्यवाद।\nऑफ़िस का समय: %s।" % hrs,
            "hinglish": "NidaanPartner ko likhne ke liye dhanyavaad 🙏 Hamari team se koi jald hi aapse "
                        "sampark karega — aapka message hamare paas safe hai. Aapke dhairya ke liye "
                        "dhanyavaad.\nOffice timing: %s." % hrs,
        }[lang]
    else:
        when = next_open(cfg, now, lang)
        body = {
            "en": "Thank you for writing to NidaanPartner 🙏 Our office hours are %s, and we are closed "
                  "right now. Someone from our team will reach out to you %s — your message is saved "
                  "with us. We appreciate your patience." % (hrs, when),
            "hi": "NidaanPartner को लिखने के लिए धन्यवाद 🙏 हमारे ऑफ़िस का समय %s है, अभी ऑफ़िस बंद है। "
                  "हमारी टीम से कोई %s आपसे संपर्क करेगा — आपका संदेश हमारे पास सुरक्षित है। "
                  "आपके धैर्य के लिए धन्यवाद।" % (hrs, when),
            "hinglish": "NidaanPartner ko likhne ke liye dhanyavaad 🙏 Hamara office timing %s hai, abhi "
                        "office band hai. Hamari team se koi %s aapse sampark karega — aapka message "
                        "hamare paas safe hai. Aapke dhairya ke liye dhanyavaad." % (hrs, when),
        }[lang]
    if last:
        body += {
            "en": "\n\nYou don't need to wait on this chat — we will contact you.",
            "hi": "\n\nआपको इस चैट पर इंतज़ार करने की ज़रूरत नहीं — हम आपसे संपर्क करेंगे।",
            "hinglish": "\n\nAapko is chat par intezaar karne ki zaroorat nahi — hum aapse sampark karenge.",
        }[lang]
    return body


async def take(conv_key: str) -> int:
    """Claim the next holding message for this conversation, atomically. 0 = stay silent.

    One UPDATE decides, so two messages arriving together (or in two web workers) cannot both be
    answered, and a fourth never is."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.executescript(SCHEMA)
            await c.execute("INSERT OR IGNORE INTO nidaan_bot_holds (conv_key, sent) VALUES (?,0)",
                            (conv_key,))
            cur = await c.execute(
                "UPDATE nidaan_bot_holds SET sent=sent+1, last_at=CURRENT_TIMESTAMP "
                "WHERE conv_key=? AND sent<? AND (last_at IS NULL OR last_at <= datetime('now', ?))",
                (conv_key, MAX_HOLDS, "-%d seconds" % MIN_GAP_SECONDS))
            await c.commit()
            if cur.rowcount != 1:
                return 0
            r = await (await c.execute("SELECT sent FROM nidaan_bot_holds WHERE conv_key=?",
                                       (conv_key,))).fetchone()
            return int(r[0]) if r else 0
    except Exception as e:  # noqa: BLE001 - unsure means do not repeat ourselves
        logger.warning("bot hold take failed for %s: %s", conv_key, e)
        return 0


async def reset(conv_key: str) -> None:
    """A person from our team replied: the next wait starts its own count."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.executescript(SCHEMA)
            await c.execute("UPDATE nidaan_bot_holds SET sent=0, last_at=NULL WHERE conv_key=?",
                            (conv_key,))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("bot hold reset failed for %s: %s", conv_key, e)


async def message_for(conv_key: str, lang: str) -> tuple[int, str]:
    """(n, text): the n-th holding message this conversation may receive now, or (0, '') to stay
    silent. n == 1 is the start of a wait - the moment to tell staff, once."""
    n = await take(conv_key)
    if not n:
        return 0, ""
    import biz_nidaan as _n
    cfg = await _n.get_business_hours()
    return n, compose(n, open_now=await _n.is_within_business_hours(), cfg=cfg, lang=lang)
