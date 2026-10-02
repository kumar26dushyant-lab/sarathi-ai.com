# -*- coding: utf-8 -*-
"""A PAYMENT UNLOCKS ONLY WHAT IT WAS MADE FOR (security, 2 Oct 2026).

Found by the 2 Oct payments audit, all reachable by a signed-in customer:
  * the one-time plan verify activated ANY plan for any valid payment signature of ours
    (a Rs 499 payment could have become Platinum Annual);
  * the recurring plan verify trusted the plan named in the request;
  * claim / Level-2 / review verifies never checked the order was made for THIS item.
Razorpay is answered here by a stand-in (the notes on an order are what OUR server wrote when
it created it); nothing leaves this machine.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_payment_binding.py
"""
import asyncio
import hashlib
import hmac
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")
TMP = tempfile.mkdtemp(prefix="paybind_")
DBP = os.path.join(TMP, "t.db")
os.environ["DB_PATH"] = DBP
os.environ["NIDAAN_RAZORPAY_KEY_ID"] = "rzp_test_stand_in"
os.environ["NIDAAN_RAZORPAY_KEY_SECRET"] = "stand-in-secret-for-tests-only"
SECRET = os.environ["NIDAAN_RAZORPAY_KEY_SECRET"]
import aiosqlite                                    # noqa: E402
import httpx                                        # noqa: E402
import biz_database as db                           # noqa: E402
db.DB_PATH = DBP
import biz_nidaan as nid                            # noqa: E402
nid.DB_PATH = DBP

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        print("           " + repr(detail)[:300])


def sig(a, b):
    return hmac.new(SECRET.encode(), f"{a}|{b}".encode(), hashlib.sha256).hexdigest()


# what Razorpay "holds"
RZP = {
    "payments": {
        "pay_A": {"order_id": "order_A", "status": "captured"},     # paid for claim 7's Rs 499
        "pay_L": {"order_id": "order_L", "status": "captured"},     # an L2 fee for claim 7
        "pay_P": {"order_id": "order_P", "status": "authorized"},   # not captured yet
    },
    "orders": {
        "order_A": {"notes": {"product": "nidaan_claim_499", "claim_id": "7"}},
        "order_L": {"notes": {"product": "nidaan_branch_l2", "claim_id": "7"}},
        "order_P": {"notes": {"product": "nidaan_claim_499", "claim_id": "7"}},
    },
    "subscriptions": {
        "sub_S": {"notes": {"product": "nidaan", "nidaan_account_id": "1", "nidaan_plan": "silver"}},
    },
    "down": False,
}


class _Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        return self._b


class _FakeRzp:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **k):
        if RZP["down"]:
            raise httpx.ConnectError("down")
        kind, _, ident = url.split("/v1/")[1].partition("/")
        ident = ident.split("/")[0]
        found = RZP.get(kind, {}).get(ident)
        return _Resp(200, found) if found else _Resp(404, {})

    async def post(self, *a, **k):
        return _Resp(500, {})


_RealClient = httpx.AsyncClient


def _client(*a, **k):
    return _RealClient(*a, **k) if "transport" in k else _FakeRzp()


