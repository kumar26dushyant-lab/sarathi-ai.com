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


# Hindi for the "why we need this" one-liners, keyed by the English text (many
# repeat across claim types, so one lookup covers all of them).
WHY_HI = {
    "The insurer's letter saying no or paying less — the basis of the dispute.": "बीमाकर्ता का ना या कम भुगतान का पत्र — विवाद का आधार।",
    "Shows your coverage and the exclusions the insurer is relying on.": "आपका कवरेज और वे बहिष्करण दिखाता है जिन पर बीमाकर्ता भरोसा कर रहा है।",
    "The most important hospital paper — establishes the treatment given.": "सबसे ज़रूरी अस्पताल दस्तावेज़ — किए गए इलाज को स्थापित करता है।",
    "Room rent, medicines and doctor fees shown separately — proves the amount.": "कमरा किराया, दवाइयाँ और डॉक्टर फीस अलग-अलग — राशि साबित करता है।",
    "Only if a pre-existing disease is alleged — records from before the policy.": "केवल अगर पहले से मौजूद बीमारी का आरोप हो — पॉलिसी से पहले के रिकॉर्ड।",
    "The insurer's decision — the basis of the dispute.": "बीमाकर्ता का निर्णय — विवाद का आधार।",
    "The policy and its terms.": "पॉलिसी और उसकी शर्तें।",
    "Issued by the Municipal Corporation — the official record.": "नगर निगम द्वारा जारी — आधिकारिक रिकॉर्ड।",
    "From the attending doctor/hospital — links the cause to coverage.": "इलाज करने वाले डॉक्टर/अस्पताल से — कारण को कवरेज से जोड़ता है।",
    "Proves everything was disclosed truthfully when the policy was bought.": "साबित करता है कि पॉलिसी खरीदते समय सब कुछ सही-सही बताया गया था।",
    "The insurer's no or under-assessment — the basis of the dispute.": "बीमाकर्ता का ना या कम आकलन — विवाद का आधार।",
    "Shows the Sum Insured for building and contents.": "इमारत और सामान के लिए बीमित राशि दिखाता है।",
    "For fire or theft — proves the incident occurred.": "आग या चोरी के लिए — साबित करता है कि घटना हुई।",
    "Taken right after the incident, before anything was cleaned or moved.": "घटना के तुरंत बाद ली गई — कुछ भी साफ़ या हटाने से पहले।",
    "Proves the value of what was lost or damaged.": "जो खोया या क्षतिग्रस्त हुआ उसका मूल्य साबित करता है।",
    "What the insurer's surveyor wrote after visiting — needed to contest underpayment.": "बीमाकर्ता के सर्वेयर ने दौरे के बाद जो लिखा — कम भुगतान को चुनौती देने के लिए ज़रूरी।",
    "Shows your coverage (Own Damage / Third Party) and the IDV.": "आपका कवरेज (ओन डैमेज / थर्ड पार्टी) और IDV दिखाता है।",
    "For accidents or theft — proves the incident occurred.": "दुर्घटना या चोरी के लिए — साबित करता है कि घटना हुई।",
    "Shows the extent of damage to the vehicle.": "वाहन को हुए नुकसान की सीमा दिखाता है।",
    "Proves the cost of repair you are claiming.": "आप जिस मरम्मत का दावा कर रहे हैं उसकी लागत साबित करता है।",
    "The insurer's surveyor assessment — needed to contest underpayment.": "बीमाकर्ता के सर्वेयर का आकलन — कम भुगतान को चुनौती देने के लिए ज़रूरी।",
    "For the damage or shortage — the basis of the dispute.": "क्षति या कमी के लिए — विवाद का आधार।",
    "Your coverage for the consignment.": "खेप के लिए आपका कवरेज।",
    "The paper trail proving what was shipped and its value.": "क्या भेजा गया और उसका मूल्य साबित करने वाला दस्तावेज़ी रिकॉर्ड।",
    "Proves the loss/damage at the port or on arrival.": "बंदरगाह पर या पहुँचने पर हुई हानि/क्षति साबित करता है।",
    "The remark made at delivery (e.g. damage noted on the courier receipt).": "डिलीवरी के समय की गई टिप्पणी (जैसे कूरियर रसीद पर दर्ज क्षति)।",
    "The insurer's refusal — the basis of the dispute.": "बीमाकर्ता का इनकार — विवाद का आधार।",
    "The cover you bought for the trip.": "यात्रा के लिए आपने जो कवर खरीदा।",
    "With entry/exit stamps — proves the trip and timeline.": "प्रवेश/निकास मुहरों सहित — यात्रा और समयरेखा साबित करता है।",
    "Airline delay certificate, lost-baggage PIR, or overseas medical bills — proves the event.": "एयरलाइन देरी प्रमाणपत्र, खोया-सामान PIR, या विदेशी मेडिकल बिल — घटना साबित करता है।",
    "Your coverage and its terms.": "आपका कवरेज और उसकी शर्तें।",
    "Any bills, reports, or proof relevant to your claim.": "आपके क्लेम से संबंधित कोई भी बिल, रिपोर्ट या प्रमाण।",
}

