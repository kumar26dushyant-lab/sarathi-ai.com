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


def _now_ist():
    """The server runs on CEST, the database on UTC and the office on IST. Anything that means
    'today' or 'this hour' to a person has to be asked in IST."""
    return datetime.now(IST)


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
                      "Prepare the gist, then the letter. Have it approved before anything leaves.",
                      "The draft is written and approved, and the letter is ready to go.",
                      "A weak letter is harder to undo than a slow one. Approval is yours to "
                      "confirm — the system no longer asks for a name before it moves."),
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
        # Consultation %, CF amount, review fee and PF transaction moved to the payment stage
        # (founder, 14 Sep) - consultation % and CF amount live there under the same keys.
        # From the ClaimShield gist form. The INSURER's claim number, not ClaimShield's case id.
        ("insurer_claim_no", "Claim number", "क्लेम नंबर", "text", 0,
         "The insurance company's own claim number, e.g. CIR/2026/201112/1282847"),
        # ClaimShield's "Claim Type" is the kind of DISPUTE, not health/motor/life.
        ("rejection_type", "Claim type", "क्लेम का प्रकार", "choice", 0,
         "Rejection, deduction or delay in process"),
        ("gist_comments", "Comments", "टिप्पणी", "textarea", 0, ""),
        # The complainant's relationship to the PATIENT. Not complainant_role, which records who
        # raised the claim and is read by attribution and routing.
        ("relationship", "On behalf of", "किसकी ओर से", "choice", 0,
         "The complainant's relationship to the patient"),
    ],
    "pending_docs": [
        ("originals_received", "Originals received by post", "ओरिजिनल डाक से मिले", "yesno", 0, ""),
        ("hospital_letter_sent", "Hospital refusal letter sent", "अस्पताल को पत्र भेजा", "yesno", 0, ""),
    ],
    "pending_draft": [
        # ClaimShield: "Draft" goes to the insurance company, "Lokpal Draft" to the Ombudsman.
        # Formatted text (bold / italic / underline), sanitised on the server.
        ("draft_en", "Draft", "ड्राफ़्ट", "richtext", 1, ""),
        ("draft_hi", "Lokpal Draft", "लोकपाल ड्राफ़्ट", "richtext", 0, ""),
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
        # Dates, not yes/no. "Was a reminder sent" cannot tell you when the next one is due, and
        # the whole escalation clock is counted in days from the escalation date (founder,
        # 19 Sep: 1st after 10 days, 2nd at 20, 3rd at 30, then Lokpal).
        ("esc_reminder_1", "1st reminder sent on", "पहला रिमाइंडर भेजा", "date", 0, ""),
        ("esc_reminder_2", "2nd reminder sent on", "दूसरा रिमाइंडर भेजा", "date", 0, ""),
        ("esc_reminder_3", "3rd reminder sent on", "तीसरा रिमाइंडर भेजा", "date", 0, ""),
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
        ("bank_name", "Bank name", "बैंक का नाम", "text", 0, ""),
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
    "rejection_type": "Rejection\nDeduction\nDelay in process\nPart settlement\nOther",
    "relationship": "Self\nSpouse\nChildren\nParent\nSibling\nOther",
    "review_fee_status": "Paid\nUnpaid",
    "pf_status": "Paid\nUnpaid",
    "completion_type": "Hearing\nEscalation Settlement\nConsent",
    "result": "Won\nLost\nPartial",
}

