# Sarathi-AI Business Technologies — Complete Project Context

> **Purpose:** This document captures the full project context so any AI assistant (or new developer) can resume work without needing repeated briefings. Update this file at the end of every major session.

---

## 1. Project Identity

| Field | Value |
|-------|-------|
| **Product** | Sarathi-AI Business Technologies |
| **Type** | Multi-tenant Financial Advisor CRM SaaS (voice-first) |
| **Working Dir** | `c:\sarathi-business` (production) |
| **Legacy Dir** | `c:\sarathi` (OLD — **do not use**). Note: user sometimes edits `c:\sarathi\biz.env`; server loads `c:\sarathi-business\biz.env` |
| **Stack** | Python 3.12 · FastAPI · aiosqlite · python-telegram-bot v21.11.1 · google-genai (Gemini 2.5 Flash) · Razorpay · WhatsApp Cloud API |
| **Server** | Port 8001, host 0.0.0.0 |
| **Public URL** | ngrok: `nonseparable-undarned-geoffrey.ngrok-free.dev` |
| **Telegram Master Bot** | @SarathiBizBot (display name: "Sarathi-AI.com") — onboarding & SA panel |
| **Telegram Tenant Bots** | Per-tenant bot instances via `BotManager` (e.g., Kapoor Financial Group bot) |
| **App Version** | 3.0.0 |
| **Codebase Size** | ~12,100 lines biz_bot.py + other modules ≈ **26,000+ lines total** |

---

