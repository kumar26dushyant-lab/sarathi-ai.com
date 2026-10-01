# Sarathi-AI Business Technologies — Stakeholder Flow Documentation

**Version:** 3.1.0  
**Date:** February 2026  
**E2E Test Status:** 58/58 passed (100%)

---

## Table of Contents

1. [Platform Overview](#1-platform-overview)
2. [Stakeholder Journeys](#2-stakeholder-journeys)
3. [Technical Architecture](#3-technical-architecture)
4. [Feature Inventory](#4-feature-inventory)
5. [E2E Test Results](#5-e2e-test-results)
6. [Current Limitations & Known Issues](#6-current-limitations--known-issues)
7. [Deployment Guide](#7-deployment-guide)

---

## 1. Platform Overview

Sarathi-AI Business Technologies is a **multi-tenant insurance CRM SaaS platform** designed for Indian insurance advisors and small wealth management firms. It combines:

- **Telegram Bot CRM** — Full lead pipeline management via bot commands
- **WhatsApp Cloud API** — Client engagement, greetings, report sharing
- **Financial Calculators** — 6 branded calculators with PDF report generation
- **Automated Reminders** — Birthday, anniversary, renewal, follow-up scheduling
- **Razorpay Payments** — Subscription billing with 3 pricing tiers
- **Bulk Campaigns** — Multi-channel outreach (WhatsApp, Email)
- **Bilingual Support** — English + Hindi across all touchpoints

### Target Market
- **Primary:** Tier 2/3 Indian insurance agents (IRDAI-certified, health/life)
- **Secondary:** Small wealth management firms (1-25 advisors)
- **Geography:** PAN-India, primarily Hindi-speaking regions

---

## 2. Stakeholder Journeys

### 2.1 Insurance Advisor Journey (Primary User)

```
┌─────────────────────────────────────────────────────────────────┐
│  DISCOVERY → SIGNUP → ONBOARDING → DAILY USE → GROWTH          │
└─────────────────────────────────────────────────────────────────┘
```

#### Phase 1: Discovery & Signup
1. Agent visits homepage (`/`) → Views pricing, features, demo panels
2. Selects a plan (Solo ₹499/mo, Team ₹1,499/mo, Enterprise ₹3,999/mo)
3. Fills signup form (firm name, name, phone, email, city, IRDAI license)
4. Receives 14-day free trial → Redirected to onboarding
5. Gets welcome email (if SMTP configured)

#### Phase 2: Onboarding (`/onboarding`)
1. **Step 1: Telegram Bot** — Clicks deep link to @SarathiBizBot → `/start web_{tenant_id}`
2. **Step 2: WhatsApp** — Enters WhatsApp Cloud API credentials (Phone ID, Access Token)
3. **Step 3: Branding** — Sets company tagline, CTA, phone, email, credentials
4. **Step 4: Test** — Sends a test calculator to verify setup

#### Phase 3: Daily CRM Operations (via Telegram)
```
Morning (8:30 AM):
  📊 Receives Daily Summary — today's follow-ups, birthdays, anniversaries,
     renewals, pipeline status, portfolio totals

Throughout the Day:
  ➕ /addlead    → Add new prospect (name, phone, DOB, city, need type)
  📊 /pipeline   → View funnel: Prospect → Contacted → Pitched → Proposal
                   → Negotiation → Closed Won/Lost
  📋 /leads      → List all leads with stage filters
  📞 /followup   → Schedule follow-up (call/visit/email) with date
  🧮 /calc       → Run financial calculator → Generate PDF → Share via WhatsApp
  🔄 /renewals   → View upcoming policy renewals (7/30/60 day windows)
  📱 /wa         → Send WhatsApp message to any lead
  🎂 /greet      → Send birthday/anniversary greeting via WhatsApp
  📈 /dashboard  → Business overview dashboard with stats
```

#### Phase 4: Lead Conversion Flow
```
Prospect → /addlead (capture details)
    ↓
Contacted → /followup (schedule callback)
    ↓
Pitched → /calc (run calculator, share report)
    ↓
Proposal Sent → /wa (send WhatsApp pitch)
    ↓
Negotiation → /followup (track objections)
    ↓
Closed Won → /convert (update stage) → /policy (record policy details)
    or
Closed Lost → /convert (record loss reason)
```

#### Phase 5: Automated Engagement
- **09:00 AM** — Auto birthday/anniversary WhatsApp greetings
- **10:00 AM** — Renewal reminders at T-60, T-30, T-15, T-7, T-3, T-1, T-0 days
- **10:00 AM** — Follow-up digest (today's pending + overdue)

---

### 2.2 Team Owner Journey (Firm Admin)

```
Owner Signup → Create Invite Code → Share with Agents → Monitor Team
```

1. Owner creates firm account → Gets `tenant_id`
2. Opens `/settings` → Team Management → Generate invite code
3. Shares invite code with agents (6-char alphanumeric, expiry-based)
4. Agents join via `/start` → Enter invite code → Auto-linked to firm
5. Owner views team dashboard → Aggregate stats across all agents
6. Owner manages branding → All agents use firm's logo/tagline

**Capabilities:**
- Max agents per plan: Solo=1, Team=5, Enterprise=25
- Invite codes: configurable max uses, expiry dates
- All leads, policies, interactions are tenant-isolated

---

### 2.3 Platform Admin Journey

```
Access: /admin?key=sarathi-admin-2024-secure
   or
API: Authorization: Bearer admin:<key>
```

**Admin Dashboard (`/admin`):**
| Action | Endpoint | Description |
|---|---|---|
| View all tenants | `GET /api/admin/tenants` | List with subscription status |
| Platform stats | `GET /api/admin/stats` | Aggregate metrics |
| Extend trial | `POST /api/admin/tenant/{id}/extend` | Add days to trial |
| Activate subscription | `POST /api/admin/tenant/{id}/activate` | Manual activation |
| Deactivate tenant | `POST /api/admin/tenant/{id}/deactivate` | Disable access |
| Bot status | `GET /api/admin/bots` | Master + tenant bot status |
| Restart bot | `POST /api/admin/tenant/{id}/bot/restart` | Restart tenant bot |
| Stop bot | `POST /api/admin/tenant/{id}/bot/stop` | Stop tenant bot |

**Trial Lifecycle Management:**
```
Day 1-14:    Active Trial (full features)
Day 10:      First reminder — "4 days left"
Day 13:      Urgent reminder — "Last day tomorrow!"
Day 14:      Final warning — "Trial ends today"
Day 15:      ⚠️ DEACTIVATED — features disabled, 10-day grace
Day 15-25:   Grace period — daily deletion countdown alerts
Day 25+:     🗑️ DATA WIPED — all leads, policies, agents permanently deleted
             Phone+email device-locked (no repeat free trials)
```

---

### 2.4 End Client Journey (Insurance Buyer)

Clients interact passively through WhatsApp:

```
WhatsApp Messages Received:
  🎂 Birthday greeting (branded, personalized)
  💍 Anniversary greeting (branded)
  🔄 Renewal reminder (with urgency: 🟢60d, 🟡30d, 🔴7d)
  📊 Calculator report (branded PDF with agent details)
  📱 Follow-up messages from agent
```

---

## 3. Technical Architecture

### Stack
| Component | Technology |
|---|---|
| **Backend** | Python 3.12 + FastAPI + uvicorn |
| **Database** | SQLite (aiosqlite) — `sarathi_biz.db` |
| **Bot Framework** | python-telegram-bot v21+ |
| **Payments** | Razorpay (subscriptions + one-time orders) |
| **WhatsApp** | Meta WhatsApp Business Cloud API v21.0 |
| **Auth** | JWT (HS256) + OTP (in-memory, dev mode) |
| **Security** | slowapi (rate limiting), bleach (XSS), bcrypt, CORS |
| **PDF** | Server-side HTML generation |
| **Email** | aiosmtplib (Gmail App Password) |
| **Cloud Storage** | Google Drive API (OAuth2) |
| **Tunnel** | ngrok (webhook delivery) |

### Database Schema (12 tables)
```
tenants ──┬── agents ──┬── leads ──┬── policies
          │            │           ├── interactions
          │            │           └── reminders
          │            ├── calculator_sessions
          │            └── daily_summary
          ├── invite_codes
          ├── audit_log
          └── campaigns ── campaign_recipients
              greetings_log
```

### API Surface: 65 endpoints across 11 categories
- 9 HTML pages
- 6 calculator APIs
- 4 report generators
- 5 auth endpoints
- 8 admin endpoints
- 4 onboarding endpoints
- 6 payment endpoints
- 4 WhatsApp endpoints
- 7 campaign endpoints
- 6 Google Drive endpoints
- 2 webhook endpoints
- Health check + OpenAPI docs

---

## 4. Feature Inventory

### 4.1 Financial Calculators
| Calculator | Key Inputs | Output |
|---|---|---|
| **Inflation Eraser** | Monthly amount, inflation%, years | Future value, adjustment needed |
| **Human Life Value** | Expenses, loans, children, cover | Required insurance cover |
| **Retirement Planner** | Age, retirement age, expenses | Corpus needed, monthly SIP |
| **EMI Calculator** | Premium, tenure, GST, CIBIL | Monthly EMI, total cost |
| **Health Cover** | Age, family size, city tier | Recommended cover amount |
| **SIP vs Lumpsum** | Amount, tenure, expected return | Comparison with growth charts |

### 4.2 Lead Pipeline Stages
```
Prospect → Contacted → Pitched → Proposal Sent → Negotiation → Closed Won
                                                              → Closed Lost
```

### 4.3 Bulk Campaign Types
| Type | Use Case |
|---|---|
| Birthday Wishes 🎂 | Auto-greet all leads with birthdays |
| Anniversary Wishes 💍 | Wedding anniversary outreach |
| Festival Greeting 🎉 | Diwali, Holi, Eid etc. |
| Announcement 📢 | Policy changes, company news |
| Product Promotion 🏷️ | New plan launches |
| Renewal Reminder 🔄 | Batch renewal notifications |
| Custom ✉️ | Free-form message with `{name}` templating |

### 4.4 i18n Coverage
| Component | EN | HI |
|---|---|---|
| Bot commands & menus | ✅ | ✅ |
| Onboarding flow | ✅ | ✅ |
| Calculator results | ✅ | ✅ |
| Pipeline/dashboard | ✅ | ✅ |
| Error messages | ✅ | ✅ |
| Homepage UI | ✅ | ✅ |
| Dashboard UI | ✅ | ✅ |
| Calculator UI | ✅ | ✅ |
| Email templates | ✅ | ✅ |
| WhatsApp greetings | ✅ | ✅ |
| Campaign messages | ✅ | ✅ |

---

## 5. E2E Test Results

**Test Suite:** `test_e2e_360.py`  
**Run Date:** February 2026  
**Base URL:** `http://localhost:8001`

### Summary
| Metric | Value |
|---|---|
| **Total Tests** | 58 |
| **Passed** | 58 |
| **Failed** | 0 |
| **Skipped** | 0 |
| **Pass Rate** | 100.0% |
| **Duration** | 120.8s |

### Test Categories
| # | Category | Tests | Status |
|---|---|---|---|
| 1 | Static Pages (7 public + 2 auth-gated) | 9 | ✅ All Pass |
| 2 | Health Check | 1 | ✅ Pass |
| 3 | Calculator APIs (6 calculators) | 6 | ✅ All Pass |
| 4 | Report Generation (4 report types) | 4 | ✅ All Pass |
| 5 | Signup Flow | 2 | ✅ All Pass |
| 6 | Authentication (OTP → JWT → Refresh → Logout) | 5 | ✅ All Pass |
| 7 | Payments (Plans, Order, Status) | 3 | ✅ All Pass |
| 8 | Admin API (Tenants, Stats, Bots, Auth, Actions) | 6 | ✅ All Pass |
| 9 | Onboarding (Status, Branding, WhatsApp) | 3 | ✅ All Pass |
| 10 | Dashboard API | 2 | ✅ All Pass |
| 11 | WhatsApp (Status, Webhook Verify) | 2 | ✅ All Pass |
| 12 | Google Drive (Status, Connect) | 2 | ✅ All Pass |
| 13 | Campaigns (Types, CRUD, Recipients, Delete) | 6 | ✅ All Pass |
| 14 | Subscription Management | 1 | ✅ Pass |
| 15 | Security (Invalid Admin Key, Invalid JWT, SQL Injection, XSS) | 4 | ✅ All Pass |
| 16 | API Documentation (OpenAPI, Swagger) | 2 | ✅ All Pass |

### Endpoint Coverage
- **62 OpenAPI paths documented** (confirmed via `/openapi.json`)
- **Auth flow fully tested:** Signup → OTP → JWT → Protected endpoints → Refresh → Logout
- **Security validated:** Invalid tokens rejected, SQL injection handled, XSS sanitized

---

## 6. Current Limitations & Known Issues

### 6.1 Development-Only Components
| Component | Status | Action Needed |
|---|---|---|
| **OTP System** | Mock — OTP returned in `_dev_otp` response field, never sent via SMS/WhatsApp | Integrate SMS gateway (MSG91, Kaleyra, etc.) for production |
| **Razorpay** | Test mode (`rzp_test_*` keys) | Switch to live keys for real payments |
| **ngrok Tunnel** | Temporary URL for webhook delivery | Set up permanent domain with SSL |
| **Swagger Docs** | Disabled (`/docs` returns 404) | Enable `docs_url="/docs"` in FastAPI() if needed |
| **Logo Image** | Referenced as `/static/logo.png` across all pages but **file not saved** to filesystem | Save actual PNG logo to `static/logo.png` |

### 6.2 Unconfigured Integrations
| Integration | Status | How to Enable |
|---|---|---|
| **SMTP Email** | `SMTP_USER` & `SMTP_PASSWORD` empty in `biz.env` | Get Gmail App Password: enable 2FA → generate app password at https://myaccount.google.com/apppasswords |
| **Google Drive** | `GDRIVE_CLIENT_ID` & `GDRIVE_CLIENT_SECRET` empty | Create OAuth2 Web Client at Google Cloud Console → enable Drive API → paste credentials |

### 6.3 Architecture Limitations
| Limitation | Impact | Mitigation Path |
|---|---|---|
| **SQLite** | Single-file database, no concurrent write scaling | Migrate to PostgreSQL for production (aiosqlite → asyncpg) |
| **In-memory OTP** | OTPs lost on server restart | Use Redis or database-backed OTP store |
| **Single-server** | No horizontal scaling, SPOF | Containerize (Docker Compose provided), add load balancer |
| **No CDN** | Static assets served by app server | Deploy to Cloudflare Pages/Vercel for frontend |
| **No file upload** | Logo/branding images referenced but not user-uploadable | Add file upload endpoint + S3/GCS storage |

### 6.4 Security Considerations
| Item | Current State | Recommendation |
|---|---|---|
| **JWT Secret** | Hardcoded in `biz.env` | Rotate periodically, use vault service |
| **Admin API Key** | Static key `sarathi-admin-2024-secure` | Implement admin user auth with MFA |
| **Rate Limiting** | slowapi (in-memory) | Sufficient for dev; use Redis-backed for production |
| **HTTPS** | Handled by ngrok only | Configure proper SSL certificates |
| **Cookie Security** | `secure=False` (dev mode) | Set `secure=True` in production |
| **CORS** | `allow_origins=["*"]` | Restrict to actual domain origins |

### 6.5 Feature Gaps
| Feature | Status | Priority |
|---|---|---|
| **Policy document upload** | Not implemented | High — agents need to attach scans |
| **Multi-language beyond Hindi** | Only EN/HI | Medium — add Marathi, Tamil, Gujarati |
| **Agent mobile app** | Bot-only interface | Medium — consider React Native wrapper |
| **Analytics/reporting** | Basic dashboard stats | Medium — add trend charts, conversion funnels |
| **Email campaigns** | Campaign type exists but SMTP not wired | Low — depends on SMTP config |
| **Custom Telegram bot branding** | Per-tenant bot tokens supported | Working — needs user to create bot via @BotFather |
| **Webhook retry logic** | No retry on delivery failure | Low — add exponential backoff |

---

## 7. Deployment Guide

### Local Development
```bash
# Prerequisites: Python 3.12, pip
cd sarathi-business
pip install -r biz_requirements.txt
py -3.12 sarathi_biz.py
# Server starts on http://localhost:8001
```

### Environment Configuration
All settings in `biz.env`:
```
TELEGRAM_BOT_TOKEN=<from @BotFather>
WHATSAPP_PHONE_ID=<Meta Business Suite>
WHATSAPP_ACCESS_TOKEN=<Meta Developer Portal>
SERVER_URL=<public URL for webhooks>
SERVER_PORT=8001
RAZORPAY_KEY_ID=<Razorpay Dashboard>
RAZORPAY_KEY_SECRET=<Razorpay Dashboard>
JWT_SECRET=<random 256-bit hex>
ADMIN_API_KEY=<strong random key>
```

### Docker
```bash
docker-compose up -d
```

### Production Checklist
- [ ] Switch Razorpay to live keys
- [ ] Set up real SMS/OTP provider
- [ ] Configure SMTP for email
- [ ] Set up Google Drive OAuth
- [ ] Deploy behind reverse proxy (nginx/Caddy) with SSL
- [ ] Set `secure=True` on cookies
- [ ] Restrict CORS origins
- [ ] Add monitoring/alerting (Sentry, UptimeRobot)
- [ ] Enable Swagger docs or remove `/openapi.json` in production
- [ ] Set up database backups
- [ ] Save logo.png to `/static/` directory
- [ ] Configure permanent domain (replace ngrok)

---

*Generated by Sarathi-AI 360° E2E Test Suite — February 2026*
