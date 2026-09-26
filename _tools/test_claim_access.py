# -*- coding: utf-8 -*-
'''May this person touch this claim? The checks that have to hold before a chat app can.

Founder, 26 Sep 2026, agreeing the rule before the Telegram document upload is built:
staff reach the claims they are ON; admins reach any claim, exactly as they already do on the
web. And the whole thing FAILS CLOSED, unlike the notification resolver, which fails towards
sending - a wrong "yes" here is somebody else's medical file, a wrong "yes" there is a noisy
phone.

The one that is easy to get wrong and hard to notice: "that claim is not yours" and "no such
claim" must read the SAME to a team member. If they differ, the bot becomes a way to find out
which claim numbers exist, one guess at a time, from a phone.

    py -3.14 _tools/test_claim_access.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite                       # noqa: E402
import biz_database as db              # noqa: E402
import biz_nidaan_claim_access as acc  # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="claimacc-"), "t.db")
db.DB_PATH = DB

MINE, THEIRS, GHOST = 501, 502, 999999
ME, COLLEAGUE, ADMIN, SA = 11, 12, 13, 14


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


async def main():
    await db.init_db()
    async with aiosqlite.connect(DB) as c:
        for cid in (MINE, THEIRS):
            await c.execute(
                "INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, "
                "insured_phone) VALUES (?,?,?,?,?)",
                (cid, 1, "health", "Test Claimant", "9000000000"))
        await c.execute("INSERT INTO nidaan_claim_assignees (claim_id, staff_id) VALUES (?,?)",
                        (MINE, ME))
        await c.execute("INSERT INTO nidaan_claim_note_mentions (note_id, claim_id, staff_id) "
                        "VALUES (?,?,?)", (1, THEIRS, COLLEAGUE))
        await c.commit()

    print("\nWho may touch which claim\n")

    r = await acc.claim_access(ME, MINE, role="team_member")
    check("a team member reaches the claim assigned to them", r["allowed"], r)
    check("...and the reason says why", r["basis"] == acc.BASIS_ASSIGNED, r)

    r = await acc.claim_access(ME, THEIRS, role="team_member")
    check("...and NOT somebody else's claim", not r["allowed"], r)

    r = await acc.claim_access(COLLEAGUE, THEIRS, role="team_member")
    check("being named on a claim is enough to be on it", r["allowed"], r)
    check("...and it says so", r["basis"] == acc.BASIS_MENTIONED, r)

    # The enumeration guard: the two refusals must be indistinguishable.
    not_mine = await acc.claim_access(ME, THEIRS, role="team_member")
    no_claim = await acc.claim_access(ME, GHOST, role="team_member")
    check("'not yours' and 'does not exist' read identically to a team member",
          not_mine["reason"] == no_claim["reason"] and not_mine["basis"] == no_claim["basis"],
          (not_mine, no_claim))

    for role in acc.ORG_WIDE_ROLES:
        r = await acc.claim_access(ADMIN, THEIRS, role=role)
        check("%-16s reaches any claim, as on the web" % role,
              r["allowed"] and r["basis"] == acc.BASIS_ROLE, r)
    r = await acc.claim_access(ADMIN, GHOST, role="super_admin")
    check("...but an admin is told plainly when a claim does not exist",
          not r["allowed"] and r["basis"] == acc.BASIS_NO_CLAIM, r)

    # ── rubbish in ──────────────────────────────────────────────────────────
    for bad in (None, 0, -1, "abc", 1.5):
        r = await acc.claim_access(ME, bad, role="team_member")
        if r["allowed"]:
            check("a nonsense claim id (%r) is refused" % (bad,), False, r)
            break
    else:
        check("every nonsense claim id is refused", True)
    check("no staff id at all is refused",
          not (await acc.claim_access(None, MINE, role="team_member"))["allowed"])
    check("an empty role is treated as a team member, not as an admin",
          not (await acc.claim_access(ME, THEIRS, role=""))["allowed"])
    check("a made-up role gets no privileges",
          not (await acc.claim_access(ME, THEIRS, role="administrator"))["allowed"])

    # ── and it fails CLOSED ─────────────────────────────────────────────────
    real = db.DB_PATH
    db.DB_PATH = "/nonexistent/dir/no.db"
    r = await acc.claim_access(ME, MINE, role="team_member")
    ra = await acc.claim_access(ADMIN, MINE, role="super_admin")
    db.DB_PATH = real
    check("an unreadable table refuses a team member", not r["allowed"], r)
    check("...and refuses an admin too - no role rides through a failure",
          not ra["allowed"], ra)
    check("...and says it is our problem, not 'not yours'",
          r["basis"] == acc.BASIS_ERROR and ra["basis"] == acc.BASIS_ERROR)

    # ── the convenience wrapper must not be a softer door ───────────────────
    check("assert_claim_access agrees with claim_access",
          (await acc.assert_claim_access({"staff_id": ME, "role": "team_member"}, THEIRS))["allowed"]
          is False
          and (await acc.assert_claim_access({"staff_id": ME, "role": "team_member"}, MINE))["allowed"]
          is True)
    check("...and an empty staff row is refused",
          not (await acc.assert_claim_access({}, MINE))["allowed"])
    check("...and None is refused", not (await acc.assert_claim_access(None, MINE))["allowed"])

    ids = await acc.my_claim_ids(ME)
    check("a person can be shown their own claims", ids == [MINE], ids)

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "you reach your claims, admins reach all, and a failure reaches nothing"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
