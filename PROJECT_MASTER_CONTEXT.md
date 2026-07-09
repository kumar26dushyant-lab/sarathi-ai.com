# SARATHI-AI BUSINESS — MASTER PROJECT CONTEXT

> **Purpose:** Single source of truth for project recovery. If a development session is lost, feed this document to a new session to restore full context instantly.
>
> **Last Updated:** June 17, 2026 (Section 40 covers June 11–17 — ₹499 value-first funnel end-to-end, WhatsApp/email parity, ops lead pipeline, DPDP lead-retention + account-erasure, recurring-billing fix, SMTP :465 + Brevo, zero-downtime blue-green deploy + path-unit deploy-automation fix, Sprint F security/DR with encrypted AWS S3 Mumbai offsite, dashboard bug fixes. Section 38 covers June 10. Section 37 covers Phase B, June 7–9.)
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
32–36. *(Migration + hardening, marketing studio v2, WhatsApp P0, Nidaan price drop)*
37. [Phase B Lifecycle Hardening (June 7–9, 2026)](#37-lifecycle-hardening--phase-b-june-79-2026)
38. [Post-Phase-B Work (June 10, 2026)](#38-post-phase-b-work--june-10-2026) — `[object Object]` sweep, Nidaan top ribbon, SW v2
39. [Cybersecurity Track Plan](#39-cybersecurity-track--plan-kicked-off-june-10-2026) — Sprints D, E, F

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
| **Email** | Gmail SMTP via App Password (FROM = kumar26.dushyant@gmail.com after May 28 — direct sender for SPF/DKIM alignment); Brevo HTTPS API auto-takes over if BREVO_API_KEY is set (free 300/day) — Resend also supported via RESEND_API_KEY |
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
| `biz_whatsapp.py` | ~718 | WhatsApp Cloud API: send/receive, wa.me fallback (Meta token expired — wa.me fallback in use) |
| `biz_whatsapp_evolution.py` | ~200 | Evolution API v2.2.3 gateway: `send_text()`, `is_enabled()`, `_normalize_phone()` — primary WhatsApp automation channel |
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

### Admin Automation (1)
```
POST /api/admin/trigger-scan  — Manually trigger automation scan (birthday|anniversary|renewal|followup|nurture). Owner-only.
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
- **Evolution API (primary):** `biz_whatsapp_evolution.py` — Connected via instance `sarathi_t9` on Hetzner (`5.223.64.25:8080`), routed through Webshare residential proxy. State: open. Phone: `918875674400`.
- **Meta Cloud API (secondary/fallback):** WhatsApp Cloud API token expired Feb 20, 2026. wa.me deep link used as final fallback when Evolution is not connected (503 response triggers browser redirect).
- Multi-tenant: per-tenant `wa_phone_id` + `wa_access_token` (Meta) + `wa_instances` table rows (Evolution)

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

### Nidaan Bundle Integration (May 2026)

Nidaan plans bundle Sarathi-AI CRM access. Bundled tenants are identified by `plan_source='nidaan_bundle'` and `bundled_until DATE`. `check_subscription_active()` in `biz_database.py` returns True if today ≤ `bundled_until` regardless of `subscription_status`.

| Nidaan Plan | Sarathi Tier Bundled |
|-------------|---------------------|
| Silver / Silver Annual | Individual |
| Gold / Gold Annual | Team |
| Platinum / Platinum Annual | Enterprise |

**Double-subscription block** — `POST /api/payments/create-subscription` checks if calling tenant already has an active Nidaan bundle matching the requested plan and returns HTTP 409 with `{blocked_by_bundle: true}`. Frontend shows a friendly message instead of opening Razorpay.

**Magic-link SSO** — `POST /nidaan/api/sarathi/access`: Nidaan JWT → verifies active Nidaan sub + plan has `sarathi_bundle: True` → provisions Sarathi tenant on-demand → returns Sarathi JWT + redirect URL (`/dashboard?token=…`). Called by Nidaan dashboard "Open Sarathi CRM" button.

### Payment Webhooks

| Webhook | URL | Who |
|---------|-----|-----|
| Sarathi subscriptions | `POST /api/payments/webhook` | Razorpay events for Sarathi plans |
| Nidaan subscriptions | `POST /nidaan/api/webhook` | Razorpay events for Nidaan plans; on activation calls `_provision_sarathi_bundle()` |

### UPI Recovery Flow (May 2026)

UPI payments on mobile cause browser context loss (app-switch) — Razorpay's `handler` never fires. Implemented a recovery pattern mirroring Nidaan's existing approach:

1. **Frontend (dashboard.html)**: Before `rzp.open()`, saves `{order_id, plan, ts}` to `sessionStorage('sarathi_pending_order')`.
2. **On success**: Removes sessionStorage, redirects to `/dashboard?payment=success` (toast banner instead of `alert()`).
3. **On dashboard init**: If `?payment=success` in URL → shows 7-second success toast → cleans URL. Otherwise checks sessionStorage for pending order ≤30 min old → polls recovery endpoint.
4. **Backend (GET /api/payments/check-order)**: Fetches order from Razorpay API, verifies `tenant_id` in notes matches caller (security), fetches captured payment, calls `activate_from_api_verified_payment()`.
5. **`activate_from_api_verified_payment()` (biz_payments.py)**: Idempotent activation without HMAC — uses Razorpay API server-to-server verification. Checks `is_payment_processed()` first, then `record_payment_processed()` + `update_tenant()`.

### Key Backend Functions (biz_payments.py)

```python
activate_from_api_verified_payment(tenant_id, plan_key, order_id, payment_id, amount_paise)
  → {"activated": True, "plan": ..., "expires": ...}
  → {"already_activated": True}   # idempotent
verify_and_activate(...)           # HMAC-verified path (normal Razorpay handler flow)
create_subscription(...)           # Razorpay Subscription API
process_webhook_event(...)         # 8 event handlers
```

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
SMTP_PASSWORD=[REDACTED]          # Gmail App Password — see biz.env on server
SMTP_FROM_EMAIL=info@sarathi-ai.com  # "Send mail as" via Cloudflare Email Routing + Gmail alias
GOOGLE_CLIENT_ID=903535788143-...apps.googleusercontent.com
SA_ALERT_EMAIL=kumar26.dushyant@gmail.com  # Health monitor alert recipient
GDRIVE_CLIENT_ID=                  # not configured
GDRIVE_CLIENT_SECRET=
GDRIVE_REDIRECT_URI=...
# --- Nidaan Partner (add to /opt/sarathi/biz.env on server) ---
NIDAAN_ADMIN_TOKEN=...             # random 32-byte hex; gates all /nidaan/api/admin/* routes
NIDAAN_ADMIN_EMAIL=...             # email that receives ₹499 review-request notifications
# NIDAAN_RAZORPAY_KEY_ID + NIDAAN_RAZORPAY_KEY_SECRET can share the Sarathi Razorpay account or be separate; if omitted, Sarathi Razorpay creds are used.
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
- **Domains:** sarathi-ai.com + nidaanpartner.com (Cloudflare registrar)
- **DNS:** Cloudflare proxied A records for both domains + `www.*` → **84.247.172.252** (Contabo, migrated May 28, 2026)
- **SSL:** Cloudflare Full (Strict) + Let's Encrypt cert covering all 4 hostnames (sarathi-ai.com, www.sarathi-ai.com, nidaanpartner.com, www.nidaanpartner.com)

### Nginx (/etc/nginx/sites-enabled/sarathi)
- Single config covers both domains (server_name list)
- Port 443 listener + 80→443 redirect
- Reverse proxy to `127.0.0.1:8001`
- Static files (`/static/`, `/uploads/`, `/api/video/file/`) served directly with cache
- `Service-Worker-Allowed: /` header for SW scope
- `**Permissions critical**: `/opt/sarathi` must be `755` (others have rx for nginx traversal); do NOT use `750` — that 403s everything

### systemd (sarathi.service)
- `ExecStart=/opt/sarathi/venv/bin/python sarathi_biz.py`
- `Restart=always`, `RestartSec=5`, `MemoryMax=8G`
- `WorkingDirectory=/opt/sarathi`
- Env file: `/opt/sarathi/biz.env` (mode 600)

### Deployment Flow
```
# From Windows PowerShell:
scp -o StrictHostKeyChecking=no <files> root@84.247.172.252:/tmp/
ssh root@84.247.172.252 \
  "cp /tmp/<file> /opt/sarathi/<dest> && chown sarathi:sarathi /opt/sarathi/<file> \
   && systemctl restart sarathi && sleep 4 && curl -s http://localhost:8001/health"
```

### SSH Access
```
# Contabo (production, May 28, 2026 onward)
ssh root@84.247.172.252           # uses ~/.ssh/id_ed25519

# Hetzner (Evolution API + Webshare proxies, separate box)
ssh -i ~/.ssh/id_ed25519 root@5.223.64.25

# Oracle (stopped May 28; data retained as safety net — do NOT terminate yet)
ssh -i ~/Downloads/ssh-key-2026-03-03.key ubuntu@140.238.246.0
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

> **Status:** Architecture v2 (plug-and-play) **LOCKED**. Detailed build plan lives in `NIDAAN_BUILD_PLAN.md`. **Phase 1a COMPLETE (May 3, 2026)** — homepage live at https://nidaanpartner.com, SSL active, host-header routing deployed. **Phase 1b COMPLETE (May 3, 2026)** — DB tables, biz_nidaan.py skeleton deployed. **Phase 2 COMPLETE (May 4, 2026)** — Auth (signup/login), all 5 page routes, review-request endpoint, Razorpay subscriptions, admin panel, signup email, webhook. Current server commit: `0a27a5b`.
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
- **Per-claim direct-to-consumer review = ₹499** (one-time, for insured customers without an advisor — distinct from agent plans).
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
| 2 | Per-claim direct-to-consumer fee | **₹499** |
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
6. `NIDAAN_PERCLAIM_RECEIPT` — ₹499 review purchase receipt
7. `NIDAAN_PERCLAIM_OUTCOME` — review outcome notification

Sender ID: register `NIDAAN` (6-char transactional). DLT entity ID + per-template IDs go to env once Jio approves.

`biz_sms.py` (currently a stub) gets a `Fast2SMSProvider` class + `send_nidaan(template_id, to, vars)` helper in Phase 3.

### 30.9 Phased build (acceptance criteria in `NIDAAN_BUILD_PLAN.md`)

- **Phase 1a — Domain + bilingual homepage** ✅ COMPLETE (May 3, 2026) — homepage live, SSL, host-header routing.
- **Phase 1b — DB schema + `biz_nidaan.py` skeleton** ✅ COMPLETE (May 3, 2026) — 9 Nidaan tables, all helpers.
- **Phase 2 — Auth + pages + Razorpay subscriptions + review endpoint + admin panel** ✅ COMPLETE (May 4, 2026). See §30.11.
- **Phase 3 — Subscribe flow UI + Email OTP login + claim-status email + Nidaan domain nginx verify**.
- **Phase 4 — ₹499 per-claim direct-to-consumer flow (full Razorpay payment) + admin review-status update**.
- **Phase 5 — Fast2SMS automation + Sarathi cross-promo (Claims CTA on homepage + dashboard tab)**.

### 30.10 Sprint 9 follow-up — security header fix (May 1, 2026)

Root cause of dashboard live-preview iframe failure: Nginx was adding `X-Frame-Options: DENY` with the `always` flag, which overrode the backend's `SAMEORIGIN` header. Patched both `deploy/nginx-prod.conf` and `deploy/nginx-sarathi.conf` (and the live server's `/etc/nginx/sites-available/sarathi-ai.com`) to `SAMEORIGIN`. Iframe now loads. (`biz_auth.get_security_headers()` already returned `SAMEORIGIN` after the earlier fix — this was the missing piece at the nginx layer.)

---

### 30.11 Phase 2 Implementation — May 3–4, 2026

#### DB Tables (9 total, all in `nidaan_migrations` list in `biz_database.py`)

| Table | Purpose |
|-------|---------|
| `nidaan_accounts` | Advisor accounts (email, pw_hash, phone, firm_name, created_at) |
| `nidaan_subscriptions` | Active/cancelled sub per account (plan, razorpay_sub_id, status, period_start/end) |
| `nidaan_claims` | Claims filed (account_id, insured_name, insurer_name, claim_type, disputed_amount, notes, status) |
| `nidaan_claim_status_log` | Immutable audit trail of every claim status change |
| `nidaan_per_claim_purchase` | ₹499 review leads (advisor_*, claim_type, insurer, amount, status, razorpay_sub_id) |
| `nidaan_plan_quota` | Monthly quota tracking per account (claims_used, month) |
| `product_link` | Bridge: `(nidaan_account_id, sarathi_tenant_id)` — enables bundled Sarathi access |
| `nidaan_admins` | Nidaan staff accounts (email, role, pw_hash) |
| `nidaan_users` | Sub-users under Gold/Platinum accounts |

#### Static Pages (all served by host-header routing in `sarathi_biz.py`)

| File | Route | Auth |
|------|-------|------|
| `static/nidaan_index.html` | `GET /` (nidaan host) | Public |
| `static/nidaan_signup.html` | `GET /nidaan/signup` | Public |
| `static/nidaan_login.html` | `GET /nidaan/login` | Public |
| `static/nidaan_dashboard.html` | `GET /nidaan/dashboard` | Nidaan JWT |
| `static/nidaan_review.html` | `GET /nidaan/review` | Public |
| `static/nidaan_admin.html` | `GET /nidaan/admin` | Bearer NIDAAN_ADMIN_TOKEN |

#### API Routes (all in `sarathi_biz.py`, gated by `_is_nidaan_host()` or admin token)

**Auth**
- `POST /nidaan/api/signup` — create account (bcrypt-style SHA256 pw_hash) + fire welcome email
- `POST /nidaan/api/login` — email+password → Nidaan JWT (namespaced `:nidaan` suffix on JWT_SECRET, typ="nidaan")
- `GET  /nidaan/api/me` — fetch own account details (auth required)

**Claims**
- `POST /nidaan/api/claims` — file a new claim (auth required, quota-checked)
- `GET  /nidaan/api/claims` — list own claims (auth required)
- `GET  /nidaan/api/claims/{id}` — single claim + status log

**₹499 Review (per-claim direct-to-consumer)**
- `POST /nidaan/api/review-request` — lead capture (no auth) → saves to `nidaan_per_claim_purchase`, emails admin + advisor

**Subscriptions**
- `POST /nidaan/api/subscribe` — create Razorpay subscription (auth required) → returns `{short_url, subscription_id}`
- `POST /nidaan/api/webhook` — Razorpay webhook for Nidaan events (separate from Sarathi webhook at `/api/payments/webhook`)
  - Handles: `subscription.activated`, `subscription.charged`, `subscription.cancelled`
  - Distinguished by `notes.product == "nidaan"`

**Admin (Bearer NIDAAN_ADMIN_TOKEN)**
- `GET  /nidaan/api/admin/stats` — `{total_accounts, active_subscriptions, total_claims, open_claims, pending_review_requests, plans{}}`
- `GET  /nidaan/api/admin/claims` — all claims with account info (paginated)
- `GET  /nidaan/api/admin/accounts` — all accounts with sub status (paginated)
- `GET  /nidaan/api/admin/review-requests` — all ₹499 review leads (paginated)
- `PATCH /nidaan/api/admin/claims/{id}/status` — inline status update, logs to `nidaan_claim_status_log`

#### Key Business Logic (`biz_nidaan.py`)

```python
NIDAAN_RAZORPAY_PLANS = {
    "silver":   {"amount_paise": 150000, "interval": 3},  # ₹1,500/quarter
    "gold":     {"amount_paise": 300000, "interval": 3},  # ₹3,000/quarter
    "platinum": {"amount_paise": 600000, "interval": 3},  # ₹6,000/quarter
}

async def ensure_nidaan_plans(rzp_key_id, rzp_key_secret)   # idempotent plan creation
async def create_nidaan_razorpay_subscription(...)          # returns {short_url, subscription_id}
async def activate_from_razorpay_webhook(...)               # idempotent; sets sub active + quota
async def create_review_request(...)                        # saves ₹499 lead
async def get_admin_stats() -> dict                         # dashboard metrics
async def get_all_accounts_admin(...)                       # LEFT JOIN with active sub
async def get_review_requests_admin(...)                    # paginated leads list
```

#### Admin Panel (`static/nidaan_admin.html`)
- Dark navy theme (`#0f172a` body, `#1e293b` cards)
- Login gate: paste `NIDAAN_ADMIN_TOKEN` → calls all 4 admin APIs simultaneously
- Stats row: 6 KPI cards
- 3 tabs: Claims (inline status dropdown + update via `PATCH`), Accounts, ₹499 Reviews
- Status badges color-coded (intimated=blue, resolved_won=green, resolved_lost=red, pending_payment=amber)

#### Mobile Nav (nidaan_index.html — Two-Row Layout)
- Row 1: Logo + "Nidaan Partner" brand name (full width, no collision possible)
- Row 2: Horizontally scrollable pill strip — `How It Works · Plans · FAQ · EN/हिं · Sarathi-AI CRM ↗ · Login`
- **Sarathi-AI CRM button**: `href="https://sarathi-ai.com"` by default; JS on init upgrades to `https://sarathi-ai.com/dashboard` if `localStorage.nidaan_token` exists
- **setLang() root-cause fix**: Old code called `a.style.display = ''` on ALL `.nav-links a` — cleared `display:none` from wrong-language `.nav-cta`, causing both EN+HI Login to appear simultaneously. Fixed to explicitly set `display = a.classList.contains(l) ? '' : 'none'` for each anchor.

#### Nidaan JWT Namespace Isolation
- Nidaan JWTs use `jwt_secret + ":nidaan"` (namespaced) and carry `"typ": "nidaan"` claim.
- `_nidaan_admin_auth(request)` checks `Authorization: Bearer <NIDAAN_ADMIN_TOKEN>` via `hmac.compare_digest` (constant-time).
- Cross-use with Sarathi JWTs is impossible: different secret + type check.

---

### 30.12 Authentication & Notification Strategy (LOCKED, May 4, 2026)

#### Login Strategy

| Method | Status | Notes |
|--------|--------|-------|
| Email + Password | ✅ Live | Current primary auth for Nidaan accounts |
| **Email OTP** | 🔜 Phase 3 next | Mirror of Sarathi-AI.com — `POST /nidaan/api/send-email-otp` + `POST /nidaan/api/verify-email-otp`; uses same in-memory OTP pattern as `biz_auth.py`. To be added to `biz_nidaan.py` and `nidaan_login.html`. |
| Mobile OTP | ⏳ Future | After Fast2SMS DLT registration approved |
| Google Sign-In | 🤔 Later | Not planned for Phase 3; revisit after Email OTP is live |

**Decision**: Nidaan login will parallel Sarathi-AI.com login — Email OTP as primary once built, with email+password kept as fallback. No mobile OTP until DLT + Fast2SMS integration is live.

#### SMS / Notification Strategy

| Channel | Status | Provider | Notes |
|---------|--------|----------|-------|
| Email | ✅ Live | Gmail SMTP (same as Sarathi) | Used for signup welcome, review-request alerts |
| SMS (transactional) | ⏳ Pending | **Fast2SMS** | DLT registration in progress with Jio (TRAI mandated). 7 templates planned (see §30.8). Sender ID: `NIDAAN`. |
| SMS (OTP) | ⏳ After DLT | Fast2SMS | Will replace email OTP for login once live |
| WhatsApp | ❌ Not planned | — | Not in scope for Nidaan (separate from Sarathi WA) |

**Decision**: All notifications via email until DLT registration complete. May switch to alternate DLT vendor if Jio approval is delayed. Fast2SMS API integration stub lives in `biz_sms.py`.

---

### 30.13 Phase 3 Pending Items (Priority Order, as of May 4, 2026)

| # | Item | Blocker / Notes |
|---|------|-----------------|
| 1 | **Server config** | Add `NIDAAN_ADMIN_TOKEN` + `NIDAAN_ADMIN_EMAIL` to `/opt/sarathi/biz.env`; restart service. Command: `echo "NIDAAN_ADMIN_TOKEN=$(openssl rand -hex 32)" >> /opt/sarathi/biz.env` |
| 2 | **Register Razorpay webhook** | URL: `https://nidaanpartner.com/nidaan/api/webhook`. Events: `subscription.activated`, `subscription.charged`, `subscription.cancelled` |
| 3 | **Subscribe flow in dashboard UI** | `nidaan_dashboard.html` has no "Subscribe" button. Need plan selector cards (silver/gold/platinum) → call `POST /nidaan/api/subscribe` → redirect to `short_url` |
| 4 | **Email OTP login for Nidaan** | Add `POST /nidaan/api/send-email-otp` + `POST /nidaan/api/verify-email-otp` to `biz_nidaan.py`. Update `nidaan_login.html` to show Email OTP tab. |
| 5 | **Claim status email to advisor** | `PATCH /nidaan/api/admin/claims/{id}/status` should fire email to advisor after status update |
| 6 | **Admin review-request status update** | Admin can view ₹499 leads but can't mark them `in_review` / `completed` |
| 7 | **nidaanpartner.com nginx routing** | Verify domain DNS is pointing to server and Nginx `server_name nidaanpartner.com` block is active |
| 8 | **Nidaan pages in sitemap** | `nidaanpartner.com` pages not in XML sitemap |

#### Git Commits This Session (Nidaan Phase 2)
| Commit | Message |
|--------|---------|
| `253a303` | fix(mobile): nav overflow, sticky CTA alignment, brand text ellipsis on all pages |
| `65b410c` | fix(mobile): setLang clears both nav-cta variants causing double login button overflow |
| `11aeebd` | feat(nav): two-row mobile nav, add Sarathi-AI CRM button with smart redirect |
| `0a27a5b` | feat(nidaan): review-request endpoint, Razorpay subscriptions, admin panel, signup email |

---

---

## 32. NIDAAN INTERNAL OPS PORTAL (Deployed May 2026)

> **URL:** `https://nidaanpartner.com/nidaan/ops`
> **Status:** ✅ Live and running as of commits `905583b` + `2b73657`

### 32.1 What Was Built

A full internal staff operations SPA for Nidaan's claims team. Accessible only on the `nidaanpartner.com` host. Staff authenticate separately from advisors (different JWT secret).

**New DB Tables (in `biz_database.py`):**
```sql
nidaan_staff        -- Staff accounts (name, email, password_hash, role, status)
nidaan_claim_notes  -- Internal notes on claims by staff
nidaan_followups    -- Follow-up tasks for staff per claim
```
**Migration applied:** `ALTER TABLE nidaan_claims ADD COLUMN assigned_to_staff_id INTEGER`

**Business Logic (in `biz_nidaan.py`, ~400 lines added):**
- Staff auth: SHA-256 + salt password hashing, JWT with secret `JWT_SECRET + ":nidaan_staff"`
- Role hierarchy: `super_admin` (rank 2) > `sub_super_admin` (rank 1) > `team_member` (rank 0)
- `_require_staff(request, min_role)` enforces role gates
- Claims ops: `get_claims_ops()` (role-aware filtering), `assign_claim_to_staff()`, `add_claim_note()`, `add_followup()`, `complete_followup()`
- Revenue split: 80% Ashwin / 20% Dushyant via `get_revenue_stats()`
- App health: DB latency, table counts, overdue follow-ups, unassigned claims via `get_app_health()`
- Impersonation: `impersonate_account()` generates advisor JWT (logged as WARNING)
- Account management: `get_all_accounts_admin()`, `create_account_by_admin()`, `admin_update_account()`, `admin_set_account_password()`

**API Routes (in `sarathi_biz.py`, ~20 routes added before `/sitemap.xml`):**
```
GET  /nidaan/ops                                  — SPA shell (nidaan host only)
POST /nidaan/ops/api/login                        — Staff login
GET  /nidaan/ops/api/me                           — Staff profile
GET/POST /nidaan/ops/api/staff                    — List/create (super_admin)
PATCH /nidaan/ops/api/staff/{id}                  — Update staff (super_admin)
GET  /nidaan/ops/api/claims                       — Role-aware claim list
GET  /nidaan/ops/api/claims/{id}                  — Claim detail
POST /nidaan/ops/api/claims/{id}/assign           — Assign to staff (sub_super_admin+)
PATCH /nidaan/ops/api/claims/{id}/status          — Update status
POST/GET /nidaan/ops/api/claims/{id}/notes        — Internal notes
POST /nidaan/ops/api/claims/{id}/followups        — Add follow-up
PATCH /nidaan/ops/api/followups/{id}/done         — Mark done
GET  /nidaan/ops/api/my-followups                 — My pending tasks
GET/POST /nidaan/ops/api/accounts                 — Account list/create
PATCH /nidaan/ops/api/accounts/{id}               — Update account
POST /nidaan/ops/api/accounts/{id}/impersonate    — Get advisor JWT (super_admin)
GET  /nidaan/ops/api/revenue                      — Revenue + split (super_admin)
GET  /nidaan/ops/api/health                       — App health (super_admin)
GET  /nidaan/ops/api/stats                        — Admin stats (sub_super_admin+)
```

**SPA Frontend (`static/nidaan_ops.html`):**
- Dark theme (`#060d1a` / `#22d3ee` cyan accent)
- 7 panels: Overview, Claims, My Follow-ups, Accounts, Staff, Revenue, App Health
- Claims panel: searchable/filterable table → slide-in drawer with full detail, notes, follow-ups, status update, assign dropdown
- Revenue panel: 80/20 split bars, monthly trend, by-plan breakdown
- App Health panel: DB latency, overdue follow-ups, unassigned claims, table counts
- Impersonate opens `/nidaan/dashboard` in new tab with advisor JWT pre-loaded into `localStorage`

**Dashboard Subscription Gate (`static/nidaan_dashboard.html`, commit `2b73657`):**
- Profile and Settings tabs locked behind `data-requires-sub="true"` attribute
- Non-subscribers see a paywall overlay instead of the tab content
- Future-proof: any tab with `data-requires-sub="true"` is automatically gated

### 32.2 Production Staff Accounts (Bootstrapped)

| staff_id | name | email | password | role |
|----------|------|-------|----------|------|
| 1 | Dushyant Kumar | dushyant@nidaanpartner.com | Nidaan@2026!D | super_admin |
| 2 | Ashwin | ashwin@nidaanpartner.com | Nidaan@2026!A | super_admin |

Bootstrap method: `sudo -u sarathi /opt/sarathi/venv/bin/python3 <script>` (DB is owned by `sarathi` user).

### 32.3 What Is ON HOLD (Resume Later)

| # | Feature | Notes |
|---|---------|-------|
| 1 | Password change from ops portal | Currently requires super_admin to use "Edit Staff" panel |
| 2 | Email notification on claim assignment | Fire email to assigned `team_member` when claim assigned |
| 3 | WhatsApp notification on claim status change | Notify advisor when their claim status changes |
| 4 | Ops portal mobile sidebar | Hamburger menu; sidebar currently hidden on small screens |
| 5 | Claims list pagination | Currently hardcoded `LIMIT 200` |
| 6 | Sub-super_admin creation via UI | Dushyant/Ashwin can create team members; sub-admins need UI support |
| 7 | Nidaan D2C ₹499 per-claim flow | Route and payment flow partially built; needs completion |
| 8 | Claim document uploads | PDF evidence uploads for each claim |

---

## 33. SARATHI-AI WHATSAPP AGENT — APK BRIDGE ARCHITECTURE

> **Document source:** `SARATHI-AI WHATSAPP AGENT — COMPLETE TECHNICAL BUILD PLAN.docx`
> **Status:** Architecture reviewed and analyzed. NOT yet built. On hold pending decision.

### 33.1 Concept Summary

The APK-as-bridge approach uses an Android app installed on the advisor's own phone to act as a local proxy between WhatsApp and the Sarathi-AI backend. It avoids Meta's official API entirely (no WABA, no per-message costs). The advisor's own WhatsApp account becomes the AI agent.

**Flow:**
```
Customer → WhatsApp → Advisor's Phone
                         ↓
              [Sarathi Agent APK]
                         ↓ (WebSocket, AES-256-GCM)
              [Node.js WS Server]
                         ↓
              [Python AI Engine (FastAPI)]
                         ↓
              Claude AI → reply text
                         ↓
              [Node.js] → [APK] → WhatsApp reply (via NotificationListenerService)
```

### 33.2 The Document's Proposed Tech Stack

| Layer | Technology |
|-------|-----------|
| Android APK | Kotlin, `NotificationListenerService`, `AccessibilityService`, `ForegroundService` |
| Backend bridge | Node.js (Express + WebSocket `ws` library) |
| AI engine | Python FastAPI + Anthropic Claude + OpenAI Whisper (voice) |
| Database | PostgreSQL (separate from current SQLite) |
| Queue | Bull + Redis (for offline message delivery) |
| Encryption | AES-256-GCM (APK ↔ server) |
| Auth | JWT + bcrypt device tokens |

### 33.3 What Is Technically Feasible (and How)

#### ✅ FULLY FEASIBLE — Core Reply Flow
- `NotificationListenerService` reads every WhatsApp notification (sender name, message text)
- Reply is sent back using the notification's `RemoteInput` action — no root required
- This is the same mechanism WhatsApp Web uses under the hood for quick replies
- Works on Android 8+ (API 26+), all major OEMs

#### ✅ FULLY FEASIBLE — Agent CRM Commands via Self-Message
- Advisor messages their own WhatsApp number → APK detects it → routes to `AGENT_COMMAND`
- AI parses Hindi/English voice or text → extracts CRM intent → executes against DB
- Response sent back to advisor's own number (self-message)
- **This directly replaces the current Telegram bot for advisors who prefer WhatsApp**

#### ✅ FULLY FEASIBLE — Proactive Reminders
- Backend schedules EMI/renewal reminders via Bull cron
- Pushes to APK via WebSocket → APK uses `AccessibilityService` to open WA and send
- `AccessibilityService` is more fragile (per-WA-version UI tree), but works for proactive sends

#### ✅ FULLY FEASIBLE — Voice Note Handling
- APK detects "Voice message" in notification text
- Routes to AI engine → OpenAI Whisper transcribes → Claude extracts intent
- Limitation: APK cannot extract the audio file itself from WA notification; workaround is to ask user to forward voice note to their own number

#### ⚠️ PARTIAL — Multi-Account / Multi-WhatsApp
- Supports WhatsApp Business (`com.whatsapp.w4b`) OR personal (`com.whatsapp`) — **not both simultaneously** per phone
- One APK = one advisor's WhatsApp account = one business
- For team accounts: each agent needs their own phone with APK installed

#### ⚠️ PARTIAL — Proactive Outbound (WAAccessibilityService)
- Opening WA via Accessibility and typing+sending is possible but fragile
- UI element IDs change across WA versions → requires ongoing maintenance
- Document acknowledges this as "skeleton only — full UIAutomator implementation needed"
- Safer alternative: send reminder text to advisor's own number, advisor manually forwards

#### ❌ NOT FEASIBLE — WhatsApp ToS Compliance
- This approach violates WhatsApp's Terms of Service (automation via notification listener)
- Risk: WhatsApp can ban the advisor's phone number
- Meta has historically been aggressive about banning automation tools
- **This is the #1 risk.** Mitigation: rate limiting, human-like delays, no mass blasting

### 33.4 Sarathi-AI Integration Points

The document proposes integrating into the existing Sarathi-AI dashboard with:
- A "Connect WhatsApp Agent" button → generates QR code (encodes device token + AES key + WS URL)
- APK scans QR → authenticates → establishes persistent WebSocket
- Dashboard shows connection status: Connected 🟢 / Offline 🔴

**How it maps to existing Sarathi-AI architecture:**
- The Node.js backend is a **new separate service** (not our FastAPI app) — adds infrastructure complexity
- The PostgreSQL DB is **separate** from our SQLite — needs migration/sync strategy
- The Python AI engine is **separate** from our `sarathi_biz.py` — duplicates some logic
- **Simpler integration path**: embed the WS server + device registry directly into our existing FastAPI app using `websockets` library, keep SQLite

### 33.5 Recommended Simplified Architecture for Sarathi-AI

Instead of 3 separate services (Node.js + Python FastAPI + PostgreSQL), collapse into existing stack:

```
[Sarathi Agent APK] ←WebSocket→ [sarathi_biz.py + /ws/agent endpoint]
                                         ↓
                               [Gemini AI] (already integrated)
                                         ↓
                               [SQLite biz_database.py] (existing tables)
```

**Changes needed:**
1. Add `WebSocket` endpoint to `sarathi_biz.py` (FastAPI natively supports `websockets`)
2. Add `linked_devices` table to `biz_database.py` (device_token_hash, aes_key, tenant_id)
3. Add `pending_messages` table for offline queuing
4. Write the Android APK in Kotlin (Android Studio project)
5. Add "Connect WhatsApp Agent" card to `dashboard.html`
6. Route APK events to existing `biz_ai.py` Gemini for AI responses

**Advantages of simplified approach:**
- One codebase, one DB, one server — no orchestration overhead
- Reuse existing Gemini AI, tenant data, lead/policy tables
- Reuse existing scheduler in `biz_reminders.py` for EMI/renewal triggers
- Advisor identity tied to existing JWT token system

### 33.6 Risk Assessment

| Risk | Level | Mitigation |
|------|-------|-----------|
| WhatsApp ToS ban of advisor number | HIGH | Rate limit replies, add human-like delays, avoid mass outbound sends. Educate advisors. |
| OEM battery kill (Xiaomi/Realme/Oppo) | HIGH | OEM-specific guide in onboarding; `START_STICKY` + `ForegroundService` |
| WA app UI changes break Accessibility sends | MEDIUM | Keep proactive send optional; focus MVP on reply-only flow |
| Phone offline = no automation | MEDIUM | `pending_messages` queue; messages delivered when APK reconnects |
| Voice note file unavailable in notification | LOW | Gracefully detect + ask advisor to forward audio to self |
| Play Store rejection for NotificationListenerService | LOW | Distribute APK via direct download link; no Play Store needed |

### 33.7 Build Sequence (When Ready to Start)

1. Add `WebSocket` route to `sarathi_biz.py` + device registry in-memory
2. Add `linked_devices` + `pending_messages` tables to `biz_database.py`
3. Add device connect/status endpoints: `POST /api/wa-agent/connect`, `GET /api/wa-agent/status`
4. Build Android APK (Kotlin, Android Studio): `WANotificationService` → `CRMWebSocketClient`
5. Test reply flow end-to-end (local ngrok WS tunnel)
6. Add Gemini AI response routing for customer messages
7. Add agent CRM command parsing (reuse existing voice intent system)
8. Add "Connect WhatsApp Agent" UI card to `dashboard.html`
9. Add APK download link to dashboard
10. Deploy and test with real WhatsApp account (test phone)

### 33.8 Decision Points Before Starting

| Question | Recommended Decision |
|----------|---------------------|
| Start with reply-only or full CRM commands too? | Start with reply-only (simpler, less risky) |
| Node.js bridge vs embed in FastAPI? | Embed in FastAPI (fewer moving parts) |
| PostgreSQL vs keep SQLite? | Keep SQLite (no migration needed) |
| Claude vs Gemini for AI? | Keep Gemini (already integrated, cost controlled) |
| Proactive outbound via Accessibility? | Defer to Phase 2 |
| Play Store vs direct APK download? | Direct download link from dashboard |

---

*This document is the single source of truth for the Sarathi-AI Business project. Keep it updated after every significant change.*

*Last updated: May 25, 2026*

---

## 34. WHATSAPP EVOLUTION API INTEGRATION — May 13–14, 2026

### 34.1 Overview

WhatsApp Cloud API token was expired since Feb 20, 2026. To restore full WhatsApp automation, a self-hosted WhatsApp gateway was set up using **Evolution API v2.2.3** (open-source Baileys-based gateway) on a separate Hetzner server, routed through a **Webshare static residential IP** to pass WhatsApp's ASN checks.

### 34.2 Infrastructure

| Component | Details |
|-----------|---------|
| **Evolution API server** | Hetzner VPS `root@5.223.64.25`, Docker container `evolution`, Evolution API v2.2.3 |
| **Evolution port** | `http://localhost:8080` (Hetzner-local), `http://5.223.64.25:8080` (Oracle-external) |
| **Evolution instance** | `sarathi_t9`, connected via QR code (state: open, wuid: `918875674400@s.whatsapp.net`) |
| **Evolution API key** | `[REDACTED — value in biz.env on server; rotate if this doc was ever published]` |
| **Webshare proxy** | SOCKS5 `63.141.58.29:6345`, user `[REDACTED]`, pass `[REDACTED]`, ASN: AS6079 RCN (US cable ISP — genuine residential, NOT datacenter). Credentials live in `biz.env` / Webshare dashboard; rotate if this doc was ever published. |
| **redsocks** | v0.5 on Hetzner, transparently proxies Evolution container (172.18.0.0/16) outbound port 443 through Webshare |
| **redsocks config** | `/etc/redsocks.conf` — `redirector=iptables`, `local_port=12345` |
| **iptables rule** | REDIRECT 172.18.0.0/16 → port 443 → 12345 (redsocks) |

**Why both Hetzner AND Webshare are needed (cannot remove either):**
- **Webshare** = identity layer. WhatsApp checks the IP's ASN. Datacenter IPs (Oracle, Hetzner bare) are blocked. `63.141.58.29` is AS6079 RCN — a US cable ISP — which passes as a genuine residential connection.
- **Hetzner** = execution layer. Oracle Cloud blocks outbound connections to WhatsApp servers on port 443. Evolution API must run on Hetzner. Total cost: Hetzner ~€10/mo + Webshare ~$5/mo ≈ ₹1,300/month for full WhatsApp automation.

### 34.3 New Python Module: `biz_whatsapp_evolution.py`

```python
# Key functions:
send_text(instance_name, to_phone, text, *, delay_ms=0)  # POSTs to /message/sendText/{instance}
_normalize_phone(phone)                                   # → 91XXXXXXXXXX format
is_enabled()                                              # checks EVOLUTION_API_URL configured
```

Environment variables added to `biz.env`:
```env
EVOLUTION_API_URL=http://5.223.64.25:8080
EVOLUTION_API_KEY=[REDACTED — see biz.env on server]
```

DB table added (`wa_instances`):
```sql
CREATE TABLE wa_instances (
    instance_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id          INTEGER NOT NULL,
    evolution_instance TEXT NOT NULL,
    phone_number       TEXT,
    status             TEXT DEFAULT 'connecting',  -- open/connected/connecting/disconnected
    paused_until       TEXT,
    created_at         TEXT DEFAULT (datetime('now')),
    updated_at         TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
```

### 34.4 Endpoints Fixed/Added (sarathi_biz.py)

| Endpoint | Before | After |
|----------|--------|-------|
| `POST /api/wa/send` | Returned `_WA_DISABLED_RESPONSE` stub | Queries `wa_instances` for connected Evolution instance, calls `wa_evo.send_text()` |
| `POST /api/wa/share-calc` | Returned `_WA_DISABLED_RESPONSE` stub | Sends calc summary + report URL via Evolution; falls back to `wa.me` if not connected |
| `POST /api/wa/greeting` | Returned `_WA_DISABLED_RESPONSE` stub | Sends birthday/anniversary message via Evolution; falls back to `wa.me` if not connected |
| `POST /api/nudge` | Telegram-only, crashed on non-numeric `telegram_id` (e.g. `'web_9'`) | Tries Telegram first; WhatsApp fallback to advisor's `wa_phone`/`phone` via Evolution |
| `POST /api/nudge/broadcast` | Filtered to Telegram-only agents; silently skipped agents without Telegram | Includes all agents with phone number; tries Telegram first, WhatsApp fallback for others |
| `POST /api/admin/trigger-scan` | Did not exist | New endpoint: manually fires `birthday`/`anniversary`/`renewal`/`followup`/`nurture` scans — owner-only, for testing without waiting for scheduler |

### 34.5 Automated Scheduler — Evolution Integration

`biz_reminders.py` already had `_evo_send_if_connected(agent_id, phone, message)` wired. All three scheduled scan functions use it:

- **`run_birthday_scan()`** — queries `wa_instances` for agent's tenant, sends birthday WhatsApp directly to lead's phone
- **`run_anniversary_scan()`** — same pattern for anniversaries
- **`run_renewal_scan()`** — sends renewal reminders to client phones

All three functions: try Evolution first → log `channel='whatsapp_evolution'` in `greetings_log` → fall back to Meta Cloud API if not connected.

### 34.6 Dashboard — Direct WhatsApp Send Button

In `dashboard.html`, the green **WhatsApp** pill button next to lead phone numbers was previously an `<a href="wa.me/...">` link (opened browser/app manually). Changed to:

```javascript
async function sendWaDirect(phone, name) {
  // POSTs to /api/wa/send with {phone, message}
  // On success: showToast("WhatsApp message sent ✓", 'success')
  // On 503 (WA not connected): falls back to window.open(wa.me link)
}
function _waDirectBtn(phone, name, opts) {
  // Returns <button onclick="sendWaDirect(...)"> instead of <a href="wa.me">
}
```

Both desktop table and mobile card versions updated. Message sent: `"Hi {first_name}, this is {firm}. Do you have a couple of minutes to chat?"`

### 34.7 Nurture/Drip — WhatsApp Direct Channel

`biz_nurture.py` upgraded:

**New channel type `whatsapp_customer`:**
- Sends the step's `wa_template_en/hi` directly to lead's phone via Evolution API
- No Telegram involvement

**Upgraded `telegram_agent` channel:**
- Now also auto-sends to lead's WhatsApp via Evolution (if connected) BEFORE notifying advisor
- Telegram notification updated: says "✅ WhatsApp message sent automatically to lead." instead of showing a manual wa.me button
- Manual wa.me button only shown if Evolution is not connected

**New helper in `biz_nurture.py`:**
```python
async def _evo_send_direct(tenant_id, agent_id, phone, message) -> bool:
    # Queries wa_instances for tenant's connected instance
    # Calls wa_evo.send_text()
```

### 34.8 Known Issues / Next Steps

| Item | Status |
|------|--------|
| WhatsApp connection via QR code | ✅ Connected (sarathi_t9, phone 918875674400) |
| Pairing code (phone-side linking) | ⏳ Rate-limited — wait 24h between attempts, try only once |
| Multi-tenant proxy | Current: single static residential IP serves all tenants. Works fine. For scale: each tenant may eventually need own IP. |
| WhatsApp session persistence | Evolution maintains session in Docker volume. Reconnects automatically. |
| Meta Cloud API | Still configured as fallback but token expired — wa.me link is actual fallback |

### 34.9 Infrastructure Decision: Hetzner + Webshare (Keep Both)

**Q: Can we drop Hetzner or Webshare to save cost?**

| Service | Role | Can be dropped? |
|---------|------|----------------|
| **Hetzner VPS** (~€10/mo) | Runs Evolution API Docker container. Oracle Cloud blocks outbound WA traffic. | ❌ No — Evolution cannot run on Oracle |
| **Webshare Static Residential** (~$5/mo) | Provides RCN cable ISP IP (AS6079). Without it, WhatsApp blocks the datacenter IP. | ❌ No — datacenter ASN is blocked by Meta |

Both are required for the "solid wall" approach. Total: ~₹1,300/month. For context: one paying Sarathi Team plan customer (₹799/mo) nearly covers this cost. The infrastructure enables WhatsApp automation for ALL tenants.

---

## 35. NIDAAN-SARATHI BUNDLE MECHANICS — May 25, 2026

> **Status:** ✅ Fully deployed. All bundle scenarios E2E tested.

### 35.1 What Was Built This Session

#### Bundle Mechanics Core

| Component | File | Change |
|-----------|------|--------|
| PLAN_LIMITS | `biz_nidaan.py` | All 6 Nidaan plans now have `sarathi_bundle: True` (Silver & Silver Annual were previously `False`) |
| `_provision_sarathi_bundle()` | `biz_nidaan.py` | 5 bugs fixed: wrong INSERT column (`status`→`subscription_status`), missing UPDATE of `subscription_status`, no `agents` owner record created for new tenants, missing Silver/Silver Annual in plan map (`silver`→`individual`), missing `@nidaanpartner.com` staff exclusion |
| `check_subscription_active()` | `biz_database.py` | Added `bundled_until` priority check — if today ≤ `bundled_until`, returns `True` regardless of `subscription_status` (prevents bundled users being locked out) |
| Cancellation grace | `sarathi_biz.py` | `subscription.cancelled/halted/completed` Nidaan webhook events now set `bundled_until = today + 5 days` on linked Sarathi tenant (was: just logging) |
| Double-sub block | `sarathi_biz.py` | `POST /api/payments/create-subscription` blocks if active Nidaan bundle matches requested plan → HTTP 409 with `{blocked_by_bundle: true}` |
| Magic-link SSO | `sarathi_biz.py` | `POST /nidaan/api/sarathi/access` — Nidaan JWT → on-demand provision → Sarathi JWT + redirect URL |
| Signup fraud messaging | `sarathi_biz.py` | All 3 signup locations: removed "trial was already used" message; now always: "An account already exists. Please login instead." |

#### Payment UX Fix (Sarathi)

The Sarathi payment flow had 5 UX problems not present in the Nidaan flow (which had been fixed earlier). All fixed in this session:

| Problem | Fix |
|---------|-----|
| `alert()` for success (native dialog, unprofessional) | Replaced with `showToast()` + redirect to `?payment=success` |
| `location.reload()` — no confirmation after reload | User redirected to `/dashboard?payment=success`, success toast on reload |
| No `sessionStorage` pending order | Added before `rzp.open()` — survives UPI app-switch context loss |
| No `GET /api/payments/check-order` recovery endpoint | Added — mirrors Nidaan's `/nidaan/api/subscribe/check` pattern |
| No `?payment=success` handler in dashboard init | Added — shows 7-second toast, cleans URL with `history.replaceState` |

### 35.2 New API Endpoints Added

| Endpoint | Purpose |
|----------|---------|
| `POST /nidaan/api/sarathi/access` | Magic-link SSO: Nidaan JWT → Sarathi JWT + redirect |
| `GET /api/payments/check-order` | UPI recovery: polls Razorpay API, activates tenant idempotently |

### 35.3 New Functions Added

| Function | File | Purpose |
|----------|------|---------|
| `activate_from_api_verified_payment()` | `biz_payments.py` | Idempotent activation via Razorpay API (no HMAC). Used by check-order endpoint for UPI recovery. |

### 35.4 Files Changed & Deployed

| File | Changes |
|------|---------|
| `biz_nidaan.py` | PLAN_LIMITS Silver fix + `_provision_sarathi_bundle()` 5-bug fix |
| `biz_database.py` | `check_subscription_active()` — bundled_until priority |
| `sarathi_biz.py` | Magic-link endpoint, cancellation grace, double-sub block, signup messaging, `GET /api/payments/check-order` |
| `biz_payments.py` | `activate_from_api_verified_payment()` |
| `static/dashboard.html` | sessionStorage pending order, success redirect, success toast on init, UPI recovery polling |

## 36. MIGRATION + HARDENING SPRINT — May 27–29, 2026

This was the largest infrastructure + product session since launch. Captures the move OFF Oracle, marketing studio v2 redesign, WhatsApp end-to-end fixes, Nidaan price drop, and email deliverability fix.

### 36.1 Infrastructure migration: Oracle → Contabo
- **Old:** Oracle Cloud A1.Flex (free tier) `140.238.246.0` — blocked by capacity shortage for upgrade
- **New:** Contabo Cloud VPS 30 SSD (€11.20/mo) — Ubuntu 24.04 x86_64, 8 vCPU, 24GB RAM, 400GB SSD at `84.247.172.252`
- **Migration files:** `deploy/setup-contabo.sh`, `deploy/migrate-to-contabo.sh` (in repo)
- **DNS:** Cloudflare A records updated `sarathi-ai.com` + `www.sarathi-ai.com` + `nidaanpartner.com` + `www.nidaanpartner.com` → `84.247.172.252`. SSL/TLS mode = Full (Strict)
- **SSL:** Let's Encrypt via certbot for all 4 domains (covered by one cert)
- **Permissions:** `/opt/sarathi` is `755` (nginx www-data needs traversal to serve static); `biz.env` is `600`, `sarathi_biz.db` is `640`. **DO NOT** use `chmod 750` on `/opt/sarathi` — it causes nginx 403 on every static file
- **SSH access:** `ssh root@84.247.172.252` (Contabo) — using `~/.ssh/id_ed25519` keypair
- **Oracle:** Stopped (not terminated) — keeps data preserved as safety net

### 36.2 Marketing Studio v2 (May 28–29)
A complete redesign of image quality:
- **Photo templates** at `static/templates/marketing/*.png` — overlaid with headline + body + advisor logo + soft IRDAI disclaimer
- **Default content_type → template mapping** in `biz_marketing.py::_TEMPLATE_DEFAULT`:
  - `scenario_insurance → imagen_health_hospital_bill`
  - `scenario_investment → imagen_invest_growth_chart`
  - `tip → imagen_invest_sip_chai`
  - `product_pitch → imagen_claim_handshake_advisor`
  - `festival → imagen_festival_diwali`
  - `custom → imagen_advisor_meeting_with_couple`
- **Imagen 4 stock library** generated one-time via `_tools/generate_imagen_templates.py` (script uses Gemini Imagen API, ~₹100 one-time for ~30 templates). Run with `python _tools/generate_imagen_templates.py [optional_slug]`. Note: **negative_prompt is NOT supported on Developer API tier** — must use pure scene descriptions, no quoted format hints, no "no text" instructions (Imagen will literally draw those words)
- **Pexels fallback** via `biz_pexels.py` — if no template_id provided and no default matches, searches Pexels with content-type seed + title hint (`PEXELS_API_KEY` env var). Cached at `uploads/marketing/pexels/<sha>.jpg`
- **Script-aware fonts** — `_font_for(text, size, bold)` detects Devanagari chars (U+0900–U+097F) and picks NotoSansDevanagari-Bold/Regular; everything else uses DejaVu Latin. Same logic in `biz_video.py` (Devanagari videos now render text correctly, no more "boxes")
- **Emoji stripping** — `_strip_emojis()` cleans all Gemini-generated text before render (Pillow can't render color emoji glyphs reliably)
- **Soft IRDAI disclaimer** at bottom: "General awareness post. Please consult your advisor before making a financial decision." (en/hi/mr) — placed by render code, not in source images
- **Advisor logo + co-brand** — top-left = advisor's uploaded logo (or "Your logo here" placeholder); top-right = "by Sarathi AI" co-brand text
- **Marathi (mr) support added** across `marketing_lang`, content prompts, title maps, schedule lang. Hindi remains primary
- **New endpoints**: `POST /api/marketing/upload-logo` + `DELETE`; `GET /api/marketing/templates`
- **New DB columns** (auto-migrated): `tenants.marketing_logo_path`

### 36.3 WhatsApp end-to-end fixes
4 critical fixes against user-stated requirements (C1–C4):

**C1 — Group/broadcast JID filter** (`sarathi_biz.py` webhook handler):
```python
if "@g.us" in remote or remote.startswith("status@") or remote.endswith("@broadcast"):
    return {"ok": True, "ignored": "group_or_broadcast"}
```
Prevents accidental auto-replies inside group chats.

**C2 — EMI / premium-due wording for monthly mode** (`biz_reminders.py::run_renewal_scan`):
- For `premium_mode == "monthly"`, message is now **"💳 Premium Due Reminder"** with amount + due date
- For annual/quarterly, retains **"🔔 Policy Renewal Reminder"**
- Trigger days already correct: `monthly = {7, 3, 1, 0}`, `annual = {60, 30, 15, 7, 3, 1, 0}`

**C3 — Correct agent attribution for CRM commands**:
- Was: always picked first agent of tenant → wrong attribution in multi-advisor teams
- Now: reads `wa_instances.agent_id` (the SIM owner); falls back to first agent only if instance has none (with WARNING log)

**C4 — Policies table injected into AI customer context** (`biz_wa_agent.py::get_lead_context_for_phone`):
- Adds last 3 active policies to the prompt (policy_number, premium, premium_mode, renewal_date, sum_insured, plan_name, insurer)
- Customer asking "मेरा प्रीमियम कब है?" / "renewal date?" now gets factual answer instead of escalation
- Marketed under the "AI-based decision, ask when confused, silent when unrelated" requirement

**Evolution config recovery** — `biz.env` was missing all 4 EVOLUTION_* vars after Oracle migration. Fetched from Hetzner `/opt/evolution/.env` (key value redacted from this doc; it lives only in `biz.env` on the server). Updated webhook URLs on each Hetzner instance via `POST /webhook/set/{instance}` to point at `https://sarathi-ai.com/api/whatsapp/v2/webhook`. Stale `sarathi_t6` row marked `disconnected`.

### 36.4 Email deliverability fix (May 28)
- **Root cause:** Yahoo/Gmail filtering emails to spam because SMTP_FROM=`info@sarathi-ai.com` was authenticated via Gmail (kumar26.dushyant@gmail.com) — SPF/DKIM unaligned with header-from domain
- **Fix:** Changed `SMTP_FROM_EMAIL` / `SMTP_FROM_NOREPLY` / `SMTP_FROM_SUPPORT` to `kumar26.dushyant@gmail.com` so Gmail's own SPF/DKIM authenticates. Sacrifices brand; gains inbox delivery
- **Module support added:** `biz_email.py` now supports 3 transports in priority: **Brevo** (free 300/day) > **Resend** ($20/mo, optional) > **Gmail SMTP** (current fallback). Add `BREVO_API_KEY` to biz.env when ready and the upgrade is silent
- **Verified:** Test OTP arrived in `imdushyant19@yahoo.co.in` inbox (not spam). User confirmed: ₹499 (then ₹999) Nidaan payment + Sarathi affiliate OTP flows work

### 36.5 Nidaan ₹999 → ₹499 price drop (May 29)
**11 files updated** — all-in-one bulk replace of `₹999`/`Rs.999`/`99900` → `₹499`/`Rs.499`/`49900`. Surfaces:
- `biz_nidaan.py` — DB `INSERT amount_paid=499` (2 sites)
- `sarathi_biz.py` — Razorpay `amount=49900` (4 sites: review_pay, review_pay_create_order, etc.) + email subject/body strings
- `static/nidaan_review.html`, `nidaan_dashboard.html`, `nidaan_index.html`, `nidaan_admin.html`, `nidaan_ops.html`, `nidaan_start.html`, `index.html` (Sarathi homepage Nidaan banner)
- `NIDAAN_BUILD_PLAN.md`, `PROJECT_MASTER_CONTEXT.md`
- Internal identifier strings kept unchanged for DB compat: `review_type="per_claim_999"`, Razorpay notes `product="nidaan_review_999"` (purely labels — DB rows reference these)

### 36.6 Marketing pages bug fixes
- **Partner page** (`/partner`): "Join Now" tab now hidden when logged in; "Logout" tab visible when logged in; mobile tabs scroll horizontally; touch targets ≥44px; auto-redirect to Dashboard on page load if already logged in
- **Dashboard mobile**: orange "Complete your profile" banner moved from `position:fixed;top:0;z-index:9990` (was covering topbar) → `position:sticky;top:64px;z-index:40` (inside `.main`, BELOW topbar)
- **Sidebar logout on mobile**: added `padding-bottom: 80px + safe-area-inset` so "🚪 Logout" item sits ABOVE the bottom-nav; also added 🚪 icon-collapse for topbar button under 480px

### 36.7 Homepage WhatsApp demo i18n refactor B
- Replaced legacy `_waMsgs` array + parallel `_waAiHi` arrays with **scenario-based bilingual structure** in `_waScenarios` — each message has inline `txt` + `txtHi`
- 12 scenarios × ~3 messages each = 24 bilingual lines (user inputs + AI replies BOTH translate now, not just AI)
- Render: `const _aiTxt = (_lang==='hi' && msg.txtHi) ? msg.txtHi : msg.txt`
- Dead `_startWADemo` / `_waStep` / `_waMsgs` / `_waAiHi` legacy code removed (~3.5KB chars)

### 36.8 What's still pending after this sprint
| Item | Status |
|---|---|
| Mobile OTP via Jio Connect DLT | ⏸️ Paused — waiting on user's DLT header approval from Jio |
| C5: Renewal-reminder idempotency (T-7 double-send protection) | Pending |
| C6: Birthday/anniversary retry queue (parity with renewals) | Pending |
| C7: Evolution instance failover (graceful degradation if instance down) | Pending |
| C8: Inbound voice notes — distinguish speech transcription from non-speech audio | Pending |
| DMARC TXT records published for both domains (`p=none` monitoring mode) | Pending — user to add in Cloudflare |
| Remove email login completely (keep only Google + Mobile OTP) | Pending DLT |
| Mobile thorough audit | Pending |

### 36.9 Key files / paths (cheat-sheet)
| Concern | Location |
|---|---|
| Marketing image render | `biz_marketing.py::generate_image()` |
| Marketing templates folder | `/opt/sarathi/static/templates/marketing/` |
| Pexels cache | `/opt/sarathi/uploads/marketing/pexels/<sha>.jpg` |
| Imagen generator script | `_tools/generate_imagen_templates.py` |
| WhatsApp webhook handler | `sarathi_biz.py:10380` (`/api/whatsapp/v2/webhook`) |
| WA agent intent classifier | `biz_wa_agent.py::smart_inbound_handler` |
| Evolution API client | `biz_whatsapp_evolution.py` (set on Hetzner `5.223.64.25:8080`) |
| Reminders scheduler | `biz_reminders.py::run_renewal_scan / run_birthday_scan` |
| Email transport | `biz_email.py::send_email` (Brevo → Resend → SMTP fallback) |
| Razorpay Nidaan ₹499 order | `sarathi_biz.py::nidaan_review_pay_by_id` and `nidaan_review_pay` |

---

### 35.5 Bundle Scenario Matrix (All Verified)

| Scenario | Behavior |
|----------|----------|
| New Nidaan signup (any plan incl. Silver) | `_provision_sarathi_bundle()` creates/reactivates Sarathi tenant, creates owner agent record |
| "Open Sarathi CRM" from Nidaan dashboard | Magic-link SSO: issues Sarathi JWT, redirects to `/dashboard` |
| Nidaan sub cancelled/halted | Sarathi gets 5-day grace period (`bundled_until = today+5`), then access expires |
| Bundled Sarathi user tries to pay for matching plan | Blocked with 409 + friendly message linking to Nidaan dashboard |
| Bundled Sarathi user pays for HIGHER plan | Allowed — they're upgrading beyond bundle |
| Internal `@nidaanpartner.com` staff | Excluded from bundle provisioning |
| Sarathi payment via UPI (mobile) | sessionStorage recovery → check-order endpoint → success toast on next load |

---

## 37. LIFECYCLE HARDENING — PHASE B (June 7–9, 2026)

Re-architected the Sarathi-AI lifecycle from trial → subscription → cancel → refund → bundle → affiliate to be "guide, don't block" everywhere. Eight discrete units (B1–B8), all pre-flight-checked + live-SQL-tested before deploy.

### Phase 0 — Clean slate
- Backup at `/opt/sarathi/backups/pre-phase-b-wipe-20260608_114648.db`
- Wiped: all `tenants`, `agents`, `leads`, `nidaan_accounts`, `nidaan_claims`, `nidaan_subscriptions`, `affiliates`, `affiliate_referrals`, `processed_payments`, `audit_log`, `webhook_failure_log`, and all dependent rows
- Preserved: `nidaan_staff`, `nidaan_status_def` (28 statuses), `nidaan_status_transitions` (37 transitions), `nidaan_official_instances` (paired WhatsApp instances), `system_flags`, `provider_ratecards`
- DB compacted 5.6 MB → 815 KB via VACUUM

### B1 — Guide-don't-block anti-abuse
New module `find_existing_sarathi_tenant` / `find_existing_nidaan_account` / `classify_signup_conflict(email, phone, google_sub, intent)` in `biz_database.py`. Detects 11 conflict types: `bundle_active` / `trial_active` / `sub_active` / `sub_cancelled_in_cycle` / `trial_expired` / `sub_expired` / `bundle_expired` / `nidaan_active_no_sarathi` / `nidaan_sub_active` / `sub_cancelled` / `no_sub`. Returns structured JSON with `title`, `message`, `primary_action`, `secondary_action`, deeplinks — NOT a 409 HTTP error. Frontend renders a friendly popup via `showSignupConflict(conflict)` in `index.html`.

Wired into `/api/signup/google`, `/api/auth/send-signup-otp`, `/api/auth/send-email-otp`.

### B2 — Sarathi refund pipeline (Policy A)
New `sarathi_refunds` table. Policy A: full refund if cancelled within 7 days AND tenant has < 5 leads. Helpers in `biz_payments.py`:
- `check_sarathi_refund_eligibility(tenant_id)`
- `find_latest_paid_payment_for_tenant(tenant_id)` (sourced from `processed_payments`)
- `create_sarathi_refund_row()`, `update_sarathi_refund_status()`, `get_sarathi_refund()`, `list_sarathi_refunds()`
- `issue_razorpay_refund_for_sarathi(payment_id, amount_paise, notes)` (calls Razorpay `POST /payments/{id}/refund`)
- `find_sarathi_eligible_unrefunded(days)` (reconciliation queue)

Auto-triggered in `/api/subscription/cancel` (idempotent). Webhook handlers `refund.processed` / `refund.failed` / `refund.created` registered in `process_webhook_event`. SA endpoints: `GET /api/sa/refunds`, `POST /api/sa/refunds/{id}/retry`, `POST /api/sa/refunds/manual`.

### B3 — Unified bundle teardown + 5-day grace + nudges
Helper `nidaan.apply_bundle_teardown(account_id, reason, grace_days=5)` in `biz_nidaan.py`. Shortens `tenants.bundled_until` to `today + 5` (never extends). Also stamps `lifetime_trial_used = 1`. Called from THREE paths:
1. Manual `/nidaan/api/subscribe/cancel`
2. `refund_processed` completion (safety net)
3. Razorpay webhook `subscription.cancelled` / `halted` / `completed`

Scheduler (`biz_reminders.py`) fires email nudges once daily at 09:23 UTC for T-4, T-2, T-0 cohorts via `find_bundles_ending_in(N)`. Dashboard banner `#bundle-ending-banner` auto-renders on `loadOverview` when `bundled_until` ≤ 7 days; `/api/auth/me` now returns `bundled_until`, `plan_source`, `trial_ends_at`, `subscription_expires_at`, `lifetime_trial_used` to enable it.

### B4 — Affiliate clawback automation
Helper `db.auto_clawback_for_refund(tenant_id, reason)`:
- **Unpaid commission** → calls existing `reverse_commission()` (deducts from `affiliates.total_earned`, marks `reversed`)
- **Paid commission** → marks `clawback_owed` (SA must offset next payout — money was already paid, can't claw back retroactively)

Auto-triggered in `/api/subscription/cancel` refund-processed branch AND `process_webhook_event("refund.processed")` (idempotent). SA endpoints: `GET /api/sa/affiliates/clawbacks`, `POST /api/sa/affiliates/clawbacks/settle`. Caught + fixed a pre-existing `sqlite3.Row.get()` bug in `reverse_commission` while implementing.

### B5 — TEST_MODE bypass removed + recurring subscriptions on upgrade
`verify_payment_signature` and `verify_subscription_signature` in `biz_payments.py` no longer accept the literal `"test_bypass"` signature shortcut — all production calls require valid HMAC-SHA256.

Dashboard upgrade flow rewritten: `static/dashboard.html` now calls `/api/payments/create-subscription` instead of `/api/payments/create-order`. Razorpay options use `subscription_id` (recurring mandate) instead of `order_id` (one-time). Verify handler hits `/api/payments/verify-subscription`. Customers auto-renew monthly via mandate instead of silently expiring after one charge.

The 409 `blocked_by_bundle` response from `create-subscription` opens the B1 conflict popup ("You already get this plan free → Open Sarathi") instead of a `alert()`.

### B6 — Trial reuse prevention
New columns on `tenants` (via ALTER, safe migration):
- `lifetime_trial_used INTEGER DEFAULT 0`
- `google_sub TEXT DEFAULT ''`

Set to 1 in: `create_tenant_with_owner()` (every new tenant), `auto_fix_expired_trials()` (on natural expiry), `apply_bundle_teardown()` (on bundle end). `find_existing_sarathi_tenant` now matches on email OR phone OR google_sub — closing the email-alias bypass vector. The Google signup endpoint persists `google_sub` after tenant creation via `update_tenant`.

Conflict response for expired-states (`trial_expired` / `sub_expired` / `bundle_expired`) includes `lifetime_trial_used: bool` so the frontend can show "Free trials are once-per-customer" copy.

### B7 — "Open Sarathi" CTA on Nidaan dashboard + magic-link redirect handling
Prominent teal-gradient card `#sarathiAccessCard` on Nidaan dashboard. Shown when active Nidaan plan is `silver/gold/platinum` (any tier with `sarathi_bundle: True`). Click handler `openSarathiCRM` calls `POST /nidaan/api/sarathi/access` → backend mints Sarathi JWT → returns `{access_token, redirect_url, firm_name}` → opens `https://sarathi-ai.com/dashboard?token=…` in a new tab.

`/dashboard` route updated to detect `?token=` (no cookie), validate the JWT, plant a `sarathi_token` cookie (24h, Secure, SameSite=lax), and 302-redirect to clean `/dashboard` — keeps the JWT out of address bar / browser history / Referer headers.

Direct sign-in at sarathi-ai.com (Google / email-OTP / phone-OTP) still works for bundle users — B1 detects `bundle_active` and guides them to login, doesn't block.

### B8 — Messaging polish + bilingual
Every conflict response now includes `title_hi` + `message_hi` + per-action `label_hi` alongside the English fields. Popup component (`showSignupConflict`) picks Hindi when `_lang === 'hi'`. Mobile: actions stack column-reverse on `window.innerWidth < 420`, tap targets ≥ 44px. Banner mobile rules added for `#bundle-ending-banner` (Sarathi dashboard) and `#sarathiAccessCard` (Nidaan dashboard).

### Webhook monitor false-alarm fix (between B5 and B6)
`webhook_failure_log` gained a `user_agent` column. The 4 webhook-failure call sites now pass the request's UA. `_check_webhook_failure_alert` only counts failures where `user_agent LIKE '%razorpay-webhook%'` — our smoke tests with `curl` no longer fire the alert. Replaced literal `$(hostname)` shell-var with `socket.gethostname()`.

### Schema additions in Phase B
```
tenants: lifetime_trial_used INTEGER DEFAULT 0
tenants: google_sub          TEXT    DEFAULT ''
sarathi_refunds              (12 columns; mirrors nidaan_refunds shape)
affiliate_referrals          (statuses extended: clawback_owed, clawback_settled)
webhook_failure_log: user_agent TEXT DEFAULT ''
```

### Files changed in Phase B
- `biz_database.py` — conflict detection, refund schema, audit log helper, clawback helpers
- `biz_payments.py` — Sarathi refund helpers, refund webhook handlers, TEST_MODE removal
- `biz_nidaan.py` — `apply_bundle_teardown`, `find_bundles_ending_in`
- `biz_reminders.py` — bundle nudges scheduler, monitor UA filtering
- `sarathi_biz.py` — manual cancel → refund + clawback + teardown, magic-link `?token=` handling, SA refund/clawback endpoints, Google sub persistence
- `static/index.html` — bilingual popup, mobile-responsive
- `static/dashboard.html` — bundle banner + mobile rules, recurring subscription flow on upgrade
- `static/nidaan_dashboard.html` — Sarathi-access CTA card + handler + mobile rules

### Live-verified at deploy (B1–B8 combined)
| Endpoint | Status |
|---|---|
| Public homepage, `/nidaan/start`, `/nidaan/dashboard`, `/nidaan/ops` | 200 |
| `/api/signup/google` returns `conflict` object (not 409) on existing email | ✓ |
| `/api/sa/refunds*`, `/api/sa/affiliates/clawbacks*` | 401 unauth |
| Razorpay webhook bad signature | 400 |
| Magic-link `/dashboard?token=<valid>` | 302 + Set-Cookie + Location |
| `verify_payment_signature("test_bypass")` post-B5 | False |
| `lifetime_trial_used` + `google_sub` columns exist on `tenants` | ✓ |
| `apply_bundle_teardown` shortens `bundled_until` to +5, idempotent | ✓ |
| `auto_clawback_for_refund` unpaid → reversed, paid → clawback_owed | ✓ |
| `classify_signup_conflict` returns Hindi `title_hi`/`message_hi`/`label_hi` | ✓ |

### Operational notes
- The webhook secret env var: `RAZORPAY_WEBHOOK_SECRET` (separate from `RAZORPAY_KEY_SECRET`). Set both equal on Dashboard + biz.env to keep things simple.
- Phase 0 backup: restore via `cp /opt/sarathi/backups/pre-phase-b-wipe-20260608_114648.db /opt/sarathi/sarathi_biz.db; systemctl restart sarathi`.
- Bundle teardown nudge schedule: 09:23 UTC ≈ 14:53 IST. Override via WEBHOOK_FAILURE_* env vars not applicable here (separate concern). To shift the nudge time, edit `biz_reminders.py:_fire_bundle_teardown_nudges` calling block.

---

## 38. POST-PHASE-B WORK — JUNE 10, 2026

A 3-block session covering an info-disclosure sweep, a pricing-UX regression in production, and a homepage redesign exploration.

### 38.1 `[object Object]` error info-disclosure sweep (highest priority — completed)

**Triggering bug:** User reported `[object Object]` rendered as the error message under the Nidaan signup form. Root cause: `throw new Error(data.detail || 'X')` — but FastAPI's `detail` can be a **string** (HTTPException), a **Pydantic 422 array** (`[{loc:[...], msg:"...", type:"..."}, ...]`), or a **structured object** (custom conflict responses from B1). When `detail` is an array or object, `new Error(arr).message` becomes the literal string `"[object Object]"` — exposing zero information AND violating DPDP transparent-error-messaging norms.

**Concrete cause for the user's specific report (June 10 nginx access log, 11:10–11:13):**

```
POST /nidaan/api/signup HTTP/2.0  422  221b
```

Three consecutive 422s. The frontend stored email + OTP in module-level vars (`_email`, `_regVerifiedOtp`) during step 1; on page refresh / direct nav to step 2 these reset to empty string. The empty `email: ""` triggered Pydantic to reject the body. The 422 returned an array; the frontend rendered `[object Object]`.

**Fix shipped (15 frontend files patched):**

1. **`static/_err.js`** (new, 2,089 bytes) — shared robust extractor exported as `window._extractErr(data, fallback)`. Handles all three shapes:
   - String detail → returned as-is
   - Pydantic array → `"field: message; field: message"`
   - Object → tries `message`, `msg`, `error`, `title` keys
2. **`static/nidaan_start.html`** — added inline copy of helper + **session-state guard** at top of `doRegister()`: if `_email` or `_regVerifiedOtp` is empty, send the user back to step 1 with a clean message instead of letting the backend 422.
3. **Patched files** using `<script src="/static/_err.js?v=1"></script>` include + `data.detail || X → _extractErr(data, X)` replacement (130 patterns total):

| File | Patches |
|---|---|
| nidaan_start.html (inline helper) | 15 |
| nidaan_login.html (inline helper) | 5 |
| nidaan_signup.html (inline helper) | 3 |
| nidaan_dashboard.html | 12 |
| nidaan_ops.html | 18 |
| nidaan_review.html | 3 |
| dashboard.html (Sarathi) | 27 |
| index.html (Sarathi) | 14 |
| partner.html | 9 |
| admin.html | 6 |
| superadmin.html | 8 |
| onboarding.html | 3 |
| invite.html | 3 |
| getting-started.html | 2 |
| support.html | 2 |

4. **Audit-confirmed no frontend → backend dead code:** Every fetch endpoint in `nidaan_dashboard.html` (14 endpoints) and `nidaan_ops.html` (27 endpoints) maps to a live FastAPI handler in `sarathi_biz.py`. No "endpoint removed but frontend still calls it" risk.
5. **Code-cleanup note:** Three nidaan auth files (`nidaan_start.html`, `nidaan_login.html`, `nidaan_signup.html`) carry an inlined copy of `_extractErr` instead of using the shared `_err.js`. Identical function signature, identical logic — both work. Deferred consolidation to a future "code quality" pass.

### 38.2 Nidaan ₹499 visibility — top ribbon + dashboard single-claim CTA + service-worker cache fix

**(a) Dashboard showing "Pay ₹999 Now" despite May-29 price change.** Local + prod HTML correctly say `₹499`. Root cause: `static/nidaan-sw.js` (May 6) used **cache-first** strategy with cache name `nidaan-v1` and pre-cached `/nidaan/dashboard` at install. After the May-29 code change, the dashboard fetch was intercepted and served from cache. Identifying signal: `Cf-Cache-Status: DYNAMIC` from Cloudflare (not edge-cached), prod file mtime `2026-06-10 14:11`, prod content correct — so staleness was definitively in the user's service worker.

**Fix:** Rewrote `nidaan-sw.js` as v2:

- `CACHE_NAME = 'nidaan-v2'` — activate handler purges all non-matching cache versions
- Removed `/nidaan/dashboard` from `STATIC_ASSETS` pre-cache list (HTML should never be pre-cached if copy changes weekly)
- **HTML pages → network-first** (with cached copy as offline fallback). Detection: `event.request.mode === 'navigate'` or `Accept: text/html`
- **`/static/*` assets → cache-first** (cache-warm logo, manifest, fonts)
- `/nidaan/api/*`, `/internal/*`, `/nidaan/login|logout|signup|start` → bypass SW entirely

Result: future product copy/price changes propagate immediately on next page load. The browser auto-fetches the new SW on navigation; the new SW activates → purges `nidaan-v1` cache → next request is network-first → user sees current HTML.

**(b) ₹499 vs subscribe plans not visible on homepage.** User feedback: "below hero section doesn't catch eye if someone randomly scrolls."

**Fix:** Added a **top-ribbon** (sits between `</nav>` and hero `<section>`) showing both paths side-by-side:

- LEFT card: ⚡ FASTEST badge, "Get a single claim reviewed", "₹499 / claim", → `/nidaan/start#review-section`
- RIGHT card: 🛡 MULTI-CLAIM badge, "Silver · Gold · Platinum plans", "From ₹1,500 / quarter", → `/nidaan/start`

Top border is a half-orange / half-cyan stripe; ribbon background is a soft amber gradient with a "Choose how you want to start" label and a pulsing green status dot. **Mobile** (≤780px): single column, `.path-sub-line` hidden, smaller text — still both CTAs accessible without scroll.

**(c) Dashboard offered only "View Plans" for non-subscribers.** Non-subscribers landing on dashboard had no single-claim affordance.

**Fix:** Lock-overlay on the claims table now shows two CTAs side-by-side:

- `[View Plans →]` (existing cyan button)
- `⚡ Pay ₹499 for single review` (gold gradient button → `/nidaan/start#review-section`)

Sub-copy updated bilingually: "Choose a plan below — or get a single claim reviewed for ₹499".

**(d) Upgrade/downgrade verified working.** Profile tab → "Available Plans" section has Silver / Gold / Platinum cards with `onclick="switchPlan('silver|gold|platinum')"`. `switchPlan` opens the subscribe modal with that plan pre-selected; backend at `/nidaan/api/subscribe/recurring` (sarathi_biz.py:1893) creates a new Razorpay subscription. No bugs found.

### 38.3 Sarathi-AI homepage redesign — preview drafts (NOT live)

User wants the live `static/index.html` aesthetic upgraded. **Constraint:** "Don't touch live pages — make a copy first, compare, then decide." Three preview files were created at `/static/index_v{2,3,4}.html`, deployed under those paths only (live `/` untouched).

| Draft | Aesthetic direction | Key features |
|---|---|---|
| `index_v2.html` (84K) | Apple + Stripe — heavy serif italic accents, gradient text, animated phone | "Speak your CRM into existence" headline; voice-mic SVG with concentric pulse rings; story panels |
| `index_v3.html` (68K) | **Indian institutional fintech** (Nuvama + Groww + Waterfield) — based on user-supplied research on what Indian financial advisors trust visually | Deep navy + emerald + corporate gold; SEBI · IRDAI · AMFI trust strip above topbar; bordered structural grids; editorial pull-quote in About; dark institutional metrics band |
| `index_v4.html` (84K) | v3 aesthetic + **live agentic-AI stage** with BIG logo + 4-channel orbit | 3-column stage below hero: (1) Voice waveform card with live Hindi transcript, (2) Big floating Sarathi logo at 280px with dual orbit rings + halo glow, (3) 4 channel surfaces animating in sequence — WhatsApp / Telegram / Dashboard / Mobile |

**User feedback:** v3 aesthetic accepted ("good looking at Indian professional target customers"); v4 inflates with live multi-surface scene + restored big logo from live site's hero-2 (483px). Decision on live cutover **deferred** — user paused this thread to fix the Nidaan pricing issue, then directed attention to cybersecurity.

### 38.4 Files changed (June 10 session)

| File | Change |
|---|---|
| static/_err.js | New — shared error extractor |
| static/nidaan-sw.js | Rewrote v1 → v2 (network-first for HTML) |
| static/nidaan_index.html | Top-ribbon ₹499/subscribe cards above hero |
| static/nidaan_dashboard.html | Lock-overlay dual-CTA; 12 `data.detail` patches |
| static/nidaan_start.html, nidaan_login.html, nidaan_signup.html, nidaan_review.html, nidaan_ops.html | _extractErr sweep + nidaan_start state guard |
| static/dashboard.html, index.html, partner.html, admin.html, superadmin.html, onboarding.html, invite.html, getting-started.html, support.html | `<script src="/static/_err.js">` + `_extractErr` swaps |
| static/index_v2.html, index_v3.html, index_v4.html | New — Sarathi homepage redesign preview drafts |

### 38.5 What's pending (handoff to next session)

| Item | Status |
|---|---|
| Consolidate inline `_extractErr` in 3 nidaan auth files to shared `_err.js` | Deferred — safe to swap; identical logic |
| Decide whether to push v3 or v4 homepage live, or keep current | Awaiting user decision |
| Demo/affiliate/dashboard pages in v3/v4 aesthetic | Awaiting v3/v4 sign-off first |
| Cybersecurity Sprint 1–3 (see §39) | Approved by user, full execution authorized |

---

## 39. CYBERSECURITY TRACK — PLAN (kicked off June 10, 2026)

User-authorized full execution of all three recommended cybersecurity sprints. Goal: "No spammer, hacker, or anyone should make any harm or get invalid entry. Privacy and cybersecurity should be top-notch."

### 39.1 Phasing

| Sprint | Scope | Status |
|---|---|---|
| **D — Quick wins** | DMARC publish, `pip-audit`, git secrets-scan, IDOR audit on top 20 endpoints | Pending |
| **E — Formal hardening** | Auth/RBAC review, rate-limit audit, CSRF coverage, security headers (CSP/HSTS), Cloudflare WAF rules, secrets rotation, dependency pinning | Pending |
| **F — Pen-test readiness** | OWASP Top 10 walkthrough on actual endpoints, DPDP compliance audit (data export/delete on request, consent log immutability), disaster-recovery drill | Pending |

### 39.2 Why phased

Sprint D is "low-effort, high-information" — surfaces unknowns BEFORE we commit to a multi-session formal sprint. Sprints E and F then attack the actual findings rather than a generic checklist.

### 39.3 Acceptance criteria (to be expanded per sprint)

- No `[object Object]` or generic `Error` strings reach end users (✓ done June 10)
- No secrets in `git log -p`
- All non-public endpoints have RBAC checks demonstrably present
- All Pydantic models reject unexpected fields (`extra='forbid'`)
- Auth endpoints have rate limits applied
- DMARC records published, SPF + DKIM aligned with header-from
- Disaster recovery: can restore DB from `git-backup` + `backup-db` artifacts within 30 minutes

---

## 40. ₹499 FUNNEL + INFRA + DPDP SPRINT — JUNE 11–17, 2026

A large multi-track sprint. All items are **live and verified** on the production
server (Contabo `84.247.172.252`, app dir `/opt/sarathi`, user `sarathi`).

### 40.1 ₹499 value-first funnel (NidaanPartner.com)
- **Entry → free submission:** homepage CTAs hide the price ("Check if you have a
  case — Free"); `/nidaan/start#get-reviewed` is login-gated, then a free
  claim-intake form (`submitFreeClaim` → `/nidaan/api/claims/submit` →
  `payment_status='unpaid_lead'`). ₹499 is revealed only on the dashboard.
- **Dashboard checklist + pay-gate (Step 3b):** `leadChecklistCard` renders
  per-document upload slots from `biz_nidaan_doc_checklist.py`, progress + DPDP
  trust line; the hope/hook **pay-gate** (`show_pay_gate`, disputed-amount vs
  ₹499) appears when all required docs are in → `/pay` → Razorpay → `/pay-verify`
  flips to `paid` + starts the review + **48-business-hour SLA**.
- **One-tap pay link:** claim-bound, expiring `nidaan_paylink` token →
  `GET /nidaan/pay/{claim_id}?t=` mints a session and auto-opens Razorpay.
- **WhatsApp + email parity (Step 4):** `biz_nidaan_notifications.py` —
  `on_lead_filed` (doc-chase), `on_funnel_pay_ready` (pay-nudge + one-tap link,
  idempotent), `on_funnel_paid`. Template-first, en/hi/mr, opt-in respected
  (`wa_consent` at submit). Dashboard + WhatsApp + email say the same thing.
- **Ops lead pipeline (Step 6):** `get_claims_ops` payment_status filter + paid-
  above-leads sort; ops UI LEAD/PAID/SUB badges + pipeline filter bar.
- **DPDP lead-doc retention (Step 7b):** `biz_nidaan_retention.run_lead_retention`
  — pre-notice at day 23, secure purge at day 30 (tunable
  `NIDAAN_LEAD_RETENTION_DAYS` / `_NOTICE_DAYS`); worker-gated daily sweep.
- **Upload hardening (Step 7a):** magic-byte sniff (`_doc_magic_ok`) + per-claim
  doc cap; `/claims/submit` rate-limited.

### 40.2 Recurring billing fix (both platforms)
- **Sarathi-AI** already used Razorpay Subscriptions (recurring). **Nidaan** was
  recurring only for quarterly+toggle; annual was one-time. Now **all Nidaan
  subscriptions are recurring** — quarterly = monthly/interval-3, annual =
  yearly/1 (`NIDAAN_RAZORPAY_PLANS` gained period/interval; the dashboard always
  uses `/subscribe/recurring`). Only the **₹499 single review stays one-time**.
  Fixed a plan-lookup crash on `notes=[]` that created duplicate Razorpay plans.
  Verified against **live Razorpay** (no dup plans).

### 40.3 Email — SMTP + Brevo
- The host **blocks outbound :587**; switched `SMTP_PORT=465` + port-aware TLS in
  `biz_email.py` (was silently failing). **Brevo** (`BREVO_API_KEY`, Path 1, DKIM)
  wired for deliverability. (Verify sender in Brevo dashboard.)

### 40.4 Zero-downtime (blue-green) deploy — LIVE
- `APP_ROLE` split: `sarathi-worker` (bots+scheduler singletons, :8100) +
  `sarathi-web@1/@2` (HTTP, :8001/:8002) behind nginx **ip_hash** upstream
  `sarathi_app`. SQLite **WAL** enabled. Rolling `auto-deploy.sh` (one web at a
  time, health-gated) → **no 502**. Per-instance ports come from
  `/etc/sarathi/sarathi-web-%i.env` (on this host `EnvironmentFile` overrides
  `Environment=`). Runbook: `deploy/ZERO_DOWNTIME_DEPLOY.md`.
- **Deploy-automation fix (critical):** web units have `NoNewPrivileges=true`,
  which blocks `sudo` — so the webhook couldn't restart services (stale for ~2
  days). Fixed with a **systemd path-unit**: `_run_deploy` touches
  `/opt/sarathi/.deploy-trigger`; `sarathi-deploy.path` → `sarathi-deploy.service`
  (own cgroup) runs the rolling deploy. Auto-deploy proven end-to-end.

### 40.5 Sprint F (cybersecurity) — executed
- **OWASP pass** on funnel/billing: parameterized SQL (f-strings only interpolate
  whitelisted column names), IDOR covered by ownership checks, Razorpay HMAC sig
  verification + claim-bound tokens, strong nginx CSP/HSTS, `DEPLOY_TOKEN`-authed
  webhook. Fixed the one gap (missing rate-limit on `/claims/submit`).
- **DPDP account-erasure (right-to-delete):** `request_account_deletion` (cancels
  Razorpay sub + bundle, soft-delete `deletion_pending`), 7-day undo, daily
  `run_account_erasure_sweep` hard-purge (deletes docs + all PII, anonymises the
  account, **retains** anonymised financial records). Dashboard Settings → Delete
  my account. Test `_tools/test_account_erasure.py` = 14/14.
- **DR:** daily WAL-safe backups + restore verified; **encrypted offsite to AWS
  S3 Mumbai** (`ap-south-1`, India-resident) via rclone+gpg (AES256) — full
  round-trip restore proven. `BACKUP_GPG_PASSPHRASE` in `biz.env` (user holds it
  offline too).

### 40.6 Dashboard bug fixes
- WhatsApp opt-in card had a duplicate `display` (always visible to non-subs) —
  fixed. Lock-overlay "Pay ₹499" linked to `#review-section` and bounced
  logged-in users back to the dashboard — repointed to `#get-reviewed`.

### 40.7 Open / pending
- Verify Brevo sender; `NIDAAN_ADMIN_EMAIL` empty (ops "paid claim" alert).
- Advisor per-plan caps left flexible (quarterly) — to tighten later.
- WhatsApp official numbers not yet configured (funnel WA messages need a live
  Evolution number; email works).
- **Next build:** "Review delivered" status + report delivery (A: can-be-fought →
  Nidaan legal team contacts; B: settled/no-scope → share assessment) to
  dashboard + WhatsApp + email. Then a mobile UI/UX pass on all Nidaan pages.

---

## 41. MARKETING STUDIO + AFFILIATE BRANCHES + VALUE-FIRST ENTRY + OPS CONTROL CENTER — JUNE 18–22, 2026

Another large multi-track sprint. All items **live and verified** on production
(Contabo `84.247.172.252`). ~29 commits.

### 41.1 Marketing Studio revamp (Sarathi-AI)
- **Cost & load control:** per-plan **daily caps** (`biz_marketing.DAILY_CAPS`,
  `check_daily_cap`/`daily_usage`) — posters generous (local Pillow render ≈ free),
  videos tight (paid API). A bounded **concurrency semaphore** (`_MKT_GEN_SEM`,
  `MKT_MAX_CONCURRENT_GEN`=3) guards `/api/marketing/generate` (429 "busy" when
  saturated). `GET /api/marketing/quota` drives the UI allowance meter.
- **Deliver to own WhatsApp** (`POST /api/marketing/send-to-me/{id}`): hands the
  finished poster/video + caption to the subscriber's **own** number to post
  manually (not auto-Status). Graceful when no WA connected.
- **Templated video (Creatomate):** `biz_marketing.generate_video()` +
  `POST /api/marketing/generate-video/{id}` (poster→branded video), behind
  `CREATOMATE_API_KEY` + `CREATOMATE_TEMPLATE_ID` (operator adds + designs a
  template: Title/Body/Image/Logo/Brand-Color). Gated by plan + video cap +
  semaphore. Dormant until configured.
- **Generation quality fixes:** `_clean_caption()` strips LLM artifacts ("(कुल 189
  अक्षर)", "Here's a draft:", char-counts) EN+HI; body text pure white + outline +
  stronger scrim; badge no longer overlaps the logo box; on-image caption
  length-capped; advisor photo gets a white ring; duplicate name/firm suppressed.
- **Mobile-first UI wiring** (dashboard.html): Send-to-WhatsApp / Make Video /
  Download + a live "N posters / N videos left today" meter.
- **Phase 2:** off-peak **daily batch** (05:00 singleton, serial, load-smoothed)
  pre-generates each tenant's poster + Telegram-pushes it; **analytics**
  (`get_marketing_stats` + `/api/marketing/stats` + dashboard panel).

### 41.2 Sarathi-AI plan cards validated + fixed
- Audited every plan-card claim vs code. **Removed "Email-to-CRM"** from the Team
  card (i18n too) — marketing text with **zero backing implementation**.
- Corrected `payments.PLANS` Team description ("Custom Branding" → "Team
  Dashboard"; custom_branding is Enterprise-only). 12-calculators claim verified.

### 41.3 Sarathi-AI email deliverability (advisory — pending user DNS)
- Sarathi sends from `info@sarathi-ai.com` via Brevo but **sarathi-ai.com is not
  authenticated in Brevo** (no `spf.brevo.com` in SPF, no brevo DKIM CNAMEs, DMARC
  `p=none`). DNS at **Cloudflare**. Steps handed to user. **Not yet actioned.**

### 41.4 Nidaan affiliate branch codes
- `nidaan_branches` (code/city/name/contact_email/status), seeded **IND-HO,
  PUN-01, MUM-01, CHD-01, HYD-01**; `branch_code` on `nidaan_accounts`.
- Captured at **signup AND the ₹499 claim form** (covers Google sign-up); strict
  validation, optional, neutral verbiage.
- **Superadmin "🏢 Branches" panel:** create/disable + alert email +
  signups/paid/unpaid counts + unpaid-leads drill-in.
- **Fallback alerts:** email branch on attributed signup + a twice-daily sweep
  emails once if the ₹499 stays unpaid >24h (`branch_unpaid_reminded_at`).

### 41.5 Nidaan ops — All-Claims table + Overview fix
- Added **"📋 All Claims"** to the superadmin sidebar (table existed but was
  unreachable except via an account); columns now include Payment, Assigned-to,
  **Tasks** (open follow-ups), **Branch**.
- **Bug fix:** Overview counted all `nidaan_claims` while the table inner-joins
  accounts → an **orphaned claim** (manual account delete) showed "1" vs "0".
  Overview now counts only claims with a live account; orphan cleaned.

### 41.6 Value-first entry + routing (NidaanPartner)
- See `[[project-nidaan-value-first]]`. Homepage CTA **"Get Started" → "Login"**;
  `_loginSuccess` **routes by state** (subscriber→dashboard; in-flight→dashboard;
  new/no-claim→claim funnel); the dashboard redirects no-sub/no-claim users into
  the funnel.
- **₹499 pay-gate after 2–3 KEY docs** (`pay_gate_ready`, `min(3,required)`); the
  claim form softened to need only the key docs to submit.

### 41.7 Superadmin account delete + Ops Control Center
- **Account delete:** `DELETE .../accounts/{id}` + `.../accounts/bulk-delete`
  reuse DPDP-safe `execute_account_erasure`. UI: bulk checkboxes + per-row 🗑️ +
  **2-step type-to-confirm** guard. (Accounts only for now.)
- **Activity trail:** `nidaan_audit_log` + `log_activity`/`get_activity_log` +
  `_ops_audit`. Instrumented account/staff/branch/claim CRUD + assign/status.
- **App Health → "Control Center":** live service checks (DB/Brevo/Razorpay/WA/
  disk), **Recent Errors** (in-memory ring buffer `_ERROR_RING`, resets on
  deploy), filterable **Activity Log**. **Deferred:** Layer-3 auto-remediation bot.

### 41.8 Branding
- Sarathi `/about`: removed Ashwin Kaushal; Dushyant = "Founder, Sarathi-AI ·
  Co-Founder, NidaanPartner.com". Nidaan `/about`: Ashwin = "Co-Founder,
  NidaanPartner.com" (Sarathi removed); Dushyant = "Co-Founder, NidaanPartner.com
  · Founder, Sarathi-AI.com". Sarathi homepage Nidaan section → single CTA
  "🛡️ Insurance Claims Support — Click Here →".

### 41.9 Open / pending (operator + next)
- **Operator:** Sarathi Brevo DNS (§41.3); advisor marketing photo;
  `CREATOMATE_API_KEY`/`_TEMPLATE_ID`; branch alert emails for the 5 branches.
- WhatsApp official numbers still not configured.
- **Next (discussion):** Sarathi-AI dashboard — separate **Leads** (journey to
  conversion) from **Customers** (post-conversion **portfolio** per policy type,
  AI extraction from policy docs); fold the standalone Policies section into
  Customers.

---

## 42. SARATHI CUSTOMERS/PORTFOLIO + WHATSAPP-FIRST (TELEGRAM HIDDEN) + MOBILE-FIRST — JUNE 22+, 2026

All live + verified on production. See memory `[[project-sarathi-customers]]`,
`[[project-nidaan-value-first]]`, `[[feedback-mobile-first]]`.

### 42.1 Leads → Customers separation + portfolios (Sarathi-AI)
- **New `customers` table** (first-class entity, `portfolio_token` for a shareable
  self-view) + `policies.customer_id` + `policies.type_specific` (JSON). One-time
  idempotent **backfill** (lead-with-policies → customer).
- **Conversion:** auto on first policy (`add_policy` → `ensure_customer_for_lead`)
  **+ manual "Convert"** in the Leads pipeline **+ "Add Customer"** direct
  (contact-only; flagged `client_type='customer'` so it skips the pipeline).
- **Strict isolation:** every customer read/write scoped via `agents.tenant_id`
  (owner=firm, agent=own); `_customer_in_scope()` IDOR guard on
  portfolio/share/convert. Verified: bogus share token → 404, no leak.
- **Customer → Portfolio:** policies grouped by type; **AI per-type extraction**
  (`_DOC_EXTRACT_PROMPT` emits a `type_specific` block: motor reg-no/IDV/NCB;
  life nominee/term/maturity; health members/room-rent/co-pay; investment
  folio/NAV/SIP) auto-fills on policy-doc scan.
- **Shareable portfolio link:** public `GET /portfolio/{token}` (read-only,
  commission/internal stripped, advisor contact shown), revocable via
  `regenerate_portfolio_token`.
- **Policies tab → "Renewals & Book"** (cross-customer: summary cards, sort by
  soonest renewal, renewal-window filter). Endpoints:
  `/api/admin/customers` (GET list + POST add), `.../{id}/portfolio`,
  `.../{id}/share`, `/api/admin/leads/{id}/convert`,
  `/api/admin/leads?exclude_customers=1`.

### 42.2 WhatsApp-first — Telegram hidden from customers (backend untouched)
- Product is WhatsApp-first; the Telegram bot (`biz_bot.py`) **still runs** — only
  hidden from customer UI. **Parity confirmed:** web+mobile voice
  (`/api/ai/voice-action`) + WhatsApp agent (`biz_wa_agent`) + full dashboard
  cover everything Telegram did.
- Swept sitewide: homepage (hero "AI Assistant Bot" tab hidden + rotation skips
  it; all copy → WhatsApp/app), demo (Telegram view hidden, **WhatsApp demo** now
  default), getting-started/onboarding flipped **WhatsApp-first**,
  features/help/about/invite reframed, `/telegram-guide` → 302 redirect. Hidden
  login-via-Telegram + JS identifiers (`map.telegram`, `saveTelegramBot`) left
  intact so nothing unplugs. Voice walkthroughs verified Telegram-free.

### 42.3 Mobile-first ground rule + fixes
- **Ground rule (permanent):** every change/build must be mobile UI/UX compatible
  — verify on phone viewport before done.
- Mobile passes: Customers grid → 1 col, cc-stats wrap, Renewals summary 2-up,
  type-specific chips word-break; homepage footer +96px bottom padding so the
  copyright clears the fixed Listen/Demo buttons.

---

## 43. NIDAANPARTNER OPS — OFFICE-TASK ENGINE + MONTHLY BILLING + WHATSAPP HARDENING — JUNE 23 – JULY 6, 2026
Large multi-session build turning the ops portal (`static/nidaan_ops.html`) into a real office task engine, plus a billing switch and WhatsApp/notification hardening. All shipped + verified live via `git push origin master` (blue-green). Files: `sarathi_biz.py`, `biz_nidaan.py`, `biz_nidaan_notifications.py`, `biz_nidaan_tasks.py`, `biz_nidaan_inbound.py`, `biz_whatsapp_evolution.py`, `biz_email.py`, `biz_database.py`, `static/nidaan_ops.html`, `static/nidaan_dashboard.html`, `static/nidaan_start.html`, `static/nidaan_index.html`.

### 43.1 Office-task system (quick-tasks → full engine)
- **Staff**: added `phone` + `notify_email` (personal/Gmail; email falls back login→notify); **welcome notification** (email+WhatsApp w/ Login ID + portal link) on staff create; staff table shows Login ID vs Email; live input validation (10-digit mobile, login-id chars, email).
- **Task Registry** (the durable record): "📋 All Tasks" with status tabs+counts (All/Active/Open/In-progress/Done/Cancelled/Overdue/Pending-approval), type + assignee filters, **search by title or #id**, per-row delete, admin **show-deleted** audit view. Fixed the original bug where done/cancelled tasks vanished (list was open-only).
- **Lifecycle**: reopen, reassign, **soft-delete** (history kept), immutable **activity log** (`nidaan_quick_task_log`), **merge** duplicates with **precedence** (`merged_into`, comments move, both timelines record).
- **Approval**: optional per-task `requires_approval`; approve/reject **only for super/sub-admin** (checkbox hidden from associates); creator+assignee notified.
- **Comment "Seen"** (replaced comment-approval): `nidaan_quick_task_notes` + `nidaan_quick_task_note_reads` + `nidaan_quick_task_seen`. Green-blink dot = **your** task (assigned/created) with new activity since you last opened it (new comment / assignment / status change); turns **gray** once seen; **nothing** on tasks that aren't yours. Per-comment ✓ Sent / ✓✓ Seen-by.
- **Everyone assigns to anyone**: `list_active_associates` now returns ALL active non-deleted staff (super admins included). Default `task_create_min_role`=team_member; lower roles are **nudged (not blocked)** into an upward `task_type='request'` that alerts admins.
- **Creator visibility**: associates now see tasks assigned-to OR created-by them (registry + counts via `viewer_staff_id`).
- **Tasks dashboard strip**: Active/Open/In-progress/Done/Overdue/Pending-approval/On-leave tiles, **all clickable → auto-filter** the registry (On-leave scrolls to leave card). Tasks panel moved **above Overview** and is the **default landing**.
- **Deep-link cleanup**: `?qt=/?task=/?leave=` stripped from URL after opening (fixed "task keeps popping up" re-open loop).

### 43.2 Leave (`nidaan_leave_requests`)
- Apply → admin approve/reject; **full-day or half-day (first/second half)** + optional **From/To time**; **handover** (auto-shows applicant's tasks-in-hand + notes) + **suggested cover person**.
- **Visibility**: "Currently On Leave" to everyone; admins get **"Upcoming Leaves — next 30 days"**; task rows whose assignee is **on leave today are highlighted** (🌴 + orange) for reassignment.
- Leave request → **WhatsApp (to official line) + email** to admins (handover + open-task count + half-day + cover); decision → requester.

### 43.3 Broadcast + notification bell (`nidaan_broadcasts`, `nidaan_broadcast_reactions`, `read_at` on `nidaan_notifications`)
- Top-bar **🔔 bell** (unread badge, pulsing) + dropdown: personal notifications (tasks/comments/approvals/leave, deep-linked) + a **📢 Broadcasts feed** with **emoji reactions** (👍❤️🎉😂🙏🔥, live counts, toggle). Polls 45s; opening marks read.
- **📢 Broadcast** (everyone) → one message to every active staffer's bell (bell only, no WA/email). Endpoints: POST /broadcast, GET/POST /broadcasts[/{id}/react], GET/POST /notifications[/read].

### 43.4 Monthly billing (was quarterly)
- **Plans → monthly**: Silver ₹500, Gold ₹1,000, Platinum ₹2,000 /month (annual = 10× = ₹5,000/10,000/20,000). `NIDAAN_RAZORPAY_PLANS` monthly (period=monthly, interval=1, period_days=30) + **versioned `tag` (silver_m1…)** so `ensure_nidaan_plans` creates NEW Razorpay plans (immutable) instead of reusing old ₹/quarter; internal plan keys unchanged so checkout/DB/webhook mapping intact. One-time order path uses amount_paise directly; recurring total_count 40→120.
- **Claim quota → monthly**: `PLAN_LIMITS.claims_per_month` (Silver 3, Gold 10, Platinum ∞); both quota windows 90→30 days.
- Display synced: dashboard subscribe cards (monthly+yearly), billing toggle, renewal-email prices, homepage plans (removed Sarathi-free strip, free-consultation, Platinum unlimited-logins; coverage caps ≤₹5L/₹10L/₹50L). **Existing subscribers stay on old plans** until cancel+resubscribe.

### 43.5 ₹499 form rework + login-flow fix
- **₹499 form** (nidaan_start funnel + dashboard claim form): **insurer dropdown** (30+ Indian insurers + Other), new **Policy Inception Date**, optional **TPA**, **documents optional** (single optional rejection-letter upload; removed "upload N to continue"). Backend: `policy_inception_date`+`tpa_name` on `NidaanClaimReq`/`create_nidaan_claim`/`nidaan_claims`.
- **Login routing bug** fixed: logged-in users clicking a plan lost the `?plan` intent → bounced into the claim/documents funnel (flicker). Now preserves intent → `/nidaan/dashboard?subscribe=<plan>` which **auto-opens the subscribe modal** and never bounces plan-intent users into the funnel.

### 43.6 WhatsApp hardening + user-driven official numbers
- **Phone hygiene**: `normalize_indian_mobile` / hardened `_norm_phone` — strip +91/0, require exactly 10 digits, **reject (never truncate)** malformed (root-caused a misdeliver to a stranger).
- **Staff-only allow-list**: WhatsApp goes ONLY to registered active-staff numbers (+ official numbers); all subscriber/account WhatsApp held off (flags `nidaan_wa_staff_only`, `nidaan_subscriber_wa_enabled`). Inbound bot no longer auto-replies "register" to unknown senders.
- **Verify-before-send**: Evolution `check_number_exists` (`/chat/whatsappNumbers`) → send only to canonical JID; **fail-closed** (email fallback). Self-send **allowed** so a super admin sharing the official line still gets alerts (flag `nidaan_wa_block_self_send`).
- **Admin/leave alerts → connected official line(s) only** (`_whatsapp_official_lines`), not personal admin phones; email still per-admin.
- **Official Numbers user-driven**: removed hardcoded 3-seed; add any number (name+phone) → auto free slot → connect by QR; Remove (logout). **connection.update webhook now updates `nidaan_official_instances`** (was wa_instances only → QR-scanned number showed disconnected) + official-numbers page **live-syncs** Evolution state.
- **App Health** WhatsApp status reads `nidaan_official_instances` (was wrong table) + per-number panel.

### 43.7 Staff lifecycle + permissions
- **Super-admin lockout protection**: super admins can't be deactivated/deleted; no self-deactivate (Ashwin had inactivated everyone).
- **Soft-delete/archive** (`nidaan_staff.deleted_at`): delete→archive, restore, bulk delete-inactive, Archive view. **Recreation reclaims** a soft-deleted login-ID row (fixed "email exists" on delete→recreate).
- **One-click password reset** (super admin) → temp password shown once.
- **Ops settings** KV (`nidaan_ops_settings`) — `task_create_min_role` permission (super-admin editable).

### 43.8 Email branding
- Nidaan ops notifications now send **from "Nidaan Partner"** (routes to NIDAAN_FROM). Personal-Gmail recipient fallbacks (health monitor, reminders) → `info@nidaanlegalindia.com`. **FROM-address change to info@ pending user action**: verify domain in **Brevo** (SPF/DKIM) — Brevo = sender, Cloudflare = DNS + inbound routing; a real inbox needs Zoho/Workspace. Then flip `NIDAAN_FROM_EMAIL`/`SMTP_FROM_*` env.

### 43.9 Deployment / backup posture (verified, no change made)
- **Code**: GitHub `github.com/kumar26dushyant-lab/sarathi-ai.com` (remote, safe) + server + laptop. Deploy = `git push origin master`; server pulls via PAT; `git-backup.timer` also pushes code daily.
- **Data**: SQLite `/opt/sarathi/sarathi_biz.db` (~4MB) on the Contabo VM; `backup-db.timer` (2am daily) → `deploy/backup.sh` tars DB+uploads+pdfs+videos, keeps 7 **local** copies in `/opt/sarathi/backups`. Secrets in `/opt/sarathi/biz.env` (0600, not in git).
- **Off-server encrypted backup — DONE (Jul 7, 2026)**: `deploy/git-db-backup.sh` +
  `git-db-backup.timer` (2:30 AM daily). Hot `.backup` of the DB → gzip → **AES-256
  (openssl, pbkdf2 iter=200000)** BEFORE leaving the server → pushed to a **private
  GitHub repo `kumar26dushyant-lab/sarathi-db-backups`** via a **dedicated ed25519
  deploy key** (`/root/.ssh/id_backup_repo`, not the main PAT). Passphrase in
  `biz.env` (`BACKUP_ENC_PASSPHRASE`) + held off-site by owner (without it backups
  can't be decrypted). Single overwritten blob → git history = point-in-time versions.
  Restore: `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -in sarathi_biz.db.gz.enc
  -pass pass:PP | gunzip`. Local 7-day backups still run too (belt + braces).

### 43.10 Phase 5 — PWA (installable app + Web Push) — SHIPPED Jul 7, 2026
- **Installable ops staff app**: `static/nidaan-ops.webmanifest` (standalone,
  start_url `/nidaan/ops`, 192/512 icons); ops page gets manifest link, theme-color,
  apple-touch metas, SW registration, an Android **install prompt** + iOS **"Add to
  Home Screen"** hint. Subscriber dashboard PWA already existed.
- **Service worker v3** (`nidaan-sw.js`): never-cache all `*api*` paths; added
  **Web Push** (`push` + `notificationclick`) handlers (tap → focus/open the deep link).
- **Web Push backend**: VAPID keys in `biz.env` (`VAPID_PUBLIC_KEY/PRIVATE_KEY/SUBJECT`),
  `pywebpush` in venv. `nidaan_push_subscriptions` table (per-device, deduped by
  endpoint). `push_to_staff()` sends via pywebpush, prunes dead (404/410) subs, runs
  blocking sends in an executor, never raises. **Hooked centrally** into
  `_record_notification` (every staff task/comment/approval/leave dashboard event)
  + `record_broadcast` (broadcasts) — non-blocking `asyncio.create_task`.
- **Endpoints**: GET `push/vapid-key`, POST `push/subscribe|unsubscribe|test`.
- **UI**: "Enable push" toggle in the bell dropdown (permission → subscribe →
  confirmation push; reflects on / blocked / unsupported). Verify on real device.

### 43.12 Hardening — PWA identity, product boundary, doc access (Jul 7, 2026)
- **Three cleanly-installable PWAs** (fixed collisions): each manifest now has a
  distinct `id` + non-overlapping `scope` + correct brand icon.
  Sarathi `id:"/" scope:"/"` (sarathi icon); Nidaan Partner `id:"/nidaan/dashboard"
  scope narrowed `"/"→"/nidaan/"` (nidaan logo); Nidaan Ops `scope "/nidaan/"→
  "/nidaan/ops"` + icons switched from Sarathi's `icon-192/512` to `nidaan_logo.png`
  (that icon reuse was why the admin app showed the Sarathi logo). Explicit ids equal
  each app's prior implicit id → existing installs not orphaned.
- **Internal boundary hardened**: new `biz_platform_bridge.py` is the ONLY module
  allowed to touch Sarathi's `tenants`/`agents` tables on Nidaan's behalf
  (`upsert_bundle_tenant`, `shorten_bundle_tenant`, `find_bundle_tenants_ending_on`).
  biz_nidaan.py's 3 bundle functions delegate to it (SQL moved verbatim, behavior
  unchanged); no Sarathi-table SQL remains in Nidaan code. Products still co-hosted
  (one app, one DB) but the seam is now explicit + API-ready.
- **Claim documents behind signed URLs**: files under `/uploads/nidaan-docs/` were
  reachable by anyone with the (unguessable UUID) URL, forever. Now the
  ownership-checked doc APIs emit HMAC-signed URLs (`?exp&sig`, HS256 over
  `stored_name:exp` with `JWT_SECRET`, 48h TTL); FastAPI middleware
  `nidaan_doc_access_guard` refuses unsigned/expired/forged requests + sets
  `no-store`. **Required an nginx change** — nginx served `/uploads/` from disk,
  bypassing the app, so added `location /uploads/nidaan-docs/ { proxy_pass
  sarathi_app; }` (more-specific prefix) to route docs through the app. Other
  `/uploads/*` (photos, marketing) still served from disk. Verified live:
  signed→200, unsigned/badsig/expired→403. Data isolation on the JSON APIs was
  already correct (every subscriber read filters by `account_id`).

### 43.13 PWA robustness (Play-Store-grade) — Steps 1–2 done (Jul 8, 2026)
Goal (agreed): all three apps behave like store apps — no flicker, land on login
when logged out (with a Home button) / dashboard when logged in, soft session
timeout, auto-update, managed cookies. 5-step plan; **Sarathi is already ahead**
(has refresh-token silent-refresh, client cookie, CSRF), so 3 & 5 mostly = bring
Nidaan up + upgrade both to httpOnly.
- **Step 1 (done):** no-flicker pre-paint `<head>` auth gate on Nidaan dashboard —
  logged-out opens redirect to `/nidaan/start` before any paint.
- **Step 2 (done):** login-first landing. New **`/login`** = dedicated Sarathi
  sign-in (email-OTP + Google, reuses exact endpoints/storage/redirect, Home
  button). Sarathi manifest `start_url "/"→"/dashboard"` (web visitors keep `/`).
  `/dashboard` now **302→/login** for logged-out (was a 401 page). Loop-safe:
  `/login` verifies the session via `/api/auth/me` before auto-forwarding, and
  the dashboard gate/login gate agree on the cookie. Nidaan `/nidaan/start`
  already has a Home link. Verified live (302/200/401 chain).
- **Step 4 (done):** auto-update toast — when a freshly-deployed SW takes control
  (guarded vs first-install via `controllerchange` + `_hadCtrl`), a one-tap
  "🔄 New version — Update" toast reloads to latest. Non-disruptive. Added to
  Nidaan ops, Nidaan dashboard, Sarathi dashboard (all SWs already skipWaiting).
- **Two fixes shipped alongside (Jul 8):** (a) insurer field on the Nidaan
  dashboard claim form + ₹499 review form was an `<input list>` datalist that
  shows no tappable dropdown on mobile → replaced with a native `<select>` (30
  insurers) + "Other" free-text, syncing the same hidden input the forms submit;
  (b) login screens (Sarathi `/login` + Nidaan `/nidaan/start`) now show a
  blocking "Signing you in…" spinner overlay during OTP/password/Google latency.
- **Next:** Step 3 (Nidaan silent refresh, mirror Sarathi's refresh-token flow) →
  Step 5 (httpOnly cookies for both — the security upgrade). Then WhatsApp audit +
  brains separation (bounce-to-self, template registry).

### 43.14 ₹499 subscriber-flow rebuild — in progress (Jul 8, 2026)
User very frustrated: ₹499 flow looped, asked for documents, flickered through
sign-in→dashboard→form, couldn't reach sign-in. Agreed model: **₹499 = ephemeral
transactional** (multiple concurrent reviews allowed; completed ones hidden from
user, kept at backend; returning user = fresh start; needs email+mobile; minimal
dashboard + Settings). **Silver/Gold/Platinum = permanent** (works — do NOT touch).
- **Pay anytime (done):** removed BOTH document gates — `show_pay_gate` now true for
  any `unpaid_lead`, AND the hard 409 "upload all required documents first" on
  `POST /nidaan/api/claims/{id}/pay` (the real blocker — customers literally could
  not pay). Docs optional everywhere; copy reframed.
- **Lead-user loop (done):** dashboard no longer shows the lock overlay (whose ₹499
  button linked back to the form) for lead users; banner points to the visible Pay
  card.
- **Redirect chain killed (done):** `nidaan_start` only auto-forwards on explicit
  `?plan` intent (plain "Login" reaches sign-in + can switch account); dashboard no
  longer bounces no-claim users to the form. No page auto-redirects on state.
- **Login overlay (done):** `showNBusy` moved into `_loginSuccess` + `_googleDispatch`
  so the spinner covers Google + all post-login routing latency.
- **Diagnosis:** the ₹499 form creates ONE clean `nidaan_claims` lead (no purchase);
  `nidaan_per_claim_purchase` is a legacy parallel path. Root of the mess = scattered
  client-side redirects (no single router) + `localStorage`/Bearer auth (server can't
  route page loads without a cookie).
- **Next (the "solve forever" = Steps 3+5 combined):** Nidaan session **cookie** →
  **server-side router** (one 302 before paint: subscriber→full dash, active ₹499→
  minimal dash, else→login/choice) + dedicated `/nidaan/login` + **silent refresh**
  + **httpOnly** hardening. Then retire the legacy per_claim path (Stage 4).
- **"Get Started Free" mislabel:** those are the PAID plan buttons (→ `?plan=`); rename
  to "Choose <Plan>" to stop the confusion (screenshot-3).
- **Stuck overlay (fixed):** the "Signing you in…" overlay stayed on the new-user
  claim form (funnel reveals it on the same page, no navigation) — `hideNBusy()` now
  runs in `enterClaimForm()`.
- **Step 5 foundation (done):** Nidaan session now also in a SameSite=Lax cookie —
  set on login (`_loginSuccess`), auto-migrated from localStorage on dashboard load
  (no re-login), cleared on logout. Prereq for server-side routing. NOTE: Nidaan
  tokens last **30 days**, so Step 3 (silent refresh) is low-value for Nidaan; the
  server-side gate + httpOnly flip waits until active users have migrated the cookie.
- **Nidaan Google OAuth (done, Jul 8):** Nidaan now uses its OWN client
  `NIDAAN_GOOGLE_CLIENT_ID` (env, in biz.env) so the consent screen says "Nidaan
  Partner" not "Sarathi-AI". `verify_google_id_token(…, expected_client_id=)` added;
  Nidaan endpoints pass the Nidaan id (fallback to shared `GOOGLE_CLIENT_ID` if unset).
  Sarathi unchanged. (User must finish the OAuth consent-screen branding + add
  nidaanpartner.com origin in that Google Cloud project.)
- **Minimal ₹499 dashboard (Stage 3, started):** a ₹499 lead user's raise-claim button
  is enabled ("start another ₹499 review", multiple concurrent) and Profile/Settings
  are unlocked (via `window._leadUserAccess`) — no more "Subscribe to unlock" on the
  ₹499 dashboard. Subscribers + brand-new users unchanged. Still to do: render ALL
  active reviews (not just the first), hide completed reviews (ephemeral), brand-new
  choice screen, retire legacy per_claim path (Stage 4).

### 43.15 Identity-first router + superadmin alerts (Jul 8, 2026)
- **Identity-first login (done):** `_loginSuccess` was applying the endpoint's
  ₹499/plan intent BEFORE checking account state → same email showed a different
  dashboard per button + auto-created duplicate claims. Now it checks state first:
  ANY existing user (subscription / review / claim) lands on THEIR dashboard
  regardless of which button they clicked; only a brand-new account follows intent.
  Switching ₹499⇄plan is an explicit action, never a login side-effect.
- **Switching rules (CONFIRMED, to build as a "Switch plan" flow in Settings):**
  ₹499→plan: refund ₹499 only if the review is NOT delivered (free-review hole
  closed) + ≤7 days. plan→₹499: refund current billing cycle only if NO claim
  registered that cycle. Existing plan cancelled immediately; if pending data →
  user chooses **Delete** or **Merge into new plan** (retention upsell).
- **Superadmin alerts + deep-links (done, Item 1):** `on_subscriber_signup` alerts
  SA/Sub-admin on every new signup (bell + push, deep-linked to the account);
  `on_lead_filed` now also alerts admins (₹499 lead, docs pending); `on_claim_filed`
  admin alert deep-links to the account. Notifications carry `?account=`; ops
  `_handleDeepLink` + bell items open `openAccountDrawer`.
- **Nidaan Google OAuth:** own client `NIDAAN_GOOGLE_CLIENT_ID` (consent = "Nidaan
  Partner"); backend verifies via `expected_client_id`. LIVE + confirmed by user.
- **Remaining backlog:** subscriber↔ops messaging (subscriber dashboard); Switch-plan
  flow (+ refunds + delete/merge); Stage 3 finish (render ALL active reviews, hide
  completed, brand-new choice screen); Stage 4 (retire legacy per_claim path);
  "Get Started Free" → "Choose <Plan>" relabel.

### 43.16 Post-payment lock fix + subscriber↔ops messaging (Jul 8, 2026)
- **Post-payment lock (fixed):** paying ₹499 flips the claim off `unpaid_lead`, so the
  dashboard's `_leadClaim`-based unlock gate matched nothing → user fell into the
  "no subscription → lock everything / Subscribe to manage claims" branch and their
  own PAID claim was hidden. Now a ₹499 user is "active" if they have ANY claim (lead
  OR paid/in-progress): dashboard stays unlocked, claim visible, banner "review in
  progress", Settings open. **This class of bug keeps recurring because entitlement is
  computed from the tangled dual model — Stage 4 (one model) is the durable fix.**
- **Subscriber ⇄ ops messaging (built on the long-dormant `nidaan_messages` table):**
  data fns in biz_nidaan (list/add/mark-read/unread-count) + `on_new_claim_message`
  (subscriber→ops = SA/Admin bell deep-linked to account; staff→subscriber = dashboard
  + WhatsApp/email if opted in). Endpoints: subscriber + ops GET/POST
  `…/claims/{id}/messages`. UI: a message thread in BOTH the subscriber claim drawer
  and the ops claim drawer. Live (401-gated).
- **Stage 4 — server-authoritative entitlement (done, the durable fix):**
  `/nidaan/api/me` now returns `account_state {type: subscriber|retail|new, active,
  plan, has_unpaid_lead}`, computed ONCE server-side from ALL sources (subscription,
  any claim lead/paid, per-claim purchase). Dashboard lock/unlock now uses
  `me.account_state.active` instead of re-deriving from scattered signals — the root
  cause of the recurring "paid user locked out" bugs. (Full dual-table DB collapse
  can still follow, but the entitlement decision is now single-sourced.)

### 43.11 Still pending / next
- Email FROM → `info@nidaanpartner.com` or `info@nidaanlegalindia.com` (Brevo domain verify + inbox).
- **API integration (two-way sync) — in design**: claim data originates in the
  nidaanpartner.com subscriber dashboard → review; if it **has potential to fight**,
  the claim moves to a **separate legal application** (Level 2) and **status updates
  flow back** to the subscriber dashboard. If **no potential / correctly settled**, it
  **ends at Level 1** (subscriber notified, never reaches legal). Plan: Nidaan exposes
  an authenticated versioned API (API-key per partner, `/api/v1/…`) + webhooks for
  status callbacks; consume the legal app's API via httpx. Not built yet.
- CSV/Excel export buttons for ops lists (offered, awaiting go-ahead).
- Ops architecture cleanup (deferred by user).

---

## 44. WHERE WE ARE — NIDAANPARTNER SUBSCRIBER + ₹499 FLOW (CONSOLIDATED STATE, Jul 8–9, 2026)

**One-paragraph summary.** A multi-session rebuild fixed the NidaanPartner subscriber
experience end-to-end: login is now **identity-first** (same email → same dashboard
from any button, no duplicate claims), **₹499 is payable anytime** (all document gates
removed), paying no longer locks the dashboard, entitlement is **server-authoritative**
(one source of truth), **subscriber↔ops messaging** works per claim, **superadmin gets
deep-linked alerts** on signup/claim/lead, and **Nidaan has its own Google branding**.
The PWA robustness track (installable apps, no-flicker gates, login-first landing,
auto-update) is done for all three apps except the httpOnly cookie flip (staged).

### 44.1 The two products (the core mental model — DO NOT conflate)
- **₹499 one-time review = ephemeral / transactional.** Multiple concurrent reviews
  allowed; completed reviews drop out of the user's view (retained at backend); a
  returning user (months later) starts fresh. Minimal dashboard = active review(s) +
  Settings. Needs email + mobile.
- **Silver / Gold / Platinum = permanent relationship.** Full persistent dashboard +
  history. **This flow works — do NOT touch it.**
- **Identity, not endpoint, decides everything.** `/nidaan/api/me.account_state`
  (`type: subscriber|retail|new`, `active`, `plan`, `has_unpaid_lead`) is the single
  source of truth, computed server-side from subscription + any claim + per-claim
  purchase. Frontend NEVER re-derives entitlement.

### 44.2 Switching rules (CONFIRMED with the user)
- **₹499 → plan:** refund the ₹499 **only if the review is NOT delivered** (free-review
  hole closed) **and ≤ 7 days**; then subscribe. >7d or delivered → no refund, subscribe
  as new.
- **plan → ₹499:** refund the **current billing cycle only if NO claim was registered
  that cycle**; if a claim was registered → cancel, no refund for that cycle.
- **On any switch:** cancel the old plan immediately; if pending data exists the user
  chooses **Delete** or **Merge into the new plan** (retention upsell).

### 44.3 DONE this session (all live)
Identity-first login · pay-₹499-anytime (both doc gates removed) · post-payment lock
fixed · **server-authoritative entitlement (`account_state`)** · subscriber↔ops
messaging (both drawers + notifications) · superadmin alerts (signup/claim/lead) +
`?account=` deep-links → account drawer · Nidaan Google OAuth (`NIDAAN_GOOGLE_CLIENT_ID`)
· minimal ₹499 dashboard (raise-another-review + Settings, no "Subscribe to unlock") ·
redirect-chain + stuck-overlay killed · "Get Started Free" → "Choose <Plan>" · Nidaan
session cookie (Step 5 foundation) · PWA Steps 1/2/4 (no-flicker gate, dedicated
`/login` + login-first landing, auto-update toast).

### 44.4 Key mechanisms / where things live
- **Router:** `_loginSuccess` (static/nidaan_start.html) — identity-first; only
  brand-new accounts follow the button's `?plan`/`#get-reviewed` intent.
- **Entitlement:** `/nidaan/api/me` → `account_state`; dashboard gate uses
  `me.account_state.active`.
- **Messaging:** `nidaan_messages` table; biz_nidaan `list/add_claim_message`,
  `on_new_claim_message`; endpoints `…/claims/{id}/messages` (subscriber + ops); threads
  in both claim drawers.
- **Alerts:** biz_nidaan_notifications `on_subscriber_signup`, `on_lead_filed` (admin
  block), `on_claim_filed`; deep-link `?account=` handled by ops `_handleDeepLink` + bell.
- **Refund infra (EXISTS + works):** `check_refund_eligibility`, `create_refund_row`,
  `issue_razorpay_refund`, `update_refund_status`; used by `/nidaan/api/subscribe/cancel`
  (Policy A: refund within 7 days AND zero claims — this IS the plan→₹499 path). Settings
  already has **Cancel Subscription** + `switchPlan()` between plans.
- **Auth:** Nidaan JWT (30-day) in localStorage (Bearer) + a `nidaan_token` cookie
  (client-set, migrates existing users on load). Server-side routing + httpOnly = staged.

### 44.5 Remaining backlog (well-specified; mostly money/data-sensitive)
1. **₹499-refund-on-upgrade (₹499→plan):** cancel the paid ₹499 claim + refund via the
   EXISTING `issue_razorpay_refund` **iff** review not delivered (`review_outcome` null)
   AND `paid_at` ≤ 7 days; record in `nidaan_refunds`. **Build as a focused, test-with-a-
   real-transaction effort — do NOT ship blind.**
2. **Delete/Merge data choice** on cancel/switch (retention upsell) — surface in the
   Cancel Subscription flow.
3. **Render ALL active ₹499 reviews** at once (today the pay card shows only the first
   `unpaid_lead`; the claims table shows the rest). Add a "Pay ₹499" action to unpaid
   rows.
4. **Brand-new choice screen** polish (lock overlay already offers View Plans / Get a
   single review ₹499).
5. **Step 5 finish:** server-side routing + httpOnly cookie flip (after cookie migration).
6. **Stage-4 DB collapse (optional):** fully retire `nidaan_per_claim_purchase`; the
   entitlement decision is already single-sourced, so this is cleanup not urgency.

### 44.6 How to build #1 safely when ready
Endpoint `POST /nidaan/api/switch/499-to-plan {plan, data_choice}`: find the account's
paid ₹499 claim(s); for each eligible (not delivered, ≤7d) → `create_refund_row` +
`issue_razorpay_refund(payment_id, amount_paise=49900, …)` + `update_refund_status`;
mark claim cancelled (or merge per `data_choice`); then the client opens the subscribe
modal for `plan`. Verify on one real ₹499 payment before enabling for all.

### 44.7 Email branding + `/admin` as a separate installable ops app (Jul 9, 2026)
- **Email branding (fixed):** five Nidaan ₹499/lead admin emails in sarathi_biz.py
  omitted `from_name` → they sent as "Sarathi-AI Business Technologies". Added
  `from_name="Nidaan Partner"` to all (the "[Nidaan] ₹499 PAID — assign + begin
  review" admin email + the 4 review-lead/PAID/request admin emails).
- **`/admin` = its own installable PWA (fixed):** the ops portal lived at
  `/nidaan/ops`, INSIDE the subscriber app's scope `/nidaan/`, so "Add to Home
  Screen" said "already installed". Now: `/admin` **serves the ops portal directly**
  (was a 302 → /nidaan/ops); `nidaan-ops.webmanifest` `id/start_url/scope = /admin`
  (cleanly outside `/nidaan/`) → installs as a separate app. **Push/notification
  deep-links + SW `notificationclick` now target `/admin`** so a push tap opens the
  installed ops app (tasks / broadcasts / comments / new signup-claim-lead). Push
  **icon fixed** to the Nidaan logo (was Sarathi's); SW cache `nidaan-v4`. Ops still
  also reachable at `/nidaan/ops`. Subscriber app (scope `/nidaan/`) untouched.
  NOTE: a subscriber app installed long ago with an even broader old scope may need
  one uninstall+reinstall before the ops app installs cleanly.

### 44.8 Ops portal quality improvements (Jul 9, 2026)
1. **Broadcast reactions:** `list_broadcasts` returns `reactors {emoji:[names]}`;
   reaction bar has a **➕ full emoji panel** (40), each chip shows count + **who
   reacted** on hover (desktop `title`) and **long-press** (mobile → toast).
2. **Task status notify:** `on_quick_task_status_changed` notifies the assignee on
   reopen/reject/status-change (dashboard + push + WA/email, deep-linked). Reassign
   already notified.
3. **Green-blink broadened:** the unseen-activity dot now also lights on tasks you've
   previously opened when there's newer activity (not just your own), without
   flooding never-opened tasks; gray once opened. `last_activity` already includes
   the log (status/reassign/reopen).
4. **Task comment attachments:** `nidaan_quick_task_notes` +
   `attachment_stored_name/original_name`; the note endpoint is now multipart
   (optional file → gated docs dir → signed URL); ops task drawer has a 📎 attach
   button + per-comment download chip.

---

*This document is the single source of truth for the Sarathi-AI Business project. Keep it updated after every significant change.*