# from, to, kind, needs_reason
_MOVES = [
    # live_cases -> pending_docs retired 14 Sep: documents are gathered before Level-2 now.
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


# Labels and types the seed once wrote and has since corrected. Applied only where the row still
# carries the OLD seeded text - so a super-admin who renamed a field keeps their name.
_SEED_CORRECTIONS = [
    ("pending_draft", "draft_en", "Draft \u2014 English", "Draft", "\u0921\u094d\u0930\u093e\u092b\u093c\u094d\u091f", "richtext"),
    ("pending_draft", "draft_hi", "Draft \u2014 Hindi", "Lokpal Draft", "\u0932\u094b\u0915\u092a\u093e\u0932 \u0921\u094d\u0930\u093e\u092b\u093c\u094d\u091f", "richtext"),
]


# ── The escalation clock ─────────────────────────────────────────────────────
# Counted in days from the escalation date. Nothing here SENDS anything: it works out what is due
# so a person can be told, which is the founder's rule for this whole stage (19 Sep) — "make
# everything manual and increase visibility... if we automate then it will over complicated and
# break things".
ESC_REMINDER_DAYS = (10, 20, 30)
ESC_REMINDER_FIELDS = ("esc_reminder_1", "esc_reminder_2", "esc_reminder_3")


# Config the seed cannot fix, because ensure_seeded() is INSERT OR IGNORE and deliberately never
# overwrites a row a super-admin may have edited. These are corrections to rows that already
# exist, so they are written as idempotent UPDATEs guarded by the value they are changing FROM -
# a super-admin who later renames or re-types one of these keeps their version.
_CONFIG_FIXES = (
    # Grievance reference: never used by any screen or report, and no claim ever had a value.
    ("UPDATE nidaan_bucket_fields SET active=0 "
     "WHERE bucket_key='escalation' AND field_key='grievance_ref' AND active=1", ()),
    # The three reminders become dates.
    ("UPDATE nidaan_bucket_fields SET field_type='date', label_en='1st reminder sent on', "
     "label_hi='पहला रिमाइंडर भेजा' WHERE bucket_key='escalation' "
     "AND field_key='esc_reminder_1' AND field_type='yesno'", ()),
    ("UPDATE nidaan_bucket_fields SET field_type='date', label_en='2nd reminder sent on', "
     "label_hi='दूसरा रिमाइंडर भेजा' WHERE bucket_key='escalation' "
     "AND field_key='esc_reminder_2' AND field_type='yesno'", ()),
    ("UPDATE nidaan_bucket_fields SET field_type='date', label_en='3rd reminder sent on', "
     "label_hi='तीसरा रिमाइंडर भेजा' WHERE bucket_key='escalation' "
     "AND field_key='esc_reminder_3' AND field_type='yesno'", ()),
    # A yes/no answer left in what is now a date box would render as an empty, broken field.
    ("DELETE FROM nidaan_claim_fields WHERE field_key IN "
     "('esc_reminder_1','esc_reminder_2','esc_reminder_3') "
     "AND value IN ('yes','no','Yes','No','')", ()),
    # Claims escalated BEFORE the date started driving the status. Claim 119 was carrying an
    # escalation date of 18 Sep while still filed as "Escalation Pending" — the very confusion
    # this change removes, so the claims that caused it are corrected too. Deliberately narrow:
    # only an empty or 'pending' step is touched, so a claim already at 'query' or 'escalated'
    # keeps the step a person chose.
    # The two approval fields, removed at the founder's request (19 Sep: "Need to remove both
    # option"). Deactivated rather than deleted, so the three values already recorded stay
    # readable on the claims that hold them. NOTE the consequence, which is deliberate: approved_by
    # was required_exit, so Pending Draft no longer asks for an approver's name before a claim can
    # move on. The bucket's own guidance was reworded to stop promising a rule that is now a
    # judgement.
    ("UPDATE nidaan_bucket_fields SET active=0, required_exit=0 WHERE bucket_key='pending_draft' "
     "AND field_key IN ('approved_by','approved_on') AND active=1", ()),
    # The three reminder-date fields, replaced by day flags on the Escalation screen (founder,
    # 21 Sep: "we no need option 1st reminder, second reminder, third reminder... make it simple
    # and manual"). A reminder ledger asked staff to maintain a record; what they actually need on
    # opening the claim is how long the insurer has been silent, which the flags show directly.
    # Deactivated, not deleted: the dates already recorded on live claims stay readable.
    ("UPDATE nidaan_bucket_fields SET active=0, required_exit=0 WHERE bucket_key='escalation' "
     "AND field_key IN ('esc_reminder_1','esc_reminder_2','esc_reminder_3') AND active=1", ()),
    # "Past Medical Records / Doctor's Certificate" off the health list — optional, never once
    # received on any claim, and one more line on a list people already find long.
    ("UPDATE nidaan_claim_doc_checklist SET required=0 WHERE doc_key='prior_medical' "
     "AND required=1", ()),
    # …and off the claims that already carried it. Dropping it from the template was only half
    # the job: effective_docs() re-adds ANY checklist row the template does not recognise as a
    # CUSTOM document, labelled "Asked for on this case." So on 55 live claims the line came
    # back wearing a worse hat — it now read as something a staffer had specifically demanded
    # for that claim, rather than a template line nobody wanted.
    #
    # Marked removed rather than deleted, so it leaves the list the same way a staffer's own
    # removal does: it moves to removed_docs() with a name and a reason somebody can read back.
    # Guarded on received=0 — if a document was ever actually collected against this line, it
    # stays. (Live at the time of writing: 77 rows, 0 ever received.)
    ("UPDATE nidaan_claim_doc_checklist SET removed_at=CURRENT_TIMESTAMP, "
     "removed_by='NidaanPartner', removed_reason='Taken off the standard health list — this "
     "document is no longer asked for.' "
     "WHERE doc_key='prior_medical' AND removed_at IS NULL "
     "AND COALESCE(received,0)=0", ()),
    ("UPDATE nidaan_claims SET pipeline_sub='escalated' WHERE pipeline_stage='escalation' "
     "AND COALESCE(pipeline_sub,'') IN ('','pending') AND claim_id IN "
     "(SELECT claim_id FROM nidaan_claim_fields WHERE field_key='escalation_date' "
     " AND TRIM(COALESCE(value,'')) != '')", ()),
)


async def _apply_config_fixes() -> int:
    """Corrections to seeded rows. Idempotent: each is a no-op once it has run."""
    n = 0
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            for sql, args in _CONFIG_FIXES:
                cur = await c.execute(sql, args)
                n += cur.rowcount or 0
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("config fixes failed: %s", e)
    if n:
        logger.info("bucket config corrected (%d row(s))", n)
    return n


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
            for bkey, fkey, old_label, new_label, new_hi, new_type in _SEED_CORRECTIONS:
                await c.execute(
                    "UPDATE nidaan_bucket_fields SET label_en=?, label_hi=?, field_type=? "
                    "WHERE bucket_key=? AND field_key=? AND label_en=?",
                    (new_label, new_hi, new_type, bkey, fkey, old_label))
            for j, (f, t, kind, reason) in enumerate(moves):
                # Never seed a route whose far end has been retired: re-introducing a way
                # into a bucket the office has switched off is the same resurrection bug
                # wearing a different hat. (The tombstone in save_route covers a route removed
                # by hand; this covers a whole bucket being turned off.)
                cur = await c.execute(
                    "INSERT OR IGNORE INTO nidaan_bucket_moves "
                    "(from_key,to_key,kind,needs_reason,sort_order) "
                    "SELECT ?,?,?,?,? WHERE EXISTS(SELECT 1 FROM nidaan_buckets "
                    "  WHERE bucket_key=? AND active=1) "
                    "AND EXISTS(SELECT 1 FROM nidaan_buckets WHERE bucket_key=? AND active=1)",
                    (f, t, kind, reason, j, f, t))
                made["moves"] += cur.rowcount or 0
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("bucket seed failed: %s", e)
        return made
    made["fixed"] = await _apply_config_fixes()
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


async def substates(key: str, include_inactive: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        q = "SELECT * FROM nidaan_bucket_substates WHERE bucket_key=?"
        if not include_inactive:
            q += " AND active=1"
        q += " ORDER BY sort_order, sub_id"
        return [dict(r) for r in await (await c.execute(q, (key,))).fetchall()]


async def fields(key: str, include_inactive: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        q = "SELECT * FROM nidaan_bucket_fields WHERE bucket_key=?"
        if not include_inactive:
            q += " AND active=1"
        q += " ORDER BY sort_order, field_id"
        return [dict(r) for r in await (await c.execute(q, (key,))).fetchall()]


async def moves_from(key: str) -> list[dict]:
    """Where a claim in this bucket may go, with the bucket's display name attached."""
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await c.execute(
            "SELECT m.*, b.name_en, b.name_hi, b.icon FROM nidaan_bucket_moves m "
            "JOIN nidaan_buckets b ON b.bucket_key=m.to_key AND b.active=1 "
            "WHERE m.from_key=? AND m.kind <> 'removed' ORDER BY "
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
    """Whole days since a timestamp OR a bare date.

    It used to take timestamps only, so every DATE FIELD a person fills in — an escalation date,
    a reminder date — silently measured as None. The escalation clock read every claim as "no
    date" and told nobody anything was due. Strictly additive: the only inputs whose answer
    changes are the ones that used to fail.
    """
    if not ts:
        return None
    raw = str(ts)[:19].replace("T", " ").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            t = datetime.strptime(raw if fmt != "%Y-%m-%d" else raw[:10], fmt)
        except Exception:  # noqa: BLE001
            continue
        return max(0, (datetime.utcnow() - t).days)
    return None


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
            # payment_status too: a subscription IS a paid Level-2, and l2_fee_covered() reads it.
            "payment_status, "
            "pipeline_stage, pipeline_sub, pipeline_stage_at, pipeline_from, pipeline_by, "
            "hold_until, complainant_name, insured_name, l2_handover_at, l2_handover_by, "
            "l2_handover_note, back_at, back_by, back_by_role, back_from, back_reason, "
            "query_state, query_text, query_by, query_by_id, query_at, query_round, "
            "query_resolved_by, query_resolved_at, query_resolved_note, query_mo_id, query_mo_name, "
            "cq_at, cq_by, cq_by_id, cq_text, cq_channels, cq_reply_at, "
            "complainant_phone, insured_phone, complainant_email, insured_email, "
            "assigned_to_staff_id "
            "FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    return dict(r) if r else None


def l2_fee_covered(claim: dict) -> bool:
    """Has the Level-2 work been paid for - by ANY of the three routes we sell it through?

    A subscriber has already paid through their plan; a direct customer pays the L2 fee; a
    per-claim customer has a paid claim. All three are covered, and the claim screens have always
    said so. This used to accept only `l2_payment_status == 'paid'`, so a subscription claim read
    as covered on L2 Claims and as unpaid the moment somebody tried to hand it over - two answers
    to one question, which is the bug NP-112 surfaced.
    """
    return ((claim.get("l2_payment_status") or "").lower() == "paid"
            or (claim.get("payment_status") or "").lower() in ("paid", "subscription"))


def l2_ready(claim: dict) -> bool:
    """Reviewed as winnable, and the work paid for. This DESCRIBES a claim - it no longer
    forbids anything. Nothing that is not ready is refused; it is moved with a reason."""
    return ((claim.get("review_outcome") or "").lower() == "can_fight"
            and l2_fee_covered(claim))


async def claim_fields(claim_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as c:
        rows = await (await c.execute(
            "SELECT field_key, value FROM nidaan_claim_fields WHERE claim_id=?",
            (int(claim_id),))).fetchall()
    return {r[0]: r[1] for r in rows}


# The case email account is opened for ONE purpose - writing to the insurance company and the
# authorities - and its password is the only thing on a claim that is a credential rather than a
# fact. The founder's call (17 Sep): super admins and sub-super admins. Everyone else sees that it
# exists, not what it is; they can still do their work, because nothing on the draft needs the
# password itself. Asking for it is a separate, audited step.
SECRET_FIELDS = {"case_email_password"}
SECRET_ROLES = ("super_admin", "sub_super_admin")
MASK = "••••••••"


def may_see_secrets(role: str) -> bool:
    return (role or "").strip().lower() in SECRET_ROLES


def mask_secrets(values: dict, role: str) -> dict:
    """Hide credential values from anyone whose role does not include them. Done on the SERVER,
    so a password never reaches a browser that should not have it - hiding it in the page would
    only mean it was one Inspect away."""
    if may_see_secrets(role):
        return values
    out = dict(values or {})
    for k in SECRET_FIELDS:
        if (out.get(k) or "").strip():
            out[k] = MASK
    return out


# The formatting a draft may carry, and nothing else. Rich text is shown back to staff on the
# case report, so anything outside this list - a script, an event handler, an iframe, a style that
# hides text - would be stored and handed to the next person who opens the case.
_RICH_TAGS = {"b", "strong", "i", "em", "u", "br", "p", "div", "span", "ul", "ol", "li"}


def sanitize_rich(html: str) -> str:
    """Keep bold / italic / underline, paragraphs, line breaks and lists. Drop every attribute,
    every other tag, and the contents of script and style outright."""
    import html as _h
    from html.parser import HTMLParser

    out: list = []

    class _S(HTMLParser):
        skip = 0

        def handle_starttag(self, tag, attrs):
            t = tag.lower()
            if t in ("script", "style", "iframe", "object", "embed", "template", "noscript"):
                self.skip += 1
                return
            if not self.skip and t in _RICH_TAGS:
                out.append("<%s>" % t)          # every attribute dropped, always

        def handle_startendtag(self, tag, attrs):
            if not self.skip and tag.lower() == "br":
                out.append("<br>")

        def handle_endtag(self, tag):
            t = tag.lower()
            if t in ("script", "style", "iframe", "object", "embed", "template", "noscript"):
                self.skip = max(0, self.skip - 1)
                return
            if not self.skip and t in _RICH_TAGS and t != "br":
                out.append("</%s>" % t)

        def handle_data(self, data):
            if not self.skip:
                out.append(_h.escape(data, quote=False))

        def handle_entityref(self, name):
            if not self.skip:
                out.append("&%s;" % name)

        def handle_charref(self, name):
            if not self.skip:
                out.append("&#%s;" % name)

    p = _S(convert_charrefs=False)
    p.feed(html or "")
    p.close()
    return "".join(out).strip()


# How much a field may hold. A full legal draft with its formatting runs well past 8,000
# characters - the old single limit cut the end off a letter with no error at all.
_FIELD_MAX = {"richtext": 60000, "textarea": 20000}


# ── Finished work locks (founder, 15 Sep) ──────────────────────────────────────
# A bucket's work can be changed while the claim is in that bucket - or in any bucket BEFORE it,
# since filling something early harms nothing. Once the claim has moved PAST it, the work is
# locked and only a super admin may change it. The gist is the exception: it stays open until
# the drafts are finished, because the drafter is the one who spots a wrong fact in it.
SUPER = "super_admin"
GIST_BUCKET = "live_cases"
GIST_OPEN_UNTIL = "pending_draft"
# The case's own facts that the gist corrects - columns on the claim, not bucket fields.
CORE_GIST_KEYS = ("insured_name", "complainant_name", "insurer_name", "policy_no",
                  "policy_inception_date", "disputed_amount")


async def locked_fields(row: Optional[dict], role: str = "") -> dict:
    """{field_key: name of the bucket that finished it} for everything THIS person may not change
    on this claim. Empty for a super admin, and for a claim that has not started Level-2."""
    if not row or (role or "") == SUPER:
        return {}
    cur = (row.get("pipeline_stage") or "").strip()
    if not cur:
        return {}
    bmap = {b["bucket_key"]: b for b in await buckets(include_inactive=True)}
    here = bmap.get(cur) or {}
    if here.get("is_park"):
        # A parked claim is where it was parked from, for this purpose.
        here = bmap.get((row.get("pipeline_from") or "").strip()) or here
    if here.get("sort_order") is None or here.get("is_park"):
        return {}
    at = here["sort_order"]
    until = bmap.get(GIST_OPEN_UNTIL) or {}
    async with aiosqlite.connect(DB_PATH) as c:
        rows = await (await c.execute(
            "SELECT bucket_key, field_key FROM nidaan_bucket_fields WHERE active=1")).fetchall()
    last: dict = {}
    for bk, fk in rows:
        b = bmap.get(bk)
        if not b or b.get("is_park") or b.get("sort_order") is None:
            continue
        o, nm = b["sort_order"], b.get("name_en") or bk
        if bk == GIST_BUCKET and until.get("sort_order") is not None and until["sort_order"] > o:
            o, nm = until["sort_order"], until.get("name_en") or GIST_OPEN_UNTIL
        # A field kept in two buckets (settlement amount) belongs to the later one.
        if fk not in last or o > last[fk][0]:
            last[fk] = (o, nm)
    out = {fk: nm for fk, (o, nm) in last.items() if at > o}
    g = bmap.get(GIST_BUCKET) or {}
    g_o = until.get("sort_order") if until.get("sort_order") is not None else g.get("sort_order")
    if g_o is not None and at > g_o:
        nm = until.get("name_en") or g.get("name_en") or "Live Cases"
        for k in CORE_GIST_KEYS:
            out[k] = nm
    return out


def lock_message(where: str) -> str:
    return ("Locked: this was finished in %s. Only a super admin can change it now - "
            "use Request a change." % (where or "an earlier bucket"))


async def _note_locked_edit(claim_id: int, field_key: str, where: str, actor: str) -> None:
    """A super admin changing locked work goes into the remarks - once an hour per field, not
    once per autosave."""
    key = "lockedit:%s:%s:%s" % (claim_id, field_key, datetime.utcnow().strftime("%Y%m%d%H"))
    if await _alert_once(key):
        await _log(claim_id, "\U0001f513 Super admin changed %s (locked since %s)"
                   % (field_key.replace("_", " "), where), actor)


async def set_field(claim_id: int, field_key: str, value: str, actor: str = "",
                    role: str = "") -> dict:
    """Record one answer.

    Only fields the configuration knows about are accepted, so a renamed or deleted field cannot
    quietly keep collecting data that nobody will ever look at again. Finished work is locked for
    everyone but a super admin; saving the same value again is harmless and not refused.
    """
    async with aiosqlite.connect(DB_PATH) as c:
        known = await (await c.execute(
            "SELECT field_type FROM nidaan_bucket_fields WHERE field_key=? AND active=1 LIMIT 1",
            (field_key,))).fetchone()
        if not known:
            return {"ok": False, "error": "That field is not part of any bucket."}
        ftype = known[0] or "text"
        val = (value or "").strip()
        if ftype == "richtext":
            val = sanitize_rich(val)
        # A row of dots is not a password. Anyone without credential rights READS this field as
        # MASK; if their form hands the dots back, the real password would be overwritten with
        # them and the case mailbox would be locked out with no way to tell what happened.
        # Sending the mask back means "leave it alone", which is what the person intended.
        if field_key in SECRET_FIELDS and val == MASK:
            return {"ok": True, "unchanged": True}
        limit = _FIELD_MAX.get(ftype, 2000)
        if len(val) > limit:
            # Refuse rather than cut: a truncated legal draft looks complete and is not.
            return {"ok": False,
                    "error": "That is too long to save (%d characters; the limit is %d)."
                             % (len(val), limit)}
        # A discharge before the admission is not a typo we can live with: those two dates decide
        # the treatment period the whole case argues about, and a reversed pair reads as a
        # fabricated claim to an insurer. Checked HERE as well as in the browser, so it cannot be
        # stored by any route (founder, 19 Sep).
        if val and field_key in ("admission_date", "discharge_date"):
            other_key = "discharge_date" if field_key == "admission_date" else "admission_date"
            other = await (await c.execute(
                "SELECT value FROM nidaan_claim_fields WHERE claim_id=? AND field_key=?",
                (int(claim_id), other_key))).fetchone()
            other_val = ((other[0] if other else "") or "").strip()
            if other_val:
                adm = val if field_key == "admission_date" else other_val
                dis = val if field_key == "discharge_date" else other_val
                # ISO dates (yyyy-mm-dd) compare correctly as strings; anything else is left alone
                # rather than guessed at.
                if len(adm) == 10 and len(dis) == 10 and adm > dis:
                    return {"ok": False, "error":
                            "The discharge date (%s) is before the admission date (%s). "
                            "Check the discharge summary and correct whichever is wrong."
                            % (dis, adm)}

        row = await _claim_row(claim_id)
        locks = await locked_fields(row, "")        # what is locked for everyone but a super admin
        if field_key in locks:
            cur = await (await c.execute(
                "SELECT value FROM nidaan_claim_fields WHERE claim_id=? AND field_key=?",
                (int(claim_id), field_key))).fetchone()
            same = ((cur[0] if cur else "") or "").strip()
            if ftype == "richtext":
                same = sanitize_rich(same)
            if same == val:
                return {"ok": True, "unchanged": True}
            if (role or "") != SUPER:
                return {"ok": False, "locked": True, "error": lock_message(locks[field_key])}
        _became_escalated = (
            field_key == "escalation_date" and val
            and (row or {}).get("pipeline_stage") == "escalation"
            and ((row or {}).get("pipeline_sub") or "") in ("", "pending"))
        await c.execute(
            "INSERT INTO nidaan_claim_fields (claim_id, field_key, value, updated_by, updated_at) "
            "VALUES (?,?,?,?,CURRENT_TIMESTAMP) "
            "ON CONFLICT(claim_id, field_key) DO UPDATE SET value=excluded.value, "
            "updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP",
            (int(claim_id), field_key, val, (actor or "")[:80]))
        if _became_escalated:
            # THE DATE IS THE STATUS. Recording when we escalated is the act of escalating, so
            # nobody should also have to remember to change a dropdown to say so — that is how a
            # claim ends up filed under "Escalation Pending" a week after it was escalated, which
            # is exactly what claim 119 looked like. (founder, 19 Sep: "when we record first date
            # there, then the status will change escalated as soon as escalation date is
            # recorded".)
            # Same columns set_substate() writes, so the age shown on the board restarts for the
            # new step exactly as it does for a manual change.
            await c.execute(
                "UPDATE nidaan_claims SET pipeline_sub='escalated', "
                "pipeline_stage_at=CURRENT_TIMESTAMP, pipeline_by=? WHERE claim_id=?",
                ((actor or "")[:80], int(claim_id)))
        await c.commit()
    if _became_escalated:
        await _log(claim_id, "Escalated — escalation date recorded as %s" % val, actor)
    if field_key in locks:
        await _note_locked_edit(claim_id, field_key, locks[field_key], actor)
    return {"ok": True, "became_escalated": bool(_became_escalated)}


async def _clean_rich_values(vals: dict) -> dict:
    """Rich-text answers sanitised on the way OUT. The case sheet puts these straight into an
    editor inside the ops page, and drafts saved before they were rich text were never cleaned."""
    async with aiosqlite.connect(DB_PATH) as c:
        rich = {r[0] for r in await (await c.execute(
            "SELECT field_key FROM nidaan_bucket_fields WHERE field_type='richtext'")).fetchall()}
    out = dict(vals or {})
    for k in rich:
        if out.get(k):
            out[k] = sanitize_rich(out[k])
    return out


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
    # Again: nothing here refuses. What is outstanding is collected and recorded on the claim.
    concerns = []
    if (row.get("review_outcome") or "").lower() != "can_fight":
        concerns.append("The review has not said this case can be fought yet.")
    if not l2_fee_covered(row):
        concerns.append("No Level-2 fee recorded - not on the claim, not a subscription.")
    if not row.get("l2_handover_at"):
        concerns.append("Nobody on intake handed this over - it was started directly.")
    rd = await readiness(claim_id)
    for b in (rd.get("blocks") or []):
        concerns.append("%s - %s" % (b["label"], b["detail"]))

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
    note = "Level-2 processing started - now in %s" % entry["name_en"]
    if concerns:
        note += " | STARTED WITH THESE STILL OPEN: " + "; ".join(concerns[:4])
    await _log(claim_id, note, actor)
    await _notify_move(claim_id, to_key=entry["bucket_key"], to_name=entry["name_en"],
                       from_name="To start", kind="forward",
                       reason=(row.get("l2_handover_note") or ""), actor=actor,
                       who=(row.get("complainant_name") or row.get("insured_name") or "").strip())
    return {"ok": True, "bucket": entry["bucket_key"], "name": entry["name_en"],
            "sub": default_sub, "concerns": concerns}


async def move(claim_id: int, to_key: str, *, sub: str = "", reason: str = "",
               hold_until: str = "", actor: str = "", force: bool = False,
               actor_role: str = "", quiet: bool = False) -> dict:
    """Move a claim to any other bucket.

    NO MOVE IS EVER REFUSED FOR BEING UNTIDY. A route that is not in the configuration is allowed
    and recorded as off the usual path; a required field still blank is allowed once the person
    says why. The only two things that stop a move are the ones that would make it meaningless:
    no comment at all (the next bucket would learn nothing) and a park with no return date (an
    open-ended park is how a case disappears for a year). Both of those ask for one sentence, and
    that sentence is the thing the next person actually reads.
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

    # ANY BUCKET, ANY TIME. The configured routes describe the normal path and decide which
    # button is offered first - they do not fence the claim in. Work goes wrong: a claim is
    # moved in error, a step turns out not to apply, something has to jump. Refusing that would
    # only teach people to work around the system, and then it stops describing reality.
    #
    # An off-route move is still recorded as exactly that, so the history shows it was unusual.
    off_route = rule is None
    if off_route:
        order = [b["bucket_key"] for b in await buckets()]
        try:
            kind = "back" if order.index(to_key) < order.index(cur_key) else "forward"
        except ValueError:
            kind = "forward"
        if dest.get("is_park"):
            kind = "park"
        elif src.get("is_park"):
            kind = "resume"
    else:
        kind = rule.get("kind", "forward")

    # THE ONE FENCE. Everything above says a claim may go anywhere, and that stays true except
    # for this single route: once drafting has started, the claim does not drift back to Live
    # Cases (founder, 19 Sep). A draft query is the legitimate way to ask Live Cases for
    # something, and since 19 Sep that does it WITHOUT moving the claim - so a backward move here
    # is now always either a mistake or a genuine reversal, and a genuine reversal is a
    # super-admin's call. Theirs still works, and is recorded as a pull-back.
    if kind == "back" and cur_key in NO_RETURN_TO_LIVE and to_key == QUERY_TO \
            and (actor_role or "") != SUPER:
        return {"ok": False, "error":
                ("Drafting has started on this claim, so it does not go back to Live Cases. "
                 "If something is missing, raise a draft query - the claim stays here and Live "
                 "Cases is told. A super admin can pull it back if it truly has to move."
                 if cur_key == QUERY_FROM else
                 "This claim has been escalated to the insurer, so it does not go back to Live "
                 "Cases. Raise an escalation query if something is needed - the claim stays "
                 "here. A super admin can pull it back if it truly has to move.")}

    # What is still blank, worked out BEFORE we ask for the comment - so the one prompt can say
    # both things at once. Leaving a bucket forwards means finishing it; going back or parking is
    # explicitly not finishing, so blank fields only matter on the way forward.
    missing = await missing_required(claim_id, cur_key) if kind == "forward" else []

    # GROUND RULE: every move carries a comment, forwards as well as backwards.
    #
    # The person receiving the claim in the next bucket starts cold. They need to know what was
    # done, what is still pending and what to do next - and the only person who can tell them is
    # the one letting go of it. A bucket system without this degenerates into claims appearing
    # in queues with no explanation, which is exactly the silence it was built to end.
    #
    # Note what this is NOT: it is not a gate on the claim being tidy. Nothing here refuses a
    # move because a field is blank or a bucket was skipped. It asks for one sentence, and that
    # sentence is the thing the next person actually reads.
    if not (reason or "").strip() and not force:
        if kind == "back":
            return {"ok": False,
                    "error": "Say what is wrong - the person who sent it forward needs to know."}
        if kind == "park":
            return {"ok": False, "error": "Say why this is being paused."}
        if missing:
            names = ", ".join(m["label"] for m in missing[:4])
            return {"ok": False, "missing": missing, "needs_override": True,
                    "error": "Still blank: %s. You can move it anyway - say why, and the next "
                             "bucket will see your note." % names}
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

    # (`missing` was worked out above, before the comment prompt, so one ask covers both.)

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
            # The flag the next person sees: set on a backward move, cleared once the claim goes
            # forward again. A park and its return leave it as it was.
            if kind == "back":
                await c.execute(
                    "UPDATE nidaan_claims SET back_at=CURRENT_TIMESTAMP, back_by=?, back_by_role=?, "
                    "back_from=?, back_reason=? WHERE claim_id=?",
                    ((actor or "")[:80], (actor_role or "")[:20], src.get("name_en", cur_key)[:60],
                     (reason or "").strip()[:400], int(claim_id)))
            elif kind == "forward":
                await c.execute(
                    "UPDATE nidaan_claims SET back_at=NULL, back_by='', back_by_role='', "
                    "back_from='', back_reason='' WHERE claim_id=?", (int(claim_id),))
                # A draft query lives and dies inside Pending Draft — it no longer travels with
                # the claim (founder, 19 Sep). So when the claim finally leaves Pending Draft
                # forwards, the query goes with it: still open means somebody moved on without
                # formally answering, and their move note becomes the answer; already resolved
                # means it is simply finished.
                _qs = (row.get("query_state") or "")
                if cur_key == QUERY_FROM and _qs == "open":
                    await c.execute(
                        "UPDATE nidaan_claims SET query_state='resolved', query_resolved_by=?, "
                        "query_resolved_at=CURRENT_TIMESTAMP, query_resolved_note=? WHERE claim_id=?",
                        ((actor or "")[:80], (reason or "").strip()[:400], int(claim_id)))
                elif cur_key == QUERY_FROM and _qs == "resolved":
                    await c.execute("UPDATE nidaan_claims SET query_state='' WHERE claim_id=?",
                                    (int(claim_id),))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("bucket move failed for %s: %s", claim_id, e)
        return {"ok": False, "error": "Could not save that. Try again."}

    verb = {"back": ("pulled back by a super admin to" if (actor_role or "") == SUPER
                     else "sent back to"),
            "park": "parked in", "resume": "resumed into"}.get(kind, "moved to")
    summary = "%s -> %s %s%s" % (src.get("name_en", cur_key), verb, dest["name_en"],
                                 " (off the usual path)" if off_route else "")
    if day:
        summary += " until %s" % day
    # A field that was still blank when the claim moved on is part of the record, not a footnote.
    # The next bucket should not have to discover it.
    if missing:
        summary += " [left blank: %s]" % ", ".join(m["label"] for m in missing[:4])
    if (reason or "").strip():
        summary += " - %s" % reason.strip()
    await _log(claim_id, summary, actor)

    who = (row.get("complainant_name") or row.get("insured_name") or "").strip()
    if not quiet:          # the draft query sends its own, more specific alert
        await _notify_move(claim_id, to_key=to_key, to_name=dest["name_en"],
                           from_name=src.get("name_en", cur_key), kind=kind,
                           reason=reason, actor=actor, who=who)
        if kind == "back":
            await _notify_sender_back(claim_id, to_name=dest["name_en"], reason=reason,
                                      actor=actor, who=who)

    return {"ok": True, "bucket": to_key, "name": dest["name_en"], "sub": sub, "kind": kind,
            "off_route": off_route}


# ══ The draft query ════════════════════════════════════════════════════════════
QUERY_FROM = "pending_draft"
QUERY_TO = "live_cases"

# Buckets a claim does not drift back to Live Cases from.
#
# Pending Draft was the original fence (founder, 19 Sep): once drafting starts, a backward move is
# either a mistake or a genuine reversal, and a reversal is a super-admin's call. Escalation joins
# it for the same reason and a stronger one - the insurer has already been written to, so "back to
# Live Cases" describes something that did not happen (founder, 21 Sep).
#
# Lokpal is deliberately NOT here yet: it was not asked for, and a fence nobody requested is the
# kind of thing that gets worked around. Adding it later is this one line.
NO_RETURN_TO_LIVE = (QUERY_FROM, "escalation")



async def _supers_only() -> list:
    """The three super admins - not the wider admin group (founder: 'alert superadmin and the
    respective staff')."""
    async with aiosqlite.connect(DB_PATH) as c:
        return [r[0] for r in await (await c.execute(
            "SELECT staff_id FROM nidaan_staff WHERE role='super_admin' AND status='active' "
            "AND deleted_at IS NULL")).fetchall()]


async def _staff_row(staff_id) -> Optional[dict]:
    if not staff_id:
        return None
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT staff_id, name, role FROM nidaan_staff WHERE staff_id=? AND status='active' "
            "AND deleted_at IS NULL", (int(staff_id),))).fetchone()
    return dict(r) if r else None


async def _claim_handlers(claim_id: int, row: dict) -> list:
    ids = []
    if row.get("assigned_to_staff_id"):
        ids.append(int(row["assigned_to_staff_id"]))
    async with aiosqlite.connect(DB_PATH) as c:
        for (sid,) in await (await c.execute(
                "SELECT staff_id FROM nidaan_claim_assignees WHERE claim_id=?", (int(claim_id),))).fetchall():
            if sid and int(sid) not in ids:
                ids.append(int(sid))
    return ids


async def raise_query(claim_id: int, text: str, *, actor: str, actor_id=None,
                      actor_role: str = "") -> dict:
    """The doctor/advocate in Pending Draft cannot finish: the claim is marked DRAFT QUERY and the
    people who can fix it are told now - not left to find it.

    THE CLAIM DOES NOT MOVE. It used to be sent back to Live Cases, which made a question look
    like a reversal: the case left the bucket it was being written in, the drafter lost sight of
    it, and the history read as though the work had been undone. The founder's rule (19 Sep):
    "Only status changing draft query, should not be moving anywhere." So the status changes, the
    right people are told, and the claim stays exactly where the work is.
    """
    text = (text or "").strip()
    if len(text) < 5:
        return {"ok": False, "error": "Say what is needed - the Live Cases team starts from your words."}
    row = await _claim_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case does not exist."}
    if (row.get("pipeline_stage") or "") != QUERY_FROM:
        return {"ok": False, "error": "A draft query is raised from Pending Draft."}
    if (row.get("query_state") or "") == "open":
        return {"ok": False, "error": "There is already an open query on this claim."}
    await _log(claim_id, "\u2753 Draft query raised: " + text[:380], actor)
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "UPDATE nidaan_claims SET query_state='open', query_text=?, query_by=?, query_by_id=?, "
            "query_at=CURRENT_TIMESTAMP, query_round=COALESCE(query_round,0)+1, "
            "query_resolved_by='', query_resolved_at=NULL, query_resolved_note='', "
            "query_mo_id=NULL, query_mo_name='' WHERE claim_id=?",
            (text[:1000], (actor or "")[:80], actor_id, int(claim_id)))
        await c.commit()
    # Who is told: Live Cases' duty staff and the claim's own handlers - never just a queue.
    import biz_nidaan as _n
    import biz_nidaan_notifications as _nnot
    try:
        ids = list(await _n.on_duty_rep_ids(QUERY_TO))
    except Exception:
        ids = []
    for sid in await _claim_handlers(claim_id, row):
        if sid not in ids:
            ids.append(sid)
    if actor_id in ids:
        ids.remove(actor_id)
    fallback = not ids
    if fallback:
        ids = [a["staff_id"] for a in await _nnot._super_admin_staff()]
    who = (row.get("complainant_name") or row.get("insured_name") or "").strip()
    rnd = int(row.get("query_round") or 0) + 1
    subj = "\u2753 Draft query \u2014 NP-%s %s" % (claim_id, who)
    body = ("%s raised a draft query on NP-%s%s.\n\n\u201c%s\u201d\n\n"
            "The claim stays in Pending Draft. Fix this, then press \u2705 Query resolved on the "
            "claim in Level-2 \u2192 Settlement \u2192 Pending Draft." % (
                actor or "Someone", claim_id, (" (round %d)" % rnd) if rnd > 1 else "",
                text[:600]))
    if fallback:
        body += "\n\n\u26a0 Nobody is on duty for Live Cases, so this came to the admins."
    try:
        await _nnot.notify_staff_inapp(ids, subj, body, event_key="case.draft_query",
                                       email=True, claim_id=claim_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("draft query alert failed for %s: %s", claim_id, e)
    return {"ok": True, "told": len(ids), "round": rnd}


async def resolve_query(claim_id: int, mo_staff_id, note: str, *, actor: str, actor_id=None,
                        actor_role: str = "") -> dict:
    """Live Cases has fixed the query: the claim is handed to the doctor/advocate chosen - one
    place at a time - and that person is told it is theirs again.

    As with raise_query, THE CLAIM DOES NOT MOVE: it never left Pending Draft, so there is nothing
    to send back. What changes is who owns it and that the question is answered.
    """
    note = (note or "").strip()
    if len(note) < 3:
        return {"ok": False, "error": "Say what was done - the doctor/advocate reads this first."}
    row = await _claim_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case does not exist."}
    if (row.get("query_state") or "") != "open" or (row.get("pipeline_stage") or "") != QUERY_FROM:
        return {"ok": False, "error": "This claim has no open draft query in Pending Draft."}
    mo = await _staff_row(mo_staff_id)
    if not mo:
        return {"ok": False, "error": "Pick the doctor or advocate it goes back to."}
    await _log(claim_id, "\u2705 Draft query resolved \u2014 for %s: %s"
               % (mo["name"], note[:300]), actor)
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "UPDATE nidaan_claims SET query_state='resolved', query_resolved_by=?, "
            "query_resolved_at=CURRENT_TIMESTAMP, query_resolved_note=?, query_mo_id=?, "
            "query_mo_name=? WHERE claim_id=?",
            ((actor or "")[:80], note[:1000], mo["staff_id"], mo["name"][:80], int(claim_id)))
        if not await (await c.execute(
                "SELECT 1 FROM nidaan_claim_assignees WHERE claim_id=? AND staff_id=?",
                (int(claim_id), mo["staff_id"]))).fetchone():
            await c.execute(
                "INSERT INTO nidaan_claim_assignees (claim_id, staff_id, assigned_by, assigned_at) "
                "VALUES (?,?,?,CURRENT_TIMESTAMP)", (int(claim_id), mo["staff_id"], actor_id))
        await c.commit()
    import biz_nidaan_notifications as _nnot
    ids = [mo["staff_id"]]
    if row.get("query_by_id") and int(row["query_by_id"]) not in ids:
        ids.append(int(row["query_by_id"]))
    who = (row.get("complainant_name") or row.get("insured_name") or "").strip()
    subj = "\u2705 Draft query resolved \u2014 NP-%s %s" % (claim_id, who)
    body = ("NP-%s is yours again in Pending Draft, %s.\n\n%s: \u201c%s\u201d\n\n"
            "The query was: \u201c%s\u201d" % (claim_id, mo["name"], actor or "Live Cases",
                                                 note[:600], (row.get("query_text") or "")[:400]))
    try:
        await _nnot.notify_staff_inapp(ids, subj, body, event_key="case.draft_query_resolved",
                                       email=True, claim_id=claim_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("query resolved alert failed for %s: %s", claim_id, e)
    return {"ok": True, "to": mo["name"]}


async def contact_recipients(claim_id: int) -> dict:
    """Who a query message goes to: the complainant, and by email in copy the branch/subscriber/
    partner who brought the claim."""
    row = await _claim_row(claim_id) or {}
    to = {"name": (row.get("complainant_name") or row.get("insured_name") or "").strip(),
          "phone": (row.get("complainant_phone") or row.get("insured_phone") or "").strip(),
          "email": (row.get("complainant_email") or row.get("insured_email") or "").strip()}
    cc = []
    try:
        import biz_nidaan_doc_request as _dr
        for p in await _dr.recipients(claim_id):
            if p.get("kind") == "cc" and p.get("email") and p["email"].lower() != to["email"].lower():
                cc.append({"label": p.get("label") or p.get("role") or "", "name": p.get("name") or "",
                           "email": p["email"]})
    except Exception as e:  # noqa: BLE001
        logger.info("query cc lookup failed for %s: %s", claim_id, e)
    # Can we actually reach this person on WhatsApp today? Somebody who replied STOP must be
    # visible as STOPPED before a staffer types a message to them, not after it silently fails;
    # and the daily/weekly allowance is worth showing for the same reason.
    wa = {}
    if to["phone"]:
        try:
            import biz_nidaan_whatsapp as _w, biz_nidaan_wa_guard as _g
            wa = await _g.summary(_w.normalize_msisdn(to["phone"])) or {}
        except Exception as e:  # noqa: BLE001
            logger.info("whatsapp reachability lookup failed for %s: %s", claim_id, e)
    return {"to": to, "cc": cc, "asked": _query_info(row).get("asked"), "wa": wa}


async def send_query_to_complainant(claim_id: int, text: str, *, whatsapp: bool, email: bool,
                                    cc: bool, actor: str, actor_id=None) -> dict:
    """ONE query message to the complainant - the exact words, not a stream. A second is refused
    while the first is unanswered for 24 hours; the answer is to call them."""
    text = " ".join((text or "").split())
    if len(text) < 5:
        return {"ok": False, "error": "Write what the complainant must send or answer."}
    if len(text) > 300:
        return {"ok": False, "error": "Keep it to one clear ask (under 300 characters)."}
    if not (whatsapp or email):
        return {"ok": False, "error": "Choose WhatsApp, email or both."}
    row = await _claim_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case does not exist."}
    asked = _query_info(row).get("asked")
    if asked and not asked.get("replied"):
        since = _days_since(row.get("cq_at"))
        async with aiosqlite.connect(DB_PATH) as c:
            fresh = await (await c.execute(
                "SELECT 1 FROM nidaan_claims WHERE claim_id=? AND cq_at > datetime('now','-24 hours')",
                (int(claim_id),))).fetchone()
        if fresh:
            return {"ok": False, "error": "A query already went to the complainant (%s, by %s) and they "
                    "have not answered yet. One message, not a stream - call them, or wait for the "
                    "reply." % (str(row.get("cq_at"))[:16], row.get("cq_by") or "staff")}
    rec = await contact_recipients(claim_id)
    out = {"ok": False, "whatsapp": None, "email": None, "cc": []}
    sent = []
    if whatsapp:
        if not rec["to"]["phone"]:
            out["whatsapp"] = {"ok": False, "error": "no phone number on the claim"}
        else:
            import biz_nidaan_wa_orchestrator as _orch
            r = await _orch.wa_journey(claim_id, "doc_reminder", {"doc_label": text})
            out["whatsapp"] = {"ok": bool(r.get("ok")), "error": r.get("error") or ""}
            if r.get("ok"):
                sent.append("WhatsApp")
    if email:
        if not rec["to"]["email"]:
            out["email"] = {"ok": False, "error": "no email address on the claim"}
        else:
            import biz_nidaan_doc_request as _dr
            first = (rec["to"]["name"] or "").split(" ")[0] or "ji"
            msg = ("Namaste %s,\n\nTo move your claim (Ref NP-%s) forward, we still need:\n\n"
                   "%s\n\nPlease reply to this email, or send it on WhatsApp to +91 91836 86384.\n\n"
                   "Thank you,\nTeam NidaanPartner" % (first, claim_id, text))
            ok, err = await _dr._mail(rec["to"]["email"], "NP-%s: one thing we need for your claim"
                                      % claim_id, msg, claim_id)
            out["email"] = {"ok": ok, "error": err}
            if ok:
                sent.append("email")
            if ok and cc:
                for p in rec["cc"]:
                    cmsg = ("For your information: we have asked %s (NP-%s) for the following:\n\n%s\n\n"
                            "\u2014 Team NidaanPartner" % (rec["to"]["name"] or "the complainant", claim_id, text))
                    cok, cerr = await _dr._mail(p["email"], "Copy \u2014 NP-%s: we asked the complainant "
                                                "for one thing" % claim_id, cmsg, claim_id)
                    out["cc"].append({"to": p["label"], "ok": cok, "error": cerr})
    if not sent:
        return dict(out, error="Nothing was sent - " + "; ".join(
            "%s: %s" % (k, v["error"]) for k, v in (("WhatsApp", out["whatsapp"]), ("Email", out["email"]))
            if v and not v.get("ok")))
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "UPDATE nidaan_claims SET cq_at=CURRENT_TIMESTAMP, cq_by=?, cq_by_id=?, cq_text=?, "
            "cq_channels=?, cq_reply_at=NULL WHERE claim_id=?",
            ((actor or "")[:80], actor_id, text, "+".join(sent), int(claim_id)))
        await c.commit()
    copies = [x["to"] for x in out["cc"] if x.get("ok")]
    await _log(claim_id, "\U0001f4e8 Query sent to the complainant by %s via %s%s: %s" % (
        actor or "staff", " and ".join(sent), (" (copy: %s)" % ", ".join(copies)) if copies else "",
        text), actor)
    out["ok"] = True
    return out


async def on_query_reply(msisdn: str, mtype: str, text: str = "") -> int:
    """A complainant wrote on WhatsApp. If a query to them is waiting for an answer, the super
    admins and the staff member who sent it are told now, with what they said."""
    digits = "".join(ch for ch in (msisdn or "") if ch.isdigit())[-10:]
    if len(digits) < 10:
        return 0
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, complainant_name, insured_name, cq_by, cq_by_id, cq_text, cq_at "
            "FROM nidaan_claims WHERE cq_at IS NOT NULL "
            "AND (cq_reply_at IS NULL OR cq_reply_at < cq_at) "
            "AND (substr(replace(replace(COALESCE(complainant_phone,''),'+',''),' ',''),-10)=? "
            "  OR substr(replace(replace(COALESCE(insured_phone,''),'+',''),' ',''),-10)=?)",
            (digits, digits))).fetchall()]
        for r in rows:
            await c.execute("UPDATE nidaan_claims SET cq_reply_at=CURRENT_TIMESTAMP WHERE claim_id=?",
                            (r["claim_id"],))
        await c.commit()
    if not rows:
        return 0
    import biz_nidaan_notifications as _nnot
    said = (text or "").strip()[:300] if mtype in ("text", "button", "interactive") else ""
    what = ("\u201c%s\u201d" % said) if said else ("\U0001f4ce a %s" % (mtype or "message"))
    for r in rows:
        ids = await _supers_only()
        if r.get("cq_by_id") and int(r["cq_by_id"]) not in ids:
            ids.append(int(r["cq_by_id"]))
        who = (r.get("complainant_name") or r.get("insured_name") or "").strip()
        subj = "\U0001f4ac Query answered \u2014 NP-%s %s" % (r["claim_id"], who)
        body = ("%s replied on WhatsApp to the query sent by %s (%s).\n\nThe query: \u201c%s\u201d\n"
                "Their reply: %s\n\nOpen the WhatsApp inbox or the case in Level-2 \u2192 Settlement."
                % (who or "The complainant", r.get("cq_by") or "staff", str(r.get("cq_at") or "")[:16],
                   (r.get("cq_text") or "")[:300], what))
        try:
            await _nnot.notify_staff_inapp(ids, subj, body, event_key="case.query_reply",
                                           email=False, claim_id=r["claim_id"])
            await _log(r["claim_id"], "\U0001f4ac Complainant answered the query on WhatsApp: %s"
                       % (said or (mtype or "message")), "complainant")
        except Exception as e:  # noqa: BLE001
            logger.warning("query reply alert failed for %s: %s", r["claim_id"], e)
    return len(rows)


