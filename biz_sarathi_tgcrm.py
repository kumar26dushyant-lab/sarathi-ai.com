"""
biz_sarathi_tgcrm.py
====================
Sarathi-AI — Telegram Voice CRM for subscribers (per-firm bot).

Each firm (tenant) connects its OWN Telegram bot (BotFather token). We register a
WEBHOOK (routed by an opaque bot_id) so one HTTPS endpoint fans out to many
tenant bots — no long-polling loops. The Nidaan ops bot (biz_nidaan_telegram.py,
long-polling) is separate and untouched.

SECURITY (design goal: no scammers/fraudsters/anomalies):
  • Bot token stored ENCRYPTED at rest (Fernet). Never logged, never in a URL.
  • Every incoming webhook is verified against a per-bot secret via the
    `X-Telegram-Bot-Api-Secret-Token` header (Telegram-native anti-spoof).
  • Actor must be an ACTIVE, LINKED agent of that firm (is_active re-checked);
    unknown Telegram users get a generic reply (no info leakage).
  • SINGLE-FIRM: a Telegram account can be bound to exactly one firm
    (UNIQUE(telegram_user_id) in tg_links) — the data-isolation guarantee.

This is P0: schema + secure connect/disconnect + webhook pipeline skeleton.
Feature-flagged: SARATHI_TGCRM_ENABLED=0 disables all of it.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite
import httpx

import biz_database as db

logger = logging.getLogger("sarathi.tgcrm")

DB_PATH = db.DB_PATH
API_BASE = "https://api.telegram.org/bot{token}/{method}"
_TIMEOUT = 15.0

# Public base URL for webhook registration (Sarathi host).
SARATHI_BASE_URL = os.getenv("SARATHI_BASE_URL", "https://sarathi-ai.com").rstrip("/")

# Feature gate. Global flag SARATHI_TGCRM_ENABLED turns it on for everyone;
# SARATHI_TGCRM_BETA_TENANTS (comma-separated tenant_ids) turns it on for just
# those firms — so we can beta-test on prod without exposing a half-built feature.
def is_enabled(tenant_id: Optional[int] = None) -> bool:
    if os.getenv("SARATHI_TGCRM_ENABLED", "0") not in ("0", "", "false", "False"):
        return True
    if tenant_id is not None:
        beta = os.getenv("SARATHI_TGCRM_BETA_TENANTS", "")
        if str(tenant_id) in {x.strip() for x in beta.split(",") if x.strip()}:
            return True
    return False


# ── Token encryption at rest ─────────────────────────────────────────────────
def _fernet():
    from cryptography.fernet import Fernet
    key = os.getenv("TGCRM_ENC_KEY", "").strip()
    if not key:
        # Derive a stable Fernet key from JWT_SECRET so no new env var is
        # strictly required; set TGCRM_ENC_KEY to rotate independently.
        seed = (os.getenv("JWT_SECRET") or "sarathi-tgcrm-fallback-seed").encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(seed).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(token: str) -> str:
    return _fernet().encrypt(token.encode()).decode()


def decrypt_token(blob: str) -> str:
    return _fernet().decrypt(blob.encode()).decode()


# ── Raw Telegram API ─────────────────────────────────────────────────────────
async def _call(method: str, payload: Optional[dict] = None,
                token: Optional[str] = None, timeout: Optional[float] = None) -> dict:
    if not token:
        return {"ok": False, "error": "no_token"}
    url = API_BASE.format(token=token, method=method)
    try:
        async with httpx.AsyncClient(timeout=timeout or _TIMEOUT) as client:
            r = await client.post(url, json=payload or {})
            try:
                return r.json()
            except Exception:
                return {"ok": False, "error": f"http_{r.status_code}"}
    except httpx.TimeoutException:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        logger.warning("tgcrm API error %s: %s", method, str(e)[:150])
        return {"ok": False, "error": str(e)[:200]}


async def verify_token(token: str) -> dict:
    """getMe — validate a pasted token, return bot identity. The numeric bot id is
    stable across token regeneration, so it's our opaque routing key (bot_id)."""
    res = await _call("getMe", token=token)
    if res.get("ok"):
        r = res.get("result") or {}
        return {"ok": True, "username": r.get("username", ""),
                "name": r.get("first_name", ""), "bot_id": str(r.get("id") or "")}
    return {"ok": False, "error": res.get("description") or res.get("error") or "invalid_token"}


