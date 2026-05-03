# SARATHI-AI BUSINESS — MASTER PROJECT CONTEXT

> **Purpose:** Single source of truth for project recovery. If a development session is lost, feed this document to a new session to restore full context instantly.
>
> **Last Updated:** May 2, 2026
>
> **Maintainer:** Update this doc after every significant change.

---

## TABLE OF CONTENTS

1. [Project Identity](#1-project-identity)
2. [Tech Stack & Infrastructure](#2-tech-stack--infrastructure)
3. [File Inventory (16 Python + 17 HTML)](#3-file-inventory)
4. [Database Schema (25 Tables)](#4-database-schema)
5. [API Endpoints (200+)](#5-api-endpoints)
6. [Telegram Bot Architecture](#6-telegram-bot-architecture)
7. [Voice System (24 Intents + Context-Aware AI)](#7-voice-system)
8. [Calculator System (12 Calculators)](#8-calculator-system)
9. [WhatsApp Integration](#9-whatsapp-integration)
10. [AI Features (Gemini 2.5 Flash)](#10-ai-features)
11. [Payment System (Razorpay)](#11-payment-system)
12. [Multi-Tenant Architecture](#12-multi-tenant-architecture)
13. [Authentication & Authorization](#13-authentication--authorization)
14. [Background Scheduler & Proactive AI](#14-background-scheduler--proactive-ai)
15. [SEBI Compliance & DPDP Consent](#15-sebi-compliance--dpdp-consent)
16. [Affiliate & Partner Program](#16-affiliate--partner-program)
17. [Support Ticket System](#17-support-ticket-system)
18. [Resilience & Observability](#18-resilience--observability)
19. [Deployment](#19-deployment)
20. [Environment Variables](#20-environment-variables)
21. [Development Setup](#21-development-setup)
22. [Security Measures](#22-security-measures)
23. [Known Issues & Limitations](#23-known-issues--limitations)
24. [Build Log — All Features Implemented](#24-build-log)
25. [Critical Code Patterns](#25-critical-code-patterns)
26. [Static Web Pages](#26-static-web-pages)
27. [i18n — Bilingual System](#27-i18n--bilingual-system)
28. [Recent Work Log (March 22–April 5, 2026)](#28-recent-work-log)
29. [PWA (Progressive Web App)](#29-pwa)
30. [Production Infrastructure (Oracle Cloud)](#30-production-infrastructure)
31. [Data Protection & Backward Compatibility](#31-data-protection)

---

## 1. PROJECT IDENTITY

**Product:** Sarathi-AI Business Technologies
**Type:** Voice-First CRM SaaS for Indian Insurance/Financial Advisors
**USP:** Advisors manage leads, policies, and client communication entirely through Telegram voice notes + AI in Hindi/English
**Target Market:** Indian insurance agents, LIC advisors, mutual fund distributors

**Core Value Prop:**
- Voice-first: Send a voice note → AI creates lead, logs meeting, sets follow-up
- 12 financial calculators with branded PDF reports + WhatsApp sharing
- Proactive AI Assistant: daily briefings, smart nudges, deal celebrations, stale lead alerts
- SEBI/DPDP compliance: regulatory credentials on PDFs, consent tracking, data protection
- Automated birthday/anniversary/renewal greetings
- Multi-tenant: Each firm gets their own branded experience
- Bilingual: Full Hindi + English support throughout (UI, bot, PDFs, reminders, web pages)

---

## 2. TECH STACK & INFRASTRUCTURE

| Component | Technology |
|-----------|-----------|
| **Language** | Python 3.12 |
| **Web Framework** | FastAPI + Uvicorn |
| **Bot Framework** | python-telegram-bot v21.11.1 |
| **Database** | SQLite (aiosqlite, async) |
| **AI** | Google Gemini 2.5 Flash |
| **Payments** | Razorpay (orders + subscriptions) |
| **WhatsApp** | Meta Cloud API (Graph v21.0) |
| **Email** | SMTP (Gmail App Passwords, "Send mail as" info@sarathi-ai.com via Cloudflare Email Routing) |
| **PDF** | HTML → Browser PDF (custom branded templates) |
| **Cloud Storage** | Google Drive OAuth2 |
| **Rate Limiting** | slowapi (200/min default, per-endpoint overrides) |
| **Deployment** | Nginx + systemd on Ubuntu 24.04, Oracle Cloud VM |
| **Production** | sarathi-ai.com (Cloudflare DNS → 140.238.246.0) |
| **Tunnel (Dev)** | ngrok (free tier, static domain) |
| **Hosting (Dev)** | Local Windows, port 8001 |

**Dev Environment:**
- Python: `C:\Users\imdus\AppData\Local\Programs\Python\Python312\python.exe`
- Server port: 8001 (from `biz.env: SERVER_PORT=8001`)
- ngrok domain: `nonseparable-undarned-geoffrey.ngrok-free.dev` → port 8001
- Start server: `python sarathi_biz.py`
- Start ngrok: `ngrok http 8001 --domain=nonseparable-undarned-geoffrey.ngrok-free.dev`

---

## 3. FILE INVENTORY

### Python Modules (~31,900 LOC total)

| File | Lines | Purpose |
|------|-------|---------|
| `biz_bot.py` | ~12,889 | Telegram bot: 61 handlers, voice system (24 intents), 12 calculators, context-aware voice AI, proactive callbacks, 15 FSM conversations |
| `sarathi_biz.py` | ~6,497 | FastAPI entry point: 200+ API routes, 5 middleware layers, startup sequence, health monitor endpoints |
| `biz_database.py` | ~4,381 | Async SQLite: 28 tables, 100+ query functions, SEBI/DPDP, anomaly scan, auto-remediation, health monitor tables |
| `biz_i18n.py` | ~1,866 | Bilingual strings (150+ keys, EN + HI) for Telegram messages |
| `biz_pdf.py` | ~1,310 | 12 HTML report generators + 181 i18n keys (EN + HI) |
| `biz_reminders.py` | ~1,290 | Background scheduler: 7 daily tasks + 6 proactive AI functions + 15-min health monitor + 3AM cleanup |
| `biz_calculators.py` | ~1,116 | 12 calculator functions + 12 @dataclass results + 9 format functions |
| `biz_ai.py` | ~943 | Gemini AI: 8 features (scoring, pitch, recommendations, etc.) |
| `biz_payments.py` | ~872 | Razorpay: orders, subscriptions, webhooks |
| `biz_whatsapp.py` | ~718 | WhatsApp Cloud API: send/receive, wa.me fallback |
| `biz_auth.py` | ~573 | JWT + Email OTP + Google Sign-In + CSRF authentication, role-based access |
| `biz_health_monitor.py` | ~479 | Tier 2 Health Monitor: 11 checks (server, DB, email, bots, queue, disk, data integrity, payments, auth), auto-fix, email alerts |
| `biz_resilience.py` | ~471 | Retry decorator, message queue, health check |
| `biz_email.py` | ~436 | SMTP email: 16 email functions (OTP, welcome, receipts, health alerts, trials). Deliverability: Message-ID, MIME-Version, List-Unsubscribe, X-Mailer headers + auto plain-text fallback |
| `biz_campaigns.py` | ~342 | Bulk messaging: WhatsApp + Email campaigns |
| `biz_gdrive.py` | ~327 | Google Drive OAuth2 file management |
| `biz_bot_manager.py` | ~317 | Multi-tenant bot lifecycle management |
| `biz_sms.py` | ~69 | SMS stub module (placeholder for future SMS integration) |

### Static HTML Pages (~20,150 LOC total, 17 files)

| File | Lines | Purpose |
|------|-------|---------|
| `dashboard.html` | 3,228 | Agent KPI dashboard with charts, pipeline, CSRF |
| `calculators.html` | 2,486 | 12 interactive web calculators with Chart.js |
| `index.html` | ~2,890 | Homepage: 2-part hero (big bot demo screen + brand row), pricing, features, signup, i18n |
| `superadmin.html` | ~882 | Super Admin Cockpit: mobile-first, bottom nav, 6 panels (Home, Firms, Alerts, Support, Monitor, More), customer health diagnostics, live health monitor dashboard |
| `demo.html` | 1,829 | Interactive demo with 6 device frames |
| `telegram-guide.html` | 1,537 | Telegram setup guide with i18n |
| `partner.html` | 1,089 | Affiliate partner program |
| `getting-started.html` | 695 | Setup guide |
| `admin.html` | 633 | Admin tenant management panel |
| `help.html` | 584 | FAQs with i18n |
| `support.html` | 480 | Support ticket submission |
| `onboarding.html` | 469 | 4-step tenant setup wizard |
| `terms.html` | 288 | Terms of service |
| `invite.html` | 231 | Team member invitation |
| `privacy.html` | 203 | Privacy policy |

### Other Files

| File | Purpose |
|------|---------|
| `biz.env` | Environment variables (secrets, API keys, config) |
| `biz_requirements.txt` | Python dependencies (13 packages) |
| `Dockerfile` | Container build (Python 3.12-slim) |
| `docker-compose.yml` | Container orchestration |
| `deploy/` | Server setup, nginx, systemd, backup scripts |
| `static/manifest.json` | PWA web app manifest (standalone, 5 icons) |
| `static/sw.js` | Service Worker v14 (network-first HTML, cache-first static) |
| `static/app-icon-512.png` | PWA maskable icon 512x512 (white bg, safe zone) |
| `static/app-icon-192.png` | PWA maskable icon 192x192 (white bg, safe zone) |
| `static/dark-mode.css` | Dark mode theme CSS |
| `static/dark-mode.js` | Dark mode toggle JS |
| `static/logos/` | Brand logo assets |
| `static/audio/` | Help audio content |
| `static/demo-screenshots/` | Demo images |
| `static/superadmin_backup.html` | Original SA panel backup (2,624 lines) |
| `psutil` | Python package installed on production for CPU/memory/disk monitoring |

---

## 4. DATABASE SCHEMA

**Engine:** SQLite via aiosqlite (async), file: `sarathi_biz.db`

### Core CRM Tables (28 tables total)

```
tenants
├── tenant_id (PK, auto)
├── firm_name, owner_phone, owner_email
├── plan (individual/team/enterprise)
├── subscription_status (trial/active/expired/cancelled)
├── trial_ends_at, subscription_ends_at
├── max_agents (1/5/25)
├── brand_* (colors, tagline, domain, cta)
├── wa_phone_id, wa_access_token (per-tenant WhatsApp)
├── bot_token (custom Telegram bot)
├── irdai_license, irdai_verified (none/pending/verified)
├── sebi_ria_code, amfi_reg, compliance_disclaimer
├── lang (en/hi)
└── created_at, updated_at

agents
├── agent_id (PK, auto)
├── tenant_id (FK → tenants)
├── telegram_id (UNIQUE)
├── name, phone, email
├── role (owner/agent)
├── lang (en/hi), is_active
├── onboarding_step
├── profile_photo
├── arn_number, euin, irdai_license
├── last_active_at
└── created_at

leads
├── lead_id (PK, auto)
├── agent_id (FK → agents)
├── name, phone, whatsapp, email
├── dob, anniversary, city, occupation
├── monthly_income, family_size
├── need_type (health/term/endowment/ulip/child/retirement/motor/investment/nps/general)
├── stage (prospect/contacted/pitched/proposal_sent/negotiation/closed_won/closed_lost)
├── source, notes, sum_insured, premium_budget
├── dpdp_consent (0/1), dpdp_consent_date
└── created_at, updated_at

policies
├── policy_id (PK, auto)
├── lead_id (FK → leads), agent_id (FK → agents)
├── policy_number, insurer, plan_name
├── policy_type, sum_insured, premium, premium_mode
├── start_date, end_date, renewal_date
├── status (active/lapsed/surrendered/matured/claim)
├── commission, notes
└── created_at

interactions
├── interaction_id (PK, auto)
├── lead_id (FK → leads), agent_id (FK → agents)
├── type (call/meeting/email/whatsapp/note/follow_up_scheduled/pitch/claim)  ← Column is `type` NOT `interaction_type`
├── channel, summary, follow_up_date, follow_up_time
├── follow_up_status (pending/done), created_by_agent_id (FK → agents)
├── assigned_to_agent_id (FK → agents) — task assignee
└── created_at
⚠️ NOTE: The Python function `log_interaction(interaction_type=...)` maps to column `type`. Raw SQL must use `i.type`, NOT `i.interaction_type`.
```

### Feature Tables

```
reminders (reminder_id, agent_id, lead_id, policy_id, type, due_date, message, status, channel)
greetings_log (greeting_id, lead_id, agent_id, type, channel, sent_at)
calculator_sessions (session_id, agent_id, lead_id, calc_type, inputs JSON, result JSON, pdf_path)
daily_summary (summary_id, agent_id, summary_date, new_leads, deals_closed, commission)
voice_logs (voice_id, agent_id, lead_id, transcript, extracted_data, audio_duration)
abuse_warnings (id, agent_id, warning_count, blocked_until, last_text)
claims (claim_id, agent_id, lead_id, policy_id, claim_type, status, hospital, confirmation_docs)
nudges (nudge_id, tenant_id, sender_agent_id, target_agent_id, nudge_type, lead_id, message, status)
```

### Admin & Compliance Tables

```
audit_log (log_id, tenant_id, agent_id, action, detail, ip_address, role, created_at)
support_tickets (ticket_id, tenant_id, agent_id, subject, status, category, priority)
ticket_messages (message_id, ticket_id, sender_type, message)
otp_store (phone PK, otp_hash, expires_at, attempts)
pending_plan_changes (change_id, tenant_id UNIQUE, current_plan, new_plan, effective_after)
system_events (event_id, event_type, severity, category, title, resolved, auto_fixed)
ai_usage_log (id, tenant_id, agent_id, feature, tokens_in, tokens_out, cost_usd)
invite_codes (code PK, tenant_id, created_by, max_uses, used_count, expires_at)
```

### Affiliate Tables

```
affiliates (affiliate_id, phone, referral_code UNIQUE, commission_pct, status, payout_upi, payout_bank_*)
affiliate_referrals (referral_id, affiliate_id, tenant_id, status, cooling_ends_at, converted_at)
affiliate_payouts (payout_id, affiliate_id, amount, method, status, reference_id)
affiliate_tickets (ticket_id, affiliate_id, subject, status, category, priority)
affiliate_ticket_messages (message_id, ticket_id, sender_type, message)
```

### Health Monitor Tables

```
health_checks (check_id, run_id, check_name, status, message, auto_fixed, details JSON, created_at)
health_alerts (alert_id, run_id, alert_type, message, acknowledged, created_at)
```

### Other Tables

```
lead_notes (note_id, lead_id, agent_id, note_text, created_at)
otp_store (phone PK, otp_hash, expires_at, attempts)
pending_plan_changes (change_id, tenant_id UNIQUE, current_plan, new_plan, effective_after)
```

---

## 5. API ENDPOINTS (200+)

### Authentication (13)
```
POST /api/auth/csrf-token           — Get CSRF token (per-session, 1h TTL)
POST /api/auth/send-otp             — Send OTP to phone (rate: 5/min) [legacy]
POST /api/auth/verify-otp           — Verify OTP → JWT tokens (rate: 10/min) [legacy]
POST /api/auth/send-email-otp       — Send Email OTP for EXISTING users (rate: 5/min)
POST /api/auth/verify-email-otp     — Verify Email OTP → JWT tokens (rate: 10/min)
POST /api/auth/send-signup-otp      — Send Email OTP for NEW signups (no account required, 409 if email exists) [April 2026]
POST /api/auth/verify-signup-otp    — Verify signup OTP only (returns {verified, email}, does NOT create account) [April 2026]
POST /api/auth/google-login         — Google Sign-In → JWT tokens (rate: 10/min)
POST /api/auth/refresh              — Refresh access token (rate: 20/min)
GET  /api/auth/me                   — Current user info with plan features
POST /api/auth/logout               — Clear session
GET  /api/auth/telegram-login       — Telegram OAuth redirect (firm_name escaped for JS injection safety)
GET  /api/auth/google-client-id     — Return Google OAuth client ID for frontend
```

### Super Admin (40+)
```
# Auth
GET  /superadmin                    — SA dashboard page
POST /api/sa/login                  — Phone + password login (rate: 10/min)
POST /api/sa/logout                 — Clear SA session
GET  /api/sa/me                     — SA auth status

# Dashboard
GET  /api/sa/dashboard              — KPIs: tenants, MRR, signups, leads, funnel

# Tenant CRUD
GET  /api/sa/tenants                — List all (enriched: agent/lead/policy counts)
GET  /api/sa/tenant/{id}            — Full tenant detail
POST /api/sa/create-firm            — Create firm manually
PUT  /api/sa/tenant/{id}            — Edit tenant details
DELETE /api/sa/tenant/{id}          — Cascading delete (rate: 3/min)

# Tenant Lifecycle
POST /api/sa/tenant/{id}/extend     — Extend trial
POST /api/sa/tenant/{id}/activate   — Activate subscription
POST /api/sa/tenant/{id}/deactivate — Deactivate tenant
POST /api/sa/tenant/{id}/plan       — Change plan
POST /api/sa/tenant/{id}/force-plan-change
POST /api/sa/tenant/{id}/schedule-plan-change
DELETE /api/sa/tenant/{id}/pending-plan-change

# Agent Management
PUT  /api/sa/agent/{id}             — Edit agent
POST /api/sa/agent/{id}/toggle      — Toggle active/inactive
GET  /api/sa/agents/activity        — Agent activity monitoring

# Feature Management
GET  /api/sa/tenant/{id}/features   — Get feature flags
PUT  /api/sa/tenant/{id}/features   — Update feature overrides

# Audit & Monitoring
GET  /api/sa/audit                  — Query audit log
GET  /api/sa/tenant/{id}/errors     — Tenant error logs
GET  /api/sa/duplicates             — Duplicate report

# System Events & Anomalies
GET  /api/sa/events                 — System events (filterable)
POST /api/sa/events/{id}/resolve    — Resolve event
POST /api/sa/events/bulk-resolve    — Bulk resolve
POST /api/sa/anomaly-scan           — Run anomaly scan (7 categories)
POST /api/sa/auto-remediate         — Auto-fix expired/orphaned
POST /api/sa/ai-classify-events     — AI classify unresolved events
GET  /api/sa/notifications          — SA notification digest

# Revenue & System
GET  /api/sa/revenue                — Revenue by plan, MRR/ARR, trends
GET  /api/sa/system-status          — Health, DB stats, disk

# Bots
GET  /api/sa/bots                   — Bot status overview
POST /api/sa/tenant/{id}/bot/restart|stop
POST /api/sa/restart-server         — Full server restart

# Impersonation
POST /api/sa/tenant/{id}/impersonate — 1h impersonation token

# Data Export
GET  /api/sa/export/tenants|leads|affiliates

# Bulk Operations
POST /api/sa/tenants/bulk-activate|bulk-deactivate|bulk-delete|bulk-plan

# Support (SA view)
GET  /api/sa/tickets                — All tickets
GET  /api/sa/tickets/stats          — Statistics
GET  /api/sa/tickets/{id}           — Detail
PUT  /api/sa/tickets/{id}           — Update
POST /api/sa/tickets/{id}/reply     — SA reply

# AI Costs
GET  /api/sa/ai-costs               — Global AI cost summary

# Health Monitor (Tier 2)
GET  /api/sa/health-monitor         — Latest health check results
GET  /api/sa/health-monitor/history — Check history (default: last 20)
GET  /api/sa/health-monitor/alerts  — Alert history (default: last 50)
POST /api/sa/health-monitor/run     — Trigger manual health check
```

### Signup & Onboarding (7)
```
POST /api/signup                    — New firm registration (rate: 5/min)
POST /api/onboarding/whatsapp       — Configure WA credentials (owner only)
POST /api/onboarding/telegram-bot   — Save tenant bot token (owner only)
POST /api/onboarding/branding       — Save branding + compliance credentials
GET  /api/onboarding/status         — Onboarding progress
GET  /api/wa/setup-guide            — WA setup instructions
POST /api/wa/verify-credentials     — Verify WA creds
```

### Payments & Subscriptions (13)
```
POST /api/payments/create-order         — Razorpay order (owner only)
POST /api/payments/verify               — Verify payment (owner only)
POST /api/payments/create-subscription  — Recurring sub (owner only)
GET  /api/payments/status               — Subscription status
POST /api/payments/webhook              — Razorpay webhook
GET  /api/payments/plans                — Available plans

POST /api/subscription/cancel           — Cancel (CSRF required)
POST /api/subscription/schedule-change  — Schedule plan change (CSRF)
GET  /api/subscription/pending-change
DELETE /api/subscription/pending-change
POST /api/subscription/upgrade          — Immediate upgrade (owner)
POST /api/subscription/downgrade        — Schedule downgrade (owner)
GET  /api/subscription/status
```

### Calculators (9 GET)
```
GET /api/calc/inflation|hlv|retirement|emi|health|sip|mfsip|ulip|nps
```

### PDF Reports (9 GET)
```
GET /api/report/inflation|hlv|retirement|emi|health|sip|mfsip|ulip|nps
    — Generate branded HTML report (agent photo, compliance credentials, lang)
```

### Dashboard & AI Usage
```
GET /api/dashboard          — Agent KPI data (JWT required)
GET /api/ai-usage           — AI usage summary for tenant
```

### WhatsApp (5)
```
POST /api/wa/send           — Send message (rate: 30/min)
POST /api/wa/share-calc     — Share calc results (rate: 20/min)
POST /api/wa/greeting       — Send greeting (rate: 20/min)
GET  /api/wa/status         — WA config status
GET|POST /webhook           — WA incoming webhook
```

### Google Drive (6)
```
GET  /api/gdrive/connect|callback|status|files
POST /api/gdrive/disconnect|upload-report
```

### AI Features (9)
```
GET  /api/ai/verify
POST /api/ai/score-lead/{id}|generate-pitch/{id}|suggest-followup/{id}
POST /api/ai/recommend-policies/{id}|generate-template|handle-objection
POST /api/ai/renewal-intelligence/{id}|ask
```

### Nudge System (6)
```
POST /api/nudge|/api/nudge/broadcast|preview|bulk
GET  /api/nudge/history|suggestions
```

### Campaigns (7)
```
POST /api/campaigns          — Create (Team+ only)
GET  /api/campaigns|/{id}|/{id}/recipients|/types
POST /api/campaigns/{id}/send
DELETE /api/campaigns/{id}
```

### Profile & Agents (12)
```
GET|PUT /api/profile
POST|DELETE /api/profile/photo
GET  /api/agents
PUT  /api/agents/{id}
POST /api/agents/{id}/deactivate|reactivate
POST /api/agents/transfer|/{id}/remove
POST|DELETE /api/agent/{id}/photo
```

### Leads & Policies (11)
```
POST /api/admin/leads           — Add lead
PUT  /api/admin/leads/{id}|/{id}/stage
DELETE /api/admin/leads/{id}
POST /api/admin/leads/{id}/reassign
POST /api/import/leads          — Bulk CSV/JSON

GET  /api/admin/policies
POST /api/admin/policies
PUT  /api/admin/policies/{id}
DELETE /api/admin/policies/{id}
POST /api/admin/policies/extract — AI extract from text/image
```

### Invites (3)
```
POST /api/admin/invite|/api/invite/accept
GET  /api/invite/validate/{code}
```

### Support Tickets (4 customer-facing)
```
POST /api/support/tickets|/{id}/reply
GET  /api/support/tickets|/{id}
```

### Affiliates (22 — see Section 16)

### Message Queue (3)
```
GET  /api/admin/message-queue/stats|dead-letters
POST /api/admin/message-queue/{id}/retry
```

### Static Pages (17)
```
GET / | /onboarding | /admin | /superadmin | /dashboard | /calculators
    /help | /privacy | /terms | /getting-started | /demo | /support
    /partner | /telegram-guide | /invite
```

---

## 6. TELEGRAM BOT ARCHITECTURE

### Entry Point
`sarathi_biz.py` → `biz_bot_manager.py` → `biz_bot.build_bot()` → `Application`

### 61 Registered Handlers

**Command Handlers:**
```
/start, /addlead, /pipeline, /leads, /followup, /convert, /policy
/calc, /renewals, /dashboard, /wa, /wacalc, /wadash, /greet
/lead, /help, /plans, /claim, /claims, /claimstatus, /ai
/team, /settings, /partner, /lang, /createbot, /whatsapp_setup
/weblogin, /editprofile, /editagent, /editlead, /sa, /refresh
```

### 15 Conversation Handlers (FSM)
```
ONBOARD_*    (7 states)  — Firm setup wizard
LEAD_*       (8 states)  — Add lead flow
FOLLOWUP_*   (4 states)  — Schedule follow-up
CONVERT_*    (2 states)  — Stage conversion
POLICY_*     (8 states)  — Add policy
CALC_*       (3 states)  — Calculator flow (12 types)
WA_*         (2 states)  — WhatsApp send
GREET_*      (2 states)  — Greeting flow
SEARCH_*     (1 state)   — Lead search
EDITPROFILE  (multiple)  — Profile editing
EDITLEAD     (multiple)  — Lead editing
CLAIM        (multiple)  — Insurance claims
TEAM         (multiple)  — Team management
EDITAGENT    (multiple)  — Agent editing (SA)
```

### Callback Query Handlers
```
_menu_inline_callback     — Main menu buttons
_nudge_callback           — Engagement nudges
_team_callback            — Team management
_ai_callback              — AI tools
_sa_callback              — Super admin
_payment_callback         — Payment flow (pay_*, cancel_sub, pay_confirm_cancel, pay_back)
_voice_callback           — Voice confirm/edit/cancel
_voice_fill_callback      — Voice fill missing fields
_voice_cancel_callback    — Cancel multi-turn (voice_cancel)
_vc_choice_callback       — Smart fallback choice (vc_go_*, vc_dismiss)
_vcalc_callback           — Voice calculator (vcalc_*, vcparam_*)
_conv_retry_callback      — Retry failed conversation
_proactive_callback       — Proactive AI nudge buttons
_celebration_callback     — Deal celebration + greeting buttons
```

### Message Handlers
```
Voice messages    → _voice_to_action (Gemini transcription + intent)
CSV files         → _csv_import_handler (bulk lead import)
Text (catch-all)  → _global_catch_all (Just Talk mode + multi-turn)
```

---

## 7. VOICE SYSTEM (24 Intents + Context-Aware AI)

### Processing Pipeline
```
User sends voice note
  → Telegram downloads .ogg file
  → Build dynamic context block (last lead, last calc, recent actions)
  → Gemini 2.5 Flash transcribes + detects intent + confidence scoring
  → Returns JSON: {transcript, intent, language, confidence, extracted_data}
  → If confidence == 'low': show smart choice buttons
  → If confidence == 'high'/'medium': route to intent handler
  → Show result with confirm/edit/cancel buttons
  → Track action in voice_history for next context
```

### All 24 Intents

| # | Intent | Handler |
|---|--------|---------|
| 1 | `create_lead` | `_voice_handle_create_lead` → preview + confirm/edit/cancel |
| 2 | `log_meeting` | `_voice_handle_log_meeting` |
| 3 | `update_stage` | `_voice_handle_update_stage` |
| 4 | `create_reminder` | `_voice_handle_create_reminder` |
| 5 | `add_note` | `_voice_handle_add_note` |
| 6 | `list_leads` | `_voice_handle_list_leads` |
| 7 | `show_pipeline` | `_voice_handle_show_pipeline` |
| 8 | `show_dashboard` | `_voice_handle_show_dashboard` |
| 9 | `show_renewals` | `_voice_handle_show_renewals` |
| 10 | `show_today` | `_voice_handle_show_today` |
| 11 | `setup_followup` | `_voice_handle_setup_followup` |
| 12 | `send_whatsapp` | `_voice_handle_send_whatsapp` |
| 13 | `send_greeting` | `_voice_handle_send_greeting` |
| 14 | `edit_lead` | `_voice_handle_edit_lead` |
| 15 | `ask_ai` | `_voice_handle_ask_ai` |
| 16 | `ai_lead_score` | `_voice_handle_ai_lead_score` |
| 17 | `ai_pitch` | `_voice_handle_ai_tool(pitch)` |
| 18 | `ai_followup_suggest` | `_voice_handle_ai_tool(followup)` |
| 19 | `ai_recommend` | `_voice_handle_ai_tool(recommend)` |
| 20 | `open_calculator` | `_voice_handle_open_calculator` |
| 21 | `select_calculator` | `_voice_handle_select_calculator` |
| 22 | `calc_compute` | `_voice_handle_calc_compute` |
| 23 | `send_calc_result` | `_voice_handle_send_calc_result` |
| 24 | `general` | `_voice_handle_general` |

### Voice Prompt Structure
- **`_VOICE_PROMPT`** — 24 intents, Gemini 2.5 Flash, JSON output
- **`_JUST_TALK_PROMPT`** — 11 intents (text-based natural language via `_global_catch_all`)
- **Languages:** Hindi, English, Hinglish — all handled natively
- **Date parsing:** Relative dates (kal, tomorrow, agle hafte, next Monday)
- **Number parsing:** Hindi words (das hazaar → 10000), lakh/crore multipliers

### Context-Aware Voice System

**Context Tracking (`_track_voice_context()`):**
- Called after every successful voice action
- Stores `voice_history` (last 5 actions with timestamps)
- Updates `last_lead` with `{lead_id, name, ts}`
- Tracks `calc_type` for calculator actions

**Context Injection (`_build_voice_context_block()`):**
- Built dynamically before every Gemini call
- Injects: last lead referenced, last calculator, recent actions
- 10-minute expiry on context
- Enables pronoun resolution: "uska phone update karo" → resolves to last lead

**Confidence Scoring:**
- Gemini returns `"confidence": "high" | "medium" | "low"`
- High/Medium → direct route; Low → smart choice buttons (AI guess + related intents)

**Multi-Turn Voice Context:**
- Stored in `context.user_data['voice_context']`
- Used for calculator step-by-step param collection
- **5-minute expiry** — auto-cleared if stale
- **Intent override** — new unrelated intent clears stale context
- **Cancel button** — ❌ Cancel on all multi-turn prompts

---

## 8. CALCULATOR SYSTEM (12 CALCULATORS)

### Calculator Functions (biz_calculators.py — 1,116 lines)

| # | Calculator | Function | @dataclass Result |
|---|-----------|----------|-------------------|
| 1 | Inflation Eraser | `inflation_eraser()` | `InflationResult` |
| 2 | Human Life Value | `hlv_calculator()` | `HLVResult` |
| 3 | Retirement Planner | `retirement_planner()` | `RetirementResult` |
| 4 | Premium EMI | `emi_calculator()` | `EMIResult` |
| 5 | Health Cover | `health_cover_estimator()` | `HealthCoverResult` |
| 6 | SIP vs Lumpsum | `sip_vs_lumpsum()` | `SIPvLumpsumResult` |
| 7 | MF SIP Goal Planner | `mf_sip_planner()` | `MFSIPResult` |
| 8 | ULIP vs Mutual Fund | `ulip_vs_mf()` | `ULIPvsMFResult` |
| 9 | NPS Pension Planner | `nps_planner()` | `NPSResult` |
| 10 | Step-Up SIP | `stepup_sip_planner()` | `StepUpSIPResult` |
| 11 | SWP (Systematic Withdrawal) | `swp_calculator()` | `SWPResult` |
| 12 | Delay Cost Analyzer | `delay_cost_calculator()` | `DelayCostResult` |

### Integration Points (per calculator)

| Layer | Component | Location |
|-------|-----------|----------|
| Math engine | @dataclass + calc function | `biz_calculators.py` |
| Telegram format | `format_*_result()` (9 explicit + 3 inline) | `biz_calculators.py` / `biz_bot.py` |
| PDF report | `generate_*_html()` (12) with 181 i18n keys | `biz_pdf.py` |
| Bot interactive | `_CALC_PARAMS` (12 entries) + `_calc_show_result()` | `biz_bot.py` |
| Bot gen_map | 12 entries: calc_type → PDF generator | `biz_bot.py` |
| Voice dispatch | `_voice_calc_compute_and_show()` (12 elif) | `biz_bot.py` |
| Voice gen_map | 12 entries | `biz_bot.py` |
| Voice aliases | 27 aliases (Hindi + English → canonical type) | `biz_bot.py` |
| Voice format | `_format_calc_result_text()` (12 types, HI/EN) | `biz_bot.py` |
| Web UI | 12 tabs + 12 JS `calcXxx()` + Chart.js | `calculators.html` |
| Web i18n | `_CT` object (100+ keys, EN/HI) | `calculators.html` |

### Voice Calculator Flow
```
Voice: "Calculate SIP 10000 monthly 20 years 12% return"
  → Gemini: {intent: calc_compute, calc_type: sip, calc_params: {...}}
  → All params present? → compute + show result + PDF + action buttons
  → Missing params? → multi-turn: store context → quick-select buttons
  → When all filled → compute and show
```

### _CALC_PARAMS Registry
```python
{
    'title': 'EMI Calculator', 'title_hi': 'EMI कैलकुलेटर',
    'params': [
        {'key': 'premium', 'prompt': 'Annual premium (₹)', 'prompt_hi': '...',
         'min': 1000, 'max': 50000000, 'buttons': [10000, 20000, 50000]},
        {'key': 'family', 'type': 'choice', 'allowed': ['1A', '2A', '2A+1C', ...]},
    ]
}
```

### Callback Patterns
```
vcalc_menu                    → Show 12-calculator inline menu
vcalc_{type}                  → Start interactive calculator
vcalc_send_{type}_{lead_id}   → Send result to lead via WhatsApp
vcparam_{value}               → Quick-select value during multi-turn
```

---

## 9. WHATSAPP INTEGRATION

### Architecture
```
Outgoing: Bot → wa.send_text/send_calc_report → Meta Graph API
  → If API fails → auto-fallback to wa.me deep link

Incoming: Meta webhook → POST /webhook → parse → match tenant → match lead → reply
```

### Send Functions (biz_whatsapp.py — 714 lines)
```python
send_text(to, message)
send_document(to, url, filename, caption)
send_image(to, url, caption)
send_birthday_greeting(to, name, ...)
send_anniversary_greeting(to, name, ...)
send_renewal_reminder(to, name, ...)
send_premium_due_reminder(to, name, ...)
send_pitch_summary(to, name, type, ...)
send_calc_report(to, name, type, ...)
send_or_link(to, message)        # Smart: API → fallback to link
send_otp(to, otp)
send_text_for_tenant(tenant, to, message)  # Multi-tenant
```

### Current Status
- WhatsApp token **expired Feb 20, 2026** — wa.me link fallback active
- Multi-tenant: per-tenant `wa_phone_id` + `wa_access_token`

---

## 10. AI FEATURES

### Model: Gemini 2.5 Flash (biz_ai.py — 943 lines)
- `google-genai` SDK, JSON mode, bilingual prompts

### 8 AI Functions
1. **score_lead** — 1-100 score, A-D grade, reasoning
2. **generate_pitch** — Context-aware sales pitch
3. **suggest_followup** — Next best action
4. **recommend_policies** — Product recommendations
5. **handle_objection** — Counter objections
6. **renewal_intelligence** — Renewal strategy + upsell
7. **communication_template** — Professional templates
8. **claims_helper** — Claim guidance + checklists

### AI Quota System
- Per-plan daily limits via `db.check_ai_quota(agent_id)`
- Usage logged: `db.log_ai_usage(tenant_id, agent_id, feature, tokens_in, tokens_out)`
- SA monitoring: `/api/sa/ai-costs`

---

## 11. PAYMENT SYSTEM

### Plans

| Plan | Price/mo | Agents | Key Features |
|------|----------|--------|--------------|
| Individual (Solo Advisor) | ₹199 | 1 | CRM, 12 calculators, basic AI |
| Team | ₹799 | Admin + 5 | + WhatsApp, AI tools, campaigns, GDrive |
| Enterprise | ₹1,999 | Admin + 25 | + Priority, all features, custom branding, API |

### Flow (Recurring Subscriptions — v17k+)
```
Dashboard:
1. POST /api/payments/create-subscription → {subscription_id, razorpay_key_id}
2. Frontend: Razorpay Checkout modal with subscription_id (auto-pay mandate)
3. Razorpay webhook (subscription.activated) → Activate tenant
4. Monthly auto-charge via mandate → webhook (subscription.charged) → Extend expiry

Bot (/plans):
1. User taps plan button → POST create_subscription() → Razorpay short_url
2. Bot sends payment link → User completes on Razorpay hosted page
3. Webhook → Activate
```

### Razorpay Subscription Details
- Plans created at startup via `ensure_plans_exist()` → cached in `_razorpay_plan_ids`
- `total_count=120` (10 years max), monthly billing
- Webhooks handled: `subscription.activated`, `.charged`, `.completed`, `.cancelled`, `.halted`, `.pending`, `payment.captured`, `payment.failed`
- `_activate_tenant_from_sub()` sets expiry from Razorpay `current_end` timestamp

### Cancel Subscription
- **Dashboard:** Red "Cancel Subscription" card in Subscription tab (owner-only, active subs). CSRF-protected `POST /api/subscription/cancel`
- **Bot:** "❌ Cancel Subscription" button on `/plans` (owner/admin with active sub). 2-step confirmation flow in `_payment_callback`: `cancel_sub` → confirm → `pay_confirm_cancel` → execute

### Subscription Lifecycle
- Trial: 15 days → reminders T-10/13/14 → T-15 deactivate → T-25 data wipe
- Active: Auto-renewing via Razorpay mandate, `subscription_ends_at` updated on each `.charged` webhook
- Cancel: Immediate via Razorpay API → remains active until `current_end` → 30-day retention → wipe
- CSRF required on cancel + schedule-change

### Legacy One-Time Orders
- `POST /api/payments/create-order` still exists but dashboard now uses subscriptions exclusively
- Bot also switched to subscriptions (v17k)

---

## 12. MULTI-TENANT ARCHITECTURE

```
Super Admin (platform owner)
  └── Tenant (firm)
        ├── Owner (role: owner) — billing, settings, agent management
        └── Agent(s) (role: agent) — own leads, policies, interactions
```

### Isolation
- **Data:** agent_id filter per agent; owner sees all in tenant
- **Super Admin:** Cross-tenant access
- **Bot:** Per-tenant Telegram bot optional

### Feature Gating
```python
await db.check_plan_feature(tenant_id, 'whatsapp')   # team/enterprise
await db.check_plan_feature(tenant_id, 'ai_tools')    # team/enterprise
await db.check_plan_feature(tenant_id, 'campaigns')    # team/enterprise
```

---

## 13. AUTHENTICATION & AUTHORIZATION

### Token Types
```
Access Token (24h):  {sub: tenant_id, phone, firm, role, aid: agent_id}
Refresh Token (7d):  {sub, phone, role, jti}
SA Token (12h):      {sub, imp: True for impersonation}
Affiliate Token:     {sub, type: "affiliate"}
```

### Auth Methods
- **Agent/Owner (Primary):** Email OTP → JWT pair (6-digit OTP, 5-min expiry, sent via SMTP)
- **Agent/Owner (Alternative):** Google Sign-In → verify Google ID token → match email to tenant → JWT pair
- **Agent/Owner (Legacy):** Phone OTP → JWT pair (still supported but Email OTP is primary)
- **Super Admin:** Phone + password
- **Affiliate (Primary):** Email OTP → affiliate JWT
- **Affiliate (Alternative):** Google Sign-In → verify Google ID token → match email to affiliate → affiliate JWT
- **Telegram:** telegram_id → agent lookup

### Google Sign-In Flow (CRM)
1. Frontend loads Google Sign-In button with `GOOGLE_CLIENT_ID`
2. Placeholder "Loading Google Sign-In..." shown during SDK load; retry at 2s and 5s if SDK fails to initialize
3. User signs in with Google → receives `id_token`
4. Frontend sends `id_token` to `/api/auth/google-login`
5. Backend verifies token via `https://oauth2.googleapis.com/tokeninfo`
6. Matches `email` to `agents.email` or `tenants.owner_email`
7. Returns JWT token pair (same as OTP flow)
8. Unregistered email → error with "Start Free Trial →" link to #pricing

### Email OTP Login Flow (Existing CRM Users)
1. User enters email on login page
2. `/api/auth/send-email-otp` → checks email exists in `agents`/`tenants`, generates 6-digit OTP, stores in-memory with 5-min TTL
3. OTP sent via branded HTML email (SMTP from info@sarathi-ai.com via Gmail "Send mail as")
4. `/api/auth/verify-email-otp` → verifies OTP (timing-safe hmac.compare_digest), matches email to tenant, returns JWT pair
5. **Note:** Returns 404 if email not found — only for existing users

### Email OTP Signup Flow (New CRM Users) [April 2026]
1. User enters email on homepage signup form
2. `/api/auth/send-signup-otp` → sends OTP to ANY email without requiring existing account
   - Returns 409 if email already registered (with link to login)
   - Uses same `generate_email_otp()` + `send_otp_email()` chain
3. `/api/auth/verify-signup-otp` → verifies OTP only, returns `{status: "verified", email}`
   - Does NOT create account or issue tokens
4. Frontend then calls `/api/signup` with verified email + firm details to create account
5. This 2-step flow prevents half-created accounts from failed signups

### Affiliate Auth Flows [March-April 2026]
- **Register (Email OTP):** `/api/affiliate/register` → OTP → `/api/affiliate/verify` → create affiliate + auto-login JWT
- **Login (Email OTP):** `/api/affiliate/login` → OTP → `/api/affiliate/login/verify` → affiliate JWT + auto-login
- **Register (Google):** `/api/affiliate/register/google` → verify ID token → create affiliate + auto-login JWT
- **Login (Google):** `/api/affiliate/login/google` → verify ID token → match to affiliate → affiliate JWT + auto-login
- **Token extraction:** `_get_affiliate_from_token()` properly extracts from `Authorization: Bearer <token>` header

### OTP Security
- OTP values **NOT** logged to production logs (redacted April 2026)
- In-memory store with 5-min TTL, 60-second cooldown between sends, 5 max attempts
- OTP verification uses `hmac.compare_digest()` (timing-safe comparison)

### Middleware Stack (5 layers)
1. `CORSMiddleware` — Origin whitelisting
2. `security_headers_middleware` — CSP, HSTS, X-Frame-Options
3. `error_capture_middleware` — 5xx → system_events
4. `subscription_enforcement_middleware` — Block expired plans
5. `impersonation_audit_middleware` — Log SA impersonation writes

---

## 14. BACKGROUND SCHEDULER & PROACTIVE AI

### Daily Scheduled Tasks (biz_reminders.py — 1,290 lines)

| Time | Task |
|------|------|
| 6:00 AM | Auto-remediation + Anomaly scan + Inactive agent cleanup |
| 8:30 AM | Daily Summary (KPI digest, HI/EN) |
| 9:00 AM | Birthday Scan + Anniversary Scan (WA greeting + Telegram alert) |
| 10:00 AM | Renewal Scan (T-60/30/15/7/3/1/0) + Follow-up Scan |
| 11:00 AM | Trial Expiry (4-stage pipeline: remind → deactivate → grace → wipe) |
| 12:00 PM | Mid-day anomaly scan |
| Every 2 min | Message queue processing |
| Every 15 min | **Tier 2 Health Monitor** — 11 checks (server, DB, email, bots, queue, disk, data integrity, payments, auth) |
| 3:00 AM | **Health monitor cleanup** — purge check/alert data older than 30 days |

### Proactive AI Assistant (6 functions)

| Function | Schedule | Purpose |
|----------|----------|---------|
| `run_proactive_followup_nudge()` | 9AM/2PM/6PM | Agenda, gentle reminder, missed FUs |
| `run_celebration_assistant()` | 7 PM | Eve-of-birthday/anniversary greeting prompt |
| `run_deal_won_celebration()` | Instant | Fires on closed_won with premium stats |
| `run_stale_lead_alert()` | Monday 11 AM | Leads untouched 2+ weeks |
| `run_weekly_momentum()` | Saturday 6 PM | Wins, streak, motivation |
| `run_smart_post_action_suggestion()` | Instant | After log_meeting/create_lead/calc_compute |

### De-duplication
- `_proactive_sent_today` dict — "agent_id:type:entity_id"
- Resets at midnight

---

## 15. SEBI COMPLIANCE & DPDP CONSENT

### SEBI Regulatory Credentials
- **Agent fields:** `arn_number`, `euin`, `irdai_license`
- **Tenant fields:** `sebi_ria_code`, `amfi_reg`, `irdai_license`, `compliance_disclaimer`
- **`build_compliance_credentials(agent_id)`** — Formatted credential string for PDFs
- **Onboarding:** `/api/onboarding/branding` saves credential fields

### DPDP Data Protection
- **Lead consent:** `dpdp_consent` (0/1) + `dpdp_consent_date`
- **Contact prefs:** max_messages_per_week, preferred_channel, opted_out
- **`can_message_lead(lead_id)`** — Check opt-out + frequency limits
- **Data lifecycle:** Trial T-25 → complete wipe; Cancel → 30-day retention → wipe

### Audit Trail
- `audit_log` with role column — all actions logged with IP, role, detail

---

## 16. AFFILIATE & PARTNER PROGRAM

### Public APIs (12)
```
POST /api/affiliate/register           — Send registration OTP to email
POST /api/affiliate/verify             — Verify OTP + create affiliate + auto-login
POST /api/affiliate/login              — Send login OTP to email
POST /api/affiliate/login/verify       — Verify login OTP + JWT + auto-login
POST /api/affiliate/register/google    — Google Sign-In register + auto-login
POST /api/affiliate/login/google       — Google Sign-In login + auto-login
POST /api/affiliate/track              — Track referral click
GET  /api/affiliate/check/{code}       — Validate referral code
GET  /api/affiliate/me                 — Current affiliate info
GET  /api/affiliate/dashboard          — Affiliate dashboard stats
GET  /api/affiliate/payouts            — Payout history
PUT  /api/affiliate/payout-info        — Update payout details (UPI/bank)
```

### SA Management APIs (12)
```
GET  /api/sa/affiliates|stats|/{id}/referrals|payouts
POST /api/sa/affiliates|/{id}/approve|reject|mature-commissions|payout|payout/{id}/complete
GET  /api/sa/affiliates/payout-queue
POST /api/sa/affiliates/referrals/{id}/reverse
```

### Commission Flow
```
1. Affiliate shares referral code
2. New firm signs up → referral tracked
3. 7-day cooling period (chargeback protection)
4. SA matures commissions → status: ready
5. SA initiates payout → complete
```

---

## 17. SUPPORT TICKET SYSTEM

### Tenant (CRM) Tickets
- **Create:** `POST /api/support/tickets` — title, message, category, priority
- **Reply:** `POST /api/support/tickets/{id}/reply` — threaded messages
- **List:** `GET /api/support/tickets` — agent sees own tenant tickets
- **Detail:** `GET /api/support/tickets/{id}` — ticket + all messages
- **AI L1 auto-response:** Optional first reply from AI
- Displayed in `support.html` and `admin.html`

### Affiliate Tickets
- **Create:** `POST /api/affiliate/tickets` — affiliate-scoped
- **Reply:** `POST /api/affiliate/tickets/{id}/reply`
- **List/Detail:** `GET /api/affiliate/tickets`, `GET /api/affiliate/tickets/{id}`
- Displayed in `partner.html`

### Super Admin Ticket Management
- **List all:** `GET /api/sa/tickets` — cross-tenant + affiliate tickets
- **Stats:** `GET /api/sa/tickets/stats` — open/in-progress/resolved counts
- **Detail:** `GET /api/sa/tickets/{id}` — ticket + messages (fixed destructure: `d.ticket` + `d.messages`)
- **Update:** `PUT /api/sa/tickets/{id}` — status, priority, assignment
- **Reply:** `POST /api/sa/tickets/{id}/reply` — SA response
- Managed in `superadmin.html` Support panel with IST timestamps (relative time display)

### Ticket Tables
- `support_tickets` (tenant/agent tickets)
- `ticket_messages` (threaded replies)
- `affiliate_tickets` (affiliate tickets)
- `affiliate_ticket_messages` (affiliate replies)
- Status flow: `open` → `in_progress` → `resolved` → `closed`

---

## 18. RESILIENCE & OBSERVABILITY

### Resilience (biz_resilience.py — 471 lines)
- Retry decorator with exponential backoff
- Message queue: failed → retry → dead-letter
- Health check: `/health`

### Anomaly Detection (7 categories)
1. Expired trials still active
2. Orphan agents (no valid tenant)
3. Orphan leads (no valid agent)
4. Duplicate phones (fraud risk)
5. Tenants with no agents (broken onboarding)
6. Failed login spikes (brute-force)
7. Massive lead creation (spam)

### Auto-Remediation
- `auto_fix_expired_trials()`, `auto_fix_orphan_agents()`, `auto_fix_orphan_leads()`
- All fixes logged to `system_events`

### Tier 2 Health Monitor (biz_health_monitor.py — 479 lines)

**11 Automated Checks** (runs every 15 minutes):

| Check | Category | What It Does |
|-------|----------|-------------|
| Server Health | server | CPU, memory, disk % via psutil |
| Database Health | database | Connection test, WAL size, table integrity |
| Database Size | database | DB file size monitoring |
| Email Config | email | SMTP credentials configured check |
| Bot Status | bots | All active tenant bots polling status |
| Dead Bot Detection | bots | Bots not polling in 10+ minutes |
| Message Queue | queue | Dead letter count, queue backlog |
| Stale Queue Items | queue | Messages stuck > 1 hour |
| Disk Space | disk | Free space % and absolute GB |
| Data Integrity | data | Orphan agents/leads, expired trials still active |
| Payment System | payments | Razorpay credentials configured |
| Auth System | auth | JWT secret present, SA password set |

**Auto-Fix Actions:**
- Expired trials still active → auto-deactivate
- Orphan agents → auto-deactivate
- Orphan leads → log warning

**Alert System:**
- Critical/warning results trigger email to SA_ALERT_EMAIL
- HTML-formatted alert email with check details + auto-fix summary
- Alerts stored in `health_alerts` table

**SA Dashboard Integration:**
- 6th panel "Monitor" in superadmin.html bottom nav
- Live status with last check time, category breakdown
- Check history with expand/collapse details
- Manual "Run Now" button
- Auto-refresh every 60 seconds

---

## 19. DEPLOYMENT

### Production Stack (Oracle Cloud)
```
Oracle Cloud VM (140.238.246.0) → Ubuntu 24.04 → Cloudflare DNS → Nginx (port 80, reverse proxy) → Uvicorn (8001) → FastAPI + Telegram Bot
```

**Domain:** `sarathi-ai.com` / `www.sarathi-ai.com` (Cloudflare proxied A records → 140.238.246.0)
**SSH:** `ssh -i ssh-key-2026-03-03.key ubuntu@140.238.246.0` → `sudo su sarathi`, dir: `/opt/sarathi`
**Service:** `sudo systemctl restart sarathi` (auto-restart on crash, RestartSec=3)
**Nginx:** Port 80, reverse proxy to :8001, static files with 7d cache, Service-Worker-Allowed header
**SSL:** Cloudflare edge (Flexible mode)

### Scripts (deploy/)
- `setup-server.sh` — Oracle VM initial setup (Python 3.12, venv, systemd, nginx)
- `push-update.sh` — SCP-based code deployment
- `backup.sh` — DB + static backup before deploy
- `sarathi.service` — systemd unit (WorkingDir=/opt/sarathi, User=sarathi)
- `nginx-sarathi.conf` / `nginx-prod.conf` — Reverse proxy configs

### Startup Sequence
```
1. Database init (schema + migrations + campaigns + resilience)
2. Services (auth, email, WA, GDrive, PDF, Razorpay)
3. Telegram bots (master webhook + tenant bots from DB)
4. Callbacks (reminders + queue processor)
5. Background tasks (scheduler + plan change applier)
6. Uvicorn web server
7. Signal handlers (graceful shutdown)
```

---

## 20. ENVIRONMENT VARIABLES

```env
DEV_MODE=true
TELEGRAM_BOT_TOKEN=...
TELEGRAM_BOT_NAME=Sarathi-AI.com
WHATSAPP_PHONE_ID=...
WHATSAPP_ACCESS_TOKEN=...          # EXPIRED Feb 20, 2026
WHATSAPP_VERIFY_TOKEN=...
SERVER_URL=https://nonseparable-undarned-geoffrey.ngrok-free.dev
SERVER_PORT=8001
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
BRAND_COMPANY=Sarathi-AI Business Technologies
BRAND_AGENT=Your Financial Advisor
BRAND_TAGLINE=AI-Powered CRM for Financial Advisors
BRAND_EMAIL=support@sarathi-ai.com
BRAND_PRIMARY_COLOR=#1a56db
BRAND_ACCENT_COLOR=#ea580c
BRAND_DOMAIN=sarathi-ai.com
JWT_SECRET=...
ADMIN_API_KEY=...                  # deprecated, use SA
SUPERADMIN_PHONES=8875674400
SUPERADMIN_PASSWORD=...
RAZORPAY_KEY_ID=rzp_live_...
RAZORPAY_KEY_SECRET=...
SMTP_HOST=smtp.gmail.com           # CONFIGURED
SMTP_PORT=587
SMTP_USER=kumar26.dushyant@gmail.com
SMTP_PASSWORD=bsyw****bdamgkuu    # Gmail App Password
SMTP_FROM_EMAIL=info@sarathi-ai.com  # "Send mail as" via Cloudflare Email Routing + Gmail alias
GOOGLE_CLIENT_ID=903535788143-...apps.googleusercontent.com
SA_ALERT_EMAIL=kumar26.dushyant@gmail.com  # Health monitor alert recipient
GDRIVE_CLIENT_ID=                  # not configured
GDRIVE_CLIENT_SECRET=
GDRIVE_REDIRECT_URI=...
```

---

## 21. DEVELOPMENT SETUP

### Prerequisites
- Python 3.12 (NOT 3.13 — broken on this Windows machine)
- ngrok account (free tier)

### Quick Start
```bash
cd c:\sarathi-business
pip install -r biz_requirements.txt
python sarathi_biz.py
# In another terminal:
ngrok http 8001 --domain=nonseparable-undarned-geoffrey.ngrok-free.dev
```

### Compile Check
```bash
python -m py_compile biz_bot.py
python -m py_compile sarathi_biz.py
```

---

## 22. SECURITY MEASURES

- JWT: 24h access + 7d refresh, 64-char hex secret
- OTP: bcrypt-hashed, 5-min expiry, 5 attempts (phone OTP + email OTP)
- Email OTP: In-memory store, 5-min TTL, 5 attempts max, rate-limited, **OTP values NOT logged** (redacted April 2026)
- Google Sign-In: ID token verified via Google's tokeninfo endpoint, audience check
- CSRF: per-session tokens on state-changing mutations
- Role-based: Owner vs Agent vs SA, enforced at middleware
- Owner-only payments: `require_owner` on create-order/verify/create-subscription
- HTML escaping: `html.escape()` on all user-rendered text
- Subscription enforcement middleware
- Audit trail: action + IP + role + timestamp
- Impersonation logging: separate audit for SA impersonation
- Rate limiting: slowapi per endpoint (5-200/min)
- IP blocking: Failed SA login → 15-min cooldown
- Abuse detection: 3-strike → 24h block, 5-strike → permanent
- DPDP consent: lead-level consent + contact frequency limits

---

## 23. KNOWN ISSUES & LIMITATIONS

| Issue | Status |
|-------|--------|
| WhatsApp token expired (Feb 20, 2026) | **Mitigated** — wa.me fallback active |
| ~~Email not configured~~ | **RESOLVED** (March 25, 2026) — Gmail SMTP + App Password configured, 16 email functions working |
| Google Sign-In | **CONFIGURED** — Google OAuth2 client ID set, verify via tokeninfo endpoint |
| ~~CRM signup Email OTP broken for new users~~ | **FIXED** (April 5, 2026) — New `/api/auth/send-signup-otp` + `/api/auth/verify-signup-otp` endpoints |
| ~~OTP values leaked to production logs~~ | **FIXED** (April 5, 2026) — OTP redacted from log messages in `biz_auth.py` |
| ~~interaction_type column error in reminders~~ | **FIXED** (April 5, 2026) — `i.interaction_type` → `i.type` in two SQL queries in `biz_database.py` |
| ~~Affiliate token extraction broken~~ | **FIXED** (April 2026) — `_get_affiliate_from_token()` properly extracts Bearer token |
| ~~Affiliate Google sign-in no auto-login~~ | **FIXED** (April 2026) — register + login Google endpoints return JWT for auto-login |
| Yahoo/non-Gmail OTP delivery | **Known** — Emails sent successfully but may go to Yahoo spam. SPF includes Google. No DMARC record (consider adding `v=DMARC1; p=none; rua=mailto:info@sarathi-ai.com`) |
| Google Drive not configured | Active — GDRIVE_CLIENT_ID empty |
| SQLite concurrency | Known — migrate to PostgreSQL for scale |
| Calculator PDF: HTML only | Known — browser-based print |
| Gemini rate limits | Known — free tier: 15 RPM, 1M TPM |
| Python 3.13 incompatible | Known — use 3.12 only |

---

## 24. BUILD LOG — ALL FEATURES IMPLEMENTED

### Core CRM
- [x] Multi-tenant registration + onboarding
- [x] Agent management (invite, activate, deactivate, transfer, remove)
- [x] Lead CRUD (name, phone, DOB, anniversary, city, income, need_type, stage)
- [x] 7-stage pipeline (prospect → closed_won/lost)
- [x] Policy management (add, track, renewal dates)
- [x] Follow-up scheduling + reminders
- [x] Meeting logging with channel tracking
- [x] Notes system per lead
- [x] CSV/JSON bulk import
- [x] Bilingual UI (EN + HI)

### Voice System
- [x] 24 intents via Gemini transcription
- [x] Hindi + English + Hinglish voice notes
- [x] Voice CRUD (create lead, log meeting, update stage, add note, edit lead)
- [x] Voice follow-up scheduling with date parsing
- [x] Voice queries (leads, pipeline, dashboard, renewals, today)
- [x] Voice WhatsApp + greeting
- [x] Voice AI tools (score, pitch, recommend, follow-up suggest)
- [x] Abuse detection (3/5-strike system)
- [x] Context-aware: pronoun resolution via context injection
- [x] Confidence scoring with smart fallback buttons
- [x] Multi-turn context: 5-min expiry + intent override + cancel
- [x] Voice history tracking across all handlers

### Calculator System
- [x] 12 calculators: Inflation, HLV, Retirement, EMI, Health, SIP, MF SIP, ULIP, NPS, Step-Up SIP, SWP, Delay Cost
- [x] Voice one-shot + multi-turn compute
- [x] Quick-select buttons + Hindi/English number parsing
- [x] 12 branded PDF reports with compliance credentials
- [x] WhatsApp sharing with wa.me fallback
- [x] Web calculators page (12 tabs + Chart.js + i18n)
- [x] Just Talk text mode: calculator intents

### Proactive AI Assistant
- [x] Morning/afternoon/evening follow-up nudges
- [x] Eve-of-birthday/anniversary celebration assistant
- [x] Deal won celebration (instant trigger)
- [x] Stale lead alert (Monday)
- [x] Weekly momentum digest (Saturday)
- [x] Smart post-action suggestions
- [x] All nudges bilingual (HI/EN)

### SEBI & DPDP Compliance
- [x] Regulatory credential fields (ARN, EUIN, IRDAI, SEBI RIA, AMFI)
- [x] Credentials on PDF footers
- [x] DPDP consent per lead (consent + timestamp)
- [x] Contact preferences (frequency, opt-out, channel)
- [x] Data lifecycle (trial → grace → wipe)
- [x] Immutable audit log with role

### WhatsApp
- [x] Meta Cloud API (text, document, image)
- [x] Auto-greetings (birthday, anniversary, renewal)
- [x] Calc report sharing + wa.me fallback
- [x] Multi-tenant credentials

### AI Features
- [x] 8 AI functions (score, pitch, suggest, recommend, objection, renewal, template, claims)
- [x] AI quota + cost tracking

### Admin & Super Admin
- [x] 40+ SA APIs
- [x] System events + anomaly scan + auto-remediation
- [x] Bulk operations + data export
- [x] CSRF, owner-only payments, impersonation audit

### Payments
- [x] Razorpay (orders + subscriptions), 3 plans
- [x] Trial 15-day pipeline + feature gating
- [x] Scheduled plan changes

### Other
- [x] Affiliate program (commission + cooling + payouts)
- [x] Support tickets (AI L1 auto-response)
- [x] Insurance claims tracking
- [x] Campaign management (bulk WA + email)
- [x] Nudge system (owner → advisor)
- [x] Resilience (retry, queue, dead-letter)
- [x] Dark mode (CSS + JS)

### Authentication (March 25-26, 2026)
- [x] Email OTP login (6-digit, 5-min TTL, branded HTML email, rate-limited)
- [x] Google Sign-In (OAuth2 ID token verification, email-to-tenant matching)
- [x] Login page with Email OTP + Google Sign-In UI
- [x] Legacy phone OTP preserved as fallback

### Tier 2 Health Monitor (March 26, 2026)
- [x] `biz_health_monitor.py` — 11 automated checks
- [x] Auto-fix for expired trials + orphan agents
- [x] Email alerts to SA on critical/warning
- [x] 15-minute scheduled runs + 3AM cleanup
- [x] 4 SA API endpoints (latest, history, alerts, manual run)
- [x] Monitor panel in superadmin.html (6th bottom nav tab)
- [x] psutil for server CPU/memory/disk monitoring

### Production Maintenance (March 25-26, 2026)
- [x] Dead file cleanup — 20+ backup/unused files removed from production
- [x] Email logo fix — changed to `logo.png` (transparent, works in dark mode)
- [x] SA system-status updated — Email shows top, Google Sign-In added, WA/SMS shown as disabled
- [x] SA health display fix — color-coded badges, proper status rendering

### Affiliate System E2E (March-April 2026)
- [x] 6 affiliate auth endpoints (register, verify, login, login/verify, register/google, login/google)
- [x] Google Sign-In for affiliates (register + login with auto-login JWT)
- [x] OTP verify auto-login (register + login flows)
- [x] `_get_affiliate_from_token()` Bearer token extraction fix
- [x] Partner page (`partner.html`) with full auth UI, dashboard, payouts, IST timestamps
- [x] Affiliate support ticket system (create, reply, view)

### Homepage & Hero Overhaul (April 2026)
- [x] Hero section Phase B: Voice AI demos, animated waveforms, confidence scoring
- [x] Hero flickering fix: fixed-height containers + absolute position panels
- [x] Dashboard Voice AI demo integration (mobile-optimized)
- [x] Horizontal scroll buttons for feature cards (overlay fix)
- [x] Signup flow: email OTP via dedicated `/api/auth/send-signup-otp` endpoint

### Auth & Security Hardening (April 5, 2026)
- [x] New CRM signup OTP endpoint (`/api/auth/send-signup-otp`) — OTP for unregistered emails
- [x] New CRM signup verify endpoint (`/api/auth/verify-signup-otp`) — verify only, no account creation
- [x] OTP log leak fixed — OTP values redacted from production logs
- [x] `interaction_type` → `type` SQL column fix in 2 queries (stopped every-minute error spam)
- [x] Email sender identity: `Sender` header + `Reply-To` in `biz_email.py`
- [x] Gmail "Send mail as" `info@sarathi-ai.com` via Cloudflare Email Routing
- [x] SA ticket detail fix (response destructure) + IST timestamps
- [x] Comprehensive E2E auth audit: all 13 CRM + 6 affiliate endpoints verified

---

## 25. CRITICAL CODE PATTERNS

### Safe Message Editing
```python
async def _safe_edit_text(msg_or_query, text, **kwargs):
    if hasattr(msg_or_query, 'edit_message_text'):
        return await msg_or_query.edit_message_text(text, **kwargs)
    return await msg_or_query.edit_text(text, **kwargs)
```

### WhatsApp Auto-Fallback
```python
result = await send_text(to, message)
if not result.get('success'):
    return {"success": True, "method": "link", "wa_link": generate_wa_link(to, message)}
```

### Multi-Turn Calculator Context
```python
context.user_data['voice_context'] = {
    'pending_action': 'calc_compute', 'calc_type': 'emi',
    'values': {'premium': 50000}, 'missing_keys': ['gst', 'cibil_disc'],
    'missing_step': 0, 'created_at': time.time(),  # 5-min expiry
}
```

### i18n in PDF Reports
```python
t = lambda k: _t(k, lang)
html = f"<h1>{t('inf_title')}</h1>"
```

### Proactive De-duplication
```python
key = f"{agent_id}:birthday:{lead_id}"
if _was_proactive_sent(key): return
_mark_proactive_sent(key)
```

---

## 26. STATIC WEB PAGES

### Homepage (index.html — ~3,923 lines)
- **2-Part Hero Section (flickering fix April 2026):**
  - Part 1 (top): Big Telegram bot demo screen (82% viewport width, max 1200px), 12 interactive buttons in 3×4 grid (Menu first), typewriter chat scenarios, "Click to explore" hint + intro pulse on Menu button
  - Part 2 (below): Left = dynamic tagline (5 cycling phrases, crossfade, **fixed-height containers + all panels position:absolute to prevent flicker**) + sub text + CTAs + FOMO badges; Right = big brand logo (483px, float animation)
  - Mobile (<900px): Phone-frame mockup (tall, 620px) replaces wide screen; order: Bot Demo → Logo → Text
- **Interactive Demo section:** 6 tabs (Telegram Bot, Calculators, Lead Journey, **Voice AI with demos**, Dashboard, Reports)
  - Voice AI tab: Animated waveform demos — "Voice se lead add karo", real-time confidence scoring
  - Dashboard tab: Mobile-friendly demo with Voice AI integration
- **Signup flow:** Email OTP (using `/api/auth/send-signup-otp`) + Google Sign-In, 409 handling for existing accounts
- Horizontal scroll buttons for feature cards (overlay fix April 2026)
- 10 feature cards (Voice AI, 12 Calculators, Pipeline, WhatsApp, Proactive AI, SEBI/DPDP, etc.)
- Pricing: Individual ₹199 / Team ₹1,499 / Enterprise ₹3,999
- Trust counter: 12 calculators, comparison table: 11 rows
- Full Hindi/English i18n

### Web Calculators (calculators.html — ~2,508 lines)
- 12 tabs: inflation → delaycost
- 12 `calcXxx()` JS functions + Chart.js
- `_CT` i18n object (100+ keys EN/HI)
- Slider inputs, responsive, dark mode

### Other Key Pages
- **dashboard.html** (~4,985) — KPI charts, CSRF, mobile-optimized with Voice AI demo integration
- **superadmin.html** (~959) — Mobile-first SA Cockpit (bottom nav, 6 panels including Monitor, customer health, 60+ API endpoints, live health dashboard, ticket management with IST timestamps, relative time display)
- **demo.html** (~1,842) — 6 device frames
- **telegram-guide.html** (~1,537) — Bot setup with i18n
- **partner.html** (~1,288) — Affiliate program: register/login (email OTP + Google), dashboard, payouts with IST timestamps, auto-login on OTP verify + Google sign-in
- **support.html** (~480) — Support ticket submission
- **admin.html** (~639) — Admin tenant management panel

---

## 27. i18n — BILINGUAL SYSTEM

| Layer | File | Keys |
|-------|------|------|
| Telegram Bot | `biz_i18n.py` | 150+ |
| PDF Reports | `biz_pdf.py` | 181 |
| Web Pages | Each `.html` | varies |
| Reminders | `biz_reminders.py` | inline |
| Bot Messages | `biz_bot.py` | inline |

### Language Resolution
1. Agent `lang` field (en/hi) — via /lang or profile
2. Tenant `lang` — team-level default
3. Web: client-side toggle

---

## 28. RECENT WORK LOG (March 22–April 5, 2026)

### March 22: SEBI, AI, Calculators, Security

#### SEBI Compliance + DPDP Consent
- Regulatory credential fields + `build_compliance_credentials()`
- DPDP consent per lead + contact preferences + data lifecycle

#### Proactive AI Assistant
- 6 proactive functions (nudges, celebrations, momentum, post-action)
- All bilingual, de-duplicated

#### 3 New Calculators (Step-Up SIP, SWP, Delay Cost)
- Full stack: engine → bot → PDF → voice → web (12 total now)

#### Homepage & Branding Refresh
- 10 feature cards, 12 calculators throughout, comparison table expanded
- All HTML pages cross-updated (index, demo, help, telegram-guide)

#### i18n Audit: 14 gaps fixed
- 3 CRITICAL (voice wiring), 8 IMPORTANT (reminders), 3 MINOR

#### Security Audit: 6 gaps fixed
- Owner-only payments, audit log role, CSRF, feature gates, SA monitoring

#### Voice Enhancements
- Context-aware + confidence scoring + multi-turn protection

### March 23: CRM Overhaul + Renewals + Homepage

#### CRM Accountability System (4 Phases)
- **Phase 1**: Admin gate on 12 voice handlers + 5 callback handlers (owner/admin only for team-wide ops)
- **Phase 2**: Dashboard icon-only buttons → 14 buttons got text labels + i18n keys
- **Phase 3**: Follow-up system overhauled with `created_by_agent_id` column, duplicate detection, cross-agent notifications

#### Task System (Follow-ups → Tasks)
- **DB schema**: Added `follow_up_time`, `follow_up_status` (pending/done), `created_by_agent_id`, `assigned_to_agent_id` columns to `interactions`
- **Voice**: `_extract_time_from_transcript()` fallback when Gemini misses time; AI prompt strengthened with `task_assignee` + `reminder_time` enforcement
- **Task assignee resolution**: Voice commands like "create task for Neha" → fuzzy match agent names → sets `assigned_to_agent_id`
- **API**: `FollowupRequest`/`FollowupEditRequest` accept `assigned_to_agent_id`; notifications go to assignee
- **Dashboard**: "Tasks Due" header, assignee display, assign dropdown in edit modal, mark-done button

#### Task Display & Timezone Fixes
- IST timezone: All queries use `date('now','+5 hours','+30 minutes')`
- Upcoming tasks: Next 7 days visible (not just overdue/today)
- 12hr AM/PM display; sorted nearest-first

#### Renewals Fix
- Policy renewal queries fixed for IST timezone
- Bot `/renewals` command now correctly shows policies expiring in next 30 days

#### Homepage Upgrade
- New hero section with animated logo, gradient overlays
- Dark mode toggle + full dark mode CSS system across all 15 pages
- Terms & Conditions section with Hindi/English audio playback (gTTS MP3)

#### PDF Report Link Fix
- `_reportEndpoint()` mapping: stepupsip→stepup, delaycost→delay
- WhatsApp report sharing now uses same format as web

#### Affiliate & Partner Program Launch
- Complete `static/partner.html`: 3-tab interface (About, Join, Dashboard)
- Registration: Name → Phone OTP → Email OTP → Referral Code (SAR-XXXXXX)
- Dashboard: Stats, referral history, payout details (UPI/Bank), T&C with audio
- 13 SA API endpoints for affiliate management
- 8 public API endpoints for self-service
- 3 DB tables: affiliates, affiliate_referrals, affiliate_payouts
- Fraud prevention: dedup, self-referral block, velocity limits, 7-day cooling

### March 24: Oracle Cloud Deployment + PWA + Logo Fixes

#### Oracle Cloud Production Deployment
- VM: `140.238.246.0`, Ubuntu 24.04, user `sarathi`, dir `/opt/sarathi`
- Python 3.12 venv, systemd service (auto-restart), nginx reverse proxy
- Cloudflare DNS: `sarathi-ai.com` + `www.sarathi-ai.com` → A records
- All 27+ files deployed: Python modules, HTML pages, static assets
- Production environment variables configured in `/opt/sarathi/biz.env`

#### PWA (Progressive Web App)
- `static/manifest.json`: Standalone app, theme #0d9488, 5 icon sizes
- `static/sw.js`: Service Worker v6, network-first for HTML/API, cache-first for static, auto-update
- FastAPI routes: `/sw.js` (FileResponse, no-cache, Service-Worker-Allowed header), `/manifest.json`
- PWA meta tags + SW registration in all 15 HTML pages
- Installable from Chrome → Add to Home Screen

#### Logo Transparency Fix
- White background removed from `logo.png` via Pillow pixel processing (R>235 & G>235 & B>235 → alpha=0)
- Original backed up as `logo_original_white.png`
- All CSS `mix-blend-mode:multiply` workarounds removed
- Dark mode: `brightness(1.5) contrast(1.05)` filter only

#### PWA Icons
- Generated from transparent logo.png: 512, 192, 180, 32, 16 + favicon.ico
- Maskable icons: White background, centered in safe zone, new filenames (`app-icon-512.png`, `app-icon-192.png`)
- Manifest updated with new icon paths, background_color #ffffff

#### Cache Busting
- All CSS/JS/image refs bumped from `?v=2` → `?v=3` across all 15 HTML files
- SW cache `sarathi-v5` → `sarathi-v6`
- Cloudflare verified MISS on new versioned URLs

#### Hero Logo Alignment
- Fixed mobile alignment: removed overflow:hidden, negative margins
- `object-fit:contain`, max-width: 520px desktop, 300px tablet, 240px mobile

### March 25: Super Admin Cockpit Revamp

#### Complete SA Redesign — Mobile-First "Cockpit"
Old: 2624 lines, desktop-oriented, 12 horizontal tabs, hard to use on mobile
New: 807 lines, mobile-first, bottom navigation bar, card-based UI

**Architecture:**
- Bottom navigation: Home / Firms / Alerts / Support / More (thumb-reachable)
- Slide-up overlay panels for details (tenant, tickets) — no page navigation
- All data loads async, cached client-side
- Single-page app feel with panel switching

**5 Main Panels:**
1. **🏠 Home (Command Center)**: System health strip, 6 KPI cards, 30d signup chart, quick actions, recent audit
2. **🏢 Firms**: Searchable list with status filter tabs (All/Trial/Paid/Expired/Inactive), tap-to-open detail overlay
3. **⚠️ Alerts**: System events with Scan/AI Classify/Auto-Fix buttons, event filter tabs, per-event resolve
4. **🎫 Support**: Ticket list with priority badges, status filters, detail overlay with reply + resolve
5. **⚙️ More**: Telegram bots, revenue breakdown, audit log with search, CSV exports, duplicate detector

**6th Panel (Added March 26):**
6. **📊 Monitor**: Tier 2 Health Monitor dashboard — live status indicators, last check time, category breakdown (server/database/email/bots/queue/disk/data/payments/auth), check history with expandable details, manual "Run Now" button, auto-refresh every 60 seconds

**Tenant Detail Overlay (The Cockpit View):**
- Customer info (phone, email, owner, plan, created date, trial end, agents, leads, bot status)
- **🔴 Customer Health panel**: Shows all system events + error logs + dead letters for that tenant
  - Auto-fixed issues shown with 🔧 tag
  - Dead letters highlighted with warning banner
  - Green "All systems operational" when clean
- **🎮 Actions**: Extend Trial, Activate, Change Plan, Deactivate, Restart Bot, Delete, Impersonate

**Also includes:**
- Affiliates panel: Stats, approve/reject, payout queue with one-tap Pay
- Create Firm overlay: Firm name, owner, phone, email, plan selector
- 60+ SA API endpoints all wired in
- XSS protection via `esc()` helper on all dynamic content
- JWT auth with session check on load
- Dark mode support via shared dark-mode.css
- Old SA backup preserved as `superadmin_backup.html`

### March 25 (continued): Auth Migration + Email Configuration + SA Fixes

#### Email System Configuration
- Gmail SMTP configured: `kumar26.dushyant@gmail.com` with App Password
- 16 email functions verified working: OTP, welcome, payment receipt, trial reminders, health alerts, etc.
- Email logo fixed: changed to `logo.png` (transparent background, dark mode compatible)
- `SA_ALERT_EMAIL` configured for health monitor notifications

#### Authentication Migration: Email OTP + Google Sign-In
- **Email OTP Login**: New primary auth method
  - `send_email_otp()` → 6-digit OTP, in-memory store, 5-min TTL, 5 attempts max
  - `verify_email_otp()` → matches email to `agents.email` or `tenants.owner_email`
  - Branded HTML email template with OTP
  - Rate-limited: 5 sends/min, 10 verifies/min
- **Google Sign-In**: Alternative auth method
  - `verify_google_id_token()` → verifies via Google's tokeninfo API
  - Audience check against `GOOGLE_CLIENT_ID`
  - Email matching to tenant → JWT pair
  - Frontend: Google Sign-In button loaded dynamically
- **Login Page Updated**: Email input → OTP or Google Sign-In → JWT
- **Legacy Phone OTP preserved**: Still functional as fallback
- API endpoints: `/api/auth/send-email-otp`, `/api/auth/verify-email-otp`, `/api/auth/google-login`, `/api/auth/google-client-id`

#### Super Admin System Status Fixes
- System status panel reordered: Email shown first (as it's now primary), Google Sign-In added
- WhatsApp and SMS shown as disabled with proper status badges
- Color-coded status badges: green (✓), red (✗), yellow (disabled)
- SA health display fixed for proper rendering

#### Dead File Cleanup
- 20+ backup/unused files removed from production `/opt/sarathi/`:
  - HTML backups: `dashboard_old.html`, `index_backup.html`, `admin_old.html`, `dashboard_backup.html`, etc.
  - Unused logo variants: `logo_transparent.png`, `logo_original_white.png`, multiple generated logo PNGs
  - Test/script files: `generate_logos.py`, `_*.py` test scripts
- Production `/opt/sarathi/static/` cleaned of stale assets

### March 26: Tier 2 Health Monitor

#### Health Monitor Engine (`biz_health_monitor.py` — 479 lines)
- **11 automated health checks** across 9 categories:
  - Server: CPU %, memory %, system load (via `psutil`)
  - Database: connection test, WAL file size, table integrity, DB file size
  - Email: SMTP credentials configured
  - Bots: Active tenant bots polling status, dead bot detection (10+ min stale)
  - Queue: Dead letter count, queue backlog, stale items (> 1 hour)
  - Disk: Free space % and absolute GB
  - Data Integrity: Orphan agents/leads, expired trials still active
  - Payments: Razorpay credentials configured
  - Auth: JWT secret present, SA password set

#### Auto-Fix Capabilities
- Expired trials still active → auto-deactivate tenant
- Orphan agents (no valid tenant) → auto-deactivate agent
- All auto-fixes logged with 🔧 marker in check results

#### Alert System
- Critical/warning results → HTML email alert to `SA_ALERT_EMAIL`
- Email includes: run ID, check count, critical/warning/auto-fixed counts, detailed per-check status
- Alerts stored in `health_alerts` DB table for history

#### Database Tables
- `health_checks`: Individual check results per run (check_name, status, message, auto_fixed, details JSON)
- `health_alerts`: Alert records with acknowledgement tracking

#### Scheduler Integration
- Every 15 minutes: `run_full_health_check()` via `biz_reminders.py`
- 3:00 AM daily: `cleanup_old_data(30)` — purge checks/alerts older than 30 days

#### SA API Endpoints (4)
- `GET /api/sa/health-monitor` — Latest check results
- `GET /api/sa/health-monitor/history` — Check history (default: 20)
- `GET /api/sa/health-monitor/alerts` — Alert history (default: 50)
- `POST /api/sa/health-monitor/run` — Manual trigger

#### SA Dashboard Panel (Monitor — 6th tab)
- Added "📊 Monitor" as 6th bottom navigation tab in `superadmin.html`
- Live dashboard: last check time, overall status (healthy/warning/critical count)
- Category breakdown with color-coded status indicators
- Check history list with expandable details per check
- Manual "🔍 Run Check Now" button
- Auto-refresh every 60 seconds

#### Production Deployment
- `psutil` package installed on production venv
- `biz_health_monitor.py` deployed to `/opt/sarathi/`
- Updated `biz_database.py`, `biz_reminders.py`, `sarathi_biz.py`, `superadmin.html`
- Service restarted, health check running confirmed

### March 27–28: Hero Section Complete Redesign (SW v8→v14)

Multi-round hero section redesign, culminating in a 2-part hero layout.

#### Round 1 (SW v8–v9): Initial Improvements
- Expanded phone buttons from 9 (3×3) to 12 (4×3): added Upload, Email, Share, Menu
- Rewrote tagline to pain-point focus: "Bolo. AI Samjhega. Sab Ho Jayega."
- 5 cycling tagline phrases with word-by-word animation (en + hi)
- Removed "Telegram" from hero text, removed 🇮🇳 flag from badge
- Added button click/tap glow feedback (touchstart + .pressed class)
- Added features page dark mode CSS rules
- Fixed word spacing bug (margin-right:.22em instead of trailing space)

#### Round 2 (SW v10–v11): Layout Tuning
- Full-width hero layout attempt (max-width:100%, padding:0 5vw) — too wide, content spread to edges
- Viewport-relative phone sizing with min() — scaling issues
- Reverted to 1400px centered container with 1fr+420px grid
- Fixed tagline flickering: replaced word-by-word animation with clean crossfade (opacity transition)
- Removed logo float animation for stability
- Removed touchstart preventDefault hack (was causing sticky button feel)

#### Round 3 (SW v12–v14): 2-Part Hero (Final Architecture)

**Part 1 — Big Bot Demo Screen (desktop, top of hero):**
- Wide Telegram-style panel: `width:82%; max-width:1200px`, centered, rounded dark UI
- NOT a phone mockup — a zoomed/stretched bot screen for attention-grabbing
- Chat area: 320–380px height, typewriter scenarios auto-cycle through 12 demo conversations
- 12 buttons in 3 rows × 4 columns, Menu button first (shows welcome message on load)
- Bigger buttons: 12px padding, .88em font, 1.5px border, clean CSS `:active` feedback
- Button discoverability: "👆 Click any button to explore features live" hint text + intro pulse on Menu button, both dismissed on first click
- Dark mode support via `dark-mode.css` rules for `.hero-bot-screen`, `.pm-btn`, `.bot-menu`, `.bot-hint`

**Part 2 — Brand Row (below demo):**
- 2-column grid (1fr 1fr): Left = hero texts, Right = big logo
- Left: Dynamic tagline (5 phrases cycling with opacity crossfade — zero flicker), sub description, CTAs (Start Free + See Demo), FOMO badges (fire/setup/no card/price)
- Right: Big Sarathi-AI logo (max-width:483px, float animation, drop-shadow)
- Max-width:1300px centered

**Mobile (<900px):**
- Desktop bot screen hides, tall phone-frame-mobile appears instead (620px height on tablet, 560px on phone)
- Phone-frame mockup with same 12 buttons + chat area
- Order: Bot Demo → Logo → Text
- Logo: 322px (tablet), 276px (phone)
- Buttons sized for touch (7px padding, .68em font)

**JavaScript Changes:**
- `_getChatEl()` — viewport-aware chat element selection (desktop vs mobile)
- `_dismissHint()` — fades out hint text + removes intro pulse on first button click
- `_cycleTagline()` / `_fillTagline()` — clean crossfade tagline cycling (opacity 0 → swap content → opacity 1), 4s hold per phrase
- Removed `touchstart` + `preventDefault` hack entirely — standard `click` events only
- CSS `:active` handles press feedback (no .pressed JS class needed)
- `switchShowcase(11)` — starts with Menu/welcome scenario

**Bug Fix — Demo Panel Phone Frames:**
- `.phone-frame{display:none}` (added for hero cleanup) was hiding phone frames globally, including in Telegram Bot and Voice AI demo panels
- Fixed by scoping to `.hero .phone-frame{display:none}` — only hides unused hero phone frame

**CSS Files Updated:**
- `index.html`: Complete hero CSS rewrite (~100 lines), hero HTML restructured, JS button/tagline logic
- `dark-mode.css`: Updated selectors for `.hero-bot-screen`, `.phone-frame-mobile`, `.bot-menu`, `.bot-hint`, removed `.pm-btn.pressed` rule
- `sw.js`: Cache version bumped through v8→v14 across all deployments
- `features.html`: Added SW registration + dark mode CSS link (for features page dark mode fix)

#### Service Worker Cache Versioning Log
| Version | Changes |
|---------|---------|
| v8 | 12 buttons, new tagline, remove Telegram/flag |
| v9 | Full-width layout, bigger phone, dynamic tagline cycling |
| v10 | Viewport-relative sizing, fixed tagline height 3.5em |
| v11 | 1400px centered, 1fr+420px grid, clean crossfade tagline |
| v12 | 2-part hero layout, big bot screen, brand row, hint+pulse |
| v13 | Wider bot screen (82%), Menu first, logo +15% |
| v14 | Fix .phone-frame display:none scope (demo panels) |

### March 28: Dashboard JS Critical Fixes (SW v14→v17h)

Multiple rounds of dashboard debugging to resolve JS errors that broke the entire dashboard.

#### SW v15–v17g (Intermediate Fixes)
- Various dashboard fixes, SA impersonation flow, plan change logic, activation flow improvements

#### SW v17h: Critical JS Syntax + Structure Fixes
- **Literal `\n` in template string**: A Python-escaped `\n` in a JS template literal broke the entire dashboard JS (SyntaxError killed all functions). Fixed to proper newline.
- **Unclosed `<div>`**: Unbalanced div tags in dashboard HTML caused layout collapse.
- **`catch {}` → `catch(e) {}`**: Bare `catch{}` syntax not supported in older browsers / strict parsing. Fixed all occurrences.
- **Cache-Control headers**: Added `Cache-Control: no-cache, no-store, must-revalidate` + `Pragma: no-cache` to dashboard HTML response to prevent stale JS caching.
- Files: `dashboard.html`, `sarathi_biz.py`

### March 28–29: Payment & Subscription Fixes (SW v17i–v17k)

#### SW v17i: Razorpay Amount Bug Fix
- **Bug**: Razorpay Checkout asked user to pay ₹1 instead of ₹199 (or plan price).
- **Root Cause**: Field name mismatches in `schedulePlanChange()`:
  - `order.amount_paise` → should be `order.amount`
  - `order.razorpay_order_id` → should be `order.order_id`
- Files: `dashboard.html`

#### SW v17j: Trial Plan Subscribe Fix (3 Issues)
- **Bug**: Clicking Subscribe on Individual plan (₹199) redirected to Team plan (₹799).
- **Root causes**:
  1. Trial banner "Choose Plan" button used `PLAN_ORDER[indexOf+1]` → gave "team" instead of current plan for trial users
  2. Individual plan card showed "Current" badge with no Subscribe button for trial users (treated trial-individual same as paid-individual)
  3. `schedulePlanChange()` treated same-plan activation (trial→paid individual) as a downgrade instead of upgrade
- **Fixes**: Banner button uses current plan key, plan cards show Subscribe for trial users regardless of matching plan, same-plan with trial status treated as upgrade.
- Files: `dashboard.html`

#### SW v17k: Full Recurring Subscription System + Cancel Feature
Major payment architecture change: switched from Razorpay one-time orders to Razorpay Subscriptions API (recurring auto-pay mandate).

**Dashboard (`dashboard.html`):**
- `schedulePlanChange()` now calls `POST /api/payments/create-subscription` instead of `create-order`
- Razorpay Checkout opens with `subscription_id` (not `order_id` + `amount`)
- Cancel Subscription: Red card at bottom of Subscription tab, owner-only, visible for active subs
- `cancelSubscription()` function: CSRF-protected `POST /api/subscription/cancel`
- Auto-renew indicator: "🔄 Auto-renewing monthly via Razorpay mandate" for active subscribers
- Cancelled notice: "⚠️ Subscription cancelled — active until [date]" for cancelled-but-still-active subs
- i18n keys added: `cancel_sub`, `cancel_sub_q`, `cancel_sub_reason`, `cancel_sub_success`, `cancel_sub_note`, `sub_autorenew`, `sub_cancelled_notice`
- Updated policy text for recurring billing in subscription tab

**Bot (`biz_bot.py`):**
- `/plans` command: Shows "❌ Cancel Subscription" button for active paid subscribers (owner/admin)
- `_payment_callback` handler: Added `cancel_sub` (2-step confirmation), `pay_confirm_cancel` (executes cancel), `pay_back` (dismiss)
- Payment flow: Creates Razorpay subscription via `pay_mod.create_subscription()`, sends `short_url` payment link (instead of web checkout redirect)
- Handler pattern updated: `r"^(pay_|cancel_sub$)"` to match both pay_ prefixed and cancel_sub callbacks

**Backend (`biz_payments.py` — already had full infrastructure):**
- `create_subscription()`: Creates Razorpay Subscription with plan_id, total_count=120
- `ensure_plans_exist()`: Creates Razorpay Plans on startup, cached in `_razorpay_plan_ids`
- All 8 webhook event handlers already implemented (subscription.activated/charged/completed/cancelled/halted/pending, payment.captured/failed)
- `_activate_tenant_from_sub()`: Activates tenant, sets expiry from `current_end`

### March 29: Login, Email, Weblogin Fixes (SW v17l)

#### Google Sign-In Alignment & Reliability (`index.html`)
- **Problem**: Google Sign-In button appeared misaligned and sometimes failed to render (SDK latency).
- **Fix**: Added "Loading Google Sign-In..." placeholder text during SDK load, extracted `_initGoogleSignIn()` function with retry logic at 2s and 5s intervals, fixed `width` parameter to numeric `400` (was string).

#### Unregistered Google User Flow (`index.html`)
- **Problem**: Unregistered user who signed in with Google got a dead-end error message.
- **Fix**: Error message now includes clickable "Start Free Trial →" link that scrolls to #pricing section.

#### Email Deliverability Improvements (`biz_email.py`)
- **Problem**: Emails from Sarathi going to spam folder.
- **5 Fixes**:
  1. `Message-ID` header with proper domain format
  2. `MIME-Version: 1.0` header
  3. `List-Unsubscribe` header with mailto link
  4. `X-Mailer: Sarathi-AI/1.0` header
  5. Auto-generated plain text fallback (strips HTML tags) when `text_body` not provided — ensures multipart/alternative MIME structure

#### Weblogin JS Injection Fix (`sarathi_biz.py`)
- **Problem**: Firm names containing quotes or special characters (`'`, `\`, newlines) broke the JS string interpolation in `/api/auth/telegram-login` endpoint, causing "Script error." crash.
- **Fix**: Escape `\` → `\\`, `'` → `\'`, `\n` → `\\n`, `\r` → `\\r` before injecting `firm_name` into JS template string.

### March 29: Error Banner False Positive Filter (SW v17m)

- **Problem**: Mobile users saw persistent "⚠️ JS Error" banner on dashboard, but no actual errors existed in the app code.
- **Root Cause**: Global `window.onerror` handler was catching `"Script error."` at line 0 from cross-origin third-party scripts (Razorpay Checkout SDK, Google Sign-In SDK). Browsers report these as generic "Script error." with no file/line info for security reasons.
- **Fix**: Added filter in `window.onerror` to ignore errors matching ALL of:
  - Message is exactly `"Script error."` or `"Script error"`
  - Line number is 0
  - Source URL is empty or from external domains
- Files: `dashboard.html`

#### Service Worker Cache Versioning Log (v17h–v17m)
| Version | Changes |
|---------|---------|
| v17h | Dashboard JS syntax fix (literal \n), unclosed div, catch{} compat, Cache-Control headers |
| v17i | Razorpay amount field name mismatch fix |
| v17j | Trial plan subscribe fix (banner button, plan card, same-plan activation) |
| v17k | Full recurring subscriptions + cancel subscription (dashboard + bot) |
| v17l | Google Sign-In reliability, unregistered user flow, email deliverability, weblogin JS fix |
| v17m | Error banner cross-origin Script error filter |

### April 2026: Auth Overhaul, Affiliate Polish, Hero Fixes, E2E Launch Readiness

#### April 1–3: Homepage Hero Overhaul + Dashboard Voice AI Demo
- **Hero section Phase B:** Complete hero overhaul with Voice AI demos
  - Voice AI tab in Interactive Demo: animated waveform demos, confidence scoring visualization
  - Dashboard tab redesigned: mobile-friendly demo integrating Voice AI features
  - Horizontal scroll buttons for feature cards with overlay positioning fix
  - 5 cycling tagline phrases with crossfade animation (no flicker)
- **Hero flickering fix:** All cycling panels use `position: absolute` inside fixed-height containers — eliminates layout shift during transitions
- **Dashboard overhaul:** `dashboard.html` expanded (~4,985 lines) with mobile-optimized layout and Voice AI integration demo

#### April 3–4: Affiliate System E2E Fixes
- **`_get_affiliate_from_token()` extraction fix:** Properly extracts JWT from `Authorization: Bearer <token>` header (was failing to parse token)
- **Google Sign-In auto-login:** Both `/api/affiliate/register/google` and `/api/affiliate/login/google` now return JWT for immediate auto-login (previously required separate login step)
- **OTP verify auto-login:** `/api/affiliate/verify` and `/api/affiliate/login/verify` return JWT for auto-login after OTP verification
- **Tab default names fix:** Affiliate dashboard tabs display correct default names

#### April 4: Super Admin, Email, Ticket System
- **Ticket detail bug fix:** `superadmin.html` `openTicket()` fixed response destructure — uses `d.ticket` + `d.messages` (was trying to use flat response)
- **Email sender identity:** Added `Sender` header and updated `Reply-To` to use configured business email in `biz_email.py`
- **IST timestamps in tickets:** All ticket timestamps display in IST with relative time ("2 hours ago", "3 days ago") in superadmin.html
- **Gmail "Send mail as":** Configured `info@sarathi-ai.com` as sender via Gmail "Send mail as" + Cloudflare Email Routing

#### April 5: Critical Auth Fixes + Security + Database Fix (LAUNCH DAY PREP)
- **CRM signup broken for new email users — FIXED:**
  - Root cause: `sendSignupOTP()` in `index.html` called `/api/auth/send-email-otp` which returns 404 for non-existent users
  - Fix: Created 2 new endpoints in `sarathi_biz.py`:
    - `POST /api/auth/send-signup-otp` — sends OTP to ANY email without requiring existing account (409 if email already registered)
    - `POST /api/auth/verify-signup-otp` — verifies OTP only, returns `{verified, email}`, does NOT create account
  - Updated `index.html` signup flow: send-signup-otp → verify-signup-otp → /api/signup (3-step)
- **OTP log leak — FIXED:** Removed actual OTP value from log message in `biz_auth.py` line 288 (`"OTP generated for %s: %s"` → `"OTP generated for ***%s"`)
- **interaction_type column error — FIXED:** Two SQL queries in `biz_database.py` used `i.interaction_type` instead of `i.type`:
  - `get_agent_followups_with_time()` (L5303): `i.interaction_type as type` → `i.type as type`
  - `get_agent_weekly_stats()` (L5345): `interaction_type='follow_up_scheduled'` → `type='follow_up_scheduled'`
  - This was causing `sqlite3.OperationalError` every minute from `biz_reminders.py` (proactive follow-up nudge + weekly momentum)
- **Yahoo email deliverability:** Confirmed emails ARE being sent successfully. Yahoo likely spam-filtering. SPF includes Google. No DMARC record exists (recommended to add)
- **Comprehensive E2E auth audit:** All 13 CRM auth endpoints + 6 affiliate auth endpoints verified working
- **All 4 files deployed:** sarathi_biz.py, biz_database.py, biz_auth.py, index.html → server restarted → health 200 ✅

#### Files Changed (April 2026)
| File | Changes |
|------|---------|
| `sarathi_biz.py` | +2 new endpoints (send-signup-otp, verify-signup-otp) |
| `biz_database.py` | Fixed 2 SQL queries (interaction_type → type) |
| `biz_auth.py` | OTP log redaction (security fix) |
| `biz_email.py` | Sender header, Reply-To update |
| `index.html` | Signup flow fix, hero Voice AI demos, hero flickering fix, scroll buttons |
| `dashboard.html` | Mobile Voice AI demo overhaul |
| `superadmin.html` | Ticket detail fix, IST timestamps |
| `partner.html` | Auto-login on OTP verify + Google, IST timestamps |

---

## 29. PWA (Progressive Web App)

### Files
- `static/manifest.json` — App manifest (standalone, theme #0d9488, background #ffffff)
- `static/sw.js` — Service Worker (cache version: `sarathi-v17m`)

### Service Worker Strategy
- **Network-first**: HTML pages, `/api/`, `/health`, `/login`, `/webhook` (always fresh)
- **Cache-first**: `/static/` assets (CSS, JS, images — fast loads)
- **Auto-update**: `skipWaiting()` + `clients.claim()` on new SW install
- **Pre-cache**: Homepage, dark-mode.css/js, icons, logo, favicon

### Routes (sarathi_biz.py)
- `GET /sw.js` → FileResponse with `Cache-Control: no-cache`, `Service-Worker-Allowed: /`
- `GET /manifest.json` → FileResponse with `application/manifest+json`

### Icons
| File | Size | Purpose |
|------|------|---------|
| `icon-512x512.png` | 512x512 | High-res icon (purpose: any) |
| `icon-192x192.png` | 192x192 | Standard icon (purpose: any) |
| `app-icon-512.png` | 512x512 | Maskable icon (white bg, centered in safe zone) |
| `app-icon-192.png` | 192x192 | Maskable icon (white bg, centered in safe zone) |
| `icon-180x180.png` | 180x180 | Apple touch icon |
| `icon-32x32.png` | 32x32 | Browser tab |
| `favicon.ico` | 32x32 | Favicon |

---

## 30. PRODUCTION INFRASTRUCTURE (Oracle Cloud)

### Server
- **Provider:** Oracle Cloud Free Tier (Always Free VM)
- **IP:** 140.238.246.0
- **OS:** Ubuntu 24.04 LTS
- **User:** `sarathi` (app user), `ubuntu` (SSH user)
- **App Dir:** `/opt/sarathi`
- **Python:** 3.12 in `/opt/sarathi/venv/`

### Domain & DNS
- **Domain:** sarathi-ai.com (Cloudflare registrar)
- **DNS:** Cloudflare proxied A records (sarathi-ai.com + www → 140.238.246.0)
- **SSL:** Cloudflare edge (Flexible mode — HTTPS at edge, HTTP to origin)

### Nginx (/etc/nginx/sites-enabled/sarathi)
- Port 80 listener for sarathi-ai.com + www
- Reverse proxy to `127.0.0.1:8001`
- Static files served directly with 7d cache
- `Service-Worker-Allowed: /` header for SW scope

### systemd (sarathi.service)
- `ExecStart=/opt/sarathi/venv/bin/python sarathi_biz.py`
- `Restart=always`, `RestartSec=3`
- `WorkingDirectory=/opt/sarathi`
- Env file: `/opt/sarathi/biz.env`

### Deployment Flow
```
Local: scp files → ubuntu@140.238.246.0:/tmp/sarathi_deploy/
Server: sudo cp /tmp/sarathi_deploy/* /opt/sarathi/ (+ /static/)
        sudo chown sarathi:sarathi
        sudo systemctl restart sarathi
```

### SSH Access
```
ssh -i "C:\Users\imdus\Downloads\ssh-key-2026-03-03.key" ubuntu@140.238.246.0
```

---

## 31. DATA PROTECTION & BACKWARD COMPATIBILITY

### Data Safety Layers
1. **SQLite WAL Mode** — Atomic writes, crash-safe, reads never block writes
2. **Additive Migrations** — `ALTER TABLE ADD COLUMN` only, never drop/rename
3. **Audit Trail** — Every SA action logged to `audit_log` with timestamp + details
4. **Dead Letter Queue** — Failed messages preserved for manual review
5. **Soft Deactivation** — `is_active=0` preserves all data (leads, agents, policies)
6. **Wiped State** — Core tenant record preserved for audit history
7. **Resilience Module** — Circuit breakers, retry logic, graceful degradation for external APIs
8. **systemd Auto-Restart** — Server restarts within 3 seconds on crash
9. **Backup Script** — `deploy/backup.sh` snapshots DB before deployment

### Backward Compatibility Guarantee
- No schema migration has ever dropped or renamed a column/table
- All new features are additive — existing API contracts never broken
- Feature flags (`feature_overrides` JSON column) enable/disable per tenant without code changes
- Plan-based feature gates respect existing data — upgrading/downgrading preserves all records

---

## APPENDIX: HOW TO USE THIS DOCUMENT

### Starting a New Session
> "Read PROJECT_MASTER_CONTEXT.md — it contains the complete project context. I'm continuing development on Sarathi-AI Business, a voice-first CRM SaaS. The project is at c:\sarathi-business. Python 3.12, server runs on port 8001 via sarathi_biz.py. Production at 140.238.246.0 (sarathi-ai.com). Auth: Email OTP + Google Sign-In. Health monitor runs every 15 min. ngrok domain is nonseparable-undarned-geoffrey.ngrok-free.dev."

### After Making Changes
- New feature → Section 24 Build Log
- New API → Section 5 Endpoints
- New table/column → Section 4 Schema
- New calculator → Section 8 + Section 27
- New scheduled task → Section 14
- Bug fix → Section 23
- Auth change → Section 13
- New health check → Section 18 (Tier 2 Health Monitor)
- Significant work → Section 28 Work Log

---

## 29. SPRINT 9 — APRIL 22 → MAY 1, 2026 (5 SALES FEATURES + HOMEPAGE OVERHAUL + NIDAAN PLAN)

### 29.1 Five new sales features (ALL DEPLOYED & VERIFIED)

**Feature 1 — Drip Nurture Sequences (Apr 22)**
- File: `biz_nurture.py` + scheduler entries in `sarathi_biz.py`
- 7-touch bilingual EN+HI sequences trigger automatically on `lead.stage` transitions (`new`, `contacted`, `pitched`, `won`, `lost`).
- Channels: Telegram + WhatsApp Evolution + Email; cadence stored in `nurture_sequences` and `nurture_steps` tables; per-lead progress tracked in `lead_nurture_state`.
- Idempotent: every send writes a row in `nurture_sends` keyed on `(lead_id, sequence_id, step_idx)`.
- Honors `lead.dnd` and DPDP consent.

**Feature 2 — Lapse-Risk Prediction (Apr 23)**
- File: `biz_lapse.py`
- Runs daily; scores every active policy in `policies` 30 days before `renewal_date`.
- Heuristic features: months-since-last-payment, premium-vs-income ratio, prior partial payments, customer age band.
- Surfaces top-N at-risk policies in `/api/lapse/risk-list` and pushes a daily Telegram digest to advisor.
- DB: new columns `policies.lapse_risk_score`, `policies.lapse_risk_reason`, `policies.lapse_alerted_at`.

**Feature 3 — Voice → CRM (Apr 23)**
- Extended `biz_ai.py` voice intent map with 6 new business intents: `add_lead_minimal`, `set_call_reminder`, `mark_done`, `update_stage`, `add_note`, `quick_pitch_request`.
- Telegram voice notes are downloaded, sent through Gemini for transcription + intent extraction, then routed to existing CRM handlers.
- Bilingual: pre-translates Hindi → English internally for intent matching, replies in original language.

**Feature 4 — Advisor Microsite (Apr 30)**
- Public URL: `https://sarathi-ai.com/m/{slug}` (rate-limited 60/min).
- New tenant columns: `microsite_slug` (unique partial index), `microsite_bio`, `microsite_years_exp`, `microsite_families_served`, `microsite_services` (JSON), `microsite_testimonials` (JSON), `microsite_show_badge`, `microsite_published`, `microsite_photo`, `microsite_views`.
- New helpers in `biz_database.py`: `_slugify_microsite`, `get_tenant_by_microsite_slug`, `is_microsite_slug_available` (with reserved blacklist), `suggest_microsite_slug`, `increment_microsite_view`.
- Routes in `sarathi_biz.py`: `GET /m/{slug}`, `GET/POST /api/microsite/settings`, `POST /api/microsite/upload-photo`, `POST /m/{slug}/lead`, `GET /api/microsite/qr`, `GET /api/microsite/check-slug`.
- Template: `static/microsite.html` — self-contained mobile-first page; 12 calculator modals; lead form with DPDP checkbox; sticky bottom bar with `tel:` + `wa.me/{phone}` + form CTA.
- Lead capture: writes to `leads` with `source="microsite"`, marks `dpdp_consent=1`, sends Telegram alert + email to advisor.
- Bot command: `/microsite` (bilingual) shows public URL + view count + status badge.
- Photo upload: JPEG/PNG ≤ 500KB, magic-byte checked, saved to `/uploads/microsite/tenant_{id}.{ext}`.
- Plan-gated: only Team/Enterprise plans can hide the "Powered by Sarathi-AI" badge.
- Live test tenant: `rahul-vyas` at `/m/rahul-vyas`.

**Feature 5 — Quote Compare (Apr 23)**
- File: `biz_quotes.py`
- Compares 8 term + 8 health + ULIP + SIP providers; rate-cards uploadable per tenant via `/api/quotes/upload-ratecard`.
- Generates branded PDF via `quotes.generate_comparison_html_v2`, stored in `/reports/`.
- Endpoints: `POST /api/quotes/compare`, `GET /api/quotes/ratecards`, `POST /api/quotes/upload-ratecard`.

### 29.2 Homepage overhaul (Apr 30 → May 1)

- **Hero copy** changed to mythological framing: *"Arjun had Krishna. You have Sarathi-AI.com"* with subline *"India's voice-first CRM — built for financial advisors who play to win."* Bilingual EN/HI via `data-i18n-html="hero_h1"`.
- **Features section** replaced 8-card generic grid with **6 Killer Features grid** (the 5 sales features + Marketing Studio "SOON" badge), plus a slim 6-card foundational row. Heavy 6-panel `#demo` content hidden (only header + CTA to `/demo` remains) to slim the page.
- **Voice walkthrough widget** (`#voiceWalkBtn` + `#voiceWalkPanel`):
  - Floating bottom-left teal pill, pulses on first load.
  - Browser-native `speechSynthesis` API — no audio files, no server endpoints.
  - Auto-opens panel + auto-plays in **हिंदी** on first visit (after first user gesture). `localStorage.vw_played` flag prevents replay.
  - Picks **female voice** by name match (Heera, Swara, Aditi, Priya, Zira, Samantha) + raised pitch 1.15.
  - Controls: EN/HI toggle, Play/Pause/Stop. Pause/Stop highlighted with amber pulse for 5s on auto-start.
  - "🔕 Don't show this again" → sets `localStorage.vw_hide` and removes the floating button.
- Service-worker bumped to `sarathi-v27` to force cache refresh.

### 29.3 Feature 4 polish (May 1)

- **Auto-suggest slug**: `/api/microsite/settings` already returns a generated slug when none saved; dashboard JS uses it as default in the input.
- **Live preview iframe** in dashboard `#tab-microsite`: shows the actual `/m/{slug}` page in a phone-frame card with Mobile/Tablet/Desktop size toggles. Auto-refreshes after Save with `?preview={ts}` cache-bust.
- **Microsite URL in PDFs**: `_footer_html` in `biz_pdf.py` now renders a teal CTA chip *"🌐 Visit my page: https://sarathi-ai.com/m/{slug}"* when `brand['microsite_url']` is set.
- **Plumbing**: `_build_brand` in `sarathi_biz.py` accepts new `microsite_url` arg; all 12 `/api/report/{calc}` endpoints accept new `microsite_url` query param. Bot's calculator flow auto-derives the URL from `tenant.microsite_published + microsite_slug`.

### 29.4 Security header fix (May 1)

- `biz_auth.get_security_headers()` was returning `X-Frame-Options: DENY`, which conflicted with `SAMEORIGIN` set elsewhere and broke the dashboard live-preview iframe.
- Changed to `SAMEORIGIN` so dashboard can iframe `/m/{slug}` while still blocking cross-origin embedding.

### 29.5 Known limitations after Sprint 9

- Public microsite (`/m/{slug}`) is currently English-only. **Item 5 in next sprint:** add HI translations + auto-detect from `navigator.language`.
- PDFs and microsite footer don't yet display the mandatory **"Insurance is the subject matter of solicitation"** SEBI/IRDAI line. **Item 6 in next sprint.**
- No audit-log entries yet for microsite events (settings update, publish, photo upload, lead received). **Item 7 in next sprint.**
- No analytics dashboard for lead-source ROI / conversion funnel / advisor leaderboard. **Item 8 in next sprint.**
- No bulk `wa.me` broadcaster yet. **Item 9 in next sprint.**
- Marketing Content Studio (AI templates + scheduler + Web Share) is shown on homepage as "SOON" but not built. **Item 10 in next sprint.**

---

## 30. NIDAAN PARTNER — UPCOMING SEPARATE PRODUCT (PLAN LOCKED, MAY 2, 2026)

> **Status:** Architecture v2 (plug-and-play) **LOCKED**. Detailed build plan lives in `NIDAAN_BUILD_PLAN.md`. **Phase 1a COMPLETE (May 3, 2026)** — homepage live at https://nidaanpartner.com, SSL active, host-header routing deployed. Phase 1b (DB scaffold) next.
> **Companion doc:** [NIDAAN_BUILD_PLAN.md](NIDAAN_BUILD_PLAN.md) — table DDLs, route specs, phased acceptance criteria.

### 30.1 Product overview

- **Brand:** Nidaan — The Legal Consultants LLP (existing real-world legal/insurance-claims firm; trademarked logo provided).
- **Reference site:** https://nidaanlegalindia.com/ — aesthetic and content reference.
- **Domain:** `nidaanpartner.com` (purchased on Cloudflare; DNS not yet pointed to VM).
- **Positioning:** Legal-claims dispute-resolution service for insurance advisors. Sarathi-AI is a **lead-generation channel** for Nidaan's legal team. Nidaan handles the actual dispute work; we route leads + show status updates.
- **Reference brochure (Hindi):** `c:\Users\imdus\Downloads\NIDAAN BROCHER HINDI.pdf` — to be parsed in Phase 1a for content + claim categories (translate Hindi-only items to English).

### 30.2 Subscription model (Nidaan plans)

| Plan | Quarterly | Annual | Claims/month | Sarathi-AI bundled tier | Logins |
|------|-----------|--------|--------------|--------------------------|--------|
| **Silver**   | ₹1,500 | ₹6,000  | 3 | Solo       | 1 |
| **Gold**     | ₹3,000 | ₹12,000 | 6 | Team       | 5 |
| **Platinum** | ₹6,000 | ₹24,000 | Unlimited (soft cap 100/yr) | Enterprise | Unlimited |

- Nidaan subscription **bundles Sarathi-AI CRM access** at the matching tier.
- **Per-claim direct-to-consumer review = ₹999** (one-time, for insured customers without an advisor — distinct from agent plans).
- Sarathi-AI-only customers do **not** automatically get Nidaan access; they can upgrade or buy a per-claim review.

### 30.3 Cross-product flows

- **Sarathi homepage** → "Claims" CTA → `nidaanpartner.com` (cold prospect).
- **Sarathi dashboard** → "Claims" tab → "Add Claims Service" or "Open Nidaan Partner Dashboard" (state depends on `product_link` row).
- **Nidaan dashboard** → twin buttons: "Open Sarathi-AI CRM" + stay on Nidaan.
- Cross-domain SSO via signed 60-second one-time token (cookies cannot be shared across the two registered domains).

### 30.4 Plug-and-play architecture (LOCKED)

```
ONE FastAPI app, ONE SQLite DB, ONE VM. Two Nginx server-blocks routed by Host: header.

  sarathi-ai.com  ──►  tenants, leads, policies, ...   (UNCHANGED)
                                  ╲
                                   ╲   product_link  ◄── thin bridge
                                  ╱   (the only join)
  nidaanpartner.com  ──►  nidaan_accounts, nidaan_users, nidaan_subscriptions,
                          nidaan_claims, nidaan_claim_status_log,
                          nidaan_admins, nidaan_per_claim_purchase,
                          nidaan_plan_quota
```

- All Nidaan code in new module **`biz_nidaan.py`**; routes mounted under `/api/nidaan/...` and gated by host-header check.
- **Sarathi schema impact = 2 columns only:** `tenants.plan_source` ('self_paid'|'nidaan_bundle') + `tenants.bundled_until` DATE.
- **Removal procedure** (if partnership ends): drop nginx server-block → drop `nidaan_*` tables → delete `biz_nidaan.py` → reset `tenants.plan_source` rows. Sarathi keeps running with zero schema rewrite.

### 30.5 Bundling lifecycle

- On Nidaan plan purchase (Razorpay webhook): create/find Sarathi tenant by email → set `plan = mapped_tier`, `plan_source='nidaan_bundle'`, `bundled_until=current_period_end` → insert `product_link` row.
- Daily cron: if Nidaan sub lapsed, enter 30-day grace for the bundled Sarathi tenant (warn at day 7, 1, 0) → downgrade to `trial` and reset `plan_source='self_paid'`.
- Partnership-end script: 30-day notice email to all bundled tenants, then standard cron handles downgrades.

### 30.6 Nidaan admin roles

| Role | Capabilities |
|------|--------------|
| **Super Admin** | Everything: manage admins, freeze partnership, refund any amount, view all accounts/claims/revenue. |
| **Sub-Super Admin** | Same as super-admin EXCEPT manage admins, freeze partnership, **refunds (₹0 cap — all refunds need super-admin)**. |
| **Legal Agent** | View claims assigned to them, update status, add internal notes. Cannot see billing or other agents' claims. |
| **Account Owner** | File claims, view own claims, manage sub-users (Gold/Platinum), manage subscription. |
| **Sub-User** | File claims (counts to account quota), view own claims, no subscription rights. |

### 30.7 Locked decisions (May 2, 2026)

| # | Decision | Value |
|---|----------|-------|
| 1 | Architecture | Plug-and-play v2 (separate `nidaan_*` tables + `product_link` bridge) |
| 2 | Per-claim direct-to-consumer fee | **₹999** |
| 3 | SMS provider | **Fast2SMS** (Jio DLT registration in progress; awaiting approval) |
| 4 | Sub-super-admin refund cap | **₹0** (all refunds via super-admin) |
| 5 | Bilingual approach | Same as Sarathi (toggle + auto-detect from `navigator.language`); storage key `localStorage.nidaan_lang` |
| 6 | Phase 1 first deliverable | **Homepage + DNS + Nginx (Phase 1a)** for Nidaan LLP team validation; DB scaffold (1b) in parallel |
| 7 | Brochure | Pull max content (HI + EN); translate Hindi-only sections to English |
| 8 | Cloudflare DNS | Domain just purchased; DNS setup is part of Phase 1a checklist |
| 9 | Sensitive docs | **NOT stored.** Only insured contact info captured; Nidaan team takes documents offline |

### 30.8 SMS automation (Fast2SMS, DLT pending)

7 DLT templates required (registered EN + HI variants on Fast2SMS dashboard):

1. `NIDAAN_CLAIM_NEW_AGENT` — claim filed confirmation to advisor
2. `NIDAAN_CLAIM_NEW_INSURED` — claim filed alert to insured customer
3. `NIDAAN_CLAIM_NEW_OPS` — claim filed notification to Nidaan ops number
4. `NIDAAN_STATUS_AGENT` — status change to advisor
5. `NIDAAN_STATUS_INSURED` — status change to insured
6. `NIDAAN_PERCLAIM_RECEIPT` — ₹999 review purchase receipt
7. `NIDAAN_PERCLAIM_OUTCOME` — review outcome notification

Sender ID: register `NIDAAN` (6-char transactional). DLT entity ID + per-template IDs go to env once Jio approves.

`biz_sms.py` (currently a stub) gets a `Fast2SMSProvider` class + `send_nidaan(template_id, to, vars)` helper in Phase 3.

### 30.9 Phased build (acceptance criteria in `NIDAAN_BUILD_PLAN.md`)

- **Phase 1a — Domain + bilingual homepage** (no DB changes; visible quick win for LLP validation).
- **Phase 1b — DB schema + `biz_nidaan.py` skeleton** (parallel to 1a; additive migration only).
- **Phase 2 — Auth + Razorpay subscriptions + cross-product SSO + bundling cron**.
- **Phase 3 — Nidaan dashboard + dynamic claim form + quota + Fast2SMS automation + admin panels**.
- **Phase 4 — ₹999 per-claim direct-to-consumer flow + revenue/funnel analytics**.
- **Phase 5 — Sarathi cross-promo (Claims CTA on homepage + dashboard tab)**.

### 30.10 Sprint 9 follow-up — security header fix (May 1, 2026)

Root cause of dashboard live-preview iframe failure: Nginx was adding `X-Frame-Options: DENY` with the `always` flag, which overrode the backend's `SAMEORIGIN` header. Patched both `deploy/nginx-prod.conf` and `deploy/nginx-sarathi.conf` (and the live server's `/etc/nginx/sites-available/sarathi-ai.com`) to `SAMEORIGIN`. Iframe now loads. (`biz_auth.get_security_headers()` already returned `SAMEORIGIN` after the earlier fix — this was the missing piece at the nginx layer.)

---

*This document is the single source of truth for the Sarathi-AI Business project. Keep it updated after every significant change.*

*Last updated: May 2, 2026*
