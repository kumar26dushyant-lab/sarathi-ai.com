"""
NidaanPartner — Document Splitter (standalone ops tool).

Customers send a big mixed file (discharge summary + bills + lab reports + policy copy + …) as one or a
few PDFs/images. The team must send each document SEPARATELY to authorities. This tool:
  1) normalizes the uploads (PDF + JPEG/PNG/WebP/…) into ONE working PDF,
  2) uses Gemini (multimodal) to read it and detect each distinct document + its page range,
  3) lets a human review/adjust the split,
  4) exports one clean PDF per document (a zip).

Standalone (not tied to a claim); visible to all staff. DOC/DOCX needs LibreOffice (not installed yet).
"""
from __future__ import annotations

import os
import io
import time
import uuid
import re
import zipfile
import logging
import tempfile
from typing import Optional

import fitz  # PyMuPDF

logger = logging.getLogger("sarathi.docsplit")

# Job files must live where EVERY web worker can read them. The systemd units run with
# PrivateTmp=true (each worker gets its own /tmp) AND nginx load-balances across workers, so
# /tmp would let one worker save a job the next worker can't find ("Job expired"). Store under
# the app dir instead (shared; covered by ReadWritePaths=/opt/sarathi; not isolated by PrivateTmp).
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_ROOT = os.getenv("DOCSPLIT_TMP") or os.path.join(_BASE_DIR, "var", "docsplit")
MAX_PAGES = 80          # safety cap for a single job
IMAGE_EXTS = ("jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff")

def _safe_job(job: str) -> str:
    return re.sub(r"[^a-f0-9]", "", (job or "").lower())[:32]


def _safe_name(s: str) -> str:
    s = re.sub(r"[^\w\s\-ऀ-ॿ]", "", (s or "").strip())  # keep alnum, spaces, hyphen, Devanagari
    s = re.sub(r"\s+", "_", s).strip("_")
    return (s or "Document")[:60]


# ── Normalize any uploads → one working PDF ──────────────────────────────────
def normalize_to_pdf(files: list) -> tuple[bytes, int, list]:
    """files = [(filename, bytes), …]. Merge PDFs + images into ONE PDF (in upload order).
    Returns (pdf_bytes, page_count, skipped_filenames)."""
    out = fitz.open()
    skipped = []
    for fname, data in files:
        if not data:
            continue
        ext = fname.lower().rsplit(".", 1)[-1] if "." in fname else ""
        try:
            if ext == "pdf" or data[:5] == b"%PDF-":
                src = fitz.open(stream=data, filetype="pdf")
                out.insert_pdf(src)
                src.close()
            elif ext in IMAGE_EXTS or data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n":
                img = fitz.open(stream=data, filetype="image")
                pdfbytes = img.convert_to_pdf()
                img.close()
                src = fitz.open(stream=pdfbytes, filetype="pdf")
                out.insert_pdf(src)
                src.close()
            else:
                # last try: maybe a pdf with an odd name
                try:
                    src = fitz.open(stream=data, filetype="pdf")
                    out.insert_pdf(src)
                    src.close()
                except Exception:
                    skipped.append(fname)
        except Exception as e:
            logger.info("docsplit normalize %s failed: %s", fname, e)
            skipped.append(fname)
    pdf = out.tobytes()
    n = out.page_count
    out.close()
    return pdf, n, skipped


# ── Job storage (short-lived working PDF on disk) ────────────────────────────
def save_job(pdf_bytes: bytes) -> str:
    os.makedirs(TMP_ROOT, exist_ok=True)
    _cleanup_old()
    job = uuid.uuid4().hex[:16]
    d = os.path.join(TMP_ROOT, job)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "working.pdf"), "wb") as f:
        f.write(pdf_bytes)
    return job


def load_job(job: str) -> Optional[bytes]:
    p = os.path.join(TMP_ROOT, _safe_job(job), "working.pdf")
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def _cleanup_old(max_age: int = 6 * 3600) -> None:
    try:
        now = time.time()
        for name in os.listdir(TMP_ROOT):
            d = os.path.join(TMP_ROOT, name)
            try:
                if os.path.isdir(d) and (now - os.path.getmtime(d)) > max_age:
                    for f in os.listdir(d):
                        os.remove(os.path.join(d, f))
                    os.rmdir(d)
            except Exception:
                pass
    except Exception:
        pass


