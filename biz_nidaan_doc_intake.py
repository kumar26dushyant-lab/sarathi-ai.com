"""
NidaanPartner — WHAT A COMPLAINANT ACTUALLY SENDS.

People do not send one tidy document per checklist line. They send a ZIP from the hospital, a
40-page PDF with everything in it, eight photos of a bill, or a mix of all three. Until now every
inbound file was judged as ONE document against ONE expected line: a fat PDF containing all nine
documents was classified as "not the discharge summary" and the sender was told it was wrong. If
nothing was outstanding the file was thanked for and then DISCARDED without being stored at all.

The tool to fix this already existed in the building, in the wrong room: the doc splitter, sitting
in the ops feature list where nobody opens it. It knows how to find where one document ends and
the next begins. Moved in here, it turns one upload into nine ticked lines.

The rules this module is built on (founder, 19 Sep):
  • ACCEPT ANYTHING. A format we cannot read is our problem, never "you did it wrong".
  • NOTHING IS EVER DISCARDED. Every piece is stored on the claim even when we cannot name it -
    a document we failed to classify is still the complainant's evidence.
  • WHEN WE ARE UNSURE, A PERSON DECIDES - NOT THE COMPLAINANT. Low confidence goes to a staff
    queue with our best guess. They are never asked to fix our uncertainty.
  • ONE REPLY PER BATCH, never one per file.
"""
from __future__ import annotations

import io
import json
import logging
import os
import uuid
import zipfile
from pathlib import Path
from typing import Optional

import biz_database as db
import biz_doc_splitter as _split

logger = logging.getLogger("nidaan.doc.intake")

DOCS_DIR = Path(os.getenv("NIDAAN_DOCS_DIR", "uploads/nidaan-docs"))

# Below this we do not tell the complainant anything about the piece - a person looks first.
# Deliberately high: the cost of a wrong "this is your discharge summary" is a mis-filed case,
# and the cost of a staff glance is ten seconds.
CONFIDENT = 0.75

# A ZIP arrives as one file and can hold the whole case. One level deep only: a zip inside a zip
# is rare enough, and unbounded recursion on an untrusted archive is how you get a zip bomb.
MAX_MEMBERS = 40
MAX_MEMBER_BYTES = 25 * 1024 * 1024

_DOCLIKE = (".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff",
            ".doc", ".docx")


def unpack(files: list) -> tuple[list, list]:
    """[(name, bytes)] → ([(name, bytes)] flattened, [notes]). Never raises.

    A ZIP is expanded; anything else passes through untouched. Members that are not document-like
    (a stray .DS_Store, a video) are dropped with a note rather than failing the whole batch.
    """
    out, notes = [], []
    for name, data in files or []:
        low = (name or "").lower()
        if not low.endswith(".zip"):
            out.append((name, data))
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                members = [m for m in z.infolist() if not m.is_dir()][:MAX_MEMBERS]
                took = 0
                for m in members:
                    mlow = m.filename.lower()
                    if not mlow.endswith(_DOCLIKE):
                        continue
                    if m.file_size > MAX_MEMBER_BYTES:
                        notes.append("%s was too large to open" % os.path.basename(m.filename))
                        continue
                    out.append((os.path.basename(m.filename), z.read(m)))
                    took += 1
            notes.append("opened the zip (%d file%s inside)" % (took, "" if took == 1 else "s"))
        except Exception as e:  # noqa: BLE001
            logger.info("could not open zip %s: %s", name, e)
            notes.append("could not open that zip, so it was kept whole")
            out.append((name, data))
    return out, notes


