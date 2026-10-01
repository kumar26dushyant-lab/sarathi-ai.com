# Sarathi-AI — End-to-End Stakeholder Flows

This document describes how each stakeholder uses the platform, step by step.

---

## Stakeholders

| Role | Description |
|------|-------------|
| **Superadmin (You)** | Platform owner — manages all tenants, monitors KPIs, handles billing |
| **Firm Owner** | Insurance/financial advisory firm — signs up, configures their instance, manages agents |
| **Agent** | Financial advisor working under a firm — uses Telegram bot + dashboard to manage clients |
| **Client/Lead** | End customer — interacts via WhatsApp, receives PDF reports, gets policy reminders |

---

## 1. Superadmin Flow

### Daily Operations
1. **Login** → `sarathi-ai.com/superadmin` → Enter phone (8875674400) + password → JWT cookie set
2. **Dashboard** → `GET /api/sa/dashboard` → View KPIs (total tenants, active bots, revenue, signup trend, lead stages)
3. **Monitor Tenants** → `GET /api/sa/tenants` → See all firms, their plans, trial status, bot status
4. **Audit Trail** → `GET /api/sa/audit` → Track all critical operations (signups, logins, payments, config changes)
5. **Revenue** → `GET /api/sa/revenue` → View payment history, MRR, plan distribution

### Tenant Management
6. **Extend Trial** → `POST /api/sa/tenant/{id}/extend?days=N` → Give a firm more trial time
7. **Activate Plan** → `POST /api/sa/tenant/{id}/activate?plan=team` → Manually activate a firm's paid plan
8. **Bot Management** → `GET /api/sa/bots` → See Telegram bot connection status per tenant

### Endpoints Used
| Endpoint | Purpose |
|----------|---------|
| `POST /api/sa/login` | Authenticate (cookie-based JWT) |
| `GET /api/sa/dashboard` | KPI overview |
| `GET /api/sa/tenants` | List all tenants |
| `GET /api/sa/bots` | Bot status |
| `GET /api/sa/audit` | Audit log |
| `GET /api/sa/revenue` | Revenue data |
| `GET /api/sa/me` | Current SA info |
| `POST /api/sa/tenant/{id}/extend` | Extend trial |
| `POST /api/sa/tenant/{id}/activate` | Activate plan |

---

## 2. Firm Owner Flow

### Initial Setup (Day 1)
1. **Visit** `sarathi-ai.com` → See landing page with features, pricing, demo
2. **Sign Up** → `sarathi-ai.com/onboarding` → Fill firm name, owner name, phone, email, city, plan
3. **API:** `POST /api/signup` → Creates tenant + owner agent → Returns `tenant_id` + 14-day trial
4. **Login** → `POST /api/auth/send-otp` (phone) → Receive OTP → `POST /api/auth/verify-otp` → JWT token

### Onboarding (Day 1-3)
5. **Branding** → `POST /api/onboarding/branding` → Set tagline, CTA, contact info
6. **Connect Telegram Bot** → Follow `sarathi-ai.com/telegram-guide` → Get Bot Token from @BotFather → Configure via bot
7. **Connect WhatsApp** → `POST /api/onboarding/whatsapp` → Enter Meta Business Phone Number ID + Access Token (validated against Meta API in real-time)
8. **Upload Agent Photo** → Dashboard → Upload profile photo (used in PDF reports)
9. **Onboarding Status** → `GET /api/onboarding/status` → See which steps are complete

### Payments
10. **View Plans** → `GET /api/payments/plans` → Individual (₹499/mo), Team (₹1499/mo), Enterprise (₹4999/mo)
11. **Create Order** → `POST /api/payments/create-order` → Razorpay order created → Pay via Razorpay checkout
12. **Verification** → Razorpay webhook → `POST /api/payments/webhook` → Plan activated automatically
13. **Check Status** → `GET /api/payments/status` → View subscription status

### Team Management (Team/Enterprise plans)
14. **Generate Invite** → `POST /api/admin/invite` → Get invite code + shareable URL
15. **Share Link** → `sarathi-ai.com/invite.html?code=XXXX` → Agent opens link
16. **Agent Joins** → Agent enters name + phone → `POST /api/invite/accept` → Added to firm

### Daily Usage
17. **Dashboard** → `GET /api/dashboard` → View stats (leads, policies, followups, renewals, subscription info)
18. **Calculators** → `GET /api/calc/{type}` → Run inflation, HLV, retirement, EMI, health, SIP calculations
19. **Reports** → `GET /api/report/{type}` → Generate branded PDF reports for clients (with agent photo + company branding)
20. **Campaigns** → `POST /api/campaigns` → Create WhatsApp campaigns to clients (Team/Enterprise only)

### Endpoints Used
| Endpoint | Purpose |
|----------|---------|
| `POST /api/signup` | Create firm |
| `POST /api/auth/send-otp` | Login step 1 |
| `POST /api/auth/verify-otp` | Login step 2 |
| `GET /api/auth/me` | Current user info |
| `POST /api/auth/refresh` | Refresh JWT |
| `POST /api/onboarding/branding` | Set firm branding |
| `POST /api/onboarding/whatsapp` | Configure WhatsApp |
| `GET /api/onboarding/status` | Onboarding progress |
| `GET /api/payments/plans` | View plans |
| `POST /api/payments/create-order` | Start payment |
| `GET /api/payments/status` | Payment status |
| `POST /api/admin/invite` | Generate invite code |
| `GET /api/dashboard` | Agent dashboard data |
| `GET /api/calc/*` | Run calculators |
| `GET /api/report/*` | Generate PDF reports |
| `POST /api/campaigns` | Create campaigns |
| `GET /api/campaigns` | List campaigns |
| `GET /api/wa/status` | WhatsApp connection status |
| `GET /api/gdrive/status` | GDrive connection status |

