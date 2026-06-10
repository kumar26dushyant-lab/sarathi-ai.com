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

async def generate_device_credentials(tenant_id: int, agent_id: int, phone: str = "") -> dict:
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
        "p": phone,           # advisor's phone for self-message detection
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

# ── Conversation history & lead context helpers ───────────────────────────────

async def get_conversation_history(instance_id: int, phone: str, limit: int = 5) -> list:
    """Return last `limit` messages for a conversation as list of dicts."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT direction, content, sent_at FROM wa_messages "
                "WHERE instance_id=? AND conversation_id=("
                "  SELECT conversation_id FROM wa_conversations "
                "  WHERE instance_id=? AND customer_phone=? LIMIT 1"
                ") ORDER BY sent_at DESC LIMIT ?",
                (instance_id, instance_id, phone, limit))
            rows = await cur.fetchall()
            return [{"role": "lead" if r["direction"] == "in" else "advisor",
                     "text": r["content"] or "", "at": r["sent_at"]} for r in reversed(rows)]
    except Exception as e:
        logger.error("get_conversation_history error: %s", e)
        return []


async def get_lead_context_for_phone(tenant_id: int, phone: str) -> dict:
    """Return lead profile (name, interest, budget, stage, past notes) matched by phone."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            # Match phone digits (last 10) against leads.phone or leads.whatsapp
            digits = "".join(c for c in (phone or "") if c.isdigit())[-10:]
            cur = await conn.execute(
                "SELECT l.lead_id, l.name, l.phone, l.need_type, l.premium_budget, "
                "l.stage, l.notes, l.city, l.occupation "
                "FROM leads l JOIN agents a ON a.agent_id = l.agent_id "
                "WHERE a.tenant_id=? AND ("
                "  SUBSTR(REPLACE(REPLACE(l.phone,'+',''),' ',''),-10)=? OR "
                "  SUBSTR(REPLACE(REPLACE(l.whatsapp,'+',''),' ',''),-10)=?"
                ") ORDER BY l.created_at DESC LIMIT 1",
                (tenant_id, digits, digits))
            row = await cur.fetchone()
            if not row:
                return {}
            lead = dict(row)
            # Get last 3 interaction notes
            cur2 = await conn.execute(
                "SELECT type, summary, follow_up_date FROM interactions "
                "WHERE lead_id=? ORDER BY created_at DESC LIMIT 3",
                (lead["lead_id"],))
            notes = await cur2.fetchall()
            lead["past_notes"] = [{"type": n["type"], "summary": n["summary"],
                                    "date": n["follow_up_date"]} for n in notes]
            # Get last 3 active policies so the AI can answer "premium kab hai" /
            # "claim status" / "renewal date" questions factually instead of
            # escalating to the advisor.
            cur3 = await conn.execute(
                "SELECT policy_number, insurer, plan_name, policy_type, sum_insured, "
                "premium, premium_mode, renewal_date, end_date, status "
                "FROM policies WHERE lead_id=? AND status='active' "
                "ORDER BY renewal_date ASC LIMIT 3",
                (lead["lead_id"],))
            polrows = await cur3.fetchall()
            lead["policies"] = [{
                "policy_number": p["policy_number"],
                "insurer": p["insurer"],
                "plan_name": p["plan_name"],
                "type": p["policy_type"],
                "sum_insured": p["sum_insured"],
                "premium": p["premium"],
                "premium_mode": p["premium_mode"],
                "renewal_date": p["renewal_date"],
                "end_date": p["end_date"],
                "status": p["status"],
            } for p in polrows]
            return lead
    except Exception as e:
        logger.error("get_lead_context_for_phone error: %s", e)
        return {}


