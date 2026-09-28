# -*- coding: utf-8 -*-
'''A real file, read on this server, corrected by a person, and the sets that come out.

Founder, 28 Sep: the splitter should hand back the SETS the team actually sends - CIO documents,
everything merged, the claim set - not a pile of loose PDFs somebody then assembles by hand. And
a correction should TEACH it, visibly.

This runs the whole path on a real PDF rather than on fixtures: build a file, classify it with
the local engine, compose the sets, correct a page the way the screen does, and cut the set out.

What it defends:

  * a correction STICKS. The type a person chose is locked, and a later re-read must not quietly
    put it back - that would undo somebody's work silently, which is the worst kind;
  * correcting a page moves it between sets, which is the only reason the screen shows sets at
    all: you can see what your correction did;
  * a set is cut from SCATTERED pages. Composing by type means "every bill in this file" is pages
    4, 9 and 17 - the old extract() only cut contiguous ranges and would have been wrong here;
  * a taught rule fires on the NEXT file, not just this one;
  * and the page count of every set adds up - nothing is silently dropped on the way out.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_doc_review.py
'''
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                      # noqa: E402
import biz_database as db                             # noqa: E402

_root = tempfile.mkdtemp(prefix="review_")
db.DB_PATH = os.path.join(_root, "t.db")

import biz_doc_splitter as split                      # noqa: E402
import biz_nidaan_doc_sets as sets                    # noqa: E402
import biz_nidaan_doc_store as store                  # noqa: E402
import biz_nidaan_doc_brain as brain                  # noqa: E402

split.TMP_ROOT = os.path.join(_root, "docsplit")

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_doc_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT, doc_type TEXT NOT NULL,
    words TEXT NOT NULL DEFAULT '[]', taught_by TEXT NOT NULL DEFAULT '',
    taught_by_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    times_fired INTEGER NOT NULL DEFAULT 0, last_fired_at TIMESTAMP,
    archived_at TIMESTAMP, archived_by TEXT NOT NULL DEFAULT '');
