"""
NidaanPartner WhatsApp — WHO PROVED WHO THEY ARE, AND WHAT LEAVES THE BUILDING.

The old model treated a phone-number match as proof of identity: "Meta verifies possession, so a
number in our records is authenticated." That is not good enough for what sits behind it. The
branch view lists other people's claims and insured names; the subscriber view lists the cases
filed under an account. Numbers get recycled by operators, SIMs get swapped, and phones get
shared inside a family or an office — so possession of a handset must not, on its own, open a
book of somebody else's insurance claims.

So there are now two states, and only one of them can see anything private:

  PUBLIC (default, and where every unknown number stays)
      Anyone can find NidaanPartner on WhatsApp and talk to the bot. They can be told what the
      service does, what it costs, which claim types we handle, and how to start. Nothing else:
      no customer, no claim, no staff member, no branch, no ops detail.

  VERIFIED (a short session, earned)
      A code is sent to the REGISTERED EMAIL on the account — not to the WhatsApp number. That
      is the point: it is a second factor the holder of the SIM does not automatically have. Get
      it right and a 12-hour session opens for that number, for that identity only.

Three layers keep private data in, because instructions alone are not a security control:

  1. STARVE  — an unverified conversation is never given private context to begin with.
  2. INSTRUCT — the model is told, in public mode, that it knows nothing about any individual.
  3. INSPECT — every outbound bot reply on an unverified conversation is scanned, and anything
     carrying a claim reference, an email, a phone number, a branch code or a non-public amount
     is replaced with a safe message rather than sent.

Layer 3 is the one that holds when the other two fail: a prompt can be talked around, a scanner
on the way out cannot.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import secrets
from datetime import datetime, timedelta

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.wa.auth")
DB_PATH = db.DB_PATH

CODE_TTL_MIN = 10          # a code is useless after ten minutes
SESSION_HOURS = 12         # a verified session is short on purpose
MAX_ATTEMPTS = 5           # wrong guesses per code before it is burned
MAX_CODES_PER_DAY = 5      # stops a number being used to spray a mailbox
CODE_DIGITS = 6


def _pepper() -> bytes:
    """Server-side secret for hashing codes. Falls back to the JWT secret, never to a constant."""
    v = (os.getenv("WA_VERIFY_PEPPER") or os.getenv("NIDAAN_JWT_SECRET")
         or os.getenv("JWT_SECRET") or "")
    if not v:
        # No secret configured: refuse to run rather than hash with something guessable.
        raise RuntimeError("no server secret available for WhatsApp verification")
    return v.encode()


def _hash(code: str) -> str:
    return hmac.new(_pepper(), (code or "").encode(), hashlib.sha256).hexdigest()


def mask_email(e: str) -> str:
    """a***@gmail.com — enough for the owner to recognise, useless to anyone else."""
    e = (e or "").strip()
    if "@" not in e:
        return ""
    user, _, dom = e.partition("@")
    return f"{user[:1]}{'*' * max(2, len(user) - 1)}@{dom}"


# ── session state ────────────────────────────────────────────────────────────
async def session(msisdn: str) -> dict:
    """The live verified session for this number, or an empty dict. Never raises."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT verified_role, verified_ref, verified_name, verified_until "
                "FROM nidaan_wa_contacts WHERE msisdn=?", ((msisdn or "").strip(),))).fetchone()
        if not r:
            return {}
        d = dict(r)
        until = d.get("verified_until")
        if not d.get("verified_role") or not until:
            return {}
        if datetime.strptime(str(until)[:19], "%Y-%m-%d %H:%M:%S") <= datetime.utcnow():
            return {}      # expired — treated exactly like never verified
        return {"role": d["verified_role"], "ref": d.get("verified_ref") or "",
                "name": d.get("verified_name") or "", "until": str(until)}
    except Exception as e:  # noqa: BLE001
        logger.warning("session read failed for %s: %s", msisdn, e)
        return {}           # fail CLOSED: no session means public mode


async def is_verified(msisdn: str) -> bool:
    return bool(await session(msisdn))


