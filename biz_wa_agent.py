# =============================================================================
#  biz_wa_agent.py — Sarathi-AI: APK-Bridge WhatsApp Automation Engine
# =============================================================================
#
#  Manages the lifecycle of Sarathi Agent APK connections:
#    • Device registration & secure token authentication
#    • Persistent WebSocket connection registry (in-memory)
#    • Incoming customer message handling → AI reply via Gemini
#    • Agent self-message parsing → CRM commands (voice/text)
#    • Risk mitigations: rate limits, business hours, takeover keywords,
#      human-like delays, daily caps, auto-reply footer
#    • Offline queue: pending messages stored in DB, delivered on reconnect
#    • Conversation audit log: every message in/out stored in DB
#
#  Architecture:
#    APK (Kotlin) ──WSS──▶ /ws/agent ──▶ biz_wa_agent.py ──▶ Gemini AI
#                                                          ──▶ SQLite CRM
#
# =============================================================================

import asyncio
import base64
import hashlib
import hmac as _hmac
import json
import logging
import os
import random
import secrets
import time
from datetime import datetime, date
from typing import Optional, Dict, Any

import aiosqlite
import pytz

import biz_database as db
import biz_ai as ai

logger = logging.getLogger("sarathi.wa_agent")

# =============================================================================
#  IN-MEMORY REGISTRIES
# =============================================================================

# Maps device_id → WebSocket connection (live connections only)
_live_connections: Dict[int, Any] = {}

# Maps device_id → {hourly_count, hourly_window_start, daily_count, daily_date}
_rate_state: Dict[int, dict] = {}

# =============================================================================
#  CONSTANTS & DEFAULTS
# =============================================================================

DEFAULT_TAKEOVER_KEYWORDS = [
    "complaint", "refund", "fraud", "legal", "police", "court", "irda",
    "angry", "scam", "mislead", "cancel policy", "death claim",
    "cheated", "false claim", "consumer forum", "lawyer", "sue",
]

MAX_DAILY_MSGS_DEFAULT = 200
MAX_HOURLY_MSGS_DEFAULT = 20
REPLY_DELAY_MIN = 1.5   # seconds — human-like pause before auto-reply
REPLY_DELAY_MAX = 4.0   # seconds
HEARTBEAT_INTERVAL = 30  # seconds — ping from server to APK
HEARTBEAT_TIMEOUT = 90   # seconds — mark offline after this silence

IST = pytz.timezone("Asia/Kolkata")


# =============================================================================
#  DEVICE CREDENTIAL MANAGEMENT
# =============================================================================

async def generate_device_credentials(tenant_id: int, agent_id: int) -> dict:
    """
    Generate a new device token + HMAC key for an agent.
    Revokes any existing active device for this agent first.
    Returns QR payload (base64) that the APK scans.
    """
    # Generate a 64-char hex token (shown once, user never sees the hash)
    token = secrets.token_hex(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    hmac_key = secrets.token_hex(32)   # 64-char hex key for HMAC-SHA256 signing

    # Build WSS URL from environment
    server_url = os.getenv("SERVER_URL", "https://sarathi-ai.com").rstrip("/")
    ws_url = server_url.replace("https://", "wss://").replace("http://", "ws://") + "/ws/agent"

    async with aiosqlite.connect(db.DB_PATH) as conn:
        # Revoke any existing active device for this agent
        await conn.execute(
            "UPDATE wa_agent_devices SET status='revoked', connected=0 "
            "WHERE agent_id=? AND tenant_id=? AND status IN ('active','pending')",
            (agent_id, tenant_id),
        )
        # Create new pending device
        cur = await conn.execute(
            "INSERT INTO wa_agent_devices (tenant_id, agent_id, token_hash, hmac_key, status) "
            "VALUES (?, ?, ?, ?, 'pending')",
            (tenant_id, agent_id, token_hash, hmac_key),
        )
        device_id = cur.lastrowid
        await conn.commit()

    # QR payload — scanned by APK's onboarding screen
    qr_payload = {
        "v": 1,               # schema version
        "d": device_id,
        "t": token,
        "k": hmac_key,
        "u": ws_url,
    }
    qr_data = base64.b64encode(json.dumps(qr_payload, separators=(",", ":")).encode()).decode()

    logger.info("Device credentials generated: device_id=%d tenant=%d agent=%d",
                device_id, tenant_id, agent_id)
    return {
        "device_id": device_id,
        "qr_data": qr_data,
        "ws_url": ws_url,
        "expires_in": 300,   # QR valid for 5 minutes
    }


async def authenticate_device(device_id: int, token: str) -> Optional[dict]:
    """
    Verify a device token on WebSocket connect.
    Returns the full device row or None if invalid/revoked.
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM wa_agent_devices WHERE device_id=? AND token_hash=? "
            "AND status IN ('active','pending')",
            (device_id, token_hash),
        )
        row = await cur.fetchone()
        if row:
            return dict(row)
    return None


async def mark_device_active(device_id: int, device_model: str = None,
                             android_version: str = None):
    """Mark device as active+connected on first successful WebSocket auth."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE wa_agent_devices SET status='active', connected=1, "
            "last_seen_at=datetime('now'), "
            "device_model=COALESCE(?,device_model), "
            "android_version=COALESCE(?,android_version) "
            "WHERE device_id=?",
            (device_model, android_version, device_id),
        )
        await conn.commit()


