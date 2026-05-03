# SARATHI-AI — COMPLETE FEATURE INVENTORY

> **Version**: 3.0.0 | **Stack**: FastAPI + Python 3.12 + Telegram Bot + SQLite  
> **AI Engine**: Google Gemini (gemini-2.5-flash) | **Payments**: Razorpay  
> **Architecture**: Multi-tenant SaaS with per-tenant bots  

Legend: **Web** = Dashboard/Web Pages | **Bot** = Telegram Bot | **BG** = Background/Server-side

---

## 1. AUTHENTICATION & ONBOARDING

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 1.1 | OTP Login (Phone) | ✅ `/api/auth/send-otp` + `/api/auth/verify-otp` | ❌ | 6-digit, 10min expiry, 5 max attempts |
| 1.2 | OTP Login (Email) | ✅ Same endpoints | ❌ | Email OTP via SMTP |
| 1.3 | JWT Access Token | ✅ 24h expiry, HMAC-SHA256 | ❌ | Auto-refresh on web |
| 1.4 | JWT Refresh Token | ✅ 30d expiry | ❌ | `/api/auth/refresh` |
| 1.5 | Session Info | ✅ `/api/auth/me` | ❌ | Returns agent + tenant + plan details |
| 1.6 | Logout | ✅ `/api/auth/logout` | ❌ | Clears refresh cookie |
| 1.7 | Bot Onboarding `/start` | ❌ | ✅ Multi-step ConversationHandler | Choose language → Create Firm / Join Firm → name → phone → OTP verify → email → OTP verify → city → bot token setup |
| 1.8 | Web Deep-link from Bot | ❌ | ✅ `/start` sends dashboard link | Cross-channel linking: bot → web |
| 1.9 | Web Signup | ✅ `/api/signup` → onboarding flow | ❌ | `/onboarding` page with multi-step wizard |
| 1.10 | Invite Code Join | ✅ `/api/invite/accept`, `/api/invite/validate/{code}` | ✅ `ONBOARD_INVITE` state | Agents join existing firm via invite code |
| 1.11 | Super Admin Login | ✅ `/api/sa/login` phone + password (bcrypt) | ✅ `/sa` command (phone-based) | IP blocking after 5 failures |
| 1.12 | Role-based Access | ✅ JWT carries role | ✅ `@registered`, `@superadmin_only` decorators | Roles: superadmin > owner > admin > agent |
| 1.13 | Input Sanitization | ✅ bleach library | ✅ `h()` HTML escape | Prevents XSS |

---

## 2. LEAD MANAGEMENT (CRM Core)

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 2.1 | Add Lead | ✅ Dashboard → Leads tab → Add Lead modal | ✅ `/addlead` or ➕ button | Name → Phone → DOB → Anniversary → City → Need (multi-select) → Email → Notes |
| 2.2 | Duplicate Detection | ✅ API-level duplicate check | ✅ Phone-based duplicate warning + "View Existing" button | On phone entry |
| 2.3 | List Leads | ✅ Dashboard → Leads tab (data-table with search/filter) | ✅ `/leads` — paginated, stage-grouped | Web has richer filtering UI |
| 2.4 | View Lead Detail | ✅ Click lead row → detail panel | ✅ `/lead <id>` — full profile + interactions + policies | |
| 2.5 | Edit Lead | ✅ Dashboard inline edit | ✅ `/editlead <id>` — field selection (name/phone/email/dob/anniversary/city/need_type/notes) | Full validation on both |
| 2.6 | Delete Lead | ✅ `DELETE /api/admin/leads/{id}` | ❌ | Web only |
| 2.7 | Lead Pipeline View | ✅ Dashboard → Overview (KPI cards with stage counts) | ✅ `/pipeline` — stage-by-stage with counts & emoji | Stages: Prospect → Contacted → Proposal → Negotiation → Won → Lost |
| 2.8 | Move Lead Stage | ✅ Dashboard → stage dropdown / drag | ✅ `/convert <id>` — inline button stage selection | |
| 2.9 | Reassign Lead | ✅ `/api/admin/leads/{id}/reassign` | ❌ | Owner/admin can reassign to another agent |
| 2.10 | Lead Search/Filter | ✅ Dashboard leads tab — text search + stage filter | ✅ Limited (by command args) | Web is more powerful |
| 2.11 | CSV Import (Leads) | ✅ Dashboard → Import CSV modal (drag & drop, `/api/import/leads`) | ✅ Send CSV file directly in Telegram | Max 500 rows, auto-maps columns |
| 2.12 | CSV Template Download | ✅ `/api/import/template` | ❌ | Downloads sample CSV |
| 2.13 | Contact Preferences | ✅ `/api/leads/{id}/contact-pref` (GET+PUT) | ❌ | Per-lead preferred time, channel, language |
| 2.14 | Need Type Multi-select | ✅ Checkboxes in add-lead form | ✅ Inline keyboard with ✅ checkmarks | health, term, endowment, ulip, child, retirement, motor, investment, nps, general |
| 2.15 | Premium Budget | ✅ Lead add form field | ✅ Voice-to-Action extracts it | Optional lead field |

