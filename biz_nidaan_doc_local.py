# -*- coding: utf-8 -*-
"""Reading claim documents ON THIS SERVER. No page ever leaves it.

Founder, 28 Sep 2026: *"nidaanpartner.com carries medical data, so we cannot plug AI directly to
see doc... so no AI is needed for this. Means data should be secure."*

He is right, and the exposure was wider than the splitter he was asking about. Four paths sent
whole documents to Google: the splitter's segmenter, its prompt-library tasks,
`doc_intake.match_document` - which is EVERY document arriving by WhatsApp, Telegram or the web -
and the WhatsApp orchestrator. His decision: all four. Nothing leaves the server.

WHY THIS WORKS WITHOUT A MODEL. Claim paperwork is not a reasoning problem, it is a recognition
problem. A discharge summary says DISCHARGE SUMMARY. A policy schedule says POLICY SCHEDULE or
CERTIFICATE OF INSURANCE. A repudiation says REPUDIATION or "we regret to inform". These are
printed headings on standardised forms, and matching them is something a table of weighted terms
does well - in milliseconds, for nothing, and identically every time.

AND IT GETS BETTER THAN A GENERAL MODEL WOULD. The taught rules in biz_nidaan_doc_sets are
learned from THIS firm's insurers and THIS firm's hospitals. A general model knows insurance
paperwork; this will come to know Star Health's rejection letterhead and that particular
hospital's bill format. Narrow beats broad when the corpus is narrow.

WHAT IT CANNOT DO, said plainly:
  * A photograph has no text layer. Without OCR such a page classifies as `other`, low
    confidence - which the review screen floats to the top rather than filing wrongly.
  * Handwriting will not classify. Neither would the model, reliably.
  * Day one is worse than Gemini was. Day thirty should be better, because the rules will be
    yours. The design absorbs the bad start: `other` is a real answer, not a failure.

OCR is OPTIONAL and pluggable. If pytesseract and the tesseract binary are present it is used
for pages with no text layer; if not, those pages are honestly marked unreadable rather than
guessed at. Nothing here ever reaches for the network.
"""
from __future__ import annotations

import logging
import os
import re
import time

logger = logging.getLogger("nidaan.doc.local")

