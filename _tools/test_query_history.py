# -*- coding: utf-8 -*-
'''Every query we put to a complainant must be kept, and each reply must land on its own ask.

Founder, 24 Sep: *"all history should be recording in this section only just so whosoever staff
is triggering it should know when the last time query been sent."*

A query used to live in columns ON THE CLAIM — cq_at, cq_by, cq_text, cq_channels — and each new
one OVERWROTE the one before. So the screen could show the most recent ask and nothing else. A
colleague could not see that the same thing had been asked twice last week, and "have we already
chased this?" had no answer anywhere in the system.

`nidaan_claim_queries` is the record now; the claim columns stay as a cached copy of the newest
row, because the board badges, the bucket filters and the WhatsApp reply matcher all read them.
Two stores for one fact is how things drift, so what is checked here is that they cannot:

  - every ask is kept, newest first
  - the claim's cached columns always equal the newest row
  - a reply lands on the newest UNANSWERED ask, not on the newest ask, and not on all of them
  - a second reply does not overwrite the first one's answer
  - a claim with no history answers cleanly rather than raising

    py -3.13 _tools/test_query_history.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite               # noqa: E402
import biz_database as db      # noqa: E402
import biz_nidaan_buckets as bk  # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="qhist-"), "t.db")
db.DB_PATH = DB
bk.DB_PATH = DB
PHONE = "9876500011"


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def ask(claim_id, text, who, channels="whatsapp+email", copies=""):
    """What contact_complainant() writes once a send has succeeded — both stores, together."""
    async with aiosqlite.connect(DB) as c:
        await c.execute(
            "INSERT INTO nidaan_claim_queries (claim_id, asked_by, asked_by_id, text, channels, "
            "copies) VALUES (?,?,?,?,?,?)", (claim_id, who, 1, text, channels, copies))
        await c.execute(
            "UPDATE nidaan_claims SET cq_at=CURRENT_TIMESTAMP, cq_by=?, cq_by_id=?, cq_text=?, "
            "cq_channels=?, cq_reply_at=NULL WHERE claim_id=?",
            (who, 1, text, channels, claim_id))
        await c.commit()
        # SQLite CURRENT_TIMESTAMP has one-second resolution; without this two asks in the same
        # second sort arbitrarily and the test would be checking luck.
        await asyncio.sleep(1.05)


async def main():
    await db.init_db()
    async with aiosqlite.connect(DB) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone) "
                        "VALUES (1,'ACME','a@b.com','9000000000')")
        await c.execute(
            "INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
            "insured_phone, complainant_name, complainant_phone, status) "
            "VALUES (300,1,'health','PRITI','%s','PRITI','%s','in_review')" % (PHONE, PHONE))
        await c.execute(
            "INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
            "insured_phone, complainant_name, status) "
            "VALUES (301,1,'health','NOBODY','9000000123','NOBODY','in_review')")
        await c.commit()

    print("\nWhat we have asked, and what came back\n")

    await ask(300, "Send the policy number", "Dr.Ashish")
    await ask(300, "Send the rejection letter", "TAMANNA", channels="whatsapp")
    await ask(300, "Send the discharge summary", "Dr.Ashish", copies="Branch PUNEICD-01")

    info = await bk.contact_recipients(300)
    hist = info.get("history") or []
    check("every ask is kept", len(hist) == 3, len(hist))
    check("...newest first", hist[0]["text"] == "Send the discharge summary", hist[0]["text"])
    check("...with who asked", hist[0]["asked_by"] == "Dr.Ashish", hist[0]["asked_by"])
    check("...and on which channels", hist[1]["channels"] == "whatsapp", hist[1]["channels"])
    check("...and who was copied", "PUNEICD" in (hist[0]["copies"] or ""), hist[0]["copies"])

    # The cached copy on the claim must agree with the newest row - two stores, one fact.
    async with aiosqlite.connect(DB) as c:
        c.row_factory = aiosqlite.Row
        row = dict(await (await c.execute(
            "SELECT cq_text, cq_by, cq_channels FROM nidaan_claims WHERE claim_id=300")).fetchone())
    check("the claim's cached copy matches the newest ask",
          row["cq_text"] == hist[0]["text"] and row["cq_by"] == hist[0]["asked_by"], row)

    # A reply must find the newest UNANSWERED ask.
    n = await bk.on_query_reply(PHONE, "text", "Here is the discharge summary")
    check("the reply is matched to the claim", n == 1, n)
    hist = (await bk.contact_recipients(300))["history"]
    check("...and lands on the newest ask", bool(hist[0]["reply_at"]), hist[0])
    check("...carrying what they said",
          "discharge" in (hist[0]["reply_text"] or ""), hist[0]["reply_text"])
    check("...and NOT on the older ones",
          not hist[1]["reply_at"] and not hist[2]["reply_at"],
          [hist[1]["reply_at"], hist[2]["reply_at"]])

    # Ask again, reply again: the first answer must survive.
    first_reply = hist[0]["reply_at"]
    await ask(300, "Also send the ID proof", "SHRADDHA")
    await bk.on_query_reply(PHONE, "text", "ID proof attached")
    hist = (await bk.contact_recipients(300))["history"]
    check("a later ask gets its own reply", bool(hist[0]["reply_at"]), hist[0])
    check("...and the earlier answer is untouched",
          hist[1]["reply_at"] == first_reply, (hist[1]["reply_at"], first_reply))
    check("...so the two answers are different rows",
          "ID proof" in (hist[0]["reply_text"] or ""), hist[0]["reply_text"])

    # A claim nobody has asked anything.
    empty = await bk.contact_recipients(301)
    check("a claim with no history answers cleanly", empty.get("history") == [], empty.get("history"))

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "every ask kept, every answer on the ask it answers"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