---

## 3. POLICY MANAGEMENT

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 3.1 | Add Policy | ✅ Dashboard → Policies tab → Add Policy modal | ✅ `/policy <lead_id>` — multi-step: insurer → plan → type → SI → premium → start → renewal | |
| 3.2 | List Policies | ✅ Dashboard → Policies tab (data-table) | ✅ Part of `/lead <id>` output | |
| 3.3 | Edit Policy | ✅ Dashboard inline edit (`PUT /api/admin/policies/{id}`) | ❌ | Web only |
| 3.4 | Delete Policy | ✅ `DELETE /api/admin/policies/{id}` | ❌ | Web only |
| 3.5 | AI Policy Extraction | ✅ Dashboard → Add Policy → "Extract from Text" or "Upload Image" | ❌ | Gemini reads pasted text or photo and fills form fields |
| 3.6 | Policy Types | Both | Both | health, term, endowment, ulip, child, retirement, motor, investment |
| 3.7 | Renewal Date Tracking | Both | Both | Feeds into renewal reminders and `/renewals` |

---

## 4. FOLLOW-UP & INTERACTIONS

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 4.1 | Log Interaction | ✅ Dashboard lead detail - interaction history | ✅ `/followup` — select lead → type (call/meeting/whatsapp/email/visit) → notes → next date | |
| 4.2 | Follow-up Reminders | ✅ Dashboard shows upcoming follow-ups | ✅ Automated Telegram reminders at scheduled time | |
| 4.3 | Interaction History | ✅ Lead detail panel → timeline | ✅ `/lead <id>` shows recent interactions | |
| 4.4 | Next Follow-up Date | Both | Both | Set during follow-up logging, persisted as reminder |

---

## 5. FINANCIAL CALCULATORS (9 total)

| # | Calculator | Web (`/calculators`) | Bot (`/calc`) | PDF Report | WhatsApp Share |
|---|-----------|-----|-----|------------|----------------|
| 5.1 | Inflation Eraser | ✅ Tab | ✅ Interactive params | ✅ `/api/report/inflation` | ✅ `shareWhatsAppPDF('inflation')` |
| 5.2 | Human Life Value (HLV) | ✅ Tab | ✅ Interactive params | ✅ `/api/report/hlv` | ✅ |
| 5.3 | Retirement Planner | ✅ Tab | ✅ Interactive params | ✅ `/api/report/retirement` | ✅ |
| 5.4 | EMI Calculator | ✅ Tab | ✅ Interactive params | ✅ `/api/report/emi` | ✅ |
| 5.5 | Health Cover Estimator | ✅ Tab | ✅ Interactive params | ✅ `/api/report/health` | ✅ |
| 5.6 | SIP vs Lumpsum | ✅ Tab | ✅ Interactive params | ✅ `/api/report/sip` | ✅ |
| 5.7 | Mutual Fund SIP Planner | ✅ Tab | ✅ Interactive params | ✅ `/api/report/mfsip` | ✅ |
| 5.8 | ULIP vs Mutual Fund | ✅ Tab | ✅ Interactive params | ✅ `/api/report/ulip` | ✅ |
| 5.9 | NPS Planner | ✅ Tab | ✅ Interactive params | ✅ `/api/report/nps` | ✅ |

**Calculator Sub-features:**

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 5.10 | Branded PDF Reports | ✅ "📊 View Report" button per calc | ✅ `/wacalc` — share via WhatsApp | HTML-based, branded with firm logo/name, bilingual EN/HI |
| 5.11 | WhatsApp PDF Sharing | ✅ "📤 WhatsApp Report" button on each calc | ✅ `/wacalc <lead_id> <calc_type>` | Generates + sends via WA Cloud API |
| 5.12 | Calculator Dark Mode | ✅ `dark-mode.css` + `dark-mode.js` | N/A | Moon/sun toggle |
| 5.13 | Calculator Language Switch | ✅ EN/HI toggle in header | ✅ `/lang` affects calc output | All calc labels bilingual |
| 5.14 | Client-facing CTA Bar | ✅ Each calc result has "Contact Advisor" + "Share" buttons | ❌ | Branded with agent's name/phone |
| 5.15 | Google Drive Upload | ✅ Reports auto-upload to Drive if connected | ❌ | Via `biz_gdrive.py` |

---