async def query_reminders() -> dict:
    """Every morning an open draft query is still open, Live Cases hears about it again; after 3
    days the super admins do too. Silence while it is open is exactly ClaimShield's failure."""
    import biz_nidaan as _n
    import biz_nidaan_notifications as _nnot
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, complainant_name, insured_name, query_text, query_by, query_at "
            "FROM nidaan_claims WHERE query_state='open' AND pipeline_stage=?", (QUERY_FROM,))).fetchall()]
    if not rows:
        return {"open": 0, "sent": 0}
    try:
        duty = list(await _n.on_duty_rep_ids(QUERY_TO))
    except Exception:
        duty = []
    admins = await _supers_only()
    today = _today_ist().isoformat()
    sent = 0
    for r in rows:
        days = _days_since(r.get("query_at")) or 0
        if not await _alert_once("draft_query_open:%s:%s" % (r["claim_id"], today)):
            continue
        ids = list(duty) or list(admins)
        if days >= 3:
            ids += [a for a in admins if a not in ids]
        who = (r.get("complainant_name") or r.get("insured_name") or "").strip()
        subj = "\u2753 Draft query still open (%d day%s) \u2014 NP-%s %s" % (
            days, "" if days == 1 else "s", r["claim_id"], who)
        body = ("Raised by %s: \u201c%s\u201d\n\nResolve it in Level-2 \u2192 Settlement \u2192 "
                "Live Cases (\u2705 Query resolved)." % (r.get("query_by") or "staff",
                                                        (r.get("query_text") or "")[:400]))
        if days >= 3:
            body += "\n\nIt has been open %d days, so the super admins are told too." % days
        try:
            await _nnot.notify_staff_inapp(ids, subj, body, event_key="case.draft_query_open",
                                           email=False, claim_id=r["claim_id"])
            sent += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("draft query reminder failed for %s: %s", r["claim_id"], e)
    return {"open": len(rows), "sent": sent}


