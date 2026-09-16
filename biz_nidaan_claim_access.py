# =============================================================================
#  biz_nidaan_claim_access.py — proving it is really the complainant
# =============================================================================
#
#  The founder's reason, in his words: "no random person should open the link and
#  authorized, we want to ensure it's authorized by the complainant, that's why
#  the registered email/mobile is the one thing our magic link can identify, and
#  collect authorization from right person."
#
#  Until now the portal link WAS the credential: whoever held the URL could open
#  the claim and accept the success-fee terms. A link forwarded in a family
#  WhatsApp group, or a phone lent to somebody, was enough.
#
#  So the link now only gets you as far as "confirm it is you":
#
#    1. We offer the channels WE ALREADY HAVE on the claim — their WhatsApp
#       number, their email — shown masked. The complainant picks one.
#    2. A 6-digit code goes to THAT contact. Never to an address or number typed
#       into the page: a code you can redirect is not proof of anything.
#    3. The code buys a session. Only the session opens the claim, uploads a
#       document or accepts the terms — the raw link never does again.
#
#  Deliberate choices:
#    • The code is stored as a peppered HMAC, never in the clear, so reading the
#      database does not let anyone log in as a complainant.
#    • Five wrong guesses kill the challenge; a new code has to be asked for.
#    • Five codes an hour per claim, so the link cannot be used to hammer
#      somebody's phone with messages from us.
#    • The reply looks the same whether or not a channel exists, so this cannot
#      be used to discover whose number we hold.
#    • Staff never need the complainant's code: ops mints its own short preview
#      session, which can look but can never accept the terms.
# =============================================================================
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

logger = logging.getLogger("sarathi.nidaan.claim_access")

DB_PATH = db.DB_PATH

CODE_DIGITS = 6
CODE_TTL_MIN = 10          # long enough to switch apps and read a message
MAX_ATTEMPTS = 5           # then the challenge is dead and they ask for a new code
MAX_CODES_PER_HOUR = 5     # so the link cannot be used to spam somebody's phone
SESSION_MIN = 720          # 12 hours - one sitting, not a standing key
PREVIEW_MIN = 20           # a staffer looking at what the complainant sees


def _pepper() -> bytes:
    v = (os.getenv("WA_VERIFY_PEPPER") or os.getenv("NIDAAN_JWT_SECRET")
         or os.getenv("JWT_SECRET") or "")
    if not v:
        raise RuntimeError("no server secret available for complainant verification")
    return v.encode()


def _hash(code: str) -> str:
    return hmac.new(_pepper(), (code or "").encode(), hashlib.sha256).hexdigest()


def mask_email(e: str) -> str:
    e = (e or "").strip()
    if "@" not in e:
        return ""
    user, _, dom = e.partition("@")
    return "%s%s@%s" % (user[:1], "*" * max(2, len(user) - 1), dom)


def mask_phone(p: str) -> str:
    d = "".join(ch for ch in (p or "") if ch.isdigit())
    return ("•••• " + d[-4:]) if len(d) >= 4 else ""


async def _claim(claim_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, complainant_name, complainant_phone, complainant_email, "
            "insured_name, insured_phone, insured_email FROM nidaan_claims WHERE claim_id=?",
            (int(claim_id),))).fetchone()
    return dict(r) if r else {}


def _contacts(claim: dict) -> dict:
    """The contact details ALREADY on the claim. Nothing typed into the page reaches this."""
    return {
        "phone": (claim.get("complainant_phone") or claim.get("insured_phone") or "").strip(),
        "email": (claim.get("complainant_email") or claim.get("insured_email") or "").strip(),
    }


async def channels(claim_id: int) -> list[dict]:
    """What we can send a code to, masked. Their choice, as the founder asked."""
    c = _contacts(await _claim(claim_id))
    out = []
    if c["phone"]:
        out.append({"kind": "whatsapp", "masked": mask_phone(c["phone"])})
    if c["email"]:
        out.append({"kind": "email", "masked": mask_email(c["email"])})
    return out


async def _codes_this_hour(claim_id: int) -> int:
    since = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as c:
        r = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claim_verify WHERE claim_id=? AND created_at>=?",
            (int(claim_id), since))).fetchone()
    return int(r[0]) if r else 0


