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
import io
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


# Bump when the way a document is identified changes (new file names, new page signals), so
# every claim re-reads once instead of keeping the old answer until somebody presses the button.
READER_VERSION = 4


def _fingerprint(docs: list, rules: list = ()) -> str:
    """What the cached reading covered: these documents, read this way, under these rules.

    Changes the moment a document is added or removed, a rule is taught or undone, or the
    reader itself improves. Keyed on documents alone, a claim kept yesterday's answer after an
    admin taught a rule - exactly when staff expect it to have got better.
    """
    h = hashlib.sha256()
    h.update(b"v%d|" % READER_VERSION)
    for d in docs:
        h.update(str(d.get("doc_id") or "").encode())
        h.update(b"|")
    h.update(b"rules|")
    for rid in sorted(int(r.get("rule_id") or 0) for r in (rules or [])):
        h.update(str(rid).encode())
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

    import biz_nidaan_doc_store as store
    rules = await store.load_rules()
    fp = _fingerprint(docs, rules)
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

    # ONE READER for this screen and the standalone splitter (brain.read_files): each file
    # identified once - its name first, checked against its pages - and a file holding several
    # documents read page by page. A time budget for OCR across the whole claim: identifying per
    # document without one took 7m30s on claim 151; past it, names and text layers still count and
    # only photographed pages stop being rendered - those go to a person.
    budget = float(os.getenv("NIDAAN_CLAIM_OCR_BUDGET_S", "90"))
    got_pages, per_file = await brain.read_files(files, rules, budget_s=budget)
    for f in per_file:
        d = readable[f["index"]]
        if f.get("unreadable"):
            d["unreadable"] = True
            continue
        for k in ("doc_type", "confidence", "why", "mixed", "kinds", "taught_by"):
            d[k] = f.get(k)
    pages = []
    for pg in got_pages:
        d = readable[pg.pop("file_index")]
        pg["doc_id"] = d.get("doc_id")
        pg["doc_name"] = d.get("original_name") or pg.get("doc_name") or "document"
        pages.append(pg)
    page_no = len(pages)

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

    read, pages = await final_pages(claim_id, force=force)
    # Excluded pages are shown on the screen (so somebody can put them back) but never composed
    # into a set.
    sendable = [p for p in pages if not p.get("excluded")]

    out_sets = []
    for st in sets.compose_all(sendable):
        out_sets.append({
            "key": st["key"], "label": st["label"], "why": st.get("why") or "",
            "pages": [p.get("page") for p in st.get("pages") or []],
            "missing": [sets.type_label(m) for m in st.get("missing") or []],
            "parts": [{"type": t, "label": sets.type_label(t), "pages": len(g)}
                      for t, g in _by_type(st.get("pages") or [])],
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
                   "by_person": p.get("by_person") or "", "was": p.get("was") or "",
                   "excluded": bool(p.get("excluded")),
                   "excluded_by": p.get("excluded_by") or ""}
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
        # A page somebody deliberately held back is a decision already made - it must not keep
        # the claim in "please check".
        "arrangement": arrangement_state(sendable),
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


# ── one answer to "what is in this set", for the screen AND the download ─────
async def final_pages(claim_id: int, *, force: bool = False) -> tuple:
    """The reading, with everything a person decided laid over it. Returns (read, pages).

    The single place corrections and exclusions are applied. The screen and the PDF download
    both come through here - they used not to, and a corrected page showed correctly on screen
    and then downloaded in its old place.
    """
    read = await read_claim(claim_id, force=force)
    # Copies, so laying decisions over them never writes into the cached reading.
    pages = [dict(p) for p in read["pages"]]

    typed = await page_types(claim_id)
    held = await excluded_pages(claim_id)
    for pg in pages:
        key = (pg.get("doc_id"), pg.get("page_in_doc"))
        if key in typed:
            pg["was"] = pg.get("doc_type")
            pg["doc_type"] = typed[key]["doc_type"]
            pg["confidence"] = 1.0
            pg["by_person"] = typed[key]["set_by"] or "a colleague"
        if key in held:
            pg["excluded"] = True
            pg["excluded_by"] = held[key] or "a colleague"
    return read, pages


async def excluded_pages(claim_id: int) -> dict:
    """{(doc_id, page_in_doc): set_by} for every page currently held back from the sets."""
    try:
        async with aiosqlite.connect(_db()) as c:
            rows = await (await c.execute(
                "SELECT doc_id, page_in_doc, set_by FROM nidaan_claim_page_excluded "
                "WHERE claim_id=? AND excluded=1", (int(claim_id),))).fetchall()
        return {(int(r[0]), int(r[1])): r[2] for r in rows}
    except Exception as e:  # noqa: BLE001
        # Unreadable means nothing is held back - which errs towards SENDING a page. That is the
        # safer failure here: a missing page is noticed when the set is checked, while a page
        # silently dropped from a legal bundle may never be.
        logger.info("claim %s: could not read held-back pages: %s", claim_id, e)
        return {}


async def set_excluded(claim_id: int, doc_id: int, page_in_doc: int,
                       excluded: bool, by: str) -> bool:
    """Hold a page back from every set, or put it back. Never deletes the row."""
    try:
        async with aiosqlite.connect(_db()) as c:
            await c.execute(
                "INSERT INTO nidaan_claim_page_excluded "
                "(claim_id, doc_id, page_in_doc, excluded, set_by, set_at) "
                "VALUES (?,?,?,?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(claim_id, doc_id, page_in_doc) DO UPDATE SET "
                "excluded=excluded.excluded, set_by=excluded.set_by, set_at=CURRENT_TIMESTAMP",
                (int(claim_id), int(doc_id), int(page_in_doc), 1 if excluded else 0,
                 (by or "")[:80]))
            await c.commit()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("claim %s: could not change a held-back page: %s", claim_id, e)
        return False


async def build_set_pdf(claim_id: int, set_key: str) -> bytes:
    """One set as a PDF, built page by page from (document, page inside it).

    NOT by merged page number. The old download re-merged every file and trusted that its page
    47 was the reading's page 47 - true only until one file failed to open, after which every
    later page would have come from the wrong document.
    """
    import fitz
    import biz_doc_splitter as split
    import biz_nidaan_doc_sets as sets

    _read, pages = await final_pages(claim_id)
    sendable = [p for p in pages if not p.get("excluded")]
    composed = sets.compose(sendable, set_key)
    order = composed.get("pages") or []
    if not order:
        return b""
    return (await _render(claim_id, [order]))[0]


def _by_type(order: list) -> list:
    """[(doc_type, [pages...]), ...] in the set's own order. A set is composed BY TYPE, so all of
    one type's pages already sit together - this only draws the lines between them."""
    out = []
    for p in order:
        t = p.get("doc_type") or "other"
        if out and out[-1][0] == t:
            out[-1][1].append(p)
        else:
            out.append((t, [p]))
    return out


async def build_set_parts(claim_id: int, set_key: str) -> list:
    """The set as one PDF PER DOCUMENT: [(file name, pdf bytes), ...].

    Claim form (3 pages) one PDF, discharge summary (10 pages) one PDF, final bill one PDF - in
    the set's order, numbered so they sort that way in any folder. Built from exactly the pages
    the screen shows, like the single PDF.
    """
    import biz_nidaan_doc_sets as sets
    import biz_doc_splitter as split

    _read, pages = await final_pages(claim_id)
    sendable = [p for p in pages if not p.get("excluded")]
    order = sets.compose(sendable, set_key).get("pages") or []
    groups = _by_type(order)
    if not groups:
        return []
    blobs = await _render(claim_id, [g for _t, g in groups])
    out = []
    for i, ((t, _g), blob) in enumerate(zip(groups, blobs), 1):
        if blob:
            name = "%02d %s.pdf" % (i, split._safe_name(sets.type_label(t)).replace("_", " ")
                                     or t)
            out.append((name, blob))
    return out


async def build_set_zip(claim_id: int, set_key: str) -> bytes:
    """build_set_parts, as one zip to download."""
    import zipfile
    parts = await build_set_parts(claim_id, set_key)
    if not parts:
        return b""
    buf = io.BytesIO()
    # Stored, not compressed: PDFs are compressed already, and this keeps it quick.
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name, blob in parts:
            z.writestr(name, blob)
    return buf.getvalue()


async def _render(claim_id: int, groups: list) -> list:
    """One PDF per list of pages, each page copied from (document, page inside it).

    In a worker thread: turning a claim's photos into PDF pages takes seconds, and doing it on
    the event loop would freeze every other request on this worker meanwhile.
    """
    import asyncio
    docs = {d.get("doc_id"): d for d in await claim_documents(claim_id)}
    return await asyncio.to_thread(_render_sync, claim_id, docs, groups)


def _render_sync(claim_id: int, docs: dict, groups: list) -> list:
    import fitz
    import biz_doc_splitter as split

    docs_dir = os.getenv("NIDAAN_DOCS_DIR", "uploads/nidaan-docs")
    opened: dict = {}
    results = []
    try:
        for order in groups:
            out = fitz.open()
            try:
                for pg in order:
                    did = pg.get("doc_id")
                    n = int(pg.get("page_in_doc") or 0)
                    if did not in opened:
                        d = docs.get(did) or {}
                        try:
                            with open(os.path.join(docs_dir, d.get("stored_name") or ""),
                                      "rb") as f:
                                blob = f.read()
                            one, _n, _sk = split.normalize_to_pdf(
                                [(d.get("original_name") or "doc", blob)])
                            opened[did] = fitz.open(stream=one, filetype="pdf") if one else None
                        except Exception as e:  # noqa: BLE001
                            logger.info("claim %s: could not open doc %s for a set: %s",
                                        claim_id, did, e)
                            opened[did] = None
                    src = opened.get(did)
                    if src is None or n < 1 or n > src.page_count:
                        continue
                    out.insert_pdf(src, from_page=n - 1, to_page=n - 1)
                results.append(out.tobytes() if out.page_count else b"")
            finally:
                out.close()
        return results
    finally:
        for v in opened.values():
            try:
                if v is not None:
                    v.close()
            except Exception:  # noqa: BLE001
                pass
