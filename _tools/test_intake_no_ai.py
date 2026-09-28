# -*- coding: utf-8 -*-
'''A claimant's document never leaves this server, and the machine never files it.

Founder, 28 Sep 2026: *"nidaanpartner.com carries medical data, so we cannot plug AI directly to
see doc"*, and then, on how staff should work: *"make it simplify and staff to use it rather
multiple automations keep staff confused about process."*

Both halves need guarding, because both are easy to undo by accident:

  * NO OUTSIDE MODEL. A future edit that reaches for biz_ai in this path would be one line and
    would look perfectly reasonable. The check reads the actual source of every module on the
    claimant document path, so it fails on the line rather than months later.

  * NO AUTOMATIC TICK. The local reader agrees with staff about two times in three. That is a
    good suggestion on a screen where somebody approves it, and a mis-filed claim here, where
    nobody does. So accept() must store the document and tick NOTHING - even when the page says
    "DISCHARGE SUMMARY" in capitals and the checklist is waiting for exactly that.

  * AND IT MUST STILL ASK FOR A BETTER PHOTOGRAPH. That is the one judgement only the claimant
    can act on, it needs no classification, and it would be the easy thing to lose while
    removing the rest.

EVERY CHECK HERE HAS BEEN PROVEN TO FAIL against the code as it was before this change - an
always-passing test is worse than none (founder's rule, and this repo has had several).

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_intake_no_ai.py
'''
import asyncio
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


# ── 1. nothing on this path can reach an outside model ───────────────────────
# Read the source. Importing and hoping never to see a call proves nothing, because the call only
# happens on a document we did not feed it.
print("\nNo claim document leaves this server\n")

PATH_MODULES = [
    "biz_nidaan_doc_intake.py",       # every document a complainant sends
    "biz_nidaan_doc_brain.py",        # the one door to "what is this"
    "biz_nidaan_doc_local.py",        # the reader itself
    "biz_doc_splitter.py",            # the staff splitter, same documents
    "biz_nidaan_wa_orchestrator.py",  # the WhatsApp pipeline around intake
]
# `biz_ai` is the house client for Gemini; the others are how it would be reached directly.
OUTSIDE = re.compile(r"\bbiz_ai\b|google\.genai|generate_content|DOCSPLIT_MODEL|gemini-")

for name in PATH_MODULES:
    src = io.open(name, encoding="utf-8").read()
    # A mention inside a comment or docstring is how we record WHY it went - only code counts.
    code = "\n".join(l for l in src.splitlines()
                     if not l.lstrip().startswith("#"))
    hits = sorted(set(OUTSIDE.findall(code)))
    check("%-32s no outside model in the code" % name, not hits, "found: %s" % hits)


# ── 2. accept() stores, and ticks nothing ────────────────────────────────────
print("\nWhat happens when a complainant sends a document\n")

import biz_nidaan_doc_intake as intake            # noqa: E402
import biz_nidaan_doc_checklist as _ck            # noqa: E402


def a_pdf(text: str) -> bytes:
    """A real one-page PDF with a real text layer, so the reader has something to read."""
    import fitz
    d = fitz.open()
    p = d.new_page()
    p.insert_text((60, 90), text, fontsize=13)
    return d.tobytes()


def a_blank_scan() -> bytes:
    """A page with no text at all - what an unusable photograph looks like to us."""
    import fitz
    d = fitz.open()
    d.new_page()
    return d.tobytes()


