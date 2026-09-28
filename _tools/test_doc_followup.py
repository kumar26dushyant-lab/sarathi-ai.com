# -*- coding: utf-8 -*-
'''Follow-up so far: what was done to get a claim's documents, and the one next step.

Founder, 29 Sep: "just record what action someone performed before ... then next person
whosoever is following up will be clear when someone needs to send a nudge for document or
activate auto-collector to nudge complainant timely or take time schedule and nudge at that time".

What these checks defend:

  * the next step is worked out from the SAME state the workers use - so it never says
    "reminders are running" while automatic reminders are switched off for everyone (they are,
    live, on 29 Sep);
  * each situation gives the right instruction: nobody asked / asked, nothing set / booked /
    automatic / call / nothing missing;
  * who did what is listed, newest first, in IST - and turning automatic reminders on or off is
    now written on the claim, where it used to reach only the audit log.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_doc_followup.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_root = tempfile.mkdtemp(prefix="followup_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_nidaan as nid                            # noqa: E402
import biz_nidaan_doc_request as dr                 # noqa: E402
import biz_nidaan_wa_schedule as sch                # noqa: E402

nid.DB_PATH = dr.DB_PATH = sch.DB_PATH = db.DB_PATH

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_claims (claim_id INTEGER PRIMARY KEY, archived INTEGER DEFAULT 0,
    status TEXT DEFAULT '');
CREATE TABLE nidaan_doc_requests (req_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL, doc_keys TEXT DEFAULT '', message TEXT DEFAULT '',
    channels TEXT DEFAULT '', recipients TEXT DEFAULT '', sent_by_staff_id INTEGER,
    sent_by TEXT DEFAULT '', kind TEXT DEFAULT 'request', result TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_doc_chase (claim_id INTEGER PRIMARY KEY, nudges INTEGER DEFAULT 0,
    last_nudge_at TIMESTAMP, next_nudge_at TIMESTAMP, paused INTEGER DEFAULT 0,
    call_due INTEGER DEFAULT 0, call_done_at TIMESTAMP, call_by TEXT DEFAULT '',
    call_note TEXT DEFAULT '', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_claim_activity (act_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL, kind TEXT NOT NULL, channel TEXT DEFAULT '',
    direction TEXT DEFAULT '', actor TEXT DEFAULT '', summary TEXT DEFAULT '',
    meta TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_wa_schedule (sch_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL, next_at TIMESTAMP, repeat_rule TEXT DEFAULT 'once',
    repeat_every INTEGER DEFAULT 7, repeat_weekday INTEGER, note TEXT DEFAULT '',
    max_sends INTEGER DEFAULT 6, stop_when_complete INTEGER DEFAULT 1,
    sent_count INTEGER DEFAULT 0, last_sent_at TIMESTAMP, status TEXT DEFAULT 'active',
    done_reason TEXT DEFAULT '', created_by TEXT DEFAULT '', created_by_name TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_ops_settings (key TEXT PRIMARY KEY, value TEXT, updated_by TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""

AUTO = {"on": False}


async def f_auto():
    return AUTO["on"]


dr.auto_collection_on = f_auto


async def run(sql, *args):
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute(sql, args)
        await c.commit()


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    print("\nThe one next step\n")

    fu = await dr.followup(1, missing=3)
    check("nobody asked yet: say so, and what to press",
          fu["step"] == "act" and "Nobody has asked" in fu["next"], fu["next"])
    check("...and that automatic reminders are OFF for everyone",
          fu["auto_global"] is False and fu["auto_running"] is False, fu)

    await run("INSERT INTO nidaan_doc_requests (claim_id, sent_by, created_at) VALUES "
              "(1, 'Asha', datetime('now','-4 days'))")
    fu = await dr.followup(1, missing=3)
    check("asked, nothing booked: who asked, how long ago, and what to do",
          fu["step"] == "act" and "Asha" in fu["next"] and "4 days ago" in fu["next"]
          and "reminder" in fu["next"], fu["next"])

    # Automatic reminders armed on the claim, but switched off for everyone: NOT waiting.
    await run("INSERT INTO nidaan_doc_chase (claim_id, next_nudge_at) VALUES "
              "(1, datetime('now','+2 days'))")
    fu = await dr.followup(1, missing=3)
    check("armed on the claim but OFF for everyone is NOT 'nothing to do'",
          fu["step"] == "act" and not fu["auto_running"], fu["next"])
    AUTO["on"] = True
    fu = await dr.followup(1, missing=3)
    check("with automatic reminders really running: wait, and when",
          fu["step"] == "wait" and "Automatic reminder next on" in fu["next"], fu["next"])

    r = await sch.create(1, when_date="2099-01-04", when_time="10:00", by="Ravi")
    fu = await dr.followup(1, missing=3)
    check("a booked reminder wins: when, and who set it",
          r.get("ok") and fu["step"] == "wait" and "Ravi" in fu["next"]
          and "04 Jan" in fu["next"], fu["next"])

    await run("UPDATE nidaan_doc_chase SET call_due=1 WHERE claim_id=1")
    fu = await dr.followup(1, missing=3)
    check("reminders exhausted: CALL comes first", fu["step"] == "call" and "CALL" in fu["next"],
          fu["next"])

    fu = await dr.followup(1, missing=0)
    check("nothing missing: nothing to chase", fu["step"] == "done", fu["next"])

    print("\nWho did what, where the next person looks\n")

    await dr.pause_chase(1, paused=True, actor="Priya")
    fu = await dr.followup(1, missing=3)
    ev = fu["events"]
    check("turning automatic reminders off is now on the claim",
          any(e["kind"] == "doc_chase" and e["who"] == "Priya" and "OFF" in e["what"]
              for e in ev), ev)
    check("a booked reminder is on it too, with who booked it",
          any(e["kind"] == "wa_scheduled" and e["who"] == "Ravi" for e in ev), ev)
    check("newest first", ev and ev[0]["kind"] == "doc_chase", [e["kind"] for e in ev])
    check("times in IST words, never raw UTC",
          ev and "," in ev[0]["at"] and ("AM" in ev[0]["at"] or "PM" in ev[0]["at"]), ev and ev[0])
    check("...and the paused state is reported", fu["auto_paused"] is True)

    await run("INSERT INTO nidaan_claim_activity (claim_id, kind, actor, summary) VALUES "
              "(1, 'wa_answer', 'bot', 'Answered: hello')")
    fu = await dr.followup(1, missing=3)
    check("ordinary chat is not listed as document follow-up",
          not any(e["kind"] == "wa_answer" for e in fu["events"]))
    check("another claim's follow-up never shows here",
          (await dr.followup(2, missing=3))["events"] == [])

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
