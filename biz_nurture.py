# =============================================================================
#  biz_nurture.py — Drip Nurture Sequence Engine
# =============================================================================
#
#  Multi-step time-delayed message sequences that automatically nurture leads
#  through their journey. Triggers on lead-stage changes (or manual enrolment).
#
#  Architecture:
#    nurture_sequences      — template (per tenant)
#    nurture_steps          — ordered steps with delay + channel + template
#    nurture_enrollments    — per-lead enrolment with current step + next-fire
#
#  Scheduler (called from biz_reminders) processes due enrollments every 10min.
#  Lead reaching closed_won / closed_lost → all active enrollments auto-cancel.
#
#  Channels (extensible):
#    - telegram_agent : DM the AGENT with a suggested WhatsApp message + wa.me
#                       button. Agent clicks → WhatsApp opens with text pre-filled.
#                       (Zero infra risk, no Meta/Baileys dependency.)
#    - email_customer : direct email to customer (Phase 2)
#    - sms_customer   : SMS to customer (Phase 2)
#
# =============================================================================

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable

import aiosqlite
import biz_database as db

logger = logging.getLogger("sarathi.nurture")

# Telegram send callback (registered by biz_bot at startup)
_telegram_send: Optional[Callable] = None


def set_telegram_callback(callback: Callable):
    """Register the bot's per-tenant send function.
    Signature: async def send(tenant_id:int, telegram_id:str, text:str, reply_markup=None)"""
    global _telegram_send
    _telegram_send = callback
    logger.info("Nurture: Telegram callback registered")


# =============================================================================
#  SCHEMA
# =============================================================================

NURTURE_SCHEMA = """
CREATE TABLE IF NOT EXISTS nurture_sequences (
    sequence_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       INTEGER NOT NULL,
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    trigger_event   TEXT NOT NULL DEFAULT 'lead_stage_change',
    trigger_value   TEXT NOT NULL DEFAULT '',
    is_active       INTEGER DEFAULT 1,
    is_seed         INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
CREATE INDEX IF NOT EXISTS idx_nurture_seq_tenant ON nurture_sequences(tenant_id);
CREATE INDEX IF NOT EXISTS idx_nurture_seq_trigger ON nurture_sequences(trigger_event, trigger_value);

CREATE TABLE IF NOT EXISTS nurture_steps (
    step_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_id     INTEGER NOT NULL,
    step_order      INTEGER NOT NULL,
    delay_days      INTEGER NOT NULL DEFAULT 0,
    delay_hours     INTEGER NOT NULL DEFAULT 0,
    channel         TEXT NOT NULL DEFAULT 'telegram_agent',
    label           TEXT NOT NULL DEFAULT '',
    template_en     TEXT NOT NULL DEFAULT '',
    template_hi     TEXT NOT NULL DEFAULT '',
    wa_template_en  TEXT DEFAULT '',
    wa_template_hi  TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (sequence_id) REFERENCES nurture_sequences(sequence_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_nurture_steps_seq ON nurture_steps(sequence_id, step_order);

CREATE TABLE IF NOT EXISTS nurture_enrollments (
    enrollment_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       INTEGER NOT NULL,
    sequence_id     INTEGER NOT NULL,
    lead_id         INTEGER NOT NULL,
    agent_id        INTEGER NOT NULL,
    current_step    INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active',
    next_fire_at    TEXT NOT NULL,
    last_fired_at   TEXT,
    started_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    cancel_reason   TEXT,
    fired_count     INTEGER DEFAULT 0,
    FOREIGN KEY (sequence_id) REFERENCES nurture_sequences(sequence_id),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id) ON DELETE CASCADE,
    UNIQUE(sequence_id, lead_id, started_at)
);
CREATE INDEX IF NOT EXISTS idx_nurture_enrol_status ON nurture_enrollments(status, next_fire_at);
CREATE INDEX IF NOT EXISTS idx_nurture_enrol_lead ON nurture_enrollments(lead_id, status);
CREATE INDEX IF NOT EXISTS idx_nurture_enrol_tenant ON nurture_enrollments(tenant_id, status);
"""