## 6. AI FEATURES (8 Gemini-powered + 1 general)

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 6.1 | AI Lead Scoring | ✅ Dashboard → AI Tools tab → "Score Lead" | ✅ `/ai` → 🎯 Lead Scoring → select lead or "Score ALL" | 1-100 score, A/B/C/D grade, reasons, next action. Requires team+ plan |
| 6.2 | AI Pitch Generator | ✅ Dashboard → AI Tools tab → "Generate Pitch" | ✅ `/ai` → 💡 Pitch Generator → select lead | Opening, main pitch, key points, closing, WhatsApp-ready message |
| 6.3 | AI Smart Follow-up | ✅ Dashboard → AI Tools tab → "Smart Follow-up" | ✅ `/ai` → 📅 Smart Follow-up → select lead | Urgency level, channel, timing, action, reasoning, draft message |
| 6.4 | AI Policy Recommender | ✅ Dashboard → AI Tools tab → "Recommend Policies" | ✅ `/ai` → 📋 Policy Recommender → select lead | Gap analysis, recommendations by priority, cross-sell opportunities |
| 6.5 | AI Communication Templates | ✅ Dashboard → AI Tools tab | ✅ `/ai` → ✉️ Templates → select type | 14 types: introduction, follow_up, proposal, thank_you, referral_ask, birthday, anniversary, festival, renewal, premium_reminder, cross_sell, reactivation. Generates WhatsApp, Email, SMS versions |
| 6.6 | AI Voice Meeting Summary | ❌ | ✅ Send voice note → auto-transcribe + extract lead data + create lead | Max 2min, Gemini transcription, fills name/phone/need/city/budget/follow-up |
| 6.7 | AI Objection Handler | ✅ Dashboard → AI Tools tab | ✅ `/ai` → 🛡️ Objection Handler → preset or custom | Empathy → counter-arguments → reframe → closing question → real-world example |
| 6.8 | AI Renewal Intelligence | ✅ Dashboard → AI Tools tab | ✅ `/ai` → 🔄 Renewal Intelligence → select policy | Retention risk, premium change estimate, upsell, talking points, competitor view, draft message |
| 6.9 | Ask AI Anything | ✅ Dashboard → AI Tools tab | ✅ `/ai` → 💬 Ask AI → type question | General insurance Q&A powered by Gemini |
| 6.10 | AI Policy Extraction | ✅ Dashboard → Add Policy → Extract from Text / Upload Image | ❌ | Gemini reads policy doc text/photo and fills form |
| 6.11 | AI Verify Setup | ✅ `/api/ai/verify` | ❌ | Health-check for Gemini API key |

---

## 7. WHATSAPP INTEGRATION

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 7.1 | Send Text Message | ✅ `/api/wa/send` | ✅ `/wa <lead_id> <msg>` | Per-tenant WA credentials |
| 7.2 | Send Document/Report | ✅ `/api/wa/share-calc` | ✅ `/wacalc <lead_id> <type>` | Sends calc PDF via WhatsApp |
| 7.3 | Birthday Greeting | ✅ API available | ✅ Auto via reminders | Scanned daily at 9 AM |
| 7.4 | Anniversary Greeting | ✅ API available | ✅ Auto via reminders | Scanned daily at 9 AM |
| 7.5 | WA Status Check | ✅ `/api/wa/status` | ❌ | Verify WA credentials |
| 7.6 | WA Setup Guide | ✅ `/api/wa/setup-guide` — step-by-step page | ✅ `/wasetup` — inline guide with Meta portal link | Full BotFather-style walkthrough |
| 7.7 | WA Credential Config | ✅ Dashboard → Profile → WhatsApp Settings + `/api/onboarding/whatsapp` | ✅ Onboarding stores WA creds | Phone ID + Access Token |
| 7.8 | WA Webhook (Inbound) | ✅ `POST /webhook` — processes incoming WA messages | ❌ | Routes to tenant by phone |
| 7.9 | Send Dashboard via WA | ❌ | ✅ `/wadash` — portfolio summary via WhatsApp | Sends text summary of leads/policies/renewals |

---

## 8. GOOGLE DRIVE INTEGRATION

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 8.1 | OAuth2 Connect | ✅ `/api/gdrive/connect` → Google consent | ❌ | Per-tenant OAuth tokens stored in `gdrive_tokens/` |
| 8.2 | OAuth2 Callback | ✅ `/api/gdrive/callback` | ❌ | Exchanges code → tokens |
| 8.3 | Check Status | ✅ `/api/gdrive/status` | ❌ | Shows connected email |
| 8.4 | Disconnect | ✅ `/api/gdrive/disconnect` | ❌ | Revoke + delete tokens |
| 8.5 | List Reports | ✅ `/api/gdrive/files` | ❌ | Lists uploaded PDFs in CRM folder |
| 8.6 | Upload Report | ✅ `/api/gdrive/upload-report` | ❌ | Auto-creates "{FirmName} — Reports" folder |
| 8.7 | Auto-upload on Calc | ✅ Calc report generation triggers upload if connected | ❌ | Transparent to user |

---

## 9. CAMPAIGNS (Bulk Messaging)

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 9.1 | Create Campaign | ✅ `/api/campaigns` POST | ❌ | Types: birthday, anniversary, festival, announcement, promotion, renewal_reminder, custom |
| 9.2 | List Campaigns | ✅ `/api/campaigns` GET | ❌ | |
| 9.3 | Campaign Detail | ✅ `/api/campaigns/{id}` GET | ❌ | |
| 9.4 | Add Recipients | ✅ `/api/campaigns/{id}/recipients` | ❌ | Filter from leads |
| 9.5 | Send Campaign | ✅ `/api/campaigns/{id}/send` | ❌ | Via WhatsApp or Email |
| 9.6 | Delete Campaign | ✅ `DELETE /api/campaigns/{id}` | ❌ | |
| 9.7 | Campaign Types List | ✅ `/api/campaigns/types` | ❌ | Returns available types |