class Spy:
    """Stands in for the parts that need a database, and records what was asked of them."""

    def __init__(self):
        self.stored = []
        self.ticked = []

    def install(self):
        self._orig = {}
        self.asked = []

        async def _store(account_id, claim_id, filename, pdf_bytes, source):
            self.stored.append((filename, len(pdf_bytes)))
            return 4242

        async def _match(pdf_bytes, candidates):
            """A matcher that is CERTAIN, so "nothing was ticked" cannot pass by accident.

            Without this the no-tick checks pass on any machine with no API key configured -
            the old code asked Gemini, got no client, and ticked nothing for the wrong reason.
            Here the answer is confident, legible and one the checklist is waiting for. Any code
            that consults a classifier on this path will therefore tick, and the check will fail.
            """
            self.asked.append(len(pdf_bytes))
            return {"key": "discharge", "label": "Discharge summary", "confidence": 1.0,
                    "looks_like": "a discharge summary", "legible": True, "reason": "certain"}

        async def _mark(claim_id, key, via="", doc_id=None):
            self.ticked.append(key)          # must stay empty - that is the whole point
            return True

        async def _pending(claim_id, claim_type):
            return [{"key": "discharge", "en": "Discharge summary"},
                    {"key": "final_bill", "en": "Final hospital bill"}]

        async def _record(claim_id, res, source):
            return None

        async def _scan(data):
            return True, ""

        import biz_av_scan as _av
        for mod, attr, fn in ((intake, "_store", _store), (intake, "_record", _record),
                              (intake, "match_document", _match),
                              (_ck, "mark_doc_received", _mark),
                              (_ck, "pending_required_docs", _pending),
                              (_av, "scan_bytes", _scan)):
            self._orig[(mod, attr)] = getattr(mod, attr, None)
            setattr(mod, attr, fn)
        self._orig[(_ck, "doc_template_for")] = _ck.doc_template_for
        _ck.doc_template_for = lambda ct: [{"key": "discharge"}, {"key": "final_bill"}]

    def restore(self):
        for (mod, attr), fn in self._orig.items():
            if fn is not None:
                setattr(mod, attr, fn)


spy = Spy()
spy.install()
try:
    obvious = a_pdf("DISCHARGE SUMMARY - date of admission 12/03/2026 - final diagnosis")
    res = asyncio.run(intake.accept(7, 1, [("scan.pdf", obvious)],
                                    claim_type="health", source="whatsapp"))

    check("the document is stored", res["stored"] == 1, res)
    check("no classifier is consulted at all on this path", spy.asked == [],
          "match_document was called %d time(s)" % len(spy.asked))
    check("NOTHING is ticked, though a certain matcher says DISCHARGE SUMMARY",
          res["ticked"] == [] and spy.ticked == [],
          "ticked=%s, checklist asked for %s" % (res["ticked"], spy.ticked))
    check("it is put in front of a person instead", len(res["unsorted"]) == 1, res["unsorted"])
    # Indexed defensively on purpose: when this check FAILS the list is empty, and a test that
    # dies on an IndexError reports one finding instead of all of them.
    first = (res["unsorted"] or [{}])[0]
    check("and no guess is attached to it for them to trust",
          bool(res["unsorted"]) and (first.get("looks_like") or "") == ""
          and float(first.get("confidence") or 0) == 0.0,
          res["unsorted"])
    check("the complainant is told nothing about our uncertainty", res["unclear"] == [],
          res["unclear"])

    # The one message that survives, because only they can act on it.
    res2 = asyncio.run(intake.accept(7, 1, [("photo.pdf", a_blank_scan())],
                                     claim_type="health", source="whatsapp"))
    check("an unreadable page still asks for a better photograph", len(res2["unclear"]) == 1,
          res2["unclear"])
    check("...and it is stored anyway, never discarded", res2["stored"] == 1, res2)
    check("...and that is not turned into a filing job as well",
          res2["unsorted"] == [], res2["unsorted"])
finally:
    spy.restore()


# ── 3. what the complainant reads ────────────────────────────────────────────
# Removing the automatic tick created a trap: the outstanding list is now a snapshot from BEFORE
# a person looked, so an unqualified "Still needed: discharge summary" goes to somebody who has
# just sent exactly that. It reads as though we lost it.
print("\nThe reply to somebody who has just sent their documents\n")

import biz_nidaan_wa_messages as msg  # noqa: E402

ctx = {"stored": 3, "ticked": [], "unclear": [],
       "pending": ["Discharge summary", "Final hospital bill"]}

for lang in ("en", "hi", "hinglish"):
    body = msg.compose("doc_batch", lang, ctx)
    check("%-8s says we have them and that a person will look" % lang,
          bool(body) and ("Discharge summary" in body),
          body)
    check("%-8s does not claim they still owe us what they just sent" % lang,
          ("As far as we know" in body or "जहाँ तक हमें पता है" in body
           or "Jahan tak humein pata hai" in body),
          body)

# And when a person HAS ticked something - the staff path still works as it did.
ctx_ticked = {"stored": 1, "ticked": ["Discharge summary"], "unclear": [],
              "pending": ["Final hospital bill"]}
body = msg.compose("doc_batch", "en", ctx_ticked)
check("a confirmed document is still announced plainly",
      "Received" in body and "As far as we know" not in body, body)

print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
sys.exit(1 if FAILED else 0)
