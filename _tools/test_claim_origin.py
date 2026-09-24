# -*- coding: utf-8 -*-
'''A claim must be able to say WHO brought it, WHEN, and HOW — in names, not codes.

Founder, 23 Sep: "we need all details not only code but branch name, channel name accounts name,
subscriber name and other details ... so it'll be easy to track who, when, what."

The claim panel said "Came in as: 🏢 Branch · SP-GJG7BA". SP-GJG7BA is not a branch. It is
TAMANNA VASHISHTHA — under the staff-as-branch referral scheme a colleague's referral code goes
in the same column an office code does, and the screen called all of them "Branch".

On live data: 64 claims carry a STAFF referral code there, 23 carry a real branch code. So the
single most common thing that screen said about where a claim came from was wrong.

Pinned here, against a temporary database rather than the live one:

  - a staff referral code resolves to the PERSON, never to "Branch"
  - a real branch code resolves to the branch, with its name and city
  - a code matching neither says so instead of inventing an owner
  - a hand-typed referrer NAME still finds its person (some rows hold a name, not a code)
  - a claim with no recorded channel says the answer was WORKED OUT, because 59 are like that
    and a confident wrong answer is worse than an honest gap
  - both languages, per the standing rule

    py -3.13 _tools/test_claim_origin.py
'''
import asyncio
import os
import sys
import tempfile

os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite       # noqa: E402
import biz_nidaan as n  # noqa: E402

FAILED = 0
DB = os.path.join(tempfile.mkdtemp(prefix="origin-"), "t.db")
n.DB_PATH = DB


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_claims (
  claim_id INTEGER PRIMARY KEY, origin TEXT, created_at TIMESTAMP, branch_code TEXT,
  raised_by_name TEXT, raised_by_staff_id INTEGER, raised_via TEXT,
  channel_partner_id INTEGER, associate_referrer TEXT, account_id INTEGER);
CREATE TABLE nidaan_accounts (
  account_id INTEGER PRIMARY KEY, owner_name TEXT, firm_name TEXT, email TEXT, phone TEXT,
  branch_code TEXT, source_channel TEXT, created_at TIMESTAMP);
CREATE TABLE nidaan_branches (
  branch_code TEXT PRIMARY KEY, name TEXT, city TEXT, contact_email TEXT, contact_phone TEXT,
  status TEXT, created_at TIMESTAMP);
CREATE TABLE nidaan_staff (
  staff_id INTEGER PRIMARY KEY, name TEXT, role TEXT, status TEXT, referral_code TEXT);
CREATE TABLE nidaan_channel_partners (
  cp_id INTEGER PRIMARY KEY, name TEXT, company TEXT, email TEXT, phone TEXT,
  created_by_name TEXT, approved_by_name TEXT);