async def mark_device_offline(device_id: int):
    """Mark device as disconnected."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE wa_agent_devices SET connected=0, last_seen_at=datetime('now') "
            "WHERE device_id=?",
            (device_id,),
        )
        await conn.commit()


async def update_heartbeat(device_id: int):
    """Update last_seen_at on heartbeat ping."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE wa_agent_devices SET last_seen_at=datetime('now') WHERE device_id=?",
            (device_id,),
        )
        await conn.commit()


async def revoke_device(tenant_id: int, agent_id: int) -> bool:
    """Revoke the active device for an agent. Closes live connection if any.
    If agent_id=0, revokes any active device for this tenant."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if agent_id:
            cur = await conn.execute(
                "SELECT device_id FROM wa_agent_devices "
                "WHERE tenant_id=? AND agent_id=? AND status='active'",
                (tenant_id, agent_id),
            )
        else:
            cur = await conn.execute(
                "SELECT device_id FROM wa_agent_devices "
                "WHERE tenant_id=? AND status='active'",
                (tenant_id,),
            )
        row = await cur.fetchone()
        if not row:
            return False
        device_id = row["device_id"]
        # Close live WebSocket if present
        ws = _live_connections.pop(device_id, None)
        if ws:
            try:
                await ws.close(code=4001)
            except Exception:
                pass
        _rate_state.pop(device_id, None)
        await conn.execute(
            "UPDATE wa_agent_devices SET status='revoked', connected=0 WHERE device_id=?",
            (device_id,),
        )
        await conn.commit()
        logger.info("Device %d revoked (tenant=%d, agent=%d)", device_id, tenant_id, agent_id)
        return True


async def get_device_status(tenant_id: int, agent_id: int) -> Optional[dict]:
    """Get the active device for an agent with live connection status.
    If agent_id=0 (owner without agent record), queries by tenant_id only."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if agent_id:
            cur = await conn.execute(
                "SELECT device_id, status, connected, device_model, android_version, "
                "agent_name, agent_phone, auto_reply_enabled, business_hours, "
                "max_daily_msgs, max_hourly_msgs, daily_msg_count, daily_msg_date, "
                "last_seen_at, created_at "
                "FROM wa_agent_devices "
                "WHERE tenant_id=? AND agent_id=? AND status='active' "
                "ORDER BY created_at DESC LIMIT 1",
                (tenant_id, agent_id),
            )
        else:
            cur = await conn.execute(
                "SELECT device_id, status, connected, device_model, android_version, "
                "agent_name, agent_phone, auto_reply_enabled, business_hours, "
                "max_daily_msgs, max_hourly_msgs, daily_msg_count, daily_msg_date, "
                "last_seen_at, created_at "
                "FROM wa_agent_devices "
                "WHERE tenant_id=? AND status='active' "
                "ORDER BY created_at DESC LIMIT 1",
                (tenant_id,),
            )
        row = await cur.fetchone()
        if row:
            d = dict(row)
            d["is_live"] = d["device_id"] in _live_connections
            return d
    return None