---

## 10. CLAIMS HELPER

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 10.1 | Initiate Claim | ❌ | ✅ `/claim` → select lead → select policy → type (health/term/motor/general) → description → hospital (if health) → confirm | Full conversation flow |
| 10.2 | View All Claims | ❌ | ✅ `/claims` — status-coded list with emoji (🟡🟠🔵🟣🟢🔴✅) | Up to 15 claims |
| 10.3 | Claim Status Detail | ❌ | ✅ `/claimstatus <id>` — full detail with document checklist | Each doc tracked as pending/done |
| 10.4 | Document Checklist | ❌ | ✅ Per claim type: health (8 docs), term (7), motor (7), general (5) | Generated on claim creation |

---

## 11. TEAM MANAGEMENT

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 11.1 | Invite Agent | ✅ `/api/admin/invite` — generates invite code | ❌ | Owner/admin only |
| 11.2 | Accept Invite | ✅ `/api/invite/accept` + `/api/invite/validate/{code}` | ✅ During onboarding | |
| 11.3 | List Team | ✅ Dashboard → Team tab (shows agents with lead/policy counts) | ✅ `/team` — agent list with status, lead/policy counts | Owner/admin only |
| 11.4 | Deactivate Agent | ✅ `/api/agents/{id}/deactivate` | ✅ `/team` → "❌ Deactivate" button | |
| 11.5 | Reactivate Agent | ✅ `/api/agents/{id}/reactivate` | ✅ `/team` → "✅ Reactivate" button | |
| 11.6 | Transfer Data | ✅ `/api/agents/transfer` | ✅ `/team` → "🔄 Transfer" → select target agent | Transfers leads, policies, interactions, claims, reminders |
| 11.7 | Remove Agent | ✅ `/api/agents/{id}/remove` | ❌ | Permanent removal |
| 11.8 | Agent Photo Upload | ✅ `/api/agent/{id}/photo` POST | ✅ `/editprofile` → 📸 Profile Photo | Photo shows in dashboard |
| 11.9 | Agent Photo Delete | ✅ `DELETE /api/agent/{id}/photo` | ❌ | |
| 11.10 | Agent Capacity Check | ✅ API-level max-agents per plan | ✅ Checked on invite | Solo: 1, Team: 5, Enterprise: 25 |

---

## 12. PROFILE & SETTINGS

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 12.1 | View Profile | ✅ Dashboard → Profile & Settings tab | ✅ `/editprofile` shows current values | |
| 12.2 | Edit Name | ✅ Dashboard edit | ✅ `/editprofile` → 📝 Name | |
| 12.3 | Edit Phone | ✅ Dashboard edit | ✅ `/editprofile` → 📱 Phone | Validated 10-digit |
| 12.4 | Edit Email | ✅ Dashboard edit | ✅ `/editprofile` → 📧 Email | Validated format |
| 12.5 | Edit Firm Name | ✅ Dashboard edit (owner only) | ✅ `/editprofile` → 🏢 Firm Name (owner only) | Updates tenant record |
| 12.6 | Upload Profile Photo | ✅ Dashboard | ✅ `/editprofile` → 📸 send photo | Saved to `uploads/photos/` |
| 12.7 | Language Switch | ✅ Dashboard header toggle (EN/HI) | ✅ `/lang` — English ↔ Hindi | Persisted per-agent |
| 12.8 | Dark Mode | ✅ `dark-mode.css` + `dark-mode.js` — moon/sun toggle on dashboard & calculators | N/A | CSS variables based |
| 12.9 | Settings Menu | ❌ | ✅ `/settings` or ⚙️ button → inline keyboard | Links to edit profile, language, WhatsApp setup |
| 12.10 | Firm Branding | ✅ Dashboard → Profile → Firm Branding section (owner only) | ❌ | Tagline, primary color, credentials |
| 12.11 | Logo Upload | ✅ Dashboard → Profile → Logo upload/delete | ❌ | JPEG/PNG, max 2MB, used on calc pages & PDFs |
| 12.12 | Logo Delete | ✅ Dashboard → "🗑️ Remove" button (`DELETE /api/tenant/logo`) | ❌ | |

---

