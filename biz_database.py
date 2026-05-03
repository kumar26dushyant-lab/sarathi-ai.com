# =============================================================================
#  biz_database.py — Sarathi-AI Business Technologies: CRM Database Layer
# =============================================================================
#
#  Multi-tenant async SQLite database for financial advisor CRM SaaS.
#  Tables: tenants, agents, leads, policies, interactions, reminders,
#          greetings_log, calculator_sessions, daily_summary, invite_codes
#
# =============================================================================

import aiosqlite
import json
import logging
import os
import secrets
from datetime import datetime, date, timedelta
from contextlib import asynccontextmanager
from typing import Optional

logger = logging.getLogger("sarathi.db")

DB_PATH = "sarathi_biz.db"


@asynccontextmanager
async def _get_db():
    """Async context manager that yields an aiosqlite connection."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn

# =============================================================================
#  SCHEMA
# =============================================================================

SCHEMA = """
-- Tenants (firms / individual agents subscribing to Sarathi)
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    firm_name       TEXT NOT NULL,
    owner_name      TEXT NOT NULL,
    phone           TEXT NOT NULL,
    email           TEXT,
    -- Branding
    brand_tagline   TEXT DEFAULT 'AI-Powered CRM for Financial Advisors',
    brand_cta       TEXT DEFAULT 'Grow Your Advisory Business',
    brand_phone     TEXT,
    brand_email     TEXT,
    brand_primary_color TEXT DEFAULT '#1a56db',
    brand_accent_color  TEXT DEFAULT '#ea580c',
    -- IRDAI verification
    irdai_license   TEXT,
    irdai_verified  TEXT DEFAULT 'none',
    -- Subscription
    plan            TEXT DEFAULT 'trial',
    subscription_status TEXT DEFAULT 'trial',
    razorpay_sub_id TEXT,
    trial_ends_at   TEXT,
    subscription_expires_at TEXT,
    max_agents      INTEGER DEFAULT 1,
    -- WhatsApp Cloud API config (per-tenant)
    wa_phone_id     TEXT,
    wa_access_token TEXT,
    wa_verify_token TEXT,
    -- Telegram (shared bot, but store owner telegram_id; optional per-tenant bot)
    owner_telegram_id TEXT,
    tg_bot_token    TEXT,
    -- Settings
    lang            TEXT DEFAULT 'en',
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Invite codes (for adding agents to a tenant)
CREATE TABLE IF NOT EXISTS invite_codes (
    code            TEXT PRIMARY KEY,
    tenant_id       INTEGER NOT NULL,
    created_by      INTEGER NOT NULL,
    max_uses        INTEGER DEFAULT 1,
    used_count      INTEGER DEFAULT 0,
    expires_at      TEXT,
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (created_by) REFERENCES agents(agent_id)
);

-- Agent profiles (belong to a tenant)
CREATE TABLE IF NOT EXISTS agents (
    agent_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       INTEGER NOT NULL,
    telegram_id     TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    phone           TEXT,
    email           TEXT,
    role            TEXT DEFAULT 'agent',
    lang            TEXT DEFAULT 'en',
    onboarding_step TEXT,
    is_active       INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);

-- Lead pipeline (prospects → clients)
CREATE TABLE IF NOT EXISTS leads (
    lead_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL,
    name            TEXT NOT NULL,
    phone           TEXT,
    whatsapp        TEXT,
    email           TEXT,
    dob             TEXT,
    anniversary     TEXT,
    city            TEXT,
    occupation      TEXT,
    monthly_income  REAL,
    family_size     TEXT,
    need_type       TEXT DEFAULT 'health',
    stage           TEXT DEFAULT 'prospect',
    source          TEXT DEFAULT 'direct',
    notes           TEXT,
    sum_insured     REAL,
    premium_budget  REAL,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    closed_at       TEXT,
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

-- Policies sold (closed deals)
CREATE TABLE IF NOT EXISTS policies (
    policy_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id         INTEGER NOT NULL,
    agent_id        INTEGER NOT NULL,
    policy_number   TEXT,
    insurer         TEXT,
    plan_name       TEXT,
    policy_type     TEXT DEFAULT 'health',
    sum_insured     REAL,
    premium         REAL,
    premium_mode    TEXT DEFAULT 'annual',
    start_date      TEXT,
    end_date        TEXT,
    renewal_date    TEXT,
    status          TEXT DEFAULT 'active',
    commission      REAL DEFAULT 0,
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

-- Interaction log (every touchpoint with a lead/client)
CREATE TABLE IF NOT EXISTS interactions (
    interaction_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id         INTEGER NOT NULL,
    agent_id        INTEGER NOT NULL,
    type            TEXT NOT NULL,
    channel         TEXT DEFAULT 'telegram',
    summary         TEXT,
    follow_up_date  TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

-- Reminders (premium due, renewals, follow-ups)
CREATE TABLE IF NOT EXISTS reminders (
    reminder_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL,
    lead_id         INTEGER,
    policy_id       INTEGER,
    type            TEXT NOT NULL,
    due_date        TEXT NOT NULL,
    message         TEXT,
    status          TEXT DEFAULT 'pending',
    sent_at         TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

-- Greetings log (birthday/anniversary messages sent)
CREATE TABLE IF NOT EXISTS greetings_log (
    greeting_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id         INTEGER NOT NULL,
    agent_id        INTEGER NOT NULL,
    type            TEXT NOT NULL,
    channel         TEXT DEFAULT 'whatsapp',
    message         TEXT,
    sent_at         TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
);

-- Calculator sessions (when agent uses a calculator for a pitch)
CREATE TABLE IF NOT EXISTS calculator_sessions (
    session_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL,
    lead_id         INTEGER,
    calc_type       TEXT NOT NULL,
    inputs          TEXT,
    result          TEXT,
    pdf_path        TEXT,
    shared_via      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Agent daily summary log
CREATE TABLE IF NOT EXISTS daily_summary (
    summary_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL,
    summary_date    TEXT NOT NULL,
    new_leads       INTEGER DEFAULT 0,
    follow_ups_done INTEGER DEFAULT 0,
    deals_closed    INTEGER DEFAULT 0,
    premium_earned  REAL DEFAULT 0,
    commission      REAL DEFAULT 0,
    greetings_sent  INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Voice-to-Action logs
CREATE TABLE IF NOT EXISTS voice_logs (
    voice_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL,
    lead_id         INTEGER,
    transcript      TEXT,
    extracted_data  TEXT,
    audio_duration  INTEGER,
    status          TEXT DEFAULT 'processed',
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

-- Abuse/content-violation warnings & auto-block tracking
CREATE TABLE IF NOT EXISTS abuse_warnings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL,
    warning_count   INTEGER DEFAULT 1,
    last_text       TEXT,
    blocked_until   TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);

-- Claims Helper tracking
CREATE TABLE IF NOT EXISTS claims (
    claim_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        INTEGER NOT NULL,
    lead_id         INTEGER NOT NULL,
    policy_id       INTEGER,
    claim_type      TEXT NOT NULL,
    claim_amount    REAL,
    incident_date   TEXT,
    description     TEXT,
    status          TEXT DEFAULT 'initiated',
    hospital_name   TEXT,
    insurer_ref     TEXT,
    documents_json  TEXT DEFAULT '[]',
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id),
    FOREIGN KEY (policy_id) REFERENCES policies(policy_id)
);

-- Audit log (tracks important actions for compliance)
CREATE TABLE IF NOT EXISTS audit_log (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       INTEGER,
    agent_id        INTEGER,
    role            TEXT,
    action          TEXT NOT NULL,
    detail          TEXT,
    ip_address      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- Support tickets (help & support system)
CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       INTEGER,
    agent_id        INTEGER,
    subject         TEXT NOT NULL,
    description     TEXT NOT NULL,
    category        TEXT DEFAULT 'general',
    priority        TEXT DEFAULT 'normal',
    status          TEXT DEFAULT 'open',
    assigned_to     TEXT,
    resolution      TEXT,
    is_trial        INTEGER DEFAULT 0,
    contact_name    TEXT,
    contact_phone   TEXT,
    contact_email   TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    resolved_at     TEXT
);

-- Support ticket messages (thread)
CREATE TABLE IF NOT EXISTS ticket_messages (
    message_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id       INTEGER NOT NULL,
    sender_type     TEXT DEFAULT 'customer',
    sender_name     TEXT,
    message         TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (ticket_id) REFERENCES support_tickets(ticket_id)
);

-- Affiliate support tickets
CREATE TABLE IF NOT EXISTS affiliate_tickets (
    ticket_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliate_id    INTEGER NOT NULL,
    subject         TEXT NOT NULL,
    category        TEXT DEFAULT 'general',
    priority        TEXT DEFAULT 'normal',
    status          TEXT DEFAULT 'open',
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    resolved_at     TEXT,
    FOREIGN KEY (affiliate_id) REFERENCES affiliates(affiliate_id)
);

CREATE TABLE IF NOT EXISTS affiliate_ticket_messages (
    message_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id       INTEGER NOT NULL,
    sender_type     TEXT DEFAULT 'affiliate',
    sender_name     TEXT,
    message         TEXT NOT NULL,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (ticket_id) REFERENCES affiliate_tickets(ticket_id)
);

-- Affiliates / Partners
CREATE TABLE IF NOT EXISTS affiliates (
    affiliate_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    phone           TEXT NOT NULL,
    email           TEXT,
    referral_code   TEXT UNIQUE NOT NULL,
    commission_pct  REAL DEFAULT 20.0,
    status          TEXT DEFAULT 'pending_verification',
    phone_verified  INTEGER DEFAULT 0,
    email_verified  INTEGER DEFAULT 0,
    approved        INTEGER DEFAULT 0,
    total_referrals INTEGER DEFAULT 0,
    successful_conversions INTEGER DEFAULT 0,
    total_earned    REAL DEFAULT 0,
    total_paid      REAL DEFAULT 0,
    upi_id          TEXT,
    bank_account    TEXT,
    ifsc_code       TEXT,
    bank_name       TEXT,
    account_holder  TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

-- Affiliate referrals tracking
CREATE TABLE IF NOT EXISTS affiliate_referrals (
    referral_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliate_id    INTEGER NOT NULL,
    tenant_id       INTEGER,
    referral_code   TEXT NOT NULL,
    referred_phone  TEXT,
    referred_name   TEXT,
    status          TEXT DEFAULT 'pending',
    plan_activated  TEXT,
    commission_amount REAL DEFAULT 0,
    paid            INTEGER DEFAULT 0,
    cooling_ends_at TEXT,
    payout_status   TEXT DEFAULT 'pending',
    payout_id       INTEGER,
    created_at      TEXT DEFAULT (datetime('now')),
    converted_at    TEXT,
    FOREIGN KEY (affiliate_id) REFERENCES affiliates(affiliate_id),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (payout_id) REFERENCES affiliate_payouts(payout_id)
);

-- Affiliate payouts tracking
CREATE TABLE IF NOT EXISTS affiliate_payouts (
    payout_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    affiliate_id    INTEGER NOT NULL,
    amount          REAL NOT NULL,
    method          TEXT DEFAULT 'upi',
    upi_id          TEXT,
    bank_account    TEXT,
    ifsc_code       TEXT,
    reference_id    TEXT,
    status          TEXT DEFAULT 'pending',
    initiated_by    TEXT DEFAULT 'system',
    note            TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    completed_at    TEXT,
    FOREIGN KEY (affiliate_id) REFERENCES affiliates(affiliate_id)
);

CREATE TABLE IF NOT EXISTS system_events (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,         -- error, security, anomaly, info, warning
    severity        TEXT DEFAULT 'medium', -- low, medium, high, critical
    category        TEXT DEFAULT 'system', -- system, auth, api, bot, payment, data
    title           TEXT NOT NULL,
    detail          TEXT,
    tenant_id       INTEGER,
    agent_id        INTEGER,
    ip_address      TEXT,
    resolved        INTEGER DEFAULT 0,
    resolved_by     TEXT,
    resolved_at     TEXT,
    auto_fixed      INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sysevents_type ON system_events(event_type);
CREATE INDEX IF NOT EXISTS idx_sysevents_severity ON system_events(severity);
CREATE INDEX IF NOT EXISTS idx_sysevents_resolved ON system_events(resolved);

-- Processed payments (idempotency guard for webhooks + frontend verify)
CREATE TABLE IF NOT EXISTS processed_payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    razorpay_payment_id TEXT NOT NULL UNIQUE,
    tenant_id           INTEGER,
    plan_key            TEXT,
    source              TEXT NOT NULL,       -- 'webhook' or 'frontend_verify'
    amount_paise        INTEGER DEFAULT 0,
    processed_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_pp_payment ON processed_payments(razorpay_payment_id);

-- Owner → Advisor nudge messages
CREATE TABLE IF NOT EXISTS nudges (
    nudge_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       INTEGER NOT NULL,
    sender_agent_id INTEGER NOT NULL,      -- owner who sent
    target_agent_id INTEGER NOT NULL,      -- advisor who receives
    nudge_type      TEXT NOT NULL DEFAULT 'followup',  -- followup, new_lead, renewal, broadcast, custom
    lead_id         INTEGER,               -- related lead (NULL for broadcast)
    message         TEXT NOT NULL,          -- the message sent to advisor
    status          TEXT DEFAULT 'sent',    -- sent, delivered, acted, dismissed
    acted_at        TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (sender_agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY (target_agent_id) REFERENCES agents(agent_id),
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
);
CREATE INDEX IF NOT EXISTS idx_nudges_target ON nudges(target_agent_id, status);
CREATE INDEX IF NOT EXISTS idx_nudges_tenant ON nudges(tenant_id, created_at);

-- ── AI Usage Tracking ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_usage_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id       INTEGER,
    agent_id        INTEGER,
    feature         TEXT NOT NULL,
    tokens_in       INTEGER DEFAULT 0,
    tokens_out      INTEGER DEFAULT 0,
    cost_usd        REAL DEFAULT 0,
    source          TEXT DEFAULT 'web',
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
    FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
);
CREATE INDEX IF NOT EXISTS idx_ai_usage_tenant ON ai_usage_log(tenant_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_usage_agent ON ai_usage_log(agent_id, created_at);
"""

# =============================================================================
#  INIT
# =============================================================================

async def init_db():
    """Create all tables and run migrations (idempotent)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.executescript(SCHEMA)

        # --- Migrations (safe to re-run) ---
        migrations = [
            "ALTER TABLE agents ADD COLUMN lang TEXT DEFAULT 'en'",
            "ALTER TABLE agents ADD COLUMN tenant_id INTEGER DEFAULT 0",
            "ALTER TABLE agents ADD COLUMN role TEXT DEFAULT 'agent'",
            "ALTER TABLE agents ADD COLUMN onboarding_step TEXT",
            "ALTER TABLE tenants ADD COLUMN tg_bot_token TEXT",
            "ALTER TABLE tenants ADD COLUMN feature_overrides TEXT DEFAULT '{}'",
            # Phase-2 migrations: city, account_type, signup_channel
            "ALTER TABLE tenants ADD COLUMN city TEXT DEFAULT ''",
            "ALTER TABLE tenants ADD COLUMN account_type TEXT DEFAULT 'firm'",
            "ALTER TABLE tenants ADD COLUMN signup_channel TEXT DEFAULT 'web'",
            "ALTER TABLE agents ADD COLUMN profile_photo TEXT DEFAULT ''",
            "ALTER TABLE agents ADD COLUMN city TEXT DEFAULT ''",
            # Affiliate verification columns
            "ALTER TABLE affiliates ADD COLUMN phone_verified INTEGER DEFAULT 0",
            "ALTER TABLE affiliates ADD COLUMN email_verified INTEGER DEFAULT 0",
            "ALTER TABLE affiliates ADD COLUMN approved INTEGER DEFAULT 0",
            # Tenant referral tracking
            "ALTER TABLE tenants ADD COLUMN referral_code TEXT DEFAULT ''",
            # Branding: logo path + credentials
            "ALTER TABLE tenants ADD COLUMN brand_logo TEXT DEFAULT ''",
            "ALTER TABLE tenants ADD COLUMN brand_credentials TEXT DEFAULT ''",
            # Affiliate payout fields
            "ALTER TABLE affiliates ADD COLUMN upi_id TEXT",
            "ALTER TABLE affiliates ADD COLUMN bank_account TEXT",
            "ALTER TABLE affiliates ADD COLUMN ifsc_code TEXT",
            "ALTER TABLE affiliates ADD COLUMN bank_name TEXT",
            "ALTER TABLE affiliates ADD COLUMN account_holder TEXT",
            # Affiliate referrals: cooling period + payout status
            "ALTER TABLE affiliate_referrals ADD COLUMN cooling_ends_at TEXT",
            "ALTER TABLE affiliate_referrals ADD COLUMN payout_status TEXT DEFAULT 'pending'",
            "ALTER TABLE affiliate_referrals ADD COLUMN payout_id INTEGER",
            # Agent activity tracking for session expiry + inactive cleanup
            "ALTER TABLE agents ADD COLUMN last_active TEXT",
            # Audit log: track actor role for compliance
            "ALTER TABLE audit_log ADD COLUMN role TEXT",
            # ── Phase 1: SEBI Compliance & DPDP Consent ──
            # Agent regulatory credentials
            "ALTER TABLE agents ADD COLUMN arn_number TEXT DEFAULT ''",
            "ALTER TABLE agents ADD COLUMN euin TEXT DEFAULT ''",
            "ALTER TABLE agents ADD COLUMN irdai_license TEXT DEFAULT ''",
            # Tenant regulatory credentials
            "ALTER TABLE tenants ADD COLUMN sebi_ria_code TEXT DEFAULT ''",
            "ALTER TABLE tenants ADD COLUMN amfi_reg TEXT DEFAULT ''",
            "ALTER TABLE tenants ADD COLUMN compliance_disclaimer TEXT DEFAULT ''",
            # DPDP consent for leads
            "ALTER TABLE leads ADD COLUMN dpdp_consent INTEGER DEFAULT 0",
            "ALTER TABLE leads ADD COLUMN dpdp_consent_date TEXT",
            # Phase: Time-aware follow-ups + accountability
            "ALTER TABLE interactions ADD COLUMN follow_up_time TEXT",
            "ALTER TABLE interactions ADD COLUMN follow_up_status TEXT DEFAULT 'pending'",
            # Phase: Cross-visibility — track who created the follow-up
            "ALTER TABLE interactions ADD COLUMN created_by_agent_id INTEGER",
            # Phase: Task system — explicit assignee (who must do the follow-up)
            "ALTER TABLE interactions ADD COLUMN assigned_to_agent_id INTEGER",
            # Branding: website URL for PDFs and reports
            "ALTER TABLE tenants ADD COLUMN brand_website TEXT DEFAULT ''",
            # Founding customer: self-referral 20% discount for 1st year
            "ALTER TABLE tenants ADD COLUMN founding_discount INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN founding_discount_until TEXT",
            # ── Phase: Document AI + CRM Enhancement (March 30, 2026) ──
            # Leads: client lifecycle + household grouping
            "ALTER TABLE leads ADD COLUMN client_type TEXT DEFAULT 'prospect'",
            "ALTER TABLE leads ADD COLUMN household_id TEXT",
            "ALTER TABLE leads ADD COLUMN relation TEXT DEFAULT 'self'",
            "ALTER TABLE leads ADD COLUMN pan_number TEXT",
            "ALTER TABLE leads ADD COLUMN address TEXT",
            "ALTER TABLE leads ADD COLUMN annual_income REAL",
            # Policies: enriched tracking
            "ALTER TABLE policies ADD COLUMN sold_by_agent INTEGER DEFAULT 1",
            "ALTER TABLE policies ADD COLUMN policy_status TEXT DEFAULT 'active'",
            "ALTER TABLE policies ADD COLUMN folio_number TEXT",
            "ALTER TABLE policies ADD COLUMN fund_name TEXT",
            "ALTER TABLE policies ADD COLUMN sip_amount REAL",
            "ALTER TABLE policies ADD COLUMN maturity_date TEXT",
            "ALTER TABLE policies ADD COLUMN maturity_value REAL",
            "ALTER TABLE policies ADD COLUMN riders TEXT",
            # ── Feature 4: Advisor Microsite (April 30, 2026) ──
            "ALTER TABLE tenants ADD COLUMN microsite_slug TEXT",
            "ALTER TABLE tenants ADD COLUMN microsite_bio TEXT DEFAULT ''",
            "ALTER TABLE tenants ADD COLUMN microsite_years_exp INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN microsite_families_served INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN microsite_services TEXT DEFAULT '[]'",
            "ALTER TABLE tenants ADD COLUMN microsite_testimonials TEXT DEFAULT '[]'",
            "ALTER TABLE tenants ADD COLUMN microsite_show_badge INTEGER DEFAULT 1",
            "ALTER TABLE tenants ADD COLUMN microsite_published INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN microsite_photo TEXT DEFAULT ''",
            "ALTER TABLE tenants ADD COLUMN microsite_views INTEGER DEFAULT 0",
        ]
        for m in migrations:
            try:
                await conn.execute(m)
            except Exception:
                pass  # column already exists

        # --- Unique constraints as indexes (idempotent) ---
        try:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_tg_bot_token "
                "ON tenants(tg_bot_token) WHERE tg_bot_token IS NOT NULL AND tg_bot_token != ''")
        except Exception:
            pass  # older SQLite doesn't support partial indexes — app-level check still enforces

        # Microsite slug unique index (app also validates)
        try:
            await conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tenants_microsite_slug "
                "ON tenants(microsite_slug) WHERE microsite_slug IS NOT NULL AND microsite_slug != ''")
        except Exception:
            pass

        # --- Create lead_notes table (threaded notes for CRM accountability) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_notes (
                note_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id         INTEGER NOT NULL,
                interaction_id  INTEGER,
                agent_id        INTEGER NOT NULL,
                author_role     TEXT DEFAULT 'advisor',
                note_text       TEXT NOT NULL,
                parent_note_id  INTEGER,
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (lead_id) REFERENCES leads(lead_id),
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id),
                FOREIGN KEY (interaction_id) REFERENCES interactions(interaction_id),
                FOREIGN KEY (parent_note_id) REFERENCES lead_notes(note_id)
            )
        """)

        # --- Create affiliate_payouts table if not exists ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_payouts (
                payout_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_id    INTEGER NOT NULL,
                amount          REAL NOT NULL,
                method          TEXT DEFAULT 'upi',
                upi_id          TEXT,
                bank_account    TEXT,
                ifsc_code       TEXT,
                reference_id    TEXT,
                status          TEXT DEFAULT 'pending',
                initiated_by    TEXT DEFAULT 'system',
                note            TEXT,
                created_at      TEXT DEFAULT (datetime('now')),
                completed_at    TEXT,
                FOREIGN KEY (affiliate_id) REFERENCES affiliates(affiliate_id)
            )
        """)

        # --- Create health_checks table (Tier 2 health monitor) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS health_checks (
                check_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL,
                category        TEXT NOT NULL,
                check_name      TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'healthy',
                detail          TEXT,
                response_ms     INTEGER DEFAULT 0,
                auto_fixable    INTEGER DEFAULT 0,
                fix_applied     INTEGER DEFAULT 0,
                fix_detail      TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)

        # --- Create health_alerts table (email alerts sent) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS health_alerts (
                alert_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id          TEXT NOT NULL,
                severity        TEXT NOT NULL DEFAULT 'warning',
                title           TEXT NOT NULL,
                detail          TEXT,
                emailed         INTEGER DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)

        # --- Create policy_members table (insured persons per policy) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS policy_members (
                member_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                policy_id       INTEGER NOT NULL,
                lead_id         INTEGER,
                member_name     TEXT NOT NULL,
                relation        TEXT DEFAULT 'self',
                dob             TEXT,
                age             INTEGER,
                sum_insured     REAL,
                premium_share   REAL,
                coverage_type   TEXT DEFAULT 'floater',
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (policy_id) REFERENCES policies(policy_id),
                FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
            )
        """)

        # --- Create affiliate_commissions table (recurring commission tracking) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_commissions (
                commission_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                affiliate_id    INTEGER NOT NULL,
                referral_id     INTEGER,
                tenant_id       INTEGER NOT NULL,
                payment_id      TEXT,
                plan            TEXT,
                payment_amount  REAL DEFAULT 0,
                commission_amount REAL NOT NULL DEFAULT 0,
                commission_pct  REAL DEFAULT 20,
                payout_status   TEXT DEFAULT 'cooling',
                cooling_ends_at TEXT,
                payout_id       INTEGER,
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (affiliate_id) REFERENCES affiliates(affiliate_id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY (payout_id) REFERENCES affiliate_payouts(payout_id)
            )
        """)
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_aff_comm_payment "
            "ON affiliate_commissions(payment_id) WHERE payment_id IS NOT NULL")

        # ─────────────────────────────────────────────────────────────────────
        #  WhatsApp Automation v2 (Evolution API + Agent-Assist Model)
        #  Phase 1 — Foundation tables. Safe to run on existing DB.
        # ─────────────────────────────────────────────────────────────────────

        # WA tenant-level configuration: instance, phone, plan tier behavior
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_instances (
                instance_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id            INTEGER NOT NULL,
                agent_id             INTEGER,
                evolution_instance   TEXT UNIQUE NOT NULL,
                phone_number         TEXT,
                display_name         TEXT,
                sim_type             TEXT DEFAULT 'dedicated',
                status               TEXT DEFAULT 'pending',
                qr_code              TEXT,
                qr_expires_at        TEXT,
                last_connected_at    TEXT,
                last_disconnected_at TEXT,
                ban_warmup_until     TEXT,
                health_score         INTEGER DEFAULT 100,
                spam_reports_count   INTEGER DEFAULT 0,
                paused_until         TEXT,
                pause_reason         TEXT,
                acknowledgement      TEXT DEFAULT '{}',
                created_at           TEXT DEFAULT (datetime('now')),
                updated_at           TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wa_inst_tenant ON wa_instances(tenant_id)")

        # Conversation thread per (instance, customer)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_conversations (
                conversation_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id         INTEGER NOT NULL,
                tenant_id           INTEGER NOT NULL,
                lead_id             INTEGER,
                customer_phone      TEXT NOT NULL,
                customer_name       TEXT,
                trust_score         INTEGER DEFAULT 50,
                consent_status      TEXT DEFAULT 'unknown',
                last_inbound_at     TEXT,
                last_outbound_at    TEXT,
                last_message_at     TEXT,
                unread_count        INTEGER DEFAULT 0,
                escalated           INTEGER DEFAULT 0,
                escalation_reason   TEXT,
                created_at          TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (instance_id) REFERENCES wa_instances(instance_id),
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
                FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
            )
        """)
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_conv_unique "
            "ON wa_conversations(instance_id, customer_phone)")

        # All WhatsApp messages (in/out, suggestion/sent/failed)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_messages (
                message_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id     INTEGER NOT NULL,
                instance_id         INTEGER NOT NULL,
                wa_message_id       TEXT,
                direction           TEXT NOT NULL,
                msg_type            TEXT DEFAULT 'text',
                content             TEXT,
                media_url           TEXT,
                media_mimetype      TEXT,
                status              TEXT DEFAULT 'pending',
                source              TEXT DEFAULT 'manual',
                sent_at             TEXT,
                delivered_at        TEXT,
                read_at             TEXT,
                failed_reason       TEXT,
                ai_suggestion_id    INTEGER,
                created_at          TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES wa_conversations(conversation_id),
                FOREIGN KEY (instance_id) REFERENCES wa_instances(instance_id)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wa_msg_conv ON wa_messages(conversation_id, created_at DESC)")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wa_msg_wid ON wa_messages(wa_message_id)")

        # AI-generated reply suggestions awaiting agent approval
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_suggestions (
                suggestion_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id     INTEGER NOT NULL,
                instance_id         INTEGER NOT NULL,
                trigger_message_id  INTEGER,
                intent              TEXT,
                suggested_text      TEXT NOT NULL,
                confidence          REAL DEFAULT 0.5,
                status              TEXT DEFAULT 'pending',
                approved_at         TEXT,
                rejected_at         TEXT,
                edited_text         TEXT,
                sent_message_id     INTEGER,
                created_at          TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (conversation_id) REFERENCES wa_conversations(conversation_id),
                FOREIGN KEY (instance_id) REFERENCES wa_instances(instance_id),
                FOREIGN KEY (trigger_message_id) REFERENCES wa_messages(message_id)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wa_sug_status ON wa_suggestions(status, created_at DESC)")

        # Per-customer Brain Lock (mutex across telegram/whatsapp/web/scheduler)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_brain_locks (
                lock_id             INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id           INTEGER NOT NULL,
                customer_phone      TEXT NOT NULL,
                source              TEXT NOT NULL,
                acquired_at         TEXT DEFAULT (datetime('now')),
                expires_at          TEXT NOT NULL,
                released_at         TEXT,
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
            )
        """)
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_lock_active "
            "ON wa_brain_locks(tenant_id, customer_phone) WHERE released_at IS NULL")

        # Outbound queue (rate-limited send pipeline; consumed by Node.js bridge)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS wa_send_queue (
                queue_id            INTEGER PRIMARY KEY AUTOINCREMENT,
                instance_id         INTEGER NOT NULL,
                conversation_id     INTEGER,
                customer_phone      TEXT NOT NULL,
                msg_type            TEXT DEFAULT 'text',
                content             TEXT,
                media_url           TEXT,
                priority            INTEGER DEFAULT 5,
                source              TEXT DEFAULT 'manual',
                idempotency_key     TEXT,
                scheduled_for       TEXT,
                attempts            INTEGER DEFAULT 0,
                last_attempt_at     TEXT,
                status              TEXT DEFAULT 'queued',
                error_message       TEXT,
                sent_message_id     INTEGER,
                created_at          TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (instance_id) REFERENCES wa_instances(instance_id)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wa_queue_pickup "
            "ON wa_send_queue(status, scheduled_for, priority)")
        await conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_queue_idem "
            "ON wa_send_queue(idempotency_key) WHERE idempotency_key IS NOT NULL")

        # WA-specific migrations on existing tables (safe — wrapped in try below)
        wa_migrations = [
            "ALTER TABLE agents ADD COLUMN wa_instance_id INTEGER",
            "ALTER TABLE agents ADD COLUMN wa_phone TEXT",
            "ALTER TABLE agents ADD COLUMN wa_self_crm_enabled INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN wa_enabled INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN wa_tier TEXT DEFAULT 'none'",
            "ALTER TABLE tenants ADD COLUMN wa_addon_reminders INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN wa_addon_ai_assist INTEGER DEFAULT 0",
            "ALTER TABLE tenants ADD COLUMN wa_tos_accepted_at TEXT",
            "ALTER TABLE tenants ADD COLUMN gdrive_connected INTEGER DEFAULT 0",
        ]
        for m in wa_migrations:
            try:
                await conn.execute(m)
            except Exception:
                pass

        await conn.commit()
    logger.info("Database initialized: %s", DB_PATH)


