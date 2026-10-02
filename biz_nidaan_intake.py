# -*- coding: utf-8 -*-
"""ONE CLAIM INTAKE, AT EVERY DOOR (founder, 2 Oct 2026).

"the claim intake details should be almost similar at all endpoints ... basic details should be
unified at all places and other details as per the scenario."

Six doors create a claim - the subscriber dashboard, the Get-started page, the Authorized Partner
portal, My Business, Raise for a Subscriber and (on payment) the Rs 499 review. Each grew its own
rules: one asked for a single "customer" and stored that person as both patient and complainant,
two never asked for the complainant's email, four kept their own list of claim types, and the
rejection letter - the paper the whole case is built on - was checked only in the browser, so a
failed upload left a claim with nothing. This module is the rulebook all of them now pass through.

THE CORE (every door):
  1. Patient / insured - name required; mobile and email optional (checked if given).
  2. Complainant - name, mobile and email ALL required. They are who we talk to for the whole case.
  3. Insurance type - one list of the standard Indian types (TYPES).
  4. Insurance company.
  5. Disputed amount - required, Rs 1 to Rs 100 crore.
  6. Policy number - optional.
  7. Rejection letter - required. It is uploaded and virus-checked BEFORE the claim exists and
     arrives as a single-use token bound to whoever uploaded it, so a claim without the letter
     cannot be created and nobody can attach a letter somebody else uploaded.

THE ONE EXCEPTION (founder, 2 Oct): an Authorized Partner or a staff member may raise without the
letter if they give the reason. The letter is then due within LETTER_GRACE_DAYS; the raiser is
reminded every day (AP on WhatsApp / email, staff on Telegram) and on the last day the claim is
ARCHIVED - never deleted - and the raiser and super-admins are told.
"""
from __future__ import annotations

import hashlib
import logging
import re
import secrets
import unicodedata
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.intake")

# ── Insurance types: the standard Indian lines, one list for every form ─────────────────────
# (code, English, Hindi, checklist template). The template decides which documents the claim asks
# for; a type with no template of its own uses the general one. Codes already on live claims
# (health, life, motor, travel) are unchanged.
TYPES = [
    ("health", "Health / Mediclaim", "स्वास्थ्य / मेडिक्लेम", "health"),
    ("life", "Life", "जीवन बीमा", "life"),
    ("personal_accident", "Personal Accident", "व्यक्तिगत दुर्घटना", "other"),
    ("motor", "Motor (car, bike, commercial vehicle)", "मोटर (कार, बाइक, व्यावसायिक वाहन)", "motor"),
    ("travel", "Travel", "यात्रा बीमा", "travel"),
    ("home", "Home / Householder", "घर / गृह बीमा", "property"),
    ("fire", "Fire / Shop / Business property", "आग / दुकान / व्यापार संपत्ति", "property"),
    ("marine", "Marine / Goods in transit", "मरीन / माल ढुलाई", "marine"),
    ("crop", "Crop / Livestock", "फसल / पशुधन", "other"),
    ("engineering", "Engineering / Machinery", "इंजीनियरिंग / मशीनरी", "other"),
    ("liability", "Liability (public, professional, cyber)", "दायित्व (पब्लिक, प्रोफेशनल, साइबर)", "other"),
    ("other", "Other", "अन्य", "other"),
]
CODES = [t[0] for t in TYPES]
_BY_CODE = {t[0]: t for t in TYPES}
# What older forms (and people) send. Mapped, never refused, so a page cached before this change
# still files its claim under the right type.
LEGACY = {
    "general": "other", "property": "fire", "mediclaim": "health", "medical": "health",
    "vehicle": "motor", "car": "motor", "bike": "motor", "house": "home", "transit": "marine",
    "pa": "personal_accident", "accident": "personal_accident", "cyber": "liability",
}

AMOUNT_MIN = 1
AMOUNT_MAX = 1_000_000_000          # Rs 100 crore - big commercial fire claims exist
NAME_MAX = 120
INSURER_MAX = 120
POLICY_MAX = 80
REASON_MIN = 10
REASON_MAX = 300
LETTER_GRACE_DAYS = 7
LETTER_TOKEN_HOURS = 24

# Which doors may raise a claim without the letter (with a reason). Everyone else: no letter, no
# claim - "without rejection letter people do spam and dont take the process seriously".
DOORS = {
    "subscriber": False,     # subscriber dashboard and the Get-started page
    "ap": True,              # Authorized Partner portal
    "my_business": True,     # a staff member's own claims
    "on_behalf": True,       # staff raising for a subscriber - staff are accountable, as My Business
    "review": False,         # Rs 499 review
}


