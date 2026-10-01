# -*- coding: utf-8 -*-
'''A subscriber who cancels and subscribes again gets a fresh monthly count (1 Oct, Deepika Yadav).

  1. three claims under an OLD subscription do not block a NEW one;
  2. the cap still blocks when the claims were raised under the CURRENT subscription;
  3. the first claim under the new subscription starts the counter again at 1;
  4. a lapsed subscription that comes back by renewal also starts fresh;
  5. the accounts list shows the same count the check uses;
  6. nobody sees a raw "quota_exceeded_silver" code.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_quota_reactivation.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="quota_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def sql(q, *a):
    async with aiosqlite.connect(DBP) as c:
        await c.execute(q, a)
        await c.commit()


async def main():
    await db.init_db()
    cap = (await nid.get_plan_cfg("silver")).get("claims_per_month") or nid.PLAN_LIMITS["silver"]["claims_per_month"]
    for acct in (1, 2, 3):
        await sql("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                  "VALUES (?, 'Sub', ?, ?, 'x')", acct, "s%d@example.invalid" % acct, "900000000%d" % acct)

    # account 1 = Deepika's shape: old Silver (expired), claims 21 days ago, new Silver since yesterday
    await sql("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, started_at, current_period_end, status) "
              "VALUES (1,'silver',588,datetime('now','-36 days'),datetime('now','-6 days'),'expired')")
    await sql("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, started_at, current_period_end, status) "
              "VALUES (1,'silver',589,datetime('now','-1 day'),datetime('now','+29 days'),'active')")
    await sql("INSERT INTO nidaan_plan_quota (account_id, current_window_start, claims_this_window, updated_at) "
              "VALUES (1, date('now','-21 days'), ?, datetime('now','-21 days'))", cap)
    ok, why = await nid.can_submit_claim(1)
    check("1. claims under her OLD subscription do not block the new one", ok, why)

    # account 2 = the cap is real: same claims, but under the subscription that is still running
    await sql("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, started_at, current_period_end, status) "
              "VALUES (2,'silver',588,datetime('now','-25 days'),datetime('now','+5 days'),'active')")
    await sql("INSERT INTO nidaan_plan_quota (account_id, current_window_start, claims_this_window, updated_at) "
              "VALUES (2, date('now','-21 days'), ?, datetime('now','-21 days'))", cap)
    ok2, why2 = await nid.can_submit_claim(2)
    check("2. the cap still blocks claims raised under the CURRENT subscription", (not ok2) and why2.startswith("quota_exceeded"), why2)

    # 3 - the first claim under the new subscription counts as 1, and the cap applies from there
    sub = await nid.get_active_subscription(1)
    async with aiosqlite.connect(DBP) as c:
        await nid._increment_quota(1, c, sub)
        await c.commit()
        n = (await (await c.execute("SELECT claims_this_window FROM nidaan_plan_quota WHERE account_id=1")).fetchone())[0]
    check("3. the first claim under the new subscription starts the count at 1", n == 1, n)
    async with aiosqlite.connect(DBP) as c:
        for _ in range(cap - 1):
            await nid._increment_quota(1, c, sub)
        await c.commit()
    ok3, why3 = await nid.can_submit_claim(1)
    check("3. ...and after %d claims under it, the cap blocks again" % cap, not ok3, why3)

    # 4 - a lapsed subscription brought back by a renewal: the renewal update stamps active_since
    await sql("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, started_at, current_period_end, status) "
              "VALUES (3,'silver',588,datetime('now','-40 days'),datetime('now','-10 days'),'expired')")
    await sql("INSERT INTO nidaan_plan_quota (account_id, current_window_start, claims_this_window, updated_at) "
              "VALUES (3, date('now','-12 days'), ?, datetime('now','-12 days'))", cap)
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "biz_nidaan.py"),
               encoding="utf-8").read()
    check("4. the renewal update stamps active_since when the subscription was not active",
          "active_since = CASE WHEN status <> 'active' THEN CURRENT_TIMESTAMP ELSE active_since END" in src)
    await sql("UPDATE nidaan_subscriptions SET "
              "active_since = CASE WHEN status <> 'active' THEN CURRENT_TIMESTAMP ELSE active_since END, "
              "status='active', current_period_end=datetime('now','+30 days') WHERE account_id=3")
    ok4, why4 = await nid.can_submit_claim(3)
    check("4. ...so a subscriber whose lapsed plan renews can raise claims again", ok4, why4)

    # 5 - the accounts list agrees with the check
    rows = {r["account_id"]: r for r in await nid.get_all_accounts_admin()}
    check("5. the accounts list shows the same count the check uses",
          rows[1]["claims_used"] == cap and rows[2]["claims_used"] == cap and rows[3]["claims_used"] == 0,
          {k: rows[k].get("claims_used") for k in rows})

    # 6 - plain words, never a code
    for staff in (False, True):
        msg = nid.claim_block_message("quota_exceeded_silver", for_staff=staff)
        check("6. %s sees words, not 'quota_exceeded_silver'" % ("staff" if staff else "the subscriber"),
              "quota_exceeded" not in msg and "claims" in msg, msg)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