# =============================================================================
#  TENANT OPERATIONS
# =============================================================================

async def create_tenant(firm_name: str, owner_name: str, phone: str,
                        email: str = None, owner_telegram_id: str = None,
                        lang: str = "en", city: str = "",
                        account_type: str = "firm",
                        signup_channel: str = "web") -> int:
    """Create a new tenant (firm). Returns tenant_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        trial_end = (datetime.now() + timedelta(days=14)).isoformat()
        cursor = await conn.execute(
            """INSERT INTO tenants
               (firm_name, owner_name, phone, email, owner_telegram_id,
                brand_phone, brand_email, lang, trial_ends_at,
                city, account_type, signup_channel)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (firm_name, owner_name, phone, email, owner_telegram_id,
             phone, email, lang, trial_end,
             city, account_type, signup_channel))
        await conn.commit()
        return cursor.lastrowid


async def create_tenant_with_owner(firm_name: str, owner_name: str, phone: str,
                                   email: str = None, owner_telegram_id: str = None,
                                   lang: str = "en", city: str = "",
                                   account_type: str = "firm",
                                   signup_channel: str = "web") -> dict:
    """Create tenant AND owner agent atomically. Returns {tenant_id, agent_id}.
    The owner agent is created with telegram_id=NULL for web signups.
    When the owner later does /start on Telegram, the bot matches by phone
    and links the telegram_id to this existing agent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        trial_end = (datetime.now() + timedelta(days=14)).isoformat()
        # Create tenant
        cursor = await conn.execute(
            """INSERT INTO tenants
               (firm_name, owner_name, phone, email, owner_telegram_id,
                brand_phone, brand_email, lang, trial_ends_at,
                city, account_type, signup_channel)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (firm_name, owner_name, phone, email, owner_telegram_id,
             phone, email, lang, trial_end,
             city, account_type, signup_channel))
        tenant_id = cursor.lastrowid
        # Create owner agent (telegram_id=NULL for web signups, set later)
        # Create owner agent (use web_<tenant_id> placeholder for web signups;
        # link_agent_telegram() will upgrade it when agent opens Telegram bot)
        tg_id = owner_telegram_id or f"web_{tenant_id}"
        cursor2 = await conn.execute(
            """INSERT INTO agents
               (tenant_id, telegram_id, name, phone, email, role, lang)
               VALUES (?, ?, ?, ?, ?, 'owner', ?)""",
            (tenant_id, tg_id, owner_name, phone, email, lang))
        agent_id = cursor2.lastrowid
        await conn.commit()
        logger.info("Created tenant %d + owner agent %d (%s)",
                    tenant_id, agent_id, signup_channel)
    # Seed default nurture sequences (idempotent — safe to call)
    try:
        import biz_nurture as _nurture
        await _nurture.seed_default_sequences_for_tenant(tenant_id)
    except Exception as _e:
        logger.warning("Nurture seed for new tenant %d failed: %s", tenant_id, _e)
    return {'tenant_id': tenant_id, 'agent_id': agent_id}


async def link_agent_telegram(phone: str, telegram_id: str) -> Optional[dict]:
    """Link a Telegram ID to an existing agent matched by phone.
    Used when a web-signup owner/agent later does /start on Telegram.
    Handles both NULL telegram_id and placeholder 'web_*' IDs from web invite flow.
    Returns the agent dict if linked, None if no match."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT a.agent_id, a.tenant_id, a.telegram_id, a.name, a.role
               FROM agents a WHERE a.phone = ? AND a.is_active = 1
               ORDER BY a.role = 'owner' DESC LIMIT 1""",
            (phone,))
        row = await cursor.fetchone()
        if not row:
            return None
        agent = dict(row)
        existing_tg = agent.get('telegram_id') or ''
        # Allow linking if: no telegram_id, or any placeholder, or same ID
        is_placeholder = (existing_tg.startswith('web_') or
                          existing_tg.startswith('logout_') or
                          existing_tg.startswith('__unlinked_') or
                          existing_tg.startswith('__deactivated_'))
        if existing_tg and not is_placeholder and existing_tg != telegram_id:
            # Already linked to a different real Telegram account
            return None
        if not existing_tg or is_placeholder:
            await conn.execute(
                "UPDATE agents SET telegram_id = ?, updated_at = datetime('now') "
                "WHERE agent_id = ?",
                (telegram_id, agent['agent_id']))
            await conn.commit()
            logger.info("Linked telegram_id %s to agent %d (phone %s)",
                        telegram_id, agent['agent_id'], phone[-4:])
        return agent


async def link_agent_telegram_by_email(email: str, telegram_id: str) -> Optional[dict]:
    """Link a Telegram ID to an existing agent matched by email.
    Returns the agent dict if linked, None if no match."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT a.agent_id, a.tenant_id, a.telegram_id, a.name, a.role
               FROM agents a WHERE LOWER(a.email) = LOWER(?) AND a.is_active = 1
               ORDER BY a.role = 'owner' DESC LIMIT 1""",
            (email,))
        row = await cursor.fetchone()
        if not row:
            return None
        agent = dict(row)
        existing_tg = agent.get('telegram_id') or ''
        is_placeholder = (existing_tg.startswith('web_') or
                          existing_tg.startswith('logout_') or
                          existing_tg.startswith('__unlinked_') or
                          existing_tg.startswith('__deactivated_'))
        if existing_tg and not is_placeholder and existing_tg != telegram_id:
            return None
        if not existing_tg or is_placeholder:
            await conn.execute(
                "UPDATE agents SET telegram_id = ?, updated_at = datetime('now') "
                "WHERE agent_id = ?",
                (telegram_id, agent['agent_id']))
            await conn.commit()
            logger.info("Linked telegram_id %s to agent %d (email %s)",
                        telegram_id, agent['agent_id'], email)
        return agent


async def get_agent_by_phone_tenant(phone: str, tenant_id: int) -> Optional[dict]:
    """Get agent by phone number within a specific tenant.
    Used for OTP login flow on tenant bots."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT a.*, t.firm_name AS _tenant_firm, t.plan,
                      t.subscription_status
               FROM agents a
               LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
               WHERE a.phone = ? AND a.tenant_id = ? AND a.is_active = 1
               LIMIT 1""",
            (phone, tenant_id))
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d['firm_name'] = d.pop('_tenant_firm', d.get('firm_name', ''))
        return d


async def get_agent_by_email_tenant(email: str, tenant_id: int) -> Optional[dict]:
    """Get agent by email within a specific tenant.
    Used for email-based OTP login flow on tenant bots."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT a.*, t.firm_name AS _tenant_firm, t.plan,
                      t.subscription_status
               FROM agents a
               LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
               WHERE LOWER(a.email) = LOWER(?) AND a.tenant_id = ? AND a.is_active = 1
               LIMIT 1""",
            (email, tenant_id))
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d['firm_name'] = d.pop('_tenant_firm', d.get('firm_name', ''))
        return d


async def unlink_agent_telegram(telegram_id: str) -> bool:
    """Unlink a Telegram ID from an agent (set telegram_id to placeholder).
    Used for /logout command. Returns True if unlinked."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT agent_id FROM agents WHERE telegram_id = ?",
            (telegram_id,))
        row = await cursor.fetchone()
        if not row:
            return False
        agent_id = row[0]
        # Set to placeholder instead of NULL to avoid UNIQUE constraint issues
        placeholder = f"logout_{agent_id}_{int(datetime.now().timestamp())}"
        await conn.execute(
            "UPDATE agents SET telegram_id = ?, updated_at = datetime('now') "
            "WHERE agent_id = ?",
            (placeholder, agent_id))
        await conn.commit()
        logger.info("Unlinked telegram_id %s from agent %d (logout)",
                    telegram_id, agent_id)
        return True


async def get_owner_agent_by_tenant(tenant_id: int) -> Optional[dict]:
    """Get the owner agent for a tenant (regardless of telegram_id).
    Used for cross-channel identity detection (web→telegram linking)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM agents
               WHERE tenant_id = ? AND role = 'owner' AND is_active = 1
               LIMIT 1""",
            (tenant_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_tenant(tenant_id: int) -> Optional[dict]:
    """Get tenant by ID."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_tenant_by_owner(telegram_id: str) -> Optional[dict]:
    """Get tenant by owner's telegram ID."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tenants WHERE owner_telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def update_tenant(tenant_id: int, **kwargs) -> bool:
    """Update tenant fields dynamically."""
    allowed = {'firm_name', 'owner_name', 'phone', 'email',
               'brand_tagline', 'brand_cta', 'brand_phone', 'brand_email',
               'brand_primary_color', 'brand_accent_color',
               'brand_logo', 'brand_credentials',
               'irdai_license', 'irdai_verified',
               'sebi_ria_code', 'amfi_reg', 'compliance_disclaimer',
               'plan', 'subscription_status', 'razorpay_sub_id',
               'subscription_expires_at', 'max_agents',
               'wa_phone_id', 'wa_access_token', 'wa_verify_token',
               'lang', 'is_active',
               'trial_ends_at', 'tg_bot_token', 'owner_telegram_id',
               'feature_overrides', 'referral_code',
               'city', 'account_type', 'signup_channel',
               'microsite_slug', 'microsite_bio', 'microsite_years_exp',
               'microsite_families_served', 'microsite_services',
               'microsite_testimonials', 'microsite_show_badge',
               'microsite_published', 'microsite_photo'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [tenant_id]
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE tenants SET {set_clause} WHERE tenant_id=?", values)
        # Keep agents.firm_name in sync with tenants.firm_name
        if 'firm_name' in fields:
            await conn.execute(
                "UPDATE agents SET firm_name=? WHERE tenant_id=?",
                (fields['firm_name'], tenant_id))
        await conn.commit()
    return True


# ── Microsite helpers (Feature 4) ─────────────────────────────────────────

import re as _re_micro

def _slugify_microsite(text: str) -> str:
    """Convert a firm/owner name into a URL-safe slug."""
    if not text:
        return ""
    s = _re_micro.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
    return s[:40] or ""


async def get_tenant_by_microsite_slug(slug: str) -> Optional[dict]:
    """Public lookup of a tenant by their microsite slug."""
    if not slug:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tenants WHERE microsite_slug = ? AND is_active = 1",
            (slug.lower().strip(),))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def is_microsite_slug_available(slug: str, exclude_tenant_id: int = None) -> bool:
    """Check whether a slug is free (not taken by any other tenant)."""
    if not slug or not _re_micro.match(r'^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$', slug):
        return False
    # Reserved tokens that must never become slugs
    reserved = {'admin', 'api', 'static', 'uploads', 'reports', 'docs',
                'login', 'signup', 'dashboard', 'onboarding', 'calculators',
                'superadmin', 'sa', 'support', 'pricing', 'help', 'm',
                'webhook', 'health', 'sw', 'pwa', 'manifest', 'robots',
                'sitemap', 'partner', 'affiliate', 'about', 'terms', 'privacy'}
    if slug in reserved:
        return False
    async with aiosqlite.connect(DB_PATH) as conn:
        if exclude_tenant_id:
            cursor = await conn.execute(
                "SELECT tenant_id FROM tenants WHERE microsite_slug=? AND tenant_id != ?",
                (slug, exclude_tenant_id))
        else:
            cursor = await conn.execute(
                "SELECT tenant_id FROM tenants WHERE microsite_slug=?", (slug,))
        return await cursor.fetchone() is None


async def suggest_microsite_slug(firm_name: str, owner_name: str = "",
                                  tenant_id: int = None) -> str:
    """Generate a unique slug suggestion. Tries firm, then firm-owner, then numbered."""
    base = _slugify_microsite(firm_name) or _slugify_microsite(owner_name) or "advisor"
    if await is_microsite_slug_available(base, exclude_tenant_id=tenant_id):
        return base
    if owner_name:
        combo = _slugify_microsite(f"{firm_name}-{owner_name}")
        if combo and combo != base and await is_microsite_slug_available(combo, exclude_tenant_id=tenant_id):
            return combo
    for n in range(2, 100):
        cand = f"{base}-{n}"[:40]
        if await is_microsite_slug_available(cand, exclude_tenant_id=tenant_id):
            return cand
    return f"{base}-{int(datetime.now().timestamp()) % 10000}"


async def increment_microsite_view(tenant_id: int) -> None:
    """Bump the view counter (best-effort, fire-and-forget)."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE tenants SET microsite_views = COALESCE(microsite_views,0) + 1 "
                "WHERE tenant_id=?", (tenant_id,))
            await conn.commit()
    except Exception:
        pass


async def delete_tenant_cascade(tenant_id: int) -> dict:
    """Permanently delete a tenant and ALL associated data (cascading).
    Returns a summary of what was deleted.
    WARNING: This is irreversible!"""
    summary = {}
    async with aiosqlite.connect(DB_PATH) as conn:
        # Count what we're about to delete
        for table, col in [
            ('agents', 'tenant_id'),
            ('leads', 'agent_id'),
            ('reminders', 'agent_id'),
            ('interactions', 'agent_id'),
            ('policies', 'agent_id'),
            ('claims', 'agent_id'),
            ('greetings_log', 'agent_id'),
            ('calculator_sessions', 'agent_id'),
            ('daily_summary', 'agent_id'),
            ('voice_logs', 'agent_id'),
            ('audit_log', 'tenant_id'),
            ('invite_codes', 'tenant_id'),
            ('campaigns', 'tenant_id'),
            ('support_tickets', 'tenant_id'),
        ]:
            if col == 'tenant_id':
                cursor = await conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE tenant_id=?",
                    (tenant_id,))
            else:
                # For agent_id-linked tables, find via agents
                cursor = await conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {col} IN "
                    f"(SELECT agent_id FROM agents WHERE tenant_id=?)",
                    (tenant_id,))
            summary[table] = (await cursor.fetchone())[0]

        # Get agent IDs for this tenant
        cursor = await conn.execute(
            "SELECT agent_id FROM agents WHERE tenant_id=?", (tenant_id,))
        agent_ids = [row[0] for row in await cursor.fetchall()]

        if agent_ids:
            placeholders = ",".join("?" * len(agent_ids))
            # Delete agent-linked data
            for table in ('reminders', 'interactions', 'policies', 'claims',
                          'greetings_log', 'calculator_sessions',
                          'daily_summary', 'voice_logs', 'leads'):
                await conn.execute(
                    f"DELETE FROM {table} WHERE agent_id IN ({placeholders})",
                    agent_ids)

        # Delete tenant-linked data
        for table in ('invite_codes', 'audit_log', 'campaigns',
                      'pending_plan_changes'):
            await conn.execute(
                f"DELETE FROM {table} WHERE tenant_id=?", (tenant_id,))

        # Delete support ticket messages via ticket_id, then tickets
        await conn.execute(
            "DELETE FROM ticket_messages WHERE ticket_id IN "
            "(SELECT ticket_id FROM support_tickets WHERE tenant_id=?)",
            (tenant_id,))
        await conn.execute(
            "DELETE FROM support_tickets WHERE tenant_id=?", (tenant_id,))

        # Delete agents
        await conn.execute(
            "DELETE FROM agents WHERE tenant_id=?", (tenant_id,))

        # Delete the tenant itself
        await conn.execute(
            "DELETE FROM tenants WHERE tenant_id=?", (tenant_id,))

        await conn.commit()

    summary['tenant'] = 1
    return summary


async def find_tenant_by_phone_or_email(phone: str = None, email: str = None) -> Optional[dict]:
    """Check if a phone or email is already registered with ANY tenant.
    Returns the matching tenant dict (with subscription_status) or None.
    Used to block duplicate trials via Telegram bot registration."""
    if not phone and not email:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        conditions = []
        params = []
        if phone:
            conditions.append("(t.phone=? OR a.phone=?)")
            params.extend([phone, phone])
        if email:
            conditions.append("(t.email=? OR a.email=?)")
            params.extend([email, email])
        where = " OR ".join(conditions)
        cursor = await conn.execute(
            f"""SELECT t.* FROM tenants t
                LEFT JOIN agents a ON a.tenant_id = t.tenant_id
                WHERE {where}
                ORDER BY t.tenant_id DESC LIMIT 1""",
            params)
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_tenant_agent_count(tenant_id: int) -> int:
    """Count active agents for a tenant."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM agents WHERE tenant_id=? AND is_active=1",
            (tenant_id,))
        return (await cursor.fetchone())[0]


async def can_add_agent(tenant_id: int) -> dict:
    """Check if tenant can add another agent based on plan limits.
    Returns {'allowed': bool, 'current': int, 'max': int, 'plan': str}."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return {'allowed': False, 'current': 0, 'max': 0, 'plan': 'unknown',
                'reason': 'Tenant not found'}
    max_agents = tenant.get('max_agents', 1)
    plan = tenant.get('plan', 'trial')
    current = await get_tenant_agent_count(tenant_id)
    allowed = current < max_agents
    result = {'allowed': allowed, 'current': current, 'max': max_agents,
              'plan': plan}
    if not allowed:
        plan_names = {'individual': 'Solo', 'team': 'Team',
                      'enterprise': 'Enterprise', 'trial': 'Trial'}
        result['reason'] = (
            f"{plan_names.get(plan, plan)} plan allows max {max_agents} "
            f"advisor(s). Currently {current}/{max_agents}. "
            f"Upgrade your plan to add more.")
    return result


# ── Plan feature gates ──────────────────────────────────────────────────────
# Plan agent limits (includes admin): Solo=1, Team=admin+5=6, Enterprise=admin+25=26
PLAN_FEATURES = {
    'trial':      {'max_agents': 1, 'bulk_campaigns': False,
                   'google_drive': True, 'team_dashboard': False,
                   'admin_controls': False, 'custom_branding': False,
                   'api_access': False, 'ai_daily_quota': 30},
    'individual': {'max_agents': 1, 'bulk_campaigns': False,
                   'google_drive': True, 'team_dashboard': False,
                   'admin_controls': False, 'custom_branding': False,
                   'api_access': False, 'ai_daily_quota': 50},
    'team':       {'max_agents': 6, 'bulk_campaigns': True,
                   'google_drive': True, 'team_dashboard': True,
                   'admin_controls': False, 'custom_branding': False,
                   'api_access': False, 'ai_daily_quota': 80},
    'enterprise': {'max_agents': 26, 'bulk_campaigns': True,
                   'google_drive': True, 'team_dashboard': True,
                   'admin_controls': True, 'custom_branding': True,
                   'api_access': True, 'ai_daily_quota': 200},
}


