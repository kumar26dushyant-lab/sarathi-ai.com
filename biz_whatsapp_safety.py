# =============================================================================
#  biz_whatsapp_safety.py — Brain Lock + Safety Engine (WhatsApp v2)
# =============================================================================
#
#  Implements the 4-Layer Brain Lock architecture:
#    1. Lead Deduplication      → enforced at db.bulk_add_leads / add_lead_admin
#    2. Mutex Lock              → THIS MODULE (acquire / release / is_locked)
#    3. Action Audit Trail      → logged via db.log_audit on every send
#    4. Real-time UI sync       → WebSocket layer (later phase)
#
#  Plus the core safety checks (anti-ban):
#    • daily/hourly send limits per instance
#    • cooldown per customer
#    • health-score / pause-state gating
#    • consent / trust-score gating for outbound
#    • escalation keywords → never auto-reply
#
#  Phone normalization is shared with biz_whatsapp_evolution._normalize_phone.
# =============================================================================
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.wa.safety")

# Lock duration constants (minutes)
LOCK_DEFAULT_MINUTES = 5
LOCK_INBOUND_MINUTES = 5      # customer just messaged → don't auto-send for 5 min
LOCK_AGENT_TYPING_MINUTES = 2  # agent is composing reply manually
LOCK_SCHEDULED_MINUTES = 1     # short hold while a scheduled reminder is dispatched

# Per-tier daily message caps (outbound to customers)
TIER_DAILY_LIMITS = {
    "none": 0,           # WhatsApp not enabled
    "self_only": 0,      # Solo plan: no customer messages from automation
    "reminders": 50,     # Team plan: scheduled reminders
    "full": 200,         # Enterprise plan
}

# Per-tier hourly caps (anti-burst)
TIER_HOURLY_LIMITS = {
    "none": 0, "self_only": 0, "reminders": 10, "full": 25,
}

# Per-customer cooldown (minutes) to prevent spamming same person
PER_CUSTOMER_COOLDOWN_MIN = 30

# Escalation keywords — these in inbound mean MUST hand to human, never auto-reply
ESCALATION_KEYWORDS = [
    "claim", "complaint", "lawyer", "fraud", "cheat", "sue", "police",
    "court", "rbi", "irdai", "sebi", "consumer forum", "trai",
    "बीमा क्लेम", "क्लेम", "धोखा", "पुलिस", "वकील", "शिकायत",
]


def normalize_phone(phone: str) -> str:
    """Same normalization as evolution client — keep in sync."""
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return digits


# ─────────────────────────────────────────────────────────────────────────────
#  Layer 2: Brain Lock (mutex per (tenant, customer))
# ─────────────────────────────────────────────────────────────────────────────

async def acquire_lock(tenant_id: int, customer_phone: str, source: str,
                       duration_minutes: int = LOCK_DEFAULT_MINUTES) -> tuple[bool, str]:
    """
    Try to acquire a lock for (tenant, customer).
    Returns (acquired, reason). If acquired=False, reason explains who holds it.
    """
    phone = normalize_phone(customer_phone)
    now = datetime.utcnow()
    expires = now + timedelta(minutes=duration_minutes)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        # Auto-release any expired locks
        await conn.execute(
            "UPDATE wa_brain_locks SET released_at = datetime('now') "
            "WHERE tenant_id = ? AND customer_phone = ? "
            "AND released_at IS NULL AND expires_at < datetime('now')",
            (tenant_id, phone))
        # Check active lock
        cur = await conn.execute(
            "SELECT source, expires_at FROM wa_brain_locks "
            "WHERE tenant_id = ? AND customer_phone = ? AND released_at IS NULL "
            "ORDER BY acquired_at DESC LIMIT 1",
            (tenant_id, phone))
        row = await cur.fetchone()
        if row:
            return False, f"locked_by_{row[0]}_until_{row[1]}"
        # Insert new lock
        try:
            await conn.execute(
                "INSERT INTO wa_brain_locks (tenant_id, customer_phone, source, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (tenant_id, phone, source, expires.strftime("%Y-%m-%d %H:%M:%S")))
            await conn.commit()
            return True, ""
        except aiosqlite.IntegrityError:
            # Race condition — another writer beat us; treat as locked
            return False, "race_condition"


async def release_lock(tenant_id: int, customer_phone: str,
                       source: Optional[str] = None) -> None:
    """Release the active lock. If source given, only release if it matches."""
    phone = normalize_phone(customer_phone)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        if source:
            await conn.execute(
                "UPDATE wa_brain_locks SET released_at = datetime('now') "
                "WHERE tenant_id = ? AND customer_phone = ? AND source = ? AND released_at IS NULL",
                (tenant_id, phone, source))
        else:
            await conn.execute(
                "UPDATE wa_brain_locks SET released_at = datetime('now') "
                "WHERE tenant_id = ? AND customer_phone = ? AND released_at IS NULL",
                (tenant_id, phone))
        await conn.commit()


async def is_locked(tenant_id: int, customer_phone: str) -> tuple[bool, str]:
    """Read-only check; returns (locked, holder_source_or_empty)."""
    phone = normalize_phone(customer_phone)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT source FROM wa_brain_locks "
            "WHERE tenant_id = ? AND customer_phone = ? AND released_at IS NULL "
            "AND expires_at > datetime('now') LIMIT 1",
            (tenant_id, phone))
        row = await cur.fetchone()
        return (True, row[0]) if row else (False, "")


