# -*- coding: utf-8 -*-
'''A sub-state tab must not renumber the bucket it sits in.

Founder, 24 Sep, with two screenshots: the Escalation bucket showed
*All 6 · Escalation Pending 5 · Escalation Query 0 · Escalated 1*. He clicked "Escalation
Pending" and it became *All 5 · Escalation Pending 5 · Escalation Query 0 · Escalated 0*.

The numbers moved when he touched them, and a tab reported **0** about a claim that exists.

board() was applying the `sub` filter in the SQL WHERE clause and then computing sub_counts,
matching, late, red, ours, docs_short and blocked_fields from the rows that survived it. So every
figure on the screen described the tab instead of the pile it was sitting above.

Pinned here:
  - the chips count the BUCKET, identical whichever tab is open
  - the list itself does narrow
  - a SEARCH still narrows everything, because a search changes what you are looking at while a
    tab is only a slice of that
  - the figures above the tabs (late/red/ours/docs_short/blocked_fields/closing_window) never
    move either - they were part of the same bug

Runs against a temporary database.

    py -3.13 _tools/test_bucket_counts.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite                  # noqa: E402
import biz_nidaan_buckets as bk   # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="buckets-"), "t.db")
bk.DB_PATH = DB


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def main():
    # Real schema, so a column this function reads cannot quietly not exist. Two builders,
    # because nidaan_claim_documents is created by its own ensure_ function on boot rather than
    # by init_db, and board() joins to it.
    import biz_database as db
    import biz_nidaan as n
    db.DB_PATH = DB
    n.DB_PATH = DB
    await db.init_db()
    await n.ensure_claim_documents_table()

    async with aiosqlite.connect(DB) as c:
        # phone is NOT NULL on the real schema - which is the point of using the real schema.
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone) "
                        "VALUES (1,'ACME','a@b.com','9000000000')")
        # Six claims in Escalation: five pending, one escalated. Exactly his screenshot.
        rows = [(70 + i, 'escalation_pending', 'NISHANT %d' % i) for i in range(5)]
        rows.append((80, 'escalated', 'ONE THAT IS ESCALATED'))
        for cid, sub, name in rows:
            await c.execute(
                # account_id, claim_type, insured_name and insured_phone are the NOT NULL columns
                # with no default — asked of the schema rather than discovered one error at a time.
                "INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
                "insured_phone, complainant_name, pipeline_stage, pipeline_sub, created_at, "
                "status) VALUES (?,1,'health',?,'9000000001',?,'escalation',?,"
                "datetime('now','-1 day'),'in_review')",
                (cid, name, name, sub))
        await c.commit()

    print("\nA tab must not renumber its own bucket\n")

    allv = await bk.board("escalation")
    check("the bucket holds 6", allv["matching"] == 6, allv["matching"])
    check("...5 pending, 1 escalated",
          allv["sub_counts"].get("escalation_pending") == 5
          and allv["sub_counts"].get("escalated") == 1, allv["sub_counts"])
    check("...and shows all 6", len(allv["items"]) == 6, len(allv["items"]))

    pend = await bk.board("escalation", sub="escalation_pending")
    check("on the Pending tab the bucket STILL says 6", pend["matching"] == 6,
          "said %s" % pend["matching"])
    check("...Escalated STILL says 1, not 0",
          pend["sub_counts"].get("escalated") == 1, pend["sub_counts"])
    check("...Pending still says 5",
          pend["sub_counts"].get("escalation_pending") == 5, pend["sub_counts"])
    check("...but the LIST narrows to 5", len(pend["items"]) == 5, len(pend["items"]))
    check("...and it says so", pend.get("showing") == 5, pend.get("showing"))
    check("...and every row really is pending",
          all(i["sub"] == "escalation_pending" for i in pend["items"]))

    esc = await bk.board("escalation", sub="escalated")
    check("the Escalated tab shows its 1", len(esc["items"]) == 1, len(esc["items"]))
    check("...without claiming the bucket has only 1", esc["matching"] == 6, esc["matching"])

    # The figures ABOVE the tabs were computed the same wrong way.
    for key in ("late", "red", "ours", "docs_short", "blocked_fields", "closing_window"):
        check("'%s' is the same on every tab" % key,
              allv.get(key) == pend.get(key) == esc.get(key),
              "%s / %s / %s" % (allv.get(key), pend.get(key), esc.get(key)))

    # A search is a different intent and SHOULD narrow the counts.
    srch = await bk.board("escalation", q="ONE THAT IS")
    check("a SEARCH does narrow the counts — it changes what you are looking at",
          srch["matching"] == 1, srch["matching"])
    check("...and a tab inside a search narrows only the list",
          (await bk.board("escalation", q="NISHANT",
                          sub="escalation_pending"))["matching"] == 5)

    # An empty bucket must not throw.
    empty = await bk.board("lokpal")
    check("an empty bucket answers cleanly",
          empty["matching"] == 0 and empty["items"] == [], empty["matching"])

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "the chips describe the bucket, whichever tab is open"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
