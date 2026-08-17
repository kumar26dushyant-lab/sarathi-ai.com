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

        CREATE TABLE IF NOT EXISTS tg_digest_prefs (
            telegram_user_id INTEGER PRIMARY KEY,
            tenant_id        INTEGER NOT NULL,
            enabled          INTEGER DEFAULT 1,
            hour_ist         INTEGER DEFAULT 9,
            last_sent_date   TEXT DEFAULT '',
            enabled_by       INTEGER,          -- admin agent_id who enabled it (self or for a teammate)
            created_at       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tg_digest_due ON tg_digest_prefs(enabled, hour_ist);
        """)
        # Migration: "paused draft" slot for context-switching nudges (existing rows).
        try:
            await conn.execute("ALTER TABLE tg_context ADD COLUMN prev_pending TEXT")
        except Exception:
            pass
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


# ── P2: menu + read flows ────────────────────────────────────────────────────
def _menu_kb(role: str) -> list:
    if role in ("owner", "admin"):
        return [
            [{"text": "📊 Today", "callback_data": "today"}],
            [{"text": "📋 Leads", "callback_data": "leads"}],
            [{"text": "🔔 Follow-ups due", "callback_data": "followups"}],
            [{"text": "🔄 Renewals due", "callback_data": "renewals"}],
            [{"text": "🤖 Ask AI", "callback_data": "ask"}],
            [{"text": "📅 Daily summary", "callback_data": "digest"}],
            [{"text": "❓ Help", "callback_data": "help"}],
        ]
    return [
        [{"text": "📋 My Leads", "callback_data": "leads"}],
        [{"text": "🔔 Follow-ups due", "callback_data": "followups"}],
        [{"text": "🔄 Renewals due", "callback_data": "renewals"}],
        [{"text": "🤖 Ask AI", "callback_data": "ask"}],
        [{"text": "❓ Help", "callback_data": "help"}],
    ]


async def _firm_renewals(tenant_id: int, days: int = 60, limit: int = 15) -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT p.*, l.name AS client_name FROM policies p "
            "JOIN agents a ON p.agent_id=a.agent_id JOIN leads l ON p.lead_id=l.lead_id "
            "WHERE a.tenant_id=? AND p.status='active' AND p.renewal_date IS NOT NULL "
            "AND date(p.renewal_date) BETWEEN date('now','+5 hours','+30 minutes') "
            "AND date('now','+5 hours','+30 minutes', ? || ' days') "
            "ORDER BY p.renewal_date ASC LIMIT ?",
            (tenant_id, str(days), limit))).fetchall()
        return [dict(r) for r in rows]


async def _renewals_view(token, chat_id, link) -> None:
    role = link["role"]; tid = int(link["tenant_id"]); aid = link.get("agent_id")
    if role in ("owner", "admin"):
        rows = await _firm_renewals(tid, 60, 15)
    else:
        rows = (await db.get_upcoming_renewals(aid, 60))[:15] if aid else []
    if not rows:
        await send_message(token, chat_id, "No renewals due in the next 60 days 🎉",
                           [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
        return
    lines = []
    for r in rows:
        d = (r.get("renewal_date") or "")[:10]
        nm = r.get("client_name", "?")
        ins = r.get("insurer") or r.get("plan_name") or ""
        lines.append(f"• <b>{nm}</b> — {d}{(' · ' + ins) if ins else ''}")
    await send_message(token, chat_id,
                       f"🔄 <b>Renewals due (next 60 days)</b> — {len(rows)}:\n" + "\n".join(lines),
                       [[{"text": "⬅️ Menu", "callback_data": "menu"}]])


async def _firm_stats(tenant_id: int) -> dict:
    """Aggregate the firm's day at a glance (IST-aware)."""
    IST = "'+5 hours','+30 minutes'"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async def _c(sql):
            r = await (await conn.execute(sql, (tenant_id,))).fetchone()
            return r["c"] if r else 0
        new_leads = await _c(
            "SELECT COUNT(*) c FROM leads l JOIN agents a ON l.agent_id=a.agent_id "
            f"WHERE a.tenant_id=? AND date(l.created_at)=date('now',{IST})")
        active = await _c(
            "SELECT COUNT(*) c FROM leads l JOIN agents a ON l.agent_id=a.agent_id "
            "WHERE a.tenant_id=? AND l.stage NOT IN ('closed_won','closed_lost')")
        followups = await _c(
            "SELECT COUNT(*) c FROM interactions i JOIN leads l ON i.lead_id=l.lead_id "
            "JOIN agents a ON l.agent_id=a.agent_id WHERE a.tenant_id=? "
            f"AND i.follow_up_date IS NOT NULL AND date(i.follow_up_date)<=date('now',{IST}) "
            "AND (i.follow_up_status IS NULL OR i.follow_up_status!='done')")
        renewals = await _c(
            "SELECT COUNT(*) c FROM policies p JOIN agents a ON p.agent_id=a.agent_id "
            "WHERE a.tenant_id=? AND p.renewal_date IS NOT NULL "
            f"AND date(p.renewal_date) BETWEEN date('now',{IST}) AND date('now',{IST},'+30 days')")
    return {"new_leads": new_leads, "active": active,
            "followups": followups, "renewals": renewals}


async def _today_view(token, chat_id, link) -> None:
    tid = int(link["tenant_id"])
    firm = await _tenant_firm(tid)
    s = await _firm_stats(tid)
    txt = (f"📊 <b>{firm} — Today</b>\n\n"
           f"🆕 New leads today: <b>{s['new_leads']}</b>\n"
           f"📋 Active leads: <b>{s['active']}</b>\n"
           f"🔔 Follow-ups due: <b>{s['followups']}</b>\n"
           f"🔄 Renewals (next 30 days): <b>{s['renewals']}</b>")
    await send_message(token, chat_id, txt, [[{"text": "⬅️ Menu", "callback_data": "menu"}]])


def _help_text(role: str) -> str:
    if role in ("owner", "admin"):
        return ("<b>Sarathi CRM — quick help</b>\n"
                "• 📋 Leads — your firm's leads; tap one for details\n"
                "• 🔔 Follow-ups due — what needs action\n"
                "• ➕ Add team members from your web dashboard\n"
                "🎤 Voice commands (log calls, set follow-ups) are rolling out next.")
    return ("<b>Sarathi CRM — quick help</b>\n"
            "• 📋 My Leads — your assigned leads; tap one for details\n"
            "• 🔔 Follow-ups due — what needs action\n"
            "🎤 Voice commands are rolling out next.")


async def _send_menu(token, chat_id, link) -> None:
    firm = await _tenant_firm(int(link["tenant_id"]))
    await send_message(token, chat_id,
                       f"🙏 <b>{firm}</b> — what would you like to do?",
                       _menu_kb(link["role"]))


async def _firm_leads(tenant_id: int, limit: int = 8) -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT l.* FROM leads l JOIN agents a ON l.agent_id=a.agent_id "
            "WHERE a.tenant_id=? ORDER BY l.updated_at DESC LIMIT ?",
            (tenant_id, limit))).fetchall()
        return [dict(r) for r in rows]