# ─────────────────────────────────────────────────────────────────────────────
#  Safety checks (run before any outbound send)
# ─────────────────────────────────────────────────────────────────────────────

async def check_can_send(*, tenant_id: int, instance_id: int,
                         customer_phone: str, source: str) -> tuple[bool, str]:
    """
    Run all safety checks. Returns (allowed, reason).
    `source`: 'manual' (agent typed) | 'reminder' (scheduled) | 'ai_auto' (AI-replied)
    Manual sends bypass most checks (agent is in control).
    """
    phone = normalize_phone(customer_phone)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        # 1. Instance status / pause
        cur = await conn.execute(
            "SELECT status, paused_until, health_score, ban_warmup_until "
            "FROM wa_instances WHERE instance_id = ?", (instance_id,))
        inst = await cur.fetchone()
        if not inst:
            return False, "instance_not_found"
        status, paused_until, health, warmup = inst
        if status not in ("connected", "open"):
            return False, f"instance_not_connected({status})"
        if paused_until:
            return False, f"instance_paused_until_{paused_until}"
        if health is not None and health < 30 and source != "manual":
            return False, f"low_health_score({health})"

        # Manual sends: agent is in control — skip volume checks
        if source == "manual":
            return True, ""

        # 2. Tier configuration (which automation is allowed)
        cur = await conn.execute(
            "SELECT t.wa_tier, t.wa_addon_reminders, t.wa_addon_ai_assist "
            "FROM wa_instances i JOIN tenants t ON i.tenant_id = t.tenant_id "
            "WHERE i.instance_id = ?", (instance_id,))
        tier_row = await cur.fetchone()
        if not tier_row:
            return False, "tenant_not_found"
        tier, addon_rem, addon_ai = tier_row
        # Effective tier resolution
        if tier == "full" or addon_ai:
            effective = "full"
        elif tier == "reminders" or addon_rem:
            effective = "reminders"
        elif tier in ("self_only", "self"):
            effective = "self_only"
        else:
            effective = "none"
        # Source-vs-tier gating
        if source == "ai_auto" and effective != "full":
            return False, "ai_auto_not_in_plan"
        if source == "reminder" and effective not in ("reminders", "full"):
            return False, "reminders_not_in_plan"

        # 3. Daily / hourly volume caps
        daily_cap = TIER_DAILY_LIMITS.get(effective, 0)
        hourly_cap = TIER_HOURLY_LIMITS.get(effective, 0)
        if daily_cap == 0:
            return False, "daily_cap_zero"
        cur = await conn.execute(
            "SELECT COUNT(*) FROM wa_messages "
            "WHERE instance_id = ? AND direction = 'out' "
            "AND date(created_at) = date('now')", (instance_id,))
        sent_today = (await cur.fetchone())[0]
        if sent_today >= daily_cap:
            return False, f"daily_cap_reached({sent_today}/{daily_cap})"
        cur = await conn.execute(
            "SELECT COUNT(*) FROM wa_messages "
            "WHERE instance_id = ? AND direction = 'out' "
            "AND created_at > datetime('now', '-1 hour')", (instance_id,))
        sent_hour = (await cur.fetchone())[0]
        if sent_hour >= hourly_cap:
            return False, f"hourly_cap_reached({sent_hour}/{hourly_cap})"

        # 4. Per-customer cooldown
        cur = await conn.execute(
            "SELECT created_at FROM wa_messages m "
            "JOIN wa_conversations c ON m.conversation_id = c.conversation_id "
            "WHERE c.instance_id = ? AND c.customer_phone = ? AND m.direction = 'out' "
            "ORDER BY m.created_at DESC LIMIT 1",
            (instance_id, phone))
        last_out = await cur.fetchone()
        if last_out:
            try:
                last_dt = datetime.strptime(last_out[0], "%Y-%m-%d %H:%M:%S")
                if datetime.utcnow() - last_dt < timedelta(minutes=PER_CUSTOMER_COOLDOWN_MIN):
                    return False, f"customer_cooldown({PER_CUSTOMER_COOLDOWN_MIN}min)"
            except (ValueError, TypeError):
                pass

        # 5. Trust-score gating for AI auto-reply
        if source == "ai_auto":
            cur = await conn.execute(
                "SELECT trust_score, consent_status FROM wa_conversations "
                "WHERE instance_id = ? AND customer_phone = ?",
                (instance_id, phone))
            conv = await cur.fetchone()
            if not conv:
                return False, "no_conversation_history"
            trust, consent = conv
            if consent == "blocked":
                return False, "customer_blocked"
            if (trust or 0) < 60:
                return False, f"low_trust_score({trust})"

        # 6. Brain Lock check (don't compete with active source)
        locked, holder = await is_locked(tenant_id, phone)
        if locked and holder != source:
            return False, f"brain_locked_by_{holder}"

    return True, ""


