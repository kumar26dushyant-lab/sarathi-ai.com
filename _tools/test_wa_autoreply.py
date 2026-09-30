# -*- coding: utf-8 -*-
'''The phone answering is not a person answering (claim #245, 30 Sep).

Our "claim registered" message reached the complainant's number and two AUTOMATIC replies came
back - a business greeting and an away message. The bot answered each (the same reply twice, one
second apart) and the contact proof recorded "wrote to us from this number". Neither was a person.

What these checks defend:
  * both of #245's messages, word for word, are recognised as automatic; ordinary replies are not;
  * the same text arriving again from a number counts as automatic;
  * an automatic message is not answered by the bot, is NOT proof of the mobile, and is shown on
    the claim in plain words;
  * two messages arriving together can win only ONE reply (the race that sent two);
  * a My Business claim's first line names the staff member, not "advisor".

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_autoreply.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="auto_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_wa_autoreply as auto              # noqa: E402
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_wa_orchestrator as orch           # noqa: E402
import biz_nidaan_contact_verify as cv              # noqa: E402
for m in (auto, flow, orch):
    m.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:400])


AWAY = "Thank you for your message. We're unavailable right now, but will respond as soon as possible."
GREET = ("यह मैसेज आपको न्यू भारत इंश्योरेंस बड़वानी से भेजा गया है, (1) मोटर इंश्योरेंस,थर्ड पार्टी,"
         "फर्स्ट पार्टी, जीरो डेप्रिसिएशन")


def payload(msisdn, wamid, text):
    return {"entry": [{"changes": [{"value": {"messages": [
        {"from": msisdn, "id": wamid, "type": "text", "text": {"body": text}}]}}]}]}


async def main():
    await db.init_db()
    check("#245's away message is recognised", auto.reads_automatic(AWAY))
    check("#245's business greeting is recognised", auto.reads_automatic(GREET))
    for human in ("haan documents bhej diye", "ok thanks", "Kal tak bhej dunga", "मेरा क्लेम कब होगा?"):
        check("a person's reply is not automatic: %r" % human, not auto.reads_automatic(human))

    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'ACME','a@example.invalid','9000000000','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
                        "insured_phone, complainant_phone, status) VALUES "
                        "(245,1,'health','RAJA KHAN','7693954468','7693954468','review_delivered')")
        await c.commit()

    answered = []

    async def fake_text(msisdn, text):
        answered.append(text)
    real = flow._on_inbound_text
    flow._on_inbound_text = fake_text
    await flow.handle_inbound_payload(payload("917693954468", "w1", GREET))
    await flow.handle_inbound_payload(payload("917693954468", "w2", AWAY))
    async with aiosqlite.connect(DBP) as c:
        early = (await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_contact_verifications WHERE claim_id=245")).fetchone())[0]
    check("two automatic messages do NOT confirm the mobile", early == 0, early)
    await flow.handle_inbound_payload(payload("917693954468", "w3", "Mera claim kab tak hoga?"))
    await flow.handle_inbound_payload(payload("917693954468", "w4", "Mera claim kab tak hoga?"))
    flow._on_inbound_text = real
    check("the bot is not asked to answer either automatic message",
          answered == ["Mera claim kab tak hoga?"], answered)
    check("...a person's question is answered", "Mera claim kab tak hoga?" in answered, answered)
    check("...and the same words sent again are treated as automatic", len(answered) == 1, answered)

    async with aiosqlite.connect(DBP) as c:
        acts = [r[0] for r in await (await c.execute(
            "SELECT summary FROM nidaan_claim_activity WHERE claim_id=245 AND kind='wa_auto_reply'")).fetchall()]
        proofs = [r[0] for r in await (await c.execute(
            "SELECT method FROM nidaan_contact_verifications WHERE claim_id=245")).fetchall()]
    check("automatic messages are shown on the claim, in plain words",
          len(acts) == 3 and all("Automatic reply from the complainant's phone" in a for a in acts), acts)
    check("...a person's message still proves the mobile - automatic ones never did",
          proofs == ["whatsapp_message"], proofs)

    # the race: two arrivals, one reply
    await flow.upsert_contact("919999999999", mark_inbound=True)
    wins = await asyncio.gather(*[orch._reserve_reply("919999999999", 120) for _ in range(5)])
    check("five messages arriving together win exactly ONE reply", sum(1 for w in wins if w) == 1, wins)
    check("...and nothing more for two hours", not await orch._reserve_reply("919999999999", 120))

    cid, _msg = await nid.submit_claim(
        account_id=1, user_id=None, claim_type="health", insured_name="TEST", insured_phone="9000000002",
        branch_code="SP-TEST01", origin="branch", payment_status="unpaid_lead", skip_eligibility=True,
        raised_by_staff_id=7, raised_by_name="Tamanna", raised_via="my_business")
    async with aiosqlite.connect(DBP) as c:
        note = (await (await c.execute(
            "SELECT note FROM nidaan_claim_status_log WHERE claim_id=? ORDER BY rowid LIMIT 1", (cid,))).fetchone())[0]
    check("a My Business claim's first line names who raised it", note == "Raised by Tamanna from My Business", note)

    # a file from a number we cannot match keeps its media id, so it can still be fetched
    real_media = flow._on_inbound_media

    async def no_media(*a, **k):
        return None
    flow._on_inbound_media = no_media
    await flow.handle_inbound_payload({"entry": [{"changes": [{"value": {"messages": [
        {"from": "918888888888", "id": "wdoc1", "type": "document",
         "document": {"id": "MEDIA123", "filename": "rejection.pdf", "caption": "claim papers"}}]}}]}]})
    flow._on_inbound_media = real_media
    async with aiosqlite.connect(DBP) as c:
        row = await (await c.execute("SELECT media_id, body FROM nidaan_wa_messages WHERE wa_message_id='wdoc1'")).fetchone()
    check("an incoming file keeps its media id and name - never lost", row and row[0] == "MEDIA123"
          and "rejection.pdf" in (row[1] or ""), row)

    import biz_nidaan_buckets as bk
    check("a staff code is never called an Authorized Partner",
          bk._origin_of({"origin": "branch", "branch_code": "SP-GJG7BA"}) == "Raised by staff SP-GJG7BA (My Business)")


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