async def store_pending_reply(instance_id: int, lead_jid: str, lead_name: str,
                               context: str, expires_minutes: int = 30) -> None:
    """Store a pending advisor→lead reply context (advisor must reply within window)."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            # Invalidate any previous pending replies for this instance
            await conn.execute(
                "UPDATE wa_pending_reply SET used_at=datetime('now') "
                "WHERE instance_id=? AND used_at IS NULL",
                (instance_id,))
            await conn.execute(
                "INSERT INTO wa_pending_reply "
                "(instance_id, lead_jid, lead_name, context, expires_at) "
                "VALUES (?, ?, ?, ?, datetime('now', ? || ' minutes'))",
                (instance_id, lead_jid, lead_name, context, str(expires_minutes)))
            await conn.commit()
    except Exception as e:
        logger.error("store_pending_reply error: %s", e)


async def pop_pending_reply(instance_id: int) -> dict | None:
    """Get the most recent unexpired pending reply for this instance and mark it used."""
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT pending_id, lead_jid, lead_name, context FROM wa_pending_reply "
                "WHERE instance_id=? AND used_at IS NULL "
                "AND datetime('now') < datetime(expires_at) "
                "ORDER BY created_at DESC LIMIT 1",
                (instance_id,))
            row = await cur.fetchone()
            if not row:
                return None
            result = dict(row)
            await conn.execute(
                "UPDATE wa_pending_reply SET used_at=datetime('now') WHERE pending_id=?",
                (row["pending_id"],))
            await conn.commit()
            return result
    except Exception as e:
        logger.error("pop_pending_reply error: %s", e)
        return None


# ── Smart inbound classifier ──────────────────────────────────────────────────

async def smart_inbound_handler(
    text: str,
    instance_id: int,
    tenant_id: int,
    phone: str,
    sender_name: str,
    firm_name: str,
) -> dict:
    """
    Classify an inbound lead message and decide how to respond.

    Returns:
        {"action": "reply_lead",    "reply": str}
        {"action": "alert_advisor", "alert": str, "lead_name": str}
        {"action": "silent"}
    """
    from datetime import date as _date
    today = _date.today().isoformat()

    # Gather context in parallel
    hist_task = asyncio.ensure_future(get_conversation_history(instance_id, phone, limit=5))
    lead_task = asyncio.ensure_future(get_lead_context_for_phone(tenant_id, phone))
    hist, lead = await asyncio.gather(hist_task, lead_task)

    # Format conversation history
    hist_text = ""
    if hist:
        lines = []
        for m in hist:
            role = "Lead" if m["role"] == "lead" else "Advisor/Bot"
            lines.append(f"{role}: {m['text'][:200]}")
        hist_text = "\n".join(lines)

    # Format lead profile
    lead_profile = ""
    if lead:
        lead_profile = (
            f"Name: {lead.get('name', 'Unknown')}\n"
            f"Interest: {lead.get('need_type', 'N/A')}\n"
            f"Budget: {lead.get('premium_budget', 'N/A')}\n"
            f"Stage: {lead.get('stage', 'N/A')}\n"
            f"City: {lead.get('city', 'N/A')}\n"
            f"Occupation: {lead.get('occupation', 'N/A')}\n"
            f"Notes: {lead.get('notes', '')}\n"
        )
        if lead.get("past_notes"):
            for n in lead["past_notes"]:
                lead_profile += f"- [{n['type']}] {n['summary']} ({n['date']})\n"
        # Inject active policies so AI can factually answer "premium kab hai",
        # "renewal date", "what's my sum insured", etc., instead of escalating.
        if lead.get("policies"):
            lead_profile += "\n=== ACTIVE POLICIES (use this for factual answers) ===\n"
            for p in lead["policies"]:
                policy_line = (
                    f"- {p.get('insurer', '')} {p.get('plan_name', '')} "
                    f"({p.get('type', '')})"
                )
                if p.get("policy_number"):
                    policy_line += f" #{p['policy_number']}"
                if p.get("sum_insured"):
                    policy_line += f" | Sum insured: ₹{int(p['sum_insured']):,}"
                if p.get("premium"):
                    mode = p.get("premium_mode", "annual")
                    policy_line += f" | Premium: ₹{int(p['premium']):,}/{mode}"
                if p.get("renewal_date"):
                    policy_line += f" | Next renewal: {p['renewal_date']}"
                elif p.get("end_date"):
                    policy_line += f" | Ends: {p['end_date']}"
                lead_profile += policy_line + "\n"

    prompt = f"""You are a smart WhatsApp AI assistant for {firm_name}, an Indian insurance/financial advisory firm.
