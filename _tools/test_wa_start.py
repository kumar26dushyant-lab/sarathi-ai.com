# -*- coding: utf-8 -*-
'''"Start WhatsApp collection" (founder, 2 Oct: "should not send in one click"):
  - the preview says who, which number, what will be asked - and sends NOTHING;
  - a junk complainant name ("OLKL;L;L;L;L;L;") is warned about;
  - a staff start is NOT the complainant's consent (opted_in is the campaign audience);
  - a person handling the chat by hand stops the bot on the template path too;
and the send guard's daily/weekly caps count delivered and read messages (they undercounted).

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_wa_start.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBP = os.path.join(tempfile.mkdtemp(prefix="wastart_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_wa_orchestrator as orch           # noqa: E402
import biz_nidaan_wa_flow as flow                   # noqa: E402
import biz_nidaan_wa_guard as guard                 # noqa: E402
import biz_nidaan_doc_checklist as ck               # noqa: E402
orch.DB_PATH = flow.DB_PATH = guard.DB_PATH = DBP
for m in (ck,):
    if hasattr(m, "DB_PATH"):
        m.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def one(q, *a):
    async with aiosqlite.connect(DBP) as c:
        r = await (await c.execute(q, a)).fetchone()
        return r if r else None


async def main():
    await db.init_db()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'A','a@example.invalid','9000000000','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                        "complainant_name, complainant_phone, status) VALUES "
                        "(41,1,'health','X','9000000041','OLKL;L;L;L;L;L;','9811100041','intimated')")
        await c.commit()
    await ck.seed_checklist_for_claim(41, "health")

    sent = []

    async def journey(cid, event, extra=None, skip_phones=None):
        sent.append((cid, event))
        return {"ok": True}
    real_journey = orch.wa_journey
    orch.wa_journey = journey
    try:
        p = await orch.start_for_claim(41, by="Ravi", preview=True)
        check("the preview answers who, which number and what is asked first",
              p.get("ok") and p.get("preview") and p.get("to", "").endswith("0041") and p.get("first_doc"), p)
        check("...and sends NOTHING", sent == [], sent)
        check("a junk complainant name is warned about", any("name looks wrong" in w for w in p.get("warnings") or []),
              p.get("warnings"))
        r = await orch.start_for_claim(41, by="Ravi")
        check("pressing Send starts it (the approved first message, they never wrote)", r.get("ok") and sent, (r, sent))
        row = await one("SELECT COALESCE(opted_in,0), COALESCE(opt_source,'') FROM nidaan_wa_contacts WHERE msisdn=?",
                        "919811100041")
        check("a staff start is NOT recorded as the complainant's consent (campaign audience)",
              row is not None and int(row[0]) == 0 and row[1] != "claimant_msg", row)

        async with aiosqlite.connect(DBP) as c:
            await c.execute("UPDATE nidaan_wa_contacts SET bot_paused=1, assigned_name='Suhana' WHERE msisdn='919811100041'")
            await c.commit()
        sent.clear()
        r = await orch.start_for_claim(41, by="Ravi")
        check("someone handling the chat by hand stops the bot - on the template path too",
              not r.get("ok") and r.get("error") == "human_takeover" and not sent, (r, sent))
    finally:
        orch.wa_journey = real_journey

    # the guard counts what reached them, whatever the webhook later called it
    async with aiosqlite.connect(DBP) as c:
        for st in ("sent", "delivered", "read", "failed"):
            await c.execute("INSERT INTO nidaan_wa_messages (msisdn, direction, body, status, send_class) "
                            "VALUES ('919800000099','out','x',?,'initiated')", (st,))
        await c.commit()
    n = await guard._counts("919800000099")
    check("the daily cap counts sent + delivered + read (not failed)", n["day_init"] == 3, n)

    src = open(os.path.join(ROOT, "sarathi_biz.py"), encoding="utf-8").read()
    check("the send route refuses without the person's confirmation",
          'if not (body and body.confirm):' in src)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
