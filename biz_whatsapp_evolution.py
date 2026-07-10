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

# Residential proxy config (optional — loaded from env)
_proxy_host: str = ""
_proxy_port: str = ""
_proxy_username: str = ""
_proxy_password: str = ""
_proxy_protocol: str = "socks5"


def init_evolution() -> None:
    """Read configuration from environment. Idempotent."""
    global _base_url, _api_key, _webhook_url, _webhook_token
    global _proxy_host, _proxy_port, _proxy_username, _proxy_password, _proxy_protocol
    _base_url = os.getenv("EVOLUTION_API_URL", "").rstrip("/")
    _api_key = os.getenv("EVOLUTION_API_KEY", "")
    _webhook_url = os.getenv("EVOLUTION_WEBHOOK_URL", "")
    _webhook_token = os.getenv("EVOLUTION_WEBHOOK_TOKEN", "")
    _proxy_host = os.getenv("WA_PROXY_HOST", "")
    _proxy_port = os.getenv("WA_PROXY_PORT", "")
    _proxy_username = os.getenv("WA_PROXY_USERNAME", "")
    _proxy_password = os.getenv("WA_PROXY_PASSWORD", "")
    _proxy_protocol = os.getenv("WA_PROXY_PROTOCOL", "socks5")
    if is_enabled():
        proxy_status = f" (proxy: {_proxy_host}:{_proxy_port})" if _proxy_host else " (no proxy)"
        logger.info("\u2705 Evolution API client ready: %s%s", _base_url, proxy_status)
    else:
        logger.info("\u23f8\ufe0f  Evolution API not configured (EVOLUTION_API_URL/KEY missing)")


def proxy_config() -> dict:
    """Return the residential proxy config dict, or empty dict if not configured."""
    if _proxy_host and _proxy_port:
        return {
            "enabled": True,
            "host": _proxy_host,
            "port": _proxy_port,
            "protocol": _proxy_protocol,
            "username": _proxy_username,
            "password": _proxy_password,
        }
    return {}


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

async def create_instance(instance_name: str, *, tenant_id: int,
                          qrcode: bool = True, number: str = "") -> dict:
    """
    Create a new Baileys instance. The instance_name MUST be unique
    across all tenants (use e.g. "sarathi_t{tenant_id}").
    Webhook is auto-registered if EVOLUTION_WEBHOOK_URL is set.
    Set qrcode=False and number=E164 when requesting pairing-code mode.
    """
    payload: dict[str, Any] = {
        "instanceName": instance_name,
        "qrcode": qrcode,
        "integration": "WHATSAPP-BAILEYS",
        # Mimic a real Windows/Chrome desktop — reduces IP-reputation 401 rejections
        # from WhatsApp's fingerprint check during the pairing handshake.
        # Format: [OS, Browser, Version] matching Baileys Browsers.windows("Chrome")
        "browser": ["Windows", "Chrome", "126.0.0.0"],
    }
    # Embed proxy in the create payload so Baileys is configured BEFORE it opens
    # the WebSocket — calling proxy/set after create is a race condition because
    # Baileys starts connecting immediately on instance creation.
    cfg = proxy_config()
    if cfg:
        payload["proxy"] = cfg
    if number:
        payload["number"] = number
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


async def set_instance_proxy(instance_name: str) -> dict:
    """
    Apply the residential proxy to a Baileys instance via Evolution API.
    Must be called BEFORE connect_instance or request_pairing_code so that
    the WhatsApp WebSocket handshake goes through the residential IP.
    No-op if WA_PROXY_HOST is not configured.
    """
    cfg = proxy_config()
    if not cfg:
        logger.info("No proxy configured — skipping proxy setup for %s", instance_name)
        return {"ok": True, "skipped": True}
    result = await _request("POST", f"/proxy/set/{instance_name}", json=cfg)
    logger.info("Proxy set for %s → %s", instance_name, result)
    return result


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


