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
            ai_history       TEXT DEFAULT '',
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
        # Migration: rolling AI conversation memory (existing rows).
        try:
            await conn.execute("ALTER TABLE tg_context ADD COLUMN ai_history TEXT DEFAULT ''")
        except Exception:
            pass
        # Migration: per-user bot language (existing rows).
        try:
            await conn.execute("ALTER TABLE tg_links ADD COLUMN lang TEXT DEFAULT 'en'")
        except Exception:
            pass
        # Migration: per-user voice-reply preference — auto (speak when you spoke) | on | off.
        try:
            await conn.execute("ALTER TABLE tg_links ADD COLUMN voice_reply TEXT DEFAULT 'auto'")
        except Exception:
            pass
        await conn.commit()


def _now() -> str:
    return datetime.now().isoformat()


# ── i18n (EN/HI) ─────────────────────────────────────────────────────────────
STRINGS = {
    # buttons
    "b_today": {"en": "📊 Today", "hi": "📊 आज"},
    "b_leads": {"en": "📋 Leads", "hi": "📋 लीड्स"},
    "b_myleads": {"en": "📋 My Leads", "hi": "📋 मेरी लीड्स"},
    "b_followups": {"en": "🔔 Follow-ups due", "hi": "🔔 बकाया फ़ॉलो-अप"},
    "b_renewals": {"en": "🔄 Renewals due", "hi": "🔄 बकाया रिन्यूअल"},
    "b_ask": {"en": "🤖 Ask AI", "hi": "🤖 AI से पूछें"},
    "b_digest": {"en": "📅 Daily summary", "hi": "📅 दैनिक सारांश"},
    "b_support": {"en": "🎫 Support", "hi": "🎫 सहायता"},
    "b_help": {"en": "❓ Help", "hi": "❓ मदद"},
    "b_lang": {"en": "🌐 भाषा / Language", "hi": "🌐 भाषा / Language"},
    "b_voice": {"en": "🔊 Voice", "hi": "🔊 आवाज़"},
    "voice_menu": {"en": "🔊 <b>Voice replies</b>\nShould I speak my answers back as a voice note?\n\n• <b>Auto</b> — I speak when you send a voice note, else I text (recommended)\n• <b>Always</b> — I speak every reply\n• <b>Off</b> — text only",
                   "hi": "🔊 <b>आवाज़ में जवाब</b>\nक्या मैं अपने जवाब वॉइस नोट में बोलकर दूँ?\n\n• <b>ऑटो</b> — जब आप वॉइस नोट भेजें तब बोलूँ, वरना टेक्स्ट (अनुशंसित)\n• <b>हमेशा</b> — हर जवाब बोलूँ\n• <b>बंद</b> — सिर्फ़ टेक्स्ट"},
    "b_v_auto": {"en": "🎙️ Auto", "hi": "🎙️ ऑटो"},
    "b_v_on":   {"en": "🔊 Always", "hi": "🔊 हमेशा"},
    "b_v_off":  {"en": "🔇 Off", "hi": "🔇 बंद"},
    "voice_set": {"en": "✅ Voice replies: {mode}", "hi": "✅ आवाज़ में जवाब: {mode}"},
    "b_menu": {"en": "⬅️ Menu", "hi": "⬅️ मेन्यू"},
    "b_back": {"en": "⬅️ Back", "hi": "⬅️ वापस"},
    "b_back_leads": {"en": "⬅️ Back to leads", "hi": "⬅️ लीड्स पर वापस"},
    "b_save": {"en": "✅ Save", "hi": "✅ सेव करें"},
    "b_cancel": {"en": "❌ Cancel", "hi": "❌ रद्द करें"},
    "b_resume": {"en": "↩️ Resume it", "hi": "↩️ जारी रखें"},
    "b_discard": {"en": "🗑 Discard", "hi": "🗑 हटाएँ"},
    "b_team_digests": {"en": "👥 Team digests", "hi": "👥 टीम के सारांश"},
    "b_send_now": {"en": "📤 Send me one now", "hi": "📤 अभी एक भेजें"},
    "b_turn_off": {"en": "Turn OFF", "hi": "बंद करें"},
    "b_turn_on": {"en": "Turn ON (9 AM)", "hi": "चालू करें (सुबह 9 बजे)"},
    # menu + greetings
    "menu_hdr": {"en": "🙏 <b>{firm}</b> — what would you like to do?",
                 "hi": "🙏 <b>{firm}</b> — आप क्या करना चाहेंगे?"},
    "greet_owner": {"en": "✅ Welcome! You're connected as <b>{role}</b> of <b>{firm}</b>.",
                    "hi": "✅ स्वागत है! आप <b>{firm}</b> के <b>{role}</b> के रूप में जुड़ गए हैं।"},
    "greet_member": {"en": "✅ Welcome to <b>{firm}</b>'s CRM! You can manage your assigned leads here.",
                     "hi": "✅ <b>{firm}</b> के CRM में स्वागत है! आप यहाँ अपनी सौंपी गई लीड्स संभाल सकते हैं।"},
    "not_linked": {"en": "You're not linked to this CRM. Please ask your firm admin for an invite link.",
                   "hi": "आप इस CRM से जुड़े नहीं हैं। कृपया अपने एडमिन से इनवाइट लिंक माँगें।"},
    "ask_admin_invite": {"en": "This bot runs a Sarathi-AI CRM. Ask your firm admin for an invite link to join.",
                         "hi": "यह बॉट Sarathi-AI CRM चलाता है। जुड़ने के लिए अपने एडमिन से इनवाइट लिंक माँगें।"},
    "inv_other_firm": {"en": "You're already part of another firm on Sarathi. Ask them to remove you first — your data stays secure — then you can join a new firm.",
                       "hi": "आप पहले से किसी अन्य फर्म से जुड़े हैं। पहले उनसे हटवाएँ — आपका डेटा सुरक्षित रहता है — फिर नई फर्म से जुड़ सकते हैं।"},
    "inv_seats": {"en": "Your firm's plan has no free team seats right now. Please ask your admin to upgrade.",
                  "hi": "आपकी फर्म के प्लान में अभी टीम सीट खाली नहीं है। कृपया एडमिन से अपग्रेड कराएँ।"},
    "inv_bad": {"en": "This invite link is invalid or has expired. Please ask your firm admin for a new one.",
                "hi": "यह इनवाइट लिंक अमान्य या समाप्त हो चुका है। कृपया एडमिन से नया लिंक लें।"},
    # views
    "leads_show": {"en": "📋 Showing {n} lead(s) — tap for details:",
                   "hi": "📋 {n} लीड्स — विवरण के लिए टैप करें:"},
    "leads_none": {"en": "No leads yet. Add leads from your web dashboard and they'll appear here.",
                   "hi": "अभी कोई लीड नहीं। वेब डैशबोर्ड से लीड जोड़ें, वे यहाँ दिखेंगी।"},
    "only_assigned": {"en": "You can only view your assigned leads.",
                      "hi": "आप केवल अपनी सौंपी गई लीड्स देख सकते हैं।"},
    "lead_notfound": {"en": "Lead not found.", "hi": "लीड नहीं मिली।"},
    "fu_hdr": {"en": "🔔 <b>Pending follow-ups</b>:", "hi": "🔔 <b>बकाया फ़ॉलो-अप</b>:"},
    "fu_none": {"en": "No pending follow-ups 🎉", "hi": "कोई बकाया फ़ॉलो-अप नहीं 🎉"},
    "ren_hdr": {"en": "🔄 <b>Renewals due (next 60 days)</b> — {n}:",
                "hi": "🔄 <b>बकाया रिन्यूअल (अगले 60 दिन)</b> — {n}:"},
    "ren_none": {"en": "No renewals due in the next 60 days 🎉",
                 "hi": "अगले 60 दिनों में कोई रिन्यूअल नहीं 🎉"},
    "today": {"en": "📊 <b>{firm} — Today</b>\n\n🆕 New leads today: <b>{nl}</b>\n📋 Active leads: <b>{ac}</b>\n🔔 Follow-ups due: <b>{fu}</b>\n🔄 Renewals (next 30 days): <b>{rn}</b>",
              "hi": "📊 <b>{firm} — आज</b>\n\n🆕 आज नई लीड्स: <b>{nl}</b>\n📋 सक्रिय लीड्स: <b>{ac}</b>\n🔔 बकाया फ़ॉलो-अप: <b>{fu}</b>\n🔄 रिन्यूअल (अगले 30 दिन): <b>{rn}</b>"},
    # help
    "help_admin": {"en": "<b>Sarathi CRM — quick help</b>\n• 📋 Leads — your firm's leads; tap one for details\n• 🔔 Follow-ups due — what needs action\n• 🔄 Renewals due — policies renewing soon\n• 🤖 Ask AI — ask about your pipeline\n• 📅 Daily summary — a daily progress digest\n• 🎫 Support — raise a ticket\n\n🎤 Tip: send a voice note like “log a call with Ramesh, follow up tomorrow”.",
                   "hi": "<b>Sarathi CRM — त्वरित मदद</b>\n• 📋 लीड्स — आपकी फर्म की लीड्स; विवरण हेतु टैप करें\n• 🔔 बकाया फ़ॉलो-अप — जिन पर काम बाकी है\n• 🔄 बकाया रिन्यूअल — जल्द रिन्यू होने वाली पॉलिसी\n• 🤖 AI से पूछें — अपनी पाइपलाइन के बारे में पूछें\n• 📅 दैनिक सारांश — रोज़ की प्रगति\n• 🎫 सहायता — टिकट बनाएँ\n\n🎤 सुझाव: वॉइस नोट भेजें जैसे “रमेश से कॉल लॉग करो, कल फ़ॉलो-अप”।"},
    "help_member": {"en": "<b>Sarathi CRM — quick help</b>\n• 📋 My Leads — your assigned leads; tap one for details\n• 🔔 Follow-ups due — what needs action\n• 🔄 Renewals due — policies renewing soon\n• 🤖 Ask AI — ask about your leads\n\n🎤 Tip: send a voice note like “log a call with Ramesh, follow up tomorrow”.",
                    "hi": "<b>Sarathi CRM — त्वरित मदद</b>\n• 📋 मेरी लीड्स — आपकी सौंपी गई लीड्स\n• 🔔 बकाया फ़ॉलो-अप — जिन पर काम बाकी है\n• 🔄 बकाया रिन्यूअल — जल्द रिन्यू होने वाली पॉलिसी\n• 🤖 AI से पूछें — अपनी लीड्स के बारे में पूछें\n\n🎤 सुझाव: वॉइस नोट भेजें जैसे “रमेश से कॉल लॉग करो, कल फ़ॉलो-अप”।"},
    # ask / support
    "ask_prompt": {"en": "🤖 Ask me anything about your leads, follow-ups, renewals or customers — just type or send a voice note.\n\nE.g. <i>“what's pending this week?”</i>",
                   "hi": "🤖 अपनी लीड्स, फ़ॉलो-अप, रिन्यूअल या ग्राहकों के बारे में कुछ भी पूछें — टाइप करें या वॉइस नोट भेजें।\n\nजैसे <i>“इस हफ़्ते क्या बकाया है?”</i>"},
    "ask_thinking": {"en": "🤔 Let me check…", "hi": "🤔 देख रहा हूँ…"},
    "support_prompt": {"en": "🎫 <b>Support</b>\nDescribe your issue in a message or voice note and I'll raise a ticket for you.",
                       "hi": "🎫 <b>सहायता</b>\nअपनी समस्या मैसेज या वॉइस नोट में बताएँ, मैं आपके लिए टिकट बना दूँगा।"},
    "ticket_ok": {"en": "🎫 Ticket <b>#{id}</b> raised. Our team will get back to you.",
                  "hi": "🎫 टिकट <b>#{id}</b> बन गया। हमारी टीम आपसे संपर्क करेगी।"},
    "ticket_fail": {"en": "⚠️ Couldn't raise the ticket — please try again.",
                    "hi": "⚠️ टिकट नहीं बन सका — कृपया फिर कोशिश करें।"},
    # confirm + writes
    "confirm_hdr": {"en": "Please confirm:", "hi": "कृपया पुष्टि करें:"},
    "c_note": {"en": "📇 <b>{name}</b>\n📝 Note: {summary}", "hi": "📇 <b>{name}</b>\n📝 नोट: {summary}"},
    "c_fu": {"en": "📇 <b>{name}</b>\n🔔 Follow-up: <b>{when}</b>\n📝 {summary}",
             "hi": "📇 <b>{name}</b>\n🔔 फ़ॉलो-अप: <b>{when}</b>\n📝 {summary}"},
    "c_move": {"en": "📇 <b>{name}</b>\n📊 Move stage to: <b>{stage}</b>",
               "hi": "📇 <b>{name}</b>\n📊 स्टेज बदलें: <b>{stage}</b>"},
    "c_assign": {"en": "📇 <b>{name}</b>\n👥 Assign to: <b>{who}</b>",
                 "hi": "📇 <b>{name}</b>\n👥 सौंपें: <b>{who}</b>"},
    "c_newlead": {"en": "➕ <b>New lead</b>\n👤 {name}\n📞 {phone}\n🩺 {need}",
                  "hi": "➕ <b>नई लीड</b>\n👤 {name}\n📞 {phone}\n🩺 {need}"},
    "saved_note": {"en": "✅ 📝 Note saved for <b>{name}</b>.", "hi": "✅ 📝 <b>{name}</b> के लिए नोट सेव हुआ।"},
    "saved_fu": {"en": "✅ 🔔 Follow-up set for <b>{name}</b>.", "hi": "✅ 🔔 <b>{name}</b> के लिए फ़ॉलो-अप सेट हुआ।"},
    "saved_move": {"en": "✅ <b>{name}</b> moved to <b>{stage}</b>.", "hi": "✅ <b>{name}</b> को <b>{stage}</b> में ले गए।"},
    "saved_assign": {"en": "✅ <b>{name}</b> assigned to <b>{who}</b>.", "hi": "✅ <b>{name}</b> को <b>{who}</b> को सौंपा।"},
    "saved_lead": {"en": "✅ Lead <b>{name}</b> added.", "hi": "✅ लीड <b>{name}</b> जोड़ी गई।"},
    "save_fail": {"en": "⚠️ Couldn't save — please try again.", "hi": "⚠️ सेव नहीं हुआ — कृपया फिर कोशिश करें।"},
    "nothing_save": {"en": "Nothing to save.", "hi": "सेव करने के लिए कुछ नहीं।"},
    "cancelled": {"en": "Cancelled.", "hi": "रद्द किया गया।"},
    "only_admin_add": {"en": "Only your admin can add new leads.", "hi": "केवल आपका एडमिन नई लीड जोड़ सकता है।"},
    "only_admin_assign": {"en": "Only your admin can assign leads.", "hi": "केवल आपका एडमिन लीड सौंप सकता है।"},
    "need_name": {"en": "Please include the person's name to add them.", "hi": "जोड़ने के लिए कृपया व्यक्ति का नाम बताएँ।"},
    "no_member": {"en": "I couldn't find a team member named “{name}”.", "hi": "“{name}” नाम का टीम सदस्य नहीं मिला।"},
    "no_lead": {"en": "I couldn't find a lead named “{name}”. Add them on the web dashboard, or try the exact name.",
                "hi": "“{name}” नाम की लीड नहीं मिली। वेब डैशबोर्ड पर जोड़ें, या सही नाम आज़माएँ।"},
    "pick_hdr": {"en": "Found {n} matching leads — which one?", "hi": "{n} मिलती-जुलती लीड्स मिलीं — कौन सी?"},
    "which_stage": {"en": "Which stage? Say e.g. contacted, proposal, negotiation, won, or lost.",
                    "hi": "कौन सा स्टेज? जैसे contacted, proposal, negotiation, won, या lost।"},
    "member_only_own": {"en": "You can only update your assigned leads.", "hi": "आप केवल अपनी सौंपी गई लीड्स अपडेट कर सकते हैं।"},
    # nudge
    "nudge": {"en": "↩️ You have a paused draft: <b>{desc}</b>.", "hi": "↩️ आपका एक रुका हुआ ड्राफ्ट है: <b>{desc}</b>।"},
    "prev_discarded": {"en": "Paused draft discarded.", "hi": "रुका हुआ ड्राफ्ट हटाया गया।"},
    "no_prev": {"en": "No paused draft to resume.", "hi": "जारी रखने के लिए कोई ड्राफ्ट नहीं।"},
    # voice
    "v_listen": {"en": "🎧 Listening…", "hi": "🎧 सुन रहा हूँ…"},
    "v_heard": {"en": "🗣️ I heard: “{text}”", "hi": "🗣️ मैंने सुना: “{text}”"},
    "v_long": {"en": "⏱️ Please keep voice notes under ~2 minutes and try again.",
               "hi": "⏱️ कृपया वॉइस नोट ~2 मिनट से कम रखें और फिर कोशिश करें।"},
    "v_silent": {"en": "🤫 I didn't hear any speech.", "hi": "🤫 कोई आवाज़ नहीं सुनाई दी।"},
    "v_noisy": {"en": "🔊 Too much background noise.", "hi": "🔊 बहुत शोर है।"},
    "v_unclear": {"en": "🙉 I couldn't catch that clearly.", "hi": "🙉 साफ़ सुनाई नहीं दिया।"},
    "v_abusive": {"en": "🙏 Let's keep it professional.", "hi": "🙏 कृपया शालीन भाषा रखें।"},
    "v_nonsense": {"en": "🤔 I couldn't make out a request.", "hi": "🤔 अनुरोध समझ नहीं आया।"},
    "v_retry": {"en": " Please try again or type it.", "hi": " कृपया फिर कोशिश करें या टाइप करें।"},
    # digest UI
    "dig_hdr": {"en": "📅 <b>Daily Summary</b>\nStatus: {status}\n\nA once-a-day snapshot of your firm's progress — new leads, follow-ups, renewals and new policies.",
                "hi": "📅 <b>दैनिक सारांश</b>\nस्थिति: {status}\n\nरोज़ एक बार आपकी फर्म की प्रगति — नई लीड्स, फ़ॉलो-अप, रिन्यूअल और नई पॉलिसी।"},
    "dig_on": {"en": "🟢 ON — every day around {hr}:00 IST", "hi": "🟢 चालू — रोज़ लगभग {hr}:00 IST"},
    "dig_off": {"en": "⚪ OFF", "hi": "⚪ बंद"},
    "dig_team_hdr": {"en": "👥 <b>Team daily summaries</b>\nTap a name to turn their daily summary on/off:",
                     "hi": "👥 <b>टीम के दैनिक सारांश</b>\nचालू/बंद करने के लिए नाम पर टैप करें:"},
    "dig_team_none": {"en": "No team members are linked yet. Invite them from the 🤖 Telegram CRM section of your web dashboard.",
                      "hi": "अभी कोई टीम सदस्य नहीं जुड़ा। वेब डैशबोर्ड के 🤖 Telegram CRM सेक्शन से इनवाइट करें।"},
    "lang_set": {"en": "✅ Language set to English.", "hi": "✅ भाषा हिंदी सेट कर दी गई।"},
    "no_longer_linked": {"en": "You're no longer linked to this CRM.", "hi": "आप अब इस CRM से जुड़े नहीं हैं।"},
    "ai_off": {"en": "The AI assistant isn't configured yet.", "hi": "AI सहायक अभी सेट नहीं है।"},
    "ai_err": {"en": "Sorry, I couldn't process that right now.", "hi": "क्षमा करें, अभी यह नहीं हो सका।"},
    "ai_none": {"en": "I couldn't find an answer to that.", "hi": "इसका उत्तर नहीं मिला।"},
    "digest_body": {"en": "📅 <b>{firm} — Daily Summary</b>\n<i>{date}</i>\n\n🆕 New leads today: <b>{nl}</b>\n📋 Active leads: <b>{ac}</b>\n🔔 Follow-ups due: <b>{fu}</b>\n🔄 Renewals (next 30 days): <b>{rn}</b>\n📄 New policies today: <b>{np}</b>\n\nHave a productive day! 🙏",
                    "hi": "📅 <b>{firm} — दैनिक सारांश</b>\n<i>{date}</i>\n\n🆕 आज नई लीड्स: <b>{nl}</b>\n📋 सक्रिय लीड्स: <b>{ac}</b>\n🔔 बकाया फ़ॉलो-अप: <b>{fu}</b>\n🔄 रिन्यूअल (अगले 30 दिन): <b>{rn}</b>\n📄 आज नई पॉलिसी: <b>{np}</b>\n\nआपका दिन शुभ हो! 🙏"},
}


