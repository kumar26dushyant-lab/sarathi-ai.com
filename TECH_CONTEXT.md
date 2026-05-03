# Sarathi-AI Business Technologies — Technical Context Document
> **Last Updated:** 2026-02-24 | **Version:** 3.1.0 | **Status:** Security Foundation Complete, 27/27 Tests Passing

---

## 1. PROJECT OVERVIEW

**Product:** Multi-tenant Insurance CRM SaaS platform for Indian insurance advisors.
**Monetization:** Freemium — 14-day trial → Razorpay-powered subscriptions (₹499/₹1,499/₹3,999 per month).
**Channels:** Web dashboard, Telegram CRM bot (per-tenant), WhatsApp Business API (planned).

**Brand Identity:**
- Company: Sarathi-AI Business Technologies
- Colors: Royal Blue `#1a56db` (primary), Saffron Orange `#ea580c` (accent), Dark Blue `#1e40af` (CTA)
- Font: Poppins (Google Fonts)
- Logo: Krishna peacock feather SVG (inline in all HTML pages)
- Domain: sarathi-ai.com

---

## 2. CRITICAL PATH NOTES

| Item | Detail |
|------|--------|
| **Active project directory** | `C:\sarathi-business` — ALL edits MUST target this directory |
| **Workspace root in VS Code** | `C:\sarathi` — this is the OLD v1.0.0 trading app, NOT the business app |
| **Python runtime** | Python 3.12 — always use `py -3.12` |
| **Server start command** | `Start-Process -FilePath "py" -ArgumentList "-3.12","c:\sarathi-business\sarathi_biz.py" -WorkingDirectory "c:\sarathi-business" -NoNewWindow` |
| **Database** | `C:\sarathi-business\sarathi_biz.db` (SQLite via aiosqlite) |
| **Port** | 8001 (env `SERVER_PORT`). Changed from 8000 to avoid conflict with Sarathi trading app. |
| **Ngrok tunnel** | `https://nonseparable-undarned-geoffrey.ngrok-free.dev` → localhost:8001 |
| **Admin key** | `sarathi-admin-2024-secure` (in biz.env as `ADMIN_API_KEY`, accessed via `Authorization: Bearer admin:<key>` header) |
| **JWT Secret** | In biz.env as `JWT_SECRET` (64-char hex, auto-generated if missing) |
| **PowerShell quirk** | Never use `#` comments in multi-line PowerShell commands — they get absorbed as comments and break execution |

---

## 3. FILE INVENTORY

### Python Backend (C:\sarathi-business\)

| File | Size | Purpose |
|------|------|---------|
| `sarathi_biz.py` | 46KB | **Main FastAPI server** — routes, startup, all API endpoints |
| `biz_database.py` | 42KB | Database layer — 12 tables, 37+ async functions |
| `biz_bot.py` | 103KB | Telegram CRM bot — all handlers, conversations, commands |
| `biz_bot_manager.py` | 11KB | Per-tenant bot lifecycle manager (BotManager singleton) |
| `biz_payments.py` | 21KB | Razorpay payment engine — orders, subscriptions, webhooks |
| `biz_calculators.py` | 23KB | Insurance calculator logic (inflation, HLV, retirement, EMI, health, SIP) |
| `biz_reminders.py` | 25KB | Reminder & greeting scheduler engine |
| `biz_i18n.py` | 21KB | Internationalization strings (Hindi/English) |
| `biz_pdf.py` | 17KB | PDF report generation (HTML→PDF via browser) |
| `biz_whatsapp.py` | 13KB | WhatsApp Business API integration |
| `biz_auth.py` | 10KB | **JWT auth module** — OTP login, token creation/verification, input sanitization, admin auth |
| `biz_email.py` | 8KB | **Transactional email** — SMTP templates (welcome, OTP, trial reminder, payment receipt, cancel) |
| `biz.env` | 1.8KB | Environment variables (tokens, keys, JWT secret, branding) |
| `biz_requirements.txt` | 735B | Python dependencies |
| `test_biz.py` | 2.5KB | Test suite |
| `_clean_test.py` | 790B | Test data cleanup utility |
| `_smoke_test.py` | 2.5KB | Security + feature smoke test (27 tests) |
| `Dockerfile` | 985B | Docker container definition |
| `docker-compose.yml` | 776B | Docker compose config |

### Frontend (C:\sarathi-business\static\)

