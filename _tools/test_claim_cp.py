# -*- coding: utf-8 -*-
'''A Channel Partner added to or removed from an existing claim - only with a super-admin's yes.

Founder, 30 Sep (claim #226): add a CP later when staff forgot at intake, "it should come for
superadmin approval ... with add, we need option to delete too with approval".

What these checks defend:
  * asking changes nothing; only a super-admin's approval changes the claim;
  * a team member cannot approve their own request (or anyone's);
  * only My Business claims, only approved partners, one open request per claim, a reason required;
  * add only when there is none, remove only the one there;
  * approval re-checks everything (a partner disabled while the request waited is refused);
  * reject needs a reason; the asker hears the outcome; every step is on the claim's timeline;
  * the asker can withdraw; nobody else except a super-admin can.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_claim_cp.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="ccp_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_claim_cp as ccp                   # noqa: E402
ccp.DB_PATH = DBP
import biz_nidaan_notifications as nn               # noqa: E402

FAILED = 0
TEAM = {"staff_id": 5, "role": "team_member", "name": "Tamanna"}
OTHER = {"staff_id": 6, "role": "team_member", "name": "Someone Else"}
ADMIN = {"staff_id": 1, "role": "super_admin", "name": "Founder"}


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def refused(coro, words=""):
    try:
        await coro
        return False, "not refused"
    except ccp.CPError as e:
        return (words.lower() in str(e).lower()), str(e)


async def cp_of(cid):
    async with aiosqlite.connect(DBP) as c:
        r = await (await c.execute("SELECT channel_partner_id, associate_referrer FROM nidaan_claims "
                                   "WHERE claim_id=?", (cid,))).fetchone()
    return r


async def main():
    await db.init_db()
    told = []

    async def fake(ids, title, body, **kw):
        told.append((tuple(ids), kw.get("event_key")))

    async def admins():
        return [{"staff_id": 1}]
    nn.notify_staff_inapp, nn._super_admin_staff = fake, admins

    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'House','h@example.invalid','9000000000','x')")
        for cid, code in ((226, "SP-GJG7BA"), (227, "PUNEICD-01")):
            await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
                            "insured_phone, branch_code, origin, status) VALUES (?,1,'health','X','9000000001',?,"
                            "'branch','review_delivered')", (cid, code))
        await c.execute("INSERT INTO nidaan_channel_partners (cp_id, name, status) VALUES (9,'Ramesh Agency','approved')")
        await c.execute("INSERT INTO nidaan_channel_partners (cp_id, name, status) VALUES (10,'Pending Co','pending')")
        await c.commit()

    ok, why = await refused(ccp.request_change(227, "add", cp_id=9, reason="forgot at intake", staff=TEAM), "My Business")
    check("an Authorized Partner claim cannot take a CP here", ok, why)
    ok, why = await refused(ccp.request_change(226, "add", cp_id=10, reason="forgot at intake", staff=TEAM), "approved")
    check("a partner that is not approved cannot be asked for", ok, why)
    ok, why = await refused(ccp.request_change(226, "add", cp_id=9, reason="x", staff=TEAM), "why")
    check("a reason is required", ok, why)
    ok, why = await refused(ccp.request_change(226, "remove", reason="wrong partner", staff=TEAM), "no Channel Partner")
    check("nothing to remove when there is none", ok, why)

    r = await ccp.request_change(226, "add", cp_id=9, reason="forgot at intake", staff=TEAM)
    check("a staff member can ask to add one", r.get("ok"), r)
    check("...asking changes nothing on the claim", (await cp_of(226))[0] is None, await cp_of(226))
    check("...the super-admins are asked", ((1,), "cp.claim_request") in told, told)
    ok, why = await refused(ccp.request_change(226, "add", cp_id=9, reason="again please", staff=OTHER), "already")
    check("one open request per claim", ok, why)
    ok, why = await refused(ccp.decide(r["req_id"], True, staff=TEAM), "super-admin")
    check("a team member cannot approve", ok, why)
    ok, why = await refused(ccp.withdraw(r["req_id"], staff=OTHER), "only the person")
    check("somebody else cannot withdraw it", ok, why)

    # the partner is disabled while the request waits
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_channel_partners SET status='disabled' WHERE cp_id=9")
        await c.commit()
    ok, why = await refused(ccp.decide(r["req_id"], True, staff=ADMIN), "no longer approved")
    check("approval re-checks: a partner disabled meanwhile is refused", ok, why)
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_channel_partners SET status='approved' WHERE cp_id=9")
        await c.commit()

    d = await ccp.decide(r["req_id"], True, staff=ADMIN)
    check("a super-admin approves", d.get("status") == "approved", d)
    check("...and only now the claim has the partner", tuple(await cp_of(226)) == (9, "Ramesh Agency"),
          await cp_of(226))
    check("...the asker is told", ((5,), "cp.claim_decided") in told, told)
    ok, why = await refused(ccp.decide(r["req_id"], False, note="not needed", staff=ADMIN), "already")
    check("a decided request cannot be decided again", ok, why)

    ok, why = await refused(ccp.request_change(226, "add", cp_id=9, reason="another one", staff=TEAM), "remove it first")
    check("add only when there is none - change means remove first", ok, why)
    r2 = await ccp.request_change(226, "remove", reason="the customer came direct", staff=TEAM)
    ok, why = await refused(ccp.decide(r2["req_id"], False, note="", staff=ADMIN), "why")
    check("a rejection needs a reason", ok, why)
    d2 = await ccp.decide(r2["req_id"], False, note="the CP did bring this customer", staff=ADMIN)
    check("...and with one it is rejected, the claim untouched",
          d2.get("status") == "rejected" and (await cp_of(226))[0] == 9, (d2, await cp_of(226)))

    r3 = await ccp.request_change(226, "remove", reason="the customer came direct", staff=TEAM)
    w = await ccp.withdraw(r3["req_id"], staff=TEAM)
    check("the asker can withdraw", w.get("ok"), w)
    r4 = await ccp.request_change(226, "remove", reason="the customer came direct", staff=TEAM)
    await ccp.decide(r4["req_id"], True, staff=ADMIN)
    check("removal, approved, clears the partner", tuple(await cp_of(226)) == (None, ""), await cp_of(226))

    async with aiosqlite.connect(DBP) as c:
        lines = [x[0] for x in await (await c.execute(
            "SELECT summary FROM nidaan_claim_activity WHERE claim_id=226 AND kind='cp_change' ORDER BY act_id")).fetchall()]
    check("every step is on the claim's timeline, with names",
          len(lines) == 8 and "approved by Founder (asked by Tamanna)" in lines[1] and "rejected by Founder" in lines[3]
          and "withdrew" in lines[5], lines)
    st = await ccp.state(226)
    check("the claim screen sees no open request and the history", st["pending"] is None and len(st["history"]) == 4, st)


asyncio.run(main())
print("\n%s" % ("all passed" if not FAILED else "%d failed" % FAILED))
sys.exit(1 if FAILED else 0)
