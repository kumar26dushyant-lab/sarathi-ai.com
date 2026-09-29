# -*- coding: utf-8 -*-
"""Any document a customer sends, as PDF pages - decided by the file's own bytes.

Founder, 29 Sep: "why we are saying DOC/DOCX support coming? why not we are covering all formats?"
and, the day before: "it's not sure what format will come, it can be mix pdf, jpg, jpeg, png, doc,
or may be excel too ... otherwise image stuck so the purpose of this feature defeat".

Until now the splitter decided a file's type by its NAME and understood PDF and a few image types;
everything else - an iPhone's HEIC photo, a Word letter, an Excel bill summary - was dropped as
"skipped". This module is the one place that turns an upload into PDF bytes:

  PDF                                   -> as it is
  JPG PNG WEBP GIF BMP TIFF             -> one PDF page each
  HEIC / HEIF (iPhone photos)           -> JPG -> one page
  DOC DOCX XLS XLSX PPT PPTX ODT ODS
  ODP RTF CSV                           -> LibreOffice -> PDF

THE TYPE COMES FROM THE BYTES, never the filename - the same rule as the upload gate
(sarathi_biz._sniff_file), because a name is whatever the sender typed.

LIBREOFFICE IS FED FILES FROM STRANGERS, so it runs as a contained subprocess: its own throwaway
profile in a private temp directory (nothing carries over between conversions), a time limit, a
memory limit, no macros (headless conversion never runs them, and the profile is new each time),
and ONE conversion at a time so a bad file cannot starve the server. If LibreOffice is missing
or fails, the file is reported as unreadable - never a crash, never a silent drop.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import zipfile
from typing import Optional

logger = logging.getLogger("sarathi.docconvert")

OFFICE_TIMEOUT_S = 90
OFFICE_MEMORY_BYTES = 1536 * 1024 * 1024
_OFFICE_LOCK = threading.Lock()          # one conversion at a time

_IMAGE_MAGIC = (
    (b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png"), (b"GIF87a", "gif"), (b"GIF89a", "gif"),
    (b"BM", "bmp"), (b"II*\x00", "tiff"), (b"MM\x00*", "tiff"),
)
_HEIC_BRANDS = (b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"mif1", b"msf1")


def kind_of(data: bytes) -> tuple:
    """(kind, ext) from the bytes. kind: pdf | image | heic | office | "" (not a document)."""
    if not data or len(data) < 12:
        return "", ""
    head = data[:2048]
    if b"%PDF" in head[:1024]:
        return "pdf", "pdf"
    for magic, ext in _IMAGE_MAGIC:
        if data.startswith(magic):
            return "image", ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image", "webp"
    if data[4:8] == b"ftyp" and data[8:12].lower() in _HEIC_BRANDS:
        return "heic", "heic"
    if data[:5] == b"{\\rtf":
        return "office", "rtf"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":          # old Word / Excel / PowerPoint
        return "office", "ole"
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "mimetype" in names:
                    mt = z.read("mimetype")[:80]
                    for key, ext in ((b"text", "odt"), (b"spreadsheet", "ods"),
                                     (b"presentation", "odp")):
                        if key in mt:
                            return "office", ext
                if "[Content_Types].xml" in names:
                    if any(n.startswith("word/") for n in names):
                        return "office", "docx"
                    if any(n.startswith("xl/") for n in names):
                        return "office", "xlsx"
                    if any(n.startswith("ppt/") for n in names):
                        return "office", "pptx"
        except Exception:  # noqa: BLE001 - a broken zip is not a document
            return "", ""
        return "", ""                                          # a plain zip is never a document
    # CSV / plain text: printable, no NUL bytes, and at least one line break.
    sample = data[:4096]
    if b"\x00" not in sample and b"\n" in sample:
        try:
            sample.decode("utf-8")
            return "office", "csv"
        except UnicodeDecodeError:
            return "", ""
    return "", ""


def office_available() -> bool:
    return bool(shutil.which("soffice") or shutil.which("libreoffice"))


def _limit_child():  # pragma: no cover - runs in the child process, POSIX only
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (OFFICE_MEMORY_BYTES, OFFICE_MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_CPU, (OFFICE_TIMEOUT_S, OFFICE_TIMEOUT_S + 5))
    except Exception:  # noqa: BLE001
        pass


def office_to_pdf(data: bytes, ext: str, name_hint: str = "") -> Optional[bytes]:
    """PDF bytes for an Office / OpenDocument / RTF / CSV file, or None."""
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        logger.warning("LibreOffice is not installed - cannot convert %s", ext)
        return None
    if ext == "ole":
        # Old binary Office: the name's extension is the only hint between doc/xls/ppt, and
        # LibreOffice detects the real format from the content anyway.
        hint = (name_hint or "").lower().rsplit(".", 1)[-1]
        ext = hint if hint in ("doc", "xls", "ppt") else "doc"
    tmp = tempfile.mkdtemp(prefix="nconv_")
    try:
        os.chmod(tmp, 0o700)
        src = os.path.join(tmp, "in." + ext)
        with open(src, "wb") as f:
            f.write(data)
        profile = "file://" + os.path.join(tmp, "profile").replace("\\", "/")
        cmd = [exe, "--headless", "--norestore", "--nolockcheck", "--nodefault",
               "-env:UserInstallation=" + profile, "--convert-to", "pdf", "--outdir", tmp, src]
        with _OFFICE_LOCK:
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=OFFICE_TIMEOUT_S, check=False,
                               preexec_fn=_limit_child if os.name == "posix" else None,
                               env={"HOME": tmp, "PATH": os.environ.get("PATH", "")})
            except subprocess.TimeoutExpired:
                logger.warning("LibreOffice timed out converting a %s", ext)
                return None
        out = os.path.join(tmp, "in.pdf")
        if not os.path.exists(out):
            logger.info("LibreOffice produced nothing for a %s", ext)
            return None
        with open(out, "rb") as f:
            pdf = f.read()
        return pdf if pdf.startswith(b"%PDF") else None
    except Exception as e:  # noqa: BLE001
        logger.warning("office conversion failed (%s): %s", ext, e)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)          # our own scratch - always removed


def heic_to_jpeg(data: bytes) -> Optional[bytes]:
    try:
        from pillow_heif import register_heif_opener
        from PIL import Image
        register_heif_opener()
        im = Image.open(io.BytesIO(data))
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=90)
        return buf.getvalue()
    except Exception as e:  # noqa: BLE001
        logger.info("HEIC conversion failed or is not installed: %s", e)
        return None


def to_pdf(data: bytes, name: str = "") -> tuple:
    """(pdf_bytes or None, kind, reason). reason is plain words when it could not be done."""
    import fitz
    kind, ext = kind_of(data)
    if kind == "pdf":
        return data, kind, ""
    if kind == "heic":
        data = heic_to_jpeg(data)
        if not data:
            return None, kind, "an iPhone photo (HEIC) that could not be converted"
        kind, ext = "image", "jpg"
    if kind == "image":
        try:
            img = fitz.open(stream=data, filetype=ext)
            try:
                return img.convert_to_pdf(), "image", ""
            finally:
                img.close()
        except Exception as e:  # noqa: BLE001
            logger.info("image %s could not be opened: %s", ext, e)
            return None, "image", "a damaged or unusual image"
    if kind == "office":
        pdf = office_to_pdf(data, ext, name)
        if pdf:
            return pdf, "office", ""
        return None, "office", ("a Word/Excel/other document that could not be converted"
                                if office_available() else
                                "a Word/Excel document - conversion is not installed")
    return None, "", "not a document or photo we can read"