async def send_message(token: str, chat_id, text: str, buttons: Optional[list] = None) -> dict:
    payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                     "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return await _call("sendMessage", payload, token=token)


# ── Schema (self-contained, additive) ────────────────────────────────────────
async def ensure_schema() -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript("""
        CREATE TABLE IF NOT EXISTS tg_firm_bots (
            bot_id         TEXT PRIMARY KEY,
            tenant_id      INTEGER NOT NULL,
            bot_token_enc  TEXT NOT NULL,
            bot_username   TEXT DEFAULT '',
            webhook_secret TEXT NOT NULL,
            status         TEXT DEFAULT 'active',
            last_error     TEXT DEFAULT '',
            created_by     INTEGER,
            created_at     TEXT,
            updated_at     TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tg_firm_bots_tenant ON tg_firm_bots(tenant_id);

        CREATE TABLE IF NOT EXISTS tg_links (
            telegram_user_id INTEGER PRIMARY KEY,   -- one link per TG user = single-firm
            tenant_id        INTEGER NOT NULL,
            agent_id         INTEGER NOT NULL,
            role             TEXT NOT NULL,
            status           TEXT DEFAULT 'active',
            linked_at        TEXT,
            revoked_at       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tg_links_tenant ON tg_links(tenant_id);

        CREATE TABLE IF NOT EXISTS tg_invites (
            code       TEXT PRIMARY KEY,
            tenant_id  INTEGER NOT NULL,
            role       TEXT DEFAULT 'member',
            created_by INTEGER,
            expires_at TEXT,
            used_by    INTEGER,
            used_at    TEXT,
            created_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tg_invites_tenant ON tg_invites(tenant_id);

        CREATE TABLE IF NOT EXISTS tg_context (
            telegram_user_id INTEGER PRIMARY KEY,
            tenant_id        INTEGER,
            last_intent      TEXT DEFAULT '',
            pending          TEXT DEFAULT '',
            updated_at       TEXT
        );
        """)
        await conn.commit()


def _now() -> str:
    return datetime.now().isoformat()