async def update_device_settings(tenant_id: int, agent_id: int,
                                 auto_reply: bool = None,
                                 business_hours: dict = None,
                                 takeover_keywords: list = None,
                                 max_daily: int = None,
                                 max_hourly: int = None) -> bool:
    """Update per-device settings from the dashboard."""
    parts = []
    params = []
    if auto_reply is not None:
        parts.append("auto_reply_enabled=?")
        params.append(1 if auto_reply else 0)
    if business_hours is not None:
        parts.append("business_hours=?")
        params.append(json.dumps(business_hours))
    if takeover_keywords is not None:
        parts.append("takeover_keywords=?")
        params.append(json.dumps(takeover_keywords))
    if max_daily is not None:
        parts.append("max_daily_msgs=?")
        params.append(max(1, min(500, max_daily)))
    if max_hourly is not None:
        parts.append("max_hourly_msgs=?")
        params.append(max(1, min(60, max_hourly)))
    if not parts:
        return False
    params += [tenant_id, agent_id]
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            f"UPDATE wa_agent_devices SET {', '.join(parts)} "
            f"WHERE tenant_id=? AND agent_id=? AND status='active'",
            params,
        )
        await conn.commit()
    return True


# =============================================================================
#  HMAC SIGNING (message integrity + authentication)
# =============================================================================