def why_hi_for(why_en: str) -> str:
    return WHY_HI.get(why_en or "", "")

def _doc(key, en, hi, why_en, required=True, conditional=False):
    return {"key": key, "en": en, "hi": hi, "why_en": why_en, "why_hi": WHY_HI.get(why_en, ""),
            "required": required, "conditional": conditional}


# ── Per-claim-type required-document templates (spec §8, real-name labels) ────
TEMPLATES: dict[str, list[dict]] = {
    # Health: the founder's own list (16 Sep 2026), in his order. The KEYS are unchanged for the
    # four documents that already existed — a tick is stored against the key, so relabelling
    # costs nobody the papers they have already sent. Three are new, plus the mail ID.
    "health": [
        _doc("policy_document", "Policy Document (with T&C page) / Policy Copy",
             "पॉलिसी डॉक्यूमेंट (नियम-शर्तें पेज सहित) / पॉलिसी कॉपी",
             "Shows your coverage and the exclusions the insurer is relying on."),
        _doc("rejection_letter", "Rejection Letter / Bill Summary",
             "रिजेक्शन लेटर / बिल समरी",
             "The insurer's letter saying no or paying less — the basis of the dispute."),
        _doc("itemized_bills", "Final Bill with Payment Receipts",
             "फाइनल बिल और भुगतान रसीदें",
             "The final bill with the receipts — proves what was actually paid."),
        _doc("claim_form", "Claim Form",
             "क्लेम फॉर्म",
             "The form filed with the insurer — what was claimed, and on what basis."),
        _doc("discharge_summary", "Discharge Summary / Discharge Documents",
             "डिस्चार्ज समरी / डिस्चार्ज दस्तावेज़",
             "The most important hospital paper — establishes the treatment given."),
        _doc("kyc", "KYC (ID proof of the policyholder)",
             "KYC (पॉलिसीधारक का पहचान प्रमाण)",
             "Aadhaar or PAN — proves who the policyholder is to the insurer and the authorities."),
        # Not an ordinary document: a NEW email account created for this case, which we use to
        # write to the insurance company and the authorities on the complainant's behalf. It asks
        # for a password, so what the complainant is told matters as much as the ask itself —
        # see MAIL_ID_NOTE in biz_nidaan_doc_request.
        _doc("mail_credentials", "Email ID created for this case (with its password)",
             "इस केस के लिए बनाई गई ईमेल आईडी (पासवर्ड सहित)",
             "A NEW email account made only for this case — we write to the insurance company and "
             "the authorities from it. Never your personal email."),
        _doc("other_docs", "Any other documents available",
             "कोई अन्य उपलब्ध दस्तावेज़",
             "Anything else about this claim — letters, messages, prescriptions.",
             required=False),
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


async def _mark_once(claim_id: int, doc_key: str, via: str, doc_id) -> int:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            """UPDATE nidaan_claim_doc_checklist
               SET received=1, received_via=?, received_doc_id=?, updated_at=datetime('now')
               WHERE claim_id=? AND doc_key=?""",
            (via, doc_id, claim_id, doc_key),
        )
        await conn.commit()
        return cur.rowcount


async def mark_doc_received(claim_id: int, doc_key: str, *, via: str,
                            doc_id: Optional[int] = None) -> bool:
    """Flip a checklist item to received. Returns True if a row was updated.

    SEEDS THE CHECKLIST IF IT IS MISSING. A claim only gets checklist rows when something calls
    seed_checklist_for_claim, and 74 of 158 live claims never had that happen — so this UPDATE
    matched nothing, returned False, and the tick vanished. Every caller ignored the return value,
    so a document genuinely received went on showing as outstanding for ever: the WhatsApp bot,
    the complainant portal and staff ticks all lost work the same silent way.

    Seeding is idempotent (INSERT OR IGNORE) and only adds the rows this claim's type says it
    needs, so healing it here is safe and repairs every caller at once instead of one at a time.
    """
    if await _mark_once(claim_id, doc_key, via, doc_id):
        return True
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            row = await (await conn.execute(
                "SELECT COALESCE(claim_type,'') FROM nidaan_claims WHERE claim_id=?",
                (int(claim_id),))).fetchone()
        await seed_checklist_for_claim(int(claim_id), (row[0] if row else "") or "")
    except Exception as e:  # noqa: BLE001
        logger.warning("could not seed the checklist for claim %s: %s", claim_id, e)
        return False
    return bool(await _mark_once(claim_id, doc_key, via, doc_id))


async def set_doc_received(claim_id: int, doc_key: str, received: bool, *, by: str = "") -> dict:
    """Tick (or untick) a checklist line BY HAND.

    Until now a line could only go green if somebody chose the document's name from a dropdown as
    they uploaded it, or if the WhatsApp bot recognised it. Papers arrive by post, by hand and in
    somebody's inbox, and they arrive named IMG_2231 — so the list said 3 of 8 while 9 documents
    sat attached to the claim. Staff can now say so themselves. Deliberately manual: matching a
    typed file name to a checklist line is a guess, and a wrong guess means we stop asking for a
    paper we never received."""
    via = ("staff:%s" % (by or "")).strip(":")[:40] if received else ""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            """UPDATE nidaan_claim_doc_checklist
               SET received=?, received_via=?, updated_at=datetime('now')
               WHERE claim_id=? AND doc_key=?""",
            (1 if received else 0, via, int(claim_id), doc_key))
        if not cur.rowcount:
            # A template line nobody has touched yet has no row of its own.
            await conn.execute(
                """INSERT INTO nidaan_claim_doc_checklist
                   (claim_id, doc_key, required, conditional, received, received_via)
                   VALUES (?,?,1,0,?,?)""",
                (int(claim_id), doc_key, 1 if received else 0, via))
        if not received:
            # Unticking by hand also breaks the link to whatever file had answered it, or the
            # next person would see a green line pointing at a document we no longer count.
            await conn.execute(
                "UPDATE nidaan_claim_doc_checklist SET received_doc_id=NULL "
                "WHERE claim_id=? AND doc_key=?", (int(claim_id), doc_key))
        await conn.commit()
    return {"ok": True, "doc_key": doc_key, "received": bool(received)}


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


