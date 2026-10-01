# -*- coding: utf-8 -*-
'''The pre-deploy review of 1 Oct found these; each check would have failed before its fix.

  1. after a staff WhatsApp reply the bot no longer talks over them, and its holding message is
     not counted as an answer;
  2. a logged-in visitor's chat is never joined to a WhatsApp thread (a staff reply there would
     have gone to someone else's WhatsApp);
  3. an old wait's count never silences a new one;
  4. a waiting chat younger than 45 minutes keeps its notice count;
  5. a staff forward that cannot be filed is kept, not lost;
  6. two people pressing Attach at once file the file once;
  7. a review upload follows a claim only if THAT purchase became the claim.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_review_fixes.py
'''
import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
ROOT = tempfile.mkdtemp(prefix="rvfix_")
DBP = os.path.join(ROOT, "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_bot_hold as hold                  # noqa: E402
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_notifications as nn               # noqa: E402
import biz_nidaan_doc_intake as intake              # noqa: E402
intake.DOCS_DIR = Path(ROOT) / "docs"
import biz_nidaan_wa_unsorted as srt                # noqa: E402
import biz_nidaan_wa_orchestrator as orch           # noqa: E402
import biz_nidaan_claim_authz as authz              # noqa: E402
import biz_av_scan as av                            # noqa: E402
hold.DB_PATH = flow.DB_PATH = srt.DB_PATH = orch.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    await db.init_db()
    await nid.ensure_claim_documents_table()

    # 1 ─ the bot does not talk over a person; its hold is not an answer
    await flow.log_message(direction="in", msisdn="915550000001", body="ok, sending")
    await flow.log_message(direction="out", msisdn="915550000001", body="please send the DS", sender="human")
    n, txt = await hold.message_for("wa:915550000001", "en")
    check("1. a person wrote on WhatsApp just now: no 'someone will reach out' over them", (n, txt) == (0, ""), (n, txt))
    await flow.log_message(direction="in", msisdn="915550000002", body="hello?")
    await flow.log_message(direction="out", msisdn="915550000002", body="Thank you for writing...", sender="hold")
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_wa_messages SET created_at=datetime('now','-2 hours') WHERE msisdn='915550000002'")
        await c.commit()
    waiting = [r["msisdn"] for r in await nn._unanswered_whatsapp(45)]
    check("1. ...and the bot's holding message does not count as an answer", "915550000002" in waiting, waiting)

    # 2 ─ a web chat is never joined to a WhatsApp thread
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (7,'Subscriber','s@example.invalid','9000000007','x')")
        await c.commit()
    wa_thread = await nid.create_support_thread(name="Complainant", contact="917000000077", account_id=7,
                                                channel="whatsapp", lang="hi")
    found = await nid.find_open_support_thread(account_id=7)
    check("2. a logged-in subscriber's chat does NOT reuse the complainant's WhatsApp thread",
          not found or found.get("thread_id") != wa_thread["thread_id"], found)
    again = await nid.find_open_support_thread(contact="917000000077", channel="whatsapp")
    check("2. ...while WhatsApp itself still finds its own thread", again and again["thread_id"] == wa_thread["thread_id"])

    # 3 ─ an old wait's count does not silence a new one
    for _ in range(3):
        await hold.take("wa:915550000003")
        async with aiosqlite.connect(DBP) as c:
            await c.execute("UPDATE nidaan_bot_holds SET last_at=datetime('now','-2 minutes') WHERE conv_key='wa:915550000003'")
            await c.commit()
    check("3. three holds used: silent now", await hold.take("wa:915550000003") == 0)
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_bot_holds SET last_at=datetime('now','-13 hours') WHERE conv_key='wa:915550000003'")
        await c.commit()
    check("3. ...but writing again the next day is a new wait and is answered", await hold.take("wa:915550000003") == 1)

    # 4 ─ a young waiting chat keeps its count
    key = "chat:wa:915550000004"
    await flow.log_message(direction="in", msisdn="915550000004", body="is anyone there")
    check("4. the handover notice is taken", await nn.chat_notice_allowed(key))

    async def open_():
        return True
    real_open = nid.is_within_business_hours
    nid.is_within_business_hours = open_

    async def quiet(*a, **k):
        return 1
    real_notify = nn.notify_staff_inapp
    nn.notify_staff_inapp = quiet
    await nn.sweep_unanswered()
    check("4. ...and the sweep does not wipe it while the chat is young and still waiting",
          await nn.chat_notices(key) == 1, await nn.chat_notices(key))
    nid.is_within_business_hours, nn.notify_staff_inapp = real_open, real_notify

    # 5 ─ a forward that cannot be filed is kept
    async def dl(media_id):
        return {"ok": True, "content": b"OggS voice", "mime": "audio/ogg"}

    async def clean(data):
        return True, ""

    async def may(staff, cid):
        return {"allowed": True}

    async def unreadable(*a, **k):
        return {"ok": False, "error": "unreadable"}
    orch._wa.download_media, av.scan_bytes, authz.assert_claim_access = dl, clean, may
    real_accept = intake.accept
    intake.accept = unreadable
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, status) "
                        "VALUES (55,7,'health','X','9000000001','review_delivered')")
        await c.commit()
    f = await srt.staff_forward({"staff_id": 3, "name": "Ravi", "role": "team_member"}, "919811100011", "MV", "audio/ogg",
                                filename="voice.ogg", caption="NP-55")
    check("5. a staff forward that is not a readable document is KEPT to sort, not lost",
          f["status"] == "to_sort" and f.get("item_id"), f)

    # 6 ─ two Attach presses, one filing
    filed = []

    async def accept(claim_id, account_id, files, **kw):
        filed.append(claim_id)
        await asyncio.sleep(0.05)
        return {"ok": True}
    intake.accept = accept
    staff = {"staff_id": 3, "name": "Suhana", "role": "team_member"}
    res = await asyncio.gather(srt.attach(f["item_id"], 55, staff=staff), srt.attach(f["item_id"], 55, staff=staff),
                               return_exceptions=True)
    ok = [r for r in res if isinstance(r, dict) and r.get("ok")]
    check("6. two people pressing Attach at once file it ONCE", len(ok) == 1 and len(filed) == 1, (res, filed))
    intake.accept = real_accept

    # 7 ─ a review upload follows only its own claim
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_per_claim_purchase (purchase_id, account_id, status, amount_paid, insured_name, insured_phone, "
                        "linked_claim_id, converted_to_claim_id) VALUES (91,7,'paid',588,'Y','9000000009',55,NULL)")
        await c.commit()
    did = await nid.save_claim_document(account_id=7, stored_name="z.pdf", original_name="z.pdf", file_size=1,
                                        mime_type="application/pdf", purchase_id=91)
    async with aiosqlite.connect(DBP) as c:
        cid = (await (await c.execute("SELECT claim_id FROM nidaan_claim_documents WHERE doc_id=?", (did,))).fetchone())[0]
    check("7. a review that did not become claim 55 does not put its upload on claim 55", not cid, cid)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
