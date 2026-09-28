# -*- coding: utf-8 -*-
"""The one door every part of the app uses to ask "what is this document?"

Founder, 28 Sep 2026, twice over: no claim document may go to an external AI, and processing
must stay **under our control, inside India** - which leaves the door open to a self-hosted
model on our own GPU box later, without reopening it to Google.

That second answer is why this module exists rather than the four call sites each importing the
rules engine. They ask HERE. Today the answer comes from biz_nidaan_doc_local - text extraction,
local OCR, weighted signatures, and the rules staff have taught. The day there is somewhere of
our own to run a real model, that becomes another provider behind this same door and nothing
that calls it changes.

A provider must never be reachable over the public internet. `PROVIDER` is read from the
environment so a future self-hosted endpoint is configuration, not a deploy - but `local` is the
default and the only one implemented, so the safe thing is also what happens when nobody
configures anything.

WHAT THIS REPLACED. Four paths were sending whole PDFs to Google: the splitter's segmenter, the
splitter's prompt library, doc_intake.match_document - every document arriving by WhatsApp,
Telegram or the web - and the WhatsApp orchestrator.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("nidaan.doc.brain")

PROVIDER = (os.getenv("NIDAAN_DOC_BRAIN") or "local").strip().lower()

# ── our vocabulary -> the checklist keys a claim actually asks for ──────────
# The checklist spans health, life, motor, fire and marine claims. 93% of this firm's claims and
# documents are health (187 of 201 claims, 884 of 947 documents, measured 28 Sep), so the
# signatures are health-first - but the common non-health documents are cheap to recognise and
# are here too. Anything unmatched becomes `other_docs`, which is where an unknown document
# already goes, so the miss is a staff member sorting rather than a document filed wrongly.
TYPE_TO_CHECKLIST: dict[str, tuple] = {
    "policy":        ("policy_document", "policy_bond", "policy_schedule", "marine_policy"),
    "rejection":     ("rejection_letter", "decision_letter", "rejection_or_survey_letter"),
    "kyc":           ("kyc",),
    "claim_form":    ("claim_form", "proposal_form"),
    "discharge":     ("discharge_summary",),
    "final_bill":    ("itemized_bills", "purchase_bills", "repair_estimate"),
    "receipt":       ("itemized_bills",),
    "pharmacy_bill": ("itemized_bills",),
    "other_bill":    ("itemized_bills", "purchase_bills"),
    "investigation": ("other_docs",),
    "prescription":  ("other_docs",),
    "cashless":      ("other_docs",),
    "bank":          ("other_docs",),
    "death_cert":    ("death_certificate", "cause_of_death"),
    "fir":           ("incident_proof",),
    "surveyor":      ("surveyor_report", "survey_report", "rejection_or_survey_letter"),
    "other":         ("other_docs",),
}


async def classify_pages(pdf_bytes: bytes, rules: list | None = None) -> list:
    """Every page: what it is, how sure, and why. The splitter's replacement for `segment`."""
    if PROVIDER != "local":
        logger.warning("doc brain provider %r is not implemented - using local", PROVIDER)
    import biz_nidaan_doc_local as local
    return local.classify_pdf(pdf_bytes, rules or [])


async def match_document(pdf_bytes: bytes, candidates: list,
                         rules: list | None = None) -> dict:
    """Which of the documents this claim still needs is this? A drop-in for the old AI call.

    Returns the same shape the intake has always used - {key, label, confidence, looks_like,
    legible, reason} - so nothing downstream had to change to stop sending documents to Google.

    FAILS OPEN, exactly as before: when it does not know, it says so and the document is stored
    for a person to sort. That property is why swapping the engine underneath is safe - the
    worst case of a less certain local answer is more sorting, never a document filed wrongly.
    """
    unknown = {"key": "", "label": "", "confidence": 0.0, "looks_like": "",
               "legible": True, "reason": ""}
    if not candidates:
        return unknown

    try:
        pages = await classify_pages(pdf_bytes, rules or [])
    except Exception as e:  # noqa: BLE001
        logger.warning("local classification failed: %s", e)
        return unknown
    if not pages:
        return unknown

    # The document's identity is its strongest page, not its first - a scanned bundle often
    # opens on a covering letter or a blank.
    best = max(pages, key=lambda p: float(p.get("confidence") or 0))
    dtype = best.get("doc_type") or "other"
    conf = float(best.get("confidence") or 0)

    # Could we read it at all? The old model judged legibility; here, a document where no page
    # yielded usable text is the same signal - and it is honest about WHY.
    readable = [p for p in pages if p.get("source") in ("pdf", "ocr")]
    legible = bool(readable)
    if not legible:
        import biz_nidaan_doc_local as local
        why = ("we could not read this - it may be a photo, and text recognition is not "
               "installed on the server yet") if not local.ocr_available() else \
              "we could not read any text on it - it may be blurred or too dark"
        return {**unknown, "legible": False, "reason": why,
                "looks_like": "an unreadable scan"}

    wanted = {c.get("key"): c for c in candidates if c.get("key")}
    for key in TYPE_TO_CHECKLIST.get(dtype, ()):
        if key in wanted:
            return {"key": key, "label": wanted[key].get("en") or key,
                    "confidence": conf, "legible": True,
                    "looks_like": _human(dtype),
                    "reason": best.get("why") or ""}

    # Recognised, but not one of the things this claim is waiting for. Say what it looks like
    # so staff are not left guessing - that is the difference between "unsorted" and "useless".
    return {**unknown, "confidence": conf, "looks_like": _human(dtype),
            "reason": "recognised as %s, which is not on this claim's list" % _human(dtype)}


def _human(dtype: str) -> str:
    import biz_nidaan_doc_sets as sets
    if dtype in sets.DOC_TYPES:
        return sets.type_label(dtype).lower()
    return re.sub(r"_", " ", dtype)