def T(lang: str, key: str, **kw) -> str:
    d = STRINGS.get(key, {})
    s = d.get(lang if lang in ("en", "hi") else "en") or d.get("en") or key
    if kw:
        try:
            s = s.format(**kw)
        except Exception:
            pass
    return s


async def set_user_lang(tg_uid: int, lang: str) -> None:
    lang = lang if lang in ("en", "hi") else "en"
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE tg_links SET lang=? WHERE telegram_user_id=?", (lang, tg_uid))
        await conn.commit()


def _lang(link) -> str:
    l = (link or {}).get("lang") or "en"
    return l if l in ("en", "hi") else "en"


# ── Voice replies (assistant speaks its answer back) ─────────────────────────
async def set_user_voice(tg_uid: int, mode: str) -> None:
    mode = mode if mode in ("auto", "on", "off") else "auto"
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE tg_links SET voice_reply=? WHERE telegram_user_id=?", (mode, tg_uid))
        await conn.commit()


def _voice_mode(link) -> str:
    m = (link or {}).get("voice_reply") or "auto"
    return m if m in ("auto", "on", "off") else "auto"


def _should_voice_reply(link, is_voice: bool) -> bool:
    """auto = speak when the advisor spoke; on = always speak; off = never."""
    m = _voice_mode(link)
    return m == "on" or (m == "auto" and bool(is_voice))


