"""
biz_nidaan_telegram.py — NidaanPartner ops Telegram bot
─────────────────────────────────────────────────────────────────────────────
A Nidaan-OWNED Telegram bot for internal ops notifications. Deliberately built
standalone (patterns borrowed from the Sarathi bot, but no shared state or
dependency) because Nidaan ops has different requirements.

Why Telegram for internal ops:
  • Official Bot API — no ban risk, unlike the unofficial WhatsApp/Baileys path.
  • Server-to-server: no phone to keep online, no session to die.
  • Free, with inline buttons, file/voice support and reliable delivery.

Flow
  1. Super admin creates a bot with @BotFather and pastes the token in the ops
     portal (Telegram Bot panel). We verify it (getMe) and register a webhook.
  2. Each staffer opens their personal deep link (t.me/<bot>?start=<code>) and
     taps Start. The webhook matches the code to their staff record and stores
     their chat_id — that's the link.
  3. Notifications then fan out to Telegram alongside dashboard/email.

Config lives in nidaan_ops_settings (DB-backed so both web workers see it):
  telegram_bot_token, telegram_bot_username, telegram_enabled
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Optional

import aiosqlite
import httpx

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.telegram")

API_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 20.0


# ── config helpers ───────────────────────────────────────────────────────────
async def _get_setting(key: str, default: str = "") -> str:
    import biz_nidaan as nidaan
    try:
        return (await nidaan.get_ops_setting(key, default)) or default
    except Exception:
        return default


async def _set_setting(key: str, value: str) -> None:
    import biz_nidaan as nidaan
    await nidaan.set_ops_setting(key, value)


async def get_bot_token() -> str:
    return (await _get_setting("telegram_bot_token", "")).strip()


async def is_enabled() -> bool:
    if (await _get_setting("telegram_enabled", "1")) != "1":
        return False
    return bool(await get_bot_token())


async def get_config() -> dict:
    """Non-secret view of the bot config for the ops UI."""
    token = await get_bot_token()
    return {
        "configured": bool(token),
        "enabled": (await _get_setting("telegram_enabled", "1")) == "1",
        "bot_username": await _get_setting("telegram_bot_username", ""),
        "token_hint": (f"…{token[-6:]}" if token else ""),
        "webhook_set_at": await _get_setting("telegram_webhook_set_at", ""),
    }


def webhook_secret(token: str) -> str:
    """Unguessable, deterministic path segment derived from the bot token."""
    return hashlib.sha256(("nidaan-tg:" + token).encode()).hexdigest()[:32]


# ── raw API ──────────────────────────────────────────────────────────────────
async def _call(method: str, payload: Optional[dict] = None,
                token: Optional[str] = None) -> dict:
    tok = token if token is not None else await get_bot_token()
    if not tok:
        return {"ok": False, "error": "no_token"}
    url = API_BASE.format(token=tok, method=method)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(url, json=payload or {})
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": f"http_{r.status_code}"}
    except httpx.TimeoutException:
        logger.info("Telegram timeout: %s", method)
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        logger.warning("Telegram call error %s: %s", method, e)
        return {"ok": False, "error": str(e)[:200]}


async def verify_token(token: str) -> dict:
    """getMe — validates a pasted token and returns the bot's identity."""
    res = await _call("getMe", token=token)
    if res.get("ok"):
        return {"ok": True, "username": (res.get("result") or {}).get("username", ""),
                "name": (res.get("result") or {}).get("first_name", "")}
    return {"ok": False, "error": res.get("description") or res.get("error") or "invalid_token"}


