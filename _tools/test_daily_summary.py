# -*- coding: utf-8 -*-
'''The end-of-day summary: the team's for super-admins, each person's own for everyone else.

Founder, 30 Sep: "End of the day telegram summary bucket-wise working and also how many claims
move from one bucket to another, and who did it ... send to all superadmins and every staff will
get their individual working summary ... voice note summary too in their preferred language ...
it's saying dollar instead of rupee."

What these checks defend:

  * a bucket move is recorded with from, to and WHO (staff id), from every door that moves one;
  * super-admins get the team view: where claims are now with in/out today, the moves by person,
    who worked on how many claims and where, who recorded nothing, who is on leave;
  * a staff member gets their own day in their own language - and a day with nothing recorded
    sends nothing; somebody on leave gets nothing;
  * money is exact (Rs 588.82, not 589) and the voice text says rupees - never dollars;
  * it runs once a day, not again on a restart.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_daily_summary.py
'''
import asyncio
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

DBP = os.path.join(tempfile.mkdtemp(prefix="dsum_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_buckets as bk                     # noqa: E402
bk.DB_PATH = DBP
import biz_nidaan_moves as mv                       # noqa: E402
mv.DB_PATH = DBP
import biz_nidaan_daily_summary as ds               # noqa: E402
ds.DB_PATH = DBP
import biz_speakable as sp                          # noqa: E402

FAILED = 0
IST = timezone(timedelta(hours=5, minutes=30))


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:600])


async def main():
    await db.init_db()
    await bk.ensure_seeded()
    today = datetime.now(IST).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DBP) as c:
        staff = ((1, "Founder Admin", "super_admin", "en"), (2, "Dr Ashish", "sub_super_admin", "hi"),
                 (3, "Quiet Person", "team_member", "en"), (4, "Away Person", "team_member", "en"),
                 (5, "Chanchal", "team_member", "hinglish"))
        for sid, name, role, lang in staff:
            await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, "
                            "status, telegram_chat_id, telegram_lang) VALUES (?,?,?,?,?,'active',?,?)",
                            (sid, name, "s%d@example.invalid" % sid, "x", role, "900%d" % sid, lang))
        await c.execute("INSERT INTO nidaan_leave_requests (staff_id, start_date, end_date, status) "
                        "VALUES (4, ?, ?, 'approved')", (today, today))
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'ACME','a@example.invalid','9000000000','x')")
        for cid in range(201, 207):
            await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
                            "insured_phone, review_outcome, status, payment_status) "
                            "VALUES (?,1,'health','TEST PERSON','9000000001','can_fight','review_delivered',"
                            "'subscription')", (cid,))
        await c.execute("INSERT INTO nidaan_payments (dedup_key, source, total_paise, status, created_at) "
                        "VALUES ('t1','review',58882,'captured',datetime('now'))")
        # Dr Ashish uploaded documents on two claims and ticked one
        for tgt, act in ((201, "claim.doc_upload"), (202, "claim.doc_upload"), (202, "doc.tick"),
                         (205, "some.new_action")):
            await c.execute("INSERT INTO nidaan_audit_log (actor_type, actor_id, actor_name, action, "
                            "target_type, target_id) VALUES ('staff',2,'Dr Ashish',?,'claim',?)", (act, str(tgt)))
        await c.commit()

    # moves, through the real functions
    r1 = await bk.start_l2(201, actor="Dr Ashish", actor_id=2)
    r2 = await bk.start_l2(202, actor="Dr Ashish", actor_id=2)
    r3 = await bk.start_l2(203, actor="Chanchal", actor_id=5)
    check("claims start Level-2", r1.get("ok") and r2.get("ok") and r3.get("ok"), (r1, r2, r3))
    entry = r1.get("bucket")
    nxt = next((b["bucket_key"] for b in await bk.buckets()
                if b["bucket_key"] != entry and not b.get("is_park") and not b.get("is_terminal")), "")
    r4 = await bk.move(201, nxt, reason="drafting", actor="Dr Ashish", actor_id=2)
    check("a claim moves to the next bucket", r4.get("ok"), r4)

    async with aiosqlite.connect(DBP) as c:
        rows = (await (await c.execute(
            "SELECT claim_id, from_key, to_key, kind, staff_id FROM nidaan_bucket_move_log ORDER BY move_id")).fetchall())
    check("every move is recorded with from, to and who",
          [(r[0], r[1], r[2], r[4]) for r in rows] ==
          [(201, "l2_claims", entry, 2), (202, "l2_claims", entry, 2), (203, "l2_claims", entry, 5),
           (201, entry, nxt, 2)], rows)
    check("...and the kind of move", [r[3] for r in rows] == ["start", "start", "start", r4.get("kind")], rows)

    plan = await ds.build()
    msgs = {m["staff_id"]: m for m in plan["messages"]}
    check("the super-admin gets the team summary", msgs.get(1, {}).get("kind") == "team", list(msgs))
    team = msgs[1]["text"]
    bname = (await bk.bucket(entry))["name_en"]
    check("...where the claims are now, with in/out today",
          ("%s: 2 (+3 / −1)" % bname) in team, team)
    check("...Level-2 waiting counted, with what left it", "Level-2 claims (waiting): 3 (+0 / −3)" in team, team)
    check("...the moves, by person, from -> to",
          "Dr Ashish — 3 move(s)" in team and "Level-2 claims (waiting) → %s: 2" % bname in team, team)
    check("...Chanchal's move is named too", "Chanchal — 1 move(s)" in team, team)
    check("...who worked on how many claims and where",
          "Dr Ashish — 3 claim(s)" in team, team)
    check("...who recorded nothing", "Nothing recorded today:" in team and "Quiet Person" in team, team)
    check("...who is on leave (and not listed as idle)",
          "On leave: Away Person" in team and "Away Person" not in team.split("On leave")[0], team)
    check("...money exact, Indian format", "₹588.82" in team, team)

    ash = msgs.get(2)
    check("Dr Ashish (a sub-super-admin) gets his own day, not the team view", ash and ash["kind"] == "own", msgs.keys())
    check("...in Hindi, his language", ash and "आपने" in ash["text"] and "आपका दिन" in ash["text"], ash and ash["text"])
    check("...naming his claims and where they sit", ash and "NP-201" in ash["text"] and "NP-202" in ash["text"],
          ash and ash["text"])
    check("...his moves", ash and "→" in ash["text"], ash and ash["text"])
    check("...what he did, in words - an unknown action is 'other', never a code",
          ash and "दस्तावेज़ अपलोड किए 2" in ash["text"] and "some.new_action" not in ash["text"],
          ash and ash["text"])
    ch = msgs.get(5)
    check("Chanchal gets hers in Hinglish", ch and "Aapka din" in ch["text"], ch and ch["text"])
    check("a day with nothing recorded sends nothing", 3 not in msgs, list(msgs))
    check("somebody on leave gets nothing", 4 not in msgs, list(msgs))

    for sid, m in msgs.items():
        v = sp.speakable(m["voice"])
        check("voice for %s has no symbols and never says dollar" % m["name"],
              "₹" not in v and "$" not in v and "dollar" not in v.lower() and "*" not in v, v)
    check("the team voice says rupees", "rupees" in sp.speakable(msgs[1]["voice"]), msgs[1]["voice"])

    # once a day
    await nid.set_ops_setting("daily_summary_enabled", "1")
    first = await ds.run_daily_ops_summary()
    second = await ds.run_daily_ops_summary()
    check("it runs", first.get("ok"), first)
    check("...and does not run twice in a day", second.get("skipped") == "already sent today", second)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
