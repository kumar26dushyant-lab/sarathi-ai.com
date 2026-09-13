"""
NidaanPartner — THE LEVEL-2 BUCKET SYSTEM.

A claim that has been reviewed as winnable and paid for enters a chain of buckets and moves along
it, one act at a time, until nothing is owed in any direction. The names are ClaimShield's,
because that is what the office already reads without thinking.

TWO IDEAS CARRY THE WHOLE DESIGN.

1. THE BUCKET OWNS THE CLAIM. Not a person. A staff member leaving, going on leave or changing
   role therefore cannot strand work — the claim stays exactly where it is and whoever is on duty
   picks it up. A named handler is optional, for the few cases that need one pair of hands.

2. BUCKETS ARE DATA. Their names, clocks, internal steps, captured fields and allowed routes all
   live in tables, so the office process can change without a deploy. Nothing in this module
   hard-codes a bucket name; the defaults below are a SEED, not a definition.

The one thing that is not configurable is the shape of a decision: a move either is allowed or it
is not, and a required field either is filled or it is not. Conditions stay checkable facts rather
than a rule language — a rule language is a programming language that only one person understands
and nobody can test.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.buckets")
DB_PATH = db.DB_PATH

IST = timezone(timedelta(hours=5, minutes=30))


def _today_ist():
    return datetime.now(IST).date()


# ── the seed ─────────────────────────────────────────────────────────────────
# Written once into empty tables. Re-seeding never overwrites an edit — it only fills in what has
# never existed — so a super-admin's changes survive every restart and every deploy.

_BUCKETS = [
    # key, name_en, name_hi, icon, colour, amber, red, waits_on, flags
    ("live_cases",      "Live Cases",      "नए केस",           "📋", "teal",  5,  10, "internal", {"is_entry": 1}),
    ("pending_docs",    "Pending Docs",    "दस्तावेज़ बाकी",    "📄", "teal",  20, 35, "complainant", {}),
    ("pending_draft",   "Pending Draft",   "ड्राफ़्ट बाकी",     "✍️", "teal",  5,  10, "internal", {}),
    ("reimbursement",   "Reimbursement",   "बीमा कंपनी के पास", "📮", "amber", 30, 45, "insurer", {}),
    ("escalation",      "Escalation",      "एस्केलेशन",        "⚖️", "amber", 15, 25, "insurer", {}),
    ("lokpal",          "Lokpal",          "लोकपाल",           "🏛️", "amber", 60, 120, "lokpal", {}),
    ("completed",       "Completed",       "नतीजा आया",        "✅", "green", 7,  14, "internal", {}),
    ("pending_payment", "Pending Payment", "भुगतान बाकी",      "💰", "green", 14, 30, "complainant", {}),
    ("cp_payment",      "CP Payment",      "CP भुगतान",        "🤝", "green", 10, 20, "internal", {}),
    ("finished",        "Finished",        "पूरा हुआ",          "🏁", "grey",  0,  0,  "none", {"is_terminal": 1}),
    ("hold",            "Hold",            "रोका हुआ",          "⏸️", "grey",  0,  0,  "none", {"is_park": 1}),
]

_GUIDE = {
    "live_cases": ("A paid, winnable claim that somebody has started. First real job: build the gist.",
                   "Fill the case gist and let the document checklist generate.",
                   "The gist is complete and the checklist exists.",
                   "The claim type decides the whole document list. Wrong type means weeks of wrong papers."),
    "pending_docs": ("Collecting every paper this kind of claim needs.",
                     "Ask for one document at a time. Check each is the right paper and readable.",
                     "Every required document is in, and originals have arrived by post.",
                     "Hospitals refusing indoor case papers is common — send the standard letter, do not wait."),
    "pending_draft": ("Writing the case up and getting it approved inside the office.",
                      "Prepare the gist, then the letter. Send for approval before anything leaves.",
                      "The Medical Officer or Advocate has approved the draft.",
                      "Nothing leaves unapproved. A weak letter is harder to undo than a slow one."),
    "reimbursement": ("The file is with the insurance company and the 30-day clock is running.",
                      "Record their acknowledgement. Send reminders on day 10, 20 and 30.",
                      "They settle, or 30 days pass with no acceptable answer.",
                      "A query puts the ball back with US — answer before their deadline, not ours."),
    "escalation": ("They said no, or said nothing. Taking it above them.",
                   "Grievance officer, and prepare the Lokpal filing if that fails too.",
                   "They settle, or the Lokpal complaint is registered.",
                   "One year from the rejection date is the hard limit. Check it before anything else."),
    "lokpal": ("The case is with the Insurance Ombudsman.",
               "Keep the BHP number on the case, answer every letter the same day, prepare for the hearing.",
               "An award or a dismissal has been received and recorded.",
               "Their deadlines are not negotiable. A missed Annexure reply can end the complaint."),
    "completed": ("A decision has come. Recording what it means for everyone.",
                  "Record the result and the amount, and tell the complainant yourself.",
                  "The result is recorded and the customer has been told by a person.",
                  "Good news or bad, a person delivers it — never an automatic message."),
    "pending_payment": ("The customer's money has to arrive, then our fee.",
                        "Confirm the customer was paid, raise our fee, record every transaction.",
                        "Customer paid and our fee received.",
                        "Once they have their money, chasing our fee gets harder every week."),
    "cp_payment": ("Paying whoever brought the case their share.",
                   "Calculate the share, pay it, record the transaction.",
                   "Every share settled.",
                   "An unpaid partner stops sending cases long before they complain."),
    "finished": ("Nothing is owed in any direction.", "Nothing — the case is closed.",
                 "Closed.", "Reopening needs a super-admin and leaves a remark."),
    "hold": ("A deliberate pause, with a date it comes back.",
             "Nothing until the date arrives.",
             "The return date arrives and the claim goes back by itself.",
             "A pause with no end date is how a case disappears for a year."),
}

# bucket -> [(sub_key, name_en, name_hi, is_default, amber, red, waits_on)]
_SUBSTATES = {
    "pending_docs": [
        ("waiting_complainant", "Waiting on complainant", "ग्राहक से बाकी", 1, None, None, "complainant"),
        ("waiting_hospital", "Waiting on hospital", "अस्पताल से बाकी", 0, None, None, "complainant"),
        ("ready", "Ready", "तैयार", 0, None, None, "internal")],
    "pending_draft": [
        ("drafting", "Drafting", "ड्राफ़्ट बन रहा", 1, None, None, "internal"),
        ("with_mo", "With Medical Officer / Advocate", "अप्रूवल के लिए", 0, 5, 10, "internal"),
        ("draft_query", "Draft Query", "ड्राफ़्ट पर सवाल", 0, None, None, "internal"),
        ("approved", "Approved", "अप्रूव हो गया", 0, None, None, "internal")],
    "reimbursement": [
        ("pending", "Reimbursement Pending", "जमा करना बाकी", 1, 5, 10, "internal"),
        ("submitted", "Submitted", "जमा कर दिया", 0, None, None, "insurer"),
        ("query", "Reimbursement Query", "कंपनी ने सवाल पूछा", 0, 3, 7, "internal")],
    "escalation": [
        ("pending", "Escalation Pending", "एस्केलेट करना बाकी", 1, 5, 10, "internal"),
        ("query", "Escalation Query", "सवाल आया", 0, 3, 7, "internal"),
        ("escalated", "Escalated", "एस्केलेट हो गया", 0, None, None, "insurer")],
    "lokpal": [
        ("pending", "Lokpal Pending", "दाखिल करना बाकी", 1, 7, 14, "internal"),
        ("registered", "Lokpal Registered", "दर्ज हो गया", 0, None, None, "lokpal"),
        ("ann5_pending", "Annexure 5 Pending", "Annexure 5 बाकी", 0, 5, 8, "internal"),
        ("ann5_replied", "Annexure 5 Replied", "Annexure 5 भेजा", 0, None, None, "lokpal"),
        ("ann6_pending", "Annexure 6 Pending", "Annexure 6 बाकी", 0, 5, 8, "internal"),
        ("ann6_replied", "Annexure 6 Replied", "Annexure 6 भेजा", 0, None, None, "lokpal"),
        ("hearing", "Hearing", "सुनवाई", 0, None, None, "lokpal")],
    "completed": [
        ("hearing", "Hearing", "सुनवाई से", 1, None, None, "internal"),
        ("escalation_settlement", "Escalation Settlement", "एस्केलेशन में सेटल", 0, None, None, "internal"),
        ("consent", "Consent", "सहमति से", 0, None, None, "internal")],
    "pending_payment": [
        ("pending", "Pending Payment", "भुगतान बाकी", 1, None, None, "complainant"),
        ("part", "Part Payment", "आंशिक भुगतान", 0, None, None, "complainant"),
        ("disputed", "Disputed Payment", "भुगतान पर विवाद", 0, 7, 14, "internal")],
    "cp_payment": [
        ("payable", "Payable", "देना बाकी", 1, None, None, "internal"),
        ("paid", "Paid", "दे दिया", 0, None, None, "none")],
}

# bucket -> [(field_key, label_en, label_hi, type, required_to_exit, hint)]
_FIELDS = {
    "live_cases": [
        ("hospital_name", "Hospital name", "अस्पताल का नाम", "text", 0, ""),
        ("admission_date", "Date of admission", "भर्ती की तारीख़", "date", 0, ""),
        ("discharge_date", "Date of discharge", "छुट्टी की तारीख़", "date", 0, ""),
        ("diagnosis", "Diagnosis", "बीमारी", "textarea", 0, ""),
        ("patient_complaint", "Patient complaint", "मरीज़ की शिकायत", "textarea", 0, ""),
        ("rejection_reason", "Rejection reason", "अस्वीकृति का कारण", "textarea", 1,
         "As written on the insurance company's letter"),
        ("rejection_date", "Rejection date", "अस्वीकृति की तारीख़", "date", 1,
         "The one-year Ombudsman window counts from this date"),
        ("case_email", "Case email", "केस ईमेल", "text", 1,
         "The complainant's own email — all correspondence runs on it"),
        ("case_email_password", "Case email password", "ईमेल पासवर्ड", "text", 0, ""),
        ("consultation_pct", "Consultation charge %", "कंसल्टेशन %", "number", 0, ""),
        ("cf_amount", "CF amount", "CF राशि", "money", 0, ""),
        ("review_fee_status", "Review fee (PF)", "रिव्यू फ़ीस (PF)", "choice", 0, ""),
        ("review_pf_txn", "PF transaction no.", "PF ट्रांज़ैक्शन नं.", "text", 0, ""),
    ],
    "pending_docs": [
        ("originals_received", "Originals received by post", "ओरिजिनल डाक से मिले", "yesno", 0, ""),
        ("hospital_letter_sent", "Hospital refusal letter sent", "अस्पताल को पत्र भेजा", "yesno", 0, ""),
    ],
    "pending_draft": [
        ("draft_en", "Draft — English", "ड्राफ़्ट — अंग्रेज़ी", "textarea", 1, ""),
        ("draft_hi", "Draft — Hindi", "ड्राफ़्ट — हिंदी", "textarea", 0, ""),
        ("approved_by", "Approved by", "किसने अप्रूव किया", "text", 1,
         "The Medical Officer, or the Advocate on a non-medical claim"),
        ("approved_on", "Approved on", "कब अप्रूव हुआ", "date", 0, ""),
    ],
    "reimbursement": [
        ("submitted_on", "Submitted on", "कब जमा किया", "date", 1, ""),
        ("courier_pod", "Courier / POD no.", "कूरियर POD नं.", "text", 0, ""),
        ("acknowledgement", "Acknowledgement received", "पावती मिली", "yesno", 0, ""),
        ("reminder_10", "Day 10 reminder sent", "10वें दिन रिमाइंडर", "yesno", 0, ""),
        ("reminder_20", "Day 20 reminder sent", "20वें दिन रिमाइंडर", "yesno", 0, ""),
        ("reminder_30", "Day 30 reminder sent", "30वें दिन रिमाइंडर", "yesno", 0, ""),
        ("insurer_reply", "Their reply", "कंपनी का जवाब", "textarea", 0, ""),
    ],
    "escalation": [
        ("escalation_date", "Escalation date", "एस्केलेशन की तारीख़", "date", 1, ""),
        ("grievance_ref", "Grievance reference", "शिकायत संदर्भ", "text", 0, ""),
        ("esc_reminder_1", "1st reminder sent", "पहला रिमाइंडर", "yesno", 0, ""),
        ("esc_reminder_2", "2nd reminder sent", "दूसरा रिमाइंडर", "yesno", 0, ""),
        ("esc_reminder_3", "3rd reminder sent", "तीसरा रिमाइंडर", "yesno", 0, ""),
    ],
    "lokpal": [
        ("bhp_number", "BHP number", "BHP नंबर", "text", 1, ""),
        ("lokpal_registered_on", "Registration date", "दर्ज होने की तारीख़", "date", 0, ""),
        ("ann5_date", "Annexure 5 received", "Annexure 5 मिला", "date", 0, ""),
        ("ann5_reply_date", "Annexure 5 replied", "Annexure 5 भेजा", "date", 0, ""),
        ("ann6_date", "Annexure 6 received", "Annexure 6 मिला", "date", 0, ""),
        ("ann6_reply_date", "Annexure 6 replied", "Annexure 6 भेजा", "date", 0, ""),
        ("hearing_date", "Hearing date", "सुनवाई की तारीख़", "date", 0, ""),
        ("dispatch_pod", "Dispatch POD no.", "डिस्पैच POD नं.", "text", 0, ""),
    ],
    "completed": [
        ("completion_type", "Completion type", "किस तरह पूरा हुआ", "choice", 1, ""),
        ("completion_date", "Completion date", "पूरा होने की तारीख़", "date", 1, ""),
        ("result", "Result", "नतीजा", "choice", 1, ""),
        ("settlement_amount", "Settlement amount", "सेटलमेंट राशि", "money", 0, ""),
        ("informed_on", "Complainant informed on", "ग्राहक को कब बताया", "date", 1, ""),
        ("informed_by", "Informed by", "किसने बताया", "text", 1,
         "A person tells them — never an automatic message"),
    ],
    "pending_payment": [
        ("customer_payment_date", "Customer payment date", "ग्राहक को भुगतान", "date", 0, ""),
        ("settlement_amount", "Settlement amount", "सेटलमेंट राशि", "money", 0, ""),
        ("cf_amount", "CF amount", "CF राशि", "money", 0, ""),
        ("consultation_pct", "Consultation charge %", "कंसल्टेशन %", "number", 0, ""),
        ("pf_status", "Processing fee (PF)", "प्रोसेसिंग फ़ीस", "choice", 0, ""),
        ("pf_txn", "PF transaction no.", "PF ट्रांज़ैक्शन नं.", "text", 0, ""),
        ("cf_txn", "CF transaction no.", "CF ट्रांज़ैक्शन नं.", "text", 0, ""),
        ("cheque_no", "Cheque number", "चेक नंबर", "text", 0, ""),
        ("cheque_amount", "Cheque amount", "चेक राशि", "money", 0, ""),
        ("part_received", "Part payment received", "आंशिक भुगतान मिला", "money", 0, ""),
        ("amount_pending", "Amount pending", "बाकी राशि", "money", 0, ""),
    ],
    "cp_payment": [
        ("cp_share_pct", "Partner share %", "पार्टनर हिस्सा %", "number", 0, ""),
        ("cp_amount", "Amount payable", "देय राशि", "money", 1, ""),
        ("cp_paid_on", "Paid on", "कब दिया", "date", 0, ""),
        ("cp_txn", "Transaction no.", "ट्रांज़ैक्शन नं.", "text", 0, ""),
    ],
}

_CHOICES = {
    "review_fee_status": "Paid\nUnpaid",
    "pf_status": "Paid\nUnpaid",
    "completion_type": "Hearing\nEscalation Settlement\nConsent",
    "result": "Won\nLost\nPartial",
}

# from, to, kind, needs_reason
_MOVES = [
    ("live_cases", "pending_docs", "forward", 0),
    ("live_cases", "pending_draft", "forward", 0),
    ("pending_docs", "pending_draft", "forward", 0),
    ("pending_docs", "live_cases", "back", 1),
    ("pending_draft", "reimbursement", "forward", 0),
    ("pending_draft", "pending_docs", "back", 1),
    ("reimbursement", "escalation", "forward", 0),
    ("reimbursement", "completed", "forward", 0),
    ("reimbursement", "pending_draft", "back", 1),
    ("escalation", "lokpal", "forward", 0),
    ("escalation", "completed", "forward", 0),
    ("escalation", "reimbursement", "back", 1),
    ("lokpal", "completed", "forward", 0),
    ("lokpal", "escalation", "back", 1),
    ("completed", "pending_payment", "forward", 0),
    ("completed", "finished", "forward", 0),
    ("pending_payment", "cp_payment", "forward", 0),
    ("pending_payment", "finished", "forward", 0),
    ("pending_payment", "completed", "back", 1),
    ("cp_payment", "finished", "forward", 0),
    ("cp_payment", "pending_payment", "back", 1),
]

# Hold is reachable from anywhere real, and always returns where it came from.
_PARKABLE = ("live_cases", "pending_docs", "pending_draft", "reimbursement",
             "escalation", "lokpal", "pending_payment", "cp_payment")


async def ensure_seeded() -> dict:
    """Write the default office process into empty tables.

    Idempotent and non-destructive: a row that already exists is left exactly as it is. This is a
    seed, not a definition — once it has run, the super-admin owns these tables.
    """
    made = {"buckets": 0, "substates": 0, "fields": 0, "moves": 0}
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            for i, (key, en, hi, icon, colour, amber, red, waits, flags) in enumerate(_BUCKETS):
                g = _GUIDE.get(key, ("", "", "", ""))
                cur = await c.execute(
                    "INSERT OR IGNORE INTO nidaan_buckets "
                    "(bucket_key,name_en,name_hi,icon,colour,sort_order,amber_days,red_days,"
                    " waits_on,is_entry,is_terminal,is_park,"
                    " guide_what,guide_do,guide_done,guide_watch) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (key, en, hi, icon, colour, i * 10, amber, red, waits,
                     flags.get("is_entry", 0), flags.get("is_terminal", 0), flags.get("is_park", 0),
                     g[0], g[1], g[2], g[3]))
                made["buckets"] += cur.rowcount or 0

            for bkey, rows in _SUBSTATES.items():
                for j, (skey, sen, shi, isdef, amber, red, waits) in enumerate(rows):
                    cur = await c.execute(
                        "INSERT OR IGNORE INTO nidaan_bucket_substates "
                        "(bucket_key,sub_key,name_en,name_hi,sort_order,amber_days,red_days,"
                        " waits_on,is_default) VALUES (?,?,?,?,?,?,?,?,?)",
                        (bkey, skey, sen, shi, j * 10, amber, red, waits, isdef))
                    made["substates"] += cur.rowcount or 0

            for bkey, rows in _FIELDS.items():
                for j, (fkey, lab_en, lab_hi, ftype, req, hint) in enumerate(rows):
                    cur = await c.execute(
                        "INSERT OR IGNORE INTO nidaan_bucket_fields "
                        "(bucket_key,field_key,label_en,label_hi,field_type,choices,hint,"
                        " required_exit,sort_order) VALUES (?,?,?,?,?,?,?,?,?)",
                        (bkey, fkey, lab_en, lab_hi, ftype, _CHOICES.get(fkey, ""), hint,
                         req, j * 10))
                    made["fields"] += cur.rowcount or 0

            moves = list(_MOVES)
            for k in _PARKABLE:
                moves.append((k, "hold", "park", 1))
                moves.append(("hold", k, "resume", 0))
            for j, (f, t, kind, reason) in enumerate(moves):
                cur = await c.execute(
                    "INSERT OR IGNORE INTO nidaan_bucket_moves "
                    "(from_key,to_key,kind,needs_reason,sort_order) VALUES (?,?,?,?,?)",
                    (f, t, kind, reason, j))
                made["moves"] += cur.rowcount or 0
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("bucket seed failed: %s", e)
        return made
    if any(made.values()):
        logger.info("bucket seed wrote %s", made)
    return made


# ── reading the configuration ────────────────────────────────────────────────
async def buckets(include_inactive: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        q = "SELECT * FROM nidaan_buckets"
        if not include_inactive:
            q += " WHERE active=1"
        q += " ORDER BY sort_order, bucket_key"
        return [dict(r) for r in await (await c.execute(q)).fetchall()]


async def bucket(key: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT * FROM nidaan_buckets WHERE bucket_key=?", (key,))).fetchone()
    return dict(r) if r else None


async def substates(key: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_bucket_substates WHERE bucket_key=? AND active=1 "
            "ORDER BY sort_order, sub_id", (key,))).fetchall()]


async def fields(key: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_bucket_fields WHERE bucket_key=? AND active=1 "
            "ORDER BY sort_order, field_id", (key,))).fetchall()]


async def moves_from(key: str) -> list[dict]:
    """Where a claim in this bucket may go, with the bucket's display name attached."""
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await c.execute(
            "SELECT m.*, b.name_en, b.name_hi, b.icon FROM nidaan_bucket_moves m "
            "JOIN nidaan_buckets b ON b.bucket_key=m.to_key AND b.active=1 "
            "WHERE m.from_key=? ORDER BY "
            "CASE m.kind WHEN 'forward' THEN 0 WHEN 'resume' THEN 1 "
            "            WHEN 'back' THEN 2 ELSE 3 END, m.sort_order", (key,))).fetchall()]