| File | Size | Purpose |
|------|------|---------|
| `index.html` | 56KB | Homepage — pricing, signup form, Razorpay Checkout.js integration |
| `onboarding.html` | 27KB | 4-step tenant onboarding wizard (Telegram bot → Branding → IRDAI → Complete) |
| `calculators.html` | 59KB | 6 insurance calculators with PDF export |
| `dashboard.html` | 33KB | Advisor dashboard — stats, leads, followups, renewals, subscription banner |
| `admin.html` | 27KB | Admin panel — tenant management, bot management, stats |
| `help.html` | 12KB | **Help & guide** — accordion FAQs, search, getting started, CRM usage, calculators, billing, security |
| `privacy.html` | 8KB | **Privacy policy** — data collection, sharing, security, retention, rights |
| `terms.html` | 9KB | **Terms of service** — acceptable use, billing, cancellation, liability, IP |

---

## 4. DATABASE SCHEMA (SQLite — sarathi_biz.db)

### Tables (12 total)

1. **tenants** — Multi-tenant core. Columns: tenant_id (PK), firm_name, owner_name, phone, email, brand_* (tagline, cta, phone, email, primary_color, accent_color), irdai_license, irdai_verified, plan, subscription_status, razorpay_sub_id, trial_ends_at, subscription_expires_at, max_agents, wa_phone_id, wa_access_token, wa_verify_token, owner_telegram_id, tg_bot_token, lang, is_active, created_at, updated_at

2. **agents** — CRM agents per tenant. Columns: agent_id (PK), tenant_id (FK), telegram_id (UNIQUE), name, phone, email, role, lang, onboarding_step, is_active, created_at, updated_at

3. **leads** — Customer leads. Columns: lead_id (PK), agent_id (FK), name, phone, whatsapp, email, dob, anniversary, city, occupation, monthly_income, family_size, need_type, stage, source, notes, sum_insured, premium_budget, created_at, updated_at, closed_at

4. **policies** — Insurance policies. Columns: policy_id (PK), lead_id (FK), agent_id (FK), policy_number, insurer, plan_name, policy_type, sum_insured, premium, premium_mode, start_date, end_date, renewal_date, status, commission, notes, created_at

5. **interactions** — Lead interaction log. Columns: interaction_id (PK), lead_id (FK), agent_id (FK), type, channel, summary, follow_up_date, created_at

6. **reminders** — Scheduled reminders. Columns: reminder_id (PK), agent_id (FK), lead_id, policy_id, type, due_date, message, status, sent_at, created_at

7. **invite_codes** — Team invite codes. Columns: code (PK), tenant_id (FK), created_by (FK), max_uses, used_count, expires_at, is_active, created_at

8. **greetings_log** — Birthday/anniversary greeting tracker. Columns: greeting_id (PK), lead_id (FK), agent_id (FK), type, channel, message, sent_at

9. **calculator_sessions** — Calculator usage log. Columns: session_id (PK), agent_id (FK), lead_id, calc_type, inputs, result, pdf_path, shared_via, created_at

10. **daily_summary** — Agent daily metrics. Columns: summary_id (PK), agent_id (FK), summary_date, new_leads, follow_ups_done, deals_closed, premium_earned, commission, greetings_sent, created_at

11. **audit_log** — System audit trail. Columns: log_id (PK), tenant_id, agent_id, action, detail, ip_address, created_at

### Default Values
- `brand_primary_color`: `#1a56db` (Royal Blue)
- `brand_accent_color`: `#ea580c` (Saffron)
- `plan`: `trial`
- `subscription_status`: `trial`
- `max_agents`: 1

---

## SECURITY ARCHITECTURE (v3.1.0)

### Authentication
- **JWT-based auth** (HMAC-SHA256) via `biz_auth.py`
- **OTP login**: Phone-based, 6-digit, 10-min expiry, rate limited (5/min)
- **Token pair**: Access token (24h) + Refresh token (30d)
- **Token delivery**: `Authorization: Bearer <token>` header, `sarathi_token` httpOnly cookie, or `?token=` query param (transition)
- **Admin auth**: `Authorization: Bearer admin:<key>` header (backward compat: `?key=` query param with `Depends(auth.require_admin)`)

### Middleware
- **Rate limiting**: `slowapi` — 200 req/min default, 5/min for OTP, 10/min for verify
- **CORS**: Whitelist `SERVER_URL`, `localhost:8001`, `127.0.0.1:8001`
- **Input sanitization**: `bleach` HTML strip on all user text, phone validation (Indian 10-digit), email validation