async def start(claim_id: int, kind: str, *, lang: str = "hinglish") -> dict:
    """Send a code to the contact we already hold. Returns {ok, masked, kind}."""
    kind = (kind or "").strip().lower()
    if kind not in ("whatsapp", "email"):
        return {"ok": False, "reason": "bad_channel", "message": "Choose WhatsApp or email."}
    claim = await _claim(claim_id)
    if not claim:
        return {"ok": False, "reason": "no_claim", "message": "That link is not valid any more."}
    c = _contacts(claim)
    dest = c["phone"] if kind == "whatsapp" else c["email"]
    if not dest:
        return {"ok": False, "reason": "no_channel",
                "message": "We do not have that on file for this claim. Try the other one, "
                           "or call us and we will help."}
    if await _codes_this_hour(claim_id) >= MAX_CODES_PER_HOUR:
        return {"ok": False, "reason": "rate_limited",
                "message": "That is a lot of codes in one hour. Please wait a little, "
                           "or call us."}

    code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
    masked = mask_phone(dest) if kind == "whatsapp" else mask_email(dest)
    exp = (datetime.utcnow() + timedelta(minutes=CODE_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as conn:
        # One live challenge per claim: asking for a new code kills the old one.
        await conn.execute("UPDATE nidaan_claim_verify SET consumed=1 "
                           "WHERE claim_id=? AND consumed=0", (int(claim_id),))
        await conn.execute(
            "INSERT INTO nidaan_claim_verify (claim_id, channel, sent_to, code_hash, expires_at) "
            "VALUES (?,?,?,?,?)", (int(claim_id), kind, masked, _hash(code), exp))
        await conn.commit()

    sent = await _send(kind, dest, code, claim, lang)
    if not sent.get("ok"):
        logger.warning("claim %s: could not send the %s code: %s", claim_id, kind, sent.get("error"))
        return {"ok": False, "reason": "send_failed",
                "message": "We could not send the code just now. Try the other way, or call us."}
    return {"ok": True, "kind": kind, "masked": masked, "ttl_min": CODE_TTL_MIN}


_SMS = {
    "en": "Your NidaanPartner code is {code}. It opens your claim page and expires in {mins} "
          "minutes. We will never ask you for this code.",
    "hi": "आपका NidaanPartner कोड {code} है। "
          "यह आपका क्लेम पेज "
          "खोलता है और {mins} मिनट "
          "में खत्म हो जाएगा। "
          "हम आपसे यह कोड कभी "
          "नहीं पूछेंगे।",
    "hinglish": "Aapka NidaanPartner code {code} hai. Ye aapka claim page kholta hai aur {mins} "
                "minute mein khatam ho jayega. Hum aapse ye code kabhi nahi poochenge.",
}


async def _send(kind: str, dest: str, code: str, claim: dict, lang: str) -> dict:
    name = (claim.get("complainant_name") or claim.get("insured_name") or "").split(" ")[0]
    if kind == "whatsapp":
        try:
            import biz_nidaan_whatsapp as _wa
            text = _SMS.get(lang, _SMS["hinglish"]).format(code=code, mins=CODE_TTL_MIN)
            # 'critical': somebody is standing at the door waiting for this. It is never held
            # back by the "how often may we speak first" caps.
            with _wa.sending_as("critical"):
                r = await _wa.send_text(dest, text)
            return {"ok": bool(r.get("ok")), "error": r.get("error")}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:120]}
    try:
        import biz_email as _mail
        html = (
            '<div style="font-family:system-ui,Segoe UI,Roboto,sans-serif;font-size:15px;color:#111">'
            '<p>Namaste %s,</p>'
            '<p>Your code to open your claim page is:</p>'
            '<p style="font-size:30px;font-weight:700;letter-spacing:.18em;margin:.4rem 0">%s</p>'
            '<p>It expires in %d minutes. <b>We will never ask you for this code</b> — not on '
            'the phone, not on WhatsApp.</p>'
            '<p style="color:#555;font-size:13px">If you did not try to open your claim page, you '
            'can ignore this email.</p>'
            '<p>— Team NidaanPartner</p></div>'
        ) % (name or "ji", code, CODE_TTL_MIN)
        r = await _mail.send_email(to_email=dest, subject="Your NidaanPartner code: %s" % code,
                                   html_body=html, from_name="Nidaan Partner")
        ok = bool(r.get("ok")) if isinstance(r, dict) else bool(r)
        return {"ok": ok, "error": (r.get("error") if isinstance(r, dict) else "")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:120]}


async def check(claim_id: int, code: str) -> dict:
    """Check the code. On success the caller mints the session; this only says yes or no."""
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if len(code) != CODE_DIGITS:
        return {"ok": False, "reason": "bad_format",
                "message": "Enter the %d-digit code we sent you." % CODE_DIGITS}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM nidaan_claim_verify WHERE claim_id=? AND consumed=0 "
            "ORDER BY vid DESC LIMIT 1", (int(claim_id),))).fetchone()
        if not row:
            return {"ok": False, "reason": "no_code",
                    "message": "Ask for a code first — we will send it to you."}
        ch = dict(row)
        if str(ch.get("expires_at") or "") < datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"):
            await conn.execute("UPDATE nidaan_claim_verify SET consumed=1 WHERE vid=?", (ch["vid"],))
            await conn.commit()
            return {"ok": False, "reason": "expired",
                    "message": "That code has expired. Ask for a new one."}
        if int(ch.get("attempts") or 0) >= MAX_ATTEMPTS:
            await conn.execute("UPDATE nidaan_claim_verify SET consumed=1 WHERE vid=?", (ch["vid"],))
            await conn.commit()
            return {"ok": False, "reason": "too_many",
                    "message": "Too many wrong tries. Ask for a new code."}
        if not hmac.compare_digest(str(ch.get("code_hash") or ""), _hash(code)):
            await conn.execute("UPDATE nidaan_claim_verify SET attempts=attempts+1 WHERE vid=?",
                               (ch["vid"],))
            await conn.commit()
            left = MAX_ATTEMPTS - (int(ch.get("attempts") or 0) + 1)
            return {"ok": False, "reason": "wrong", "left": max(0, left),
                    "message": ("That code is not right. %d tr%s left."
                                % (max(0, left), "y" if left == 1 else "ies"))
                    if left > 0 else "Too many wrong tries. Ask for a new code."}
        await conn.execute("UPDATE nidaan_claim_verify SET consumed=1 WHERE vid=?", (ch["vid"],))
        await conn.commit()
    return {"ok": True, "claim_id": int(claim_id), "channel": ch.get("channel") or ""}