## 2. Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│                    sarathi_biz.py                       │
│              (FastAPI + uvicorn entry point)            │
├──────────────┬────────────────┬────────────────────────┤
│  Web Server  │  Telegram Bots │  Background Scheduler  │
│  (FastAPI)   │  (BotManager)  │  (biz_reminders)       │
├──────────────┴────────────────┴────────────────────────┤
│                                                        │
│  biz_bot.py        — Telegram CRM bot (~12,100 lines)  │
│  biz_database.py   — SQLite multi-tenant DB (~3,400)   │
│  biz_bot_manager.py — Per-tenant bot mgmt (~340)       │
│  biz_whatsapp.py   — WhatsApp Cloud API (~745)         │
│  biz_ai.py         — Gemini AI intelligence (~714)     │
│  biz_calculators.py — 9 financial calculators (~900)   │
│  biz_payments.py   — Razorpay subscriptions (~600)     │
│  biz_i18n.py       — EN/HI translations (~583)        │
│  biz_reminders.py  — Auto-reminders engine (~575)      │
│  biz_auth.py       — JWT + OTP auth (~550)             │
│  biz_resilience.py — Retry/queue/health (~479)         │
│  biz_pdf.py        — Branded PDF reports (~458)        │
│  biz_campaigns.py  — Bulk messaging (~402)             │
│  biz_gdrive.py     — Google Drive upload (~399)        │
│  biz_email.py      — SMTP transactional (~259)         │
│                                                        │
│  static/           — 16 HTML pages + logo              │
│  generated_pdfs/   — Calculator PDF reports            │
│  sarathi_biz.db    — SQLite runtime database           │
└────────────────────────────────────────────────────────┘
```

### Three Runtime Components

1. **FastAPI Web Server** (uvicorn) — Serves HTML pages, REST API endpoints, PDF files
2. **Telegram CRM Bots** (master + per-tenant via `BotManager`) — Agent-facing sales interface with voice-first AI
3. **Background Scheduler** (`biz_reminders`) — Birthdays, renewals, follow-ups, daily summaries

---

## 3. File Inventory

### Python Modules (16 files)

| File | ~Lines | Purpose |
|------|-------:|---------|
| `sarathi_biz.py` | 6,500 | Main entry — FastAPI server, 80+ API endpoints, bot launcher, scheduler |
| `biz_bot.py` | 12,100 | Multi-tenant Telegram CRM bot (auth, menus, lead mgmt, AI pitch, voice-first, 9 calculators, WhatsApp sharing, SA panel) |
| `biz_database.py` | 3,400 | Async SQLite — tenants, agents, leads, policies, interactions, reminders, payments, audit log, team mgmt |
| `biz_whatsapp.py` | 745 | WhatsApp Cloud API — multi-tenant messaging, OTP, webhook routing, wa.me fallback, token expiry auto-recovery |
| `biz_ai.py` | 714 | 8 Gemini-powered features: lead scoring, pitch gen, follow-up, policy recommender, objection handler, renewal intel |
| `biz_calculators.py` | 900 | Pure-math calculators: Inflation Eraser, HLV, Retirement, EMI, Health Cover, SIP vs Lumpsum, Child Education, Pension, Wealth |
| `biz_payments.py` | 600 | Razorpay: subscription plans, checkout, webhook verify, auto-activation |
| `biz_i18n.py` | 583 | Bilingual string table (EN + HI), `t(lang, key)` helper |
| `biz_reminders.py` | 575 | Background scheduler: birthdays, anniversaries, renewals, follow-ups, daily summaries, trial expiry |
| `biz_auth.py` | 550 | JWT (HS256) + OTP, phone validation, tenant isolation, bleach sanitization, DEV_MODE test OTP support |
| `biz_resilience.py` | 479 | Retry with exponential backoff, graceful degradation, message queue, health monitoring |
| `biz_pdf.py` | 458 | HTML→PDF branded calculator reports |
| `biz_campaigns.py` | 402 | Bulk birthday/festival/announcement campaigns via WhatsApp & Email with tracking |
| `biz_gdrive.py` | 399 | OAuth2 Google Drive upload, per-tenant folder hierarchy |
| `biz_email.py` | 259 | SMTP transactional (welcome, OTP, trial expiry, payment receipt, recovery) |
| `biz_bot_manager.py` | 340 | BotManager — spins up/manages one Telegram bot instance per tenant, webhook routing |

### HTML Pages (static/, 16 pages, ~10,300+ lines)

| File | Lines | Description |
|------|------:|-------------|
| `static/index.html` | 2,105 | Homepage — AI-Powered CRM branding, feature showcase, inline demo, pricing, signup |
| `static/demo.html` | 1,565 | Comprehensive interactive product demo — 6 view tabs (Laptop, Mobile, PWA, Telegram, WhatsApp, Calculators) with 3D device frames |
| `static/calculators.html` | 1,352 | 9 financial calculators with live computation and branded UI |
| `static/dashboard.html` | 844 | Agent dashboard — KPIs, pipeline funnel, follow-ups, renewals |
| `static/getting-started.html` | 642 | Step-by-step setup guide |
| `static/admin.html` | 611 | Admin panel — tenant management, agent overview |
| `static/superadmin.html` | ~600 | Super Admin panel — tenant CRUD, system stats, plan management |
| `static/onboarding.html` | 521 | Tenant/agent onboarding flow |
| `static/partner.html` | ~500 | Partner/referral program page |
| `static/help.html` | 383 | Help & guide documentation |
| `static/telegram-guide.html` | ~350 | Telegram bot setup instructions |
| `static/support.html` | ~300 | Customer support page |
| `static/terms.html` | 232 | Terms of Service |
| `static/privacy.html` | 200 | Privacy Policy |
| `static/dashboard_old.html` | ~800 | Legacy dashboard backup |
| `static/index_backup.html` | 1,884 | Backup of previous homepage version |

### Other Files

| File | Description |
|------|-------------|
| `biz_requirements.txt` | Python dependencies (13 packages) |
| `biz.env` | Environment config (26 keys) |
| `Dockerfile` | Container definition |
| `docker-compose.yml` | Docker Compose config |
| `sarathi_biz.db` | SQLite runtime database |
| `static/logo.png` | Brand logo |
| `generated_pdfs/` | Output dir for calculator PDF reports |

### Test Files (5 files)

| File | Lines | Description |
|------|------:|-------------|
| `test_e2e_360.py` | 744 | 65 endpoints across 11 categories |
| `_e2e_test.py` | 201 | Comprehensive E2E suite |
| `test_biz.py` | 81 | Quick smoke test for all modules |
| `_smoke_test.py` | 76 | Security + page features test |
| `_clean_test.py` | ~22 | DB inspection utility |

---

## 4. Server Routes

All routes are defined in `sarathi_biz.py`:

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Homepage (index.html) |
| `/onboarding` | GET | Onboarding flow |
| `/health` | GET | Health check |
| `/admin` | GET | Admin dashboard |
| `/superadmin` | GET | Super Admin panel |
| `/calculators` | GET | Calculator pages |
| `/dashboard` | GET | Agent dashboard |
| `/help` | GET | Help & guide |
| `/privacy` | GET | Privacy policy |
| `/terms` | GET | Terms of service |
| `/getting-started` | GET | Setup guide |
| `/demo` | GET | Interactive product demo |
| `/partner` | GET | Partner program page |
| `/support` | GET | Customer support |
| `/telegram-guide` | GET | Telegram bot setup guide |
| `/static/*` | Mount | Static files directory |
| `/reports/*` | Mount | Generated PDF directory |
| `/api/signup` | POST | Tenant registration |
| `/api/auth/*` | Various | Authentication endpoints (login, verify-otp, refresh, logout) |
| `/api/onboarding/*` | Various | Web onboarding flow (register, verify, link) |
| `/api/leads/*` | Various | Lead CRUD |
| `/api/calculators/*` | POST | Calculator computations (9 calculators) |
| `/api/payments/*` | Various | Razorpay integration (checkout, plans, webhook) |
| `/api/whatsapp/*` | Various | WhatsApp webhook + send |
| `/api/telegram/webhook/{token_hash}` | POST | Per-tenant Telegram bot webhook |
| `/api/payments/webhook` | POST | Razorpay payment webhook |
| `/webhook` | GET/POST | WhatsApp webhook (verify + receive) |

---

## 5. Key Features

### CRM Core
- Multi-tenant architecture with tenant isolation (DB-level `tenant_id` on every table)
- Lead lifecycle: New → Contacted → Pitched → Proposal Sent → Won/Lost
- Policy tracking with renewal management
- Interaction logging (calls, meetings, follow-ups)
- Role-based access: **Owner** (full control), **Admin** (team mgmt), **Agent** (leads only)
- Plan-based feature gating: **Trial** (14 days), **Individual** (₹199/mo, 1 agent), **Team** (₹799/mo, 6 agents), **Enterprise** (₹1,999/mo, 26 agents)

### Authentication & Security
- **OTP-based login** on Telegram tenant bots (no passwords)
- DEV_MODE fixed OTP "123456" for test phones (prefix `98765`)
- JWT (HS256) for web API authentication
- Super Admin OTP sessions with 1-hour timeout
- Max 5 OTP attempts with lockout on all flows
- Cross-channel OTP: Web registration → Telegram linking via OTP verification
- Logout/re-login support with placeholder-based unlinking (`logout_*`, `web_*`, `__unlinked_*`, `__deactivated_*`)
- **24hr agent session expiry** — `AGENT_SESSION_TIMEOUT = 86400` (biz_bot.py). After 24hrs, agent must re-OTP
- **Deactivated agent block** — Deactivated agents are blocked at `cmd_start` and `registered` decorator
- **One-phone-one-firm** — Agent phone checked across all tenants during onboarding (`check_agent_phone_available()`)
- **Agent self-exit** — `/leave` command for agents to voluntarily exit firm (owners blocked)

### AI Intelligence (Gemini 2.5 Flash)
- Lead scoring (AI-assigned priority)
- AI Pitch Generator (context-aware talking points)
- Follow-up message suggestions
- Policy recommender based on client profile
- Objection handling coach
- Renewal intelligence
- **Voice-to-Action** (voice note → 28 structured intents)
- **Just Talk** (text → 15 intents, conversational AI routing)
- Claims helper (document checklists, timelines)

### Voice-First System (28 Intents)
The bot processes voice notes via Gemini transcription → intent detection → action routing:

| # | Intent | Description |
|---|--------|-------------|
| 1 | CREATE LEAD | Voice-create new lead with name/phone/city |
| 2 | LOG MEETING | Log a meeting/call interaction |
| 3 | UPDATE STAGE | Move lead to new pipeline stage |
| 4 | CREATE REMINDER | Set follow-up reminder |
| 5 | ADD NOTE | Add note to existing lead |
| 6 | LIST LEADS | Show my leads |
| 7 | SHOW PIPELINE | Show pipeline funnel |
| 8 | SHOW DASHBOARD | Show KPI dashboard |
| 9 | SHOW RENEWALS | Show upcoming renewals |
| 10 | SHOW TODAY | Show today's tasks |
| 11 | SETUP FOLLOWUP | Schedule a follow-up |
| 12 | SEND WHATSAPP | Send WhatsApp message to lead |
| 13 | SEND GREETING | Send birthday/anniversary greeting |
| 14 | EDIT LEAD | Edit lead details |
| 15 | ASK AI | Free-form AI question |
| 16 | AI LEAD SCORE | Score a lead with AI |
| 17 | AI PITCH | Generate pitch for lead |
| 18 | AI FOLLOWUP SUGGEST | AI-suggested follow-up |
| 19 | AI RECOMMEND | AI policy recommendation |
| 20 | OPEN CALCULATOR | Open calculator menu |
| 21 | SELECT CALCULATOR | Pick specific calculator |
| 22 | CALC COMPUTE | Compute calculator with voice params |
| 23 | SEND CALC RESULT | Share calculator result via WhatsApp |
| 24 | SHOW TEAM | Show team/agents (admin voice intent) |
| 25 | SHOW PLANS | Show subscription plans |
| 26 | SHOW SETTINGS | Open settings |
| 27 | SA PANEL | Open Super Admin panel |
| 28 | GENERAL | Conversational catch-all |

### Telegram Bot Architecture

#### Master Bot (@SarathiBizBot)
- Onboarding: New firm registration → bot token provisioning
- Super Admin panel: `/sa` with OTP authentication
- SA commands: `/sa_create`, `/sa_edit`, `/sa_logout`

#### Tenant Bots (One per firm)
- Each tenant has their own Telegram bot with custom token
- Managed by `BotManager` — auto-starts all active tenant bots on server startup
- Webhook routing: Unique hash per bot token → `/api/telegram/webhook/{token_hash}`
- OTP login: `/start` → identify agent → OTP verify → role-based menu
- Full CRM interface: leads, pipeline, calculators, AI, WhatsApp sharing, settings

#### Conversation States (60 total)
```
ONBOARD_CHOICE(0)  ONBOARD_FIRM(1)    ONBOARD_NAME(2)     ONBOARD_PHONE(3)
ONBOARD_EMAIL(4)   ONBOARD_INVITE(5)  ONBOARD_BOT_TOKEN(6) ONBOARD_LANG(7)
ONBOARD_VERIFY_OTP(8) LEAD_NAME(9)    LEAD_PHONE(10)      LEAD_PHONE_CONFIRM(11)
LEAD_DOB(12)       LEAD_ANNIVERSARY(13) LEAD_CITY(14)     LEAD_NEED(15)
LEAD_NEED_DONE(16) LEAD_NOTES(17)     LEAD_EMAIL(18)      FOLLOWUP_LEAD(19)
FOLLOWUP_TYPE(20)  FOLLOWUP_NOTES(21) FOLLOWUP_DATE(22)   CONVERT_LEAD(23)
CONVERT_STAGE(24)  POLICY_LEAD(25)    POLICY_INSURER(26)  POLICY_PLAN(27)
POLICY_TYPE(28)    POLICY_SI(29)      POLICY_PREMIUM(30)  POLICY_START(31)
POLICY_RENEWAL(32) CALC_TYPE(33)      CALC_INPUT(34)      CALC_RESULT(35)
WA_LEAD(36)        WA_MESSAGE(37)     GREET_LEAD(38)      GREET_TYPE(39)
SEARCH_QUERY(40)   EDITPROFILE_CHOICE(41) EDITPROFILE_VALUE(42) EDITLEAD_ID(43)
EDITLEAD_FIELD(44) EDITLEAD_VALUE(45)  CLAIM_LEAD(46)      CLAIM_POLICY(47)
CLAIM_TYPE(48)     CLAIM_DESC(49)     CLAIM_HOSPITAL(50)  CLAIM_CONFIRM(51)
ONBOARD_VERIFY_EMAIL_OTP(52) ONBOARD_CITY(53) ONBOARD_LINK_WEB(54)
ONBOARD_LINK_WEB_OTP(55) TEAM_EDIT_FIELD(56) TEAM_EDIT_VALUE(57)
LOGIN_PHONE(58)    LOGIN_OTP(59)
```

#### Menu System (Role + Plan Based)
- `_full_menu_inline()` — InlineKeyboard with buttons gated by role (owner/admin/agent) and plan (trial/individual/team/enterprise)
- `_settings_keyboard()` — Settings with admin-only options (Add Agent, Team, Admin Panel)
- Button layout: My Leads, Add Lead, Pipeline (row 1) → Dashboard, Renewals, Claims (row 2) → AI Pitch, Ask AI (row 3) → Calculators, Calendar, Search (row 4) → Settings (row 5)
- Enterprise-only: Admin Controls button

#### Key Bot Commands
```
/start      — Login/register (OTP-based on tenant bots)
/logout     — Unlink Telegram from agent account
/leave      — Agent self-exit from firm (owners blocked)
/addlead    — Add new lead (conversation flow)
/leads      — List agent's leads
/pipeline   — Pipeline funnel view
/dashboard  — KPI dashboard
/calc       — Financial calculators
/settings   — Settings menu
/team       — Team management (admin+)
/plans      — Subscription plans
/sa         — Super Admin panel (SA-only, OTP-protected)
/sa_logout  — End SA session
/cancel     — Cancel any active conversation
```

### Telegram Bot Commands (24+ registered)
```
/pipeline, /leads, /lead, /renewals, /dashboard, /wa, /wacalc, /wadash,
/greet, /lang, /settings, /weblogin, /help, /listenhelp, /plans, /claims,
/claimstatus, /ai, /team, /createbot, /wasetup, /cancel, /refresh, /logout
```

### Financial Calculators (9)
1. **Inflation Eraser** — Shows wealth erosion impact over time
2. **HLV (Human Life Value)** — Calculates exact insurance cover needed
3. **Retirement Planner** — Monthly SIP goals for retirement corpus
4. **EMI Calculator** — Loan EMI computations
5. **Health Cover** — Ideal mediclaim amount based on age/city/family
6. **SIP vs Lumpsum** — Investment comparison with visual charts
7. **Child Education** — Future education cost planning
8. **Pension Calculator** — Pension/annuity planning
9. **Wealth Builder** — Long-term wealth accumulation projections

### Voice-Driven Calculator Flow
- 3 dedicated voice intents: OPEN CALCULATOR (#20), SELECT CALCULATOR (#21), CALC COMPUTE (#22)
- Voice can specify calculator type + all parameters in a single message
- Results shared via WhatsApp with branded PDF (SEND CALC RESULT #23)

### WhatsApp Integration
- Multi-tenant Cloud API with per-tenant credentials
- Auto birthday/anniversary greetings (branded with firm details + IRDAI badge)
- Calculator PDF report sharing
- Renewal reminders with policy details
- OTP delivery
- wa.me deep-link fallback for token expiry (auto-detects 401/expired → generates wa.me links)
- Token expiry notification to owner

### Payments (Razorpay)
- Test key: `rzp_test_SJiDwBtMXVKiRk`
- 4 Plans: Trial (free/14 days), Individual (₹199/mo), Team (₹799/mo), Enterprise (₹1,999/mo)
- Subscription-based with auto-activation via webhook
- Plan change scheduling (upgrade immediate, downgrade at period end)
- Webhook verification with signature check

### Super Admin Panel
- OTP-protected access via SA phone (`SUPERADMIN_PHONES` env var)
- SA session management with 1-hour timeout (`_sa_sessions` dict)
- Accessible via `/sa` command or "sa_panel" voice intent
- Dashboard: Total tenants, active, trials, paid, expired, total agents, total leads, inactive agents (60d+)
- Tenant CRUD: Create, edit, activate/deactivate
- **Agent lifecycle management**: Per-tenant agent list with last_active, deactivate/reactivate buttons (SA-level)
- **Inactive agents view**: Platform-wide list of agents inactive 60+ days (yellow 60-89d, red 90d+)
- Commands: `/sa_create`, `/sa_edit`, `/sa_logout`
- SA callbacks with session validation (`_sa_callback`)

### Other Systems
- Background reminders (birthdays, renewals, follow-ups, daily summaries)
- Bulk campaign engine (WhatsApp + Email)
- Google Drive PDF backup
- Network resilience (retry, queue, degradation)
- Rate limiting (200 req/min via slowapi)
- Input sanitization (bleach)
- CORS whitelist for API security

---

## 6. Design System

| Element | Value |
|---------|-------|
| **Primary (Teal)** | `#0d9488` |
| **Accent (Saffron)** | `#f59e0b` |
| **Secondary (Indigo)** | `#4338ca` |
| **Success (Green)** | `#059669` |
| **Fonts** | Inter (body) + Poppins (headings) |
| **Dark BG** | `#0f172a` (slate-900) |
| **Card BG** | `rgba(255,255,255,0.04)` with backdrop-blur |
| **Border Radius** | Cards: 1.2rem, Buttons: 2rem, Inputs: 0.75rem |

---

## 7. Environment Configuration

```env
# ── Dev Mode ──
DEV_MODE=true  # Enables fixed test OTP "123456" for phones starting "98765"

# ── Telegram ──
TELEGRAM_BOT_TOKEN=<master bot token>
TELEGRAM_BOT_NAME=Sarathi-AI.com

# ── Super Admin ──
SUPERADMIN_PHONES=8875674400  # Comma-separated phone numbers

# ── WhatsApp Cloud API ──
WHATSAPP_PHONE_ID=<phone id>
WHATSAPP_ACCESS_TOKEN=<token>
WHATSAPP_VERIFY_TOKEN=<verify token>
WHATSAPP_APP_SECRET=<app secret>

# ── Server ──
SERVER_URL=https://nonseparable-undarned-geoffrey.ngrok-free.dev
SERVER_PORT=8001

# ── AI ──
GEMINI_API_KEY=<api key>

# ── Branding ──
BRAND_COMPANY=Sarathi-AI Business Technologies
BRAND_AGENT=Sarathi-AI
BRAND_TAGLINE=...
BRAND_CTA=...
BRAND_EMAIL=...
BRAND_PRIMARY_COLOR=#0d9488
BRAND_ACCENT_COLOR=#f59e0b
BRAND_CTA_COLOR=#059669
BRAND_DOMAIN=sarathi-ai.com

# ── Auth ──
JWT_SECRET=<secret>
ADMIN_API_KEY=<key>

# ── Payments ──
RAZORPAY_KEY_ID=rzp_test_SJiDwBtMXVKiRk
RAZORPAY_KEY_SECRET=<secret>

# ── Email ──
SMTP_HOST=<host>
SMTP_PORT=587
SMTP_USER=<user>
SMTP_PASSWORD=<password>
SMTP_FROM_EMAIL=<email>

# ── Google Drive ──
GDRIVE_CLIENT_ID=<id>
GDRIVE_CLIENT_SECRET=<secret>
GDRIVE_REDIRECT_URI=<uri>
```

---

## 8. Dependencies (biz_requirements.txt)

| Package | Min Version | Purpose |
|---------|-------------|---------|
| `fastapi` | ≥0.115.0 | Web framework |
| `uvicorn[standard]` | ≥0.30.0 | ASGI server |
| `python-telegram-bot[job-queue]` | ≥21.0 | Telegram integration |
| `httpx` | ≥0.27.0 | Async HTTP client |
| `python-dotenv` | ≥1.0.0 | Env loading |
| `aiosqlite` | ≥0.20.0 | Async SQLite |
| `google-genai` | ≥1.0.0 | Gemini AI |
| `pytz` | ≥2024.1 | Timezone |
| `PyJWT` | ≥2.8.0 | JWT auth |
| `slowapi` | ≥0.1.9 | Rate limiting |
| `bleach` | ≥6.0.0 | Input sanitization |
| `bcrypt` | ≥4.0.0 | Password hashing |
| `aiosmtplib` | ≥3.0.0 | Async SMTP |

---

## 9. How to Run

```bash
cd c:\sarathi-business
py -3.12 -m pip install -r biz_requirements.txt
py -3.12 sarathi_biz.py
```

Server starts on `http://localhost:8001`. Requires ngrok tunnel for Telegram/WhatsApp webhooks.

---

## 10. Current Status (as of March 20, 2026)

### Active Test Tenant
- **Kapoor Financial Group** (tenant_id: 63, plan: team)
- Owner: Arjun Kapoor (phone: 9876501234, agent_id: 35)
- Agent: Rahul Jain (phone: 6767676767, agent_id: 37)
- SA testing via SUPERADMIN_PHONES=8875674400

### Recently Completed (Multi-Session)

#### Voice-First CRM System
- ✅ 28 voice intents in `_VOICE_PROMPT` (Gemini 2.5 Flash transcription → intent → action)
- ✅ 15 text intents in `_JUST_TALK_PROMPT` (conversational AI routing)
- ✅ Voice-driven calculator system (3 dedicated intents: open, select, compute)
- ✅ Send Calc Result intent (#23→24) — share calculator via WhatsApp by voice
- ✅ Admin voice intents: show_team (#24→25), show_plans (#25→26), show_settings (#26→27), sa_panel (#27→28)

#### OTP-Based Authentication
- ✅ OTP login on tenant bot `/start` (LOGIN_PHONE → LOGIN_OTP flow)
- ✅ `/logout` command + settings button callback
- ✅ Cross-channel OTP: web registration → Telegram linking via OTP verification
- ✅ DEV_MODE OTP display across all flows (shows OTP in bot message when DEV_MODE=true)
- ✅ Max 5 OTP attempts lockout on all flows (onboard, login, SA)
- ✅ `/cancel` escape hints on all OTP prompts
- ✅ Direct DB fallback when `link_agent_telegram` fails (in `onboard_link_web_otp` and `login_verify_otp`)

#### OTP Login Loop Bug Fix (Critical — March 20, 2026)
- **Root Cause**: `link_agent_telegram` only recognized `web_*` as placeholder. After logout, `telegram_id = logout_{agent_id}_{ts}` wasn't treated as a placeholder → re-linking always failed → infinite start/OTP loop
- **Fix**: `is_placeholder` now recognizes `web_*`, `logout_*`, AND `__unlinked_*` prefixes (biz_database.py line 595)
- **Additional Fix**: DEV_MODE OTP (`123456`) only works for phones starting `98765`. Other phones get random OTPs but OTP is now shown in the bot message when DEV_MODE=true
- **Additional Fix**: Added direct DB UPDATE fallback in `onboard_link_web_otp` and `login_verify_otp` when `link_agent_telegram` returns None

#### Role + Plan Based Menu System
- ✅ `_full_menu_inline()` — buttons gated by agent role + tenant plan
- ✅ `_settings_keyboard()` — admin-only settings (Add Agent, Team, Admin Panel)
- ✅ `cmd_admin_controls` for enterprise plan
- ✅ Plans: trial, individual (₹199), team (₹799), enterprise (₹1,999)

#### Super Admin Panel
- ✅ OTP-protected via SA phone (SUPERADMIN_PHONES env var)
- ✅ SA session management: `_sa_sessions` dict, 3600s timeout
- ✅ `/sa` command with OTP → session → SA panel with stats
- ✅ `/sa_logout` — end session
- ✅ SA callbacks with session validation
- ✅ Cancel/exit/quit text support for SA OTP flow
- ✅ Global catch-all SA OTP intercept (prevents Just Talk from processing OTP text)

#### WhatsApp Token Expiry Fix
- ✅ Auto-detects 401/expired token → generates wa.me deep-link fallback
- ✅ Token expiry notification to tenant owner

#### Agent Lifecycle & Session Management (March 20, 2026)
- ✅ **24hr agent session expiry** — `AGENT_SESSION_TIMEOUT = 86400`, `_start_session()` called at all auth points, `registered` decorator checks expiry
- ✅ **Deactivated agent block** — `cmd_start` blocks deactivated agents on per-tenant bots, `deactivate_agent_full()` unlinks telegram
- ✅ **One-phone-one-firm enforcement** — `check_agent_phone_available()` during onboarding (agents only, owners exempt)
- ✅ **`/leave` command** — Agent self-exit from firm. Owners blocked. Calls `deactivate_agent_full()`, clears session, notifies admin via Telegram
- ✅ **90-day auto-deactivate** — Scheduler job at 6AM daily via `run_inactive_agent_cleanup(90)` in `biz_reminders.py`. Uses `get_inactive_agents()` + `deactivate_agent_full()`. Notifies owner.
- ✅ **Activity tracking** — `touch_agent_activity()` called non-blocking from `registered` decorator, updates `agents.last_active`
- ✅ **SA agent lifecycle panel** — Enhanced `_sa_show_agents()` with last_active, deactivate/reactivate buttons. Platform-wide inactive agents view (60d+ threshold). Stats include deactivated and inactive counts.
- ✅ **`__deactivated_*` placeholder** — Added to `is_placeholder` in `link_agent_telegram` for potential reactivation

#### Other Completed
- ✅ Homepage branding refresh — AI sales emphasis
- ✅ Comprehensive interactive demo page (`/demo`) — 6 view tabs with 3D device frames
- ✅ 9 calculator backends and frontend pages
- ✅ 8 AI intelligence features (Gemini)
- ✅ Razorpay payment integration with 4 plans
- ✅ Network resilience engine
- ✅ Bilingual (EN/HI) throughout
- ✅ Master context document maintained

### Known Issues / Notes
- ngrok must be running for Telegram/WhatsApp webhooks to work (common issue: server starts but ngrok not running → 404 on webhooks)
- Two `biz.env` files: user sometimes edits `c:\sarathi\biz.env`, server loads `c:\sarathi-business\biz.env`
- DEV_MODE OTP "123456" only works for phones starting "98765"; other phones get random OTP (shown in DEV_MODE messages)
- Conversation timeout: 30 minutes (`CONV_TIMEOUT = 30 * 60`)
- `static/index_backup.html` preserves original homepage
- Test suites: `test_biz.py` (smoke), `test_e2e_360.py` (full 65-endpoint coverage)

### Pending / Discussed
- 🟡 **Production deployment** — Currently dev/ngrok setup
- 🟡 **User testing in progress** — Active testing of OTP flows, SA panel, voice intents, agent lifecycle

---

## 11. Database Schema (Key Tables)

### tenants
```
tenant_id (PK), firm_name, owner_name, phone, email, brand_tagline, brand_cta,
brand_phone, brand_email, brand_primary_color, brand_accent_color, irdai_license,
irdai_verified, plan, subscription_status, razorpay_sub_id, trial_ends_at,
subscription_expires_at, max_agents, wa_phone_id, wa_access_token, wa_verify_token,
owner_telegram_id, lang, is_active, created_at, updated_at, tg_bot_token,
feature_overrides, city, account_type, signup_channel, referral_code, brand_logo,
brand_credentials
```

### agents
```
agent_id (PK), tenant_id (FK), name, phone, email, role (owner/admin/agent),
telegram_id, lang, is_active, last_active, created_at, updated_at
```

### leads
```
lead_id (PK), tenant_id (FK), agent_id (FK), name, phone, email, dob,
anniversary, city, need, notes, stage, source, ai_score, priority,
created_at, updated_at
```

### Key Functions
- `link_agent_telegram(phone, telegram_id)` — Links agent phone to Telegram ID (recognizes `web_*`, `logout_*`, `__unlinked_*`, `__deactivated_*` as placeholders)
- `unlink_agent_telegram(telegram_id)` — Sets `telegram_id = logout_{agent_id}_{timestamp}` (preserves history, avoids UNIQUE constraint)
- `get_agent_by_phone_tenant(phone, tenant_id)` — Lookup agent for OTP login
- `get_agent(telegram_id)` — Get agent by Telegram ID (primary lookup)
- `touch_agent_activity(agent_id)` — Updates `last_active` timestamp (called from `registered` decorator)
- `check_agent_phone_available(phone, exclude_tenant_id)` — One-phone-one-firm check across all tenants
- `deactivate_agent_full(agent_id, tenant_id, reason)` — Full deactivation: `is_active=0` + `telegram_id=__deactivated_{id}_{ts}` + audit log
- `get_inactive_agents(days=90)` — Agents inactive for N days (excludes owners)
- `get_owner_agent_by_tenant(tenant_id)` — Get owner agent for a tenant

---

## 12. BotManager Architecture

### Lifecycle
```
Server Start → main()
  → start_master_bot(TELEGRAM_TOKEN, webhook_base_url)
    → build_bot(token, tenant_id=None, is_master=True)
    → set Telegram webhook: /api/telegram/webhook/{hash(master_token)}
  → start_all_tenant_bots()
    → SELECT tenants WHERE tg_bot_token IS NOT NULL AND is_active = 1
    → For each: start_tenant_bot(tenant_id, token)
      → build_bot(token, tenant_id, is_master=False)
      → set Telegram webhook: /api/telegram/webhook/{hash(tenant_token)}
```

### Webhook Routing
```
Telegram → POST /api/telegram/webhook/{token_hash}
  → bot_manager.process_webhook_update(token_hash, data)
  → _webhook_map[token_hash] → Application → process_update()
```

### Internal State
```python
_bots: Dict[int, Application]      # tenant_id → running bot app
_tokens: Dict[int, str]            # tenant_id → bot token
_webhook_map: Dict[str, Application]  # MD5(token) → bot app
```

---

## 13. OTP Authentication Flow

### Login Flow (Tenant Bot)
```
/start → cmd_start()
  → Agent found by telegram_id? → Show role-based menu (already linked)
  → Agent not found → Show tenant info + "Login" button
    → LOGIN_PHONE state: Enter 10-digit phone
    → Validate phone → Get agent by phone+tenant
    → Generate OTP → Send via WhatsApp (or show in DEV_MODE)
    → LOGIN_OTP state: Enter OTP
    → verify_otp(phone, otp) → True?
      → link_agent_telegram(phone, user_id)
      → Success → Show menu
      → Fail → Direct DB fallback UPDATE
    → Max 5 attempts → Lock out
```

### Logout Flow
```
/logout or settings_logout callback
  → unlink_agent_telegram(user_id)
    → Sets telegram_id = "logout_{agent_id}_{timestamp}"
  → Clear context.user_data
  → Show confirmation message
```

### Cross-Channel Linking (Web → Telegram)
```
Web signup → agent created with telegram_id = "web_{phone}_{ts}"
  → User opens tenant bot → /start
  → "onboard_confirm_yes" → OTP sent
  → ONBOARD_LINK_WEB_OTP → Verify OTP
  → link_agent_telegram() recognizes "web_*" as placeholder → UPDATE
  → Agent linked → Show menu
```

### SA OTP Flow
```
/sa → superadmin_only decorator
  → Check phone in SUPERADMIN_PHONES
  → Check _sa_sessions[phone] (1hr timeout)
  → Expired/missing → Generate OTP → Show (DEV_MODE)
  → _global_catch_all intercepts OTP text → _sa_verify_otp()
  → Max 5 attempts, cancel/exit/quit support
  → Success → Create session → Show SA panel
```

---

## 14. Session Continuity Instructions

**For AI assistants resuming work on this project:**

1. The production project is at `c:\sarathi-business` — NOT `c:\sarathi`
2. Read this file first to understand the full architecture
3. Check `biz.env` for current configuration values
4. The server runs on port 8001: `py -3.12 sarathi_biz.py`
5. **ngrok must be running** for Telegram/WhatsApp webhooks: `ngrok http 8001 --domain=nonseparable-undarned-geoffrey.ngrok-free.dev`
6. Always verify syntax after edits: `py -3.12 -c "import py_compile; py_compile.compile('filename.py', doraise=True)"`
7. To restart server: Kill python processes → Start `sarathi_biz.py` in background → Verify with `/health`
8. All HTML pages use a bilingual `_T` object with `setLang()` — any text changes need both EN and HI translations
9. Design system colors: Teal `#0d9488`, Saffron `#f59e0b`, Indigo `#4338ca`, Green `#059669`
10. Static files mount at `/static/`, PDFs at `/reports/`
11. Update the "Current Status" section of this file at the end of each session
12. The user prefers: incremental builds over big-bang changes, discussion before major architecture decisions, balanced conservative UI changes
13. DEV_MODE=true in biz.env → fixed OTP "123456" only for phones starting "98765"
14. SUPERADMIN_PHONES=8875674400 → SA access requires OTP session
15. Tenant bots are separate from master bot — each has its own token in `tenants.tg_bot_token`
16. `biz_bot.py` is ~12,200+ lines — use grep/search, don't read entire file
17. ConversationHandler uses 60 states (range(60)) — shared across all conversation flows
18. Voice intents: 28 in `_VOICE_PROMPT`, 15 in `_JUST_TALK_PROMPT`
19. Agent session: `AGENT_SESSION_TIMEOUT = 86400` (24hrs), `_start_session(context)` sets timestamp, `registered` decorator checks expiry
20. Agent lifecycle functions: `deactivate_agent_full()`, `check_agent_phone_available()`, `touch_agent_activity()`, `get_inactive_agents()`
21. SA agent management: `sa_agdeact_`, `sa_agreact_`, `sa_inactive` callback data prefixes in `_sa_callback`

---

*Last updated: March 20, 2026 — Agent lifecycle system (24hr session expiry, deactivated block, one-phone-one-firm, /leave, 90-day auto-cleanup, SA agent management), OTP login fix, SA OTP enhancements.*