def _pcm_to_wav(pcm: bytes, rate: int = 24000, ch: int = 1, bits: int = 16) -> bytes:
    import struct as _s
    br = rate * ch * bits // 8
    ba = ch * bits // 8
    ds = len(pcm)
    return (b"RIFF" + _s.pack("<I", 36 + ds) + b"WAVE" + b"fmt "
            + _s.pack("<IHHIIHH", 16, 1, ch, rate, br, ba, bits)
            + b"data" + _s.pack("<I", ds) + pcm)


async def _tts_voice(text: str, lang: str = "en") -> Optional[bytes]:
    """Gemini TTS → OGG/Opus voice-note bytes (via ffmpeg). Returns None on any failure so the
    caller silently falls back to a text reply. Kept short — long replies are truncated for speech."""
    import os as _os
    import base64 as _b64
    import asyncio as _aio
    key = _os.getenv("GEMINI_API_KEY", "").strip()
    say = (text or "").strip()
    if not key or not say:
        return None
    voice = _os.getenv("TGCRM_TTS_VOICE", "Kore")
    model = _os.getenv("TGCRM_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    prompt = ("Say warmly and naturally, like a helpful human assistant: " + say)[:1400]
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    try:
        async with httpx.AsyncClient(timeout=45.0) as c:
            r = await c.post(url, json=body)
        d = r.json()
        part = d["candidates"][0]["content"]["parts"][0]["inlineData"]
        rate = 24000
        mt = part.get("mimeType", "")
        if "rate=" in mt:
            try:
                rate = int(mt.split("rate=")[1].split(";")[0])
            except Exception:
                pass
        pcm = _b64.b64decode(part["data"])
    except Exception as e:
        logger.info("tgcrm tts failed: %s", e)
        return None
    wav = _pcm_to_wav(pcm, rate)
    try:
        proc = await _aio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
            "-c:a", "libopus", "-b:a", "32k", "-f", "ogg", "pipe:1",
            stdin=_aio.subprocess.PIPE, stdout=_aio.subprocess.PIPE, stderr=_aio.subprocess.PIPE)
        out, err = await proc.communicate(input=wav)
        if proc.returncode != 0 or not out:
            logger.info("ffmpeg ogg convert failed: %s", (err or b"")[:150])
            return None
        return out
    except Exception as e:
        logger.info("ffmpeg error: %s", e)
        return None


