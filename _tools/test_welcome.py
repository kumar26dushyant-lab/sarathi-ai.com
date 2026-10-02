# -*- coding: utf-8 -*-
"""CONFIRM FIRST, THEN WELCOME (founder, 2 Oct 2026).

  * a new claim whose complainant has not proven a contact gets the confirmations (code + link,
    no claim details) - and NOT the welcome;
  * the moment the mobile or the email is proven, the welcome goes - once;
  * the alert sweep calling the claim-raised path again sends nothing more;
  * a complainant already proven (signed in with that email) is welcomed at once;
  * an old claim never gets a "registered" message out of the blue.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_welcome.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="welcome_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_contact_verify as cv              # noqa: E402
import biz_nidaan_welcome as wel                    # noqa: E402
import biz_nidaan_wa_orchestrator as orch           # noqa: E402

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
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (1,'House','house@example.invalid','','x')")
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) "
                        "VALUES (2,'Sita','sita@example.com','9811111111','x')")
        for cid, acct, phone, email, created in (
                (10, 1, '9876543210', 'ramesh@example.com', "datetime('now')"),
                (11, 2, '9811111111', 'sita@example.com', "datetime('now')"),
                (12, 1, '9822222222', 'old@example.com', "datetime('now','-5 days')")):
            await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                            "complainant_name, complainant_phone, complainant_email, status, created_at) VALUES "
                            f"(?,?,'health','PATIENT','', 'COMPLAINANT', ?, ?, 'intimated', {created})",
                            (cid, acct, phone, email))
        await c.commit()
    # Sita signed in with her email: proven on her account.
    await cv.record("email", "sita@example.com", "login_email_code", account_id=2, actor="test")

    confirms, welcomes, emails = [], [], []

    async def _confirm(claim_id, kind, **k):
        confirms.append((claim_id, kind))
        return {"ok": True}

    async def _journey(claim_id, event, *a, **k):
        welcomes.append((claim_id, event))
        return {"ok": True}

    async def _mail(claim_id):
        emails.append(claim_id)
        return {"ok": True}
    cv.send_confirm = _confirm
    orch.wa_journey = _journey
    wel._welcome_email = _mail

    r = await wel.on_claim_created(10)
    check("an unproven complainant gets the confirmations, mobile and email",
          sorted(confirms) == [(10, "email"), (10, "phone")], confirms)
    check("...and NOT the welcome", welcomes == [] and emails == [], (welcomes, emails))
    confirms.clear()
    await wel.on_claim_created(10)          # the 20-minute alert sweep re-runs the raised path
    check("the sweep running it again sends nothing", confirms == [] and welcomes == [], (confirms, welcomes))

    await cv.note_inbound("919876543210")    # they WhatsApp "Hi" from that mobile
    check("they write to us from that mobile: the WhatsApp welcome goes - and ONLY there",
          welcomes == [(10, "claim_registered")] and emails == [], (welcomes, emails))
    await cv.record("email", "ramesh@example.com", "email_link", claim_id=10, actor="complainant")
    await cv._note(10, "email", "ramesh@example.com", "email_link")
    check("the email, once THAT is proven, gets its own welcome", emails == [10], emails)
    await cv._note(10, "email", "ramesh@example.com", "email_link")
    check("...each channel once", emails == [10], emails)

    await wel.on_claim_created(11)
    check("a complainant who already proved the email (signed in with it) is welcomed there at once",
          emails.count(11) == 1, emails)
    check("...not on a WhatsApp number nobody has proven - that gets a confirmation code instead",
          (11, "claim_registered") not in welcomes and (11, "phone") in confirms and (11, "email") not in confirms,
          (welcomes, confirms))

    before = (len(welcomes), len(confirms))
    await wel.on_claim_created(12)
    await cv.note_inbound("919822222222")
    check("an old claim is never sent a 'registered' message out of the blue",
          (len(welcomes), len(confirms)) == before, (welcomes, confirms))

    print("\n" + ("all passed" if not FAILED else f"{FAILED} failed"))
    sys.exit(1 if FAILED else 0)


asyncio.run(main())