## 13. SUBSCRIPTION & PAYMENTS

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 13.1 | View Plans | ✅ Dashboard → Subscription tab (Solo/Team/Enterprise cards) | ✅ `/plans` — 3 plan cards with Razorpay buttons | Solo ₹199, Team ₹799, Enterprise ₹1999/mo |
| 13.2 | Create Payment Order | ✅ `/api/payments/create-order` | ❌ | Razorpay order |
| 13.3 | Verify Payment | ✅ `/api/payments/verify` | ❌ | Razorpay signature verification |
| 13.4 | Create Subscription | ✅ `/api/payments/create-subscription` | ❌ | Recurring Razorpay subscription |
| 13.5 | Payment Status | ✅ `/api/payments/status` | ❌ | |
| 13.6 | Payment Webhook | ✅ `/api/payments/webhook` | ❌ | Auto-activates plan on payment |
| 13.7 | Subscription Status | ✅ Dashboard → Subscription tab shows current plan details | ❌ | Plan, status, trial end, features |
| 13.8 | Upgrade Plan | ✅ `/api/subscription/upgrade` | ✅ `/plans` → select higher plan → Razorpay link | |
| 13.9 | Downgrade Plan | ✅ `/api/subscription/downgrade` | ❌ | |
| 13.10 | Cancel Subscription | ✅ `/api/subscription/cancel` | ❌ | |
| 13.11 | Schedule Plan Change | ✅ `/api/subscription/schedule-change` | ❌ | Effective at billing cycle end |
| 13.12 | Pending Change View/Cancel | ✅ `/api/subscription/pending-change` GET+DELETE | ❌ | |
| 13.13 | Feature Gating by Plan | Both | Both | `PLAN_FEATURES` dict controls access. Trial: limited; Solo: all core; Team+: AI, campaigns, drive, team |
| 13.14 | Payment Success Notification | ❌ | ✅ Telegram + Email notification on successful payment | Via webhook handler |

---

## 14. DASHBOARD (Web Only — `/dashboard`)

| # | Feature | Tab/Section | Notes |
|---|---------|-------------|-------|
| 14.1 | Overview Tab | 📊 Overview | KPI cards (leads, policies, conversions, revenue), pipeline breakdown |
| 14.2 | Leads Tab | 📋 Leads | Full CRUD table + search/filter + Add Lead modal + Import CSV |
| 14.3 | Policies Tab | 📄 Policies | Full CRUD table + Add Policy modal with AI extraction |
| 14.4 | AI Tools Tab | 🤖 AI Tools | All 8 AI features with inline forms |
| 14.5 | Team Tab | 👥 Team | Invite, list, deactivate, reactivate agents (owner/admin only, hidden for agents) |
| 14.6 | Subscription Tab | 💎 Subscription | Current plan, feature flags, upgrade/downgrade, plan comparison cards |
| 14.7 | Profile & Settings Tab | 👤 Profile | Edit name/phone/email/firm, branding (logo/tagline/color/credentials), photo |
| 14.8 | Support Tab | 🎫 Support | Create/view/reply support tickets |
| 14.9 | Calculators Link | 🧮 Calculators | Opens `/calculators` in new tab |
| 14.10 | Sidebar Navigation | Left sidebar | Logo, firm name, nav items, role-based visibility, calculator link, logout |
| 14.11 | Dark Mode Toggle | Header | Moon/sun button, persisted in localStorage |
| 14.12 | Language Toggle | Header | EN/HI switch, all UI strings are bilingual via i18n dict |
| 14.13 | Mobile Responsive | Full UI | Sidebar collapses, tables scroll, modals resize |
| 14.14 | Import CSV Modal | Leads tab | Drag & drop, file picker, result summary |
| 14.15 | Add Lead Modal | Leads tab | Multi-field form with validation |
| 14.16 | Add Policy Modal with AI Extraction | Policies tab | Form + "Extract from Text" + "Upload Image" for AI fill |

---

## 15. SUPER ADMIN (`/superadmin` Web + `/sa` Bot)

