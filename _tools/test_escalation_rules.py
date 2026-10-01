# -*- coding: utf-8 -*-
'''Escalation, 1 Oct (founder, with screenshots):
  - the escalation date cannot be before today - but a date already on file still saves
    (the gist form sends every field back);
  - a claim that comes back into Escalation already holding its date is on the Escalated step,
    not "Escalation Pending", so the step filter is true.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_escalation_rules.py
'''
import asyncio
import os
import sys
import tempfile
from datetime import timedelta

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import aiosqlite                  # noqa: E402
import biz_nidaan_buckets as bk   # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="esc-"), "t.db")
bk.DB_PATH = DB


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    import biz_database as db
    import biz_nidaan as n
    db.DB_PATH = DB
    n.DB_PATH = DB
    await db.init_db()
    await n.ensure_claim_documents_table()
    await bk.ensure_seeded()
    async with aiosqlite.connect(DB) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone) "
                        "VALUES (1,'ACME','a@b.com','9000000000')")
        for cid, stage in ((91, "escalation"), (92, "lokpal")):
            await c.execute(
                "INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                "pipeline_stage, pipeline_sub, created_at, status) VALUES (?,1,'health','X','9000000001',?,'',"
                "datetime('now','-3 day'),'in_review')", (cid, stage))
        await c.commit()

    today = bk._today_ist()
    yesterday = (today - timedelta(days=1)).isoformat()
    r = await bk.set_field(91, "escalation_date", yesterday, actor="t")
    check("an escalation date before today is refused", not r.get("ok") and "before today" in (r.get("error") or ""), r)
    r = await bk.set_field(91, "escalation_date", today.isoformat(), actor="t")
    check("today's date is accepted", r.get("ok"), r)
    # a past date already on file (recorded before the rule) still saves unchanged
    async with aiosqlite.connect(DB) as c:
        await c.execute("UPDATE nidaan_claim_fields SET value=? WHERE claim_id=91 AND field_key='escalation_date'",
                        (yesterday,))
        await c.commit()
    r = await bk.set_field(91, "escalation_date", yesterday, actor="t")
    check("a past date ALREADY on file saves again (the gist sends it back)", r.get("ok"), r)

    # back from Lokpal with the escalation already recorded -> Escalated, not Pending
    async with aiosqlite.connect(DB) as c:
        await c.execute("INSERT INTO nidaan_claim_fields (claim_id, field_key, value) VALUES (92,'escalation_date',?)",
                        (yesterday,))
        await c.commit()
    m = await bk.move(92, "escalation", reason="back from Lokpal for a correction", actor="t", force=True)
    async with aiosqlite.connect(DB) as c:
        sub = (await (await c.execute("SELECT pipeline_sub FROM nidaan_claims WHERE claim_id=92")).fetchone())[0]
    check("a claim returning to Escalation with its date recorded is on 'Escalated'",
          m.get("ok") and sub == "escalated", (m, sub))


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