async def check_plan_feature(tenant_id: int, feature: str) -> dict:
    """Check if a specific feature is available on the tenant's plan.
    Returns {'allowed': bool, 'plan': str, 'reason': str}."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return {'allowed': False, 'plan': 'unknown',
                'reason': 'Tenant not found'}
    plan = tenant.get('plan', 'trial')
    features = PLAN_FEATURES.get(plan, PLAN_FEATURES['trial'])
    # Check per-tenant feature overrides
    import json as _json
    overrides = {}
    try:
        overrides = _json.loads(tenant.get('feature_overrides') or '{}')
    except Exception:
        pass
    if feature in overrides:
        allowed = overrides[feature]
    else:
        allowed = features.get(feature, False)
    result = {'allowed': allowed, 'plan': plan}
    if not allowed:
        # Find cheapest plan that has this feature
        upgrade_to = None
        for p in ['individual', 'team', 'enterprise']:
            if PLAN_FEATURES[p].get(feature, False):
                upgrade_to = p
                break
        plan_names = {'individual': 'Solo (₹199/mo)', 'team': 'Team (₹799/mo)',
                      'enterprise': 'Enterprise (₹1,999/mo)'}
        result['reason'] = (
            f"This feature requires the {plan_names.get(upgrade_to, 'Team')} "
            f"plan or higher. Please upgrade to unlock it.")
        result['upgrade_to'] = upgrade_to
    return result


async def check_subscription_active(tenant_id: int) -> bool:
    """Check if tenant's subscription is active (trial, active, or paid)."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return False
    status = tenant.get('subscription_status', 'trial')
    if status in ('active', 'paid'):
        expires = tenant.get('subscription_expires_at')
        if expires:
            try:
                return datetime.fromisoformat(expires) > datetime.now()
            except ValueError:
                return False
        return True  # active/paid with no expiry = indefinitely active
    elif status in ('trial', 'trialing'):
        trial_end = tenant.get('trial_ends_at')
        if trial_end:
            try:
                return datetime.fromisoformat(trial_end) > datetime.now()
            except ValueError:
                return False
        return True
    return False


# =============================================================================
#  INVITE CODE OPERATIONS
# =============================================================================

async def create_invite_code(tenant_id: int, created_by: int,
                             max_uses: int = 5) -> str:
    """Generate a short invite code for adding agents to a tenant."""
    code = secrets.token_urlsafe(6).upper()[:8]  # 8-char code
    expires = (datetime.now() + timedelta(days=7)).isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO invite_codes
               (code, tenant_id, created_by, max_uses, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (code, tenant_id, created_by, max_uses, expires))
        await conn.commit()
    return code


async def validate_invite_code(code: str) -> Optional[dict]:
    """Validate and return invite code details, or None if invalid."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM invite_codes
               WHERE code=? AND is_active=1
                 AND (expires_at IS NULL OR datetime(expires_at) > datetime('now'))
                 AND used_count < max_uses""",
            (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def use_invite_code(code: str) -> bool:
    """Increment usage count on invite code."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE invite_codes SET used_count = used_count + 1 WHERE code=?",
            (code,))
        await conn.commit()
    return True


# =============================================================================
#  AGENT OPERATIONS
# =============================================================================

async def upsert_agent(telegram_id: str, name: str, phone: str = None,
                       email: str = None, tenant_id: int = 0,
                       role: str = "agent") -> int:
    """Create or update agent. Returns agent_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT agent_id FROM agents WHERE telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        if row:
            await conn.execute(
                """UPDATE agents SET name=?, phone=?, email=?, tenant_id=?,
                   role=?, onboarding_step=NULL,
                   updated_at=datetime('now') WHERE telegram_id=?""",
                (name, phone, email, tenant_id, role, telegram_id))
            await conn.commit()
            return row[0]
        else:
            cursor = await conn.execute(
                """INSERT INTO agents
                   (tenant_id, telegram_id, name, phone, email, role)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tenant_id, telegram_id, name, phone, email, role))
            await conn.commit()
            return cursor.lastrowid


async def get_agent(telegram_id: str) -> Optional[dict]:
    """Get agent by Telegram ID (includes tenant info)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT a.*, t.firm_name AS _tenant_firm, t.brand_tagline, t.brand_cta,
                      t.brand_phone, t.brand_email,
                      t.brand_primary_color, t.brand_accent_color,
                      t.plan, t.subscription_status,
                      t.wa_phone_id, t.wa_access_token,
                      t.irdai_license as tenant_irdai, t.irdai_verified
               FROM agents a
               LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
               WHERE a.telegram_id = ?""", (telegram_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        # Always use tenant's firm_name (agents.firm_name may be stale)
        d['firm_name'] = d.pop('_tenant_firm', d.get('firm_name', ''))
        return d


async def get_agent_by_id(agent_id: int) -> Optional[dict]:
    """Get agent by agent_id (includes tenant info)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT a.*, t.firm_name AS _tenant_firm, t.brand_tagline, t.brand_cta,
                      t.brand_phone, t.brand_email
               FROM agents a
               LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
               WHERE a.agent_id = ?""", (agent_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d['firm_name'] = d.pop('_tenant_firm', d.get('firm_name', ''))
        return d


async def update_agent_lang(agent_id: int, lang: str) -> bool:
    """Update agent's preferred language. Returns True on success."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE agents SET lang = ?, updated_at = datetime('now') WHERE agent_id = ?",
            (lang, agent_id))
        await conn.commit()
        return True


async def update_agent_profile(agent_id: int, **kwargs) -> bool:
    """Update agent profile fields dynamically. Returns True on success."""
    allowed = {'name', 'phone', 'email', 'is_active', 'profile_photo', 'city', 'lang', 'role',
               'arn_number', 'euin', 'irdai_license'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [agent_id]
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE agents SET {set_clause} WHERE agent_id=?", values)
        await conn.commit()
    return True


async def build_compliance_credentials(agent_id: int) -> str:
    """Build a compliance credentials string from agent + tenant regulatory fields.
    Used in PDF footers and WhatsApp signatures."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT a.arn_number, a.euin, a.irdai_license, "
            "t.sebi_ria_code, t.amfi_reg, t.irdai_license AS tenant_irdai, "
            "t.compliance_disclaimer "
            "FROM agents a JOIN tenants t ON a.tenant_id = t.tenant_id "
            "WHERE a.agent_id = ?", (agent_id,))
        row = await cursor.fetchone()
        if not row:
            return ""
        parts = []
        r = dict(row)
        if r.get('arn_number'):
            parts.append(f"ARN: {r['arn_number']}")
        if r.get('euin'):
            parts.append(f"EUIN: {r['euin']}")
        if r.get('irdai_license') or r.get('tenant_irdai'):
            lic = r.get('irdai_license') or r.get('tenant_irdai')
            parts.append(f"IRDAI Lic: {lic}")
        if r.get('sebi_ria_code'):
            parts.append(f"SEBI RIA: {r['sebi_ria_code']}")
        if r.get('amfi_reg'):
            parts.append(f"AMFI Reg: {r['amfi_reg']}")
        cred = " | ".join(parts)
        disclaimer = r.get('compliance_disclaimer', '')
        if disclaimer:
            cred = f"{cred}\n{disclaimer}" if cred else disclaimer
        return cred


async def mark_lead_dpdp_consent(lead_id: int) -> bool:
    """Mark DPDP consent for a lead with timestamp."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE leads SET dpdp_consent = 1, dpdp_consent_date = datetime('now'), "
            "updated_at = datetime('now') WHERE lead_id = ?", (lead_id,))
        await conn.commit()
        return True


async def update_agent_onboarding(telegram_id: str, step: str = None) -> bool:
    """Update agent's onboarding step (None = complete)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE agents SET onboarding_step = ?, updated_at = datetime('now') WHERE telegram_id = ?",
            (step, telegram_id))
        await conn.commit()
        return True


async def get_agents_by_tenant(tenant_id: int) -> list:
    """Get all agents for a tenant."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM agents
               WHERE tenant_id=? AND is_active=1
               ORDER BY role DESC, name ASC""",
            (tenant_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def find_tenant_by_telegram_id(telegram_id: str) -> Optional[dict]:
    """Check if a Telegram user already owns a tenant (one TG = one trial).
    Returns tenant dict if found, else None."""
    if not telegram_id:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM tenants WHERE owner_telegram_id = ?", (telegram_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def check_phone_email_duplicate(phone: str = None, email: str = None,
                                       exclude_tenant_id: int = None) -> Optional[dict]:
    """Universal duplicate check across tenants AND agents.
    Returns dict with 'field' and 'tenant' if duplicate found, else None.
    Can exclude a specific tenant_id (for edit scenarios)."""
    if not phone and not email:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Check phone
        if phone:
            q = "SELECT * FROM tenants WHERE phone = ?"
            p = [phone]
            if exclude_tenant_id:
                q += " AND tenant_id != ?"
                p.append(exclude_tenant_id)
            cursor = await conn.execute(q, p)
            row = await cursor.fetchone()
            if row:
                return {'field': 'phone', 'tenant': dict(row)}
            # Also check in agents table
            q2 = "SELECT a.*, t.tenant_id as t_id FROM agents a JOIN tenants t ON a.tenant_id=t.tenant_id WHERE a.phone = ?"
            p2 = [phone]
            if exclude_tenant_id:
                q2 += " AND t.tenant_id != ?"
                p2.append(exclude_tenant_id)
            cursor = await conn.execute(q2, p2)
            row = await cursor.fetchone()
            if row:
                t = await get_tenant(row['t_id'])
                return {'field': 'phone', 'tenant': t}
        # Check email
        if email:
            q = "SELECT * FROM tenants WHERE email = ? AND email != ''"
            p = [email]
            if exclude_tenant_id:
                q += " AND tenant_id != ?"
                p.append(exclude_tenant_id)
            cursor = await conn.execute(q, p)
            row = await cursor.fetchone()
            if row:
                return {'field': 'email', 'tenant': dict(row)}
            # Also check agents
            q2 = "SELECT a.*, t.tenant_id as t_id FROM agents a JOIN tenants t ON a.tenant_id=t.tenant_id WHERE a.email = ? AND a.email != ''"
            p2 = [email]
            if exclude_tenant_id:
                q2 += " AND t.tenant_id != ?"
                p2.append(exclude_tenant_id)
            cursor = await conn.execute(q2, p2)
            row = await cursor.fetchone()
            if row:
                t = await get_tenant(row['t_id'])
                return {'field': 'email', 'tenant': t}
    return None


async def get_duplicate_report() -> dict:
    """SA: Get report of duplicate phone/email entries across tenants."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Duplicate phones across tenants
        cur = await conn.execute("""
            SELECT phone, GROUP_CONCAT(tenant_id) as tenant_ids, COUNT(*) as cnt
            FROM tenants WHERE phone != '' AND phone IS NOT NULL
            GROUP BY phone HAVING cnt > 1
        """)
        dup_phones = [dict(r) for r in await cur.fetchall()]

        # Duplicate emails across tenants
        cur = await conn.execute("""
            SELECT email, GROUP_CONCAT(tenant_id) as tenant_ids, COUNT(*) as cnt
            FROM tenants WHERE email != '' AND email IS NOT NULL
            GROUP BY email HAVING cnt > 1
        """)
        dup_emails = [dict(r) for r in await cur.fetchall()]

        # Duplicate telegram IDs
        cur = await conn.execute("""
            SELECT owner_telegram_id, GROUP_CONCAT(tenant_id) as tenant_ids, COUNT(*) as cnt
            FROM tenants WHERE owner_telegram_id != '' AND owner_telegram_id IS NOT NULL
            GROUP BY owner_telegram_id HAVING cnt > 1
        """)
        dup_tg = [dict(r) for r in await cur.fetchall()]

    return {
        'duplicate_phones': dup_phones,
        'duplicate_emails': dup_emails,
        'duplicate_telegram_ids': dup_tg,
        'total_issues': len(dup_phones) + len(dup_emails) + len(dup_tg),
    }


async def update_agent_by_sa(agent_id: int, **kwargs) -> bool:
    """SA: Update any agent field. Returns True on success."""
    allowed = {'name', 'phone', 'email', 'role', 'is_active'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [agent_id]
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE agents SET {set_clause} WHERE agent_id=?", values)
        await conn.commit()
    return True


# =============================================================================
#  LEAD OPERATIONS
# =============================================================================

async def find_duplicate_lead(agent_id: int, phone: str) -> Optional[dict]:
    """Check if a lead with this phone already exists for this agent."""
    if not phone:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM leads
               WHERE agent_id=? AND (phone=? OR whatsapp=?)
               LIMIT 1""",
            (agent_id, phone, phone))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def find_duplicate_lead_tenant(tenant_id: int, phone: str) -> Optional[dict]:
    """Check if a lead with this phone exists for ANY agent in the tenant."""
    if not phone:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT l.*, a.name as agent_name FROM leads l
               JOIN agents a ON l.agent_id = a.agent_id
               WHERE a.tenant_id=? AND (l.phone=? OR l.whatsapp=?)
               LIMIT 1""",
            (tenant_id, phone, phone))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def add_lead(agent_id: int, name: str, phone: str = None,
                   whatsapp: str = None, dob: str = None,
                   anniversary: str = None, city: str = None,
                   occupation: str = None, need_type: str = "health",
                   source: str = "direct", notes: str = None,
                   monthly_income: float = None, family_size: str = None,
                   email: str = None, sum_insured: float = None,
                   premium_budget: float = None) -> int:
    """Add a new lead. Returns lead_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO leads
               (agent_id, name, phone, whatsapp, email, dob, anniversary,
                city, occupation, monthly_income, family_size, need_type,
                source, notes, sum_insured, premium_budget)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, name, phone, whatsapp, email, dob, anniversary,
             city, occupation, monthly_income, family_size, need_type,
             source, notes, sum_insured, premium_budget))
        await conn.commit()
        return cursor.lastrowid


async def update_lead(lead_id: int, tenant_id: int = None, **kwargs) -> bool:
    """Update lead fields dynamically.
    If tenant_id given, verifies lead belongs to an agent in that tenant (IDOR guard)."""
    allowed = {'name', 'phone', 'whatsapp', 'email', 'dob', 'anniversary',
               'city', 'occupation', 'monthly_income', 'family_size',
               'need_type', 'stage', 'source', 'notes', 'sum_insured',
               'premium_budget', 'closed_at',
               'dpdp_consent', 'dpdp_consent_date'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    if tenant_id is not None:
        values = list(fields.values()) + [lead_id, tenant_id]
        sql = (f"UPDATE leads SET {set_clause} WHERE lead_id=? "
               f"AND agent_id IN (SELECT agent_id FROM agents WHERE tenant_id=?)")
    else:
        values = list(fields.values()) + [lead_id]
        sql = f"UPDATE leads SET {set_clause} WHERE lead_id=?"
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(sql, values)
        await conn.commit()
    ok = cursor.rowcount > 0
    if ok and 'stage' in fields:
        try:
            import biz_nurture as _nurture
            await _nurture.auto_enrol_on_stage_change(lead_id, fields['stage'])
        except Exception as _e:
            import logging as _lg
            _lg.getLogger("sarathi.db").warning(
                "Nurture stage hook failed (lead %s update): %s", lead_id, _e)
    return ok


async def update_lead_stage(lead_id: int, new_stage: str,
                            tenant_id: int = None) -> bool:
    """Move lead to a new pipeline stage.
    If tenant_id given, verifies lead belongs to this tenant (IDOR guard)."""
    valid_stages = ['prospect', 'contacted', 'pitched', 'proposal_sent',
                    'negotiation', 'closed_won', 'closed_lost']
    if new_stage not in valid_stages:
        return False
    updates = {'stage': new_stage, 'updated_at': datetime.now().isoformat()}
    if new_stage in ('closed_won', 'closed_lost'):
        updates['closed_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    if tenant_id is not None:
        values = list(updates.values()) + [lead_id, tenant_id]
        sql = (f"UPDATE leads SET {set_clause} WHERE lead_id=? "
               f"AND agent_id IN (SELECT agent_id FROM agents WHERE tenant_id=?)")
    else:
        values = list(updates.values()) + [lead_id]
        sql = f"UPDATE leads SET {set_clause} WHERE lead_id=?"
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(sql, values)
        await conn.commit()
    ok = cursor.rowcount > 0
    if ok:
        try:
            import biz_nurture as _nurture
            await _nurture.auto_enrol_on_stage_change(lead_id, new_stage)
        except Exception as _e:
            import logging as _lg
            _lg.getLogger("sarathi.db").warning(
                "Nurture stage hook failed (lead %s -> %s): %s", lead_id, new_stage, _e)
    return ok


async def get_lead(lead_id: int, tenant_id: int = None) -> Optional[dict]:
    """Get single lead by ID.  When tenant_id is given, verifies ownership."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if tenant_id is not None:
            cursor = await conn.execute(
                """SELECT l.* FROM leads l
                   JOIN agents a ON l.agent_id = a.agent_id
                   WHERE l.lead_id=? AND a.tenant_id=?""",
                (lead_id, tenant_id))
        else:
            cursor = await conn.execute(
                "SELECT * FROM leads WHERE lead_id=?", (lead_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_leads_by_agent(agent_id: int, stage: str = None) -> list:
    """Get all leads for an agent, optionally filtered by stage."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if stage:
            cursor = await conn.execute(
                "SELECT * FROM leads WHERE agent_id=? AND stage=? ORDER BY updated_at DESC",
                (agent_id, stage))
        else:
            cursor = await conn.execute(
                "SELECT * FROM leads WHERE agent_id=? ORDER BY updated_at DESC",
                (agent_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_pipeline_summary(agent_id: int) -> dict:
    """Get lead counts by stage for pipeline view."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT stage, COUNT(*) as count FROM leads
               WHERE agent_id=? AND stage NOT IN ('closed_won', 'closed_lost')
               GROUP BY stage""", (agent_id,))
        rows = await cursor.fetchall()
        pipeline = {r[0]: r[1] for r in rows}

        # Also get closed stats
        cursor = await conn.execute(
            """SELECT stage, COUNT(*) as count FROM leads
               WHERE agent_id=? AND stage IN ('closed_won', 'closed_lost')
               GROUP BY stage""", (agent_id,))
        closed = await cursor.fetchall()
        for r in closed:
            pipeline[r[0]] = r[1]

        return pipeline


async def search_leads(agent_id: int, query: str) -> list:
    """Search leads by name or phone."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM leads WHERE agent_id=?
               AND (name LIKE ? OR phone LIKE ? OR whatsapp LIKE ?)
               ORDER BY updated_at DESC LIMIT 20""",
            (agent_id, f"%{query}%", f"%{query}%", f"%{query}%"))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# =============================================================================
#  POLICY OPERATIONS
# =============================================================================

async def add_policy(lead_id: int, agent_id: int, insurer: str = None,
                     plan_name: str = None, policy_type: str = "health",
                     sum_insured: float = None, premium: float = None,
                     premium_mode: str = "annual", start_date: str = None,
                     end_date: str = None, renewal_date: str = None,
                     policy_number: str = None, commission: float = 0,
                     notes: str = None, sold_by_agent: int = 1,
                     policy_status: str = "active", folio_number: str = None,
                     fund_name: str = None, sip_amount: float = None,
                     maturity_date: str = None, maturity_value: float = None,
                     riders: str = None) -> int:
    """Record a policy (sold or tracked)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO policies
               (lead_id, agent_id, policy_number, insurer, plan_name,
                policy_type, sum_insured, premium, premium_mode,
                start_date, end_date, renewal_date, commission, notes,
                sold_by_agent, policy_status, folio_number, fund_name,
                sip_amount, maturity_date, maturity_value, riders)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lead_id, agent_id, policy_number, insurer, plan_name,
             policy_type, sum_insured, premium, premium_mode,
             start_date, end_date, renewal_date, commission, notes,
             sold_by_agent, policy_status, folio_number, fund_name,
             sip_amount, maturity_date, maturity_value, riders))
        await conn.commit()
        return cursor.lastrowid


async def add_policy_member(policy_id: int, member_name: str,
                            relation: str = "self", dob: str = None,
                            age: int = None, sum_insured: float = None,
                            premium_share: float = None,
                            coverage_type: str = "floater",
                            lead_id: int = None) -> int:
    """Add an insured member to a policy (health/family floater etc)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO policy_members
               (policy_id, lead_id, member_name, relation, dob, age,
                sum_insured, premium_share, coverage_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (policy_id, lead_id, member_name, relation, dob, age,
             sum_insured, premium_share, coverage_type))
        await conn.commit()
        return cursor.lastrowid


async def get_policy_members(policy_id: int) -> list:
    """Get all insured members for a policy."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM policy_members WHERE policy_id=? ORDER BY member_id",
            (policy_id,))
        return [dict(r) for r in await cursor.fetchall()]


async def find_lead_by_phone(agent_id: int, phone: str) -> dict:
    """Find an existing lead by phone number (exact or partial match)."""
    if not phone:
        return None
    # Normalize: keep last 10 digits
    clean = ''.join(c for c in phone if c.isdigit())[-10:]
    if len(clean) < 10:
        return None
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM leads WHERE agent_id=?
               AND (phone LIKE ? OR whatsapp LIKE ?)
               ORDER BY updated_at DESC LIMIT 1""",
            (agent_id, f"%{clean}", f"%{clean}"))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_policies_by_agent(agent_id: int) -> list:
    """Get all policies for an agent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT p.*, l.name as client_name, l.phone as client_phone
               FROM policies p JOIN leads l ON p.lead_id = l.lead_id
               WHERE p.agent_id=? ORDER BY p.created_at DESC""",
            (agent_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_upcoming_renewals(agent_id: int, days_ahead: int = 60) -> list:
    """Get policies with renewal dates within N days."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT p.*, l.name as client_name, l.phone as client_phone,
                      l.whatsapp as client_whatsapp
               FROM policies p JOIN leads l ON p.lead_id = l.lead_id
               WHERE p.agent_id=? AND p.status='active'
                 AND p.renewal_date IS NOT NULL
                 AND date(p.renewal_date) BETWEEN date('now','+5 hours','+30 minutes') AND date('now','+5 hours','+30 minutes', ? || ' days')
               ORDER BY p.renewal_date ASC""",
            (agent_id, str(days_ahead)))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def advance_expired_renewals() -> int:
    """Roll renewal_date forward for active policies whose renewal has passed.

    Uses premium_mode to determine the advance interval:
      monthly → +1 month, quarterly → +3 months,
      half-yearly → +6 months, annual → +1 year.
    Keeps advancing until renewal_date is in the future (handles long-dormant policies).
    Returns the number of policies updated.
    """
    _MODE_MONTHS = {
        'monthly': 1, 'quarterly': 3, 'half-yearly': 6,
        'half_yearly': 6, 'annual': 12, 'yearly': 12,
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT policy_id, renewal_date, premium_mode
               FROM policies
               WHERE status = 'active'
                 AND renewal_date IS NOT NULL
                 AND date(renewal_date) < date('now', '+5 hours', '+30 minutes')""")
        rows = await cursor.fetchall()
        updated = 0
        today = date.today()
        for row in rows:
            mode = (row['premium_mode'] or 'annual').lower().strip()
            months = _MODE_MONTHS.get(mode, 12)
            try:
                ren = date.fromisoformat(row['renewal_date'][:10])
            except (ValueError, TypeError):
                continue
            # Advance until renewal_date is in the future
            while ren <= today:
                m = ren.month - 1 + months
                y = ren.year + m // 12
                m = m % 12 + 1
                d = min(ren.day, [31,29 if y%4==0 and (y%100!=0 or y%400==0) else 28,
                                  31,30,31,30,31,31,30,31,30,31][m-1])
                ren = date(y, m, d)
            await conn.execute(
                "UPDATE policies SET renewal_date=?, updated_at=? WHERE policy_id=?",
                (ren.isoformat(), datetime.now().isoformat(), row['policy_id']))
            updated += 1
        if updated:
            await conn.commit()
            logger.info("Auto-advanced renewal_date for %d policies", updated)
        return updated