| # | Feature | Web (superadmin.html) | Bot (/sa commands) | Notes |
|---|---------|-----|-----|-------|
| 15.1 | SA Login | ✅ Phone + password | ✅ Phone check vs `SUPERADMIN_PHONES` | bcrypt hash, IP blocking |
| 15.2 | Dashboard Tab | ✅ 📊 KPIs: total/active tenants, trials, paid, expired, agents, leads | ✅ `/sa` shows same stats | |
| 15.3 | System Tab | ✅ ⚙️ System status, health checks | ✅ Via `/api/sa/system-status` | |
| 15.4 | Tenants Tab | ✅ 🏢 Paginated table with search, click for detail | ✅ `/sa` → Tenants button, paginated | |
| 15.5 | Tenant Detail Panel | ✅ Slide-in drawer: all fields, agents, leads, policies, bot/WA status | ✅ `sa_tenant_<id>` callback | |
| 15.6 | Create Firm | ✅ ➕ Create Firm tab (form) | ✅ `/sa_create Firm \| Owner \| Phone \| Email \| Plan` | Duplicate phone/email check |
| 15.7 | Edit Tenant | ✅ Detail panel inline edit (`PUT /api/sa/tenant/{id}`) | ✅ `/sa_edit TenantID \| field \| value` | Fields: firm_name, owner_name, phone, email, city, plan, is_active |
| 15.8 | Activate Tenant | ✅ Detail panel button | ✅ Inline button `sa_activate_<id>` | Sets active + plan=individual |
| 15.9 | Deactivate Tenant | ✅ Detail panel button | ✅ Inline button `sa_deactivate_<id>` | Sets inactive + expired |
| 15.10 | Delete Tenant | ✅ `DELETE /api/sa/tenant/{id}` | ❌ | Web only |
| 15.11 | Extend Trial (+14d) | ✅ Detail panel button | ✅ Inline button `sa_extend_<id>` | |
| 15.12 | Change Plan | ✅ `/api/sa/tenant/{id}/plan` or force/schedule | ✅ `sa_plan_<id>_<plan>` buttons | |
| 15.13 | Schedule Plan Change | ✅ `/api/sa/tenant/{id}/schedule-plan-change` | ❌ | Effective at billing cycle end |
| 15.14 | Cancel Pending Change | ✅ `DELETE /api/sa/tenant/{id}/pending-plan-change` | ❌ | |
| 15.15 | Revenue Tab | ✅ 💰 Revenue analytics | ❌ | `/api/sa/revenue` |
| 15.16 | Bots Tab | ✅ 🤖 Running bots status (master + tenant bots) | ✅ `/sa` → Bots button | |
| 15.17 | Restart/Stop Bot | ✅ `/api/sa/tenant/{id}/bot/restart` + `/api/sa/tenant/{id}/bot/stop` | ❌ | Per-tenant bot control |
| 15.18 | Audit Log Tab | ✅ 📋 Audit trail with filters | ❌ | `/api/sa/audit` |
| 15.19 | Product Support Tab | ✅ 🎫 View/reply to support tickets, ticket stats | ❌ | `/api/sa/tickets`, `/api/sa/tickets/stats`, reply endpoint |
| 15.20 | Affiliates Tab | ✅ 🤝 List, approve, reject affiliates, view referrals, stats | ❌ | Full affiliate management |
| 15.21 | Affiliate Ops Tab | ✅ 📡 Operational affiliate management | ❌ | |
| 15.22 | Duplicates Tab | ✅ ⚠️ Duplicate tenant detection | ❌ | `/api/sa/duplicates` |
| 15.23 | Feature Toggle | ✅ `/api/sa/tenant/{id}/features` GET+PUT | ❌ | Per-tenant feature flags |
| 15.24 | Edit Agent | ✅ `PUT /api/sa/agent/{id}` | ❌ | |
| 15.25 | Toggle Agent | ✅ `/api/sa/agent/{id}/toggle` | ❌ | |
| 15.26 | Export Tenants CSV | ✅ `/api/sa/export/tenants` | ❌ | |
| 15.27 | Export Leads CSV | ✅ `/api/sa/export/leads` | ❌ | |
| 15.28 | Export Affiliates CSV | ✅ `/api/sa/export/affiliates` | ❌ | |
| 15.29 | View Agents by Tenant | ✅ Detail panel → Agents list | ✅ `sa_agents_<id>` button | |

---

## 16. SUPPORT TICKETS

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 16.1 | Create Ticket | ✅ Dashboard → Support tab → create form (`POST /api/support/tickets`) | ❌ | |
| 16.2 | List My Tickets | ✅ Dashboard → Support tab (`GET /api/support/tickets`) | ❌ | |
| 16.3 | View Ticket Detail | ✅ `/api/support/tickets/{id}` | ❌ | |
| 16.4 | Reply to Ticket | ✅ `/api/support/tickets/{id}/reply` | ❌ | |
| 16.5 | SA: View All Tickets | ✅ SuperAdmin → Product Support tab | ❌ | |
| 16.6 | SA: Reply to Ticket | ✅ `/api/sa/tickets/{id}/reply` | ❌ | |
| 16.7 | SA: Ticket Stats | ✅ `/api/sa/tickets/stats` | ❌ | |

---

## 17. AFFILIATE / PARTNER PROGRAM

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 17.1 | Register as Affiliate | ✅ `/partner` page → `/api/affiliate/register` | ❌ | |
| 17.2 | Verify Affiliate | ✅ `/api/affiliate/verify` | ❌ | |
| 17.3 | Affiliate Login | ✅ `/api/affiliate/login` + `/api/affiliate/login/verify` | ❌ | OTP-based |
| 17.4 | Check Referral Code | ✅ `/api/affiliate/check/{code}` | ❌ | |
| 17.5 | Affiliate Dashboard | ✅ `/api/affiliate/me` + `/api/affiliate/dashboard` | ❌ | |
| 17.6 | Track Referral | ✅ `/api/affiliate/track` | ❌ | |
| 17.7 | Partner Link from Bot | ❌ | ✅ `/partner` — sends affiliate portal URL | |
| 17.8 | SA: Manage Affiliates | ✅ SuperAdmin → Affiliates tab | ❌ | Approve/reject/list/stats/referrals |

---

## 18. EMAIL NOTIFICATIONS

| # | Feature | Channel | Notes |
|---|---------|---------|-------|
| 18.1 | Welcome Email | Email (SMTP) | On registration, HTML branded template |
| 18.2 | OTP Email | Email | 6-digit code with expiry |
| 18.3 | Trial Expiry Warning | Email | Sent before trial ends |
| 18.4 | Payment Receipt | Email | On successful payment |
| 18.5 | Subscription Cancelled | Email | On cancellation |
| 18.6 | Affiliate Welcome | Email | On affiliate registration |

