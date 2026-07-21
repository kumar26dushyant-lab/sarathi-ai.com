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
        "bot_id": await _get_setting("telegram_bot_id", ""),
        "token_hint": (f"…{token[-6:]}" if token else ""),
        "webhook_set_at": await _get_setting("telegram_webhook_set_at", ""),
    }


def webhook_secret(token: str) -> str:
    """Unguessable, deterministic path segment derived from the bot token."""
    return hashlib.sha256(("nidaan-tg:" + token).encode()).hexdigest()[:32]


# ── raw API ──────────────────────────────────────────────────────────────────
async def _call(method: str, payload: Optional[dict] = None,
                token: Optional[str] = None, timeout: Optional[float] = None) -> dict:
    tok = token if token is not None else await get_bot_token()
    if not tok:
        return {"ok": False, "error": "no_token"}
    url = API_BASE.format(token=tok, method=method)
    try:
        async with httpx.AsyncClient(timeout=timeout or _TIMEOUT) as client:
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
    """getMe — validates a pasted token and returns the bot's identity. `bot_id` is
    stable for the life of a bot even if its token is regenerated, so it's what we
    use to tell "same bot, new token" (links survive) from "different bot" (links are
    dead, because a chat_id only means anything to the bot that issued it)."""
    res = await _call("getMe", token=token)
    if res.get("ok"):
        r = res.get("result") or {}
        return {"ok": True, "username": r.get("username", ""),
                "name": r.get("first_name", ""), "bot_id": str(r.get("id") or "")}
    return {"ok": False, "error": res.get("description") or res.get("error") or "invalid_token"}


async def delete_webhook() -> dict:
    """Remove any registered webhook (required before getUpdates polling can run)."""
    return await _call("deleteWebhook", {"drop_pending_updates": False})


async def clear_all_links() -> int:
    """Drop every staff link. Used when the bot IDENTITY changes — those chat_ids can
    never work again, so keeping them would just fail silently forever."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nidaan_staff SET telegram_chat_id=NULL, telegram_username=NULL, "
            "telegram_linked_at=NULL WHERE telegram_chat_id IS NOT NULL")
        await conn.commit()
        return cur.rowcount or 0


async def list_unlinked_staff() -> list[dict]:
    """Active staff who still need to connect (used to nudge them)."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT staff_id, name, COALESCE(NULLIF(notify_email,''), email) AS email "
            "FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
            "AND (telegram_chat_id IS NULL OR telegram_chat_id='')")).fetchall()
        return [dict(r) for r in rows]


# ── LONG-POLLING (Cloudflare-independent) ────────────────────────────────────
# We PULL updates from Telegram (outbound from our server) instead of Telegram
# pushing to us (inbound, which Cloudflare's bot protection blocks with a 520).
# Runs as a single worker-only loop, so each update is processed exactly once.
_poll_offset = 0


async def run_polling_loop() -> None:
    """Continuously pull + process updates. Self-heals across token changes,
    pause/resume and network blips."""
    global _poll_offset
    import asyncio as _asyncio
    last_token = None
    logger.info("📡 Telegram polling loop starting")
    while True:
        try:
            token = await get_bot_token()
            if not token or (await _get_setting("telegram_enabled", "1")) != "1":
                await _asyncio.sleep(8)
                last_token = None if not token else last_token
                continue
            if token != last_token:
                # New/changed bot → getUpdates and webhook are mutually exclusive,
                # so drop any webhook first, and start from a clean offset.
                await _call("deleteWebhook", {"drop_pending_updates": False}, token=token)
                await _set_setting("telegram_webhook_set_at", "")
                await _set_setting("telegram_poll_active", "1")
                last_token = token
                _poll_offset = 0
                logger.info("📡 Telegram polling active for @%s",
                            await _get_setting("telegram_bot_username", ""))
            res = await _call("getUpdates",
                              {"offset": _poll_offset, "timeout": 25,
                               "allowed_updates": ["message", "callback_query"]},
                              token=token, timeout=35)
            if not res.get("ok"):
                # 409 = a webhook is still set somewhere; clear it and retry.
                if "409" in str(res.get("error", "")) or "conflict" in str(res.get("description", "")).lower():
                    await _call("deleteWebhook", {"drop_pending_updates": False}, token=token)
                await _asyncio.sleep(3)
                continue
            for u in res.get("result", []):
                _poll_offset = u.get("update_id", _poll_offset) + 1
                try:
                    await handle_update(u)
                except Exception as e:
                    logger.warning("Telegram update processing error: %s", e)
        except Exception as e:
            logger.warning("Telegram polling loop error: %s", e)
            await _asyncio.sleep(5)