# What the insurer came back with, and where that sends the case. Straight off the founder's
# flow map (19 Sep):
#
#     Escalated ──no reply──> reminder 1 → 2 → 3 ──> Lokpal
#               └─reply──┬── yes ──────────────────> Complete
#                        ├── no ───────────────────> Lokpal
#                        └── query ──> we answer ──┬─ yes ─> Complete
#                                                  └─ no ──> Lokpal
#
# Complete and Lokpal are BUCKETS, not statuses - they are where the case goes next. Query is the
# one reply that keeps the case here, because it turns the waiting around: until now we were
# waiting on them, and from here they are waiting on us.
ESC_REPLIES = {
    "accepted": ("completed", "escalation_settlement",
                 "\u2705 Insurer accepted at escalation"),
    "refused": ("lokpal", "", "\u26d4 Insurer refused at escalation \u2014 going to Lokpal"),
    "query": ("", "query", "\u2753 Insurer raised a query"),
}

# THESE TWO NO LONGER MOVE ANYTHING (founder, 21 Sep). They were a dropdown that closed a case or
# sent it to Lokpal - the software deciding the outcome from a menu choice. The buttons came off
# the screen with the rest of #8; this is the endpoint behind them, refused so that an old page
# still open in somebody's browser cannot move a claim either.
#
# The entries stay in ESC_REPLIES on purpose: their labels are what the existing remarks on real
# claims were written from, and deleting them would make that history unreadable.
DECIDED_BY_A_PERSON = ("accepted", "refused")


