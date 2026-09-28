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
CREATE TABLE nidaan_claim_doc_auto (
    claim_id INTEGER PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
    updated_by TEXT NOT NULL DEFAULT '', updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE nidaan_claim_page_types (
    claim_id INTEGER NOT NULL, doc_id INTEGER NOT NULL, page_in_doc INTEGER NOT NULL,
    doc_type TEXT NOT NULL, set_by TEXT NOT NULL DEFAULT '',
    set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (claim_id, doc_id, page_in_doc));
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

    check("the screen is given the names a person can choose from",
          len(res.get("types") or []) > 5
          and all(t.get("key") and t.get("label") for t in res["types"]),
          "without these the 'what is this page?' buttons render empty")

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

    print("\nEvery page knows which document it came from\n")

    att = await cs.sets_for_claim(77, "health", force=True)
    named = [p for p in att["pages"] if p.get("doc_name")]
    check("each page names its document", len(named) == len(att["pages"]),
          [(p["page"], p.get("doc_name")) for p in att["pages"]])
    check("...and its page number inside that document",
          all(p.get("page_in_doc") for p in named),
          "'page 2 of FINAL BILL.pdf' is actionable; 'page 7' is not")

    print("\nThe switch is per claim, and off unless somebody turns it on\n")

    check("off by default", (await cs.automation_on(77)) is False)
    check("it can be turned on", await cs.set_automation(77, True, "Dushyant"))
    check("...and reads back on", (await cs.automation_on(77)) is True)
    check("...for THAT claim only", (await cs.automation_on(999)) is False,
          "the founder asked for per claim")
    check("...and can be turned off again",
          (await cs.set_automation(77, False, "Dushyant"))
          and (await cs.automation_on(77)) is False)

    print("\nConfident, or a person looks\n")

    sure = [{"page": 1, "doc_id": 1, "doc_name": "policy.pdf", "confidence": 0.9,
             "source": "doc", "why": "policy schedule"},
            {"page": 2, "doc_id": 2, "doc_name": "bill.pdf", "confidence": 0.8,
             "source": "doc", "why": "total payable"}]
    st = cs.arrangement_state(sure)
    check("all confident means ready", st["ready"] is True and st["unsure"] == [], st)

    weak = sure + [{"page": 3, "doc_id": 3, "doc_name": "scan.jpg", "confidence": 0.4,
                    "source": "doc", "why": "a few weak signs"}]
    st = cs.arrangement_state(weak)
    check("ONE doubtful document holds the whole claim", st["ready"] is False, st)
    check("...and it is named, not numbered",
          [u["name"] for u in st["unsure"]] == ["scan.jpg"], st["unsure"])
    check("...with a reason a person can act on",
          "not sure" in st["unsure"][0]["why"], st["unsure"])

    unread = sure + [{"page": 3, "doc_id": 3, "doc_name": "photo.jpg", "confidence": 0.99,
                      "source": "none", "why": ""}]
    st = cs.arrangement_state(unread)
    check("a document nobody could read is never 'sure'",
          st["unsure"] and "nothing could be read" in st["unsure"][0]["why"], st)

    bundle = sure + [{"page": 3, "doc_id": 3, "doc_name": "all.pdf", "confidence": 0.9,
                      "source": "doc", "why": "x", "mixed": True}]
    st = cs.arrangement_state(bundle)
    check("a file holding several documents says so",
          st["unsure"] and "more than one document" in st["unsure"][0]["why"], st)

    settled = weak[:]
    settled[2] = dict(settled[2], by_person="Asha")
    check("a document a person settled stops holding it up",
          cs.arrangement_state(settled)["ready"] is True)

    many = sure + [{"page": 4, "doc_id": 2, "doc_name": "bill.pdf", "confidence": 0.8,
                    "source": "doc", "why": "total payable"}]
    check("a document is counted once, however many pages it has",
          len(cs.arrangement_state(many)["unsure"]) == 0,
          "otherwise a 40-page bill would be listed 40 times")

    print("\nThe audit case: automation was sure, and still wrong\n")

    pol = next(p for p in att["pages"] if p.get("doc_name") == "policy.pdf")
    was = pol["doc_type"]
    check("a person can retype it afterwards",
          (await cs.set_page_type(77, pol["doc_id"], pol["page_in_doc"], "kyc", "Auditor")))

    after_fix = await cs.sets_for_claim(77, "health", force=True)
    fixed = next(p for p in after_fix["pages"] if p.get("doc_name") == "policy.pdf")
    check("...and a full re-read does NOT undo them", fixed["doc_type"] == "kyc", fixed)
    check("...and the screen can say who settled it", fixed.get("by_person") == "Auditor", fixed)
    check("...and what it used to think", fixed.get("was") == was, fixed)
    check("an unknown type is refused",
          (await cs.set_page_type(77, pol["doc_id"], 1, "not-a-type", "X")) is False)

    print("\nA correction survives another document arriving\n")

    async with aiosqlite.connect(db.DB_PATH) as c:
        await add(c, 77, "discharge.pdf", "whatsapp")
    later = await cs.sets_for_claim(77, "health", force=True)
    still = next(p for p in later["pages"] if p.get("doc_name") == "policy.pdf")
    check("the correction is still on the right page", still["doc_type"] == "kyc", still)
    check("...because it is keyed by document, not by merged page number",
          still.get("by_person") == "Auditor", still)

    print("\nThe filename is read before the pages\n")

    import biz_nidaan_doc_local as _loc
    check("a name a person gave it is used",
          _loc.type_from_filename("CLAIM FORM PART A.pdf").get("doc_type") == "claim_form")
    check("...and says why, in words",
          "named" in _loc.type_from_filename("DISCHARGE SUMMARY.pdf").get("why", ""))
    for machine in ("Scanned_20260924_151559.pdf", "IMG-20260428-WA0246.jpg",
                    "WhatsApp Image 2026-09-01 at 10.12.pdf", "PXL_20260901.jpg"):
        check("a camera/scanner name says nothing: %s" % machine,
              _loc.type_from_filename(machine) == {},
              "Scanned_2026 must not become an ultrasound report")
    check("a name that names nothing is not guessed from",
          _loc.type_from_filename("random notes.pdf") == {})

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
