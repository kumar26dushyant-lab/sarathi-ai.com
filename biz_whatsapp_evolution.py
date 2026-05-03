# =============================================================================
#  biz_whatsapp_evolution.py — Evolution API Client (WhatsApp v2)
# =============================================================================
#
#  Python client for the Evolution API (Baileys-based unofficial WhatsApp).
#  Used by Sarathi-AI's Agent-Assist WhatsApp automation.
#
#  All calls are async (httpx). Configure via env in biz.env:
#    EVOLUTION_API_URL       — e.g., http://localhost:8080
#    EVOLUTION_API_KEY       — global API key set in evolution.env
#    EVOLUTION_WEBHOOK_URL   — public URL Sarathi exposes for webhooks
#    EVOLUTION_WEBHOOK_TOKEN — shared secret to validate inbound webhooks
#
#  Lifecycle for a tenant:
#    1. create_instance()  → registers a new Baileys session
#    2. connect_instance() → returns QR base64 to scan
#    3. (user scans QR) Evolution emits CONNECTION_UPDATE webhook
#    4. send_text() / send_media() once connected
#    5. logout_instance() / delete_instance() to revoke
#
# =============================================================================
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import httpx

logger = logging.getLogger("sarathi.wa.evo")

_base_url: str = ""
_api_key: str = ""
_webhook_url: str = ""
_webhook_token: str = ""
_default_timeout = 20.0


def init_evolution() -> None:
    """Read configuration from environment. Idempotent."""
    global _base_url, _api_key, _webhook_url, _webhook_token
    _base_url = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
    _api_key = os.getenv("EVOLUTION_API_KEY", "")
    _webhook_url = os.getenv("EVOLUTION_WEBHOOK_URL", "")
    _webhook_token = os.getenv("EVOLUTION_WEBHOOK_TOKEN", "")
    if is_enabled():
        logger.info("✅ Evolution API client ready: %s", _base_url)
    else:
        logger.info("⏸️  Evolution API not configured (EVOLUTION_API_URL/KEY missing)")


def is_enabled() -> bool:
    return bool(_base_url and _api_key)


def webhook_token() -> str:
    """Shared secret used to validate inbound webhook signatures."""
    return _webhook_token


# ─────────────────────────────────────────────────────────────────────────────
#  Internal HTTP helper
# ─────────────────────────────────────────────────────────────────────────────

async def _request(method: str, path: str, *, json: Optional[dict] = None,
                   params: Optional[dict] = None, timeout: Optional[float] = None) -> dict:
    """Low-level HTTP call. Returns {} on error (logged). Never raises."""
    if not is_enabled():
        return {"error": "evolution_not_configured"}
    url = f"{_base_url}{path}"
    headers = {"apikey": _api_key, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout or _default_timeout) as client:
            resp = await client.request(method, url, json=json, params=params, headers=headers)
            if resp.status_code >= 400:
                logger.warning("Evolution %s %s → %d: %s",
                               method, path, resp.status_code, resp.text[:200])
                return {"error": f"http_{resp.status_code}", "detail": resp.text[:200]}
            try:
                return resp.json()
            except Exception:
                return {"ok": True, "raw": resp.text[:500]}
    except httpx.TimeoutException:
        logger.error("Evolution timeout: %s %s", method, path)
        return {"error": "timeout"}
    except Exception as e:
        logger.error("Evolution request error: %s", e)
        return {"error": str(e)[:200]}


# ─────────────────────────────────────────────────────────────────────────────
#  Instance lifecycle
# ─────────────────────────────────────────────────────────────────────────────

async def create_instance(instance_name: str, *, tenant_id: int) -> dict:
    """
    Create a new Baileys instance. The instance_name MUST be unique
    across all tenants (use e.g. "sarathi_t{tenant_id}").
    Webhook is auto-registered if EVOLUTION_WEBHOOK_URL is set.
    """
    payload: dict[str, Any] = {
        "instanceName": instance_name,
        "qrcode": True,
        "integration": "WHATSAPP-BAILEYS",
    }
    if _webhook_url:
        payload["webhook"] = {
            "url": _webhook_url,
            "byEvents": False,
            "base64": True,
            "events": [
                "QRCODE_UPDATED",
                "CONNECTION_UPDATE",
                "MESSAGES_UPSERT",
                "MESSAGES_UPDATE",
                "SEND_MESSAGE",
            ],
            "headers": {"X-Sarathi-Webhook-Token": _webhook_token} if _webhook_token else {},
        }
    return await _request("POST", "/instance/create", json=payload)


