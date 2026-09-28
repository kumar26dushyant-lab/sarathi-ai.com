# -*- coding: utf-8 -*-
'''The complainant picks when we remind them - understood, confirmed, then booked.

Founder, 29 Sep: "we can ask user when to remind you ... our bot should understand the details
well, if details are not clear then our bot should nudge user for more clarity and nudging
schedule confirmation ... keep it simple."

What these checks defend:

  * the way people actually write it - Hinglish, Hindi, English, "2 ghante baad" - is understood;
  * a day with no time, a time at night, a date months away: asked again, not guessed;
  * NOTHING is booked without their yes, and a yes to a time that has passed is asked again;
  * booked into the SAME schedule staff use (so it stops when documents arrive, obeys the caps,
    falls back to the template past 24 hours, and nudges a person when it fires);
  * a second choice replaces the first - which is CANCELLED, never deleted;
  * it never traps a conversation: an unrelated question, or STOP, is not ours;
  * and it is OFF until a super-admin turns it on.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_remind.py
'''
import asyncio
import io
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_root = tempfile.mkdtemp(prefix="waremind_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_nidaan_wa_remind as rm                   # noqa: E402
import biz_nidaan_wa_schedule as sch                # noqa: E402
import biz_nidaan as nid                            # noqa: E402

rm.DB_PATH = db.DB_PATH
sch.DB_PATH = db.DB_PATH

FAILED = 0
DEV = re.compile(r"[ऀ-ॿ]")


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_wa_remind_state (msisdn TEXT PRIMARY KEY, claim_id INTEGER NOT NULL,
    state TEXT NOT NULL DEFAULT '', proposed_utc TEXT NOT NULL DEFAULT '',
    tries INTEGER NOT NULL DEFAULT 0, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_wa_schedule (
    sch_id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL, next_at TIMESTAMP,
    repeat_rule TEXT DEFAULT 'once', repeat_every INTEGER DEFAULT 7, repeat_weekday INTEGER,
    note TEXT DEFAULT '', max_sends INTEGER DEFAULT 6, stop_when_complete INTEGER DEFAULT 1,
    sent_count INTEGER DEFAULT 0, last_sent_at TIMESTAMP, status TEXT DEFAULT 'active',
    done_reason TEXT DEFAULT '', created_by TEXT DEFAULT '', created_by_name TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


async def f_quiet():
    return 8, 21


rm._quiet_hours = f_quiet


def real_now():
    return datetime.now(rm.IST)


async def sched_rows(claim_id):
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_wa_schedule WHERE claim_id=? ORDER BY sch_id", (claim_id,)))
            .fetchall()]


async def state(msisdn):
    async with aiosqlite.connect(db.DB_PATH) as c:
        r = await (await c.execute("SELECT state, tries FROM nidaan_wa_remind_state WHERE msisdn=?",
                                   (msisdn,))).fetchone()
    return (r[0], r[1]) if r else ("", 0)


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    print("\nUnderstanding the way people write it\n")
    tue = datetime(2026, 9, 29, 11, 0, tzinfo=rm.IST)      # a Tuesday, 11 am

    def at(t):
        p = rm.parse_when(t, tue)
        return p["at"].strftime("%a %d %H:%M") if p["kind"] == "at" else p["kind"]

    cases = [
        ("kal shaam 7 baje", "Wed 30 19:00"), ("Sunday 10am", "Sun 04 10:00"),
        ("रविवार सुबह 10 बजे", "Sun 04 10:00"), ("2 ghante baad", "Tue 29 13:00"),
        ("2 घंटे बाद", "Tue 29 13:00"), ("parso dopahar 2", "Thu 01 14:00"),
        ("somvar subah", "Mon 05 10:00"), ("7 baje", "Tue 29 19:00"),
        ("10:30", "Wed 30 10:30"), ("Tuesday 10am", "Tue 06 10:00"),
        ("30 min", "Tue 29 11:30"), ("इतवार शाम 6 बजे", "Sun 04 18:00"),
    ]
    for text_in, want in cases:
        check("%-22s -> %s" % (text_in, want), at(text_in) == want, at(text_in))
    check("a day with no time is NOT guessed", rm.parse_when("Sunday", tue)["kind"] == "need_time")
    check("'kal' alone asks for the time", rm.parse_when("kal", tue)["kind"] == "need_time")
    check("a sentence that merely mentions hours is not a time answer",
          rm.parse_when("mera claim 2 hours pehle reject hua", tue)["words"] >= 3)
    check("no day and no time is nothing", rm.parse_when("haan", tue)["kind"] == "none")

    print("\nSaying it back in their language\n")
    sun10 = datetime(2026, 10, 4, 10, 0, tzinfo=rm.IST)
    check("English", rm.say_when(sun10, "en") == "Sunday 4 Oct, 10:00 am", rm.say_when(sun10, "en"))
    check("Hinglish", rm.say_when(sun10, "hinglish") == "Ravivar 4 Oct, subah 10:00 baje",
          rm.say_when(sun10, "hinglish"))
    check("Hindi", rm.say_when(sun10, "hi") == "रविवार 4 अक्टूबर, सुबह 10:00 बजे",
          rm.say_when(sun10, "hi"))
    check("7 pm is evening, not night",
          "shaam 7" in rm.say_when(datetime(2026, 10, 4, 19, 0, tzinfo=rm.IST), "hinglish"))
    for kind in ("ask", "need_time", "quiet", "too_far", "propose", "booked", "declined",
                 "give_up", "failed", "offer"):
        check("%-9s exists in all three languages, Hindi in Hindi" % kind,
              all(rm.text(kind, l, when="X") for l in ("hinglish", "hi", "en"))
              and DEV.search(rm.text(kind, "hi", when="X")))
    check("the confirmation keeps the fast-track promise",
          "fast-track" in rm.text("booked", "hinglish", when="X"))

    print("\nThe conversation\n")
    # A fixed noon tomorrow, so the checks mean the same at whatever hour they run: at 8pm the
    # real clock would put "in 2 hours" into quiet hours and a check could pass by accident.
    NOW = (real_now() + timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)

    async def H(msisdn, claim_id, text_in, lang):
        return await rm.handle(msisdn, claim_id, text_in, lang, now=NOW)
    n1 = "919000000001"
    r = await H(n1, 11, "Sunday 11am", "hinglish")
    check("a clear time is PROPOSED, not booked", r and "HAAN" in r, r)
    check("...nothing is booked yet", await sched_rows(11) == [])
    r = await H(n1, 11, "haan ji", "hinglish")
    rows = await sched_rows(11)
    check("their yes books it", r and r.startswith("✅") and len(rows) == 1, (r, rows))
    check("...in the schedule staff use, marked as theirs",
          rows and rows[0]["created_by_name"] == rm.BY_NAME and rows[0]["repeat_rule"] == "once",
          rows)
    check("...at the moment they chose (stored in UTC)",
          rows and rows[0]["next_at"].endswith("05:30:00"), rows and rows[0]["next_at"])
    check("...and stops by itself when the documents arrive",
          rows and rows[0]["stop_when_complete"] == 1)

    r = await H(n1, 11, "actually Saturday 5 pm", "hinglish")
    r2 = await H(n1, 11, "ok", "hinglish")
    rows = await sched_rows(11)
    active = [x for x in rows if x["status"] == "active"]
    check("a new choice replaces the old one", len(active) == 1 and "11:30:00" in
          active[0]["next_at"], [(x["status"], x["next_at"]) for x in rows])
    check("...and the old one is CANCELLED, not deleted",
          len(rows) == 2 and rows[0]["status"] == "cancelled", [x["status"] for x in rows])

    print("\nWhen it is not clear\n")
    n2 = "919000000002"
    r = await H(n2, 12, "abhi busy hoon, baad mein", "hinglish")
    check("'busy, later' gets the question, with an example", r and "baje" in r, r)
    r = await H(n2, 12, "kal", "hinglish")
    check("a day without a time: which time?", r and "kitne baje" in r.lower(), r)
    r = await H(n2, 12, "raat 11 baje", "hinglish")
    check("a time at night is refused politely, with the window", r and "8" in r, r)
    r = await H(n2, 12, "hmm", "hinglish")
    r = await H(n2, 12, "pata nahi", "hinglish")
    check("twice unclear and a person takes over", r and "team" in r.lower(), r)
    check("...and the bot stops asking", (await state(n2))[0] == "gave_up", await state(n2))

    n3 = "919000000003"
    await H(n3, 13, "remind me later", "en")
    r = await H(n3, 13, "stop", "en")
    check("STOP is never ours - even while our question is waiting", r is None, r)
    await H(n3, 13, "remind me later", "en")
    r = await H(n3, 13, "what is the status of my claim with the insurance company?", "en")
    check("an unrelated question is NOT trapped by our pending question", r is None, r)
    r = await H("919000000004", 14, "mera claim kab tak hoga?", "hinglish")
    check("a question about the claim, with nothing pending, is not ours", r is None, r)

    print("\nNo booking without a valid yes\n")
    n5 = "919000000005"
    await H(n5, 15, "remind me in 2 hours", "en")
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute("UPDATE nidaan_wa_remind_state SET proposed_utc=? WHERE msisdn=?",
                        (past, n5))
        await c.commit()
    r = await H(n5, 15, "yes", "en")
    check("a yes to a time that has already passed is asked again",
          r and "When should I remind you" in r and await sched_rows(15) == [], r)
    await H(n5, 15, "Friday 10 am", "en")
    r = await H(n5, 15, "no", "en")
    check("a no is not booked, and they are asked again",
          r and "When" in r and await sched_rows(15) == [], r)
    await H(n5, 15, "Friday 10 am", "en")
    r = await H(n5, 15, "I will send the discharge summary now", "en")
    check("...and a different message while we wait for yes is let through",
          r is None and await sched_rows(15) == [], r)
    r = await H(n5, 15, "remind me in 1000 hours", "en")
    check("more than %d days ahead is asked again, not booked" % rm.MAX_DAYS_AHEAD,
          r is not None and "too far" in r and await sched_rows(15) == [], r)

    print("\nOFF until a super-admin turns it on\n")
    check("the default is OFF", nid.OPS_SETTING_DEFAULTS.get(rm.SETTING) == "0",
          nid.OPS_SETTING_DEFAULTS.get(rm.SETTING))
    orig = nid.get_ops_setting

    async def broken(*a, **k):
        raise RuntimeError("db gone")
    nid.get_ops_setting = broken
    check("an unreadable setting means OFF", (await rm.enabled()) is False)
    nid.get_ops_setting = orig

    print("\nWhere it is wired\n")
    orch = io.open("biz_nidaan_wa_orchestrator.py", encoding="utf-8").read()
    hook = orch[orch.index("WHEN SHOULD WE REMIND THEM"):orch.index("d = await _brain.decide(")]
    check("only where documents may be asked for", '_st.get("may_send_docs")' in hook)
    check("only when switched on", "_remind.enabled()" in hook)
    check("an error answers normally instead", "except Exception" in hook and "_r = None" in hook)
    check("staff still hear the message", "_tell_staff_inbound" in hook)
    check("human takeover is checked BEFORE it",
          orch.index("if await _human_holds(msisdn, claim_id):") < orch.index("WHEN SHOULD WE REMIND"))
    ask = orch[orch.index("async def ask_next("):orch.index("async def _tell_staff_inbound")]
    check("the offer line is added only when switched on",
          '_remind.enabled()' in ask and 'offer_line' in ask)
    biz = io.open("sarathi_biz.py", encoding="utf-8").read()
    keys = biz[biz.index("_wa_keys = ["):biz.index("settings = {k: await nidaan.get_ops_setting(k) for k in _wa_keys}")]
    for k in ("wa_journey_enabled", "wa_lead_capture_enabled", "wa_remind_ask_enabled"):
        check("the panel is sent %s (it showed ON while OFF)" % k, '"%s"' % k in keys)
    check("the switch accepts only 0 or 1",
          'wa_remind_ask_enabled: Optional[Literal["0", "1"]]' in biz)

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