async def disconnect_bot() -> None:
    """Remove the bot token (stops Telegram delivery) but KEEP staff links, so
    re-adding the SAME bot later restores everyone instantly."""
    try:
        await _call("deleteWebhook", {"drop_pending_updates": True})
    except Exception:
        pass
    await _set_setting("telegram_bot_token", "")
    await _set_setting("telegram_webhook_set_at", "")


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
                     "parse_mode": "Markdown", "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = await _call("sendMessage", payload)
    if not res.get("ok"):
        # User-supplied content can break Markdown parsing — resend as plain text.
        payload.pop("parse_mode", None)
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


def _digits(s: str) -> str:
    import re as _re
    return _re.sub(r"\D", "", s or "")


async def _link_by_phone(phone: str, chat_id: str, username: str) -> Optional[dict]:
    """SECURE binding: link a Telegram chat to the staffer whose REGISTERED mobile
    matches the Telegram-verified phone number. Returns None if the number isn't a
    registered staff number — so only real staff can ever connect."""
    d10 = _digits(phone)[-10:]
    if len(d10) < 10:
        return None
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        staff = [dict(r) for r in await (await conn.execute(
            "SELECT staff_id, name, phone FROM nidaan_staff "
            "WHERE status='active' AND deleted_at IS NULL")).fetchall()]
        match = next((s for s in staff
                      if _digits(s.get("phone"))[-10:] == d10 and len(_digits(s.get("phone"))) >= 10), None)
        if not match:
            return None
        # Free this Telegram chat from any other staff first (one chat → one staffer),
        # then bind it to the verified owner (also replaces that staffer's old chat).
        await conn.execute(
            "UPDATE nidaan_staff SET telegram_chat_id=NULL, telegram_username=NULL, "
            "telegram_linked_at=NULL WHERE telegram_chat_id=?", (str(chat_id),))
        await conn.execute(
            "UPDATE nidaan_staff SET telegram_chat_id=?, telegram_username=?, "
            "telegram_linked_at=CURRENT_TIMESTAMP WHERE staff_id=?",
            (str(chat_id), username or "", match["staff_id"]))
        await conn.commit()
        return {"staff_id": match["staff_id"], "name": match["name"]}


async def _request_phone(chat_id, text: str) -> None:
    """Send a message with a Telegram 'share my phone number' button. The number
    Telegram returns is verified by Telegram and can't be spoofed or forwarded."""
    kb = {"keyboard": [[{"text": "📱 Share my phone number", "request_contact": True}]],
          "one_time_keyboard": True, "resize_keyboard": True}
    await _call("sendMessage", {"chat_id": str(chat_id), "text": text[:4000],
                                "parse_mode": "Markdown", "reply_markup": kb})


# ═════════════════════════════════════════════════════════════════════════════
#  THE OFFICE, IN TELEGRAM — role-aware button UI
#  Every action re-checks the staffer's role server-side from their chat_id; a
#  button is never trusted on its own. Roles and capabilities mirror the web app
#  exactly, so the portal, the PWA and the bot can never drift apart.
# ═════════════════════════════════════════════════════════════════════════════
ROLE_RANK = {"team_member": 0, "sub_super_admin": 1, "super_admin": 2}


async def _staff_by_chat(chat_id) -> Optional[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT staff_id, name, role, telegram_pending FROM nidaan_staff "
            "WHERE telegram_chat_id=? AND status='active' AND deleted_at IS NULL",
            (str(chat_id),))).fetchone()
        return dict(row) if row else None


