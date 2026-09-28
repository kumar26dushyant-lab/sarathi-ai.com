# -*- coding: utf-8 -*-
"""Answer a staff member's question about their own work, ON THIS SERVER.

Founder, 28 Sep 2026: *"prevent ask AI, should not send data out PII informations should be
protected. Fix or retire, take your decision if it'll need in future then fix it else retire."*

FIXED, NOT RETIRED, and the reason is worth stating. Until today the bot's "Ask AI" button sent
Gemini a block of task records - titles, staff names, and up to 220 characters of a description,
which on this system routinely names a claimant and their illness. What it got back was those
same records, rephrased. The model was doing the wording, not the thinking: the questions staff
actually ask are a small, knowable set over one table the bot had already queried.

So the question is answered here instead. That is not a downgrade:

  * nothing about a claimant leaves the building;
  * it answers instantly and costs nothing;
  * the numbers are the table's, not a model's reading of a truncated list - the old one was
    handed 80 rows and asked about a 200-row workload, and would happily say "you have 4 overdue"
    when it had been shown 4 of 11;
  * it still works when Gemini is down, out of quota, or not configured.

WHAT IT WILL NOT DO is pretend. A question outside the set it knows gets an honest "I cannot
answer that yet", followed by what it CAN answer, as tappable examples - which is the founder's
standing rule for every staff screen: *"we need to run staff step by step for everything kind of
a baby step so that they can read and move for next step."* A wrong confident answer about
somebody's workload is worse than "ask me this instead".

AUTHORISATION IS THE CALLER'S. This module never widens what a person may see: it is handed the
rows and answers over those. An associate is handed their own, an admin the office's, exactly as
the list screens already decide.
"""
from __future__ import annotations

import datetime
import logging
import re

logger = logging.getLogger("nidaan.ask.local")

# Statuses that mean the work is finished, however the row spells it.
DONE = ("done", "completed", "closed", "cancelled")


def _lang(l: str) -> str:
    l = (l or "").strip().lower()
    return l if l in ("en", "hi", "hinglish") else "en"


# ── the words people actually type, in three languages ───────────────────────
# Matched on the TYPED text, never on a claimant's data. Hindi is matched in Devanagari and in
# Roman letters, because staff here type both and a bot that only understands one is a bot half
# the office cannot use.
INTENTS = [
    ("task_id", [r"#\s*0*(\d{1,7})\b", r"\btask\s*#?\s*0*(\d{1,7})\b",
                 r"\bnumber\s*0*(\d{1,7})\b", r"\bटास्क\s*#?\s*0*(\d{1,7})\b"]),
    ("overdue", [r"\boverdue\b", r"\blate\b", r"\bdelayed?\b", r"\bdeadline\b",
                 r"ओवरड्यू", r"देर\s*से", r"लेट\b", r"समय\s*निकल"]),
    ("today",   [r"\btoday\b", r"\bdue\s+today\b", r"\baaj\b", r"आज\b"]),
    ("pending", [r"\bpending\b", r"\bopen\b", r"\bremaining\b", r"\bto\s*do\b",
                 r"\bmy\s+work\b", r"\bwhat'?s?\s+with\s+me\b",
                 r"पेंडिंग", r"बाक़ी", r"बाकी", r"मेरे\s*पास", r"\bbaki\b", r"\bmere\s*paas\b"]),
    ("done",    [r"\bdone\b", r"\bfinished\b", r"\bcompleted\b", r"\bclosed\b",
                 r"पूरा", r"पूर्ण", r"हो\s*गया", r"\bpura\b", r"\bho\s*gaya\b"]),
    ("count",   [r"\bhow\s+many\b", r"\bcount\b", r"\bkitne\b", r"कितने", r"कितना"]),
]