def sign_message(raw_json: str, hmac_key_hex: str) -> str:
    """HMAC-SHA256 sign a raw JSON string. Returns hex signature."""
    return _hmac.new(
        bytes.fromhex(hmac_key_hex),
        raw_json.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_message(raw_json: str, hmac_key_hex: str, signature: str) -> bool:
    """Verify HMAC-SHA256 signature. Constant-time comparison prevents timing attacks."""
    expected = sign_message(raw_json, hmac_key_hex)
    return _hmac.compare_digest(expected, signature)


def _send_signed(payload: dict, hmac_key: str) -> str:
    """
    Serialize payload to JSON, sign it, return the envelope string.
    Caller does: await ws.send_text(envelope)
    """
    payload_str = json.dumps(payload, separators=(",", ":"))
    sig = sign_message(payload_str, hmac_key)
    return json.dumps({"p": payload_str, "s": sig})


# =============================================================================
#  RISK MITIGATION — RATE LIMITING
# =============================================================================

def _get_rate(device_id: int) -> dict:
    """Get or initialise in-memory rate state for a device."""
    if device_id not in _rate_state:
        _rate_state[device_id] = {
            "hourly_count": 0,
            "hourly_window_start": time.monotonic(),
            "daily_count": 0,
            "daily_date": datetime.now(IST).strftime("%Y-%m-%d"),
        }
    return _rate_state[device_id]


def check_rate_limit(device_id: int,
                     max_hourly: int = MAX_HOURLY_MSGS_DEFAULT,
                     max_daily: int = MAX_DAILY_MSGS_DEFAULT) -> tuple:
    """
    Check and increment counters.
    Returns (allowed: bool, reason: str).
    Thread-safe for single-threaded asyncio event loop.
    """
    state = _get_rate(device_id)
    now = time.monotonic()
    today = datetime.now(IST).strftime("%Y-%m-%d")

    # Reset hourly counter when window rolls over
    if now - state["hourly_window_start"] >= 3600:
        state["hourly_count"] = 0
        state["hourly_window_start"] = now

    # Reset daily counter when date changes (IST)
    if state["daily_date"] != today:
        state["daily_count"] = 0
        state["daily_date"] = today

    if state["daily_count"] >= max_daily:
        return False, f"daily_limit_reached:{max_daily}"
    if state["hourly_count"] >= max_hourly:
        return False, f"hourly_limit_reached:{max_hourly}"

    state["daily_count"] += 1
    state["hourly_count"] += 1
    return True, "ok"


# =============================================================================
#  RISK MITIGATION — BUSINESS HOURS
# =============================================================================

def is_business_hours(hours_config: dict) -> tuple:
    """
    Check current IST time against configured business hours.
    Returns (in_hours: bool, reason: str).
    hours_config: {"start": 9, "end": 20, "days": [0,1,2,3,4,5,6]}
    """
    try:
        now_ist = datetime.now(IST)
        hour = now_ist.hour
        weekday = now_ist.weekday()   # 0=Mon … 6=Sun
        start = int(hours_config.get("start", 9))
        end = int(hours_config.get("end", 20))
        days = hours_config.get("days", list(range(7)))
        if weekday not in days:
            return False, "off_day"
        if hour < start or hour >= end:
            return False, "after_hours"
        return True, "ok"
    except Exception:
        return True, "ok"   # default open on error


# =============================================================================
#  RISK MITIGATION — TAKEOVER KEYWORD DETECTION
# =============================================================================

def detect_takeover(message: str, keywords: list) -> Optional[str]:
    """
    Check if message contains any keyword that should pause AI and alert advisor.
    Returns matched keyword or None.
    """
    msg_lower = message.lower()
    for kw in keywords:
        if kw.lower() in msg_lower:
            return kw
    return None


# =============================================================================
#  AI REPLY GENERATION
# =============================================================================

async def get_customer_ai_reply(device: dict, sender_name: str, message: str,
                                firm_name: str = "your advisor",
                                agent_name: str = "the advisor") -> Optional[str]:
    """
    Generate a safe, professional AI reply for an incoming customer message.
    Returns the reply string, or None if AI fails (caller must not send broken reply).
    """
    try:
        prompt = f"""You are a helpful WhatsApp assistant for {agent_name} from {firm_name}, an Indian insurance/financial advisor.

A customer named "{sender_name}" sent this message:
"{message}"

Reply as the advisor's professional assistant. Strict rules:
- Keep reply to 2–3 sentences maximum
- Be warm and professional in Indian English or Hindi/Hinglish (match customer's language)
- For policy/claim queries: say you will confirm with the advisor shortly
- For appointments/meetings: offer to check and confirm
- For EMI/premium reminders: acknowledge and say advisor will follow up
- NEVER promise specific policy terms, claim amounts, or financial outcomes
- NEVER provide regulatory or legal advice
- Add a line break then this footer exactly: "— {firm_name} 🙏"
- Add a second footer on its own line: "_Powered by Sarathi-AI_"

Respond with only the WhatsApp message text. No JSON, no explanation."""

        reply = await ai._ask_gemini(prompt)
        if not reply:
            return None

        # Ensure the Sarathi-AI footer is always present (identifies AI content)
        if "Powered by Sarathi-AI" not in reply:
            reply = reply.rstrip() + "\n\n_Powered by Sarathi-AI_"
        return reply

    except Exception as e:
        logger.error("Customer AI reply failed for device %d: %s", device.get("device_id"), e)
        return None


async def parse_crm_command(message: str, agent_id: int, tenant_id: int) -> dict:
    """
    Parse an agent's self-message (text or voice transcript) as a CRM command.
    Returns parsed intent dict.
    """
    try:
        prompt = f"""You are a CRM assistant for an Indian insurance/financial advisor using Sarathi-AI.
Parse this natural language message (may be Hindi, English, or Hinglish) into a structured CRM command.

MESSAGE: "{message}"

Return ONLY valid JSON:
{{
  "action": "<one of: create_lead | get_pipeline | get_tasks | get_followups | unknown>",
  "name": "<person name if mentioned, else null>",
  "phone": "<10-digit phone if mentioned, else null>",
  "city": "<city if mentioned, else null>",
  "interest": "<insurance/investment type if mentioned, else null>",
  "budget": "<budget amount in words/numbers if mentioned, else null>",
  "follow_up_date": "<YYYY-MM-DD if mentioned, else null>",
  "notes": "<any additional notes, else null>",
  "response_text": "<friendly Hindi/English confirmation of what you understood, 1-2 lines>"
}}"""
        raw = await ai._ask_gemini(prompt, json_mode=True)
        return ai._clean_json(raw)
    except Exception as e:
        logger.error("CRM command parse failed: %s", e)
        return {
            "action": "unknown",
            "response_text": "Maafi, yeh command samajh nahi aaya. Dobara try karein. 🙏",
        }


# =============================================================================
#  CRM ACTION EXECUTORS
# =============================================================================

async def get_pipeline_summary(agent_id: int) -> str:
    """Return a WhatsApp-formatted pipeline summary for the agent."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT stage, COUNT(*) as cnt FROM leads WHERE agent_id=? GROUP BY stage",
                (agent_id,),
            )
            rows = await cur.fetchall()
            if not rows:
                return "📊 Pipeline mein koi lead nahi hai abhi."
            emoji = {
                "prospect": "🔵", "contacted": "📞", "pitched": "🎯",
                "proposal_sent": "📄", "negotiation": "🤝",
                "closed_won": "✅", "closed_lost": "❌",
            }
            lines = ["📊 *Aapka Pipeline:*\n"]
            total = 0
            for r in rows:
                e = emoji.get(r["stage"], "•")
                label = r["stage"].replace("_", " ").title()
                lines.append(f"{e} {label}: {r['cnt']}")
                total += r["cnt"]
            lines.append(f"\n*Total: {total} leads*")
            return "\n".join(lines)
    except Exception as e:
        logger.error("Pipeline summary error: %s", e)
        return "❌ Pipeline data abhi available nahi. Baad mein try karein."


async def get_tasks_summary(agent_id: int) -> str:
    """Return today's pending follow-ups for the agent."""
    try:
        today = date.today().isoformat()
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                """SELECT i.follow_up_date, l.name AS lead_name, i.summary
                   FROM interactions i
                   JOIN leads l ON i.lead_id = l.lead_id
                   WHERE i.assigned_to_agent_id=? AND date(i.follow_up_date)=?
                     AND i.follow_up_status='pending'
                   ORDER BY i.follow_up_date ASC LIMIT 10""",
                (agent_id, today),
            )
            rows = await cur.fetchall()
            if not rows:
                return "✅ Aaj ke liye koi pending task nahi! Badiya! 🎉"
            lines = [f"📋 *Aaj ke Tasks ({today}):*\n"]
            for r in rows:
                summary = (r["summary"] or "Follow up karna hai")[:60]
                lines.append(f"• {r['lead_name']}: {summary}")
            return "\n".join(lines)
    except Exception as e:
        logger.error("Tasks summary error: %s", e)
        return "❌ Tasks abhi available nahi."