Today: {today}

=== LEAD PROFILE ===
{lead_profile if lead_profile else "Unknown contact — not in CRM yet."}

=== RECENT CONVERSATION (last 5 messages) ===
{hist_text if hist_text else "No prior conversation."}

=== NEW MESSAGE FROM LEAD ===
{sender_name}: {text}

=== YOUR TASK ===
1. Classify this message:
   - "business": insurance, investment, policy, claim, premium, EMI, renewal, meeting request, financial query
   - "personal": greetings-only, personal chitchat, non-business, casual conversation
   - "off_topic": spam, irrelevant, unclear

2. If "business": attempt a helpful, accurate reply using the lead profile + conversation history.
   - Use plain Indian English or Hinglish matching the lead's language
   - Max 3 sentences. Be warm, professional.
   - NEVER hallucinate policy terms, claim amounts, or guarantee outcomes
   - If the lead is asking something specific you cannot answer accurately → set confident=false

3. Return ONLY valid JSON:
{{
  "category": "business" | "personal" | "off_topic",
  "confident": true | false,
  "response": "<reply text for the lead if category=business and confident=true, else null>",
  "advisor_alert": "<1-2 line plain summary for the advisor: what is this lead asking and why you could not answer, else null>"
}}"""

    try:
        raw = await ai._ask_gemini(prompt, json_mode=True)
        result = ai._clean_json(raw)
        category = result.get("category", "off_topic")
        confident = bool(result.get("confident", False))
        response = result.get("response") or ""
        advisor_alert = result.get("advisor_alert") or ""

        if category in ("personal", "off_topic"):
            logger.info("WA smart: silent (category=%s) from %s", category, phone)
            return {"action": "silent"}

        # Business message
        if confident and response:
            # Append footer
            if "Powered by Sarathi-AI" not in response:
                response = response.rstrip() + f"\n\n— {firm_name} 🙏\n_Powered by Sarathi-AI_"
            return {"action": "reply_lead", "reply": response}
        else:
            # Not confident — alert advisor
            lead_name = lead.get("name") if lead else (sender_name or phone)
            alert = (
                f"📨 *Lead message — action needed*\n\n"
                f"👤 *{sender_name}* ({phone})\n"
                f"💬 \"{text[:300]}\"\n\n"
                + (f"🤖 _{advisor_alert}_\n\n" if advisor_alert else "")
                + "👆 *Reply to this message to forward your reply to the lead.*\n"
                "_Sarathi-AI_"
            )
            return {"action": "alert_advisor", "alert": alert,
                    "lead_name": lead_name, "lead_jid": phone}
    except Exception as e:
        logger.error("smart_inbound_handler error: %s", e)
        return {"action": "silent"}


async def transcribe_wa_audio_inbound(audio_bytes: bytes) -> str:
    """Transcribe an inbound lead voice note. Returns plain text or empty string."""
    import os as _os
    try:
        from google import genai as _genai
        from google.genai import types as _genai_types
    except ImportError:
        return ""
    key = _os.getenv("GEMINI_API_KEY", "")
    if not key or not audio_bytes:
        return ""
    try:
        client = _genai.Client(api_key=key)
        model = _os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        response = await client.aio.models.generate_content(
            model=model,
            contents=[
                _genai_types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                "Transcribe this voice note to plain text. Output only the transcription, nothing else.",
            ],
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.error("transcribe_wa_audio_inbound error: %s", e)
        return ""


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
    from datetime import date as _date
    today = _date.today().isoformat()
    try:
        prompt = f"""You are a CRM assistant for an Indian insurance/financial advisor using Sarathi-AI.
