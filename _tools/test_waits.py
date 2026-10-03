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

    print("\n-- Documents pending (3 Oct) --")
    one = await w.for_claim(61)
    check("the box fills itself with the checklist's missing papers", len(one.get("docs_missing") or []) >= 3,
          one.get("docs_missing"))
    check("'Documents pending' is the first reason staff see", one["choices"][0]["key"] == "docs_pending", one["choices"][:2])
    r = await w.set_reasons(61, ["docs_pending"], "", {"staff_id": 3, "name": "Ravi"}, notes={"docs_pending": "  "})
    check("ticking it with no list is refused", not r.get("ok") and "documents" in (r.get("error") or "").lower(), r)
    mylist = "Final bill\n- Discharge summary (page 2)\n\nHospital ICP"
    r = await w.set_reasons(61, ["docs_pending", "other"], "", {"staff_id": 3, "name": "Ravi"},
                            notes={"docs_pending": mylist, "other": "Waiting for the hospital to reply"})
    check("a list staff wrote is saved", r.get("ok"), r)
    t = {x["key"]: x for x in (await w.for_claim(61))["ticked"]}
    check("...one paper per line, tidied", t.get("docs_pending", {}).get("note") == "Final bill\nDischarge summary (page 2)\nHospital ICP",
          t.get("docs_pending"))
    check("...and 'Other' kept its words", t.get("other", {}).get("note") == "Waiting for the hospital to reply", t.get("other"))
    chips = (await w.for_rows([{"claim_id": 61, "review_outcome": "can_fight", "l2_payment_status": "due",
                                "payment_status": "unpaid_lead"}]))[61]
    dk = [c for c in chips if c["key"] in ("docs", "docs_pending")]
    check("ONE documents chip on a list, not two - staff's list, with the checklist count beside it",
          len(dk) == 1 and dk[0]["key"] == "docs_pending" and " of " in (dk[0].get("progress") or ""), dk)
    r = await w.set_reasons(61, ["docs_pending", "other"], "", {"staff_id": 3, "name": "Ravi"},
                            notes={"docs_pending": "Final bill", "other": "Waiting for the hospital to reply"})
    check("changing the list replaces it", r.get("ok") and r.get("added") == ["docs_pending"], r)
    async with aiosqlite.connect(DBP) as c:
        n = (await (await c.execute("SELECT COUNT(*) FROM nidaan_claim_waits WHERE claim_id=61 "
                                    "AND reason_key='docs_pending'")).fetchone())[0]
    check("...and the old list is kept as history", n == 2, n)

    print("\n-- one filter, one meaning --")
    check("'Documents pending' finds the automatic reason", w.matches([{"key": "docs", "auto": True}], "docs"))
    check("...and a list staff wrote", w.matches([{"key": "docs_pending"}], "docs"))
    check("'Nothing recorded' finds a claim with no reasons", w.matches([], "none") and not w.matches([{"key": "fee"}], "none"))
    check("no filter matches everything", w.matches([], "") and w.matches([{"key": "fee"}], ""))
    check("every list gets the same choices, 'Documents pending' first and 'Nothing recorded' last",
          [c["key"] for c in w.filter_choices()][0] == "docs" and w.filter_choices()[-1]["key"] == "none")

    print("\n-- the case board follows what staff ticked --")
    import biz_nidaan_case_state as cs
    cs.DB_PATH = DBP
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, status, "
                        "review_outcome, l2_payment_status, payment_status) VALUES "
                        "(62,1,'health','Y','9000000002','in_review','','','paid')")
        await c.commit()
    b = await cs.board()
    it = next(i for i in b["items"] if i["claim_id"] == 62)
    check("before anything is ticked, the board works it out (a claim in review is ours)", it["blocker"] == "internal", it["blocker"])
    await w.set_reasons(62, ["query_complainant"], "", {"staff_id": 3, "name": "Ravi"})
    b = await cs.board()
    it = next(i for i in b["items"] if i["claim_id"] == 62)
    check("ticking 'Query - complainant' puts the next move with the complainant", it["blocker"] == "complainant", it["blocker"])
    check("...and the board shows the same chip", [x["key"] for x in it.get("waits", [])] == ["query_complainant"], it.get("waits"))
    check("the board's 'Waiting on' filter finds it", any(i["claim_id"] == 62 for i in (await cs.board(wait="query_complainant"))["items"]))
    check("...and leaves out what does not match", not any(i["claim_id"] == 62 for i in (await cs.board(wait="insurer_reply"))["items"]))
    check("...with a count for every choice", (await cs.board()).get("by_wait", {}).get("query_complainant", 0) >= 1)
    await cs.set_blocker(62, "insurer", actor="Ravi")
    it = next(i for i in (await cs.board())["items"] if i["claim_id"] == 62)
    check("a person's own choice on the board still wins", it["blocker"] == "insurer", it["blocker"])
    st = await cs.for_claim(62)
    check("the claim drawer says what the board says", st.get("blocker") == "insurer", st.get("blocker"))

    ops = open(os.path.join(ROOT, "static", "nidaan_ops.html"), encoding="utf-8").read()
    check("All Claims, Level-2 Claims, the entry queue and the case board all offer the same filter",
          "claimWaitFilter(this.value)" in ops and "_setL2f('wait',this.value)" in ops
          and "l2StartWaitFilter(this.value)" in ops and "cbSet('wait'," in ops)
    check("All Claims shows the chips and no longer stops at 200",
          "${_waitChips(c.waits)}</td>\n      <td>${_uPay(c)}</td>" in ops and "params.set('limit','2000')" in ops)
    check("the bucket list, the L2 Claims list, the case sheet and the drawer all show it",
          "_waitChips(i.waits)" in ops and "_waitChips(c.waits)" in ops
          and "waitBox_' + id" in ops and 'id="waitBox_${c.claim_id}"' in ops)
    check("...and a bucket can be filtered by it", "l2WaitFilter(this.value)" in ops)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
