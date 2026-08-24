"""
WhatsApp Cloud API (Meta) — outbound send for Sarathi / NidaanPartner.

Isolated module (like biz_nidaan_radar). All secrets come from env, never code:
  WA_ACCESS_TOKEN     — permanent System User token
  WA_PHONE_NUMBER_ID  — the sending number's Phone Number ID (GoLuQ = 1259819740549744)
  WA_WABA_ID          — WhatsApp Business Account ID
  WA_APP_SECRET       — for webhook signature verification (two-way, later)

Two message kinds:
  • send_template — business-initiated (approved template). The ONLY way to start/re-open a chat.
  • send_text     — free-form; delivers only inside the 24h session window (after the user replied).

Best-effort: returns {ok, message_id} or {ok:False, error}. Never raises to the caller.
"""
from __future__ import annotations

import os
import re
import logging
from typing import Optional

import httpx

logger = logging.getLogger("sarathi.whatsapp")
GRAPH = "https://graph.facebook.com/v22.0"


def _token() -> str:
    return (os.getenv("WA_ACCESS_TOKEN") or "").strip()


def _phone_id() -> str:
    return (os.getenv("WA_PHONE_NUMBER_ID") or "").strip()


def is_configured() -> bool:
    return bool(_token() and _phone_id())


def normalize_msisdn(to: str) -> str:
    """Digits only; default India country code (91) when a bare 10-digit number is given."""
    d = re.sub(r"\D", "", to or "")
    if len(d) == 10:
        d = "91" + d
    return d


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
        logger.warning("whatsapp send failed: %s", e)
        return {"ok": False, "error": str(e)[:150]}
    if r.status_code == 200 and d.get("messages"):
        return {"ok": True, "message_id": d["messages"][0].get("id", ""),
                "wa_id": (d.get("contacts") or [{}])[0].get("wa_id", "")}
    err = ((d.get("error") or {}).get("message")) or str(d)[:200]
    logger.warning("whatsapp send rejected [%s]: %s", r.status_code, err)
    return {"ok": False, "error": err, "status": r.status_code}


def body_params(*values) -> list:
    """Build a template body component from ordered {{1}},{{2}}… values."""
    return [{"type": "body", "parameters": [{"type": "text", "text": str(v)} for v in values]}]


async def send_template(to: str, name: str, lang: str = "en_US",
                        components: Optional[list] = None) -> dict:
    """Send an approved template (business-initiated). `components` from body_params(...)."""
    tmpl = {"name": name, "language": {"code": lang}}
    if components:
        tmpl["components"] = components
    return await _post({"messaging_product": "whatsapp", "to": normalize_msisdn(to),
                        "type": "template", "template": tmpl})


async def send_text(to: str, body: str) -> dict:
    """Free-form text — only delivers inside the 24h session window (recipient replied recently)."""
    return await _post({"messaging_product": "whatsapp", "to": normalize_msisdn(to),
                        "type": "text", "text": {"body": (body or "")[:4000]}})


async def number_health() -> dict:
    """Sender number status + quality (for an ops health tile). None-safe."""
    if not is_configured():
        return {"configured": False}
    url = f"{GRAPH}/{_phone_id()}"
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params={"fields": "display_phone_number,verified_name,quality_rating,"
                                         "code_verification_status,platform_type",
                                         "access_token": _token()})
        d = r.json() if r.content else {}
    except Exception as e:  # noqa: BLE001
        return {"configured": True, "error": str(e)[:120]}
    if r.status_code != 200:
        return {"configured": True, "error": ((d.get("error") or {}).get("message")) or "unknown"}
    return {"configured": True, **d}