---

## 19. BACKGROUND JOBS & REMINDERS

| # | Feature | Schedule | Channel |
|---|---------|----------|---------|
| 19.1 | Birthday Scan | Daily 9:00 AM | WhatsApp greeting + agent Telegram notification |
| 19.2 | Anniversary Scan | Daily 9:00 AM | WhatsApp greeting + agent Telegram notification |
| 19.3 | Renewal Reminders | Daily | At T-60, T-30, T-15, T-7, T-1 days before renewal |
| 19.4 | Follow-up Reminders | Continuous | Telegram notification to agent at scheduled time |
| 19.5 | Daily Agent Summary | Daily 8:30 AM | Telegram: today's follow-ups, renewals, pipeline stats |
| 19.6 | Trial Expiry Reminder | Daily | For tenants approaching trial end |
| 19.7 | Subscription Expiry | Daily | For tenants with expiring subscriptions |

---

## 20. BOT-SPECIFIC FEATURES

| # | Feature | Notes |
|---|---------|-------|
| 20.1 | Persistent Button Menu | 3 always-visible buttons: ➕ Add Lead, 📞 Follow-up, 🧮 Calculator (Hybrid C) |
| 20.2 | ☰ Full Menu (Inline) | Inline keyboard with all features: Pipeline, Leads, Renewals, Dashboard, AI Tools, Settings, Team, Language, Partner |
| 20.3 | Per-user Rate Limiting | Prevents abuse |
| 20.4 | Voice-to-Action | Send voice → transcribe → extract lead → confirm → create. With "Fill Missing Details" flow |
| 20.5 | CSV Import via File | Send CSV file → bulk import leads (max 500) |
| 20.6 | Conversation Timeout | 30-min auto-cancel for all conversation handlers |
| 20.7 | Conversation Recovery | "🔄 Retry" + "🏠 Main Menu" buttons on errors |
| 20.8 | Non-text Fallback | Photos/stickers during conversation → polite rejection |
| 20.9 | Command During Conversation | Commands during active conversation → "finish this first" message |
| 20.10 | Global Catch-all | Unrecognized text → tries menu dispatch → tries AI text handler → shows help |
| 20.11 | Error Handler | Global: logs error, saves state on network errors, notifies user |
| 20.12 | Unicode Variation Selector Handling | Strips U+FE0E/FE0F for robust emoji matching |
| 20.13 | Master vs Tenant Bot | Master bot: registration commands only; Tenant bot: full CRM features |
| 20.14 | Telegram Command Picker | Registered via `set_my_commands` — different for master vs tenant bot |
| 20.15 | `/createbot` | Step-by-step BotFather guide to create tenant's own bot |
| 20.16 | `/wasetup` | WhatsApp Business API setup guide |
| 20.17 | `/greet` | Send birthday/anniversary greetings to leads with upcoming dates |
| 20.18 | `/renewals` | Upcoming 60-day renewals with urgency colors |
| 20.19 | `/dashboard` | Business stats: pipeline, portfolio, today's activity, web link |

---

## 21. RESILIENCE & INFRASTRUCTURE

| # | Feature | Notes |
|---|---------|-------|
| 21.1 | Retry with Exponential Backoff | `retry_async` decorator in `biz_resilience.py` |
| 21.2 | Message Queue (Offline Delivery) | Failed messages queued in `message_queue` table, retried later |
| 21.3 | Dead Letter Queue | `/api/admin/message-queue/dead-letters` — failed messages after max retries |
| 21.4 | Message Queue Stats | `/api/admin/message-queue/stats` |
| 21.5 | Retry Dead Letter | `/api/admin/message-queue/{id}/retry` |
| 21.6 | Health Endpoint | `/health` — server health check |
| 21.7 | System Status | `/api/sa/system-status` — comprehensive system health |
| 21.8 | Audit Logging | Every significant action logged to `audit_log` table |
| 21.9 | Docker Deployment | `Dockerfile` + `docker-compose.yml` |
| 21.10 | Nginx Config | `deploy/nginx-sarathi.conf` |
| 21.11 | Systemd Service | `deploy/sarathi.service` |
| 21.12 | Backup Script | `deploy/backup.sh` |
| 21.13 | Setup Script | `deploy/setup-server.sh` |
| 21.14 | Push Update Script | `deploy/push-update.sh` |

---

## 22. INTERNATIONALIZATION (i18n)

| # | Feature | Web | Bot | Notes |
|---|---------|-----|-----|-------|
| 22.1 | Bilingual UI Strings | ✅ IN-HTML i18n dict with EN/HI for all labels | ✅ `biz_i18n.py` — 100+ string keys | |
| 22.2 | Calculator Labels | ✅ EN/HI toggle | ✅ Calc results in chosen language | |
| 22.3 | PDF Reports | ✅ Full bilingual labels in `biz_pdf.py` | N/A | All 9 calc reports |
| 22.4 | AI Output Language | ✅ AI API accepts `lang` param | ✅ All AI features pass `lang` | Gemini responds in chosen language |
| 22.5 | Dashboard i18n | ✅ `data-i18n` attributes on all elements | N/A | Full i18n dict inline |
| 22.6 | Calculator Page i18n | ✅ EN/HI toggle on `/calculators` | N/A | |