async def get_policies_by_lead(lead_id: int, tenant_id: int = None) -> list:
    """Get all policies for a specific lead.  Tenant-scoped when tenant_id given."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if tenant_id is not None:
            cursor = await conn.execute(
                """SELECT p.* FROM policies p
                   JOIN agents a ON p.agent_id = a.agent_id
                   WHERE p.lead_id=? AND a.tenant_id=?
                   ORDER BY p.created_at DESC""",
                (lead_id, tenant_id))
        else:
            cursor = await conn.execute(
                """SELECT * FROM policies WHERE lead_id=?
                   ORDER BY created_at DESC""",
                (lead_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def update_policy(policy_id: int, tenant_id: int = None, **kwargs) -> bool:
    """Update policy fields dynamically.
    If tenant_id given, verifies policy belongs to this tenant (IDOR guard)."""
    allowed = {'insurer', 'plan_name', 'policy_type', 'sum_insured', 'premium',
               'premium_mode', 'start_date', 'end_date', 'renewal_date',
               'policy_number', 'commission', 'notes', 'status'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k}=?" for k in fields)
    if tenant_id is not None:
        values = list(fields.values()) + [policy_id, tenant_id]
        sql = (f"UPDATE policies SET {set_clause} WHERE policy_id=? "
               f"AND agent_id IN (SELECT agent_id FROM agents WHERE tenant_id=?)")
    else:
        values = list(fields.values()) + [policy_id]
        sql = f"UPDATE policies SET {set_clause} WHERE policy_id=?"
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(sql, values)
        await conn.commit()
    return cursor.rowcount > 0


async def get_policy(policy_id: int, tenant_id: int = None) -> Optional[dict]:
    """Get single policy by ID.  When tenant_id is given, verifies ownership."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if tenant_id is not None:
            cursor = await conn.execute(
                """SELECT p.* FROM policies p
                   JOIN agents a ON p.agent_id = a.agent_id
                   WHERE p.policy_id=? AND a.tenant_id=?""",
                (policy_id, tenant_id))
        else:
            cursor = await conn.execute(
                "SELECT * FROM policies WHERE policy_id=?", (policy_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_policy(policy_id: int, tenant_id: int) -> dict:
    """Delete a policy.  Tenant-scoped IDOR guard."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """DELETE FROM policies WHERE policy_id=?
               AND agent_id IN (SELECT agent_id FROM agents WHERE tenant_id=?)""",
            (policy_id, tenant_id))
        await conn.commit()
        if cursor.rowcount == 0:
            return {"success": False, "error": "Policy not found"}
        return {"success": True}


# =============================================================================
#  INTERACTION LOG
# =============================================================================

async def log_interaction(lead_id: int, agent_id: int, interaction_type: str,
                          channel: str = "telegram", summary: str = None,
                          follow_up_date: str = None,
                          follow_up_time: str = None,
                          created_by_agent_id: int = None,
                          assigned_to_agent_id: int = None) -> int:
    """Log a client interaction. follow_up_time is HH:MM in IST.
    agent_id = lead's assigned agent (for dashboard visibility).
    created_by_agent_id = who actually created this (admin/owner may differ).
    assigned_to_agent_id = who is RESPONSIBLE for this task (explicit assignee)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO interactions
               (lead_id, agent_id, type, channel, summary, follow_up_date,
                follow_up_time, follow_up_status, created_by_agent_id,
                assigned_to_agent_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (lead_id, agent_id, interaction_type, channel, summary,
             follow_up_date, follow_up_time,
             'pending' if follow_up_date else None,
             created_by_agent_id,
             assigned_to_agent_id))
        await conn.commit()
        return cursor.lastrowid


async def get_todays_followups(agent_id: int) -> list:
    """Get interactions with follow-up due today or upcoming (next 7 days)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT i.*, l.name as lead_name, l.phone as lead_phone,
                      ca.name as created_by_name,
                      aa.name as assigned_to_name
               FROM interactions i JOIN leads l ON i.lead_id = l.lead_id
               LEFT JOIN agents ca ON i.created_by_agent_id = ca.agent_id
               LEFT JOIN agents aa ON i.assigned_to_agent_id = aa.agent_id
               WHERE (i.agent_id=? OR i.assigned_to_agent_id=?)
                 AND date(i.follow_up_date) BETWEEN date('now','+5 hours','+30 minutes') AND date('now','+5 hours','+30 minutes','+7 days')
                 AND (i.follow_up_status IS NULL OR i.follow_up_status != 'done')
               ORDER BY i.follow_up_date ASC, i.follow_up_time ASC""",
            (agent_id, agent_id))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_pending_followups(agent_id: int) -> list:
    """Get overdue + today + upcoming follow-ups (next 7 days)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT i.*, l.name as lead_name, l.phone as lead_phone,
                      ca.name as created_by_name,
                      aa.name as assigned_to_name
               FROM interactions i JOIN leads l ON i.lead_id = l.lead_id
               LEFT JOIN agents ca ON i.created_by_agent_id = ca.agent_id
               LEFT JOIN agents aa ON i.assigned_to_agent_id = aa.agent_id
               WHERE (i.agent_id=? OR i.assigned_to_agent_id=?)
                 AND date(i.follow_up_date) <= date('now','+5 hours','+30 minutes','+7 days')
                 AND i.follow_up_date IS NOT NULL
                 AND (i.follow_up_status IS NULL OR i.follow_up_status != 'done')
               ORDER BY i.follow_up_date ASC, i.follow_up_time ASC LIMIT 30""",
            (agent_id, agent_id))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_tasks_by_date(agent_id: int, target_date: str = None,
                            status: str = "all", tenant_id: int = None,
                            limit: int = 50) -> list:
    """Get tasks for a specific date (or all pending). Supports date filtering and status.
    target_date: YYYY-MM-DD or 'overdue' or None (= all pending+upcoming).
    status: 'all', 'pending', 'done'.
    If tenant_id is set, returns tenant-wide (for admin/owner)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        base = """SELECT i.*, l.name as lead_name, l.phone as lead_phone,
                         ca.name as created_by_name,
                         aa.name as assigned_to_name,
                         a.name as agent_name
                  FROM interactions i
                  JOIN leads l ON i.lead_id = l.lead_id
                  JOIN agents a ON i.agent_id = a.agent_id
                  LEFT JOIN agents ca ON i.created_by_agent_id = ca.agent_id
                  LEFT JOIN agents aa ON i.assigned_to_agent_id = aa.agent_id
                  WHERE i.follow_up_date IS NOT NULL"""
        params = []
        # Scope: agent or tenant-wide
        if tenant_id:
            base += " AND a.tenant_id=?"
            params.append(tenant_id)
        else:
            base += " AND (i.agent_id=? OR i.assigned_to_agent_id=?)"
            params.extend([agent_id, agent_id])
        # Status filter
        if status == "pending":
            base += " AND (i.follow_up_status IS NULL OR i.follow_up_status != 'done')"
        elif status == "done":
            base += " AND i.follow_up_status = 'done'"
        # Date filter
        if target_date == "overdue":
            base += " AND date(i.follow_up_date) < date('now','+5 hours','+30 minutes')"
            if status != "done":
                base += " AND (i.follow_up_status IS NULL OR i.follow_up_status != 'done')"
        elif target_date:
            base += " AND date(i.follow_up_date) = date(?)"
            params.append(target_date)
        else:
            # Default: upcoming 30 days + all overdue
            base += " AND date(i.follow_up_date) <= date('now','+5 hours','+30 minutes','+30 days')"
        base += " ORDER BY i.follow_up_date ASC, i.follow_up_time ASC LIMIT ?"
        params.append(limit)
        cursor = await conn.execute(base, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_tenant_pending_followups(tenant_id: int) -> list:
    """Get all pending/overdue/upcoming follow-ups for the entire tenant."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT i.*, l.name as lead_name, l.phone as lead_phone, l.lead_id,
                      a.name as agent_name, a.agent_id, a.telegram_id as agent_telegram_id,
                      ca.name as created_by_name,
                      aa.name as assigned_to_name, aa.agent_id as assigned_to_id
               FROM interactions i
               JOIN leads l ON i.lead_id = l.lead_id
               JOIN agents a ON i.agent_id = a.agent_id
               LEFT JOIN agents ca ON i.created_by_agent_id = ca.agent_id
               LEFT JOIN agents aa ON i.assigned_to_agent_id = aa.agent_id
               WHERE a.tenant_id=? AND date(i.follow_up_date) <= date('now','+5 hours','+30 minutes','+7 days')
                 AND i.follow_up_date IS NOT NULL AND a.is_active=1
                 AND (i.follow_up_status IS NULL OR i.follow_up_status != 'done')
               ORDER BY i.follow_up_date ASC, i.follow_up_time ASC""",
            (tenant_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_pending_followups_for_lead(lead_id: int) -> list:
    """Get all pending follow-ups for a specific lead (for duplicate detection)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT i.*, a.name as agent_name, ca.name as created_by_name,
                      aa.name as assigned_to_name
               FROM interactions i
               JOIN agents a ON i.agent_id = a.agent_id
               LEFT JOIN agents ca ON i.created_by_agent_id = ca.agent_id
               LEFT JOIN agents aa ON i.assigned_to_agent_id = aa.agent_id
               WHERE i.lead_id=? AND i.follow_up_status='pending'
                 AND i.follow_up_date IS NOT NULL
               ORDER BY i.follow_up_date ASC""",
            (lead_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def update_followup(interaction_id: int, follow_up_date: str = None,
                           follow_up_time: str = None, summary: str = None,
                           interaction_type: str = None,
                           assigned_to_agent_id: int = None) -> bool:
    """Update an existing follow-up's date, time, notes, type, or assignee."""
    parts, params = [], []
    if follow_up_date is not None:
        parts.append("follow_up_date = ?"); params.append(follow_up_date)
    if follow_up_time is not None:
        parts.append("follow_up_time = ?"); params.append(follow_up_time)
    if summary is not None:
        parts.append("summary = ?"); params.append(summary)
    if interaction_type is not None:
        parts.append("type = ?"); params.append(interaction_type)
    if assigned_to_agent_id is not None:
        parts.append("assigned_to_agent_id = ?"); params.append(assigned_to_agent_id)
    if not parts:
        return False
    params.append(interaction_id)
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            f"UPDATE interactions SET {', '.join(parts)} WHERE interaction_id = ?",
            tuple(params))
        await conn.commit()
        return cursor.rowcount > 0


async def get_lead_interactions(lead_id: int, limit: int = 20, tenant_id: int = None) -> list:
    """Get all interactions for a specific lead, most recent first.
    When tenant_id is given, verifies ownership via agent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if tenant_id is not None:
            cursor = await conn.execute(
                """SELECT i.* FROM interactions i
                   JOIN agents a ON i.agent_id = a.agent_id
                   WHERE i.lead_id=? AND a.tenant_id=?
                   ORDER BY i.created_at DESC LIMIT ?""",
                (lead_id, tenant_id, limit))
        else:
            cursor = await conn.execute(
                """SELECT * FROM interactions
                   WHERE lead_id=?
                   ORDER BY created_at DESC LIMIT ?""",
                (lead_id, limit))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_upcoming_timed_followups(minutes_ahead: int = 30) -> list:
    """Get follow-ups with a specific time that are due within the next N minutes.
    Used by the 30-min-before reminder scheduler. All times are IST."""
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    today_str = now.strftime('%Y-%m-%d')
    current_time = now.strftime('%H:%M')
    future_time = (now + timedelta(minutes=minutes_ahead)).strftime('%H:%M')

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT i.*, l.name as lead_name, l.phone as lead_phone,
                      a.name as agent_name, a.telegram_id as agent_telegram_id,
                      a.lang as agent_lang
               FROM interactions i
               JOIN leads l ON i.lead_id = l.lead_id
               JOIN agents a ON i.agent_id = a.agent_id
               WHERE i.follow_up_date = ?
                 AND i.follow_up_time IS NOT NULL
                 AND i.follow_up_time > ? AND i.follow_up_time <= ?
                 AND i.follow_up_status = 'pending'
                 AND a.is_active = 1
               ORDER BY i.follow_up_time ASC""",
            (today_str, current_time, future_time))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def mark_followup_done(interaction_id: int) -> bool:
    """Mark a follow-up as completed."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "UPDATE interactions SET follow_up_status = 'done' WHERE interaction_id = ?",
            (interaction_id,))
        await conn.commit()
        return cursor.rowcount > 0


async def mark_followup_snoozed(interaction_id: int, new_date: str = None,
                                 new_time: str = None) -> bool:
    """Snooze a follow-up (reschedule by 1 hour or to a new date/time)."""
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    if not new_date:
        # Default: snooze 1 hour from now
        snoozed = now + timedelta(hours=1)
        new_date = snoozed.strftime('%Y-%m-%d')
        new_time = snoozed.strftime('%H:%M')
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """UPDATE interactions SET follow_up_date = ?, follow_up_time = ?,
               follow_up_status = 'pending'
               WHERE interaction_id = ?""",
            (new_date, new_time, interaction_id))
        await conn.commit()
        return cursor.rowcount > 0


async def get_overdue_followups_without_notes(tenant_id: int = None) -> list:
    """Get follow-ups that are done but have no notes in lead_notes.
    Used for accountability nudges."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if tenant_id:
            cursor = await conn.execute(
                """SELECT i.*, l.name as lead_name,
                          a.name as agent_name, a.telegram_id as agent_telegram_id,
                          a.lang as agent_lang, a.tenant_id
                   FROM interactions i
                   JOIN leads l ON i.lead_id = l.lead_id
                   JOIN agents a ON i.agent_id = a.agent_id
                   WHERE i.follow_up_status = 'done'
                     AND a.tenant_id = ?
                     AND NOT EXISTS (
                         SELECT 1 FROM lead_notes n
                         WHERE n.interaction_id = i.interaction_id
                     )
                     AND i.follow_up_date >= date('now', '-3 days')
                   ORDER BY i.follow_up_date DESC""",
                (tenant_id,))
        else:
            cursor = await conn.execute(
                """SELECT i.*, l.name as lead_name,
                          a.name as agent_name, a.telegram_id as agent_telegram_id,
                          a.lang as agent_lang, a.tenant_id
                   FROM interactions i
                   JOIN leads l ON i.lead_id = l.lead_id
                   JOIN agents a ON i.agent_id = a.agent_id
                   WHERE i.follow_up_status = 'done'
                     AND NOT EXISTS (
                         SELECT 1 FROM lead_notes n
                         WHERE n.interaction_id = i.interaction_id
                     )
                     AND i.follow_up_date >= date('now', '-3 days')
                   ORDER BY i.follow_up_date DESC""")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_missed_followups(tenant_id: int = None) -> list:
    """Get follow-ups that were due but never marked done (missed).
    For admin accountability digest."""
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    now = datetime.now(ist)
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        base_sql = """SELECT i.*, l.name as lead_name,
                             a.name as agent_name, a.telegram_id as agent_telegram_id,
                             a.lang as agent_lang, a.tenant_id
                      FROM interactions i
                      JOIN leads l ON i.lead_id = l.lead_id
                      JOIN agents a ON i.agent_id = a.agent_id
                      WHERE i.follow_up_status = 'pending'
                        AND i.follow_up_date < date('now')
                        AND i.follow_up_date >= date('now', '-7 days')
                        AND a.is_active = 1"""
        if tenant_id:
            cursor = await conn.execute(base_sql + " AND a.tenant_id = ? ORDER BY a.agent_id, i.follow_up_date DESC", (tenant_id,))
        else:
            cursor = await conn.execute(base_sql + " ORDER BY a.tenant_id, a.agent_id, i.follow_up_date DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ── Lead Notes (CRM Accountability) ─────────────────────────────────────

async def add_lead_note(lead_id: int, agent_id: int, note_text: str,
                        interaction_id: int = None, author_role: str = 'advisor',
                        parent_note_id: int = None) -> int:
    """Add a note to a lead's timeline. Returns note_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO lead_notes
               (lead_id, agent_id, note_text, interaction_id, author_role, parent_note_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (lead_id, agent_id, note_text, interaction_id, author_role, parent_note_id))
        await conn.commit()
        return cursor.lastrowid


async def get_lead_notes(lead_id: int, limit: int = 50, tenant_id: int = None) -> list:
    """Get all notes for a lead, most recent first. Optionally verify tenant ownership."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if tenant_id is not None:
            cursor = await conn.execute(
                """SELECT n.*, a.name as author_name, a.role as agent_role
                   FROM lead_notes n
                   JOIN agents a ON n.agent_id = a.agent_id
                   WHERE n.lead_id = ? AND a.tenant_id = ?
                   ORDER BY n.created_at DESC LIMIT ?""",
                (lead_id, tenant_id, limit))
        else:
            cursor = await conn.execute(
                """SELECT n.*, a.name as author_name, a.role as agent_role
                   FROM lead_notes n
                   JOIN agents a ON n.agent_id = a.agent_id
                   WHERE n.lead_id = ?
                   ORDER BY n.created_at DESC LIMIT ?""",
                (lead_id, limit))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_lead_full_timeline(lead_id: int, tenant_id: int = None, limit: int = 50) -> list:
    """Get combined timeline: interactions + notes, sorted by date.
    Returns unified list with 'entry_type' = 'interaction' or 'note'."""
    interactions = await get_lead_interactions(lead_id, limit=limit, tenant_id=tenant_id)
    notes = await get_lead_notes(lead_id, limit=limit, tenant_id=tenant_id)

    timeline = []
    for i in interactions:
        i['entry_type'] = 'interaction'
        i['date'] = i.get('created_at', '')
        timeline.append(i)
    for n in notes:
        n['entry_type'] = 'note'
        n['date'] = n.get('created_at', '')
        timeline.append(n)

    timeline.sort(key=lambda x: x.get('date', ''), reverse=True)
    return timeline[:limit]


async def get_admin_followup_digest(tenant_id: int) -> dict:
    """Get admin-level follow-up accountability summary for a tenant.
    Returns: done_with_notes, done_without_notes, missed, total."""
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Today's + recent follow-ups for this tenant
        cursor = await conn.execute(
            """SELECT i.interaction_id, i.follow_up_status, i.follow_up_date,
                      a.name as agent_name, a.agent_id,
                      l.name as lead_name,
                      (SELECT COUNT(*) FROM lead_notes n WHERE n.interaction_id = i.interaction_id) as note_count
               FROM interactions i
               JOIN agents a ON i.agent_id = a.agent_id
               JOIN leads l ON i.lead_id = l.lead_id
               WHERE a.tenant_id = ? AND i.follow_up_date IS NOT NULL
                 AND i.follow_up_date >= date('now', '-1 days')
                 AND i.follow_up_date <= date('now')
                 AND a.is_active = 1
               ORDER BY a.agent_id, i.follow_up_date""",
            (tenant_id,))
        rows = [dict(r) for r in await cursor.fetchall()]

    done_with_notes = [r for r in rows if r['follow_up_status'] == 'done' and r['note_count'] > 0]
    done_no_notes = [r for r in rows if r['follow_up_status'] == 'done' and r['note_count'] == 0]
    missed = [r for r in rows if r['follow_up_status'] == 'pending' and r['follow_up_date'] < datetime.now(ist).strftime('%Y-%m-%d')]
    pending_today = [r for r in rows if r['follow_up_status'] == 'pending' and r['follow_up_date'] == datetime.now(ist).strftime('%Y-%m-%d')]

    return {
        'done_with_notes': done_with_notes,
        'done_without_notes': done_no_notes,
        'missed': missed,
        'pending_today': pending_today,
        'total': len(rows),
    }


async def get_lead_greetings(lead_id: int, limit: int = 10) -> list:
    """Get all greetings sent to a specific lead."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM greetings_log
               WHERE lead_id=?
               ORDER BY sent_at DESC LIMIT ?""",
            (lead_id, limit))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# =============================================================================
#  REMINDERS
# =============================================================================

async def add_reminder(agent_id: int, reminder_type: str, due_date: str,
                       message: str = None, lead_id: int = None,
                       policy_id: int = None) -> int:
    """Schedule a reminder."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO reminders
               (agent_id, lead_id, policy_id, type, due_date, message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (agent_id, lead_id, policy_id, reminder_type, due_date, message))
        await conn.commit()
        return cursor.lastrowid


async def get_due_reminders(agent_id: int = None) -> list:
    """Get reminders due today (or for all agents if agent_id is None)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if agent_id:
            cursor = await conn.execute(
                """SELECT r.*, l.name as lead_name, l.phone as lead_phone
                   FROM reminders r LEFT JOIN leads l ON r.lead_id = l.lead_id
                   WHERE r.agent_id=? AND r.status='pending'
                     AND date(r.due_date) <= date('now')
                   ORDER BY r.due_date ASC""",
                (agent_id,))
        else:
            cursor = await conn.execute(
                """SELECT r.*, l.name as lead_name, l.phone as lead_phone,
                          a.telegram_id as agent_telegram_id
                   FROM reminders r
                   LEFT JOIN leads l ON r.lead_id = l.lead_id
                   JOIN agents a ON r.agent_id = a.agent_id
                   WHERE r.status='pending' AND date(r.due_date) <= date('now')
                   ORDER BY r.due_date ASC""")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def mark_reminder_sent(reminder_id: int):
    """Mark a reminder as sent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """UPDATE reminders SET status='sent', sent_at=datetime('now')
               WHERE reminder_id=?""", (reminder_id,))
        await conn.commit()


# =============================================================================
#  GREETINGS
# =============================================================================

async def get_todays_birthdays(agent_id: int = None) -> list:
    """Get leads with birthday today (across all agents or one), with tenant branding."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        _join = """SELECT l.*, a.telegram_id as agent_telegram_id,
                          a.name as agent_name, a.lang as agent_lang,
                          t.firm_name, t.brand_tagline, t.brand_cta, t.brand_phone
                   FROM leads l
                   JOIN agents a ON l.agent_id = a.agent_id
                   LEFT JOIN tenants t ON a.tenant_id = t.tenant_id"""
        if agent_id:
            cursor = await conn.execute(
                f"""{_join}
                   WHERE l.agent_id=? AND l.dob IS NOT NULL
                     AND strftime('%%m-%%d', l.dob) = strftime('%%m-%%d', 'now')""",
                (agent_id,))
        else:
            cursor = await conn.execute(
                f"""{_join}
                   WHERE l.dob IS NOT NULL
                     AND strftime('%m-%d', l.dob) = strftime('%m-%d', 'now')""")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_todays_anniversaries(agent_id: int = None) -> list:
    """Get leads with anniversary today, with tenant branding."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        _join = """SELECT l.*, a.telegram_id as agent_telegram_id,
                          a.name as agent_name, a.lang as agent_lang,
                          t.firm_name, t.brand_tagline, t.brand_cta, t.brand_phone
                   FROM leads l
                   JOIN agents a ON l.agent_id = a.agent_id
                   LEFT JOIN tenants t ON a.tenant_id = t.tenant_id"""
        if agent_id:
            cursor = await conn.execute(
                f"""{_join}
                   WHERE l.agent_id=? AND l.anniversary IS NOT NULL
                     AND strftime('%%m-%%d', l.anniversary) = strftime('%%m-%%d', 'now')""",
                (agent_id,))
        else:
            cursor = await conn.execute(
                f"""{_join}
                   WHERE l.anniversary IS NOT NULL
                     AND strftime('%m-%d', l.anniversary) = strftime('%m-%d', 'now')""")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def log_greeting(lead_id: int, agent_id: int, greeting_type: str,
                       channel: str = "whatsapp", message: str = None):
    """Log that a greeting was sent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO greetings_log (lead_id, agent_id, type, channel, message)
               VALUES (?, ?, ?, ?, ?)""",
            (lead_id, agent_id, greeting_type, channel, message))
        await conn.commit()


async def was_greeting_sent_today(lead_id: int, greeting_type: str) -> bool:
    """Check if a greeting was already sent today to avoid duplicates."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT 1 FROM greetings_log
               WHERE lead_id=? AND type=? AND date(sent_at) = date('now')""",
            (lead_id, greeting_type))
        return await cursor.fetchone() is not None


# =============================================================================
#  CALCULATOR SESSIONS
# =============================================================================

async def save_calculator_session(agent_id: int, calc_type: str,
                                  inputs: dict, result: dict,
                                  lead_id: int = None) -> int:
    """Save a calculator usage for audit/followup."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO calculator_sessions
               (agent_id, lead_id, calc_type, inputs, result)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_id, lead_id, calc_type,
             json.dumps(inputs), json.dumps(result)))
        await conn.commit()
        return cursor.lastrowid


# =============================================================================
#  DAILY SUMMARY
# =============================================================================

async def get_agent_stats(agent_id: int) -> dict:
    """Get comprehensive agent statistics."""
    async with aiosqlite.connect(DB_PATH) as conn:
        stats = {}

        # Total leads
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM leads WHERE agent_id=?", (agent_id,))
        stats['total_leads'] = (await cursor.fetchone())[0]

        # Pipeline counts
        cursor = await conn.execute(
            """SELECT stage, COUNT(*) FROM leads
               WHERE agent_id=? GROUP BY stage""", (agent_id,))
        stats['pipeline'] = {r[0]: r[1] for r in await cursor.fetchall()}

        # Active policies
        cursor = await conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(premium), 0),
                      COALESCE(SUM(commission), 0)
               FROM policies WHERE agent_id=? AND status='active'""",
            (agent_id,))
        row = await cursor.fetchone()
        stats['active_policies'] = row[0]
        stats['total_premium'] = row[1]
        stats['total_commission'] = row[2]

        # Today's stats
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM leads
               WHERE agent_id=? AND date(created_at) = date('now')""",
            (agent_id,))
        stats['today_new_leads'] = (await cursor.fetchone())[0]

        cursor = await conn.execute(
            """SELECT COUNT(*) FROM interactions
               WHERE agent_id=? AND date(created_at) = date('now')""",
            (agent_id,))
        stats['today_interactions'] = (await cursor.fetchone())[0]

        # Upcoming renewals (next 30 days)
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM policies
               WHERE agent_id=? AND status='active'
                 AND renewal_date IS NOT NULL
                 AND date(renewal_date) BETWEEN date('now') AND date('now', '+30 days')""",
            (agent_id,))
        stats['upcoming_renewals'] = (await cursor.fetchone())[0]

        return stats


async def get_all_active_agents() -> list:
    """Get all active agents with tenant info (for scheduler broadcasts)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT a.*, t.firm_name, t.brand_tagline, t.brand_phone,
                      t.wa_phone_id, t.wa_access_token
               FROM agents a
               LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
               WHERE a.is_active = 1""")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# =============================================================================
#  AUDIT LOG
# =============================================================================

async def log_audit(action: str, detail: str = None,
                    tenant_id: int = None, agent_id: int = None,
                    role: str = None, ip_address: str = None):
    """Log an audit event with optional actor role."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO audit_log
               (tenant_id, agent_id, role, action, detail, ip_address)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tenant_id, agent_id, role, action, detail, ip_address))
        await conn.commit()