async def effective_docs(claim_id: int, claim_type: str) -> list[dict]:
    """The documents THIS claim actually needs: the type's template, plus anything a staffer
    added for this case, minus anything a staffer removed (with their reason).

    One list, used by pending_required_docs() and checklist_status() alike, so the dashboard,
    the WhatsApp nudge and the pay-gate can never disagree about what is outstanding.
    """
    rows = {r["doc_key"]: r for r in await _rows(claim_id)}
    out, seen = [], set()
    for d in doc_template_for(claim_type):
        r = rows.get(d["key"])
        if r and r.get("removed_at"):
            continue
        seen.add(d["key"])
        out.append({**d, "custom": False, "row": r})
    # Anything on the claim that the template does not know about. A custom row carries its own
    # label, because there is no template entry to read one from.
    for key, r in rows.items():
        if key in seen or r.get("removed_at"):
            continue
        lbl = (r.get("custom_label") or "").strip() or key.replace("_", " ").title()
        out.append({"key": key, "en": lbl, "hi": lbl,
                    "why": "Asked for on this case.", "why_hi": "\u0907\u0938 \u0915\u0947\u0938 \u092a\u0930 \u092e\u093e\u0901\u0917\u093e \u0917\u092f\u093e\u0964",
                    "required": bool(r.get("required")), "conditional": False,
                    "custom": True, "added_by": r.get("added_by") or "", "row": r})
    return out