### Endpoint Security
- Admin APIs: Protected by `Depends(auth.require_admin)` — no more inline key checks
- Tenant pages (`/dashboard`, `/calculators`): Check JWT cookie → query param tenant_id (backward compat)
- Auth endpoints: `/api/auth/send-otp`, `/api/auth/verify-otp`, `/api/auth/refresh`, `/api/auth/me`, `/api/auth/logout`
- Cancellation: `/api/subscription/cancel` — requires JWT auth, logs to audit_log, sends email

### Email System
- `biz_email.py` — async SMTP via `aiosmtplib`
- Templates: welcome, OTP code, trial reminder (3d/1d/expired), payment receipt, cancellation
- Config: `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` in biz.env (not yet configured)

---

## 5. API ENDPOINTS (43 total)

### Pages (HTML)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/` | None | Homepage with pricing & signup |
| GET | `/onboarding` | tenant_id query | 4-step onboarding wizard |
| GET | `/health` | None | Health check |
| GET | `/admin` | None (login in page) | Admin panel |
| GET | `/calculators` | tenant_id query | 6 insurance calculators |
| GET | `/dashboard` | tenant_id query | Advisor dashboard |

### Admin APIs (require `key` query param = ADMIN_API_KEY)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/admin/tenants` | List all tenants with details |
| GET | `/api/admin/stats` | Aggregate stats (total, trials, paid, expired, wiped) |
| POST | `/api/admin/tenant/{id}/extend` | Extend trial by N days |
| POST | `/api/admin/tenant/{id}/activate` | Manually activate paid subscription |
| POST | `/api/admin/tenant/{id}/deactivate` | Deactivate tenant |
| GET | `/api/admin/bots` | List running Telegram bots |
| POST | `/api/admin/tenant/{id}/bot/restart` | Restart tenant's bot |
| POST | `/api/admin/tenant/{id}/bot/stop` | Stop tenant's bot |

### Signup & Onboarding
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/signup` | New tenant registration (409 if duplicate phone, includes tenant_id + can_subscribe for expired) |
| POST | `/api/onboarding/telegram-bot` | Save tenant's Telegram bot token |
| POST | `/api/onboarding/whatsapp` | Save WhatsApp Business credentials |
| POST | `/api/onboarding/branding` | Save branding customization |
| GET | `/api/onboarding/status` | Get onboarding completion status |

### Payments (Razorpay)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/payments/create-order` | Create Razorpay checkout order |
| POST | `/api/payments/verify` | Verify payment & activate subscription |
| POST | `/api/payments/create-subscription` | Create recurring subscription |
| GET | `/api/payments/status` | Get tenant's subscription status |
| POST | `/api/payments/webhook` | Razorpay webhook receiver |
| GET | `/api/payments/plans` | List available plans with pricing |

### Calculators
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/calc/inflation` | Inflation calculator |
| GET | `/api/calc/hlv` | Human Life Value calculator |
| GET | `/api/calc/retirement` | Retirement planning calculator |
| GET | `/api/calc/emi` | EMI calculator |
| GET | `/api/calc/health` | Health insurance calculator |
| GET | `/api/calc/sip` | SIP calculator |
| GET | `/api/report/inflation` | Inflation PDF report |
| GET | `/api/report/hlv` | HLV PDF report |
| GET | `/api/report/retirement` | Retirement PDF report |
| GET | `/api/report/emi` | EMI PDF report |

### Dashboard
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/dashboard` | Dashboard data with subscription info (tenant_id or agent_id) |

### WhatsApp Webhook
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/webhook` | WhatsApp webhook verification |
| POST | `/webhook` | WhatsApp message receiver |

---

## 6. PAYMENT SYSTEM (Razorpay)

**Mode:** Test
**Key ID:** `rzp_test_SJiDwBtMXVKiRk`
**Key Secret:** `czKXbEyR3gNGkRVwcY1BV7Jv`
**Webhook URL:** `https://nonseparable-undarned-geoffrey.ngrok-free.dev/api/payments/webhook`
**Webhook Events:** All subscription.* and payment.* events enabled

### Plans
| Key | Name | Price | Max Agents |
|-----|------|-------|------------|
| `individual` | Solo Advisor | ₹499/mo | 1 |
| `team` | Team | ₹1,499/mo | 5 |
| `enterprise` | Enterprise | ₹3,999/mo | 25 |

### Payment Flow
1. User clicks "Subscribe" on homepage → `startPayment(planKey)` JS function
2. Frontend POSTs to `/api/payments/create-order` → gets Razorpay order_id
3. Opens Razorpay Checkout modal with order details
4. On success, POSTs to `/api/payments/verify` with razorpay_payment_id + razorpay_order_id + razorpay_signature
5. Backend verifies signature, activates subscription, sets expiry +30 days
6. Webhook (`/api/payments/webhook`) handles renewal/cancellation/failure events

