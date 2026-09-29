# -*- coding: utf-8 -*-
"""Is this complainant's email / phone PROVEN - and proven for THIS address?

Founder, 1 Oct (claim 174, Mukesh Tak): the email was wrong and showed "verified"; after it was
corrected it still showed "verified". Two faults, found in the code:

  1. Opening the claim page set `insured_email_verified = 1` whatever the complainant used to prove
     who they were. Mukesh proved it with a WhatsApp code; nothing ever proved the email. Of the 65
     claims showing "verified" on 1 Oct, 40 had proved only their PHONE.
  2. The flag was a bare yes/no, not tied to an address - so correcting the email kept the badge,
     now on an address nobody had proved.

THE RULE HERE. A verification is a fact about an exact address: "this email (or phone) was proven,
this way, at this time". A contact is verified only if its CURRENT value has such a proof - so an
edit makes it unverified at once, and changing back to a proven address counts again. Proofs are
never deleted.

WHAT PROVES A CONTACT
  email : a code we emailed, entered back   (claim page sign-in, or the authorization step)
          a confirmation link we emailed, clicked
          signing in to the account with an email code or Google (for that account's email)
  phone : a code we sent on WhatsApp, entered back (claim page) or replied in the chat
          a message that ARRIVED from that number on WhatsApp (WhatsApp ties it to the SIM)

Nothing a member of staff types proves a contact: staff are the ones who typed the wrong email.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.contact")

CONFIRM_TTL_H = 72            # a confirmation link / code stays good this long
CONFIRM_MAX_PER_DAY = 3       # per claim and contact: nobody is flooded
CODE_DIGITS = 6
KINDS = ("email", "phone")

METHOD_WORDS = {
    "portal_email_code": "entered the code we emailed",
    "portal_whatsapp_code": "entered the code we sent on WhatsApp",
    "email_link": "clicked the confirmation link we emailed",
    "whatsapp_reply_code": "replied the code on WhatsApp",
    "whatsapp_message": "wrote to us from this number on WhatsApp",
    "login_email_code": "signed in with an emailed code",
    "login_google": "signed in with Google",
    "legacy_email_link": "opened the emailed claim link (before codes existed)",
}


def _db() -> str:
    return db.DB_PATH


def norm(kind: str, value: str) -> str:
    v = (value or "").strip()
    if kind == "email":
        return v.lower()
    d = "".join(ch for ch in v if ch.isdigit())
    return d[-10:] if len(d) >= 10 else ""


def mask(kind: str, value: str) -> str:
    v = norm(kind, value)
    if not v:
        return "(none)"
    if kind == "phone":
        return "•••••" + v[-4:]
    name, _, dom = v.partition("@")
    return (name[:2] + "•••" + (name[-1:] if len(name) > 3 else "")) + "@" + dom


def current(claim: dict) -> dict:
    """The contact this claim uses - the complainant's, falling back to the insured's. The SAME
    rule every sender uses (claim_access._contacts, doc_request, claim_parties)."""
    return {"email": norm("email", claim.get("complainant_email") or claim.get("insured_email") or ""),
            "phone": norm("phone", claim.get("complainant_phone") or claim.get("insured_phone") or "")}


async def record(kind: str, value: str, method: str, *, claim_id: Optional[int] = None,
                 account_id: Optional[int] = None, actor: str = "") -> bool:
    """A proof. Idempotent per (claim or account, kind, value, method). Never deletes."""
    v = norm(kind, value)
    if kind not in KINDS or not v or method not in METHOD_WORDS or not (claim_id or account_id):
        return False
    try:
        async with aiosqlite.connect(_db()) as c:
            row = await (await c.execute(
                "SELECT 1 FROM nidaan_contact_verifications WHERE kind=? AND value=? AND method=? "
                "AND COALESCE(claim_id,0)=? AND COALESCE(account_id,0)=?",
                (kind, v, method, int(claim_id or 0), int(account_id or 0)))).fetchone()
            if row:
                return True
            await c.execute(
                "INSERT INTO nidaan_contact_verifications (claim_id, account_id, kind, value, "
                "method, actor) VALUES (?,?,?,?,?,?)",
                (claim_id, account_id, kind, v, method, (actor or "")[:80]))
            await c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("could not record a %s proof: %s", kind, e)
        return False


async def status(claim: dict) -> dict:
    """{email: {...}, phone: {...}} for the claim's CURRENT contacts."""
    cur = current(claim)
    out = {}
    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            for kind in KINDS:
                v = cur[kind]
                entry = {"masked": mask(kind, v), "present": bool(v), "verified": False,
                         "method": "", "how": "", "at": "", "pending_since": ""}
                if v:
                    r = await (await c.execute(
                        "SELECT method, verified_at FROM nidaan_contact_verifications "
                        "WHERE kind=? AND value=? AND (claim_id=? OR (account_id IS NOT NULL "
                        "AND account_id=?)) ORDER BY vid DESC LIMIT 1",
                        (kind, v, int(claim.get("claim_id") or 0),
                         int(claim.get("account_id") or -1)))).fetchone()
                    if r:
                        entry.update(verified=True, method=r["method"],
                                     how=METHOD_WORDS.get(r["method"], r["method"]),
                                     at=str(r["verified_at"] or ""))
                    else:
                        p = await (await c.execute(
                            "SELECT sent_at FROM nidaan_contact_confirm WHERE claim_id=? AND "
                            "kind=? AND value=? AND used_at IS NULL AND expires_at > ? "
                            "ORDER BY cid DESC LIMIT 1",
                            (int(claim.get("claim_id") or 0), kind, v,
                             datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))).fetchone()
                        if p:
                            entry["pending_since"] = str(p["sent_at"] or "")
                out[kind] = entry
    except Exception as e:  # noqa: BLE001 - unreadable reads as NOT verified, never as verified
        logger.warning("contact status unreadable for claim %s: %s", claim.get("claim_id"), e)
        for kind in KINDS:
            out[kind] = {"masked": mask(kind, cur[kind]), "present": bool(cur[kind]),
                         "verified": False, "method": "", "how": "", "at": "", "pending_since": ""}
    return out


