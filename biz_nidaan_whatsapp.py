"""
NidaanPartner claimant-facing WhatsApp (Meta Cloud API) — the document-collection bot channel.

ISOLATED and SEPARATE from biz_sarathi_whatsapp.py (the Sarathi premium WA add-on). This one
uses NidaanPartner's OWN branded number + WABA so claimants see "NidaanPartner" as the sender.
All secrets from env, never code:
  WA_NIDAAN_ACCESS_TOKEN     — permanent System User token for the Nidaan WABA
  WA_NIDAAN_PHONE_NUMBER_ID  — the Nidaan sending number's Phone Number ID (number 9183686384)
  WA_NIDAAN_WABA_ID          — WhatsApp Business Account ID
  WA_NIDAAN_APP_SECRET       — app secret, for inbound webhook signature verification
  WA_NIDAAN_VERIFY_TOKEN     — the token Meta echoes on webhook GET verification

Message kinds:
  • send_template  — business-initiated (approved template). The ONLY way to START/re-open a chat.
  • send_text      — free-form; delivers only inside the 24h session (after the claimant replied).
  • send_audio     — voice note (TTS) — inside the 24h session; for low-literacy claimants.
  • send_document  — send a PDF/file inside the 24h session.
  • download_media — pull an inbound media file (a document the claimant sent) by media id.

Never raises to the caller — returns {ok, ...} or {ok:False, error}.
"""
from __future__ import annotations

import os
import re
import hmac
import hashlib
import logging
import contextlib
import contextvars
from typing import Optional

import httpx

logger = logging.getLogger("nidaan.whatsapp")
GRAPH = "https://graph.facebook.com/v22.0"

# ── outbound attribution ─────────────────────────────────────────────────────
# Only INBOUND messages were ever written to nidaan_wa_messages, so every reply the bot sent was
# invisible to ops (the "Messages sent" stat sat at 0 forever) and a staffer could not read what
# the AI had told a customer. _post() is the one choke point every send passes through, so the
# log is written here — one place, complete coverage, no call site left to forget.
#
# A context variable carries WHO is sending, because _post() cannot see the caller. Unset means
# "bot": every existing caller is an automation, so the default label stays truthful.
_SENDER: contextvars.ContextVar = contextvars.ContextVar("wa_sender", default=("bot", "", ""))


@contextlib.contextmanager
def sending_as(sender: str, name: str = "", staff_id: str = ""):
    """Attribute sends made inside this block — 'human', 'campaign', 'journey', 'bot'."""
    tok = _SENDER.set((sender or "bot", name or "", str(staff_id or "")))
    try:
        yield
    finally:
        _SENDER.reset(tok)


async def _log_outbound(payload: dict, res: dict) -> None:
    """Record one outbound message. Best-effort: a logging failure must never break a send."""
    try:
        import biz_nidaan_wa_flow as _flow
        to = str(payload.get("to") or "")
        mtype = str(payload.get("type") or "")
        tmpl = ((payload.get("template") or {}).get("name") or "") if mtype == "template" else ""
        body = ((payload.get("text") or {}).get("body") or "") if mtype == "text" else ""
        media_id = ""
        for k in ("audio", "document", "image", "video"):
            if isinstance(payload.get(k), dict) and payload[k].get("id"):
                media_id = payload[k]["id"]
                break
        claim_id = None
        try:
            ct = await _flow.get_contact(to) or {}
            claim_id = ct.get("claim_id")
        except Exception:
            pass
        sender, sname, sid = _SENDER.get()
        ok = bool(res.get("ok"))
        await _flow.log_message(
            direction="out", msisdn=to, claim_id=claim_id,
            wa_message_id=str(res.get("message_id") or ""), msg_type=mtype or "text",
            template_name=tmpl, body=body, media_id=media_id,
            status="sent" if ok else "failed", error=str(res.get("error") or "")[:300],
            sender=sender, sender_name=sname, staff_id=sid)
    except Exception as e:  # noqa: BLE001
        logger.info("outbound WhatsApp log failed (send itself was fine): %s", e)


def _token() -> str:
    return (os.getenv("WA_NIDAAN_ACCESS_TOKEN") or "").strip()


def _phone_id() -> str:
    return (os.getenv("WA_NIDAAN_PHONE_NUMBER_ID") or "").strip()


def _app_secret() -> str:
    return (os.getenv("WA_NIDAAN_APP_SECRET") or "").strip()


def verify_token() -> str:
    return (os.getenv("WA_NIDAAN_VERIFY_TOKEN") or "").strip()


def is_configured() -> bool:
    return bool(_token() and _phone_id())


def normalize_msisdn(to: str) -> str:
    """Digits only; default India country code (91) for a bare 10-digit number."""
    d = re.sub(r"\D", "", to or "")
    if len(d) == 10:
        d = "91" + d
    return d


def verify_webhook_signature(app_secret: str, raw_body: bytes, header_sig: str) -> bool:
    """Validate Meta's X-Hub-Signature-256 over the RAW request body. Never raises."""
    try:
        secret = (app_secret or _app_secret())
        if not secret or not header_sig:
            return False
        expected = "sha256=" + hmac.new(secret.encode(), raw_body or b"", hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header_sig.strip())
    except Exception:
        return False


