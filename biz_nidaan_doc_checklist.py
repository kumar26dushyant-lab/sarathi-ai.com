"""
biz_nidaan_doc_checklist.py — the required-document checklist engine.

This is the SPINE of the ₹499 funnel (and the shared advisor-subscription review
flow). One source of truth for:
  • which documents a claim of a given type requires,
  • which have been received (from dashboard OR WhatsApp — cross-channel),
  • what's still pending (drives the smart-chase de-dup + the pay-gate).

The dashboard banner, the WhatsApp nudge, and the "Pay ₹499 / unlock" gate all
read pending_required_docs() — so de-dup is correct BY CONSTRUCTION (we can never
double-ask, and the pay button can't appear until the checklist is complete).

Labels use the real document names people actually say (per spec §8). en + hi now;
mr falls back to en until the WhatsApp phase fills it. Doc `key` is the stable id.
Pure data + thin DB helpers — unit-testable in isolation.
"""
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.checklist")

VIA_DASHBOARD = "dashboard"
VIA_WHATSAPP = "whatsapp"

# DPDP trust line shown alongside every upload ask (en/hi; mr later).
TRUST_LINE = {
    "en": ("🔒 Your documents are used only to fight your claim. We follow the "
           "Government of India DPDP Act 2023 — no leaks, no sharing, and your "
           "files are securely destroyed after your case is resolved."),
    "hi": ("🔒 आपके दस्तावेज़ केवल आपके क्लेम की लड़ाई के लिए इस्तेमाल होते हैं। हम "
           "भारत सरकार के DPDP अधिनियम 2023 का पालन करते हैं — कोई लीक नहीं, कोई "
           "साझा नहीं, और केस सुलझने के बाद आपकी फ़ाइलें सुरक्षित रूप से नष्ट कर दी जाती हैं।"),
}


def _doc(key, en, hi, why_en, required=True, conditional=False):
    return {"key": key, "en": en, "hi": hi, "why_en": why_en,
            "required": required, "conditional": conditional}


