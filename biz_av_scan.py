"""
NidaanPartner — ANTIVIRUS SCANNING for uploads.

Type checks prove a file is a well-formed PDF; they cannot prove it is safe. A genuine PDF or
DOCX can still carry an exploit or a malicious macro, and we hand these documents to insurers,
hospitals and our own staff — so we are a distribution point, not just a store.

Talks to a local clamd over its UNIX socket. Design decisions that matter:

  • FAIL CLOSED for uploads. If the scanner is unreachable we REJECT rather than wave the file
    through, because an attacker who can knock the scanner over must not thereby disable scanning.
    (`fail_open=True` exists for callers where availability genuinely outranks this.)
  • Scan the BYTES WE WILL STORE, in memory, before anything touches disk — nothing infected is
    ever written, so there is no window where a malicious file exists on the server.
  • Bounded: a size cap and a timeout, so a huge or pathological file cannot stall a request.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import struct

logger = logging.getLogger("nidaan.av")

CLAMD_SOCKET = os.getenv("CLAMD_SOCKET", "/var/run/clamav/clamd.ctl")
_SCAN_TIMEOUT = float(os.getenv("CLAMD_TIMEOUT", "20"))
_MAX_SCAN_BYTES = 32 * 1024 * 1024      # clamd's default StreamMaxLength
_CHUNK = 64 * 1024


def _scan_blocking(data: bytes) -> tuple:
    """(clean, detail). Uses clamd's INSTREAM so nothing is written to disk."""
    s = None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(_SCAN_TIMEOUT)
        s.connect(CLAMD_SOCKET)
        s.sendall(b"zINSTREAM\0")
        for i in range(0, len(data), _CHUNK):
            chunk = data[i:i + _CHUNK]
            s.sendall(struct.pack("!L", len(chunk)) + chunk)
        s.sendall(struct.pack("!L", 0))          # zero-length chunk ends the stream
        resp = b""
        while b"\0" not in resp and len(resp) < 4096:
            part = s.recv(4096)
            if not part:
                break
            resp += part
        text = resp.decode("utf-8", "ignore").strip("\0").strip()
        if text.endswith("OK"):
            return True, ""
        if "FOUND" in text:
            # "stream: Eicar-Test-Signature FOUND"
            name = text.split(":", 1)[-1].replace("FOUND", "").strip()
            return False, name or "malware"
        return None, text or "scanner error"      # None = indeterminate
    except FileNotFoundError:
        return None, "scanner socket missing"
    except (socket.timeout, TimeoutError):
        return None, "scanner timeout"
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:120]
    finally:
        try:
            if s is not None:
                s.close()
        except Exception:
            pass


async def scan_bytes(data: bytes, *, fail_open: bool = False) -> tuple:
    """(allowed, reason). allowed=False means REJECT the upload.

    fail_open=False (the default, and what every upload path uses): if the scanner cannot give a
    verdict we refuse the file. Silently accepting unscanned uploads whenever the scanner is down
    would make the protection trivial to bypass."""
    if not data:
        return True, ""
    if len(data) > _MAX_SCAN_BYTES:
        return False, "file too large to scan safely"
    try:
        clean, detail = await asyncio.wait_for(
            asyncio.to_thread(_scan_blocking, data), timeout=_SCAN_TIMEOUT + 5)
    except Exception as e:  # noqa: BLE001
        clean, detail = None, str(e)[:120]
    if clean is True:
        return True, ""
    if clean is False:
        logger.warning("AV BLOCKED an upload: %s", detail)
        return False, detail
    # Indeterminate — scanner down, timed out, or errored.
    logger.error("AV scanner unavailable (%s) — upload %s", detail,
                 "allowed (fail-open)" if fail_open else "REFUSED (fail-closed)")
    return (True, "") if fail_open else (False, "virus scanner unavailable")


async def available() -> bool:
    """Is clamd reachable? Used by App Health so a dead scanner is visible, not silent."""
    try:
        clean, _ = await asyncio.wait_for(
            asyncio.to_thread(_scan_blocking, b"clamav-availability-probe"), timeout=10)
        return clean is not None
    except Exception:
        return False