async def config() -> dict:
    """Everything the front end needs to draw the whole system, in one call."""
    bs = await buckets()
    out = []
    for b in bs:
        out.append({**b,
                    "substates": await substates(b["bucket_key"]),
                    "fields": await fields(b["bucket_key"]),
                    "moves": await moves_from(b["bucket_key"])})
    return {"buckets": out}


# ── ageing ───────────────────────────────────────────────────────────────────
def _days_since(ts) -> Optional[int]:
    if not ts:
        return None
    try:
        t = datetime.strptime(str(ts)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None
    return max(0, (datetime.utcnow() - t).days)


def age_state(days: Optional[int], amber: Optional[int], red: Optional[int]) -> str:
    """ok · amber · red. A bucket with no clock never reddens."""
    if days is None or not red:
        return "ok"
    if red and days >= red:
        return "red"
    if amber and days >= amber:
        return "amber"
    return "ok"


# ── where a claim is ─────────────────────────────────────────────────────────
async def _claim_row(claim_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, status, archived, review_outcome, l2_payment_status, "
            "pipeline_stage, pipeline_sub, pipeline_stage_at, pipeline_from, pipeline_by, "
            "hold_until, complainant_name, insured_name, l2_handover_at, l2_handover_by "
            "FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    return dict(r) if r else None


def l2_ready(claim: dict) -> bool:
    """Reviewed as winnable AND the Level-2 fee paid. Both, or the buckets do not take it."""
    return ((claim.get("review_outcome") or "").lower() == "can_fight"
            and (claim.get("l2_payment_status") or "").lower() == "paid")


async def claim_fields(claim_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as c:
        rows = await (await c.execute(
            "SELECT field_key, value FROM nidaan_claim_fields WHERE claim_id=?",
            (int(claim_id),))).fetchall()
    return {r[0]: r[1] for r in rows}


async def set_field(claim_id: int, field_key: str, value: str, actor: str = "") -> dict:
    """Record one answer.

    Only fields the configuration knows about are accepted, so a renamed or deleted field cannot
    quietly keep collecting data that nobody will ever look at again.
    """
    async with aiosqlite.connect(DB_PATH) as c:
        known = await (await c.execute(
            "SELECT 1 FROM nidaan_bucket_fields WHERE field_key=? AND active=1 LIMIT 1",
            (field_key,))).fetchone()
        if not known:
            return {"ok": False, "error": "That field is not part of any bucket."}
        await c.execute(
            "INSERT INTO nidaan_claim_fields (claim_id, field_key, value, updated_by, updated_at) "
            "VALUES (?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(claim_id, field_key) DO UPDATE SET value=excluded.value, "
            "updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP",
            (int(claim_id), field_key, (value or "").strip()[:8000], (actor or "")[:80]))
        await c.commit()
    return {"ok": True}


async def missing_required(claim_id: int, bucket_key: str) -> list:
    """Which required-to-exit fields are still blank.

    This is what turns finished from an opinion into something checkable. The refusal names them,
    so nobody has to hunt for what is missing.
    """
    vals = await claim_fields(claim_id)
    out = []
    for f in await fields(bucket_key):
        if f.get("required_exit") and not (vals.get(f["field_key"]) or "").strip():
            out.append({"field_key": f["field_key"], "label": f["label_en"]})
    return out


async def _log(claim_id: int, summary: str, actor: str) -> None:
    """Every move writes a remark.

    The remarks log is the spine of a case. A move that leaves no trace is how a file becomes
    unexplainable six months later.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "INSERT INTO nidaan_claim_activity "
                "(claim_id, kind, channel, direction, actor, summary) VALUES (?,?,?,?,?,?)",
                (int(claim_id), "case_bucket", "web", "", (actor or "staff")[:80], summary[:400]))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("bucket log failed for %s: %s", claim_id, e)


async def start_l2(claim_id: int, *, actor: str = "", force: bool = False) -> dict:
    """Put a paid, winnable claim into the entry bucket. The act that begins Level-2 work."""
    row = await _claim_row(claim_id)
    if not row or row.get("archived") or (row.get("status") or "") in ("closed", "withdrawn"):
        return {"ok": False, "error": "That case is closed or does not exist."}
    if (row.get("pipeline_stage") or "").strip():
        return {"ok": False, "error": "This case has already started Level-2.",
                "bucket": row.get("pipeline_stage")}
    if not l2_ready(row):
        if (row.get("review_outcome") or "").lower() != "can_fight":
            return {"ok": False, "error": "The review has not said this case can be fought yet."}
        return {"ok": False,
                "error": "The Level-2 fee has not been paid, so the work has not been bought yet."}

    # Intake signs for a claim before Level-2 can begin on it. Without this a claim could drift
    # into the buckets with nobody having looked at it, and nobody to ask when something turns
    # out to be missing three weeks later.
    if not force and not row.get("l2_handover_at"):
        return {"ok": False, "needs_handover": True,
                "error": "This claim has not been handed over to Level-2 yet. Someone on intake "
                         "duty moves it across from L2 Claims first."}

    # Everything Level-2 runs on must be true BEFORE the claim enters the buckets. A gap here
    # costs weeks once the work is under way, and by then the person who could have fixed it in
    # ten seconds has moved on. `force` exists for a super-admin who knows better.
    if not force:
        rd = await readiness(claim_id)
        if rd.get("ok") and rd.get("blocks"):
            return {"ok": False, "readiness": rd,
                    "error": "Not ready to start: " + "; ".join(
                        "%s - %s" % (b["label"], b["detail"]) for b in rd["blocks"][:3])}

    entry = None
    for b in await buckets():
        if b.get("is_entry"):
            entry = b
            break
    if not entry:
        return {"ok": False, "error": "No entry bucket is configured. Ask a super-admin."}

    subs = await substates(entry["bucket_key"])
    default_sub = next((s["sub_key"] for s in subs if s.get("is_default")),
                       (subs[0]["sub_key"] if subs else ""))
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "UPDATE nidaan_claims SET pipeline_stage=?, pipeline_sub=?, "
            "pipeline_entered_at=CURRENT_TIMESTAMP, pipeline_stage_at=CURRENT_TIMESTAMP, "
            "pipeline_by=?, pipeline_from='' WHERE claim_id=?",
            (entry["bucket_key"], default_sub, (actor or "")[:80], int(claim_id)))
        await c.commit()
    await _log(claim_id, "Level-2 processing started - now in %s" % entry["name_en"], actor)
    return {"ok": True, "bucket": entry["bucket_key"], "name": entry["name_en"], "sub": default_sub}


async def move(claim_id: int, to_key: str, *, sub: str = "", reason: str = "",
               hold_until: str = "", actor: str = "", force: bool = False) -> dict:
    """Move a claim to another bucket, if the configuration allows that route.

    Refuses when the route is not configured, when a reason is required and missing, when a
    required field is still blank, or when a park has no return date. Each refusal says exactly
    what is wrong - a refusal a person cannot act on is just a locked door.
    """
    row = await _claim_row(claim_id)
    if not row or row.get("archived") or (row.get("status") or "") in ("closed", "withdrawn"):
        return {"ok": False, "error": "That case is closed or does not exist."}
    cur_key = (row.get("pipeline_stage") or "").strip()
    if not cur_key:
        return {"ok": False, "error": "This case has not started Level-2 yet."}
    to_key = (to_key or "").strip()
    if to_key == cur_key:
        return {"ok": False, "error": "The case is already in that bucket."}

    dest = await bucket(to_key)
    if not dest or not dest.get("active"):
        return {"ok": False, "error": "That bucket does not exist."}

    allowed = {m["to_key"]: m for m in await moves_from(cur_key)}
    rule = allowed.get(to_key)
    src = await bucket(cur_key) or {}
    if not rule and not force:
        return {"ok": False,
                "error": "A case in %s cannot move to %s. A super-admin can open that route in "
                         "the bucket designer." % (src.get("name_en", cur_key),
                                                   dest.get("name_en", to_key))}
    kind = (rule or {}).get("kind", "forward")

    # GROUND RULE: every move carries a comment, forwards as well as backwards.
    #
    # The person receiving the claim in the next bucket starts cold. They need to know what was
    # done, what is still pending and what to do next - and the only person who can tell them is
    # the one letting go of it. A bucket system without this degenerates into claims appearing
    # in queues with no explanation, which is exactly the silence it was built to end.
    if not (reason or "").strip() and not force:
        if kind == "back":
            return {"ok": False,
                    "error": "Say what is wrong - the person who sent it forward needs to know."}
        if kind == "park":
            return {"ok": False, "error": "Say why this is being paused."}
        return {"ok": False,
                "error": "Add a note for the next bucket - what you did, and what is still pending."}

    # Parking always needs a date. An open-ended pause is how a case disappears for a year.
    if dest.get("is_park"):
        day = (hold_until or "").strip()[:10]
        try:
            d = datetime.strptime(day, "%Y-%m-%d").date()
        except Exception:
            return {"ok": False, "error": "Pick the date this case should come back."}
        if d < _today_ist():
            return {"ok": False, "error": "That date has already passed. Pick a future date."}
    else:
        day = ""

    # Leaving a bucket forwards means finishing it. Going backwards or parking is explicitly NOT
    # finishing, so the required fields are only enforced on the way forward.
    if kind == "forward" and not force:
        missing = await missing_required(claim_id, cur_key)
        if missing:
            names = ", ".join(m["label"] for m in missing[:4])
            return {"ok": False, "missing": missing,
                    "error": "Fill these before moving on: %s" % names}

    subs = await substates(to_key)
    sub = (sub or "").strip()
    valid_subs = {s["sub_key"] for s in subs}
    if sub and sub not in valid_subs:
        return {"ok": False, "error": "That is not a step inside %s." % dest["name_en"]}
    if not sub:
        sub = next((s["sub_key"] for s in subs if s.get("is_default")),
                   (subs[0]["sub_key"] if subs else ""))

    # A park remembers where it came from; resuming clears the memory.
    if dest.get("is_park"):
        came_from = cur_key
    elif src.get("is_park"):
        came_from = ""
    else:
        came_from = row.get("pipeline_from") or ""

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "UPDATE nidaan_claims SET pipeline_stage=?, pipeline_sub=?, "
                "pipeline_stage_at=CURRENT_TIMESTAMP, pipeline_by=?, pipeline_from=?, "
                "hold_until=? WHERE claim_id=?",
                (to_key, sub, (actor or "")[:80], came_from, (day or None), int(claim_id)))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("bucket move failed for %s: %s", claim_id, e)
        return {"ok": False, "error": "Could not save that. Try again."}

    verb = {"back": "sent back to", "park": "parked in",
            "resume": "resumed into"}.get(kind, "moved to")
    summary = "%s -> %s %s" % (src.get("name_en", cur_key), verb, dest["name_en"])
    if day:
        summary += " until %s" % day
    if (reason or "").strip():
        summary += " - %s" % reason.strip()
    await _log(claim_id, summary, actor)
    return {"ok": True, "bucket": to_key, "name": dest["name_en"], "sub": sub, "kind": kind}


async def set_substate(claim_id: int, sub: str, *, actor: str = "") -> dict:
    """Move a claim between steps INSIDE its bucket.

    The clock restarts, because a step with its own deadline - an Annexure awaiting reply - is a
    new wait, not a continuation of the old one.
    """
    row = await _claim_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case does not exist."}
    cur_key = (row.get("pipeline_stage") or "").strip()
    if not cur_key:
        return {"ok": False, "error": "This case has not started Level-2 yet."}
    subs = {s["sub_key"]: s for s in await substates(cur_key)}
    if sub not in subs:
        return {"ok": False, "error": "That is not a step in this bucket."}
    if (row.get("pipeline_sub") or "") == sub:
        return {"ok": True, "sub": sub, "unchanged": True}
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "UPDATE nidaan_claims SET pipeline_sub=?, pipeline_stage_at=CURRENT_TIMESTAMP, "
            "pipeline_by=? WHERE claim_id=?", (sub, (actor or "")[:80], int(claim_id)))
        await c.commit()
    await _log(claim_id, "Step changed to %s" % subs[sub]["name_en"], actor)
    return {"ok": True, "sub": sub}


async def wake_parked(*, actor: str = "system") -> dict:
    """Return every parked claim whose date has arrived to the bucket it came from.

    Nobody has to remember. This is the half of parking that makes it safe: without it, a park is
    just a tidier way of losing a case.
    """
    today = _today_ist().strftime("%Y-%m-%d")
    woken = []
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        parks = [r["bucket_key"] for r in await (await c.execute(
            "SELECT bucket_key FROM nidaan_buckets WHERE is_park=1")).fetchall()]
        if not parks:
            return {"woken": [], "count": 0}
        ph = ",".join("?" * len(parks))
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, pipeline_from FROM nidaan_claims "
            "WHERE pipeline_stage IN (%s) AND COALESCE(hold_until,'') <> '' "
            "AND date(hold_until) <= date(?)" % ph, (*parks, today))).fetchall()]
    for r in rows:
        back_to = (r.get("pipeline_from") or "").strip()
        if not back_to:
            continue
        res = await move(r["claim_id"], back_to, actor=actor,
                         reason="the pause has ended", force=True)
        if res.get("ok"):
            woken.append({"claim_id": r["claim_id"], "to": back_to})
    if woken:
        logger.info("woke %d parked claim(s)", len(woken))
    return {"woken": woken, "count": len(woken)}


# ── reading the work ─────────────────────────────────────────────────────────
_CLAIM_COLS = (
    "c.claim_id, c.account_id, c.claim_type, c.insured_name, c.complainant_name, "
    "c.complainant_phone, c.complainant_email, c.insured_phone, c.insured_email, "
    "c.insurer_name, c.policy_no, c.disputed_amount, c.branch_code, c.status, "
    "c.review_outcome, c.l2_payment_status, c.assigned_to_staff_id, c.created_at, "
    "c.pipeline_stage, c.pipeline_sub, c.pipeline_stage_at, c.pipeline_entered_at, "
    "c.pipeline_by, c.pipeline_from, c.hold_until, c.raised_by_name, c.raised_via, "
    "c.channel_partner_id, c.origin"
)


def _origin_of(r: dict) -> str:
    """Where the case came from, as a sentence. A trail, not a person to chase."""
    via = (r.get("raised_via") or "").strip()
    who = (r.get("raised_by_name") or "").strip()
    branch = (r.get("branch_code") or "").strip()
    if via == "on_behalf" and who:
        return "Raised for subscriber by %s" % who
    if (r.get("origin") or "") == "branch" and branch:
        return "Raised by branch %s" % branch
    if branch.startswith("SP-"):
        return "Raised by staff %s" % branch
    if branch:
        return "Raised by branch %s" % branch
    if r.get("account_id"):
        return "Subscriber raised"
    return "Direct"


async def _docs_counts(claim_ids: list) -> dict:
    """{claim_id: (done, total)} for the document checklist. Best effort - never blocks a board."""
    out: dict = {}
    if not claim_ids:
        return out
    try:
        ph = ",".join("?" * len(claim_ids))
        async with aiosqlite.connect(DB_PATH) as c:
            rows = await (await c.execute(
                "SELECT claim_id, COUNT(*) AS total, "
                "SUM(CASE WHEN COALESCE(received,0)=1 THEN 1 ELSE 0 END) AS done "
                "FROM nidaan_claim_doc_checklist "
                "WHERE claim_id IN (%s) AND COALESCE(required,1)=1 GROUP BY claim_id" % ph,
                claim_ids)).fetchall()
        for r in rows:
            out[r[0]] = (int(r[2] or 0), int(r[1] or 0))
    except Exception:
        pass
    return out


async def _lokpal_days_left(r: dict, vals: dict) -> Optional[int]:
    """Days until the one-year Ombudsman window closes, counted from the rejection date.

    It never resets - not for a park, not for going back a bucket, not for the company reopening
    the file. Wherever the claim is, this is the number that outranks everything.
    """
    rej = (vals.get("rejection_date") or "").strip()[:10]
    if not rej:
        return None
    try:
        d = datetime.strptime(rej, "%Y-%m-%d").date()
    except Exception:
        return None
    return 365 - (_today_ist() - d).days


async def board(bucket_key: str = "", *, sub: str = "", q: str = "",
                limit: int = 300) -> dict:
    """The claims in one bucket, ready to draw as a table.

    Ordered so the answer to "what do I do next" is the top of the list: the most overdue first.
    """
    limit = max(1, min(int(limit or 300), 1000))
    where = ["COALESCE(c.archived,0)=0", "COALESCE(c.pipeline_stage,'') <> ''"]
    params: list = []
    if bucket_key:
        where.append("c.pipeline_stage = ?")
        params.append(bucket_key)
    if sub:
        where.append("COALESCE(c.pipeline_sub,'') = ?")
        params.append(sub)
    if q:
        like = "%" + q.strip() + "%"
        where.append("(c.insured_name LIKE ? OR c.complainant_name LIKE ? OR "
                     "c.complainant_phone LIKE ? OR c.insurer_name LIKE ? OR "
                     "c.policy_no LIKE ? OR CAST(c.claim_id AS TEXT) LIKE ?)")
        params += [like] * 6

    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT %s FROM nidaan_claims c WHERE %s ORDER BY c.claim_id DESC LIMIT 2000"
            % (_CLAIM_COLS, " AND ".join(where)), params)).fetchall()]

    bmap = {b["bucket_key"]: b for b in await buckets(include_inactive=True)}
    submap: dict = {}
    for bk in {r["pipeline_stage"] for r in rows if r.get("pipeline_stage")}:
        submap[bk] = {s["sub_key"]: s for s in await substates(bk)}

    ids = [r["claim_id"] for r in rows]
    docs = await _docs_counts(ids)

    items = []
    for r in rows:
        bk = r.get("pipeline_stage") or ""
        b = bmap.get(bk) or {}
        sk = r.get("pipeline_sub") or ""
        sdef = (submap.get(bk) or {}).get(sk) or {}
        # A step with its own clock overrides the bucket's. An Annexure awaiting reply is urgent
        # inside a bucket that is otherwise measured in months.
        amber = sdef.get("amber_days") or b.get("amber_days")
        red = sdef.get("red_days") or b.get("red_days")
        days = _days_since(r.get("pipeline_stage_at"))
        done, total = docs.get(r["claim_id"], (0, 0))
        vals = await claim_fields(r["claim_id"])
        left = await _lokpal_days_left(r, vals)
        items.append({
            "claim_id": r["claim_id"],
            "who": (r.get("complainant_name") or r.get("insured_name") or "").strip(),
            "insured": (r.get("insured_name") or "").strip(),
            "phone": (r.get("complainant_phone") or r.get("insured_phone") or "").strip(),
            "email": (r.get("complainant_email") or r.get("insured_email") or "").strip(),
            "insurer": (r.get("insurer_name") or "").strip(),
            "policy_no": (r.get("policy_no") or "").strip(),
            "claim_type": (r.get("claim_type") or "").strip(),
            "amount": r.get("disputed_amount") or 0,
            "bucket": bk, "bucket_name": b.get("name_en", bk), "bucket_icon": b.get("icon", ""),
            "sub": sk, "sub_name": sdef.get("name_en", ""),
            "days": days, "age_state": age_state(days, amber, red),
            "amber_days": amber, "red_days": red,
            "waits_on": sdef.get("waits_on") or b.get("waits_on") or "internal",
            "docs_done": done, "docs_total": total,
            "docs_ready": bool(total and done >= total),
            "origin": _origin_of(r),
            "assigned_to": r.get("assigned_to_staff_id"),
            "moved_by": (r.get("pipeline_by") or ""),
            "hold_until": (r.get("hold_until") or ""),
            "from_bucket": (r.get("pipeline_from") or ""),
            "lokpal_days_left": left,
            "created_at": r.get("created_at"),
        })

    order = {"red": 0, "amber": 1, "ok": 2}
    items.sort(key=lambda i: (order.get(i["age_state"], 3), -(i["days"] or 0)))

    sub_counts: dict = {}
    for i in items:
        sub_counts[i["sub"]] = sub_counts.get(i["sub"], 0) + 1

    return {"items": items[:limit], "matching": len(items),
            "sub_counts": sub_counts,
            "late": sum(1 for i in items if i["age_state"] in ("red", "amber")),
            "red": sum(1 for i in items if i["age_state"] == "red")}


async def counts() -> dict:
    """Per-bucket totals and how many are late, for the sidebar and the overview."""
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, pipeline_stage, pipeline_sub, pipeline_stage_at, disputed_amount "
            "FROM nidaan_claims WHERE COALESCE(archived,0)=0 "
            "AND COALESCE(pipeline_stage,'') <> ''")).fetchall()]
    bmap = {b["bucket_key"]: b for b in await buckets(include_inactive=True)}
    submap: dict = {}
    for bk in bmap:
        submap[bk] = {s["sub_key"]: s for s in await substates(bk)}

    out: dict = {}
    for r in rows:
        bk = r.get("pipeline_stage") or ""
        b = bmap.get(bk) or {}
        sdef = (submap.get(bk) or {}).get(r.get("pipeline_sub") or "") or {}
        amber = sdef.get("amber_days") or b.get("amber_days")
        red = sdef.get("red_days") or b.get("red_days")
        st = age_state(_days_since(r.get("pipeline_stage_at")), amber, red)
        e = out.setdefault(bk, {"total": 0, "amber": 0, "red": 0, "amount": 0})
        e["total"] += 1
        e["amount"] += int(r.get("disputed_amount") or 0)
        if st in ("amber", "red"):
            e[st] += 1
    return out


async def waiting_to_start(limit: int = 200) -> list:
    """Handed across by intake, and not yet begun.

    Being QUALIFIED for Level-2 is not the same as being handed over: somebody on intake duty has
    to look the file over and sign for it first. This list is the ones that have been signed for -
    so the days counted here are days since the handover, which is the clock the Level-2 team is
    actually answerable for.
    """
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT %s, c.l2_handover_at, c.l2_handover_by, c.l2_handover_note "
            "FROM nidaan_claims c WHERE COALESCE(c.archived,0)=0 "
            "AND COALESCE(c.pipeline_stage,'')='' AND c.l2_handover_at IS NOT NULL "
            "ORDER BY c.l2_handover_at ASC LIMIT ?" % _CLAIM_COLS, (int(limit),))).fetchall()]
    return [{"claim_id": r["claim_id"],
             "who": (r.get("complainant_name") or r.get("insured_name") or "").strip(),
             "insurer": (r.get("insurer_name") or "").strip(),
             "amount": r.get("disputed_amount") or 0,
             "origin": _origin_of(r),
             "handed_by": r.get("l2_handover_by") or "",
             "handed_at": r.get("l2_handover_at") or "",
             "handover_note": r.get("l2_handover_note") or "",
             "waiting_days": _days_since(r.get("l2_handover_at"))} for r in rows]


async def for_claim(claim_id: int) -> dict:
    """Everything the case report needs about where this claim is."""
    row = await _claim_row(claim_id)
    if not row:
        return {}
    bk = (row.get("pipeline_stage") or "").strip()
    if not bk:
        return {"in_pipeline": False, "l2_ready": l2_ready(row)}
    b = await bucket(bk) or {}
    subs = await substates(bk)
    sdef = next((s for s in subs if s["sub_key"] == (row.get("pipeline_sub") or "")), {})
    amber = sdef.get("amber_days") or b.get("amber_days")
    red = sdef.get("red_days") or b.get("red_days")
    days = _days_since(row.get("pipeline_stage_at"))
    vals = await claim_fields(claim_id)
    return {
        "in_pipeline": True, "l2_ready": True,
        "bucket": bk, "bucket_name": b.get("name_en", bk), "bucket_icon": b.get("icon", ""),
        "guide": {"what": b.get("guide_what", ""), "do": b.get("guide_do", ""),
                  "done": b.get("guide_done", ""), "watch": b.get("guide_watch", "")},
        "sub": row.get("pipeline_sub") or "", "sub_name": sdef.get("name_en", ""),
        "substates": subs,
        "days": days, "age_state": age_state(days, amber, red),
        "amber_days": amber, "red_days": red,
        "fields": await fields(bk), "values": vals,
        "missing_required": await missing_required(claim_id, bk),
        "moves": await moves_from(bk),
        "hold_until": row.get("hold_until") or "",
        "from_bucket": row.get("pipeline_from") or "",
        "moved_by": row.get("pipeline_by") or "",
        "lokpal_days_left": await _lokpal_days_left(row, vals),
    }


# The stage names the first pipeline used, and the bucket each becomes. Run once at startup;
# after that there is nothing left to map and it costs a single indexed UPDATE that matches
# nothing. Kept rather than deleted because a database restored from an old backup would
# otherwise carry vocabulary nothing understands.
_LEGACY_STAGES = {
    "consolidation": "live_cases",
    "documentation": "pending_docs",
    "drafting": "pending_draft",
    "representation": "reimbursement",
    "escalation": "escalation",
    "lokpal": "lokpal",
    "outcome": "completed",
    "settlement": "pending_payment",
}


async def migrate_legacy_stages() -> int:
    """Rewrite any first-generation stage name as its bucket. Returns how many moved."""
    n = 0
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            for old, new in _LEGACY_STAGES.items():
                if old == new:
                    continue
                cur = await c.execute(
                    "UPDATE nidaan_claims SET pipeline_stage=? WHERE pipeline_stage=?", (new, old))
                n += cur.rowcount or 0
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("legacy stage migration failed: %s", e)
        return 0
    if n:
        logger.info("migrated %d claim(s) from first-generation stage names to buckets", n)
    return n


# ── is this claim fit to start? ──────────────────────────────────────────────
# Everything Level-2 runs on has to be true BEFORE a claim enters the buckets, because each of
# these gaps costs weeks once the work is under way: a complainant nobody can reach, an insurance
# company recorded as a person's name, no authorisation to act, a channel we cannot copy in.
#
# Two severities, and the difference matters.
#   BLOCK  the work literally cannot proceed - no way to reach anyone, or no company to write to.
#   FIX    the work can start but this must be sorted, and it is named loudly until it is.
#
# The checks name the CHANNEL too, because "no mobile number" is useless without "whose".

import re as _re

_PHONE_RX = _re.compile(r"^(?:\+?91[\-\s]?)?[6-9]\d{9}$")
_EMAIL_RX = _re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Words that show up when somebody types a person into the insurance-company box. Not a
# guarantee, but it catches the common case and asks a human to look.
_NOT_A_COMPANY = _re.compile(
    r"\b(insurance|assurance|general|health|life|bupa|allianz|lombard|ergo|tokio|sompo|"
    r"gic|lic|acko|digit|niva|star|care|manipal|chola|shriram|magma|navi|zuno|united|"
    r"oriental|national|reliance|iffco|royal|universal|future|liberty|kotak|birla|"
    r"metlife|hdfc|icici|sbi|tata|max|pnb|new india)\b", _re.I)


def _clean_phone(v: str) -> str:
    return _re.sub(r"[^\d+]", "", (v or "").strip())


def looks_like_a_person(name: str) -> bool:
    """Two or three capitalised words and no insurance vocabulary - almost certainly a person."""
    n = (name or "").strip()
    if not n:
        return False
    if _NOT_A_COMPANY.search(n):
        return False
    words = [w for w in _re.split(r"\s+", n) if w]
    return 1 < len(words) <= 4


async def readiness(claim_id: int) -> dict:
    """What is still missing before this claim can be worked in the buckets.

    Returns every check with a severity, what is wrong, and - where we can - which channel to
    ring about it. Nothing here guesses: each item is a fact that is present or absent.
    """
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, account_id, claim_type, insured_name, insured_phone, insured_email, "
            "complainant_name, complainant_phone, complainant_email, insurer_name, policy_no, "
            "disputed_amount, branch_code, channel_partner_id, origin, raised_by_name, raised_via, "
            "review_outcome, l2_payment_status, pipeline_stage "
            "FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
        if not r:
            return {"ok": False, "error": "not_found"}
        row = dict(r)

        branch = None
        if (row.get("branch_code") or "").strip():
            b = await (await c.execute(
                "SELECT branch_code, name, contact_email, contact_phone FROM nidaan_branches "
                "WHERE branch_code=?", (row["branch_code"].strip(),))).fetchone()
            branch = dict(b) if b else None

        cp = None
        if row.get("channel_partner_id"):
            p = await (await c.execute(
                "SELECT cp_id, name, email, phone FROM nidaan_channel_partners WHERE cp_id=?",
                (row["channel_partner_id"],))).fetchone()
            cp = dict(p) if p else None

        acct = None
        if row.get("account_id"):
            a = await (await c.execute(
                "SELECT account_id, owner_name, firm_name, email, phone FROM nidaan_accounts "
                "WHERE account_id=?", (row["account_id"],))).fetchone()
            acct = dict(a) if a else None

        portal = await (await c.execute(
            "SELECT consent_accepted_at, access_token FROM nidaan_claimant_portal "
            "WHERE claim_id=? ORDER BY portal_id DESC LIMIT 1", (int(claim_id),))).fetchone()
        portal = dict(portal) if portal else None

        docs = await (await c.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN COALESCE(received,0)=1 THEN 1 ELSE 0 END) AS done "
            "FROM nidaan_claim_doc_checklist WHERE claim_id=? AND COALESCE(required,1)=1",
            (int(claim_id),))).fetchone()
        docs = dict(docs) if docs else {"total": 0, "done": 0}

    items = []

    def add(key, label, sev, ok, detail="", fix=""):
        items.append({"key": key, "label": label, "severity": sev, "ok": bool(ok),
                      "detail": detail, "fix": fix})

    # ── reaching the complainant ─────────────────────────────────────────────
    ph = _clean_phone(row.get("complainant_phone") or row.get("insured_phone") or "")
    em = (row.get("complainant_email") or row.get("insured_email") or "").strip()
    ph_ok = bool(_PHONE_RX.match(ph))
    em_ok = bool(_EMAIL_RX.match(em))

    add("complainant_phone", "Complainant's mobile", "fix", ph_ok,
        ("Not recorded" if not ph else ("Does not look like an Indian mobile: " + ph)) if not ph_ok else ph,
        "Edit the claim and correct the mobile number.")
    add("complainant_email", "Complainant's email", "fix", em_ok,
        ("Not recorded" if not em else ("Does not look like an email: " + em)) if not em_ok else em,
        "Consolidation, Escalation and Lokpal all run on email - get one before those stages.")
    # One of the two is the hard floor: with neither, nobody can be told anything at all.
    add("reachable", "Some way to reach the complainant", "block", ph_ok or em_ok,
        "" if (ph_ok or em_ok) else "No usable mobile and no usable email",
        "Ask the channel who brought the case for a working contact.")

    # ── the insurance company ────────────────────────────────────────────────
    ins = (row.get("insurer_name") or "").strip()
    if not ins:
        add("insurer", "Insurance company", "block", False, "Not recorded",
            "Pick it from the list on the claim - it decides who we write to.")
    elif looks_like_a_person(ins):
        add("insurer", "Insurance company", "block", False,
            "\"%s\" looks like a person, not a company" % ins,
            "Someone typed a name into this field. Pick the real company from the list.")
    else:
        add("insurer", "Insurance company", "fix", True, ins)

    add("policy_no", "Policy number", "fix", bool((row.get("policy_no") or "").strip()),
        (row.get("policy_no") or "").strip() or "Not recorded")
    add("amount", "Disputed amount", "fix", bool(row.get("disputed_amount")),
        ("Rs %s" % row["disputed_amount"]) if row.get("disputed_amount") else "Not recorded",
        "The fee is a percentage of this, so it cannot stay blank.")

    # ── permission to act ────────────────────────────────────────────────────
    consent = bool(portal and portal.get("consent_accepted_at"))
    add("authorization", "Signed authorisation", "fix", consent,
        ("Accepted " + str(portal["consent_accepted_at"])[:10]) if consent
        else ("Link issued, not yet accepted" if portal else "No portal link issued yet"),
        "Open the claim and push the authorisation to the complainant.")

    # ── the documents ────────────────────────────────────────────────────────
    total = int(docs.get("total") or 0)
    done = int(docs.get("done") or 0)
    add("checklist", "Document checklist", "fix", total > 0,
        ("%d of %d collected" % (done, total)) if total else "No checklist generated yet",
        "The checklist comes from the claim type - set the type on the claim.")

    # ── the channel that brought it, so they can be copied in ────────────────
    chans = []
    if branch:
        chans.append(("branch", "Branch %s" % (branch.get("name") or branch.get("branch_code")),
                      branch.get("contact_phone"), branch.get("contact_email")))
    if cp:
        chans.append(("cp", "Channel partner %s" % (cp.get("name") or cp.get("cp_id")),
                      cp.get("phone"), cp.get("email")))
    if acct:
        chans.append(("subscriber", "Subscriber %s" % (acct.get("owner_name")
                                                       or acct.get("firm_name") or ""),
                      acct.get("phone"), acct.get("email")))
    for kind, label, cph, cem in chans:
        cph_ok = bool(_PHONE_RX.match(_clean_phone(cph or "")))
        cem_ok = bool(_EMAIL_RX.match((cem or "").strip()))
        add("channel_" + kind, label, "fix", cph_ok or cem_ok,
            (", ".join([x for x in [(_clean_phone(cph or "") if cph_ok else ""),
                                    ((cem or "").strip() if cem_ok else "")] if x])
             or "No usable phone or email on record"),
            "They are copied on every update, so a bad contact means they hear nothing.")
    if not chans:
        add("channel_none", "Where it came from", "fix", True, "Direct - no channel to copy in")

    blocks = [i for i in items if i["severity"] == "block" and not i["ok"]]
    fixes = [i for i in items if i["severity"] == "fix" and not i["ok"]]
    return {
        "ok": True,
        "claim_id": int(claim_id),
        "ready": not blocks and not fixes,
        "can_start": not blocks,
        "blocks": blocks, "fixes": fixes, "items": items,
        "missing_count": len(blocks) + len(fixes),
        "origin": _origin_of(row),
    }


async def readiness_many(claim_ids: list) -> dict:
    """Readiness for a list of claims, for the To-start table."""
    out = {}
    for cid in (claim_ids or [])[:300]:
        try:
            out[cid] = await readiness(cid)
        except Exception as e:  # noqa: BLE001
            logger.warning("readiness failed for %s: %s", cid, e)
    return out


# ── the handover from L1 to L2 ───────────────────────────────────────────────
# Two steps, deliberately, because they are two different decisions made by two different people.
#
#   1. HAND OVER   Intake duty checks the file over, answers the probing questions, signs their
#                  name to it and passes it across. The claim appears in "To start".
#   2. START       Whoever works the first bucket picks it up and begins.
#
# Merging them would mean a claim could drift into Level-2 with nobody having looked at it, and
# nobody to ask when something turns out to be missing three weeks later. The handover record is
# the answer to "who said this was ready?".

import json as _json


async def _handover_row(claim_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, status, archived, review_outcome, l2_payment_status, "
            "pipeline_stage, l2_handover_at, l2_handover_by, l2_handover_note "
            "FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    return dict(r) if r else None


async def probing_questions(claim_id: int) -> dict:
    """What intake must confirm before handing a claim across.

    Built from the readiness check, so the questions are always about THIS claim: a blocker has to
    be fixed, and everything merely missing has to be consciously acknowledged rather than
    skipped. The answers are stored with the handover, which is what makes the sign-off mean
    something later.
    """
    rd = await readiness(claim_id)
    if not rd.get("ok"):
        return rd
    qs = []
    for i in rd.get("fixes", []):
        qs.append({"key": i["key"], "label": i["label"], "detail": i["detail"],
                   "why": i.get("fix", ""), "required": False})
    # Two questions that no automatic check can answer, and both cost weeks when wrong.
    qs.append({"key": "ack_docs_plan", "required": True,
               "label": "Do we know which documents this case needs, and has the complainant been told?",
               "detail": "", "why": "Documents are the longest wait in Level-2. Starting without a "
                                    "plan for them is how a case sits for forty days."})
    qs.append({"key": "ack_contactable", "required": True,
               "label": "Has someone actually spoken to the complainant recently?",
               "detail": "", "why": "A number on file is not the same as a number that answers."})
    return {"ok": True, "claim_id": int(claim_id), "readiness": rd, "questions": qs,
            "can_hand_over": rd.get("can_start", False)}


async def hand_over(claim_id: int, *, note: str = "", checks: Optional[dict] = None,
                    actor: str = "", force: bool = False) -> dict:
    """Intake hands the claim to Level-2, with their name on it."""
    row = await _handover_row(claim_id)
    if not row or row.get("archived") or (row.get("status") or "") in ("closed", "withdrawn"):
        return {"ok": False, "error": "That case is closed or does not exist."}
    if row.get("l2_handover_at"):
        return {"ok": False, "error": "This claim was already handed over by %s."
                % (row.get("l2_handover_by") or "someone")}
    if not l2_ready(row):
        if (row.get("review_outcome") or "").lower() != "can_fight":
            return {"ok": False, "error": "The review has not said this case can be fought yet."}
        return {"ok": False, "error": "The Level-2 fee has not been paid yet."}

    rd = await readiness(claim_id)
    if not force and rd.get("blocks"):
        return {"ok": False, "readiness": rd,
                "error": "Fix these first: " + "; ".join(
                    "%s - %s" % (b["label"], b["detail"]) for b in rd["blocks"][:3])}

    # The two judgement questions are not optional: they are the whole point of a human handover.
    checks = checks or {}
    for k in ("ack_docs_plan", "ack_contactable"):
        if not checks.get(k):
            return {"ok": False, "error": "Answer both questions before handing this over."}
    if not (note or "").strip():
        return {"ok": False,
                "error": "Add a short note for the Level-2 team - they pick this up cold."}

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "UPDATE nidaan_claims SET l2_handover_at=CURRENT_TIMESTAMP, l2_handover_by=?, "
                "l2_handover_note=?, l2_handover_checks=? WHERE claim_id=?",
                ((actor or "")[:80], (note or "").strip()[:600],
                 _json.dumps(checks)[:2000], int(claim_id)))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("handover failed for %s: %s", claim_id, e)
        return {"ok": False, "error": "Could not save that. Try again."}

    gaps = len(rd.get("fixes", []))
    await _log(claim_id,
               "Handed to Level-2 by %s%s - %s" % (actor or "staff",
                                                   (" (%d gap(s) acknowledged)" % gaps) if gaps else "",
                                                   (note or "").strip()),
               actor)
    return {"ok": True, "handed_by": actor, "acknowledged_gaps": gaps}


async def undo_handover(claim_id: int, *, reason: str = "", actor: str = "") -> dict:
    """Pull a claim back out of the Level-2 waiting list. Super-admin only, and recorded."""
    row = await _handover_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case does not exist."}
    if not row.get("l2_handover_at"):
        return {"ok": False, "error": "This claim has not been handed over."}
    if (row.get("pipeline_stage") or "").strip():
        return {"ok": False,
                "error": "Level-2 work has already started on this claim - move it in the "
                         "workspace instead."}
    if not (reason or "").strip():
        return {"ok": False, "error": "Say why it is being pulled back."}
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "UPDATE nidaan_claims SET l2_handover_at=NULL, l2_handover_by='', "
            "l2_handover_note='', l2_handover_checks='' WHERE claim_id=?", (int(claim_id),))
        await c.commit()
    await _log(claim_id, "Pulled back out of the Level-2 waiting list - %s" % reason.strip(), actor)
    return {"ok": True}


async def pending_handover(limit: int = 300) -> list:
    """Qualified for Level-2 but not yet handed across. This is what L2 Claims shows."""
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT %s FROM nidaan_claims c WHERE COALESCE(c.archived,0)=0 "
            "AND COALESCE(c.pipeline_stage,'')='' AND c.l2_handover_at IS NULL "
            "AND LOWER(COALESCE(c.review_outcome,''))='can_fight' "
            "AND LOWER(COALESCE(c.l2_payment_status,''))='paid' "
            "ORDER BY c.created_at ASC LIMIT ?" % _CLAIM_COLS, (int(limit),))).fetchall()]
    return [{"claim_id": r["claim_id"],
             "who": (r.get("complainant_name") or r.get("insured_name") or "").strip(),
             "insurer": (r.get("insurer_name") or "").strip(),
             "amount": r.get("disputed_amount") or 0,
             "origin": _origin_of(r),
             "waiting_days": _days_since(r.get("created_at"))} for r in rows]