async def _send_voice(token: str, chat_id, ogg_bytes: bytes, caption: str = "",
                      buttons: Optional[list] = None) -> bool:
    """Send an OGG/Opus voice note (with the text as caption + optional buttons). Best-effort."""
    import json as _json
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
        data["parse_mode"] = "HTML"
    if buttons:
        data["reply_markup"] = _json.dumps({"inline_keyboard": buttons})
    try:
        async with httpx.AsyncClient(timeout=45.0) as c:
            r = await c.post(API_BASE.format(token=token, method="sendVoice"),
                             data=data, files={"voice": ("reply.ogg", ogg_bytes, "audio/ogg")})
        return r.status_code == 200
    except Exception as e:
        logger.info("sendVoice failed: %s", e)
        return False


async def _reply(token, chat_id, text, link, is_voice, buttons=None) -> None:
    """Deliver an assistant reply: as a VOICE note (with the text as caption) when voice is warranted,
    else as text. Voice failure always falls back to text — the answer is never lost."""
    if _should_voice_reply(link, is_voice):
        audio = await _tts_voice(text, _lang(link))
        if audio and await _send_voice(token, chat_id, audio, caption=text, buttons=buttons):
            return
    await send_message(token, chat_id, text, buttons)


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
def _menu_kb(role: str, lang: str = "en") -> list:
    if role in ("owner", "admin"):
        return [
            [{"text": T(lang, "b_today"), "callback_data": "today"}],
            [{"text": T(lang, "b_leads"), "callback_data": "leads"}],
            [{"text": T(lang, "b_followups"), "callback_data": "followups"}],
            [{"text": T(lang, "b_renewals"), "callback_data": "renewals"}],
            [{"text": T(lang, "b_ask"), "callback_data": "ask"}],
            [{"text": T(lang, "b_digest"), "callback_data": "digest"}],
            [{"text": T(lang, "b_support"), "callback_data": "support"}],
            [{"text": T(lang, "b_help"), "callback_data": "help"},
             {"text": T(lang, "b_lang"), "callback_data": "lang"}],
        ]
    return [
        [{"text": T(lang, "b_myleads"), "callback_data": "leads"}],
        [{"text": T(lang, "b_followups"), "callback_data": "followups"}],
        [{"text": T(lang, "b_renewals"), "callback_data": "renewals"}],
        [{"text": T(lang, "b_ask"), "callback_data": "ask"}],
        [{"text": T(lang, "b_support"), "callback_data": "support"}],
        [{"text": T(lang, "b_help"), "callback_data": "help"},
         {"text": T(lang, "b_lang"), "callback_data": "lang"},
         {"text": T(lang, "b_voice"), "callback_data": "voice"}],
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
    role = link["role"]; tid = int(link["tenant_id"]); aid = link.get("agent_id"); lang = _lang(link)
    if role in ("owner", "admin"):
        rows = await _firm_renewals(tid, 60, 15)
    else:
        rows = (await db.get_upcoming_renewals(aid, 60))[:15] if aid else []
    if not rows:
        await send_message(token, chat_id, T(lang, "ren_none"),
                           [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]])
        return
    lines = []
    for r in rows:
        d = (r.get("renewal_date") or "")[:10]
        nm = r.get("client_name", "?")
        ins = r.get("insurer") or r.get("plan_name") or ""
        lines.append(f"• <b>{nm}</b> — {d}{(' · ' + ins) if ins else ''}")
    await send_message(token, chat_id, T(lang, "ren_hdr", n=len(rows)) + "\n" + "\n".join(lines),
                       [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]])


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
    tid = int(link["tenant_id"]); lang = _lang(link)
    firm = await _tenant_firm(tid)
    s = await _firm_stats(tid)
    txt = T(lang, "today", firm=firm, nl=s['new_leads'], ac=s['active'],
            fu=s['followups'], rn=s['renewals'])
    await send_message(token, chat_id, txt, [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]])


def _help_text(role: str, lang: str = "en") -> str:
    return T(lang, "help_admin" if role in ("owner", "admin") else "help_member")


async def _send_menu(token, chat_id, link) -> None:
    firm = await _tenant_firm(int(link["tenant_id"]))
    lang = _lang(link)
    await send_message(token, chat_id, T(lang, "menu_hdr", firm=firm), _menu_kb(link["role"], lang))


async def _firm_leads(tenant_id: int, limit: int = 8) -> list:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT l.* FROM leads l JOIN agents a ON l.agent_id=a.agent_id "
            "WHERE a.tenant_id=? ORDER BY l.updated_at DESC LIMIT ?",
            (tenant_id, limit))).fetchall()
        return [dict(r) for r in rows]


async def _leads_view(token, chat_id, link) -> None:
    role = link["role"]; tid = int(link["tenant_id"]); aid = link.get("agent_id"); lang = _lang(link)
    if role in ("owner", "admin"):
        rows = await _firm_leads(tid, 8)
    else:
        rows = (await db.get_leads_by_agent(aid))[:8] if aid else []
    if not rows:
        await send_message(token, chat_id, T(lang, "leads_none"),
                           [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]])
        return
    kb = [[{"text": f"👤 {(r.get('name') or '—')[:28]} · {r.get('stage','')}",
            "callback_data": f"lead:{r['lead_id']}"}] for r in rows]
    kb.append([{"text": T(lang, "b_menu"), "callback_data": "menu"}])
    await send_message(token, chat_id, T(lang, "leads_show", n=len(rows)), kb)


async def _lead_detail(token, chat_id, link, lead_id: int) -> None:
    lead = await db.get_lead(lead_id, int(link["tenant_id"]))
    lang = _lang(link)
    if not lead:
        await send_message(token, chat_id, T(lang, "lead_notfound"),
                           [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]])
        return
    if link["role"] not in ("owner", "admin") and lead.get("agent_id") != link.get("agent_id"):
        await send_message(token, chat_id, T(lang, "only_assigned"),
                           [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]])
        return
    txt = (f"👤 <b>{lead.get('name','—')}</b>\n"
           f"📞 {lead.get('phone') or '—'}\n"
           f"📊 {lead.get('stage') or '—'}\n"
           f"🩺 {lead.get('need_type') or '—'}\n"
           f"🏙 {lead.get('city') or '—'}\n"
           f"📝 {lead.get('notes') or '—'}")
    kb = [[{"text": T(lang, "b_back_leads"), "callback_data": "leads"}],
          [{"text": T(lang, "b_menu"), "callback_data": "menu"}]]
    await send_message(token, chat_id, txt, kb)


async def _followups_view(token, chat_id, link) -> None:
    aid = link.get("agent_id"); lang = _lang(link)
    rows = await db.get_pending_followups(aid) if aid else []
    if not rows:
        await send_message(token, chat_id, T(lang, "fu_none"),
                           [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]])
        return
    lines = []
    for r in rows[:10]:
        d = (r.get("follow_up_date") or "")[:10]
        lines.append(f"• <b>{r.get('lead_name','?')}</b> — {d} {(r.get('summary') or '')}".rstrip())
    await send_message(token, chat_id, T(lang, "fu_hdr") + "\n" + "\n".join(lines),
                       [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]])


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


