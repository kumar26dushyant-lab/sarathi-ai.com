# -*- coding: utf-8 -*-
'''WhatsApp like WhatsApp (founder, 2 Oct):
  - search across every chat: names, numbers and the words in any message;
  - each claim shows its own conversation - the very messages the inbox shows.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_inbox_g7.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="wainbox_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_wa_inbox as inbox                 # noqa: E402
flow.DB_PATH = inbox.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    await db.init_db()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) VALUES (1,'A','a@x.in','9000000000','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                        "complainant_name, complainant_phone, status) VALUES "
                        "(51,1,'health','INSURED','9811100051','Complainant','9811100052','intimated')")
        await c.commit()
    await flow.log_message(direction="in", msisdn="919811100052", body="I sent the discharge summary yesterday")
    await flow.log_message(direction="out", msisdn="919811100052", body="Thank you, we got it", sender="human")
    await flow.log_message(direction="in", msisdn="919811100051", body="This is the insured, any update?")
    await flow.log_message(direction="in", msisdn="919800000077", body="100% sure the discharge_summary is fine")
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT OR IGNORE INTO nidaan_wa_contacts (msisdn) VALUES ('919800000077')")
        await c.execute("UPDATE nidaan_wa_contacts SET display_name='Other Person' WHERE msisdn='919800000077'")
        # a message tagged to ANOTHER claim on the shared number must not show on this claim
        await c.execute("INSERT INTO nidaan_wa_messages (msisdn, direction, body, status, claim_id) "
                        "VALUES ('919811100052','out','about claim 99 only','sent',99)")
        await c.commit()

    r = await inbox.search("discharge")
    nums = [x["msisdn"] for x in r]
    check("search finds the words in any message, one row per chat", set(nums) == {"919811100052", "919800000077"}, r)
    check("...with the matching words as the snippet", all("discharge" in x["snippet"].lower() for x in r), r)
    check("a name is found too", [x["msisdn"] for x in await inbox.search("Other Pers")] == ["919800000077"])
    check("a number is found too", [x["msisdn"] for x in await inbox.search("11100051")] == ["919811100051"])
    check("% and _ are taken literally (no match-everything)", [x["msisdn"] for x in await inbox.search("100%")] == ["919800000077"]
          and len(await inbox.search("_summary")) == 1)
    check("a one-letter search returns nothing (no full dump)", await inbox.search("a") == [])

    t = await inbox.claim_thread(51)
    bodies = [m["body"] for m in t["messages"]]
    check("the claim's window shows BOTH its numbers' messages - the complainant's and the insured's",
          "I sent the discharge summary yesterday" in bodies and "This is the insured, any update?" in bodies, bodies)
    check("...and our reply, in order", bodies.index("I sent the discharge summary yesterday") < bodies.index("Thank you, we got it"))
    check("...but never a message tagged to another claim on a shared number", "about claim 99 only" not in bodies)
    check("...nor another person's chat", not any("100%" in b for b in bodies))

    # a number on SEVERAL claims (an agent's mobile): only the rows tagged to this claim
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                        "complainant_name, complainant_phone, status) VALUES "
                        "(52,1,'health','OTHER','9811100099','Other','9811100052','intimated')")
        await c.execute("INSERT INTO nidaan_wa_messages (msisdn, direction, body, status, claim_id) "
                        "VALUES ('919811100052','in','about claim 52 only','sent',52)")
        await c.commit()
    b51 = [m["body"] for m in (await inbox.claim_thread(51))["messages"]]
    b52 = [m["body"] for m in (await inbox.claim_thread(52))["messages"]]
    check("a shared number never shows another claim's messages (review, 2 Oct)",
          "about claim 52 only" not in b51 and "about claim 52 only" in b52, (b51, b52))
    check("...nor its untagged ones on either claim", "I sent the discharge summary yesterday" not in b52, b52)
    await flow.log_message(direction="in", msisdn="919811100051", body="tagged at the door")
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT OR IGNORE INTO nidaan_wa_contacts (msisdn) VALUES ('919811100051')")
        await c.execute("UPDATE nidaan_wa_contacts SET claim_id=51 WHERE msisdn='919811100051'")
        await c.commit()
    await flow.log_message(direction="in", msisdn="919811100051", body="tagged now")
    async with aiosqlite.connect(DBP) as c:
        cid = (await (await c.execute("SELECT claim_id FROM nidaan_wa_messages WHERE body='tagged now'")).fetchone())[0]
    check("a customer's message is tagged with their number's claim as it arrives", cid == 51, cid)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
