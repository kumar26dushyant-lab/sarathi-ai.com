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
import json
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


# ── AI segmentation ──────────────────────────────────────────────────────────
async def segment(pdf_bytes: bytes, page_count: int) -> list:
    """Detect the distinct documents in the merged PDF + their contiguous page ranges (1-indexed).
    Best-effort: on any failure, returns a single document covering all pages (the human then splits)."""
    fallback = [{"name": "Document 1", "start": 1, "end": page_count, "summary": ""}]
    try:
        import biz_ai
        client = biz_ai._get_client()
        if not client:
            return fallback
        from google.genai import types as gt
        prompt = (
            f"This PDF has {page_count} page(s) and usually contains SEVERAL different documents merged "
            "together — e.g. discharge summary, hospital/final bills, lab or investigation reports, "
            "prescriptions, insurance policy copy, claim form, ID/KYC, referral or cashless letters, etc. "
            "Read it and identify each DISTINCT document and the CONTIGUOUS page range it spans. "
            f"Cover ALL pages 1..{page_count} in order, with no gaps and no overlaps. Give each a short, "
            "clear name (its document type) and a one-line summary. If a page is unclear, still assign it "
            "to the most likely adjacent document. Respond with JSON ONLY: "
            '{"documents":[{"name":"...","start":<int>,"end":<int>,"summary":"..."}]}')
        resp = await client.aio.models.generate_content(
            model=os.getenv("DOCSPLIT_MODEL", "gemini-2.5-flash"),
            contents=[gt.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"), prompt],
            config=gt.GenerateContentConfig(response_mime_type="application/json"))
        docs = (json.loads(resp.text) or {}).get("documents") or []
        return _sanitize(docs, page_count) or fallback
    except Exception as e:
        logger.warning("docsplit segment failed: %s", e)
        return fallback


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
