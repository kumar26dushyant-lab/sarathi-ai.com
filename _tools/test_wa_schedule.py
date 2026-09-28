# -*- coding: utf-8 -*-
'''Scheduled document reminders: reached means reached, and the person who set it hears.

What these checks defend:

  * REACHED, NOT RECORDED. doc_request.send() says ok when it logged the ask, even when the
    complainant was not reached. The schedule read that as "sent" and closed a one-off as
    "one-off reminder sent" - a reminder that reached nobody, reported as done;
  * THE 24-HOUR RULE. Past 24 hours since the complainant last wrote, a free message cannot be
    delivered. The approved np_doc_reminder template can, so the reminder falls back to it;
  * a colleague who asked minutes ago is not overridden by the template;
  * THE STAFF NUDGE. Whoever set the reminder hears what happened - and when it did not get
    through, is told to call, with the number. Bell and Telegram, never email;
  * and Meta's failed receipt keeps its reason, in words.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_schedule.py
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

_root = tempfile.mkdtemp(prefix="wasched_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_nidaan_wa_schedule as sch                # noqa: E402
import biz_nidaan_doc_request as dr                 # noqa: E402
import biz_nidaan_doc_checklist as ck               # noqa: E402
import biz_nidaan_wa_orchestrator as orch           # noqa: E402
import biz_nidaan_notifications as nnot             # noqa: E402
import biz_nidaan_wa_flow as flow                   # noqa: E402

sch.DB_PATH = db.DB_PATH

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
CREATE TABLE nidaan_wa_schedule (
    sch_id INTEGER PRIMARY KEY AUTOINCREMENT, claim_id INTEGER NOT NULL, next_at TIMESTAMP,
    repeat_rule TEXT DEFAULT 'once', repeat_every INTEGER DEFAULT 7, repeat_weekday INTEGER,
    note TEXT DEFAULT '', max_sends INTEGER DEFAULT 6, stop_when_complete INTEGER DEFAULT 1,
    sent_count INTEGER DEFAULT 0, last_sent_at TIMESTAMP, status TEXT DEFAULT 'active',
    done_reason TEXT DEFAULT '', created_by TEXT DEFAULT '', created_by_name TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""

# ── the world outside, replaced ─────────────────────────────────────────────
CLAIM = {"claim_id": 5, "complainant_name": "Test Person", "complainant_phone": "9000000000",
         "claim_type": "health", "pipeline_stage": ""}
STATE = {}


def reset(send_result, template_ok=True, template_error=""):
    STATE.clear()
    STATE.update(send=send_result, tmpl_ok=template_ok, tmpl_err=template_error,
                 template_calls=[], nudges=[])


async def f_claim(cid):
    return dict(CLAIM)


async def f_pending(cid, ctype):
    return [{"key": "discharge", "en": "Discharge summary", "hi": "डिस्चार्ज समरी"},
            {"key": "final_bill", "en": "Final bill", "hi": "फ़ाइनल बिल"}]


async def f_draft(cid, keys, kind="request", note=""):
    return "please send"


async def f_preview(cid, **kw):
    return {"ok": True, "confirm": "c"}


async def f_send(cid, **kw):
    return dict(STATE["send"])


async def f_lang(cid, claim):
    return "hi"


async def f_journey(cid, event, extra=None, skip_phones=None):
    STATE["template_calls"].append((event, dict(extra or {})))
    return {"ok": STATE["tmpl_ok"], "error": STATE["tmpl_err"]}


async def f_notify(ids, subject, body, event_key="ops.notice", email=True, **kw):
    STATE["nudges"].append({"ids": list(ids), "subject": subject, "body": body,
                            "event_key": event_key, "email": email})
    return len(ids)


async def f_admins():
    return [{"staff_id": 1}]


dr._claim = f_claim
dr.draft_message = f_draft
dr.preview = f_preview
dr.send = f_send
dr._lang_for = f_lang
ck.pending_required_docs = f_pending
orch.wa_journey = f_journey
nnot.notify_staff_inapp = f_notify
nnot._super_admin_staff = f_admins


async def schedule(created_by="42", repeat="once"):
    async with aiosqlite.connect(db.DB_PATH) as c:
        cur = await c.execute(
            "INSERT INTO nidaan_wa_schedule (claim_id, next_at, repeat_rule, created_by, "
            "created_by_name) VALUES (5, datetime('now','-1 minute'), ?, ?, 'Asha')",
            (repeat, created_by))
        await c.commit()
        return cur.lastrowid


async def row(sid):
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        return dict(await (await c.execute(
            "SELECT * FROM nidaan_wa_schedule WHERE sch_id=?", (sid,))).fetchone())


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.execute("INSERT INTO nidaan_claims (claim_id) VALUES (5)")
        await c.commit()

    print("\nInside the 24 hours: the full message goes, nothing else\n")
    reset({"ok": True, "reached_complainant": True, "results": []})
    sid = await schedule()
    out = await sch.run_due()
    r = await row(sid)
    check("it counts as sent", out["sent"] == 1 and r["sent_count"] == 1, (out, r))
    check("...and no template is sent on top", STATE["template_calls"] == [])
    check("a one-off closes as sent", r["done_reason"] == "one-off reminder sent", r["done_reason"])
    n = STATE["nudges"]
    check("the person who set it hears", len(n) == 1 and n[0]["ids"] == [42], n)
    check("...that it went out", n and "went out" in n[0]["subject"], n)
    check("...on the bell and Telegram, not email",
          n and n[0]["email"] is False and n[0]["event_key"] == "doc.schedule_due", n)

    print("\nPast the 24 hours: the approved template goes instead\n")
    reset({"ok": True, "reached_complainant": False,
           "results": [{"kind": "to", "whatsapp": "no open WhatsApp window"}]})
    sid = await schedule()
    out = await sch.run_due()
    r = await row(sid)
    check("the approved reminder template is used",
          [e for e, _x in STATE["template_calls"]] == ["doc_reminder"], STATE["template_calls"])
    check("...naming the first missing document, in THEIR language",
          STATE["template_calls"] and STATE["template_calls"][0][1].get("doc_label")
          == "डिस्चार्ज समरी", STATE["template_calls"])
    check("...and it counts as sent", r["sent_count"] == 1 and r["done_reason"]
          == "one-off reminder sent", r)
    check("...and the setter is told it went as the template",
          STATE["nudges"] and "24-hour" in STATE["nudges"][0]["body"], STATE["nudges"])

    print("\nNobody reached: never reported as sent\n")
    reset({"ok": True, "reached_complainant": False,
           "results": [{"kind": "to", "whatsapp": "they replied STOP"}]},
          template_ok=False, template_error="opted_out")
    sid = await schedule()
    out = await sch.run_due()
    r = await row(sid)
    check("nothing is counted as sent", r["sent_count"] == 0 and out["sent"] == 0, (out, r))
    check("the schedule does NOT say 'reminder sent'",
          "sent" not in r["done_reason"] or "could not" in r["done_reason"], r["done_reason"])
    check("...it says it could not reach them, and why",
          r["done_reason"].startswith("could not reach them") and "opted_out" in r["done_reason"],
          r["done_reason"])
    nd = STATE["nudges"][0] if STATE["nudges"] else {}
    check("the setter is told to CALL", "call" in nd.get("subject", "").lower(), nd)
    check("...with the number", "9000000000" in nd.get("body", ""), nd.get("body"))

    print("\nA colleague asked minutes ago\n")
    reset({"ok": False, "asked_recently": True, "error": "Asha already asked today"})
    sid = await schedule()
    await sch.run_due()
    check("no template is pushed over a colleague's ask", STATE["template_calls"] == [],
          STATE["template_calls"])

    print("\nA schedule nobody in particular set\n")
    reset({"ok": True, "reached_complainant": True, "results": []})
    sid = await schedule(created_by="")
    await sch.run_due()
    check("it still reaches somebody (the admins, when nobody is on duty)",
          STATE["nudges"] and STATE["nudges"][0]["ids"] == [1], STATE["nudges"])

    print("\nMeta's failed receipt keeps its reason\n")
    w = flow.failure_reason({"status": "failed", "errors": [{"code": 131047,
                                                              "title": "Re-engagement message"}]})
    check("the 24-hour rule, in words", w.startswith("131047") and "24 hours" in w, w)
    w = flow.failure_reason({"errors": [{"code": 131026, "title": "Message undeliverable"}]})
    check("a number not on WhatsApp, in words", "cannot receive" in w, w)
    w = flow.failure_reason({"errors": [{"code": 999999, "title": "Something new"}]})
    check("an unknown code keeps Meta's own title", w == "999999 - Something new", w)
    check("a receipt with no error gives nothing", flow.failure_reason({"status": "failed"}) == "")
    w = flow.failure_reason({"errors": [{"code": "13; DROP TABLE", "title": "x" * 500}]})
    check("hostile input: a non-number code and a huge title are contained",
          len(w) <= 160 and "DROP" not in w, w)

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
