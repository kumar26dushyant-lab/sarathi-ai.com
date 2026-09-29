# -*- coding: utf-8 -*-
'''Claims from customers someone referred - seen by that staff member or AP, and nobody else.

Founder, 29 Sep: Trivesh (team member) shared his code, a subscriber signed up and filed a claim
for Uttam Singh, and Trivesh could not see it. The code sits on the ACCOUNT; the claim (#233)
carries none.

What these checks defend:

  * the Trivesh case: a claim with no code of its own is found through the customer's account;
  * a claim that carries the code itself is found too;
  * another referrer's claims, and archived ones, are NOT;
  * what is shown is enough to follow up (stage in the customer's words, missing documents,
    handler) and nothing more - no policy number, no phone;
  * the one action - a note - lands on the claim and reaches the handler, only for your own
    referral, and "not yours" looks exactly like "no such claim";
  * the staffer's code is read from the database, not from anything the browser sends.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_referred_claims.py
'''
import asyncio
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_root = tempfile.mkdtemp(prefix="referred_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_nidaan as nid                            # noqa: E402
import biz_nidaan_referrals as ref                  # noqa: E402
import biz_nidaan_doc_checklist as ck               # noqa: E402
import biz_nidaan_notifications as nn               # noqa: E402

nid.DB_PATH = db.DB_PATH

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_staff (staff_id INTEGER PRIMARY KEY, name TEXT, role TEXT,
    referral_code TEXT DEFAULT '', status TEXT DEFAULT 'active', deleted_at TIMESTAMP);
CREATE TABLE nidaan_accounts (account_id INTEGER PRIMARY KEY, owner_name TEXT,
    branch_code TEXT DEFAULT '', phone TEXT DEFAULT '');
CREATE TABLE nidaan_claims (claim_id INTEGER PRIMARY KEY, account_id INTEGER, claim_type TEXT,
    insurer_name TEXT, policy_no TEXT, insured_phone TEXT, status TEXT, pipeline_stage TEXT,
    origin TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, last_status_at TEXT,
    assigned_to_staff_id INTEGER, branch_code TEXT DEFAULT '', archived INTEGER DEFAULT 0,
    docs_complete_at TEXT);
CREATE TABLE nidaan_claim_doc_checklist (claim_id INTEGER, doc_key TEXT, received INTEGER DEFAULT 0);
INSERT INTO nidaan_claim_doc_checklist VALUES (233, 'discharge', 0);
CREATE TABLE nidaan_claim_activity (act_id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_id INTEGER NOT NULL, kind TEXT NOT NULL, channel TEXT DEFAULT '',
    direction TEXT DEFAULT '', actor TEXT DEFAULT '', summary TEXT DEFAULT '',
    meta TEXT DEFAULT '', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
INSERT INTO nidaan_staff VALUES (18, 'TRIVESH NIHORE', 'team_member', 'SP-HDFG8T', 'active', NULL);
INSERT INTO nidaan_staff VALUES (23, 'Priya', 'sub_super_admin', 'SP-PRIYA1', 'active', NULL);
INSERT INTO nidaan_staff VALUES (40, 'Gone', 'team_member', 'SP-GONE01', 'archived', NULL);
INSERT INTO nidaan_accounts VALUES (155, 'UTTAM SINGH', 'SP-HDFG8T', '7354053177');
INSERT INTO nidaan_accounts VALUES (156, 'Other Person', 'SP-PRIYA1', '9000000000');
INSERT INTO nidaan_accounts VALUES (900, 'AP House', 'AP-INDORE', '');
-- the Trivesh case: the CLAIM carries no code; the account does
INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insurer_name, policy_no,
    insured_phone, status, assigned_to_staff_id) VALUES
    (233, 155, 'health', 'Star Health', 'POL-SECRET-1', '9999999999', 'review_delivered', 23);
-- another referrer's customer
INSERT INTO nidaan_claims (claim_id, account_id, claim_type, status) VALUES (234, 156, 'motor', 'intimated');
-- archived: not shown
INSERT INTO nidaan_claims (claim_id, account_id, claim_type, status, archived) VALUES (235, 155, 'life', 'intimated', 1);
-- a claim carrying the code itself (lower case on purpose)
INSERT INTO nidaan_claims (claim_id, account_id, claim_type, status, branch_code) VALUES (236, NULL, 'health', 'assigned', 'sp-hdfg8t');
-- an AP: one claim it raised itself, one filed by a customer it referred
INSERT INTO nidaan_accounts VALUES (901, 'AP Customer', 'AP-INDORE', '');
INSERT INTO nidaan_claims (claim_id, account_id, claim_type, status, origin, branch_code) VALUES (300, 900, 'health', 'intimated', 'branch', 'AP-INDORE');
INSERT INTO nidaan_claims (claim_id, account_id, claim_type, status, origin) VALUES (301, 901, 'health', 'intimated', 'self');
"""

TOLD = []


async def f_pending(claim_id, ctype):
    # The real function falls back to the full template when a claim has no checklist - so it
    # answers for EVERY claim here, and only the has-a-checklist rule can keep it off the screen.
    return [{"key": "discharge", "en": "Discharge summary", "hi": "डिस्चार्ज समरी"}]


async def f_notify(ids, subject, body, event_key="", email=True, **kw):
    TOLD.append({"ids": list(ids), "subject": subject, "key": event_key, "email": email})
    return len(ids)


async def f_admins():
    return [{"staff_id": 1}]


ck.pending_required_docs = f_pending
nn.notify_staff_inapp = f_notify
nn._super_admin_staff = f_admins


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    print("\nThe Trivesh case\n")
    code = await ref.staff_code(18)
    check("the staffer's code comes from the database", code == "SP-HDFG8T", code)
    got = await ref.referred_claims(code)
    ids = [c["claim_id"] for c in got]
    check("claim #233 - no code of its own - is found through the customer's account",
          233 in ids, ids)
    check("a claim carrying the code itself is found (any case)", 236 in ids, ids)
    check("another referrer's customer is NOT", 234 not in ids, ids)
    check("an archived claim is NOT", 235 not in ids, ids)

    print("\nEnough to follow up, nothing more\n")
    c233 = next(c for c in got if c["claim_id"] == 233)
    check("stage in the words the customer sees", c233["stage"] == "Assessment shared", c233)
    check("who is handling it", c233["handler"] == "Priya", c233)
    check("what is still missing, in both languages",
          c233["missing"] == [{"en": "Discharge summary", "hi": "डिस्चार्ज समरी"}], c233)
    check("the customer's name, the claim type, the insurer",
          c233["customer"] == "UTTAM SINGH" and c233["insurer"] == "Star Health", c233)
    c236 = next(c for c in got if c["claim_id"] == 236)
    check("a claim with no checklist of its own shows nothing missing (not the full template)",
          c236["missing"] == [], c236)
    flat = repr(got)
    check("no policy number and no phone number", "POL-SECRET" not in flat
          and "9999999999" not in flat and "7354053177" not in flat)

    print("\nAn AP\n")
    ap = [c["claim_id"] for c in await ref.referred_claims("ap-indore",
                                                           exclude_raised_by_branch=True)]
    check("a claim filed by a customer the AP referred is listed", 301 in ap, ap)
    check("...the AP's own raised claim is not listed twice", 300 not in ap, ap)

    print("\nNo code, no claims\n")
    check("an empty code sees nothing", await ref.referred_claims("") == [])
    check("an archived staffer's code is not honoured", await ref.staff_code(40) == "")

    print("\nThe note\n")
    TOLD.clear()
    res = await ref.add_referrer_note("SP-HDFG8T", 233, "Customer will send DS tomorrow",
                                      who="TRIVESH NIHORE")
    async with aiosqlite.connect(db.DB_PATH) as c:
        rows = await (await c.execute(
            "SELECT kind, actor, summary FROM nidaan_claim_activity WHERE claim_id=233")).fetchall()
    check("it is saved on the claim's remarks", res.get("ok") and rows
          and rows[0][0] == "referrer_note" and "DS tomorrow" in rows[0][2], (res, rows))
    check("...saying who sent it, as the referrer", rows and "referrer" in rows[0][1], rows)
    check("...and the handler is told, on the bell and Telegram",
          TOLD and TOLD[0]["ids"] == [23] and TOLD[0]["email"] is False
          and TOLD[0]["key"] == "claim.referrer_note", TOLD)

    TOLD.clear()
    res = await ref.add_referrer_note("SP-HDFG8T", 234, "hello there", who="TRIVESH")
    async with aiosqlite.connect(db.DB_PATH) as c:
        n = (await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claim_activity WHERE claim_id=234")).fetchone())[0]
    check("a claim you did not refer: refused, nothing written, nobody told",
          res.get("not_found") and n == 0 and not TOLD, (res, n, TOLD))
    res2 = await ref.add_referrer_note("SP-HDFG8T", 99999, "hello there", who="TRIVESH")
    check("...and it looks exactly like a claim that does not exist", res == res2, (res, res2))
    check("an empty note is refused",
          not (await ref.add_referrer_note("SP-HDFG8T", 233, "  ", who="T")).get("ok"))
    TOLD.clear()
    await ref.add_referrer_note("SP-HDFG8T", 236, "unassigned claim note", who="T")
    check("a claim nobody handles yet: the admins hear it", TOLD and TOLD[0]["ids"] == [1], TOLD)

    print("\nThe routes\n")
    src = io.open("sarathi_biz.py", encoding="utf-8").read()
    for name in ("ops_my_business_claims", "ops_my_business_claim_note"):
        m = re.search(r"async def %s\(.*?(?=\n@app\.|\nclass |\nasync def )" % name, src, re.S)
        body = m.group(0) if m else ""
        check("%-28s reads the code from the database" % name,
              "_ref.staff_code(staff[\"staff_id\"])" in body, body[:200])
    for name in ("ops_my_business_claim_note", "nidaan_branch_referred_claim_note"):
        m = re.search(r"async def %s\(.*?(?=\n@app\.|\nclass |\nasync def )" % name, src, re.S)
        body = m.group(0) if m else ""
        check("%-34s answers 404, never 403" % name,
              "status_code=404" in body and "status_code=403" not in body, body[-200:])
    check("the notes are rate-limited",
          src.count('@limiter.limit("20/minute")\nasync def ops_my_business_claim_note') == 1
          and src.count('@limiter.limit("20/minute")\nasync def nidaan_branch_referred_claim_note') == 1)

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