async def restart_instance(instance_name: str) -> dict:
    """Restart the Baileys socket for an instance (keeps creds). Best-effort
    automatic recovery step used by the WhatsApp watchdog."""
    return await _request("POST", f"/instance/restart/{instance_name}")


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
    """Normalize phone for Evolution: digits only, default +91 if 10-digit.
    If the input already contains '@' (a full JID like xxx@lid or xxx@s.whatsapp.net),
    pass it through unchanged so Evolution routes it correctly."""
    if "@" in (phone or ""):
        return phone
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


async def check_number_exists(instance_name: str, phone: str) -> Optional[str]:
    """Verify a number is registered on WhatsApp and return its CANONICAL JID.
    Returns the jid string if the number exists, None if it does not, and
    raises on a transport/API error (so callers can fail-closed deliberately).

    Uses Evolution's /chat/whatsappNumbers — the authoritative check that also
    resolves the true JID, preventing sends to non-existent or mis-mapped
    accounts."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if "@" in (phone or ""):
        digits = "".join(c for c in phone.split("@")[0] if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    if not digits:
        return None
    res = await _request("POST", f"/chat/whatsappNumbers/{instance_name}",
                         json={"numbers": [digits]}, timeout=15.0)
    # Evolution returns a list like [{"exists":true,"jid":"91..@s.whatsapp.net","number":"91.."}]
    items = res if isinstance(res, list) else (res.get("numbers") if isinstance(res, dict) else None)
    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected whatsappNumbers response: {res!r}")
    for it in items:
        if isinstance(it, dict) and (it.get("exists") or it.get("isWhatsapp") or it.get("isWhatsApp")):
            return it.get("jid") or f"{digits}@s.whatsapp.net"
    return None


async def mark_read(instance_name: str, remote_jid: str, message_id: str) -> dict:
    """Mark an inbound message as read (blue ticks)."""
    payload = {
        "readMessages": [
            {"remoteJid": remote_jid, "id": message_id, "fromMe": False}
        ]
    }
    return await _request("POST", f"/chat/markMessageAsRead/{instance_name}", json=payload)


async def get_media_base64(instance_name: str, message_key: dict) -> bytes:
    """Download a media message (audio/image/video) from Evolution API.

    Returns raw bytes on success, empty bytes on failure.
    message_key is the 'key' dict from the Evolution webhook message object.
    """
    result = await _request(
        "POST", f"/chat/getBase64FromMediaMessage/{instance_name}",
        json={"message": {"key": message_key}, "convertToMp4": False},
        timeout=30.0,
    )
    b64 = (result.get("base64") or
           (result.get("data") or {}).get("base64") or "")
    if not b64:
        return b""
    import base64
    try:
        return base64.b64decode(b64)
    except Exception:
        return b""


async def send_status_image(instance_name: str, image_path: str,
                            caption: str = "") -> dict:
    """
    Post an image to the advisor's WhatsApp Status (Story/Status broadcast).
    image_path may be:
      - An absolute filesystem path (encoded as base64)
      - A public URL (used directly)
    Uses Evolution API POST /status/send/{instance}.
    """
    import base64
    from pathlib import Path as _Path

    payload: dict[str, Any] = {"type": "image"}
    if caption:
        payload["caption"] = caption

    p = _Path(image_path) if not image_path.startswith("http") else None
    if p and p.exists():
        # Read file and send as base64
        img_bytes = p.read_bytes()
        payload["content"] = base64.b64encode(img_bytes).decode()
    else:
        # Use URL directly
        payload["content"] = image_path

    return await _request("POST", f"/status/send/{instance_name}", json=payload)


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


async def request_pairing_code(instance_name: str, phone_number: str = "") -> dict:
    """
    Poll Evolution for a WhatsApp pairing code.
    The instance must have been created with qrcode=False and number set.
    Evolution v2.2.3: GET /instance/connect/{name} returns {"code":"ABCD-1234"}
    once Baileys has connected to WA and WA has issued the pairing code.
    Returns {"count": 0} while still waiting (caller should retry).
    """
    params = {}
    if phone_number:
        digits = "".join(c for c in phone_number if c.isdigit())
        if len(digits) == 10:
            digits = "91" + digits
        params["number"] = digits
    return await _request("GET", f"/instance/connect/{instance_name}",
                          params=params if params else None)