def _can(staff: dict, need: str) -> bool:
    return ROLE_RANK.get((staff or {}).get("role", ""), -1) >= ROLE_RANK.get(need, 99)


async def _set_pending(staff_id: int, payload: Optional[dict]) -> None:
    import json as _json
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("UPDATE nidaan_staff SET telegram_pending=? WHERE staff_id=?",
                           (_json.dumps(payload) if payload else None, staff_id))
        await conn.commit()


def _kb(rows: list) -> list:
    """Filter out empty rows so role-gated menus never render blank buttons."""
    return [r for r in rows if r]


def _main_menu(staff: dict) -> tuple[str, list]:
    admin = _can(staff, "sub_super_admin")
    sa = _can(staff, "super_admin")
    text = (f"🏢 *NidaanPartner Ops*\n"
            f"Hi {staff.get('name','')} — {(staff.get('role') or '').replace('_',' ')}\n\n"
            f"Run your day right here. Pick anything below 👇")
    kb = _kb([
        [{"text": "📥 Pending with me", "callback_data": "t:mine"},
         {"text": "📤 Assigned by me", "callback_data": "t:byme"}],
        [{"text": "🏷️ I'm involved", "callback_data": "t:inv"},
         {"text": "🗄️ Archived", "callback_data": "t:arch"}],
        [{"text": "⏳ Approvals", "callback_data": "ap:list"}] if admin else None,
        [{"text": "🌴 Apply leave", "callback_data": "lv:new:leave"},
         {"text": "🏠 Apply WFH", "callback_data": "lv:new:wfh"}],
        [{"text": "🤖 Ask AI", "callback_data": "ai:ask"}],
        [{"text": "📣 Broadcast", "callback_data": "bc:new"}] if sa else None,
        [{"text": "❓ Help", "callback_data": "h:help"}],
    ])
    return text, kb


# ── task helpers ─────────────────────────────────────────────────────────────
_STATUS_ICON = {"open": "🔵", "in_progress": "🟡", "done": "✅", "cancelled": "⛔"}
_PRIO_ICON = {"low": "⚪", "normal": "🔵", "high": "🟠", "urgent": "🔴"}


async def _task_list(staff: dict, scope: str) -> tuple[str, list]:
    import biz_nidaan as nidaan
    titles = {"assigned_to_me": "📥 Pending with me", "created_by_me": "📤 Assigned by me",
              "involved": "🏷️ I'm involved", "archived": "🗄️ Archived"}
    if scope == "archived":
        rows = await nidaan.list_quick_tasks(
            status="archived", viewer_staff_id=(None if _can(staff, "sub_super_admin") else staff["staff_id"]),
            include_done=True, sort="updated", limit=10)
    else:
        rows = await nidaan.list_quick_tasks(
            scope=scope, scope_staff_id=staff["staff_id"], sort="smart", limit=10)
        rows = [r for r in rows if r.get("status") not in ("done", "cancelled")]
    head = titles.get(scope, "Tasks")
    if not rows:
        return (f"*{head}*\n\nNothing here right now ✓", _kb([[{"text": "⬅️ Menu", "callback_data": "m:home"}]]))
    lines = [f"*{head}* — {len(rows)} shown"]
    btns = []
    for r in rows:
        icon = _STATUS_ICON.get(r.get("status"), "•")
        pr = _PRIO_ICON.get((r.get("priority") or "normal"), "")
        cat = f" [{r['category_code']}]" if r.get("category_code") else ""
        lines.append(f"\n{icon} *#{r['quick_task_id']}*{cat} {r.get('title','')[:70]}")
        meta = []
        if r.get("assignee_name"):
            meta.append(f"👤 {r['assignee_name']}")
        if r.get("due_date"):
            meta.append(f"📅 {str(r['due_date'])[:10]}")
        if meta:
            lines.append("   " + " · ".join(meta))
        btns.append([{"text": f"{pr} #{r['quick_task_id']} {r.get('title','')[:28]}",
                      "callback_data": f"t:v:{r['quick_task_id']}"}])
    btns.append([{"text": "⬅️ Menu", "callback_data": "m:home"}])
    return ("\n".join(lines), _kb(btns))