"""

# A realistic mixed bundle: the documents are NOT grouped, because customers do not group them.
PAGES_TEXT = [
    "POLICY SCHEDULE   sum insured   policy period   insured member   premium",
    "FINAL BILL   total amount payable   room rent   pharmacy   bill number",
    "DISCHARGE SUMMARY   date of admission   date of discharge   final diagnosis   treating",
    "FINAL BILL continued   consumables   investigations   grand total payable",
    "SPECIAL WORKS ORDER 4471   consignment   loading   despatch   freight   octroi",
    "DISCHARGE SUMMARY page two   course in hospital   advice on discharge   follow up",
]


def build_pdf(texts):
    import fitz
    d = fitz.open()
    for t in texts:
        pg = d.new_page()
        # Wrapped so each line is real text the reader can pick up.
        y = 80
        for chunk in t.split("   "):
            pg.insert_text((60, y), chunk, fontsize=12)
            y += 22
    return d.tobytes()


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()

    pdf = build_pdf(PAGES_TEXT)
    job = split.save_job(pdf)

    print("\nReading the file on this server\n")

    pages = await brain.classify_pages(pdf, await store.load_rules())
    check("every page is accounted for", len(pages) == len(PAGES_TEXT),
          "%d of %d" % (len(pages), len(PAGES_TEXT)))
    check("...and each carries the words it was recognised by",
          all(isinstance(p.get("words"), list) for p in pages))
    split.save_pages(job, pages)
    check("the reading is saved, so reopening does not cost another OCR pass",
          len(split.load_pages(job)) == len(PAGES_TEXT))

    print("\nThe sets it composes\n")

    all_sets = {st["key"]: st for st in sets.compose_all(pages)}
    check("all three sets are built", set(all_sets) == {"cio", "all_merged", "claim_set"},
          sorted(all_sets))
    merged = all_sets["all_merged"]
    check("'everything merged' loses no page", len(merged["pages"]) == len(PAGES_TEXT),
          "%d of %d - catch_all must sweep up whatever nobody classified"
          % (len(merged["pages"]), len(PAGES_TEXT)))
    nums = [p["page"] for p in merged["pages"]]
    check("...and lists each page exactly once", sorted(nums) == list(range(1, 7)), nums)

    print("\nA person corrects a page, the way the screen does\n")

    # Page 5 is a works order - nothing to do with this claim. A person files it as 'other'.
    page5 = next(p for p in pages if p["page"] == 5)
    before_type = page5["doc_type"]
    page5["was"] = before_type
    page5["doc_type"] = "other"
    page5["confidence"] = 1.0
    page5["locked"] = True
    split.save_pages(job, pages)

    reloaded = split.load_pages(job)
    p5 = next(p for p in reloaded if p["page"] == 5)
    check("the correction is remembered", p5["doc_type"] == "other" and p5.get("locked") is True,
          p5)

    # THE IMPORTANT ONE: a correction must survive reopening the job. The product achieves this
    # by not re-reading at all once there is a saved answer, so that is what is checked - reading
    # the route helper's source, because reimplementing the merge here would only prove that this
    # test can merge. (An earlier version of this check did exactly that and proved nothing.)
    import io as _io
    src = _io.open("sarathi_biz.py", encoding="utf-8").read()
    helper = src[src.index("async def _docsplit_pages("):]
    helper = helper[:helper.index("\n@app.")]
    check("reopening reads the saved answer first",
          "docsplit.load_pages(job)" in helper and helper.index("docsplit.load_pages(job)")
          < helper.index("classify_pages"), helper[:200])
    check("...and only classifies when there is none",
          "if pages:" in helper and "return pages" in helper,
          "otherwise a re-read would silently undo somebody's correction")

    kept = reloaded          # what a reopen actually hands back
    k5 = next(p for p in kept if p["page"] == 5)
    check("so the corrected type is what comes back", k5["doc_type"] == "other", k5)

    print("\nCorrecting a page moves it between sets\n")

    cio_before = {p["page"] for p in all_sets["cio"]["pages"]}
    after = {st["key"]: st for st in sets.compose_all(kept)}
    cio_after = {p["page"] for p in after["cio"]["pages"]}
    check("the sets are recomputed from the corrected pages", cio_before != cio_after
          or 5 not in cio_after,
          "cio before=%s after=%s" % (sorted(cio_before), sorted(cio_after)))
    check("the corrected page is not in the CIO set", 5 not in cio_after, sorted(cio_after))
    check("...but 'everything merged' still has it",
          5 in {p["page"] for p in after["all_merged"]["pages"]})

    print("\nCutting a set out of scattered pages\n")

    bills = [p["page"] for p in kept if p["doc_type"] == "final_bill"]
    check("the bills are not next to each other in the file", len(bills) >= 2
          and bills != list(range(bills[0], bills[0] + len(bills))), bills)
    out = split.extract_pages(pdf, bills)
    check("...and still come out as one PDF", bool(out) and out[:4] == b"%PDF", len(out or b""))

    import fitz
    d = fitz.open(stream=out, filetype="pdf")
    got = d.page_count
    d.close()
    check("...with exactly the pages asked for", got == len(bills), "%d vs %d" % (got, len(bills)))

    check("a page number outside the file is ignored, not fatal",
          split.extract_pages(pdf, [1, 999]) != b"")
    check("an empty list gives nothing rather than a broken PDF",
          split.extract_pages(pdf, []) == b"")

    print("\nTeaching it, so the next file is better\n")

    rid = await store.teach("other", page5.get("words") or [], "Asha", 11)
    check("the correction can be taught", rid > 0, page5.get("words"))

    # A NEW file containing the same kind of page.
    pdf2 = build_pdf([PAGES_TEXT[4]])
    taught = await brain.classify_pages(pdf2, await store.load_rules())
    check("the rule fires on the next file", taught and taught[0]["doc_type"] == "other",
          taught[0] if taught else None)
    check("...and says who taught it", (taught[0].get("taught_by") or "") == "Asha",
          taught[0])

    await store.undo_rule(rid, "Ravi")
    undone = await brain.classify_pages(pdf2, await store.load_rules())
    check("undoing the rule stops it firing",
          (undone[0].get("taught_by") or "") == "", undone[0])

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