async def _leads_view(token, chat_id, link) -> None:
    role = link["role"]; tid = int(link["tenant_id"]); aid = link.get("agent_id")
    if role in ("owner", "admin"):
        rows = await _firm_leads(tid, 8)
    else:
        rows = (await db.get_leads_by_agent(aid))[:8] if aid else []
    if not rows:
        await send_message(token, chat_id,
                           "No leads yet. Add leads from your web dashboard and they'll appear here.",
                           [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
        return
    kb = [[{"text": f"👤 {(r.get('name') or '—')[:28]} · {r.get('stage','')}",
            "callback_data": f"lead:{r['lead_id']}"}] for r in rows]
    kb.append([{"text": "⬅️ Menu", "callback_data": "menu"}])
    await send_message(token, chat_id, f"📋 Showing {len(rows)} lead(s) — tap for details:", kb)


async def _lead_detail(token, chat_id, link, lead_id: int) -> None:
    lead = await db.get_lead(lead_id, int(link["tenant_id"]))
    if not lead:
        await send_message(token, chat_id, "Lead not found.",
                           [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
        return
    if link["role"] not in ("owner", "admin") and lead.get("agent_id") != link.get("agent_id"):
        await send_message(token, chat_id, "You can only view your assigned leads.",
                           [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
        return
    txt = (f"👤 <b>{lead.get('name','—')}</b>\n"
           f"📞 {lead.get('phone') or '—'}\n"
           f"📊 Stage: {lead.get('stage') or '—'}\n"
           f"🩺 Need: {lead.get('need_type') or '—'}\n"
           f"🏙 {lead.get('city') or '—'}\n"
           f"📝 {lead.get('notes') or '—'}")
    kb = [[{"text": "⬅️ Back to leads", "callback_data": "leads"}],
          [{"text": "⬅️ Menu", "callback_data": "menu"}]]
    await send_message(token, chat_id, txt, kb)


async def _followups_view(token, chat_id, link) -> None:
    aid = link.get("agent_id")
    rows = await db.get_pending_followups(aid) if aid else []
    if not rows:
        await send_message(token, chat_id, "No pending follow-ups 🎉",
                           [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
        return
    lines = []
    for r in rows[:10]:
        d = (r.get("follow_up_date") or "")[:10]
        lines.append(f"• <b>{r.get('lead_name','?')}</b> — {d} {(r.get('summary') or '')}".rstrip())
    await send_message(token, chat_id, "🔔 <b>Pending follow-ups</b>:\n" + "\n".join(lines),
                       [[{"text": "⬅️ Menu", "callback_data": "menu"}]])


# ── Daily digest ─────────────────────────────────────────────────────────────
async def get_digest_pref(tg_uid: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT * FROM tg_digest_prefs WHERE telegram_user_id=?", (tg_uid,))).fetchone()
        return dict(r) if r else None


async def set_digest_pref(tg_uid: int, tenant_id: int, enabled: bool,
                          hour_ist: int = 9, enabled_by: Optional[int] = None) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO tg_digest_prefs (telegram_user_id, tenant_id, enabled, hour_ist, enabled_by, created_at) "
            "VALUES (?,?,?,?,?,?) ON CONFLICT(telegram_user_id) DO UPDATE SET "
            "tenant_id=excluded.tenant_id, enabled=excluded.enabled, hour_ist=excluded.hour_ist, "
            "enabled_by=excluded.enabled_by",
            (tg_uid, tenant_id, 1 if enabled else 0, hour_ist, enabled_by, _now()))
        await conn.commit()


async def compose_digest(tenant_id: int) -> str:
    firm = await _tenant_firm(tenant_id)
    s = await _firm_stats(tenant_id)
    IST = "'+5 hours','+30 minutes'"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        pol = await (await conn.execute(
            "SELECT COUNT(*) c FROM policies p JOIN agents a ON p.agent_id=a.agent_id "
            f"WHERE a.tenant_id=? AND date(p.created_at)=date('now',{IST})", (tenant_id,))).fetchone()
    new_pol = pol["c"] if pol else 0
    return (f"📅 <b>{firm} — Daily Summary</b>\n"
            f"<i>{datetime.now().strftime('%d %b %Y')}</i>\n\n"
            f"🆕 New leads today: <b>{s['new_leads']}</b>\n"
            f"📋 Active leads: <b>{s['active']}</b>\n"
            f"🔔 Follow-ups due: <b>{s['followups']}</b>\n"
            f"🔄 Renewals (next 30 days): <b>{s['renewals']}</b>\n"
            f"📄 New policies today: <b>{new_pol}</b>\n\n"
            f"Have a productive day! 🙏")


async def run_digests() -> int:
    """Worker loop entry — send due daily digests (IST hour match, once/day). Returns count sent."""
    ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
    hour = ist_now.hour
    today = ist_now.strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        prefs = await (await conn.execute(
            "SELECT * FROM tg_digest_prefs WHERE enabled=1 AND hour_ist=? AND last_sent_date!=?",
            (hour, today))).fetchall()
    sent = 0
    for p in prefs:
        tid = int(p["tenant_id"]); tg_uid = int(p["telegram_user_id"])
        if not is_enabled(tid):
            continue
        link = await _active_link(tg_uid)
        if not (link and int(link["tenant_id"]) == tid):
            continue
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            b = await (await conn.execute(
                "SELECT bot_token_enc FROM tg_firm_bots WHERE tenant_id=? AND status='active'",
                (tid,))).fetchone()
        if not b:
            continue
        try:
            token = decrypt_token(b["bot_token_enc"])
            await send_message(token, tg_uid, await compose_digest(tid))
            sent += 1
        except Exception as e:
            logger.warning("digest send failed tenant %s: %s", tid, str(e)[:120])
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("UPDATE tg_digest_prefs SET last_sent_date=? WHERE telegram_user_id=?",
                               (today, tg_uid))
            await conn.commit()
    if sent:
        logger.info("📅 tgcrm digests sent: %d", sent)
    return sent


async def _digest_view(token, chat_id, tg_uid, link) -> None:
    pref = await get_digest_pref(tg_uid)
    on = bool(pref and pref.get("enabled"))
    hr = (pref or {}).get("hour_ist", 9)
    status = f"🟢 ON — every day around {hr}:00 IST" if on else "⚪ OFF"
    txt = (f"📅 <b>Daily Summary</b>\nStatus: {status}\n\n"
           f"A once-a-day snapshot of your firm's progress — new leads, follow-ups, "
           f"renewals and new policies.")
    kb = []
    if on:
        kb.append([{"text": "Turn OFF", "callback_data": "digest_off"}])
    else:
        kb.append([{"text": "Turn ON (9 AM)", "callback_data": "digest_on"}])
    kb.append([{"text": "📤 Send me one now", "callback_data": "digest_now"}])
    kb.append([{"text": "⬅️ Menu", "callback_data": "menu"}])
    await send_message(token, chat_id, txt, kb)


# ── P3: voice + text WRITE flows (log note / set follow-up) ──────────────────
async def _download_file(token: str, file_id: str) -> Optional[bytes]:
    res = await _call("getFile", {"file_id": file_id}, token=token)
    fp = ((res.get("result") or {}).get("file_path")) if res.get("ok") else None
    if not fp:
        return None
    url = f"https://api.telegram.org/file/bot{token}/{fp}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.get(url)
            if r.status_code == 200:
                return r.content
    except Exception as e:
        logger.info("tgcrm file download failed: %s", e)
    return None


async def _transcribe(audio: bytes, mime: str) -> Optional[dict]:
    """Gemini transcribe + clarity/safety assessment → {status, transcript, language}."""
    import os as _os, base64 as _b64, json as _json
    key = _os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    prompt = (
        "You are the voice front-end of a CRM app. Listen and reply with ONLY JSON: "
        '{"status":"clear|unclear|noisy|silent|abusive|nonsense","transcript":"...","language":"hi|en"}. '
        "Put EXACT spoken words in transcript; keep names, numbers, amounts, dates verbatim; never invent words.")
    model = _os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = {"contents": [{"parts": [
        {"text": prompt},
        {"inline_data": {"mime_type": mime or "audio/ogg", "data": _b64.b64encode(audio).decode()}},
    ]}], "generationConfig": {"response_mime_type": "application/json", "temperature": 0}}
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(url, json=payload)
            data = r.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
        raw = (parts[0].get("text") or "").strip()
        if not raw:
            if (data.get("promptFeedback") or {}).get("blockReason"):
                return {"status": "abusive", "transcript": "", "language": "en"}
            return None
        out = _json.loads(raw)
        if out.get("status") not in ("clear", "unclear", "noisy", "silent", "abusive", "nonsense"):
            out["status"] = "unclear"
        return out
    except Exception as e:
        logger.info("tgcrm transcription failed: %s", e)
        return None


async def _parse_intent(text: str) -> dict:
    """Turn a note into a CRM action (STRICT JSON)."""
    import os as _os, json as _json
    key = _os.getenv("GEMINI_API_KEY", "").strip()
    if not key or not (text or "").strip():
        return {"action": "none"}
    today = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    prompt = (
        "Convert an insurance advisor's short note/voice message into a CRM action as STRICT JSON.\n"
        f"Today (IST) is {today}. Shape:\n"
        '{"action":"log_note|set_followup|move_stage|create_lead|ask|none","lead_name":"","summary":"",'
        '"followup_date":"YYYY-MM-DD","followup_time":"HH:MM","stage":"","phone":"","need_type":""}\n'
        "- 'set_followup' = schedule a future call/meeting/reminder for a lead (has a date).\n"
        "- 'log_note' = record something that happened (a call/update) with no future date.\n"
        "- 'move_stage' = change a lead's pipeline stage. 'stage' MUST be one of: "
        "prospect, contacted, proposal_sent, negotiation, closed_won, closed_lost "
        "(map 'won'->closed_won, 'lost'->closed_lost, 'quoted'/'proposal'->proposal_sent).\n"
        "- 'create_lead' = add a NEW lead/customer. phone = digits only if spoken; "
        "need_type = product if said (health/life/term/motor/etc).\n"
        "- 'ask' = a QUESTION about their CRM (leads, pipeline, follow-ups, renewals, "
        "customers, counts, 'what's pending', 'who did I add') to be answered from data.\n"
        "- 'none' = greeting or small talk, not an action or a data question.\n"
        "- lead_name = the customer name mentioned. summary = concise note.\n"
        "- Resolve relative dates (today/tomorrow/next monday) to YYYY-MM-DD. Empty strings if absent.\n"
        "Output ONLY the JSON.\n\n" f"MESSAGE: {text}")
    model = _os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(url, json={"contents": [{"parts": [{"text": prompt}]}],
                                        "generationConfig": {"response_mime_type": "application/json", "temperature": 0}})
            data = r.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
        out = _json.loads((parts[0].get("text") or "").strip() or "{}")
        if out.get("action") not in ("log_note", "set_followup", "move_stage", "create_lead", "ask", "none"):
            out["action"] = "none"
        return out
    except Exception as e:
        logger.info("tgcrm intent parse failed: %s", e)
        return {"action": "none"}


_ACTIONABLE = {"log_note", "set_followup", "move_stage", "create_lead"}


async def _set_pending(tg_uid: int, tenant_id: int, payload: Optional[dict]) -> None:
    import json as _json
    async with aiosqlite.connect(DB_PATH) as conn:
        if payload is None:
            # Save/cancel → clear the current draft AND any paused draft.
            await conn.execute(
                "INSERT INTO tg_context (telegram_user_id, tenant_id, pending, prev_pending, updated_at) "
                "VALUES (?,?, '', '', ?) ON CONFLICT(telegram_user_id) DO UPDATE SET "
                "pending='', prev_pending='', updated_at=excluded.updated_at",
                (tg_uid, tenant_id, _now()))
        else:
            await conn.execute(
                "INSERT INTO tg_context (telegram_user_id, tenant_id, pending, updated_at) "
                "VALUES (?,?,?,?) ON CONFLICT(telegram_user_id) DO UPDATE SET "
                "tenant_id=excluded.tenant_id, pending=excluded.pending, updated_at=excluded.updated_at",
                (tg_uid, tenant_id, _json.dumps(payload), _now()))
        await conn.commit()


async def _stash_current_as_prev(tg_uid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE tg_context SET prev_pending=pending WHERE telegram_user_id=?", (tg_uid,))
        await conn.commit()


async def _get_prev(tg_uid: int) -> Optional[dict]:
    import json as _json
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT prev_pending FROM tg_context WHERE telegram_user_id=?", (tg_uid,))).fetchone()
    if not r or not r["prev_pending"]:
        return None
    try:
        return _json.loads(r["prev_pending"])
    except Exception:
        return None


async def _clear_prev(tg_uid: int) -> None:
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE tg_context SET prev_pending='' WHERE telegram_user_id=?", (tg_uid,))
        await conn.commit()


def _describe_pending(p: dict) -> str:
    a = (p or {}).get("action"); nm = (p or {}).get("lead_name", "")
    if a == "create_lead":
        return f"add lead {nm}"
    if a == "set_followup":
        return f"follow-up for {nm}"
    if a == "move_stage":
        return f"move {nm} to {(p.get('stage') or '').replace('_',' ')}"
    if a == "log_note":
        return f"note for {nm}"
    return "your draft"


async def _render_confirm(token, chat_id, p: dict) -> None:
    a = p.get("action")
    if a == "create_lead":
        card = f"➕ <b>New lead</b>\n👤 {p.get('lead_name','')}\n📞 {p.get('phone') or '—'}\n🩺 {p.get('need','health')}"
    elif a == "set_followup":
        when = ((p.get('fud') or '') + ((' ' + p.get('fut')) if p.get('fut') else '')) or "the given date"
        card = f"📇 <b>{p.get('lead_name','')}</b>\n🔔 Follow-up: <b>{when}</b>\n📝 {p.get('summary','')}"
    elif a == "move_stage":
        card = f"📇 <b>{p.get('lead_name','')}</b>\n📊 Move stage to: <b>{(p.get('stage') or '').replace('_',' ')}</b>"
    else:
        card = f"📇 <b>{p.get('lead_name','')}</b>\n📝 Note: {p.get('summary','')}"
    await send_message(token, chat_id, "Please confirm:\n\n" + card, _SAVE_KB)


async def _nudge_prev(token, chat_id, tg_uid) -> None:
    prev = await _get_prev(tg_uid)
    if not prev:
        return
    await send_message(token, chat_id,
                       f"↩️ You have a paused draft: <b>{_describe_pending(prev)}</b>.",
                       [[{"text": "↩️ Resume it", "callback_data": "resume"},
                         {"text": "🗑 Discard", "callback_data": "discard_prev"}]])


async def _get_pending(tg_uid: int) -> Optional[dict]:
    import json as _json
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT pending FROM tg_context WHERE telegram_user_id=?", (tg_uid,))).fetchone()
    if not r or not r["pending"]:
        return None
    try:
        return _json.loads(r["pending"])
    except Exception:
        return None


async def _find_lead(link, name: str) -> list:
    name = (name or "").strip()
    if not name:
        return []
    if link["role"] in ("owner", "admin"):
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            rows = await (await conn.execute(
                "SELECT l.* FROM leads l JOIN agents a ON l.agent_id=a.agent_id "
                "WHERE a.tenant_id=? AND l.name LIKE ? ORDER BY l.updated_at DESC LIMIT 5",
                (int(link["tenant_id"]), f"%{name}%"))).fetchall()
            return [dict(r) for r in rows]
    aid = link.get("agent_id")
    return (await db.search_leads(aid, name))[:5] if aid else []


_STAGES = {"prospect", "contacted", "proposal_sent", "negotiation", "closed_won", "closed_lost"}
_STAGE_ALIASES = {
    "won": "closed_won", "closed won": "closed_won", "proposal": "proposal_sent",
    "proposal sent": "proposal_sent", "quoted": "proposal_sent", "quote": "proposal_sent",
    "lost": "closed_lost", "closed lost": "closed_lost", "negotiating": "negotiation",
    "called": "contacted", "interested": "contacted", "new": "prospect",
}
_SAVE_KB = [[{"text": "✅ Save", "callback_data": "cfm:save"},
             {"text": "❌ Cancel", "callback_data": "cfm:cancel"}]]


def _canon_stage(s: str) -> str:
    s = (s or "").strip().lower().replace("-", " ")
    if s in _STAGES:
        return s
    if s.replace(" ", "_") in _STAGES:
        return s.replace(" ", "_")
    return _STAGE_ALIASES.get(s, "")


async def _finalize_action(token, chat_id, tg_uid, link, intent, lead) -> None:
    """Build the confirm card for an existing-lead action and store the pending write."""
    act = intent.get("action")
    tid = int(link["tenant_id"])
    summary = (intent.get("summary") or "").strip()
    base = {"lead_id": lead["lead_id"], "lead_name": lead.get("name", ""),
            "lead_agent": lead.get("agent_id")}
    if act == "move_stage":
        stage = _canon_stage(intent.get("stage", ""))
        if stage not in _STAGES:
            await send_message(token, chat_id,
                               "Which stage? Say e.g. contacted, proposal, negotiation, won, or lost.",
                               _menu_kb(link["role"]))
            return
        await _set_pending(tg_uid, tid, {**base, "action": "move_stage", "stage": stage})
        card = f"📇 <b>{lead.get('name','')}</b>\n📊 Move stage to: <b>{stage.replace('_',' ')}</b>"
    elif act == "set_followup":
        fud = (intent.get("followup_date") or "").strip()
        fut = (intent.get("followup_time") or "").strip()
        await _set_pending(tg_uid, tid, {**base, "action": "set_followup",
                                         "summary": summary or "Follow-up", "fud": fud, "fut": fut})
        when = (fud + ((" " + fut) if fut else "")) or "the given date"
        card = f"📇 <b>{lead.get('name','')}</b>\n🔔 Follow-up: <b>{when}</b>\n📝 {summary or 'Follow-up'}"
    else:  # log_note
        await _set_pending(tg_uid, tid, {**base, "action": "log_note", "summary": summary or "Note"})
        card = f"📇 <b>{lead.get('name','')}</b>\n📝 Note: {summary or 'Note'}"
    await send_message(token, chat_id, "Please confirm:\n\n" + card, _SAVE_KB)


async def _ai_context(link) -> dict:
    """Compact, role-scoped snapshot of the CRM for grounded Q&A (read-only)."""
    role = link["role"]; tid = int(link["tenant_id"]); aid = link.get("agent_id")
    ctx: dict = {}
    if role in ("owner", "admin"):
        ctx["stats"] = await _firm_stats(tid)
        ctx["recent_leads"] = [{"name": l.get("name"), "stage": l.get("stage"),
                                "need": l.get("need_type")} for l in await _firm_leads(tid, 15)]
        ctx["renewals"] = [{"name": r.get("client_name"), "date": (r.get("renewal_date") or "")[:10]}
                           for r in await _firm_renewals(tid, 60, 15)]
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            fu = await (await conn.execute(
                "SELECT l.name lead_name, i.follow_up_date, i.summary FROM interactions i "
                "JOIN leads l ON i.lead_id=l.lead_id JOIN agents a ON l.agent_id=a.agent_id "
                "WHERE a.tenant_id=? AND i.follow_up_date IS NOT NULL "
                "AND (i.follow_up_status IS NULL OR i.follow_up_status!='done') "
                "ORDER BY i.follow_up_date ASC LIMIT 20", (tid,))).fetchall()
        ctx["followups"] = [{"name": r["lead_name"], "date": (r["follow_up_date"] or "")[:10],
                             "note": r["summary"]} for r in fu]
    else:
        leads = (await db.get_leads_by_agent(aid))[:15] if aid else []
        ctx["recent_leads"] = [{"name": l.get("name"), "stage": l.get("stage"),
                                "need": l.get("need_type")} for l in leads]
        rens = (await db.get_upcoming_renewals(aid, 60))[:15] if aid else []
        ctx["renewals"] = [{"name": r.get("client_name"), "date": (r.get("renewal_date") or "")[:10]}
                           for r in rens]
        fus = (await db.get_pending_followups(aid))[:20] if aid else []
        ctx["followups"] = [{"name": r.get("lead_name"), "date": (r.get("follow_up_date") or "")[:10],
                             "note": r.get("summary")} for r in fus]
    return ctx


async def _ask_ai(link, question: str) -> str:
    import os as _os, json as _json
    key = _os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return "The AI assistant isn't configured yet."
    ctx = await _ai_context(link)
    today = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    prompt = (
        f"You are a helpful CRM assistant for an insurance advisor. Today (IST) is {today}. "
        "Answer the user's question ONLY from the DATA below (their own CRM). Be concise "
        "(1-4 short lines), simple language. If the answer isn't in the data, say you don't have "
        "that info. Never invent leads, numbers, or dates.\n\n"
        f"DATA (JSON): {_json.dumps(ctx, ensure_ascii=False)[:6000]}\n\nQUESTION: {question}")
    model = _os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(url, json={"contents": [{"parts": [{"text": prompt}]}],
                                        "generationConfig": {"temperature": 0.2}})
            data = r.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
        return (parts[0].get("text") or "").strip() or "I couldn't find an answer to that."
    except Exception as e:
        logger.info("tgcrm ask_ai failed: %s", e)
        return "Sorry, I couldn't process that right now."


async def _process_command(token, chat_id, tg_uid, link, text) -> None:
    """Parse a note (typed or transcribed) → (pick lead if needed) → confirm card → save."""
    intent = await _parse_intent(text)
    act = intent.get("action", "none")
    if act == "none":
        await _send_menu(token, chat_id, link)
        return
    if act == "ask":
        await send_message(token, chat_id, "🤔 Let me check…")
        ans = await _ask_ai(link, text)
        await send_message(token, chat_id, ans, [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
        return
    intent["summary"] = (intent.get("summary") or text).strip()

    # Context-switch: a new command supersedes any unconfirmed draft, which we pause
    # (stash) and nudge so the user can Resume or Discard it.
    had = await _get_pending(tg_uid)
    had_actionable = bool(had and had.get("action") in _ACTIONABLE)

    if act == "create_lead":
        if link["role"] not in ("owner", "admin"):
            await send_message(token, chat_id, "Only your admin can add new leads.",
                               _menu_kb(link["role"]))
            return
        name = (intent.get("lead_name") or "").strip()
        if not name:
            await send_message(token, chat_id, "Please include the person's name to add them.",
                               _menu_kb(link["role"]))
            return
        phone = "".join(ch for ch in (intent.get("phone") or "") if ch.isdigit())
        need = (intent.get("need_type") or "").strip() or "health"
        if had_actionable:
            await _stash_current_as_prev(tg_uid)
        await _set_pending(tg_uid, int(link["tenant_id"]),
                           {"action": "create_lead", "lead_name": name, "phone": phone, "need": need})
        card = f"➕ <b>New lead</b>\n👤 {name}\n📞 {phone or '—'}\n🩺 {need}"
        await send_message(token, chat_id, "Please confirm:\n\n" + card, _SAVE_KB)
        if had_actionable:
            await _nudge_prev(token, chat_id, tg_uid)
        return

    leads = await _find_lead(link, intent.get("lead_name", ""))
    if not leads:
        await send_message(token, chat_id,
                           f"I couldn't find a lead named “{intent.get('lead_name','')}”. "
                           f"Add them on the web dashboard, or try the exact name.",
                           _menu_kb(link["role"]))
        return
    if len(leads) > 1:
        if had_actionable:
            await _stash_current_as_prev(tg_uid)
        await _set_pending(tg_uid, int(link["tenant_id"]), {"action": "pick", "intent": intent})
        kb = [[{"text": f"👤 {(l.get('name') or '')[:24]} · {l.get('phone') or l.get('stage','')}",
                "callback_data": f"pick:{l['lead_id']}"}] for l in leads]
        kb.append([{"text": "❌ Cancel", "callback_data": "cfm:cancel"}])
        await send_message(token, chat_id, f"Found {len(leads)} matching leads — which one?", kb)
        return
    if had_actionable:
        await _stash_current_as_prev(tg_uid)
    await _finalize_action(token, chat_id, tg_uid, link, intent, leads[0])
    if had_actionable:
        await _nudge_prev(token, chat_id, tg_uid)


async def _handle_callback(token, tenant_id: int, cb: dict) -> dict:
    cid = cb.get("id")
    data = cb.get("data", "") or ""
    chat_id = (cb.get("message", {}) or {}).get("chat", {}).get("id")
    tg_uid = (cb.get("from", {}) or {}).get("id")
    if cid:
        await _call("answerCallbackQuery", {"callback_query_id": cid}, token=token)
    link = await _active_link(tg_uid) if tg_uid else None
    if not (link and int(link["tenant_id"]) == tenant_id):
        if chat_id:
            await send_message(token, chat_id, "You're no longer linked to this CRM.")
        return {"ok": True}
    if not chat_id:
        return {"ok": True}
    if data == "menu":
        await _send_menu(token, chat_id, link)
    elif data == "today":
        if link["role"] in ("owner", "admin"):
            await _today_view(token, chat_id, link)
        else:
            await _send_menu(token, chat_id, link)
    elif data == "leads":
        await _leads_view(token, chat_id, link)
    elif data == "followups":
        await _followups_view(token, chat_id, link)
    elif data == "renewals":
        await _renewals_view(token, chat_id, link)
    elif data == "ask":
        await send_message(token, chat_id,
                           "🤖 Ask me anything about your leads, follow-ups, renewals or customers — "
                           "just type or send a voice note.\n\nE.g. <i>“what's pending this week?”</i>",
                           [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
    elif data in ("digest", "digest_on", "digest_off", "digest_now"):
        if link["role"] not in ("owner", "admin"):
            await _send_menu(token, chat_id, link)
        elif data == "digest_on":
            await set_digest_pref(tg_uid, tenant_id, True, 9, link.get("agent_id"))
            await _digest_view(token, chat_id, tg_uid, link)
        elif data == "digest_off":
            _cur = await get_digest_pref(tg_uid)
            await set_digest_pref(tg_uid, tenant_id, False,
                                  (_cur or {}).get("hour_ist", 9), link.get("agent_id"))
            await _digest_view(token, chat_id, tg_uid, link)
        elif data == "digest_now":
            await send_message(token, chat_id, await compose_digest(tenant_id))
        else:
            await _digest_view(token, chat_id, tg_uid, link)
    elif data == "help":
        await send_message(token, chat_id, _help_text(link["role"]), _menu_kb(link["role"]))
    elif data == "cfm:save":
        p = await _get_pending(tg_uid)
        _menu_only = [[{"text": "⬅️ Menu", "callback_data": "menu"}]]
        if not p or p.get("action") == "pick":
            await send_message(token, chat_id, "Nothing to save.", _menu_only)
        elif p.get("action") == "create_lead":
            if link["role"] not in ("owner", "admin"):
                await send_message(token, chat_id, "Only your admin can add new leads.")
            else:
                try:
                    async with aiosqlite.connect(DB_PATH) as conn:
                        await conn.execute(
                            "INSERT INTO leads (agent_id, name, phone, need_type, stage, source) "
                            "VALUES (?,?,?,?, 'prospect', 'telegram')",
                            (link.get("agent_id"), p.get("lead_name", ""),
                             p.get("phone", ""), p.get("need", "health")))
                        await conn.commit()
                    await _set_pending(tg_uid, tenant_id, None)
                    await send_message(token, chat_id, f"✅ Lead <b>{p.get('lead_name','')}</b> added.", _menu_only)
                except Exception as e:
                    logger.warning("tgcrm create_lead failed: %s", e)
                    await send_message(token, chat_id, "⚠️ Couldn't add the lead — please try again.")
        elif link["role"] not in ("owner", "admin") and p.get("lead_agent") != link.get("agent_id"):
            await send_message(token, chat_id, "You can only update your assigned leads.")
        elif p.get("action") == "move_stage":
            try:
                async with aiosqlite.connect(DB_PATH) as conn:
                    await conn.execute(
                        "UPDATE leads SET stage=?, updated_at=datetime('now') WHERE lead_id=? "
                        "AND agent_id IN (SELECT agent_id FROM agents WHERE tenant_id=?)",
                        (p.get("stage"), int(p["lead_id"]), tenant_id))
                    await conn.commit()
                await _set_pending(tg_uid, tenant_id, None)
                await send_message(token, chat_id,
                                   f"✅ <b>{p.get('lead_name','')}</b> moved to "
                                   f"<b>{(p.get('stage') or '').replace('_',' ')}</b>.", _menu_only)
            except Exception as e:
                logger.warning("tgcrm move_stage failed: %s", e)
                await send_message(token, chat_id, "⚠️ Couldn't update the stage — please try again.")
        else:  # log_note / set_followup
            itype = "followup" if p.get("action") == "set_followup" else "note"
            try:
                await db.log_interaction(
                    int(p["lead_id"]), int(p.get("lead_agent") or link.get("agent_id") or 0),
                    itype, "telegram", p.get("summary", ""),
                    p.get("fud") or None, p.get("fut") or None, link.get("agent_id"))
                await _set_pending(tg_uid, tenant_id, None)
                done = "🔔 Follow-up set" if itype == "followup" else "📝 Note saved"
                await send_message(token, chat_id, f"✅ {done} for <b>{p.get('lead_name','')}</b>.", _menu_only)
            except Exception as e:
                logger.warning("tgcrm save failed: %s", e)
                await send_message(token, chat_id, "⚠️ Couldn't save — please try again.")
    elif data.startswith("pick:"):
        p = await _get_pending(tg_uid)
        if p and p.get("action") == "pick":
            try:
                lead_id = int(data.split(":", 1)[1])
            except (ValueError, IndexError):
                lead_id = 0
            lead = await db.get_lead(lead_id, tenant_id) if lead_id else None
            if lead and (link["role"] in ("owner", "admin") or lead.get("agent_id") == link.get("agent_id")):
                await _finalize_action(token, chat_id, tg_uid, link, p.get("intent", {}), lead)
            else:
                await send_message(token, chat_id, "Lead not found.",
                                   [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
        else:
            await send_message(token, chat_id, "This selection expired — please try again.",
                               [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
    elif data == "cfm:cancel":
        await _set_pending(tg_uid, tenant_id, None)
        await send_message(token, chat_id, "Cancelled.",
                           [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
    elif data == "resume":
        prev = await _get_prev(tg_uid)
        if prev:
            await _set_pending(tg_uid, tenant_id, prev)
            await _clear_prev(tg_uid)
            await _render_confirm(token, chat_id, prev)
        else:
            await send_message(token, chat_id, "No paused draft to resume.",
                               [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
    elif data == "discard_prev":
        await _clear_prev(tg_uid)
        await send_message(token, chat_id, "Paused draft discarded.",
                           [[{"text": "⬅️ Menu", "callback_data": "menu"}]])
    elif data.startswith("lead:"):
        try:
            await _lead_detail(token, chat_id, link, int(data.split(":", 1)[1]))
        except (ValueError, IndexError):
            pass
    return {"ok": True}


async def handle_update(bot_id: str, secret_header: str, update: dict) -> dict:
    """Entry point for POST /api/tg/hook/{bot_id}. Verifies the per-bot secret,
    resolves firm + actor, and dispatches (P2: menu + read flows).
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
    tenant_id = int(bot["tenant_id"])

    # Button tap
    cb = update.get("callback_query")
    if cb:
        return await _handle_callback(token, tenant_id, cb)

    msg = update.get("message") or {}
    from_user = msg.get("from", {}) or {}
    tg_uid = from_user.get("id")
    chat_id = (msg.get("chat", {}) or {}).get("id") or tg_uid
    if not tg_uid or not chat_id:
        return {"ok": True}
    text = msg.get("text", "") or ""
    is_voice = bool(msg.get("voice") or msg.get("audio"))

    # /start [invite_code] → onboarding (then show the menu).
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        code = parts[1].strip() if len(parts) > 1 else ""
        link = await _active_link(tg_uid)
        if link and int(link["tenant_id"]) == tenant_id:
            await _send_menu(token, chat_id, link)
            return {"ok": True}
        if code:
            nm = (from_user.get("first_name", "") + " " + from_user.get("last_name", "")).strip() or "Member"
            res = await _redeem_invite(code, tg_uid, nm, tenant_id)
            if res.get("ok"):
                firm = res.get("firm", "your firm"); role = res.get("role", "member")
                greet = (f"✅ Welcome! You're connected as <b>{role}</b> of <b>{firm}</b>."
                         if role in ("owner", "admin")
                         else f"✅ Welcome to <b>{firm}</b>'s CRM! You can manage your assigned leads here.")
                await send_message(token, chat_id, greet)
                newlink = await _active_link(tg_uid)
                if newlink:
                    await _send_menu(token, chat_id, newlink)
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

    # Non-/start messages — only ACTIVE, LINKED members of THIS firm get a response.
    link = await _active_link(tg_uid)
    if not (link and int(link["tenant_id"]) == tenant_id):
        await send_message(token, chat_id,
                           "You're not linked to this CRM. Please ask your firm admin for an invite link.")
        return {"ok": True}
    if is_voice:
        v = msg.get("voice") or msg.get("audio") or {}
        if int(v.get("duration") or 0) > 150:
            await send_message(token, chat_id, "⏱️ Please keep voice notes under ~2 minutes and try again.",
                               _menu_kb(link["role"]))
            return {"ok": True}
        await send_message(token, chat_id, "🎧 Listening…")
        audio = await _download_file(token, v.get("file_id"))
        tr = await _transcribe(audio, v.get("mime_type") or "audio/ogg") if audio else None
        if not tr or tr.get("status") != "clear" or not (tr.get("transcript") or "").strip():
            st = (tr or {}).get("status", "unclear")
            emap = {"silent": "🤫 I didn't hear any speech.", "noisy": "🔊 Too much background noise.",
                    "unclear": "🙉 I couldn't catch that clearly.", "abusive": "🙏 Let's keep it professional.",
                    "nonsense": "🤔 I couldn't make out a request."}
            await send_message(token, chat_id,
                               emap.get(st, "⚠️ Couldn't process that audio.") + " Please try again or type it.",
                               _menu_kb(link["role"]))
            return {"ok": True}
        await send_message(token, chat_id, f"🗣️ I heard: “{tr['transcript']}”")
        await _process_command(token, chat_id, tg_uid, link, tr["transcript"])
        return {"ok": True}
    # Typed message → try a CRM command; falls back to the menu if it's not one.
    await _process_command(token, chat_id, tg_uid, link, text)
    return {"ok": True}
