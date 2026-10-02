# -*- coding: utf-8 -*-
"""ONE CLAIM INTAKE AT EVERY DOOR (founder, 2 Oct 2026) - the contract, door by door.

Pinned here, through the real routes of the real app:
  * the seven core details are checked the same way at the subscriber dashboard, the AP portal,
    My Business and Raise for a Subscriber - patient name required, complainant name + mobile +
    email required, a known insurance type, the insurer, the disputed amount;
  * a claim cannot be created without the rejection letter: it is uploaded FIRST and arrives as a
    single-use token that only its uploader can spend;
  * only the AP and staff doors may go without it, with a reason - the letter is then due in 7
    days, the raiser is reminded, and on the due date the claim is ARCHIVED (never deleted);
  * the patient and complainant are stored as the two people the form named (My Business used to
    store one "customer" as both).

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_intake.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
TMP = tempfile.mkdtemp(prefix="intake_")
DBP = os.path.join(TMP, "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_intake as intake                  # noqa: E402

FAILED = 0
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:400])


def raises(fn, *a):
    try:
        fn(*a)
    except intake.IntakeError as e:
        return e.field
    return None


GOOD = {"insured_name": "Kamla Devi", "complainant_name": "Ramesh Kumar",
        "complainant_phone": "+91 98765 43210", "complainant_email": "Ramesh@Example.com",
        "claim_type": "health", "insurer_name": "Star Health", "disputed_amount": "1,50,000"}


def unit():
    print("\n-- the rules --")
    c = intake.check_core(GOOD)
    check("a complete claim passes, the mobile becomes 10 digits, the email lower case, the amount a number",
          c["complainant_phone"] == "9876543210" and c["complainant_email"] == "ramesh@example.com"
          and c["disputed_amount"] == 150000, c)
    check("the patient's mobile and email are optional", c["insured_phone"] == "" and c["insured_email"] == "", c)
    for field in ("insured_name", "complainant_name", "complainant_phone", "complainant_email",
                  "claim_type", "insurer_name", "disputed_amount"):
        d = dict(GOOD); d[field] = ""
        check(f"missing {field} is refused, naming that field", raises(intake.check_core, d) == field)
    d = dict(GOOD, complainant_phone="5876543210")
    check("a number that is not an Indian mobile is refused", raises(intake.check_core, d) == "complainant_phone")
    d = dict(GOOD, complainant_phone="09876543210")
    check("a 0-prefixed mobile is understood", intake.check_core(d)["complainant_phone"] == "9876543210")
    d = dict(GOOD, insured_phone="12345")
    check("a patient mobile, if given, must be real", raises(intake.check_core, d) == "insured_phone")
    d = dict(GOOD, complainant_name="Ramesh 123")
    check("digits in a name are refused", raises(intake.check_core, d) == "complainant_name")
    d = dict(GOOD, insured_name="कमला देवी")
    check("a name written in Hindi is accepted", intake.check_core(d)["insured_name"] == "कमला देवी")
    d = dict(GOOD, disputed_amount="0")
    check("a zero amount is refused", raises(intake.check_core, d) == "disputed_amount")
    d = dict(GOOD, disputed_amount=str(10 ** 10))
    check("an amount above Rs 100 crore is refused (the zeros)", raises(intake.check_core, d) == "disputed_amount")
    d = dict(GOOD, policy_no="<script>")
    check("a policy number with markup is refused", raises(intake.check_core, d) == "policy_no")
    d = dict(GOOD, claim_type="general")
    check("an old form's 'general' still files, as 'other'", intake.check_core(d)["claim_type"] == "other")
    check("every standard type has an English and a Hindi name",
          all(t["en"] and t["hi"] for t in intake.types_public()) and len(intake.CODES) >= 10)
    keys = {c: intake.letter_key(c) for c in intake.CODES}
    check("every type knows which checklist line is the rejection letter",
          all(k in [d["key"] for d in __import__("biz_nidaan_doc_checklist").doc_template_for(intake.template_for(c))]
              for c, k in keys.items()), keys)
    check("the subscriber door cannot go without the letter",
          raises(intake.no_letter_reason, "subscriber", "insurer never replied") == "rejection_letter")
    check("the AP door needs a real reason", raises(intake.no_letter_reason, "ap", "na") == "no_letter_reason")
    check("...and accepts one", intake.no_letter_reason("ap", "Insurer has not replied yet") != "")
    d = dict(GOOD, insured_name="M/S SHARMA TRADERS (24 CARAT) & CO")
    check("an insured that is a firm is accepted (fire, marine, business claims)",
          intake.check_core(d)["insured_name"].startswith("M/S"))
    d = dict(GOOD, complainant_name="M/S SHARMA TRADERS")
    check("...but the complainant is a person", raises(intake.check_core, d) == "complainant_name")
    check("a life claim's letter is its 'decision letter'", intake.letter_key("life") == "decision_letter")
    check("same person: same name or same mobile",
          intake.same_person({"insured_name": "A B", "complainant_name": "a  b"})
          and not intake.same_person({"insured_name": "A", "complainant_name": "B"}))


async def routes():
    import httpx
    os.environ.setdefault("NIDAAN_JWT_SECRET", "test-only-not-a-secret")
    import nidaan_app as app_mod
    import biz_av_scan

    async def _clean(_b):
        return True, ""
    biz_av_scan.scan_bytes = _clean                 # no clamd here; the real scan is tested elsewhere
    app_mod._NIDAAN_DOCS_DIR = __import__("pathlib").Path(TMP)
    app_mod.nidaan.DB_PATH = DBP
    import biz_nidaan_access as acc
    acc.DB_PATH = DBP
    import biz_nidaan_notifications as nnot
    import biz_nidaan_wa_orchestrator as orch

    async def _quiet(*a, **k):
        return None
    nnot.on_ops_claim_raised = _quiet
    nnot.on_claim_filed = _quiet
    nnot.on_lead_filed = _quiet

    await db.init_db()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash, status) "
                        "VALUES (1,'Sub One','sub@example.invalid','9000000001','x','active')")
        await c.execute("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, status) "
                        "VALUES (1,'silver',0,'active')")
        await c.execute("INSERT INTO nidaan_branches (branch_code, name, city, status, contact_phone, contact_email) "
                        "VALUES ('NP-TEST','Test AP','Pune','active','9000000002','ap@example.invalid')")
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status, referral_code) "
                        "VALUES (5,'Ravi','ravi@example.invalid','x','team_member','active','SP-RAVI')")
        await c.commit()
    ap = {"Authorization": "Bearer " + nid.create_branch_token("NP-TEST")}
    staff = {"Authorization": "Bearer " + nid.create_staff_token(5, "team_member", "Ravi")}
    sub = {"Authorization": "Bearer " + nid.create_nidaan_token(1, "sub@example.invalid")}

    transport = httpx.ASGITransport(app=app_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="https://nidaanpartner.com") as cl:
        async def stage(path, hdr):
            r = await cl.post(path, headers=hdr, files={"file": ("letter.pdf", PDF, "application/pdf")})
            return r

        print("\n-- the AP portal --")
        body = {"insured_name": "Kamla Devi", "complainant_name": "Ramesh Kumar",
                "complainant_phone": "9876543210", "complainant_email": "r@example.com",
                "claim_type": "health", "insurer_name": "Star Health", "disputed_amount": 150000}
        r = await cl.post("/nidaan/branch/api/claims", headers=ap, json=body)
        check("no letter and no reason: refused, naming the letter",
              r.status_code == 400 and r.json().get("field") == "rejection_letter", (r.status_code, r.text))
        check("...in English and in Hindi", bool(r.json().get("detail")) and bool(r.json().get("detail_hi")), r.text)
        r = await cl.post("/nidaan/branch/api/claims", headers=ap,
                          json=dict(body, complainant_email=""))
        check("no complainant email: refused", r.status_code == 400 and r.json().get("field") == "complainant_email",
              r.text)
        s = await stage("/nidaan/branch/api/intake/letter", ap)
        check("the AP uploads the letter first and gets a token", s.status_code == 200 and s.json().get("token"),
              s.text)
        tok = s.json().get("token", "")
        r = await cl.post("/nidaan/ops/api/my-claims", headers=staff, json=dict(body, letter_token=tok))
        check("someone else cannot spend the AP's letter", r.status_code == 400
              and r.json().get("field") == "rejection_letter", r.text)
        r = await cl.post("/nidaan/branch/api/claims", headers=ap, json=dict(body, letter_token=tok))
        check("with its own letter the AP raises the claim", r.status_code == 200 and r.json().get("claim_id"),
              r.text)
        cid = r.json().get("claim_id")
        async with aiosqlite.connect(DBP) as c:
            row = await (await c.execute(
                "SELECT insured_name, complainant_name, insured_phone, insured_email, complainant_email "
                "FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone()
            docs = (await (await c.execute(
                "SELECT COUNT(*) FROM nidaan_claim_documents WHERE claim_id=?", (cid,))).fetchone())[0]
            tick = await (await c.execute(
                "SELECT received FROM nidaan_claim_doc_checklist WHERE claim_id=? AND doc_key='rejection_letter'",
                (cid,))).fetchone()
        check("patient and complainant are stored as two people, the complainant's email NOT copied to the patient",
              row and row[0] == "KAMLA DEVI" and row[1] == "RAMESH KUMAR" and row[2] == "" and row[3] == ""
              and row[4] == "r@example.com", row)
        check("the letter is filed on the claim and ticked on the checklist", docs == 1 and tick and tick[0] == 1,
              (docs, tick))
        r = await cl.post("/nidaan/branch/api/claims", headers=ap, json=dict(body, letter_token=tok))
        check("the same letter cannot raise a second claim", r.status_code == 400, r.text)
        r = await cl.post("/nidaan/branch/api/claims", headers=ap,
                          json=dict(body, no_letter_reason="Insurer has not replied in writing yet"))
        check("the AP may raise without it, with a reason", r.status_code == 200, r.text)
        cid2 = r.json().get("claim_id")
        async with aiosqlite.connect(DBP) as c:
            due = (await (await c.execute(
                "SELECT letter_due_at > datetime('now','+6 days') FROM nidaan_claims WHERE claim_id=?",
                (cid2,))).fetchone())[0]
        check("...and the letter is due in 7 days", due == 1, due)

        print("\n-- My Business --")
        r = await cl.post("/nidaan/ops/api/my-claims", headers=staff,
                          json=dict(body, no_letter_reason="Customer will send it tomorrow"))
        check("staff may raise without the letter, with a reason", r.status_code == 200, r.text)
        cid3 = r.json().get("claim_id")

        print("\n-- the subscriber dashboard --")
        r = await cl.post("/nidaan/api/claims/submit", headers=sub, json=body)
        check("a subscriber cannot go without the letter", r.status_code == 400
              and r.json().get("field") == "rejection_letter", r.text)
        s = await stage("/nidaan/api/intake/letter", sub)
        r = await cl.post("/nidaan/api/claims/submit", headers=sub,
                          json={k: v for k, v in dict(body, letter_token=s.json().get("token")).items()})
        check("with the letter, the subscriber's claim is created", r.status_code == 200, r.text)
        # A paid Rs 499 credit, unused: the claim is PAID, not a lead with a second pay-gate.
        async with aiosqlite.connect(DBP) as c:
            await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash, status) "
                            "VALUES (50,'Retail','r2@example.invalid','9000000003','x','active')")
            await c.execute("INSERT INTO nidaan_per_claim_purchase (account_id, status, amount_paid, claim_type, insured_name, insured_phone, advisor_name, advisor_phone, advisor_email) VALUES (50,'paid',49900,'health','A','9000000003','R','9000000003','r2@example.invalid')")
            await c.commit()
        sub2 = {"Authorization": "Bearer " + nid.create_nidaan_token(50, "r2@example.invalid")}
        s2 = await stage("/nidaan/api/intake/letter", sub2)
        r = await cl.post("/nidaan/api/claims/submit", headers=sub2, json=dict(body, letter_token=s2.json().get("token")))
        async with aiosqlite.connect(DBP) as c:
            ps = (await (await c.execute("SELECT payment_status FROM nidaan_claims WHERE claim_id=?",
                                         (r.json().get("claim_id"),))).fetchone() or [None])[0]
        check("a paid Rs 499 credit makes the claim PAID - never a second pay-gate", r.status_code == 200 and ps == "paid",
              (r.status_code, ps, r.text[:120]))
        s = await stage("/nidaan/api/intake/letter", {})
        check("nobody signed in cannot upload a letter", s.status_code == 401, s.status_code)

        print("\n-- the old Rs 499 page --")
        r = await cl.get("/nidaan/get-reviewed?ref=SP-RAVI", follow_redirects=False)
        check("the old page leads to Get started, keeping the referral code",
              r.status_code == 302 and r.headers.get("location") == "/nidaan/start?ref=SP-RAVI#get-reviewed",
              (r.status_code, r.headers.get("location")))
        r = await cl.post("/nidaan/api/review-signup", json={"name": "A", "phone": "9876543210",
                          "email": "a@example.com", "otp": "123456", "claim_type": "health"})
        check("its sign-up no longer makes a purchase with no complainant and no letter", r.status_code == 410,
              r.status_code)

        print("\n-- Raise for a Subscriber --")
        r = await cl.post("/nidaan/ops/api/subscribers/raise-claim", headers=staff,
                          json={"account_id": 1, "claim_type": "health", "insured_name": "Kamla Devi",
                                "insurer_name": "Star Health", "disputed_amount": 50000,
                                "no_letter_reason": "Insurer has not replied yet"})
        check("no complainant at all is refused (it used to create a claim nobody could reach)",
              r.status_code == 400 and r.json().get("field") == "complainant_name", r.text)

    print("\n-- the 7-day clock --")
    sent = []

    async def _tell(r, *, archived, kept=""):
        sent.append((r["claim_id"], archived))
    intake._tell = _tell
    res = await intake.sweep_letters()
    check("not reminded in the first minutes - the raiser has just been told", res["reminded"] == 0, res)
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_claims SET letter_reminded_at=datetime('now','-21 hours')"
                        " WHERE letter_due_at IS NOT NULL")
        await c.commit()
    res = await intake.sweep_letters()
    check("a day later: the raisers are reminded, nothing archived", res["reminded"] == 2 and res["archived"] == 0, res)
    res = await intake.sweep_letters()
    check("...once a day, not every sweep", res["reminded"] == 0, res)
    async with aiosqlite.connect(DBP) as c:
        await c.execute("UPDATE nidaan_claims SET letter_due_at=datetime('now','-1 minute') WHERE claim_id=?",
                        (cid2,))
        await c.commit()
    res = await intake.sweep_letters()
    async with aiosqlite.connect(DBP) as c:
        arch = await (await c.execute("SELECT archived, archived_by FROM nidaan_claims WHERE claim_id=?",
                                      (cid2,))).fetchone()
        still = (await (await c.execute("SELECT COUNT(*) FROM nidaan_claims WHERE claim_id=?",
                                        (cid2,))).fetchone())[0]
    check("on the due date the claim is ARCHIVED and the raiser told", res["archived"] == 1 and arch[0] == 1
          and (cid2, True) in sent, (res, arch, sent))
    check("...never deleted", still == 1)
    import biz_nidaan_doc_checklist as ck
    await ck.mark_doc_received(cid3, intake.letter_key("health"), via="staff tick")
    res = await intake.sweep_letters()
    check("a letter ticked by staff stops the clock", res["cleared"] == 1, res)

    # A LIFE claim raised without its letter, the letter then ticked by hand (review, 2 Oct): the
    # life checklist calls it "decision_letter" - it used to be archived anyway.
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, complainant_name,"
                        " status, letter_due_at) VALUES (901, 1, 'life', 'A', '', 'B', 'intimated', datetime('now','-1 minute'))")
        # ...and one whose papers arrived as a plain document, never ticked
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, complainant_name,"
                        " status, letter_due_at) VALUES (902, 1, 'health', 'A', '', 'B', 'intimated', datetime('now','-1 minute'))")
        await c.execute("INSERT INTO nidaan_claim_documents (account_id, claim_id, stored_name, original_name, file_size)"
                        " VALUES (1, 902, 'x.pdf', 'scan.pdf', 10)")
        await c.commit()
    await ck.mark_doc_received(901, "decision_letter", via="staff tick")
    sent.clear()
    res = await intake.sweep_letters()
    async with aiosqlite.connect(DBP) as c:
        a901 = (await (await c.execute("SELECT archived FROM nidaan_claims WHERE claim_id=901")).fetchone())[0]
        a902 = (await (await c.execute("SELECT archived FROM nidaan_claims WHERE claim_id=902")).fetchone())[0]
    check("a life claim whose decision letter is ticked is NOT archived", not a901, a901)
    check("a claim whose papers arrived (unticked) is NOT archived - the raiser is asked to tick it",
          not a902 and res["archived"] == 0, (a902, res))


async def main():
    unit()
    await routes()
    print("\n" + ("all passed" if not FAILED else f"{FAILED} failed"))
    sys.exit(1 if FAILED else 0)


asyncio.run(main())