### Trial Lifecycle
- Day 0: Signup → 14-day trial starts, `subscription_status=trial`
- Day 14: Trial expires → `subscription_status=expired`, `is_active=0`
- Day 14-25: Daily reminder notifications via Telegram
- Day 25: Data wipe → `subscription_status=wiped`, all leads/agents/policies deleted
- **Device-level trial locking** prevents re-trials from same device

---

## 7. TELEGRAM BOT SYSTEM

### Architecture
- **Master Bot:** @SarathiBizBot (token in biz.env) — handles new agent registration, routes to tenant bots
- **Per-Tenant Bots:** Created via @BotFather by tenants during onboarding → token saved in `tenants.tg_bot_token` → started by BotManager

### BotManager (biz_bot_manager.py)
- Singleton: `bot_manager = BotManager()`
- On server startup: starts master bot + all tenant bots with tokens
- Methods: `start_master_bot()`, `start_tenant_bot()`, `stop_tenant_bot()`, `restart_tenant_bot()`, `start_all_tenant_bots()`, `stop_all()`, `send_alert()`

### Bot Features (biz_bot.py — 103KB)
- `/start` — Agent registration with invite code flow
- Add leads (conversational flow)
- Search leads, view pipeline
- Follow-up reminders
- Policy management (add, view, renewal tracking)
- Calculator shortcuts
- Lead stage conversion flow
- Language toggle (Hindi/English)
- Daily summary reports

---

## 8. FRONTEND ARCHITECTURE

### Homepage (index.html — 56KB)
- Hero section with animated peacock feather logo
- "How it Works" — 4 steps
- Feature showcase (6 cards)
- Pricing section (3 plan cards with "Subscribe" buttons)
- Signup modal form (firm_name, owner_name, phone, email, plan)
- Razorpay Checkout.js integration
- Handles 409 duplicate phone → redirects to payment if expired

### Onboarding (onboarding.html — 27KB)
- Step 1: Create Telegram CRM Bot via @BotFather → paste token
- Step 2: Branding customization (tagline, CTA, colors)
- Step 3: IRDAI verification (optional)
- Step 4: Complete — links to dashboard & calculators

### Dashboard (dashboard.html — 33KB)
- Subscription status banner (trial/active/expired with days left)
- Summary cards (leads, policies, premium, pipeline)
- Today's follow-ups table
- Upcoming renewals table
- Auto-refreshes via `/api/dashboard?tenant_id=X`

### Calculators (calculators.html — 59KB)
- 6 calculators: Inflation, HLV, Retirement, EMI, Health, SIP
- Each with form inputs, real-time results, PDF export
- Branded with tenant colors