async def removed_docs(claim_id: int) -> list[dict]:
    """What was taken off this claim's list, who took it off and why - a removal is a decision
    somebody has to be able to explain later."""
    return [{"doc_key": r["doc_key"], "label": (r.get("custom_label") or "").strip(),
             "by": r.get("removed_by") or "", "at": r.get("removed_at"),
             "reason": r.get("removed_reason") or ""}
            for r in await _rows(claim_id) if r.get("removed_at")]


async def add_custom_doc(claim_id: int, label: str, *, by: str, required: bool = True) -> dict:
    """Ask this claim for something the template never anticipated."""
    label = (label or "").strip()[:120]
    if not label:
        return {"ok": False, "error": "Say what document you need."}
    key = "x_" + "".join(ch if ch.isalnum() else "_" for ch in label.lower()).strip("_")[:48]
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        existing = await (await conn.execute(
            "SELECT doc_key, removed_at FROM nidaan_claim_doc_checklist WHERE claim_id=? "
            "AND doc_key=?", (claim_id, key))).fetchone()
        if existing and not existing["removed_at"]:
            return {"ok": False, "error": "That is already on the list."}
        if existing:
            # It was removed before and is being asked for again - revive the same row so the
            # history of both decisions stays on one line.
            await conn.execute(
                "UPDATE nidaan_claim_doc_checklist SET removed_at=NULL, removed_by='', "
                "removed_reason='', custom_label=?, required=?, added_by=?, "
                "updated_at=datetime('now') WHERE claim_id=? AND doc_key=?",
                (label, 1 if required else 0, (by or "")[:80], claim_id, key))
        else:
            await conn.execute(
                "INSERT INTO nidaan_claim_doc_checklist (claim_id, doc_key, required, "
                "conditional, received, custom_label, added_by) VALUES (?,?,?,0,0,?,?)",
                (claim_id, key, 1 if required else 0, label, (by or "")[:80]))
        await conn.commit()
    return {"ok": True, "doc_key": key, "label": label}