async def _task_detail(staff: dict, qid: int) -> tuple[str, list]:
    import biz_nidaan as nidaan
    qt = await nidaan.get_quick_task(qid)
    if not qt:
        return ("Task not found.", _kb([[{"text": "⬅️ Menu", "callback_data": "m:home"}]]))
    # Same visibility rule as the web app.
    if not _can(staff, "sub_super_admin") and not await nidaan.is_task_participant(qid, staff["staff_id"]):
        return ("🔒 You don't have access to this task.",
                _kb([[{"text": "⬅️ Menu", "callback_data": "m:home"}]]))
    icon = _STATUS_ICON.get(qt.get("status"), "•")
    lines = [f"{icon} *Task #{qid}*", f"*{qt.get('title','')}*"]
    if qt.get("description"):
        lines.append(f"\n{qt['description'][:400]}")
    meta = [f"Status: {qt.get('status')}", f"Priority: {qt.get('priority')}"]
    if qt.get("category_code"):
        meta.append(f"Category: {qt['category_code']}")
    if qt.get("assignee_name"):
        meta.append(f"Assignee: {qt['assignee_name']}")
    if qt.get("creator_name"):
        meta.append(f"Created by: {qt['creator_name']}")
    if qt.get("due_date"):
        meta.append(f"Due: {str(qt['due_date'])[:10]}")
    if qt.get("complainant_name"):
        meta.append(f"Complainant: {qt['complainant_name']} {qt.get('complainant_phone') or ''}")
    lines.append("\n" + "\n".join(meta))
    try:
        notes = await nidaan.list_quick_task_notes(qid)
        if notes:
            lines.append("\n💬 *Latest comments*")
            for n in notes[-3:]:
                lines.append(f"• {n.get('staff_name','')}: {(n.get('note') or '')[:90]}")
    except Exception:
        pass
    is_assignee = qt.get("assigned_to_staff_id") == staff["staff_id"]
    can_move = is_assignee or _can(staff, "sub_super_admin")
    row1 = []
    if can_move and qt.get("status") == "open":
        row1.append({"text": "▶️ Start", "callback_data": f"t:s:{qid}:in_progress"})
    if can_move and qt.get("status") not in ("done", "cancelled"):
        row1.append({"text": "✅ Mark done", "callback_data": f"t:s:{qid}:done"})
    if can_move and qt.get("status") in ("done", "cancelled"):
        row1.append({"text": "↺ Reopen", "callback_data": f"t:s:{qid}:open"})
    kb = _kb([
        row1,
        [{"text": "💬 Add comment", "callback_data": f"t:c:{qid}"}],
        [{"text": "🔗 Open in portal", "url": f"{_base_url()}/admin?qt={qid}"}],
        [{"text": "⬅️ Menu", "callback_data": "m:home"}],
    ])
    return ("\n".join(lines), kb)


def _base_url() -> str:
    import os as _os
    return _os.getenv("NIDAAN_BASE_URL", "https://nidaanpartner.com")


async def _approvals_view(staff: dict) -> tuple[str, list]:
    import biz_nidaan as nidaan
    rows = await nidaan.list_quick_tasks(pending_approval=True, include_done=True, limit=10)
    # Only what THIS admin should decide: tasks naming them, or unassigned-approver ones.
    mine = [r for r in rows if (r.get("approver_staff_id") in (None, staff["staff_id"]))
            or _can(staff, "super_admin")]
    if not mine:
        return ("*⏳ Approvals*\n\nNothing awaiting your approval ✓",
                _kb([[{"text": "⬅️ Menu", "callback_data": "m:home"}]]))
    lines = ["*⏳ Awaiting your approval*"]
    btns = []
    for r in mine:
        qid = r["quick_task_id"]
        lines.append(f"\n• *#{qid}* {r.get('title','')[:70]}\n   by {r.get('creator_name','')}")
        btns.append([{"text": f"✅ Approve #{qid}", "callback_data": f"ap:{qid}:approved"},
                     {"text": f"❌ Reject #{qid}", "callback_data": f"ap:{qid}:rejected"}])
    btns.append([{"text": "⬅️ Menu", "callback_data": "m:home"}])
    return ("\n".join(lines), _kb(btns))