def read_question(text: str) -> dict:
    """What is being asked? Returns {"intent": ..., "task_id": int|None}.

    A task NUMBER wins over everything else: "is 55 overdue" is a question about 55, and
    answering it with the whole overdue list would be answering a question nobody asked.
    """
    t = (text or "").strip()
    if not t:
        return {"intent": "", "task_id": None}
    for name, pats in INTENTS:
        for p in pats:
            m = re.search(p, t, re.I)
            if m:
                if name == "task_id":
                    try:
                        return {"intent": "task_id", "task_id": int(m.group(1))}
                    except (ValueError, IndexError):
                        continue
                return {"intent": name, "task_id": None}
    return {"intent": "", "task_id": None}


def _is_done(row: dict) -> bool:
    return str(row.get("status") or "").strip().lower() in DONE


def _due(row: dict):
    """The due date as a date, or None. Never raises on a malformed row."""
    raw = str(row.get("due_date") or "")[:10]
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None


def _overdue(row: dict, today: datetime.date) -> bool:
    d = _due(row)
    return bool(d and d < today and not _is_done(row))


# ── the words of the answers ─────────────────────────────────────────────────
S = {
    "none_pending": {
        "en": "✅ Nothing is pending with you right now.",
        "hi": "✅ अभी आपके पास कुछ भी बाकी नहीं है।",
        "hinglish": "✅ Abhi aapke paas kuch bhi pending nahi hai.",
    },
    "none_overdue": {
        "en": "✅ Nothing is overdue. ",
        "hi": "✅ कुछ भी देर से नहीं चल रहा। ",
        "hinglish": "✅ Kuch bhi late nahi chal raha. ",
    },
    "none_today": {
        "en": "📅 Nothing is due today.",
        "hi": "📅 आज कुछ भी पूरा करने को नहीं है।",
        "hinglish": "📅 Aaj kuch bhi due nahi hai.",
    },
    "none_done": {
        "en": "Nothing has been marked done yet.",
        "hi": "अभी तक कुछ भी पूरा नहीं लगाया गया है।",
        "hinglish": "Abhi tak kuch bhi done mark nahi hua hai.",
    },
    "pending_head": {
        "en": "📋 *%d pending with you*",
        "hi": "📋 *आपके पास %d बाकी हैं*",
        "hinglish": "📋 *Aapke paas %d pending hain*",
    },
    "overdue_head": {
        "en": "⏰ *%d overdue*",
        "hi": "⏰ *%d देर से चल रहे हैं*",
        "hinglish": "⏰ *%d late chal rahe hain*",
    },
    "today_head": {
        "en": "📅 *%d due today*",
        "hi": "📅 *आज %d पूरे करने हैं*",
        "hinglish": "📅 *Aaj %d poore karne hain*",
    },
    "done_head": {
        "en": "✅ *%d finished recently*",
        "hi": "✅ *हाल में %d पूरे हुए*",
        "hinglish": "✅ *Haal mein %d poore hue*",
    },
    "no_such": {
        "en": "I cannot find task #%d — either it does not exist, or it is not one of yours.",
        "hi": "टास्क #%d नहीं मिला — या तो वह है ही नहीं, या वह आपका नहीं है।",
        "hinglish": "Task #%d nahi mila — ya to wo hai hi nahi, ya wo aapka nahi hai.",
    },
    "more": {
        "en": "\n…and %d more.",
        "hi": "\n…और %d।",
        "hinglish": "\n…aur %d.",
    },
    "days_late": {
        "en": " — %d day(s) late",
        "hi": " — %d दिन देर",
        "hinglish": " — %d din late",
    },
    # The honest fallback. It never guesses, and it always leaves the person with a next step.
    "dunno": {
        "en": ("🤔 I could not understand that one.\n\nI can answer these — tap one, or type it:\n"
               "• *what is pending with me*\n• *what is overdue*\n• *what is due today*\n"
               "• *status of #55* (any task number)\n\n"
               "For anything else, please use the menu below."),
        "hi": ("🤔 यह सवाल मैं समझ नहीं पाया।\n\nमैं ये बता सकता हूँ — दबाइए, या लिखिए:\n"
               "• *मेरे पास क्या पेंडिंग है*\n• *क्या देर से चल रहा है*\n• *आज क्या पूरा करना है*\n"
               "• *#55 की स्थिति* (कोई भी टास्क नंबर)\n\n"
               "बाकी किसी काम के लिए नीचे का मेन्यू इस्तेमाल कीजिए।"),
        "hinglish": ("🤔 Yeh sawaal main samajh nahi paaya.\n\nMain ye bata sakta hoon — dabaiye, "
                     "ya likhiye:\n• *mere paas kya pending hai*\n• *kya late chal raha hai*\n"
                     "• *aaj kya poora karna hai*\n• *#55 ka status* (koi bhi task number)\n\n"
                     "Baaki kisi kaam ke liye neeche ka menu use kijiye."),
    },
}


