# -*- coding: utf-8 -*-
'''A file sent while a person holds the chat is SAVED - never dropped (NP-123, 30 Sep).

Brajesh Gupta's chat had been handed to a person; then he sent eight files - discharge summary,
claim form, final bills, investigation reports. The document path returned "human_takeover" and
threw every one away.

What these checks defend:
  * during a takeover every file is still saved to the claim, with the sender's file name;
  * the bot says nothing (the person on the chat decides what to say);
  * the people on the claim are told - once for a burst, not once per file;
  * outside a takeover nothing changes: the bot still answers.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_takeover_docs.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="tko_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_wa_orchestrator as orch           # noqa: E402
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_doc_intake as intake              # noqa: E402
orch.DB_PATH = flow.DB_PATH = DBP

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
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'ACME','a@example.invalid','9000000000','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                        "complainant_phone, status) VALUES (123,1,'health','RACHNA GUPTA','8103283241',"
                        "'8103283241','review_delivered')")
        await c.commit()
    await flow.upsert_contact("918103283241", mark_inbound=True)
    await orch.pause_bot("918103283241", by="support")

    saved, said, told = [], [], []

    async def dl(media_id):
        return {"ok": True, "content": b"%PDF-1.4 test " + media_id.encode()}

    async def accept(claim_id, account_id, files, **kw):
        saved.append((claim_id, files[0][0], kw.get("source")))
        return {"ok": True, "stored": 1, "total": 1, "pending": []}

    async def send_text(msisdn, text):
        said.append(text)

    async def tell(claim_id, msisdn, text):
        told.append(text)
    orch._wa.download_media, orch._wa.send_text, orch._tell_staff_inbound = dl, send_text, tell
    intake.accept = accept

    names = ["DISCHARGE SUMMARY.pdf", "claim form filled documents.pdf", "final hosptial bills.pdf",
             "Investigation Reports.pdf", "230222428240027469.pdf", "Dr. Prescription.pdf",
             "2510120638.pdf", "../../etc/passwd.pdf"]
    results = [await orch.handle_inbound_document("918103283241", "M%d" % i, "application/pdf", filename=n)
               for i, n in enumerate(names)]
    check("every file sent during a takeover is saved to the claim",
          len(saved) == 8 and all(s[0] == 123 and s[2] == "whatsapp" for s in saved), saved)
    check("...with the sender's own file name", saved[0][1] == "DISCHARGE SUMMARY.pdf", saved[:2])
    check("...and a hostile file name is made safe", "/" not in saved[7][1] and ".." not in saved[7][1].replace("..pdf", ""), saved[7])
    check("...each reported as held by a person", all(r.get("ok") and r.get("held_by_person") for r in results), results[:2])
    check("the bot said nothing", said == [], said)
    check("the people on the claim were told - once for the burst", len(told) == 1, told)

    # outside a takeover the bot answers as before
    await orch.resume_bot("918103283241") if hasattr(orch, "resume_bot") else None
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_wa_contacts SET bot_paused=0 WHERE msisdn='918103283241'")
        await c.commit()
    said.clear()
    r = await orch.handle_inbound_document("918103283241", "M99", "application/pdf", filename="bill.pdf")
    check("without a takeover the bot still acknowledges the file", r.get("ok") and len(said) == 1, (r, said))


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