async def _claim(claim_id: int) -> dict:
    async with aiosqlite.connect(_db()) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, account_id, complainant_name, insured_name, complainant_email, "
            "insured_email, complainant_phone, insured_phone FROM nidaan_claims WHERE claim_id=?",
            (int(claim_id),))).fetchone()
    return dict(r) if r else {}


def _hash(s: str) -> str:
    # The same server secret as the claim-page codes - and like them, NO fallback: with no secret
    # configured this raises rather than hashing with a guessable key.
    import biz_nidaan_claim_access as _acc
    return hmac.new(_acc._pepper(), (s or "").encode(), hashlib.sha256).hexdigest()


# ── when a contact CHANGES ───────────────────────────────────────────────────
async def on_change(claim_id: int, changes: dict, *, actor: str = "staff",
                    send_confirmation: bool = True) -> dict:
    """changes = {"email": (old, new), "phone": (old, new)} - only what really changed.

    Everything that depended on the OLD contact is cut, in one place:
      * codes already sent to the old contact die (a code sent minutes before the edit would
        otherwise still open the claim page);
      * the claim link is replaced (links already sent to the old address stop working);
      * the old WhatsApp number is unlinked from this claim, so the bot does not keep treating
        whoever holds it as this claim's complainant;
      * the change is written on the claim's timeline, masked, old -> new;
      * a confirmation goes to the NEW contact at once.
    """
    out = {"changed": [], "confirm": {}}
    if not changes:
        return out
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.execute("UPDATE nidaan_claim_verify SET consumed=1 "
                            "WHERE claim_id=? AND consumed=0", (int(claim_id),))
            if "phone" in changes:
                old = norm("phone", changes["phone"][0])
                if old:
                    await c.execute(
                        "UPDATE nidaan_wa_contacts SET claim_id=NULL WHERE claim_id=? "
                        "AND substr(msisdn, -10)=?", (int(claim_id), old))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("claim %s: could not cut the old contact: %s", claim_id, e)
    try:
        import biz_nidaan_claimant as _cl
        await _cl.rotate_token(claim_id)
    except Exception as e:  # noqa: BLE001
        logger.info("claim %s: could not replace the claim link: %s", claim_id, e)
    try:
        import biz_nidaan as _n
        for kind, (old, new) in changes.items():
            await _n.record_claim_activity(
                claim_id, "contact_change", channel="web", actor=actor or "staff",
                summary="Complainant %s changed: %s → %s (unverified until confirmed)"
                        % ("email" if kind == "email" else "mobile", mask(kind, old), mask(kind, new)))
            out["changed"].append(kind)
    except Exception as e:  # noqa: BLE001
        logger.warning("claim %s: could not write the contact change: %s", claim_id, e)
    if send_confirmation:
        for kind, (_old, new) in changes.items():
            if norm(kind, new):
                out["confirm"][kind] = await send_confirm(claim_id, kind, actor=actor)
    return out


