# -*- coding: utf-8 -*-
'''While nobody from our team is on the chat, the bot tells them our hours - three times at most.

Founder, 1 Oct: homepage bot, dashboard bot and WhatsApp bot - out of office hours (10am-6pm IST)
or when nobody is free - tell the customer our office timings and that someone will reach out,
then hand over; the LAST message is the bot's; "this message 3 time if user is not okay to leave
the chat and then silent"; and staff Telegram about a waiting chat "only 2 times ... not in every
hour".

What these checks defend:
  * the message reads the office hours from the Support setting, says when we open next, in
    English, Hindi and Hinglish, and never mentions a claim;
  * at most three per waiting chat, never two within a minute, then silence; a staff reply on
    WhatsApp or on the website chat restarts the count;
  * WhatsApp under a takeover and the unverified path both send it, and tell staff ONCE;
  * the sweep sends two notices per chat at most, only in office hours, and counts a WhatsApp
    chat and its support thread as one customer;
  * the website chat route uses the same module and no longer hard-codes the hours.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_bot_hold.py
'''
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="hold_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_bot_hold as hold                  # noqa: E402
import biz_nidaan_wa_orchestrator as orch           # noqa: E402
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_notifications as nn               # noqa: E402
hold.DB_PATH = orch.DB_PATH = flow.DB_PATH = DBP

IST = timezone(timedelta(hours=5, minutes=30))
CFG = {"days": [0, 1, 2, 3, 4], "start": "10:00", "end": "18:00"}
FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:400])


async def age(key, seconds):
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_bot_holds SET last_at=datetime('now', ?) WHERE conv_key=?",
                        ("-%d seconds" % seconds, key))
        await c.commit()