# ── segmentation, on this server ─────────────────────────────────────────────
async def segment(pdf_bytes: bytes, page_count: int) -> list:
    """Find the separate documents in a merged PDF and their page ranges (1-indexed).

    Reads every page HERE - the text layer where there is one, local OCR where there is not -
    and cuts a new document wherever the page's type changes. Nothing is uploaded anywhere.

    This replaced a Gemini call on 28 Sep. A claim bundle is somebody's hospital file and it does
    not leave this server. The local reader is less certain than the model was, which is why the
    page ranges land in front of a person to adjust before anything is exported - and why a rule
    a staff member teaches (biz_nidaan_doc_sets) beats whatever this works out.

    Best-effort, exactly as before: any failure gives one document covering every page, and the
    person splits it by hand.
    """
    fallback = [{"name": "Document 1", "start": 1, "end": page_count, "summary": ""}]
    try:
        import biz_nidaan_doc_brain as brain
        import biz_nidaan_doc_sets as sets
        pages = await brain.classify_pages(pdf_bytes, await _learned_rules())
        if not pages:
            return fallback
        # The engine speaks in keys ("discharge"); a person reading the review screen needs the
        # words ("Discharge summary"). `why` carries what the page actually said that decided it,
        # which is the one thing that makes a wrong guess quick to correct rather than puzzling.
        labelled = []
        for pg in pages:
            t = pg.get("doc_type") or "other"
            labelled.append({**pg,
                             "doc_type": sets.type_label(t),
                             "summary": pg.get("why") or ""})
        docs = _pages_to_docs(labelled, page_count)
        return docs or fallback
    except Exception as e:  # noqa: BLE001
        logger.warning("docsplit segment failed: %s", e)
        return fallback


async def _learned_rules() -> list:
    """The rules staff have taught, so a correction made once holds the next time.

    Every correction a staff member makes on the review screen is stored as a rule - a handful of
    readable words off that page, and the name of who taught it - and a rule always beats the
    engine's own reading, because a person looked at that page and the engine guessed.

    Fails to an EMPTY list, never an error: a splitter that still works without rules is worth
    more than one that refuses because a table is missing.
    """
    try:
        import biz_nidaan_doc_store as store
        return await store.load_rules()
    except Exception as e:  # noqa: BLE001
        logger.debug("no learned rules available: %s", e)
        return []


def _pages_to_docs(pages: list, n: int) -> list:
    """Fold per-page labels into contiguous documents by their `new_doc` boundaries."""
    # Index labels by page number; tolerate gaps/dupes by clamping to 1..n.
    by_page = {}
    for p in pages or []:
        try:
            pg = max(1, min(int(p.get("page", 0)), n))
        except Exception:
            continue
        by_page.setdefault(pg, p)
    docs, cur = [], None
    for pg in range(1, n + 1):
        lbl = by_page.get(pg, {})
        name = (str(lbl.get("doc_type") or "").strip() or "Document")[:80]
        is_start = bool(lbl.get("new_doc")) or pg == 1 or cur is None
        summ = (str(lbl.get("summary") or "").strip())[:200]
        if is_start:
            if cur:
                docs.append(cur)
            cur = {"name": name, "start": pg, "end": pg, "summary": summ}
        else:
            cur["end"] = pg
            if summ and not cur["summary"]:
                cur["summary"] = summ
    if cur:
        docs.append(cur)
    # Number repeats of the same type (e.g. "Lab Report", "Lab Report 2") for clarity.
    seen = {}
    for d in docs:
        seen[d["name"]] = seen.get(d["name"], 0) + 1
        if seen[d["name"]] > 1:
            d["name"] = f"{d['name']} {seen[d['name']]}"
    return docs


def _sanitize(docs: list, n: int) -> list:
    """Clamp ranges to 1..n, drop invalid, sort by start. (Gaps/overlaps are fine — the human fixes them.)"""
    out = []
    for d in docs:
        try:
            s = max(1, min(int(d.get("start", 1)), n))
            e = max(1, min(int(d.get("end", s)), n))
            if e < s:
                s, e = e, s
            out.append({"name": (str(d.get("name") or "Document")).strip()[:80],
                        "start": s, "end": e,
                        "summary": (str(d.get("summary") or "")).strip()[:200]})
        except Exception:
            continue
    out.sort(key=lambda x: (x["start"], x["end"]))
    return out


# ── Thumbnails + export ──────────────────────────────────────────────────────
def render_thumb(pdf_bytes: bytes, page_no: int, width: int = 190) -> Optional[bytes]:
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if page_no < 1 or page_no > doc.page_count:
            doc.close()
            return None
        p = doc[page_no - 1]
        zoom = max(0.2, min(width / max(1.0, p.rect.width), 2.0))
        pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        png = pix.tobytes("png")
        doc.close()
        return png
    except Exception as e:
        logger.info("docsplit thumb %s failed: %s", page_no, e)
        return None


def extract(pdf_bytes: bytes, documents: list) -> list:
    """documents = [{name, start, end}, …] → [(filename.pdf, bytes), …] (names de-duplicated)."""
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    out, used = [], {}
    for d in documents:
        try:
            s = max(1, int(d.get("start")))
            e = min(src.page_count, int(d.get("end")))
        except Exception:
            continue
        if s > e:
            continue
        nd = fitz.open()
        nd.insert_pdf(src, from_page=s - 1, to_page=e - 1)
        base = _safe_name(d.get("name"))
        used[base] = used.get(base, 0) + 1
        fn = f"{base}.pdf" if used[base] == 1 else f"{base}_{used[base]}.pdf"
        out.append((fn, nd.tobytes()))
        nd.close()
    src.close()
    return out


def zip_docs(docs: list) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fn, b in docs:
            z.writestr(fn, b)
    return buf.getvalue()