async def add_audit_log(tenant_id, agent_id, action, detail=None, ip_address=None, role=None):
    """Convenience wrapper matching SA call signature."""
    await log_audit(action=action, detail=detail, tenant_id=tenant_id,
                    agent_id=agent_id, role=role, ip_address=ip_address)


# =============================================================================
#  VOICE-TO-ACTION LOG
# =============================================================================

async def log_voice_action(agent_id: int, transcript: str,
                           extracted_data: str, lead_id: int = None,
                           audio_duration: int = 0) -> int:
    """Log a processed voice note. Returns voice_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO voice_logs
               (agent_id, lead_id, transcript, extracted_data, audio_duration)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_id, lead_id, transcript, extracted_data, audio_duration))
        await conn.commit()
        return cursor.lastrowid


async def get_voice_logs(agent_id: int, limit: int = 20) -> list:
    """Get recent voice logs for an agent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT v.*, l.name as lead_name
               FROM voice_logs v LEFT JOIN leads l ON v.lead_id = l.lead_id
               WHERE v.agent_id = ?
               ORDER BY v.created_at DESC LIMIT ?""",
            (agent_id, limit))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ── Abuse / content-violation tracking ────────────────────────────────────
async def get_abuse_record(agent_id: int) -> Optional[dict]:
    """Get abuse warning record for an agent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM abuse_warnings WHERE agent_id=?", (agent_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def record_abuse_warning(agent_id: int, text: str) -> dict:
    """Increment abuse warning count. Returns updated record with warning_count
    and blocked_until (set on 3rd strike for 24h, permanent on 5th)."""
    rec = await get_abuse_record(agent_id)
    now = datetime.now().isoformat()
    if rec:
        new_count = rec['warning_count'] + 1
        blocked = rec.get('blocked_until')
        if new_count >= 5:
            blocked = '9999-12-31T23:59:59'  # permanent
        elif new_count >= 3:
            blocked = (datetime.now() + timedelta(hours=24)).isoformat()
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                """UPDATE abuse_warnings
                   SET warning_count=?, last_text=?, blocked_until=?, updated_at=?
                   WHERE agent_id=?""",
                (new_count, text[:500], blocked, now, agent_id))
            await conn.commit()
        return {'warning_count': new_count, 'blocked_until': blocked}
    else:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                """INSERT INTO abuse_warnings (agent_id, warning_count, last_text, updated_at)
                   VALUES (?, 1, ?, ?)""",
                (agent_id, text[:500], now))
            await conn.commit()
        return {'warning_count': 1, 'blocked_until': None}


async def is_agent_blocked(agent_id: int) -> bool:
    """Check if agent is currently blocked due to abuse."""
    rec = await get_abuse_record(agent_id)
    if not rec or not rec.get('blocked_until'):
        return False
    try:
        blocked_until = datetime.fromisoformat(rec['blocked_until'])
        return datetime.now() < blocked_until
    except (ValueError, TypeError):
        return False


# =============================================================================
#  CLAIMS HELPER
# =============================================================================

async def add_claim(agent_id: int, lead_id: int, claim_type: str,
                    policy_id: int = None, claim_amount: float = None,
                    incident_date: str = None, description: str = None,
                    hospital_name: str = None, notes: str = None) -> int:
    """Create a new claim record. Returns claim_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO claims
               (agent_id, lead_id, policy_id, claim_type, claim_amount,
                incident_date, description, hospital_name, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (agent_id, lead_id, policy_id, claim_type, claim_amount,
             incident_date, description, hospital_name, notes))
        await conn.commit()
        return cursor.lastrowid


async def update_claim(claim_id: int, tenant_id: int = None, **kwargs) -> bool:
    """Update claim fields dynamically.
    If tenant_id given, verifies claim belongs to this tenant (IDOR guard)."""
    allowed = {'status', 'claim_amount', 'description', 'hospital_name',
               'insurer_ref', 'documents_json', 'notes', 'incident_date'}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return False
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    if tenant_id is not None:
        values = list(fields.values()) + [claim_id, tenant_id]
        sql = (f"UPDATE claims SET {set_clause} WHERE claim_id = ? "
               f"AND agent_id IN (SELECT agent_id FROM agents WHERE tenant_id=?)")
    else:
        values = list(fields.values()) + [claim_id]
        sql = f"UPDATE claims SET {set_clause} WHERE claim_id = ?"
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(sql, values)
        await conn.commit()
        return cursor.rowcount > 0


async def get_claim(claim_id: int, tenant_id: int = None) -> Optional[dict]:
    """Get a single claim with lead/policy info.  Tenant-scoped when tenant_id given."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if tenant_id is not None:
            cursor = await conn.execute(
                """SELECT c.*, l.name as lead_name, l.phone as lead_phone,
                          p.insurer, p.plan_name, p.policy_number
                   FROM claims c
                   JOIN leads l ON c.lead_id = l.lead_id
                   JOIN agents a ON c.agent_id = a.agent_id
                   LEFT JOIN policies p ON c.policy_id = p.policy_id
                   WHERE c.claim_id = ? AND a.tenant_id = ?""",
                (claim_id, tenant_id))
        else:
            cursor = await conn.execute(
                """SELECT c.*, l.name as lead_name, l.phone as lead_phone,
                          p.insurer, p.plan_name, p.policy_number
                   FROM claims c
                   JOIN leads l ON c.lead_id = l.lead_id
                   LEFT JOIN policies p ON c.policy_id = p.policy_id
                   WHERE c.claim_id = ?""",
                (claim_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_claims_by_agent(agent_id: int, status: str = None) -> list:
    """Get all claims for an agent, optionally filtered by status."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if status:
            cursor = await conn.execute(
                """SELECT c.*, l.name as lead_name
                   FROM claims c JOIN leads l ON c.lead_id = l.lead_id
                   WHERE c.agent_id = ? AND c.status = ?
                   ORDER BY c.updated_at DESC""",
                (agent_id, status))
        else:
            cursor = await conn.execute(
                """SELECT c.*, l.name as lead_name
                   FROM claims c JOIN leads l ON c.lead_id = l.lead_id
                   WHERE c.agent_id = ?
                   ORDER BY c.updated_at DESC""",
                (agent_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_claims_by_lead(lead_id: int, tenant_id: int = None) -> list:
    """Get all claims for a specific lead.  Tenant-scoped when tenant_id given."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if tenant_id is not None:
            cursor = await conn.execute(
                """SELECT c.*, p.insurer, p.plan_name
                   FROM claims c
                   JOIN agents a ON c.agent_id = a.agent_id
                   LEFT JOIN policies p ON c.policy_id = p.policy_id
                   WHERE c.lead_id = ? AND a.tenant_id = ?
                   ORDER BY c.created_at DESC""",
                (lead_id, tenant_id))
        else:
            cursor = await conn.execute(
                """SELECT c.*, p.insurer, p.plan_name
                   FROM claims c
                   LEFT JOIN policies p ON c.policy_id = p.policy_id
                   WHERE c.lead_id = ?
                   ORDER BY c.created_at DESC""",
                (lead_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# =============================================================================
#  AGENT MANAGEMENT (Deactivate / Reactivate / Transfer / Remove)
# =============================================================================

async def deactivate_agent(agent_id: int, tenant_id: int = None) -> bool:
    """Set an agent as inactive — revokes all bot access.
    If tenant_id given, verifies agent belongs to that tenant."""
    async with aiosqlite.connect(DB_PATH) as conn:
        if tenant_id is not None:
            cursor = await conn.execute(
                "UPDATE agents SET is_active=0, updated_at=? WHERE agent_id=? AND tenant_id=?",
                (datetime.now().isoformat(), agent_id, tenant_id))
        else:
            cursor = await conn.execute(
                "UPDATE agents SET is_active=0, updated_at=? WHERE agent_id=?",
                (datetime.now().isoformat(), agent_id))
        await conn.commit()
        return cursor.rowcount > 0


async def reactivate_agent(agent_id: int, tenant_id: int = None) -> bool:
    """Reactivate a previously deactivated agent.
    If tenant_id given, verifies agent belongs to that tenant."""
    async with aiosqlite.connect(DB_PATH) as conn:
        if tenant_id is not None:
            cursor = await conn.execute(
                "UPDATE agents SET is_active=1, updated_at=? WHERE agent_id=? AND tenant_id=?",
                (datetime.now().isoformat(), agent_id, tenant_id))
        else:
            cursor = await conn.execute(
                "UPDATE agents SET is_active=1, updated_at=? WHERE agent_id=?",
                (datetime.now().isoformat(), agent_id))
        await conn.commit()
        return cursor.rowcount > 0


async def transfer_agent_data(from_agent_id: int, to_agent_id: int,
                              tenant_id: int = None) -> dict:
    """Transfer ALL data from one agent to another (leads, policies, claims, interactions).
    If tenant_id is provided, verifies both agents belong to the same tenant.
    Returns counts of transferred items."""
    # Defense-in-depth: verify both agents belong to the same tenant
    if tenant_id is not None:
        from_agent = await get_agent_by_id(from_agent_id)
        to_agent = await get_agent_by_id(to_agent_id)
        if not from_agent or from_agent.get('tenant_id') != tenant_id:
            return {'error': 'Source agent not in your firm', 'leads': 0}
        if not to_agent or to_agent.get('tenant_id') != tenant_id:
            return {'error': 'Target agent not in your firm', 'leads': 0}

    counts = {}
    async with aiosqlite.connect(DB_PATH) as conn:
        # Transfer leads
        cursor = await conn.execute(
            "UPDATE leads SET agent_id=?, updated_at=? WHERE agent_id=?",
            (to_agent_id, datetime.now().isoformat(), from_agent_id))
        counts['leads'] = cursor.rowcount

        # Transfer policies
        cursor = await conn.execute(
            "UPDATE policies SET agent_id=? WHERE agent_id=?",
            (to_agent_id, from_agent_id))
        counts['policies'] = cursor.rowcount

        # Transfer interactions
        cursor = await conn.execute(
            "UPDATE interactions SET agent_id=? WHERE agent_id=?",
            (to_agent_id, from_agent_id))
        counts['interactions'] = cursor.rowcount

        # Transfer claims
        cursor = await conn.execute(
            "UPDATE claims SET agent_id=?, updated_at=? WHERE agent_id=?",
            (to_agent_id, datetime.now().isoformat(), from_agent_id))
        counts['claims'] = cursor.rowcount

        # Transfer reminders
        cursor = await conn.execute(
            "UPDATE reminders SET agent_id=? WHERE agent_id=?",
            (to_agent_id, from_agent_id))
        counts['reminders'] = cursor.rowcount

        await conn.commit()
    return counts


async def remove_agent(agent_id: int, transfer_to_agent_id: int = None,
                       tenant_id: int = None) -> dict:
    """Remove an agent — optionally transfer data first, then deactivate.
    If tenant_id given, validates transfer_to agent belongs to same tenant.
    Returns transfer counts + success status."""
    result = {'success': False, 'transfers': {}}
    agent = await get_agent_by_id(agent_id)
    if not agent:
        result['error'] = 'Agent not found'
        return result

    if agent.get('role') == 'owner':
        result['error'] = 'Cannot remove the firm owner'
        return result

    if transfer_to_agent_id:
        # Validate transfer target belongs to same tenant
        if tenant_id is not None:
            to_agent = await get_agent_by_id(transfer_to_agent_id)
            if not to_agent or to_agent.get('tenant_id') != tenant_id:
                result['error'] = 'Transfer target agent not in your firm'
                return result
        result['transfers'] = await transfer_agent_data(
            agent_id, transfer_to_agent_id, tenant_id=tenant_id)
        if result['transfers'].get('error'):
            result['error'] = result['transfers']['error']
            return result

    await deactivate_agent(agent_id)
    result['success'] = True
    return result


async def touch_agent_activity(agent_id: int):
    """Update last_active timestamp for an agent (called on every command)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE agents SET last_active = datetime('now') WHERE agent_id = ?",
            (agent_id,))
        await conn.commit()


async def check_agent_phone_available(phone: str, exclude_tenant_id: int = None) -> dict:
    """Check if a phone number is available for registration.
    Returns {available: bool, reason: str, existing_agent: dict|None}.
    Rules: One phone = one active agent across all tenants (owners exempt — can own + be agent)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        query = ("SELECT a.agent_id, a.name, a.phone, a.role, a.is_active, "
                 "a.tenant_id, t.firm_name "
                 "FROM agents a LEFT JOIN tenants t ON a.tenant_id = t.tenant_id "
                 "WHERE a.phone = ? AND a.is_active = 1")
        params = [phone]
        if exclude_tenant_id is not None:
            query += " AND a.tenant_id != ?"
            params.append(exclude_tenant_id)
        cursor = await conn.execute(query, params)
        rows = [dict(r) for r in await cursor.fetchall()]
    if not rows:
        return {'available': True, 'reason': '', 'existing_agent': None}
    # Phone is active elsewhere
    existing = rows[0]
    return {
        'available': False,
        'reason': f"Phone already registered at {existing.get('firm_name', 'another firm')}",
        'existing_agent': existing
    }


async def deactivate_agent_full(agent_id: int, tenant_id: int = None,
                                reason: str = 'admin_action') -> bool:
    """Deactivate agent + unlink telegram_id (full block).
    Sets is_active=0 and telegram_id to __deactivated_ placeholder."""
    async with aiosqlite.connect(DB_PATH) as conn:
        now_ts = datetime.now().isoformat()
        placeholder = f"__deactivated_{agent_id}_{int(datetime.now().timestamp())}"
        if tenant_id is not None:
            cursor = await conn.execute(
                "UPDATE agents SET is_active=0, telegram_id=?, updated_at=? "
                "WHERE agent_id=? AND tenant_id=?",
                (placeholder, now_ts, agent_id, tenant_id))
        else:
            cursor = await conn.execute(
                "UPDATE agents SET is_active=0, telegram_id=?, updated_at=? "
                "WHERE agent_id=?",
                (placeholder, now_ts, agent_id))
        await conn.commit()
        if cursor.rowcount > 0:
            await log_audit(f"agent_deactivated_{reason}",
                           f"Agent #{agent_id} deactivated (reason: {reason})",
                           tenant_id=tenant_id, agent_id=agent_id)
        return cursor.rowcount > 0


async def get_inactive_agents(days: int = 90) -> list:
    """Get agents who haven't been active for N days (for auto-cleanup).
    Excludes owners (they control the subscription)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT a.agent_id, a.name, a.phone, a.role, a.tenant_id, "
            "a.last_active, a.created_at, t.firm_name "
            "FROM agents a LEFT JOIN tenants t ON a.tenant_id = t.tenant_id "
            "WHERE a.is_active = 1 AND a.role != 'owner' "
            "AND ("
            "  (a.last_active IS NOT NULL AND "
            "   datetime(a.last_active) < datetime('now', ? || ' days')) "
            "  OR "
            "  (a.last_active IS NULL AND "
            "   datetime(a.created_at) < datetime('now', ? || ' days'))"
            ")",
            (f"-{days}", f"-{days}"))
        return [dict(r) for r in await cursor.fetchall()]


async def get_agent_by_id(agent_id: int) -> Optional[dict]:
    """Get agent by agent_id (not telegram_id)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM agents WHERE agent_id=?", (agent_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_agents_by_tenant_all(tenant_id: int) -> list:
    """Get ALL agents for a tenant (including inactive)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT a.*, 
                      (SELECT COUNT(*) FROM leads WHERE agent_id=a.agent_id) as lead_count,
                      (SELECT COUNT(*) FROM policies WHERE agent_id=a.agent_id) as policy_count
               FROM agents a WHERE a.tenant_id=?
               ORDER BY a.role DESC, a.is_active DESC, a.name""",
            (tenant_id,))
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# =============================================================================
#  SUBSCRIPTION UPGRADE / DOWNGRADE
# =============================================================================

# Plan pricing: max_agents includes admin (Solo=1, Team=admin+5=6, Enterprise=admin+25=26)
PLAN_PRICING = {
    'individual': {'price': 199, 'max_agents': 1, 'name': 'Solo Advisor'},
    'team':       {'price': 799, 'max_agents': 6, 'name': 'Team'},
    'enterprise': {'price': 1999, 'max_agents': 26, 'name': 'Enterprise'},
}

PLAN_ORDER = ['trial', 'individual', 'team', 'enterprise']


async def upgrade_tenant_plan(tenant_id: int, new_plan: str) -> dict:
    """Upgrade a tenant's plan. Returns result dict."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return {'success': False, 'error': 'Tenant not found'}

    current = tenant.get('plan', 'trial')
    if PLAN_ORDER.index(new_plan) <= PLAN_ORDER.index(current):
        return {'success': False, 'error': f'Cannot upgrade from {current} to {new_plan}'}

    plan_info = PLAN_PRICING.get(new_plan)
    if not plan_info:
        return {'success': False, 'error': f'Unknown plan: {new_plan}'}

    await update_tenant(tenant_id,
                        plan=new_plan,
                        subscription_status='active',
                        max_agents=plan_info['max_agents'])

    await log_audit('plan_upgrade',
                    f'{current} → {new_plan}',
                    tenant_id=tenant_id)

    return {'success': True, 'old_plan': current, 'new_plan': new_plan,
            'max_agents': plan_info['max_agents']}


async def downgrade_tenant_plan(tenant_id: int, new_plan: str) -> dict:
    """Downgrade a tenant's plan. Checks agent count constraints."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return {'success': False, 'error': 'Tenant not found'}

    current = tenant.get('plan', 'trial')
    plan_info = PLAN_PRICING.get(new_plan)
    if not plan_info:
        return {'success': False, 'error': f'Unknown plan: {new_plan}'}

    # Check if agent count exceeds new plan limit
    agent_count = await get_tenant_agent_count(tenant_id)
    if agent_count > plan_info['max_agents']:
        return {'success': False,
                'error': f'You have {agent_count} agents but {plan_info["name"]} '
                         f'allows max {plan_info["max_agents"]}. '
                         f'Remove agents before downgrading.'}

    await update_tenant(tenant_id,
                        plan=new_plan,
                        max_agents=plan_info['max_agents'])

    await log_audit('plan_downgrade',
                    f'{current} → {new_plan}',
                    tenant_id=tenant_id)

    return {'success': True, 'old_plan': current, 'new_plan': new_plan}


# =============================================================================
#  MESSAGE FREQUENCY / CONTACT PREFERENCE PER LEAD
# =============================================================================

async def update_lead_contact_pref(lead_id: int, max_messages_per_week: int = 3,
                                    preferred_channel: str = 'whatsapp',
                                    preferred_time: str = None,
                                    opted_out: bool = False) -> bool:
    """Set contact preferences for a lead.
    Uses the 'notes' field to store JSON prefs until we add a dedicated column."""
    lead = await get_lead(lead_id)
    if not lead:
        return False
    # Store prefs in notes as structured JSON prefix
    existing_notes = lead.get('notes') or ''
    # Remove existing pref block
    import re
    existing_notes = re.sub(r'\[PREF:.*?\]', '', existing_notes).strip()
    pref = json.dumps({
        'max_msg_week': max_messages_per_week,
        'channel': preferred_channel,
        'time': preferred_time,
        'opted_out': opted_out,
    })
    new_notes = f"[PREF:{pref}] {existing_notes}".strip()
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE leads SET notes=?, updated_at=? WHERE lead_id=?",
            (new_notes, datetime.now().isoformat(), lead_id))
        await conn.commit()
    return True


async def get_lead_contact_pref(lead_id: int, tenant_id: int = None) -> dict:
    """Get contact preferences for a lead.  Tenant-scoped when tenant_id given."""
    lead = await get_lead(lead_id, tenant_id=tenant_id)
    if not lead:
        return {'max_msg_week': 3, 'channel': 'whatsapp', 'time': None, 'opted_out': False}
    notes = lead.get('notes') or ''
    import re
    match = re.search(r'\[PREF:(.*?)\]', notes)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return {'max_msg_week': 3, 'channel': 'whatsapp', 'time': None, 'opted_out': False}


async def count_messages_sent_this_week(lead_id: int) -> int:
    """Count interactions (messages) sent to a lead in the current week."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM interactions
               WHERE lead_id=? AND created_at >= date('now', 'weekday 0', '-7 days')""",
            (lead_id,))
        return (await cursor.fetchone())[0]


async def can_message_lead(lead_id: int) -> dict:
    """Check if we can send another message to a lead based on preferences.
    Returns {'allowed': bool, 'reason': str, 'sent_this_week': int, 'max': int}."""
    pref = await get_lead_contact_pref(lead_id)
    if pref.get('opted_out'):
        return {'allowed': False, 'reason': 'Client opted out of messages',
                'sent_this_week': 0, 'max': 0}
    sent = await count_messages_sent_this_week(lead_id)
    max_allowed = pref.get('max_msg_week', 3)
    if sent >= max_allowed:
        return {'allowed': False,
                'reason': f'Weekly limit reached ({sent}/{max_allowed})',
                'sent_this_week': sent, 'max': max_allowed}
    return {'allowed': True, 'reason': 'OK',
            'sent_this_week': sent, 'max': max_allowed}


# =============================================================================
#  CSV / BULK IMPORT — LEADS
# =============================================================================

async def bulk_add_leads(agent_id: int, leads_data: list,
                         tenant_id: int = None) -> dict:
    """Bulk import leads from a list of dicts.
    Each dict can have: name, phone, email, city, need_type, notes, dob, etc.
    When tenant_id is given, checks for duplicate phone numbers tenant-wide
    and skips them (reporting as 'duplicates').
    Returns {'imported': int, 'skipped': int, 'duplicates': int, 'errors': [...]}."""
    result = {'imported': 0, 'skipped': 0, 'duplicates': 0, 'errors': []}
    async with aiosqlite.connect(DB_PATH) as conn:
        # Pre-load existing phones for duplicate detection
        existing_phones = set()
        if tenant_id is not None:
            cursor = await conn.execute(
                """SELECT l.phone FROM leads l
                   JOIN agents a ON l.agent_id = a.agent_id
                   WHERE a.tenant_id = ? AND l.phone IS NOT NULL AND l.phone != ''""",
                (tenant_id,))
            rows = await cursor.fetchall()
            existing_phones = {r[0] for r in rows}

        for i, lead in enumerate(leads_data):
            name = (lead.get('name') or '').strip()
            if not name:
                result['skipped'] += 1
                result['errors'].append(f"Row {i+1}: Missing name")
                continue

            phone = (lead.get('phone') or '').strip()
            # Duplicate check
            if phone and tenant_id is not None and phone in existing_phones:
                result['duplicates'] += 1
                result['errors'].append(f"Row {i+1} ({name}): Duplicate phone {phone}")
                continue

            try:
                await conn.execute(
                    """INSERT INTO leads
                       (agent_id, name, phone, email, whatsapp, city,
                        need_type, notes, dob, anniversary, occupation,
                        monthly_income, family_size, stage, source)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (agent_id, name,
                     phone, lead.get('email', ''),
                     lead.get('whatsapp', phone),
                     lead.get('city', ''), lead.get('need_type', 'health'),
                     lead.get('notes', ''), lead.get('dob', ''),
                     lead.get('anniversary', ''), lead.get('occupation', ''),
                     lead.get('monthly_income'), lead.get('family_size', ''),
                     lead.get('stage', 'prospect'),
                     lead.get('source', 'csv_import')))
                result['imported'] += 1
                if phone:
                    existing_phones.add(phone)  # track within this batch too
            except Exception as e:
                result['skipped'] += 1
                result['errors'].append(f"Row {i+1} ({name}): {str(e)[:60]}")
        await conn.commit()
    return result


# =============================================================================
#  OTP PERSISTENCE (for production — replaces in-memory store)
# =============================================================================

async def init_otp_table():
    """Create OTP persistence table (safe to call multiple times)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS otp_store (
                phone       TEXT PRIMARY KEY,
                otp_hash    TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                attempts    INTEGER DEFAULT 0,
                last_sent   TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await conn.commit()


async def save_otp(phone: str, otp_hash: str, expires_at: str):
    """Save OTP to DB (upsert)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT OR REPLACE INTO otp_store
               (phone, otp_hash, expires_at, attempts, last_sent)
               VALUES (?, ?, ?, 0, datetime('now'))""",
            (phone, otp_hash, expires_at))
        await conn.commit()


async def get_otp(phone: str) -> Optional[dict]:
    """Get stored OTP for a phone number."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM otp_store WHERE phone=?", (phone,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def increment_otp_attempts(phone: str) -> int:
    """Increment OTP attempt counter. Returns new count."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "UPDATE otp_store SET attempts = attempts + 1 WHERE phone=?",
            (phone,))
        await conn.commit()
        cursor = await conn.execute(
            "SELECT attempts FROM otp_store WHERE phone=?", (phone,))
        row = await cursor.fetchone()
        return row[0] if row else 0


async def delete_otp(phone: str):
    """Delete OTP after successful verification."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("DELETE FROM otp_store WHERE phone=?", (phone,))
        await conn.commit()


async def cleanup_expired_otps():
    """Delete expired OTPs (housekeeping)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM otp_store WHERE expires_at < datetime('now')")
        await conn.commit()


# =============================================================================
#  SUPPORT TICKETS
# =============================================================================

async def create_ticket(tenant_id: int = None, agent_id: int = None,
                        subject: str = "", description: str = "",
                        category: str = "general", priority: str = "normal",
                        is_trial: int = 0, contact_name: str = None,
                        contact_phone: str = None, contact_email: str = None) -> int:
    """Create a support ticket. Returns ticket_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO support_tickets
               (tenant_id, agent_id, subject, description, category, priority,
                is_trial, contact_name, contact_phone, contact_email)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, agent_id, subject, description, category, priority,
             is_trial, contact_name, contact_phone, contact_email))
        await conn.commit()
        return cur.lastrowid


async def get_ticket(ticket_id: int) -> Optional[dict]:
    """Get ticket with details."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT st.*, t.firm_name, t.owner_name
               FROM support_tickets st
               LEFT JOIN tenants t ON st.tenant_id = t.tenant_id
               WHERE st.ticket_id = ?""", (ticket_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_tickets(tenant_id: int = None, status: str = None,
                      limit: int = 50, offset: int = 0) -> tuple:
    """List tickets with optional filters. Returns (tickets, total)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = """SELECT st.*, t.firm_name, t.owner_name
               FROM support_tickets st
               LEFT JOIN tenants t ON st.tenant_id = t.tenant_id"""
        conditions, params = [], []
        if tenant_id:
            conditions.append("st.tenant_id = ?")
            params.append(tenant_id)
        if status:
            conditions.append("st.status = ?")
            params.append(status)
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        # Count
        count_q = q.replace("SELECT st.*, t.firm_name, t.owner_name", "SELECT COUNT(*)")
        cur = await conn.execute(count_q, params)
        total = (await cur.fetchone())[0]
        # Fetch
        q += " ORDER BY st.created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cur = await conn.execute(q, params)
        rows = [dict(r) for r in await cur.fetchall()]
        return rows, total


async def update_ticket(ticket_id: int, **kwargs):
    """Update ticket fields."""
    allowed = {'subject', 'description', 'category', 'priority', 'status',
               'assigned_to', 'resolution', 'resolved_at'}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE support_tickets SET {set_clause} WHERE ticket_id = ?",
            (*fields.values(), ticket_id))
        await conn.commit()