def t(key: str, lang: str) -> str:
    return S[key][_lang(lang)]


def _line(row: dict, lang: str, today: datetime.date) -> str:
    """One task, one line. Short enough to read on a phone."""
    bits = "#%s %s" % (row.get("quick_task_id"), (row.get("title") or "")[:60])
    d = _due(row)
    if d and d < today and not _is_done(row):
        bits += t("days_late", lang) % (today - d).days
    elif d:
        bits += " — %s" % d.isoformat()
    who = row.get("assignee_name") or ""
    if who:
        bits += " · %s" % who[:20]
    return "• " + bits


def _listing(rows: list, head_key: str, empty_key: str, lang: str,
             today: datetime.date, limit: int = 10) -> str:
    if not rows:
        return t(empty_key, lang)
    out = [t(head_key, lang) % len(rows), ""]
    out += [_line(r, lang, today) for r in rows[:limit]]
    if len(rows) > limit:
        out.append(t("more", lang) % (len(rows) - limit))
    return "\n".join(out)


def answer(question: str, rows: list, *, lang: str = "en",
           today: datetime.date | None = None) -> dict:
    """Answer over the rows the caller is allowed to see.

    Returns {"text": ..., "understood": bool}. `understood` is False when we did not recognise
    the question - the bot uses it to show the examples rather than pretend, and it is a separate
    flag rather than a magic string so nothing downstream has to match on wording.
    """
    today = today or datetime.date.today()
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    q = read_question(question)

    if q["intent"] == "task_id":
        tid = q["task_id"]
        row = next((r for r in rows if str(r.get("quick_task_id")) == str(tid)), None)
        if not row:
            # Identical wording for "does not exist" and "not yours", so the bot cannot be used
            # to find out which task numbers are real - the same rule as claim ids.
            return {"text": t("no_such", lang) % tid, "understood": True}
        d = _due(row)
        parts = ["📌 *#%s · %s*" % (row.get("quick_task_id"), row.get("title") or "")]
        parts.append("Status: %s" % (row.get("status") or "—"))
        if row.get("priority"):
            parts.append("Priority: %s" % row["priority"])
        if row.get("assignee_name"):
            parts.append("With: %s" % row["assignee_name"])
        if d:
            late = (today - d).days
            parts.append("Due: %s%s" % (d.isoformat(),
                                        (t("days_late", lang) % late) if late > 0
                                        and not _is_done(row) else ""))
        return {"text": "\n".join(parts), "understood": True}

    if q["intent"] in ("pending", "count"):
        open_rows = [r for r in rows if not _is_done(r)]
        return {"text": _listing(open_rows, "pending_head", "none_pending", lang, today),
                "understood": True}

    if q["intent"] == "overdue":
        late = [r for r in rows if _overdue(r, today)]
        return {"text": _listing(late, "overdue_head", "none_overdue", lang, today),
                "understood": True}

    if q["intent"] == "today":
        due = [r for r in rows if _due(r) == today and not _is_done(r)]
        return {"text": _listing(due, "today_head", "none_today", lang, today),
                "understood": True}

    if q["intent"] == "done":
        fin = [r for r in rows if _is_done(r)]
        return {"text": _listing(fin, "done_head", "none_done", lang, today),
                "understood": True}

    return {"text": t("dunno", lang), "understood": False}
