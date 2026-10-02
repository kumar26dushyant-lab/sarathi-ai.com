# -*- coding: utf-8 -*-
"""ONE PERSON, ONE MESSAGE (founder, 2 Oct 2026: "in cases insured and complainant same so need to
ensure no double messaging/notifications should be going out for same number and same email").

  * a claim update reaches a number once and an address once, however many roles that person
    holds and however the number was written (+91, 0, spaces) or the email capitalised;
  * a document ask does the same, even when a staffer types the complainant's number in again;
  * "claim registered" and the welcome go once per claim - the alert sweep cannot resend them -
    and "payment failed" at most once in 15 minutes.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_one_message.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="onemsg_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_claim_parties as parties          # noqa: E402
import biz_nidaan_doc_request as dr                 # noqa: E402
import biz_nidaan_wa_orchestrator as orch           # noqa: E402
import biz_nidaan_notifications as nnot             # noqa: E402
for m in (parties, dr, orch):
    m.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


async def main():
    await db.init_db()
    async with aiosqlite.connect(DBP) as c:
        # The subscriber raised it for himself: he is the account holder AND the complainant.
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'Ramesh','Ramesh@Example.com','+91 98765 43210','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                        "complainant_name, complainant_phone, complainant_email, status) VALUES "
                        "(7,1,'health','RAMESH','','RAMESH','09876543210','ramesh@example.com','intimated')")
        await c.commit()

    print("\n-- a claim update --")
    wa, mail = [], []

    async def _wa(p, text):
        wa.append(p["phone"])

    async def _dispatch(**k):
        mail.append(k.get("recipient_email"))
        return {"channels": {}}
    parties._send_party_whatsapp = _wa
    real_dispatch = nnot.dispatch
    nnot.dispatch = _dispatch
    try:
        await parties.notify_claim_parties(7, event_key="claim.status", subject="s", body="b")
    finally:
        nnot.dispatch = real_dispatch
    check("complainant + subscriber with one phone (+91 / 0 / spaces): ONE WhatsApp", len(wa) == 1, wa)
    check("...and one email for one address in two capitalisations", len(mail) == 1, mail)
    wa.clear(); mail.clear()
    nnot.dispatch = _dispatch
    try:
        await parties.notify_claim_parties(7, event_key="claim.status", subject="s", body="b",
                                           skip_emails=["RAMESH@example.com"])
    finally:
        nnot.dispatch = real_dispatch
    check("an inbox already written to by another path is not written to again", mail == [], mail)

    print("\n-- a document ask --")
    pv = await dr.preview(7, doc_keys=["policy_document"], message="Please send your policy",
                          extras=[{"phone": "9876543210"}, {"email": "RAMESH@EXAMPLE.COM"}])
    ways = [w for p in pv.get("recipients", []) for w in p.get("ways", [])]
    check("a typed-in copy of the complainant's number and email adds nothing",
          sum(1 for w in ways if "WhatsApp" in w) == 1 and sum(1 for w in ways if "@" in w) == 1, ways)

    print("\n-- who hears what (founder, 3 Oct) --")
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status, phone) "
                        "VALUES (9,'Ravi','ravi@example.invalid','x','team_member','active','9822222222')")
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (2,'Advisor','adv@example.invalid','9811111111','x')")
        await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                        "complainant_name, complainant_phone, complainant_email, status, assigned_to_staff_id) VALUES "
                        "(8,2,'health','KAMLA','','KAMLA','9800000000','k@example.invalid','intimated',9)")
        await c.commit()
    pv = await dr.preview(8, doc_keys=["policy_document"], message="Please send your policy")
    staff_rows = [p for p in pv.get("recipients", []) if p.get("role") == "staff"]
    check("a staff member copied on a document ask gets it on Telegram - not WhatsApp, not email",
          staff_rows and staff_rows[0]["ways"] == ["Telegram"], staff_rows)
    wa.clear(); mail.clear()
    texts = []

    async def _wa2(p, text):
        texts.append((p["role"], text))
    parties._send_party_whatsapp = _wa2
    nnot.dispatch = _dispatch
    try:
        await parties.notify_claim_parties(8, event_key="claim.status", subject="s", body="Claim moved",
                                           roles=["complainant", "subscriber", "branch", "staff"])
    finally:
        nnot.dispatch = real_dispatch
    sub_txt = [t for r, t in texts if r == "subscriber"]
    check("the subscriber follows the claim as an FYI on WhatsApp", sub_txt and sub_txt[0].startswith("FYI - "), texts)
    check("...the complainant gets the update itself, and staff no WhatsApp at all",
          any(r == "complainant" and not t.startswith("FYI") for r, t in texts) and not any(r == "staff" for r, _ in texts),
          texts)

    print("\n-- one-time messages --")
    sends = []

    class _W:
        @staticmethod
        def is_configured():
            return True

        @staticmethod
        def normalize_msisdn(p):
            d = "".join(ch for ch in p if ch.isdigit())[-10:]
            return "91" + d

        @staticmethod
        async def send_text(m, t):
            sends.append(m)
            return {"ok": True}

        @staticmethod
        async def send_template(m, *a, **k):
            sends.append(m)
            return {"ok": True}

        @staticmethod
        def body_params(*a):
            return []

        class sending_as:
            def __init__(self, *_a):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
    real_wa = orch._wa
    orch._wa = _W
    import biz_nidaan_wa_flow as flow

    async def _open(_m):
        return True
    real_open = flow.in_session_window
    flow.in_session_window = _open
    try:
        await orch.wa_journey(7, "claim_registered")
        r2 = await orch.wa_journey(7, "claim_registered")      # what the 20-minute sweep used to do
        check("'claim registered' goes once - the sweep's second call sends nothing",
              len(sends) == 1 and r2.get("error") == "already_sent", (sends, r2))
        sends.clear()
        await orch.wa_journey(7, "payment_failed")
        await orch.wa_journey(7, "payment_failed")
        check("two failed payments in a minute: one 'payment failed' message", len(sends) == 1, sends)
        async with aiosqlite.connect(DBP) as c:
            await c.execute("UPDATE nidaan_journey_sends SET at=datetime('now','-20 minutes') "
                            "WHERE claim_id=7 AND event='payment_failed'")
            await c.commit()
        await orch.wa_journey(7, "payment_failed")
        check("...and another one after 15 minutes", len(sends) == 2, sends)
    finally:
        orch._wa = real_wa
        flow.in_session_window = real_open

    print("\n" + ("all passed" if not FAILED else f"{FAILED} failed"))
    sys.exit(1 if FAILED else 0)


asyncio.run(main())