async def add_ticket_message(ticket_id: int, sender_type: str, sender_name: str,
                             message: str) -> int:
    """Add a message to a ticket thread."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO ticket_messages (ticket_id, sender_type, sender_name, message)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, sender_type, sender_name, message))
        await conn.commit()
        return cur.lastrowid


async def get_ticket_messages(ticket_id: int) -> list:
    """Get all messages for a ticket."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,))
        return [dict(r) for r in await cur.fetchall()]


async def get_ticket_stats() -> dict:
    """Ticket stats for SA dashboard."""
    async with aiosqlite.connect(DB_PATH) as conn:
        stats = {}
        for s in ('open', 'in_progress', 'resolved', 'closed'):
            cur = await conn.execute(
                "SELECT COUNT(*) FROM support_tickets WHERE status = ?", (s,))
            stats[s] = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM support_tickets")
        stats['total'] = (await cur.fetchone())[0]
        # Avg resolution time
        cur = await conn.execute(
            """SELECT AVG(julianday(resolved_at) - julianday(created_at))
               FROM support_tickets WHERE resolved_at IS NOT NULL""")
        avg_days = (await cur.fetchone())[0]
        stats['avg_resolution_days'] = round(avg_days, 1) if avg_days else 0
        return stats


# =============================================================================
#  AFFILIATES
# =============================================================================

async def create_affiliate(name: str, phone: str, email: str = None,
                           commission_pct: float = 20.0) -> dict:
    """Create an affiliate. Returns {affiliate_id, referral_code}."""
    code = "SAR-" + secrets.token_hex(4).upper()
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO affiliates (name, phone, email, referral_code, commission_pct)
               VALUES (?, ?, ?, ?, ?)""",
            (name, phone, email, code, commission_pct))
        await conn.commit()
        return {"affiliate_id": cur.lastrowid, "referral_code": code}


async def get_affiliate(affiliate_id: int = None, referral_code: str = None,
                        phone: str = None) -> Optional[dict]:
    """Get affiliate by ID, code, or phone."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if affiliate_id:
            cur = await conn.execute("SELECT * FROM affiliates WHERE affiliate_id=?", (affiliate_id,))
        elif referral_code:
            cur = await conn.execute("SELECT * FROM affiliates WHERE referral_code=?", (referral_code,))
        elif phone:
            cur = await conn.execute("SELECT * FROM affiliates WHERE phone=?", (phone,))
        else:
            return None
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_affiliates(status: str = None, limit: int = 50, offset: int = 0,
                         include_discontinued: bool = False) -> tuple:
    """List affiliates. Returns (affiliates, total). Excludes discontinued by default."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = "SELECT * FROM affiliates"
        params = []
        conditions = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        elif not include_discontinued:
            conditions.append("status != 'discontinued'")
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        count_q = q.replace("SELECT *", "SELECT COUNT(*)")
        cur = await conn.execute(count_q, params)
        total = (await cur.fetchone())[0]
        q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()], total


async def update_affiliate(affiliate_id: int, **kwargs):
    """Update affiliate fields."""
    allowed = {'name', 'phone', 'email', 'commission_pct', 'status',
               'phone_verified', 'email_verified', 'approved',
               'total_referrals', 'successful_conversions', 'total_earned', 'total_paid',
               'upi_id', 'bank_account', 'ifsc_code', 'bank_name', 'account_holder'}
    fields = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not fields:
        return
    fields['updated_at'] = datetime.now().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            f"UPDATE affiliates SET {set_clause} WHERE affiliate_id = ?",
            (*fields.values(), affiliate_id))
        await conn.commit()


async def create_referral(affiliate_id: int, referral_code: str,
                          referred_phone: str = None, referred_name: str = None) -> int:
    """Track a new referral. Returns referral_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO affiliate_referrals
               (affiliate_id, referral_code, referred_phone, referred_name)
               VALUES (?, ?, ?, ?)""",
            (affiliate_id, referral_code, referred_phone, referred_name))
        # Increment total referrals
        await conn.execute(
            "UPDATE affiliates SET total_referrals = total_referrals + 1 WHERE affiliate_id = ?",
            (affiliate_id,))
        await conn.commit()
        return cur.lastrowid


async def convert_referral(referral_id: int, tenant_id: int, plan: str,
                           commission_amount: float):
    """Mark a referral as converted."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """UPDATE affiliate_referrals SET status='converted', tenant_id=?,
               plan_activated=?, commission_amount=?, converted_at=datetime('now')
               WHERE referral_id = ?""",
            (tenant_id, plan, commission_amount, referral_id))
        # Get affiliate_id
        cur = await conn.execute(
            "SELECT affiliate_id FROM affiliate_referrals WHERE referral_id=?",
            (referral_id,))
        row = await cur.fetchone()
        if row:
            await conn.execute(
                """UPDATE affiliates SET
                   successful_conversions = successful_conversions + 1,
                   total_earned = total_earned + ?
                   WHERE affiliate_id = ?""",
                (commission_amount, row[0]))
        await conn.commit()


async def get_referrals(affiliate_id: int = None, status: str = None,
                        limit: int = 50) -> list:
    """Get referrals for an affiliate."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = """SELECT ar.*, a.name as affiliate_name, t.firm_name
               FROM affiliate_referrals ar
               LEFT JOIN affiliates a ON ar.affiliate_id = a.affiliate_id
               LEFT JOIN tenants t ON ar.tenant_id = t.tenant_id"""
        conditions, params = [], []
        if affiliate_id:
            conditions.append("ar.affiliate_id = ?")
            params.append(affiliate_id)
        if status:
            conditions.append("ar.status = ?")
            params.append(status)
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY ar.created_at DESC LIMIT ?"
        params.append(limit)
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]


async def get_affiliate_for_tenant(tenant_id: int) -> dict | None:
    """Reverse-lookup: given a tenant, find the affiliate who referred them."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT a.name, a.referral_code, a.email, a.phone
            FROM affiliate_referrals ar
            JOIN affiliates a ON ar.affiliate_id = a.affiliate_id
            WHERE ar.tenant_id = ? LIMIT 1
        """, (tenant_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_affiliate_map_for_tenants(tenant_ids: list) -> dict:
    """Bulk reverse-lookup: returns {tenant_id: {name, referral_code}} for a list of tenants."""
    if not tenant_ids:
        return {}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        placeholders = ','.join('?' * len(tenant_ids))
        cur = await conn.execute(f"""
            SELECT ar.tenant_id, a.name, a.referral_code
            FROM affiliate_referrals ar
            JOIN affiliates a ON ar.affiliate_id = a.affiliate_id
            WHERE ar.tenant_id IN ({placeholders})
        """, tenant_ids)
        rows = await cur.fetchall()
        return {r['tenant_id']: {'name': r['name'], 'referral_code': r['referral_code']} for r in rows}


async def get_affiliate_stats() -> dict:
    """Affiliate program stats for SA dashboard."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute("SELECT COUNT(*) FROM affiliates WHERE status='active'")
        active = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM affiliates WHERE status='pending_verification'")
        pending = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM affiliates")
        total = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(total_referrals),0) FROM affiliates")
        total_refs = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(successful_conversions),0) FROM affiliates")
        total_conv = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(total_earned),0) FROM affiliates")
        total_earned = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COALESCE(SUM(total_paid),0) FROM affiliates")
        total_paid = (await cur.fetchone())[0]
        # Payout pipeline stats
        cur = await conn.execute(
            "SELECT COUNT(*) FROM affiliate_referrals WHERE payout_status='cooling'")
        cooling_count = (await cur.fetchone())[0]
        cur = await conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(commission_amount),0) FROM affiliate_referrals WHERE payout_status='ready' AND paid=0")
        row = await cur.fetchone()
        ready_count, ready_amount = row[0], row[1]
        return {
            "active": active, "pending": pending,
            "total_affiliates": total,
            "total_referrals": total_refs, "conversions": total_conv,
            "total_earned": total_earned, "total_paid": total_paid,
            "pending_payout": total_earned - total_paid,
            "conversion_rate": round(total_conv / max(total_refs, 1), 3),
            "cooling_count": cooling_count,
            "ready_for_payout": ready_count,
            "ready_amount": ready_amount,
        }


async def is_phone_already_referred(phone: str) -> Optional[dict]:
    """Check if a phone has already been referred by ANY affiliate.
    Prevents cross-affiliate duplicate referrals."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT ar.*, a.name as affiliate_name
               FROM affiliate_referrals ar
               JOIN affiliates a ON ar.affiliate_id = a.affiliate_id
               WHERE ar.referred_phone = ? LIMIT 1""", (phone,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def get_founding_customer_count() -> int:
    """Count how many tenants have founding_discount=1 (first 500 founding customers)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT COUNT(*) FROM tenants WHERE founding_discount = 1")
        return (await cur.fetchone())[0]


async def convert_referral_by_phone(phone: str, tenant_id: int, plan: str) -> Optional[dict]:
    """Auto-convert a referral when a referred phone completes payment.
    Calculates commission based on affiliate's commission_pct and plan price.
    Sets a 7-day cooling period before commission becomes payable.
    Returns conversion details or None if no matching referral."""
    from biz_payments import PLANS
    plan_info = PLANS.get(plan, {})
    plan_amount = plan_info.get('amount_paise', 0) / 100  # ₹
    cooling_days = 7

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT ar.referral_id, ar.affiliate_id, a.commission_pct, a.name, a.phone as aff_phone
               FROM affiliate_referrals ar
               JOIN affiliates a ON ar.affiliate_id = a.affiliate_id
               WHERE ar.referred_phone = ? AND ar.status = 'pending'
               LIMIT 1""", (phone,))
        row = await cur.fetchone()
        if not row:
            return None

        commission = round(plan_amount * row['commission_pct'] / 100, 2)
        cooling_end = (datetime.now() + timedelta(days=cooling_days)).isoformat()
        await conn.execute(
            """UPDATE affiliate_referrals SET status='converted', tenant_id=?,
               plan_activated=?, commission_amount=?, converted_at=datetime('now'),
               cooling_ends_at=?, payout_status='cooling'
               WHERE referral_id = ?""",
            (tenant_id, plan, commission, cooling_end, row['referral_id']))
        await conn.execute(
            """UPDATE affiliates SET
               successful_conversions = successful_conversions + 1,
               total_earned = total_earned + ?
               WHERE affiliate_id = ?""",
            (commission, row['affiliate_id']))
        await conn.commit()

        return {
            'referral_id': row['referral_id'],
            'affiliate_name': row['name'],
            'affiliate_phone': row['aff_phone'],
            'commission': commission,
            'plan': plan,
            'cooling_ends_at': cooling_end,
        }


async def process_payment_commission(tenant_id: int, plan: str,
                                      payment_id: str = None,
                                      amount_paise: int = 0) -> Optional[dict]:
    """Record affiliate commission for ANY payment (first or recurring).
    Uses tenant.referral_code to find the affiliate.
    Idempotent: won't double-record for same payment_id.
    Also converts pending referral on first payment."""
    from biz_payments import PLANS
    plan_info = PLANS.get(plan, {})
    payment_amount = (amount_paise / 100) if amount_paise else (plan_info.get('amount_paise', 0) / 100)
    cooling_days = 7

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Get tenant's referral code
        cur = await conn.execute(
            "SELECT referral_code, phone FROM tenants WHERE tenant_id = ?",
            (tenant_id,))
        tenant = await cur.fetchone()
        if not tenant or not tenant['referral_code']:
            return None

        # Get affiliate
        cur = await conn.execute(
            """SELECT affiliate_id, commission_pct, name, phone as aff_phone, email
               FROM affiliates WHERE referral_code = ? AND status = 'active'""",
            (tenant['referral_code'],))
        aff = await cur.fetchone()
        if not aff:
            return None

        # Idempotency: check if this payment already commissioned
        if payment_id:
            cur = await conn.execute(
                "SELECT commission_id FROM affiliate_commissions WHERE payment_id = ?",
                (payment_id,))
            if await cur.fetchone():
                return None  # Already processed

        commission = round(payment_amount * aff['commission_pct'] / 100, 2)
        if commission <= 0:
            return None

        cooling_end = (datetime.now() + timedelta(days=cooling_days)).isoformat()

        # Also convert pending referral if this is the first payment
        phone = tenant['phone']
        if phone:
            cur = await conn.execute(
                """SELECT referral_id FROM affiliate_referrals
                   WHERE referred_phone = ? AND status = 'pending' LIMIT 1""",
                (phone,))
            pending_ref = await cur.fetchone()
            if pending_ref:
                await conn.execute(
                    """UPDATE affiliate_referrals SET status='converted', tenant_id=?,
                       plan_activated=?, commission_amount=?, converted_at=datetime('now'),
                       cooling_ends_at=?, payout_status='cooling'
                       WHERE referral_id = ?""",
                    (tenant_id, plan, commission, cooling_end, pending_ref['referral_id']))
                await conn.execute(
                    """UPDATE affiliates SET successful_conversions = successful_conversions + 1
                       WHERE affiliate_id = ?""",
                    (aff['affiliate_id'],))

        # Record commission in new table
        cur = await conn.execute(
            """INSERT INTO affiliate_commissions
               (affiliate_id, tenant_id, payment_id, plan, payment_amount,
                commission_amount, commission_pct, payout_status, cooling_ends_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'cooling', ?)""",
            (aff['affiliate_id'], tenant_id, payment_id, plan,
             payment_amount, commission, aff['commission_pct'], cooling_end))
        commission_id = cur.lastrowid

        # Update affiliate.total_earned
        await conn.execute(
            "UPDATE affiliates SET total_earned = total_earned + ? WHERE affiliate_id = ?",
            (commission, aff['affiliate_id']))
        await conn.commit()

        return {
            'commission_id': commission_id,
            'affiliate_id': aff['affiliate_id'],
            'affiliate_name': aff['name'],
            'affiliate_phone': aff['aff_phone'],
            'affiliate_email': aff['email'],
            'commission': commission,
            'plan': plan,
            'cooling_ends_at': cooling_end,
        }


async def mature_cooling_commissions() -> int:
    """Move commissions past their 7-day cooling period to 'ready' status.
    Called periodically (e.g. daily cron). Returns count of matured records."""
    async with aiosqlite.connect(DB_PATH) as conn:
        # Legacy referrals table
        cur1 = await conn.execute(
            """UPDATE affiliate_referrals
               SET payout_status = 'ready'
               WHERE status = 'converted'
                 AND payout_status = 'cooling'
                 AND cooling_ends_at <= datetime('now')""")
        # New commissions table
        cur2 = await conn.execute(
            """UPDATE affiliate_commissions
               SET payout_status = 'ready'
               WHERE payout_status = 'cooling'
                 AND cooling_ends_at <= datetime('now')""")
        await conn.commit()
        return cur1.rowcount + cur2.rowcount


async def get_ready_commissions(affiliate_id: int = None) -> list:
    """Get all commissions ready for payout (from both legacy referrals and recurring commissions)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        results = []
        # Legacy referrals (first-conversion commissions)
        q1 = """SELECT ar.referral_id as id, 'referral' as source,
                       ar.affiliate_id, ar.commission_amount, ar.converted_at as earned_at,
                       ar.payout_status, ar.payout_id, ar.paid, ar.plan_activated as plan,
                       a.name as affiliate_name, a.upi_id, a.bank_account,
                       a.ifsc_code, a.bank_name, a.account_holder, a.email
                FROM affiliate_referrals ar
                JOIN affiliates a ON ar.affiliate_id = a.affiliate_id
                WHERE ar.payout_status = 'ready' AND ar.paid = 0"""
        params1 = []
        if affiliate_id:
            q1 += " AND ar.affiliate_id = ?"
            params1.append(affiliate_id)
        cur1 = await conn.execute(q1, params1)
        results.extend([dict(r) for r in await cur1.fetchall()])
        # Recurring commissions
        q2 = """SELECT ac.commission_id as id, 'recurring' as source,
                       ac.affiliate_id, ac.commission_amount, ac.created_at as earned_at,
                       ac.payout_status, ac.payout_id, 0 as paid, ac.plan,
                       a.name as affiliate_name, a.upi_id, a.bank_account,
                       a.ifsc_code, a.bank_name, a.account_holder, a.email
                FROM affiliate_commissions ac
                JOIN affiliates a ON ac.affiliate_id = a.affiliate_id
                WHERE ac.payout_status = 'ready'"""
        params2 = []
        if affiliate_id:
            q2 += " AND ac.affiliate_id = ?"
            params2.append(affiliate_id)
        cur2 = await conn.execute(q2, params2)
        results.extend([dict(r) for r in await cur2.fetchall()])
        results.sort(key=lambda r: r.get('earned_at', ''))
        return results


async def create_payout(affiliate_id: int, amount: float, method: str = 'upi',
                        upi_id: str = None, bank_account: str = None,
                        ifsc_code: str = None, reference_id: str = None,
                        initiated_by: str = 'sa', note: str = None) -> int:
    """Create a payout record and snapshot ready referrals + commissions. Returns payout_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO affiliate_payouts
               (affiliate_id, amount, method, upi_id, bank_account, ifsc_code,
                reference_id, initiated_by, note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (affiliate_id, amount, method, upi_id, bank_account, ifsc_code,
             reference_id, initiated_by, note))
        payout_id = cur.lastrowid
        # Snapshot: lock current ready referrals to this payout
        await conn.execute(
            """UPDATE affiliate_referrals
               SET payout_id = ?, payout_status = 'processing'
               WHERE affiliate_id = ? AND payout_status = 'ready' AND paid = 0""",
            (payout_id, affiliate_id))
        # Snapshot: lock current ready commissions to this payout
        await conn.execute(
            """UPDATE affiliate_commissions
               SET payout_id = ?, payout_status = 'processing'
               WHERE affiliate_id = ? AND payout_status = 'ready'""",
            (payout_id, affiliate_id))
        await conn.commit()
        return payout_id


async def complete_payout(payout_id: int, reference_id: str = None) -> bool:
    """Mark a payout as completed. Only marks referrals snapshotted to this payout as paid."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM affiliate_payouts WHERE payout_id = ?", (payout_id,))
        payout = await cur.fetchone()
        if not payout:
            return False
        if payout['status'] == 'completed':
            return False  # Prevent double-completion
        updates = {"status": "completed", "completed_at": datetime.now().isoformat()}
        if reference_id:
            updates["reference_id"] = reference_id
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        await conn.execute(
            f"UPDATE affiliate_payouts SET {set_clause} WHERE payout_id = ?",
            (*updates.values(), payout_id))
        # Update affiliate total_paid
        await conn.execute(
            "UPDATE affiliates SET total_paid = total_paid + ? WHERE affiliate_id = ?",
            (payout['amount'], payout['affiliate_id']))
        # Mark ONLY referrals snapshotted to this payout as paid
        await conn.execute(
            """UPDATE affiliate_referrals
               SET paid = 1, payout_status = 'paid'
               WHERE payout_id = ? AND paid = 0""",
            (payout_id,))
        # Mark recurring commissions snapshotted to this payout as paid
        await conn.execute(
            """UPDATE affiliate_commissions
               SET payout_status = 'paid'
               WHERE payout_id = ?""",
            (payout_id,))
        await conn.commit()
        return True


async def get_payouts(affiliate_id: int = None, status: str = None,
                      limit: int = 50) -> list:
    """Get payout records, optionally filtered."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        q = """SELECT p.*, a.name as affiliate_name, a.phone as affiliate_phone
               FROM affiliate_payouts p
               JOIN affiliates a ON p.affiliate_id = a.affiliate_id"""
        conditions, params = [], []
        if affiliate_id:
            conditions.append("p.affiliate_id = ?")
            params.append(affiliate_id)
        if status:
            conditions.append("p.status = ?")
            params.append(status)
        if conditions:
            q += " WHERE " + " AND ".join(conditions)
        q += " ORDER BY p.created_at DESC LIMIT ?"
        params.append(limit)
        cur = await conn.execute(q, params)
        return [dict(r) for r in await cur.fetchall()]


async def reverse_commission(referral_id: int, reason: str = 'chargeback') -> Optional[dict]:
    """Reverse a commission (chargeback/refund). Deducts from affiliate's total_earned.
    Only works on unpaid commissions."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM affiliate_referrals WHERE referral_id = ?", (referral_id,))
        ref = await cur.fetchone()
        if not ref:
            return None
        if ref['paid']:
            return {'error': 'Cannot reverse already-paid commission'}
        commission = ref['commission_amount'] or 0
        await conn.execute(
            """UPDATE affiliate_referrals
               SET payout_status = 'reversed', status = 'reversed'
               WHERE referral_id = ?""", (referral_id,))
        if commission > 0:
            await conn.execute(
                """UPDATE affiliates
                   SET total_earned = MAX(0, total_earned - ?),
                       successful_conversions = MAX(0, successful_conversions - 1)
                   WHERE affiliate_id = ?""",
                (commission, ref['affiliate_id']))
        await conn.commit()
        await log_audit('commission_reversed',
                        f'Referral #{referral_id} reversed ({reason}), ₹{commission} deducted',
                        tenant_id=ref.get('tenant_id'))
        return {'referral_id': referral_id, 'amount_reversed': commission, 'reason': reason}


# =============================================================================
#  AFFILIATE SUPPORT TICKETS
# =============================================================================

async def create_affiliate_ticket(affiliate_id: int, subject: str, message: str,
                                   category: str = 'general') -> dict:
    """Create a support ticket from an affiliate."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO affiliate_tickets (affiliate_id, subject, category)
               VALUES (?, ?, ?)""",
            (affiliate_id, subject, category))
        ticket_id = cur.lastrowid
        await conn.execute(
            """INSERT INTO affiliate_ticket_messages (ticket_id, sender_type, sender_name, message)
               VALUES (?, 'affiliate', (SELECT name FROM affiliates WHERE affiliate_id = ?), ?)""",
            (ticket_id, affiliate_id, message))
        await conn.commit()
        return {'ticket_id': ticket_id, 'status': 'open'}


