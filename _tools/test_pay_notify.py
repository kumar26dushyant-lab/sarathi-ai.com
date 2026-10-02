# -*- coding: utf-8 -*-
"""PAYMENT MESSAGES GO ONLY TO THE PERSON WHO PAID (founder, 2-3 Oct 2026).

"we had a scenario in the past wherein our staff paid and message went to complainant/insured
created a problem because our staff charged a bit high".

  * an AP's Level-2 fee: the AP is thanked; the complainant hears nothing about it;
  * a staff member's Level-2 fee: the staff member, on Telegram - no WhatsApp, no email;
  * a payment link: whoever actually paid it (the complainant only if THEY paid);
  * once per payment; the Rs 499 review is thanked by its own "review started" message;
  * a failed payment: the payer, once per order, only if the order is STILL unpaid; a link payer
    gets a fresh link instead; the webhook no longer WhatsApps the complainant;
  * a refund we did not start: its payer is told.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_pay_notify.py
"""
import asyncio
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
DBP = os.path.join(tempfile.mkdtemp(prefix="paynote_"), "t.db")
os.environ["DB_PATH"] = DBP
import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP
import biz_nidaan_pay_notify as pn                  # noqa: E402

FAILED = 0
OUT = []        # (channel, to, text)


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


def to(*who):
    return [o for o in OUT if o[1] in who]


