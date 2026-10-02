# -*- coding: utf-8 -*-
"""PAYMENT MESSAGES GO TO THE PERSON WHO PAID - nobody else (founder, 2-3 Oct 2026).

"payment thing should go to the person who did the payment not to complainant or insured/patient
... we had a scenario in the past wherein our staff paid and message went to complainant/insured
created a problem because our staff charged a bit high."

WHO PAID is read from the payment itself, never from who the claim is about:
  * an Authorized Partner's Level-2 fee (portal checkout)  -> the AP (its contact phone / email)
  * a staff member's Level-2 fee (My Business)             -> that staff member, on Telegram
  * a claim review fee / plan on a customer's own account  -> the account holder
  * a payment LINK                                         -> whoever actually paid it (Razorpay's
                                                              email / contact on the payment); if
                                                              that is our AP or staff, them
The complainant / patient hears about a payment only if they are that person.

WHAT they hear, once per payment per event (nidaan_pay_notices):
  paid     - thank you, what for, the amount, the payment id (WhatsApp + email; staff: Telegram)
  failed   - it did not go through; no money taken (or it returns by itself); try again - sent
             only if the order is STILL unpaid after FAILED_WAIT_S (a UPI retry often succeeds)
  refunded - the amount is on its way back
Every message is sent only after Razorpay has confirmed the event (captured / failed / refunded).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.paynotify")

FAILED_WAIT_S = 600
WA_NUMBER = "+91 91836 86384"
_WHAT = {
    "per_claim_review": "the claim review", "nidaan_claim_499": "the claim review",
    "nidaan_review_999": "the claim review", "nidaan_review": "the claim review",
    "branch_l2": "the Level-2 fee", "nidaan_branch_l2": "the Level-2 fee",
    "subscription": "your plan", "subscription_renewal": "your plan renewal", "nidaan": "your plan",
    "payment_link": "your payment", "nidaan_plink": "your payment",
}


def _digits10(v) -> str:
    d = "".join(ch for ch in str(v or "") if ch.isdigit())
    return d[-10:] if len(d) >= 10 else ""


def _esc(v) -> str:
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rupees(paise) -> str:
    r = (int(paise or 0)) / 100.0
    return "₹" + (("%.2f" % r).rstrip("0").rstrip("."))


async def _one(sql: str, args=()) -> Optional[dict]:
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(sql, args)).fetchone()
    return dict(r) if r else None


async def _staff_by_phone_or_email(phone: str, email: str) -> Optional[dict]:
    p, e = _digits10(phone), (email or "").strip().lower()
    if not (p or e):
        return None
    return await _one("SELECT staff_id, name, phone, email FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
                      "AND ((? <> '' AND substr(COALESCE(phone,''),-10)=?) OR (? <> '' AND LOWER(COALESCE(email,''))=?)) LIMIT 1",
                      (p, p, e, e))


async def _branch(code: str) -> Optional[dict]:
    if not code:
        return None
    return await _one("SELECT branch_code, name, contact_phone AS phone, contact_email AS email FROM nidaan_branches "
                      "WHERE UPPER(branch_code)=?", (code.strip().upper(),))


async def _claim_side(claim_id) -> dict:
    """For a claim: who OWNS its account - an AP (branch house account), a staff member (SP- code)
    or a customer account."""
    if not claim_id:
        return {}
    c = await _one("SELECT c.claim_id, c.branch_code, c.origin, c.account_id, a.owner_name, a.phone, a.email "
                   "FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id WHERE c.claim_id=?",
                   (int(claim_id),))
    return c or {}


async def payer_for(*, source: str, claim_id=None, account_id=None, branch_code: str = "",
                    pay_email: str = "", pay_phone: str = "") -> dict:
    """{kind: ap|staff|account|link_payer|unknown, name, email, phone, staff_id, branch_code}.
    pay_email / pay_phone: what Razorpay recorded for the payer of THIS payment (links)."""
    src = source or ""
    claim = await _claim_side(claim_id)
    code = (branch_code or claim.get("branch_code") or "").strip().upper()
    is_link = src in ("payment_link", "nidaan_plink")
    if is_link:
        # Whoever paid the link. If that is our own AP or staff member, they hear it as such.
        st = await _staff_by_phone_or_email(pay_phone, pay_email)
        if st:
            return {"kind": "staff", "name": st["name"], "staff_id": st["staff_id"], "email": "", "phone": ""}
        br = await _branch(code)
        if br and ((_digits10(pay_phone) and _digits10(pay_phone) == _digits10(br.get("phone")))
                   or (pay_email and pay_email.lower() == (br.get("email") or "").lower())):
            return {"kind": "ap", "name": br["name"] or code, "email": br.get("email") or "",
                    "phone": br.get("phone") or "", "branch_code": code}
        if pay_email or pay_phone:
            return {"kind": "link_payer", "name": "", "email": pay_email, "phone": pay_phone}
        return {"kind": "unknown"}
    if src in ("branch_l2", "nidaan_branch_l2") or (claim.get("origin") == "branch" and src in ("per_claim_review", "nidaan_claim_499")):
        if code.startswith("SP-"):
            st = await _one("SELECT staff_id, name FROM nidaan_staff WHERE UPPER(COALESCE(referral_code,''))=? "
                            "AND status='active' AND deleted_at IS NULL", (code,))
            if st:
                return {"kind": "staff", "name": st["name"], "staff_id": st["staff_id"], "email": "", "phone": ""}
            return {"kind": "unknown"}
        br = await _branch(code)
        if br:
            return {"kind": "ap", "name": br["name"] or code, "email": br.get("email") or "",
                    "phone": br.get("phone") or "", "branch_code": code}
        return {"kind": "unknown"}
    acct_id = account_id or claim.get("account_id")
    if acct_id:
        a = await _one("SELECT owner_name, phone, email FROM nidaan_accounts WHERE account_id=?", (int(acct_id),))
        if a and not (a.get("email") or "").lower().endswith("@house.nidaanpartner.internal"):
            return {"kind": "account", "name": a.get("owner_name") or "", "email": a.get("email") or "",
                    "phone": a.get("phone") or "", "account_id": acct_id}
    if pay_email or pay_phone:
        return {"kind": "link_payer", "name": "", "email": pay_email, "phone": pay_phone}
    return {"kind": "unknown"}


async def _claim_once(key: str, event: str) -> bool:
    """Reserve (key, event). True the first time only - a payment is thanked / refused once."""
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute("CREATE TABLE IF NOT EXISTS nidaan_pay_notices (pkey TEXT NOT NULL, event TEXT NOT NULL, "
                        "payer TEXT DEFAULT '', sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (pkey, event))")
        cur = await c.execute("INSERT OR IGNORE INTO nidaan_pay_notices (pkey, event) VALUES (?,?)", (key, event))
        await c.commit()
        return cur.rowcount == 1


def _texts(event: str, *, name: str, amount: str, what: str, ref: str, pid: str) -> tuple[str, str, str]:
    first = (name or "").strip().split(" ")[0].title()
    hello = ("Namaste %s," % first) if first else "Namaste,"
    pid_line = (" (payment %s)" % pid) if pid else ""
    if event == "paid":
        subj = "Payment received - thank you"
        body = ("%s\n\nThank you - we have received your payment of %s for %s%s%s.\n\n"
                "If you need any help, write to us on WhatsApp %s.\n\n- NidaanPartner"
                % (hello, amount, what, (" on " + ref) if ref else "", pid_line, WA_NUMBER))
    elif event == "failed":
        subj = "Your payment did not go through"
        body = ("%s\n\nYour payment of %s for %s%s did not go through. If any money was taken, it "
                "returns to you by itself within 5-7 working days - please do not worry.\n\nYou can try "
                "again from the same page. Need help? WhatsApp %s.\n\n- NidaanPartner"
                % (hello, amount, what, (" on " + ref) if ref else "", WA_NUMBER))
    else:   # refunded
        subj = "Your refund is on its way"
        body = ("%s\n\nWe have refunded %s for %s%s%s. It reaches your account in 5-7 working days.\n\n"
                "Questions? WhatsApp %s.\n\n- NidaanPartner"
                % (hello, amount, what, (" on " + ref) if ref else "", pid_line, WA_NUMBER))
    return subj, body, first


async def _send_whatsapp(phone: str, text: str, *, event: str, first: str, amount: str, ref: str) -> bool:
    """Free text inside the 24-hour window; otherwise the approved np_payment_thanks template for a
    thank-you (its placeholders are counted from Meta's own wording - never guessed)."""
    try:
        import biz_nidaan_whatsapp as wa
        import biz_nidaan_wa_flow as flow
        if not wa.is_configured() or not _digits10(phone):
            return False
        msisdn = wa.normalize_msisdn(phone)
        ct = await flow.get_contact(msisdn) or {}
        if (ct.get("status") or "") == "stopped":
            return False
        with wa.sending_as("system"):
            if await flow.in_session_window(msisdn):
                res = await wa.send_text(msisdn, text)
                return bool(res.get("ok"))
            if event != "paid":
                return False           # no approved template for these yet - the email carries it
            bodies = await wa._template_bodies()
            for lang in ("en", "hi"):
                tb = bodies.get(("np_payment_thanks", lang))
                if not tb:
                    continue
                n = len(set(re.findall(r"\{\{(\d+)\}\}", tb)))
                vals = [first or "there", amount.replace("₹", ""), ref or "your payment"][:n]
                if len(vals) < n:
                    return False
                res = await wa.send_template(msisdn, "np_payment_thanks", lang, wa.body_params(*vals))
                return bool(res.get("ok"))
    except Exception as e:  # noqa: BLE001
        logger.info("payer WhatsApp failed: %s", e)
    return False


async def notify(event: str, *, key: str, source: str, amount_paise: int = 0, claim_id=None,
                 account_id=None, branch_code: str = "", pay_email: str = "", pay_phone: str = "",
                 payment_id: str = "", email_too: bool = True) -> dict:
    """Tell the PAYER, once. Never raises."""
    try:
        if not key or not await _claim_once(key, event):
            return {"ok": True, "skipped": "already told"}
        payer = await payer_for(source=source, claim_id=claim_id, account_id=account_id,
                                branch_code=branch_code, pay_email=pay_email, pay_phone=pay_phone)
        if payer.get("kind") == "unknown":
            logger.info("payer unknown for %s %s - nobody told", event, key)
            return {"ok": False, "why": "payer unknown"}
        amount = _rupees(amount_paise)
        what = _WHAT.get(source, "your payment")
        ref = ("claim NP-%s" % claim_id) if claim_id else ""
        subj, body, first = _texts(event, name=payer.get("name", ""), amount=amount, what=what, ref=ref, pid=payment_id)
        out = {"payer": payer.get("kind")}
        if payer["kind"] == "staff":
            import biz_nidaan_notifications as nn
            await nn.notify_staff_inapp([payer["staff_id"]], subj, body, event_key="payment.payer_notice",
                                        email=False, claim_id=claim_id)
            out["telegram"] = True
            return out
        if email_too and payer.get("email"):
            import biz_email as em
            html = "<div style='font-family:Arial,sans-serif;font-size:15px;line-height:1.6'>%s</div>" % (
                _esc(body).replace("\n", "<br>"))
            r = await em.send_email(to_email=payer["email"], subject=subj, html_body=html, from_name="Nidaan Partner")
            out["email"] = bool(r.get("ok")) if isinstance(r, dict) else bool(r)
        out["whatsapp"] = await _send_whatsapp(payer.get("phone", ""), body, event=event, first=first,
                                               amount=amount, ref=ref)
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning("payer notice %s failed for %s: %s", event, key, e)
        return {"ok": False}


async def _rzp_get(path: str) -> Optional[dict]:
    rid = os.getenv("NIDAAN_RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_KEY_ID", "")
    rsec = os.getenv("NIDAAN_RAZORPAY_KEY_SECRET") or os.getenv("RAZORPAY_KEY_SECRET", "")
    if not (rid and rsec):
        return None
    try:
        import httpx
        async with httpx.AsyncClient() as c:
            r = await c.get("https://api.razorpay.com/v1/" + path, auth=(rid, rsec), timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception:  # noqa: BLE001
        return None


async def paid(*, source: str, payment_id: str, dedup_key: str = "", amount_paise: int = 0, claim_id=None,
               account_id=None, branch_code: str = "") -> dict:
    """A payment the ledger has just recorded, confirmed by Razorpay. Thanks its payer.
    The claim review fee (Rs 499) is thanked by its own 'review has started' message to the
    account holder (on_funnel_paid), so it is not thanked twice here."""
    if source == "per_claim_review":
        return {"ok": True, "skipped": "thanked by the review-started message"}
    pe, pp = "", ""
    if source == "payment_link" and payment_id:
        p = await _rzp_get("payments/%s" % payment_id) or {}
        pe, pp = (p.get("email") or ""), (p.get("contact") or "")
    return await notify("paid", key=payment_id or dedup_key, source=source, amount_paise=amount_paise,
                        claim_id=claim_id, account_id=account_id, branch_code=branch_code,
                        pay_email=pe, pay_phone=pp, payment_id=payment_id,
                        # a plan's own activation email already went: WhatsApp only, never two emails
                        email_too=source not in ("subscription", "subscription_renewal"))


async def refund_notice(refund: dict) -> dict:
    """A refund Razorpay has processed that we did not start ourselves (those already told the
    payer). The payer is found from the ORIGINAL payment."""
    pid = (refund or {}).get("payment_id") or ""
    if not pid:
        return {"ok": False}
    p = await _rzp_get("payments/%s" % pid) or {}
    notes = p.get("notes") or {}
    cid = str(notes.get("claim_id") or "")
    return await notify("refunded", key=(refund.get("id") or pid), source=notes.get("product") or "",
                        amount_paise=int(refund.get("amount") or 0),
                        claim_id=int(cid) if cid.isdigit() else None,
                        account_id=int(notes["nidaan_account_id"]) if str(notes.get("nidaan_account_id") or "").isdigit() else None,
                        branch_code=notes.get("branch") or "", pay_email=p.get("email") or "",
                        pay_phone=p.get("contact") or "", payment_id=pid)


async def failed_later(*, key: str, order_id: str, source: str, amount_paise: int, claim_id=None,
                       account_id=None, branch_code: str = "", pay_email: str = "", pay_phone: str = "",
                       retry=None) -> None:
    """A failed attempt: wait, and tell the payer only if the order is STILL unpaid (a UPI retry a
    minute later is common - "your payment failed" after it succeeded would be wrong)."""
    await asyncio.sleep(FAILED_WAIT_S)
    try:
        if order_id:
            o = await _rzp_get("orders/%s" % order_id)
            if not o or o.get("status") == "paid":
                return                       # paid after all, or we cannot tell: say nothing
        payer = await payer_for(source=source, claim_id=claim_id, account_id=account_id,
                                branch_code=branch_code, pay_email=pay_email, pay_phone=pay_phone)
        # Someone who paid a LINK has no page to go back to: they get a fresh link to try again,
        # once. Everyone else is told, and tries again where they paid.
        if payer.get("kind") == "link_payer" and payer.get("email") and retry and await _claim_once(key, "failed"):
            await retry(payer["email"], payer.get("phone") or "", payer.get("name") or "")
            return
        await notify("failed", key=key, source=source, amount_paise=amount_paise, claim_id=claim_id,
                     account_id=account_id, branch_code=branch_code, pay_email=pay_email, pay_phone=pay_phone)
    except Exception as e:  # noqa: BLE001
        logger.info("failed-payment notice skipped for %s: %s", key, e)
