# -*- coding: utf-8 -*-
'''The pager's total must match the rows it is paging, under every filter.

Founder, 24 Sep: *"all claims, L2 claims, buckets, accounts all section should have pages option
because as claims are increasing the scrolling is getting increasing."*

A pager needs to know how many match. The endpoint returned `count: len(claims)` — the size of
the page it had just built — so no screen could say "30 of 188" or know a second page existed.

The total is counted with the SAME `where` and the SAME params as the rows, which is the only
way it cannot drift. Two things make that non-trivial, and both are checked here because getting
either wrong produces a confidently wrong number rather than an error:

  - the conditions reference `a.branch_code`, `a.owner_name`, `a.firm_name` and `sub.plan`, so
    the count has to carry the same joins. Counting from nidaan_claims alone fails outright on a
    branch filter and overcounts wherever the accounts INNER JOIN would have dropped a row.
  - the row query prepends [staff_id, staff_id] for a subquery in its SELECT list. Those params
    belong to the columns, not the WHERE, and passing them to the count would bind the wrong
    values to the filters.

So the test does not check the total against a number I typed. It checks it against the number of
rows the same call returns with the limit lifted — the only definition that matters.

    py -3.13 _tools/test_claims_total.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite        # noqa: E402
import biz_database as db   # noqa: E402
import biz_nidaan as n  # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="total-"), "t.db")
db.DB_PATH = DB
n.DB_PATH = DB


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def seed():
    await db.init_db()
    await n.ensure_claim_documents_table()
    async with aiosqlite.connect(DB) as c:
        for aid, nm, br in ((1, 'ACME HEALTH', 'BIAORA-01'),
                            (2, 'BETA CORP', 'SP-GJG7BA'),
                            (3, 'GAMMA LLP', 'BIAORA-01')):
            await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, firm_name, "
                            "email, phone, branch_code) VALUES (?,?,?,?,?,?)",
                            (aid, nm, nm + ' LTD', 'a%d@x.com' % aid, '90000000%02d' % aid, br))
        # 47 claims so a 30-per-page default really has a second page.
        for i in range(47):
            aid = (i % 3) + 1
            await c.execute(
                "INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
                "insured_phone, complainant_name, status, payment_status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,datetime('now',?))",
                (500 + i, aid, 'health', 'PERSON %d' % i, '99999000%02d' % i,
                 'PERSON %d' % i,
                 'intimated' if i % 2 else 'review_delivered',
                 'paid' if i % 3 else 'unpaid_lead', '-%d hours' % i))
        # One archived claim — it must not be counted by a default view.
        await c.execute(
            "INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
            "insured_phone, complainant_name, status, archived, created_at) "
            "VALUES (9999,1,'health','ARCHIVED ONE','9111111111','ARCHIVED ONE','intimated',1,"
            "datetime('now'))")
        await c.commit()


async def both(**kw):
    """The total the endpoint would report, and the true number of matching rows."""
    st: dict = {}
    await n.get_claims_ops(staff_id=1, role="super_admin", limit=30, offset=0, stats=st, **kw)
    everything = await n.get_claims_ops(staff_id=1, role="super_admin", limit=100000,
                                        offset=0, **kw)
    return st.get("total"), len(everything)


async def main():
    await seed()
    print("\nThe pager's total\n")

    for label, kw in (
        ("no filter",                     {}),
        ("by status",                     {"status": "intimated"}),
        ("by payment status",             {"payment_status": "paid"}),
        # The one that would CRASH if the count did not join accounts.
        ("by branch (needs the a. join)", {"branch": "BIAORA-01"}),
        ("by a search over account name", {"search": "BETA"}),
        ("by claim type",                 {"claim_type": "health"}),
        ("archived only",                 {"archived_only": True}),
        ("a filter matching nothing",     {"status": "no_such_status"}),
    ):
        try:
            total, real = await both(**kw)
            check("%s — total matches the rows" % label, total == real,
                  "total=%s but %s rows match" % (total, real))
        except Exception as e:  # noqa: BLE001
            check("%s — total matches the rows" % label, False, "raised: %s" % e)

    # The page itself must still be a page.
    st: dict = {}
    page = await n.get_claims_ops(staff_id=1, role="super_admin", limit=30, offset=0, stats=st)
    check("a 30-row page holds 30", len(page) == 30, len(page))
    check("...while the total says there are more", st["total"] == 47, st["total"])

    p2 = await n.get_claims_ops(staff_id=1, role="super_admin", limit=30, offset=30)
    check("page 2 holds the remaining 17", len(p2) == 17, len(p2))
    ids1 = {c["claim_id"] for c in page}
    ids2 = {c["claim_id"] for c in p2}
    check("...and shares no claim with page 1", not (ids1 & ids2), ids1 & ids2)
    check("...so the two pages are the whole set", len(ids1 | ids2) == 47, len(ids1 | ids2))

    # Archived must not leak into a normal view.
    check("an archived claim is not counted by default", 9999 not in ids1 | ids2)

    # And the default path (no stats asked for) must be untouched.
    plain = await n.get_claims_ops(staff_id=1, role="super_admin", limit=5)
    check("callers that ask for no total still work", len(plain) == 5, len(plain))

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "the total counts what the rows count, under every filter"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