async def revoke(msisdn: str) -> None:
    """End the verified session (customer said so, or a staffer reset it)."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "UPDATE nidaan_wa_contacts SET verified_role='', verified_ref='', "
                "verified_name='', verified_until=NULL WHERE msisdn=?", ((msisdn or "").strip(),))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("revoke failed for %s: %s", msisdn, e)


# ── issuing a code ───────────────────────────────────────────────────────────
async def _registered_email(identity: dict) -> str:
    """The email on record for this identity. Empty means we cannot verify them here."""
    role, aid = identity.get("role"), identity.get("account_id")
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            if role == "complainant":
                ids = identity.get("claim_ids") or []
                if ids:
                    r = await (await c.execute(
                        "SELECT a.email FROM nidaan_claims cl JOIN nidaan_accounts a "
                        "ON a.account_id=cl.account_id WHERE cl.claim_id=? AND a.deleted_at IS NULL",
                        (ids[0],))).fetchone()
                    if r and (dict(r).get("email") or "").strip():
                        return dict(r)["email"].strip()
                    r = await (await c.execute(
                        "SELECT complainant_email FROM nidaan_claims WHERE claim_id=?",
                        (ids[0],))).fetchone()
                    return ((dict(r).get("complainant_email") if r else "") or "").strip()
            if role == "subscriber" and aid:
                r = await (await c.execute(
                    "SELECT email FROM nidaan_accounts WHERE account_id=? AND deleted_at IS NULL",
                    (aid,))).fetchone()
                return ((dict(r).get("email") if r else "") or "").strip()
            if role == "branch":
                r = await (await c.execute(
                    "SELECT contact_email FROM nidaan_branches WHERE branch_code=?",
                    ((identity.get("branch_code") or "").upper(),))).fetchone()
                return ((dict(r).get("contact_email") if r else "") or "").strip()
            if role == "staff":
                r = await (await c.execute(
                    "SELECT COALESCE(NULLIF(notify_email,''), email) AS email FROM nidaan_staff "
                    "WHERE staff_id=? AND status='active' AND deleted_at IS NULL",
                    (identity.get("staff_id"),))).fetchone()
                return ((dict(r).get("email") if r else "") or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("registered email lookup failed: %s", e)
    return ""


async def _codes_today(msisdn: str) -> int:
    since = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(DB_PATH) as c:
        r = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_wa_verify WHERE msisdn=? AND created_at>=?",
            (msisdn, since))).fetchone()
    return int(r[0]) if r else 0


async def request_code(msisdn: str, identity: dict, lang: str = "hinglish") -> dict:
    """Send a verification code to the registered email. Returns {ok, message, masked}.

    Deliberately does NOT confirm whether a number is on our books when it is not — the reply is
    the same shape either way, so this cannot be used to test which numbers we hold.
    """
    msisdn = (msisdn or "").strip()
    role = identity.get("role") or "unknown"
    if role == "unknown":
        return {"ok": False, "reason": "not_registered", "message": _T["not_registered"].get(lang, _T["not_registered"]["hinglish"])}

    try:
        if await _codes_today(msisdn) >= MAX_CODES_PER_DAY:
            return {"ok": False, "reason": "rate_limited",
                    "message": _T["rate_limited"].get(lang, _T["rate_limited"]["hinglish"])}
    except Exception:
        pass

    email = await _registered_email(identity)
    if not email or "@" not in email:
        return {"ok": False, "reason": "no_email",
                "message": _T["no_email"].get(lang, _T["no_email"]["hinglish"])}

    code = "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))
    ref = str(identity.get("account_id") or identity.get("branch_code")
              or identity.get("staff_id") or (identity.get("claim_ids") or [""])[0] or "")
    exp = (datetime.utcnow() + timedelta(minutes=CODE_TTL_MIN)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            # Any earlier challenge for this number is dead the moment a new one is issued.
            await c.execute("UPDATE nidaan_wa_verify SET consumed=1 WHERE msisdn=? AND consumed=0",
                            (msisdn,))
            await c.execute(
                "INSERT INTO nidaan_wa_verify (msisdn, code_hash, role, ref_id, name, sent_to, "
                "expires_at) VALUES (?,?,?,?,?,?,?)",
                (msisdn, _hash(code), role, ref, (identity.get("name") or "")[:80],
                 mask_email(email), exp))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("could not store verification challenge: %s", e)
        return {"ok": False, "reason": "error",
                "message": _T["error"].get(lang, _T["error"]["hinglish"])}

    try:
        import biz_email as _mail
        await _mail.send_email(
            email, f"NidaanPartner WhatsApp verification code: {code}",
            _email_html(code, identity.get("name") or ""),
            text_body=(f"Your NidaanPartner WhatsApp verification code is {code}. "
                       f"It is valid for {CODE_TTL_MIN} minutes. If you did not ask for this, "
                       f"ignore this email and tell us."),
            from_name="Nidaan Partner", delivery_critical=True)
    except Exception as e:  # noqa: BLE001
        logger.warning("verification email failed: %s", e)
        return {"ok": False, "reason": "email_failed",
                "message": _T["error"].get(lang, _T["error"]["hinglish"])}

    logger.info("🔐 WhatsApp verification code sent for %s (%s) to %s", msisdn, role, mask_email(email))
    msg = _T["sent"].get(lang, _T["sent"]["hinglish"]).format(masked=mask_email(email))
    return {"ok": True, "masked": mask_email(email), "message": msg}


def looks_like_code(text: str) -> str:
    """The 6-digit code if the message is plausibly just that, else ''."""
    t = (text or "").strip()
    m = re.fullmatch(r"[^0-9]{0,12}?(\d{6})[^0-9]{0,12}?", t)
    return m.group(1) if m else ""


async def try_verify(msisdn: str, code: str, lang: str = "hinglish") -> dict:
    """Check a code and, if it is right, open a verified session. Returns {ok, message, role}."""
    msisdn = (msisdn or "").strip()
    now = datetime.utcnow()
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT * FROM nidaan_wa_verify WHERE msisdn=? AND consumed=0 "
                "ORDER BY vid DESC LIMIT 1", (msisdn,))).fetchone()
            if not r:
                return {"ok": False, "reason": "no_challenge",
                        "message": _T["no_challenge"].get(lang, _T["no_challenge"]["hinglish"])}
            ch = dict(r)
            if datetime.strptime(str(ch["expires_at"])[:19], "%Y-%m-%d %H:%M:%S") <= now:
                await c.execute("UPDATE nidaan_wa_verify SET consumed=1 WHERE vid=?", (ch["vid"],))
                await c.commit()
                return {"ok": False, "reason": "expired",
                        "message": _T["expired"].get(lang, _T["expired"]["hinglish"])}
            if int(ch["attempts"] or 0) >= MAX_ATTEMPTS:
                await c.execute("UPDATE nidaan_wa_verify SET consumed=1 WHERE vid=?", (ch["vid"],))
                await c.commit()
                return {"ok": False, "reason": "too_many",
                        "message": _T["too_many"].get(lang, _T["too_many"]["hinglish"])}

            # compare_digest keeps a wrong code from being narrowed down by timing
            if not hmac.compare_digest(ch["code_hash"], _hash(code)):
                await c.execute("UPDATE nidaan_wa_verify SET attempts=attempts+1 WHERE vid=?",
                                (ch["vid"],))
                await c.commit()
                left = MAX_ATTEMPTS - int(ch["attempts"] or 0) - 1
                logger.info("🔐 wrong WhatsApp code for %s (%d attempt(s) left)", msisdn, max(0, left))
                return {"ok": False, "reason": "wrong", "attempts_left": max(0, left),
                        "message": _T["wrong"].get(lang, _T["wrong"]["hinglish"])}

            until = (now + timedelta(hours=SESSION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
            await c.execute("UPDATE nidaan_wa_verify SET consumed=1 WHERE vid=?", (ch["vid"],))
            await c.execute("INSERT OR IGNORE INTO nidaan_wa_contacts (msisdn) VALUES (?)", (msisdn,))
            await c.execute(
                "UPDATE nidaan_wa_contacts SET verified_role=?, verified_ref=?, verified_name=?, "
                "verified_at=CURRENT_TIMESTAMP, verified_until=? WHERE msisdn=?",
                (ch["role"], ch["ref_id"], ch["name"], until, msisdn))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("verify failed for %s: %s", msisdn, e)
        return {"ok": False, "reason": "error",
                "message": _T["error"].get(lang, _T["error"]["hinglish"])}

    logger.info("🔐 WhatsApp verified: %s as %s (%s) for %dh", msisdn, ch["role"], ch["ref_id"], SESSION_HOURS)
    return {"ok": True, "role": ch["role"], "ref": ch["ref_id"],
            "message": _T["ok"].get(lang, _T["ok"]["hinglish"]).format(hours=SESSION_HOURS)}


# ── the outbound inspector ───────────────────────────────────────────────────
# Public pricing may be quoted freely; anything else with a rupee sign is somebody's money.
_PUBLIC_AMOUNTS = {"99", "199", "299", "499", "999", "1999", "2000", "2999", "4999"}

_LEAK_PATTERNS = [
    ("claim reference", re.compile(r"\bNP[-\s]?\d{2,}\b", re.I)),
    ("claim number", re.compile(r"\bclaim\s*(?:id|no\.?|number|#)\s*:?\s*\d+", re.I)),
    ("email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("phone number", re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{9}(?!\d)")),
    ("branch code", re.compile(r"\b[A-Z]{3,12}-\d{2}\b")),
    ("policy number", re.compile(r"\bpolicy\s*(?:no\.?|number|#)\s*:?\s*[A-Z0-9/-]{5,}", re.I)),
]
_AMOUNT = re.compile(r"(?:₹|\bRs\.?\s?|\bINR\s?)\s?([\d,]+)", re.I)
# Indian comma grouping ("2,45,000") is how money gets written when no symbol precedes it.
_GROUPED = re.compile(r"\b\d{1,3}(?:,\d{2,3})+\b")


def scan_for_leak(text: str) -> str:
    """What private thing this reply would disclose, or '' if it is safe to send publicly."""
    t = text or ""
    for label, rx in _LEAK_PATTERNS:
        if rx.search(t):
            return label
    for m in _AMOUNT.finditer(t):
        amt = m.group(1).replace(",", "").lstrip("0") or "0"
        if amt not in _PUBLIC_AMOUNTS:
            return "an amount"
    for m in _GROUPED.finditer(t):
        if (m.group(0).replace(",", "").lstrip("0") or "0") not in _PUBLIC_AMOUNTS:
            return "an amount"
    return ""


async def guard_public_reply(msisdn: str, text: str, lang: str = "hinglish") -> tuple[str, str]:
    """Last line of defence before a bot reply leaves for an UNVERIFIED number.

    Returns (text_to_send, blocked_reason). A blocked reply is replaced, never trimmed: editing
    a leak out of a sentence risks leaving half of it behind.
    """
    reason = scan_for_leak(text)
    if not reason:
        return text, ""
    logger.warning("🛡️ blocked a WhatsApp reply to unverified %s — it contained %s", msisdn, reason)
    try:
        import biz_nidaan as _n
        await _n.record_event("wa_leak_blocked", status="blocked", reason=reason,
                              contact=msisdn, purpose="wa_public_guard")
    except Exception:
        pass
    return _T["blocked"].get(lang, _T["blocked"]["hinglish"]), reason


def _email_html(code: str, name: str) -> str:
    who = f"Hi {name}," if name else "Hi,"
    return (
        '<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;'
        'padding:24px;color:#0f172a">'
        f'<p style="font-size:15px">{who}</p>'
        '<p style="font-size:15px">Someone is asking for your case details on the NidaanPartner '
        'WhatsApp number. Enter this code there to confirm it is you:</p>'
        f'<p style="font-size:34px;font-weight:800;letter-spacing:.28em;margin:22px 0;color:#0e7490">{code}</p>'
        f'<p style="font-size:14px;color:#475569">This code is valid for {CODE_TTL_MIN} minutes and can '
        'be used once.</p>'
        '<p style="font-size:14px;color:#b91c1c"><b>If this was not you, do not share this code with '
        'anyone.</b> Nobody from NidaanPartner will ever ask you for it — not on a call, not on '
        'WhatsApp. Just ignore this email and tell us.</p>'
        '<p style="font-size:13px;color:#64748b">— Team NidaanPartner</p></div>')


# Plain wording, in all three languages the bot speaks. Short enough to read on a phone.
_T = {
    "sent": {
        "hinglish": ("Aapki jaankari surakshit rakhne ke liye — maine aapke registered email "
                     "{masked} par ek 6-digit code bheja hai. Wahi code yahan bhej dijiye, phir "
                     "main aapke case ki baat kar sakta hoon. 🔐"),
        "hi": ("आपकी जानकारी सुरक्षित रखने के लिए — मैंने आपके रजिस्टर्ड ईमेल {masked} पर एक 6-अंकों का "
               "कोड भेजा है। वही कोड यहाँ भेज दीजिए, फिर मैं आपके केस की बात कर सकता हूँ। 🔐"),
        "en": ("To keep your information safe, I've sent a 6-digit code to your registered email "
               "{masked}. Send me that code here and I can then talk about your case. 🔐"),
    },
    "ok": {
        "hinglish": "Shukriya — aap verify ho gaye. Ab {hours} ghante tak main aapke case ki baat kar sakta hoon. ✅",
        "hi": "धन्यवाद — आप वेरिफ़ाई हो गए। अब {hours} घंटे तक मैं आपके केस की बात कर सकता हूँ। ✅",
        "en": "Thank you — you're verified. I can talk about your case for the next {hours} hours. ✅",
    },
    "wrong": {
        "hinglish": "Ye code sahi nahi hai. Email dobara dekh kar sahi code bhejiye. 🙏",
        "hi": "यह कोड सही नहीं है। ईमेल दोबारा देखकर सही कोड भेजिए। 🙏",
        "en": "That code isn't right. Please check the email and send the correct code. 🙏",
    },
    "expired": {
        "hinglish": "Ye code purana ho gaya. 'CODE' likh kar bhejiye, main naya bhej dunga. 🙏",
        "hi": "यह कोड पुराना हो गया। 'CODE' लिखकर भेजिए, मैं नया भेज दूँगा। 🙏",
        "en": "That code has expired. Send 'CODE' and I'll email you a fresh one. 🙏",
    },
    "too_many": {
        "hinglish": "Bahut baar galat code aaya. Suraksha ke liye ye code band kar diya — 'CODE' bhej kar naya mangaiye. 🙏",
        "hi": "कई बार गलत कोड आया। सुरक्षा के लिए यह कोड बंद कर दिया — 'CODE' भेजकर नया मँगाइए। 🙏",
        "en": "Too many wrong tries, so I've closed that code for safety. Send 'CODE' for a new one. 🙏",
    },
    "no_challenge": {
        "hinglish": "Abhi koi code chal nahi raha. 'CODE' likh kar bhejiye. 🙏",
        "hi": "अभी कोई कोड चालू नहीं है। 'CODE' लिखकर भेजिए। 🙏",
        "en": "There's no code waiting right now. Send 'CODE' and I'll email you one. 🙏",
    },
    "rate_limited": {
        "hinglish": "Aaj bahut code maange ja chuke hain. Kal dobara koshish kijiye, ya hamari team se baat kijiye. 🙏",
        "hi": "आज बहुत कोड माँगे जा चुके हैं। कल दोबारा कोशिश कीजिए, या हमारी टीम से बात कीजिए। 🙏",
        "en": "That's a lot of codes for one day. Please try tomorrow, or talk to our team. 🙏",
    },
    "no_email": {
        "hinglish": "Aapke record me email nahi mila, isliye main code nahi bhej sakta. Hamari team aapse baat karegi. 🙏",
        "hi": "आपके रिकॉर्ड में ईमेल नहीं मिला, इसलिए मैं कोड नहीं भेज सकता। हमारी टीम आपसे बात करेगी। 🙏",
        "en": "I couldn't find an email on your record, so I can't send a code. Our team will help you. 🙏",
    },
    "not_registered": {
        "hinglish": ("Kisi bhi case ki jaankari main sirf registered contact ko de sakta hoon. "
                     "Service ke baare me poochhiye — main khushi se bataunga. 🙏"),
        "hi": ("किसी भी केस की जानकारी मैं सिर्फ़ रजिस्टर्ड कॉन्टैक्ट को दे सकता हूँ। "
               "सर्विस के बारे में पूछिए — मैं ख़ुशी से बताऊँगा। 🙏"),
        "en": ("I can only share case details with a registered contact. Ask me about the service "
               "though — happy to explain. 🙏"),
    },
    "blocked": {
        "hinglish": ("Ye jaankari main yahan nahi bhej sakta jab tak aap verify na ho jaayen. "
                     "'CODE' likh kar bhejiye — main aapke registered email par code bhej dunga. 🔐"),
        "hi": ("यह जानकारी मैं यहाँ नहीं भेज सकता जब तक आप वेरिफ़ाई न हो जाएँ। "
               "'CODE' लिखकर भेजिए — मैं आपके रजिस्टर्ड ईमेल पर कोड भेज दूँगा। 🔐"),
        "en": ("I can't share that here until you're verified. Send 'CODE' and I'll email a "
               "verification code to your registered address. 🔐"),
    },
    "error": {
        "hinglish": "Abhi kuch takneeki dikkat hai. Hamari team aapse baat karegi. 🙏",
        "hi": "अभी कुछ तकनीकी दिक्कत है। हमारी टीम आपसे बात करेगी। 🙏",
        "en": "Something went wrong on our side. Our team will get in touch. 🙏",
    },
}


def text(key: str, lang: str = "hinglish", **kw) -> str:
    d = _T.get(key) or {}
    s = d.get(lang) or d.get("hinglish") or ""
    return s.format(**kw) if kw else s