class IntakeError(ValueError):
    """A claim detail that is missing or wrong. Carries the field and the words in both languages
    so every door says the same thing."""

    def __init__(self, field: str, en: str, hi: str):
        super().__init__(en)
        self.field, self.en, self.hi = field, en, hi

    def message(self, lang: str = "en") -> str:
        return self.hi if (lang or "").startswith("hi") else self.en


# ── types ───────────────────────────────────────────────────────────────────────────────────
def type_code(raw) -> Optional[str]:
    t = (raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    t = LEGACY.get(t, t)
    return t if t in _BY_CODE else None


def type_label(code: str, lang: str = "en") -> str:
    t = _BY_CODE.get(type_code(code) or "")
    if not t:
        return (code or "").replace("_", " ").title()
    return t[2] if (lang or "").startswith("hi") else t[1]


def types_public() -> list:
    return [{"code": c, "en": en, "hi": hi} for c, en, hi, _ in TYPES]


def template_for(code: str) -> str:
    t = _BY_CODE.get(type_code(code) or "")
    return t[3] if t else "other"


# ── single fields ───────────────────────────────────────────────────────────────────────────
def _name(raw, field: str, who_en: str, who_hi: str, *, firm_ok: bool = False) -> str:
    v = " ".join(str(raw or "").split())
    if not v:
        raise IntakeError(field, f"Enter the {who_en}'s full name.", f"{who_hi} का पूरा नाम लिखें।")
    if len(v) > NAME_MAX:
        raise IntakeError(field, f"The {who_en}'s name is too long.", f"{who_hi} का नाम बहुत लंबा है।")
    letters = 0
    for ch in v:
        cat = unicodedata.category(ch)
        if cat.startswith("L"):
            letters += 1
        elif cat.startswith("M") or ch in " .'-" or (firm_ok and (ch.isdigit() or ch in "&/(),")):
            continue
        else:
            raise IntakeError(field, f"The {who_en}'s name can have letters only - no numbers or symbols.",
                              f"{who_hi} के नाम में सिर्फ़ अक्षर हों - अंक या चिह्न नहीं।")
    if letters < 2:
        raise IntakeError(field, f"Enter the {who_en}'s full name.", f"{who_hi} का पूरा नाम लिखें।")
    return v


def mobile(raw) -> str:
    """An Indian mobile as 10 digits, or '' when it is not one. Accepts +91, 91, 0 and spaces."""
    d = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    elif len(d) == 13 and d.startswith("091"):
        d = d[3:]
    return d if re.fullmatch(r"[6-9]\d{9}", d) else ""


_EMAIL = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def email(raw) -> str:
    v = (str(raw or "")).strip().lower()
    return v[:254] if (v and len(v) <= 254 and _EMAIL.match(v) and ".." not in v) else ""


def amount(raw) -> int:
    try:
        if isinstance(raw, str):
            raw = raw.replace(",", "").replace("₹", "").strip()
        v = int(float(raw)) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        v = 0
    if v < AMOUNT_MIN:
        raise IntakeError("disputed_amount", "Enter the disputed amount - the money the insurer did not pay.",
                          "विवादित राशि लिखें - जो पैसा बीमा कंपनी ने नहीं दिया।")
    if v > AMOUNT_MAX:
        raise IntakeError("disputed_amount", "That amount is above Rs 100 crore - please check the zeros.",
                          "यह राशि 100 करोड़ से ज़्यादा है - कृपया शून्य (0) दोबारा जाँचें।")
    return v


def _plain(raw, limit: int) -> str:
    v = " ".join(str(raw or "").split())
    return "".join(ch for ch in v if ch not in "<>\x00")[:limit]


# ── the core ────────────────────────────────────────────────────────────────────────────────
def check_core(d: dict) -> dict:
    """Every door's seven core details, checked the same way. Returns the cleaned values or raises
    IntakeError for the first thing that is wrong."""
    out = {}
    # The insured can be a firm ("M/S SHARMA TRADERS", "24 CARAT JEWELLERS") on fire, marine and
    # business claims; the complainant is always a person.
    out["insured_name"] = _name(d.get("insured_name"), "insured_name", "patient / insured", "मरीज़ / बीमित व्यक्ति",
                                firm_ok=True)
    ip = str(d.get("insured_phone") or "").strip()
    out["insured_phone"] = mobile(ip) if ip else ""
    if ip and not out["insured_phone"]:
        raise IntakeError("insured_phone", "The patient's mobile is not a valid 10-digit Indian number (or leave it blank).",
                          "मरीज़ का मोबाइल सही 10 अंकों का नंबर नहीं है (या खाली छोड़ दें)।")
    ie = str(d.get("insured_email") or "").strip()
    out["insured_email"] = email(ie) if ie else ""
    if ie and not out["insured_email"]:
        raise IntakeError("insured_email", "The patient's email does not look right (or leave it blank).",
                          "मरीज़ का ईमेल सही नहीं लग रहा (या खाली छोड़ दें)।")

    out["complainant_name"] = _name(d.get("complainant_name"), "complainant_name", "complainant", "शिकायतकर्ता")
    out["complainant_phone"] = mobile(d.get("complainant_phone"))
    if not out["complainant_phone"]:
        raise IntakeError("complainant_phone",
                          "Enter the complainant's 10-digit mobile - we use it on WhatsApp for the whole case.",
                          "शिकायतकर्ता का 10 अंकों का मोबाइल लिखें - पूरे केस में व्हाट्सऐप पर इसी से बात होगी।")
    out["complainant_email"] = email(d.get("complainant_email"))
    if not out["complainant_email"]:
        raise IntakeError("complainant_email",
                          "Enter the complainant's email - we send document requests and updates there.",
                          "शिकायतकर्ता का ईमेल लिखें - दस्तावेज़ और अपडेट वहीं भेजे जाते हैं।")

    out["claim_type"] = type_code(d.get("claim_type"))
    if not out["claim_type"]:
        raise IntakeError("claim_type", "Choose the insurance type.", "बीमा का प्रकार चुनें।")
    out["insurer_name"] = _plain(d.get("insurer_name"), INSURER_MAX)
    if len(out["insurer_name"]) < 2:
        raise IntakeError("insurer_name", "Choose the insurance company.", "बीमा कंपनी चुनें।")
    out["disputed_amount"] = amount(d.get("disputed_amount"))
    pol = " ".join(str(d.get("policy_no") or "").split())     # checked as typed - never "cleaned" into shape
    if len(pol) > POLICY_MAX or (pol and not re.fullmatch(r"[A-Za-z0-9/\-._# ]+", pol)):
        raise IntakeError("policy_no", "The policy number has characters it should not - check it, or leave it blank.",
                          "पॉलिसी नंबर में गलत चिह्न हैं - जाँचें, या खाली छोड़ दें।")
    out["policy_no"] = pol
    return out


def same_person(core: dict) -> bool:
    """The patient and the complainant are one human - same name, or the same mobile."""
    n1 = " ".join((core.get("insured_name") or "").upper().split())
    n2 = " ".join((core.get("complainant_name") or "").upper().split())
    return bool(n1 and n1 == n2) or bool(core.get("insured_phone")
                                         and core.get("insured_phone") == core.get("complainant_phone"))


def no_letter_reason(door: str, reason) -> str:
    """'' when a letter is required; the cleaned reason when this door may go without one."""
    r = _plain(reason, REASON_MAX)
    if not r:
        return ""
    if not DOORS.get(door, False):
        raise IntakeError("rejection_letter", "Attach the insurer's rejection letter - a claim cannot be raised without it.",
                          "बीमा कंपनी का रिजेक्शन लेटर लगाएँ - इसके बिना क्लेम दर्ज नहीं होता।")
    if len(r) < REASON_MIN:
        raise IntakeError("no_letter_reason", "Say in a few words why the letter is not attached.",
                          "कुछ शब्दों में बताएँ कि लेटर क्यों नहीं लगा है।")
    return r


# ── the rejection letter, uploaded first ────────────────────────────────────────────────────
def owner_key(kind: str, ident) -> str:
    """Who uploaded a letter: 'acct:12', 'branch:NP-PUNE', 'staff:5'. A token only works for its owner."""
    if kind not in ("acct", "branch", "staff"):
        raise ValueError("unknown owner kind")
    v = str(ident or "").strip().upper()
    if not v:
        raise ValueError("empty owner")
    return f"{kind}:{v}"


def _hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


async def _conn():
    c = await aiosqlite.connect(db.DB_PATH)
    c.row_factory = aiosqlite.Row
    await c.execute(
        "CREATE TABLE IF NOT EXISTS nidaan_intake_letters ("
        " letter_id INTEGER PRIMARY KEY AUTOINCREMENT, token_hash TEXT NOT NULL UNIQUE,"
        " owner TEXT NOT NULL, stored_name TEXT NOT NULL, original_name TEXT DEFAULT '',"
        " file_size INTEGER DEFAULT 0, mime_type TEXT DEFAULT '',"
        " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, reserved_at TIMESTAMP,"
        " claim_id INTEGER, doc_id INTEGER)")
    return c


async def stage_letter(owner: str, *, stored_name: str, original_name: str, file_size: int,
                       mime_type: str) -> str:
    """Record a letter the route has already size-checked, type-checked, virus-scanned and written.
    Returns the token the form sends with the claim. Only its hash is stored."""
    token = secrets.token_urlsafe(24)
    c = await _conn()
    try:
        await c.execute(
            "INSERT INTO nidaan_intake_letters (token_hash, owner, stored_name, original_name, file_size, mime_type)"
            " VALUES (?,?,?,?,?,?)",
            (_hash(token), owner, stored_name, (original_name or "")[:200], int(file_size or 0),
             (mime_type or "")[:100]))
        await c.commit()
    finally:
        await c.close()
    return token


_LETTER_GONE = IntakeError(
    "rejection_letter",
    "The rejection letter upload has expired or was already used - please attach it again.",
    "रिजेक्शन लेटर की अपलोड पुरानी हो गई या पहले ही इस्तेमाल हो चुकी है - कृपया दोबारा लगाएँ।")


async def reserve_letter(token: str, owner: str) -> dict:
    """Take the letter for one claim. Atomic: two submissions with the same token cannot both have
    it, and a token is useless to anyone but the person who uploaded the file."""
    if not token or len(token) > 100:
        raise IntakeError("rejection_letter", "Attach the insurer's rejection letter.",
                          "बीमा कंपनी का रिजेक्शन लेटर लगाएँ।")
    c = await _conn()
    try:
        cur = await c.execute(
            "UPDATE nidaan_intake_letters SET reserved_at=CURRENT_TIMESTAMP"
            " WHERE token_hash=? AND owner=? AND reserved_at IS NULL AND claim_id IS NULL"
            " AND created_at > datetime('now', ?)",
            (_hash(token), owner, f"-{LETTER_TOKEN_HOURS} hours"))
        await c.commit()
        if cur.rowcount != 1:
            raise _LETTER_GONE
        row = await (await c.execute(
            "SELECT * FROM nidaan_intake_letters WHERE token_hash=?", (_hash(token),))).fetchone()
        return dict(row)
    finally:
        await c.close()


async def release_letter(letter_id: int) -> None:
    """The claim could not be created - give the letter back so the person can press Submit again."""
    c = await _conn()
    try:
        await c.execute("UPDATE nidaan_intake_letters SET reserved_at=NULL WHERE letter_id=? AND claim_id IS NULL",
                        (int(letter_id),))
        await c.commit()
    finally:
        await c.close()


_LETTER_WORDS = ("reject", "refus", "decision", "repudiat")


def letter_keys(claim_type: str) -> list:
    """Every checklist line that IS the insurer's letter for this type - each template names it
    differently: rejection_letter, rejection_or_survey_letter, refusal_letter, and life's
    decision_letter (missed until the pre-deploy review, 2 Oct)."""
    import biz_nidaan_doc_checklist as ck
    return [d["key"] for d in ck.doc_template_for(template_for(claim_type))
            if any(w in d["key"] for w in _LETTER_WORDS)]


def letter_key(claim_type: str) -> str:
    """The one line the attached letter is ticked against."""
    return (letter_keys(claim_type) or ["rejection_letter"])[0]


async def attach_letter(letter: dict, *, claim_id: int, account_id: int, claim_type: str,
                        by: str = "") -> int:
    """File the reserved letter on the new claim, tick it on the checklist, and record it."""
    import biz_nidaan as nidaan
    import biz_nidaan_doc_checklist as ck
    doc_id = await nidaan.save_claim_document(
        account_id=account_id, stored_name=letter["stored_name"],
        original_name=letter.get("original_name") or letter["stored_name"],
        file_size=int(letter.get("file_size") or 0), mime_type=letter.get("mime_type") or "",
        claim_id=claim_id)
    c = await _conn()
    try:
        await c.execute("UPDATE nidaan_intake_letters SET claim_id=?, doc_id=? WHERE letter_id=?",
                        (claim_id, doc_id, letter["letter_id"]))
        await c.commit()
    finally:
        await c.close()
    try:
        await ck.seed_checklist_for_claim(claim_id, template_for(claim_type))
        await ck.mark_doc_received(claim_id, letter_key(claim_type), via="intake", doc_id=doc_id)
    except Exception as e:  # noqa: BLE001 - the file is on the claim; a tick can be put right by hand
        logger.warning("letter tick failed for claim %s: %s", claim_id, e)
    try:
        await nidaan.record_claim_activity(
            claim_id, "letter_received", actor=by or "intake",
            summary="Rejection letter attached when the claim was raised")
    except Exception:  # noqa: BLE001
        pass
    return doc_id


# ── no letter yet: 7 days, reminders, then archive ──────────────────────────────────────────
async def set_letter_due(claim_id: int, reason: str, by: str) -> None:
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.execute(
            "UPDATE nidaan_claims SET letter_due_at=datetime('now', ?), letter_reminded_at=CURRENT_TIMESTAMP"
            " WHERE claim_id=?",
            (f"+{LETTER_GRACE_DAYS} days", int(claim_id)))
        await c.commit()
    import biz_nidaan as nidaan
    await nidaan.record_claim_activity(
        claim_id, "raised_without_letter", actor=by,
        summary=(f"Raised WITHOUT the rejection letter by {by} - {reason}. The letter is due within "
                 f"{LETTER_GRACE_DAYS} days, or the claim is archived."))


async def letter_arrived(claim_id: int, by: str = "") -> bool:
    """The letter is on the claim now: stop the clock. True if a clock was running."""
    async with aiosqlite.connect(db.DB_PATH) as c:
        cur = await c.execute(
            "UPDATE nidaan_claims SET letter_due_at=NULL WHERE claim_id=? AND letter_due_at IS NOT NULL",
            (int(claim_id),))
        await c.commit()
        stopped = cur.rowcount == 1
    if stopped:
        import biz_nidaan as nidaan
        await nidaan.record_claim_activity(claim_id, "letter_received", actor=by or "system",
                                           summary="Rejection letter received - the 7-day clock is stopped")
    return stopped


async def _letter_ticked(conn, claim_id: int, claim_type: str) -> bool:
    keys = letter_keys(claim_type) or ["rejection_letter"]
    r = await (await conn.execute(
        "SELECT MAX(received) FROM nidaan_claim_doc_checklist WHERE claim_id=? AND doc_key IN (%s)"
        % ",".join("?" * len(keys)), (claim_id, *keys))).fetchone()
    return bool(r and r[0])


async def _moved_on(conn, claim_id: int) -> str:
    """Why archiving would be wrong even without a tick: papers arrived, or the claim has gone
    further than intake. '' when none of that is true."""
    n = (await (await conn.execute(
        "SELECT COUNT(*) FROM nidaan_claim_documents WHERE claim_id=?", (claim_id,))).fetchone())[0]
    if n:
        return "%d document(s) have arrived - one may be the letter" % n
    r = await (await conn.execute(
        "SELECT COALESCE(review_outcome,''), COALESCE(l2_payment_status,'') FROM nidaan_claims WHERE claim_id=?",
        (claim_id,))).fetchone()
    if r and (r[0] or r[1] == "paid"):
        return "the claim has already been reviewed" if r[0] else "the Level-2 fee is paid"
    return ""


async def sweep_letters() -> dict:
    """Every claim raised without its letter: stop the clock if it has come, remind once a day, and
    archive on the due date. Each step claims its row with a conditional UPDATE, so two workers
    running the sweep at once cannot remind twice or archive twice."""
    out = {"cleared": 0, "reminded": 0, "archived": 0}
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, claim_type, branch_code, origin, raised_via, raised_by_staff_id,"
            " raised_by_name, insured_name, complainant_name, letter_due_at,"
            " CAST((julianday(letter_due_at) - julianday('now')) AS REAL) AS days_left"
            " FROM nidaan_claims WHERE letter_due_at IS NOT NULL AND COALESCE(archived,0)=0"
            " ORDER BY letter_due_at LIMIT 200")).fetchall()]
        for r in rows:
            cid = r["claim_id"]
            if await _letter_ticked(c, cid, r.get("claim_type") or ""):
                await c.execute("UPDATE nidaan_claims SET letter_due_at=NULL WHERE claim_id=?", (cid,))
                await c.commit()
                out["cleared"] += 1
                continue
            if (r.get("days_left") or 0) <= 0:
                why = await _moved_on(c, cid)
                if why:
                    cur = await c.execute("UPDATE nidaan_claims SET letter_due_at=NULL WHERE claim_id=?"
                                          " AND letter_due_at IS NOT NULL", (cid,))
                    await c.commit()
                    if cur.rowcount == 1:
                        out["cleared"] += 1
                        await _tell(r, archived=False, kept=why)
                    continue
                cur = await c.execute(
                    "UPDATE nidaan_claims SET archived=1, archived_at=CURRENT_TIMESTAMP,"
                    " archived_by='no rejection letter in 7 days', letter_due_at=NULL"
                    " WHERE claim_id=? AND COALESCE(archived,0)=0 AND letter_due_at IS NOT NULL", (cid,))
                await c.commit()
                if cur.rowcount == 1:
                    out["archived"] += 1
                    await _tell(r, archived=True)
                continue
            cur = await c.execute(
                "UPDATE nidaan_claims SET letter_reminded_at=CURRENT_TIMESTAMP WHERE claim_id=?"
                " AND (letter_reminded_at IS NULL OR letter_reminded_at < datetime('now','-20 hours'))", (cid,))
            await c.commit()
            if cur.rowcount == 1:
                out["reminded"] += 1
                await _tell(r, archived=False)
    return out