# ── Gemini brain (read-only, role-scoped) ────────────────────────────────────
async def _ask_gemini(staff: dict, question: str) -> str:
    """Answer a natural-language question using ONLY the tasks this staffer may see.
    Read-only by design: the model summarises context we hand it, it cannot act."""
    import os as _os
    import biz_nidaan as nidaan
    key = _os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return "The AI brain isn't configured yet (no GEMINI_API_KEY)."
    admin = _can(staff, "sub_super_admin")
    try:
        rows = await nidaan.list_quick_tasks(
            viewer_staff_id=(None if admin else staff["staff_id"]),
            include_done=True, sort="updated", limit=60)
    except Exception:
        rows = []
    ctx = []
    for r in rows:
        ctx.append(
            f"#{r['quick_task_id']} | {r.get('title','')} | status={r.get('status')} | "
            f"priority={r.get('priority')} | assignee={r.get('assignee_name') or '-'} | "
            f"creator={r.get('creator_name') or '-'} | due={str(r.get('due_date') or '-')[:10]} | "
            f"category={r.get('category_code') or '-'}")
    prompt = (
        "You are the NidaanPartner office assistant inside Telegram. Answer the staff "
        "member's question using ONLY the task records below. Be concise and practical "
        "(a few short lines, Telegram-friendly, no markdown tables). Refer to tasks as #id. "
        "If the answer isn't in the data, say so plainly and suggest what to check.\n\n"
        f"Staff member: {staff.get('name')} (role: {staff.get('role')})\n"
        f"Today: {__import__('datetime').date.today().isoformat()}\n\n"
        f"TASK RECORDS ({len(ctx)}):\n" + "\n".join(ctx) +
        f"\n\nQUESTION: {question}\n\nANSWER:")
    model = _os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            r = await client.post(url, json={"contents": [{"parts": [{"text": prompt}]}]})
            data = r.json()
        cand = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
        out = (cand[0].get("text") or "").strip()
        return out or "I couldn't form an answer for that — try rephrasing."
    except Exception as e:
        logger.warning("Gemini ask failed: %s", e)
        return "The AI brain is unreachable right now. Please try again in a moment."