async def compose_digest(tenant_id: int, lang: str = "en") -> str:
    firm = await _tenant_firm(tenant_id)
    s = await _firm_stats(tenant_id)
    IST = "'+5 hours','+30 minutes'"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        pol = await (await conn.execute(
            "SELECT COUNT(*) c FROM policies p JOIN agents a ON p.agent_id=a.agent_id "
            f"WHERE a.tenant_id=? AND date(p.created_at)=date('now',{IST})", (tenant_id,))).fetchone()
    new_pol = pol["c"] if pol else 0
    return T(lang, "digest_body", firm=firm, date=datetime.now().strftime('%d %b %Y'),
             nl=s['new_leads'], ac=s['active'], fu=s['followups'], rn=s['renewals'], np=new_pol)


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
            await send_message(token, tg_uid, await compose_digest(tid, _lang(link)))
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
    lang = _lang(link)
    pref = await get_digest_pref(tg_uid)
    on = bool(pref and pref.get("enabled"))
    hr = (pref or {}).get("hour_ist", 9)
    status = T(lang, "dig_on", hr=hr) if on else T(lang, "dig_off")
    txt = T(lang, "dig_hdr", status=status)
    kb = []
    if on:
        kb.append([{"text": T(lang, "b_turn_off"), "callback_data": "digest_off"}])
    else:
        kb.append([{"text": T(lang, "b_turn_on"), "callback_data": "digest_on"}])
    kb.append([{"text": T(lang, "b_send_now"), "callback_data": "digest_now"}])
    kb.append([{"text": T(lang, "b_team_digests"), "callback_data": "digest_team"}])
    kb.append([{"text": T(lang, "b_menu"), "callback_data": "menu"}])
    await send_message(token, chat_id, txt, kb)