async def main():
    import nidaan_app as app_mod      # first: libraries subclass httpx.AsyncClient as they load
    httpx.AsyncClient = _client
    app_mod.nidaan.DB_PATH = DBP
    import biz_nidaan_access as acc
    acc.DB_PATH = DBP
    import biz_nidaan_notifications as nnot
    alerts = []

    async def _inapp(ids, subj, body, **k):
        alerts.append(k.get("event_key"))
    nnot.notify_staff_inapp = _inapp

    async def _quiet(*a, **k):
        return None
    for fn in ("on_claim_paid", "on_funnel_paid", "on_claim_filed", "on_ops_claim_raised"):
        if hasattr(nnot, fn):
            setattr(nnot, fn, _quiet)

    await db.init_db()
    async with aiosqlite.connect(DBP) as c:
        await c.execute("INSERT INTO nidaan_accounts (account_id, owner_name, email, phone, password_hash, status) "
                        "VALUES (1,'Sub','s@example.invalid','9000000001','x','active')")
        for cid in (7, 8):
            await c.execute("INSERT INTO nidaan_claims (claim_id, account_id, claim_type, insured_name, insured_phone, "
                            "status, payment_status) VALUES (?,1,'health','A','', 'intimated','unpaid_lead')", (cid,))
        await c.commit()
    hdr = {"Authorization": "Bearer " + nid.create_nidaan_token(1, "s@example.invalid")}

    async def ps(cid):
        async with aiosqlite.connect(DBP) as c:
            return (await (await c.execute("SELECT payment_status FROM nidaan_claims WHERE claim_id=?",
                                           (cid,))).fetchone())[0]

    async with _RealClient(transport=httpx.ASGITransport(app=app_mod.app), base_url="https://nidaanpartner.com") as cl:
        def body(order, pay):
            return {"razorpay_order_id": order, "razorpay_payment_id": pay, "razorpay_signature": sig(order, pay)}

        print("\n-- a claim's Rs 499 --")
        r = await cl.post("/nidaan/api/claims/8/pay-verify", headers=hdr, json=body("order_A", "pay_A"))
        check("claim 7's payment presented for claim 8 is REFUSED", r.status_code == 400 and await ps(8) == "unpaid_lead",
              (r.status_code, r.text[:120]))
        check("...and the founder is told", "security.payment_mismatch" in alerts, alerts)
        r = await cl.post("/nidaan/api/claims/7/pay-verify", headers=hdr, json=body("order_L", "pay_L"))
        check("a Level-2 fee presented as the Rs 499 is refused", r.status_code == 400 and await ps(7) == "unpaid_lead",
              (r.status_code, r.text[:120]))
        r = await cl.post("/nidaan/api/claims/7/pay-verify", headers=hdr, json=body("order_L", "pay_A"))
        check("a payment presented with another order's id is refused", r.status_code == 400, r.status_code)
        r = await cl.post("/nidaan/api/claims/7/pay-verify", headers=hdr, json=body("order_P", "pay_P"))
        check("a payment not captured yet unlocks nothing (pending)", r.status_code == 200
              and r.json().get("status") == "pending" and await ps(7) == "unpaid_lead", r.text[:120])
        RZP["down"] = True
        r = await cl.post("/nidaan/api/claims/7/pay-verify", headers=hdr, json=body("order_A", "pay_A"))
        check("Razorpay unreachable: nothing is unlocked (pending - the webhook finishes it)",
              r.status_code == 200 and r.json().get("status") == "pending" and await ps(7) == "unpaid_lead", r.text[:120])
        RZP["down"] = False
        r = await cl.post("/nidaan/api/claims/7/pay-verify", headers=hdr, json=body("order_A", "pay_A"))
        check("the right payment for the right claim goes through", r.status_code == 200 and await ps(7) == "paid",
              (r.status_code, r.text[:160]))

        print("\n-- plans --")
        r = await cl.post("/nidaan/api/subscribe/verify", headers=hdr,
                          json={"razorpay_order_id": "order_A", "razorpay_payment_id": "pay_A",
                                "razorpay_signature": sig("order_A", "pay_A"), "plan": "platinum_annual"})
        check("the old one-time plan verify is retired (a Rs 499 payment cannot become Platinum)", r.status_code == 410,
              r.status_code)
        r = await cl.post("/nidaan/api/subscribe", headers=hdr, json={"plan": "silver"})
        check("...and its order route too", r.status_code == 410, r.status_code)
        r = await cl.post("/nidaan/api/subscribe/recurring/verify", headers=hdr,
                          json={"razorpay_payment_id": "pay_S", "razorpay_subscription_id": "sub_S",
                                "razorpay_signature": hmac.new(SECRET.encode(), b"pay_S|sub_S", hashlib.sha256).hexdigest(),
                                "plan": "platinum_annual"})
        async with aiosqlite.connect(DBP) as c:
            plat = (await (await c.execute("SELECT COUNT(*) FROM nidaan_subscriptions WHERE plan='platinum_annual'"))
                    .fetchone())[0]
        check("a Silver subscription presented as Platinum Annual is refused", r.status_code == 400 and plat == 0,
              (r.status_code, r.text[:160]))
        r = await cl.post("/nidaan/api/subscribe/recurring/verify", headers=hdr,
                          json={"razorpay_payment_id": "pay_S", "razorpay_subscription_id": "sub_S",
                                "razorpay_signature": hmac.new(SECRET.encode(), b"pay_S|sub_S", hashlib.sha256).hexdigest(),
                                "plan": "silver"})
        check("...and the genuine Silver payment activates Silver", r.status_code == 200
              and r.json().get("status") == "active", (r.status_code, r.text[:160]))

    print("\n" + ("all passed" if not FAILED else f"{FAILED} failed"))
    sys.exit(1 if FAILED else 0)


asyncio.run(main())