# ── the signatures ──────────────────────────────────────────────────────────
# type -> [(regex, weight)]. Weight says how much a hit MEANS, not how often it appears.
# A heading is decisive; a word that shows up on every bill is nearly worthless.
#
# Tuned for Indian health-insurance paperwork, English and Devanagari. Everything is matched
# case-insensitively against the page's text.
SIGNATURES: dict[str, list] = {
    "discharge": [
        (r"discharge\s+summary", 10), (r"discharge\s+card", 9), (r"डिस्चार्ज", 8),
        (r"course\s+in\s+(the\s+)?hospital", 6), (r"final\s+diagnosis", 5),
        (r"date\s+of\s+admission", 3), (r"date\s+of\s+discharge", 4),
        (r"condition\s+(at|on)\s+discharge", 5), (r"treatment\s+given", 3),
    ],
    "policy": [
        (r"policy\s+schedule", 10), (r"certificate\s+of\s+insurance", 9),
        (r"पॉलिसी", 6), (r"sum\s+insured", 6), (r"period\s+of\s+insurance", 6),
        (r"policy\s+(no|number)", 4), (r"nominee", 3), (r"premium", 2),
        (r"insured\s+member", 2),
    ],
    "rejection": [
        # Tuned against the letters this firm ACTUALLY receives, 28 Sep. The phrasing I had
        # imagined - "we regret to inform", "repudiated" - appears in almost none of them.
        # Star Health, the commonest insurer here, writes: "We regret we are unable to admit
        # the claim for the below-mentioned reason/s". Eleven real letters classified as
        # `other` because of that gap.
        (r"unable\s+to\s+admit\s+the\s+claim", 12),
        (r"we\s+regret\s+we\s+are\s+unable", 11),
        (r"below[- ]mentioned\s+reason", 9),
        (r"claim\s+intimation\s+number", 8),
        (r"repudiat", 12), (r"we\s+regret\s+to\s+inform", 9),
        (r"claim\s+(is|stands|has\s+been)\s+(rejected|repudiated|denied)", 11),
        (r"claim\s+rejection|rejection\s+of\s+claim", 10), (r"rejection\s+letter", 10),
        (r"denial\s+(letter|of\s+claim)", 10),
        (r"not\s+(payable|admissible)", 6), (r"exclusion\s+clause", 6), (r"deduction", 4),
        (r"closure\s+of\s+(the\s+)?claim", 6), (r"अस्वीकृत", 7),
    ],
    "kyc": [
        (r"aadhaar|aadhar", 12), (r"आधार", 11),
        (r"unique\s+identification\s+authority", 11),
        (r"permanent\s+account\s+number", 10), (r"income\s+tax\s+department", 8),
        (r"election\s+commission", 9), (r"driving\s+licence|driving\s+license", 9),
        (r"republic\s+of\s+india.*passport|passport\s+no", 8),
        (r"\b\d{4}\s?\d{4}\s?\d{4}\b", 5),
    ],
    "claim_form": [
        (r"claim\s+form", 11), (r"part\s+[ab]\b.*claim|claim.*part\s+[ab]\b", 6),
        (r"declaration\s+by\s+the\s+insured", 7),
        (r"details\s+of\s+the\s+insured", 5), (r"to\s+be\s+filled\s+(in\s+)?by", 4),
    ],
    "final_bill": [
        (r"final\s+bill", 11), (r"consolidated\s+bill", 10), (r"bill\s+summary", 9),
        (r"(in\s?patient|ip)\s+bill", 8), (r"summary\s+of\s+charges", 7),
        (r"room\s+rent", 5), (r"bill\s+(no|number)", 3), (r"grand\s+total", 3),
    ],
    "receipt": [
        # The bare word "receipt" used to be worth 8 - heading weight for a word that turns up
        # in the body of half the letters here, which is how a rejection letter scored as a
        # receipt. A common word must not outvote a document's actual heading.
        (r"payment\s+receipt", 10), (r"received\s+with\s+thanks", 10),
        (r"receipt\s+(no|number)", 7), (r"amount\s+received", 7),
        (r"रसीद", 7),
        (r"receipt", 2),
    ],
    "pharmacy_bill": [
        (r"pharmacy", 10), (r"chemist", 10), (r"medical\s+store", 9),
        (r"drug\s+licen[cs]e", 8), (r"batch\s*(no)?\b", 5),
        (r"\bmfg\b|\bexp(iry)?\.?\b", 4), (r"दवा", 5),
    ],
    "other_bill": [
        (r"\bbill\b", 4), (r"\binvoice\b", 6), (r"tax\s+invoice", 7),
        (r"ambulance", 5), (r"implant", 5), (r"consultation\s+charge", 5),
    ],
    "investigation": [
        (r"(pathology|radiology|laboratory)\s+report", 10),
        (r"reference\s+range|normal\s+range|biological\s+ref", 9),
        (r"h(a)?emoglobin|platelet\s+count|creatinine|bilirubin", 8),
        (r"x[- ]?ray|ultrasound|sonograph|ct\s+scan|\bmri\b|\becho\b", 8),
        (r"specimen", 6), (r"जाँच", 5), (r"test\s+(name|result)", 5),
        (r"impression\s*:", 5),
    ],
    "prescription": [
        (r"prescription", 9), (r"\brx\b", 7), (r"पर्ची", 6),
        (r"\btab\.|\bcap\.|\bsyp\.|\binj\.", 5),
        (r"follow\s*up\s+after", 5), (r"advice\s*:", 4),
    ],
    "cashless": [
        (r"pre[- ]?auth", 11), (r"cashless", 10), (r"authorization\s+letter", 8),
        (r"\btpa\b", 6), (r"third\s+party\s+administrator", 7),
        (r"query\s+on\s+pre", 7),
    ],
    "bank": [
        (r"\bifsc\b", 11), (r"cancelled\s+cheque", 11), (r"passbook", 9),
        (r"account\s+(no|number)", 5), (r"branch\s+name", 4),
    ],
    # Non-health claims are 7% of volume here, but these three are most of what life and
    # motor cases send, and recognising them costs nothing.
    "death_cert": [
        (r"death\s+certificate", 12), (r"cause\s+of\s+death", 10),
        (r"मृत्यु\s*प्रमाण", 10),
        (r"registrar\s+of\s+births\s+(and|&)\s+deaths", 10),
        (r"date\s+of\s+death", 6),
    ],
    "fir": [
        (r"first\s+information\s+report", 12), (r"\bf\.?i\.?r\.?\b", 9),
        (r"police\s+station", 6), (r"fire\s+brigade", 8),
        (r"प्रथम\s*सूचना", 9),
        (r"under\s+section\s+\d+", 5),
    ],
    "surveyor": [
        (r"surveyor", 11), (r"survey\s+report", 11),
        (r"loss\s+assessment", 8), (r"assessed\s+loss", 8),
        (r"irda.*surveyor|surveyor.*licence", 7),
    ],
}

_COMPILED = {t: [(re.compile(p, re.I | re.S), w) for p, w in rows]
             for t, rows in SIGNATURES.items()}