async def main():
    await db.init_db()
    # ── the words ────────────────────────────────────────────────────────
    fri_night = datetime(2026, 10, 2, 21, 0, tzinfo=IST)      # a Friday, 9 pm
    m = hold.compose(1, open_now=False, cfg=CFG, lang="en", now=fri_night)
    check("out of hours: our office hours, read from the setting", "Mon–Fri, 10 am–6 pm IST" in m, m)
    check("...says we are closed and WHEN we will reach out", "closed" in m and "on Monday at 10 am" in m, m)
    check("...and thanks them for their patience", "patience" in m, m)
    m = hold.compose(1, open_now=False, cfg=CFG, lang="en", now=datetime(2026, 10, 1, 7, 0, tzinfo=IST))
    check("early morning on a working day: 'today at 10 am'", "today at 10 am" in m, m)
    m = hold.compose(1, open_now=False, cfg=CFG, lang="en", now=datetime(2026, 10, 1, 19, 0, tzinfo=IST))
    check("weekday evening: 'tomorrow at 10 am'", "tomorrow at 10 am" in m, m)
    m = hold.compose(1, open_now=True, cfg=CFG, lang="en")
    check("in hours: someone will reach out shortly", "shortly" in m and "closed" not in m, m)
    check("Hindi", "ऑफ़िस" in hold.compose(1, open_now=False, cfg=CFG, lang="hi", now=fri_night))
    check("Hinglish", "office band hai" in hold.compose(1, open_now=False, cfg=CFG, lang="hinglish", now=fri_night))
    m3 = hold.compose(3, open_now=False, cfg=CFG, lang="en", now=fri_night)
    check("the third says they need not wait on the chat", "don't need to wait" in m3, m3)
    for w in ("claim", "NP-", "₹", "document"):
        check("never mentions %r" % w, w not in m and w not in m3)
    check("a changed setting changes the words",
          "Mon–Sat, 9 am–5 pm IST" in hold.compose(1, open_now=True, cfg={"days": [0, 1, 2, 3, 4, 5],
                                                                        "start": "09:00", "end": "17:00"}, lang="en"))

    # ── three, then silent ───────────────────────────────────────────────
    k = "wa:919000000001"
    got = [await hold.take(k)]
    got.append(await hold.take(k))                       # within the minute: no
    await age(k, 120)
    got.append(await hold.take(k))
    await age(k, 120)
    got.append(await hold.take(k))
    await age(k, 120)
    got.append(await hold.take(k))
    check("1st, (not within a minute), 2nd, 3rd, then silent", got == [1, 0, 2, 3, 0], got)
    burst = await asyncio.gather(*[hold.take("wa:burst") for _ in range(5)])
    check("five messages at once get ONE holding reply", sorted(burst) == [0, 0, 0, 0, 1], burst)
    await flow.log_message(direction="out", msisdn="919000000001", body="Hello, Suhana here", sender="human")
    check("a staff WhatsApp reply restarts the count", await hold.take(k) == 1)
    tid = (await nid.create_support_thread(name="Visitor", contact="v@example.invalid", channel="web",
                                           lang="en"))["thread_id"]
    for _ in range(3):
        await hold.take("sup:%s" % tid)
        await age("sup:%s" % tid, 120)
    await nid.add_support_message(tid, "staff", "Hi, how can I help?")
    check("a staff reply on the website chat restarts its count", await hold.take("sup:%s" % tid) == 1)

    # ── WhatsApp: takeover and unverified paths ───────────────────────────
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'ACME','a@example.invalid','9000000000','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
                        "insured_phone, complainant_phone, status) VALUES (123,1,'health','X','8103283241',"
                        "'8103283241','review_delivered')")
        await c.commit()
    sent, told = [], []

    async def send_text(to, body):
        sent.append(body)
        return {"ok": True}

    async def tell(cid, msisdn, text):
        told.append(text)

    async def esc(tid):
        told.append("escalated")
    orch._wa.send_text, orch._tell_staff_inbound = send_text, tell
    nn.on_support_escalated = esc
    real_hours0 = nid.is_within_business_hours

    async def _open():
        return True

    async def _closed():
        return False
    # at night: the customer is told, nobody on staff is pinged
    nid.is_within_business_hours = _closed
    await flow.upsert_contact("917000000001", mark_inbound=True)
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
                        "insured_phone, complainant_phone, status) VALUES (124,1,'health','Y','7000000001',"
                        "'7000000001','review_delivered')")
        await c.commit()
    await orch.handle_inbound_text("917000000001", "hello at night")
    check("at night the customer gets the office-hours message", any("closed right now" in x or "band hai" in x
                                                                    or "बंद है" in x for x in sent), sent)
    check("...and nobody on staff is pinged at night", [t for t in told if t != "escalated"] == [], told)
    sent.clear(); told.clear()
    nid.is_within_business_hours = _open
    await flow.upsert_contact("918103283241", mark_inbound=True)
    for i in range(5):
        await orch.handle_inbound_text("918103283241", "Apko kya chahiye clear kare %d" % i)
        await age("wa:918103283241", 120)
    holding = [s for s in sent if "NidaanPartner" in s and ("reach out" in s or "sampark" in s or "संपर्क" in s)]
    check("unverified complainant: the holding message, three times in all", len(holding) == 3, sent)
    check("...never the old 'tell us what the claim is for' text", not any("kaunsi insurance company" in s for s in sent), sent)
    check("...staff told once for the wait, not per message", told.count("escalated") == 1 and len(told) == 2, told)
    nid.is_within_business_hours = real_hours0

    # ── the sweep: two notices per chat, office hours only ────────────────
    notices = []

    async def fake_notify(ids, subject, body, **kw):
        notices.append((subject, body))
        return 1

    async def admins():
        return [{"staff_id": 1}]
    nn.notify_staff_inapp, nn._super_admin_staff = fake_notify, admins
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_wa_messages (direction, msisdn, msg_type, body, created_at) "
                        "VALUES ('in','919111111111','text','hello?', datetime('now','-4 hours'))")
        await c.execute("UPDATE nidaan_support_threads SET sa_escalated_at=datetime('now','-4 hours'), "
                        "status='escalated', contact='919111111111' WHERE thread_id=?", (tid,))
        await c.commit()
    real_hours = nid.is_within_business_hours

    async def closed():
        return False

    async def open_():
        return True
    nid.is_within_business_hours = closed
    await nn.sweep_unanswered()
    check("out of office hours: no notice at all", notices == [], notices)
    nid.is_within_business_hours = open_
    for _ in range(4):
        await nn.sweep_unanswered()
    subjects = [s for s, _ in notices]
    check("in office hours: two notices for the chat, never a third", len(subjects) == 2, subjects)
    check("...the first to whoever is on duty, the second says it is the last",
          "waiting for a reply" in subjects[0] and "still unanswered" in subjects[1]
          and "final notice" in notices[1][1], notices)
    check("...and the WhatsApp chat and its support thread are ONE customer",
          all("Support #" not in b for _, b in notices), notices)
    nid.is_within_business_hours = real_hours

    src = open("sarathi_biz.py", encoding="utf-8").read()
    route = src[src.index('async def nidaan_support_message('):]
    route = route[:route.index("\n@app.")]
    check("the website chat uses the same module", "_hold.message_for(" in route)
    check("...and no longer hard-codes the hours", "Mon–Fri, 10am–6pm IST" not in route, "hard-coded hours")
    check("...and while waiting for a person the AI is not asked",
          route.index('if _prev_status == "escalated":') < route.index("nidaan_support_reply("))
    rep = src[src.index("async def ops_support_reply("):]
    rep = rep[:rep.index("\n@app.")]
    check("a Support reply on a WhatsApp chat is SENT on WhatsApp (it used to be saved only)",
          "_inbox.send_human(" in rep and rep.index("_inbox.send_human(") < rep.index("add_support_message("))
    check("...with the WhatsApp screen's permission, and not saved if WhatsApp refuses",
          "_require_wa_reply(request)" in rep and 'raise HTTPException(status_code=400, detail="Not sent to WhatsApp' in rep)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