async def get_affiliate_tickets(affiliate_id: int = None, status: str = None,
                                 limit: int = 50) -> list:
    """Get affiliate tickets. If affiliate_id is None, returns all (for SA)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        sql = """SELECT t.*, a.name as affiliate_name, a.phone as affiliate_phone,
                        a.referral_code
                 FROM affiliate_tickets t
                 JOIN affiliates a ON a.affiliate_id = t.affiliate_id
                 WHERE 1=1"""
        params = []
        if affiliate_id is not None:
            sql += " AND t.affiliate_id = ?"
            params.append(affiliate_id)
        if status:
            sql += " AND t.status = ?"
            params.append(status)
        sql += " ORDER BY t.updated_at DESC LIMIT ?"
        params.append(limit)
        cur = await conn.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]


async def get_affiliate_ticket(ticket_id: int) -> Optional[dict]:
    """Get a single affiliate ticket with messages."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT t.*, a.name as affiliate_name, a.phone as affiliate_phone,
                      a.referral_code, a.email as affiliate_email
               FROM affiliate_tickets t
               JOIN affiliates a ON a.affiliate_id = t.affiliate_id
               WHERE t.ticket_id = ?""", (ticket_id,))
        ticket = await cur.fetchone()
        if not ticket:
            return None
        ticket = dict(ticket)
        cur = await conn.execute(
            "SELECT * FROM affiliate_ticket_messages WHERE ticket_id = ? ORDER BY created_at ASC",
            (ticket_id,))
        ticket['messages'] = [dict(r) for r in await cur.fetchall()]
        return ticket


async def add_affiliate_ticket_message(ticket_id: int, message: str,
                                        sender_type: str = 'affiliate',
                                        sender_name: str = None) -> dict:
    """Add a message to an affiliate ticket."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO affiliate_ticket_messages (ticket_id, sender_type, sender_name, message)
               VALUES (?, ?, ?, ?)""",
            (ticket_id, sender_type, sender_name, message))
        await conn.execute(
            "UPDATE affiliate_tickets SET updated_at = datetime('now') WHERE ticket_id = ?",
            (ticket_id,))
        if sender_type == 'admin' and sender_name:
            # Auto move to in_progress when admin first replies
            await conn.execute(
                """UPDATE affiliate_tickets SET status = 'in_progress'
                   WHERE ticket_id = ? AND status = 'open'""", (ticket_id,))
        await conn.commit()
        return {'status': 'ok'}


async def update_affiliate_ticket(ticket_id: int, **updates) -> dict:
    """Update affiliate ticket fields (status, priority, etc.)."""
    allowed = {'status', 'priority', 'category'}
    fields = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not fields:
        return {'status': 'no_changes'}
    async with aiosqlite.connect(DB_PATH) as conn:
        sets = ', '.join(f"{k} = ?" for k in fields)
        vals = list(fields.values())
        if 'status' in fields and fields['status'] == 'resolved':
            sets += ", resolved_at = datetime('now')"
        sets += ", updated_at = datetime('now')"
        await conn.execute(f"UPDATE affiliate_tickets SET {sets} WHERE ticket_id = ?",
                          vals + [ticket_id])
        await conn.commit()
        return {'status': 'ok'}


async def get_affiliate_ticket_stats() -> dict:
    """Stats for affiliate tickets (SA dashboard)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        stats = {}
        for s in ('open', 'in_progress', 'resolved'):
            cur = await conn.execute(
                "SELECT COUNT(*) FROM affiliate_tickets WHERE status = ?", (s,))
            stats[s] = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT COUNT(*) FROM affiliate_tickets")
        stats['total'] = (await cur.fetchone())[0]
        return stats

async def init_plan_changes_table():
    """Create pending_plan_changes table (idempotent)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_plan_changes (
                change_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id       INTEGER NOT NULL UNIQUE,
                current_plan    TEXT NOT NULL,
                new_plan        TEXT NOT NULL,
                scheduled_at    TEXT NOT NULL,
                effective_after TEXT NOT NULL,
                requested_by    TEXT DEFAULT 'tenant',
                status          TEXT DEFAULT 'pending',
                created_at      TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
            )
        """)
        await conn.commit()


async def schedule_plan_change(tenant_id: int, new_plan: str,
                                requested_by: str = 'tenant') -> dict:
    """Schedule a plan change for the next billing cycle.
    Returns result dict. Only one pending change per tenant at a time."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return {'success': False, 'error': 'Tenant not found'}

    current = tenant.get('plan', 'trial')
    if current == new_plan:
        return {'success': False, 'error': 'Already on this plan'}

    if new_plan not in PLAN_PRICING and new_plan != 'individual':
        return {'success': False, 'error': f'Unknown plan: {new_plan}'}

    plan_info = PLAN_PRICING.get(new_plan, PLAN_PRICING.get('individual'))

    # For downgrades: validate agent count NOW
    current_idx = PLAN_ORDER.index(current) if current in PLAN_ORDER else 0
    new_idx = PLAN_ORDER.index(new_plan) if new_plan in PLAN_ORDER else 0
    is_downgrade = new_idx < current_idx

    if is_downgrade:
        agent_count = await get_tenant_agent_count(tenant_id)
        if agent_count > plan_info['max_agents']:
            return {
                'success': False,
                'error': f'You have {agent_count} active agents but '
                         f'{plan_info["name"]} allows max {plan_info["max_agents"]}. '
                         f'Remove/deactivate agents before scheduling downgrade.'
            }

    # Determine effective date: end of current billing cycle
    effective_after = tenant.get('subscription_expires_at') or \
                      tenant.get('trial_ends_at') or \
                      datetime.now().isoformat()

    async with aiosqlite.connect(DB_PATH) as conn:
        # Remove any existing pending change
        await conn.execute(
            "DELETE FROM pending_plan_changes WHERE tenant_id=?", (tenant_id,))
        await conn.execute(
            """INSERT INTO pending_plan_changes
               (tenant_id, current_plan, new_plan, scheduled_at, effective_after, requested_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tenant_id, current, new_plan, datetime.now().isoformat(),
             effective_after, requested_by))
        await conn.commit()

    change_type = 'downgrade' if is_downgrade else 'upgrade'
    await log_audit(f'plan_{change_type}_scheduled',
                    f'{current} → {new_plan} (effective after {effective_after})',
                    tenant_id=tenant_id)

    return {
        'success': True,
        'change_type': change_type,
        'current_plan': current,
        'new_plan': new_plan,
        'effective_after': effective_after,
        'message': f'Plan change to {plan_info["name"]} scheduled. '
                   f'Will take effect at next billing cycle.'
    }


async def get_pending_plan_change(tenant_id: int) -> Optional[dict]:
    """Get pending plan change for a tenant, if any."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM pending_plan_changes WHERE tenant_id=? AND status='pending'",
            (tenant_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def cancel_pending_plan_change(tenant_id: int) -> bool:
    """Cancel a pending plan change."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "DELETE FROM pending_plan_changes WHERE tenant_id=? AND status='pending'",
            (tenant_id,))
        await conn.commit()
        if cursor.rowcount > 0:
            await log_audit('plan_change_cancelled', 'Pending plan change cancelled',
                            tenant_id=tenant_id)
            return True
    return False


async def apply_pending_plan_changes() -> list:
    """Apply all pending plan changes whose effective date has passed.
    Called by background scheduler. Returns list of applied changes."""
    applied = []
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM pending_plan_changes
               WHERE status='pending' AND effective_after <= ?""", (now,))
        pending = [dict(r) for r in await cursor.fetchall()]

    for change in pending:
        tid = change['tenant_id']
        new_plan = change['new_plan']
        plan_info = PLAN_PRICING.get(new_plan)
        if not plan_info:
            continue

        # Re-validate agent count for downgrades
        agent_count = await get_tenant_agent_count(tid)
        if agent_count > plan_info['max_agents']:
            # Cannot apply — mark as blocked
            async with aiosqlite.connect(DB_PATH) as conn:
                await conn.execute(
                    "UPDATE pending_plan_changes SET status='blocked' WHERE change_id=?",
                    (change['change_id'],))
                await conn.commit()
            await log_audit('plan_change_blocked',
                            f'Cannot apply: {agent_count} agents > {plan_info["max_agents"]} limit',
                            tenant_id=tid)
            continue

        # Apply the change
        await update_tenant(tid,
                            plan=new_plan,
                            max_agents=plan_info['max_agents'])

        # Mark as applied
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                "UPDATE pending_plan_changes SET status='applied' WHERE change_id=?",
                (change['change_id'],))
            await conn.commit()

        await log_audit('plan_change_applied',
                        f'{change["current_plan"]} → {new_plan}',
                        tenant_id=tid)
        applied.append(change)

    return applied


async def force_apply_plan_change(tenant_id: int, new_plan: str) -> dict:
    """SA: Immediately apply a plan change (bypass scheduling)."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return {'success': False, 'error': 'Tenant not found'}

    current = tenant.get('plan', 'trial')
    plan_info = PLAN_PRICING.get(new_plan)
    if not plan_info:
        return {'success': False, 'error': f'Unknown plan: {new_plan}'}

    current_idx = PLAN_ORDER.index(current) if current in PLAN_ORDER else 0
    new_idx = PLAN_ORDER.index(new_plan) if new_plan in PLAN_ORDER else 0

    if new_idx < current_idx:
        agent_count = await get_tenant_agent_count(tenant_id)
        if agent_count > plan_info['max_agents']:
            return {
                'success': False,
                'error': f'Tenant has {agent_count} agents but {plan_info["name"]} '
                         f'allows max {plan_info["max_agents"]}. Cannot force downgrade.'
            }

    await update_tenant(tenant_id,
                        plan=new_plan,
                        subscription_status='active',
                        max_agents=plan_info['max_agents'])

    # Clear any pending change
    await cancel_pending_plan_change(tenant_id)

    await log_audit('plan_force_changed',
                    f'{current} → {new_plan} (SA forced)',
                    tenant_id=tenant_id)

    return {'success': True, 'old_plan': current, 'new_plan': new_plan,
            'max_agents': plan_info['max_agents']}


# =============================================================================
#  ADMIN DASHBOARD DATA — Tenant-level views for firm owners
# =============================================================================

async def get_leads_by_tenant(tenant_id: int, stage: str = None,
                               search: str = None, limit: int = 200,
                               offset: int = 0, agent_id: int = None,
                               client_type: str = None) -> dict:
    """Get leads for a tenant. If agent_id provided, filter to that agent only."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        conditions = ["a.tenant_id = ?"]
        params = [tenant_id]

        if agent_id:
            conditions.append("l.agent_id = ?")
            params.append(agent_id)

        if client_type:
            conditions.append("l.client_type = ?")
            params.append(client_type)

        if stage and stage != 'all':
            conditions.append("l.stage = ?")
            params.append(stage)
        if search:
            conditions.append("(l.name LIKE ? OR l.phone LIKE ? OR l.email LIKE ?)")
            s = f"%{search}%"
            params.extend([s, s, s])

        where = " AND ".join(conditions)

        # Count total
        count_q = f"""SELECT COUNT(*) FROM leads l
                      JOIN agents a ON l.agent_id = a.agent_id
                      WHERE {where}"""
        cursor = await conn.execute(count_q, params)
        total = (await cursor.fetchone())[0]

        # Fetch page — use datetime() to normalise mixed ISO-T / space formats,
        # tie-break by lead_id DESC so newest insert always wins on equal timestamps.
        q = f"""SELECT l.*, a.name as agent_name, a.agent_id
                FROM leads l
                JOIN agents a ON l.agent_id = a.agent_id
                WHERE {where}
                ORDER BY datetime(l.updated_at) DESC, l.lead_id DESC
                LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        cursor = await conn.execute(q, params)
        rows = [dict(r) for r in await cursor.fetchall()]

    return {'leads': rows, 'total': total, 'limit': limit, 'offset': offset}


async def get_policies_by_tenant(tenant_id: int, status: str = None,
                                  limit: int = 200, offset: int = 0,
                                  agent_id: int = None) -> dict:
    """Get policies for a tenant. If agent_id provided, filter to that agent only."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        conditions = ["a.tenant_id = ?"]
        params = [tenant_id]
        if agent_id:
            conditions.append("p.agent_id = ?")
            params.append(agent_id)
        if status:
            conditions.append("p.status = ?")
            params.append(status)

        where = " AND ".join(conditions)
        count_q = f"""SELECT COUNT(*) FROM policies p
                      JOIN agents a ON p.agent_id = a.agent_id
                      WHERE {where}"""
        cursor = await conn.execute(count_q, params)
        total = (await cursor.fetchone())[0]

        q = f"""SELECT p.*, a.name as agent_name, l.name as lead_name, l.phone as lead_phone
                FROM policies p
                JOIN agents a ON p.agent_id = a.agent_id
                LEFT JOIN leads l ON p.lead_id = l.lead_id
                WHERE {where}
                ORDER BY p.created_at DESC
                LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        cursor = await conn.execute(q, params)
        rows = [dict(r) for r in await cursor.fetchall()]

    return {'policies': rows, 'total': total}


async def get_customers_with_portfolio(tenant_id: int, search: str = None,
                                        limit: int = 50, offset: int = 0,
                                        agent_id: int = None) -> dict:
    """Get customers (client_type='customer') with their policy counts and totals."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        conditions = ["a.tenant_id = ?", "l.client_type = 'customer'"]
        params = [tenant_id]
        if agent_id:
            conditions.append("l.agent_id = ?")
            params.append(agent_id)
        if search:
            conditions.append("(l.name LIKE ? OR l.phone LIKE ? OR l.email LIKE ?)")
            s = f"%{search}%"
            params.extend([s, s, s])
        where = " AND ".join(conditions)

        count_q = f"""SELECT COUNT(*) FROM leads l
                      JOIN agents a ON l.agent_id = a.agent_id
                      WHERE {where}"""
        cursor = await conn.execute(count_q, params)
        total = (await cursor.fetchone())[0]

        q = f"""SELECT l.*, a.name as agent_name,
                (SELECT COUNT(*) FROM policies p2 WHERE p2.lead_id = l.lead_id) as policy_count,
                (SELECT COALESCE(SUM(p3.premium),0) FROM policies p3 WHERE p3.lead_id = l.lead_id AND p3.status='active') as total_premium,
                (SELECT COUNT(*) FROM policies p4 WHERE p4.lead_id = l.lead_id AND p4.sold_by_agent=1) as sold_count,
                (SELECT COUNT(*) FROM policies p5 WHERE p5.lead_id = l.lead_id AND p5.sold_by_agent=0) as tracked_count
                FROM leads l
                JOIN agents a ON l.agent_id = a.agent_id
                WHERE {where}
                ORDER BY l.name ASC
                LIMIT ? OFFSET ?"""
        params.extend([limit, offset])
        cursor = await conn.execute(q, params)
        rows = [dict(r) for r in await cursor.fetchall()]

    return {'customers': rows, 'total': total}


async def get_admin_overview(tenant_id: int, agent_id: int = None) -> dict:
    """Get dashboard overview. If agent_id provided, scope to that agent only."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return {}

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        if agent_id:
            # Single agent scope
            agent_ids = [agent_id]
        else:
            # All agents in tenant
            cursor = await conn.execute(
                "SELECT agent_id FROM agents WHERE tenant_id=? AND is_active=1",
                (tenant_id,))
            agent_ids = [r[0] for r in await cursor.fetchall()]

        if not agent_ids:
            return {
                'total_leads': 0, 'total_policies': 0, 'total_premium': 0,
                'today_leads': 0, 'pipeline': {}, 'conversion_rate': 0,
                'total_agents': 0, 'active_agents': 0,
                'month_leads': 0, 'month_policies': 0, 'month_premium': 0,
            }

        placeholders = ','.join('?' * len(agent_ids))

        # Total leads
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM leads WHERE agent_id IN ({placeholders})",
            agent_ids)
        total_leads = (await cursor.fetchone())[0]

        # Today's leads
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM leads WHERE agent_id IN ({placeholders}) "
            f"AND date(created_at) = date('now')", agent_ids)
        today_leads = (await cursor.fetchone())[0]

        # This month leads
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM leads WHERE agent_id IN ({placeholders}) "
            f"AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')", agent_ids)
        month_leads = (await cursor.fetchone())[0]

        # Pipeline
        cursor = await conn.execute(
            f"SELECT stage, COUNT(*) as cnt FROM leads "
            f"WHERE agent_id IN ({placeholders}) GROUP BY stage", agent_ids)
        pipeline = {r['stage']: r['cnt'] for r in await cursor.fetchall()}

        # Policies
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM policies WHERE agent_id IN ({placeholders}) "
            f"AND status='active'", agent_ids)
        total_policies = (await cursor.fetchone())[0]

        # Total premium
        cursor = await conn.execute(
            f"SELECT COALESCE(SUM(premium),0) FROM policies "
            f"WHERE agent_id IN ({placeholders}) AND status='active'", agent_ids)
        total_premium = (await cursor.fetchone())[0]

        # This month policies
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM policies WHERE agent_id IN ({placeholders}) "
            f"AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')", agent_ids)
        month_policies = (await cursor.fetchone())[0]

        # Month premium
        cursor = await conn.execute(
            f"SELECT COALESCE(SUM(premium),0) FROM policies "
            f"WHERE agent_id IN ({placeholders}) "
            f"AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')", agent_ids)
        month_premium = (await cursor.fetchone())[0]

        # Conversion rate
        won = pipeline.get('closed_won', 0)
        total_closed = won + pipeline.get('closed_lost', 0)
        conversion_rate = round(won / max(total_closed, 1) * 100, 1)

        # Agent counts
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM agents WHERE tenant_id=?", (tenant_id,))
        total_agents = (await cursor.fetchone())[0]
        active_agents = len(agent_ids)

        # Needs review count (leads with need_type='review')
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM leads WHERE agent_id IN ({placeholders}) "
            f"AND need_type='review'", agent_ids)
        needs_review_count = (await cursor.fetchone())[0]

    return {
        'total_leads': total_leads, 'total_policies': total_policies,
        'total_premium': total_premium, 'today_leads': today_leads,
        'pipeline': pipeline, 'conversion_rate': conversion_rate,
        'total_agents': total_agents, 'active_agents': active_agents,
        'month_leads': month_leads, 'month_policies': month_policies,
        'month_premium': month_premium, 'needs_review_count': needs_review_count,
    }


async def delete_lead(lead_id: int, agent_id: int = None,
                      tenant_id: int = None) -> dict:
    """Delete a lead and all associated data.
    If agent_id given, verify ownership. If tenant_id given, verify tenant scope."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM leads WHERE lead_id=?", (lead_id,))
        lead = await cursor.fetchone()
        if not lead:
            return {'success': False, 'error': 'Lead not found'}
        if agent_id and lead['agent_id'] != agent_id:
            return {'success': False, 'error': 'Not your lead'}
        # Tenant scope check
        if tenant_id is not None:
            agent_row = await (await conn.execute(
                "SELECT tenant_id FROM agents WHERE agent_id=?",
                (lead['agent_id'],))).fetchone()
            if not agent_row or agent_row['tenant_id'] != tenant_id:
                return {'success': False, 'error': 'Lead not in your firm'}

        # Delete associated data
        await conn.execute("DELETE FROM interactions WHERE lead_id=?", (lead_id,))
        await conn.execute("DELETE FROM reminders WHERE lead_id=?", (lead_id,))
        await conn.execute("DELETE FROM claims WHERE lead_id=?", (lead_id,))
        await conn.execute("DELETE FROM policies WHERE lead_id=?", (lead_id,))
        await conn.execute("DELETE FROM greetings_log WHERE lead_id=?", (lead_id,))
        await conn.execute("DELETE FROM leads WHERE lead_id=?", (lead_id,))
        await conn.commit()

    return {'success': True, 'deleted_lead_id': lead_id}


async def add_lead_admin(tenant_id: int, name: str, phone: str = None,
                          email: str = None, dob: str = None, city: str = None,
                          need_type: str = 'health', source: str = 'web_admin',
                          notes: str = None, assign_to_agent_id: int = None) -> dict:
    """Admin: Add a lead from web dashboard. Auto-assigns to owner if no agent specified."""
    tenant = await get_tenant(tenant_id)
    if not tenant:
        return {'success': False, 'error': 'Tenant not found'}

    # Determine which agent to assign to
    if assign_to_agent_id:
        agent = await get_agent_by_id(assign_to_agent_id)
        if not agent or agent.get('tenant_id') != tenant_id:
            return {'success': False, 'error': 'Agent not found in your firm'}
        target_agent_id = assign_to_agent_id
    else:
        # Assign to owner
        owner_tg = tenant.get('owner_telegram_id')
        if owner_tg:
            agent = await get_agent(owner_tg)
            if agent:
                target_agent_id = agent['agent_id']
            else:
                return {'success': False, 'error': 'No agent found for owner'}
        else:
            # Fallback: first active agent
            agents = await get_agents_by_tenant(tenant_id)
            if agents:
                target_agent_id = agents[0]['agent_id']
            else:
                return {'success': False, 'error': 'No agents available'}

    # Check for duplicate within tenant
    if phone:
        dup = await find_duplicate_lead_tenant(tenant_id, phone)
        if dup:
            return {'success': False, 'error': f'Lead with phone {phone} already exists (assigned to {dup.get("agent_name", "agent")})'}

    lead_id = await add_lead(
        agent_id=target_agent_id,
        name=name, phone=phone, email=email,
        dob=dob, city=city, need_type=need_type,
        source=source, notes=notes
    )

    return {'success': True, 'lead_id': lead_id, 'agent_id': target_agent_id}


async def reassign_lead(lead_id: int, new_agent_id: int, tenant_id: int) -> dict:
    """Admin: Reassign a lead to a different agent within the same tenant.
    Verifies both the target agent AND the lead belong to this tenant."""
    agent = await get_agent_by_id(new_agent_id)
    if not agent or agent.get('tenant_id') != tenant_id:
        return {'success': False, 'error': 'Agent not in your firm'}

    # Verify lead belongs to this tenant (via its current agent)
    lead = await get_lead(lead_id)
    if not lead:
        return {'success': False, 'error': 'Lead not found'}
    current_agent = await get_agent_by_id(lead['agent_id'])
    if not current_agent or current_agent.get('tenant_id') != tenant_id:
        return {'success': False, 'error': 'Lead not in your firm'}

    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "UPDATE leads SET agent_id=?, updated_at=? WHERE lead_id=?",
            (new_agent_id, datetime.now().isoformat(), lead_id))
        await conn.commit()
        if cursor.rowcount == 0:
            return {'success': False, 'error': 'Lead not found'}

    return {'success': True, 'lead_id': lead_id, 'new_agent_id': new_agent_id}


async def create_invite_code_web(tenant_id: int, owner_agent_id: int) -> dict:
    """Admin: Generate invite code from web dashboard."""
    check = await can_add_agent(tenant_id)
    if not check.get('allowed'):
        return {'success': False, 'error': check.get('reason', 'Agent limit reached')}

    code = await create_invite_code(tenant_id, owner_agent_id, max_uses=5)
    return {'success': True, 'code': code, 'max_uses': 5, 'expires_in': '7 days'}


# =============================================================================
#  PROCESSED PAYMENTS — Idempotency guard for webhook + frontend verify
# =============================================================================

async def is_payment_processed(razorpay_payment_id: str) -> bool:
    """Check if a payment has already been processed (prevents duplicates)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT 1 FROM processed_payments WHERE razorpay_payment_id = ?",
            (razorpay_payment_id,))
        return await cur.fetchone() is not None


async def record_payment_processed(razorpay_payment_id: str, tenant_id: int,
                                    plan_key: str, source: str,
                                    amount_paise: int = 0) -> bool:
    """Record a payment as processed. Returns True if inserted, False if duplicate."""
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute(
                """INSERT INTO processed_payments
                   (razorpay_payment_id, tenant_id, plan_key, source, amount_paise)
                   VALUES (?, ?, ?, ?, ?)""",
                (razorpay_payment_id, tenant_id, plan_key, source, amount_paise))
            await conn.commit()
            return True
    except Exception:
        # UNIQUE constraint violation = already processed
        return False


# =============================================================================
#  SYSTEM EVENTS — Error / Security / Anomaly tracking for SA
# =============================================================================

async def add_system_event(event_type: str, severity: str, category: str,
                           title: str, detail: str = None,
                           tenant_id: int = None, agent_id: int = None,
                           ip_address: str = None) -> int:
    """Log a system event (error, security alert, anomaly, etc). Returns event_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO system_events
               (event_type, severity, category, title, detail,
                tenant_id, agent_id, ip_address)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, severity, category, title, detail,
             tenant_id, agent_id, ip_address))
        await conn.commit()
        return cursor.lastrowid


async def get_system_events(event_type: str = None, severity: str = None,
                            resolved: int = None, limit: int = 100,
                            offset: int = 0) -> list:
    """Fetch system events with optional filters."""
    clauses, params = [], []
    if event_type:
        clauses.append("event_type = ?"); params.append(event_type)
    if severity:
        clauses.append("severity = ?"); params.append(severity)
    if resolved is not None:
        clauses.append("resolved = ?"); params.append(resolved)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            f"SELECT * FROM system_events {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset))
        return [dict(r) for r in await cur.fetchall()]


async def get_system_event_stats() -> dict:
    """Get event counts by type and severity."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # By type
        cur = await conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM system_events GROUP BY event_type")
        by_type = {r['event_type']: r['cnt'] for r in await cur.fetchall()}
        # Unresolved by severity
        cur = await conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM system_events WHERE resolved=0 GROUP BY severity")
        unresolved = {r['severity']: r['cnt'] for r in await cur.fetchall()}
        # Total / unresolved
        cur = await conn.execute("SELECT COUNT(*) as total FROM system_events")
        total = (await cur.fetchone())['total']
        cur = await conn.execute("SELECT COUNT(*) as cnt FROM system_events WHERE resolved=0")
        open_cnt = (await cur.fetchone())['cnt']
        return {"total": total, "open": open_cnt, "by_type": by_type, "unresolved_by_severity": unresolved}