async def init_schema():
    """Initialise nurture tables. Idempotent."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.executescript(NURTURE_SCHEMA)
        await conn.commit()
    logger.info("Nurture schema initialised")


# =============================================================================
#  CRUD: SEQUENCES
# =============================================================================

async def create_sequence(tenant_id: int, name: str, trigger_event: str,
                          trigger_value: str, description: str = "",
                          is_seed: int = 0) -> int:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nurture_sequences (tenant_id, name, description, "
            "trigger_event, trigger_value, is_seed) VALUES (?, ?, ?, ?, ?, ?)",
            (tenant_id, name, description, trigger_event, trigger_value, is_seed))
        await conn.commit()
        return cur.lastrowid


async def list_sequences(tenant_id: int) -> list:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT s.*, "
            "(SELECT COUNT(*) FROM nurture_steps WHERE sequence_id=s.sequence_id) AS step_count, "
            "(SELECT COUNT(*) FROM nurture_enrollments WHERE sequence_id=s.sequence_id AND status='active') AS active_enrollments, "
            "(SELECT COUNT(*) FROM nurture_enrollments WHERE sequence_id=s.sequence_id AND status='completed') AS completed_enrollments "
            "FROM nurture_sequences s WHERE s.tenant_id=? ORDER BY s.is_seed DESC, s.sequence_id ASC",
            (tenant_id,))
        return [dict(r) for r in await cur.fetchall()]


async def get_sequence(sequence_id: int, tenant_id: int) -> Optional[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nurture_sequences WHERE sequence_id=? AND tenant_id=?",
            (sequence_id, tenant_id))
        row = await cur.fetchone()
        if not row:
            return None
        seq = dict(row)
        cur = await conn.execute(
            "SELECT * FROM nurture_steps WHERE sequence_id=? ORDER BY step_order ASC",
            (sequence_id,))
        seq["steps"] = [dict(r) for r in await cur.fetchall()]
        return seq


async def update_sequence(sequence_id: int, tenant_id: int, **fields) -> bool:
    allowed = {"name", "description", "trigger_event", "trigger_value", "is_active"}
    upd = {k: v for k, v in fields.items() if k in allowed}
    if not upd:
        return False
    upd["updated_at"] = datetime.now().isoformat()
    sets = ", ".join(f"{k}=?" for k in upd)
    vals = list(upd.values()) + [sequence_id, tenant_id]
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            f"UPDATE nurture_sequences SET {sets} WHERE sequence_id=? AND tenant_id=?", vals)
        await conn.commit()
        return cur.rowcount > 0


async def delete_sequence(sequence_id: int, tenant_id: int) -> bool:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        # Cancel active enrollments first
        await conn.execute(
            "UPDATE nurture_enrollments SET status='cancelled', cancel_reason='sequence_deleted', "
            "completed_at=datetime('now') WHERE sequence_id=? AND status='active'",
            (sequence_id,))
        cur = await conn.execute(
            "DELETE FROM nurture_sequences WHERE sequence_id=? AND tenant_id=?",
            (sequence_id, tenant_id))
        await conn.commit()
        return cur.rowcount > 0


# =============================================================================
#  CRUD: STEPS
# =============================================================================

async def add_step(sequence_id: int, step_order: int, delay_days: int,
                   delay_hours: int, channel: str, label: str,
                   template_en: str, template_hi: str,
                   wa_template_en: str = "", wa_template_hi: str = "") -> int:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nurture_steps (sequence_id, step_order, delay_days, delay_hours, "
            "channel, label, template_en, template_hi, wa_template_en, wa_template_hi) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sequence_id, step_order, delay_days, delay_hours, channel, label,
             template_en, template_hi, wa_template_en, wa_template_hi))
        await conn.commit()
        return cur.lastrowid


async def delete_step(step_id: int, tenant_id: int) -> bool:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "DELETE FROM nurture_steps WHERE step_id=? AND sequence_id IN "
            "(SELECT sequence_id FROM nurture_sequences WHERE tenant_id=?)",
            (step_id, tenant_id))
        await conn.commit()
        return cur.rowcount > 0


# =============================================================================
#  ENROLMENT
# =============================================================================

async def _first_step_due_at(sequence_id: int) -> Optional[str]:
    """Compute next_fire_at for the first step of a sequence."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT delay_days, delay_hours FROM nurture_steps "
            "WHERE sequence_id=? ORDER BY step_order ASC LIMIT 1",
            (sequence_id,))
        row = await cur.fetchone()
        if not row:
            return None
        due = datetime.now() + timedelta(days=row["delay_days"], hours=row["delay_hours"])
        return due.isoformat()