### Admin Panel (admin.html — 27KB)
- Login with admin API key
- Stats grid (total tenants, active trials, paid, expired, wiped, today's signups, agents, leads)
- Tenant table with search/filter
- Actions: Extend trial, Activate subscription, Deactivate
- Bot Management section: Master bot status, tenant bot cards with Restart/Stop buttons
- Modal dialogs for extend/activate actions

---

## 9. ENVIRONMENT VARIABLES (biz.env)

| Variable | Value | Purpose |
|----------|-------|---------|
| `TELEGRAM_BOT_TOKEN` | `8587280320:AAE8J...` | Master bot @SarathiBizBot token |
| `TELEGRAM_BOT_NAME` | `SarathiBizBot` | Master bot display name |
| `WHATSAPP_PHONE_ID` | `914405771764161` | WhatsApp Business phone ID |
| `WHATSAPP_ACCESS_TOKEN` | `EAANHAu3l4fs...` | WhatsApp API token |
| `SERVER_URL` | `https://nonseparable-undarned-geoffrey.ngrok-free.dev` | Public URL (ngrok) |
| `SERVER_PORT` | `8000` | FastAPI server port |
| `GEMINI_API_KEY` | `AIzaSyA9rTW...` | Google Gemini AI key |
| `BRAND_COMPANY` | `Sarathi-AI Business Technologies` | Company name |
| `BRAND_DOMAIN` | `sarathi-ai.com` | Production domain |
| `ADMIN_API_KEY` | `sarathi-admin-2024-secure` | Admin panel auth key |
| `RAZORPAY_KEY_ID` | `rzp_test_SJiDwBtMXVKiRk` | Razorpay test key |
| `RAZORPAY_KEY_SECRET` | `czKXbEyR3gNGkRVwcY1BV7Jv` | Razorpay test secret |

---

## 10. DEPENDENCIES (biz_requirements.txt)

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
python-telegram-bot[job-queue]>=21.0
httpx>=0.27.0
python-dotenv>=1.0.0
aiosqlite>=0.20.0
google-genai>=1.0.0
pytz>=2024.1
```

---

## 11. TEST DATA IN DATABASE

| tenant_id | Firm Name | Phone | Plan | Status | Notes |
|-----------|-----------|-------|------|--------|-------|
| 3 | Apex Insurance Solutions | 9876543210 | team | trial | Test data from accidental signup |
| 4 | Shield Insurance Agency | 8765432109 | individual | trial | Clean test tenant, 13 days left |

---

## 12. E2E TEST RESULTS (2026-02-24) — 31/31 PASSED

| Test | Result | Details |
|------|--------|---------|
| Server health | ✅ | v3.0.0, port 8000 |
| Homepage | ✅ | 200, 55KB |
| Onboarding page | ✅ | 200, 27KB |
| Calculators page | ✅ | 200, 58KB |
| Dashboard page | ✅ | 200, 32KB |
| Admin page | ✅ | 200, 27KB |
| Fresh signup | ✅ | tenant_id=4 created |
| Duplicate phone guard | ✅ | 409 with tenant_id in response |
| Onboarding status API | ✅ | Returns proper status |
| Payment order creation | ✅ | order_SJjFV3KMFW6LIs via Razorpay |
| Plans API | ✅ | 3 plans with Razorpay key |
| Dashboard subscription API | ✅ | Solo Advisor, trial, 13 days left |
| Admin stats API | ✅ | 2 tenants, 2 active trials |
| Admin bots API | ✅ | Master running, 0 tenant bots |
| Razorpay webhook reachable | ✅ | Via ngrok, returns {"status":"ignored"} |

---

## 13. KNOWN ISSUES & REMAINING WORK

### Completed ✅
- [x] Homepage redesign (Royal Blue + Saffron)
- [x] All sub-pages redesigned (dashboard, calculators, onboarding, admin)
- [x] Multi-tenant database schema
- [x] Trial lifecycle (14-day trial → expire → remind → wipe)
- [x] Device-level trial locking
- [x] Admin dashboard with full tenant management
- [x] Per-tenant Telegram bot system (BotManager)
- [x] Razorpay payment integration (test mode)
- [x] Webhook configured and verified
- [x] Dashboard subscription status banner
- [x] Admin bot management tab
- [x] Expired trial → payment redirect (409 response with tenant_id + can_subscribe)
- [x] Agent-driven E2E testing

### Pending 🔄
- [ ] **Manual E2E testing by user** — complete signup → onboarding → bot → payment flow
- [ ] **WhatsApp Business API** — message sending, template messages, webhook handling
- [ ] **Production deployment** — VPS + domain (sarathi-ai.com) + SSL + nginx
- [ ] **Razorpay live mode** — switch from test to production keys after KYC
- [ ] **Email notifications** — signup confirmation, payment receipts, trial expiry warnings
- [ ] **Data export** — CSV/Excel export for leads, policies, reports
- [ ] **Mobile responsiveness audit** — final pass on all pages

---

## 14. DEPLOYMENT PLAN (for sarathi-ai.com)

### Recommended Stack
- **Server:** VPS (DigitalOcean/Hetzner/AWS Lightsail, 2GB RAM minimum)
- **OS:** Ubuntu 22.04 LTS
- **Reverse Proxy:** Caddy (auto-SSL) or Nginx + Certbot
- **Process Manager:** systemd service
- **Database:** SQLite (fine for early stage, migrate to PostgreSQL later)
- **Domain:** sarathi-ai.com → A record → VPS IP
- **SSL:** Auto via Caddy or Let's Encrypt

### Deployment Steps (future)
1. Provision VPS
2. Install Python 3.12, pip, venv
3. Clone/upload project files
4. Create venv, install requirements
5. Configure production biz.env (live Razorpay keys, real domain, etc.)
6. Set up Caddy/Nginx reverse proxy with SSL
7. Create systemd service for auto-start
8. Point sarathi-ai.com DNS to VPS IP
9. Update Razorpay webhook URL to https://sarathi-ai.com/api/payments/webhook
10. Update Telegram bot webhook to https://sarathi-ai.com
11. Test everything on production