async def create_lead_from_command(agent_id: int, parsed: dict):
    """Create a new lead from a parsed voice/text CRM command."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO leads "
                "(agent_id, name, phone, city, need_type, premium_budget, notes, stage, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'prospect', 'wa_agent')",
                (
                    agent_id,
                    parsed.get("name"),
                    parsed.get("phone"),
                    parsed.get("city"),
                    parsed.get("interest"),
                    parsed.get("budget"),
                    parsed.get("notes"),
                ),
            )
            await conn.commit()
    except Exception as e:
        logger.error("Create lead from WA command failed: %s", e)


# =============================================================================
#  OFFLINE MESSAGE QUEUE
# =============================================================================

async def queue_pending(device_id: int, event_type: str, payload: dict):
    """Enqueue a message for delivery when device comes back online."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO wa_agent_pending (device_id, event_type, payload_json) VALUES (?,?,?)",
                (device_id, event_type, json.dumps(payload)),
            )
            await conn.commit()
    except Exception as e:
        logger.error("Queue pending failed: %s", e)


async def deliver_pending(device_id: int, ws, hmac_key: str):
    """Flush queued messages to a newly reconnected device."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT pending_id, event_type, payload_json FROM wa_agent_pending "
                "WHERE device_id=? AND deliver_after<=datetime('now') "
                "ORDER BY created_at ASC LIMIT 50",
                (device_id,),
            )
            rows = await cur.fetchall()
            delivered = []
            for row in rows:
                try:
                    payload = json.loads(row["payload_json"])
                    envelope = _send_signed(payload, hmac_key)
                    await ws.send_text(envelope)
                    delivered.append(row["pending_id"])
                except Exception:
                    pass
            if delivered:
                placeholders = ",".join("?" * len(delivered))
                await conn.execute(
                    f"DELETE FROM wa_agent_pending WHERE pending_id IN ({placeholders})",
                    delivered,
                )
                await conn.commit()
                logger.info("Delivered %d queued messages to device %d", len(delivered), device_id)
    except Exception as e:
        logger.error("Deliver pending failed: %s", e)


# =============================================================================
#  CONVERSATION LOGGING
# =============================================================================

async def log_conv(device_id: int, tenant_id: int, sender_name: str,
                   sender_phone: str, direction: str, message: str,
                   msg_type: str = "text", ai_reply: str = None,
                   intent: str = None, auto_handled: bool = True,
                   takeover_triggered: bool = False):
    """Persist a conversation record. Swallows errors — never block the main flow."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO wa_agent_conversations "
                "(device_id, tenant_id, sender_name, sender_phone, direction, msg_type, "
                "message, ai_reply, intent, auto_handled, takeover_triggered) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (device_id, tenant_id, sender_name, sender_phone, direction, msg_type,
                 message, ai_reply, intent,
                 1 if auto_handled else 0,
                 1 if takeover_triggered else 0),
            )
            await conn.commit()
    except Exception as e:
        logger.debug("log_conv error: %s", e)