# ── Per-claim-type required-document templates (spec §8, real-name labels) ────
TEMPLATES: dict[str, list[dict]] = {
    "health": [
        _doc("rejection_letter", "Rejection / Underpaid Settlement Letter",
             "रिजेक्शन / कम भुगतान सेटलमेंट लेटर",
             "The insurer's letter saying no or paying less — the basis of the dispute."),
        _doc("policy_document", "Policy Document (with T&C page) / Policy Copy",
             "पॉलिसी डॉक्यूमेंट (नियम-शर्तें पेज सहित) / पॉलिसी कॉपी",
             "Shows your coverage and the exclusions the insurer is relying on."),
        _doc("discharge_summary", "Discharge Summary / Discharge Documents",
             "डिस्चार्ज समरी / डिस्चार्ज दस्तावेज़",
             "The most important hospital paper — establishes the treatment given."),
        _doc("itemized_bills", "Itemised Hospital Bills",
             "विस्तृत अस्पताल बिल",
             "Room rent, medicines and doctor fees shown separately — proves the amount."),
        _doc("prior_medical", "Past Medical Records / Doctor's Certificate",
             "पुराने मेडिकल रिकॉर्ड / डॉक्टर का प्रमाणपत्र",
             "Only if a pre-existing disease is alleged — records from before the policy.",
             required=False, conditional=True),
    ],
    "life": [
        _doc("decision_letter", "Rejection / Claim Decision Letter",
             "रिजेक्शन / क्लेम निर्णय लेटर",
             "The insurer's decision — the basis of the dispute."),
        _doc("policy_bond", "Original Policy Bond / Policy Document",
             "मूल पॉलिसी बॉन्ड / पॉलिसी डॉक्यूमेंट",
             "The policy and its terms."),
        _doc("death_certificate", "Death Certificate",
             "मृत्यु प्रमाणपत्र",
             "Issued by the Municipal Corporation — the official record."),
        _doc("cause_of_death", "Cause-of-Death Certificate / Hospital Death Summary",
             "मृत्यु-कारण प्रमाणपत्र / अस्पताल मृत्यु समरी",
             "From the attending doctor/hospital — links the cause to coverage."),
        _doc("proposal_form", "Proposal Form (Application) + Past Medical History",
             "प्रपोज़ल फॉर्म (आवेदन) + पुराना मेडिकल इतिहास",
             "Proves everything was disclosed truthfully when the policy was bought."),
    ],
    "property": [
        _doc("rejection_or_survey_letter", "Rejection Letter / Surveyor's Assessment Letter",
             "रिजेक्शन लेटर / सर्वेयर मूल्यांकन लेटर",
             "The insurer's no or under-assessment — the basis of the dispute."),
        _doc("policy_schedule", "Policy Schedule",
             "पॉलिसी शेड्यूल",
             "Shows the Sum Insured for building and contents."),
        _doc("incident_proof", "FIR Copy / Fire Brigade Report",
             "FIR कॉपी / फायर ब्रिगेड रिपोर्ट",
             "For fire or theft — proves the incident occurred."),
        _doc("damage_evidence", "Photos / Videos of the Damage",
             "नुकसान की फोटो / वीडियो",
             "Taken right after the incident, before anything was cleaned or moved."),
        _doc("purchase_bills", "Purchase Bills / Invoices for Damaged Items",
             "क्षतिग्रस्त वस्तुओं के खरीद बिल / इनवॉइस",
             "Proves the value of what was lost or damaged."),
        _doc("surveyor_report", "Surveyor's Report",
             "सर्वेयर रिपोर्ट",
             "What the insurer's surveyor wrote after visiting — needed to contest underpayment."),
    ],
    "motor": [
        _doc("rejection_or_survey_letter", "Rejection Letter / Surveyor's Assessment Letter",
             "रिजेक्शन लेटर / सर्वेयर मूल्यांकन लेटर",
             "The insurer's no or under-assessment — the basis of the dispute."),
        _doc("policy_document", "Policy Copy / Policy Schedule",
             "पॉलिसी कॉपी / पॉलिसी शेड्यूल",
             "Shows your coverage (Own Damage / Third Party) and the IDV."),
        _doc("incident_proof", "FIR / Accident or Theft Report",
             "FIR / दुर्घटना या चोरी रिपोर्ट",
             "For accidents or theft — proves the incident occurred."),
        _doc("damage_evidence", "Photos / Videos of the Vehicle Damage",
             "वाहन क्षति की फोटो / वीडियो",
             "Shows the extent of damage to the vehicle."),
        _doc("repair_estimate", "Repair Estimate + Final Repair Bills",
             "मरम्मत अनुमान + अंतिम मरम्मत बिल",
             "Proves the cost of repair you are claiming."),
        _doc("surveyor_report", "Surveyor's Report",
             "सर्वेयर रिपोर्ट",
             "The insurer's surveyor assessment — needed to contest underpayment.",
             required=False, conditional=True),
    ],
    "marine": [
        _doc("rejection_letter", "Rejection Letter",
             "रिजेक्शन लेटर",
             "For the damage or shortage — the basis of the dispute."),
        _doc("marine_policy", "Marine Policy / Open Cover Certificate",
             "मरीन पॉलिसी / ओपन कवर सर्टिफिकेट",
             "Your coverage for the consignment."),
        _doc("transit_papers", "Bill of Lading + Packing List + Invoices",
             "बिल ऑफ लैडिंग + पैकिंग लिस्ट + इनवॉइस",
             "The paper trail proving what was shipped and its value."),
        _doc("survey_report", "Survey Report (port / destination)",
             "सर्वे रिपोर्ट (बंदरगाह / गंतव्य)",
             "Proves the loss/damage at the port or on arrival."),
        _doc("delivery_protest", "Delivery Protest Note",
             "डिलीवरी प्रोटेस्ट नोट",
             "The remark made at delivery (e.g. damage noted on the courier receipt)."),
    ],
    "travel": [
        _doc("refusal_letter", "Travel Claim Refusal Letter",
             "ट्रैवल क्लेम अस्वीकृति लेटर",
             "The insurer's refusal — the basis of the dispute."),
        _doc("travel_certificate", "Travel Insurance Certificate",
             "ट्रैवल इंश्योरेंस सर्टिफिकेट",
             "The cover you bought for the trip."),
        _doc("trip_proof", "Tickets / Boarding Passes / Passport",
             "टिकट / बोर्डिंग पास / पासपोर्ट",
             "With entry/exit stamps — proves the trip and timeline."),
        _doc("incident_proof", "Incident Proof (delay cert / PIR / overseas medical bills)",
             "घटना प्रमाण (देरी प्रमाणपत्र / PIR / विदेशी मेडिकल बिल)",
             "Airline delay certificate, lost-baggage PIR, or overseas medical bills — proves the event."),
    ],
    # Generic fallback for 'other'/unknown types.
    "other": [
        _doc("rejection_letter", "Rejection / Underpaid Settlement Letter",
             "रिजेक्शन / कम भुगतान सेटलमेंट लेटर",
             "The insurer's decision — the basis of the dispute."),
        _doc("policy_document", "Policy Document / Policy Copy",
             "पॉलिसी डॉक्यूमेंट / पॉलिसी कॉपी",
             "Your coverage and its terms."),
        _doc("supporting_docs", "Supporting Documents",
             "सहायक दस्तावेज़",
             "Any bills, reports, or proof relevant to your claim."),
    ],
}