async def match_document(pdf_bytes: bytes, candidates: list) -> dict:
    """Which of the documents this claim still needs is this? Best-effort, fails OPEN as unknown.

    Deliberately different from the old classify_document, which could only answer yes/no about
    ONE expected document. Asking "which of these is it" is what lets a single upload satisfy
    several lines at once, and it is also kinder: an unexpected-but-useful document is recognised
    instead of rejected.
    """
    unknown = {"key": "", "label": "", "confidence": 0.0, "looks_like": "", "legible": True,
               "reason": ""}
    if not candidates:
        return unknown
    try:
        import biz_ai
        client = biz_ai._get_client()
        if not client:
            return unknown
        from google.genai import types as gt
        listing = "\n".join("  - %s: %s" % (c["key"], c.get("en") or c["key"])
                            for c in candidates)
        prompt = (
            "An insurance claim needs these documents:\n%s\n\n"
            "Look at the attached document and answer STRICTLY as JSON:\n"
            '{"key": "<the key above it matches, or \\"\\" if it matches none>", '
            '"confidence": <0.0-1.0>, '
            '"looks_like": "<what it actually is, short>", '
            '"legible": <true if clear and complete enough to read and use, false if blurry, '
            'cropped, dark or partial>, '
            '"reason": "<one short reason>"}' % listing)
        resp = await client.aio.models.generate_content(
            model=os.getenv("DOCSPLIT_MODEL", "gemini-2.5-flash"),
            contents=[gt.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt],
            config=gt.GenerateContentConfig(response_mime_type="application/json"))
        v = json.loads(resp.text) or {}
        key = str(v.get("key") or "").strip()
        if key and key not in {c["key"] for c in candidates}:
            key = ""
        label = next((c.get("en") or c["key"] for c in candidates if c["key"] == key), "")
        try:
            conf = float(v.get("confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        return {"key": key, "label": label, "confidence": max(0.0, min(1.0, conf)),
                "looks_like": str(v.get("looks_like") or "")[:60],
                "legible": bool(v.get("legible", True)),
                "reason": str(v.get("reason") or "")[:120]}
    except Exception as e:  # noqa: BLE001
        logger.info("match_document failed (treating as unknown): %s", e)
        return unknown


async def _store(account_id, claim_id: int, filename: str, pdf_bytes: bytes,
                 source: str) -> Optional[int]:
    """Put the bytes on the claim. Returns doc_id, or None if it could not be stored."""
    try:
        import biz_nidaan as _n
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        stored = "%s.pdf" % uuid.uuid4().hex
        (DOCS_DIR / stored).write_bytes(pdf_bytes)
        return await _n.save_claim_document(
            account_id=account_id, stored_name=stored, original_name=filename[:120],
            file_size=len(pdf_bytes), mime_type="application/pdf", claim_id=claim_id,
            source=source)
    except Exception as e:  # noqa: BLE001
        logger.warning("could not store a document for claim %s: %s", claim_id, e)
        return None


async def accept(claim_id: int, account_id, files: list, *, claim_type: str = "",
                 source: str = "whatsapp") -> dict:
    """Take whatever arrived and do as much of the work as can be done without a person.

    Returns everything a caller needs to write ONE reply and to show staff what happened:
      {ok, stored, ticked:[{key,label}], unclear:[{label,reason}], unsorted:[{looks_like}],
       pending:[...], total, notes:[...]}
    """
    import biz_nidaan_doc_checklist as _ck

    out = {"ok": False, "stored": 0, "ticked": [], "unclear": [], "unsorted": [],
           "pending": [], "total": 0, "notes": []}
    files, notes = unpack(files)
    out["notes"] = notes
    if not files:
        out["error"] = "nothing_readable"
        return out

    # Everything becomes one PDF so the splitter can look across the whole batch at once - that is
    # what lets eight photos of one bill be recognised as a single document.
    try:
        merged, pages, skipped = _split.normalize_to_pdf(files)
    except Exception as e:  # noqa: BLE001
        logger.info("normalize failed for claim %s: %s", claim_id, e)
        merged, pages, skipped = None, 0, []
    if not merged:
        out["error"] = "unreadable"
        return out
    if skipped:
        out["notes"].append("%d file(s) could not be opened" % len(skipped))

    pending = await _ck.pending_required_docs(claim_id, claim_type)
    out["total"] = len(_ck.doc_template_for(claim_type) or [])

    # One page is one document; more than one gets split properly.
    pieces = [{"name": "Document 1", "start": 1, "end": pages}]
    if pages > 1:
        try:
            pieces = await _split.segment(merged, pages) or pieces
        except Exception as e:  # noqa: BLE001
            logger.info("segment failed for claim %s: %s", claim_id, e)
    try:
        cut = _split.extract(merged, pieces)
    except Exception as e:  # noqa: BLE001
        logger.info("extract failed for claim %s: %s", claim_id, e)
        cut = [("document.pdf", merged)]

    seen_keys = set()
    for filename, blob in cut:
        # Match against what is STILL outstanding, minus anything this same batch just satisfied,
        # so two copies of the discharge summary do not both claim the same line.
        candidates = [c for c in pending if c["key"] not in seen_keys]
        m = await match_document(blob, candidates)
        doc_id = await _store(account_id, claim_id, filename, blob, source)
        if doc_id:
            out["stored"] += 1

        if m["key"] and m["confidence"] >= CONFIDENT and m["legible"]:
            # The return value is CHECKED. Ignoring it is how a recognised document went on
            # showing as outstanding: the update matched no checklist row and said so, and
            # nobody listened. If it still cannot be ticked, the piece is stored and put in
            # front of a person rather than reported to the complainant as received.
            if await _ck.mark_doc_received(claim_id, m["key"], via=source, doc_id=doc_id):
                seen_keys.add(m["key"])
                out["ticked"].append({"key": m["key"], "label": m["label"]})
            else:
                logger.warning("claim %s: recognised %s but could not tick it", claim_id, m["key"])
                out["unsorted"].append({"doc_id": doc_id, "looks_like": m["label"],
                                        "confidence": m["confidence"]})
        elif m["key"] and m["confidence"] >= CONFIDENT and not m["legible"]:
            # We know what it is and cannot read it. This is the ONE thing worth asking them for,
            # because only they can take a better photograph.
            out["unclear"].append({"key": m["key"], "label": m["label"],
                                   "reason": m.get("reason") or "it is hard to read"})
        else:
            # We do not know what this is. It is stored and a person will look - the complainant
            # is not told anything, because our uncertainty is not their problem.
            out["unsorted"].append({"doc_id": doc_id, "looks_like": m.get("looks_like") or "",
                                    "confidence": m["confidence"]})

    out["pending"] = await _ck.pending_required_docs(claim_id, claim_type)
    out["ok"] = True
    await _record(claim_id, out, source)
    return out


async def _record(claim_id: int, res: dict, source: str) -> None:
    """One honest line on the claim timeline, so staff see what the machine did and did not do."""
    try:
        import biz_nidaan as _n
        bits = []
        if res["ticked"]:
            bits.append("ticked " + ", ".join(t["label"] or t["key"] for t in res["ticked"]))
        if res["unclear"]:
            bits.append("%d too unclear to use" % len(res["unclear"]))
        if res["unsorted"]:
            bits.append("%d could not be identified — needs a look" % len(res["unsorted"]))
        await _n.record_claim_activity(
            claim_id, "doc_batch", channel=source, direction="in", actor="complainant",
            summary="Received %d document(s): %s" % (res["stored"], "; ".join(bits) or "stored"),
            meta=json.dumps({"ticked": [t["key"] for t in res["ticked"]],
                             "unclear": [u["key"] for u in res["unclear"]],
                             "unsorted": len(res["unsorted"])}, ensure_ascii=False))
    except Exception as e:  # noqa: BLE001
        logger.debug("could not record the document batch for %s: %s", claim_id, e)


async def needs_a_look(limit: int = 50) -> list:
    """Documents the machine could not name, waiting for a person.

    This is the queue that keeps our uncertainty away from the complainant: everything in here was
    accepted, stored and never questioned out loud.
    """
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = await (await c.execute(
            "SELECT a.claim_id, a.created_at, a.meta, cl.complainant_name, cl.insured_name "
            "FROM nidaan_claim_activity a JOIN nidaan_claims cl ON cl.claim_id = a.claim_id "
            "WHERE a.kind='doc_batch' ORDER BY a.created_at DESC LIMIT ?", (int(limit),))).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            meta = json.loads(d.get("meta") or "{}")
        except Exception:  # noqa: BLE001
            meta = {}
        if int(meta.get("unsorted") or 0) > 0:
            out.append({"claim_id": d["claim_id"], "at": str(d.get("created_at") or ""),
                        "who": d.get("complainant_name") or d.get("insured_name") or "",
                        "unsorted": int(meta.get("unsorted") or 0)})
    return out