# ── confirming a contact ─────────────────────────────────────────────────────
async def send_confirm(claim_id: int, kind: str, *, actor: str = "staff", base_url: str = "") -> dict:
    """Send a confirmation to the claim's CURRENT contact: a code on WhatsApp for a phone (they
    reply it in the chat), a link by email for an email. At most 3 a day per contact."""
    claim = await _claim(claim_id)
    if not claim or kind not in KINDS:
        return {"ok": False, "why": "no such claim"}
    value = current(claim)[kind]
    if not value:
        return {"ok": False, "why": "there is no %s on this claim" % kind}
    st = (await status(claim)).get(kind) or {}
    if st.get("verified"):
        return {"ok": True, "already": True}
    since = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(_db()) as c:
        n = (await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_contact_confirm WHERE claim_id=? AND kind=? AND sent_at > ?",
            (int(claim_id), kind, since))).fetchone())[0]
    if n >= CONFIRM_MAX_PER_DAY:
        return {"ok": False, "why": "3 confirmations were already sent today"}
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
    token = secrets.token_urlsafe(24)
    exp = (datetime.utcnow() + timedelta(hours=CONFIRM_TTL_H)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(_db()) as c:
        # One live confirmation per claim and contact: a new one retires the old.
        await c.execute("UPDATE nidaan_contact_confirm SET used_at='superseded' WHERE claim_id=? "
                        "AND kind=? AND used_at IS NULL", (int(claim_id), kind))
        await c.execute(
            "INSERT INTO nidaan_contact_confirm (claim_id, kind, value, code_hash, token_hash, "
            "expires_at, sent_by) VALUES (?,?,?,?,?,?,?)",
            (int(claim_id), kind, value, _hash(code), _hash(token), exp, (actor or "")[:80]))
        await c.commit()
    sent = await (_send_phone(claim, value, code) if kind == "phone"
                  else _send_email(claim, value, token, base_url, code))
    try:
        import biz_nidaan as _n
        await _n.record_claim_activity(
            claim_id, "contact_confirm_sent", channel="whatsapp" if kind == "phone" else "email",
            actor=actor or "system",
            summary="Confirmation sent to %s %s%s" % (
                "mobile" if kind == "phone" else "email", mask(kind, value),
                "" if sent.get("ok") else " - NOT delivered: %s" % (sent.get("why") or "failed")))
    except Exception:  # noqa: BLE001
        pass
    return sent


async def _send_phone(claim: dict, value: str, code: str) -> dict:
    """The approved authentication template (np_login_code) - it reaches a number cold."""
    try:
        import biz_nidaan_claim_access as _acc
        r = await _acc._send("whatsapp", value, code, claim, "hinglish")
        return {"ok": bool(r.get("ok")), "why": str(r.get("error") or "")[:120]}
    except Exception as e:  # noqa: BLE001
        logger.warning("phone confirmation send failed: %s", e)
        return {"ok": False, "why": "send failed"}


async def _send_email(claim: dict, value: str, token: str, base_url: str, code: str = "") -> dict:
    try:
        import biz_email as _email
        base = (base_url or os.getenv("NIDAAN_BASE_URL") or "https://nidaanpartner.com").rstrip("/")
        link = "%s/nidaan/confirm-email?t=%s" % (base, token)
        name = ((claim.get("complainant_name") or claim.get("insured_name") or "").strip()
                .split(" ") or [""])[0].title()
        html = ("<div style='font-family:Arial,sans-serif;font-size:15px;line-height:1.6'>"
                "<p>Namaste %s,</p><p>Please confirm this is your email for your claim "
                "<b>NP-%s</b> with NidaanPartner. We will send your case updates here.</p>"
                "<p><a href='%s' style='background:#0B6E53;color:#fff;padding:10px 16px;"
                "border-radius:8px;text-decoration:none'>Yes, this is my email</a></p>"
                "<p>Or type this code on your claim page: <b style='font-size:20px;"
                "letter-spacing:.15em'>%s</b></p>"
                "<p>कृपया पुष्टि करें कि यह आपका ईमेल है — ऊपर वाला बटन दबाइए, या यह कोड अपने "
                "क्लेम पेज पर डालिए।</p>"
                "<p style='color:#666;font-size:13px'>We will never ask you for this code on a call "
                "or on WhatsApp. If this is not you, ignore this email. It works for 3 days.</p>"
                "</div>") % (name or "", claim.get("claim_id"), link, code or "")
        r = await _email.send_email(to_email=value,
                                    subject="Please confirm your email - claim NP-%s"
                                            % claim.get("claim_id"),
                                    html_body=html, from_name="Nidaan Partner")
        # send_email returns a bool OR a dict; bool(dict) is True even for {"ok": False} - the
        # silent-success shape this codebase has been burned by. Read the outcome.
        ok = bool(r.get("ok")) if isinstance(r, dict) else bool(r)
        return {"ok": ok, "why": "" if ok else "email not sent"}
    except Exception as e:  # noqa: BLE001
        logger.warning("email confirmation send failed: %s", e)
        return {"ok": False, "why": "send failed"}


async def confirm_link(token: str) -> dict:
    """The emailed link was clicked. Proves the email - if it is still the claim's email."""
    t = (token or "").strip()
    if not t or len(t) > 80:
        return {"ok": False}
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(_db()) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT * FROM nidaan_contact_confirm WHERE token_hash=? AND kind='email'",
            (_hash(t),))).fetchone()
        if not r:
            return {"ok": False}
        r = dict(r)
        if r.get("used_at") and r["used_at"] != "superseded":
            return {"ok": True, "already": True, "claim_id": r["claim_id"]}
        if r.get("used_at") == "superseded" or str(r["expires_at"]) < now:
            return {"ok": False, "expired": True}
        await c.execute("UPDATE nidaan_contact_confirm SET used_at=? WHERE cid=?", (now, r["cid"]))
        await c.commit()
    claim = await _claim(r["claim_id"])
    if current(claim).get("email") != r["value"]:
        return {"ok": False, "changed": True}    # the claim's email changed since: proves nothing now
    await record("email", r["value"], "email_link", claim_id=r["claim_id"], actor="complainant")
    await _note(r["claim_id"], "email", r["value"], "email_link")
    return {"ok": True, "claim_id": r["claim_id"]}