# Below this, we say we do not know rather than pick the least-bad option. A wrong confident
# answer costs a staff member their trust in the tool; an honest "not sure" costs one drag.
MIN_SCORE = 8
SURE_MARGIN = 6          # how far ahead the winner must be to count as confident


def score_page(text: str) -> dict:
    """Score one page's text against every signature. Returns {type, confidence, scores, why}."""
    if not (text or "").strip():
        return {"doc_type": "other", "confidence": 0.0, "scores": {}, "why": "no readable text"}

    scores, why = {}, {}
    for t, rows in _COMPILED.items():
        hit, terms = 0, []
        for rx, w in rows:
            m = rx.search(text)
            if m:
                hit += w
                # The WORDS FOUND ON THE PAGE, not the pattern that found them. This used to
                # append rx.pattern, so staff were shown things like
                # "discharge\s+summary, course\s+in\s+(the\s+)?hospital" and could not tell
                # whether the answer was right - which is the only question the line exists to
                # help with.
                terms.append(" ".join((m.group(0) or "").split())[:60].lower())
        if hit:
            scores[t] = hit
            why[t] = terms[:3]

    if not scores:
        return {"doc_type": "other", "confidence": 0.0, "scores": {},
                "why": "nothing recognisable on this page"}

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, best_score = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0

    if best_score < MIN_SCORE:
        return {"doc_type": "other", "confidence": 0.25, "scores": scores,
                "why": "a few weak signs only"}

    margin = best_score - second
    # Confidence is the margin, not the score: a page scoring 20 for a bill and 19 for a
    # pharmacy bill is genuinely uncertain, however high both numbers look.
    conf = 0.55 if margin < SURE_MARGIN else min(0.95, 0.6 + margin / 40.0)
    return {"doc_type": best, "confidence": round(conf, 2), "scores": scores,
            "why": ", ".join(why.get(best, [])[:2])}


# ── getting the text off the page, locally ──────────────────────────────────
# ── what the FILENAME says ───────────────────────────────────────────────────
# Ordered: the first match wins, so the specific comes before the general ("final bill" before
# "bill", "claim form" before anything that might catch "form").
_NAME_HINTS = [
    (r"discharge|dischage|dis\s*charge|\bd\s*s\b\s*(summary)?$", "discharge"),
    (r"claim\s*form", "claim_form"),
    (r"pharmac|chemist|medicine|medical\s*store", "pharmacy_bill"),
    (r"final\s*bill|hospital\s*bill|ipd\s*bill|\binvoice\b|bill\s*summary", "final_bill"),
    (r"receipt|recipt|reciept|payment\s*proof", "receipt"),
    (r"reject|repudiat|denial|deduction", "rejection"),
    (r"pre\s*-?\s*auth|cashless|authori[sz]ation\s*letter", "cashless"),
    (r"\bpolicy\b|policy\s*schedule|cover\s*letter|certificate\s*of\s*insurance", "policy"),
    (r"\bkyc\b|aadhaa?r|adhar|\bpan\s*card\b|\bpan\b|voter|passport|driving\s*licen", "kyc"),
    (r"prescription|\brx\b", "prescription"),
    (r"death\s*cert", "death_cert"),
    (r"\bfir\b|police|panchnama", "fir"),
    (r"surveyor|survey\s*report", "surveyor"),
    (r"cancel+ed\s*cheque|passbook|bank\s*statement|\bneft\b", "bank"),
    (r"lab\s*report|pathology|x\s*-?\s*ray|\bmri\b|\bct\s*scan\b|\busg\b|ultrasound|\becg\b|"
     r"\becho\b|investigation|blood\s*test|\breport\b", "investigation"),
    (r"\bbill\b", "final_bill"),
]
_NAME_RX = [(re.compile(rx, re.I), t) for rx, t in _NAME_HINTS]

# Names a camera, a scanner or WhatsApp generated. They say nothing about the document, and
# guessing from them is how "Scanned_2026..." would become an ultrasound report.
_MACHINE_NAME = re.compile(
    r"^(img|image|scan|scanned|doc|document|whatsapp|pxl|dsc|photo|file|new|cam|screenshot|"
    r"wa|vid|mobile|cs|adobe\s*scan)[\s_\-]*[\d(]", re.I)


def type_from_filename(name: str) -> dict:
    """What the file's own NAME says it is, or {} if it says nothing useful.

    Returns {doc_type, why}. A name a person gave a document is the best signal we have: it
    costs no OCR, and when a staff member renamed the file it is correct by definition.
    """
    raw = (name or "").strip()
    if not raw:
        return {}
    stem = re.sub(r"\.(pdf|jpe?g|png|webp|gif|bmp|tiff?|heic|docx?|xlsx?|csv)$", "", raw,
                  flags=re.I)
    if _MACHINE_NAME.match(stem):
        return {}
    words = re.sub(r"[_\-\.+]+", " ", stem).lower()
    for rx, t in _NAME_RX:
        if rx.search(words):
            return {"doc_type": t, "why": "the file is named “%s”" % raw[:60]}
    return {}