# claim_type aliases → canonical template key
ALIASES = {
    "home": "property",
    "fire": "property",
    "house": "property",
    "medical": "health",
    "mediclaim": "health",
    "vehicle": "motor",
    "car": "motor",
    "transit": "marine",
}


def canonical_type(claim_type: str) -> str:
    t = (claim_type or "").strip().lower()
    if t in TEMPLATES:
        return t
    if t in ALIASES:
        return ALIASES[t]
    return "other"


def doc_template_for(claim_type: str) -> list[dict]:
    return TEMPLATES[canonical_type(claim_type)]


def label(doc_key: str, claim_type: str, lang: str = "en") -> str:
    for d in doc_template_for(claim_type):
        if d["key"] == doc_key:
            return d.get(lang) or d["en"]
    return doc_key


# ── DB helpers ───────────────────────────────────────────────────────────────
async def seed_checklist_for_claim(claim_id: int, claim_type: str) -> int:
    """Insert the required-doc rows for a claim (idempotent). Returns row count."""
    tmpl = doc_template_for(claim_type)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        for d in tmpl:
            await conn.execute(
                """INSERT OR IGNORE INTO nidaan_claim_doc_checklist
                   (claim_id, doc_key, required, conditional, received)
                   VALUES (?, ?, ?, ?, 0)""",
                (claim_id, d["key"], 1 if d["required"] else 0,
                 1 if d["conditional"] else 0),
            )
        await conn.commit()
    return len(tmpl)


async def mark_doc_received(claim_id: int, doc_key: str, *, via: str,
                            doc_id: Optional[int] = None) -> bool:
    """Flip a checklist item to received. Returns True if a row was updated."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            """UPDATE nidaan_claim_doc_checklist
               SET received=1, received_via=?, received_doc_id=?, updated_at=datetime('now')
               WHERE claim_id=? AND doc_key=?""",
            (via, doc_id, claim_id, doc_key),
        )
        await conn.commit()
        return cur.rowcount > 0


async def set_doc_required(claim_id: int, doc_key: str, required: bool) -> None:
    """Reviewer toggles a (conditional) item required or not."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_claim_doc_checklist SET required=?, updated_at=datetime('now') "
            "WHERE claim_id=? AND doc_key=?",
            (1 if required else 0, claim_id, doc_key),
        )
        await conn.commit()


async def _rows(claim_id: int) -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_claim_doc_checklist WHERE claim_id=?", (claim_id,))
        return [dict(r) for r in await cur.fetchall()]


async def pending_required_docs(claim_id: int, claim_type: str) -> list[dict]:
    """The still-missing REQUIRED docs — the single source for de-dup + pay-gate.
    Returns enriched doc dicts (key + labels + why) so callers can render asks."""
    rows = {r["doc_key"]: r for r in await _rows(claim_id)}
    pending = []
    for d in doc_template_for(claim_type):
        r = rows.get(d["key"])
        # required if the template says so OR the reviewer marked it required
        is_required = (r["required"] == 1) if r else d["required"]
        received = (r["received"] == 1) if r else False
        if is_required and not received:
            pending.append(d)
    return pending


PAY_GATE_MIN_DOCS = 3   # ₹499 appears after this many key docs (flexibility-first)


def pay_gate_ready(st: dict) -> bool:
    """Whether enough key documents are in to surface the ₹499 pay-gate.
    Flexibility-first: we don't force every required doc — just the first few
    important ones (or all required, if the category needs fewer than the
    threshold)."""
    req = int(st.get("required_total", 0))
    rec = int(st.get("received_required", 0))
    if req <= 0:
        return False
    return rec >= min(PAY_GATE_MIN_DOCS, req)


async def checklist_status(claim_id: int, claim_type: str) -> dict:
    """Full status for dashboard/ops: counts + pending + complete flag."""
    rows = {r["doc_key"]: r for r in await _rows(claim_id)}
    tmpl = doc_template_for(claim_type)
    required_total = received_required = 0
    items = []
    for d in tmpl:
        r = rows.get(d["key"])
        is_required = (r["required"] == 1) if r else d["required"]
        received = (r["received"] == 1) if r else False
        via = r["received_via"] if r else None
        if is_required:
            required_total += 1
            received_required += 1 if received else 0
        items.append({**d, "required_effective": is_required,
                      "received": received, "received_via": via})
    complete = required_total > 0 and received_required == required_total
    return {
        "claim_id": claim_id,
        "claim_type": canonical_type(claim_type),
        "required_total": required_total,
        "received_required": received_required,
        "complete": complete,
        "items": items,
    }
