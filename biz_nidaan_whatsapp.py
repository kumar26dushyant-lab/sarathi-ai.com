"""
NidaanPartner claimant-facing WhatsApp (Meta Cloud API) — the document-collection bot channel.

ISOLATED and SEPARATE from biz_sarathi_whatsapp.py (the Sarathi premium WA add-on). This one
uses NidaanPartner's OWN branded number + WABA so complainants see "NidaanPartner" as the sender.
All secrets from env, never code:
  WA_NIDAAN_ACCESS_TOKEN     — permanent System User token for the Nidaan WABA
  WA_NIDAAN_PHONE_NUMBER_ID  — the Nidaan sending number's Phone Number ID (number 9183686384)
  WA_NIDAAN_WABA_ID          — WhatsApp Business Account ID
  WA_NIDAAN_APP_SECRET       — app secret, for inbound webhook signature verification
  WA_NIDAAN_VERIFY_TOKEN     — the token Meta echoes on webhook GET verification

Message kinds:
  • send_template  — business-initiated (approved template). The ONLY way to START/re-open a chat.
  • send_text      — free-form; delivers only inside the 24h session (after the complainant replied).
  • send_audio     — voice note (TTS) — inside the 24h session; for low-literacy complainants.
  • send_document  — send a PDF/file inside the 24h session.
  • download_media — pull an inbound media file (a document the complainant sent) by media id.

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


# ── what a template actually said ───────────────────────────────────────────
# The approved wording lives at Meta. One call returns every template, so it is read once and kept
# for six hours; a failed read is retried after ten minutes rather than on every send.
_TMPL_TTL_S = 6 * 3600
_TMPL_RETRY_S = 600
_TMPL_CACHE: dict = {"at": -1e9, "by": {}}


async def _template_bodies() -> dict:
    import time as _t
    now = _t.monotonic()
    if now - _TMPL_CACHE["at"] < (_TMPL_TTL_S if _TMPL_CACHE["by"] else _TMPL_RETRY_S):
        return _TMPL_CACHE["by"]
    _TMPL_CACHE["at"] = now
    waba = (os.getenv("WA_NIDAAN_WABA_ID") or "").strip()
    if not (waba and _token()):
        return _TMPL_CACHE["by"]
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{GRAPH}/{waba}/message_templates",
                            params={"fields": "name,language,components", "limit": 250},
                            headers={"Authorization": f"Bearer {_token()}"})
        by = {}
        for t in (r.json() or {}).get("data") or []:
            for comp in t.get("components") or []:
                if (comp.get("type") or "").upper() == "BODY" and comp.get("text"):
                    by[(t.get("name") or "", t.get("language") or "")] = comp["text"]
        if by:
            _TMPL_CACHE["by"] = by
        else:
            _TMPL_CACHE["at"] = now - _TMPL_TTL_S + _TMPL_RETRY_S
    except Exception as e:  # noqa: BLE001
        logger.info("could not read template wording from Meta: %s", e)
        _TMPL_CACHE["at"] = now - _TMPL_TTL_S + _TMPL_RETRY_S
    return _TMPL_CACHE["by"]


async def template_text(template: dict) -> str:
    """The words a customer received for a template send: the approved body with this message's
    values in place. Falls back to the values alone when the wording cannot be read."""
    name = (template or {}).get("name") or ""
    lang = ((template or {}).get("language") or {}).get("code") or ""
    params = []
    for comp in (template or {}).get("components") or []:
        if (comp.get("type") or "").lower() == "body":
            params = [str(p.get("text") or "") for p in comp.get("parameters") or []]
    body = (await _template_bodies()).get((name, lang), "")
    if body:
        def _fill(m):
            i = int(m.group(1)) - 1
            return params[i] if 0 <= i < len(params) else m.group(0)
        return re.sub(r"\{\{(\d+)\}\}", _fill, body)
    return (" · ".join(p for p in params if p)) if params else ""


async def _log_outbound(payload: dict, res: dict, send_class: str = "") -> None:
    """Record one outbound message. Best-effort: a logging failure must never break a send."""
    try:
        import biz_nidaan_wa_flow as _flow
        to = str(payload.get("to") or "")
        mtype = str(payload.get("type") or "")
        tmpl = ((payload.get("template") or {}).get("name") or "") if mtype == "template" else ""
        body = ((payload.get("text") or {}).get("body") or "") if mtype == "text" else ""
        if mtype == "template":
            # What the customer READ, not just which template - so the inbox can show it.
            try:
                body = await template_text(payload.get("template") or {})
            except Exception:  # noqa: BLE001
                body = ""
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
            sender=sender, sender_name=sname, staff_id=sid, send_class=send_class)
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
    if os.getenv("NIDAAN_NO_OUTBOUND") == "1":        # test runs never reach a real customer
        return {"ok": False, "error": "outbound_off"}
    # How often are we allowed to speak first? Asked HERE because this is the one place every
    # Nidaan WhatsApp message passes through — a cap on any other line would be a cap with a
    # way around it. See biz_nidaan_wa_guard for what is capped and what deliberately is not.
    _cls = "initiated"
    try:
        import biz_nidaan_wa_guard as _guard
        _to = str(payload.get("to") or "")
        _g = await _guard.decide(_to, str(payload.get("type") or ""), _SENDER.get()[0])
        _cls = _g.get("cls") or _cls
        if not _g.get("send"):
            _body = ((payload.get("text") or {}).get("body") or "") if payload.get("type") == "text" \
                else ((payload.get("template") or {}).get("name") or "")
            await _guard.note_held(_to, _g.get("claim_id"), _g.get("reason") or "held", _body)
            return {"ok": False, "error": _g.get("reason") or "held", "held": True}
        if _g.get("footer") and payload.get("type") == "text":
            _b = (payload.get("text") or {}).get("body") or ""
            payload["text"]["body"] = (_b + _g["footer"])[:4000]
    except Exception as _e:  # noqa: BLE001 — a guard failure must never stop a real message
        logger.warning("wa guard skipped (sending anyway): %s", _e)
    url = f"{GRAPH}/{_phone_id()}/messages"
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(url, headers={"Authorization": f"Bearer {_token()}",
                                           "Content-Type": "application/json"}, json=payload)
        d = r.json() if r.content else {}
    except Exception as e:  # noqa: BLE001
        logger.warning("nidaan-wa send failed: %s", e)
        res = {"ok": False, "error": str(e)[:150]}
        await _log_outbound(payload, res, _cls)
        return res
    if r.status_code == 200 and d.get("messages"):
        res = {"ok": True, "message_id": d["messages"][0].get("id", ""),
               "wa_id": (d.get("contacts") or [{}])[0].get("wa_id", "")}
        await _log_outbound(payload, res, _cls)
        return res
    err = ((d.get("error") or {}).get("message")) or str(d)[:200]
    logger.warning("nidaan-wa send rejected [%s]: %s", r.status_code, err)
    res = {"ok": False, "error": err, "status": r.status_code}
    await _log_outbound(payload, res, _cls)
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


AUTH_TEMPLATE = "np_login_code"


async def send_auth_code(to: str, code: str, lang: str = "en") -> dict:
    """Send a login code on WhatsApp, COLD — no 24-hour window required.

    This is the only way a code reaches someone who has not just written to us, which is what a
    login fallback has to do to be worth having. Meta owns the wording of authentication
    templates, so the code is all we supply — twice: once for the body, and once for the
    copy-code button, which is a separate component with its own parameter (leave it out and the
    send is rejected).
    """
    code = str(code)
    components = [
        {"type": "body", "parameters": [{"type": "text", "text": code}]},
        {"type": "button", "sub_type": "url", "index": "0",
         "parameters": [{"type": "text", "text": code}]},
    ]
    return await send_template(to, AUTH_TEMPLATE, lang=lang, components=components)


async def send_text(to: str, body: str) -> dict:
    """Free-form text — delivers only inside the 24h session (complainant replied recently)."""
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
    """Pull an inbound media file (a document the complainant sent). Two steps: resolve the media
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