---

## 3. Agent Flow

### Joining a Firm
1. **Receive Invite Link** from firm owner → `sarathi-ai.com/invite.html?code=XXXX`
2. **Validate Code** → Page calls `GET /api/invite/validate/{code}` → Shows firm name
3. **Accept Invite** → Enter name + phone → `POST /api/invite/accept` → Joined to firm
4. **Connect Telegram** → Open firm's Telegram bot → `/start` → Auto-linked to firm

### Daily Work via Telegram Bot
5. **Add Lead** → Bot conversation → Enter client name, phone, email, needs
6. **Run Calculator** → Bot menu → Select calculator type → Enter params → Get instant result
7. **Generate Report** → Bot → Select report type → Enter client details → PDF generated with agent branding
8. **Share Report** → Bot sends report link → Agent forwards to client via WhatsApp/email
9. **View Followups** → Bot → See today's followups and upcoming renewals
10. **Set Reminders** → Bot → Set custom reminders for client callbacks
11. **AI Chat** → Bot → Ask questions about insurance products, regulations, sales tips (powered by Gemini 2.0 Flash)

### Web Dashboard
12. **Login** → `sarathi-ai.com/dashboard` → Phone OTP login
13. **View Stats** → Lead count, conversion rate, policy count, followup schedule
14. **Run Calculators** → `sarathi-ai.com/calculators` → Interactive calculator widgets
15. **Upload Photo** → Dashboard settings → Upload profile photo for report branding

---

## 4. Client/Lead Flow

### Initial Contact
1. **Agent adds client** via Telegram bot or CSV import
2. Client receives **WhatsApp message** from agent's firm number (automated or campaign)

### Interactions
3. **Receive Calculator Report** → Agent generates PDF report → Client gets link → Opens branded HTML report with inflation/HLV/retirement/EMI projections, agent photo + contact info
4. **WhatsApp Responses** → Client replies on WhatsApp → Webhook → Bot processes → Agent notified on Telegram
5. **Policy Reminders** → Automated WhatsApp reminders before renewal dates
6. **Follow-up Calls** → System creates followup tasks → Agent contacts client

### What the Client Sees
- **PDF Reports**: Professional HTML pages with firm branding, agent photo, calculator results, contact details
- **WhatsApp Messages**: Personalized messages from the firm's WhatsApp Business number
- **Support Page**: `sarathi-ai.com/support` for general help

---

## Integration Pipeline

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Superadmin  │     │  Firm Owner  │     │   Agent     │
│  Dashboard   │     │  Web Portal  │     │ Telegram Bot│
└──────┬───────┘     └──────┬───────┘     └──────┬──────┘
       │                    │                    │
       ▼                    ▼                    ▼
  ┌─────────────────────────────────────────────────┐
  │           FastAPI Server (sarathi_biz.py)        │
  │  • JWT Auth (phone OTP / SA password)            │
  │  • Role-based access (SA / Owner / Agent)        │
  │  • Rate limiting per endpoint                    │
  │  • Audit logging for all critical ops            │
  ├─────────────────────────────────────────────────┤
  │  Core Modules:                                   │
  │  biz_auth.py     — JWT, OTP, session management  │
  │  biz_database.py — SQLite, 21+ tables, migrations│
  │  biz_pdf.py      — Report generator + branding   │
  │  biz_calculators.py — 6 calculator engines        │
  │  biz_ai.py       — Gemini 2.0 Flash integration  │
  │  biz_bot.py      — Telegram bot (52 states)       │
  │  biz_whatsapp.py — Meta WA Business API bridge   │
  │  biz_campaigns.py — Campaign engine               │
  │  biz_payments.py — Razorpay gateway               │
  │  biz_email.py    — Email OTP + notifications      │
  │  biz_gdrive.py   — Google Drive backup            │
  │  biz_reminders.py — Renewal + followup scheduler  │
  │  biz_i18n.py     — Internationalization           │
  │  biz_resilience.py — Circuit breaker, retry logic │
  │  biz_bot_manager.py — Multi-tenant bot lifecycle  │
  └────────────┬────────────────────────────────────┘
               │
   ┌───────────┼───────────┬──────────────┐
   ▼           ▼           ▼              ▼
┌────────┐ ┌────────┐ ┌──────────┐ ┌───────────┐
│ SQLite │ │Telegram│ │ WhatsApp │ │ Razorpay  │
│  DB    │ │Bot API │ │ Meta API │ │ Payments  │
└────────┘ └────────┘ └──────────┘ └───────────┘
                                   ┌───────────┐
                                   │  Gemini   │
                                   │ 2.0 Flash │
                                   └───────────┘
```

---

## Key Metrics (from test run)

| Metric | Value |
|--------|-------|
| Total API paths | 146 |
| Static pages | 15 (all with dark mode) |
| Calculator types | 6 |
| Report types | 4 (all with agent photo branding) |
| Database tables | 21+ |
| Telegram bot states | 52 |
| Auth methods | Phone OTP, Email OTP, SA password, JWT Bearer, Cookie |
| Payment plans | 3 (Individual ₹499, Team ₹1499, Enterprise ₹4999) |
| Test coverage | 72/72 tests, 100% pass rate |