async def escalation_reply(claim_id: int, outcome: str, *, note: str = "", actor: str = "",
                           actor_role: str = "") -> dict:
    """Record what the insurer said, and let that decide where the case goes.

    A person records the fact; the routing is not a judgement the system makes on its own. Nothing
    here is automatic - it runs because somebody read a letter and pressed a button.
    """
    outcome = (outcome or "").strip().lower()
    if outcome in DECIDED_BY_A_PERSON:
        return {"ok": False, "error":
                "Where the case goes next is not recorded here any more. Write down what the "
                "insurer said, then use Move \u2014 to Completed if they have settled, to Lokpal if "
                "they have refused. A person decides, not the form."}
    if outcome not in ESC_REPLIES:
        return {"ok": False, "error": "Say what the insurer asked."}
    note = (note or "").strip()
    if len(note) < 3:
        return {"ok": False, "error": "Say what they wrote \u2014 the next person starts from it."}

    row = await _claim_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case does not exist."}
    if (row.get("pipeline_stage") or "") != "escalation":
        return {"ok": False, "error": "This case is not in Escalation."}
    sub = (row.get("pipeline_sub") or "")
    if sub not in ("escalated", "query"):
        return {"ok": False,
                "error": "Record the escalation date first \u2014 there is nothing for them to "
                         "have replied to yet."}

    to_key, to_sub, label = ESC_REPLIES[outcome]
    if not to_key:
        # A query keeps the case here. A second query is allowed and recorded: insurers do come
        # back more than once, and pretending otherwise would push people to lie to the system.
        res = await set_substate(claim_id, to_sub, actor=actor)
        if not res.get("ok"):
            return res
        await _log(claim_id, "%s: %s" % (label, note[:300]), actor)
        return {"ok": True, "outcome": outcome, "stayed": True}

    res = await move(claim_id, to_key, sub=to_sub,
                     reason="%s \u2014 %s" % (label, note[:300]),
                     actor=actor, actor_role=actor_role)
    if not res.get("ok"):
        return res
    return {"ok": True, "outcome": outcome, "moved_to": to_key}


async def escalation_due() -> dict:
    """What the escalation bucket needs a person to do today.

    The clock is fixed and public: a reminder at day 10, another at 20, a third at 30, and if the
    insurer has still said nothing after the third, the case goes to Lokpal. None of that happens
    by itself. This works out what is due and says so; a person sends the reminder and a person
    moves the case, which is the founder's rule for this whole stage (19 Sep): "Staff will take
    action manually, if we automate then it will over complicated and break things."

    Returns {ok, reminders: [...], lokpal: [...]} - reminders that should have gone by now, and
    cases that have run out of reminders.
    """
    out = {"ok": True, "reminders": [], "lokpal": [], "owed": []}
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, COALESCE(complainant_name,'') AS complainant_name, "
            "       COALESCE(insured_name,'') AS insured_name, COALESCE(pipeline_sub,'') AS sub, "
            "       pipeline_stage_at AS sub_at "
            "FROM nidaan_claims WHERE pipeline_stage='escalation' "
            "AND COALESCE(archived,0)=0 AND COALESCE(status,'') NOT IN ('closed','withdrawn')"
        )).fetchall()]
        if not rows:
            return out
        ids = [int(r["claim_id"]) for r in rows]
        marks = ",".join("?" * len(ids))
        vals = {}
        for f in await (await c.execute(
                "SELECT claim_id, field_key, value FROM nidaan_claim_fields "
                "WHERE claim_id IN (%s) AND field_key IN "
                "('escalation_date','esc_reminder_1','esc_reminder_2','esc_reminder_3')" % marks,
                ids)).fetchall():
            d = dict(f)
            vals.setdefault(int(d["claim_id"]), {})[d["field_key"]] = (d["value"] or "").strip()

    for r in rows:
        cid = int(r["claim_id"])
        v = vals.get(cid, {})
        started = v.get("escalation_date") or ""
        if not started:
            continue                       # not escalated yet; nothing is counting
        days = _days_since(started)
        if days is None:
            continue
        who = r["complainant_name"] or r["insured_name"]
        if r["sub"] == "query":
            # They answered, with a question. The reminder clock is for silence, and this is not
            # silence - chasing them now would be chasing somebody who is waiting on us.
            out["owed"].append({"claim_id": cid, "who": who, "days_since_escalation": days,
                                "waiting_days": _days_since(r.get("sub_at")) or 0})
            continue
        sent = [bool(v.get(k)) for k in ESC_REMINDER_FIELDS]
        # The first reminder that is due and has not been sent. Only one at a time: telling
        # somebody three reminders are overdue on one case helps nobody.
        nxt = None
        for i, due_day in enumerate(ESC_REMINDER_DAYS):
            if not sent[i]:
                nxt = (i + 1, due_day, days - due_day)
                break
        if nxt and nxt[2] >= 0:
            out["reminders"].append({
                "claim_id": cid, "who": who, "number": nxt[0], "due_day": nxt[1],
                "days_since_escalation": days, "overdue_by": nxt[2],
                "field": ESC_REMINDER_FIELDS[nxt[0] - 1]})
        elif all(sent) and days >= ESC_REMINDER_DAYS[-1]:
            # Three reminders sent and still here: the insurer has not answered.
            out["lokpal"].append({
                "claim_id": cid, "who": who, "days_since_escalation": days,
                "last_reminder": v.get(ESC_REMINDER_FIELDS[-1]) or ""})
    out["reminders"].sort(key=lambda x: -x["overdue_by"])
    out["lokpal"].sort(key=lambda x: -x["days_since_escalation"])
    out["owed"].sort(key=lambda x: -x["waiting_days"])
    return out


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
    "c.review_outcome, c.l2_payment_status, c.payment_status, c.assigned_to_staff_id, "
    "c.created_at, "
    "c.pipeline_stage, c.pipeline_sub, c.pipeline_stage_at, c.pipeline_entered_at, "
    "c.pipeline_by, c.pipeline_from, c.hold_until, c.raised_by_name, c.raised_via, "
    "c.channel_partner_id, c.origin, c.back_at, c.back_by, c.back_by_role, c.back_from, "
    "c.back_reason, c.query_state, c.query_text, c.query_by, c.query_by_id, c.query_at, c.query_round, "
    "c.query_resolved_by, c.query_resolved_at, c.query_resolved_note, c.query_mo_name, "
    "c.cq_at, c.cq_by, c.cq_reply_at"
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


# ── saying why a claim is sitting here ───────────────────────────────────────
# This is the whole reason the office is moving off ClaimShield. There, a claim sat in a bucket
# and nobody could tell you what it was waiting for without opening it. Every fact needed to
# answer that is already on the row - who we are waiting for, how long, what is missing, what
# the last person said. It just has to be said out loud.

_WAIT_WORDS = {
    "complainant": "the complainant",
    "insurer": "the insurance company",
    "lokpal": "the forum",
    "internal": "us",
    "none": "nobody",
}


def _why_here(item: dict, note: str, missing: list) -> tuple:
    """One sentence for WHY, a few words for WHAT IS PENDING.

    Ordered by what actually decides the next action, not by what is easiest to compute: a
    closing Lokpal window outranks everything, then a pause with a date, then documents, then a
    required field, then the plain "who are we waiting for and how long".
    """
    days = item.get("days")
    who = _WAIT_WORDS.get(item.get("waits_on") or "internal", "us")
    dn, dt = item.get("docs_done") or 0, item.get("docs_total") or 0
    state = item.get("age_state") or "ok"

    # The clock that never resets.
    left = item.get("lokpal_days_left")
    if left is not None and left <= 30:
        return (("The one-year window closes in %d days." % left) if left > 0
                else "The one-year window has CLOSED.", "file at the forum")

    if item.get("hold_until"):
        return ("Paused until %s." % str(item["hold_until"])[:10], "nothing until then")

    # Documents are gathered in L2 Claims, before the handover. Past that point the checklist is
    # not what a claim is waiting for - except in Pending Docs, where it is the whole job.
    if dt and dn < dt and item.get("bucket") == "pending_docs":
        short = dt - dn
        # Documents come from the COMPLAINANT. They are who has them and who the document window
        # asks. The bucket's waits_on is about who owes the next move on the CASE - a different
        # question, and using it here told staff to chase the insurance company for the
        # complainant's hospital bills.
        base = ("None of the %d document(s) have arrived yet." % dt if dn == 0
                else "Still waiting for %d of the %d document(s)." % (short, dt))
        base += " We are asking the complainant."
        if state == "red":
            base += " Asked %d days ago, nothing back." % (days or 0)
        return (base, "%d document(s) from the complainant" % short)

    if missing:
        names = ", ".join(m["label"] for m in missing[:2])
        return ("Cannot move on until %s %s recorded."
                % (names, "is" if len(missing) == 1 else "are"),
                "fill in %s" % names)

    step = (item.get("sub_name") or "").strip()
    if state == "red":
        return ("Waiting on %s for %d days - past the %d-day limit."
                % (who, days or 0, item.get("red_days") or 0),
                ("chase %s" % who) if who != "us" else "this is ours to move")
    if state == "amber":
        return ("Waiting on %s for %d days." % (who, days or 0),
                ("chase %s" % who) if who != "us" else "ours to move")
    if step:
        return ("On '%s', waiting on %s." % (step, who), step.lower())
    if who == "us":
        return ("Ours to move - here %s." % (("%d day(s)" % days) if days else "since today"),
                "our next step")
    return ("Waiting on %s%s." % (who, (" for %d day(s)" % days) if days else ""),
            "waiting on %s" % who)