async def get_recent_conversations(tenant_id: int, agent_id: int,
                                   limit: int = 100) -> list:
    """Fetch recent conversations for the dashboard view."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            if agent_id:
                cur = await conn.execute(
                    """SELECT c.conv_id, c.sender_name, c.sender_phone, c.direction,
                              c.msg_type, c.message, c.ai_reply, c.intent,
                              c.auto_handled, c.takeover_triggered, c.created_at
                       FROM wa_agent_conversations c
                       JOIN wa_agent_devices d ON c.device_id = d.device_id
                       WHERE c.tenant_id=? AND d.agent_id=?
                       ORDER BY c.created_at DESC LIMIT ?""",
                    (tenant_id, agent_id, limit),
                )
            else:
                cur = await conn.execute(
                    """SELECT c.conv_id, c.sender_name, c.sender_phone, c.direction,
                              c.msg_type, c.message, c.ai_reply, c.intent,
                              c.auto_handled, c.takeover_triggered, c.created_at
                       FROM wa_agent_conversations c
                       WHERE c.tenant_id=?
                       ORDER BY c.created_at DESC LIMIT ?""",
                    (tenant_id, limit),
                )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("get_recent_conversations error: %s", e)
        return []


async def get_conversation_stats(tenant_id: int, agent_id: int) -> dict:
    """Stats for the dashboard (today's counts)."""
    try:
        today = date.today().isoformat()
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            if agent_id:
                cur = await conn.execute(
                    """SELECT
                         COUNT(*) FILTER (WHERE date(c.created_at)=? AND c.direction='in') AS incoming_today,
                         COUNT(*) FILTER (WHERE date(c.created_at)=? AND c.auto_handled=1) AS auto_replied_today,
                         COUNT(*) FILTER (WHERE c.takeover_triggered=1) AS total_takeovers,
                         COUNT(*) AS total_messages
                       FROM wa_agent_conversations c
                       JOIN wa_agent_devices d ON c.device_id = d.device_id
                       WHERE c.tenant_id=? AND d.agent_id=?""",
                    (today, today, tenant_id, agent_id),
                )
            else:
                cur = await conn.execute(
                    """SELECT
                         COUNT(*) FILTER (WHERE date(c.created_at)=? AND c.direction='in') AS incoming_today,
                         COUNT(*) FILTER (WHERE date(c.created_at)=? AND c.auto_handled=1) AS auto_replied_today,
                         COUNT(*) FILTER (WHERE c.takeover_triggered=1) AS total_takeovers,
                         COUNT(*) AS total_messages
                       FROM wa_agent_conversations c
                       WHERE c.tenant_id=?""",
                    (today, today, tenant_id),
                )
            row = await cur.fetchone()
            return dict(row) if row else {}
    except Exception as e:
        logger.error("get_conversation_stats error: %s", e)
        return {}


# =============================================================================
#  MAIN EVENT DISPATCHER — called from WebSocket handler in sarathi_biz.py
# =============================================================================

async def handle_apk_event(device: dict, event: dict, ws,
                           firm_name: str = "your advisor"):
    """
    Process a single event from the APK.
    Risk mitigations applied here:
      • Business hours check (INCOMING_MESSAGE only)
      • Takeover keyword detection
      • Rate limiting (hourly + daily)
      • Human-like reply delay (1.5–4 s)
      • AI failure safety (no broken reply sent if AI fails)
    """
    device_id = device["device_id"]
    tenant_id = device["tenant_id"]
    agent_id = device["agent_id"]
    hmac_key = device["hmac_key"]
    agent_name = device.get("agent_name") or "the advisor"

    takeover_kws = []
    try:
        takeover_kws = json.loads(device.get("takeover_keywords") or "[]")
    except Exception:
        pass
    if not takeover_kws:
        takeover_kws = DEFAULT_TAKEOVER_KEYWORDS

    hours_config = {"start": 9, "end": 20, "days": list(range(7))}
    try:
        hours_config = json.loads(device.get("business_hours") or "{}")
    except Exception:
        pass

    max_hourly = int(device.get("max_hourly_msgs") or MAX_HOURLY_MSGS_DEFAULT)
    max_daily = int(device.get("max_daily_msgs") or MAX_DAILY_MSGS_DEFAULT)
    auto_reply_on = bool(device.get("auto_reply_enabled", 1))

    event_type = event.get("type", "")

    # ── INCOMING_MESSAGE: customer sent a message to the advisor ─────────────
    if event_type == "INCOMING_MESSAGE":
        sender = event.get("sender", "Customer")
        message = event.get("message", "").strip()
        conv_id = event.get("conversationId", "")
        msg_type = event.get("messageType", "text")
        sender_phone = event.get("senderPhone", "")

        if not message:
            return

        # ── 1. Business hours check ──────────────────────────────────────────
        in_hours, hours_reason = is_business_hours(hours_config)
        if not in_hours and auto_reply_on:
            start_h = hours_config.get("start", 9)
            end_h = hours_config.get("end", 20)
            after_hours_reply = (
                f"Namaste! 🙏 Hum abhi available nahi hain.\n"
                f"Hamara samay: {start_h}:00 – {end_h}:00 IST.\n"
                f"Aapka message mil gaya hai. Hum jald hi contact karenge.\n\n"
                f"— {firm_name} 🙏\n_Powered by Sarathi-AI_"
            )
            envelope = _send_signed({
                "type": "SEND_REPLY",
                "conversationId": conv_id,
                "text": after_hours_reply,
            }, hmac_key)
            await ws.send_text(envelope)
            await log_conv(device_id, tenant_id, sender, sender_phone, "in", message,
                           msg_type=msg_type, auto_handled=False, intent="after_hours")
            return

        # ── 2. Takeover keyword detection ────────────────────────────────────
        matched_kw = detect_takeover(message, takeover_kws)
        if matched_kw:
            # Pause AI — alert advisor via SEND_TO_SELF
            alert_text = (
                f"🚨 *Takeover Alert!*\n\n"
                f"Customer *{sender}* ne kuch sensitive likha:\n"
                f"_{message[:200]}_\n\n"
                f"Trigger word: `{matched_kw}`\n\n"
                f"⚠️ AI auto-reply is paused. Please respond manually.\n"
                f"_Powered by Sarathi-AI_"
            )
            envelope = _send_signed({"type": "SEND_TO_SELF", "text": alert_text}, hmac_key)
            await ws.send_text(envelope)
            await log_conv(device_id, tenant_id, sender, sender_phone, "in", message,
                           msg_type=msg_type, auto_handled=False,
                           takeover_triggered=True, intent=f"takeover:{matched_kw}")
            logger.warning("Takeover triggered device=%d kw=%r sender=%s", device_id, matched_kw, sender)
            return

        # ── 3. Skip AI if disabled ───────────────────────────────────────────
        if not auto_reply_on:
            await log_conv(device_id, tenant_id, sender, sender_phone, "in", message,
                           msg_type=msg_type, auto_handled=False, intent="ai_disabled")
            return

        # ── 4. Rate limiting ─────────────────────────────────────────────────
        allowed, rate_reason = check_rate_limit(device_id, max_hourly, max_daily)
        if not allowed:
            logger.info("Rate limit device=%d reason=%s", device_id, rate_reason)
            await log_conv(device_id, tenant_id, sender, sender_phone, "in", message,
                           msg_type=msg_type, auto_handled=False, intent=f"rate_limited")
            return

        # ── 5. Human-like delay ──────────────────────────────────────────────
        delay = random.uniform(REPLY_DELAY_MIN, REPLY_DELAY_MAX)
        await asyncio.sleep(delay)

        # ── 6. Generate AI reply (safe — never send broken reply) ────────────
        reply_text = await get_customer_ai_reply(
            device, sender, message, firm_name=firm_name, agent_name=agent_name
        )
        if not reply_text:
            # AI failed — log, but DON'T send a broken reply
            await log_conv(device_id, tenant_id, sender, sender_phone, "in", message,
                           msg_type=msg_type, auto_handled=False, intent="ai_error")
            logger.error("AI reply unavailable for device %d — message NOT auto-replied", device_id)
            return

        # ── 7. Send the reply ─────────────────────────────────────────────────
        envelope = _send_signed({
            "type": "SEND_REPLY",
            "conversationId": conv_id,
            "text": reply_text,
        }, hmac_key)
        await ws.send_text(envelope)
        await log_conv(device_id, tenant_id, sender, sender_phone, "in", message,
                       msg_type=msg_type, ai_reply=reply_text, auto_handled=True,
                       intent="customer_query")

    # ── AGENT_COMMAND: advisor messaged their own number (CRM command) ────────
    elif event_type == "AGENT_COMMAND":
        message = event.get("message", "").strip()
        msg_type = event.get("messageType", "text")
        agent_phone = device.get("agent_phone", "")

        if not message:
            return

        parsed = await parse_crm_command(message, agent_id, tenant_id)
        action = parsed.get("action", "unknown")
        response_text = parsed.get("response_text", "Samajh gaya! ✅")

        # Execute CRM action
        if action == "get_pipeline":
            response_text = await get_pipeline_summary(agent_id)
        elif action == "get_tasks" or action == "get_followups":
            response_text = await get_tasks_summary(agent_id)
        elif action == "create_lead" and parsed.get("name"):
            await create_lead_from_command(agent_id, parsed)
            name = parsed.get("name", "")
            phone = parsed.get("phone", "N/A")
            interest = parsed.get("interest", "N/A")
            fu = parsed.get("follow_up_date", "")
            response_text = (
                f"✅ *Lead banaya!*\n\n"
                f"👤 Naam: {name}\n"
                f"📱 Phone: {phone}\n"
                f"💼 Interest: {interest}\n"
                + (f"📅 Follow-up: {fu}" if fu else "")
            )

        # Send result to agent's own WA number via APK
        envelope = _send_signed({
            "type": "SEND_TO_SELF",
            "text": f"🤖 *Sarathi CRM*\n\n{response_text}\n\n_Powered by Sarathi-AI_",
        }, hmac_key)
        await ws.send_text(envelope)
        await log_conv(device_id, tenant_id, agent_name, agent_phone, "self", message,
                       msg_type=msg_type, ai_reply=response_text, intent=action, auto_handled=True)

    # ── DEVICE_INFO: APK sends device metadata after connect ─────────────────
    elif event_type == "DEVICE_INFO":
        model = event.get("model", "")
        android = event.get("android", "")
        agent_name_apk = event.get("agentName", "")
        agent_phone_apk = event.get("agentPhone", "")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE wa_agent_devices SET device_model=?, android_version=?, "
                "agent_name=?, agent_phone=? WHERE device_id=?",
                (model, android, agent_name_apk, agent_phone_apk, device_id),
            )
            await conn.commit()
        logger.info("Device info updated: device=%d model=%s android=%s", device_id, model, android)

    # ── DEVICE_HEARTBEAT: APK ping ────────────────────────────────────────────
    elif event_type == "DEVICE_HEARTBEAT":
        await update_heartbeat(device_id)

    else:
        logger.debug("Unknown event type from device %d: %s", device_id, event_type)


