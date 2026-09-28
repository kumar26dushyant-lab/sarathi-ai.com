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

    # The documents are already on disk; merge them the same way an upload is merged, so one
    # page number means the same thing here as it does in the standalone tool.
    docs_dir = os.getenv("NIDAAN_DOCS_DIR", "uploads/nidaan-docs")
    files = []
    for d in docs:
        p = os.path.join(docs_dir, d.get("stored_name") or "")
        try:
            with open(p, "rb") as f:
                files.append((d.get("original_name") or "document", f.read()))
        except Exception as e:  # noqa: BLE001
            # A missing file is reported, never silently dropped: "the bill is not in the set"
            # and "the bill is not on the server" are different problems.
            logger.info("claim %s: could not read %s (%s)", claim_id, d.get("stored_name"), e)
            d["unreadable"] = True

    if not files:
        return {"pages": [], "docs": docs, "truncated": False, "from_cache": False}

    try:
        merged, pages_n, _skipped = split.normalize_to_pdf(files)
    except Exception as e:  # noqa: BLE001
        logger.warning("claim %s: could not merge its documents: %s", claim_id, e)
        return {"pages": [], "docs": docs, "truncated": False, "from_cache": False}
    if not merged:
        return {"pages": [], "docs": docs, "truncated": False, "from_cache": False}

    import biz_nidaan_doc_brain as brain
    import biz_nidaan_doc_store as store
    try:
        pages = await brain.classify_pages(merged, await store.load_rules())
    except Exception as e:  # noqa: BLE001
        logger.warning("claim %s: could not read the pages: %s", claim_id, e)
        pages = []

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
                   "locked": bool(p.get("locked")), "taught_by": p.get("taught_by") or ""}
                  for p in pages],
        "sets": out_sets,
        "still_needed": still_needed,
        "truncated": read.get("truncated", False),
        "from_cache": read.get("from_cache", False),
    }