async def enrol_lead(tenant_id: int, sequence_id: int, lead_id: int,
                     agent_id: int) -> Optional[int]:
    """Enrol a lead in a sequence. Idempotent — skips if already active."""
    # Check sequence exists, active, has steps
    seq = await get_sequence(sequence_id, tenant_id)
    if not seq or not seq.get("is_active") or not seq.get("steps"):
        return None
    # Check no active enrolment exists
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT enrollment_id FROM nurture_enrollments "
            "WHERE sequence_id=? AND lead_id=? AND status='active'",
            (sequence_id, lead_id))
        if await cur.fetchone():
            return None  # Already enrolled
    next_fire = await _first_step_due_at(sequence_id)
    if not next_fire:
        return None
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "INSERT INTO nurture_enrollments (tenant_id, sequence_id, lead_id, agent_id, "
            "current_step, status, next_fire_at, started_at) "
            "VALUES (?, ?, ?, ?, 0, 'active', ?, datetime('now'))",
            (tenant_id, sequence_id, lead_id, agent_id, next_fire))
        await conn.commit()
        eid = cur.lastrowid
    logger.info("Nurture: enrolled lead %d in sequence %d (enrollment %d, fire %s)",
                lead_id, sequence_id, eid, next_fire)
    return eid


async def cancel_enrollment(enrollment_id: int, tenant_id: int,
                            reason: str = "manual") -> bool:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nurture_enrollments SET status='cancelled', cancel_reason=?, "
            "completed_at=datetime('now') WHERE enrollment_id=? AND tenant_id=? AND status='active'",
            (reason, enrollment_id, tenant_id))
        await conn.commit()
        return cur.rowcount > 0