async def resolve_system_event(event_id: int, resolved_by: str = "superadmin",
                               auto_fixed: bool = False) -> bool:
    """Mark a system event as resolved."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """UPDATE system_events SET resolved=1, resolved_by=?, resolved_at=datetime('now'),
               auto_fixed=? WHERE event_id=?""",
            (resolved_by, 1 if auto_fixed else 0, event_id))
        await conn.commit()
        return cur.rowcount > 0


async def bulk_resolve_system_events(event_ids: list, resolved_by: str = "superadmin") -> int:
    """Resolve multiple events. Returns count resolved."""
    if not event_ids:
        return 0
    placeholders = ",".join("?" * len(event_ids))
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            f"""UPDATE system_events SET resolved=1, resolved_by=?,
                resolved_at=datetime('now') WHERE event_id IN ({placeholders}) AND resolved=0""",
            (resolved_by, *event_ids))
        await conn.commit()
        return cur.rowcount


async def run_anomaly_scan() -> list:
    """Detect anomalies across the system. Returns list of findings."""
    findings = []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Tenants with expired trials still marked active
        cur = await conn.execute(
            """SELECT tenant_id, firm_name, trial_ends_at FROM tenants
               WHERE is_active=1 AND subscription_status='trial'
               AND trial_ends_at < datetime('now')""")
        for r in await cur.fetchall():
            findings.append({
                "type": "anomaly", "severity": "medium", "category": "data",
                "title": f"Expired trial still active: {r['firm_name']}",
                "detail": f"Tenant {r['tenant_id']} trial ended {r['trial_ends_at']} but is_active=1",
                "tenant_id": r["tenant_id"]
            })

        # 2. Agents without a valid tenant
        cur = await conn.execute(
            """SELECT a.agent_id, a.name, a.tenant_id FROM agents a
               LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
               WHERE t.tenant_id IS NULL AND a.tenant_id != 0""")
        for r in await cur.fetchall():
            findings.append({
                "type": "anomaly", "severity": "high", "category": "data",
                "title": f"Orphan agent: {r['name']} (ID {r['agent_id']})",
                "detail": f"Agent references tenant_id={r['tenant_id']} which doesn't exist",
                "tenant_id": r["tenant_id"]
            })

        # 3. Leads with invalid agent_id
        cur = await conn.execute(
            """SELECT l.lead_id, l.name, l.agent_id FROM leads l
               LEFT JOIN agents a ON l.agent_id = a.agent_id
               WHERE a.agent_id IS NULL""")
        orphan_leads = await cur.fetchall()
        if len(orphan_leads) > 0:
            findings.append({
                "type": "anomaly", "severity": "medium", "category": "data",
                "title": f"{len(orphan_leads)} leads with missing agent reference",
                "detail": f"Lead IDs: {[r['lead_id'] for r in orphan_leads[:20]]}"
            })

        # 4. Duplicate phone across tenants (potential fraud)
        cur = await conn.execute(
            """SELECT phone, COUNT(*) as cnt FROM tenants
               WHERE phone != '' GROUP BY phone HAVING cnt > 1""")
        for r in await cur.fetchall():
            findings.append({
                "type": "security", "severity": "high", "category": "auth",
                "title": f"Duplicate tenant phone: {r['phone']} ({r['cnt']}x)",
                "detail": f"Same phone registered for {r['cnt']} tenants — possible duplicate/fraud"
            })

        # 5. Tenants with no agents (broken onboarding)
        cur = await conn.execute(
            """SELECT t.tenant_id, t.firm_name FROM tenants t
               LEFT JOIN agents a ON t.tenant_id = a.tenant_id
               WHERE a.agent_id IS NULL AND t.is_active=1""")
        for r in await cur.fetchall():
            findings.append({
                "type": "anomaly", "severity": "medium", "category": "data",
                "title": f"Active tenant with no agents: {r['firm_name']}",
                "detail": f"Tenant {r['tenant_id']} is active but has zero agents",
                "tenant_id": r["tenant_id"]
            })

        # 6. Failed login spikes (from audit_log)
        cur = await conn.execute(
            """SELECT COUNT(*) as cnt FROM audit_log
               WHERE action LIKE '%fail%' AND created_at > datetime('now', '-1 hour')""")
        fail_cnt = (await cur.fetchone())['cnt']
        if fail_cnt > 10:
            findings.append({
                "type": "security", "severity": "critical", "category": "auth",
                "title": f"{fail_cnt} failed logins in last hour",
                "detail": "Possible brute-force attack"
            })

        # 7. Massive data creation (spam detection)
        cur = await conn.execute(
            """SELECT agent_id, COUNT(*) as cnt FROM leads
               WHERE created_at > datetime('now', '-1 hour')
               GROUP BY agent_id HAVING cnt > 50""")
        for r in await cur.fetchall():
            findings.append({
                "type": "security", "severity": "high", "category": "data",
                "title": f"Agent {r['agent_id']} created {r['cnt']} leads in last hour",
                "detail": "Possible spam or automated abuse"
            })

    return findings


# =============================================================================
#  AUTO-REMEDIATION ENGINE — Proactive system fixes
# =============================================================================

async def auto_fix_expired_trials() -> list:
    """Auto-deactivate tenants whose trial has expired. Returns list of fixed tenants."""
    fixed = []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT tenant_id, firm_name, trial_ends_at FROM tenants
               WHERE is_active=1 AND subscription_status='trial'
               AND trial_ends_at < datetime('now')""")
        rows = await cur.fetchall()
        for r in rows:
            await conn.execute(
                "UPDATE tenants SET is_active=0, subscription_status='expired' WHERE tenant_id=?",
                (r['tenant_id'],))
            fixed.append({"tenant_id": r['tenant_id'], "firm_name": r['firm_name'],
                          "trial_ends_at": r['trial_ends_at']})
        if fixed:
            await conn.commit()
    return fixed


async def auto_fix_orphan_agents() -> list:
    """Reassign or flag agents whose tenant is deactivated. Returns list of affected agents."""
    fixed = []
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            """SELECT a.agent_id, a.name, a.tenant_id, t.firm_name
               FROM agents a JOIN tenants t ON a.tenant_id = t.tenant_id
               WHERE t.is_active=0 AND a.is_active=1""")
        rows = await cur.fetchall()
        for r in rows:
            await conn.execute(
                "UPDATE agents SET is_active=0 WHERE agent_id=?",
                (r['agent_id'],))
            fixed.append({"agent_id": r['agent_id'], "name": r['name'],
                          "tenant_id": r['tenant_id'], "firm_name": r['firm_name']})
        if fixed:
            await conn.commit()
    return fixed


async def auto_fix_orphan_leads() -> int:
    """Delete leads with no valid agent. Returns count removed."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """DELETE FROM leads WHERE agent_id NOT IN (SELECT agent_id FROM agents)""")
        await conn.commit()
        return cur.rowcount


async def run_auto_remediation() -> dict:
    """Run all auto-remediation routines. Returns summary + logs events."""
    summary = {"expired_trials": [], "orphan_agents": [], "orphan_leads_removed": 0,
               "total_fixes": 0, "events_logged": 0}

    # 1. Fix expired trials
    expired = await auto_fix_expired_trials()
    summary["expired_trials"] = expired
    for t in expired:
        await add_system_event(
            event_type="anomaly", severity="medium", category="subscription",
            title=f"Auto-deactivated expired trial: {t['firm_name']}",
            detail=f"Tenant {t['tenant_id']} trial expired at {t['trial_ends_at']}. Auto-deactivated.",
            tenant_id=t['tenant_id'])
        summary["events_logged"] += 1

    # 2. Fix orphan agents
    orphans = await auto_fix_orphan_agents()
    summary["orphan_agents"] = orphans
    for a in orphans:
        await add_system_event(
            event_type="anomaly", severity="low", category="data",
            title=f"Auto-deactivated orphan agent: {a['name']}",
            detail=f"Agent {a['agent_id']} belonged to inactive tenant {a['tenant_id']} ({a['firm_name']}). Deactivated.",
            tenant_id=a['tenant_id'], agent_id=a['agent_id'])
        summary["events_logged"] += 1

    # 3. Fix orphan leads
    removed = await auto_fix_orphan_leads()
    summary["orphan_leads_removed"] = removed
    if removed > 0:
        await add_system_event(
            event_type="anomaly", severity="low", category="data",
            title=f"Auto-removed {removed} orphan leads",
            detail="Leads with no valid agent reference were cleaned up.")
        summary["events_logged"] += 1

    summary["total_fixes"] = len(expired) + len(orphans) + removed
    return summary


async def get_notification_digest() -> dict:
    """Get notification digest for SA bell icon: unresolved counts + recent critical events."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Unresolved count
        cur = await conn.execute("SELECT COUNT(*) as cnt FROM system_events WHERE resolved=0")
        unresolved = (await cur.fetchone())['cnt']
        # Critical/high unresolved
        cur = await conn.execute(
            """SELECT COUNT(*) as cnt FROM system_events
               WHERE resolved=0 AND severity IN ('critical', 'high')""")
        urgent = (await cur.fetchone())['cnt']
        # Latest 10 unresolved events
        cur = await conn.execute(
            """SELECT event_id, event_type, severity, title, created_at, category
               FROM system_events WHERE resolved=0
               ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1
                        WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC
               LIMIT 10""")
        recent = [dict(r) for r in await cur.fetchall()]
        return {"unresolved": unresolved, "urgent": urgent, "recent": recent}


# =============================================================================
#  NUDGE OPERATIONS
# =============================================================================

async def create_nudge(tenant_id: int, sender_agent_id: int,
                       target_agent_id: int, nudge_type: str,
                       message: str, lead_id: int = None) -> int:
    """Create a nudge record. Returns nudge_id."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO nudges
               (tenant_id, sender_agent_id, target_agent_id, nudge_type, lead_id, message)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (tenant_id, sender_agent_id, target_agent_id, nudge_type, lead_id, message))
        await conn.commit()
        return cursor.lastrowid


async def update_nudge_status(nudge_id: int, status: str) -> bool:
    """Update nudge status (sent, delivered, acted, dismissed)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        acted_clause = ", acted_at = datetime('now')" if status in ('acted', 'dismissed') else ""
        await conn.execute(
            f"UPDATE nudges SET status = ?{acted_clause} WHERE nudge_id = ?",
            (status, nudge_id))
        await conn.commit()
        return True


async def get_nudge_history(tenant_id: int, limit: int = 20) -> list:
    """Get recent nudge history for a tenant."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT n.*, a_sender.name as sender_name, a_target.name as target_name,
                      l.name as lead_name, l.phone as lead_phone
               FROM nudges n
               JOIN agents a_sender ON n.sender_agent_id = a_sender.agent_id
               JOIN agents a_target ON n.target_agent_id = a_target.agent_id
               LEFT JOIN leads l ON n.lead_id = l.lead_id
               WHERE n.tenant_id = ?
               ORDER BY n.created_at DESC LIMIT ?""",
            (tenant_id, limit))
        return [dict(r) for r in await cursor.fetchall()]


async def get_smart_nudge_signals(tenant_id: int) -> dict:
    """Detect nudge-worthy situations across the tenant.
    Returns categorized signals for the AI to prioritize."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # 1. Overdue follow-ups (past due by 2+ days)
        cursor = await conn.execute(
            """SELECT i.follow_up_date, l.name as lead_name, l.lead_id, l.phone, l.stage,
                      a.name as agent_name, a.agent_id, a.telegram_id
               FROM interactions i
               JOIN leads l ON i.lead_id = l.lead_id
               JOIN agents a ON i.agent_id = a.agent_id
               WHERE a.tenant_id=? AND i.follow_up_date IS NOT NULL
                 AND date(i.follow_up_date) <= date('now', '-2 days')
                 AND a.is_active=1
               ORDER BY i.follow_up_date ASC LIMIT 20""",
            (tenant_id,))
        overdue = [dict(r) for r in await cursor.fetchall()]

        # 2. Stale leads — no interaction in 7+ days, still in active stages
        cursor = await conn.execute(
            """SELECT l.lead_id, l.name as lead_name, l.phone, l.stage, l.updated_at,
                      a.name as agent_name, a.agent_id, a.telegram_id
               FROM leads l
               JOIN agents a ON l.agent_id = a.agent_id
               WHERE a.tenant_id=? AND a.is_active=1
                 AND l.stage IN ('new','contacted','interested','proposal_sent','negotiation')
                 AND date(l.updated_at) <= date('now', '-7 days')
               ORDER BY l.updated_at ASC LIMIT 20""",
            (tenant_id,))
        stale = [dict(r) for r in await cursor.fetchall()]

        # 3. Hot leads going cold — stage is interested/negotiation, no activity in 3+ days
        cursor = await conn.execute(
            """SELECT l.lead_id, l.name as lead_name, l.phone, l.stage, l.updated_at,
                      a.name as agent_name, a.agent_id, a.telegram_id
               FROM leads l
               JOIN agents a ON l.agent_id = a.agent_id
               WHERE a.tenant_id=? AND a.is_active=1
                 AND l.stage IN ('interested','negotiation','proposal_sent')
                 AND date(l.updated_at) <= date('now', '-3 days')
               ORDER BY l.updated_at ASC LIMIT 15""",
            (tenant_id,))
        cooling = [dict(r) for r in await cursor.fetchall()]

        # 4. Upcoming renewals with no recent interaction (within 15 days)
        cursor = await conn.execute(
            """SELECT l.name as lead_name, l.phone, p.renewal_date,
                      p.plan_name, p.premium, p.policy_id,
                      a.name as agent_name, a.agent_id, a.telegram_id,
                      l.lead_id
               FROM policies p
               JOIN leads l ON p.lead_id = l.lead_id
               JOIN agents a ON p.agent_id = a.agent_id
               WHERE a.tenant_id=? AND a.is_active=1
                 AND p.renewal_date IS NOT NULL
                 AND date(p.renewal_date) BETWEEN date('now') AND date('now', '+15 days')
               ORDER BY p.renewal_date ASC LIMIT 15""",
            (tenant_id,))
        renewals_due = [dict(r) for r in await cursor.fetchall()]

        # 5. New leads untouched for 24h+
        cursor = await conn.execute(
            """SELECT l.lead_id, l.name as lead_name, l.phone, l.stage, l.created_at,
                      a.name as agent_name, a.agent_id, a.telegram_id
               FROM leads l
               JOIN agents a ON l.agent_id = a.agent_id
               WHERE a.tenant_id=? AND a.is_active=1
                 AND l.stage = 'new'
                 AND datetime(l.created_at) <= datetime('now', '-1 day')
               ORDER BY l.created_at ASC LIMIT 15""",
            (tenant_id,))
        untouched_new = [dict(r) for r in await cursor.fetchall()]

        return {
            "overdue_followups": overdue,
            "stale_leads": stale,
            "cooling_hot_leads": cooling,
            "renewals_due": renewals_due,
            "untouched_new_leads": untouched_new,
        }


# =============================================================================
#  AI USAGE TRACKING & QUOTA
# =============================================================================

async def log_ai_usage(*, tenant_id: int = None, agent_id: int = None,
                       feature: str, tokens_in: int = 0, tokens_out: int = 0,
                       source: str = "web"):
    """Record an AI API call for cost tracking and quota enforcement."""
    # Estimate cost (Gemini 2.5 Flash pricing)
    cost = (tokens_in * 0.075 + tokens_out * 0.3) / 1_000_000
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """INSERT INTO ai_usage_log
               (tenant_id, agent_id, feature, tokens_in, tokens_out,
                cost_usd, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, agent_id, feature, tokens_in, tokens_out,
             cost, source))
        await conn.commit()


async def get_daily_ai_usage(agent_id: int) -> int:
    """Count AI calls made by an agent today."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """SELECT COUNT(*) FROM ai_usage_log
               WHERE agent_id = ? AND date(created_at) = date('now')""",
            (agent_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0


async def check_ai_quota(agent_id: int) -> dict:
    """Check if agent has remaining AI quota for today.
    Returns {'allowed': bool, 'used': int, 'limit': int, 'plan': str}."""
    agent = await get_agent_by_id(agent_id)
    if not agent:
        return {'allowed': False, 'used': 0, 'limit': 0, 'plan': 'none'}
    tenant = await get_tenant(agent.get('tenant_id', 0))
    plan = tenant.get('plan', 'trial') if tenant else 'trial'
    features = PLAN_FEATURES.get(plan, PLAN_FEATURES['trial'])
    daily_limit = features.get('ai_daily_quota', 30)
    used = await get_daily_ai_usage(agent_id)
    return {
        'allowed': used < daily_limit,
        'used': used,
        'limit': daily_limit,
        'plan': plan,
    }


async def get_tenant_ai_usage_summary(tenant_id: int, days: int = 30) -> dict:
    """Get aggregate AI usage for a tenant over N days."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT feature, COUNT(*) as calls,
                      SUM(tokens_in) as total_in, SUM(tokens_out) as total_out,
                      SUM(cost_usd) as total_cost
               FROM ai_usage_log
               WHERE tenant_id = ?
                 AND created_at >= datetime('now', ? || ' days')
               GROUP BY feature ORDER BY calls DESC""",
            (tenant_id, f"-{days}"))
        rows = [dict(r) for r in await cursor.fetchall()]
        total_cost = sum(r['total_cost'] or 0 for r in rows)
        total_calls = sum(r['calls'] or 0 for r in rows)
        return {
            'by_feature': rows,
            'total_calls': total_calls,
            'total_cost_usd': round(total_cost, 4),
            'period_days': days,
        }


async def get_global_ai_cost_summary(days: int = 30) -> dict:
    """Get platform-wide AI cost summary for super admin budget monitoring."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Daily cost trend
        cursor = await conn.execute(
            """SELECT date(created_at) as day, COUNT(*) as calls,
                      SUM(cost_usd) as cost
               FROM ai_usage_log
               WHERE created_at >= datetime('now', ? || ' days')
               GROUP BY date(created_at) ORDER BY day DESC LIMIT 30""",
            (f"-{days}",))
        daily = [dict(r) for r in await cursor.fetchall()]
        # Top tenants by cost
        cursor2 = await conn.execute(
            """SELECT tenant_id, COUNT(*) as calls, SUM(cost_usd) as cost
               FROM ai_usage_log
               WHERE created_at >= datetime('now', ? || ' days')
               GROUP BY tenant_id ORDER BY cost DESC LIMIT 10""",
            (f"-{days}",))
        top_tenants = [dict(r) for r in await cursor2.fetchall()]
        total_cost = sum(d['cost'] or 0 for d in daily)
        # Budget alert
        monthly_budget = float(os.getenv("AI_MONTHLY_BUDGET_USD", "15"))
        return {
            'daily_trend': daily,
            'top_tenants': top_tenants,
            'total_cost_usd': round(total_cost, 4),
            'budget_usd': monthly_budget,
            'budget_used_pct': round((total_cost / monthly_budget) * 100, 1) if monthly_budget > 0 else 0,
            'over_budget': total_cost > monthly_budget,
        }


# =============================================================================
#  PROACTIVE ASSISTANT — DB HELPERS
# =============================================================================

async def get_tomorrows_birthdays(agent_id: int = None) -> list:
    """Get leads with birthday tomorrow — for eve-of-birthday nudges."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        _base = """SELECT l.*, a.telegram_id as agent_telegram_id,
                          a.name as agent_name, a.lang,
                          t.firm_name, t.brand_tagline
                   FROM leads l
                   JOIN agents a ON l.agent_id = a.agent_id
                   LEFT JOIN tenants t ON a.tenant_id = t.tenant_id"""
        if agent_id:
            cursor = await conn.execute(
                f"""{_base}
                   WHERE l.agent_id=? AND l.dob IS NOT NULL
                     AND strftime('%m-%d', l.dob) = strftime('%m-%d', 'now', '+1 day')""",
                (agent_id,))
        else:
            cursor = await conn.execute(
                f"""{_base}
                   WHERE l.dob IS NOT NULL
                     AND strftime('%m-%d', l.dob) = strftime('%m-%d', 'now', '+1 day')""")
        return [dict(r) for r in await cursor.fetchall()]


async def get_tomorrows_anniversaries(agent_id: int = None) -> list:
    """Get leads with anniversary tomorrow."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        _base = """SELECT l.*, a.telegram_id as agent_telegram_id,
                          a.name as agent_name, a.lang,
                          t.firm_name
                   FROM leads l
                   JOIN agents a ON l.agent_id = a.agent_id
                   LEFT JOIN tenants t ON a.tenant_id = t.tenant_id"""
        if agent_id:
            cursor = await conn.execute(
                f"""{_base}
                   WHERE l.agent_id=? AND l.anniversary IS NOT NULL
                     AND strftime('%m-%d', l.anniversary) = strftime('%m-%d', 'now', '+1 day')""",
                (agent_id,))
        else:
            cursor = await conn.execute(
                f"""{_base}
                   WHERE l.anniversary IS NOT NULL
                     AND strftime('%m-%d', l.anniversary) = strftime('%m-%d', 'now', '+1 day')""")
        return [dict(r) for r in await cursor.fetchall()]


async def get_recently_won_leads(agent_id: int, days: int = 7) -> list:
    """Get leads closed_won in the last N days."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT l.*, a.name as agent_name
               FROM leads l JOIN agents a ON l.agent_id = a.agent_id
               WHERE l.agent_id=? AND l.stage='closed_won'
                 AND date(l.updated_at) >= date('now', ? || ' days')
               ORDER BY l.updated_at DESC""",
            (agent_id, f"-{days}"))
        return [dict(r) for r in await cursor.fetchall()]


async def get_agent_followups_with_time(agent_id: int) -> list:
    """Get today's + overdue follow-ups with richer lead info for proactive nudges."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT i.interaction_id, i.follow_up_date, i.type as type,
                      i.summary, i.created_at as scheduled_at,
                      l.lead_id, l.name as lead_name, l.phone as lead_phone,
                      l.stage, l.need_type, l.premium_budget
               FROM interactions i
               JOIN leads l ON i.lead_id = l.lead_id
               WHERE i.agent_id=? AND i.follow_up_date IS NOT NULL
                 AND date(i.follow_up_date) <= date('now')
               ORDER BY i.follow_up_date ASC LIMIT 30""",
            (agent_id,))
        return [dict(r) for r in await cursor.fetchall()]


async def get_agent_weekly_stats(agent_id: int) -> dict:
    """Get this week's performance stats for momentum nudges."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Deals won this week
        cursor = await conn.execute(
            """SELECT COUNT(*) as won, COALESCE(SUM(l.premium_budget), 0) as premium
               FROM leads l WHERE l.agent_id=? AND l.stage='closed_won'
                 AND date(l.updated_at) >= date('now', 'weekday 0', '-7 days')""",
            (agent_id,))
        won_row = dict(await cursor.fetchone())

        # New leads this week
        cursor = await conn.execute(
            """SELECT COUNT(*) as count FROM leads
               WHERE agent_id=? AND date(created_at) >= date('now', 'weekday 0', '-7 days')""",
            (agent_id,))
        new_leads = (await cursor.fetchone())[0]

        # Interactions this week
        cursor = await conn.execute(
            """SELECT COUNT(*) as count FROM interactions
               WHERE agent_id=? AND date(created_at) >= date('now', 'weekday 0', '-7 days')""",
            (agent_id,))
        interactions = (await cursor.fetchone())[0]

        # Follow-ups completed (interactions of type follow_up_scheduled where created this week)
        cursor = await conn.execute(
            """SELECT COUNT(*) as count FROM interactions
               WHERE agent_id=? AND type='follow_up_scheduled'
                 AND date(created_at) >= date('now', 'weekday 0', '-7 days')""",
            (agent_id,))
        followups_done = (await cursor.fetchone())[0]

        # Streak: consecutive days with at least 1 interaction
        cursor = await conn.execute(
            """SELECT DISTINCT date(created_at) as d FROM interactions
               WHERE agent_id=? ORDER BY d DESC LIMIT 30""",
            (agent_id,))
        dates = [r[0] for r in await cursor.fetchall()]
        streak = 0
        today = datetime.now().date()
        for i, d_str in enumerate(dates):
            expected = (today - timedelta(days=i)).isoformat()
            if d_str == expected:
                streak += 1
            else:
                break

        return {
            'deals_won': won_row['won'],
            'premium_won': won_row['premium'],
            'new_leads': new_leads,
            'interactions': interactions,
            'followups_done': followups_done,
            'streak_days': streak,
        }


async def get_stale_leads_for_agent(agent_id: int, days: int = 14) -> list:
    """Get leads with no interaction for N+ days (for stale lead alerts)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT l.lead_id, l.name, l.phone, l.stage, l.updated_at,
                      l.need_type, l.premium_budget
               FROM leads l
               WHERE l.agent_id=? AND l.stage NOT IN ('closed_won', 'closed_lost')
                 AND date(l.updated_at) <= date('now', ? || ' days')
               ORDER BY l.updated_at ASC LIMIT 20""",
            (agent_id, f"-{days}"))
        return [dict(r) for r in await cursor.fetchall()]


async def get_last_interaction_for_lead(lead_id: int) -> dict:
    """Get the most recent interaction for a lead."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM interactions
               WHERE lead_id=? ORDER BY created_at DESC LIMIT 1""",
            (lead_id,))
        row = await cursor.fetchone()
        return dict(row) if row else {}