# ── update routing ───────────────────────────────────────────────────────────
async def handle_update(update: dict) -> None:
    """Route one webhook update: /start linking, button presses, and typed replies."""
    try:
        if update.get("callback_query"):
            await _handle_callback(update["callback_query"])
            return
        msg = update.get("message") or {}
        chat_id = (msg.get("chat") or {}).get("id")
        text = (msg.get("text") or "").strip()
        username = (msg.get("from") or {}).get("username") or ""
        from_id = (msg.get("from") or {}).get("id")
        contact = msg.get("contact")
        if not chat_id:
            return

        # ── SECURE LINKING: verified phone number ────────────────────────────
        # A shared contact is how a staffer proves identity. We accept ONLY the
        # sender's OWN Telegram-verified number, and link ONLY if it matches a
        # registered staff mobile — so a leaked connect link is useless to anyone
        # whose Telegram number isn't already staff.
        if contact:
            if str(contact.get("user_id")) != str(from_id):
                await send_message(str(chat_id),
                    "⚠️ Please tap the *📱 Share my phone number* button to share YOUR OWN "
                    "number — a forwarded contact won't work.")
                return
            linked = await _link_by_phone(contact.get("phone_number"), str(chat_id), username)
            if linked:
                staff = await _staff_by_chat(chat_id)
                await _call("sendMessage", {"chat_id": str(chat_id),
                    "text": f"✅ Verified & connected, {linked['name']}!",
                    "reply_markup": {"remove_keyboard": True}})
                t, kb = _main_menu(staff or {"name": linked["name"], "role": "team_member"})
                await send_message(str(chat_id), t, kb)
                logger.info("🔐 Telegram linked staff_id=%s by verified phone", linked["staff_id"])
            else:
                await _call("sendMessage", {"chat_id": str(chat_id),
                    "text": ("🔒 *Not connected.*\n\nThis Telegram number is not registered for "
                             "any staff member. Ask your admin to check the mobile number on your "
                             "staff profile, then try again from the correct Telegram account."),
                    "parse_mode": "Markdown", "reply_markup": {"remove_keyboard": True}})
            return

        if not text:
            return

        if text.startswith("/start"):
            staff = await _staff_by_chat(chat_id)
            if staff:
                t, kb = _main_menu(staff)
                await send_message(str(chat_id), t, kb)
                return
            # Not linked yet → require a verified phone number to connect.
            await _request_phone(str(chat_id),
                "🔐 *Connect securely*\n\nTo receive your NidaanPartner notifications, tap the "
                "button below to share your phone number.\n\nIt must match the mobile number "
                "registered for you in the office system — Telegram verifies it, so nobody can "
                "connect using someone else's number.")
            return

        staff = await _staff_by_chat(chat_id)
        if not staff:
            await _request_phone(str(chat_id),
                "🔒 This Telegram isn't linked yet.\n\nTap the button below to connect with your "
                "registered mobile number.")
            return

        if text.lower() in ("/menu", "menu", "/home", "hi", "hello"):
            t, kb = _main_menu(staff)
            await send_message(str(chat_id), t, kb)
            return

        # A pending flow expecting typed input?
        import json as _json
        pending = {}
        try:
            pending = _json.loads(staff.get("telegram_pending") or "{}")
        except Exception:
            pending = {}
        act = pending.get("a")
        if act == "comment" and pending.get("qid"):
            await _do_comment(staff, int(pending["qid"]), text, chat_id)
            await _set_pending(staff["staff_id"], None)
            return
        if act == "ai":
            await _set_pending(staff["staff_id"], None)
            await send_message(str(chat_id), "🤖 Thinking…")
            ans = await _ask_gemini(staff, text)
            await send_message(str(chat_id), ans,
                               _kb([[{"text": "🤖 Ask again", "callback_data": "ai:ask"},
                                     {"text": "⬅️ Menu", "callback_data": "m:home"}]]))
            return
        if act == "broadcast" and _can(staff, "super_admin"):
            await _set_pending(staff["staff_id"], None)
            await _do_broadcast(staff, text, chat_id)
            return
        if act == "leave" and pending.get("kind"):
            await _set_pending(staff["staff_id"], None)
            await _do_leave(staff, pending["kind"], text, chat_id)
            return

        # Free text with no pending flow → treat as a question for the AI.
        await send_message(str(chat_id), "🤖 Thinking…")
        ans = await _ask_gemini(staff, text)
        await send_message(str(chat_id), ans,
                           _kb([[{"text": "⬅️ Menu", "callback_data": "m:home"}]]))
    except Exception as e:
        logger.warning("Telegram update handling failed: %s", e)