async def connect_instance(instance_name: str) -> dict:
    """
    Trigger QR generation for an existing instance.
    Returns dict with 'base64' (QR PNG data URL) and 'pairingCode' if available.
    """
    return await _request("GET", f"/instance/connect/{instance_name}")


async def get_connection_state(instance_name: str) -> dict:
    """Returns: {state: 'open'|'connecting'|'close'} or error."""
    return await _request("GET", f"/instance/connectionState/{instance_name}")


async def logout_instance(instance_name: str) -> dict:
    """Logout the WhatsApp session (instance config remains)."""
    return await _request("DELETE", f"/instance/logout/{instance_name}")


async def delete_instance(instance_name: str) -> dict:
    """Permanently delete the instance and its credentials."""
    return await _request("DELETE", f"/instance/delete/{instance_name}")


async def list_instances() -> list:
    """List all instances on this Evolution server."""
    res = await _request("GET", "/instance/fetchInstances")
    if isinstance(res, list):
        return res
    return res.get("instances", []) if isinstance(res, dict) else []


# ─────────────────────────────────────────────────────────────────────────────
#  Messaging
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_phone(phone: str) -> str:
    """Normalize phone for Evolution: digits only, default +91 if 10-digit."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return digits


async def send_text(instance_name: str, to_phone: str, text: str,
                    *, delay_ms: int = 0, quoted_msg_id: str = "") -> dict:
    """
    Send a plain-text WhatsApp message.
    delay_ms — server-side composing delay (Evolution simulates 'typing').
    """
    payload: dict[str, Any] = {
        "number": _normalize_phone(to_phone),
        "text": text,
    }
    if delay_ms > 0:
        payload["delay"] = delay_ms
    if quoted_msg_id:
        payload["quoted"] = {"key": {"id": quoted_msg_id}}
    return await _request("POST", f"/message/sendText/{instance_name}", json=payload)


async def send_media(instance_name: str, to_phone: str, media_url: str,
                     *, caption: str = "", media_type: str = "image",
                     filename: str = "", delay_ms: int = 0) -> dict:
    """
    Send media (image/video/document/audio) via URL.
    media_type: 'image' | 'video' | 'document' | 'audio'
    """
    payload: dict[str, Any] = {
        "number": _normalize_phone(to_phone),
        "mediatype": media_type,
        "media": media_url,
    }
    if caption:
        payload["caption"] = caption
    if filename:
        payload["fileName"] = filename
    if delay_ms > 0:
        payload["delay"] = delay_ms
    return await _request("POST", f"/message/sendMedia/{instance_name}", json=payload)


async def send_presence(instance_name: str, to_phone: str,
                        presence: str = "composing", duration_ms: int = 2000) -> dict:
    """
    Send 'typing...' or 'recording...' presence indicator.
    presence: 'composing' (typing) | 'recording' | 'paused'
    """
    payload = {
        "number": _normalize_phone(to_phone),
        "presence": presence,
        "delay": duration_ms,
    }
    return await _request("POST", f"/chat/sendPresence/{instance_name}", json=payload)


async def mark_read(instance_name: str, remote_jid: str, message_id: str) -> dict:
    """Mark an inbound message as read (blue ticks)."""
    payload = {
        "readMessages": [
            {"remoteJid": remote_jid, "id": message_id, "fromMe": False}
        ]
    }
    return await _request("POST", f"/chat/markMessageAsRead/{instance_name}", json=payload)


# ─────────────────────────────────────────────────────────────────────────────
#  Webhook validation helper
# ─────────────────────────────────────────────────────────────────────────────

def validate_webhook_token(received_token: str) -> bool:
    """Check inbound webhook against shared secret. Constant-time compare."""
    if not _webhook_token:
        # If no token configured, accept (dev only). In prod always set token.
        return True
    if not received_token:
        return False
    # Constant-time comparison
    a, b = received_token.encode(), _webhook_token.encode()
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0


# ─────────────────────────────────────────────────────────────────────────────
#  Convenience: build a deterministic instance name for a tenant/agent
# ─────────────────────────────────────────────────────────────────────────────

def build_instance_name(tenant_id: int, agent_id: Optional[int] = None) -> str:
    """
    Stable instance identifier used inside Evolution and Sarathi DB.
    For tenant-wide (Enterprise main): sarathi_t{tid}
    For per-agent (multi-agent firms): sarathi_t{tid}_a{aid}
    """
    if agent_id:
        return f"sarathi_t{tenant_id}_a{agent_id}"
    return f"sarathi_t{tenant_id}"
