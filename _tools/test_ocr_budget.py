# -*- coding: utf-8 -*-
'''OCR cannot run away with the server, and it cannot block it either.

Swapping Gemini for a reader that runs here changed the SHAPE of the work, not just its location.
The old call was one network round trip. Reading pages is blocking CPU work, and OCR on this box
costs about fifteen seconds a page - so a 40-page scanned bundle in a request handler would freeze
every other request on that worker for ten minutes. That is an outage, not a slow page, and no
test of correctness would have caught it.

What these checks defend:

  * a file with more scanned pages than the budget allows still RETURNS, with every page
    accounted for - a partial answer a person corrects beats a timeout;
  * pages that carry their own text are never charged against the OCR budget, because reading
    them costs nothing;
  * the classification really does leave the event loop, so a long read does not stall the
    worker serving everyone else;
  * and a page that could not be read says so ('none') rather than quietly looking like an
    empty document somebody might trust.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_ocr_budget.py
'''
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# A budget of zero: no page may be rendered. Set BEFORE the module is imported, because the
# constant is read at import time.
os.environ["NIDAAN_OCR_BUDGET_S"] = "0"

import biz_nidaan_doc_local as local   # noqa: E402

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail:
            print("           " + str(detail))


def mixed_pdf(text_pages: int, blank_pages: int) -> bytes:
    """Pages with a real text layer, then pages with nothing - a scan, as far as we can tell."""
    import fitz
    d = fitz.open()
    for i in range(text_pages):
        p = d.new_page()
        p.insert_text((60, 90), "FINAL BILL - total amount payable - bill no %d" % (i + 1),
                      fontsize=13)
    for _ in range(blank_pages):
        d.new_page()
    return d.tobytes()


print("\nWith the OCR budget exhausted\n")

pdf = mixed_pdf(text_pages=3, blank_pages=5)
t0 = time.monotonic()
pages = local.classify_pdf(pdf, [])
took = time.monotonic() - t0

check("every page is still accounted for", len(pages) == 8, "got %d" % len(pages))
check("it returns promptly instead of grinding through OCR", took < 20,
      "took %.1fs" % took)

with_text = [p for p in pages if p["source"] == "pdf"]
unread = [p for p in pages if p["source"] == "none"]
check("the pages that carry their own text are still read", len(with_text) == 3,
      [p["page"] for p in with_text])
check("...and were not charged against the OCR budget",
      all(p["doc_type"] != "other" for p in with_text),
      [(p["page"], p["doc_type"]) for p in with_text])
check("the pages that needed rendering say plainly they were not read", len(unread) == 5,
      [(p["page"], p["source"]) for p in unread])
check("...and carry no confidence for anyone to trust",
      all(float(p["confidence"]) == 0.0 for p in unread),
      [(p["page"], p["confidence"]) for p in unread])

# A page may be skipped for time, but it must never silently vanish from the numbering.
check("page numbers are continuous, so nothing was dropped",
      [p["page"] for p in pages] == list(range(1, 9)),
      [p["page"] for p in pages])


print("\nOff the event loop\n")

import biz_nidaan_doc_brain as brain  # noqa: E402


async def _ticks_during_classification() -> int:
    """How often can an unrelated task run while a file is being classified?

    The reading itself is SUBSTITUTED with half a second of ordinary blocking work, because the
    real thing on a text-only PDF finishes in about forty milliseconds - fast enough that a
    heartbeat count measures scheduling noise rather than whether the loop was free. With a known
    half-second of blocking, the two outcomes are unmistakable: on the loop the heartbeat cannot
    tick at all; in a worker thread it ticks dozens of times.
    """
    ticks = []

    async def heartbeat():
        while True:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.005)

    def slow_read(pdf_bytes, rules):
        time.sleep(0.5)          # stands in for OCR, which is blocking work of exactly this kind
        return [{"page": 1, "doc_type": "other", "confidence": 0.0, "why": "", "source": "none",
                 "words": [], "new_doc": True}]

    orig = local.classify_pdf
    local.classify_pdf = slow_read
    hb = asyncio.create_task(heartbeat())
    try:
        await asyncio.sleep(0)   # let the heartbeat start, so we are timing the call itself
        before = len(ticks)
        await brain.classify_pages(b"", [])
        return len(ticks) - before
    finally:
        hb.cancel()
        local.classify_pdf = orig


ticks = asyncio.run(_ticks_during_classification())
# Half a second at 5ms is ~100 ticks if the loop is free, and 0 if it is not. Anything above a
# handful can only mean the work went to a thread.
check("the loop kept serving other work during classification", ticks > 10,
      "an unrelated task ran %d time(s) during 0.5s of reading - near 0 means the loop was "
      "blocked" % ticks)

print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
sys.exit(1 if FAILED else 0)