async def _post(payload: dict) -> dict:
    if not is_configured():
        return {"ok": False, "error": "not_configured"}
    url = f"{GRAPH}/{_phone_id()}/messages"
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(url, headers={"Authorization": f"Bearer {_token()}",
                                           "Content-Type": "application/json"}, json=payload)
        d = r.json() if r.content else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("nidaan-wa send failed: %s", e)
        res = {"ok": False, "error": str(e)[:150]}
        await _log_outbound(payload, res)
        return res
    if r.status_code == 200 and d.get("messages"):
        res = {"ok": True, "message_id": d["messages"][0].get("id", ""),
               "wa_id": (d.get("contacts") or [{}])[0].get("wa_id", "")}
        await _log_outbound(payload, res)
        return res
    err = ((d.get("error") or {}).get("message")) or str(d)[:200]
    logger.warning("nidaan-wa send rejected [%s]: %s", r.status_code, err)
    res = {"ok": False, "error": err, "status": r.status_code}
    await _log_outbound(payload, res)
    return res


def body_params(*values) -> list:
    """Template body component from ordered {{1}},{{2}}… values."""
    return [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in values]}]


async def send_template(to: str, name: str, lang: str = "en", components: Optional[list] = None) -> dict:
    """Send an approved template (business-initiated). `components` from body_params(...)."""
    tmpl = {"name": name, "language": {"code": lang}}
    if components:
        tmpl["components"] = components
    return await _post({"messaging_product": "whatsapp", "to": normalize_msisdn(to),
                        "type": "template", "template": tmpl})


async def send_text(to: str, body: str) -> dict:
    """Free-form text — delivers only inside the 24h session (claimant replied recently)."""
    return await _post({"messaging_product": "whatsapp", "to": normalize_msisdn(to),
                        "type": "text", "text": {"body": (body or "")[:4000]}})


async def _upload_media(content: bytes, mime: str, filename: str = "file") -> dict:
    """Upload media to the Cloud API → returns {ok, media_id}. Needed before sending audio/doc."""
    if not is_configured():
        return {"ok": False, "error": "not_configured"}
    url = f"{GRAPH}/{_phone_id()}/media"
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(url, headers={"Authorization": f"Bearer {_token()}"},
                             data={"messaging_product": "whatsapp", "type": mime},
                             files={"file": (filename, content, mime)})
        d = r.json() if r.content else {}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:150]}
    if r.status_code == 200 and d.get("id"):
        return {"ok": True, "media_id": d["id"]}
    return {"ok": False, "error": ((d.get("error") or {}).get("message")) or str(d)[:200]}


async def send_audio(to: str, audio_bytes: bytes, mime: str = "audio/ogg") -> dict:
    """Send a voice note (TTS) — inside the 24h session. WhatsApp prefers OGG/Opus for voice."""
    up = await _upload_media(audio_bytes, mime, "voice.ogg")
    if not up.get("ok"):
        return up
    return await _post({"messaging_product": "whatsapp", "to": normalize_msisdn(to),
                        "type": "audio", "audio": {"id": up["media_id"]}})


async def send_document(to: str, pdf_bytes: bytes, filename: str = "document.pdf",
                        caption: str = "") -> dict:
    """Send a PDF/file (e.g. a receipt or the compiled claim doc) — inside the 24h session."""
    up = await _upload_media(pdf_bytes, "application/pdf", filename)
    if not up.get("ok"):
        return up
    doc = {"id": up["media_id"], "filename": filename}
    if caption:
        doc["caption"] = caption[:1000]
    return await _post({"messaging_product": "whatsapp", "to": normalize_msisdn(to),
                        "type": "document", "document": doc})


async def download_media(media_id: str) -> dict:
    """Pull an inbound media file (a document the claimant sent). Two steps: resolve the media
    URL, then GET the bytes (both need the bearer token). Returns {ok, content, mime, sha256}."""
    if not is_configured() or not media_id:
        return {"ok": False, "error": "not_configured_or_no_id"}
    try:
        async with httpx.AsyncClient(timeout=60) as c:
            meta = await c.get(f"{GRAPH}/{media_id}",
                               headers={"Authorization": f"Bearer {_token()}"})
            md = meta.json() if meta.content else {}
            url = md.get("url")
            if not url:
                return {"ok": False, "error": "no_media_url"}
            fr = await c.get(url, headers={"Authorization": f"Bearer {_token()}"})
        if fr.status_code != 200:
            return {"ok": False, "error": f"download_{fr.status_code}"}
        content = fr.content
        return {"ok": True, "content": content, "mime": md.get("mime_type", ""),
                "sha256": md.get("sha256", ""), "size": len(content)}
    except Exception as e:  # noqa: BLE001
        logger.warning("nidaan-wa download_media failed: %s", e)
        return {"ok": False, "error": str(e)[:150]}


async def number_health() -> dict:
    """Sender number status + quality (for the super-admin WA health tile). None-safe."""
    if not is_configured():
        return {"configured": False}
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{GRAPH}/{_phone_id()}",
                            params={"fields": "display_phone_number,verified_name,quality_rating,"
                                    "code_verification_status,platform_type,status",
                                    "access_token": _token()})
        d = r.json() if r.content else {}
    except Exception as e:  # noqa: BLE001
        return {"configured": True, "error": str(e)[:120]}
    if r.status_code != 200:
        return {"configured": True, "error": ((d.get("error") or {}).get("message")) or "unknown"}
    return {"configured": True, **d}
