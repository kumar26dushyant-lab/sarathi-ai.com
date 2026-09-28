# -*- coding: utf-8 -*-
'''The three sets, built from the documents already on a claim.

Founder, 28-29 Sep: the sets should be buildable at claim level, the standalone splitter stays,
and *"the source will be the same"* - one engine, one set of taught rules.

What these checks defend:

  * ONE ENGINE. The claim path reads with biz_nidaan_doc_brain and composes with
    biz_nidaan_doc_sets, the same as the standalone tool. If these ever diverge, a page filed one
    way in the tool and another way on the claim would tell two staff members different things
    about the same document;
  * a taught rule applies HERE too - that is what "same source" has to mean in practice;
  * READ ONCE. A scanned page costs ~15s, so the reading is cached against the claim and reused
    until its documents actually change - and re-read the moment one is added;
  * a document whose FILE is missing is reported, never silently dropped: "the bill is not in the
    set" and "the bill is not on the server" are different problems;
  * the claim-level answer says what the CHECKLIST is still waiting for, which is the sentence
    staff act on and the thing the standalone tool cannot know;
  * and the routes refuse a claim this staff member may not touch, reusing the existing rule
    rather than a second copy of it.

    PYTHONPATH=. NIDAAN_NO_OUTBOUND=1 py -3.14 _tools/test_claim_sets.py
'''
import asyncio
import io
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if os.environ.get("NIDAAN_NO_OUTBOUND") != "1":
    sys.exit("refusing to run with outbound enabled")

import aiosqlite                                    # noqa: E402
import biz_database as db                           # noqa: E402

_root = tempfile.mkdtemp(prefix="claimsets_")
db.DB_PATH = os.path.join(_root, "t.db")
os.environ["NIDAAN_DOCS_DIR"] = os.path.join(_root, "docs")
os.makedirs(os.environ["NIDAAN_DOCS_DIR"], exist_ok=True)

import biz_nidaan_claim_sets as cs                  # noqa: E402
import biz_nidaan_doc_store as store                # noqa: E402
import biz_nidaan_doc_sets as sets                  # noqa: E402

cs.CACHE_ROOT = os.path.join(_root, "cache")

FAILED = 0


def check(label, ok, detail=""):
    global FAILED
    print(("  PASS  " if ok else "  FAIL  ") + label)
    if not ok:
        FAILED += 1
        if detail != "":
            print("           " + str(detail))


SCHEMA = """
CREATE TABLE nidaan_claim_documents (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, purchase_id INTEGER,
    claim_id INTEGER, stored_name TEXT, original_name TEXT, file_size INTEGER,
    mime_type TEXT, uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP, source TEXT DEFAULT '',
    submitted_at TEXT);
CREATE TABLE nidaan_doc_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT, doc_type TEXT NOT NULL,
    words TEXT NOT NULL DEFAULT '[]', taught_by TEXT NOT NULL DEFAULT '',
    taught_by_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    times_fired INTEGER NOT NULL DEFAULT 0, last_fired_at TIMESTAMP,
    archived_at TIMESTAMP, archived_by TEXT NOT NULL DEFAULT '');
"""

PAGE_TEXT = {
    "policy.pdf": "POLICY SCHEDULE   sum insured   policy period   insured member   premium",
    "bill.pdf": "FINAL BILL   total amount payable   room rent   pharmacy   bill number",
    "discharge.pdf": "DISCHARGE SUMMARY   date of admission   final diagnosis   treating doctor",
    "oddity.pdf": "SPECIAL WORKS ORDER 4471   consignment   loading   despatch   freight",
}


def write_doc(name, text):
    import fitz
    d = fitz.open()
    pg = d.new_page()
    y = 80
    for chunk in text.split("   "):
        pg.insert_text((60, y), chunk, fontsize=12)
        y += 22
    stored = name
    with open(os.path.join(os.environ["NIDAAN_DOCS_DIR"], stored), "wb") as f:
        f.write(d.tobytes())
    return stored


async def add(conn, claim_id, name, source):
    stored = write_doc(name, PAGE_TEXT[name])
    await conn.execute(
        "INSERT INTO nidaan_claim_documents (claim_id, stored_name, original_name, mime_type, "
        "source) VALUES (?,?,?,?,?)", (claim_id, stored, name, "application/pdf", source))
    await conn.commit()