# ── Connect / disconnect (admin) ─────────────────────────────────────────────
async def connect_bot(tenant_id: int, token: str, created_by: Optional[int]) -> dict:
    """Validate a pasted BotFather token, store it encrypted, register the webhook
    with a per-bot secret, and send the admin a self-test message. Idempotent per
    firm (re-connecting replaces the stored bot)."""
    token = (token or "").strip()
    if not token or ":" not in token:
        return {"ok": False, "error": "That doesn't look like a valid bot token. Copy it from BotFather."}

    ident = await verify_token(token)
    if not ident.get("ok"):
        return {"ok": False, "error": "Telegram rejected this token. Check you copied the whole token from BotFather."}

    bot_id = ident["bot_id"]

    # Guard: a bot already linked to a DIFFERENT firm can't be reused.
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT tenant_id FROM tg_firm_bots WHERE bot_id=?", (bot_id,))).fetchone()
        if row and int(row["tenant_id"]) != int(tenant_id):
            return {"ok": False, "error": "This bot is already connected to another firm. Create a fresh bot in BotFather."}

    webhook_secret = secrets.token_hex(24)
    token_enc = encrypt_token(token)
    hook_url = f"{SARATHI_BASE_URL}/api/tg/hook/{bot_id}"

    # Register webhook with the per-bot secret token (Telegram will echo it back
    # in the X-Telegram-Bot-Api-Secret-Token header on every update).
    res = await _call("setWebhook", {
        "url": hook_url,
        "secret_token": webhook_secret,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    }, token=token)
    if not res.get("ok"):
        return {"ok": False, "error": "Could not register the bot webhook. Please try again."}

    now = _now()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO tg_firm_bots (bot_id, tenant_id, bot_token_enc, bot_username,
                webhook_secret, status, last_error, created_by, created_at, updated_at)
            VALUES (?,?,?,?,?, 'active', '', ?, ?, ?)
            ON CONFLICT(bot_id) DO UPDATE SET
                tenant_id=excluded.tenant_id, bot_token_enc=excluded.bot_token_enc,
                bot_username=excluded.bot_username, webhook_secret=excluded.webhook_secret,
                status='active', last_error='', updated_at=excluded.updated_at
        """, (bot_id, tenant_id, token_enc, ident.get("username", ""),
              webhook_secret, created_by, now, now))
        await conn.commit()

    logger.info("🤖 tgcrm connect: tenant %s → bot @%s (id %s)",
                tenant_id, ident.get("username", ""), bot_id)

    # Connect-proof self-test: message the admin from their own bot if they've
    # already linked their Telegram; otherwise the connection is still valid and
    # they'll get greeted when they open the bot.
    await _notify_owner_connected(tenant_id, token, ident.get("username", ""))

    # One-time deep link the owner taps to bind their own Telegram to the firm.
    dl = await owner_deeplink(tenant_id, created_by)
    return {"ok": True, "bot_username": ident.get("username", ""), "bot_id": bot_id,
            "owner_link": dl.get("link", "")}


async def _notify_owner_connected(tenant_id: int, token: str, username: str) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT telegram_user_id FROM tg_links "
                "WHERE tenant_id=? AND role IN ('owner','admin') AND status='active' "
                "ORDER BY linked_at DESC LIMIT 1", (tenant_id,))).fetchone()
        if row and row["telegram_user_id"]:
            await send_message(token, row["telegram_user_id"],
                               "✅ Your Sarathi CRM bot is connected and live. "
                               "Your team can now be invited to run the CRM from here.")
    except Exception as e:
        logger.info("tgcrm connect self-test skipped: %s", str(e)[:120])


async def disconnect_bot(tenant_id: int) -> dict:
    """Remove the webhook and mark the firm's bot revoked. Links are frozen too."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT bot_id, bot_token_enc FROM tg_firm_bots "
            "WHERE tenant_id=? AND status='active'", (tenant_id,))).fetchone()
    if not row:
        return {"ok": True, "already": True}
    try:
        token = decrypt_token(row["bot_token_enc"])
        await _call("deleteWebhook", {"drop_pending_updates": False}, token=token)
    except Exception as e:
        logger.warning("tgcrm disconnect deleteWebhook failed: %s", str(e)[:120])
    now = _now()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE tg_firm_bots SET status='revoked', updated_at=? "
                           "WHERE tenant_id=?", (now, tenant_id))
        await conn.execute("UPDATE tg_links SET status='revoked', revoked_at=? "
                           "WHERE tenant_id=? AND status='active'", (now, tenant_id))
        await conn.commit()
    logger.info("🤖 tgcrm disconnect: tenant %s bot revoked", tenant_id)
    return {"ok": True}


async def get_bot_status(tenant_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT bot_id, bot_username, status, last_error, created_at "
            "FROM tg_firm_bots WHERE tenant_id=? ORDER BY updated_at DESC LIMIT 1",
            (tenant_id,))).fetchone()
        members = 0
        if row:
            m = await (await conn.execute(
                "SELECT COUNT(*) c FROM tg_links WHERE tenant_id=? AND status='active'",
                (tenant_id,))).fetchone()
            members = m["c"] if m else 0
    if not row or row["status"] != "active":
        return {"connected": False, "enabled": is_enabled(tenant_id)}
    return {"connected": True, "enabled": is_enabled(tenant_id),
            "bot_username": row["bot_username"],
            "status": row["status"], "linked_members": members,
            "connected_at": row["created_at"]}


# ── Webhook resolution + dispatch (P0 skeleton) ──────────────────────────────
async def _bot_by_id(bot_id: str) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT * FROM tg_firm_bots WHERE bot_id=? AND status='active'",
            (bot_id,))).fetchone()
        return dict(row) if row else None