---

## 23. STATIC PAGES

| # | Page | URL | Notes |
|---|------|-----|-------|
| 23.1 | Landing Page | `/` | Marketing/index page |
| 23.2 | Onboarding | `/onboarding` | Multi-step signup wizard |
| 23.3 | Dashboard | `/dashboard` | Main CRM dashboard (auth required) |
| 23.4 | Super Admin | `/superadmin` | SA control panel (SA auth required) |
| 23.5 | Calculators | `/calculators` | 9 financial calculators (public, branded) |
| 23.6 | Support | `/support` | Support ticket page |
| 23.7 | Partner/Affiliate | `/partner` | Affiliate registration & dashboard |
| 23.8 | Help | `/help` | Help/documentation |
| 23.9 | Privacy Policy | `/privacy` | Legal page |
| 23.10 | Terms of Service | `/terms` | Legal page |
| 23.11 | Getting Started Guide | `/getting-started` | User guide |
| 23.12 | Telegram Guide | `/telegram-guide` | Bot setup instructions |
| 23.13 | Demo Page | `/demo` | Product demo |
| 23.14 | Bot Setup Guide | `/api/bot-setup/guide` | Step-by-step bot creation |
| 23.15 | WA Setup Guide | `/api/wa/setup-guide` | WhatsApp API setup walkthrough |

---

## 24. DATABASE TABLES (20+)

| Table | Purpose |
|-------|---------|
| `tenants` | Multi-tenant firms with plan, branding, WA/TG credentials |
| `invite_codes` | Agent invitation codes |
| `agents` | Users (owner/admin/agent) with profile, lang, photo |
| `leads` | CRM leads with full profile, stage, need_type |
| `policies` | Insurance policies linked to leads |
| `interactions` | Follow-up/meeting/call logs |
| `reminders` | Scheduled reminders (birthday/anniversary/renewal/follow-up) |
| `greetings_log` | Track sent greetings (prevent duplicates) |
| `calculator_sessions` | Calculator usage tracking |
| `daily_summary` | Pre-computed daily stats |
| `voice_logs` | Voice-to-action transcripts & extracted data |
| `claims` | Insurance claim tracking |
| `audit_log` | All significant actions |
| `support_tickets` | Product support tickets |
| `ticket_messages` | Ticket conversation thread |
| `affiliates` | Partner/affiliate registrations |
| `affiliate_referrals` | Referral tracking |
| `campaigns` | Bulk message campaigns |
| `campaign_recipients` | Campaign recipient lists |
| `message_queue` | Failed message retry queue |
| `pending_plan_changes` | Scheduled plan changes |

---

## 25. PLAN FEATURE GATING

| Feature | Trial | Solo (₹199) | Team (₹799) | Enterprise (₹1999) |
|---------|-------|-------------|--------------|---------------------|
| Max Agents | 1 | 1 | 5 | 25 |
| Leads | 25 | ∞ | ∞ | ∞ |
| Policies | 25 | ∞ | ∞ | ∞ |
| Calculators | ✅ | ✅ | ✅ | ✅ |
| PDF Reports | ✅ | ✅ | ✅ | ✅ |
| WhatsApp | ✅ | ✅ | ✅ | ✅ |
| AI Features | Limited | Limited | ✅ Full | ✅ Full |
| Bulk Campaigns | ❌ | ❌ | ✅ | ✅ |
| Google Drive | ❌ | ❌ | ✅ | ✅ |
| Team Dashboard | ❌ | ❌ | ✅ | ✅ |
| Custom Bot Branding | ❌ | ❌ | ✅ | ✅ |
| Data Transfer | ❌ | ❌ | ✅ | ✅ |
| Priority Support | ❌ | ❌ | ❌ | ✅ |

---

## TOTAL FEATURE COUNT SUMMARY

| Category | Count |
|----------|-------|
| Auth & Onboarding | 13 |
| Lead Management | 15 |
| Policy Management | 7 |
| Follow-up & Interactions | 4 |
| Calculators | 15 (9 calcs + 6 sub-features) |
| AI Features | 11 |
| WhatsApp Integration | 9 |
| Google Drive | 7 |
| Campaigns | 7 |
| Claims Helper | 4 |
| Team Management | 10 |
| Profile & Settings | 12 |
| Subscription & Payments | 14 |
| Dashboard Tabs & UI | 16 |
| Super Admin | 29 |
| Support Tickets | 7 |
| Affiliate Program | 8 |
| Email Notifications | 6 |
| Background Jobs | 7 |
| Bot-specific Features | 19 |
| Infrastructure | 14 |
| Internationalization | 6 |
| Static Pages | 15 |
| **GRAND TOTAL** | **~255 features** |

---

*Generated from full source code analysis of all 15+ Python modules + HTML frontends.*