Parse this natural language message (may be Hindi, English, or Hinglish) into a structured CRM command.
Today's date: {today}

MESSAGE: "{message}"

Return ONLY valid JSON:
{{
  "action": "<one of: create_lead | create_task | add_note | update_stage | get_pipeline | get_tasks | get_followups | unknown>",
  "name": "<person/lead name if mentioned, else null>",
  "phone": "<10-digit Indian mobile if mentioned, else null>",
  "city": "<city if mentioned, else null>",
  "interest": "<insurance/investment type if mentioned, else null>",
  "budget": "<budget amount if mentioned, else null>",
  "stage": "<new stage for update_stage — one of: prospect|contacted|pitched|proposal_sent|negotiation|closed_won|closed_lost — else null>",
  "task_type": "<for create_task: meeting|call|follow_up — else null>",
  "follow_up_date": "<YYYY-MM-DD if mentioned, else null>",
  "follow_up_time": "<HH:MM 24h if time mentioned, else null>",
  "notes": "<summary/details of the note or task, else null>",
  "response_text": "<friendly Hindi/English confirmation of what you understood, 1-2 lines>"
}}

ACTION RULES:
- create_lead: new prospect/client mentioned by name
- create_task: schedule a meeting, call, or follow-up with an EXISTING lead
- add_note: add a note/update about an existing lead
- update_stage: move a lead to a new stage (won, lost, pitched, etc.)
- get_pipeline: show pipeline summary
- get_tasks / get_followups: show today's tasks
- unknown: anything else"""
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


async def find_lead_by_name(agent_id: int, name: str) -> dict | None:
    """Find a lead by partial name match for the given agent (most recent match)."""
    if not name:
        return None
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(
                "SELECT lead_id, name, phone, stage FROM leads "
                "WHERE agent_id=? AND name LIKE ? ORDER BY created_at DESC LIMIT 1",
                (agent_id, f"%{name}%"))
            row = await cur.fetchone()
            return dict(row) if row else None
    except Exception as e:
        logger.error("find_lead_by_name error: %s", e)
        return None


async def create_task_from_command(agent_id: int, parsed: dict) -> dict:
    """Create a follow-up task or meeting for an existing lead."""
    name = parsed.get("name", "")
    lead = await find_lead_by_name(agent_id, name)
    if not lead:
        return {"ok": False, "error": f"Lead '{name}' nahi mila pipeline mein. Pehle lead banayein."}
    try:
        task_type = (parsed.get("task_type") or "follow_up").lower()
        if task_type not in ("meeting", "call", "follow_up", "other"):
            task_type = "follow_up"
        notes = parsed.get("notes") or f"{task_type.replace('_',' ').title()} scheduled via WhatsApp"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO interactions "
                "(lead_id, agent_id, type, channel, summary, follow_up_date, follow_up_time, "
                "follow_up_status, created_by_agent_id, assigned_to_agent_id) "
                "VALUES (?, ?, ?, 'wa_agent', ?, ?, ?, 'pending', ?, ?)",
                (lead["lead_id"], agent_id, task_type, notes,
                 parsed.get("follow_up_date"), parsed.get("follow_up_time"),
                 agent_id, agent_id))
            await conn.commit()
        return {"ok": True, "lead": lead}
    except Exception as e:
        logger.error("create_task_from_command error: %s", e)
        return {"ok": False, "error": str(e)}


async def add_note_from_command(agent_id: int, parsed: dict) -> dict:
    """Add a note/interaction to an existing lead."""
    name = parsed.get("name", "")
    lead = await find_lead_by_name(agent_id, name)
    if not lead:
        return {"ok": False, "error": f"Lead '{name}' nahi mila pipeline mein."}
    try:
        note_text = parsed.get("notes") or parsed.get("response_text") or "Note added via WhatsApp"
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO interactions "
                "(lead_id, agent_id, type, channel, summary, follow_up_status, "
                "created_by_agent_id, assigned_to_agent_id) "
                "VALUES (?, ?, 'note', 'wa_agent', ?, 'done', ?, ?)",
                (lead["lead_id"], agent_id, note_text, agent_id, agent_id))
            await conn.commit()
        return {"ok": True, "lead": lead}
    except Exception as e:
        logger.error("add_note_from_command error: %s", e)
        return {"ok": False, "error": str(e)}


async def update_stage_from_command(agent_id: int, parsed: dict) -> dict:
    """Move a lead to a new stage."""
    name = parsed.get("name", "")
    lead = await find_lead_by_name(agent_id, name)
    if not lead:
        return {"ok": False, "error": f"Lead '{name}' nahi mila pipeline mein."}
    valid_stages = ("prospect", "contacted", "pitched", "proposal_sent",
                    "negotiation", "closed_won", "closed_lost")
    stage = (parsed.get("stage") or "").lower().replace(" ", "_")
    if stage not in valid_stages:
        return {"ok": False, "error": f"Stage '{stage}' valid nahi hai."}
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "UPDATE leads SET stage=?, updated_at=datetime('now') WHERE lead_id=? AND agent_id=?",
                (stage, lead["lead_id"], agent_id))
            await conn.commit()
        return {"ok": True, "lead": lead, "new_stage": stage}
    except Exception as e:
        logger.error("update_stage_from_command error: %s", e)
        return {"ok": False, "error": str(e)}


_WA_VOICE_PROMPT = """You are a CRM assistant for an Indian insurance/financial advisor using Sarathi-AI.
The advisor just sent a WhatsApp voice note to their own Saved Messages (self-chat) as a hands-free CRM command.
Transcribe the audio and detect what they want to do.