async def _active_link(telegram_user_id: int) -> Optional[dict]:
    """Return the caller's ACTIVE firm link, re-checking the agent is still active
    (single-firm: at most one row)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT l.*, a.is_active AS agent_active FROM tg_links l "
            "LEFT JOIN agents a ON a.agent_id = l.agent_id "
            "WHERE l.telegram_user_id=? AND l.status='active'",
            (telegram_user_id,))).fetchone()
    if not row:
        return None
    if row["agent_active"] is not None and int(row["agent_active"]) != 1:
        return None  # deactivated agent → treated as unlinked
    return dict(row)


async def _tenant_firm(tenant_id: int) -> str:
    try:
        t = await db.get_tenant(tenant_id)
        return (t or {}).get("firm_name", "") or "your firm"
    except Exception:
        return "your firm"


async def create_invite(tenant_id: int, role: str = "member",
                        created_by: Optional[int] = None, hours: int = 72) -> str:
    code = secrets.token_urlsafe(6)[:10]
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO tg_invites (code, tenant_id, role, created_by, expires_at, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (code, tenant_id, role, created_by,
             (datetime.now() + timedelta(hours=hours)).isoformat(), _now()))
        await conn.commit()
    return code


async def invite_link(tenant_id: int, role: str = "member",
                      created_by: Optional[int] = None, hours: int = 72) -> dict:
    """Build a one-time t.me deep link that binds the tapper to the firm with `role`."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT bot_username FROM tg_firm_bots WHERE tenant_id=? AND status='active'",
            (tenant_id,))).fetchone()
    if not r or not r["bot_username"]:
        return {"ok": False}
    code = await create_invite(tenant_id, role, created_by, hours=hours)
    return {"ok": True, "code": code, "role": role,
            "link": f"https://t.me/{r['bot_username']}?start={code}"}


async def owner_deeplink(tenant_id: int, created_by: Optional[int] = None) -> dict:
    """One-time deep link the owner taps to bind their own Telegram to the firm."""
    return await invite_link(tenant_id, "owner", created_by, hours=168)


async def revoke_agent_links(agent_id: int) -> int:
    """Sever a member's Telegram binding (offboarding). Frees their single-firm slot
    so they can later join another firm. Returns rows revoked."""
    if not agent_id:
        return 0
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE tg_links SET status='revoked', revoked_at=? "
            "WHERE agent_id=? AND status='active'", (_now(), agent_id))
        await conn.commit()
        return cur.rowcount or 0