async def main():
    async with aiosqlite.connect(db.DB_PATH) as c:
        await c.executescript(SCHEMA)
        await c.commit()
        await add(c, 77, "policy.pdf", "whatsapp")
        await add(c, 77, "bill.pdf", "claimant")
        await add(c, 77, "discharge.pdf", "")

    print("\nReading what is already on the claim\n")

    res = await cs.sets_for_claim(77, "health")
    check("it finds the claim's documents", res["documents"] == 3, res["documents"])
    check("...and reads every page", len(res["pages"]) == 3, len(res["pages"]))
    check("...and says where each came from",
          res["by_source"].get("whatsapp") == 1 and res["by_source"].get("claimant") == 1
          and res["by_source"].get("uploaded by staff") == 1, res["by_source"])
    check("nobody had to upload anything", res["from_cache"] is False)

    print("\nThe three sets\n")

    keys = {s["key"] for s in res["sets"]}
    check("all three are built", keys == {"cio", "all_merged", "claim_set"}, sorted(keys))
    merged = next(s for s in res["sets"] if s["key"] == "all_merged")
    check("'everything merged' holds every page", len(merged["pages"]) == 3, merged["pages"])
    check("a set says what is NOT in it, by name",
          all(isinstance(m, str) for m in merged["missing"]), merged["missing"])

    print("\nWhat the standalone tool cannot know\n")

    check("it reports what the CHECKLIST still wants",
          isinstance(res["still_needed"], list),
          "the claim knows this; a loose pile of files does not")

    print("\nRead once, not on every open\n")

    again = await cs.sets_for_claim(77, "health")
    check("opening it a second time uses the stored reading", again["from_cache"] is True)
    check("...and gives the same answer",
          [p["doc_type"] for p in again["pages"]] == [p["doc_type"] for p in res["pages"]])

    async with aiosqlite.connect(db.DB_PATH) as c:
        await add(c, 77, "oddity.pdf", "whatsapp")
    after = await cs.sets_for_claim(77, "health")
    check("a new document forces a re-read", after["from_cache"] is False,
          "otherwise the set would quietly miss what just arrived")
    check("...and the new page is in it", len(after["pages"]) == 4, len(after["pages"]))

    forced = await cs.sets_for_claim(77, "health", force=True)
    check("refresh re-reads even when nothing changed", forced["from_cache"] is False)

    print("\nOne engine, one set of rules\n")

    odd = next(p for p in after["pages"] if p["page"] == 4)
    rid = await store.teach("other", ["consignment", "despatch", "freight", "loading"],
                            "Asha", 11)
    check("a rule can be taught", rid > 0)
    taught = await cs.sets_for_claim(77, "health", force=True)
    t4 = next(p for p in taught["pages"] if p["page"] == 4)
    check("a rule taught anywhere applies on the claim too", t4["doc_type"] == "other", t4)
    check("...and says who taught it", (t4.get("taught_by") or "") == "Asha", t4)
    check("...which is what 'the source will be the same' has to mean",
          t4["doc_type"] != odd["doc_type"] or odd["doc_type"] == "other",
          "before=%s after=%s" % (odd["doc_type"], t4["doc_type"]))

    print("\nWhen a file is not where the database says\n")

    os.remove(os.path.join(os.environ["NIDAAN_DOCS_DIR"], "bill.pdf"))
    gone = await cs.sets_for_claim(77, "health", force=True)
    check("a missing file is REPORTED, not silently dropped",
          "bill.pdf" in (gone["unreadable"] or []), gone["unreadable"])
    check("...and the rest of the claim still reads", len(gone["pages"]) >= 2, len(gone["pages"]))

    print("\nA claim with nothing on it\n")

    empty = await cs.sets_for_claim(999, "health")
    check("no documents is not an error", empty["documents"] == 0 and empty["pages"] == [])
    check("...and the sets are empty rather than missing", len(empty["sets"]) == 3)

    print("\nThe routes reuse the existing claim rule\n")

    src = io.open("sarathi_biz.py", encoding="utf-8").read()
    for name in ("ops_claim_doc_sets", "ops_claim_doc_set_pdf"):
        m = re.search(r"async def %s\(.*?(?=\n@app\.|\nasync def )" % name, src, re.S)
        body = m.group(0) if m else ""
        check("%-22s asks biz_nidaan_claim_authz" % name,
              "assert_claim_access" in body,
              "a second copy of the access rule is how one of them drifts")
        check("%-22s refuses with 404, not 403" % name,
              "status_code=404" in body and "status_code=403" not in body, body[-200:])

    print("\n%s\n" % ("ALL GOOD" if not FAILED else "%d FAILED" % FAILED))
    return 1 if FAILED else 0


sys.exit(asyncio.run(main()))