def is_escalation(text: str) -> tuple[bool, str]:
    """Return (True, matched_keyword) if message contains escalation trigger."""
    if not text:
        return False, ""
    low = text.lower()
    for kw in ESCALATION_KEYWORDS:
        if kw.lower() in low:
            return True, kw
    return False, ""


# ─────────────────────────────────────────────────────────────────────────────
#  Health score adjustments (called by webhook handler)
# ─────────────────────────────────────────────────────────────────────────────

async def report_spam_event(instance_id: int, severity: str = "low") -> None:
    """
    Customer reported / blocked us. Decrement health score & maybe auto-pause.
      severity: 'low' (one block) | 'medium' | 'high' (multiple in short time)
    """
    delta = {"low": -10, "medium": -25, "high": -50}.get(severity, -10)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE wa_instances SET health_score = MAX(0, health_score + ?), "
            "spam_reports_count = spam_reports_count + 1, "
            "updated_at = datetime('now') WHERE instance_id = ?",
            (delta, instance_id))
        # Auto-pause if score critically low
        cur = await conn.execute(
            "SELECT health_score FROM wa_instances WHERE instance_id = ?", (instance_id,))
        row = await cur.fetchone()
        if row and row[0] < 20:
            await conn.execute(
                "UPDATE wa_instances SET paused_until = datetime('now', '+24 hours'), "
                "pause_reason = 'auto: critical health score' WHERE instance_id = ?",
                (instance_id,))
            logger.warning("⚠️ WA instance %d auto-paused: health=%d", instance_id, row[0])
        await conn.commit()


async def report_health_signal(instance_id: int, signal: str, delta: int = 0) -> None:
    """
    Generic health-score adjustment hook.
    signal: 'message_delivered' (+1) | 'message_read' (+1) | 'reply_received' (+2) | custom
    """
    if delta == 0:
        delta = {
            "message_delivered": 1,
            "message_read": 1,
            "reply_received": 2,
            "send_failed": -2,
        }.get(signal, 0)
    if delta == 0:
        return
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE wa_instances SET health_score = MIN(100, MAX(0, health_score + ?)), "
            "updated_at = datetime('now') WHERE instance_id = ?",
            (delta, instance_id))
        await conn.commit()