async def confirm_email_code(claim_id: int, code: str) -> dict:
    """The emailed code, typed on the claim page. Proves the email - if still the claim's."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != CODE_DIGITS:
        return {"ok": False, "why": "Enter the 6-digit code from the email."}
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(_db()) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT * FROM nidaan_contact_confirm WHERE claim_id=? AND kind='email' AND "
            "used_at IS NULL AND expires_at > ? ORDER BY cid DESC LIMIT 1",
            (int(claim_id), now))).fetchone()
        if not r:
            return {"ok": False, "why": "Ask for a code first."}
        r = dict(r)
        if int(r.get("attempts") or 0) >= 5:
            return {"ok": False, "why": "Too many wrong tries. Ask for a new code."}
        if not hmac.compare_digest(r["code_hash"], _hash(code)):
            await c.execute("UPDATE nidaan_contact_confirm SET attempts=attempts+1 WHERE cid=?",
                            (r["cid"],))
            await c.commit()
            return {"ok": False, "why": "That code is not right."}
        await c.execute("UPDATE nidaan_contact_confirm SET used_at=? WHERE cid=?", (now, r["cid"]))
        await c.commit()
    if current(await _claim(claim_id)).get("email") != r["value"]:
        return {"ok": False, "why": "Your email changed since the code was sent. Ask for a new one."}
    await record("email", r["value"], "portal_email_code", claim_id=claim_id, actor="complainant")
    await _note(claim_id, "email", r["value"], "portal_email_code")
    return {"ok": True}


async def tell_handler(claim_id: int, subject: str, body: str) -> None:
    """The person handling the claim hears it (bell + Telegram); with nobody assigned, whoever is
    on duty, then the admins. Never allowed to fail the action that caused it."""
    try:
        import biz_nidaan as _n
        import biz_nidaan_notifications as _nn
        async with aiosqlite.connect(_db()) as c:
            r = await (await c.execute(
                "SELECT assigned_to_staff_id, pipeline_stage FROM nidaan_claims WHERE claim_id=?",
                (int(claim_id),))).fetchone()
        ids = [r[0]] if r and r[0] else []
        if not ids and r and r[1]:
            try:
                ids = list(await _n.on_duty_rep_ids(r[1]))
            except Exception:  # noqa: BLE001
                ids = []
        if not ids:
            ids = [a["staff_id"] for a in await _nn._super_admin_staff()]
        if ids:
            await _nn.notify_staff_inapp(ids, subject, body, event_key="claim.contact_changed",
                                         email=False, claim_id=claim_id)
    except Exception as e:  # noqa: BLE001
        logger.info("contact notice failed for claim %s: %s", claim_id, e)


async def confirm_whatsapp_reply(msisdn: str, text: str) -> Optional[int]:
    """A code replied in the WhatsApp chat. Returns the claim id it confirmed, or None."""
    code = "".join(ch for ch in (text or "") if ch.isdigit())
    phone = norm("phone", msisdn)
    if len(code) != CODE_DIGITS or not phone or len((text or "").strip()) > 20:
        return None
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(_db()) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT * FROM nidaan_contact_confirm WHERE kind='phone' AND value=? AND "
            "used_at IS NULL AND expires_at > ? ORDER BY cid DESC LIMIT 1", (phone, now))).fetchone()
        if not r:
            return None
        r = dict(r)
        if int(r.get("attempts") or 0) >= 5:
            return None
        if not hmac.compare_digest(r["code_hash"], _hash(code)):
            await c.execute("UPDATE nidaan_contact_confirm SET attempts=attempts+1 WHERE cid=?",
                            (r["cid"],))
            await c.commit()
            return None
        await c.execute("UPDATE nidaan_contact_confirm SET used_at=? WHERE cid=?", (now, r["cid"]))
        await c.commit()
    await record("phone", phone, "whatsapp_reply_code", claim_id=r["claim_id"], actor="complainant")
    await _note(r["claim_id"], "phone", phone, "whatsapp_reply_code")
    return int(r["claim_id"])


async def note_inbound(msisdn: str) -> int:
    """A message ARRIVED from this number on WhatsApp: that proves the number (WhatsApp ties it
    to the SIM). Recorded for every open claim whose CURRENT mobile it is. Returns how many."""
    phone = norm("phone", msisdn)
    if not phone:
        return 0
    n = 0
    try:
        async with aiosqlite.connect(_db()) as c:
            rows = await (await c.execute(
                "SELECT claim_id FROM nidaan_claims WHERE COALESCE(archived,0)=0 AND "
                "substr(COALESCE(NULLIF(complainant_phone,''), insured_phone, ''), -10)=?",
                (phone,))).fetchall()
        for (cid,) in rows:
            st = (await status(await _claim(cid))).get("phone") or {}
            if not st.get("verified"):
                if await record("phone", phone, "whatsapp_message", claim_id=cid,
                                actor="complainant"):
                    await _note(cid, "phone", phone, "whatsapp_message")
                    n += 1
    except Exception as e:  # noqa: BLE001 - never allowed to break the inbox
        logger.info("inbound number proof failed: %s", e)
    return n


async def _note(claim_id: int, kind: str, value: str, method: str) -> None:
    try:
        import biz_nidaan as _n
        await _n.record_claim_activity(
            claim_id, "contact_verified", channel="system", actor="complainant",
            summary="Complainant %s %s confirmed - %s" % (
                "email" if kind == "email" else "mobile", mask(kind, value),
                METHOD_WORDS.get(method, method)))
    except Exception:  # noqa: BLE001
        pass


# ── the daily nudge to the people handling the claims ────────────────────────
NUDGE_KEY = "contact_nudge_last"
NUDGE_ACTIVE_DAYS = 30        # only claims that moved in the last 30 days
NUDGE_MAX_LINES = 15


async def nudge_unverified(today: str = "") -> dict:
    """Once a day: each handler gets ONE Telegram / bell message listing their active claims whose
    email or mobile is still not proven. Founder, 1 Oct: flag things at the right time and tell the
    people involved - a human asks the complainant, the system makes sure it is not forgotten.

    Skips a contact a confirmation went to in the last day (it is on its way), closed and archived
    claims, and claims that have not moved for 30 days. Claims nobody is assigned go to the admins.
    """
    import biz_nidaan as _n
    import biz_nidaan_notifications as _nn
    day = today or datetime.utcnow().strftime("%Y-%m-%d")
    if str(await _n.get_ops_setting(NUDGE_KEY, "") or "") == day:
        return {"skipped": "already sent today"}
    since = (datetime.utcnow() - timedelta(days=NUDGE_ACTIVE_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    recent = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(_db()) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, account_id, assigned_to_staff_id, complainant_email, insured_email, "
            "complainant_phone, insured_phone, complainant_name, insured_name FROM nidaan_claims "
            "WHERE COALESCE(archived,0)=0 AND COALESCE(status,'') NOT IN "
            "('closed','withdrawn','resolved_won','resolved_lost') "
            "AND COALESCE(last_status_at, created_at) >= ? ORDER BY claim_id", (since,))).fetchall()]
        sent_recently = {(r[0], r[1]) for r in await (await c.execute(
            "SELECT claim_id, kind FROM nidaan_contact_confirm WHERE sent_at >= ?",
            (recent,))).fetchall()}
    by_handler: dict = {}
    for r in rows:
        st = await status(r)
        missing = [k for k in KINDS if st[k]["present"] and not st[k]["verified"]
                   and (r["claim_id"], k) not in sent_recently]
        if not missing:
            continue
        who = (r.get("complainant_name") or r.get("insured_name") or "").strip()
        line = "NP-%s %s \u2014 %s not confirmed" % (
            r["claim_id"], who[:30], " and ".join("email" if k == "email" else "mobile"
                                                    for k in missing))
        by_handler.setdefault(r.get("assigned_to_staff_id") or 0, []).append(line)
    admins = [a["staff_id"] for a in await _nn._super_admin_staff()]
    told = 0
    for sid, lines in by_handler.items():
        ids = [sid] if sid else admins
        if not ids:
            continue
        more = len(lines) - NUDGE_MAX_LINES
        body = ("Please ask these complainants to confirm (or correct) their contact - open the "
                "claim and press Send confirmation:\n\n" + "\n".join(lines[:NUDGE_MAX_LINES])
                + ("\n\n...and %d more." % more if more > 0 else ""))
        await _nn.notify_staff_inapp(
            ids, "\U0001f4c7 %d claim(s) with an unconfirmed email or mobile" % len(lines),
            body, event_key="contact.unverified", email=False)
        told += 1
    await _n.set_ops_setting(NUDGE_KEY, day)
    return {"handlers": told, "claims": sum(len(v) for v in by_handler.values())}


# ── the one-time carry-over of the old yes/no flag ───────────────────────────
async def carry_over_legacy() -> dict:
    """Turn the old flag into proofs - ONLY what it really proved. Adds rows; removes nothing.

    WhatsApp code -> the PHONE was proven (not the email). Email code -> the email. Before codes
    existed (link era) -> opening the emailed link proved the email. And nothing carries if the
    claim's details were edited after the proof: the address may not be the one proven.
    """
    done = {"email": 0, "phone": 0, "skipped_edited": 0}
    async with aiosqlite.connect(_db()) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, account_id, complainant_email, insured_email, complainant_phone, "
            "insured_phone, insured_email_verified_at FROM nidaan_claims "
            "WHERE insured_email_verified=1")).fetchall()]
        for r in rows:
            cid = r["claim_id"]
            last = await (await c.execute(
                "SELECT summary, created_at FROM nidaan_claim_activity WHERE claim_id=? AND "
                "kind='portal_open' ORDER BY act_id DESC LIMIT 1", (cid,))).fetchone()
            proved_at = str((last["created_at"] if last else r["insured_email_verified_at"]) or "")
            edited = await (await c.execute(
                "SELECT 1 FROM nidaan_audit_log WHERE action='claim.info_edit' AND target_id=? "
                "AND created_at > ? LIMIT 1", (str(cid), proved_at))).fetchone()
            summ = (last["summary"] if last else "") or ""
            cur = current(r)
            if edited:
                done["skipped_edited"] += 1
                continue
            if "by whatsapp" in summ:
                if await record("phone", cur["phone"], "portal_whatsapp_code", claim_id=cid,
                                actor="carried over"):
                    done["phone"] += 1
            elif "by email" in summ:
                if await record("email", cur["email"], "portal_email_code", claim_id=cid,
                                actor="carried over"):
                    done["email"] += 1
            else:
                if await record("email", cur["email"], "legacy_email_link", claim_id=cid,
                                actor="carried over"):
                    done["email"] += 1
    return done