async def _handle_callback(cq: dict) -> None:
    data = (cq.get("data") or "").strip()
    msg = cq.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")
    cq_id = cq.get("id")

    async def ack(text: str = ""):
        await _call("answerCallbackQuery",
                    {"callback_query_id": cq_id, "text": text[:180]} if text
                    else {"callback_query_id": cq_id})

    staff = await _staff_by_chat(chat_id)
    if not staff:
        await ack("Not linked")
        return
    try:
        if data == "m:home":
            t, kb = _main_menu(staff); await _edit(chat_id, message_id, t, kb); await ack(); return

        if data.startswith("h:help"):
            # Generated from the shared capability registry — the bot's help, the web
            # guide and the audio narration always describe the same feature set.
            import biz_nidaan_capabilities as caps
            lang = "hi" if data.endswith(":hi") else "en"
            other = "en" if lang == "hi" else "hi"
            txt = caps.telegram_help_text(staff.get("role", "team_member"), lang)
            txt += ("\n\n" + ("_कभी भी सीधे सवाल टाइप कर सकते हैं। /menu से मेन्यू खोलें।_"
                              if lang == "hi" else
                              "_You can also just type a question any time. Send /menu for the menu._"))
            await _edit(chat_id, message_id, txt, _kb([
                [{"text": "🇮🇳 हिंदी में" if lang == "en" else "🇬🇧 In English",
                  "callback_data": f"h:help:{other}"}],
                [{"text": "🔊 Audio guide", "url": f"{_base_url()}/admin#guide"}],
                [{"text": "⬅️ Menu", "callback_data": "m:home"}],
            ])); await ack(); return

        if data.startswith("t:"):
            parts = data.split(":")
            kind = parts[1]
            if kind in ("mine", "byme", "inv", "arch"):
                scope = {"mine": "assigned_to_me", "byme": "created_by_me",
                         "inv": "involved", "arch": "archived"}[kind]
                t, kb = await _task_list(staff, scope)
                await _edit(chat_id, message_id, t, kb); await ack(); return
            if kind == "v":
                t, kb = await _task_detail(staff, int(parts[2]))
                await _edit(chat_id, message_id, t, kb); await ack(); return
            if kind == "s":
                qid, new_status = int(parts[2]), parts[3]
                ok = await _do_status(staff, qid, new_status)
                await ack("Updated ✓" if ok else "Not allowed")
                t, kb = await _task_detail(staff, qid)
                await _edit(chat_id, message_id, t, kb); return
            if kind == "c":
                qid = int(parts[2])
                await _set_pending(staff["staff_id"], {"a": "comment", "qid": qid})
                await send_message(str(chat_id),
                    f"💬 Type your comment for *task #{qid}* and send it.\n"
                    f"_Everyone involved will be notified._")
                await ack(); return

        if data.startswith("ap:"):
            if not _can(staff, "sub_super_admin"):
                await ack("Admins only"); return
            parts = data.split(":")
            if parts[1] == "list":
                t, kb = await _approvals_view(staff)
                await _edit(chat_id, message_id, t, kb); await ack(); return
            qid, decision = int(parts[1]), parts[2]
            ok = await _do_approval(staff, qid, decision)
            await ack("Done ✓" if ok else "Failed")
            t, kb = await _approvals_view(staff)
            await _edit(chat_id, message_id, t, kb); return

        if data == "ai:ask":
            await _set_pending(staff["staff_id"], {"a": "ai"})
            await send_message(str(chat_id),
                "🤖 *Ask me anything about your work*\n\n"
                "For example:\n"
                "• _what's pending with me?_\n"
                "• _which tasks are overdue?_\n"
                "• _status of task 55_\n\nType your question 👇")
            await ack(); return

        if data.startswith("lv:new:"):
            kind = data.split(":")[2]
            await _set_pending(staff["staff_id"], {"a": "leave", "kind": kind})
            label = "Work From Home" if kind == "wfh" else "Leave"
            await send_message(str(chat_id),
                f"{'🏠' if kind=='wfh' else '🌴'} *Apply for {label}*\n\n"
                f"Reply with the dates and reason, e.g.\n"
                f"`2026-07-25 to 2026-07-26 family function`\n"
                f"or `2026-07-25 personal work` for a single day.")
            await ack(); return

        if data == "bc:new":
            if not _can(staff, "super_admin"):
                await ack("Super admin only"); return
            await _set_pending(staff["staff_id"], {"a": "broadcast"})
            await send_message(str(chat_id),
                "📣 *Broadcast to all staff*\n\nType the message to send to everyone's bell.")
            await ack(); return

        await ack()
    except Exception as e:
        logger.warning("Telegram callback failed (%s): %s", data, e)
        try:
            await ack("Something went wrong")
        except Exception:
            pass