async def _redeem_invite(code: str, tg_uid: int, tg_name: str, bot_tenant: int) -> dict:
    """Validate + consume an invite and bind the Telegram user to the firm.
    Enforces single-firm (a TG user active in another firm is refused)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        inv = await (await conn.execute(
            "SELECT * FROM tg_invites WHERE code=?", (code,))).fetchone()
        if not inv:
            return {"ok": False, "error": "invalid"}
        if inv["used_by"]:
            return {"ok": False, "error": "used"}
        if inv["expires_at"] and inv["expires_at"] < _now():
            return {"ok": False, "error": "expired"}
        if int(inv["tenant_id"]) != int(bot_tenant):
            return {"ok": False, "error": "wrong_bot"}
        # Single-firm guarantee
        ex = await (await conn.execute(
            "SELECT tenant_id FROM tg_links WHERE telegram_user_id=? AND status='active'",
            (tg_uid,))).fetchone()
        if ex and int(ex["tenant_id"]) != int(bot_tenant):
            return {"ok": False, "error": "other_firm"}
        role = inv["role"] or "member"
        agent_id = None
        if role in ("owner", "admin"):
            a = await (await conn.execute(
                "SELECT agent_id FROM agents WHERE tenant_id=? AND role IN ('owner','admin') "
                "AND is_active=1 ORDER BY agent_id LIMIT 1", (bot_tenant,))).fetchone()
            agent_id = a["agent_id"] if a else None
        else:
            cnt = await (await conn.execute(
                "SELECT COUNT(*) c FROM agents WHERE tenant_id=? AND is_active=1",
                (bot_tenant,))).fetchone()
            t = await db.get_tenant(bot_tenant)
            plan = (t or {}).get("plan", "trial")
            mx = db.PLAN_FEATURES.get(plan, db.PLAN_FEATURES["trial"]).get("max_agents", 1)
            if cnt and cnt["c"] >= mx:
                return {"ok": False, "error": "seats_full"}
            cur = await conn.execute(
                "INSERT INTO agents (tenant_id, telegram_id, name, phone, email, role, is_active) "
                "VALUES (?,?,?,?,?, 'agent', 1)",
                (bot_tenant, str(tg_uid), tg_name, "", ""))
            agent_id = cur.lastrowid
        await conn.execute(
            "INSERT INTO tg_links (telegram_user_id, tenant_id, agent_id, role, status, linked_at) "
            "VALUES (?,?,?,?, 'active', ?) "
            "ON CONFLICT(telegram_user_id) DO UPDATE SET tenant_id=excluded.tenant_id, "
            "agent_id=excluded.agent_id, role=excluded.role, status='active', "
            "linked_at=excluded.linked_at, revoked_at=NULL",
            (tg_uid, bot_tenant, agent_id, role, _now()))
        await conn.execute("UPDATE tg_invites SET used_by=?, used_at=? WHERE code=?",
                           (tg_uid, _now(), code))
        await conn.commit()
    firm = await _tenant_firm(bot_tenant)
    logger.info("🔗 tgcrm link: tg %s → tenant %s as %s", tg_uid, bot_tenant, role)
    return {"ok": True, "role": role, "firm": firm}


async def handle_update(bot_id: str, secret_header: str, update: dict) -> dict:
    """Entry point for POST /api/tg/hook/{bot_id}. Verifies the per-bot secret,
    resolves firm + actor, and dispatches. P0: secure pipeline + minimal replies.
    Always returns {'ok': True} so Telegram doesn't retry-storm."""
    bot = await _bot_by_id(bot_id)
    if not bot:
        return {"ok": True}  # unknown/removed bot — silently ignore
    if not is_enabled(int(bot["tenant_id"])):
        return {"ok": True}  # feature off for this firm
    # Anti-spoof: constant-time compare of the Telegram secret header.
    if not secret_header or not secrets.compare_digest(secret_header, bot["webhook_secret"] or ""):
        logger.warning("tgcrm webhook secret mismatch for bot %s", bot_id)
        return {"ok": True}

    try:
        token = decrypt_token(bot["bot_token_enc"])
    except Exception:
        return {"ok": True}

    msg = update.get("message") or update.get("callback_query", {}).get("message") or {}
    from_user = (update.get("message", {}) or update.get("callback_query", {})).get("from", {})
    tg_uid = from_user.get("id")
    chat_id = msg.get("chat", {}).get("id") or tg_uid
    if not tg_uid or not chat_id:
        return {"ok": True}

    text = (update.get("message", {}) or {}).get("text", "") or ""

    tenant_id = int(bot["tenant_id"])

    # /start [invite_code] → onboarding.
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else ""
        link = await _active_link(tg_uid)
        if link and int(link["tenant_id"]) == tenant_id:
            firm = await _tenant_firm(tenant_id)
            await send_message(token, chat_id,
                               f"👋 You're already connected to <b>{firm}</b> as {link['role']}. "
                               f"Your voice-first CRM menu is coming as we roll out features.")
            return {"ok": True}
        if code:
            nm = (from_user.get("first_name", "") + " " + from_user.get("last_name", "")).strip() or "Member"
            res = await _redeem_invite(code, tg_uid, nm, tenant_id)
            if res.get("ok"):
                firm = res.get("firm", "your firm"); role = res.get("role", "member")
                if role in ("owner", "admin"):
                    await send_message(token, chat_id,
                                       f"✅ Welcome! You're connected as <b>{role}</b> of <b>{firm}</b>. "
                                       f"Your voice-first CRM is ready — full features rolling out now.")
                else:
                    await send_message(token, chat_id,
                                       f"✅ Welcome to <b>{firm}</b>'s CRM! You can manage your assigned "
                                       f"leads here by voice note. More coming soon.")
            elif res.get("error") == "other_firm":
                await send_message(token, chat_id,
                                   "You're already part of another firm on Sarathi. Ask them to remove you "
                                   "first — your data stays secure — then you can join a new firm.")
            elif res.get("error") == "seats_full":
                await send_message(token, chat_id,
                                   "Your firm's plan has no free team seats right now. Please ask your admin to upgrade.")
            else:
                await send_message(token, chat_id,
                                   "This invite link is invalid or has expired. Please ask your firm admin for a new one.")
            return {"ok": True}
        await send_message(token, chat_id,
                           "This bot runs a Sarathi-AI CRM. Ask your firm admin for an invite link to join.")
        return {"ok": True}

    # Any other message: only ACTIVE, LINKED members of THIS firm get a response;
    # everyone else gets a neutral message (no info leakage to strangers).
    link = await _active_link(tg_uid)
    if link and int(link["tenant_id"]) == tenant_id:
        await send_message(token, chat_id, "✅ Received. Your CRM actions will appear here soon.")
    else:
        await send_message(token, chat_id,
                           "You're not linked to this CRM. Please ask your firm admin for an invite link.")
    return {"ok": True}
