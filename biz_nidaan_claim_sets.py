# -*- coding: utf-8 -*-
"""The three sets, built from the documents already on a claim.

Founder, 28-29 Sep:
  *"end to end doc collection and split and create three folders like cio, all doc, and the third
  bucket/folder all can be done at claim level itself"* - and, on whether it replaces the
  standalone tool: *"the claim level splitter wont replace standalone splitter, both will exist
  and upgrade simultaneously as source will be the same, the only difference claim level splitter
  will have more options as it's a claim level and can provide more feedback and interact with
  our staff well for claim requirements."*

SO THE ENGINE IS SHARED, DELIBERATELY. This module reads pages with `biz_nidaan_doc_brain` and
composes with `biz_nidaan_doc_sets`, exactly as `biz_doc_splitter` does. A rule somebody teaches
in the standalone tool applies here, and the reverse. There is one reader and one set of rules;
if they ever diverge, staff will be told two different things about the same page.

WHAT THE CLAIM LEVEL KNOWS THAT THE TOOL DOES NOT:
  * which documents this claim still needs (the checklist), so a set can say what is MISSING by
    the name staff use for it, rather than just what is present;
  * where each page came from - WhatsApp, the claimant's own page, or a staff upload - so "the
    discharge summary never arrived" can be answered without opening anything;
  * that nobody has to upload anything. The documents are already here.

READ ONCE, CACHED ON THE CLAIM. Reading a scanned page costs about fifteen seconds. The answer is
stored against the claim with a fingerprint of which documents it covered, so it is reused until
the set of documents actually changes - then it is read again. Without that, opening a claim
twice would cost twice.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.claim.sets")

# Where the cached reading lives, beside the splitter's own working files.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_ROOT = os.getenv("NIDAAN_CLAIMSETS_CACHE") or os.path.join(_BASE_DIR, "var", "claimsets")

# The same cap the splitter uses. A claim with more pages than this is not refused - it is read
# up to the cap and says so, because half an answer on a huge file beats a spinner.
MAX_PAGES = 120


def _db() -> str:
    return db.DB_PATH


async def claim_documents(claim_id: int) -> list:
    """Every stored document on this claim, oldest first, with where it came from."""
    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            rows = await (await c.execute(
                "SELECT doc_id, stored_name, original_name, mime_type, source, uploaded_at "
                "FROM nidaan_claim_documents WHERE claim_id=? AND COALESCE(stored_name,'')<>'' "
                "ORDER BY uploaded_at", (int(claim_id),))).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:  # noqa: BLE001
        logger.warning("could not list documents for claim %s: %s", claim_id, e)
        return []


def _fingerprint(docs: list) -> str:
    """What the cached reading covered. Changes the moment a document is added or removed."""
    h = hashlib.sha256()
    for d in docs:
        h.update(str(d.get("doc_id") or "").encode())
        h.update(b"|")
    return h.hexdigest()[:16]


def _cache_path(claim_id: int) -> str:
    return os.path.join(CACHE_ROOT, "claim_%d.json" % int(claim_id))


def load_cached(claim_id: int, fingerprint: str) -> list:
    """The stored reading, but only if it covered exactly these documents."""
    try:
        with open(_cache_path(claim_id), encoding="utf-8") as f:
            v = json.load(f)
        if isinstance(v, dict) and v.get("fingerprint") == fingerprint:
            pages = v.get("pages")
            return pages if isinstance(pages, list) else []
    except Exception:  # noqa: BLE001
        pass
    return []


def save_cached(claim_id: int, fingerprint: str, pages: list) -> None:
    try:
        os.makedirs(CACHE_ROOT, exist_ok=True)
        tmp = _cache_path(claim_id) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fingerprint, "pages": pages}, f, ensure_ascii=False)
        os.replace(tmp, _cache_path(claim_id))
    except Exception as e:  # noqa: BLE001
        logger.info("could not cache the reading for claim %s: %s", claim_id, e)


async def read_claim(claim_id: int, *, force: bool = False) -> dict:
    """Read every document on the claim and return {pages, docs, truncated, from_cache}.

    `force` re-reads even when the cache matches - for the button a staff member presses after
    teaching a rule, so they can see it take effect without waiting for a new document.
    """
    import biz_doc_splitter as split

    docs = await claim_documents(claim_id)
    if not docs:
        return {"pages": [], "docs": [], "truncated": False, "from_cache": False}

    fp = _fingerprint(docs)
    if not force:
        cached = load_cached(claim_id, fp)
        if cached:
            return {"pages": cached, "docs": docs, "truncated": False, "from_cache": True}

    # The files, and the document rows behind them in the same order.
    docs_dir = os.getenv("NIDAAN_DOCS_DIR", "uploads/nidaan-docs")
    files, readable = [], []
    for d in docs:
        path = os.path.join(docs_dir, d.get("stored_name") or "")
        try:
            with open(path, "rb") as f:
                files.append((d.get("original_name") or "document", f.read()))
            readable.append(d)
        except Exception as e:  # noqa: BLE001
            # Reported, never silently dropped: "the bill is not in the set" and "the bill is
            # not on the server" are different problems, and only one is the staffer's to fix.
            logger.info("claim %s: could not read %s (%s)", claim_id, d.get("stored_name"), e)
            d["unreadable"] = True

    if not files:
        return {"pages": [], "docs": docs, "truncated": False, "from_cache": False}

    # EACH DOCUMENT IS IDENTIFIED ON ITS OWN, from its first readable pages, and every page of
    # it takes that answer. Reading all 134 pages of a claim cost two minutes, hit the OCR
    # budget, and produced WORSE answers - page 6 of a bill has no heading, so it read as
    # "Other" and dragged the whole claim into "please arrange". Measured on claims 204, 39 and
    # 151 before this changed.
    import biz_nidaan_doc_brain as brain
    import biz_nidaan_doc_store as store
    rules = await store.load_rules()

    pages = []
    page_no = 0
    for d, (name, blob) in zip(readable, files):
        try:
            one, n_pages, _sk = split.normalize_to_pdf([(name, blob)])
        except Exception as e:  # noqa: BLE001
            logger.info("claim %s: could not open %s: %s", claim_id, name, e)
            d["unreadable"] = True
            continue
        if not one or not n_pages:
            d["unreadable"] = True
            continue
        try:
            got = await brain.identify_document(one, rules)
        except Exception as e:  # noqa: BLE001
            logger.warning("claim %s: could not identify %s: %s", claim_id, name, e)
            got = {"doc_type": "other", "confidence": 0.0, "why": "could not be read",
                   "mixed": False, "words": []}
        d["doc_type"] = got["doc_type"]
        d["confidence"] = got["confidence"]
        d["why"] = got.get("why") or ""
        d["mixed"] = bool(got.get("mixed"))
        d["kinds"] = got.get("kinds") or []
        d["taught_by"] = got.get("taught_by") or ""
        for i in range(n_pages):
            page_no += 1
            pages.append({
                "page": page_no,
                "doc_type": got["doc_type"],
                "confidence": got["confidence"],
                "why": got.get("why") or "",
                "source": "doc",
                "words": got.get("words") or [],
                "taught_by": got.get("taught_by") or "",
                "doc_id": d.get("doc_id"),
                "doc_name": d.get("original_name") or name,
                "page_in_doc": i + 1,
                "mixed": bool(got.get("mixed")),
            })

    pages_n = page_no
    if not pages:
        return {"pages": [], "docs": docs, "truncated": False, "from_cache": False}

    truncated = bool(pages_n and pages_n > MAX_PAGES)
    save_cached(claim_id, fp, pages)
    return {"pages": pages, "docs": docs, "truncated": truncated, "from_cache": False,
            "merged_pages": pages_n}


async def sets_for_claim(claim_id: int, claim_type: str = "", *, force: bool = False) -> dict:
    """The three sets for this claim, and what the claim still needs.

    The MISSING list is the claim-level difference. The standalone tool can only say "no page in
    this file looked like a policy copy"; here we can also say "and the checklist is still
    waiting for it", which is the sentence a staff member actually acts on.
    """
    import biz_nidaan_doc_sets as sets

    read = await read_claim(claim_id, force=force)
    pages = read["pages"]

    # WHAT A PERSON SET WINS, always, and after the fact. Applied here rather than baked into the
    # cache so a correction takes effect immediately and survives every later reading.
    typed = await page_types(claim_id)
    for pg in pages:
        key = (pg.get("doc_id"), pg.get("page_in_doc"))
        if key in typed:
            pg["was"] = pg.get("doc_type")
            pg["doc_type"] = typed[key]["doc_type"]
            pg["confidence"] = 1.0
            pg["by_person"] = typed[key]["set_by"] or "a colleague"

    out_sets = []
    for st in sets.compose_all(pages):
        out_sets.append({
            "key": st["key"], "label": st["label"], "why": st.get("why") or "",
            "pages": [p.get("page") for p in st.get("pages") or []],
            "missing": [sets.type_label(m) for m in st.get("missing") or []],
        })

    # What the claim itself is still waiting for, in the words staff use on the checklist.
    still_needed = []
    try:
        import biz_nidaan_doc_checklist as ck
        still_needed = [{"key": d["key"], "label": d.get("en") or d["key"]}
                        for d in await ck.pending_required_docs(claim_id, claim_type)]
    except Exception as e:  # noqa: BLE001
        logger.info("claim %s: could not read the checklist: %s", claim_id, e)

    by_source: dict = {}
    for d in read["docs"]:
        s = (d.get("source") or "").strip() or "uploaded by staff"
        by_source[s] = by_source.get(s, 0) + 1

    return {
        "claim_id": int(claim_id),
        "documents": len(read["docs"]),
        "unreadable": [d.get("original_name") for d in read["docs"] if d.get("unreadable")],
        "by_source": by_source,
        "pages": [{"page": p.get("page"), "doc_type": p.get("doc_type") or "other",
                   "label": sets.type_label(p.get("doc_type") or "other"),
                   "confidence": round(float(p.get("confidence") or 0), 2),
                   "why": p.get("why") or "", "source": p.get("source") or "",
                   "locked": bool(p.get("locked")), "taught_by": p.get("taught_by") or "",
                   "doc_id": p.get("doc_id"), "doc_name": p.get("doc_name") or "",
                   "page_in_doc": p.get("page_in_doc"),
                   "by_person": p.get("by_person") or "", "was": p.get("was") or ""}
                  for p in pages],
        "sets": out_sets,
        "still_needed": still_needed,
        "truncated": read.get("truncated", False),
        "from_cache": read.get("from_cache", False),
        # The names a person can choose from. Without these the "what is this page?" buttons
        # render empty - the screen reads this list rather than keeping its own copy, so adding
        # a document type never means editing the page too.
        "types": [{"key": k, "label": sets.type_label(k)} for k in sets.DOC_TYPES],
        "automation": await automation_on(claim_id),
        "arrangement": arrangement_state(pages),
    }

# ── the switch, the corrections, and the arranging ───────────────────────────
# Confidence at or above this is "we are sure". Below it, a person looks. Deliberately high: the
# cost of a wrong automatic arrangement is a set sent to an authority with the wrong papers in
# it; the cost of asking is a minute of somebody's time.
SURE = 0.75


async def automation_on(claim_id: int) -> bool:
    """Is automatic arranging on for THIS claim? Off unless somebody said otherwise."""
    try:
        async with aiosqlite.connect(_db()) as c:
            row = await (await c.execute(
                "SELECT enabled FROM nidaan_claim_doc_auto WHERE claim_id=?",
                (int(claim_id),))).fetchone()
        return bool(row and row[0])
    except Exception as e:  # noqa: BLE001
        # Unreadable means OFF. Arranging somebody's medical documents automatically because a
        # table would not answer is the wrong way to fail.
        logger.info("claim %s: could not read the arrange switch (%s) - treating as off",
                    claim_id, e)
        return False


async def set_automation(claim_id: int, enabled: bool, by: str) -> bool:
    """Turn automatic arranging on or off for this claim, and say who did."""
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.execute(
                "INSERT INTO nidaan_claim_doc_auto (claim_id, enabled, updated_by, updated_at) "
                "VALUES (?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(claim_id) DO UPDATE SET "
                "enabled=excluded.enabled, updated_by=excluded.updated_by, "
                "updated_at=CURRENT_TIMESTAMP",
                (int(claim_id), 1 if enabled else 0, (by or "")[:80]))
            await c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("claim %s: could not set the arrange switch: %s", claim_id, e)
        return False


async def set_page_type(claim_id: int, doc_id: int, page_in_doc: int,
                        doc_type: str, by: str) -> bool:
    """What a PERSON says this page is. Survives every later reading.

    Available whether automation is on or off - that is the founder's audit case: automation was
    confident, it was still wrong, and somebody corrects it afterwards.
    """
    import biz_nidaan_doc_sets as sets
    if doc_type not in sets.DOC_TYPES:
        return False
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.execute(
                "INSERT INTO nidaan_claim_page_types "
                "(claim_id, doc_id, page_in_doc, doc_type, set_by, set_at) "
                "VALUES (?,?,?,?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(claim_id, doc_id, page_in_doc) DO UPDATE SET "
                "doc_type=excluded.doc_type, set_by=excluded.set_by, set_at=CURRENT_TIMESTAMP",
                (int(claim_id), int(doc_id), int(page_in_doc), doc_type, (by or "")[:80]))
            await c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("claim %s: could not store a page type: %s", claim_id, e)
        return False


async def page_types(claim_id: int) -> dict:
    """{(doc_id, page_in_doc): {"doc_type", "set_by"}} - everything a person has typed here."""
    try:
        async with aiosqlite.connect(_db()) as c:
            c.row_factory = aiosqlite.Row
            rows = await (await c.execute(
                "SELECT doc_id, page_in_doc, doc_type, set_by FROM nidaan_claim_page_types "
                "WHERE claim_id=?", (int(claim_id),))).fetchall()
        return {(int(r["doc_id"]), int(r["page_in_doc"])):
                {"doc_type": r["doc_type"], "set_by": r["set_by"]} for r in rows}
    except Exception as e:  # noqa: BLE001
        logger.info("claim %s: could not read stored page types: %s", claim_id, e)
        return {}


def arrangement_state(pages: list) -> dict:
    """What still needs a person? Returns {ready, unsure:[...], unsure_pages:[...]}.

    BY DOCUMENT, with names. The first version listed page numbers, and on a real claim that
    read "please arrange pages 1,2,3 ... 106" - a wall of numbers nobody can act on. Staff talk
    about "the bill" and "the discharge summary", never about page 47.

    A document is unsure when nothing could be read on it, when the reading was weak, or when it
    holds several documents at once - and each of those says so in words.
    """
    by_doc = {}
    for p in pages or []:
        key = p.get("doc_id")
        if key in by_doc:
            continue                       # every page of a document carries the same answer
        by_doc[key] = p

    unsure = []
    for p in by_doc.values():
        if p.get("by_person"):
            continue                       # a person settled this one
        name = p.get("doc_name") or "a document"
        if p.get("mixed"):
            unsure.append({"doc_id": p.get("doc_id"), "name": name,
                           "why": "this file holds more than one document"})
        elif p.get("source") == "none" or not p.get("why"):
            unsure.append({"doc_id": p.get("doc_id"), "name": name,
                           "why": "nothing could be read on it"})
        elif float(p.get("confidence") or 0) < SURE:
            unsure.append({"doc_id": p.get("doc_id"), "name": name,
                           "why": "not sure what it is"})

    return {"ready": not unsure, "unsure": unsure,
            "unsure_pages": [q.get("page") for q in (pages or [])
                             if q.get("doc_id") in {u["doc_id"] for u in unsure}]}


async def remark(claim_id: int, summary: str, actor: str = "Document arranging") -> None:
    """Write to the claim's own remarks timeline - the same one staff already read.

    The founder asked that this fit the existing claim conversation "without conflict or
    discrepancies". That means ONE timeline: an automatic arrangement appears next to "Renamed a
    document" and "moved to Escalation", not in a private log nobody opens.
    """
    try:
        import biz_nidaan_buckets as bk
        await bk._log(int(claim_id), summary, actor)
    except Exception as e:  # noqa: BLE001
        logger.info("claim %s: could not write a remark: %s", claim_id, e)
