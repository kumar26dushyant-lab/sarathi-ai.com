# -*- coding: utf-8 -*-
'''The bot answers a staffer's question without sending anyone's data out.

Founder, 28 Sep 2026: *"prevent ask AI, should not send data out PII informations should be
protected."*

Until today the "Ask AI" button posted task records to Gemini - titles, staff names and up to 220
characters of a description, which on this system routinely names a claimant and their illness.
The rows were always fetched locally; only the phrasing was outsourced. Now the answering is
local too.

What these checks defend:

  * the ask path cannot reach an outside model - read from the SOURCE, because the absence of a
    call in one test run proves nothing about the next edit;
  * the counts are the TABLE'S. The old prompt was handed a truncated list and asked about the
    whole workload, so it could say "4 overdue" having been shown 4 of 11. Here 11 means 11;
  * a task number that is not yours reads exactly like one that does not exist, or the bot
    becomes a way to discover which task numbers are real, one guess at a time;
  * a question it does not understand says so and offers what it CAN answer - it never invents.
    A confident wrong answer about somebody's workload is worse than "ask me this instead";
  * and it answers in all three languages, because half this office types Hindi in Roman letters.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_ask_local.py
'''
import datetime
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import biz_nidaan_ask_local as ask  # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


TODAY = datetime.date(2026, 9, 28)


def task(tid, title, status="open", due=None, who="Asha"):
    return {"quick_task_id": tid, "title": title, "status": status,
            "due_date": due, "assignee_name": who, "priority": "normal",
            "description": "Claimant Sharma, cardiac, policy 9912"}     # the PII that must not travel


ROWS = [
    task(11, "Collect discharge summary", due="2026-09-20"),          # overdue
    task(12, "Call the insurer", due="2026-09-20"),                   # overdue
    task(13, "File Lokpal form", due="2026-09-28"),                   # today
    task(14, "Draft reply", due="2026-10-10"),                        # later
    task(15, "Old thing", status="done", due="2026-09-01"),           # done, so not overdue
    task(16, "No date at all", due=None),
]


# ── 1. nothing on this path can reach a model ────────────────────────────────
print("\nThe ask path, at the source\n")

SRC = io.open("biz_nidaan_ask_local.py", encoding="utf-8").read()
code = "\n".join(l for l in SRC.splitlines() if not l.lstrip().startswith("#"))
for bad in ("httpx", "requests", "urllib", "genai", "generativelanguage", "biz_ai",
            "GEMINI_API_KEY", "openai"):
    check("the answerer never mentions %-20s" % bad, bad not in code)

BOT = io.open("biz_nidaan_telegram.py", encoding="utf-8").read()
check("the bot no longer has a Gemini ask function", "_ask_gemini" not in BOT)
# Looked up defensively: when the checks below FAIL the function is absent, and a test that dies
# on a ValueError reports one finding instead of all of them.
MARK = "async def _answer_question("
fn = BOT[BOT.index(MARK):] if MARK in BOT else ""
fn = fn[:fn.index("\n\nasync def ")] if "\n\nasync def " in fn else fn[:2000]
check("the local answering function exists at all", bool(fn))
check("...and the function that replaced it makes no web call",
      not re.search(r"httpx|generativelanguage|GEMINI_API_KEY", fn))
check("...while KEEPING the per-task authorisation check",
      "is_task_participant" in fn, "an associate could otherwise read any task by its number")


# ── 2. the answers are the table's ───────────────────────────────────────────
print("\nWhat it answers\n")

r = ask.answer("what is pending with me", ROWS, lang="en", today=TODAY)
check("pending counts every unfinished task", "5 pending" in r["text"], r["text"])
check("...and does not count the finished one", "Old thing" not in r["text"], r["text"])

r = ask.answer("what is overdue?", ROWS, lang="en", today=TODAY)
check("overdue is only what is past due AND unfinished", "*2 overdue*" in r["text"], r["text"])
check("...and says how late each one is", "8 day(s) late" in r["text"], r["text"])
check("...and a finished task is never overdue", "Old thing" not in r["text"], r["text"])

r = ask.answer("what is due today", ROWS, lang="en", today=TODAY)
check("due-today is exactly today", "*1 due today*" in r["text"] and "#13" in r["text"],
      r["text"])

r = ask.answer("status of #12", ROWS, lang="en", today=TODAY)
check("a task by number answers about THAT task",
      "#12" in r["text"] and "Call the insurer" in r["text"] and "#11" not in r["text"],
      r["text"])

# The trap the old prompt fell into: a number inside a question about something else.
r = ask.answer("is task 11 overdue?", ROWS, lang="en", today=TODAY)
check("a number wins over a keyword - this is a question about #11",
      "#11" in r["text"] and "*2 overdue*" not in r["text"], r["text"])


# ── 3. it cannot be used to discover what exists ─────────────────────────────
print("\nWhat it refuses to leak\n")

not_mine = ask.answer("status of #999", ROWS, lang="en", today=TODAY)["text"]
no_such = ask.answer("status of #4242", ROWS, lang="en", today=TODAY)["text"]
check("'not yours' and 'no such task' read identically",
      not_mine.replace("999", "N") == no_such.replace("4242", "N"),
      "%r vs %r" % (not_mine, no_such))


# ── 4. it never pretends ─────────────────────────────────────────────────────
print("\nWhen it does not understand\n")

r = ask.answer("who should I marry", ROWS, lang="en", today=TODAY)
check("an unknown question is admitted, not guessed", r["understood"] is False, r)
check("...and the reply offers what it CAN answer",
      "pending" in r["text"] and "overdue" in r["text"], r["text"])
check("...and invents no task", "#1" not in r["text"] and "Draft reply" not in r["text"],
      r["text"])

r = ask.answer("", ROWS, lang="en", today=TODAY)
check("an empty question does not crash and does not guess", r["understood"] is False)

# A malformed row must not take the whole answer down - one bad date is not an outage.
bad = ROWS + [{"quick_task_id": 99, "title": "Broken", "status": "open", "due_date": "not-a-date"}]
r = ask.answer("what is overdue", bad, lang="en", today=TODAY)
check("a malformed due date is survived", "*2 overdue*" in r["text"], r["text"])


# ── 5. all three languages ───────────────────────────────────────────────────
print("\nIn every language the office types\n")

for lang, word in (("en", "pending"), ("hi", "बाकी"),
                   ("hinglish", "pending")):
    r = ask.answer("mere paas kya pending hai", ROWS, lang=lang, today=TODAY)
    check("%-8s understands Hinglish and answers in its own language" % lang,
          r["understood"] and word in r["text"], r["text"][:80])

r = ask.answer("क्या देर से चल "
               "रहा है", ROWS, lang="hi", today=TODAY)
check("Devanagari is understood too", r["understood"], r["text"][:80])

print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
sys.exit(1 if FAILED else 0)