async def remove_doc(claim_id: int, doc_key: str, *, by: str, reason: str = "") -> dict:
    """Take a document off this claim's list.

    A reason used to be compulsory. The founder's call (16 Sep): staff tidying a list should not
    have to write a sentence every time, and nobody is told when a line comes off. Who removed it
    and when is still recorded, the row is still kept rather than deleted, and a reason is still
    saved when one is given — so "why did we stop asking for the FIR?" can still be answered by
    the person who did it."""
    reason = (reason or "").strip()
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT received FROM nidaan_claim_doc_checklist WHERE claim_id=? AND doc_key=?",
            (claim_id, doc_key))).fetchone()
        if r is None:
            # A template item nobody has touched yet has no row. Create one, already removed, so
            # the decision is recorded rather than silently applied.
            await conn.execute(
                "INSERT INTO nidaan_claim_doc_checklist (claim_id, doc_key, required, "
                "conditional, received, removed_at, removed_by, removed_reason) "
                "VALUES (?,?,0,0,0,datetime('now'),?,?)",
                (claim_id, doc_key, (by or "")[:80], reason[:400]))
        else:
            await conn.execute(
                "UPDATE nidaan_claim_doc_checklist SET removed_at=datetime('now'), removed_by=?, "
                "removed_reason=?, updated_at=datetime('now') WHERE claim_id=? AND doc_key=?",
                ((by or "")[:80], reason[:400], claim_id, doc_key))
        await conn.commit()
    return {"ok": True}


async def restore_doc(claim_id: int, doc_key: str, *, by: str) -> dict:
    """Put a removed document back on the list."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_claim_doc_checklist SET removed_at=NULL, removed_by='', "
            "removed_reason='', added_by=?, updated_at=datetime('now') "
            "WHERE claim_id=? AND doc_key=? AND removed_at IS NOT NULL",
            ((by or "")[:80], claim_id, doc_key))
        await conn.commit()
    return {"ok": cur.rowcount > 0}


async def pending_required_docs(claim_id: int, claim_type: str) -> list[dict]:
    """The still-missing REQUIRED docs — the single source for de-dup + pay-gate.
    Returns enriched doc dicts (key + labels + why) so callers can render asks."""
    pending = []
    for d in await effective_docs(claim_id, claim_type):
        r = d.get("row")
        # required if the template says so OR the reviewer marked it required
        is_required = (r["required"] == 1) if r else d["required"]
        received = (r["received"] == 1) if r else False
        if is_required and not received:
            pending.append({k: v for k, v in d.items() if k != "row"})
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


async def unmark_doc_by_doc_id(claim_id: int, doc_id: int) -> bool:
    """When a customer deletes a document, clear the checklist item that pointed to it
    so it shows as still-needed (Upload) again instead of a stale 'Received'."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_claim_doc_checklist SET received=0, received_via=NULL, "
            "received_doc_id=NULL, updated_at=datetime('now') "
            "WHERE claim_id=? AND received_doc_id=?", (claim_id, doc_id))
        await conn.commit()
        return cur.rowcount > 0


async def checklist_status(claim_id: int, claim_type: str) -> dict:
    """Full status for dashboard/ops: counts + pending + complete flag."""
    rows = {r["doc_key"]: r for r in await _rows(claim_id)}
    # original filenames of received docs, so the customer sees exactly what they attached
    doc_ids = [r["received_doc_id"] for r in rows.values() if r and r["received_doc_id"]]
    names = {}
    if doc_ids:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            ph = ",".join("?" * len(doc_ids))
            for dr in await (await conn.execute(
                    f"SELECT doc_id, original_name FROM nidaan_claim_documents WHERE doc_id IN ({ph})",
                    doc_ids)).fetchall():
                names[dr["doc_id"]] = dr["original_name"]
    required_total = received_required = 0
    items = []
    for d in await effective_docs(claim_id, claim_type):
        r = d.pop("row", None)
        is_required = (r["required"] == 1) if r else d["required"]
        received = (r["received"] == 1) if r else False
        via = r["received_via"] if r else None
        rdid = r["received_doc_id"] if r else None
        if is_required:
            required_total += 1
            received_required += 1 if received else 0
        items.append({**d, "required_effective": is_required,
                      "received": received, "received_via": via,
                      "received_doc_id": rdid, "received_name": names.get(rdid)})
    complete = required_total > 0 and received_required == required_total
    return {
        "claim_id": claim_id,
        "claim_type": canonical_type(claim_type),
        "required_total": required_total,
        "received_required": received_required,
        "complete": complete,
        "items": items,
    }