def _who(r: dict) -> str:
    return (r.get("complainant_name") or r.get("insured_name") or "the customer").strip()


async def _tell(r: dict, *, archived: bool, kept: str = "") -> None:
    """The raiser hears it where they live: an AP on WhatsApp/email, a staff member on Telegram."""
    import biz_nidaan as nidaan
    import biz_nidaan_notifications as nnot
    cid = r["claim_id"]
    days = max(1, int(round(r.get("days_left") or 0))) if not archived else 0
    if kept:
        subj = f"Claim #{nnot._cn(cid)} - is the rejection letter in?"
        body = (f"Claim #{nnot._cn(cid)} ({_who(r)}) reached its 7-day letter date, but it was NOT "
                f"archived: {kept}. Open it and tick the rejection letter on the checklist if it is "
                f"there - if it is not, ask for it.")
    elif archived:
        subj = f"Claim #{nnot._cn(cid)} archived - no rejection letter"
        body = (f"Claim #{nnot._cn(cid)} ({_who(r)}) was raised without the insurer's rejection letter "
                f"and it did not arrive within {LETTER_GRACE_DAYS} days, so the claim is now ARCHIVED. "
                f"Nothing is deleted. Send the letter and ask the team to bring the claim back.")
    else:
        subj = f"Rejection letter needed - claim #{nnot._cn(cid)}"
        body = (f"Claim #{nnot._cn(cid)} ({_who(r)}) still has no rejection letter. Please send it - "
                f"{days} day(s) left before the claim is archived.")
    try:
        await nidaan.record_claim_activity(
            cid, "letter_archived" if archived else ("letter_kept" if kept else "letter_reminder"),
            actor="system", summary=body[:300])
    except Exception:  # noqa: BLE001
        pass
    sid = r.get("raised_by_staff_id")
    try:
        if sid and (r.get("raised_via") or "") in ("my_business", "on_behalf"):
            if archived:
                await nnot.notify_staff_inapp([int(sid)], subj, body, event_key="claim.letter_archived",
                                              email=False, claim_id=cid)
            else:
                await nnot.notify_staff_inapp([int(sid)], subj, body, event_key="claim.letter_due",
                                              email=False, claim_id=cid)
        elif (r.get("branch_code") or "").strip():
            import biz_nidaan_claim_parties as parties
            if archived:
                await parties.notify_claim_parties(cid, event_key="claim.letter_archived", subject=subj,
                                                   body=body, roles=["branch"])
            else:
                await parties.notify_claim_parties(cid, event_key="claim.letter_due", subject=subj,
                                                   body=body, roles=["branch"])
    except Exception as e:  # noqa: BLE001
        logger.warning("letter %s notice failed for claim %s: %s", "archive" if archived else "reminder", cid, e)
    if archived:
        try:
            ids = [a["staff_id"] for a in await nnot._super_admin_staff()
                   if not (sid and int(a["staff_id"]) == int(sid))]   # the raiser already heard
            await nnot.notify_staff_inapp(ids, subj, body, event_key="claim.letter_archived",
                                          email=False, claim_id=cid)
        except Exception as e:  # noqa: BLE001
            logger.warning("letter archive notice to super admins failed for claim %s: %s", cid, e)
