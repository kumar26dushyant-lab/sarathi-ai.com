# -*- coding: utf-8 -*-
"""Document sets — what each page IS, and which bundles it belongs in.

Founder, 28 Sep 2026: the splitter should stop being a splitter and start being a tool that
understands a claim file and hands back ready-made SETS.

THE INSIGHT THAT SHAPES ALL OF THIS. Look at what he asked for: the policy copy appears in the
CIO set AND in the claim set. Final bill and receipts appear in both. "All docs merged" contains
everything. The sets OVERLAP — so they are not a split, and the old model (every page in exactly
one document) cannot express them.

    Classify once. Compose many.

A page gets a TYPE. A set is then an ordered list of types. One correction to a page's type
fixes that page in every set at once, which is also the only reason teaching the tool is worth
anything — a lesson that fixed one bundle and not the others would be worth very little.

It also makes the ORDER he drew into data rather than code: changing what goes into CIO, or in
what order, is editing a list here, not a deploy.

WHY A FIXED VOCABULARY. Today the classifier returns free text - "Discharge Summary", "discharge
summary sheet", "DISCHARGE SUMMARY (FINAL)" are three different answers to the same question, and
you cannot build a set out of free text. Every page maps to one of DOC_TYPES or to `other`, and
`other` is a real answer rather than a failure.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger("nidaan.doc.sets")

# ── the vocabulary ──────────────────────────────────────────────────────────
# key -> (English label, Hindi label, what it looks like - shown to staff and given to the model)
DOC_TYPES: dict[str, tuple] = {
    "policy":        ("Policy copy", "पॉलिसी कॉपी",
                      "the insurance policy schedule or certificate, policy number, sum insured"),
    "rejection":     ("Rejection / deduction letter", "रिजेक्शन / कटौती पत्र",
                      "the insurer's letter repudiating, rejecting, partly paying or deducting"),
    "kyc":           ("KYC / ID proof", "KYC / पहचान पत्र",
                      "Aadhaar, PAN, passport, voter ID, driving licence — any identity document"),
    "claim_form":    ("Claim form", "क्लेम फ़ॉर्म",
                      "the insurer's claim form, Part A or Part B, signed by the insured"),
    # "(DS)" - what staff call it. A discharge CARD is the same document and is filed here.
    "discharge":     ("Discharge summary (DS)", "डिस्चार्ज समरी (DS)",
                      "the hospital's discharge summary or discharge card, with diagnosis and course"),
    "final_bill":    ("Final bill", "फ़ाइनल बिल",
                      "the hospital's final or consolidated bill, the summary of charges"),
    "receipt":       ("Payment receipt", "पेमेंट रसीद",
                      "money received — a receipt or payment acknowledgement, not a bill"),
    "pharmacy_bill": ("Medicine bill", "दवा का बिल",
                      "a pharmacy or chemist bill for medicines"),
    "other_bill":    ("Other bill", "अन्य बिल",
                      "any other bill — investigation, consultation, implant, ambulance"),
    "investigation": ("Investigation report", "जाँच रिपोर्ट",
                      "lab, pathology, radiology, scan or any diagnostic report"),
    "prescription":  ("Prescription", "पर्ची / प्रिस्क्रिप्शन",
                      "a doctor's prescription or advice slip"),
    "cashless":      ("Cashless / pre-auth letter", "कैशलेस / प्री-ऑथ पत्र",
                      "pre-authorisation request, approval or denial from the insurer or TPA"),
    "bank":          ("Bank details", "बैंक डिटेल",
                      "cancelled cheque, passbook page or bank account details"),
    # Non-health claims are 7% of this firm's volume (14 of 201 claims, measured 28 Sep) but
    # these three cover most of what life and motor cases actually send, and they cost almost
    # nothing to recognise.
    "death_cert":    ("Death certificate", "मृत्यु प्रमाण पत्र",
                      "a death certificate, or a hospital's cause-of-death certificate"),
    "fir":           ("FIR / incident report", "FIR / घटना रिपोर्ट",
                      "a police FIR, accident report or fire brigade report"),
    "surveyor":      ("Surveyor report", "सर्वेयर रिपोर्ट",
                      "an insurance surveyor's assessment of damage or loss"),
    "other":         ("Other document", "अन्य दस्तावेज़",
                      "anything that is none of the above — a real answer, not a failure"),
}

# Things that are bills of some kind, for rules that speak about "all bills".
BILL_TYPES = ("final_bill", "pharmacy_bill", "other_bill", "receipt")


# ── the sets ────────────────────────────────────────────────────────────────
# Each set is an ORDERED list of types. A type that is not present is skipped - the founder's
# "whatever is available". `catch_all` sweeps up anything not already named, so no page is ever
# silently dropped from a bundle that is meant to be complete.
#
# CIO keeps its name: the team already calls it that, exactly as they call the Lokpal reference
# a BHP number. A label staff recognise is worth more than a label that explains itself.
SETS: dict[str, dict] = {
    "cio": {
        "label": "CIO documents",
        "label_hi": "CIO दस्तावेज़",
        "why": "The set the team sends as CIO documents.",
        "order": ["policy", "rejection", "kyc", "claim_form", "discharge", "final_bill", "receipt"],
        "catch_all": False,
        # Only the 'other documents' PDF is capped - the founder was explicit, 28 Sep.
        "size_cap_mb": None,
    },
    "all_merged": {
        "label": "All documents merged",
        "label_hi": "सारे दस्तावेज़ एक साथ",
        "why": "Everything in the file, in a sensible order, as one PDF.",
        "order": ["policy", "claim_form", "kyc", "discharge", "investigation", "prescription",
                  "final_bill", "pharmacy_bill", "other_bill", "receipt", "cashless",
                  "rejection", "bank"],
        "catch_all": True,
        "size_cap_mb": None,
    },
    "claim_set": {
        # Named here rather than asked about: the founder said "can be anything suitable".
        # Plain words a Tier II/III reader gets first time.
        "label": "Claim set",
        "label_hi": "क्लेम सेट",
        "why": "The medical and money evidence, in the order it reads best.",
        "order": ["discharge", "policy", "final_bill", "receipt", "pharmacy_bill", "other_bill",
                  "investigation"],
        "catch_all": True,
        "size_cap_mb": None,
    },
}

# The one cap the founder named: the "other documents" PDF, under 10 MB.
OTHER_DOCS_CAP_MB = 10


def type_label(key: str, lang: str = "en") -> str:
    row = DOC_TYPES.get(key) or DOC_TYPES["other"]
    return row[1] if lang == "hi" else row[0]


def set_label(key: str, lang: str = "en") -> str:
    s = SETS.get(key) or {}
    return (s.get("label_hi") if lang == "hi" else s.get("label")) or key


def compose(pages: list, set_key: str) -> dict:
    """Build one set from classified pages. Returns {key, label, pages:[...], missing:[...]}.

    `pages` is [{page, doc_type, confidence, ...}] — the classifier's output, already corrected.

    Ordering is by TYPE first (the order the founder drew), then by original page number inside a
    type, so a three-page discharge summary stays in its own order. A type nobody has a page for
    is simply skipped and reported in `missing` — "whatever is available", and the gap is named
    rather than hidden.
    """
    spec = SETS.get(set_key)
    if not spec:
        return {"key": set_key, "label": set_key, "pages": [], "missing": [], "error": "unknown set"}

    by_type: dict[str, list] = {}
    for p in pages or []:
        by_type.setdefault(p.get("doc_type") or "other", []).append(p)
    for t in by_type:
        by_type[t].sort(key=lambda x: int(x.get("page") or 0))

    out, used, missing = [], set(), []
    for t in spec["order"]:
        got = by_type.get(t) or []
        if not got:
            missing.append(t)
            continue
        for p in got:
            out.append(p)
            used.add(int(p["page"]))

    if spec.get("catch_all"):
        # The types the set does not name, still kept TOGETHER - each type in the order it first
        # appears, its pages in order. Sorted by page alone they interleaved: on claim 204 the
        # claim set held prescriptions in three places, so "one PDF per document" gave three
        # Prescription PDFs and the single PDF scattered one document across it.
        leftovers = [p for p in (pages or []) if int(p.get("page") or 0) not in used]
        leftovers.sort(key=lambda x: int(x.get("page") or 0))
        first: dict = {}
        for p in leftovers:
            first.setdefault(p.get("doc_type") or "other", int(p.get("page") or 0))
        leftovers.sort(key=lambda x: (first[x.get("doc_type") or "other"],
                                      int(x.get("page") or 0)))
        out.extend(leftovers)

    return {"key": set_key, "label": spec["label"], "label_hi": spec["label_hi"],
            "why": spec["why"], "pages": out, "missing": missing}


def compose_all(pages: list) -> list:
    """Every set, in the order staff see them."""
    return [compose(pages, k) for k in SETS]


# ── learning, the visible kind ──────────────────────────────────────────────
# A correction is stored as a RULE somebody can read, check and delete. Founder's choice,
# 28 Sep. The alternative - feeding corrections invisibly into the model - buys the same
# accuracy and costs the ability to answer "why did it file it there", which on medical
# documents is not a trade worth making.

_WORD = re.compile(r"[A-Za-z]{4,}")
STOP = {"page", "this", "that", "with", "from", "have", "been", "will", "your", "name",
        "date", "total", "amount", "number", "patient", "hospital", "the", "and", "for"}


def fingerprint(text: str, limit: int = 8) -> list:
    """The handful of words that make a page recognisable — the readable part of a rule.

    Deliberately words, not a hash. A rule has to be something a person can look at and say
    "yes, that is a rejection letter" or "no, delete that". A hash would be tidier and would
    make the rule screen useless.
    """
    words = [w.lower() for w in _WORD.findall(text or "")]
    seen, out = set(), []
    for w in words:
        if w in STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def rule_matches(rule_words: list, page_words: list, need: int = 4) -> bool:
    """Does this page look like the page the rule was taught on?

    A count of shared distinctive words, not a similarity score. Somebody reading the rule
    screen can be told 'matches when at least 4 of these 8 words appear', and that sentence is
    true — which a cosine distance would not be.
    """
    if not rule_words or not page_words:
        return False
    return len(set(rule_words) & set(page_words)) >= min(need, len(rule_words))


def apply_rules(pages: list, rules: list) -> list:
    """Re-type pages that match a taught rule. Returns the pages, annotated.

    A rule always beats the model. Somebody looked at that page and said what it was; the model
    guessed. When a rule fires, the page carries `taught_by` so the review screen can say why it
    is filed where it is, rather than leaving staff to wonder whether the AI got lucky.
    """
    if not rules:
        return pages
    for p in pages or []:
        pw = p.get("words") or []
        for r in rules:
            if rule_matches(r.get("words") or [], pw):
                if p.get("doc_type") != r.get("doc_type"):
                    p["was"] = p.get("doc_type")
                p["doc_type"] = r.get("doc_type")
                p["confidence"] = 1.0
                p["taught_by"] = r.get("taught_by") or "a colleague"
                p["rule_id"] = r.get("rule_id")
                break
    return pages
