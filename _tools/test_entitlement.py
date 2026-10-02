# -*- coding: utf-8 -*-
"""NO ENTITLEMENT, NO NEW CLAIM - at every door (founder, 2 Oct 2026).

"block everything for that subscriber and/or one time review user, only their existing case
access". One judge, biz_nidaan.claim_entitlement, through the real routes:
  * a brand-new account raises ONE free claim (the Rs 499 value-first funnel) - not unlimited;
  * a live plan raises within its monthly cap, then is frozen with the reason;
  * a plan past its period is over even if no sweep has run (autopay on: 3 days for the renewal);
  * an expired plan, a used one-time review: frozen; an unused paid review: allowed;
  * AP / staff house accounts are not subscribers and are never judged here;
  * Raise for a Subscriber refuses a lapsed plan and its picker SHOWS lapsed subscribers with why;
  * cancelling stops the autopay and keeps the period already paid for;
  * /me carries the answer, so the dashboard can freeze "raise a claim" (existing claims untouched).

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_entitlement.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
TMP = tempfile.mkdtemp(prefix="ent_")
DBP = os.path.join(TMP, "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP

FAILED = 0
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def ex(q, *a):
    async with aiosqlite.connect(DBP) as c:
        await c.execute(q, a)
        await c.commit()


async def main():
    import httpx
    import nidaan_app as app_mod
    import biz_av_scan

    async def _clean(_b):
        return True, ""
    biz_av_scan.scan_bytes = _clean
    app_mod._NIDAAN_DOCS_DIR = __import__("pathlib").Path(TMP)
    app_mod.nidaan.DB_PATH = DBP
    import biz_nidaan_access as acc
    acc.DB_PATH = DBP
    import biz_nidaan_notifications as nnot

    async def _quiet(*a, **k):
        return None
    for fn in ("on_ops_claim_raised", "on_claim_filed", "on_lead_filed", "notify_staff_inapp"):
        setattr(nnot, fn, _quiet)

    async def _stopped(_sid):
        return True
    nid.stop_razorpay_autopay = _stopped

    await db.init_db()
    accts = [(1, "New Person"), (2, "Live Silver"), (3, "Lapsed Silver"), (4, "Used Review"),
             (5, "Has Credit"), (6, "Expired Status"), (7, "Grace Silver"), (8, "Over Grace")]
    for aid, name in accts:
        await ex("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash, status) "
                 "VALUES (?,?,?,?, 'x','active')", aid, name, f"a{aid}@example.invalid", f"90000000{aid:02d}")
    await ex("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash, status) "
             "VALUES (9,'House','branch.np-x@house.nidaanpartner.internal','', 'x','active')")
    # plans: live; ended with autopay off; status expired; ended 1 day ago (autopay on); ended 5 days ago
    await ex("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, status, current_period_end) "
             "VALUES (2,'silver',589,'active',datetime('now','+20 days'))")
    await ex("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, status, current_period_end, auto_renew) "
             "VALUES (3,'silver',589,'active',datetime('now','-1 day'),0)")
    await ex("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, status, current_period_end) "
             "VALUES (6,'silver',589,'expired',datetime('now','-40 days'))")
    await ex("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, status, current_period_end) "
             "VALUES (7,'silver',589,'active',datetime('now','-1 day'))")
    await ex("INSERT INTO nidaan_subscriptions (account_id, plan, amount_paid, status, current_period_end) "
             "VALUES (8,'silver',589,'active',datetime('now','-5 days'))")
    # one-time review used (linked to a claim); one unused paid credit
    await ex("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, status, payment_status) "
             "VALUES (40,4,'health','A','','intimated','paid')")
    for aid, linked in ((4, 40), (5, None)):
        await ex("INSERT INTO nidaan_per_claim_purchase (account_id, status, amount_paid, claim_type, insured_name, "
                 "insured_phone, advisor_name, advisor_phone, advisor_email, linked_claim_id) "
                 "VALUES (?,'paid',499,'health','A','9000000000','A','9000000000','a@example.invalid',?)", aid, linked)

    print("\n-- the judge --")
    E = {aid: await nid.claim_entitlement(aid) for aid in range(1, 10)}
    check("a brand-new account may raise its first claim (free, pay later)",
          E[1]["can_raise"] and E[1]["pay_status"] == "unpaid_lead", E[1])
    check("a live plan within its cap may raise", E[2]["can_raise"] and E[2]["pay_status"] == "subscription", E[2])
    check("a plan whose period ended with autopay off is FROZEN (no sweep needed)",
          not E[3]["can_raise"] and E[3]["reason"] == "sub_expired", E[3])
    check("an expired plan is frozen, with words in English and Hindi",
          not E[6]["can_raise"] and E[6]["message_en"] and E[6]["message_hi"], E[6])
    check("autopay on, period ended yesterday: still live (the renewal has 3 days to land)", E[7]["can_raise"], E[7])
    check("...5 days over: frozen", not E[8]["can_raise"], E[8])
    check("a one-time review already used is frozen", not E[4]["can_raise"] and E[4]["reason"] == "one_time_used", E[4])
    check("an unused paid review may raise (as paid)", E[5]["can_raise"] and E[5]["pay_status"] == "paid", E[5])
    check("an AP / staff house account is not judged as a subscriber", E[9]["can_raise"], E[9])
    cap = E[2]["cap"]
    await ex("INSERT INTO nidaan_plan_quota (account_id, current_window_start, claims_this_window, updated_at) "
             "VALUES (2, date('now'), ?, datetime('now'))", int(cap or 0))
    e2 = await nid.claim_entitlement(2)
    check("a live plan at its cap is frozen, saying when it frees up",
          cap is not None and not e2["can_raise"] and e2["reason"] == "sub_quota_exhausted" and e2["resets_on"], e2)
    await ex("DELETE FROM nidaan_plan_quota WHERE account_id=2")

    tok = {aid: {"Authorization": "Bearer " + nid.create_nidaan_token(aid, f"a{aid}@example.invalid")} for aid in range(1, 9)}
    await ex("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status) "
             "VALUES (5,'Ravi','ravi@example.invalid','x','team_member','active')")
    staff = {"Authorization": "Bearer " + nid.create_staff_token(5, "team_member", "Ravi")}
    body = {"insured_name": "Kamla Devi", "complainant_name": "Ramesh Kumar", "complainant_phone": "9876543210",
            "complainant_email": "r@example.com", "claim_type": "health", "insurer_name": "Star Health",
            "disputed_amount": 150000}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app_mod.app), base_url="https://nidaanpartner.com") as cl:
        async def stage(hdr):
            return await cl.post("/nidaan/api/intake/letter", headers=hdr, files={"file": ("l.pdf", PDF, "application/pdf")})

        print("\n-- the dashboard / Get started door --")
        s = await stage(tok[1])
        r = await cl.post("/nidaan/api/claims/submit", headers=tok[1], json=dict(body, letter_token=s.json().get("token")))
        check("the new account's first claim goes in", r.status_code == 200, r.text[:160])
        s = await stage(tok[1])
        check("...its SECOND is refused at the letter upload already (no free claims for ever)",
              s.status_code == 402 and s.json().get("reason") == "lead_pending_payment", (s.status_code, s.text[:160]))
        s = await stage(tok[3])
        check("a lapsed plan cannot even start a new claim", s.status_code == 402 and s.json().get("detail_hi"),
              (s.status_code, s.text[:160]))
        r = await cl.post("/nidaan/api/claims/submit", headers=tok[3], json=dict(body, letter_token="x" * 30))
        check("...and its submit is refused with the reason", r.status_code == 402 and r.json().get("reason") == "sub_expired",
              (r.status_code, r.text[:160]))
        r = await cl.get("/nidaan/api/me", headers=tok[3])
        check("/me tells the dashboard to freeze new claims", r.status_code == 200
              and (r.json().get("entitlement") or {}).get("can_raise") is False, r.text[:200])

        print("\n-- Raise for a Subscriber --")
        r = await cl.post("/nidaan/ops/api/subscribers/raise-claim", headers=staff,
                          json=dict(body, account_id=3, no_letter_reason="Insurer has not replied yet"))
        check("a lapsed plan cannot be used on their behalf either", r.status_code == 400 and "ended" in r.text, r.text[:160])
        r = await cl.get("/nidaan/ops/api/subscribers/pick?q=Lapsed", headers=staff)
        rows = r.json().get("subscribers") or []
        check("the picker SHOWS the lapsed subscriber, with why", rows and rows[0]["entitlement"]["can_raise"] is False
              and rows[0]["entitlement"]["message_staff"], r.text[:200])

        print("\n-- cancelling --")

        async def _not_eligible(_sid):
            return False, "outside window", {}
        app_mod.nidaan.check_refund_eligibility = _not_eligible
        r = await cl.post("/nidaan/api/subscribe/cancel", headers=tok[2])
        e2 = await nid.claim_entitlement(2)
        check("cancelling stops the autopay and KEEPS the paid period", r.status_code == 200
              and r.json().get("status") == "autopay_off" and e2["can_raise"] and e2["autopay_on"] is False,
              (r.status_code, r.text[:160], e2))

    print("\n" + ("all passed" if not FAILED else f"{FAILED} failed"))
    sys.exit(1 if FAILED else 0)


asyncio.run(main())