async def main():
    await db.init_db()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_branches (branch_code, name, city, status, contact_phone, contact_email) "
                        "VALUES ('NP-PUNE','Rakesh Sharma','Pune','active','9811111111','ap@example.invalid')")
        await c.execute("INSERT INTO nidaan_staff (staff_id, name, email, password_hash, role, status, referral_code, phone) "
                        "VALUES (5,'Ravi','ravi@example.invalid','x','team_member','active','SP-RAVI','9822222222')")
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash) VALUES "
                        "(1,'House','branch.np-pune@house.nidaanpartner.internal','','x'),"
                        "(2,'House','branch.sp-ravi@house.nidaanpartner.internal','','x'),"
                        "(3,'Sita Advisor','sita@example.invalid','9833333333','x')")
        for cid, acct, code in ((10, 1, "NP-PUNE"), (11, 2, "SP-RAVI"), (12, 3, "")):
            await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                            "complainant_name, complainant_phone, complainant_email, branch_code, origin, status) VALUES "
                            "(?,?,'health','PATIENT','9800000099','COMPLAINANT','9800000000','comp@example.invalid',?,?,'intimated')",
                            (cid, acct, code, "branch" if code else ""))
        await c.commit()

    import biz_email as em
    import biz_nidaan_whatsapp as wa
    import biz_nidaan_wa_flow as flow
    import biz_nidaan_notifications as nn

    async def _mail(to_email="", subject="", html_body="", **k):
        OUT.append(("email", to_email, subject))
        return True

    async def _text(m, t):
        OUT.append(("whatsapp", m[-10:], t))
        return {"ok": True}

    async def _open(_m):
        return True

    async def _contact(_m):
        return {}

    async def _inapp(ids, subj, body, **k):
        for i in ids:
            OUT.append(("telegram", "staff:%s" % i, subj))
    em.send_email = _mail
    wa.send_text = _text
    wa.is_configured = lambda: True
    flow.in_session_window = _open
    flow.get_contact = _contact
    nn.notify_staff_inapp = _inapp
    RZP = {"payments/pay_LINK_C": {"email": "comp@example.invalid", "contact": "+919800000000"},
           "payments/pay_LINK_A": {"email": "", "contact": "9811111111"},
           "orders/order_UNPAID": {"status": "attempted"}, "orders/order_PAID": {"status": "paid"},
           "payments/pay_R": {"email": "sita@example.invalid", "contact": "9833333333",
                              "notes": {"product": "nidaan_claim_499", "claim_id": "12", "nidaan_account_id": "3"}}}

    async def _rzp(path):
        return RZP.get(path)
    pn._rzp_get = _rzp
    pn.FAILED_WAIT_S = 0

    COMPLAINANT = ("comp@example.invalid", "9800000000", "9800000099")

    print("\n-- paid --")
    await pn.paid(source="branch_l2", payment_id="pay_AP", amount_paise=58882, claim_id=10, branch_code="NP-PUNE")
    check("an AP's Level-2 fee: the AP is thanked by email and WhatsApp",
          len(to("ap@example.invalid")) == 1 and len(to("9811111111")) == 1, OUT)
    check("...and the complainant / patient hear NOTHING about it", not to(*COMPLAINANT), OUT)
    OUT.clear()
    await pn.paid(source="branch_l2", payment_id="pay_AP", amount_paise=58882, claim_id=10, branch_code="NP-PUNE")
    check("the same payment is thanked once", OUT == [], OUT)
    await pn.paid(source="branch_l2", payment_id="pay_ST", amount_paise=58882, claim_id=11, branch_code="SP-RAVI")
    check("a staff member's Level-2 fee: Telegram to that staff member only",
          to("staff:5") and not [o for o in OUT if o[0] in ("email", "whatsapp")], OUT)
    OUT.clear()
    await pn.paid(source="payment_link", payment_id="pay_LINK_C", amount_paise=58882, claim_id=10, branch_code="NP-PUNE")
    check("a link the complainant paid themselves: they are thanked (they paid)", to("comp@example.invalid"), OUT)
    OUT.clear()
    await pn.paid(source="payment_link", payment_id="pay_LINK_A", amount_paise=58882, claim_id=10, branch_code="NP-PUNE")
    check("a link the AP paid: the AP, not the complainant", to("ap@example.invalid", "9811111111") and not to(*COMPLAINANT), OUT)
    OUT.clear()
    await pn.paid(source="per_claim_review", payment_id="pay_499", amount_paise=58882, claim_id=12, account_id=3)
    check("the Rs 499 review is not thanked twice (its 'review started' message does it)", OUT == [], OUT)

    print("\n-- failed --")
    await pn.failed_later(key="order:order_PAID", order_id="order_PAID", source="nidaan_branch_l2",
                          amount_paise=58882, claim_id=10, branch_code="NP-PUNE")
    check("a failed try on an order that was paid after all: nobody is told", OUT == [], OUT)
    await pn.failed_later(key="order:order_UNPAID", order_id="order_UNPAID", source="nidaan_branch_l2",
                          amount_paise=58882, claim_id=10, branch_code="NP-PUNE")
    await pn.failed_later(key="order:order_UNPAID", order_id="order_UNPAID", source="nidaan_branch_l2",
                          amount_paise=58882, claim_id=10, branch_code="NP-PUNE")
    check("still unpaid: the AP is told - once for the order, however many tries failed",
          len(to("ap@example.invalid")) == 1 and not to(*COMPLAINANT), OUT)
    OUT.clear()
    retried = []

    async def _retry(e, p, n):
        retried.append(e)
    await pn.failed_later(key="order:order_UNPAID2", order_id="order_UNPAID", source="nidaan_plink",
                          amount_paise=58882, claim_id=None, pay_email="payer@example.invalid",
                          pay_phone="9844444444", retry=_retry)
    check("someone who paid a LINK gets a fresh link instead", retried == ["payer@example.invalid"] and OUT == [],
          (retried, OUT))
    src = io.open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sarathi_biz.py"),
                  encoding="utf-8").read()
    check("the webhook no longer WhatsApps the complainant when a payment fails",
          'wa_journey(int(_cid_note), "payment_failed")' not in src, "")

    print("\n-- refunded --")
    OUT.clear()
    await pn.refund_notice({"id": "rfnd_1", "payment_id": "pay_R", "amount": 58882})
    check("a refund we did not start: its payer (the account holder) is told",
          to("sita@example.invalid") and not to(*COMPLAINANT), OUT)

    print("\n" + ("all passed" if not FAILED else f"{FAILED} failed"))
    sys.exit(1 if FAILED else 0)


asyncio.run(main())