async def cancel_enrollments_for_lead(lead_id: int, reason: str = "stage_change") -> int:
    """Cancel ALL active enrollments for a lead (called when lead is closed)."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE nurture_enrollments SET status='cancelled', cancel_reason=?, "
            "completed_at=datetime('now') WHERE lead_id=? AND status='active'",
            (reason, lead_id))
        await conn.commit()
        return cur.rowcount


async def list_enrollments(tenant_id: int, status: Optional[str] = None,
                           lead_id: Optional[int] = None, limit: int = 100) -> list:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        sql = ("SELECT e.*, s.name AS sequence_name, l.name AS lead_name, l.phone AS lead_phone, "
               "(SELECT COUNT(*) FROM nurture_steps WHERE sequence_id=e.sequence_id) AS total_steps "
               "FROM nurture_enrollments e "
               "JOIN nurture_sequences s ON e.sequence_id=s.sequence_id "
               "JOIN leads l ON e.lead_id=l.lead_id "
               "WHERE e.tenant_id=?")
        args = [tenant_id]
        if status:
            sql += " AND e.status=?"
            args.append(status)
        if lead_id:
            sql += " AND e.lead_id=?"
            args.append(lead_id)
        sql += " ORDER BY e.enrollment_id DESC LIMIT ?"
        args.append(limit)
        cur = await conn.execute(sql, args)
        return [dict(r) for r in await cur.fetchall()]


# =============================================================================
#  AUTO-ENROLMENT ON STAGE CHANGE
# =============================================================================

# Stages that should CANCEL all active nurture (lead is done)
_TERMINAL_STAGES = ("closed_won", "closed_lost")


async def auto_enrol_on_stage_change(lead_id: int, new_stage: str) -> int:
    """Called after a lead's stage changes. Returns count of new enrollments.
    Cancels existing enrollments if lead reached a terminal stage."""
    if new_stage in _TERMINAL_STAGES:
        cancelled = await cancel_enrollments_for_lead(lead_id, reason=f"reached_{new_stage}")
        if cancelled:
            logger.info("Nurture: cancelled %d enrollments for lead %d (reached %s)",
                        cancelled, lead_id, new_stage)
        return 0
    # Look up lead → tenant_id + agent_id
    lead = await db.get_lead(lead_id)
    if not lead:
        return 0
    agent_id = lead.get("agent_id")
    # Get tenant via agent
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT tenant_id FROM agents WHERE agent_id=?", (agent_id,))
        ar = await cur.fetchone()
        if not ar:
            return 0
        tenant_id = ar["tenant_id"]
        # Find matching sequences
        cur = await conn.execute(
            "SELECT sequence_id FROM nurture_sequences "
            "WHERE tenant_id=? AND is_active=1 AND trigger_event='lead_stage_change' "
            "AND trigger_value=?",
            (tenant_id, new_stage))
        seq_ids = [r["sequence_id"] for r in await cur.fetchall()]
    enrolled = 0
    for sid in seq_ids:
        eid = await enrol_lead(tenant_id, sid, lead_id, agent_id)
        if eid:
            enrolled += 1
    return enrolled


# =============================================================================
#  TEMPLATE RENDERING
# =============================================================================

def _render(tpl: str, lead: dict, agent: dict, firm: str) -> str:
    """Replace {first_name}, {name}, {firm}, {agent}, {city} in a template."""
    if not tpl:
        return ""
    name = (lead.get("name") or "").strip()
    first = name.split(" ")[0] if name else ""
    return (tpl
            .replace("{first_name}", first or "there")
            .replace("{name}", name or "there")
            .replace("{firm}", firm or "Sarathi-AI")
            .replace("{agent}", (agent.get("name") if agent else "") or "")
            .replace("{city}", (lead.get("city") or "")))


def _wa_link(phone: str, text: str) -> str:
    """Build a wa.me link with pre-filled text."""
    from urllib.parse import quote
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if not digits:
        return ""
    if len(digits) == 10:
        digits = "91" + digits
    return f"https://wa.me/{digits}?text={quote(text)}"


# =============================================================================
#  STEP DISPATCH
# =============================================================================

async def _send_step(enrollment: dict, step: dict, lead: dict,
                     agent: dict, firm_name: str, lang: str) -> bool:
    """Dispatch a single step. Returns True on success."""
    channel = step.get("channel", "telegram_agent")

    # Render templates in agent's language (fallback to en)
    tpl = step.get(f"template_{lang}") or step.get("template_en") or ""
    body = _render(tpl, lead, agent, firm_name)

    wa_tpl = step.get(f"wa_template_{lang}") or step.get("wa_template_en") or ""
    wa_text = _render(wa_tpl, lead, agent, firm_name) if wa_tpl else ""

    if channel == "telegram_agent":
        if not _telegram_send:
            logger.warning("Nurture: no telegram callback registered, skipping step %d",
                           step["step_id"])
            return False
        tg_id = agent.get("telegram_id")
        if not tg_id:
            logger.info("Nurture: agent %d has no telegram_id, skipping",
                        agent.get("agent_id"))
            return False
        # Build message + optional WA action button
        seq_label = step.get("label", "")
        header = f"💧 <b>Drip — {seq_label}</b>\n👤 {lead.get('name','')}"
        if lead.get("phone"):
            header += f" • 📱 {lead['phone']}"
        full_msg = f"{header}\n\n{body}"
        # Reply markup with WA send button (only if phone + wa_text present)
        reply_markup = None
        if lead.get("phone") and wa_text:
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                wa_url = _wa_link(lead["phone"], wa_text)
                if wa_url:
                    btn_label = "💬 Send via WhatsApp" if lang == "en" else "💬 WhatsApp भेजें"
                    reply_markup = InlineKeyboardMarkup([[
                        InlineKeyboardButton(btn_label, url=wa_url)
                    ]])
            except Exception as e:
                logger.warning("Nurture: button build failed: %s", e)
        try:
            tenant_id = enrollment["tenant_id"]
            await _telegram_send(tenant_id, tg_id, full_msg, reply_markup=reply_markup)
            return True
        except Exception as e:
            logger.error("Nurture: telegram send failed: %s", e)
            return False

    # Future channels (placeholders for Phase 2)
    elif channel == "email_customer":
        logger.info("Nurture: email_customer channel not yet implemented")
        return False
    elif channel == "sms_customer":
        logger.info("Nurture: sms_customer channel not yet implemented")
        return False

    logger.warning("Nurture: unknown channel '%s'", channel)
    return False


# =============================================================================
#  SCHEDULER TICK
# =============================================================================

async def process_due_enrollments(batch_limit: int = 100) -> dict:
    """Main scheduler tick — find all enrollments past next_fire_at and process."""
    stats = {"processed": 0, "advanced": 0, "completed": 0, "failed": 0, "cancelled_terminal": 0}

    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nurture_enrollments "
            "WHERE status='active' AND next_fire_at <= datetime('now') "
            "ORDER BY next_fire_at ASC LIMIT ?", (batch_limit,))
        due = [dict(r) for r in await cur.fetchall()]

    if not due:
        return stats

    logger.info("Nurture tick: %d enrollments due", len(due))

    for enrol in due:
        stats["processed"] += 1
        try:
            # Re-load lead (may have changed stage / been deleted)
            lead = await db.get_lead(enrol["lead_id"])
            if not lead:
                await _mark_cancelled(enrol["enrollment_id"], "lead_deleted")
                continue
            # If lead reached terminal stage, cancel
            if lead.get("stage") in _TERMINAL_STAGES:
                await _mark_cancelled(enrol["enrollment_id"], f"reached_{lead.get('stage')}")
                stats["cancelled_terminal"] += 1
                continue
            # Get all steps for this sequence (ordered)
            async with aiosqlite.connect(db.DB_PATH) as conn:
                conn.row_factory = aiosqlite.Row
                cur = await conn.execute(
                    "SELECT * FROM nurture_steps WHERE sequence_id=? ORDER BY step_order ASC",
                    (enrol["sequence_id"],))
                steps = [dict(r) for r in await cur.fetchall()]
            # Step we should fire = current_step (0-indexed)
            idx = enrol["current_step"]
            if idx >= len(steps):
                # Already past last step — mark complete defensively
                await _mark_completed(enrol["enrollment_id"])
                stats["completed"] += 1
                continue
            step = steps[idx]
            # Get agent + tenant info
            agent = await db.get_agent_by_id(enrol["agent_id"])
            if not agent:
                await _mark_cancelled(enrol["enrollment_id"], "agent_missing")
                continue
            tenant = await db.get_tenant(enrol["tenant_id"])
            firm_name = (tenant or {}).get("firm_name", "")
            lang = (tenant or {}).get("language") or (agent or {}).get("language") or "en"
            if lang not in ("en", "hi"):
                lang = "en"
            # Dispatch
            ok = await _send_step(enrol, step, lead, agent, firm_name, lang)
            if not ok:
                stats["failed"] += 1
                # Don't advance on failure — push next_fire 1h forward (retry once)
                await _push_retry(enrol["enrollment_id"], hours=1)
                continue
            # Advance to next step (or complete)
            next_idx = idx + 1
            if next_idx >= len(steps):
                await _mark_completed(enrol["enrollment_id"])
                stats["completed"] += 1
            else:
                next_step = steps[next_idx]
                next_due = datetime.now() + timedelta(
                    days=next_step["delay_days"], hours=next_step["delay_hours"])
                async with aiosqlite.connect(db.DB_PATH) as conn:
                    await conn.execute(
                        "UPDATE nurture_enrollments SET current_step=?, next_fire_at=?, "
                        "last_fired_at=datetime('now'), fired_count=fired_count+1 "
                        "WHERE enrollment_id=?",
                        (next_idx, next_due.isoformat(), enrol["enrollment_id"]))
                    await conn.commit()
                stats["advanced"] += 1
        except Exception as e:
            logger.exception("Nurture: enrollment %d processing error: %s",
                             enrol.get("enrollment_id"), e)
            stats["failed"] += 1

    if stats["processed"]:
        logger.info("Nurture tick complete: %s", stats)
    return stats


async def _mark_completed(enrollment_id: int):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nurture_enrollments SET status='completed', "
            "completed_at=datetime('now'), last_fired_at=datetime('now'), "
            "fired_count=fired_count+1 WHERE enrollment_id=?", (enrollment_id,))
        await conn.commit()


async def _mark_cancelled(enrollment_id: int, reason: str):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nurture_enrollments SET status='cancelled', cancel_reason=?, "
            "completed_at=datetime('now') WHERE enrollment_id=?",
            (reason, enrollment_id))
        await conn.commit()


async def _push_retry(enrollment_id: int, hours: int = 1):
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nurture_enrollments SET next_fire_at=datetime('now', ?) "
            "WHERE enrollment_id=?", (f"+{hours} hours", enrollment_id))
        await conn.commit()


# =============================================================================
#  SEED DEFAULT SEQUENCES (per tenant, on first creation)
# =============================================================================

DEFAULT_SEQUENCES = [
    {
        "name": "Cold Lead Warm-up",
        "description": "5-touch nurture for fresh prospects — earn trust before pitching.",
        "trigger_event": "lead_stage_change",
        "trigger_value": "prospect",
        "steps": [
            {
                "delay_days": 0, "delay_hours": 2,
                "label": "Welcome",
                "template_en": "👋 New prospect just added. Send a friendly welcome WhatsApp now — first impressions matter most in the first 2 hours.",
                "template_hi": "👋 नया prospect जुड़ा है। अभी एक दोस्ताना welcome WhatsApp भेजें — पहले 2 घंटे में पहली छाप सबसे मायने रखती है।",
                "wa_template_en": "Hi {first_name}! Thanks for connecting with {firm}. I help families like yours protect what matters most. When's a good time for a quick 5-minute call?",
                "wa_template_hi": "नमस्ते {first_name}! {firm} से जुड़ने के लिए धन्यवाद। मैं आपके जैसे परिवारों को सबसे ज़रूरी चीज़ों की सुरक्षा में मदद करता हूँ। 5 मिनट की एक छोटी call के लिए कब समय मिलेगा?"
            },
            {
                "delay_days": 2, "delay_hours": 0,
                "label": "Soft check-in",
                "template_en": "💧 2 days since you added {first_name}. Send a value-first message — share a useful tip, not a pitch.",
                "template_hi": "💧 {first_name} को जोड़े 2 दिन हो गए। एक value-first message भेजें — कोई useful tip share करें, pitch नहीं।",
                "wa_template_en": "Hi {first_name}, sharing a quick tip — most families in {city} are under-insured by 60%. Want me to do a free 2-min cover-gap check for you?",
                "wa_template_hi": "नमस्ते {first_name}, एक quick tip — ज़्यादातर families 60% तक under-insured हैं। क्या मैं आपके लिए free 2-min cover-gap check करूँ?"
            },
            {
                "delay_days": 5, "delay_hours": 0,
                "label": "Social proof",
                "template_en": "💧 5 days in. Share a recent client win or testimonial with {first_name} — builds credibility before the pitch.",
                "template_hi": "💧 5 दिन हो गए। {first_name} के साथ recent client win या testimonial share करें — pitch से पहले credibility बनती है।",
                "wa_template_en": "Hi {first_name}, last month I helped a client save ₹40k/yr while doubling their family's cover. Curious if I can do the same review for you — no obligation. Free?",
                "wa_template_hi": "नमस्ते {first_name}, पिछले महीने मैंने एक client की ₹40k/year बचत करवाई और उनका family cover double किया। क्या मैं आपके लिए भी ऐसा review करूँ — बिना obligation। Free?"
            },
            {
                "delay_days": 9, "delay_hours": 0,
                "label": "Direct CTA",
                "template_en": "💧 Day 9. Time for a clear ask — propose a specific 15-min slot to {first_name}.",
                "template_hi": "💧 दिन 9। अब clear ask का समय — {first_name} को एक specific 15-min slot propose करें।",
                "wa_template_en": "Hi {first_name}, would Saturday 11am work for a quick 15-min review call? I'll come prepared with options tailored to your family.",
                "wa_template_hi": "नमस्ते {first_name}, क्या Saturday 11am एक quick 15-min review call के लिए ठीक रहेगा? मैं आपके परिवार के अनुसार options तैयार करके आऊँगा।"
            },
            {
                "delay_days": 14, "delay_hours": 0,
                "label": "Last touch",
                "template_en": "💧 Day 14 — final nurture touch. Either close the loop or move {first_name} to 'closed_lost' to free up your pipeline.",
                "template_hi": "💧 दिन 14 — आख़िरी nurture touch। या तो loop close करें या {first_name} को 'closed_lost' में move कर दें ताकि pipeline free हो जाए।",
                "wa_template_en": "Hi {first_name}, I won't keep messaging — but my offer to help stands. If insurance feels relevant in the coming months, I'm just one message away. Wishing you and your family well!",
                "wa_template_hi": "नमस्ते {first_name}, मैं और messages नहीं भेजूँगा — लेकिन मेरी help का offer हमेशा है। आने वाले महीनों में insurance की ज़रूरत लगे तो बस एक message दूर हूँ। आपके और परिवार के लिए शुभकामनाएँ!"
            },
        ],
    },
    {
        "name": "Pitched but Silent",
        "description": "Re-engage leads who saw the pitch but didn't reply.",
        "trigger_event": "lead_stage_change",
        "trigger_value": "pitched",
        "steps": [
            {
                "delay_days": 2, "delay_hours": 0,
                "label": "Gentle nudge",
                "template_en": "💧 2 days post-pitch and {first_name} hasn't replied. Send a low-pressure nudge.",
                "template_hi": "💧 Pitch के 2 दिन बाद {first_name} ने reply नहीं किया। एक low-pressure nudge भेजें।",
                "wa_template_en": "Hi {first_name}, just checking — any questions on what I shared? Happy to clarify on call or chat, whichever you prefer.",
                "wa_template_hi": "नमस्ते {first_name}, बस check कर रहा हूँ — मैंने जो share किया उस पर कोई questions? Call या chat — जो आपको ठीक लगे, मैं समझा दूँगा।"
            },
            {
                "delay_days": 5, "delay_hours": 0,
                "label": "Address objection",
                "template_en": "💧 5 days silent. Most likely objection: price or trust. Send an answer to the most common concern.",
                "template_hi": "💧 5 दिन silent। सबसे common objection: price या trust। एक common concern का answer भेजें।",
                "wa_template_en": "Hi {first_name}, often when people pause, it's about price or commitment. The plan I shared starts at less than ₹50/day — and you can cancel within 15 days, no questions asked. Want me to walk through it once more?",
                "wa_template_hi": "नमस्ते {first_name}, अक्सर लोग pause करते हैं तो वजह price या commitment होती है। मैंने जो plan share किया वो ₹50/day से भी कम से शुरू है — और आप 15 दिनों में बिना सवाल cancel कर सकते हैं। क्या मैं एक बार फिर समझाऊँ?"
            },
            {
                "delay_days": 7, "delay_hours": 0,
                "label": "Decision push",
                "template_en": "💧 Week post-pitch. Time for a clear yes/no ask.",
                "template_hi": "💧 Pitch के एक हफ़्ते बाद। अब clear yes/no ask का समय।",
                "wa_template_en": "Hi {first_name}, totally fine if this isn't the right time — could you let me know either way? I'll respect your decision and stop following up if it's a no. 🙏",
                "wa_template_hi": "नमस्ते {first_name}, अगर यह सही समय नहीं है तो बिल्कुल ठीक — बस मुझे एक बार बता दें। आपके decision को मानूँगा और अगर 'No' है तो आगे follow-up नहीं करूँगा। 🙏"
            },
        ],
    },
    {
        "name": "Post-Meeting Follow-up",
        "description": "Convert in-person/call meetings into closed deals.",
        "trigger_event": "lead_stage_change",
        "trigger_value": "contacted",
        "steps": [
            {
                "delay_days": 0, "delay_hours": 4,
                "label": "Thank you + recap",
                "template_en": "💧 Send a 'thanks for meeting' WhatsApp to {first_name} within 4 hrs of contact — this is the highest-converting touch.",
                "template_hi": "💧 Contact के 4 घंटों में {first_name} को 'thanks for meeting' WhatsApp भेजें — यह सबसे ज़्यादा converting touch है।",
                "wa_template_en": "Thanks for your time today, {first_name}! As discussed, I'll prepare a personalised plan and share it within 48 hours. Any urgent questions, just message here.",
                "wa_template_hi": "आज समय देने के लिए धन्यवाद, {first_name}! जैसा हमने बात की, मैं एक personalised plan तैयार करूँगा और 48 घंटों में share करूँगा। कोई urgent question हो तो यहाँ message कीजिए।"
            },
            {
                "delay_days": 3, "delay_hours": 0,
                "label": "Send proposal",
                "template_en": "💧 3 days since meeting. Time to share the proposal/plan you promised to {first_name}.",
                "template_hi": "💧 Meeting के 3 दिन बाद। {first_name} को promise किया हुआ proposal/plan share करने का समय।",
                "wa_template_en": "Hi {first_name}, here's the personalised plan I promised. Take your time to review — happy to do a 10-min walkthrough whenever convenient.",
                "wa_template_hi": "नमस्ते {first_name}, यह वो personalised plan है जो मैंने promise किया था। आराम से review कीजिए — जब भी convenient हो 10-min walkthrough करवा दूँगा।"
            },
            {
                "delay_days": 6, "delay_hours": 0,
                "label": "Walkthrough offer",
                "template_en": "💧 6 days post-meeting. Offer a walkthrough call to clarify the plan.",
                "template_hi": "💧 Meeting के 6 दिन बाद। Plan समझाने के लिए walkthrough call offer करें।",
                "wa_template_en": "Hi {first_name}, did you get a chance to review the plan? Happy to do a quick 10-min call to walk you through — would Tuesday or Wednesday work?",
                "wa_template_hi": "नमस्ते {first_name}, plan review करने का मौका मिला? एक quick 10-min call से समझा देता हूँ — Tuesday या Wednesday ठीक रहेगा?"
            },
            {
                "delay_days": 10, "delay_hours": 0,
                "label": "Soft close",
                "template_en": "💧 10 days. Time for a soft close — surface the value one more time.",
                "template_hi": "💧 10 दिन। अब soft close का समय — value को एक बार और surface करें।",
                "wa_template_en": "Hi {first_name}, just wanted to check in — every month without cover is a month of risk for your family. If you want to start small, I can suggest the most affordable option. Worth a 5-min chat?",
                "wa_template_hi": "नमस्ते {first_name}, बस check कर रहा हूँ — बिना cover का हर महीना परिवार के लिए risk का महीना है। अगर छोटी शुरुआत करनी हो तो मैं सबसे affordable option suggest कर सकता हूँ। एक 5-min chat worth है?"
            },
        ],
    },
]


async def seed_default_sequences_for_tenant(tenant_id: int) -> int:
    """Seed the 3 default drip sequences for a new tenant. Idempotent."""
    # Skip if already seeded
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM nurture_sequences WHERE tenant_id=? AND is_seed=1",
            (tenant_id,))
        row = await cur.fetchone()
        if row and row[0] > 0:
            return 0
    created = 0
    for spec in DEFAULT_SEQUENCES:
        sid = await create_sequence(
            tenant_id=tenant_id, name=spec["name"], description=spec["description"],
            trigger_event=spec["trigger_event"], trigger_value=spec["trigger_value"],
            is_seed=1)
        for i, step in enumerate(spec["steps"]):
            await add_step(
                sequence_id=sid, step_order=i + 1,
                delay_days=step["delay_days"], delay_hours=step["delay_hours"],
                channel="telegram_agent", label=step["label"],
                template_en=step["template_en"], template_hi=step["template_hi"],
                wa_template_en=step.get("wa_template_en", ""),
                wa_template_hi=step.get("wa_template_hi", ""))
        created += 1
    logger.info("Nurture: seeded %d default sequences for tenant %d", created, tenant_id)
    return created


async def seed_for_all_tenants():
    """Seed defaults for any tenant that doesn't have them yet. Run once at startup."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT tenant_id FROM tenants WHERE is_active=1")
        tenants = [r["tenant_id"] for r in await cur.fetchall()]
    seeded = 0
    for tid in tenants:
        if await seed_default_sequences_for_tenant(tid):
            seeded += 1
    logger.info("Nurture: seeded defaults for %d tenants", seeded)
    return seeded