async def set_webhook(base_url: str, token: Optional[str] = None) -> dict:
    tok = token if token is not None else await get_bot_token()
    if not tok:
        return {"ok": False, "error": "no_token"}
    url = f"{base_url.rstrip('/')}/nidaan/telegram/webhook/{webhook_secret(tok)}"
    res = await _call("setWebhook", {"url": url, "allowed_updates": ["message", "callback_query"],
                                     "drop_pending_updates": True}, token=tok)
    if res.get("ok"):
        from datetime import datetime
        await _set_setting("telegram_webhook_set_at",
                           datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    return res


async def send_message(chat_id: str, text: str,
                       buttons: Optional[list] = None) -> tuple[bool, str]:
    """Send a plain-text message. `buttons` = [[{'text':…, 'url':…}], …]."""
    if not chat_id:
        return (False, "no_chat_id")
    payload: dict = {"chat_id": str(chat_id), "text": text[:4000],
                     "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = await _call("sendMessage", payload)
    if res.get("ok"):
        return (True, "")
    err = res.get("description") or res.get("error") or "unknown"
    return (False, str(err)[:200])


# ── staff linking ────────────────────────────────────────────────────────────
async def get_or_create_link_code(staff_id: int) -> str:
    """A stable per-staff code used in the bot deep link."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT telegram_link_code FROM nidaan_staff WHERE staff_id=?", (staff_id,))).fetchone()
        code = (row["telegram_link_code"] if row else "") or ""
        if not code:
            code = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]
            await conn.execute(
                "UPDATE nidaan_staff SET telegram_link_code=? WHERE staff_id=?", (code, staff_id))
            await conn.commit()
        return code


async def get_staff_telegram(staff_id: int) -> dict:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT telegram_chat_id, telegram_username, telegram_linked_at "
            "FROM nidaan_staff WHERE staff_id=?", (staff_id,))).fetchone()
        return dict(row) if row else {}


async def unlink_staff(staff_id: int) -> None:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_staff SET telegram_chat_id=NULL, telegram_username=NULL, "
            "telegram_linked_at=NULL WHERE staff_id=?", (staff_id,))
        await conn.commit()


async def _link_by_code(code: str, chat_id: str, username: str) -> Optional[dict]:
    """Bind a Telegram chat to the staffer holding this link code."""
    if not code:
        return None
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT staff_id, name FROM nidaan_staff WHERE telegram_link_code=? "
            "AND status='active' AND deleted_at IS NULL", (code,))).fetchone()
        if not row:
            return None
        await conn.execute(
            "UPDATE nidaan_staff SET telegram_chat_id=?, telegram_username=?, "
            "telegram_linked_at=CURRENT_TIMESTAMP WHERE staff_id=?",
            (str(chat_id), username or "", row["staff_id"]))
        await conn.commit()
        return {"staff_id": row["staff_id"], "name": row["name"]}


async def handle_update(update: dict) -> None:
    """Process one webhook update. Only /start <code> linking is supported for now
    (read-only AI querying comes later); anything else gets a gentle hint."""
    try:
        msg = update.get("message") or {}
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        text = (msg.get("text") or "").strip()
        username = (msg.get("from") or {}).get("username") or ""
        if not chat_id or not text:
            return
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            code = parts[1].strip() if len(parts) > 1 else ""
            if code:
                linked = await _link_by_code(code, str(chat_id), username)
                if linked:
                    await send_message(str(chat_id),
                        f"✅ Connected, {linked['name']}!\n\n"
                        f"You'll now get your NidaanPartner task and approval "
                        f"notifications right here.\n\n"
                        f"You can unlink anytime from the portal → Telegram Bot.")
                    return
                await send_message(str(chat_id),
                    "⚠️ That link code isn't valid or has expired.\n\n"
                    "Open the NidaanPartner portal → Telegram Bot and use your personal "
                    "link again.")
                return
            await send_message(str(chat_id),
                "👋 This is the NidaanPartner ops bot.\n\n"
                "To receive your notifications, open the portal → Telegram Bot and tap "
                "your personal connect link.")
            return
        # Any other message — keep it simple and safe for now.
        await send_message(str(chat_id),
            "This bot delivers your NidaanPartner ops notifications.\n"
            "Manage it from the portal → Telegram Bot.")
    except Exception as e:
        logger.warning("Telegram update handling failed: %s", e)


# ── notification fan-out ─────────────────────────────────────────────────────
async def notify_staff(staff_id: int, text: str, url: Optional[str] = None) -> tuple[bool, str]:
    """Send an ops notification to one staffer's linked Telegram."""
    if not await is_enabled():
        return (False, "telegram_disabled")
    tg = await get_staff_telegram(staff_id)
    chat_id = (tg or {}).get("telegram_chat_id")
    if not chat_id:
        return (False, "not_linked")
    buttons = [[{"text": "Open in portal", "url": url}]] if url else None
    return await send_message(chat_id, text, buttons)


async def linked_staff_count() -> int:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        row = await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_staff WHERE telegram_chat_id IS NOT NULL "
            "AND telegram_chat_id != '' AND status='active' AND deleted_at IS NULL")).fetchone()
        return int(row[0]) if row else 0
