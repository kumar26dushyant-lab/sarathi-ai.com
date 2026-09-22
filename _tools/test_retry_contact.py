"""Would a failed payment find anybody to write to? Asked once per product, on real rows.

27 payments failed between 17 Aug and 22 Sep 2026 and not one retry link was sent, because the
lookup read a key no product writes. So this hands _retry_contact the notes each product REALLY
sends - taken from the order payloads in sarathi_biz.py, not invented - and checks it comes back
with an address.

A UPI payment carries no email on the Razorpay entity. That is the case that matters and it is
the case every example here uses: `entity` deliberately has no email in it.
"""
import asyncio
import os
import shutil
import sys
import tempfile

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

LIVE = "/opt/sarathi/sarathi_biz.db"
db = os.path.join(tempfile.mkdtemp(prefix="rt_"), "copy.db")
shutil.copy(LIVE, db)
for e in ("-wal", "-shm"):
    if os.path.exists(LIVE + e):
        shutil.copy(LIVE + e, db + e)

os.environ["DB_PATH"] = db
OV = os.path.dirname(os.path.abspath(__file__))
sys.path = [q for q in sys.path if os.path.abspath(q) not in (OV, "/opt/sarathi")]
sys.path.insert(0, "/opt/sarathi")
sys.path.insert(0, OV)

import aiosqlite                                       # noqa: E402
import biz_database as _db; _db.DB_PATH = db           # noqa: E402,E702
import biz_nidaan as _n; _n.DB_PATH = db               # noqa: E402,E702
import biz_nidaan_claimant as _cl; _cl.DB_PATH = db    # noqa: E402,E702
import sarathi_biz as app                              # noqa: E402

assert app.__file__.startswith(OV), "ABORT: testing the DEPLOYED module, not the change"
_n.DB_PATH = db
app.nidaan.DB_PATH = db

P = F = 0


def check(label, ok, detail=""):
    global P, F
    if ok:
        P += 1
        print("  PASS  " + label)
    else:
        F += 1
        print("  FAIL  " + label + (("  " + str(detail)) if detail else ""))


def same(label, got, want):
    """Equality, said out loud.

    Six assertions in the first draft of this file passed `got` as the truthiness flag and `want`
    as the failure DETAIL, so they never compared anything - and some of them passed by luck,
    which is worse than failing.
    """
    global P, F
    if got == want:
        P += 1
        print("  PASS  " + label)
    else:
        F += 1
        print("  FAIL  %s" % label)
        print("          got:  %r" % (got,))
        print("          want: %r" % (want,))


async def pick():
    """Real ids from the copy, so the lookups have something to find."""
    async with aiosqlite.connect(db) as c:
        c.row_factory = aiosqlite.Row
        acct = await (await c.execute(
            "SELECT account_id, email FROM nidaan_accounts WHERE COALESCE(email,'')<>'' "
            "AND email NOT LIKE '%internal%' ORDER BY account_id DESC LIMIT 1")).fetchone()
        claim = await (await c.execute(
            "SELECT claim_id FROM nidaan_claims WHERE COALESCE(complainant_email,'')<>'' "
            "OR COALESCE(insured_email,'')<>'' ORDER BY claim_id DESC LIMIT 1")).fetchone()
        pur = await (await c.execute(
            "SELECT purchase_id FROM nidaan_per_claim_purchase "
            "WHERE COALESCE(insured_email,'')<>'' OR COALESCE(advisor_email,'')<>'' "
            "ORDER BY purchase_id DESC LIMIT 1")).fetchone()
    return (dict(acct) if acct else None, dict(claim) if claim else None,
            dict(pur) if pur else None)


async def main():
    acct, claim, pur = await pick()
    print("\nUsing account %s, claim %s, purchase %s from the copy\n"
          % ((acct or {}).get("account_id"), (claim or {}).get("claim_id"),
             (pur or {}).get("purchase_id")))

    # A UPI payment: no email anywhere on the entity. This is the case that broke.
    UPI = {"id": "pay_TEST", "method": "upi", "amount": 117882, "contact": "+919009237757"}

    print("1. subscription - notes carry notify_email AND nidaan_account_id")
    e, n = await app._retry_contact(
        UPI, {"product": "nidaan", "nidaan_plan": "gold",
              "nidaan_account_id": str((acct or {}).get("account_id") or 0),
              "notify_email": "buyer@example.com"}, "Subscription")
    check("found an address", bool(e), e)
    same("and preferred the one written in the notes", e, "buyer@example.com")

    print("\n2. subscription with only the account id (an older one)")
    if acct:
        e, n = await app._retry_contact(
            UPI, {"product": "nidaan", "nidaan_account_id": str(acct["account_id"])}, "Subscription")
        check("found the account's own address", e == acct["email"], e)
    else:
        check("an account with an address exists to test with", False)

    print("\n3. the ₹499 review - notes carry only claim_id")
    if claim:
        e, n = await app._retry_contact(
            UPI, {"product": "nidaan_claim_499", "claim_id": str(claim["claim_id"])},
            "₹499 review")
        check("found the complainant", bool(e), e)
        who = await _cl.contact_for_claim(claim["claim_id"]) or {}
        same("and it IS the complainant, not the insured", e, (who.get("to_email") or ""))
    else:
        check("a claim with an address exists to test with", False)

    print("\n4. the branch Level-2 fee - claim_id again")
    if claim:
        e, n = await app._retry_contact(
            UPI, {"product": "nidaan_branch_l2", "claim_id": str(claim["claim_id"]),
                  "branch": "MP01"}, "Branch Level-2")
        check("found somebody", bool(e), e)

    print("\n5. the D2C review - notes carry only purchase_id")
    if pur:
        e, n = await app._retry_contact(
            UPI, {"product": "nidaan_review_999", "purchase_id": str(pur["purchase_id"])},
            "Review")
        check("found the buyer", bool(e), e)
    else:
        check("a purchase with an address exists to test with", False)

    print("\n6. nidaan_review - the address is in the notes")
    e, n = await app._retry_contact(
        UPI, {"product": "nidaan_review", "advisor_email": "advisor@example.com",
              "insured_name": "RAM"}, "Review")
    same("found the advisor", e, "advisor@example.com")

    print("\n7. the OLD keys still work, so nothing older breaks")
    if acct:
        e, n = await app._retry_contact(UPI, {"account_id": str(acct["account_id"])}, "x")
        check("account_id", e == acct["email"], e)
        e, n = await app._retry_contact(UPI, {"acct_id": str(acct["account_id"])}, "x")
        check("acct_id", e == acct["email"], e)

    print("\n8. and nothing is invented when there is genuinely nobody")
    e, n = await app._retry_contact(UPI, {"product": "nidaan_plink"}, "Payment link")
    same("returns empty rather than a guess", (e, n), ("", ""))
    e, n = await app._retry_contact(UPI, {"claim_id": "99999999"}, "x")
    same("a claim that does not exist returns empty", e, "")

    print("\n9. an email ON the entity still wins - it is the most direct")
    e, n = await app._retry_contact(
        {"id": "pay_X", "email": "onentity@example.com"},
        {"notify_email": "notes@example.com"}, "x")
    same("the entity's own address", e, "onentity@example.com")

    print("\n%d passed, %d failed" % (P, F))
    return 1 if F else 0


sys.exit(asyncio.run(main()))