async def _last_notes(claim_ids: list) -> dict:
    """The comment the last person left when they moved each claim. Every move carries one, so
    this is never empty for a claim that got here by being moved."""
    if not claim_ids:
        return {}
    out: dict = {}
    ph = ",".join("?" * len(claim_ids))
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = await (await c.execute(
            "SELECT claim_id, summary, actor, created_at FROM nidaan_claim_activity "
            "WHERE claim_id IN (%s) AND kind='case_bucket' ORDER BY act_id DESC" % ph,
            [int(i) for i in claim_ids])).fetchall()
    for r in rows:
        d = dict(r)
        if d["claim_id"] in out:
            continue
        txt = (d.get("summary") or "").strip()
        # The summary is "From -> to - the comment". The comment is what a person wants to read.
        if " - " in txt:
            txt = txt.split(" - ", 1)[1].strip()
        out[d["claim_id"]] = {"note": txt[:300], "by": (d.get("actor") or "").strip(),
                              "at": d.get("created_at")}
    return out


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
    # How many FILES are on each claim. In Level-2 that is the useful number - NP-119 had eight
    # attached and its checklist said 0/4, because they were attached without saying which line
    # each one answered.
    files: dict = {}
    if ids:
        async with aiosqlite.connect(DB_PATH) as c:
            ph = ",".join("?" * len(ids))
            for cid_, n_ in await (await c.execute(
                    "SELECT claim_id, COUNT(*) FROM nidaan_claim_documents WHERE claim_id IN (%s) "
                    "GROUP BY claim_id" % ph, ids)).fetchall():
                files[cid_] = n_

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
            # The INSURER's own claim number, off the rejection letter. Every letter, email and
            # Ombudsman form quotes it, so staff were opening each claim to read a number they
            # need before they can write a sentence (founder, 19 Sep). Already loaded with the
            # claim's other fields — nothing extra is fetched to show it.
            "insurer_claim_no": (vals.get("insurer_claim_no") or "").strip(),
            "claim_type": (r.get("claim_type") or "").strip(),
            "amount": r.get("disputed_amount") or 0,
            "bucket": bk, "bucket_name": b.get("name_en", bk), "bucket_icon": b.get("icon", ""),
            "sub": sk, "sub_name": sdef.get("name_en", ""),
            "days": days, "age_state": age_state(days, amber, red),
            "amber_days": amber, "red_days": red,
            "waits_on": sdef.get("waits_on") or b.get("waits_on") or "internal",
            "docs_done": done, "docs_total": total,
            "files": files.get(r["claim_id"], 0),
            "docs_ready": bool(total and done >= total),
            "origin": _origin_of(r),
            "assigned_to": r.get("assigned_to_staff_id"),
            "moved_by": (r.get("pipeline_by") or ""),
            "hold_until": (r.get("hold_until") or ""),
            "from_bucket": (r.get("pipeline_from") or ""),
            "lokpal_days_left": left,
            "created_at": r.get("created_at"),
            "back": _back_flag(r),
            "query": _query_info(r),
        })

    # WHY each one is sitting here, and WHAT is outstanding. Computed after the loop so the
    # notes and the missing-field lookups happen once for the page rather than once per row.
    notes = await _last_notes([i["claim_id"] for i in items])
    for i in items:
        miss = await missing_required(i["claim_id"], i["bucket"])
        why, pending = _why_here(i, (notes.get(i["claim_id"]) or {}).get("note", ""), miss)
        n = notes.get(i["claim_id"]) or {}
        i["why"] = why
        i["pending"] = pending
        i["note"] = n.get("note", "")
        i["note_by"] = n.get("by", "")
        i["missing_n"] = len(miss)

    order = {"red": 0, "amber": 1, "ok": 2}
    # An open draft query comes first, always - it is the one ClaimShield let go quiet.
    items.sort(key=lambda i: (0 if (i.get("query") or {}).get("state") == "open" else 1,
                              order.get(i["age_state"], 3), -(i["days"] or 0)))

    sub_counts: dict = {}
    for i in items:
        sub_counts[i["sub"]] = sub_counts.get(i["sub"], 0) + 1

    # A one-line summary for the top of the bucket: what is in here, and what needs a person.
    ours = sum(1 for i in items if (i.get("waits_on") or "internal") == "internal")
    return {"items": items[:limit], "matching": len(items),
            "sub_counts": sub_counts,
            "late": sum(1 for i in items if i["age_state"] in ("red", "amber")),
            "red": sum(1 for i in items if i["age_state"] == "red"),
            "ours": ours,
            "docs_short": sum(1 for i in items
                              if (i.get("docs_total") or 0) and not i.get("docs_ready")),
            "blocked_fields": sum(1 for i in items if i.get("missing_n")),
            "closing_window": sum(1 for i in items
                                  if i.get("lokpal_days_left") is not None
                                  and i["lokpal_days_left"] <= 30)}


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


def _query_info(row: dict) -> dict:
    st = (row or {}).get("query_state") or ""
    out = {}
    if st:
        out = {"state": st, "text": row.get("query_text") or "", "by": row.get("query_by") or "",
               "by_id": row.get("query_by_id"),
               "at": str(row.get("query_at") or ""), "round": int(row.get("query_round") or 0),
               "days": _days_since(row.get("query_at")),
               "resolved_by": row.get("query_resolved_by") or "",
               "resolved_at": str(row.get("query_resolved_at") or ""),
               "note": row.get("query_resolved_note") or "",
               "mo": row.get("query_mo_name") or ""}
    if row and row.get("cq_at"):
        rep = row.get("cq_reply_at")
        out["asked"] = {"at": str(row.get("cq_at") or ""), "by": row.get("cq_by") or "",
                        "text": row.get("cq_text") or "", "channels": row.get("cq_channels") or "",
                        "replied": bool(rep and str(rep) >= str(row.get("cq_at") or "")),
                        "reply_at": str(rep or "")}
    return out


def _back_flag(row: dict) -> dict:
    if not (row or {}).get("back_at"):
        return {}
    return {"at": str(row.get("back_at") or ""), "by": row.get("back_by") or "",
            "super": (row.get("back_by_role") or "") == SUPER,
            "from": row.get("back_from") or "", "reason": row.get("back_reason") or ""}


async def for_claim(claim_id: int, role: str = "") -> dict:
    """Everything the case report needs about where this claim is - and, for the person asking,
    which finished work they may not change."""
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
        # Credentials are masked for anyone whose role does not include them, on the way OUT.
        "fields": await fields(bk),
        "values": mask_secrets(await _clean_rich_values(vals), role),
        "may_see_secrets": may_see_secrets(role),
        "missing_required": await missing_required(claim_id, bk),
        "moves": await moves_from(bk),
        "hold_until": row.get("hold_until") or "",
        "from_bucket": row.get("pipeline_from") or "",
        "moved_by": row.get("pipeline_by") or "",
        "lokpal_days_left": await _lokpal_days_left(row, vals),
        "query": _query_info(row),
        "contact": {"name": (row.get("complainant_name") or row.get("insured_name") or "").strip(),
                    "phone": (row.get("complainant_phone") or row.get("insured_phone") or "").strip(),
                    "email": (row.get("complainant_email") or row.get("insured_email") or "").strip()},
        "locked": await locked_fields(row, role),
        # What is locked for everyone else - so a super admin is told their edit is an override.
        "locked_for_others": await locked_fields(row, ""),
        "is_super": (role or "") == SUPER,
        "back": _back_flag(row),
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
    """Rewrite any first-generation stage name as its bucket - on claims AND on the duty roster.

    The roster matters as much as the claims. A duty row still reading "consolidation" means
    on_duty_rep_ids("live_cases") finds nobody, so every arrival in that bucket is escalated to
    the admins with the note "nobody is on duty here" - while somebody is.
    """
    n = 0
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            for old, new in _LEGACY_STAGES.items():
                if old == new:
                    continue
                cur = await c.execute(
                    "UPDATE nidaan_claims SET pipeline_stage=? WHERE pipeline_stage=?", (new, old))
                n += cur.rowcount or 0
                cur = await c.execute(
                    "UPDATE nidaan_support_reps SET duty=? WHERE COALESCE(duty,'')=?", (new, old))
                n += cur.rowcount or 0
                cur = await c.execute(
                    "UPDATE nidaan_claims SET pipeline_from=? WHERE COALESCE(pipeline_from,'')=?",
                    (new, old))
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
            "review_outcome, l2_payment_status, payment_status, pipeline_stage "
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
            "payment_status, docs_complete_at, docs_complete_by, "
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
    # Documents are gathered HERE, in L2 Claims, before the handover - so that Level-2 starts
    # with the papers already in and can build the gist from them. The founder's rule: once a
    # person has ticked "all documents received", the claim can move. Ticking it is one click,
    # and it records whose word it is.
    if not row.get("docs_complete_at"):
        return {"ok": False, "needs_docs": True,
                "error": "Tick 'All documents received' first. Documents are collected here, "
                         "before Level-2, so the gist can be prepared from them."}

    # NOTHING BELOW REFUSES THE MOVE. Everything that is wrong is collected, shown to the
    # person doing it, and written onto the claim with their name - so the Level-2 team opens it
    # knowing exactly what was outstanding and who decided to send it anyway. A wall here only
    # taught people to route around the system; a recorded reason is what the next person can
    # actually act on.
    concerns = []
    if (row.get("review_outcome") or "").lower() != "can_fight":
        concerns.append("The review has not said this case can be fought yet.")
    if not l2_fee_covered(row):
        concerns.append("No Level-2 fee recorded - not on the claim, not a subscription.")
    rd = await readiness(claim_id)
    for b in (rd.get("blocks") or []):
        concerns.append("%s - %s" % (b["label"], b["detail"]))

    # The two acknowledgement tick-boxes are gone (founder, 16 Sep): "we are checking the box
    # before moving, and then moving it finally, so the popup box should not be coming". The
    # documents tick above is the real gate and it is made deliberately, a step earlier; asking
    # the same person to confirm the same thing twice taught them to tick without reading.
    # `checks` is still accepted, and still recorded when a caller sends it, so nothing that
    # already sent them breaks.
    checks = checks or {}
    if checks and not all(checks.get(q) for q in ("ack_docs_plan", "ack_contactable")):
        concerns.append("Handed over without confirming: %s" % ", ".join(
            {"ack_docs_plan": "that we know which documents this case needs",
             "ack_contactable": "that someone has actually spoken to the complainant"}[q]
            for q in ("ack_docs_plan", "ack_contactable") if not checks.get(q)))

    # The COMMENT is the one thing that is genuinely required, and it always was: the Level-2
    # team picks this up cold. When something is outstanding the note has to say why anyway.
    if not (note or "").strip():
        if concerns:
            return {"ok": False, "concerns": concerns, "readiness": rd,
                    "error": "Some things are still outstanding. You can hand it over anyway - "
                             "say why in the note, and the Level-2 team will see it."}
        return {"ok": False, "concerns": [], "readiness": rd,
                "error": "Add a short note for the Level-2 team - they pick this up cold."}

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "UPDATE nidaan_claims SET l2_handover_at=CURRENT_TIMESTAMP, l2_handover_by=?, "
                "l2_handover_note=?, l2_handover_checks=? WHERE claim_id=?",
                ((actor or "")[:80], (note or "").strip()[:600],
                 # What was NOT confirmed travels with the handover. Level-2 opening this claim
                 # can see both what intake checked and what they knowingly left open.
                 _json.dumps({**checks, "_open": concerns[:8]})[:2000], int(claim_id)))
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
    # AND THE WORK BEGINS (founder, 21 Sep: "as soon as any claim is moving from L2 claims, that
    # should be moving to Live cases, we can cut down 'To start' step"). Handing over and starting
    # were two acts with one meaning, and between them the claim belonged to nobody.
    #
    # If this fails the handover still stands - the claim is exactly where it used to sit before
    # somebody pressed Start, and the workspace still shows that list when it is not empty. A
    # half-done handover must never be a silent one.
    started = await start_l2(claim_id, actor=actor)
    if not started.get("ok"):
        logger.warning("handover started but start_l2 refused for %s: %s",
                       claim_id, started.get("error"))
    return {"ok": True, "handed_by": actor, "acknowledged_gaps": gaps,
            "started": bool(started.get("ok")),
            "bucket": started.get("bucket") or "", "bucket_name": started.get("name") or "",
            "start_error": "" if started.get("ok") else (started.get("error") or "")}