def page_text(doc, index: int, allow_ocr: bool = True) -> tuple:
    """(text, source) for one page. source is 'pdf', 'ocr' or 'none'.

    The text layer first, because it is exact and free. OCR only when there is nothing - a
    photograph of a bill. If OCR is not installed, say so honestly: the page becomes `other`
    with no confidence and the review screen puts it in front of somebody.

    allow_ocr=False means the caller has run out of time for rendering pages. The text layer is
    still read; a page without one comes back as 'none' and goes to a person. Defaults to True so
    every existing caller behaves exactly as it did.
    """
    try:
        text = doc[index].get_text() or ""
    except Exception as e:  # noqa: BLE001
        logger.info("could not read page %s: %s", index + 1, e)
        text = ""
    if len(text.strip()) >= 40:
        return text, "pdf"

    ocr = _ocr_page(doc, index) if allow_ocr else ""
    if ocr:
        return ocr, "ocr"
    return text, ("pdf" if text.strip() else "none")


def ocr_available() -> bool:
    """Is local OCR usable? Checked once per call site, never assumed."""
    try:
        import pytesseract  # noqa: F401
        import shutil
        return bool(shutil.which("tesseract"))
    except Exception:  # noqa: BLE001
        return False


def _ocr_page(doc, index: int) -> str:
    """Render the page and read it with a LOCAL tesseract. Never leaves the machine."""
    if not ocr_available():
        return ""
    try:
        import io as _io
        import pytesseract
        from PIL import Image
        pix = doc[index].get_pixmap(dpi=200)
        img = Image.open(_io.BytesIO(pix.tobytes("png")))
        # English plus Devanagari: half the paperwork here is bilingual.
        return pytesseract.image_to_string(img, lang="eng+hin") or ""
    except Exception as e:  # noqa: BLE001
        logger.info("local OCR failed on page %s: %s", index + 1, e)
        return ""


# How long OCR may spend on ONE file, in seconds. Pages already carrying a text layer are free
# and are never counted against it; only rendering-and-reading a photograph is.
#
# 120s is about eight scanned pages on this box. A staff member watching an upload will wait that
# long; they will not wait twenty minutes, and neither will a proxy. When it runs out the rest of
# the file is still returned - marked not-read, which is honest and puts it in front of somebody.
OCR_BUDGET_S = float(os.getenv("NIDAAN_OCR_BUDGET_S", "120"))


def classify_pdf(pdf_bytes: bytes, rules: list | None = None) -> list:
    """Every page of a merged PDF: what it is, how sure, and why. Nothing leaves the server.

    Returns [{page, doc_type, confidence, why, source, words, new_doc}] — the shape
    biz_nidaan_doc_sets.compose() expects.
    """
    import fitz
    import biz_nidaan_doc_sets as sets

    out = []
    spent = 0.0
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for i in range(doc.page_count):
            t0 = time.monotonic()
            # Once the budget is gone we stop RENDERING pages, but still read any that carry
            # their own text - that costs nothing and is the better answer where it exists.
            text, src = page_text(doc, i, allow_ocr=(spent < OCR_BUDGET_S))
            spent += time.monotonic() - t0
            res = score_page(text)
            out.append({
                "page": i + 1,
                "doc_type": res["doc_type"],
                "confidence": res["confidence"],
                "why": res["why"],
                "source": src,
                "words": sets.fingerprint(text),
            })
    finally:
        doc.close()

    # A page that looks like the one before it, and is not sure of itself, is almost always a
    # continuation - page 2 of a bill rarely repeats the heading that named it.
    #
    # ONLY A PAGE WE ACTUALLY READ. A page whose text we never saw ('none' - a photograph we had
    # no time or no OCR for) has nothing to continue FROM: calling it page 2 of the bill above is
    # a guess about content nobody has looked at, and it would file the page into that bundle.
    # Left as 'other' with no confidence, it goes to a person instead, which is the honest answer.
    for i in range(1, len(out)):
        prev, cur = out[i - 1], out[i]
        if cur["source"] == "none":
            continue
        if cur["doc_type"] == "other" and cur["confidence"] < 0.5 and prev["confidence"] >= 0.6:
            cur["doc_type"] = prev["doc_type"]
            cur["confidence"] = 0.5
            cur["why"] = "continues the previous page"
    for i, p in enumerate(out):
        p["new_doc"] = (i == 0) or (p["doc_type"] != out[i - 1]["doc_type"])

    # Anything a person has taught beats anything this file worked out.
    return sets.apply_rules(out, rules or [])