async def _digest_team_view(token, chat_id, tenant_id: int, lang: str = "en") -> None:
    """Admin: toggle the daily summary on/off per linked team member."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT l.telegram_user_id AS tguid, a.name AS name, d.enabled AS enabled "
            "FROM tg_links l LEFT JOIN agents a ON a.agent_id=l.agent_id "
            "LEFT JOIN tg_digest_prefs d ON d.telegram_user_id=l.telegram_user_id "
            "WHERE l.tenant_id=? AND l.status='active' AND l.role NOT IN ('owner','admin')",
            (tenant_id,))).fetchall()
    if not rows:
        await send_message(token, chat_id, T(lang, "dig_team_none"),
                           [[{"text": T(lang, "b_back"), "callback_data": "digest"}]])
        return
    kb = []
    for r in rows:
        on = bool(r["enabled"])
        nm = r["name"] or "Member"
        kb.append([{"text": f"{'🟢' if on else '⚪'} {nm}",
                    "callback_data": f"digmem:{r['tguid']}:{'off' if on else 'on'}"}])
    kb.append([{"text": T(lang, "b_back"), "callback_data": "digest"}])
    await send_message(token, chat_id, T(lang, "dig_team_hdr"), kb)


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
        '{"action":"log_note|set_followup|move_stage|create_lead|assign|ask|none","lead_name":"","summary":"",'
        '"followup_date":"YYYY-MM-DD","followup_time":"HH:MM","stage":"","phone":"","need_type":"","assignee_name":""}\n'
        "- 'set_followup' = schedule a future call/meeting/reminder for a lead (has a date).\n"
        "- 'log_note' = record something that happened (a call/update) with no future date.\n"
        "- 'move_stage' = change a lead's pipeline stage. 'stage' MUST be one of: "
        "prospect, contacted, proposal_sent, negotiation, closed_won, closed_lost "
        "(map 'won'->closed_won, 'lost'->closed_lost, 'quoted'/'proposal'->proposal_sent).\n"
        "- 'create_lead' = add a NEW lead/customer. phone = digits only if spoken; "
        "need_type = product if said (health/life/term/motor/etc).\n"
        "- 'assign' = reassign an existing lead to a team member. lead_name = the lead; "
        "assignee_name = the team member's name.\n"
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
        if out.get("action") not in ("log_note", "set_followup", "move_stage", "create_lead",
                                     "assign", "ask", "none"):
            out["action"] = "none"
        return out
    except Exception as e:
        logger.info("tgcrm intent parse failed: %s", e)
        return {"action": "none"}


_ACTIONABLE = {"log_note", "set_followup", "move_stage", "create_lead", "assign"}


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
    if a == "assign":
        return f"assign {nm} to {p.get('assignee_name','')}"
    if a == "log_note":
        return f"note for {nm}"
    return "your draft"


async def _render_confirm(token, chat_id, p: dict, lang: str = "en") -> None:
    a = p.get("action")
    if a == "create_lead":
        card = T(lang, "c_newlead", name=p.get('lead_name', ''), phone=p.get('phone') or '—',
                 need=p.get('need', 'health'))
    elif a == "set_followup":
        when = ((p.get('fud') or '') + ((' ' + p.get('fut')) if p.get('fut') else '')) or "-"
        card = T(lang, "c_fu", name=p.get('lead_name', ''), when=when, summary=p.get('summary', ''))
    elif a == "move_stage":
        card = T(lang, "c_move", name=p.get('lead_name', ''), stage=(p.get('stage') or '').replace('_', ' '))
    elif a == "assign":
        card = T(lang, "c_assign", name=p.get('lead_name', ''), who=p.get('assignee_name', ''))
    else:
        card = T(lang, "c_note", name=p.get('lead_name', ''), summary=p.get('summary', ''))
    await send_message(token, chat_id, T(lang, "confirm_hdr") + "\n\n" + card, _save_kb(lang))


async def _nudge_prev(token, chat_id, tg_uid, lang: str = "en") -> None:
    prev = await _get_prev(tg_uid)
    if not prev:
        return
    await send_message(token, chat_id, T(lang, "nudge", desc=_describe_pending(prev)),
                       [[{"text": T(lang, "b_resume"), "callback_data": "resume"},
                         {"text": T(lang, "b_discard"), "callback_data": "discard_prev"}]])


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
def _save_kb(lang: str = "en") -> list:
    return [[{"text": T(lang, "b_save"), "callback_data": "cfm:save"},
             {"text": T(lang, "b_cancel"), "callback_data": "cfm:cancel"}]]


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
    tid = int(link["tenant_id"]); lang = _lang(link)
    summary = (intent.get("summary") or "").strip()
    base = {"lead_id": lead["lead_id"], "lead_name": lead.get("name", ""),
            "lead_agent": lead.get("agent_id")}
    if act == "move_stage":
        stage = _canon_stage(intent.get("stage", ""))
        if stage not in _STAGES:
            await send_message(token, chat_id, T(lang, "which_stage"), _menu_kb(link["role"], lang))
            return
        await _set_pending(tg_uid, tid, {**base, "action": "move_stage", "stage": stage})
        card = T(lang, "c_move", name=lead.get('name', ''), stage=stage.replace('_', ' '))
    elif act == "set_followup":
        fud = (intent.get("followup_date") or "").strip()
        fut = (intent.get("followup_time") or "").strip()
        await _set_pending(tg_uid, tid, {**base, "action": "set_followup",
                                         "summary": summary or "Follow-up", "fud": fud, "fut": fut})
        when = (fud + ((" " + fut) if fut else "")) or "-"
        card = T(lang, "c_fu", name=lead.get('name', ''), when=when, summary=summary or "")
    elif act == "assign":
        await _set_pending(tg_uid, tid, {**base, "action": "assign",
                                         "assignee_agent": intent.get("assignee_agent"),
                                         "assignee_name": intent.get("assignee_name", "")})
        card = T(lang, "c_assign", name=lead.get('name', ''), who=intent.get('assignee_name', ''))
    else:  # log_note
        await _set_pending(tg_uid, tid, {**base, "action": "log_note", "summary": summary or "Note"})
        card = T(lang, "c_note", name=lead.get('name', ''), summary=summary or "")
    await send_message(token, chat_id, T(lang, "confirm_hdr") + "\n\n" + card, _save_kb(lang))


async def _find_member(tenant_id: int, name: str) -> Optional[dict]:
    name = (name or "").strip()
    if not name:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        r = await (await conn.execute(
            "SELECT agent_id, name FROM agents WHERE tenant_id=? AND is_active=1 AND name LIKE ? "
            "ORDER BY agent_id LIMIT 1", (tenant_id, f"%{name}%"))).fetchone()
        return dict(r) if r else None


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


# ── AI conversation memory (rolling, per Telegram user) ──────────────────────
_AI_TURNS = 8            # keep the last N exchanges (user+assistant pairs)
_AI_TTL_MIN = 30        # a gap longer than this starts a fresh conversation


async def _load_ai_history(tg_uid) -> list:
    """Recent conversation turns [{role,text}], or [] if none/stale (>30 min)."""
    import json as _json, time as _time
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT ai_history FROM tg_context WHERE telegram_user_id=?", (tg_uid,))).fetchone()
        if not row or not row["ai_history"]:
            return []
        blob = _json.loads(row["ai_history"]) or {}
        if _time.time() - float(blob.get("ts", 0)) > _AI_TTL_MIN * 60:
            return []
        return (blob.get("turns") or [])[-_AI_TURNS * 2:]
    except Exception:
        return []


async def _save_ai_history(tg_uid, tid, turns) -> None:
    import json as _json, time as _time
    try:
        blob = _json.dumps({"ts": _time.time(), "turns": turns[-_AI_TURNS * 2:]}, ensure_ascii=False)
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "INSERT OR IGNORE INTO tg_context (telegram_user_id, tenant_id, updated_at) "
                "VALUES (?,?,CURRENT_TIMESTAMP)", (tg_uid, tid))
            await conn.execute("UPDATE tg_context SET ai_history=? WHERE telegram_user_id=?",
                               (blob, tg_uid))
            await conn.commit()
    except Exception as e:
        logger.info("tgcrm save_ai_history failed: %s", e)


# Short affirmations that confirm an action the assistant just offered (EN + Hindi/Hinglish).
_AFFIRM_EXACT = {"yes", "yeah", "yep", "ya", "yup", "ok", "okay", "k", "sure", "please", "yes please",
                 "do it", "go ahead", "haan", "haanji", "haan ji", "ha", "ji", "ji haan", "kar do",
                 "kardo", "karo", "kr do", "krdo", "theek", "thik", "theek hai", "thik hai", "done",
                 "great", "perfect", "yes do it", "haan karo", "ok do it", "yes please do", "bilkul"}


def _is_affirmation(text: str) -> bool:
    """True if the message is a short 'yes, do it' — used only to confirm a pending AI action proposal."""
    t = (text or "").strip().lower()
    if "👍" in t and len(t) <= 4:
        return True
    t = "".join(ch for ch in t if ch.isalnum() or ch == " ").strip()
    if not t or len(t) > 22:
        return False
    if t in _AFFIRM_EXACT:
        return True
    return any(t.startswith(p) for p in
               ("yes", "haan", "kar do", "kardo", "ok do", "sure do", "please do", "go ahead", "ji haan"))


async def _ask_ai(link, question: str, tg_uid=None) -> dict:
    """Conversational CRM answer + an OPTIONAL structured action proposal the user can confirm.
    Returns {"answer": <text>, "action": None | {action, lead_name, …}} (same shape the intent parser
    uses, so a confirmed proposal flows through the normal Save-confirm card)."""
    import os as _os, json as _json
    lang = _lang(link)
    key = _os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return {"answer": T(lang, "ai_off"), "action": None}
    ctx = await _ai_context(link)
    today = (datetime.utcnow() + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d")
    langname = "Hindi (Devanagari script)" if lang == "hi" else "English"
    history = await _load_ai_history(tg_uid) if tg_uid else []
    hist_txt = "\n".join(
        ("User: " if h.get("role") == "user" else "Sarathi: ") + (h.get("text") or "")
        for h in history) or "(this is the start of the conversation)"
    prompt = (
        "You are Sarathi — a warm, sharp CRM assistant for an insurance advisor, chatting on Telegram. "
        f"Today (IST) is {today}. Reply in {langname}, in simple, friendly language.\n"
        "Hold a NATURAL, CONTINUOUS conversation. The user often asks follow-ups that refer to what you "
        'just said ("those", "the second one", "him", "and health?", "call him tomorrow") — use the '
        "conversation so far to understand exactly what they mean.\n"
        "Ground every fact ONLY in the DATA below (their own CRM). Never invent leads, numbers or dates; "
        "keep names/numbers/dates exactly as given. If something isn't in the data, say so briefly.\n"
        "Be concise but human (2-5 short lines); when it helps, proactively OFFER a next step.\n"
        "If — and ONLY if — you offer to DO a concrete action the user can confirm (set a reminder/"
        "follow-up, add a new lead, log a call note, or move a lead's stage) AND you have enough detail "
        "(a lead name; a date for reminders), include it as \"action\"; otherwise action=null. NEVER act "
        "on your own — the user confirms next.\n\n"
        f"DATA (JSON): {_json.dumps(ctx, ensure_ascii=False)[:6000]}\n\n"
        f"Conversation so far:\n{hist_txt}\n\nUser: {question}\n\n"
        "Respond with JSON ONLY: {\"answer\":\"<reply in the user's language>\", \"action\": null or "
        "{\"action\":\"set_followup|create_lead|log_note|move_stage\",\"lead_name\":\"\",\"summary\":\"\","
        "\"followup_date\":\"YYYY-MM-DD\",\"followup_time\":\"HH:MM\",\"phone\":\"\",\"need_type\":\"\","
        "\"stage\":\"\"}}")
    model = _os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(url, json={"contents": [{"parts": [{"text": prompt}]}],
                                        "generationConfig": {"temperature": 0.45,
                                                             "responseMimeType": "application/json"}})
            data = r.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [{}]
        raw = (parts[0].get("text") or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[4:] if raw[:4].lower() == "json" else raw
        parsed = _json.loads(raw)
        answer = (parsed.get("answer") or "").strip() or T(lang, "ai_none")
        action = parsed.get("action")
        # Only keep a well-formed, actionable proposal (a known action + a lead name).
        if not (isinstance(action, dict)
                and action.get("action") in ("set_followup", "create_lead", "log_note", "move_stage")
                and (action.get("lead_name") or "").strip()):
            action = None
    except Exception as e:
        logger.info("tgcrm ask_ai failed: %s", e)
        return {"answer": T(lang, "ai_err"), "action": None}
    if tg_uid:
        history.append({"role": "user", "text": (question or "")[:800]})
        history.append({"role": "assistant", "text": answer[:800]})
        await _save_ai_history(tg_uid, int(link["tenant_id"]), history)
    return {"answer": answer, "action": action}


async def _ask_opener(link) -> str:
    """A short, data-grounded proactive line shown when the advisor opens Ask AI — so it feels
    smart and personal from the first tap. Falls back to the static prompt on any error."""
    lang = _lang(link)
    try:
        ctx = await _ai_context(link)
        now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        today = now.strftime("%Y-%m-%d")
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        due_today = sum(1 for f in (ctx.get("followups") or []) if (f.get("date") or "")[:10] == today)
        soon = 0
        for r in (ctx.get("renewals") or []):
            try:
                dt = datetime.strptime((r.get("date") or "")[:10], "%Y-%m-%d")
                if 0 <= (dt - midnight).days <= 7:
                    soon += 1
            except Exception:
                pass
    except Exception:
        return T(lang, "ask_prompt")
    if lang == "hi":
        bits = []
        if due_today:
            bits.append(f"आज {due_today} फ़ॉलो-अप बाकी")
        if soon:
            bits.append(f"अगले 7 दिन में {soon} रिन्यूअल")
        head = ("🤖 " + " · ".join(bits) + "।\n\n") if bits else "🤖 "
        return head + ("मुझसे कुछ भी पूछें — जैसे <i>“आज क्या पेंडिंग है?”</i> या "
                       "<i>“इस हफ़्ते किसके रिन्यूअल हैं?”</i>। फ़ॉलो-अप सवाल भी पूछ सकते हैं — "
                       "मैं हमारी बातचीत याद रखता हूँ।")
    bits = []
    if due_today:
        bits.append(f"{due_today} follow-up{'s' if due_today != 1 else ''} due today")
    if soon:
        bits.append(f"{soon} renewal{'s' if soon != 1 else ''} in the next 7 days")
    head = ("🤖 " + " · ".join(bits) + ".\n\n") if bits else "🤖 "
    return head + ("Ask me anything — e.g. <i>“what's pending today?”</i> or "
                   "<i>“whose renewals this week?”</i>. Follow-up questions are fine too — "
                   "I remember our chat.")


async def _process_command(token, chat_id, tg_uid, link, text, is_voice=False) -> None:
    """Parse a note (typed or transcribed) → (pick lead if needed) → confirm card → save.
    is_voice: whether the source was a voice note (drives voice-vs-text replies for AI answers)."""
    lang = _lang(link)
    mkb = [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]]
    # Support capture mode: the next message becomes a support ticket.
    _pend = await _get_pending(tg_uid)
    if _pend and _pend.get("action") == "support_capture":
        await _set_pending(tg_uid, int(link["tenant_id"]), None)
        body = (text or "").strip()
        try:
            tkt = await db.create_ticket(
                tenant_id=int(link["tenant_id"]), agent_id=link.get("agent_id"),
                subject=(body[:60] or "Support request (Telegram)"),
                description=body, category="general", priority="normal")
            await send_message(token, chat_id, T(lang, "ticket_ok", id=tkt), mkb)
        except Exception as e:
            logger.warning("tgcrm support ticket failed: %s", e)
            await send_message(token, chat_id, T(lang, "ticket_fail"), mkb)
        return
    # Are we mid-conversation with the AI? Then keep vague/greeting follow-ups in the chat
    # (a stateless intent-parse would bounce "and health?" to the menu).
    _in_ask = bool(_pend and _pend.get("action") == "ask_mode")
    _proposal = (_pend or {}).get("proposal")
    if _in_ask and isinstance(_proposal, dict) and _is_affirmation(text):
        # confirm-to-act: user said "yes" to an action Sarathi just offered → run it through the
        # normal Save-confirm card (we NEVER auto-save — the user still taps Save).
        await _set_pending(tg_uid, int(link["tenant_id"]), None)
        _in_ask = False
        intent = dict(_proposal)
        act = intent.get("action", "none")
    else:
        intent = await _parse_intent(text)
        act = intent.get("action", "none")
        if _in_ask and act == "none":
            act = "ask"
        if act == "ask":
            await send_message(token, chat_id, T(lang, "ask_thinking"))
            _res = await _ask_ai(link, text, tg_uid)
            # Stay in the conversation; remember any action Sarathi proposed so a "yes" can confirm it.
            _pd = {"action": "ask_mode"}
            if _res.get("action"):
                _pd["proposal"] = _res["action"]
            await _set_pending(tg_uid, int(link["tenant_id"]), _pd)
            await _reply(token, chat_id, _res["answer"], link, is_voice, mkb)
            return
        # A real command (log a note, add a lead, …) breaks out of the AI chat.
        if _in_ask:
            await _set_pending(tg_uid, int(link["tenant_id"]), None)
    if act == "none":
        await _send_menu(token, chat_id, link)
        return
    intent["summary"] = (intent.get("summary") or text).strip()

    # Context-switch: a new command supersedes any unconfirmed draft, which we pause
    # (stash) and nudge so the user can Resume or Discard it.
    had = await _get_pending(tg_uid)
    had_actionable = bool(had and had.get("action") in _ACTIONABLE)

    if act == "create_lead":
        if link["role"] not in ("owner", "admin"):
            await send_message(token, chat_id, T(lang, "only_admin_add"), _menu_kb(link["role"], lang))
            return
        name = (intent.get("lead_name") or "").strip()
        if not name:
            await send_message(token, chat_id, T(lang, "need_name"), _menu_kb(link["role"], lang))
            return
        phone = "".join(ch for ch in (intent.get("phone") or "") if ch.isdigit())
        need = (intent.get("need_type") or "").strip() or "health"
        if had_actionable:
            await _stash_current_as_prev(tg_uid)
        await _set_pending(tg_uid, int(link["tenant_id"]),
                           {"action": "create_lead", "lead_name": name, "phone": phone, "need": need})
        card = T(lang, "c_newlead", name=name, phone=phone or '—', need=need)
        await send_message(token, chat_id, T(lang, "confirm_hdr") + "\n\n" + card, _save_kb(lang))
        if had_actionable:
            await _nudge_prev(token, chat_id, tg_uid, lang)
        return

    if act == "assign":
        if link["role"] not in ("owner", "admin"):
            await send_message(token, chat_id, T(lang, "only_admin_assign"), _menu_kb(link["role"], lang))
            return
        member = await _find_member(int(link["tenant_id"]), intent.get("assignee_name", ""))
        if not member:
            await send_message(token, chat_id, T(lang, "no_member", name=intent.get('assignee_name', '')),
                               _menu_kb(link["role"], lang))
            return
        intent["assignee_agent"] = member["agent_id"]
        intent["assignee_name"] = member.get("name", "")
        # falls through to lead resolution below

    leads = await _find_lead(link, intent.get("lead_name", ""))
    if not leads:
        await send_message(token, chat_id, T(lang, "no_lead", name=intent.get('lead_name', '')),
                           _menu_kb(link["role"], lang))
        return
    if len(leads) > 1:
        if had_actionable:
            await _stash_current_as_prev(tg_uid)
        await _set_pending(tg_uid, int(link["tenant_id"]), {"action": "pick", "intent": intent})
        kb = [[{"text": f"👤 {(l.get('name') or '')[:24]} · {l.get('phone') or l.get('stage','')}",
                "callback_data": f"pick:{l['lead_id']}"}] for l in leads]
        kb.append([{"text": T(lang, "b_cancel"), "callback_data": "cfm:cancel"}])
        await send_message(token, chat_id, T(lang, "pick_hdr", n=len(leads)), kb)
        return
    if had_actionable:
        await _stash_current_as_prev(tg_uid)
    await _finalize_action(token, chat_id, tg_uid, link, intent, leads[0])
    if had_actionable:
        await _nudge_prev(token, chat_id, tg_uid, lang)


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
            await send_message(token, chat_id, T("en", "no_longer_linked"))
        return {"ok": True}
    if not chat_id:
        return {"ok": True}
    lang = _lang(link)
    mkb = [[{"text": T(lang, "b_menu"), "callback_data": "menu"}]]
    # Tapping any button other than "Ask AI" leaves the AI conversation — drop ask-mode so later
    # typing isn't mistaken for a follow-up question. (Only clears ask-mode, never a real draft.)
    if data != "ask":
        try:
            _p = await _get_pending(tg_uid)
            if _p and _p.get("action") == "ask_mode":
                await _set_pending(tg_uid, tenant_id, None)
        except Exception:
            pass
    if data == "menu":
        await _send_menu(token, chat_id, link)
    elif data == "lang":
        newlang = "hi" if lang == "en" else "en"
        await set_user_lang(tg_uid, newlang)
        link["lang"] = newlang
        await send_message(token, chat_id, T(newlang, "lang_set"))
        await _send_menu(token, chat_id, link)
    elif data == "voice":
        cur = _voice_mode(link)
        def _mk(m, key):
            return {"text": T(lang, key) + (" ✓" if cur == m else ""), "callback_data": "voice:" + m}
        await send_message(token, chat_id, T(lang, "voice_menu"),
                           [[_mk("auto", "b_v_auto"), _mk("on", "b_v_on"), _mk("off", "b_v_off")]])
    elif data.startswith("voice:"):
        mode = data.split(":", 1)[1]
        if mode not in ("auto", "on", "off"):
            mode = "auto"
        await set_user_voice(tg_uid, mode)
        link["voice_reply"] = mode
        _lbl = {"auto": T(lang, "b_v_auto"), "on": T(lang, "b_v_on"), "off": T(lang, "b_v_off")}[mode]
        await send_message(token, chat_id, T(lang, "voice_set", mode=_lbl))
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
        # Enter conversation mode so the next message (and follow-ups) are treated as questions.
        await _set_pending(tg_uid, tenant_id, {"action": "ask_mode"})
        await send_message(token, chat_id, await _ask_opener(link), mkb)
    elif data == "support":
        await _set_pending(tg_uid, tenant_id, {"action": "support_capture"})
        await send_message(token, chat_id, T(lang, "support_prompt"),
                           [[{"text": T(lang, "b_cancel"), "callback_data": "cfm:cancel"}]])
    elif data in ("digest", "digest_on", "digest_off", "digest_now", "digest_team"):
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
            await send_message(token, chat_id, await compose_digest(tenant_id, lang))
        elif data == "digest_team":
            await _digest_team_view(token, chat_id, tenant_id, lang)
        else:
            await _digest_view(token, chat_id, tg_uid, link)
    elif data.startswith("digmem:"):
        if link["role"] in ("owner", "admin"):
            parts = data.split(":")
            try:
                muid = int(parts[1]); act = parts[2]
            except (IndexError, ValueError):
                muid, act = 0, ""
            if muid:
                async with aiosqlite.connect(DB_PATH) as conn:
                    conn.row_factory = aiosqlite.Row
                    ok = await (await conn.execute(
                        "SELECT 1 FROM tg_links WHERE telegram_user_id=? AND tenant_id=? AND status='active'",
                        (muid, tenant_id))).fetchone()
                if ok:
                    await set_digest_pref(muid, tenant_id, act == "on", 9, link.get("agent_id"))
            await _digest_team_view(token, chat_id, tenant_id, lang)
    elif data == "help":
        await send_message(token, chat_id, _help_text(link["role"], lang), _menu_kb(link["role"], lang))
    elif data == "cfm:save":
        p = await _get_pending(tg_uid)
        if not p or p.get("action") == "pick":
            await send_message(token, chat_id, T(lang, "nothing_save"), mkb)
        elif p.get("action") == "create_lead":
            if link["role"] not in ("owner", "admin"):
                await send_message(token, chat_id, T(lang, "only_admin_add"))
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
                    await send_message(token, chat_id, T(lang, "saved_lead", name=p.get('lead_name', '')), mkb)
                except Exception as e:
                    logger.warning("tgcrm create_lead failed: %s", e)
                    await send_message(token, chat_id, T(lang, "save_fail"))
        elif link["role"] not in ("owner", "admin") and p.get("lead_agent") != link.get("agent_id"):
            await send_message(token, chat_id, T(lang, "member_only_own"))
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
                                   T(lang, "saved_move", name=p.get('lead_name', ''),
                                     stage=(p.get('stage') or '').replace('_', ' ')), mkb)
            except Exception as e:
                logger.warning("tgcrm move_stage failed: %s", e)
                await send_message(token, chat_id, T(lang, "save_fail"))
        elif p.get("action") == "assign":
            try:
                async with aiosqlite.connect(DB_PATH) as conn:
                    await conn.execute(
                        "UPDATE leads SET agent_id=?, updated_at=datetime('now') WHERE lead_id=? "
                        "AND agent_id IN (SELECT agent_id FROM agents WHERE tenant_id=?)",
                        (int(p.get("assignee_agent") or 0), int(p["lead_id"]), tenant_id))
                    await conn.commit()
                await _set_pending(tg_uid, tenant_id, None)
                await send_message(token, chat_id,
                                   T(lang, "saved_assign", name=p.get('lead_name', ''),
                                     who=p.get('assignee_name', '')), mkb)
            except Exception as e:
                logger.warning("tgcrm assign failed: %s", e)
                await send_message(token, chat_id, T(lang, "save_fail"))
        else:  # log_note / set_followup
            itype = "followup" if p.get("action") == "set_followup" else "note"
            try:
                await db.log_interaction(
                    int(p["lead_id"]), int(p.get("lead_agent") or link.get("agent_id") or 0),
                    itype, "telegram", p.get("summary", ""),
                    p.get("fud") or None, p.get("fut") or None, link.get("agent_id"))
                await _set_pending(tg_uid, tenant_id, None)
                msg = T(lang, "saved_fu" if itype == "followup" else "saved_note", name=p.get('lead_name', ''))
                await send_message(token, chat_id, msg, mkb)
            except Exception as e:
                logger.warning("tgcrm save failed: %s", e)
                await send_message(token, chat_id, T(lang, "save_fail"))
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
                await send_message(token, chat_id, T(lang, "lead_notfound"), mkb)
        else:
            await send_message(token, chat_id, T(lang, "lead_notfound"), mkb)
    elif data == "cfm:cancel":
        await _set_pending(tg_uid, tenant_id, None)
        await send_message(token, chat_id, T(lang, "cancelled"), mkb)
    elif data == "resume":
        prev = await _get_prev(tg_uid)
        if prev:
            await _set_pending(tg_uid, tenant_id, prev)
            await _clear_prev(tg_uid)
            await _render_confirm(token, chat_id, prev, lang)
        else:
            await send_message(token, chat_id, T(lang, "no_prev"), mkb)
    elif data == "discard_prev":
        await _clear_prev(tg_uid)
        await send_message(token, chat_id, T(lang, "prev_discarded"), mkb)
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

    # Language for pre-link onboarding messages (from Telegram's client locale).
    ulang = "hi" if (from_user.get("language_code", "") or "").lower().startswith("hi") else "en"

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
                newlink = await _active_link(tg_uid)
                glang = _lang(newlink) if newlink else ulang
                greet = (T(glang, "greet_owner", role=role, firm=firm) if role in ("owner", "admin")
                         else T(glang, "greet_member", firm=firm))
                await send_message(token, chat_id, greet)
                if newlink:
                    await _send_menu(token, chat_id, newlink)
            elif res.get("error") == "other_firm":
                await send_message(token, chat_id, T(ulang, "inv_other_firm"))
            elif res.get("error") == "seats_full":
                await send_message(token, chat_id, T(ulang, "inv_seats"))
            else:
                await send_message(token, chat_id, T(ulang, "inv_bad"))
            return {"ok": True}
        await send_message(token, chat_id, T(ulang, "ask_admin_invite"))
        return {"ok": True}

    # Non-/start messages — only ACTIVE, LINKED members of THIS firm get a response.
    link = await _active_link(tg_uid)
    if not (link and int(link["tenant_id"]) == tenant_id):
        await send_message(token, chat_id, T(ulang, "not_linked"))
        return {"ok": True}
    lang = _lang(link)
    if is_voice:
        v = msg.get("voice") or msg.get("audio") or {}
        if int(v.get("duration") or 0) > 150:
            await send_message(token, chat_id, T(lang, "v_long"), _menu_kb(link["role"], lang))
            return {"ok": True}
        await send_message(token, chat_id, T(lang, "v_listen"))
        audio = await _download_file(token, v.get("file_id"))
        tr = await _transcribe(audio, v.get("mime_type") or "audio/ogg") if audio else None
        if not tr or tr.get("status") != "clear" or not (tr.get("transcript") or "").strip():
            st = (tr or {}).get("status", "unclear")
            emap = {"silent": "v_silent", "noisy": "v_noisy", "unclear": "v_unclear",
                    "abusive": "v_abusive", "nonsense": "v_nonsense"}
            await send_message(token, chat_id, T(lang, emap.get(st, "v_unclear")) + T(lang, "v_retry"),
                               _menu_kb(link["role"], lang))
            return {"ok": True}
        await send_message(token, chat_id, T(lang, "v_heard", text=tr['transcript']))
        await _process_command(token, chat_id, tg_uid, link, tr["transcript"], is_voice=True)
        return {"ok": True}
    # Typed message → try a CRM command; falls back to the menu if it's not one.
    await _process_command(token, chat_id, tg_uid, link, text, is_voice=False)
    return {"ok": True}