POSSIBLE ACTIONS:
- create_lead   : new prospect/client (name, phone, details)
- create_task   : schedule a meeting, call, or follow-up with an existing lead
- add_note      : add a note/update about an existing lead
- update_stage  : move a lead to a new stage (won, lost, pitched, etc.)
- get_pipeline  : wants to see their pipeline/summary
- get_tasks     : wants to see today's tasks/follow-ups
- unknown       : unclear or general chat

Return ONLY valid JSON:
{
  "transcript": "<what was said, cleaned up>",
  "action": "<create_lead | create_task | add_note | update_stage | get_pipeline | get_tasks | unknown>",
  "name": "<lead/person name if mentioned, else null>",
  "phone": "<10-digit Indian mobile if mentioned, else null>",
  "city": "<city if mentioned, else null>",
  "interest": "<insurance/investment type if mentioned, else null>",
  "budget": "<budget amount if mentioned, else null>",
  "stage": "<new stage for update_stage: prospect|contacted|pitched|proposal_sent|negotiation|closed_won|closed_lost — else null>",
  "task_type": "<for create_task: meeting|call|follow_up — else null>",
  "follow_up_date": "<YYYY-MM-DD if mentioned, else null>",
  "follow_up_time": "<HH:MM 24h format if time mentioned, else null>",
  "notes": "<summary/details, else null>",
  "response_text": "<friendly 1-line confirmation in same language as the voice note (Hindi/English/Hinglish)>"
}