"""


async def setup():
    async with aiosqlite.connect(DB) as c:
        await c.executescript(SCHEMA)
        await c.execute("INSERT INTO nidaan_staff VALUES (5,'TAMANNA VASHISHTHA',"
                        "'sub_super_admin','active','SP-GJG7BA')")
        await c.execute("INSERT INTO nidaan_staff VALUES (9,'ANNAPURNA KASERA',"
                        "'super_admin','active','SP-E45MTX')")
        await c.execute("INSERT INTO nidaan_branches VALUES ('BIAORA-01','BIAORA BRANCH',"
                        "'Biaora','b@x.com','9000000000','active','2026-01-01')")
        for aid, nm, ph in ((85, 'CHETAN', '9826080799'),
                            (86, 'GOURAV PANDIT', '9131327170'),
                            (87, 'Dushyant Sharma', '')):
            await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, phone, "
                            "created_at) VALUES (?,?,?,'2026-01-01')", (aid, nm, ph))
        # House accounts, named exactly as the app names them.
        for aid, code in ((88, 'SP-GJG7BA'), (89, 'BIAORA-01')):
            await c.execute(
                "INSERT INTO nidaan_accounts (account_id, owner_name, email, created_at) "
                "VALUES (?,?,?,'2026-01-01')",
                (aid, 'Branch %s — house account' % code,
                 'branch.%s@house.nidaanpartner.internal' % code.lower()))
        rows = [
            # a STAFF referral code sitting in branch_code - the 64-claim case
            (1, 'branch', '2026-09-15 07:21', 'SP-GJG7BA', 'TAMANNA VASHISHTHA', 5,
             'on_behalf', None, '', 85),
            # a REAL branch
            (2, 'branch', '2026-09-01 10:00', 'BIAORA-01', '', None, '', None, '', 86),
            # a code that is neither
            (3, 'branch', '2026-09-02 10:00', 'ZZ-NOPE', '', None, '', None, '', 86),
            # a referrer typed as a NAME rather than a code
            (4, 'branch', '2026-09-03 10:00', '', '', None, '', None,
             'ANNAPURNA KASERA', 86),
            # no origin at all - the 59-claim case
            (5, '', '2026-07-08 16:15', '', '', None, '', None, '', 87),
            # a STAFF referral whose account is a house account - the "why does it say Branch"
            (6, 'branch', '2026-09-22 12:06', 'SP-GJG7BA', '', None, '', None, '', 88),
            # a REAL branch with a house account - must keep reading as a branch
            (7, 'branch', '2026-09-22 12:06', 'BIAORA-01', '', None, '', None, '', 89),
        ]
        for r in rows:
            await c.execute("INSERT INTO nidaan_claims (claim_id, origin, created_at, "
                            "branch_code, raised_by_name, raised_by_staff_id, raised_via, "
                            "channel_partner_id, associate_referrer, account_id) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?)", r)
        await c.commit()


def find(d, label):
    for r in d.get("rows", []):
        if r["label"] == label:
            return r
    return None


def all_text(d):
    return " | ".join("%s=%s %s" % (r["label"], r["value"], r["detail"]) for r in d["rows"])


async def main():
    await setup()
    print("\nWhere a claim came from\n")

    # ── the one that was wrong on 64 claims ─────────────────────────────────
    d = await n.claim_origin(1)
    staff = find(d, "Staff referral")
    check("a staff referral code resolves to the PERSON",
          staff is not None and "TAMANNA VASHISHTHA" in staff["value"], all_text(d))
    check("...and is NOT presented as a branch",
          find(d, "Branch") is None, all_text(d))
    check("...and the headline does not claim a branch raised it",
          "branch portal" in d["how"]["label"].lower(), d["how"])
    check("...while still showing the code, so it can be traced",
          staff and "SP-GJG7BA" in staff["detail"], staff)
    check("the subscriber is named, not just numbered",
          (find(d, "Subscriber account") or {}).get("value") == "CHETAN", all_text(d))
    check("...and a real subscriber is NOT relabelled as a house account",
          find(d, "Billing account") is None, all_text(d))
    check("who raised it is named", (find(d, "Raised by") or {}).get("value")
          == "TAMANNA VASHISHTHA", all_text(d))
    check("and WHEN is carried", (d.get("when") or "").startswith("2026-09-15"), d.get("when"))
    check("nothing is reported as missing when everything resolved", not d["gaps"], d["gaps"])

    # ── a real branch ───────────────────────────────────────────────────────
    d = await n.claim_origin(2)
    br = find(d, "Branch")
    check("a real branch code resolves to the branch, by name",
          br is not None and "BIAORA BRANCH" in br["value"], all_text(d))
    check("...with its city and code beside it",
          br and "Biaora" in br["detail"] and "BIAORA-01" in br["detail"], br)
    check("...and is not mistaken for a staff referral",
          find(d, "Staff referral") is None, all_text(d))

    # ── a code that owns nothing ────────────────────────────────────────────
    d = await n.claim_origin(3)
    check("a code matching neither says so rather than inventing an owner",
          any("matches neither" in g for g in d["gaps"]), d["gaps"])
    check("...and still shows the code itself",
          (find(d, "Code on the claim") or {}).get("value") == "ZZ-NOPE", all_text(d))

    # ── a referrer typed as a name ──────────────────────────────────────────
    d = await n.claim_origin(4)
    ref = find(d, "Referred by")
    check("a referrer typed as a NAME still finds the person",
          ref is not None and "ANNAPURNA KASERA" in ref["value"], all_text(d))
    check("...without echoing the name back as if it were a code",
          ref and ref["detail"].count("ANNAPURNA") == 0, ref)

    # ── the house account must not wear the word "Branch" on a staff referral ──
    # Founder, 24 Sep: "subscriber account shows branch and code number, but that's internal
    # staff Shraddha raised not branch, so is it possible to remove 'branch' word".
    d = await n.claim_origin(6)
    house = find(d, "Billing account")
    check("a staff referral's house account is not called a Branch",
          house is not None and "branch" not in house["value"].lower(), all_text(d))
    check("...and says whose it is", house and "TAMANNA" in house["detail"], house)
    check("...while no 'Subscriber account' row pretends there is a subscriber",
          find(d, "Subscriber account") is None, all_text(d))

    d = await n.claim_origin(7)
    house = find(d, "Billing account")
    check("a REAL branch's house account still reads as the branch's own",
          house is not None and "branch" in (house["detail"] or "").lower(), all_text(d))

    # ── no channel recorded ─────────────────────────────────────────────────
    d = await n.claim_origin(5)
    check("a claim with no recorded channel still says something useful",
          bool(d["how"]["label"]), d["how"])
    check("...and admits the answer was worked out, not recorded",
          any("never recorded" in g for g in d["gaps"]), d["gaps"])

    # ── both languages ──────────────────────────────────────────────────────
    hi = await n.claim_origin(1, lang="hi")
    import re
    check("the whole block comes back in Hindi when asked",
          bool(re.search(r"[ऀ-ॿ]", hi["how"]["label"]))
          and all(re.search(r"[ऀ-ॿ]", r["label"]) for r in hi["rows"]),
          hi["how"]["label"])
    check("...and has the same number of facts in both languages",
          len(hi["rows"]) == len((await n.claim_origin(1))["rows"]))

    # ── a claim that does not exist ─────────────────────────────────────────
    check("a missing claim returns nothing rather than raising",
          await n.claim_origin(99999) == {})

    print("\n" + ("%d failed" % FAILED if FAILED
                  else "who, when and how — in names, and honest about the gaps"))


asyncio.run(main())
sys.exit(1 if FAILED else 0)