async def undo_handover(claim_id: int, *, reason: str = "", actor: str = "") -> dict:
    """Pull a claim back out of the Level-2 waiting list. Super-admin only, and recorded."""
    row = await _handover_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case does not exist."}
    if not row.get("l2_handover_at"):
        return {"ok": False, "error": "This claim has not been handed over."}
    # The handover now puts the claim straight into the entry bucket, so "it has a bucket" can no
    # longer mean "work has started". What means that is work: a move out of the entry bucket, or
    # anything recorded against the claim. Untouched in the entry bucket is still undoable, which
    # is the whole point of this function - an accidental handover must not be permanent.
    stage = (row.get("pipeline_stage") or "").strip()
    entry_key = ""
    for b in await buckets():
        if b.get("is_entry"):
            entry_key = b["bucket_key"]
            break
    # "Work has started" means the claim has been MOVED since it started. start_l2() leaves
    # pipeline_from empty; move() fills it with wherever the claim came from, so a non-empty one
    # is proof a person moved this claim. Deliberately not "has any field filled": the WhatsApp
    # document collection fills fields on the claim before Level-2 ever sees it, and counting
    # those would refuse to undo a handover nobody had touched.
    touched = True
    if stage and stage == entry_key:
        async with aiosqlite.connect(DB_PATH) as c:
            n = await (await c.execute(
                "SELECT COALESCE(pipeline_from,'') FROM nidaan_claims WHERE claim_id=?",
                (int(claim_id),))).fetchone()
        touched = bool((n[0] if n else "").strip())
    if stage and (stage != entry_key or touched):
        return {"ok": False,
                "error": "Level-2 work has already started on this claim - move it in the "
                         "workspace instead."}
    if not (reason or "").strip():
        return {"ok": False, "error": "Say why it is being pulled back."}
    async with aiosqlite.connect(DB_PATH) as c:
        await c.execute(
            "UPDATE nidaan_claims SET l2_handover_at=NULL, l2_handover_by='', "
            "l2_handover_note='', l2_handover_checks='', pipeline_stage='', pipeline_sub='', "
            "pipeline_entered_at=NULL, pipeline_stage_at=NULL, pipeline_by='', pipeline_from='' "
            "WHERE claim_id=?", (int(claim_id),))
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
            # All three routes we sell the work through, matching l2_fee_covered(). The old
            # single-route test hid every subscription claim from this list.
            "AND (LOWER(COALESCE(c.l2_payment_status,''))='paid' "
            "     OR LOWER(COALESCE(c.payment_status,'')) IN ('paid','subscription')) "
            "ORDER BY c.created_at ASC LIMIT ?" % _CLAIM_COLS, (int(limit),))).fetchall()]
    return [{"claim_id": r["claim_id"],
             "who": (r.get("complainant_name") or r.get("insured_name") or "").strip(),
             "insurer": (r.get("insurer_name") or "").strip(),
             "amount": r.get("disputed_amount") or 0,
             "origin": _origin_of(r),
             "waiting_days": _days_since(r.get("created_at"))} for r in rows]


# ── telling the next bucket ──────────────────────────────────────────────────
# A claim arriving in a queue nobody is watching is the failure this whole system exists to
# prevent. So every move tells the people on duty for the bucket it lands in - and, when a claim
# is sent BACK, the person who sent it forward, because they are the one who has to fix it.
#
# Never raises into a move: a notification that fails must not undo work that succeeded.

async def _notify_move(claim_id: int, *, to_key: str, to_name: str, from_name: str,
                       kind: str, reason: str, actor: str, who: str = "") -> None:
    try:
        import biz_nidaan as _n
        import biz_nidaan_notifications as _nnot
    except Exception:
        return
    try:
        ids = list(await _n.on_duty_rep_ids(to_key))
    except Exception as e:  # noqa: BLE001
        logger.warning("on-duty lookup failed for %s: %s", to_key, e)
        ids = []

    # Nobody rostered on the receiving bucket is itself worth knowing, so it goes to the admins
    # rather than nowhere.
    unstaffed = not ids
    if unstaffed:
        try:
            ids = [a["staff_id"] for a in await _nnot._super_admin_staff()]
        except Exception:
            ids = []
    if not ids:
        return

    label = "NP-%s%s" % (claim_id, (" · " + who) if who else "")
    if kind == "back":
        head = "↩ %s sent back to %s" % (label, to_name)
    elif kind == "park":
        head = "⏸ %s paused" % label
    elif kind == "resume":
        head = "▶ %s is back from hold, in %s" % (label, to_name)
    else:
        head = "→ %s arrived in %s" % (label, to_name)

    body = ("From: %s\nMoved by: %s\n\n%s" % (from_name, actor or "staff",
                                              (reason or "").strip() or "(no note)"))
    if unstaffed:
        body += ("\n\n⚠ Nobody is on duty for %s, so this went to the admins instead."
                 % to_name)
    try:
        await _nnot.notify_staff_inapp(
            ids, head, body, event_key="bucket.move", email=False, claim_id=claim_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("move notification failed for %s: %s", claim_id, e)


async def _notify_sender_back(claim_id: int, *, to_name: str, reason: str,
                              actor: str, who: str = "") -> None:
    """A claim going backwards should reach the person who sent it forward - they are the one
    who can fix whatever is wrong, and otherwise they never find out."""
    try:
        import biz_nidaan_notifications as _nnot
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT actor FROM nidaan_claim_activity WHERE claim_id=? AND kind='case_bucket' "
                "AND actor <> ? ORDER BY act_id DESC LIMIT 1", (int(claim_id), actor or ""))).fetchone()
            if not r or not (r["actor"] or "").strip():
                return
            prev = r["actor"].strip()
            s = await (await c.execute(
                "SELECT staff_id FROM nidaan_staff WHERE name=? AND status='active' "
                "AND deleted_at IS NULL LIMIT 1", (prev,))).fetchone()
        if not s:
            return
        await _nnot.notify_staff_inapp(
            [s[0]], "↩ NP-%s%s came back to %s" % (claim_id, (" · " + who) if who else "", to_name),
            "%s sent it back.\n\n%s" % (actor or "Someone", (reason or "").strip() or "(no note)"),
            event_key="bucket.sent_back", email=False, claim_id=claim_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("send-back notification failed for %s: %s", claim_id, e)


# ── the bucket designer ──────────────────────────────────────────────────────
# A super-admin owns the office process. Renaming a bucket, adding a step, inventing a field or
# opening a route must not need a deploy - and, more importantly, must not need me.
#
# Two rules run through all of it:
#   NOTHING IS EVER DELETED WHILE IT HOLDS WORK. A bucket with claims in it, or a field with
#   answers recorded against it, is DEACTIVATED - it stops appearing on new work and keeps every
#   value already captured. Deleting would silently destroy the history a case is argued from.
#   EVERY CHANGE IS ATTRIBUTED. The process is as auditable as the claims that move through it.

_SAFE_KEY = _re.compile(r"^[a-z][a-z0-9_]{1,38}$")
_FIELD_TYPES = ("text", "textarea", "richtext", "date", "number", "money", "yesno", "choice")
_WAITS = ("none", "complainant", "insurer", "lokpal", "internal")


def _key_from(name: str, existing: set) -> str:
    """A machine key from a human name, unique among what already exists."""
    base = _re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")[:38]
    if not base or not base[0].isalpha():
        base = "b_" + base
    base = base[:38]
    key, n = base, 2
    while key in existing:
        key = "%s_%d" % (base[:35], n)
        n += 1
    return key


async def _bucket_in_use(bucket_key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as c:
        r = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claims WHERE pipeline_stage=? "
            "AND COALESCE(archived,0)=0", (bucket_key,))).fetchone()
    return int(r[0] or 0)


async def save_bucket(*, bucket_key: str = "", name_en: str = "", name_hi: str = "",
                      icon: str = "", colour: str = "", amber_days=None, red_days=None,
                      waits_on: str = "", sort_order=None, active=None,
                      guide: Optional[dict] = None, actor: str = "") -> dict:
    """Create or update a bucket. An empty bucket_key creates one."""
    name_en = (name_en or "").strip()
    if not bucket_key and not name_en:
        return {"ok": False, "error": "Give the bucket a name."}
    if waits_on and waits_on not in _WAITS:
        return {"ok": False, "error": "That is not something a case can wait for."}
    try:
        amber = int(amber_days) if amber_days not in (None, "") else None
        red = int(red_days) if red_days not in (None, "") else None
    except (TypeError, ValueError):
        return {"ok": False, "error": "The day counts must be numbers."}
    if amber is not None and red is not None and red and amber and amber > red:
        return {"ok": False,
                "error": "Amber must come before red - a bucket cannot turn red before it warns."}

    g = guide or {}
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        if bucket_key:
            row = await (await c.execute(
                "SELECT bucket_key FROM nidaan_buckets WHERE bucket_key=?", (bucket_key,))).fetchone()
            if not row:
                return {"ok": False, "error": "That bucket does not exist."}
            sets, params = [], []
            for col, val in (("name_en", name_en or None), ("name_hi", name_hi or None),
                             ("icon", icon or None), ("colour", colour or None),
                             ("waits_on", waits_on or None)):
                if val is not None:
                    sets.append("%s=?" % col)
                    params.append(val)
            for col, val in (("amber_days", amber), ("red_days", red),
                             ("sort_order", sort_order)):
                if val is not None:
                    sets.append("%s=?" % col)
                    params.append(int(val))
            if active is not None:
                # Deactivating a bucket that still holds work would hide live claims.
                if not int(active):
                    n = await _bucket_in_use(bucket_key)
                    if n:
                        return {"ok": False,
                                "error": "%d claim(s) are in this bucket. Move them first - "
                                         "turning it off would hide live work." % n}
                sets.append("active=?")
                params.append(1 if int(active) else 0)
            for k, col in (("what", "guide_what"), ("do", "guide_do"),
                           ("done", "guide_done"), ("watch", "guide_watch")):
                if k in g:
                    sets.append("%s=?" % col)
                    params.append((g.get(k) or "")[:600])
            if not sets:
                return {"ok": True, "bucket_key": bucket_key, "unchanged": True}
            sets.append("updated_at=CURRENT_TIMESTAMP")
            params.append(bucket_key)
            await c.execute("UPDATE nidaan_buckets SET %s WHERE bucket_key=?" % ", ".join(sets),
                            params)
            await c.commit()
            logger.info("bucket %s edited by %s", bucket_key, actor)
            return {"ok": True, "bucket_key": bucket_key}

        existing = {r[0] for r in await (await c.execute(
            "SELECT bucket_key FROM nidaan_buckets")).fetchall()}
        key = _key_from(name_en, existing)
        if sort_order is None:
            r = await (await c.execute(
                "SELECT COALESCE(MAX(sort_order),0)+10 FROM nidaan_buckets")).fetchone()
            sort_order = int(r[0] or 10)
        await c.execute(
            "INSERT INTO nidaan_buckets (bucket_key,name_en,name_hi,icon,colour,sort_order,"
            "amber_days,red_days,waits_on,guide_what,guide_do,guide_done,guide_watch) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (key, name_en, name_hi or "", icon or "", colour or "teal", int(sort_order),
             amber if amber is not None else 10, red if red is not None else 20,
             waits_on or "internal",
             (g.get("what") or "")[:600], (g.get("do") or "")[:600],
             (g.get("done") or "")[:600], (g.get("watch") or "")[:600]))
        await c.commit()
    logger.info("bucket %s created by %s", key, actor)
    return {"ok": True, "bucket_key": key, "created": True}


