# -*- coding: utf-8 -*-
'''Why is this claim waiting? (founder, 2 Oct - approved as proposed, "Other" in their own words)
  - automatic: documents (have / need, and which are missing), L2 fee unpaid, authorization sent
    but not accepted;
  - ticked by staff, several at once; "Other" needs words; unticking keeps the history;
  - the bucket list carries them as chips.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_waits.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBP = os.path.join(tempfile.mkdtemp(prefix="waits_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_buckets as bk                     # noqa: E402
bk.DB_PATH = DBP
import biz_nidaan_doc_checklist as ck               # noqa: E402
import biz_nidaan_waits as w                        # noqa: E402

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
    await bk.ensure_seeded()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone) VALUES (1,'A','a@b.com','9000000000')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, status, "
                        "review_outcome, l2_payment_status, payment_status, pipeline_stage, pipeline_sub) VALUES "
                        "(61,1,'health','X','9000000001','in_review','can_fight','due','unpaid_lead','live_cases','')")
        await c.execute("INSERT INTO nidaan_claimant_portal (claim_id, consent_pushed_at) VALUES (61, datetime('now'))")
        await c.commit()
    await ck.seed_checklist_for_claim(61, "health")

    one = await w.for_claim(61)
    keys = {a["key"] for a in one["auto"]}
    check("automatic: documents short, fee unpaid, authorization not accepted", keys == {"docs", "fee", "auth"}, keys)
    docs = next(a for a in one["auto"] if a["key"] == "docs")
    check("...documents say how many of how many, and which are MISSING by name",
          " of " in docs["label"] and docs.get("missing"), docs)

    r = await w.set_reasons(61, ["other"], "", {"staff_id": 3, "name": "Ravi"})
    check("'Other' without words is refused", not r.get("ok"), r)
    r = await w.set_reasons(61, ["query_complainant", "other"], "Waiting for the hospital to reply",
                            {"staff_id": 3, "name": "Ravi"})
    check("several reasons can be ticked at once, 'Other' in their own words", r.get("ok") and len(r["added"]) == 2, r)
    t = (await w.for_claim(61))["ticked"]
    check("...each records who ticked it", all(x["by"] == "Ravi" for x in t) and len(t) == 2, t)
    r = await w.set_reasons(61, ["other"], "Waiting for the hospital to reply", {"staff_id": 3, "name": "Ravi"})
    check("unticking one clears it", r.get("cleared") == ["query_complainant"], r)
    async with aiosqlite.connect(DBP) as c:
        n = (await (await c.execute("SELECT COUNT(*) FROM nidaan_claim_waits WHERE claim_id=61")).fetchone())[0]
    check("...but keeps it as history (nothing deleted)", n == 2, n)
    check("an unknown reason is refused", not (await w.set_reasons(61, ["made_up"], "", {"name": "x"})).get("ok"))

    b = await bk.board("live_cases")
    row = next(i for i in b["items"] if i["claim_id"] == 61)
    keys = [x["key"] for x in row.get("waits", [])]
    check("the bucket list carries every reason as a chip", set(keys) == {"docs", "fee", "auth", "other"}, keys)

    ops = open(os.path.join(ROOT, "static", "nidaan_ops.html"), encoding="utf-8").read()
    check("the bucket list, the L2 Claims list, the case sheet and the drawer all show it",
          "_waitChips(i.waits)" in ops and "_waitChips(c.waits)" in ops
          and "waitBox_' + id" in ops and 'id="waitBox_${c.claim_id}"' in ops)
    check("...and a bucket can be filtered by it", "l2WaitFilter(this.value)" in ops)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
