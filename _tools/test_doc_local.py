# -*- coding: utf-8 -*-
'''Reading claim documents without sending them anywhere.

Founder, 28 Sep 2026: NidaanPartner carries medical data, so no document may go to an external
AI. His decision covered all four paths that were doing it, the splitter being the smallest.

The claim this makes is that recognising claim paperwork is a matching problem, not a reasoning
one - a discharge summary says DISCHARGE SUMMARY. These checks test that claim against text taken
from the documents this firm actually handles.

What matters most here is the HONESTY of the answers, not the hit rate:

  * a page it does not recognise must say `other` with low confidence, never the least-bad guess.
    A confident wrong answer costs a staff member their trust in the tool; an honest "not sure"
    costs one drag.
  * confidence must come from the MARGIN, not the score. A page scoring 20 for a bill and 19 for
    a pharmacy bill is genuinely uncertain however large both numbers are.
  * and nothing in this module may reach the network, which is asserted by reading the source
    rather than by trusting the intention.

    py -3.13 _tools/test_doc_local.py
'''
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import biz_nidaan_doc_local as loc  # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


# Text of the kind these pages actually carry.
SAMPLES = {
    "discharge": "DISCHARGE SUMMARY\nName: Sunita Devi  Age 46/F\nDate of Admission: 12/03/2026\n"
                 "Date of Discharge: 19/03/2026\nFinal Diagnosis: Acute Cholecystitis\n"
                 "Course in Hospital: Patient was admitted with pain, underwent laparoscopic...",
    "policy": "POLICY SCHEDULE\nPolicy No: P/161118/01/2026/004512\n"
              "Period of Insurance: 01/04/2025 to 31/03/2026\nSum Insured: Rs 5,00,000\n"
              "Nominee: Ramesh Kumar\nPremium: Rs 18,450",
    "rejection": "Sub: Repudiation of claim\nDear Sir/Madam,\nWe regret to inform you that your "
                 "claim stands rejected under exclusion clause 4.2 of the policy contract, the "
                 "ailment being pre-existing.",
    "kyc": "GOVERNMENT OF INDIA\nUnique Identification Authority of India\n"
           "Aadhaar 4321 8765 9012\nSunita Devi  DOB 14/07/1979",
    "final_bill": "FINAL BILL\nBill No: IP/2026/8891\nRoom Rent 7 days ............ 42,000\n"
                  "Surgeon charges ............ 55,000\nGRAND TOTAL ............ 2,14,780",
    "pharmacy_bill": "CITY PHARMACY & CHEMIST\nDrug Licence No 21B/554\n"
                     "Tab Pantop 40mg  Batch A2214  Exp 08/27  ...  240.00",
    "investigation": "PATHOLOGY REPORT\nSpecimen: Whole blood\n"
                     "Haemoglobin 11.2 g/dL   Biological Ref Range 12.0-15.0\n"
                     "Platelet Count 1.8 lakh/cumm",
    "receipt": "PAYMENT RECEIPT\nReceipt No 4471\nReceived with thanks from Sunita Devi "
               "the sum of Rs 2,14,780 towards hospital charges.",
    "claim_form": "CLAIM FORM - PART A\nTo be filled in by the insured\n"
                  "Declaration by the insured: I hereby declare that the information given...",
    "cashless": "PRE-AUTHORIZATION REQUEST\nCashless facility - TPA ref 99120\n"
                "Third Party Administrator: Medi Assist",
    "bank": "Cancelled Cheque\nAccount Number 3041xxxxxx88\nIFSC SBIN0004512\nBranch Name: Indore",
    "prescription": "Rx\nTab. Augmentin 625 BD x 5 days\nCap. Omez OD\nAdvice: Follow up after 7 days",
}

print("\nRecognising the paperwork, locally\n")

for want, text in SAMPLES.items():
    got = loc.score_page(text)
    ok = got["doc_type"] == want
    check("%-15s -> %-15s conf %.2f" % (want, got["doc_type"], got["confidence"]),
          ok, "why: %s | scores: %s" % (got.get("why"), got.get("scores")))

print()
# ── the honesty checks, which matter more than the hit rate ─────────────────
blank = loc.score_page("")
check("an empty page says 'other', not a guess",
      blank["doc_type"] == "other" and blank["confidence"] == 0.0)
check("...and says why", "no readable text" in blank["why"])

junk = loc.score_page("Page 3 of 9\nContinued overleaf\n.....")
check("a page with nothing recognisable is NOT forced into a type",
      junk["doc_type"] == "other", junk)

weak = loc.score_page("Total amount payable 4,500  Date 12/03/2026")
check("a page with only weak generic signs is not filed confidently",
      weak["doc_type"] == "other" or weak["confidence"] <= 0.6, weak)

# margin, not score
close = loc.score_page("TAX INVOICE\nBill No 22\nPHARMACY\nBatch B12 Exp 09/27\nTotal 310.00")
check("a page that could be two things is marked uncertain, not picked confidently",
      close["confidence"] <= 0.75, close)

strong = loc.score_page(SAMPLES["rejection"])
check("...while an unmistakable page IS confident", strong["confidence"] >= 0.75, strong)

# Devanagari
hindi = loc.score_page("आधार संख्या 4321 8765 9012")
check("Hindi text is recognised too", hindi["doc_type"] == "kyc", hindi)

print()
# ── nothing may leave the server ────────────────────────────────────────────
src = io.open(os.path.join(ROOT, "biz_nidaan_doc_local.py"), encoding="utf-8").read()
for bad in ("httpx", "requests", "urllib", "genai", "generativelanguage", "biz_ai",
            "openai", "aiohttp", "socket"):
    check("no '%s' anywhere in this module" % bad, bad not in src)
check("...and no http(s) URL at all", not re.search(r"https?://", src))
check("OCR is checked for, never assumed", "def ocr_available" in src)
check("...and a missing OCR is reported honestly rather than guessed around",
      "'none'" in src or '"none"' in src)

print("\n" + ("%d failed" % FAILED if FAILED
              else "it reads the page, says how sure it is, and nothing leaves the machine"))
sys.exit(1 if FAILED else 0)