async def save_substate(*, bucket_key: str, sub_key: str = "", name_en: str = "",
                        name_hi: str = "", amber_days=None, red_days=None, waits_on: str = "",
                        sort_order=None, is_default=None, active=None, actor: str = "") -> dict:
    """Create or update a step inside a bucket."""
    if not await bucket(bucket_key):
        return {"ok": False, "error": "That bucket does not exist."}
    name_en = (name_en or "").strip()
    if not sub_key and not name_en:
        return {"ok": False, "error": "Give the step a name."}
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        if sub_key:
            row = await (await c.execute(
                "SELECT sub_id FROM nidaan_bucket_substates WHERE bucket_key=? AND sub_key=?",
                (bucket_key, sub_key))).fetchone()
            if not row:
                return {"ok": False, "error": "That step does not exist."}
            if active is not None and not int(active):
                n = await (await c.execute(
                    "SELECT COUNT(*) FROM nidaan_claims WHERE pipeline_stage=? AND pipeline_sub=? "
                    "AND COALESCE(archived,0)=0", (bucket_key, sub_key))).fetchone()
                if int(n[0] or 0):
                    return {"ok": False,
                            "error": "%d claim(s) are on this step. Move them first." % int(n[0])}
            sets, params = [], []
            for col, val in (("name_en", name_en or None), ("name_hi", name_hi or None),
                             ("waits_on", waits_on or None)):
                if val is not None:
                    sets.append("%s=?" % col); params.append(val)
            for col, val in (("amber_days", amber_days), ("red_days", red_days),
                             ("sort_order", sort_order)):
                if val not in (None, ""):
                    sets.append("%s=?" % col); params.append(int(val))
            if is_default is not None:
                sets.append("is_default=?"); params.append(1 if int(is_default) else 0)
            if active is not None:
                sets.append("active=?"); params.append(1 if int(active) else 0)
            if not sets:
                return {"ok": True, "sub_key": sub_key, "unchanged": True}
            params += [bucket_key, sub_key]
            await c.execute("UPDATE nidaan_bucket_substates SET %s WHERE bucket_key=? AND sub_key=?"
                            % ", ".join(sets), params)
            if is_default is not None and int(is_default):
                await c.execute("UPDATE nidaan_bucket_substates SET is_default=0 "
                                "WHERE bucket_key=? AND sub_key<>?", (bucket_key, sub_key))
            await c.commit()
            return {"ok": True, "sub_key": sub_key}

        existing = {r[0] for r in await (await c.execute(
            "SELECT sub_key FROM nidaan_bucket_substates WHERE bucket_key=?",
            (bucket_key,))).fetchall()}
        key = _key_from(name_en, existing)
        if sort_order is None:
            r = await (await c.execute(
                "SELECT COALESCE(MAX(sort_order),0)+10 FROM nidaan_bucket_substates "
                "WHERE bucket_key=?", (bucket_key,))).fetchone()
            sort_order = int(r[0] or 10)
        await c.execute(
            "INSERT INTO nidaan_bucket_substates (bucket_key,sub_key,name_en,name_hi,sort_order,"
            "amber_days,red_days,waits_on,is_default) VALUES (?,?,?,?,?,?,?,?,?)",
            (bucket_key, key, name_en, name_hi or "", int(sort_order),
             (int(amber_days) if amber_days not in (None, "") else None),
             (int(red_days) if red_days not in (None, "") else None),
             waits_on or "", 1 if is_default else 0))
        if is_default:
            await c.execute("UPDATE nidaan_bucket_substates SET is_default=0 "
                            "WHERE bucket_key=? AND sub_key<>?", (bucket_key, key))
        await c.commit()
    return {"ok": True, "sub_key": key, "created": True}


async def save_field(*, bucket_key: str, field_key: str = "", label_en: str = "",
                     label_hi: str = "", field_type: str = "text", choices: str = "",
                     hint: str = "", required_exit=None, sort_order=None, active=None,
                     actor: str = "") -> dict:
    """Create or update a field captured in a bucket."""
    if not await bucket(bucket_key):
        return {"ok": False, "error": "That bucket does not exist."}
    label_en = (label_en or "").strip()
    if not field_key and not label_en:
        return {"ok": False, "error": "Give the field a label."}
    if field_type and field_type not in _FIELD_TYPES:
        return {"ok": False, "error": "That is not a kind of field we can store."}
    if field_type == "choice" and not (choices or "").strip() and not field_key:
        return {"ok": False, "error": "A choice field needs its options, one per line."}

    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        if field_key:
            row = await (await c.execute(
                "SELECT field_id FROM nidaan_bucket_fields WHERE bucket_key=? AND field_key=?",
                (bucket_key, field_key))).fetchone()
            if not row:
                return {"ok": False, "error": "That field does not exist."}
            sets, params = [], []
            for col, val in (("label_en", label_en or None), ("label_hi", label_hi or None),
                             ("field_type", field_type or None), ("hint", hint or None)):
                if val is not None:
                    sets.append("%s=?" % col); params.append(val)
            if choices is not None and choices != "":
                sets.append("choices=?"); params.append(choices)
            if required_exit is not None:
                sets.append("required_exit=?"); params.append(1 if int(required_exit) else 0)
            if sort_order not in (None, ""):
                sets.append("sort_order=?"); params.append(int(sort_order))
            if active is not None:
                # A field with answers is retired, never removed: those answers are case history.
                sets.append("active=?"); params.append(1 if int(active) else 0)
            if not sets:
                return {"ok": True, "field_key": field_key, "unchanged": True}
            params += [bucket_key, field_key]
            await c.execute("UPDATE nidaan_bucket_fields SET %s WHERE bucket_key=? AND field_key=?"
                            % ", ".join(sets), params)
            await c.commit()
            return {"ok": True, "field_key": field_key}

        existing = {r[0] for r in await (await c.execute(
            "SELECT field_key FROM nidaan_bucket_fields")).fetchall()}
        key = _key_from(label_en, existing)
        if sort_order is None:
            r = await (await c.execute(
                "SELECT COALESCE(MAX(sort_order),0)+10 FROM nidaan_bucket_fields "
                "WHERE bucket_key=?", (bucket_key,))).fetchone()
            sort_order = int(r[0] or 10)
        await c.execute(
            "INSERT INTO nidaan_bucket_fields (bucket_key,field_key,label_en,label_hi,field_type,"
            "choices,hint,required_exit,sort_order) VALUES (?,?,?,?,?,?,?,?,?)",
            (bucket_key, key, label_en, label_hi or "", field_type or "text",
             choices or "", hint or "", 1 if required_exit else 0, int(sort_order)))
        await c.commit()
    return {"ok": True, "field_key": key, "created": True}


async def field_usage(field_key: str) -> int:
    async with aiosqlite.connect(DB_PATH) as c:
        r = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claim_fields WHERE field_key=? "
            "AND TRIM(COALESCE(value,''))<>''", (field_key,))).fetchone()
    return int(r[0] or 0)


async def save_route(*, from_key: str, to_key: str, kind: str = "forward",
                     needs_reason=None, remove: bool = False, actor: str = "") -> dict:
    """Open or close a route between two buckets.

    Closing one does not trap anything: a move to an unlisted bucket is still allowed, it simply
    stops being offered as a usual next step and is recorded as off the usual path.
    """
    if from_key == to_key:
        return {"ok": False, "error": "A bucket cannot lead to itself."}
    if not await bucket(from_key) or not await bucket(to_key):
        return {"ok": False, "error": "One of those buckets does not exist."}
    if kind not in ("forward", "back", "park", "resume"):
        return {"ok": False, "error": "That is not a kind of move."}
    async with aiosqlite.connect(DB_PATH) as c:
        if remove:
            # A TOMBSTONE, not a delete. The seed runs on every boot with INSERT OR IGNORE,
            # so a deleted row would simply come back and the decision would be undone by the
            # next deploy - which is exactly what happened when Reimbursement was retired. The
            # row stays, marked removed, and its primary key is what keeps the seed out.
            await c.execute(
                "INSERT INTO nidaan_bucket_moves (from_key,to_key,kind,needs_reason,sort_order) "
                "VALUES (?,?,'removed',0,0) ON CONFLICT(from_key,to_key) DO UPDATE SET "
                "kind='removed'", (from_key, to_key))
        else:
            await c.execute(
                "INSERT INTO nidaan_bucket_moves (from_key,to_key,kind,needs_reason,sort_order) "
                "VALUES (?,?,?,?,0) ON CONFLICT(from_key,to_key) DO UPDATE SET "
                "kind=excluded.kind, needs_reason=excluded.needs_reason",
                (from_key, to_key, kind, 1 if needs_reason else 0))
        await c.commit()
    return {"ok": True}


async def designer_view() -> dict:
    """The whole process, plus how much work each part is holding - because that is what decides
    whether something can be changed freely or has to be retired carefully."""
    out = []
    for b in await buckets(include_inactive=True):
        subs = await substates(b["bucket_key"], include_inactive=True)
        flds = await fields(b["bucket_key"], include_inactive=True)
        for f in flds:
            f["answers"] = await field_usage(f["field_key"])
        out.append({**b, "claims": await _bucket_in_use(b["bucket_key"]),
                    "substates": subs, "fields": flds,
                    "moves": await moves_from(b["bucket_key"])})
    return {"buckets": out, "field_types": list(_FIELD_TYPES), "waits_on": list(_WAITS)}


# ── telling people what has gone quiet ───────────────────────────────────────
# A claim that nobody moves raises no move notification, by definition. That is the exact case
# the office loses claims in, so it gets its own daily sweep. One message per person, only what
# has gone stale, and silence when there is nothing worth saying.

async def _digest_lines(items: list, limit: int = 8) -> list:
    """The claims, worst first, each as one line a person can act on."""
    out = []
    for i in items[:limit]:
        head = "NP-%s" % i["claim_id"]
        who = (i.get("who") or "").strip()
        if who:
            head += " \u00b7 " + who
        out.append("%s (%sd)\n   %s" % (head, i.get("days") or 0, i.get("why") or ""))
    if len(items) > limit:
        out.append("\u2026and %d more." % (len(items) - limit))
    return out


async def standing_alerts(force: bool = False) -> dict:
    """Once a day: what has gone stale, to whoever is on duty for that bucket.

    Returns what it did, so the worker can log something meaningful rather than 'ran'.
    """
    import biz_nidaan as _n
    import biz_nidaan_notifications as _nnot
    try:
        await query_reminders()          # open draft queries first - they are the urgent ones
    except Exception as e:  # noqa: BLE001
        logger.warning("draft query reminders failed: %s", e)

    today = _today_ist().isoformat()
    sent, skipped, unstaffed = 0, 0, []
    for b in await buckets():
        if b.get("is_terminal") or b.get("is_park"):
            continue
        key = b["bucket_key"]
        d = await board(key)
        stale = [i for i in (d.get("items") or []) if i.get("age_state") in ("amber", "red")]
        # Silence is the default. Nothing to say means nothing is sent - an "all clear" every
        # morning is how people learn to ignore the ones that matter.
        if not stale:
            continue

        red = [i for i in stale if i["age_state"] == "red"]
        try:
            ids = list(await _n.on_duty_rep_ids(key))
        except Exception:
            ids = []

        # Nobody rostered: only the RED ones are worth waking an admin for, and the message says
        # plainly that the bucket has no one on it - which is the real problem to fix.
        note = ""
        if not ids:
            if not red:
                continue
            unstaffed.append(key)
            try:
                ids = [a["staff_id"] for a in await _nnot._super_admin_staff()]
            except Exception:
                ids = []
            stale = red
            note = ("\n\n\u26a0 Nobody is on duty for %s, so this came to the admins."
                    % b["name_en"])
        if not ids:
            continue

        head = "%s %s \u2014 %d need looking at" % (b.get("icon") or "", b["name_en"], len(stale))
        if red:
            head += " (%d past the limit)" % len(red)
        body = "\n\n".join(await _digest_lines(stale)) + note

        for sid in ids:
            # One per person per bucket per day. The key carries the date, so yesterday's
            # message never suppresses today's and today's can never be sent twice.
            akey = "bucket_stale:%s:%s:%s" % (key, sid, today)
            if not force and not await _alert_once(akey):
                skipped += 1
                continue
            try:
                await _nnot.notify_staff_inapp([sid], head.strip(), body,
                                               event_key="bucket.stale", email=False)
                sent += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("standing alert failed for %s/%s: %s", key, sid, e)

    if unstaffed:
        logger.info("standing alerts: buckets with nobody on duty: %s", unstaffed)
    return {"sent": sent, "already_sent_today": skipped, "unstaffed": unstaffed}


async def _alert_once(alert_key: str) -> bool:
    """True the first time this key is seen, False every time after. The dedup table is already
    how the rest of the app stops an alert repeating; this reuses it rather than inventing a
    second way to remember."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                "INSERT OR IGNORE INTO nidaan_alert_dedup (alert_key, sent_count, last_at) "
                "VALUES (?, 1, CURRENT_TIMESTAMP)", (alert_key,))
            await c.commit()
            return (cur.rowcount or 0) > 0
    except Exception as e:  # noqa: BLE001
        logger.warning("alert dedup failed for %s: %s", alert_key, e)
        return False