# =============================================================================
#  AUTH HELPER — used by sarathi_biz.py route handlers
# =============================================================================

async def _get_agent_from_request(request) -> tuple:
    """
    Extract (tenant_id, agent_id) from a JWT bearer token.
    - Uses 'sub' for tenant_id and 'aid' for agent_id (correct JWT keys).
    - Falls back to DB lookup if 'aid' not in token (owner logins via web).
    - Returns (0, 0) if unauthenticated.
    """
    try:
        import biz_auth as auth
        import jwt as _jwt
        token = auth._extract_token(request)
        if not token:
            return 0, 0
        payload = _jwt.decode(
            token, auth.JWT_SECRET,
            algorithms=[auth.JWT_ALGORITHM],
            options={"verify_exp": True},
        )
        tenant_id = int(payload.get("sub", 0))
        if not tenant_id:
            return 0, 0
        # JWT uses 'aid', not 'agent_id'
        agent_id = int(payload.get("aid") or 0)
        # If owner login has no 'aid', look up their agent record by phone
        if not agent_id:
            phone = payload.get("phone", "")
            if phone:
                try:
                    async with aiosqlite.connect(db.DB_PATH) as conn:
                        conn.row_factory = aiosqlite.Row
                        cur = await conn.execute(
                            "SELECT agent_id FROM agents "
                            "WHERE tenant_id=? AND phone=? AND is_active=1 "
                            "ORDER BY agent_id ASC LIMIT 1",
                            (tenant_id, phone),
                        )
                        row = await cur.fetchone()
                        if row:
                            agent_id = row["agent_id"]
                except Exception:
                    pass
        return tenant_id, agent_id
    except Exception:
        return 0, 0


async def _get_firm_name(tenant_id: int) -> str:
    """Look up firm name for AI context."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT firm_name FROM tenants WHERE tenant_id=?", (tenant_id,)
            )
            row = await cur.fetchone()
            return row["firm_name"] if row else "your advisor"
    except Exception:
        return "your advisor"
