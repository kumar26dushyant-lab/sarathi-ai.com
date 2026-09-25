# -*- coding: utf-8 -*-
'''What the WhatsApp bot may say, and how much anyone may throw at it.

The founder's charter, 23-25 Sep 2026:
  * *"only verified phone numbers of complainant should be provided claim/case related info ...
    only restricted to document collection if anything is pending, but we should not provide info
    when it moves to consolidation"*
  * *"after consolidation we also have questions/queries ... those communication should not be
    restricted"*
  * *"anyone ask claim related details we should not be sharing, only if our team initiate
    discussion for details"*
  * *"anomalies detection unnecessary attachment bombardment, bot attack, etc. needs to be very
    strong as foundation"*

Security logic is the last place to trust a reading of the code, so every rule is exercised
against a real schema. What matters most here are the FAILURE directions, because they are
opposite on purpose and getting either backwards is silent:

  stance() FAILS CLOSED - an unreadable claim is not permission to talk about it. Being wrong
           costs a handoff.
  flood()  FAILS OPEN   - a complainant sending documents must not be stonewalled by a database
           hiccup. Being wrong costs a few wasted replies.

    py -3.13 _tools/test_wa_charter.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite                      # noqa: E402
import biz_database as db             # noqa: E402
import biz_nidaan as _n               # noqa: E402
import biz_nidaan_wa_charter as ch    # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="charter-"), "t.db")
for _m in (db, _n, ch):
    _m.DB_PATH = DB
import biz_nidaan_doc_checklist as _dc  # noqa: E402
_dc.DB_PATH = DB

PHONE = "919876500011"


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def claim(cid, *, stage="", asked=False, replied=False):
    async with aiosqlite.connect(DB) as c:
        await c.execute(
            "INSERT OR REPLACE INTO nidaan_claims (claim_id, account_id, claim_type, "
            "insured_name, insured_phone, complainant_name, complainant_phone, status, "
            "pipeline_stage, cq_at, cq_reply_at) VALUES (?,1,'health','P',?,'P',?,'in_review',?,?,?)",
            (cid, PHONE, PHONE, stage,
             "2026-09-20 10:00:00" if asked else None,
             "2026-09-20 11:00:00" if replied else None))
        await c.commit()


async def inbound(n, *, minutes_ago=1, msg_type="text"):
    async with aiosqlite.connect(DB) as c:
        for _ in range(n):
            await c.execute(
                "INSERT INTO nidaan_wa_messages (direction, msisdn, msg_type, body, created_at) "
                "VALUES ('in',?,?,'x',datetime('now',?))",
                (PHONE, msg_type, "-%d minutes" % minutes_ago))
        await c.commit()


async def main():
    await db.init_db()
    async with aiosqlite.connect(DB) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone) "
                        "VALUES (1,'A','a@b.com','9000000000')")
        await c.commit()

    print("\nWhat the bot may say\n")

    # ── identity comes first, always ────────────────────────────────────────
    await claim(1, stage="")
    s = await ch.stance(1, verified=False)
    check("an UNVERIFIED number gets nothing, even with a matching claim",
          s["stance"] == ch.STANCE_QUIET and not s["may_send_docs"], s)
    check("...and no stance ever permits narrating the claim", not s["may_reveal_detail"])

    s = await ch.stance(None, verified=True)
    check("a verified number with no claim gets nothing",
          s["stance"] == ch.STANCE_QUIET, s)

    # ── still collecting: the bot's actual job ──────────────────────────────
    await _dc.seed_checklist_for_claim(1, "health")
    s = await ch.stance(1, verified=True)
    check("while documents are pending the bot collects documents",
          s["stance"] == ch.STANCE_DOCS and s["may_send_docs"], s)
    check("...and still may not narrate the claim", not s["may_reveal_detail"])

    # ── past collection: the founder's line ─────────────────────────────────
    await claim(2, stage="live_cases")
    s = await ch.stance(2, verified=True)
    check("once it reaches Level-2 the bot goes quiet",
          s["stance"] == ch.STANCE_QUIET and not s["may_send_docs"], s)
    check("...and says why, so a handoff can carry a reason",
          "Level-2" in s["reason"], s["reason"])

    # ── the carve-out he named ──────────────────────────────────────────────
    await claim(3, stage="pending_draft", asked=True)
    s = await ch.stance(3, verified=True)
    check("a question WE asked is still answerable in Level-2",
          s["stance"] == ch.STANCE_ANSWER_ASK, s)
    check("...and it does not become permission to reveal detail",
          not s["may_reveal_detail"], s)

    await claim(4, stage="pending_draft", asked=True, replied=True)
    s = await ch.stance(4, verified=True)
    check("once they have answered it, the bot goes quiet again",
          s["stance"] == ch.STANCE_QUIET, s)

    # ── FAIL CLOSED ─────────────────────────────────────────────────────────
    s = await ch.stance(99999, verified=True)
    check("a claim that does not exist gets silence", s["stance"] == ch.STANCE_QUIET, s)
    real = ch.DB_PATH
    ch.DB_PATH = "/nonexistent/dir/no.db"
    s = await ch.stance(1, verified=True)
    ch.DB_PATH = real
    check("an unreadable database gets silence — NOT the benefit of the doubt",
          s["stance"] == ch.STANCE_QUIET and not s["may_send_docs"], s)

    # ── flood ───────────────────────────────────────────────────────────────
    print("\nHow much anyone may throw at it\n")
    f = await ch.flood(PHONE)
    check("a quiet number is fine", f["ok"], f)

    await inbound(8, minutes_ago=2)
    f = await ch.flood(PHONE)
    check("a real burst of documents and questions is still fine", f["ok"], f)

    await inbound(ch.FLOOD_MSGS_PER_10MIN, minutes_ago=2)
    f = await ch.flood(PHONE)
    check("a machine-gun in ten minutes is stopped", not f["ok"], f)
    check("...and says what it counted", "ten minutes" in f["reason"], f["reason"])

    # Attachments: the expensive flood. Each one is stored, scanned and read by a model.
    # SPREAD OVER THE HOUR, which is what makes the media rule worth having: 26 attachments
    # paced out stays under every message limit and is still a bombardment. (My first version of
    # this test dumped them all into five minutes, where the ordinary message rule catches it and
    # the media rule proves nothing.)
    other = "919876500099"
    async with aiosqlite.connect(DB) as c:
        for i in range(ch.FLOOD_MEDIA_PER_HOUR + 1):
            await c.execute(
                "INSERT INTO nidaan_wa_messages (direction, msisdn, msg_type, body, created_at) "
                "VALUES ('in',?,'image','x',datetime('now',?))",
                (other, "-%d minutes" % (i * 2 + 1)))
        await c.commit()
    f = await ch.flood(other, is_media=False)
    check("paced-out attachments slip past the MESSAGE limits", f["ok"], f)
    f = await ch.flood(other, is_media=True)
    check("...but the attachment rule catches them", not f["ok"], f)
    check("...and says it counted attachments, not messages",
          "attachment" in f["reason"], f["reason"])

    # ── FAIL OPEN, the other way on purpose ─────────────────────────────────
    ch.DB_PATH = "/nonexistent/dir/no.db"
    f = await ch.flood(PHONE)
    ch.DB_PATH = real
    check("an unreadable database does NOT stonewall a real complainant", f["ok"], f)

    f = await ch.flood("")
    check("a missing number does not raise", f["ok"], f)

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "identity first, documents only while needed, and no flood reaches the bot"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
