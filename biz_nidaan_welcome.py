# -*- coding: utf-8 -*-
"""CONFIRM FIRST, THEN WELCOME (founder, 2 Oct 2026).

"Complainant name, email and mobile ALL mandatory ... OTP verification of at least one (email or
WhatsApp) from the official email/WhatsApp. Send the welcome message after verification."

WHY THE ORDER MATTERS. A complainant's mobile or email is typed by somebody else - an AP, a staff
member, a relative - and people get digits wrong. The welcome names the claim and the patient; sent
to a mistyped number it tells a stranger about somebody's medical claim. A confirmation code or link
carries no claim details at all, so it is safe to send to whatever was typed. Only once the person
proves the number or the address is theirs does the welcome go - once, signed with the Authorized
Partner's name on an AP case.

HOW A CONTACT IS PROVEN (biz_nidaan_contact_verify):
  * they reply the WhatsApp code in the chat, or simply write to us on WhatsApp from that number;
  * they click the emailed link, or type the emailed code on their claim page;
  * they already proved it - e.g. they signed in with that email - and then nothing is sent.
Staff help on a call by asking them to WhatsApp "Hi" to our number. Staff never ask anyone to read
a code out: that is the habit fraud calls rely on, and our own emails say we will never ask.

welcome_state on the claim: '' a claim from before this (never welcomed by this path),
'waiting' confirmation sent, 'sent' welcomed. Each step moves it with a conditional UPDATE, so the
alert sweep and a second worker cannot send anything twice.
"""
from __future__ import annotations

import logging

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.welcome")

NEW_CLAIM_DAYS = 2     # the path only takes claims this new - never an old claim found by a sweep


async def _claim(claim_id: int) -> dict:
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute("SELECT * FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    return dict(r) if r else {}


async def on_claim_created(claim_id: int) -> dict:
    """Every door calls this once its claim exists. Welcome now if a contact is already proven;
    otherwise send the confirmations and wait."""
    import biz_nidaan_contact_verify as cv
    async with aiosqlite.connect(db.DB_PATH) as c:
        cur = await c.execute(
            "UPDATE nidaan_claims SET welcome_state='waiting' WHERE claim_id=? AND COALESCE(welcome_state,'')=''"
            " AND COALESCE(archived,0)=0 AND created_at >= datetime('now', ?)",
            (int(claim_id), f"-{NEW_CLAIM_DAYS} days"))
        await c.commit()
        if cur.rowcount != 1:
            return {"ok": True, "skipped": "already started"}
    claim = await _claim(claim_id)
    st = await cv.status(claim)
    if (st.get("phone") or {}).get("verified") or (st.get("email") or {}).get("verified"):
        return await welcome(claim_id)
    sent = {}
    for kind in ("phone", "email"):
        if (st.get(kind) or {}).get("present"):
            try:
                sent[kind] = await cv.send_confirm(claim_id, kind, actor="system (new claim)")
            except Exception as e:  # noqa: BLE001 - one channel failing must not stop the other
                logger.warning("confirmation %s failed for claim %s: %s", kind, claim_id, e)
                sent[kind] = {"ok": False}
    return {"ok": True, "waiting": True, "sent": sent}


async def on_verified(claim_id: int) -> dict:
    """A contact on this claim was just proven. If its welcome is waiting, send it now."""
    return await welcome(claim_id, only_if_waiting=True)


async def welcome(claim_id: int, *, only_if_waiting: bool = False) -> dict:
    cond = "welcome_state='waiting'" if only_if_waiting else "COALESCE(welcome_state,'') IN ('','waiting')"
    async with aiosqlite.connect(db.DB_PATH) as c:
        cur = await c.execute(f"UPDATE nidaan_claims SET welcome_state='sent' WHERE claim_id=? AND {cond}"
                              " AND COALESCE(archived,0)=0", (int(claim_id),))
        await c.commit()
        if cur.rowcount != 1:
            return {"ok": True, "skipped": "not waiting"}
    out = {}
    try:
        import biz_nidaan_wa_orchestrator as orch
        out["whatsapp"] = await orch.wa_journey(claim_id, "claim_registered")
    except Exception as e:  # noqa: BLE001
        logger.warning("welcome WhatsApp failed for claim %s: %s", claim_id, e)
    try:
        out["email"] = await _welcome_email(claim_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("welcome email failed for claim %s: %s", claim_id, e)
    return {"ok": True, **out}


async def _welcome_email(claim_id: int) -> dict:
    """The welcome by email, in English (founder: emails in English are fine), signed with the AP's
    name on an AP case - the same signature the WhatsApp carries."""
    import biz_email as em
    import biz_nidaan_ap_sign as aps
    import biz_nidaan_contact_verify as cv
    claim = await _claim(claim_id)
    to = cv.current(claim).get("email") or ""
    if not to:
        return {"ok": False, "why": "no email"}
    name = ((claim.get("complainant_name") or claim.get("insured_name") or "").strip().split(" ") or [""])[0].title()
    esc = lambda s: str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
    html = ("<div style='font-family:Arial,sans-serif;font-size:15px;line-height:1.6;color:#1a1a1a'>"
            "<p>Namaste %s,</p>"
            "<p>Thank you for confirming. Your claim <b>NP-%s</b> for <b>%s</b> is registered with "
            "NidaanPartner. Our team will review it and keep you updated here and on WhatsApp at "
            "<b>+91 91836 86384</b>.</p>"
            "<p>Please save that number - every message about your claim comes from it. We will never "
            "ask you for a code or a password on a call.</p></div>") % (
        esc(name), claim_id, esc((claim.get("insured_name") or "").title()))
    with aps.about(claim_id=claim_id):
        r = await em.send_email(to_email=to, subject="Your claim NP-%s is registered" % claim_id,
                                html_body=html, from_name="Nidaan Partner")
    ok = bool(r.get("ok")) if isinstance(r, dict) else bool(r)
    try:
        import biz_nidaan as nid
        await nid.record_claim_activity(claim_id, "welcome_email", channel="email", actor="system",
                                        summary="Welcome email to the complainant" + ("" if ok else " - NOT sent"))
    except Exception:  # noqa: BLE001
        pass
    return {"ok": ok}