async def _edit(chat_id, message_id, text: str, buttons: Optional[list] = None) -> None:
    payload = {"chat_id": str(chat_id), "message_id": message_id, "text": text[:4000],
               "parse_mode": "Markdown", "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    res = await _call("editMessageText", payload)
    if not res.get("ok"):
        # Markdown can trip on user content — retry as plain text.
        payload.pop("parse_mode", None)
        await _call("editMessageText", payload)


# ── actions (each re-checks permission server-side) ──────────────────────────
async def _do_status(staff: dict, qid: int, new_status: str) -> bool:
    import biz_nidaan as nidaan
    import biz_nidaan_notifications as nnot
    qt = await nidaan.get_quick_task(qid)
    if not qt:
        return False
    is_assignee = qt.get("assigned_to_staff_id") == staff["staff_id"]
    if not (is_assignee or _can(staff, "sub_super_admin")):
        return False
    await nidaan.update_quick_task_status(qid, new_status, changed_by=staff["staff_id"])
    try:
        fresh = await nidaan.get_quick_task(qid)
        if fresh:
            await nnot.on_quick_task_status_changed(fresh, new_status, staff.get("name", ""),
                                                    by_id=staff["staff_id"])
    except Exception:
        pass
    return True


async def _do_comment(staff: dict, qid: int, text: str, chat_id) -> None:
    import biz_nidaan as nidaan
    import biz_nidaan_notifications as nnot
    if not await nidaan.is_task_participant(qid, staff["staff_id"]) and not _can(staff, "sub_super_admin"):
        await send_message(str(chat_id), "🔒 You don't have access to that task.")
        return
    await nidaan.add_quick_task_note(quick_task_id=qid, staff_id=staff["staff_id"], note=text)
    try:
        qt = await nidaan.get_quick_task(qid)
        if qt:
            await nnot.on_quick_task_comment(qt, staff["staff_id"], text)
    except Exception:
        pass
    await send_message(str(chat_id), f"✅ Comment added to task #{qid}. Everyone involved was notified.",
                       _kb([[{"text": f"📄 Open #{qid}", "callback_data": f"t:v:{qid}"},
                             {"text": "⬅️ Menu", "callback_data": "m:home"}]]))


async def _do_approval(staff: dict, qid: int, decision: str) -> bool:
    import biz_nidaan as nidaan
    import biz_nidaan_notifications as nnot
    if not _can(staff, "sub_super_admin"):
        return False
    try:
        await nidaan.set_quick_task_approval(qid, decision, changed_by=staff["staff_id"])
        qt = await nidaan.get_quick_task(qid)
        if qt:
            await nnot.on_quick_task_approval(qt, decision)
        return True
    except Exception as e:
        logger.warning("Telegram approval failed #%s: %s", qid, e)
        return False


async def _do_leave(staff: dict, kind: str, text: str, chat_id) -> None:
    """Parse a free-text leave/WFH request: dates + reason."""
    import re as _re
    import biz_nidaan as nidaan
    import biz_nidaan_notifications as nnot
    dates = _re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if not dates:
        await send_message(str(chat_id),
            "I couldn't find a date. Please use `YYYY-MM-DD`, e.g. `2026-07-25 personal work`.")
        return
    start = dates[0]
    end = dates[1] if len(dates) > 1 else dates[0]
    reason = _re.sub(r"\d{4}-\d{2}-\d{2}|to", " ", text).strip() or "-"
    if end < start:
        start, end = end, start
    lid = await nidaan.create_leave_request(
        staff_id=staff["staff_id"], start_date=start, end_date=end,
        reason=reason, request_kind=kind)
    try:
        lv = await nidaan.get_leave_request(lid)
        if lv:
            await nnot.on_leave_requested(lv)
    except Exception:
        pass
    label = "WFH" if kind == "wfh" else "Leave"
    await send_message(str(chat_id),
        f"✅ *{label} request sent*\n{start} → {end}\nReason: {reason}\n\nAdmins have been notified.",
        _kb([[{"text": "⬅️ Menu", "callback_data": "m:home"}]]))


async def _do_broadcast(staff: dict, text: str, chat_id) -> None:
    import biz_nidaan_notifications as nnot
    if not _can(staff, "super_admin"):
        await send_message(str(chat_id), "🔒 Super admin only.")
        return
    n = await nnot.record_broadcast(staff["staff_id"], staff.get("name", "Staff"), text)
    await send_message(str(chat_id), f"📣 Broadcast sent to {n} staff member(s).",
                       _kb([[{"text": "⬅️ Menu", "callback_data": "m:home"}]]))


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