Examples:
- "Ramesh Sharma se kal meeting hai, 11 baje" → create_task, name=Ramesh Sharma, follow_up_date=tomorrow, follow_up_time=11:00, task_type=meeting
- "naya client aaya, Suresh Patel, 9876543210, health insurance chahiye" → create_lead
- "Priya ka stage update karo, proposal send kar diya" → update_stage, name=Priya, stage=proposal_sent
- "Amit ke liye note add karo — premium quoted, 15000 annual" → add_note, name=Amit
- "pipeline dikhao" → get_pipeline
The advisor may speak Hindi, English, or Hinglish. Handle all naturally."""


async def handle_wa_voice_note(audio_bytes: bytes, agent_id: int, tenant_id: int) -> dict:
    """Transcribe a WhatsApp voice note using Gemini and parse as CRM command.

    Returns a dict with keys: action, transcript, name, phone, response_text, ...
    """
    import os as _os
    try:
        from google import genai as _genai
        from google.genai import types as _genai_types
    except ImportError:
        logger.error("google-genai not installed — voice note transcription unavailable")
        return {"action": "unknown", "response_text": "AI library missing"}

    key = _os.getenv("GEMINI_API_KEY", "")
    if not key or not audio_bytes:
        return {"action": "unknown", "response_text": ""}

    try:
        client = _genai.Client(api_key=key)
        model = _os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        response = await client.aio.models.generate_content(
            model=model,
            contents=[
                _genai_types.Part.from_bytes(data=audio_bytes, mime_type="audio/ogg"),
                _WA_VOICE_PROMPT,
            ],
        )
        raw = response.text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
        result = json.loads(raw)
        logger.info("WA voice note transcribed: action=%s transcript='%s'",
                    result.get("action"), (result.get("transcript") or "")[:80])
        return result
    except json.JSONDecodeError as e:
        logger.error("WA voice JSON parse error: %s", e)
        return {"action": "unknown", "response_text": "Could not understand the voice note"}
    except Exception as e:
        logger.error("WA voice transcription error: %s", e)
        return {"action": "unknown", "response_text": str(e)[:100]}


async def send_outbound_via_apk(tenant_id: int, agent_id: int,
                                 to_phone: str, message: str) -> bool:
    """
    Send an outbound WhatsApp message to a lead via the connected APK.
    The APK opens WhatsApp with the phone number and pre-filled message;
    the agent sees it ready and taps Send once.

    Used for: EMI reminders, policy renewals, birthday greetings, follow-ups.

    If the device is offline, the message is queued in wa_agent_pending and
    delivered the next time the APK connects.

    Returns True if dispatched (live) or queued (offline).
    """
    payload = {
        "type": "SEND_OUTBOUND",
        "phone": to_phone,
        "text": message,
    }
    try:
        # Find active device for this agent/tenant
        device = await get_device_status(tenant_id, agent_id)
        if not device:
            logger.debug("send_outbound_via_apk: no active device for tenant=%d agent=%d",
                         tenant_id, agent_id)
            return False

        device_id = device["device_id"]
        hmac_key = device["hmac_key"]

        # Try live delivery first
        ws = _live_connections.get(device_id)
        if ws:
            try:
                envelope = _send_signed(payload, hmac_key)
                await ws.send_text(envelope)
                logger.info("SEND_OUTBOUND dispatched live: device=%d to=%s", device_id, to_phone)
                return True
            except Exception as e:
                logger.warning("SEND_OUTBOUND live send failed: %s — queuing", e)

        # Device offline — queue it
        await queue_pending(device_id, "SEND_OUTBOUND", payload)
        logger.info("SEND_OUTBOUND queued: device=%d to=%s", device_id, to_phone)
        return True

    except Exception as e:
        logger.error("send_outbound_via_apk error tenant=%d: %s", tenant_id, e)
        return False


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
        conv_id = event.get("conversationId", "")
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

        full_reply = f"🤖 *Sarathi CRM*\n\n{response_text}\n\n_Powered by Sarathi-AI_"

        # Send result back into the SAME WhatsApp chat (via conversationId if available)
        # The APK will use sendReply() to reply inside WA, falling back to local notification
        envelope = _send_signed({
            "type": "SEND_TO_SELF",
            "conversationId": conv_id,   # APK uses this to reply back into WA chat
            "text": full_reply,
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
        return tenant_id, agent_id, payload.get("phone", "")
    except Exception:
        return 0, 0, ""


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
