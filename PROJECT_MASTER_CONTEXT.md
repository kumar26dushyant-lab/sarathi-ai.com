# SARATHI-AI BUSINESS — MASTER PROJECT CONTEXT

> **Purpose:** Single source of truth for project recovery. If a development session is lost, feed this document to a new session to restore full context instantly.
>
> **Last Updated:** Aug 19, 2026. Newest work is at the BOTTOM in sections **A74–A85** (read those first for what's current). Older numbered sections 1–73 are the original detailed reference. Also load the memory index: `C:\Users\imdus\.claude\projects\c--sarathi-business\memory\MEMORY.md`.
>
> **Maintainer:** Update this doc after every significant change.

---

## 🏗️ A88 ARCHITECTURE & WIRING (Aug 25 2026) — key systems, flows, decisions

**WhatsApp Business (Cloud API) — LIVE.** Sender = GoLuQ WABA `1942085573135209`, number +91 83495 04400 (Phone Number ID `1259819740549744`), VERIFIED+GREEN, business-verified. Secrets in `/opt/sarathi/biz.env`: `WA_ACCESS_TOKEN` (permanent System User token), `WA_APP_SECRET`, `WA_APP_ID=839673715804540`, `WA_PHONE_NUMBER_ID`, `WA_WABA_ID`. Module `biz_sarathi_whatsapp.py` (isolated): `send_template`(business-initiated), `send_text`(24h session), `number_health`, `body_params`, `normalize_msisdn` (10-digit→+91). Graph v22.0. Message rules: template = only way to open a chat; text = only inside 24h after user replies. **6 templates created (3×EN/HI: policy_renewal_reminder / emi_reminder / policy_lapse_warning)** — awaiting Meta approval. NEXT: `wa_messages` send-log + opt-in table + Sarathi manual "send reminder" test UI + data-driven sends. Registration gotcha: number must be OFF the consumer WhatsApp app + 2-step PIN needs old PIN or 7-day wait. Two-app strategy + Nidaan branch reseller model: WHATSAPP_SUBSCRIBERS_PLAN.md §9.

**Referral attribution model.** Attribution lives in `nidaan_accounts.branch_code` (holds BOTH branch codes and staff `SP-XXXXXX` codes). `is_valid_ref_code()` accepts either. `set_account_branch()` = FIRST-TOUCH + LOCKED (only fills a blank). Display: `get_claims_ops` joins → `ref_kind`/`ref_name` (staff/branch) + `source_kind` (branch|staff|subscriber|review|direct). Frontends capture `?ref=` + persist via `NidaanTrack` (first-touch). FIXED (commit f52c781): the ₹499 review-signup path now forwards `ref_code` (was the leak → all review leads showed "Direct lead"). Branch-raise stamps `claim.branch_code`+`origin='branch'`; subscriber signup passes `branch_code` to `create_account`; `/claims/submit` inherits from account. **PENDING:** super-admin re-attribution override (since first-touch is locked).

**Claim trail (per-row visibility).** `get_claims_ops` returns the FULL trail per claim: insured, `owner_name` (raiser), `source_kind`+`ref_name` (referrer), `origin`, `payment_status` (unpaid_lead|paid|subscription), `account_plan`, and (joined from `nidaan_claimant_portal`) `authorization` (none|portal_ready|pushed|accepted) + `portal_created`/`portal_opened`/`portal_token`. **All Claims is now THE single rich pane** (Table/Board/Cards + "Auth / Dashboard" column + trail on every card via `_claimTrail`/`_srcBadge`/`_payBadge`/`_authBadge`/`_portalBadge`). Staff can open a claimant dashboard with `/nidaan/claim/magic?token=…&staff=1` (skips claimant first-open stamp). L2 view also shows the trail.

**Authorization flow (built P1 + founder decisions Aug 25).** Claimant portal `nidaan_claimant_portal` (per-claim token + consent snapshot: terms text EN+HI, %, GST, IP, device, SHA-256 hash + `consent_pushed_by/at`). L2 = `review_outcome='can_fight'`. Ops "Push authorization" (verify-dispute-amount prompt → records who/when → emails claimant if not accepted). Claimant dashboard shows fee ONLY at L2. Consent-proof PDF (fitz, super-admin download). **DECISIONS:** gate ClaimShield send on acceptance (accept→PDF→then CS); email verify via the L2 magic-link (email+mobile mandatory at creation, no OTP for mediated). Auto-send toggle `claimant_autosend_enabled` (default OFF).

---

## ⭐ OPEN TO-DOS (Aug 25 2026) — phased backlog (founder-approved priorities)

**PHASE 1 — Referral Transparency & Flow Integrity (HIGHEST PRIORITY, NEW).** Money/incentive depends on this.
- **1a — ✅ FIXED (commit f52c781):** the ₹499 review-signup path now captures `ref_code` → validated via `is_valid_ref_code` → attributed to the account FIRST-TOUCH via `set_account_branch` (`NidaanReviewSignupReq` + endpoint + `create_review_signup` + `nidaan_review.html` sends persisted `_ref`). Claim #066 backfilled → SUHANA JAIN (SP-EE53CU, staff 12). New signup tested end-to-end. STILL TO AUDIT (1a-rest): confirm subscriber-signup (sends branch_code already), branch-raise (origin='branch'+branch_code), `/claims/submit` (inherits from account) all attribute with no gaps; add a super-admin RE-ATTRIBUTION tool (set_account_branch is locked → needs an admin override path for corrections).
- **1a(orig) — FIX referral attribution across ALL claim-creation flows.** BUG: claim #066 raised via a STAFF my-business one-time-review link (`/nidaan/start?ref=SP-EE53CU`, Suhana) recorded as **"Direct lead"** — the ref never attached to the claim. Root cause direction: `nidaan_start.html` captures `?ref=` + `NidaanTrack` persistence and pre-fills it at **signup** (`regBranch`), but the **₹499 one-time-review / lead-claim path doesn't carry the ref onto the CLAIM**. AUDIT every entry: ₹499 one-time review, direct claimant, branch-raise, staff my-business, subscriber signup link. Ensure ref attaches to claim + account.
- **1b — Referrer dashboards:** staff/branch see their referred claims AND subscriptions as their referral.
- **1c — ✅ STARTED (commit ef491ba):** `get_claims_ops` enriched with claimant-portal/authorization trail (`portal_created`/`portal_opened`/`authorization`[none|portal_ready|pushed|accepted]/`portal_token`) on top of existing `source_kind`/`ref_name`/`owner_name`/`origin`/`payment_status`/`account_plan`. **L2 Board+Cards now show the FULL per-claim trail** (raised-by, source+referrer, paid-status, authorization, claimant-dashboard + "enter ↗" for admins). Claimant magic route gained `&staff=1` (staff inspect without stamping claimant first-open). **STILL TO DO (1c-rest):** add trail to the L2 TABLE column + the All Claims view; consider collating Claims-dashboard/All-Claims/Accounts into 1-2 rich views (founder ask — discuss merge vs. make All-Claims the single rich pane). #64 origin resolved: raised by SHARDA HARIYALA (unpaid lead, NOT subscriber), referred by Suhana (SP-EE53CU), insured Vinod Hariyala.
- **1c — ✅ ALL CLAIMS = single rich pane (commit 1fe52d7):** All Claims now has the full trail per row ("Auth / Dashboard" column + Source/Who) + Table/Board/Cards switcher (Board/Cards reuse L2 renderers). Founder chose "make All Claims the single rich pane" (not merge tabs); Accounts stays the subscriber lens.
- **1c-BUG — ✅ topbar overflow FIXED (commit 1fe52d7):** Nidaan ops `.topbar-right` now wraps at all widths + compacts to icon-only at ≤1024px (tablet/impersonation view) so logout/bell never pushed off-screen.
- **1d — Fallback/duplicate intelligence:** e.g. an existing subscriber trying to re-subscribe → detect + guide, never error or mis-record. Same for other deviations — GUIDE, don't error.

**PHASE 2 — Claimant mandatory fields (NEW).** Claimant **email (verified) + mobile MANDATORY** at claim creation on **ALL endpoints** (branch/₹499/direct/subscriber). Mobile → later WhatsApp OTP. NOTE: for mediated claims (claimant not present) "verification" = the claimant opening the emailed magic link (that's the natural verify); direct self-signup = OTP at signup. CONFIRM with founder.

**FOUNDER DECISIONS (Aug 25):** (1) **YES — gate ClaimShield on claimant authorization acceptance** (L2 → auth email → accept → PDF filed in L2 → THEN ClaimShield; if never accepted, case waits + we chase/notify). (2) **Email verify = via the L2 magic-link** (no OTP at claim creation): email+mobile MANDATORY to raise any claim; mediated claims verify when the claimant opens the emailed L2 link; direct self-signup still OTP-verifies at signup.

**PHASE 3 — Authorization flow gating + fallbacks (extends built P1).** ⚠️ Changes ClaimShield gating.
- **Gate ClaimShield send on claimant authorization acceptance:** L2 → email (+WA later) → accept page shows *disputed amount + 15% + GST as EXAMPLE* → accept → generate acceptance PDF → PDF aligned in L2 claims → **THEN move to ClaimShield.** (Currently paid+GO auto-sends to CS — this must now wait for acceptance. CONFIRM.)
- **Fallbacks:** accepted once → no duplicate record; re-open after accepting → show "you already accepted, contact NidaanPartner" (not the accept page); declined first → later can accept (page visible again).
- **All-channel notify super-admins + admins on every authorization action**; admins/SAs have live visibility into the authorization stage/journey.

**PHASE 4 — WhatsApp Business (foundation LIVE — commit f28822d).**
- OWNER: submit 3 Utility templates (renewal/EMI/lapse EN+HI) in WhatsApp Manager.
- Build: `wa_messages` send-log + opt-in tracking; Sarathi manual "send reminder" test UI; data-driven renewal/EMI/lapse sends; later Embedded Signup multi-number + Nidaan branch reseller + two-way webhook. Strategy: WHATSAPP_SUBSCRIBERS_PLAN.md §9.

**PHASE 5 — Old pending (interrupted by WhatsApp config).**
- Views engine: roll Table/Board/Cards switcher to Tasks/Accounts (proper shared-component refactor).
- Telegram: radar read/reply in-bot; payment-link create; stage-move customer-notify parity.
- Claimant Portal P2: two-way messaging (reuse nidaan_messages); doc-requests as Tasks.
- Radar dual-mode (one-way/two-way/both) + Message-ID dedup + mode badges + Yahoo + auto-forward ingest.
- Doc Splitter P2: attach split docs to a claim; DOC/DOCX (LibreOffice); custom category list.

**OWNER action items:** submit WA templates · live-test Claimant Portal + flip `claimant_autosend_enabled` ON · CS live doc-pull test + status resync · clean 'T30 G ABHISHEK' test account · send staff announcements (ANNOUNCEMENTS.md) · counsel-vet success-fee T&C (LLP wording drafted).

---

## ★ START HERE — the whole project in 2 minutes (for a new agent)

**What this is:** ONE FastAPI app + ONE SQLite DB serving **TWO products**, chosen per request by host: `_is_nidaan_host(request)` → NidaanPartner; else Sarathi.

1. **Sarathi-AI.com** — a **voice-first CRM for Indian insurance advisors**. Advisor runs their day by **voice note on a private Telegram bot** (+ web app + mobile web). Leads, follow-ups, renewals, tasks, quotes, calculators, AI tools. Plans from ₹199/mo, 7-day free trial. Admin = **`/superadmin`**.
2. **NidaanPartner.com** — **insurance claim-dispute resolution** ("Nidaan · The Legal Consultants LLP"). Policyholders/advisors submit rejected/underpaid claims; Nidaan reviews (₹499 one-time or subscription); "can-fight" claims escalate to **Level-2 (L2) legal** via the **ClaimShield.in** integration. Surfaces: customer dashboard (`nidaan_dashboard.html`), **ops portal `/nidaan/ops`** (`nidaan_ops.html`), branch portal (`nidaan_branch.html`), homepage (`nidaan_index.html`).

**Key modules (all backend routes live in `sarathi_biz.py`, ~23k lines):**
- `biz_database.py` — schema + migrations (all `CREATE TABLE` + `ALTER` here). DB = `/opt/sarathi/sarathi_biz.db` (SQLite WAL).
- `biz_auth.py` — JWT/tenant/staff auth. `biz_ai.py` — all Gemini calls. `biz_email.py` — email (Resend/SMTP).
- **Nidaan:** `biz_nidaan.py` (data/claims/branches/tasks), `biz_nidaan_notifications.py` (all-channel staff/subscriber notifs), `biz_claimshield.py` (L2 integration), `biz_nidaan_radar.py` (**Email Update Radar** — watches customer Gmails, AI-triages, auto-creates Tasks; see §A84).
- **Sarathi:** `biz_sarathi_tgcrm.py` (Telegram voice CRM bot — conversational AI with memory + confirm-to-act; see §A83/A85). `static/sarathi_guide_widget.js` (homepage AI sales chat → persists to retail inbox).
- **Roles (Nidaan staff):** `super_admin` > `sub_super_admin` > `team_member`, via `_require_staff(request, min_role)`.

**Infra & deploy** (full detail §19/§30 + memory `infra_*`):
- Server **84.247.172.252** (Contabo, `ssh -i ~/.ssh/id_ed25519 root@…`). **Blue-green web** on ports 8001+8002 (nginx upstream) + **one `sarathi-worker`** (Telegram bots + APScheduler singletons, guarded by `if RUN_SINGLETONS:`).
- **Deploy:** `git push origin master` → `ssh … "sudo -n systemctl start sarathi-deploy.service"` (does `git reset --hard origin/master` + rolling restart). **Validate before push:** `C:/Windows/py.exe -m py_compile <files>` + `node` vm-check inline `<script>` JS. **Cloudflare caches `/static` immutably → bump `?v=N`** on JS/CSS changes.
- `/opt/sarathi/biz.env` (secrets, `sarathi:sarathi 600`, NOT in git). Env changes need chown+chmod + health-curl.

**Ground rules (from founder — memory `feedback_*`):** mobile-first (verify phone viewport); Tier-II/III plain language (words over icons); **total-language i18n** (everything switches with the selector); **additive + backward-compatible, never break the live path**; **confirm before any delete**; **endpoint uniformity** (a shared-concept change applies at ALL sibling endpoints); draft a **bilingual EN+HI staff announcement** in `ANNOUNCEMENTS.md` per ship (founder sends); keep **this doc live**.

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

### 44.9 Ops refresh flicker, WA count alignment, WA coverage (Jul 10, 2026)
1. **Ops login-flash on refresh (fixed):** `#loginScreen` was visible while the saved
   token was validated async. Pre-paint gate `html.ops-has-token #loginScreen{display:none}`
   (set in `<head>` from localStorage); init() reveals login only if validation fails.
2. **WhatsApp "sent today" mismatch (fixed):** App Health used raw `daily_sent_count`
   while the Official Numbers page used the reset-aware count (`compute_effective_caps`
   zeroes a counter whose `daily_count_reset_at` ≠ today). App Health is now reset-aware
   too — both agree.
3. **WhatsApp plug-and-play — confirmed + extended:** disconnect already DROPS WhatsApp
   silently (no queue/backlog: `no_active_instance` doesn't record/defer), and routing
   is already hardened (staff-only allow-list + verify-before-send). Added coverage:
   `on_quick_task_comment` (new comment → assignee+creator via dashboard+push+WhatsApp)
   wired into the note endpoint; `record_broadcast` now mirrors to staff WhatsApp when a
   line is connected (background, flag `nidaan_broadcast_wa`, per-send verify) and skips
   silently when disconnected. Broadcast push URL → `/admin`. (Budget-defer for
   near-cap numbers stays — that's intentional ban protection, not a disconnect backlog.)
4. **Ghost-connection detection (Jul 10):** ROOT CAUSE of "comment didn't trigger
   WhatsApp" was NOT code — Evolution reported the number `open` while every send
   failed with `SessionError: No sessions` (a stale WhatsApp session; number verifies
   fine, connectionState 'open', but 0 sends). Fix is operational (**Re-pair QR**, or
   Remove+Add). Code added to surface it: `_send_wa` now preserves the real Evolution
   error detail; `wa_send_health()` derives per-slot send health from recent WhatsApp
   outcomes (broken = latest attempt failed + no recent success); Official Numbers page
   shows an orange **"⚠ CONNECTED (SEND FAILING)"** pill + re-pair banner, App Health
   flags it too. A single successful send clears the flag.
   *(Superseded Jul 10–11 — see §45.5 "NOT WORKING — RE-PAIR" + §45.6 orchestrator.)*

---

## 45. WHATSAPP RELIABILITY + TASK COLLABORATION + PWA + AI-BOT PLAN — JUL 10–11, 2026

This session hardened WhatsApp end-to-end, made the ops app a real installable app on
both platforms, added admin-editable task categories + attachments, built multi-party
task collaboration, and stood up a self-managing WhatsApp orchestrator. All shipped +
deployed (blue-green) unless marked otherwise.

### 45.1 QR pairing made reliable — "Couldn't link device / try again later" (fixed)
- **Root cause:** the pairing QR was fetched once and shown as a *frozen image*. WhatsApp
  rotates its QR every ~20s and invalidates the old ref, so the SA was scanning a dead
  code → WhatsApp's own "Couldn't link device — try again later". (WhatsApp Web works
  because it live-refreshes.) The earlier 40s QR spam-guard made it worse by blocking any
  refresh.
- **Fix (`ops_official_qr` + `showQR` in `nidaan_ops.html`):** split the heavy **Re-pair**
  (`force=1`: logout + recreate, throttled 15s) from a lightweight **live-QR poll**
  (`force=0`, no logout). The UI now polls every ~18s, swaps the QR image live, and
  auto-detects the connect (state `open` → green "Slot connected!"), stops on drawer
  close / view change / ~4 min. Guidance: scan promptly, use the official WhatsApp app.

### 45.2 Official-number "save the number" popup firing on every refresh (fixed)
- Gate compared instances' max `updated_at` to the ack timestamp — but `updated_at` bumps
  on **every send + every re-pair**, so it kept re-triggering. Now gated on a **signature
  of the phone-number SET** (add/remove only), acknowledged per-device in localStorage
  (`nidaan_ops_numack`). Fires only when the set of numbers actually changes.

### 45.3 Admin-editable task categories + attachment on quick-task create
- **Categories (#6):** new `nidaan_task_categories` table (code/label/colour/sort/active),
  seeded **RT (Review Task)** + **GT (General Task)**; `nidaan_quick_tasks.category_code`
  column. API `GET /task-categories` (any staff) + `POST/PATCH/DELETE` (SA, soft-deactivate).
  Ops UI: category dropdown in the Quick Task form; coloured badge in registry/widgets/drawer;
  category **filter** on the board; full **category manager in Workflow Settings**
  (add/rename/recolour/reorder/deactivate). `list_quick_tasks` gained a `category_code` filter.
- **Attachment on create (#5):** Quick Task form has a 📎 picker; on create the file (with
  the first comment) is uploaded as the task's first note via the existing multipart notes
  endpoint.
- **Task-list sorting (#2):** `list_quick_tasks` gained a `sort` param
  (`smart` | `updated` | `created_desc/asc` | `id_desc/asc` | `due` | `priority`) via
  `_quick_task_order_sql`; ops registry has a Sort dropdown.

### 45.4 Real app-install + iOS notifications + mobile app-shell (#3/#4)
- The "Chrome • possible spam / Unsubscribe" push chrome + missing iOS notifications both
  come from the app not being installed to the home screen. Fix = make it reliably
  installable everywhere.
- New shared **`static/nidaan_install.js`**: captures `beforeinstallprompt` (Android/desktop)
  for one-tap Install, AND on iOS Safari (no such event; Web Push only works once installed)
  shows an **"Add to Home Screen"** guide. Standalone-aware, dismissal remembered per app,
  exposes `NidaanInstall.show()`. Subscriber dashboard swapped its Android-only banner for
  this module (now covers iPhone). Ops app already had Android+iOS handling — left intact.
- Mobile app-shell: `viewport-fit=cover` + `@media (display-mode:standalone)` **safe-area
  insets** on both apps (header clears the notch, content clears the home bar).

### 45.5 WhatsApp send reliability — failover, honest health, task linking
- **Line-failover (`_send_wa_failover`):** a send tries the picked line first, then
  automatically fails over to the other healthy official line on a session/slot error, so a
  single working number keeps WhatsApp flowing when another is a dead ghost. Recipient-
  specific errors (not-on-WhatsApp / blocked) do NOT retry. `dispatch()` records the line
  that actually sent. `pick_staff_slot` now prefers lines that are actually sending (skips
  ghosts when a working line exists).
- **Honest line health (`wa_send_health`):** was marking a line healthy if it had ANY success
  in 24h — so a line that sent this morning but fails every send now showed green. Now judges
  the **current streak**: newest send failed with a session error (or a run of failures with
  no success since) ⇒ **broken**. Badge relabelled **"NOT WORKING — RE-PAIR"**.
- **Task linking:** assignment/reassign/comment/status notifications now pass `task_id` so
  alerts trace to the task and deep-link correctly.

### 45.6 Self-managing WhatsApp ORCHESTRATOR (watchdog) — LIVE
Deterministic orchestrator (intentionally NOT an LLM — never let an AI guess whether to
restart a line), worker-only singleton, every 4 min (`run_wa_watchdog_cycle`):
1. **Routes** through a line that's actually sending (health-aware `pick_staff_slot` + failover).
2. **Checks** real send-ability per line (from `wa_send_health` + Evolution state).
3. **Auto-fixes** — `wa_evo.restart_instance` (up to 3×/outage) then a probe send to confirm.
4. **Escalates** — if it can't self-heal, alerts **every super-admin** via dashboard bell +
   web push + email (NEVER the dead WhatsApp), **once per outage**, telling them to Re-pair.
5. **Recovers + resumes** — while down a probe fails silently (nothing delivered, no spam);
   on recovery it delivers one "back online" ping, clears state, announces recovery, WhatsApp
   resumes automatically.
- State in `nidaan_ops_settings` (`wa_wd_slot{n}` JSON); flag `nidaan_wa_watchdog_enabled`
  (default on); probe target = `wa_probe_number` or first active SA's phone.
- **Verified live:** cycle logged `{1:'down', 2:'down'}`, restarted 3× each, alerted SAs
  (staff 1/2/11/13/19/22) — proving detection + escalation work.

### 45.7 The Baileys "No sessions" diagnosis + strategic decision
- **Proven by direct Evolution API test:** BOTH official lines return
  `{"error":"Bad Request","message":["SessionError: No sessions"]}` on every send while
  reporting state `open`. Restart doesn't fix it; number verifies fine. This is inherent
  fragility of self-hosted **linked-device (Baileys)** automation — sessions die when the
  host phone sleeps/loses network, or when a **clone/dual WhatsApp app** is used (line 1 /
  9244144804 is on a clone → unfixable via server; must use genuine WhatsApp or Remove).
- Today's channel tally proved the *system* is fine: **email 53/53, dashboard 106/106,
  WhatsApp 5 sent / 29 failed** (all failures after ~06:53). Assignees still got tasks by
  email + dashboard; only WhatsApp failed.
- **User decision:** stay on **Baileys** (re-pair when it dies) rather than move to the
  official WhatsApp Cloud API. The orchestrator (§45.6) exists to make that choice bearable.
  **Operational TODO (user):** re-pair Annapurna (9826011116) from its *genuine* WhatsApp on
  a phone kept **online**; line 1 likely to be Removed (clone).

### 45.8 Multi-party task collaboration — @mention / participants / mute (LIVE)
A task has one assignee but work is collaborative:
- **@mention** a teammate in a comment (autocomplete in the comment box) → they become a
  **participant**: task appears in their list, they can open + comment, and get a
  "🏷️ you were tagged" alert.
- **All progression** (comments, status changes) notifies **everyone involved** — creator +
  assignee + every @mentioned participant — minus the actor.
- Any participant who's done can **Mute** the task (per-person) to stop pings while keeping
  access (for busy 10-person tasks).
- Backend: `nidaan_quick_task_watchers` table; `add_task_watchers` / `list_task_watchers` /
  `set_task_watch_mute` / `is_task_participant` / `get_task_participants`; `list_quick_tasks`
  visibility widened to @mentioned tasks; note-add accepts `mentions`; `POST .../mute`; get
  returns `participants` + `me_muted`. Notifications: `on_quick_task_mention` +
  `_notify_task_participants` fan-out (used by `on_quick_task_comment` / `_status_changed`)
  respecting mute. UI: @mention autocomplete, "👥 Involved" chips, Mute/Unmute; participants
  can comment.

### 45.9 AI WhatsApp assistant — PLAN (read-only first; NEXT build)
- **Confirmed scope:** read-only first. Vision: a staffer/SA sends a WhatsApp text/voice note
  ("status of the Bajaj escalation task?") → the assistant reads tasks/claims and replies
  naturally. Honest split agreed: **health/routing/auto-fix = deterministic code (§45.6)**;
  **Claude Sonnet = the conversation layer** (natural inbound answers with claim/task context).
- **Architecture:** inbound Evolution webhook (`messages.upsert`) → **strict sender-auth**
  (only registered staff numbers may query internal data) → (Gemini voice transcription for
  voice notes) → Claude Sonnet agentic tool-use (search tasks, get status, my open work,
  claim status) → reply on WhatsApp. Build transport-agnostic so it moves to the official
  API later with zero rework.
- **Dependencies/blockers:** no inbound WhatsApp exists yet (send-only today); cannot be
  tested end-to-end until a line is re-paired (both down). **Status: queued, not started.**

### 45.10 Two platforms + backup posture (reaffirmed — the "kept separate + backed up" answer)
- **One codebase, two products, cleanly separated.** A single FastAPI app (`sarathi_biz.py`)
  serves BOTH by **host detection** — `_is_sarathi_host` (sarathi-ai.com, advisor CRM) vs
  `_is_nidaan_host` (nidaanpartner.com, claim-review + ops portal). Routes 404 on the wrong
  host, so the products never bleed into each other. `biz_platform_bridge.py` is the ONLY
  module that reaches from Nidaan into Sarathi tenants/agents (see Infra: Platform Boundary).
  Nidaan ops lives under its own installable scope `/admin`; subscribers under `/nidaan/`.
- **Backups (unchanged, healthy):** local **7-day rotation** + off-server **AES-256-encrypted**
  snapshots pushed to a private repo (`sarathi-db-backups`); passphrase in `biz.env` + off-site.
  Secrets in `biz.env` (0600, never committed).
- **Deploy:** `git push origin master` → `ssh root@84.247.172.252 … deploy/auto-deploy-zerodowntime.sh`
  (blue-green: worker singletons restart, then web@1/@2 roll one at a time with health checks —
  no downtime). Validate before deploy: `py_compile` + extract inline JS → `node --check`.

---

## 46. OPS PHASES 1–5 — TASK UPGRADES, WFH, TELEGRAM OPS BOT — JUL 20, 2026

Agreed up front with the user: discuss → phase → build. All phases below are shipped and
verified in production unless flagged. Governing decisions this round: approval
notifications go to a **named approver** (fallback super-admins only — no more all-admin
blasts); tasks are **editable by their creator** (audit-logged); ops comms **move to
Telegram** (WhatsApp/Baileys stays customer-facing, best-effort).

### 46.0 Bug found + fixed: Sarathi renewal reminders were dead (revenue impact)
`run_sarathi_subscription_renewal_scan` selected a non-existent column `subscription_plan`
from `tenants` (real column: **`plan`**), so the scan raised on every run and **Sarathi-AI
renewal reminder emails had silently stopped**. Fixed with `plan AS subscription_plan`;
verified against live data. Found while triaging the "lots of errors in App Health" report.

### 46.1 App Health noise triage (most of it was NOT actionable)
- `Evolution timeout` on routine health polling → now **INFO**; the actionable signal is the
  line's health state, already surfaced honestly in the UI.
- Watchdog `cycle: {n:'down'}` → **INFO** (it already WARNs + alerts once on transition).
- Watchdog now **clears stale state** for slots whose number was removed.
- `Exception in ASGI application` (×1) = client disconnect mid-response — benign.

### 46.2 Phase 1 — task upgrades
- **Assign-to defaults to "None (unassigned)"** — it pre-selected the current user, so an
  untouched picker silently self-assigned.
- **Multiple attachments** — new `nidaan_quick_task_attachments` table; notes endpoint takes
  `files` (up to 10; legacy single `file` still honoured); create form + comment box are
  multi-file; every attachment renders as a chip.
- **Task edit** — creator **or** super-admin can fix title / description / category / due
  date / priority via PATCH; every field change written to the immutable task log. New
  ✏️ Edit panel.
- **Involve people at creation** — multi-select adds collaborators up front (same watcher
  model as @mention) and notifies them.
- **Approval routing** — `nidaan_quick_tasks.approver_staff_id`; only the named approver is
  pinged, falling back to super-admins.

### 46.3 Category-driven complainant capture (not hardcoded to "RT")
Mandatory "Complainant name + mobile" for Review Task, implemented as an admin-editable
**`requires_complainant`** flag on `nidaan_task_categories` (seeded ON for RT, checkbox in
the category manager) rather than hardcoding a code — any future category can demand it with
no code change. `complainant_name` / `complainant_phone` live on the task and **persist
permanently even if the category changes later** (explicit requirement). Enforced in the form
AND server-side; shown in the drawer; editable via ✏️ Edit.

### 46.4 Phase 2 — personalized task dashboard + archive
- `list_quick_tasks` gained `scope=assigned_to_me | created_by_me | involved`
  ("involved" = @mentioned in, excluding tasks already yours).
- "My Open Quick Tasks" became three slices: **📥 Pending with me · 📤 Assigned by me ·
  🏷️ I'm involved**, each with an open count.
- **Leave/WFH tiles moved ABOVE** the task sections.
- **Archive:** the board defaulted to "All" so it grew forever. Registry now defaults to
  **Active**, with a dedicated **🗄️ Archived** view (`status=archived` → `done + cancelled`,
  plus an `archived` count). Scope is automatic — associates see their own archived tasks
  (viewer scoping), admins/SA see everyone's.

### 46.5 Phase 3 — Work From Home
WFH reuses the **entire** leave pipeline instead of duplicating it: `nidaan_leave_requests`
gained **`request_kind` ('leave' | 'wfh')**, so apply → notify → approve/reject → "currently
away" tiles all work for both through one tested path.
- "🏠 Apply WFH" button; modal retitles itself; new **🏠 Working From Home** tile; WFH pill on
  rows; approvals panel renamed "Pending Approvals"; notification copy is kind-aware.
- **Task Permissions** moved out of the leave tiles into **Workflow Settings**.

### 46.6 Phase 5 — TELEGRAM OPS BOT (the strategic shift)
Rationale: Baileys WhatsApp kept dying (`SessionError: No sessions`) and carries real ban
risk. Telegram's **official Bot API** has no ban risk, needs no phone kept online, has no
session to re-pair, is free, and supports inline buttons/files/voice.

New **`biz_nidaan_telegram.py`** — Nidaan-owned (patterns borrowed from the Sarathi bot but
**no shared state or dependency**, per the user: "copy, don't reuse"):
- `verify_token` (getMe), `set_webhook` with a **token-derived secret path**, `send_message`
  with inline buttons, per-staff link codes, `/start <code>` linking, `notify_staff`.
- Config in `nidaan_ops_settings` (`telegram_bot_token/_username/_enabled`); staff link
  fields on `nidaan_staff` (`telegram_chat_id`, `telegram_username`, `telegram_linked_at`,
  `telegram_link_code`).
- Endpoints: `GET/POST /telegram/config`, `/telegram/toggle`, `/telegram/unlink`,
  `/telegram/test`, `POST /nidaan/telegram/webhook/{secret}` (404s unless the secret matches).
- **Delivery:** staff dashboard notifications mirror to Telegram alongside web push —
  fire-and-forget, silent when unconfigured/unlinked so rollout can't break anything.
- **UI — self-service by design** (explicit requirement): new **✈️ Telegram Bot** menu panel.
  Staff get a one-tap Connect deep link + `/start <code>` desktop fallback, test button and
  Disconnect. Super admin gets a step-by-step @BotFather guide, token paste, live status,
  linked-staff count, pause/resume.

### 46.7 One-time comms onboarding popup
The "Official WhatsApp numbers updated" modal kept re-appearing (it re-fired whenever the
number set changed). Now a **one-time** Telegram onboarding acknowledged **server-side** via
`nidaan_staff.comms_onboarded_at` — once dismissed it never returns on any device.

### 46.8 Email — OPEN ITEM (blocked on credentials)
**Brevo rejected** (300/day then costly). Chosen: **Gmail SMTP with `nidaanpartner@gmail.com`**
— free, ~500/day vs ~53/day actual. (Cloudflare **cannot send** — inbound routing only;
Amazon SES ≈ ₹15/month is the scale path if Gmail is outgrown.)
**Status:** the app password in `biz.env` still belongs to `kumar26.dushyant@gmail.com`
(verified `LOGIN OK` as that account; key ends `feqi`). The correct key for
`nidaanpartner@gmail.com` ends `hoqx` but was never saved. Needed in `biz.env`: `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NOREPLY`, `SMTP_FROM_SUPPORT`,
`NIDAAN_FROM_EMAIL` → all `nidaanpartner@gmail.com` + the new key. Deliberately NOT changed
unilaterally — swapping addresses against the wrong account's password breaks all email.

### 46.9 Next up
- Finish 46.8 once the correct app password is saved, then verify a real send end-to-end.
- **AI Telegram assistant (read-only)** — now the natural home for the assistant idea.

---

## 47. TELEGRAM OPS PLATFORM — FULL BUILD, VOICE, TASK-CREATE, PROFILES — JUL 20–22, 2026

The Telegram bot went from notifications-only to **running the office**: role-aware button
UI, an AI brain, voice notes, and task creation — all in sync with web/mobile because every
action calls the SAME backend. Module: **`biz_nidaan_telegram.py`** (Nidaan-owned; Gemini
key `GEMINI_API_KEY`, model `gemini-2.5-flash`). Bot: **@NidaanOpsBot** (`bot_id` stored).
All shipped + verified in production.

### 47.1 Email — FIXED (was §46.8 blocker)
The app password was saved only in the LOCAL `C:\sarathi-business\biz.env`; production reads
`/opt/sarathi/biz.env` on the server. Copied the correct key (ends `hoqx`) to the server via
SSH (piped, never printed), de-duped `SMTP_` lines, re-locked 0600. **Verified**: SMTP
`LOGIN OK` as `nidaanpartner@gmail.com` + a real test email delivered. All Nidaan mail now
sends from/replies to `nidaanpartner@gmail.com`. Also set super-admin Dushyant's `notify_email`
→ `nidaanpartner@gmail.com` (was routing to a personal Gmail via a domain forward on
`dushyant@nidaanpartner.com`). `8696483340` confirmed NOT in any staff record (it was only the
"Sonal" Telegram account); staff phone is `8875674400`.

### 47.2 Delivery transport — LONG-POLLING (not webhooks)
Cloudflare's bot protection returned **520** to Telegram's inbound webhook (our own curl to
the same URL got 200). Switched to **outbound long-polling** (`run_polling_loop`, worker-only
singleton, `getUpdates` timeout 25) so Cloudflare is out of the path entirely. Single consumer
= each update processed once; self-heals across token change / pause / network blips. Saving a
token now `deleteWebhook`s rather than setting one. The webhook endpoint still exists but is
unused.

### 47.3 Secure linking (staff-only) — the "non-staff got a message" fix
Incident: a non-staff Telegram account linked via a **shareable connect code** (bearer token).
Fixed twice over:
- **Phone-verified** (`_link_by_phone`) — Telegram's request_contact button; link only if the
  verified number matches a registered staff mobile. BUT request_contact is **mobile-app only**
  (no button on Telegram Web) — so:
- **Universal one-time code** (`issue_link_code` / `_link_by_code`) — 8-char, 15-min, single-use,
  bound to the portal-authenticated staffer, consumed on first use. Deep link
  `t.me/<bot>?start=<code>` works on web/desktop/mobile. This is the primary path; a leaked link
  is useless because it expires + is single-use. Portal card redesigned to 3 clean steps + a
  collapsed code fallback.

### 47.4 Multi-device — one staffer, many Telegram accounts
Telegram bot links are per-ACCOUNT (already shared across that account's devices). Users who run
DIFFERENT Telegram accounts on phone vs web needed each linked. New table
**`nidaan_staff_telegram`** (chat_id PK, staff_id, username, linked_at); existing single links
migrated in. `_bind_chat` adds/moves a device; linking ADDS (not replaces); `notify_staff` fans
out to ALL a staffer's devices and prunes dead ones (bot blocked/deleted); lookup/count/
unlink-all/clear-all rewritten against the table. Portal shows device count + "➕ Connect another
device". The legacy `nidaan_staff.telegram_chat_id` column is kept loosely in sync but the table
is the source of truth.

### 47.5 The office, in Telegram (role-aware button UI)
Every action re-checks role SERVER-SIDE from the chat_id (a button is never trusted). Menu:
📥 Pending with me · 📤 Assigned by me · 🏷️ I'm involved · 🗄️ Archived (same four slices +
scoping as web) · ➕ New task · ⏳ Approvals (admins) · 🌴 Leave / 🏠 WFH · 🤖 Ask AI · 📣
Broadcast (SA) · ❓ Help · 🌐 language toggle. Task detail: ▶️ Start / ✅ Done / ↺ Reopen
(assignee or admin), 💬 Add comment, 🔗 open in portal. Approvals: inline Approve/Reject filtered
to the named approver. Leave/WFH: free-text dates+reason → same approval pipeline.

### 47.6 Gemini AI brain (read-only, role-scoped)
`_ask_gemini`: answers ONLY from tasks the asker may see (associates = their own; admins =
org-wide), so it can't leak across roles or act. Replies in the staffer's language.
**Fix (Jul 21):** "status of #333" wrongly said not-found because only the 60 most-recent tasks
were in context (≈295 total). Now every task number named in the question (#333 / task 336 /
number 340) is fetched DIRECTLY via `get_quick_task` (with access check) and added to context,
with its description for richer answers; recent window 60→80. Applies to text AND voice.

### 47.7 Bilingual (Hindi/English) + non-destructive translation
Per-staff `telegram_lang`; 🌐 toggle. All bot chrome routed through a fixed EN/HI table
(`T(lang,key)`, `_BOT_TXT`) — zero mistranslation risk (pre-written). Task CONTENT shown as-is.
Typed/spoken Hindi comments keep the ORIGINAL text and store an auto **English aid**
(`nidaan_quick_task_notes.note_lang/note_translation`, Devanagari-detected) shown on the web
dashboard as "🌐 English (auto): …" — original is NEVER overwritten. `translate_to_english`
preserves names/numbers/IDs.

### 47.8 Self-syncing staff guide + audio
`biz_nidaan_capabilities.py` is ONE registry (each capability: EN/HI text, telegram?, web?,
min_role). It generates the web "📖 How to use" panel, the bot ❓ Help, AND the spoken narration
— so they can never contradict the product. Web guide has an EN/हिंदी toggle + 🔊 Listen using
the browser SpeechSynthesis API (chunked for Chrome's long-text limit, async voice load,
keep-alive resume, honest "no Hindi voice installed" fallback + install steps).

### 47.9 Voice notes (transcribe + clarity + safety) — Jul 21
Send a 🎤 voice note (any language). ONE Gemini call transcribes AND assesses, returning
`status ∈ {clear, unclear, noisy, silent, abusive, nonsense}`:
- clear → shows "🗣️ I heard: …" then routes exactly like typed text (`_process_message_text`).
- silent/noisy/unclear → specific human prompt (speak up / quieter place / re-record).
- abusive → politely refused (also catches Gemini safety `blockReason`).
- nonsense → asks for a clear request.
Safeguards: ≤~2.5 min / 15 MB, temperature 0, "never invent words", download/transcription
failure → "try again or type". Comments via voice still go through the confirm-before-save step.
`_download_file` (getFile + file endpoint), `_transcribe_and_assess` (inline base64 audio,
response_mime_type application/json). **Cost:** Gemini bills ~32 tokens/sec of audio → ~₹0.06–0.20
per note; ~₹300–450/month at 100/day. Trivial.

### 47.10 Create tasks from Telegram — hybrid (speak + tap + review), Jul 22
➕ New task flow: speak/type the TITLE (voice ok) → pick the exact fields with BUTTONS
(category → assignee → priority → due) so people/categories/dates can't be misheard → if the
category requires complainant details (e.g. Review Task) the bot demands name + a validated
10-digit mobile (same as web) → FINAL review card (every field) → ✅ Create. Role-based like web
(admins assign; team members raise a request). Calls the SAME `create_quick_task`
(`source='telegram'`) → identical task, in sync, notifies everyone. **The bot never EDITS a
task** — all corrections/error-fixes happen on web/app (deliberate, avoids conflicting edits).
State machine in `telegram_pending`; stale text at a button step nudges to use buttons.

### 47.11 Bot manager + instant connect link (super admin)
Telegram Bot panel shows a live **Team connections** list (connected / device count / @username /
pending) with counts. **🔗 Instant link**: SA generates a fresh one-time (force) code for a
struggling staffer → copy / share on WhatsApp → they tap → connected. Endpoints
`GET telegram/staff-status`, `POST telegram/instant-link/{staff_id}` (SA, audited).
**Bot lifecycle** documented + handled: pause (token+links kept), disconnect (links kept —
re-add SAME bot restores all), new token same bot (survives — `bot_id` compared), DIFFERENT bot
(old links dead → auto-cleared + told how many must reconnect); "📨 Remind unconnected staff"
nudges via bell+push+email. Throughout, dashboard+push+email keep delivering — only the Telegram
copy pauses.

### 47.12 Traceability + wrong-task safeguard (Phase B)
- **Activity source** on every task action: `source` column on notes + log; threaded through
  create/status/reopen/reassign/edit/approval/comment. Web sets it from the User-Agent
  (`_req_source` → web | mobile-web); bot passes `telegram`. UI shows a chip (✈️/💻/📱) in the
  activity log and on each comment.
- **Wrong-task confirm**: commenting from Telegram asks "Add this comment to #321 — <title>?
  ✅/✕" and only saves on confirm — a comment can't land on the wrong task (also lets the sender
  verify a voice transcript before saving).

### 47.13 Staff profile + avatars (Phase C)
Top-bar avatar+name → **My Profile** modal: VIEW-ONLY name/role/email/mobile/Telegram status;
team members may change ONLY their **photo** (≤5 MB, `nidaan_staff.profile_pic`, served via
signed doc URLs so `<img>` works) and **language** (EN/HI, shared with the bot). Email/mobile are
admin-managed. Avatars now show on task cards (assignee), @mention dropdowns, task-drawer
"Involved" chips, and the top bar (initials fallback). Endpoints: `GET me/profile`,
`POST me/profile-pic`, `POST me/language`.

### 47.14 Involve-tagging fix + role-targeted announcements
- **Involve others** on the create form: replaced the native multi-select (which visibly
  deselected) with @-tag chips (type → pick → chip, remove with ✕); ids sent as `mention_ids`.
- **🆕 Announce** (SA): compose title + details + role checkboxes → reaches ONLY those roles on
  bell + push + Telegram + email (via `notify_staff_inapp`). So staff learn about features
  relevant to their role. Endpoint `POST /nidaan/ops/api/announce` (SA, audited).

### 47.15 Also this session
- **Archived tasks view** — registry defaults to Active; 🗄️ Archived (done+cancelled), scoped
  (associates see own, admins all), so the board stays short.
- **Sarathi renewal-scan bug** — `run_sarathi_subscription_renewal_scan` selected a non-existent
  `subscription_plan` (real col `plan`) → crashed every run → renewal emails had stopped. Fixed
  (`plan AS subscription_plan`), verified.
- **App Health noise** downgraded (routine Evolution timeouts + watchdog cycles → INFO; stale
  watchdog state cleared).
- **Task search** moved to the top of the Tasks panel; **Task Permissions** moved into Workflow
  Settings; **complainant fields** category-driven (`requires_complainant`); **WFH** via
  `request_kind`; **task categories** admin-editable; **@mention collaboration** + mute; **task
  edit** (creator/SA, audited); **multiple attachments**; **assign-to defaults to None**;
  **approval routing** to a named approver.

### 47.16 Next up / parked
- Admin "move a comment/attachment to another task" — corrective tool, parked until a real mix-up.
- Natural Telegram additions when desired: claims lookup, staff workload, morning digest.
- WhatsApp (Evolution/Baileys) remains customer-facing best-effort with the self-healing
  watchdog; internal ops now runs on Telegram.

---

## 48. FLEXIBLE PLANS + MOBILE-FIRST IDENTITY + OPS RESTRUCTURE — JUL 24–26, 2026

Theme: make the whole subscription/pricing machine super-admin editable (no code changes),
switch customer identity to mobile-first (email optional), harden payments against drop-off,
and restructure the ops Accounts/Claims views. All shipped to prod via blue-green + verified.

### 48.0 Housekeeping fixed earlier this session
- **Off-server encrypted backup restored** — `deploy/git-db-backup.sh` was untracked and got
  wiped by `git clean`; reconstructed, tracked, `.gitattributes` pins `*.sh` to LF. (Hot sqlite
  `.backup` → gzip → AES-256-cbc pbkdf2 → private repo `sarathi-db-backups`.)
- **Web task creation was dead** — a `_req_source` helper sat between `@app.post(".../quick-tasks")`
  and its handler, so the route bound to the helper (always returned "web", never created). Moved
  the helper above the decorator.
- **@mention notifications silently failing** — `aiosqlite.Row.get()` crash in a fire-and-forget
  task; fixed with `dict()`, added a global background-task exception handler (`_install_bg_exception_handler`).
- **UX**: confirmation toasts centered + larger; bell notifications newest-first; App Health now
  reports Telegram bot + staff-linked status.
- **Telegram bot**: clean `/menu` (setMyCommands removes start/reconnect clutter), universal
  escape (/menu, /cancel), full tracebacks on errors.
- **Email**: reply-to leak fixed (uses `sender_email`, not the global FROM), SMTP-first for the
  aligned Gmail sender.
- **Sarathi-AI**: "no agents available" fixed (auto-create owner agent when a tenant has none);
  DOB optional (only name + mobile mandatory on add-lead); request-timing middleware added to
  trace post-login latency.
- **Claim form** (nidaan_dashboard): branch-code free-text field (validated, uppercased), DOB
  optional, disclaimer simplified (no IRDA/DPDP wording); homepage walkthrough "Direct
  Policyholders" line reworded.
- **WhatsApp connect debugging**: disk was 100% full (69 GB Evolution container log) → truncated +
  logrotate + daemon.json caps; dead residential proxy replaced; redsocks → **gost bridge**
  (`gost-wa.service`). Rotating residential proxies proved unsuitable for Baileys' persistent
  socket → decision to use a **stable India 4G mobile proxy (iProxy)**. See §48.7.

### 48.1 Phase 1B — plans/pricing fully super-admin editable (single source of truth)
- **`nidaan_plans_config` table** is now the source of truth (seeded from `PLAN_LIMITS` +
  `NIDAAN_RAZORPAY_PLANS`). Editable in **ops → Plans & Billing**: price, claims/mo, disputed cap,
  CRM seats, features, badge, active, sort_order. Caps use `-1 = unlimited` (stored NULL).
- **Propagates everywhere**: `/nidaan/api/plans` (public) feeds the **homepage** tier cards and the
  **dashboard** upgrade/change-plan cards (both render dynamically now, with a static fallback);
  the claim-form disputed-cap nudge; quota enforcement (`can_submit_claim` reads `get_plan_cfg`);
  and the actual Razorpay charge amount.
- **Editable price with grandfathering**: checkout uses one-time Razorpay **ORDERS keyed on
  amount** (not immutable plan objects), so a price change needs no Razorpay-plan recreation.
  `create_nidaan_razorpay_order` sources the amount from config; existing subscribers keep the
  amount already charged (their sub row holds it) — only NEW checkouts use the new price. Ops UI
  confirms the grandfather rule before saving. Validated live: bad prices rejected, round-trip OK.
- Helpers: `seed_plans_config`, `get_plans_config`/`get_plan_cfg` (cached, `invalidate_plans_cache`),
  `update_plan_config` (field whitelist + bounds, parameterized), `public_plans`.

### 48.2 Phase 1C-c — mobile-primary identity (email OPTIONAL, payment-verified)
Decision (see §48.6): mobile is the primary identity; email optional; the Razorpay payment (not an
email/SMS OTP) verifies a real person; login by mobile OR email.
- **C-c1 keystone**: sessions resolve by token `account_id` via `_nidaan_account_from_payload()`
  (falls back to email) — migrated all 13 `get_account_by_email(payload["email"])` call sites.
  Behaviour-preserving for email accounts; lets email-less sessions work.
- **C-c2 schema rebuild (live, prod)**: `nidaan_accounts.email` was `NOT NULL UNIQUE`. Rebuilt the
  table so **email is nullable** (multiple NULLs OK under UNIQUE) + a **partial UNIQUE index on
  non-empty phone** (one mobile = one account). Backup taken first
  (`/opt/sarathi/backups/pre_email_migration_20260725_010228.db`); 17 rows + every FK preserved
  (account_ids kept verbatim); `integrity_check = ok`. Idempotent guarded rebuild added to
  `biz_database.py` (no-op on prod, self-heals dev/restores). `create_account` now: mobile
  required + unique, email optional (NULL when blank); `normalize_phone()` = canonical 10-digit
  key; `get_account_by_phone`; `authenticate_account` accepts mobile or email.
- **C-c3 backend**: `POST /nidaan/api/check-phone` (mobile-first entry) + `POST /nidaan/api/signup/mobile`
  (name + mobile + password, email optional & OTP-verified only if supplied, branch code locked at
  signup). 7/7 HTTP tests pass (invalid → 400, dup mobile → 409, email-less signup → token).
- **C-c3 UI (PAUSED)**: the mobile-first `nidaan_start.html` rewrite + `→ /nidaan/dashboard?subscribe=<plan>`
  handoff is intentionally deferred for the user's on-device testing (revenue-critical, mobile-first).
  The existing email-first signup still works and nothing is broken.

### 48.3 Payment drop-off resilience (three layers)
Requested focus: smooth payment, no dead-ends, recover if the user drops mid-payment.
1. **Client success**: Razorpay `handler` → `/subscribe/verify` → token+plan → `?payment=success`.
2. **Client recovery**: pending order moved from `sessionStorage` → **`localStorage`** (survives a
   mobile-UPI tab-kill); `recoverPendingPayment()` runs on load + on dismiss, calls
   `/subscribe/check`, activates idempotently (30-min expiry). `backdropclose/escape=false`.
3. **Server backstop**: signed webhook `/nidaan/api/webhook` (`payment.captured`) activates the plan
   idempotently regardless of the client. `RAZORPAY_KEY_ID/SECRET` + `RAZORPAY_WEBHOOK_SECRET` all
   confirmed present on the server.

### 48.4 Phase 1C-a — ops Accounts restructure
- `get_all_accounts_admin` enriched: `account_type` (subscriber / per_claim / lead), `claims_used`
  vs `claims_cap` (from config, honoring the 30-day window rollover), `disputed_cap`, per-claim
  balance. UI: segment tabs with counts (All / Subscribers / ₹499 one-time / Leads), plan badge
  (+ disputed cap), colour-coded usage bar. Verified live: 3 subscribers, 14 leads.

### 48.5 Phase 1C-b — All-Claims filters
- `get_claims_ops` + `/ops/api/claims` gained **branch**, **plan** (via active-subscription join),
  and **account_id** filters; returns `account_plan` per claim. Ops Claims panel: Plan + Branch
  dropdowns (branch list fetched once) routed through one `applyClaimFilters()` so all filters
  compose. Verified live (plan=silver→1, account=36→1, bad params → 422/401).

### 48.6 Decisions locked this session
- **Identity**: mobile-primary, email optional, **payment-verified** (no SMS gateway). Trade-off
  accepted: no email ⇒ no self-service password reset (nudge email; support otherwise).
- **Pricing**: price editable, **existing subscribers grandfathered**; checkout is one-time orders.
- **Branch profit-share** (planned): a configurable **% of subscription revenue** to the attributing
  branch; **branch attribution locked at signup** (no gaming). Attribution already flows via
  `branch_code` on `create_account`.
- **WhatsApp proxy**: use a **dedicated always-on Android phone** on the WhatsApp/data SIM running
  iProxy (stable IP), not the user's primary carry phone. Endpoint is swappable in ~2 min via
  `gost-wa.service`.

### 48.7 WhatsApp proxy — how we'll move (user action pending)
- iProxy turns an Android phone's mobile-data connection into a **fixed proxy endpoint**
  (`host:port` + creds) that stays constant even as the carrier IP rotates. WhatsApp *number* (the
  business SIM, dual-SIM OK) is separate from the proxy *IP*.
- Stability is the real constraint — a carried phone flips WiFi/cells (the failure we hit). Use a
  spare phone kept plugged in at home/office. Content is TLS to WhatsApp, so iProxy can't read it;
  keep it off the personal SIM for privacy + battery.
- **Next**: user arranges a separate phone → installs iProxy → sends the endpoint → swap
  `gost-wa.service` + restart → test connect. Parked until the phone is arranged.

### 48.8 Next up / planned to-dos
- **Signup UI (mobile-first)** — build `nidaan_start.html` rewrite + `?subscribe=` handoff. Backend
  is 100% ready; paused for the user's device testing first.
- **Phase 1C-d — branch profit-share + branch portal**: configurable %-of-revenue per branch,
  super-admin reconciliation view (ops), then a branch-facing portal (separate login) for a branch
  to see its attributed accounts + earnings. Attribution data already exists.
- **AI-driven customer support module** (large, standalone): multi-channel (WhatsApp reactive for
  customers, web chat, email), Telegram staff alerts, chat→ticket, AI auto-answer + human fallback
  (Mon–Fri 10–6).
- **Google Workspace branch emails** (`xyz@nidaanpartner.com`) — deferred to the end by the user.
- **WhatsApp proxy** (§48.7) — awaiting a dedicated phone + iProxy endpoint.
- Housekeeping: one harmless pre-existing orphan `nidaan_plan_quota` row for deleted account 22
  (can be cleaned anytime).

### 48.9 Phase 1C-d — branch profit-share + portal (BUILT, Jul 26)
- **1C-d.1 reconciliation (ops)**: `nidaan_branches.share_pct` (super-admin editable %, money
  config gated to super_admin). `list_branches` computes **revenue** (subscription ₹ collected from
  attributed accounts — `amount_paid` is stored in RUPEES) and **payout** = revenue × share_pct.
  Ops → Branches shows Revenue / Share % / Payout (a reconciliation figure, not auto-paid).
  Verified: acct 36 (silver ₹500) @ 20% → payout 100.
- **1C-d.2 branch portal** at `/nidaan/branch` (`static/nidaan_branch.html`): affiliate branches log
  in with **email OTP to their registered branch email** (the `@nidaanpartner.com` Workspace inbox)
  and see their referrals + earnings. Secure: branch JWT (`typ=nidaan_branch`) scoped to ONE
  branch_code (every endpoint resolves branch from the token, never a param); request-otp returns a
  generic response always (no email enumeration); only ACTIVE branches log in; accounts view is
  masked (mobile last-4, no claim details). Endpoints: `request-otp`, `verify-otp`, `me`, `accounts`.
  Verified end-to-end (401 no-token, share math, masking, enumeration-safe, wrong-OTP → 401).
- **Branch login = the branch's `@nidaanpartner.com` email** → this is WHY we need Google Workspace.
  Guidance given: subscribe at workspace.google.com Business Starter (~₹136/user/mo), use existing
  domain `nidaanpartner.com`, verify via TXT record, set MX records (⚠️ changes where @domain mail
  is delivered — check nothing else uses it first), create one mailbox per branch, set each branch's
  mailbox as its `contact_email` in ops → Branches. OTP login works the moment the inbox is real.
  (Google Workspace signup itself is the user's action; deferred until they subscribe.)

### 48.10 AI customer-support module + Google Workspace (Jul 26)
- **Google Workspace LIVE**: MX switched to `smtp.google.com` on Cloudflare (Email Routing
  disabled), domain verified, Gmail active. Sending is UNCHANGED by this (MX = receiving only):
  app still sends Nidaan mail from `nidaanpartner@gmail.com` (SMTP_USER), Sarathi from
  `info@sarathi-ai.com`; admin alerts go TO `kumar26.dushyant@gmail.com` + `ashwin.kaushal@gmail.com`
  (gmail, so no bounce risk from the MX change). Optional upgrade queued: send app mail from
  `info@nidaanpartner.com` (create mailbox + app password → update SMTP_USER/PASSWORD/NIDAAN_FROM_EMAIL).
  Workspace admin = `dushyant@nidaanpartner.com`; the two gmail accounts are billing/recovery only.
  Branch-portal login (§48.9) uses these @nidaanpartner.com mailboxes — create one per branch and
  set it as the branch's contact_email.
- **AI customer support (nidaanpartner.com)** — increments 1–3 SHIPPED + verified:
  - Backend: `nidaan_support_threads`/`nidaan_support_messages` (thread_key = per-thread secret,
    enumeration-safe). `biz_ai.nidaan_support_reply()` = bilingual Gemini answer from a fixed KB;
    never quotes prices/caps/case outcomes; fails safe (escalate on error).
  - Endpoints: `POST /nidaan/api/support/message` (new/continue thread, AI reply, escalate),
    `GET /nidaan/api/support/thread` (key-gated).
  - Widget: `static/nidaan_support_widget.js` floating chat on the homepage + dashboard;
    persists thread in localStorage; mobile-first.
  - Escalation → `on_support_escalated()` alerts admins (bell + push + email + Telegram).
  - Ops **💬 Support** panel: thread inbox (Needs-human / AI / Closed / All), conversation drawer,
    staff reply (clears escalation), mark-closed. Verified: escalation loop, ops list, auth-gating.
  - Later increments: realtime staff-reply push to the customer widget; WhatsApp + email channels.
- One-click @nidaanpartner.com inbox creation from ops (Admin SDK Directory API + service account
  with domain-wide delegation) is FEASIBLE but deferred — manual mailbox creation in the Workspace
  admin console is the easy path for a handful of branches.

---

## 49. CHAT SUPPORT + LEAD-GEN ENGINE — PLAN (Jul 26, 2026; building next)

**Working rule (user-set):** keep THIS doc updated *simultaneously* with the work — it is the
cross-session "project brain" (context + plans + open decisions + todos). A new session should
read it and know exactly where we are and what's next. Also parked: **Google Workspace / email**
(resume ~Jul 27; MX/domain already live — remaining is per-branch mailboxes + optional
send-from-info@ upgrade).

**Vision (user):** evolve the increment-1–3 support widget into a proper **chat support + lead
generation engine** — greets + guides visitors, bilingual (EN/HI/Hinglish, asks preferred
language), never misses a lead (out-of-hours fallback capture), realtime, and secure/anti-spam.
Ops assigns support reps on a duty roster; they're alerted on all channels during office hours,
and get ticket-number notifications after hours.

**Phased plan (S1–S5):**
- **S1 — realtime + language + greeting:** widget polls the thread while open (~4s) so staff
  replies appear without refresh (ops drawer polls too). First-open **preferred-language picker**
  (EN / हिंदी / Hinglish) stored on the thread; AI + greeting in that language. Proactive greeting
  with quick-action buttons (Check my claim / See plans / Talk to a human) to guide visitors.
- **S2 — business hours + lead-capture fallback:** super-admin-configurable hours (default Mon–Fri
  10–6 IST). Out-of-hours (or human unavailable) → widget shows a "leave your details" form
  (name + email/mobile + message) → creates a ticket with a **ticket number**; ONE submission per
  browser (localStorage + server rate-limit). Lead = name + contact captured on the thread.
- **S3 — support-rep duty roster + routing:** super-admin assigns staff as support reps for a date
  range (days/weeks/months). New chat/escalation during office hours → alert on-duty reps on ALL
  channels (Telegram + web bell + PWA push). After hours → ticket created, reps get the
  ticket-number notification (async).
- **S4 — hardening (security/anomaly/spam):** per-IP + per-thread rate limits, message-length +
  messages-per-thread caps, honeypot / min-interval bot check, block abusive IPs (reuse
  `is_ip_blocked`), spam heuristic; escalate-safe. (Baked in from S1 onward.)
- **S5 — AI correctness/validation:** expand + verify the knowledge base to cover the ENTIRE
  business structure accurately; **user reviews/approves the KB draft** (this is where "validated
  and correct" is enforced); strict prompt + escalate-when-unsure guardrails.

**Decisions (CONFIRMED by user Jul 26):**
1. Office-hours alert trigger = **only on human-needed / lead** (AI handles routine silently; reps
   pinged on escalation / human request / details left). Low noise.
2. Lead destination = **support ticket in ops** (thread → ticket w/ name+contact in Support inbox;
   'convert to Nidaan lead/account' can come later).
3. Business hours = **super-admin editable** in ops (default Mon–Fri 10–6 IST).
Realtime = **polling** (~4s while a chat is open; simple/reliable through Cloudflare).

**Build status:**
- **S1 SHIPPED + verified (Jul 26):** widget polls `GET /support/thread?after_id=` (~4s while open,
  dedup by msg_id) → staff replies appear live without refresh; preferred-language picker
  (EN/हिंदी/Hinglish) stored on the thread; greeting + quick-reply chips; `nidaan_support_reply(lang)`.
  Verified: Hinglish reply, poll delta returns only new staff msg.
- **S2 SHIPPED + verified (Jul 26):** super-admin-editable support hours (IST) in ops → Support
  (days + start/end; default Mon–Fri 10–6); `is_within_business_hours()`. Public GET `/support/status`.
  Widget shows an offline note + "Leave my details" form (name + email/mobile) → POST `/support/lead`
  → ticket #; one submission per browser (localStorage) + 4/hr/IP. "Talk to a human" routes to the
  form when offline. Lead = escalated thread w/ contact → ops inbox + admin alert. Verified end-to-end.
- **Anti-hallucination hardening SHIPPED + verified (Jul 26, per user ask):** AI prompt grounded to
  the KB only (no guessing; unsure → point to page/human); canonical WHERE-TO-GUIDE links; "guide,
  don't loop" rule. Server loop guard: repeated question or ≥6 customer turns → force human handoff.
  Widget linkifies URLs + /nidaan paths. Verified: weather Q refused (no hallucination), "how to
  submit" returned /nidaan/start, repeated Q escalated.
- **S3 SHIPPED + verified (Jul 26):** duty roster `nidaan_support_reps` (staff + date range);
  super-admin assigns in ops → Support (dropdown + From/To; on-duty vs scheduled + remove).
  `on_support_escalated` routes to ON-DUTY reps (fallback = all admins so nothing is missed) on
  bell + push + email + Telegram. In-hours = "reply now"; after-hours = "ticket #N, follow up".
  Verified: on_duty resolution, after-hours framing, routing.
- **Context separation SHIPPED + verified (Jul 26, user ask):** homepage chat = **guide/lead-gen**
  mode (anonymous — refuses account/subscription/status/doc questions, redirects to login/dashboard,
  NEVER sends the customer token or exposes account data); dashboard chat = **support** mode
  (logged-in — account-aware from a minimal CUSTOMER CONTEXT name/plan/active). Mode derived from a
  valid Nidaan token server-side; threads namespaced per mode in the widget. Verified both paths.
- **S4 SHIPPED + verified (Jul 26):** anti-spam/anomaly hardening — IP-block gate
  (`auth.is_ip_blocked`) on /support/message + /support/lead; honeypot field `hp` (bots fill →
  `record_failed_login` + benign no-op, so repeat offenders auto-block); per-thread flood cap (80
  msgs → 429); existing per-IP limits (20/min chat, 4/hr lead) retained. Cloudflare edge is the 1st
  line. Verified: honeypot made no thread, normal chat unaffected.
- **S5 (LAST phase, needs USER APPROVAL):** expand the AI knowledge base (`_NIDAAN_SUPPORT_KB` in
  biz_ai.py) to cover the ENTIRE business accurately; the user reviews/edits before it's the source
  of truth. This is where "AI answers validated & correct" is enforced. NOT auto-shipped — draft →
  user approves → deploy.

- **S5 SHIPPED + verified (Jul 27):** KB finalized from the owner's confirmed answers. Facts now
  encoded: covers ANY insurance (health/life/travel/auto/…); we sell the expert REVIEW (go/no-go),
  NEVER a guarantee/promise (hard rule). Two audiences — policyholders (worth-fighting opinion) +
  advisor/agent subscribers (offload disputes, focus on selling → cross/upsell). ₹499 review 48–72
  business hrs; "can be fought" → legal team takes it forward, status on dashboard/chat; success fee
  only after resolution (case-by-case); refund window = 2 HOURS then non-refundable (plan refunds →
  human). Persona = warm customer-service + sales rep. Verified: no-guarantee, all insurance types,
  refund policy.

**ENGINE COMPLETE (S1–S5 + anti-hallucination + guide/support separation) — all SHIPPED + verified.**

## 50. L2 LEGAL PORTAL INTEGRATION — PLANNED (surfaced Jul 27)

When a claim is marked **"can be fought"** in NidaanPartner (L1) ops, it must transfer to the **L2
legal portal** (likely **Nidaanlegalindia.com** — user to confirm) where all L2 claims data +
legal process flow live. Need a secure integration (API or equivalent) that: (a) pushes an
accepted claim from L1 → L2, and (b) pulls **customer-facing status updates** from L2 back so the
customer sees them on their nidaanpartner.com **dashboard** and can ask about status via **chat
support**. This extends the earlier L1↔L2 sync idea (see memory `project_nidaan_legal_api`).
**Owner answers (Jul 27):** L2 portal = **https://claimshield.in/** (NOT Nidaanlegalindia.com).
It is **built + ours**, but a **separate portal / different architecture**; for anything we
strictly need, we'll ask the L2 team to add it, and handle the rest on our side. **We POLL
everything** (no inbound webhook from L2). Customer-facing status **stages come from the L2 portal
+ its comments** (mirror what L2 exposes). → Integration = push an accepted claim L1→L2, then poll
claimshield.in for status + customer-safe comments and surface them on the L1 dashboard + chat.

## 51. CONTENT CONSISTENCY — ANTI-DRIFT (owner: "Both — guard now + config next")

Problem (owner-raised): a business fact lives in many places (homepage EN+HI, About, FAQ, chat KB)
so a change gets missed somewhere. Decision: **guard now + editable config next.**
- **Guard SHIPPED (Jul 27):** `_tools/content_guard.py` scans the LIVE marketing + chat surfaces
  (`nidaan_index.html`, `nidaan_about.html`, `biz_ai.py` KB) for RETIRED phrases (Ombudsman/लोकपाल,
  "IRDAI+Ombudsman", "5–6 months", "average/avg resolution", "औसत समाधान") and fails the build if
  any reappears. Wired into `.github/workflows/deploy.yml` as a **gating `content-guard` job**
  (deploy `needs: content-guard`). Extend by adding a (regex, reason) row to BANNED. Allowlist keeps
  the "IRDAI Reg. applicable" solicitation line.
- **Scope note:** `nidaan_ops.html` + `nidaan_dashboard.html` use "Ombudsman" as a FUNCTIONAL
  claim-status / workflow-stage label (a real filing forum) and `nidaan_index_sample.html` is a WIP
  preview — all intentionally OUT of the guard's scope for now.
- **NEXT (config):** migrate the ~10 canonical facts (jurisdictions, hours, fees, success-fee terms,
  resolution stance, track-record numbers) into a super-admin-editable content store (like Plans);
  the chat KB + those specific homepage spots read from it → change once, everywhere.
- **Open owner decisions:** (a) keep/remove the footer compliance line "Insurance is the subject
  matter of solicitation. IRDAI Reg. applicable."? (b) should FUNCTIONAL "Ombudsman" labels
  (dashboard status tracker, ops workflow stages) also switch to "competent authority", or stay as
  the specific forum name?

Cosmetic content update (Jul 27) SHIPPED: homepage/about/KB now say "competent authority",
jurisdictions = MP · Chhattisgarh · Maharashtra · Rajasthan · Punjab, and resolution = "early /
complexity-based" (stat card → "48–72 hrs / Review Turnaround"). Verified live.

## 52. SEGREGATED BACKLOG (owner brain-dump Jul 27 — organized into phases)

**CONTENT TRACK (building now):**
- **2a Content cleanup — SHIPPED + verified (Jul 27):** removed IRDA/IRDAI, DPDP, Lokpal, Ombudsman
  from LIVE customer-facing + functional surfaces → "competent authority" / "applicable
  data-protection law". Homepage footer solicitation line removed; dashboard claim-status label +
  ops workflow label switched (display text, internal keys kept); signup/claim DPDP badges reworded.
  Guard expanded (bans IRDA/IRDAI/DPDP/Lokpal/Ombudsman + resolution phrases; scans index/about/start
  + the Nidaan KB block only — Sarathi insurance-AI's legit IRDAI ref not flagged). Deploy is gated
  on the guard. STILL OPEN: `nidaan_index_sample.html` (WIP /preview — clean at promotion) and
  privacy.html/terms.html DPDP references (legal-compliance — separate owner decision).
- **2b Content config — SHIPPED + verified (Jul 27):** `nidaan_content` table + helpers (seed at
  startup; get/update/all/public_content, 30s TTL cache so edits propagate across the 2 web
  workers). 8 core facts: jurisdictions, support_hours, review_turnaround, success_fee,
  resolution_stance, refund_window, audience, go_no_go. Chat KB appends an AUTHORITATIVE FACTS block
  from the config (overrides prose). Ops **📝 Content** panel (super-admin edits EN/HI). Public
  `GET /nidaan/api/content`; homepage `[data-nc]` spans (jurisdictions) inject from it. Verified
  change-once: edit jurisdictions → public API + chat facts block both reflect it. To extend
  coverage, mark more homepage spots with `data-nc="<key>"`.

**CHAT ENGINE:**
- **S6 Chat intent + language switcher — SHIPPED + verified (Jul 27):** always-available 🌐 switcher
  in the widget header (English/हिंदी/Hinglish); client detects a language request in a message
  ("in english", "hindi me", "change language", "hinglish") and switches + confirms warmly with NO
  AI round-trip (fixes the canned-welcome bug); AI backstop rule points to the 🌐 button. Widget v6.

**CONTENT CLEANUP EXTENSION (Jul 27, owner "change those too"):** cleaned the `_sample` WIP
(retired words → competent authority / complexity-based) + added it to the guard. privacy.html &
terms.html LEFT UNTOUCHED — they're **Sarathi-AI's** legal docs where DPDP-compliance citation is
correct/required (owner flagged; recommend keeping — removing weakens compliance).

**OPS / DATA-FLOW TRACK:**
- **1C-e Accounts:** add a **Branch Code** column (subscriber signup captures it) so each account
  shows which branch it came from.
- **1C-f All-Claims:** show **account + branch + other captured details** per claim; if feasible,
  a cleaner integrated Accounts+Claims view (only if it doesn't hamper existing function).
- **1C-g grounding (Jul 27):** the claims workflow LARGELY EXISTS — manual assign
  (`assign_claim_to_staff`), status flow, go/no-go delivery (`deliver_review`: can_fight/no_scope +
  findings), internal notes (`add_claim_note`) + customer messages. 1C-g = ENHANCE, not greenfield.
  Increments: **g.1 assignment auto/manual switch → g.2 go/no-go templates → g.3 L2 hand-off.**
  - **g.1 SHIPPED + verified (Jul 27):** super-admin toggle (ops Claims header 🟢/⚪ Auto-assign;
    GET/PATCH `/ops/api/claims-auto-assign`; default OFF). When ON, a newly submitted PAID/subscription
    claim (not an unpaid lead) auto-assigns to the **least-loaded handler** (fewest OPEN claims;
    stable ties), fire-and-forget, and the handler gets the same assignment email as a manual assign.
    Pool = active associates + sub-admins (fallback any active staff). Owner chose least-loaded.
  - **g.2 SHIPPED + verified (Jul 27):** `nidaan_review_templates` (outcome can_fight|no_scope,
    title, body, active; seeded 1 default each). Deliver-review form: choosing an outcome loads its
    templates into a picker → prefills the customer-facing findings (staff personalise). Ops 📝
    Content panel manages them (edit/add/deactivate/delete). Endpoints GET (staff) + CRUD (super_admin).
    Verified seed + CRUD round-trip.
  - **g.3 (BLOCKED on L2 API contract):** on a can_fight decision → push the claim to L2
    (claimshield.in). Needs the claimshield.in API details (push endpoint + status/comments poll +
    auth). Owner said "we poll everything" and will ask the L2 team for anything needed. Until the
    API contract is known, g.3 + the L2 integration (§50) are on hold.

REGRESSION FIXED (Jul 27): the attachment-delete change used `datetime` in the quick-task drawer GET
without a local import (sarathi_biz imports datetime per-function) → 500 "Failed to load quick task".
Added a local import; verified task #467 drawer loads (200). Lesson: sarathi_biz.py has NO module-level
`datetime` import — always `from datetime import datetime` locally.
- **(orig) 1C-g Claims workflow (subscription claims):** intimated → **assign to staff** (switch:
  auto/manual) → flow starts. Customer-facing comments + internal comments + tagging + notifications
  + **go/no-go templates** (can-fight / cannot-fight, predefined) + routing. End-to-end defined flow
  through the go/no-go decision and the handoff to L2 (claimshield.in). Similar to the office-task
  system but claim-specific with predefined options. Build without hampering existing functions.
- **1C-h Superadmin Branch Dashboard:** a dedicated dashboard inside the ops Branches section showing
  everything from branches — account subscriptions, branch-filed claims, walk-in customers the
  branch initiated, etc. (Complements the branch-facing portal already shipped.)

**L2 INTEGRATION (answers in — see §50):** poll-based sync with claimshield.in; push accepted
claims, poll status/comments → dashboard + chat.

Sequencing: content 2a → 2b, then S6 (chat intent), then ops 1C-e/f, then 1C-g (claims workflow,
the big one) + 1C-h (branch dashboard), then L2. Owner said: start with content-config phase 2.

## 53. TASK ATTACHMENTS — policy + delete (accommodated Jul 27, live case task #462)

Multi-file attach on task comments ALREADY worked end-to-end (UI `multiple`, sends `files[]`,
endpoint accepts a list). **Policy: ≤10 files per comment, 10 MB each.** The likely blocker in the
live case was **iPhone .heic** being outside the `accept` filter. SHIPPED:
- Broadened accepted formats (both create + comment inputs): pdf, jpg/jpeg, png, webp, **heic/heif**,
  doc/docx, xls/xlsx, **txt, csv**.
- **Attachment delete:** the UPLOADER can remove their own attachment within **1 hour**
  (`ATTACHMENT_DELETE_WINDOW_SEC=3600`); after that only an **admin (super/sub-super)** can.
  `delete_note_attachment()` + `DELETE /ops/api/quick-tasks/{qid}/attachments/{id}` (removes DB row +
  disk file + clears legacy note columns; audited). Drawer returns `attachment_id` + a per-attachment
  `deletable` flag; UI shows a × on removable attachments. Verified (route gated, logic sound).
Note: this delete-window pattern applies to task-comment attachments; the same policy can be
extended to other attachment surfaces (claim docs, review docs) if the owner wants it there too.

## 54. CLAIM TASK PANEL OVERHAUL → parity with quick-tasks (owner Jul 27)

Owner: the ops claim drawer is unstructured/messy vs the quick-tasks panel. Bring the best
quick-tasks collaboration features to claims + better routing. Current claim drawer = stacked
sections; claim internal notes are BASIC (no attachments, no delete, no @mention); assignment is
SINGLE-select; no read receipts/threads/watchers. Quick-tasks has all of that. This is a
multi-increment build (1C-g.4); sequence chosen for safety (a regression already hit this exact
note-render surface — the datetime import bug):
- **g.4a Attachment helper notes (SAFE, first):** show "Max 10 MB · PDF/JPG/PNG/HEIC/DOC/XLS…" near
  every attachment upload (ops task create + task comment + customer dashboard claim-doc upload +
  internal claim panel). Low-risk, explicitly requested.
- **g.4b Multi-select assignment** (2 parts, careful/additive):
  - **PART 1 SHIPPED + verified (Jul 27):** `nidaan_claim_assignees` (lazy-created) + helpers
    `set_claim_assignees` (primary=first, records all), `get_claim_assignees` (primary+extras),
    `is_claim_assignee` (primary OR extra). `assigned_to_staff_id` stays PRIMARY → zero behaviour
    change; nothing calls set_ yet. Verified: claims still load, set→revert clean.
  - **PART 2 SHIPPED + verified (Jul 27):** assign endpoint accepts `staff_ids` (keeps `staff_id`
    back-compat) → set_claim_assignees; emails all assignees. 4 access sites updated GRANT-ONLY
    (view + status-update + deliver-review use `is_claim_assignee`; list scope [pipeline counter +
    get_claims_ops] add `OR EXISTS(nidaan_claim_assignees)`). Claim detail returns `assignees`;
    checkbox multi-select UI (current assignees pre-checked). Verified LIVE: secondary assignee
    views claim (200), non-assignee blocked (403), claims list loads for all, assignees in detail
    [8,9], drawer 200 — clean revert. **g.4b DONE.**
- **g.4c Claim-note collaboration (the big one):** bring quick-tasks features to claim notes —
  attachments (multi, ≤10/10MB, +delete-within-1h/admin, §53 policy), @mention → participants +
  notifications, reply threads, read receipts, mute. Reuse the quick-task infra patterns.
- **g.4d UI restructure + routing:** reorganise the claim drawer into a clean, structured layout
  (status/assignees/timeline/notes/attachments), matching the quick-tasks panel's polish.
Owner said: keep g.3/L2 pending (blocked on claimshield.in API); build this as the next step.

**WORKING PRINCIPLE (owner Jul 27):** the software is mature/excellent — move SLOWLY, carefully,
systematically; be extra careful on high-sensitivity items; NOTHING breaks while building; additive
+ backward-compatible; preventive + security measures; test the exact live path. (See memory
`feedback_careful_no_break` — a datetime-import regression this session broke task loading.)

## 55. APP HEALTH "COCKPIT" — PLANNED (owner Jul 27; discuss scope)

Owner wants the ops **App Health** panel to become a technical cockpit so small issues can be handled
without a developer. **SUPER-ADMIN ONLY** (no other staff). Requested capabilities (to refine):
- Live metrics: request latency, load level, load spikes/alerts, DB size / disk-space warnings, table
  counts, error-rate; the existing health checks + timing middleware already feed some of this.
- Self-serve small fixes from the panel (e.g. restart a stuck watchdog, clear a cache, re-run a
  migration/seed, toggle a flag) — carefully scoped, audited, reversible.
- **Data export to CSV** (per-table or a selected set) for the owner.
- Overall "cockpit" view: everything important at a glance + safe one-click actions.
Notes: this is a SENSITIVE surface (server internals + data export) → build additively, super-admin
gate + audit every action, no destructive one-clicks without confirm.

**STATUS (Jul 30-31): Increment 1 (read-only metrics) DONE + verified.** The App Health control center
already had service checks (DB/email/payments/Telegram/WhatsApp/disk/errors). Added the read-only host
metrics the owner named: request latency (p50/p95/avg/max via a timing ring), system load (1m/5m/15m vs
CPU → spike coloring), memory %, disk %, DB file size, uptime — /nidaan/ops/api/health + a 🖥️ System row.
Verified live (load 0.11, DB 9.2MB, mem 5.2%, disk 2%, p95 458ms). Super-admin only, no side effects.

**CSV export — DONE (owner Jul 31, deployed + verified).** GET /nidaan/ops/api/export/{table}.csv
(super-admin only) for whitelist: claims / accounts / branches / tasks (nidaan_quick_tasks non-deleted).
Owner chose FULL details (their own business data). Columns auto-discovered via PRAGMA with sensitive
ones excluded (password/hash/token/secret/otp/hmac/thread_key) — verified accounts export has NO
password_hash. Row-capped 100k, every export _ops_audit'd. UI: 'Data Export (CSV)' buttons + exportCSV()
blob download. Verified: 401 unauth; claims/accounts/branches/tasks all 200 with data, no sensitive cols.

**Load-spike alerts — DONE (Jul 31, deployed + smoke-tested).** run_health_alert_sweep()
(biz_nidaan_notifications) via worker loop health_alert_loop (every 10 min): disk ≥90%, 1-min load >
2×CPU, memory ≥92% → super-admins on bell+email+Telegram, per-condition 6h cooldown. Smoke: healthy→0,
disk96%→1, cooldown→0. Live on server.

**Self-serve fixes — DONE (owner approved all examples, Jul 31, deployed + verified).** POST
/nidaan/ops/api/health/action (super-admin) with a STRICT allow-list: reseed (idempotent seeds),
clear_cache (invalidate+re-read content/plans), wa_watchdog (run one run_wa_watchdog_cycle),
toggle_wa_pause (flip wa_automation_paused; GET /health/flags shows state). Each confirm-gated + audited;
NO arbitrary shell/service control (verified: 'rm -rf' → 400). UI: '🛠️ Self-serve fixes' buttons.
Live test: 401 unauth; reseed/clear_cache/wa_watchdog 200; WA-pause flip+restore (prod unchanged);
bad action 400. **App Health cockpit COMPLETE** (metrics + CSV export + alerts + self-serve).

**App-separation Phase 2 — DECLINED by owner (Jul 31):** no separation; keep the single app as-is to
avoid any pre-launch risk. (§59 plan stays as reference only; not to be executed.)

## 61. NIDAAN "LISTEN" WALKTHROUGH + SARATHI WHATSAPP/EVOLUTION (owner Jul 31)

**A. Nidaan homepage "Listen" walkthrough — DONE (deployed + verified).** Clicking Listen (or the
auto-popup) now shows a chooser: 🧑‍💼 advisor → plays the recorded audio (/uploads/photos/walkthrough/
for-advisors.mp3, deployed to server); 🙋 policyholder → the automated Hindi/English TTS voice with a
REWRITTEN retail-only script (₹499 one-time review; all advisor/professional/Sarathi-portal lines
removed). Auto-popup no longer auto-plays — waits for the choice. (nidaan_index.html; content_guard clean.)

**B. Sarathi WhatsApp — DIAGNOSIS + partial fix (Jul 31).** Evolution API ("scan QR → connected") is
FULLY WORKING: configured in biz.env (server 5.223.64.25:8080), reachable (HTTP 200), integration
enabled, 7 instances exist (incl. sarathi_t9/t27, currently 'close' = just need re-scan). The Sarathi
QR-scan connect UI already exists (dashboard.html step 3). The APK "Sarathi Agent" section is ALREADY
ABSENT from the dashboard HTML (only dead JS functions remain, no HTML elements) — removed the leftover
apkLoadStatus() call.
  - **QR-freeze — DONE (deployed):** setup takes ~10s (Evolution delete+create+sleep(8)+connect); impatient
    users tapped Generate repeatedly → concurrent setups → QR never stabilised. Now a blocking
    'Generating your QR code…' overlay appears instantly on submit (prevents 2nd setup), auto-hides on QR
    display / failure, 25s safety net. This likely fixes BOTH the UX and the 'QR not generating' (root
    cause = concurrent setups). Owner to test.
  - **QR NOT GENERATING — ROOT CAUSE = Evolution server, NOT the Sarathi app (diagnosed Jul 31).**
    Live diag against 5.223.64.25:8080: instance CREATES fine but NO QR ever produced — connect returns
    only {"count":N} (no base64/code), instance stuck 'connecting', never 'open'; same WITH and WITHOUT
    proxy (proxy is OFF — proxy_config False). All 7 instances close/connecting, none open. ⇒ the
    Evolution/Baileys server cannot complete the WhatsApp handshake — WhatsApp is refusing to issue a
    QR/pairing code to that datacenter IP (also why pairing code 'never worked'). 'Worked earlier' = before
    the IP got flagged. FIX is on the Evolution box (owner input needed): (a) restart the Evolution/Baileys
    service/container; (b) configure a working RESIDENTIAL proxy (WA_PROXY_HOST/PORT/... → the parked iProxy
    item) so WhatsApp accepts the handshake; (c) if the server IP is banned, rotate it. Sarathi app code +
    integration are correct — no app change fixes this. Need: who manages 5.223.64.25 + can we access it?
  - **UPDATE Jul 31 (deep-dived on the Evolution box — I HAVE ssh: `ssh -i ~/.ssh/id_ed25519 root@5.223.64.25`):**
    runs `atendai/evolution-api:v2.2.3` + redis/pg (docker compose at `/opt/evolution`). Findings:
    (1) **FIXED** — WA-Web version was STALE: `CONFIG_SESSION_PHONE_VERSION` `2.3000.1035194821` → updated to
    current `2.3000.1043857760` in docker-compose.yml + internal.env (backups `.wabak.*`), recreated container
    (running, version confirmed applied). (2) Old instances carry a STALE per-instance webhook =
    `http://127.0.0.1:8090` (dead — from when the app ran on the same box) → their events (incl. QR) go nowhere,
    flooding logs with ECONNREFUSED. Fresh instances use the correct sarathi-ai.com webhook (verified reachable
    → HTTP 401 = needs token, so delivery path works). (3) **STILL BROKEN after the version fix** — a FRESH
    instance still won't emit a QR (stuck 'connecting', zero QRCODE in logs); Baileys isn't completing the
    WhatsApp handshake at all. ⇒ remaining fix is a BIGGER infra decision (owner call, do NOT do blind
    pre-launch): (a) **upgrade Evolution from v2.2.3 → latest** (its bundled Baileys is too old for current
    WhatsApp — most likely fix; but major-version = DB-migration risk to the whole WA server incl. Nidaan
    numbers); (b) add a **residential proxy** (parked iProxy) via `WA_PROXY_*` so WhatsApp accepts the
    datacenter-IP handshake; (c) I can clean up the stale 127.0.0.1:8090 webhooks on old instances anytime.
  - **★ ROOT CAUSE CONFIRMED Jul 31 — LOST RESIDENTIAL-PROXY BINDING (not version, not app):** the box
    already runs a working residential proxy — `gost-wa.service` (SOCKS5 `127.0.0.1:1080` → upstream
    `http://res.proxy-seller.io:10000`, creds embedded), exit IP `117.254.111.158` (residential, verified).
    But the `Proxy` table in Evolution's postgres is EMPTY for all 7 instances → every instance connects to
    WhatsApp from the raw Hetzner datacenter IP → WhatsApp refuses to issue a QR → stuck 'connecting' forever
    (same for pairing code). **PROVEN:** inserting a Proxy row (host=res.proxy-seller.io port=10000 proto=http
    user/pass from gost) directly in the DB + restarting the instance → QR base64 (len 10694) generated on the
    FIRST connect attempt, log 'Proxy enabled: res.proxy-seller.io'. ⇒ the fix is re-binding the proxy, NOT an
    upgrade. **BUT v2.2.3's proxy API is broken:** nested `proxy` in /instance/create = silently ignored;
    flat `proxyHost` in create = hangs (HTTP 000); `/proxy/set/{inst}` = hangs (HTTP 000). Only a DIRECT DB
    write applies the proxy on v2.2.3. So options: (a) low-risk — apply proxy via DB (works today, no upgrade)
    e.g. a postgres AFTER-INSERT trigger on "Instance" that auto-adds the Proxy row, so the app's existing
    delete→create→connect flow just works; (b) upgrade Evolution so the app's clean proxy code (create payload
    / proxy-set) works as designed (user approved, but major-version risk on shared DB). App code is fine:
    biz_whatsapp_evolution.create_instance already embeds `payload["proxy"]=proxy_config()` from biz.env
    WA_PROXY_* (currently UNSET) — v2.2.3 just ignores it. Verified proxy creds live in gost unit
    /etc/systemd/system/gost-wa.service. NOTE: also to do — remove Nidaan official WA instances (Telegram-only
    now, user 31 Jul); keep Sarathi-only.
  - **★★ HARD WALL FOUND Jul 31 (exhaustive) — v2.2.3 CANNOT apply a proxy to a RUNTIME-created
    instance:** tested every path against a fresh instance — nested `proxy` in create = ignored; flat
    `proxyHost` in create = hang(000); `/proxy/set` = hang(000, not stored); `/instance/restart` after a
    DB-inserted/trigger Proxy row = does NOT reload proxy ("Proxy enabled" never logs); `logout`+`connect` =
    does NOT reload either. The ONLY path that loads the proxy into a live socket is a FULL CONTAINER RESTART
    (instances loaded from DB at boot log "Proxy enabled" — confirmed for sarathi_t9/t27/goluq after a
    `docker compose restart`). The residential proxy is ALIVE (gost socks5 127.0.0.1:1080 → res.proxy-seller.io,
    exit IP 117.254.111.158, verified via curl). The 2 early isolated QR successes (proxy_test, diag_dec)
    coincided with container-load timing; they do NOT reproduce for the real subscriber flow (runtime create
    → restart → connect). ⇒ the low-risk trigger fix ALONE is insufficient for live use. Current box state:
    ALL instances deleted (clean slate — Sarathi ones were dead/needed re-scan anyway), Nidaan removed, DB
    backed up (/opt/evolution/evolution-db-backup-*.sql.gz), trigger `trg_auto_bind_wa_proxy` still installed
    (MUST DROP before any upgrade — it could fail inserts if the new schema differs). ⇒ RIGHT fix now =
    UPGRADE Evolution (user's original choice) — and it's now LOW risk because there's nothing live to lose
    (clean slate + DB backup + rollback). Alt = transparent network proxy (redsocks/iptables → gost) so all
    container :443 egress uses residential without any Evolution proxy config (sidesteps the bug; but infra
    surgery). App changes made locally but NOT deployed: set_instance_proxy→restart (revisit post-upgrade —
    newer /proxy/set may work), sarathi_biz connect loop range 5→9, dashboard QR-freeze 25s→55s + "~30s" copy.
  - **PARKED Jul 31 (user: "move on", don't over-spend on WA):** Evolution UPGRADED v2.2.3 →
    `evoapicloud/evolution-api:v2.3.7` (image switched in /opt/evolution/docker-compose.yml; Prisma
    migrations applied cleanly; container healthy). Box is a CLEAN SLATE (no live instances; Nidaan removed;
    proxy trigger DROPPED; DB backup at /opt/evolution/evolution-db-backup-20260731-091717.sql.gz; compose
    backups .preupgrade.* / .wabak.*). Whether v2.3.7 fixes the runtime-proxy→QR was left UNVERIFIED (a final
    background test was mid-run when we parked). Local app changes made but NOT committed/deployed (live app
    still runs old code): biz_whatsapp_evolution.set_instance_proxy→restart (revisit — on v2.3.7 the ORIGINAL
    /proxy/set may work again, in which case revert to /proxy/set + set biz.env WA_PROXY_*), sarathi_biz.py
    connect-loop range 5→9, dashboard.html QR-freeze 25s→55s + "~30s" copy. **PLAN B (user-preferred if WA
    still flaky): mobile phone as server/proxy** — a real phone on mobile-data (real device + carrier IP) is
    the most ban-resistant path (≈ the APK-Bridge biz_wa_agent.py). **To resume:** (1) run one test — create
    instance on v2.3.7 with proxy (nested-create OR /proxy/set) → does QR generate through res.proxy-seller.io?
    (2) if yes: wire app proxy (biz.env WA_PROXY_HOST=res.proxy-seller.io PORT=10000 PROTOCOL=http USER/PASS
    from gost unit) + deploy + verify; (3) if no: `docker compose` rollback image to atendai v2.2.3 + restore
    DB backup, then build phone-as-proxy. Proxy creds live in /etc/systemd/system/gost-wa.service (gost
    socks5 127.0.0.1:1080 → res.proxy-seller.io:10000).
  - **★ VERDICT Jul 31 — v2.3.7 did NOT fix it; PIVOT to phone-as-proxy (per user):** on the upgraded
    v2.3.7, `/proxy/set` STILL HANGS (HTTP 000 after 25s), and proxy-write/create ops hang while API GETs
    are instant (fetchInstances http=200 in 0.03s, box healthy: load ~2.2, 2.9GB free). So the proxy-apply
    hang persists across versions. Likely reason: Evolution synchronously tries to reach the proxy's DIRECT
    endpoint `res.proxy-seller.io:10000`, which is NOT directly reachable from the box (curl direct = http=000)
    — only gost's local tunnel works (socks5 127.0.0.1:1080 → upstream, exit 117.254.111.158, verified). The 2
    early QR successes were flukes/timing. **CONCLUSION: stop chasing Evolution+proxy (user: don't over-spend).
    Pivot to PLAN B = mobile phone as server/proxy** (real device + carrier IP; ≈ APK-Bridge biz_wa_agent.py)
    — most ban-resistant + sidesteps all datacenter-IP/proxy issues. **State left:** Evolution on v2.3.7
    (healthy, kept as baseline — NOT rolled back; clean migration), box clean (only 1 harmless dead test
    instance v37q), live app UNCHANGED (my local app edits never deployed → no regression; WA connect for
    subscribers is still non-functional, same as before this session — no worse). **Possible future micro-avenue
    (if ever revisiting Evolution):** point the instance proxy at gost via the docker bridge (host-gateway:1080
    socks5) instead of the direct upstream, since gost works where direct fails — but needs bridge/UFW wiring;
    NOT pursued per user. **Parked local edits (set_instance_proxy→restart, sarathi_biz connect-loop range 5→9,
    dashboard QR-freeze 25s→55s) were REVERTED Aug 2 2026** — we pivoted to the official Meta Cloud API, so the
    Evolution path is abandoned and the working tree is clean (nothing Evolution left uncommitted).

  - **★ NIDAAN OPS — LEAVE HISTORY report ADDED Aug 2 2026 (deployed).** New super-admin-only nav item
    "🌴 Leave History" (`panel-leavehistory`) in nidaan_ops.html. Backend: `biz_nidaan.list_leave_history()`
    (date-range overlap + staff/status/kind filters) + `GET /nidaan/ops/api/leave/history` (super_admin only;
    returns rows with computed `days` [half=0.5] + per-staff APPROVED-day totals). UI: date presets
    (week/month/last-month/3mo/year) + custom From–To, staff/type(Leave|WFH)/status filters, per-staff totals
    cards, detailed table, and client-side CSV export (14 cols, Excel-safe BOM). Purely additive — existing
    leave apply/approve/tiles flow untouched.

  - **★ NIDAAN CLAIMS IMPROVEMENTS — 9-item plan (Aug 2 2026, phased; discussed + decisions locked).**
    Decisions: (2) claim emails FROM info@nidaanpartner.com + copy to nidaanpartner@gmail.com, keep individual
    admins' emails; (1) email template = clean LIGHT card made dark-mode-safe (fixes Gmail dark-mode inversion
    that washed out dark text — root cause: `_wrap_nidaan_template` light card + inline dark text, Gmail darkens
    card only); (5) claim panel = consolidate the two task widgets (🗂️Tasks +Add Task / 📌Reminders +Quick Task)
    into ONE; (8) reassignment (tasks+claims) open to ALL staff, fully audited. **PHASES:** A=notifications+email
    (items 1,2 + audit that assigned+involved staff get email+WhatsApp+dashboard on filed/assigned/status/note);
    B=claim panel reorg (item 4: Info→Advisor→Assign→Internal notes→Documents→Messages-with-subscriber[+attach]
    →Follow-up→Deliver assessment→Status history) + consolidate task widgets (5); C=claim intake+payment (item 6:
    mobile 10-digit + MANDATORY rejection-letter attach; item 7: drop branch code from claim form, capture
    Name+Mobile[mandatory,10-digit]/Email+Branch[optional] BEFORE Razorpay for Silver/Gold/Platinum, + FIX the
    grayed-submit-needs-refresh bug on raise-another-claim); D=claims dashboard role-based stats (item 3) +
    reassign-for-all (8); E=ClaimShield integration (item 9). **Known code:** email in biz_email.py
    (send_nidaan_new_claim_admin_email MISSING from_name="Nidaan Partner" → wrong Sarathi sender; wrapper
    _wrap_nidaan_template line ~279); claim notifs via biz_nidaan_notifications.on_claim_filed dispatch();
    claim drawer static/nidaan_ops.html openClaimDrawer():3413; reassign gates sarathi_biz.py:5832(quick-task)
    +:6452(task) "admin/SA only"; claims list loadClaims():3202. **Item 9 ClaimShield API assessment:** basic
    create(partnercreatecase→caseReferenceNumber)+status(partnercasestatus) is enough to START, but ASK them for:
    🔴 HTTPS (endpoint is http:// — API key + patient PII over plaintext = insecure), full status vocabulary,
    webhook/callback (vs poll), extra create fields (insurer/policy/type/rejection-letter/our-claim-ref),
    idempotency. API key part-1 received (store in biz.env, NOT chat); part-2 to come out-of-band.
  - **PROGRESS (Aug 2 2026): Phases A + B ALL SHIPPED & verified live.** A=email readable + FROM
    info@nidaanpartner.com + copy nidaanpartner@gmail.com + assign-notif on email/dashboard/telegram
    (on_claim_assigned). B1=claim drawer reordered + task/reminder widgets consolidated. B2=file attachments
    on subscriber↔ops claim messages (nidaan_messages.attachment_doc_id + save_claim_document + signed URL;
    endpoints now multipart; both UIs have 📎). B3=INVOLVED staff + MUTE (new nidaan_claim_watchers table +
    add/list/mute helpers in biz_nidaan; @mention in a claim note persists a watcher; watchers notified on
    messages/notes via biz_nidaan_notifications.notify_claim_watchers [dashboard+telegram, skips actor,
    per-message email omitted]; endpoints GET /claims/{id}/watchers + POST /claims/{id}/mute; drawer '👥
    Involved' section + Mute-me toggle). **Item 3 (claims dashboard) DROPPED — already covered by the Overview
    panel** (role-scoped: All/My Active Claims + stat strip + widgets), building a 2nd = duplication. **REMAINING:
    Phase C (items 6,7: claim intake 10-digit mobile + MANDATORY rejection-letter attach; drop branch code from
    claim form; capture Name+Mobile[mandatory 10-digit]/Email+Branch[optional] BEFORE Razorpay Silver/Gold/
    Platinum; FIX grayed-submit-needs-refresh bug on raise-another-claim) → Phase D (item 8 only: reassign for
    ALL staff, audited — gates at sarathi_biz.py:5832 quick-task, :6452 task, + claim assign gate
    _require_staff sub_super_admin at ops_assign_claim) → Phase E (ClaimShield, blocked on externals).
  - **★ DONE (Aug 2 2026): items 1-8 ALL SHIPPED & verified live.** Overview claims stats restyled to the
    "My Focus" tile look. C1: claim form 10-digit mobile + MANDATORY rejection-letter upload + branch code
    removed from the form (safe — ops attribution is account-level; per-claim branch_code was write-only) +
    grayed-submit bug fixed (re-enable on success + openModal). C2: pre-Razorpay confirm-and-capture step
    (POST /nidaan/api/subscribe/precapture saves name/mobile[req]/email/branch to the ACCOUNT, then the
    UNCHANGED doSubscribe/Razorpay runs; subscription plans only) — verified (bad phone 400, good 200,
    account updated). D (item 8): task + claim reassignment opened to ALL staff, fully audited — removed
    admin gates on quick-task reassign, task reassign (ops_task_assign), claim assign (ops_assign_claim now
    _require_staff base), + frontend (task-registry reassign, claim-drawer canAssign=true, leave-section
    reassign) — verified (team_member reassigned a claim → 200, was 403). **ONLY item 9 (ClaimShield) remains,
    BLOCKED on founder:** API key part-2 (out-of-band, into biz.env) + ClaimShield's answers on HTTPS endpoint
    (currently http://), full status vocabulary, webhook/callback, extra create fields (insurer/policy/type/
    rejection-letter/our-claim-ref), idempotency. See WHATSAPP_CLOUD_API_SETUP.md is unrelated;
    ClaimShield contract lives in this §. When ready: build biz_claimshield.py client + 2-way sync (L1↔L2).
  - **★★ NEW 3-ITEM BATCH (Aug 5 2026, phased, discuss-first, careful):**
    **(1) Razorpay SEPARATION — Nidaan gets its OWN Razorpay account (Sarathi keeps existing).** FOUNDER has
    OPENED the new Nidaan Razorpay account. FINDING: both products currently SHARE one account/keys —
    `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` in biz.env, read by biz_payments.py (Sarathi) AND
    biz_nidaan.py + sarathi_biz.py Nidaan paths (₹499 review sarathi_biz.py:1657; Nidaan subs
    biz_nidaan.ensure_nidaan_plans/create_nidaan_subscription; webhook biz_payments.py:460
    RAZORPAY_WEBHOOK_SECRET). PLAN: add NIDAAN_RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET; point ONLY Nidaan paths
    at them; Sarathi unchanged; re-seed Nidaan plans in new acct; webhook verify both secrets/route. CAVEAT:
    existing Nidaan auto-renew mandates stay on the shared acct until they lapse; new Nidaan subs → new acct/
    bank. Money path = careful/staged/test-mode first. (One Razorpay acct settles to ONE bank — can't split
    by product on one login; hence a separate acct. Razorpay Route rejected as overkill.)
    **(2) HOMEPAGE ENTRY GATE + dual experiences (nidaan_index.html).** On landing, an impressive entry gate:
    "Insurance Advisor/Consultant?" vs "Policy Holder?" → routes to a DEDICATED experience. ADVISOR page =
    subscription model only (REMOVE all ₹499 one-time-review content), advisor-benefit framing (happy customers,
    focus on sales not claims-support), advisor voice walkthrough. POLICYHOLDER page = ₹499 one-time review,
    FOMO for rejected/underpaid claims, "3-5 steps from your phone, Nidaan handles the rest." Both: voice
    concierge (HI/EN, text+voice), a small switch back to the gate/home. GROUND RULES apply: mobile-first,
    Tier-II/III clarity, TOTAL language conversion, content_guard clean, excellent/impressive design. NOTE:
    an advisor/policyholder chooser ALREADY exists inside the "Listen 2 minutes" walkthrough (nwPanel: advisor
    audio /uploads/photos/walkthrough/for-advisors.mp3 + policyholder retail TTS) — reuse/evolve, don't
    duplicate. Open Qs: gate on every visit vs remember choice; autoplay vs click-to-play voice; SEO/direct-nav.
    **(3) BRANCH claim → LEVEL-2 payment, CONFIGURABLE.** Branches (super-admin-managed, own dashboard) raise
    claims → Nidaan reviews → if GO-for-L2-legal, branch pays a fee (default ₹499) via the NEW Nidaan Razorpay
    to move the claim to L2; NO-GO = no charge. Must be CONFIG-DRIVEN (super-admin editable): fee amount +
    charge-policy (L2-only | all-claims | free), NOT hardcoded. Depends on (1) [new Razorpay] + relates to item
    9 ClaimShield [L2 = ClaimShield, blocked] — but the PAYMENT GATE + config + status can be built now,
    decoupled from the ClaimShield API call. SEQUENCE: item 1 (Razorpay split) first → item 3 (branch pay,
    needs new Razorpay) → item 2 (homepage, independent, can parallel). All privacy/security guardrails.
  - **★ PROGRESS Aug 5 2026:** **Item 1 SHIPPED (staged)** — Nidaan payment flows read NIDAAN_RAZORPAY_KEY_ID/
    SECRET/WEBHOOK_SECRET via `_nidaan_rzp_id()/_secret()/_webhook_secret()` (sarathi_biz.py) + biz_nidaan
    account-deletion, falling back to shared RAZORPAY_* until Nidaan keys added (27 reads range-scoped
    L1657-5302). FLIP-TIME: when founder adds NIDAAN_RAZORPAY_* to biz.env → clear cached/DB Nidaan plan IDs
    (_nidaan_plan_ids + nidaan_plans.razorpay_plan_id) so plans re-seed in the new account → test sub + ₹499
    in test mode → live keys. **Item 2 SHIPPED (LIVE)** — dual-experience homepage: entry gate (advisor vs
    policyholder, remembered in localStorage, ⇄ Change in nav) in nidaan_index.html (+ /preview sample kept in
    sync). Audience toggle body.aud-advisor/.aud-policyholder + .only-adv/.only-ph. Advisor: advisor hero +
    problem + how-it-works + For-Advisors + Plans + bundle + Sarathi-AI.com link on the gate card. Policyholder:
    ₹499 hero + shared (solution/about/stats/trust/testimonials/faq/CTA). Voice = reuse nwPanel walkthrough via
    Listen. Full HI/EN, mobile top-aligns+scrolls. All flows/links intact (verified). **Item 3 DESIGN LOCKED:**
    branch raises claim ON BEHALF OF a customer (branch=handler/payer, claim=customer's); pay PER-CLAIM at the
    GO-to-L2 gate via Nidaan Razorpay (immediate); post-pay status = "L2 — payment received, queued for legal"
    (ClaimShield handoff wired later, item 9). Config via ops-settings (get/set_ops_setting): branch_l2_fee
    (₹499), branch_charge_policy (l2_only|all_claims|free). Branches today = affiliates/referrers only (no
    claim-raise) → NEW capability. Decision point: nidaan_claims.review_outcome can_fight(GO)|no_scope(NOGO).
    SUB-PHASES: 3.1 config+super-admin UI (safe) → 3.2 branch claim-raise (branch dashboard) → 3.3 payment gate
    (Razorpay). Payment end-to-end test needs Item 1 flip (Nidaan keys).
  - **★ ITEM 3 COMPLETE — 3.3 SHIPPED Aug 6 2026 (commit pending push).** Branch L2 payment gate live:
    `biz_nidaan.branch_l2_pricing()` (reads branch_l2_fee/branch_charge_policy) + `mark_l2_paid()` (idempotent,
    guards origin='branch'+can_fight, sets l2_payment_status='paid'/l2_fee_paid/l2_payment_id/l2_paid_at, logs
    'l2_queued' — claim.status untouched, non-breaking). Endpoints (branch-bearer + host gated, scoped to owning
    branch): POST /nidaan/branch/api/claims/{id}/l2-pay (Razorpay order via _nidaan_rzp_* → new account),
    /l2-pay-verify (HMAC compare_digest, then mark_l2_paid + on_branch_l2_paid), /l2-advance (free-policy, no
    charge). GET /nidaan/branch/api/claims now also returns `l2` pricing. Branch UI (nidaan_branch.html): per-
    claim button — "Pay ₹{fee} → send to Level-2" (can_fight + charge_required) OR "Send to Level-2 (free)"
    (free policy) OR "Queued for legal ✓" (paid) OR "Reviewed: no scope"; Razorpay checkout loaded on demand.
    Notification on_branch_l2_paid → SA/Admin dashboard+email+Telegram. ClaimShield handoff still item 9.
  - **★ HOMEPAGE walkthrough per-version fix SHIPPED Aug 6 2026 (live+verified).** Voice walkthrough now jumps
    straight to the visitor's OWN version (advisor recorded audio OR policyholder HI/EN TTS) via saved
    `nidaanAudience` (nwShowSmart) instead of re-showing the both-options chooser; chooser only when no version
    picked. Applied to nidaan_index.html + _sample.html.
  - **★ RAZORPAY webhook SECRET wired Aug 6 2026 (DONE).** NIDAAN_RAZORPAY_WEBHOOK_SECRET added to server
    biz.env (600), confirmed loaded in process, verified renewals will pass signature. ⚠️ LESSON LOGGED
    (memory infra_bizenv_ownership): the mv-from-root-tmp write left biz.env root:root → app (User=sarathi)
    got PermissionError → both sites 502 ~2 min; fixed via chown sarathi:sarathi + restart. ALWAYS chown+health-
    curl after biz.env edits.
  - **★ OPS Level-2 visibility SHIPPED Aug 6 2026 (live).** nidaan_ops.html claim drawer shows a "Branch &
    Level-2" section for origin='branch' claims only (origin+branch code, review GO/no-scope, L2 status: Queued
    for legal ✓ +fee / Awaiting branch payment / L2 paid-at). Payload already had fields (SELECT c.*).
  - **★ SARATHI QA + NIDAAN OPS batch (Aug 7-8 2026).** SHIPPED: (a) Sarathi Phase A live fixes —
    /api/ai/voice-action pipeline_summary execute 500 (undefined `pipeline`/`stage_labels`) fixed; dashboard
    openLeadDetail() defined (was called by task "👁️ Lead" btn, never defined); voice execute path now handles
    non-JSON/500 gracefully. (b) Nidaan #1/#2 — branch-raised claims now appear + identifiable in ops all-claims:
    get_claims_ops was `SELECT c.*, a.branch_code` (blank house-account code clobbered claim's) → fixed to
    COALESCE(NULLIF(c.branch_code,''),a.branch_code) in SELECT + branch filter; ops list shows "🏢 Branch <code>
    — raised on behalf". NOTE: auto-deploy LAGGED for commit 5ed4bb9 → had to `git reset --hard origin/master`
    + rolling-restart manually on server (watch future pushes; see [[infra_bizenv_ownership]] deploy pattern).
    ALSO SHIPPED Aug 8: #6 uppercase name normalization (data-layer _capname in create_account/submit_claim/
    create_review_signup/record_payment_link + as-you-type on inputs); #4 tiered review fee (config-driven
    review_fee_low/high/threshold in ops-settings, review_fee_for(), charge points claim /pay + review pay flows
    + create_review_signup, nidaan_claims.review_fee_paid col, ops drawer "credited toward legal" on GO,
    super-admin "💵 Review Fee" editor PUT /nidaan/ops/api/review-fee, public /nidaan/api/review-fee-config).
    SCALING (Aug 8): SQLite WAL already active on live DB (journal_mode=wal, synchronous=NORMAL, busy_timeout
    5000 in init_db) → concurrent readers don't block writer; solid for launch+growth. Postgres = PLANNED
    staged migration LATER (abstraction→test on copy→cutover+rollback), only when monitoring shows limits —
    NOT now (real dialect/data-migration risk; my earlier "no rewrite" was oversimplified). GST DECISIONS
    (Aug 8): not yet GST-registered (applied) → build GST-READY, super-admin on/off + manual override, else
    automated STATE-WISE calc (CGST+SGST intra vs IGST inter, 18%); pricing = GST-EXCLUSIVE (add on top, e.g.
    ₹499+18%); collect customer STATE at payment (in our forms); show base+GST breakup everywhere + GST-
    compliant receipt; Razorpay does NOT compute output GST (gateway only). Build GST right AFTER #3.
    ★ GST SHIPPED + ENABLED LIVE Aug 8 2026 (gst_enabled=1, rate 18, exclusive). charge_with_gst()+record_gst()
    +nidaan_gst_ledger. Applied at ALL charge points: review (claim /pay + both review pays), subscribe one-time
    order, recurring autopay (GST-VERSIONED plan tag _gst18 → existing mandates grandfathered), branch L2 (pay+
    link), admin/branch payment links. Dashboard pay gate shows base+GST + "incl. ₹X GST". Panel: Ops→Workflow
    Settings→🧾 GST + PUT /nidaan/ops/api/gst + public /nidaan/api/gst-config. FAST-FOLLOWS: customer STATE capture
    (home_state blank→flat GST + store state for CGST/SGST vs IGST later), formal GST tax-invoice/receipt, per-
    recurring-CYCLE ledger (records initial only for now). COMPLIANCE: not yet GST-registered (applied) — collect
    now + remit later per founder; on/off toggle pauses instantly.
    ★ 9-ITEM BATCH SHIPPED Aug 8 2026 (all live): #1 Razorpay Instant Settlement = GUIDANCE (founder enables in
    Razorpay dashboard). #2 GoLuQ credit added everywhere (Sarathi pages/emails footers, Nidaan site+email
    footer, Dushyant profile 'Founder GoLuQ.com Digital Consultant'); legal entity 'Sarathi-AI Business
    Technologies' KEPT for copyright/Terms-Privacy-operator/email-sender (founder chose). #3 payment-failure
    alerts: webhook payment.failed + subscription.halted → on_payment_failed() → all super-admins via must-ack
    red popup + email + Telegram + push (every failure type). #4 Recent Comments moved to top of Claims
    Dashboard. #5 prominent top search on Claims Dashboard. #6 advisor commission disclaimer = PERSISTENT
    bottom-of-dashboard note for SUBSCRIBERS (15% of Nidaan's 15%, ₹2L→₹1.5L→₹22,500→₹3,375 example; NOT in
    drawer — corrected). #7 L2 Claims nav (review_delivered+can_fight) + Archived nav (no_scope) via
    review_outcome filter on get_claims_ops; on_moved_to_l2() alerts SA+admins+assignees all channels. #8
    hero copy dropped 'Free'. #9 glowing eye-catching CTA chip ('your money is your right'). ALSO: policyholder
    'How it works' button pointed to only-adv #how-it-works (hidden) → fixed to #solution. GST pre-Razorpay
    breakup popup (Amount+GST=Total) on subscribe (recurring+one-time) since Razorpay shows only total.
    STILL TO BUILD (directions locked): #3 rename Overview→"Claims Dashboard" + operational widget + BIG
    consolidated-acknowledgement notifications (concerned = assignees+watchers+super-admins per my rec); #5
    staff-as-branch dual-role — auto referral code for EVERY staff, commission superadmin-adjustable for BOTH
    staff+branches, branch dashboard must show share AMOUNT (not just %), gamified "Your NidaanPartner Business"
    dashboard for staff+branches (psychological/motivational, nudge when stuck).
    Sarathi: Phase B QA audit (read-only) → C trial 15→7d → D subscription cockpit (Sarathi HAS a super-admin
    cockpit — confirmed by founder). Rule reaffirmed: QA audit must be read-only/non-breaking.
  - **★ PAYMENT LINKS SHIPPED Aug 6 2026 (live) — Razorpay Payment Links.** Table nidaan_payment_links.
    PHASE 1 (branch): L2 gate now has "Pay ₹499 now" OR "🔗 Share payment link" → POST
    /nidaan/branch/api/claims/{id}/l2-payment-link (3-day link bound to claim) → branch shares Copy/WhatsApp →
    customer pays → auto-queues L2. PHASE 2 (super-admin): Ops→Workflow Settings→🔗 Payment Links generator
    (purpose review499|subscription|custom + customer name/mobile/email + expiry) → POST/GET
    /nidaan/ops/api/payment-links (super_admin) → link+Copy+WhatsApp + live list. AUTO-GRANT on webhook
    `payment_link.paid` → _reconcile_admin_payment_link: create/find account by mobile
    (get_account_id_by_phone/create_account_by_admin) then review499→grant_admin_review_credit (paid ₹499
    per_claim), subscription→activate_from_order_payment (plink_id as order ref), custom→account only.
    REVENUE: get_revenue_stats adds total_custom_link_revenue (review499/subscription already counted via
    per_claim/subscription rows — no double count). ⚠ REQUIRES founder to add `payment_link.paid` (+ optionally
    payment_link.expired) event to the Razorpay webhook, else links don't auto-confirm. Live payment→grant flow
    NOT yet end-to-end tested (needs the webhook event + a real payment).
  - **★ PAYMENT FOOLPROOFING SHIPPED Aug 6 2026 (live).** ROOT CAUSE FOUND: webhook payment.captured only
    reconciled subscription orders (product='nidaan'); it IGNORED ₹499 claim orders (product='nidaan_claim_499')
    and branch_l2 → a captured payment with a lost client callback (UPI race/low internet) left the claim
    'unpaid_lead' forever (money in bank, review never started). Proven by founder's test claim #25: captured
    11:51 IST but DB paid_at 13:53 IST (~2h gap). FIX: (1) shared idempotent `_finalize_paid_claim()` (atomic
    UPDATE..WHERE payment_status!='paid' guard) used by /pay-verify + webhook + recovery; (2) webhook now
    reconciles nidaan_claim_499 (finalize) + nidaan_branch_l2 (mark_l2_paid+notify) server-side; (3) GET
    /nidaan/api/claims/{id}/pay-status (DB-first, else queries Razorpay bound order → finalize) — client
    recovery/poll; (4) dashboard payClaim: on dismiss/verify-fail/payment.failed → poll pay-status + show
    reassuring 'Confirming your payment…' overlay (never 'failed' to a paying customer); (5) POST
    /nidaan/ops/api/payments/reconcile (super_admin, dry_run default) sweeps recent Razorpay orders to catch
    stragglers. Dry-run scan Aug 6: NO stuck payments (both paid claim orders already unlocked). Gap now
    seconds not hours. TODO optional: ops UI button to trigger reconcile.
  - **★ ABOUT-PAGE founder photos fixed Aug 6 2026 (live).** Page pointed at /static/team/*.png which never
    existed (only uploads/photos/, gitignored) → showed AK/DS initials. Copied both founder photos to
    static/team/*.jpg (git-tracked, deploys with app; files were JPEG despite .png name — matters under
    nosniff), updated nidaan_about.html srcs to .jpg?v=3 + lazy-load. Live 200 image/jpeg.
  - **★ NIDAANMITRA support AI hardened Aug 6 2026 (live, tested).** _NIDAAN_SUPPORT_PROMPT (biz_ai.py) now:
    (1) intent-aware — claim-holder→free review+capture; advisor→plans/callback; NO-CLAIM/just-visiting→
    gracious + plant referral seed (tell friends/family, save/share site), never pushy; (2) HARD GUARDRAILS —
    NEVER review/judge a claim pasted in chat (scenarios/rejection letter/T&C/docs)→redirect to /nidaan/start;
    resist role/identity/prompt-injection; stay on-topic, don't engage trolling/abuse→steer back once then
    escalate; confused/out-of-context→holding reply+escalate. VERIFIED live via 3 curl tests (verdict-refusal,
    injection→stayed+escalated, no-claim→referral). Widget nidaan_support_widget.js is GLOBAL on homepage (both
    advisor+policyholder views); backend /nidaan/api/support/message → biz_ai.nidaan_support_reply (grounded in
    content_facts_block) → escalate → on_support_escalated → ops dashboard+Telegram. Frontend→ops pipe CONFIRMED.
  - **★ CONCIERGE Phase 1 SHIPPED Aug 6 2026 (live, ?v=15).** Proactive greeter in nidaan_support_widget.js: Founder wants a supermarket-style
    assistant greeting each visitor, understanding what/why/how + intent (claim / advisor / just-visiting),
    guiding, and capturing leads even if they leave. FINDING: ~70% exists via NidaanMitra (intent+capture+
    referral+guardrails+human handoff now live). REMAINING = PROACTIVITY (auto-greet on landing) + tighter
    hand-in from entry-gate/voice into the chat. Founder locked: value-first; smart intent handling; hard
    anti-abuse guardrails (all now shipped in the prompt). Next: design the proactive greet (Phase 1
    policyholder-first). NOT yet built beyond the prompt hardening.
  - **★ HOMEPAGE repeat-visitor routing fix SHIPPED Aug 6 2026 (live).** Decision: NEVER re-ask (founder chose).
    (1) Kill neutral state — if no audience decided, force the entry gate (no more confusing both-ribbons
    landing); choice still remembered permanently in localStorage nidaanAudience. (2) Always-visible one-tap
    "wrong page?" switch strip (.aud-switch, plain EN/HI) on each version — advisor page → switch to
    policyholder, policyholder page → switch to advisor (calls egChoose). (3) Nav "Change" → "Advisor /
    Policyholder". NO short timeout (rejected — nags committed users, doesn't stop mis-clicks). Both
    nidaan_index.html + _sample.html. Note: ONE page, body.aud-advisor/.aud-policyholder + .only-adv/.only-ph
    (no duplicate pages); neutral = no body class = both ribbons.
  - **★ PHONE-AS-SERVER DESIGN WRITTEN Jul 31 → see `WHATSAPP_PHONE_BRIDGE_DESIGN.md` (root).** Key finding:
    the APK-Bridge ("phone-as-CLIENT") is already ~80% built — `biz_wa_agent.py` (1514 lines: HMAC device
    auth, rate-limits, business-hours, takeover/quiet-if-manual, Gemini AI reply w/ policy+CRM context,
    conv logging), Android app `apk/` (~650 lines Kotlin: WANotificationService reads WA notifications +
    replies via RemoteInput, foreground keep-alive, boot auto-start, CRMWebSocketClient), tables
    wa_agent_devices/pending/conversations, endpoints /api/wa-agent/{connect,status,disconnect,settings,
    conversations} + WS /ws/agent, and dashboard APK UI JS (currently HIDDEN — re-enable). Recommend Model A
    (phone runs real WhatsApp, app relays notifications — max ban-resistance, no Baileys/proxy) over Model B
    (phone-as-network-proxy for Evolution — rejected). Gaps: proactive-nudge scheduler (G1), escalate-to-own-
    number (G2), recent-human-reply suppression (G3), dashboard re-enable+active-hours picker (G4), signed
    APK build+distribute (G5), reconnect/heartbeat (G6). Phased P0-P5 (P0=assess real device state first).
    4 open questions for founder. NOTHING built yet — awaiting founder review of the design.
  - **★★ DECISION Aug 1 2026 — GO OFFICIAL: Meta WhatsApp Cloud API (not unofficial).** Founder chose the
    sustainable/proven path: dedicated business numbers via the official Cloud API, fully self-serve inside
    sarathi-ai.com. Confirmed target = **Tech-Provider + Embedded Signup** (like Wati/AiSensy/Interakt): a
    Team+ subscriber (e.g. "Delight Financial") clicks "Connect WhatsApp" in their dashboard → Meta popup →
    connects their own number under their own brand → AI runs on their number. **Huge tailwind: the Cloud API
    is ALREADY BUILT in the app** — `biz_whatsapp.py` (graph.facebook.com/v21.0, multi-tenant send), per-tenant
    `wa_phone_id`/`wa_access_token`/`wa_verify_token` columns, `/webhook` GET+POST (verify+receive), and
    `/api/onboarding/whatsapp` (validates creds vs Meta + stores per-tenant) — but the onboarding endpoint is
    currently DISABLED (`return _WA_DISABLED_RESPONSE`). Full guide: `WHATSAPP_CLOUD_API_SETUP.md`. Gates:
    Meta Business Verification (SUBMITTED Aug 2026), App Review for whatsapp_business_messaging+management
    (Advanced Access — main extra gate, ~1 wk), Embedded Signup build (token exchange; per-tenant storage
    already exists). Per-subscriber realities: connected number becomes API-only, display name Meta-reviewed,
    plan-gated Team+. **SEQUENCE: Phase 0 = prove the pipe on ONE number (founder's own, Meta test number OK
    pre-verification) — founder to fetch 3 values from Meta console (Phone-Number-ID, permanent System-User
    token, App-Secret); then I wire biz.env + re-enable + set webhook https://sarathi-ai.com/webhook + test.
    Phase 1 = onboard a real subscriber number manually. Phase 2 = build Embedded Signup self-serve.** This
    SUPERSEDES the Evolution + APK-bridge paths (both parked as non-sustainable). Webhook route already exists
    at sarathi_biz.py:20341(GET)/20347(POST).
  - **TODO — WhatsApp AI-behaviour features (next phase, careful, ban-preventive):** (1) reactive AI reply
    within ~3 min IF AI knows the answer / policy-related; (2) out-of-scope msg → nudge the SUBSCRIBER's OWN
    number on WhatsApp (escalate); (3) if admin + lead already chatting manually → AI stays QUIET; (4)
    per-subscriber AI on/off toggle (connected-but-disabled = no AI); (5) AI active-hours window (date/time;
    default 24/7); (6) proactive ONLY for renewal/pending/lead-journey nudges (human-style). Investigate the
    Evolution inbound webhook + existing AI reply logic before building; keep ban-preventive (reactive-first,
    rate-limited, no bulk).

## 60. AI-DRIVEN "MY FOCUS" — PROPOSAL (owner Jul 30; design to agree)

Clickable filtering already shipped (§58-C). Proposed intelligence layer (super/sub/team, over the
ALREADY-fetched my-tasks — minimal/no extra AI cost):
- **Smart summary line** at the top of My Focus: e.g. "3 need you today — start with #<id> (overdue,
  high-priority). 2 waiting on your approval." Deterministic first (rules over the fetched tasks); an
  optional Gemini one-liner (biz_ai) only if owner wants natural-language phrasing (bilingual, Tier-II/III).
- **Smart ordering / 'Start my day':** one tap opens the single highest-priority task (overdue > due-today
  > high-priority > oldest).
- **Gentle nudges:** if something's overdue/awaiting-approval, a soft banner (not a block — per
  feedback_flexibility_first).
Build deterministically first (safe, instant, free); layer optional AI phrasing after owner confirms tone.

**STATUS (Jul 31): deterministic smart summary DONE + verified live.** My Focus band now shows a smart
summary line ('N overdue · M due today — K on you' / 'nothing on your plate ✓') + a '▶ Start #<id>'
button that opens the most-urgent task (rank: overdue > due-today > priority > earliest due). Computed
from the already-fetched my-tasks (no extra calls) — reliable + instant. Owner directive: this
deterministic message is the source of truth and must NEVER be lost; any AI phrasing is strictly an
ADDITIVE layer on top (optional, to build later). AI phrasing layer NOT built yet (kept safe).

## 56. CURRENT STATE & NEXT — orientation snapshot (Jul 28, 2026) — PAUSED for owner testing

Read this first; the sections above are the detailed history. HEAD verified on prod after each
increment (blue-green via GitHub Actions; content_guard gates the deploy).

**LIVE + verified (this arc):**
- **Flexible plans/pricing** (super-admin editable, grandfathered) — §48.1.
- **Mobile-first identity** (email optional, payment-verified) + payment drop-off hardening — §48.2–3.
- **Ops:** Accounts restructure + Branch column, All-Claims filters (+account/branch) — §48.4/1C-e/f.
- **Branch profit-share** (ops reconciliation) + **branch portal** (email-OTP) — §48.9.
- **AI support + lead-gen engine (S1–S5 + guide/support split + anti-hallucination)** — §49.
- **Content:** single-source config (chat KB + homepage) + retired IRDA/DPDP/Lokpal/Ombudsman
  everywhere + `content_guard` CI gate — §51/52/2a-b.
- **Claims workflow 1C-g:** g.1 auto/manual assign (least-loaded), g.2 go/no-go templates,
  g.4a attachment size/format notes, **g.4b multi-select assignment (grant-only access, verified)**.
- **Task attachments:** ≤10 files/10 MB, +HEIC accept, delete-within-1h/admin — §53.

**IN PROGRESS / NEXT (unblocked):**
1. **1C-g.4c — claim-note collaboration** (attachments +delete-1h/admin, @mention→participants+notify,
   reply threads, read receipts). BIG; rewrites the claim-notes surface (same area as the datetime
   regression) → build in small, individually-tested increments; reuse the proven quick-task infra.
   - **Increment 1 (backend) DONE — deployed + PROD-VERIFIED (live claim round-trip: note+reply+attach+
     mention read back with all keys, admin-deleted, zero residue). Chat-widget fixes shipped alongside
     (visible 🌐 language switcher via new .nsw-langbtn class; chat FAB lifts above sticky CTA; widget v7).**
     schema (biz_database.py: ALTER nidaan_claim_notes +parent_note_id/note_lang/note_translation/source;
     new isolated tables nidaan_claim_note_attachments / _reads / _mentions / _seen — parallel to the
     quick-task tables so the live quick-task path is untouched); helpers (biz_nidaan.py: add_claim_note
     +parent/source backward-compat, get_claim_notes now returns reads/attachments/mentions, plus
     add_claim_note_attachments / delete_claim_note_attachment(1h|admin) / set_claim_note_mentions /
     mark_claim_notes_read / delete_claim_note(1h|admin, promotes replies) / get_claim_mention_candidates).
     Smoke test (scratchpad/g4c_smoke.py): schema, thread-flatten, attach, mentions, receipts, delete → ALL PASS.
   - **Increment 2 — endpoints DONE (deployed + LIVE-VERIFIED on prod Jul 30, zero residue).** All wired:
     ops_add_note (+parent_note_id +mentions → set_claim_note_mentions + on_claim_note_mention notifier),
     POST notes/{id}/attachments (multipart), DELETE notes/attachments/{id}, DELETE notes/{id},
     GET mention-candidates, POST notes/mark-read; notes enriched with signed attachment URLs
     (_enrich_note_attachments in ops_get_notes + ops_get_claim). Live API test (real JWT): add=200,
     reply-threaded=True, mention_ok=True, candidates=24, mark-read=200, delete=200/200, notes-left=0.
     Increment 3 (drawer UI) DONE too — see below.
   - **Increment 3 — claim drawer UI DONE (deployed + verified Jul 30). g.4c COMPLETE.** The claim
     drawer's Internal Notes is now a full threaded discussion (fixes the owner's "messy claim panel"):
     _renderClaimNotesThread (mirrors the quick-task renderer) — threaded ↩ replies, @mention tag-chips
     (from mention-candidates; ★=assignee) → notifies, 📎 attachments (≤10/10MB) with per-file delete ×
     + signed-URL view, read receipts (✓ Sent / ✓✓ Seen), 🗑 delete note (author 1h / admin via
     server-authoritative `deletable`), mark-read on drawer open. Add-note flow: JSON note (+mentions
     +parent) then multipart attachments to the note. Endpoints re-verified 200 after the enrich change.
   - **Increment 2 (original scope, for reference):**
     NON-BREAKING approach (keep the live JSON note path working between increments):
     * Extend `OpsAddNote` (sarathi_biz.py ~4532) + `ops_add_note` (~4537): add optional `parent_note_id:int`,
       `mentions:list[int]`; pass `source=_req_source(request)`; after insert → `set_claim_note_mentions` →
       fire `nnot.on_claim_note_mention(...)`. Keep it JSON (current UI keeps working).
     * NEW multipart endpoint `POST /nidaan/ops/api/claims/{claim_id}/notes/{note_id}/attachments`
       (two-step upload) — mirror `ops_quick_task_note_add` file handling: ≤10 files, ≤10MB each, uuid+ext,
       write to `_NIDAAN_DOCS_DIR`, then `add_claim_note_attachments(...)`. Verify note∈claim first.
     * `DELETE …/notes/{note_id}/attachments/{attachment_id}` → `delete_claim_note_attachment` + disk unlink + `_ops_audit`.
     * `DELETE …/notes/{note_id}` → `delete_claim_note` (returns stored names) → unlink each + `_ops_audit`.
     * `GET …/claims/{claim_id}/mention-candidates` → `get_claim_mention_candidates`.
     * `POST …/claims/{claim_id}/notes/mark-read` → `mark_claim_notes_read`.
     * Serve attachments for viewing via existing `_nidaan_doc_url(stored_name)` (signed URL; same guard as
       quick-task/claim docs). Admin flag = role in (super_admin, sub_super_admin).
     * NEW notifier `on_claim_note_mention(claim, mentioned_ids, by_id, by_name, preview)` in
       biz_nidaan_notifications.py — mirror `on_quick_task_mention`; `dispatch(event_key="claim_note.mention",
       priority=PRIORITY_P1, recipient_type=RECIPIENT_STAFF, claim_id=cid, …)`; deep-link `/admin?claim={cid}`
       (ops page reads `?claim=` at nidaan_ops.html:5162).
     * Verify via API with a staff token (like g.4b), then Increment 3 (drawer UI parity) → single tested deploy.
2. **1C-g.4d** — claim drawer UI restructure (parity with quick-tasks).
3. **1C-h** — Superadmin Branch Dashboard (self-contained).
4. **App Health cockpit (§55)** — scope with owner first, then build (super-admin only, audited).

**BLOCKED (need owner input):**
- **g.3 + L2 integration** — push accepted claims + poll **claimshield.in**; needs the L2 API
  contract (push endpoint, status/comments poll, auth). Owner will get it.

**PARKED (owner action):**
- Google Workspace branch mailboxes (DNS/MX live; create inboxes → set as branch contact_email).
- Optional: send app mail from info@nidaanpartner.com (create mailbox + app password → 3 env vars).
- **Mobile-first signup UI** (backend ready; paused for owner device testing).
- **WhatsApp proxy** — awaiting a dedicated Android phone + iProxy endpoint (2-min gost-wa.service swap).
- Privacy/terms are SARATHI legal docs — DPDP kept (compliance), do NOT strip.

**GOVERNING RULES (memory):** careful/no-break on the mature codebase (additive, backward-compatible,
test the exact live path, super-admin-gate sensitive controls); mobile-first every change; keep THIS
doc updated simultaneously. See memories feedback_careful_no_break / feedback_mobile_first /
feedback_master_doc_living_context.

## 57. CHAT & NOTIFICATIONS OVERHAUL — owner testing feedback (Jul 29, 2026)

Owner tested the live chat and asked for the following. Ground rule reaffirmed: everything
user-facing must be plainly understandable to Tier II/III users (memory feedback_localization_tier23
— words over ambiguous icons; e.g. globe → हिंदी/English label).

**DONE (deployed, widget v8):**
- Chat panel header no longer hidden under the mobile browser bar (100dvh + top gap, full-width).
- Language control shows words (हिंदी / English / Hinglish) reflecting current lang — not a globe.
- Ops Customer Support thread labels customer bubbles with the customer's NAME (not "Customer").

**TODO — notifications cluster (next phase, careful/additive):**
1. **Support agent alerts — DONE (deployed + verified).** New `on_support_customer_reply(thread_id)`
   (biz_nidaan_notifications.py, after on_support_escalated) fires on customer FOLLOW-UP messages in a
   human-engaged thread (prev status 'escalated' OR a staffer already replied) → on-duty reps on
   bell+email+Telegram (falls back to super-admins). Wired in the support-message endpoint
   (sarathi_biz.py ~682, else-branch; captures `_prev_status`). Skipped for pure-AI threads (no noise).
   Note: no per-thread agent assignment exists — uses the on-duty reps roster.
2. **30-min superadmin escalation — DONE (deployed + smoke-verified).** Worker sweep
   `run_support_sla_escalation(30)` (biz_nidaan_notifications.py) runs every 5 min (worker-only
   singleton support_sla_loop in sarathi_biz.py ~20240): threads status='escalated' with NO staff
   reply for >30 min DURING business hours → super-admins on dashboard bell + web push + email +
   Telegram. Idempotent via nidaan_support_threads.sa_escalated_at (additive col), cleared on staff
   reply (ops_support_reply + biz_nidaan.clear_support_sa_escalation). Smoke test: selection,
   idempotency, re-escalation-after-reply → ALL PASS. Prod: column present, fns importable, endpoint 200.
3. **Subscriber dashboard notifications** — (a) in-claim replies: **DONE (deployed + verified).**
   No prior subscriber notif surface existed. Added biz_nidaan.unread_messages_by_claim(account_id) +
   GET /nidaan/api/my/notifications ({claim_unread_total, claims}); dashboard 🔔 bell + badge (EN/HI),
   polls 30s + on load, dropdown → tap opens claim (mark_messages_read already fires on thread open →
   badge clears). Reuses existing read-tracking (nidaan_messages.read_by_subscriber_at).
   (b) support-chat replies: **DONE (deployed + verified).** Added nidaan_support_threads.sub_last_seen_msg_id
   (additive), biz_nidaan.mark_support_seen_by_subscriber() (customer's thread fetch advances it) +
   unread_support_by_thread() (unseen STAFF replies on non-closed threads). /nidaan/api/my/notifications
   now returns chat_unread_total + chats; dashboard bell badge = claim+chat, dropdown 'new replies in
   chat' row opens the widget (→ marks seen → clears). Smoke-tested + prod-verified. Notif cluster #3 COMPLETE.

**aesthetics — DONE (deployed + verified Jul 30, widget v13):** Customer widget — animated typing dots
(was '…'), subtle 'NidaanMitra' label on bot bubbles (matches 'Support agent'), soft bubble shadow +
gentle fade-in. Ops support modal — rounder bubbles with a tail, color-coded sender labels (staff /
NidaanMitra / customer), better line-height/spacing/word-break + shadow. Pure visual/CSS, mobile-first.

Sequencing: finish g.4c (Increment 2 endpoints → Increment 3 drawer UI) first (in flight), then this
notifications cluster, then aesthetics. Or interleave if owner prioritizes chat notifications sooner.

## 58. VISITOR FALLBACK · NidaanMitra · TASK-VIEW UX · BRANCH DASHBOARD · EMAIL-FROM (owner, Jul 29)

**A. NidaanMitra + human-like AI — DONE (deployed v9).** Bot renamed NidaanMitra everywhere
visitor-facing; the word "AI" removed from visitor view. Persona rewritten (biz_ai.py
_NIDAAN_SUPPORT_PROMPT): warm saathi, NEVER reveals it's automated, draws the visitor out one gentle
question at a time to build trust, and warmly captures name + mobile/WhatsApp to reconnect. Ops AI
label → NidaanMitra. (Standing rule saved: memory feedback_localization_tier23.)

**B. Visitor fallback & reconnection mechanics — Increment 1 DONE (deployed + verified Jul 29).**
Email nudge: when a human replies (ops_support_reply), after ~2 min we check sub_last_seen_msg_id; if
the visitor still hasn't fetched that reply AND we have an email (logged-in account, or an email
contact), on_support_reply_nudge emails a reopen link from info@nidaanpartner.com — idempotent per
reply (last_nudge_msg_id). Anonymous → homepage /?nchat=<id>&k=<key> (widget v12 parses it, reopens the
same thread, strips the key from the URL); logged-in → dashboard. Bilingual, includes Chat ID.
Smoke-tested (away→send, idempotent, seen→skip, mobile-only→skip, logged-in→dashboard) → ALL PASS.
REMAINING increments: mobile-only visitors → WhatsApp/SMS nudge (needs those channels live, parked);
next-business-day gentle follow-up if still unanswered (capped). Original design below:
  1. **Capture a channel early.** When escalating (or when interest is shown), NidaanMitra asks for
     name + mobile/WhatsApp (persona already does this). Persist as a LEAD on the thread (contact on
     nidaan_support_threads). No contact = we can only reach them if they reopen the chat.
  2. **Return-to-open-tab:** already works — thread persists via thread_id+thread_key in localStorage;
     widget polls every 4s, so a staff reply appears when they come back to the open tab.
  3. **Closed-browser reply → out-of-band nudge:** when staff replies AND the visitor has a contact on
     file AND hasn't been active (no poll / offline), send a nudge on email + SMS + WhatsApp: "Aapke
     sawaal ka jawab aa gaya hai — yahan dekhiye: <deep link back to chat>". Deep link reopens the
     SAME thread (thread_id+key in URL → widget rehydrates). Needs: (a) store last-seen/last-poll on
     thread; (b) a staff-reply hook that fires the nudge if offline; (c) a signed reopen link.
  4. **Becomes a lead:** a thread with a captured contact = a lead in the ops Support inbox / leads;
     branch attribution still applies if they came via a branch code.
  5. **Nudge cadence:** at most 1 nudge per staff reply, plus a gentle "still there?" follow-up next
     business day if unanswered — capped, never spammy.
  Reuse: dispatch() multi-channel (email/SMS/WhatsApp/telegram), on_duty_rep_ids, lead endpoint.

**C. Task-view UX overhaul — Increment 1 DONE (deployed + verified Jul 29).** Reordered the ops Tasks
panel so MY tasks (Pending with me / Assigned by me / Involved) render FIRST, above the org-wide counts
strip + leave tiles (no scrolling to find your own work). Added a compact '🎯 My Focus' band at the very
top: Pending on me / Overdue / Due today / Involved, computed client-side from the already-fetched lists
(no new API calls), mobile-first. Additive + reorder only (load fns target the same IDs). ALSO fixed:
the customer dashboard notification bell dropdown was clipped by nav overflow:hidden → now moved to
<body>, position:fixed under the bell (z-index 9999). REMAINING increments: admin default landing on
'My Tasks' with one-tap switch to All-org; collapse/paginate long registry; apply the same clean
pattern to the plain Team-Member dashboard.
**Increment 2 DONE (deployed + verified Jul 30):** Task Registry caps to the top 8 (smart-sorted) rows
with a 'Show all N tasks ▾' toggle (pure display, no re-fetch — rest rendered hidden, revealed on tap);
search + chips + filters stay visible → board stays short. All task-view changes render for BOTH admins
and team-members (shared loadTasks/loadMyQuickTasksWidget/loadTaskRegistry) → team-member view
decluttered too. Task-view overhaul substantially COMPLETE. Optional later polish: an explicit admin
'My Tasks ⇄ All-org' segmented toggle (today: My Focus + my-tasks already render first, and the
registry has a 'Me' assignee filter). Original design below:

**C(design). Task-view UX overhaul.** Pain: super/sub-admins have ALL-tasks view buried
far below → endless scroll on web + mobile to find a task or see what needs them; the Team-Member
view is also clumsy/scroll-heavy. Plan (mobile-first, Tier II/III-clear):
  - **Top "My Focus" band (no scroll):** compact cards at the very top — "Pending on me", "Needs
    attention / overdue", "Awaiting my approval", "Due today". Counts + tap to filter. Role-aware.
  - **Admins get a personal "My Tasks" tab** (their own items only) as the DEFAULT landing, with a
    one-tap switch to "All tasks" (org-wide) — so they aren't forced to wade through everything.
  - **Fast find:** a search/filter bar pinned at top (by title, assignee, status, category) so any
    task is reachable without scrolling.
  - **Collapse the long lists** behind tabs/accordions; compact rows; sticky filter header.
  - Apply the SAME clean pattern to the Team-Member dashboard (de-clutter, prioritise "what's on me").
  This is a UX restructure of nidaan_ops.html task area (sensitive, high-traffic) → build additively
  behind the existing data, test the live path, mobile-first.

**D. Branch dashboard (1C-h) — DONE (deployed + verified Jul 30).** Branch portal (nidaan_branch.html)
now has: referral tracking + earnings (pre-existing) PLUS a 'Refer a customer & earn' card — referral
link (origin/nidaan/start?ref=<CODE>) + Copy, enter customer mobile → one-tap WhatsApp (wa.me) / SMS
with a ready Hinglish ₹499-review message, and a QR of the link (lazy qrcodejs from CDN; link/buttons
still work if blocked). nidaan_start.html reads ?ref=/?branch= → pre-fills regBranch so referrals
attribute. Super-admin '↪ Enter' impersonation already added (§58-G). Remaining (optional): branch
'archived' status; @nidaanpartner.com staff-email mapping surfacing in the ops Staff view.
Original requirements below:

**D(orig). Branch dashboard (1C-h) — REQUIREMENTS.** Dedicated branch portal (backend/login exists:
create_branch_token/verify_branch_token, @nidaanpartner.com email + OTP). Add the DASHBOARD UI:
  - Track their referred subscribers (attributed accounts) + status.
  - For direct ₹499 single-review filings: generate a payment link / QR the branch can share, plus
    one-tap WhatsApp / SMS share to the customer's number.
  - Login strictly via their own @nidaanpartner.com email + OTP.
  - **Map @nidaanpartner.com staff/branch emails in the superadmin ops Staff view** so we capture who
    holds a domain email (screenshot: md@, biaora@, dushyant@, info@ — Google Workspace users).

**E. Email-from info@nidaanpartner.com — arrangement (owner does DNS/Workspace steps; I wire the app).**
All internal + customer-facing mail must send FROM info@nidaanpartner.com. Current: biz_email.py sends
via aiosmtplib using SMTP_USER/PASSWORD/SMTP_FROM_EMAIL/NIDAAN_FROM_EMAIL from biz.env — memory says
SMTP NOT configured yet. Cloudflare Email Routing = INBOUND only (not sending); sending needs Workspace
SMTP + SPF/DKIM/DMARC. Steps handed to owner separately (see chat). Once mailbox app-password exists,
I set SMTP_USER/PASSWORD + SMTP_FROM_EMAIL=info@ + NIDAAN_FROM_EMAIL=info@ and restart.

**F. Customer-facing Claim # + Chat ID — DONE (deployed + verified Jul 29).** Customers now see the
IDENTICAL identifiers our team uses, for transparency + easy lookup when they contact support.
Claim number = zero-padded claim_id (ops fmtClaimNum replicated on the customer dashboard: Claim #
column in the claims list, 'Claim No.' row + padded drawer title, notif bell). Chat ID = raw
thread_id shown in the widget header ('Chat ID: #<id>', bilingual, widget v11). Notifications now pad
the claim number via biz_nidaan_notifications._cn() so emails + Telegram quote the same number (chat
IDs were already raw thread_id everywhere).

**G. Branch dashboard — superadmin access/impersonation — DONE (deployed + verified Jul 30).**
POST /nidaan/ops/api/branches/{code}/impersonate (super_admin only) → get_branch → create_branch_token
→ logged (BRANCH_IMPERSONATE) + _ops_audit('branch.impersonate'). Ops Branches panel: super-admin-only
'↪ Enter' button per row → impersonateBranch() stores the minted token in localStorage
['nidaan_branch_token'] (same origin) + opens /nidaan/branch AS that branch. Deactivate already existed
(Enable/Disable → set_branch_status). Verified: endpoint 401 unauth, UI live, branch-token round-trip
(mint+verify) OK. NO password reset (branches self-serve email OTP), per owner. Follow-up: 'archived'
status + more granular controls if wanted. Original request/design below:

**G(orig). Branch dashboard — superadmin access/impersonation.**
Superadmins must be able to ENTER a branch's dashboard (see what the branch sees) + manage them —
like staff options: **impersonate (enter dashboard), deactivate, archive**, etc. — EXCEPT password
reset (branches self-serve via email OTP). Approach (mirror the existing staff-impersonation flow):
in the ops Branches panel add per-branch actions; "Enter dashboard" = superadmin-only endpoint that
mints a short-lived branch token (verify_branch_token path) and opens the branch portal AS that branch
(ideally a read/impersonation banner + full AUDIT of every impersonation; super_admin gate only).
Deactivate/archive = status flags on the branch record (additive). Build as its own careful increment
(impersonation is sensitive → audit, gate, reversible). Check for an existing staff-impersonation
helper to reuse.

**AI-driven "My Focus" (owner Jul 30, to discuss + build).** Clickable filtering DONE (§58-C). Next:
make the band INTELLIGENT — a NidaanMitra-style smart line ("3 tasks need you today — start with #<id>
(overdue, high-priority)"), auto-prioritised ordering, maybe a one-tap "start my day" that opens the
top task. Design to agree with owner; likely a small AI summary over the already-fetched my-tasks
(no heavy calls). Keep it clear/Tier-II-III.

Recommended sequence (my rec): finish g.4c → notif #2 (30-min escalation) + #3 (subscriber dash) →
visitor-fallback (B) → task-view UX (C) → branch dashboard (D). Email (E) unblocks once owner does DNS.

## 59. APP SEPARATION PLAN — Sarathi-AI ⟂ Nidaan (design; NO changes yet; owner Jul 29)

Owner decision: emails stay separate — Sarathi from info@sarathi-ai.com, Nidaan from
info@nidaanpartner.com. Owner wants a systematic plan to separate the two apps so each can be
DEVELOPED + DEPLOYED independently without disturbing any flow in the other. Constraint: additive,
reversible, zero-downtime, careful/no-break. (Owner gave the Nidaan Workspace app password for
info@nidaanpartner.com — to be placed in biz.env only when Phase 1 executes; regenerate anytime.)

CURRENT ENTANGLEMENT (the seam):
- ONE FastAPI app (sarathi_biz.py ~20k lines) serves both; host detection _is_nidaan_host /
  _is_sarathi_host selects behavior. One process, one blue-green deploy, one worker singleton.
- ONE SQLite DB: Sarathi tables + nidaan_* tables + CROSS links (product_link tenant↔nidaan;
  branch attribution accounts↔tenant). biz_platform_bridge.py = the ONLY module touching Sarathi
  tenants/agents from Nidaan.
- Shared modules: biz_email (ALREADY branches FROM by platform: NIDAAN_FROM vs FROM_NOREPLY; supports
  Resend API or Gmail SMTP), biz_ai, biz_database, biz_nidaan_notifications. Shared biz.env (SMTP/JWT),
  nginx (host-routed), static, worker loops.

PHASES (each independently valuable, safe, reversible):
- **Phase 1 — Email/credential separation — DONE (deployed + live-tested Jul 29).** biz_email now has
  a dedicated Nidaan SMTP account: added NIDAAN_SMTP_HOST/PORT/USER/PASSWORD; @nidaanpartner.com senders
  authenticate via info@nidaanpartner.com (Workspace app password) → From=auth=Nidaan domain (DKIM
  aligned). STRICTLY ADDITIVE — only @nidaanpartner.com senders enter the branch; Sarathi keeps
  SMTP_USER=nidaanpartner@gmail.com + From=info@sarathi-ai.com, path untouched. biz.env updated on
  server (backup made: biz.env.bak.*), NIDAAN_FROM_EMAIL=info@nidaanpartner.com. Rolling restart
  (web@1→web@2→worker, zero downtime; both /health 200; log '✅ Nidaan email account ready'). Live test:
  Nidaan send True (from info@nidaanpartner.com), Sarathi send True (from info@sarathi-ai.com). Routing
  smoke-tested too. NOTE: app password is in /opt/sarathi/biz.env (600) — owner may regenerate anytime.
- **Phase 2 — Code modularization (refactor-only, behavior-preserving).** Split sarathi_biz.py routes
  into FastAPI APIRouters (sarathi_routes / nidaan_routes / shared_core), mounted by host. One process
  still, but a Nidaan change stops editing the same file as Sarathi. Huge drop in "change one, risk the
  other." Fully testable + reversible.
- **Phase 3 — Data ownership (clarity first, no physical split).** Document strict table ownership
  (nidaan_* = Nidaan; rest = Sarathi) + the few BRIDGE tables (product_link, branch attribution),
  accessed only via biz_platform_bridge. Physical two-DB split only later if needed (thin bridge API;
  higher risk; defer).
- **Phase 4 — Independent deploy (the core benefit).** Run TWO app processes on the same server sharing
  a common package: nidaan-web (e.g. 8003/8004) + sarathi-web (8001/8002); nginx routes by host to the
  right pair; each gets its own systemd units + own blue-green deploy target + own CI job. A Nidaan
  deploy then restarts only nidaan-web; Sarathi untouched (and vice-versa). Split worker loops too
  (nidaan-worker / sarathi-worker). Requires Phase 2 boundaries first.
- **Phase 5 (optional, later) — Two repos + shared library.** Extract shared modules into a versioned
  internal package; each app its own repo + pipeline. Full org-level separation; highest effort; only
  if the business wants distinct codebases.

RECOMMENDED ORDER: 1 (email) → 2 (modularize) → 4 (two processes = independent deploy) → 3 (data doc)
→ 5 (repos, only if needed). Phases 1–2 are low-risk and unlock most day-to-day benefit; Phase 4
delivers "deploy separately." NON-NEGOTIABLE: additive + reversible each step; test BOTH apps' live
paths before/after; never break a flow; zero-downtime; keep this doc updated.

---

## 62. STAFF-AS-BRANCH — personal referral business (owner Aug 8; SHIPPED, live 210504a)

Owner ask: "yes go ahead for staff-as-branch, make it carefully… run well with all
calculations/counts… no other feature/flow/wiring should get disturbed."

DESIGN (zero-disruption): every staffer is now also a referrer. Attribution reuses the
EXISTING shared slot `nidaan_accounts.branch_code`. Staff codes are formatted `SP-XXXXXX`
(alphabet excludes I/O/0/1 for Tier II/III legibility) and are checked unique across BOTH
`nidaan_staff.referral_code` AND `nidaan_branches.branch_code`. Because branch reconciliation
(`list_branches`) only counts codes that JOIN a real `nidaan_branches` row, a staff code in
that slot is invisible to branch stats — and vice-versa. No branch/claims/attribution flow
was modified.

BACKEND (biz_database / biz_nidaan / sarathi_biz):
- `nidaan_staff` += `referral_code`, `commission_pct REAL DEFAULT 0` (idempotent ALTERs).
- `ensure_staff_referral_codes()` backfills all staff → run at startup + inside create_staff
  (both fresh + reclaimed paths). Verified live: 25/25 active staff have unique codes.
- `get_staff_business(id)` / `list_staff_business()` mirror list_branches: signups, paid,
  attributed revenue, claims, commission = revenue × commission_pct (RUPEES).
- `set_staff_commission(id, pct)` (0–100).
- Endpoints: GET `/nidaan/ops/api/my-business` (own — any staff), GET `/nidaan/ops/api/staff-business`
  (super-admin reconciliation), PATCH `/nidaan/ops/api/staff/{id}/commission` (super_admin, audited).

FRONTEND (nidaan_ops.html): new "🚀 My Business" nav (minRank 0 → every staffer) + gamified
panel: personal code, shareable link (`/nidaan?ref=CODE`), copy-code/copy-link/WhatsApp-share,
stat tiles (signups · paid · claims · revenue · commission), stage-based motivational nudge.
Super-admins additionally get a "Team referral commissions" table with inline editable comm %.
Rendered in the staffer's OWN saved language (telegram_lang) via JS ternaries — the ops portal
has no live UI language toggle and no .en/.hi CSS, so dual spans were NOT used. Branch payout ₹
amount was already displayed in the ops branches table (share_pct → ₹ payout column).

COMMISSION SEMANTICS: reconciliation figure, not auto-paid; % set by super-admin (default 0).

NOT YET (future phases if owner wants): staff RAISING claims directly like a branch house
account; per-cycle recurring commission accrual; auto-payout. Current build = attribution +
visibility + commission config + gamified dashboard.

Also this session: fixed #6 commission disclaimer not switching to Hindi on the subscriber
dashboard (its `.hi` blocks had inline `display:none`, which the `.body.hi/.body.en` CSS
toggle cannot override; removed inline styles → live 6648921). Fixed My Business tab blank
(called loadMyProfile vs _loadMyProfile → 7671d6c) and staff shareable link 404 (used
/nidaan?ref= not /nidaan/start?ref= → 350468b).

## 63. BUSINESS ANALYTICS — channel attribution + funnel + failures (owner Aug 8-9; SHIPPED, live 9f2e007)

Owner ask: track every acquisition CHANNEL (subscribers / one-time reviews / signups) +
"missed, failed, payment failed" with as much per-attempt detail as possible; super-admin
full control over shared/referred accounts. Design agreed via AskUserQuestion:
Internal+marketing(UTM) channels · Failures+abandonment depth · dedicated dashboard.

Super-admin control over referred accounts ALREADY existed (referred accounts are normal
nidaan_accounts → ops Accounts panel: create/edit/bulk-delete + segments + branch search).

PHASE 1 (data spine, 5739e05): nidaan_events append-only log (event_type, channel, ref_code,
utm_*, account_id, claim_id, amount_paise, purpose, status, reason, session_id, contact, meta
+ indexes). nidaan_accounts += source_channel/utm_source/utm_medium/utm_campaign.
resolve_channel(ref,utm)→direct|staff|branch|campaign|marketing; record_event() (best-effort).
Webhook payment.failed + subscription.halted now PERSIST events (payment_failed/
subscription_failed) on top of the existing alerts.

PHASE 2 (instrumentation, 99b154f) — includes a CRITICAL fix: staff-as-branch shareable links
were being REJECTED at signup because every signup path validated the code via is_valid_branch
(branches only). Added is_valid_ref_code (active branch OR staff referral_code) and switched
email/mobile/claim/Google signup validation to it; branch-signup alert now only fires for real
branches. All signup endpoints accept + store utm_*; create_account* fire signup_completed.
New POST /nidaan/api/track (public, rate-limited, whitelisted top-of-funnel beacons only).
static/nidaan_track.js (first-touch ref+UTM capture 90d, anon session id, sendBeacon funnel/
abandonment) on landing/start/dashboard; signup carries attribution; subscription pay fires
pay_opened/completeFlow/abandoned. Abandoned one-time reviews are authoritative via
per_claim_purchase.pending_payment (no beacon needed).

PHASE 3 (dashboard, 9f2e007): get_business_analytics(days) — a SQL channel-CASE classifies
BOTH new (source_channel) and legacy (derived from branch_code) accounts, so history is
included (verified live: 22 direct + 1 branch). Metrics: signups/subscribers/one-time/revenue
(cohort by signup date), abandonment + failures (event time), stuck reviews, funnel
(signup_started→signups→pay_opened→paid), recent-failures stream. GET /nidaan/ops/api/analytics
(super_admin only). New "📊 Business Analytics" ops nav + panel: date range (7/30/90/365),
cards, funnel with drop-off %, by-channel table, payment-failure follow-up (WhatsApp/Call).

NOTE: funnel beacon steps (signup_started/pay_opened) accumulate from Aug 9 onward; confirmed
records (signed-up/paid) and failures are complete. Marketing/UTM only populates when landing
URLs carry utm_* params. Future: per-cycle recurring revenue window (vs cohort); review/L2 pay
abandonment beacons; campaign-code registry.

## 64. OUR OFFICES — super-admin editable (owner Aug 9; SHIPPED, live df86a75)

Owner: make the homepage "Our Offices" addresses add/edit/delete-able from super-admin,
reflecting on both advisor & policyholder views. (The site is ONE page — nidaan_index.html —
with audience CSS toggles; the offices section has no only-adv/only-ph class, so one source
covers both views.) Stored as a JSON list in the ops-settings KV (get_offices/set_offices;
DEFAULT_OFFICES fallback until first edit; city bilingual + single-line address). Endpoints:
GET /nidaan/api/offices (public), GET /nidaan/ops/api/offices (staff read), PUT (super_admin,
audited). Homepage renders the grid from the config (static cards kept as fallback if fetch
fails; language follows body.hi/.en CSS). Editor lives in ops → Content panel ("🏢 Our Offices").

## 65. SARATHI TRIAL: Phase B audit + Phase C 14→7 (owner Aug 9; SHIPPED, live 6fbc755)

PHASE B (read-only audit) findings: base trial was actually 14 days (not 15), referral bonus 21
(=14+7), hardcoded in 8 backend sites + ~20 copy strings across 13 static pages, with NO central
constant. Enforcement (db.check_subscription_active) reads trial_ends_at dynamically → no change
needed there; renewal reminders are paid-plan (unrelated). SA cockpit already extensive (~45
/api/sa/ endpoints) → Phase D is enhancement not greenfield.

PHASE C (change): introduced SINGLE SOURCE OF TRUTH in biz_database.py — TRIAL_DAYS=7,
REFERRAL_TRIAL_DAYS=14 (base + 7 bonus). All start/reset sites now reference them (create_tenant,
create_tenant_with_owner, both signup referral paths @ ~9506/13029, sa_activate @10308,
sa_change_plan @10379, flow-doc strings). Frontend: every "14-day free trial" (EN+HI) across
index/about/admin/dashboard/demo/features/getting-started/help/partner/superadmin/telegram-guide/
terms/index_v2/v3/v4 → 7-day. Extend-trial DEFAULTS (sa_extend Query(14), admin_extend Query(7))
left as separate operational knobs (not trial length). Future trial-length change = edit 2 constants.

PHASE D (5489c0b) subscription cockpit: the Sarathi SA cockpit was already comprehensive (tenants
by status, MRR, plan mix, signup trends, funnel, revenue, refunds, bulk ops, impersonation,
Telegram web login). Gap = renewal/churn-risk visibility → added sa_dashboard KPIs
trials_expiring_7d + subs_expiring_7d and two clickable KPI tiles that deep-link to Tenants
pre-filtered (trial/paid). Pairs with the auto-pay recovery work.

## 66. STAFF-AS-BRANCH v2 + REFERRAL + L2 FLOW (owner Aug 9-10; 7-phase batch, discuss-first)

Owner batch (staff claim-raising, branch L2 flow, referral robustness, easy login, mobile UX)
+ 2 additions (branch chatbot+Support filter; richer chat timestamps). Agreed order 1→7.

SHIPPED so far:
- **Phase 1 (c207cc7) Referral bulletproofing:** `resolve_ref_info` + public GET /nidaan/api/ref-info
  (code→{valid,type,name}). Signup page: ref = URL ?ref/?branch OR persisted first-touch
  (NidaanTrack) → shows "✓ Referred by <name>" + LOCKS the code so attribution can't be lost.
  Chain already worked server-side (is_valid_ref_code accepts staff SP- codes → create_account
  stores branch_code → counted in My Business + superadmin + analytics); this makes it visible+
  tamper-proof. Verified: SP-Q2K34U→Dushyant Sharma, IND-HO→Indore Head Office, bogus→invalid.
- **Phase 2 (4c5f6a9) Staff claim-raising in existing ops login:** additive ops-authed routes
  reusing the ENTIRE branch pipeline with the staffer's SP- code: POST/GET /nidaan/ops/api/my-claims
  + /{id}/l2-pay, l2-pay-verify, l2-advance, l2-payment-link. House account via
  get_or_create_branch_house_account(SP-code); origin='branch'. My Business panel gains a
  "📝 Raise a claim" form + "Your raised claims" table (Pay ₹fee via Razorpay checkout injected
  on demand, Share link, Send-to-L2-free). _staff_business_row adds claims_raised. NO change to
  live branch endpoints. Rejection letter optional at staff-raise (they attach via Claims Dashboard).
- **Phase 3 (d5e5d79) no_scope 5-day auto-archive:** list_branch_claims returns `archived` flag
  (no_scope + not L2-paid + review_delivered_at older than NO_SCOPE_ARCHIVE_DAYS=5). Branch
  dashboard + staff My Claims both gain Active/Archived tabs. L2 fee already ₹499 (branch_l2_fee).

- **Phase 4 (8243996) Easier login:** stay-signed-in already effective (staff token has NO exp +
  localStorage). Telegram one-tap login SHIPPED: nidaan_staff.telegram_access (default 1) +
  nidaan_tg_login nonce table; bot /start weblogin_<nonce> authorizes for a LINKED, telegram-
  enabled staffer; POST /nidaan/ops/api/tg-login/start (nonce + t.me/NidaanOpsBot?start=weblogin_)
  + GET .../tg-login/status (poll→mint session, single-use). Linking gated by telegram_access;
  PATCH /staff/{id}/telegram-access (super_admin, deny also unlinks). Ops login screen "Login via
  Telegram" + poll; Staff table per-staff ✈️ toggle. Password = universal fallback.
- **Phase 5 CORE (3cccebd) Mobile back-button:** ROOT CAUSE = subscriber/branch/sarathi dashboards
  had NO history handling + display:standalone PWA → phone Back EXITED app. Fix = shared
  static/nidaan_backguard.js (keeps a history guard entry; Back closes top overlay then stays; in
  installed PWA never accidental-exits; normal browser Back stays normal). Wired into
  nidaan_dashboard, dashboard.html (sarathi), nidaan_branch. Ops left as-is (own tab-history).

- **Phase 6 (714ca24) Branch chatbot + Support filter:** support threads accept channel
  'branch'/'staff' (create_support_thread whitelist); NidaanSupportMsgReq.channel; widget reads
  window.NSW_CHANNEL + NSW_NAME and sends them. Branch dashboard loads the widget with
  channel='branch', name 'Branch <code>'. Ops Support: per-row channel badge + channel filter
  (All/Web/Branch/Staff, client-side) + channel tag in conversation header.
- **Phase 7 (714ca24) Chat timestamps:** fmtDateTime (stored UTC → IST date+time). Ops thread
  list 'Updated' shows date+time; each message bubble (ops + customer widget) shows a per-message
  date+time tag.

- **Ops fixes (2b349a3):** (1) team-member Claims Dashboard was showing OFFICE-WIDE counts —
  get_overview_widgets now scopes total/open claims + claims-by-status to the viewer's
  assigned/involved claims (same rule as get_claims_ops); 'Active subs' admin-only; tiles relabel
  'My claims'. (2) Green unseen-update dot on claims (mirrors Tasks): get_claims_ops returns
  unseen_notes (unread claim notes by others for the viewer); all claim lists show a blinking
  .unseen-dot until opened; drawer's existing notes/mark-read clears it. Reuses
  nidaan_claim_note_reads (no new table). NOTE: dot is driven by unread NOTES; if owner later
  wants status-changes to also trigger it, extend has_new to compare last_status_at vs a seen ts.

- **Auto-pay robustness (ead2e55):** AUDIT found both apps use Razorpay Subscriptions (Razorpay
  manages mandate + retries + 24hr pre-debit). Gap: Nidaan lacked subscription.pending (Sarathi had
  it). FIXED: Nidaan webhook now handles subscription.pending (first failure → customer recovery
  email + analytics log) and, on subscription.halted, ALSO emails the customer a re-activate link
  (was SA-only). New biz_email.send_nidaan_autopay_recovery_email (pending|halted). FOUNDER CONFIG
  still required in BOTH Razorpay dashboards (separate accounts): enable subscription.* +
  payment.failed webhook events; turn Smart Retries ON; prefer UPI Autopay for small plans. Out of
  our scope: bank declines / insufficient funds / mandate not approved.

- **Branch self-login (53752c9):** the email-OTP branch login was ALREADY built (nidaan_branch.html
  loginView + /nidaan/branch/api/request-otp + verify-otp → create_branch_token; get_branch_by_email
  active-only). Root cause it felt missing: 6/9 branches had NO contact_email → couldn't receive the
  OTP, and there was no login link to hand them. FIX (ops Branches panel, no backend change):
  relabel 'Login & alert email' + how-to banner (nidaanpartner.com/nidaan/branch), '⚠ no login email'
  flag + 'add' for branches missing it, and '🔗 login link' per branch that copies ready-to-send
  sign-in steps. FOUNDER ACTION: set an email for the 6 branches lacking one (IND-HO, PUN-01,
  MUM-01, CHD-01, HYD-01, RPR-01), then send each its login link.

- **Payment integrity (8c5d332, 8a2e1cf):** verify endpoints marked paid on Razorpay SIGNATURE
  alone (= authorized, NOT captured) → a pending/UPI payment could show paid. FIX: all Nidaan
  pay-verify paths now confirm status=='captured' (_nidaan_payment_captured) before finalizing;
  webhook payment.captured is the backstop (added nidaan_review_999 handler; claim_499 + branch_l2
  already had one); payment_capture:1 on all orders. Investigated the reported GAURAV #037 case:
  the payment WAS genuinely captured (₹588.82 UPI) — dashboard was correct; the confusing
  'payment pending' Telegram was the CREATION-time 'New ₹499 lead (payment pending)' ops alert
  (biz_nidaan_notifications:2571), accurate at creation, then paid seconds later (a separate
  'PAID ₹499' alert also fires). Added a super-admin '🔄 Reconcile payments' button (runs the
  existing /payments/reconcile sweep dry-run → confirm → apply).
- **Multi-claim for ₹499 customers (bc1c9ba):** owner confirmed unlimited / free-submit→pay-to-start /
  same tier. Backend already made every non-subscriber claim unpaid_lead (get_per_claim_status has
  no 'paid' shortcut) + the claims list already renders a per-claim Pay button + capture-hardened
  pay. Only blocker was the 'Balance Exhausted' dashboard state, which dead-ended the user (locked
  section + link to /nidaan/start). FIXED: that state now enables newClaimBtn + clears the lock +
  'raise another claim — ₹499+GST per claim'. Net: one customer can raise unlimited claims, tiered
  ₹499/₹2000+GST each, from their own dashboard (submit → per-claim Pay → review).

## 67. BRANCH/STAFF PARITY (owner Aug 10-11; design locked, building in phases)

Owner intent: branch & staff are the SAME product (refer subscribers + raise retail claims), differ
only in commission %. DECISIONS: (1) ONE shared role-aware dashboard; (2) L2 retail fee = SAME tier
as homepage (₹499 / ₹2000 >₹10L + GST) collected at can_fight — NOT flat, NOT per-entity (only
commission % is per-entity); homepage pays UPFRONT, branch/staff pay at the L2 decision; (3)
attribution first-touch LOCKED. a–d (refer subs, raise retail free→pay-at-L2, share L2 link gated
to can_fight, share signup link→self-register attributed) were ALREADY built for both — parity work
mainly re-homes them into one UI.

- **Phase A SHIPPED (02f4406):** branch_l2_fee_for_claim(claim_id) = single source of truth = tiered
  review_fee_for(disputed) gated by charge policy; wired at ALL touch-points (branch+staff
  pay/verify/link, webhook, admin-link + bulk reconcile); list_branch_claims returns per-claim
  l2_fee; both dashboards show tiered amount + '+GST' + encouraging 'can be fought → pay to move to
  Level-2' copy. Attribution LOCK: set_account_branch is first-touch-only (never overwrites);
  subscriber profile referral field read-only once set.
- PENDING: Phase B (post-payment 'your claim is moving to Level-2' shareable confirmation — pay copy
  already added), Phase C (unified role-aware partner dashboard: shared renderer for branch page +
  staff My Business), Phase D (subscriber 'Referred by [name]' read-only + end-to-end parity check).
  FOUNDER TEST: raise a branch/staff claim with disputed >₹10L → verify L2 shows ₹2000+GST; <₹10L → ₹499+GST.

PENDING: Phase 5 REMAINDER (visible back/close buttons on every panel/drawer/modal; ops modal
back-hardening; full responsive audit — needs real-device verification).

- **G3b SHIPPED (d97e145):** SA/Admin edit Claim info + Advisor info from the ops claim drawer
  (mobile-friendly modals; disputed-amount edit re-tiers L2 fee; audited).
- **G3 (L2 process) SHIPPED (af02789):** the assign/tag/two-way-comms/all-channel-notifications
  were ALREADY in the shared claim workflow; closed the one gap — a claim moving to L2
  (on_moved_to_l2 for can_fight; on_branch_l2_paid for branch/staff) now AUTO-ASSIGNS a least-loaded
  owner (no-op if already assigned or auto-assign off) and includes that owner in the L2 alert.

## 68. STAGING ENVIRONMENT (owner Aug 12; BUILT, awaiting DNS/TLS)

Decision: staging = MAIN test ground; prod = clean real data. Isolated, same Contabo box, cheap.
- **Install:** /opt/sarathi-staging on the `staging` git branch (prod = master). WEB-ONLY systemd unit
  `sarathi-web-staging` on **port 8003** (APP_ROLE=web → NO worker/bots/scheduler). Shares prod venv.
- **Isolation:** OWN DB `/opt/sarathi-staging/sarathi_biz.db` (all 3 modules resolve cwd-relative —
  biz_database DB_PATH is hardcoded, so the sanitized file is NAMED sarathi_biz.db; do NOT set
  SARATHI_DB_PATH or OTP splits). OWN neutralized biz.env: live Razorpay/SMTP/WA(Evolution)/FAST2SMS/
  Brevo/VAPID/Backup/GitHub keys BLANKED; TELEGRAM_BOT_TOKEN = a fake disabled value (empty crashes
  startup guard; fake = Telegram 401, no real send); SMTP ports kept 587/465 (int() of '' crashes);
  fresh JWT_SECRET; SERVER_URL=https://staging.nidaanpartner.com. → staging can't charge money or
  message real people. prod DB provably distinct (different md5).
- **Data:** sanitized clone of prod via `deploy/sanitize_staging_db.py` (anonymizes phones/emails/names,
  blanks external IDs+in-db secrets with unique fakes, clears OTP/nonce/WA queues; 6109 cells rewritten).
- **nginx** `deploy/nginx-staging.conf` → staging.* proxy to :8003, **HTTP basic-auth gated**
  (/etc/nginx/.staging_htpasswd, user `founder`, pw in /opt/sarathi-staging/.staging_access via SSH) +
  `X-Robots-Tag: noindex`. staging.* is a transport alias: apex Host mapped in for routing.
- **Deploy:** `deploy/staging-deploy.sh` (pull origin/staging → syntax gate → restart → /health gate).
- **AWAITING (user):** add DNS A records staging.nidaanpartner.com + staging.sarathi-ai.com →
  84.247.172.252 (DNS-only/grey-cloud recommended); THEN run certbot --nginx for TLS. Until then
  reachable via curl --resolve / SSH. **Phase C (unified partner dashboard) will be built+tested HERE
  first, then promoted master→prod.**

## 69. DUAL-APP PROJECT MAP — both products, one codebase (living overview, Aug 12)

ONE FastAPI app (`sarathi_biz.py`) serves BOTH products, split by Host + path. Same SQLite DB
(`sarathi_biz.db`, WAL), same blue-green web tier (8001/8002 behind nginx `sarathi_app`), same worker
(`sarathi-worker` = bots + scheduler singletons). `biz_platform_bridge.py` is the ONLY module that
crosses the boundary. Host routing: `_is_nidaan_host(request)` → nidaanpartner.com; else Sarathi.

### 69.1 sarathi-ai.com — Sarathi-AI CRM (AI financial-advisor CRM)
- **Who:** multi-tenant SaaS for financial advisors. `tenants` (firm/owner/billing) + `agents` (per-firm
  users). Served at ROOT paths (`/`, `/admin`, `/api/...`, `/ws/agent`).
- **Core:** Leads→Customers split (separate `customers` table + per-type portfolio + shareable revocable
  link, [[project_sarathi_customers]]); advisor **cockpit = Telegram bot** (`biz_bot.py`); customer
  **megaphone** = WhatsApp via Evolution API (`biz_whatsapp_evolution.py`, `wa_instances`) — **that service
  is currently DOWN and being retired for an official RCS/SMS rail via Exotel, see §72**; Gemini AI replies;
  reminders/nurture/marketing (`biz_reminders`/`biz_nurture`/`biz_marketing`, own `DB_PATH` env); Razorpay
  tenant subscriptions; trial 7d / referral 14d.
- **Homepage:** `static/index.html` (+ index_v2/v3/v4 variants). NO GA yet (would need its own GA4 ID).

### 69.2 nidaanpartner.com — Nidaan · The Legal Consultants LLP (insurance claim disputes)
- **Who:** policyholders (retail ₹499/₹2000 review) + advisors/subscribers (plans) + branches + staff
  (staff-as-branch). Served under `/nidaan/*` + host-based homepage.
- **Surfaces:** homepage `nidaan_index.html`; login `nidaan_start.html`; subscriber dashboard
  `nidaan_dashboard.html`; ops/admin portal `nidaan_ops.html` (`/nidaan/ops`); branch dashboard
  `nidaan_branch.html`; staff "My Business" (inside ops). Support widget everywhere.
- **Money:** tiered review fee `review_fee_for(disputed)` = ₹499 base / ₹2000 if >₹10L, +GST
  (GST-exclusive via `charge_with_gst`); homepage pays UPFRONT, branch/staff pay at L2 decision
  (`branch_l2_fee_for_claim` = single source of truth). Razorpay orders + subscriptions; capture-verified.
- **Ops:** claim workflow (assign/tag/@mention/notes + two-way customer↔ops messages + watchers);
  L2 (legal) flow with auto-assign-on-move + **ClaimShield.in integration** (L2 legal partner, see §71);
  Telegram ops bot @NidaanOpsBot; Business Analytics
  (channel attribution + funnel + failures, `nidaan_events`); all-channel notifications (bell/email/
  telegram/push). [[project_nidaan_erp]], [[project_nidaan_analytics]], [[project_nidaan_telegram]].
- **Marketing/SEO (Aug 12):** GA4 `G-CJMN1DJGFM` (host-guarded to real prod only) + Search Console
  (meta tag + `/google3df0c6b7c9115ee9.html` file route, nidaan-host-gated). nginx CSP widened for
  googletagmanager + google-analytics. `🏠 Home` nav on homepage + subscriber dashboard (start page
  already had back-to-home).

### 69.3 Shared infra (both)
App server 84.247.172.252 (Contabo). biz.env `sarathi:sarathi 600` [[infra_bizenv_ownership]].
Cloudflare in front (proxied apex; caches /static) [[infra_cloudflare_cache]]. Backups: local 7d +
off-server AES-256 [[infra_backups]]. **Staging** = isolated `/opt/sarathi-staging` on :8003
(sec.68 / [[infra_staging_env]]) at staging.nidaanpartner.com + staging.sarathi-ai.com (HTTPS,
basic-auth gated, sanitized data). Deploys: prod `deploy/auto-deploy-zerodowntime.sh` (master),
staging `deploy/staging-deploy.sh` (staging branch).

## 70. LIGHT/DARK THEME + CHAT LABEL + CHECKLIST i18n (owner Aug 12-13; SHIPPED to prod)

- **Theme engine:** `nidaan_design.css` `:root[data-theme="light"]` palette (overrides --nd-* color
  tokens; brand accents kept). `nidaan_theme.js` applies saved theme early (default dark → nothing
  changes for current users), auto-wires any `.nd-theme-toggle` button (bilingual ☀️Light/🌙Dark,
  persisted). Added `--nd-cyan-text` (darkens cyan text in light). Global light `<select>` fix.
- **Converted to dual-theme (ALL LIVE on prod):** subscriber dashboard, review (/get-reviewed),
  start/login, branch portal, ops portal (~980 static colors), shared `nidaan_partner_claims.js`.
  Self-contained pages (review/start/branch) got design.css+theme.js added. Conversion via a
  property-aware, badge/button-safe script (scratchpad `theme_convert.py`): each token's DARK value
  equals the prior hardcoded value → **dark mode pixel-identical**; only light mode is new. Rule:
  white-on-dark flips; white-on-colored-button STAYS; `${}` JS-template styles skipped (verified 0
  invisible-in-light text per page; ternary counts unchanged; inline JS valid). Nav bars with
  dark-navy RGBA bg → `--nd-bg-elev-blur` so they flip; modal scrims stay dark. Cache versions:
  design.css v3, theme.js v2, partner_claims.js v2, support-widget v17.
- **Chat launcher:** persistent bilingual **"Ask NidaanMitra"** pill + blinking green live dot (mobile-aware).
- **Doc checklist i18n:** headings/descriptions/DPDP disclaimer now switch with the live EN/HI toggle
  (were bound to comm_lang). Added `WHY_HI` for every doc in `biz_nidaan_doc_checklist.py`; API returns
  both langs + trust_line_en/hi; dashboard renders .en/.hi spans.
- **QUEUED (agreed to-dos):** (a) Attachments — confirm-before-submit review step (support/ops
  backend delete already exists via G2). (b) Chat enhancements BIG batch: **30-min session model**
  (auto-close on inactivity/minimize → filed to history with session ID, no endless thread/backlog);
  bouncing+draggable launcher; minimize button; 👍/👎 rating recorded; Support-page chat analytics;
  channel segregation (homepage / subscriber plan-wise / one-time-review / branch).
- **SHIPPED TO STAGING (Aug 13, commit 5c501aa, widget v20) — awaiting owner verify:**
  - *Bouncing + draggable launcher + minimize button* (v19, already staging).
  - *30-min session model:* one chat = one ~30-min session. 30 min inactivity **or** Close (×) ends
    it → filed to history (thread id = session number); next message opens a fresh session. Minimize (–)
    keeps the session alive. Idle timer + expiry checks on open and on send; `ts` stamped on every
    thread create/restore/reply. Backend `close_support_session()` (ALTER-on-first-use `closed_at`,
    status='closed'); `POST /nidaan/api/support/close` (thread_key-validated).
  - *👍/👎 rating:* bilingual (EN/HI/Hinglish) dark-island rate bar, mobile-first, appears once the
    chat is underway; `POST /nidaan/api/support/rate` → `set_support_rating()` (ALTER-on-first-use
    `rating`/`rated_at`). Recorded on the thread for Support analytics.
  - *Smoke-tested on staging:* empty body→422, bogus thread→404 (thread_key validation), widget v20 served.
- **SHIPPED TO STAGING (Aug 13, commit d03ef1b, widget v21) — completes the chat batch, awaiting owner verify:**
  - *Channel segregation (single source of truth):* `_derive_support_channel()` in sarathi_biz.py used by
    BOTH thread-creation endpoints (message + lead). Logged-in customer → `subscriber` (plan derived via
    account_id); a page declares `homepage`/`review`/`branch`/`staff`; else `web`. `SUPPORT_CHANNELS`
    whitelist in `create_support_thread`. Homepage sets `window.NSW_CHANNEL='homepage'`; widget whitelist
    accepts homepage/review. Also fixed a **latent 422**: the lead model forbade the `channel` field the
    widget already sends (branch/staff leads would have failed).
  - *Ops Support panel analytics (new):* `📊 Chat analytics` summary — sessions, **CSAT** (👍/👎),
    escalation rate, **per-channel** table, **plan-wise** subscriber breakdown; 7/30/90-day picker;
    theme-aware tokens + mobile-first. `GET /nidaan/ops/api/support/analytics` → `support_analytics()`
    (plan via correlated subquery — no row multiplication).
  - *Inbox:* channel filter now **server-side** (`threads?channel=`); 👍/👎 **rating chip** per row + in
    the thread detail header. `_SUP_CH` map extended (homepage/subscriber/review).
  - *Backend additive:* `_ensure_support_extra_columns()` guarantees rating/rated_at/closed_at exist
    before any ops SELECT (ALTER-on-first-use is lazy).
  - *Verified on staging:* channel stamping (homepage→homepage, review→review, bogus→web), analytics
    401 without staff auth, `support_analytics(90d)` runs clean (23 sessions; web 21 / review 1 /
    homepage 1; CSAT 100% on 1 rating), channel filter returns the homepage thread.
  - **Whole chat enhancements batch is now on staging** (launcher drag+bounce+minimize · 30-min session
    model · 👍/👎 rating · Support analytics + channel segregation). Next: owner verifies → promote to prod.
- **✅ PROMOTED TO PROD (Aug 13, commit de664e9, widget v21, zero-downtime):** master fast-forwarded from
  staging; both web workers rolled healthy. Prod smoke: widget v21 served, analytics 401 without staff
  auth, homepage page sets `NSW_CHANNEL='homepage'`, `support_analytics(30d)` runs clean on the prod DB
  (19 historical sessions, all `web`), rating/closed_at columns added to prod schema (additive). Cloudflare
  gets a fresh URL from the v21 bump. **Entire chat enhancements batch is LIVE.** Staff announcement in
  ANNOUNCEMENTS.md flipped to READY-TO-SEND (owner reviews + sends).
- **✅ LIGHT-MODE + MOBILE NITS FIXED (Aug 13, commit 4266eb2, prod):** from owner phone screenshots.
  (1) Business Analytics stat cards — white `#f1f5f9` Signups + fluorescent hardcoded colors → theme
  tokens (readable both modes); same for funnel + channel table. (2) Hamburger ☰ `#e2e8f0` →
  `var(--nd-text-primary)` (was invisible in light mode) + thicker bars. (3) Mobile drawer nav darker
  (secondary) + larger (1rem/700) + 48px targets, sidebar 260px. (4) **Bell notifications now open a
  full-text detail modal** — announcements show 📣 + "Tap to read →"; the web/mobile way to re-read an
  announcement in full (previously a click did nothing + body was silently truncated). (5) Dashboard
  notif-dropdown rows `#e2e8f0` → token. Verified live on both prod workers.
- **✅ CLAIMS + SECURITY BATCH (Aug 13, commit a5153d1, prod):** from owner report on branch claim #44.
  - *L2 routing fix:* L2 bucket (`review_outcome=can_fight`) was `AND status='review_delivered'`, so a
    reviewed-GO claim that advanced (L2 paid → queued → **assigned**) silently vanished from L2. Now shows
    every ACTIVE GO claim (excludes only terminal closed/withdrawn/resolved_won/resolved_lost) → branch/staff
    L2 claims track like retail. Added a **Stage** column to the L2 list. Verified #44 back in the bucket.
  - *Paid-L2 badge:* claims list showed a bare **"Lead"** even when the ₹499 L2 fee was paid; now appends
    **"L2 ✓"** (reads `l2_payment_status`). `payPill` takes the claim, not just payment_status.
  - *Raise-a-claim attachments (My Business):* new ops upload endpoint
    `/nidaan/ops/api/my-claims/{id}/documents/upload` (scoped to the staffer's own claim code, mirrors branch
    rules); form now stages multiple files with per-file remove + review-before-submit, then attaches to the
    just-created claim. **Gap fixed:** ops previously had no claim-doc upload endpoint (only view/delete).
  - *Confirm-before-delete (new GROUND RULE, [[feedback_confirm_before_delete]]):* audited every delete/remove
    across ops + dashboard + shared module — all real destructive actions already have a confirm gate (native
    `confirm()` or modal); only false positives found (a view-filter toggle, overlay `.remove()`). New
    attachment feature complies (staged files are pre-submission).
  - *Staff removal + security:* staff JWTs carry **no expiry** and auth didn't re-check DB status, so a removed
    staffer's live session would linger forever. `_get_staff_from_request` now re-checks (cached ~30s) that the
    staffer is active/not-archived. Then **soft-deleted (archived, reversible) PAWAN GORANA** (staff_id=31,
    super_admin) on prod — 3 super admins remain (founder Dushyant Sharma intact); status re-check confirms the
    session is now rejected. Restore via `restore_staff` if ever needed.
  - *Archive = full disconnect (Aug 13 follow-up, commit 704bbb9):* per founder — an archived/deleted
    staffer must get NO notifications, NO Telegram, and no connection to EITHER app. Verified + hardened:
    (a) every staff notification recipient query already filters `status='active'` (most also
    `deleted_at IS NULL`) → no bell/email/push; (b) the bot's `_staff_by_chat` already filters the same →
    an archived staffer can't command @NidaanOpsBot; (c) staff auth re-check (above) blocks the ops portal;
    (d) NEW `_sever_staff_connections()` (called by `soft_delete_staff` + `delete_inactive_staff`) actively
    DELETEs their `nidaan_staff_telegram` devices, clears legacy telegram pointer, sets `telegram_access=0`,
    and DELETEs web-push subs — no residual link; (e) `nidaan_staff` has NO mapping into Sarathi, so an
    archived Nidaan staffer has zero access to sarathi-ai.com. Applied the sever to PAWAN (31) on prod:
    telegram device removed, access=0, pointer cleared.
- **✅ PAID-REVIEW CLASSIFICATION FIX (Aug 14, commit 2c96caf, prod):** owner reported a paid ₹499
  customer (SUHANA #65 / claim #45) showing as **"Lead"** in ops Accounts while the user dashboard showed
  paid. Root cause — TWO disjoint ₹499 funnels: (a) `nidaan_per_claim_purchase` (D2C "buy a review credit")
  and (b) direct review-fee on an advisor-submitted claim (`_finalize_paid_claim` → `nidaan_claims.payment_status
  ='paid'`, review_fee_paid; **no purchase row**). Every "paid/one-time" rollup only tested funnel (a), so
  funnel-(b) payers were invisible. **Unified "paid one-time" = active sub OR paid per_claim_purchase OR a
  claim with payment_status='paid'**, applied read-only (no migration) at 4 sites: `get_all_accounts_admin`
  (account_type per_claim not lead; +direct_paid_reviews; usage cell shows "₹499 review paid"), `_BRANCH_PAID_EXISTS`
  (branch paid/lead counts + is_paid), analytics one-time COUNT, analytics REVENUE (guarded `NOT EXISTS(purchase
  linked to claim)` → no double-count). Verified on prod: 8 accounts (31,40,46,49,56,57,58,65) flip lead→per_claim;
  revenue +₹1996 real, ₹0 duplicated (0 paid claims are purchase-linked). Subscription precedence + branch
  revenue/payout SUM untouched. Internal admin data-accuracy fix — no staff announcement needed.
- **✅ [NIDAAN] MOBILE HOMEPAGE DECLUTTER (Aug 15, commits 3bec3de+032b65c, prod):** owner: mobile felt
  "messy — so many pop-ups". Root cause = multiple auto-firing elements on load. Fixed systematically:
  (a) support teaser (widget v22) narrowed + lifted above the bottom-left Listen button (no overlap);
  (b) audience **Switch** button = amber→pink→purple gradient standout, labelled with the DESTINATION
  ("⇄ Policyholder page" / "⇄ Advisor page", bilingual); (c) 2-min **walkthrough panel is now TAP-ONLY**
  (removed the 1.2s auto-open + open-on-first-scroll/tap); (d) **PWA install banner deferred** 30s + only
  when gate/walkthrough closed + not previously dismissed (× remembers); (e) top nav collapses into a **☰
  hamburger** on mobile (was wrapping to 3 rows) — `navToggle()`, vertical dropdown, closes on link tap.
  First load now = clean page + the single audience entry-gate (or clean page for returning visitors).
- **✅ [NIDAAN] L2 ACCOUNTABILITY + IMPERSONATION UNMASK (Aug 15, commits 17abf6b+757994c, prod):** owner
  wants the REAL person who pushed a claim to ClaimShield always visible, even under impersonation.
  (a) `claimshield_sent_by` column + shown as "👤 name" in the L2 dashboard ClaimShield cell + in the case
  log ("Sent to ClaimShield by <name> — <reason>"). (b) **Staff-impersonation hole fixed:**
  `ops_impersonate_staff` minted a token that was fully the target's identity (real actor lost);
  `create_staff_token` now embeds `imp_by{id,name}`, and new `_actor_label(staff)` returns
  "RealName (as ImpersonatedName)" — used for ClaimShield sent_by AND every `_ops_audit` entry, so the
  audit trail + dashboard never show a masked identity. (c) Backfilled #16 sent_by="Dushyant Sharma" (from
  audit; the recorded actor for that pre-fix push). (d) Deleted the test dummy claim #47 + account 66 (CS
  case 804198 is ClaimShield's to remove). Real sent case remaining for live-push confirmation: #16 (CS 804199).
  NOTE (payment model reminder): a claim is eligible for ClaimShield only if PAID (l2_payment_status='paid'
  OR review paid/subscription); unpaid branch leads show "Awaiting branch ₹499 L2 fee" and are guard-blocked.
- **✅ [NIDAAN] L2 FLOW CORRECTED (Aug 15, commit 55a0276, prod) — owner clarified (logic was inverted):**
  (1) **PAID + reviewed-GO claim AUTO-moves to ClaimShield** — `auto_send_if_eligible()` fired from
  `deliver_review` (retail/sub) + `mark_l2_paid` (branch), idempotent, best-effort, flag-gated
  (`claimshield_auto_send` default ON), sent_by="Auto (payment confirmed)". (2) **DUE claim shows
  "Awaiting branch ₹499 + GST L2 fee" + a manual "Send to CS" override button** — create_case guard
  relaxed to require only `can_fight` (payment NOT required for manual override); the pusher's name
  (real actor even under impersonation) is recorded. Modal shows ⚠️ DUE-override warning vs ✓ paid.
  Auto-send only fires on NEW payment/review events — **existing paid+GO-but-unsent claims (#18,30,37,39,40,41,44)
  still show the Send button** until sent (owner to decide: bulk-send now vs leave).
- **✅ [NIDAAN] ANNOUNCEMENT REACTIONS — WEB (Aug 15, commit 5c3fa5c, prod):** announcements told staff to
  "react 👍" but had NO reaction UI (only broadcasts did). Added: `nidaan_notifications.announce_id` (links a
  bell notification to its announcement) + `nidaan_announcement_reactions` (announce_id, staff_id, emoji,
  **channel** — web/telegram/email so it's tracked across channels; one reaction per staff). `notify_staff_inapp`
  + `_record_notification` carry announce_id; `ops_announce` passes it. `react_announcement()` (toggle/upsert) +
  `announcement_reactions_for()`; `list_staff_notifications` attaches reactions+my_reaction to announcement rows.
  `POST /nidaan/ops/api/announce/{id}/react`. Web UI: 👍✅🎉🙏 bar on announcement notifications in the bell AND
  the full-read modal, live counts + highlighted choice. **Only NEW announcements (sent post-deploy) get the
  bar** (old notifications have no announce_id link). **PHASE 2 (pending):** Telegram inline reaction buttons +
  email trackable react-link (both write channel-aware into the same store) + an **adoption view** (who
  acknowledged vs targeted-but-not).
- **GOTCHA (Aug 12):** committed on `master` while intending `staging` → `git push origin staging`
  was a no-op; staging deployed stale code. Always check `git branch --show-current` before commit/push.

## 71. [NIDAAN] CLAIMSHIELD.IN — L2 LEGAL INTEGRATION (owner Aug 15; Phase 1a LIVE, rest awaiting partner)

**App: nidaanpartner.com only.** ClaimShield.in is the confirmed L2 legal partner ([[project_nidaan_legal_api]]).
When a Nidaan claim is reviewed GO (`can_fight`) + L2 fee paid ("queued for legal"), it transfers to
ClaimShield; ClaimShield works the case and pushes customer-safe status back to the customer's dashboard.

- **Model = PUSH, not polling.** WE POST create-case (our case ref + name/mobile/claim amount ONLY —
  ClaimShield declined extra fields to avoid coupling). ClaimShield stores our ref and POSTs status back.
  **We own de-dup** (they don't dedupe): send each case at most once.
- **Mapping is THEIRS, not ours** (owner decision Aug 15): ClaimShield keeps some internal statuses hidden
  and sends only already customer-safe statuses. So our inbound will DISPLAY their status text **as-is**
  (the `biz_claimshield.py` bucket map stays as an optional fallback only — TODO to switch display to as-is).
- **BUILT + LIVE on prod (Phase 1a, commit babbb2a):** `biz_claimshield.py` (map_status,
  `record_status_update` idempotent, `get_claimshield_state`, outbound `create_case` SCAFFOLD w/
  `already_sent`/`mark_case_sent` idempotency rails — HTTP call NOT written yet). Additive schema on
  `nidaan_claims` (claimshield_case_id/status_raw/bucket/status_at/sent_at) + `nidaan_claimshield_log`.
  Inbound webhook **`POST /nidaan/api/claimshield/status`** — secret-gated (`CLAIMSHIELD_WEBHOOK_SECRET` in
  biz.env; header `X-ClaimShield-Token` or body `token`, constant-time), tolerant of field-name aliases.
  Verified on prod: no/wrong token→401, valid token+bogus case→404, both sites healthy after biz.env edit.
- **Handed to ClaimShield (one-go email):** live callback URL + secret + payload shape + our case-ref format.
  **Awaiting from them:** exact create-case endpoint (path/fields/auth header/response) + part-2 of access key.
- **✅ PHASE 1 COMPLETE + ROUND-TRIP VERIFIED ON PROD (Aug 15):** ClaimShield gave create-case spec —
  `POST https://claimshield.in/api/partnercreatecase`, header `x-api-key`, body {patientName, patientMobile,
  claimAmount, Nidaanpartnercasenumber}, resp {message:"success", caseReferenceNumber}. **Note: use non-www
  host** — www.claimshield.in 307-redirects the POST. `CLAIMSHIELD_API_KEY` (part1+part2 combined) +
  `CLAIMSHIELD_API_BASE=https://claimshield.in` in prod biz.env. `create_case()` implemented (idempotent) +
  **ELIGIBILITY GUARD (owner rule): only reviewed-GO (`can_fight`) AND paid (l2_payment_status='paid' OR
  payment_status IN paid/subscription) — never an unpaid lead**. Manual ops trigger
  `POST /nidaan/ops/api/claims/{id}/send-to-claimshield` (sub_super_admin+, audited). Inbound shows their
  status **as-is**, matches by our id OR their caseReferenceNumber. **Live test:** dummy (claim 47/acct 66) →
  CS case **804198** created; simulated status push (their ref) reflected as-is. Dummy retained pending a REAL
  ClaimShield status-push (to confirm their exact field names), then delete.
- **Remaining:** confirm ClaimShield's real push field names → clean up dummy; **L2 CLAIMS DASHBOARD** (metrics
  top: paid/due/disputed/claim-type/branch-advisors + filters + proper L2 management in the L2 Claims section);
  ops "Send to ClaimShield" button in claim drawer; customer dashboard status+timeline; status-change
  notifications; auto-send on L2-paid (flagged) after manual proven. Open flow Qs: "Waiting for Customer
  Approval" (customer action — approve-API from them?) + "Pending Payment" (extra fee beyond ₹499?).

## 72. [SARATHI] CUSTOMER COMMS RAIL — RCS/SMS via Exotel (owner Aug 14-15; DISCUSSED, parked, not built)

**App: sarathi-ai.com only.** Replacing the broken WhatsApp-Evolution customer channel with an official rail.

- **Why now:** the self-hosted **Evolution/Baileys service is DOWN** — nothing on :8080, no container on the
  server, though `EVOLUTION_API_URL` is still set → every customer WhatsApp send silently fails. Two tenant
  `wa_instances` (14, 27) show stale health=100. Unofficial WhatsApp is unsustainable (ban risk + Meta ToS) →
  **retire, don't revive.** (Advisors' customer reminders are currently NOT going out — adds urgency.)
- **The core model (resolves the repeated churn):** stop making ONE channel do two jobs.
  **Cockpit** = advisor ↔ CRM (rich, free, buttons + voice notes) → **Telegram** (`biz_bot.py`) — KEEP, don't
  touch; UX is improvable *within* Telegram. **Megaphone** = business ↔ its customers (reminders/support) →
  **RCS/SMS** now, official WhatsApp later if Meta clears. Running the CRM *on* SMS/RCS = wrong (text-only or
  billed light-buttons, no voice-note workflow).
- **Direction agreed:** **SMS-first (co-branded under Sarathi's DLT header, business name in content = quick
  setup, ships fast, reaches any phone with no internet)**, **RCS as opt-in rich upgrade** once brand-verified
  (real: Aspero Bonds RCS over Jio confirms India RCS is live), WhatsApp parked (Meta business is restricted).
  **Official rails only** from now — no more gray tech. **Gemini** for AI replies (not Claude). Exotel chosen
  deliberately (SMS+RCS now, **AI voice receptionist later** on same vendor).
- **Integration shape (low-risk):** RCS/SMS = a NEW provider in the EXISTING send abstraction
  (`biz_reminders.py` already "tries channel A, falls back to B" + a "onboard new providers" hook); Evolution
  becomes a disabled provider. New `biz_exotel` module + per-tenant config + feature flag + metered (so it can
  become a **paid Nidaan add-on later** — Sarathi is bundled with Nidaan; premium features aren't free).
- **Phase 1 (when unparked):** outbound reminders only (RCS→SMS fallback, or SMS-first), no AI replies yet.
  DLT (SMS) + Google RCS brand verification are the compliance gates (accept them; the co-branded model does
  ONE verification for all businesses). Also a horizontal-SMB thesis (clinics/lenders/local services), to be
  validated with GoLuQ + one non-financial pilot before going broad. See [[project_sarathi_whatsapp]].

---

## §73 — Sarathi hardening + login gating + platform decisions (Aug 16 2026)

**Shipped (prod, staged+tested):**
- **Dashboard freezes** — Marketing Studio + WhatsApp tabs show a bilingual (EN/HI via data-i18n) "Coming Soon" card and hide their unfinished content. Reusable `.card uc-banner` + sibling-hide CSS (`#tab-x > .uc-banner ~ *{display:none}`) + `UC_LOCKED{whatsapp,marketing}` guard skips the tab loaders. TO UNLOCK: delete the `.uc-banner` div + set `UC_LOCKED[tab]=false`. (commit 16ac182)
- **Login gating** (`sarathi_biz.py` + `static/login.html`, commits 3505faa/f4c3ce9): unregistered phone/email/Google now return `code=not_registered` + friendly trial message at BOTH send-step (`send-otp`, `send-email-otp`) and verify-step + `/api/auth/google`; login.html shows a prominent "🎉 Start Free Trial" CTA and no longer wrongly advances to the OTP step on a cross-product `conflict`. EXCEPTION: `_try_bundle_login(email)` find-or-provisions the Sarathi tenant for an active Nidaan bundle (reuses `nidaan._provision_sarathi_bundle`). Safety switch `SARATHI_LOGIN_GATING=0` disables just the bundle fallback. Only the not-found branch changed — success path (registered users + Google) untouched.

**Verified (read-only):**
- **Trial cap = 7 days**: `TRIAL_DAYS=7` single source; `check_subscription_active()` + `/api/` middleware enforce expiry (403 on CRM, auth/pay/help open); Nidaan bundle bypass via `bundled_until`.
- **Calculators/Quotes**: `biz_quotes.py` math internally correct (indicative, disclaimed). SOURCE = curated static rate-cards (FY24-25) → staleness risk; tenant rate-card upload override exists. TODO: refresh cadence + data-vintage label.

**Infra cleanup:**
- **Evolution/Baileys**: FOSS (no license fee) BUT runs on a **LIVE, PAID Hetzner VPS** `ubuntu-4gb-sin-1` (`5.223.64.25`, 4GB Singapore, root via `id_ed25519`) — verified up 96d with evolution+pg+redis running = a real monthly bill for a now-dormant service (WA frozen, sessions already broken). App history: Oracle (`140.238.246.0`) → **Contabo** (`84.247.172.252`, current app server, no Docker); Evolution always lived on the separate Hetzner box. Neutralized `EVOLUTION_*` keys in Contabo `biz.env` (`#DISABLED_`, perms kept 600, health 200); `WHATSAPP_*` (Meta) parked. **COST-SAVING ACTION (owner):** DELETE the Hetzner server in the Cloud console — powering off does NOT stop Hetzner billing. Nothing to preserve. See [[infra-server-access]].

**Team-member auth (found, current state):** web/mobile login = phone/email **OTP** (no passwords) + Google; onboarding = admin invite (`/api/admin/invite` → `/invite` → accept); offboarding = `/api/agents/{id}/deactivate` (owner-only, Team+) sets `is_active=0` → blocks NEW logins everywhere (all login lookups filter `is_active=1`). GAP: `get_current_tenant`/`get_optional_tenant` read from JWT with no per-request DB check → a deactivated member's OPEN session survives to token expiry (~24h). FIX PLANNED: cached ~30s `is_active` re-check (mirror Nidaan `_staff_still_active`) → one deactivate button = instant cut across web+mobile+telegram.

**Decisions locked (builds pending):**
- **Telegram Voice CRM for subscribers** — one bot PER FIRM (BotFather token → webhook, routed by token); **SINGLE-FIRM agent model** (agent must leave before joining another firm — data-security trust guarantee, surface in invite copy); team member = **assigned-leads-only**; unified onboarding/offboarding + one deactivate button; voice-first, context-aware, member-support role; 10-min setup guide; full fallbacks. See [[project_sarathi_tgcrm]]. DESIGN DOC before code.
- **Homepage chatbot** — reuse Nidaan support widget, Sarathi skin + curated KB + DB-backed pricing, host-gated (`_is_nidaan_host`), sales-aware (Start Free Trial), ticket escalation, mobile-first.
- Ground rule reaffirmed: entire sarathi-ai.com must work flawlessly on iOS/Android mobile web (dedicated mobile audit item).

---

## A74 — Nidaan payment robustness + claims-visibility fix (Aug 17 2026)

**Context:** founder flagged NidaanPartner payment-failure noise + a claim visible in the "Pending Reviews" widget but missing from All Claims/search. Also a standing directive: keep Sarathi-AI.com and NidaanPartner.com **separate** (only the bundle couples them). All work below is Nidaan-only.

**Emergency fixes (prod, verified):**
- **Worker crash-loop** — `sarathi-worker` was crash-looping (~every 17s) on a revoked legacy `@SarathiBizBot` token (python-telegram-bot `InvalidToken` at startup), silently killing the scheduler, Nidaan ops bot, reminders and digests. Wrapped `start_master_bot`/`start_all_tenant_bots` in try/except → `NRestarts=0` stable.
- **SMTP 535 "false alarm"** — every "SMTP failed" was followed by "Brevo ✓": mail WAS delivering; dead Gmail creds only. Gated Nidaan Gmail SMTP behind `NIDAAN_SMTP_ENABLED` (default off) → Nidaan mail goes **Brevo-first**. (Owner optional: regen Gmail app password → set flag on.)

**Payment features (prod, verified):**
- **A — customer retry link:** on `payment.failed`, resolve the customer email (event → account), mint a fresh Razorpay link, email it (`_send_customer_retry_link` + `_nidaan_retry_email_html`). Fires for all payment types.
- **B — account pay-status red-flag + Mark-paid:** `get_all_accounts_admin` now derives `pay_status` (paid / attempted / halted / none) via an `unpaid_links` subquery; ops accounts list shows 🟡 payment-pending / 🔴 auto-pay-failed badges. **Super-admin-only** `POST /nidaan/ops/api/accounts/{id}/mark-paid` for offline/QR payments → `create_subscription(...MANUAL:ref...)` (+bundle provision if plan carries it) + `_ops_audit`.
- **C — auto-pay audit PASSED:** recurring path (`/nidaan/api/subscribe/recurring` → `create_nidaan_recurring_subscription`) creates a **Razorpay Subscription** (mandate/auto-pay authorised at checkout); `subscription.charged` auto-renews; fallbacks already robust (`HALTED` → alert+mark-failed, mandate-pending nudge). Active subs carry real `sub_…` ids = mandate is being collected.

**Claims-visibility fix (prod, verified) — commit 4a51eb6:**
- **Root cause:** two ₹499 funnels. `nidaan_claim_499` (advisor-lead) creates a real `nidaan_claims` row → visible. `nidaan_review_999` (D2C direct purchase) only wrote a `nidaan_per_claim_purchase` row → showed in the "Pending Reviews" widget but was **invisible in All Claims / search / filters / assignment** (those read `nidaan_claims`). GOURAV PANDIT (purchase #2, paid) was exactly this.
- **Fix:** new `nidaan.ensure_claim_for_paid_purchase(purchase_id)` — idempotently materialises a `nidaan_claims` row from a paid purchase's intake details (`payment_status='paid'`, `origin='d2c_review'`) and links it back (`linked_claim_id` + `converted_to_claim_id`). No-op if not paid / bare credit (no details) / already converted. Wired into **BOTH** payment-success paths (client verify @ `pay-verify` + webhook `nidaan_review_999` safety-net), each guarded so a claim-creation hiccup never fails payment confirmation. Now both ₹499 funnels land uniformly in the claims workspace.
- **Backfill:** ran the helper over all paid+unlinked+with-details purchases → GOURAV purchase #2 → **claim 50**. Verified: appears in `get_all_claims_admin`, `get_claims_ops` list, and search by name (any case) + phone.

---

## A75 — Sarathi public-site mobile audit (Aug 17 2026)

**Method:** drove headless Edge over the DevTools Protocol with true mobile device emulation (`Emulation.setDeviceMetricsOverride` 390×900, `mobile:true`) and measured `documentElement.scrollWidth` vs the 390px viewport per page — the objective "does the page scroll horizontally" signal. (Plain `--window-size` headless screenshots WITHOUT emulation are misleading — they don't apply the viewport meta and falsely show right-clipping; always emulate.) Tool: `scratchpad/overflow.js`.

**Result — 13 pages measured; the public site is mobile-clean at 390px** (`scrollWidth=390`): `/`, `/about`, `/features`, `/calculators`, `/support`, `/telegram-guide`, `/getting-started`, `/demo`, `/partner`, `/login`, `/onboarding`, plus `customer_portfolio.html` and `invite.html` (both fluid, hold at 390 despite 0 media queries). Elements flagged as "overflowing" on `/` (a comparison `<table>`) and `/demo` sit inside `overflow-x:auto` wrappers and scroll internally — page width stays 390 (acceptable).

**One real bug found + fixed (commit 77c409d, deployed + prod-verified):** `/help` measured `scrollWidth=546`. Cause: header nav (Home/Help/Privacy/Terms + EN/हिं lang toggle + theme toggle) in a single non-wrapping flex row + an 80px logo. Fix scoped to `@media(max-width:640px)`: navbar `flex-wrap`, nav drops to a full-width wrapping second row (removed per-link left-margins), logo image → 44px. Re-measured 390 / 0 overflow.

**Authenticated dashboard mobile pass — DONE (Aug 17, commit 804bf77).** Minted a real session token server-side for tenant 37 (`dushyant@nidaanpartner.com`), injected via CDP (localStorage + cookie), skipped onboarding (`skipOnboarding()`), and walked all 14 owner-visible tabs via `switchTab(...)` at 390px. **All 14 tabs: 0 horizontal overflow** (off-canvas `#sidebar` at left:-260 is correct hidden-drawer behavior). Visual spot-checks (overview/leads/quotes/ai) all mobile-clean. **One bug found + fixed:** the header title comes from `_dt('tt_'+tab)`, which returns the raw key when missing — `tt_quotes`/`tt_marketing`/`tt_microsite` had no entry, so those tabs showed a literal "tt_quotes" header. Added EN+HI titles; verified "💰 Quote Compare" renders on prod. Tooling: `scratchpad/dash_tabs.js` (measure) + `dash_shots.js` (screenshot). `admin.html`/`superadmin.html` (2 media queries each) remain a lower-priority staff-tool pass.

---

## A76 — Branch one-click login + Google sign-in UX (Aug 17 2026)

**Nidaan branch login — one-click link + emails (commits c50722d, 31a035b; prod-verified).** Previously the branch portal emailed only an OTP code (no link) and creating a branch sent no email at all.
- New magic-link token `create_branch_magic_token`/`verify_branch_magic_token` (typ=`nidaan_branch_magic`, bound to branch_code+email, short-lived) + `GET /nidaan/branch/magic` landing → re-checks branch ACTIVE → mints a normal `nidaan_branch` session → hands it to the portal via URL fragment `#t=…` (never hits server logs; page stores it + `history.replaceState` clears it). Expired/inactive → `/nidaan/branch?e=expired|inactive` with a clear message.
- `email_svc.send_nidaan_branch_login_email()` — big one-click "Log in" button + OTP code fallback, mobile-first, sent as **Nidaan Partner → info@nidaanpartner.com** (from_name starting "Nidaan" selects `NIDAAN_FROM`).
- Wired: **branch create** (`ops_create_branch`) emails a welcome/login email (72h magic link); **branch request-otp** now sends OTP **plus** a 20-min one-click link.
- **Bug caught in verification + fixed:** `datetime.utcnow().timestamp()` is naive-local → shifts the epoch by the server's TZ offset (Europe/Berlin **+0200 CEST**). Long-lived session tokens absorbed it; the 20-min magic token was born ~100 min **pre-expired** → one-click login always failed. Fixed to `int(time.time())`. (The other token helpers still use the old pattern but their multi-day lifetimes absorb the 2h shift — noted for future short-token work.) Verified: valid token → 303 → `#t=<session>`; bad → `?e=expired`.

**Sarathi Google sign-in UX (commit 5de6aa4; client-side, needs a live human try).** Users clicking "Sign in with Google" got no feedback until after picking an account, and clicking the page closed Google's popup silently. Now: the instant focus moves **into the Google button iframe** (`window.blur` + `document.activeElement` is the `accounts.google.com` iframe — distinguishes a real click from an alt-tab), a **blocking** wait overlay appears ("Waiting for Google… don't close it") with a **Cancel** escape hatch. A focus-return watchdog (2.5s grace) clears the overlay and shows "Google sign-in didn't finish — tap to try again" instead of a silent dead-end. `onGoogleCredential` cancels the watchdog and proceeds. Success path unchanged. `login.html` still measures clean at 390px.

---

## A77 — Nidaan branch/staff attribution gaps fixed (Aug 17 2026, commit 990794e)

Founder spotted a branch (BIAORA-01) showing 0/0/0 signups despite an existing claim, and a subscriber (Manish #72, referred by staff Avi `SP-GADPB2`) not appearing on the staff dashboard/ops, plus a lower-cased name. **Not latency/space — three concrete code gaps:**

1. **Branch reconciliation counted only REFERRED accounts.** `list_branches` counted `nidaan_accounts.branch_code`, but a branch that RAISES a claim for a walk-in uses a **house account** (blank branch_code) with attribution on `CLAIM.branch_code` + `origin='branch'`. So a branch that had only raised claims read all-zeros. Fixed: signups/paid/unpaid now = referred accounts **+ branch-raised claims** (`ref_signups`/`raised_claims` exposed separately). BIAORA-01 → signups 1 / unpaid 1. Revenue still = subscription rupees only (review-fee revenue for paid raised claims = noted TBD; share math untouched).
2. **Referral dropped on Google signup.** `nidaan_start.html` + `nidaan_signup.html` Google-signup fetches sent `{credential, plan}` but **not `branch_code`**, so `?ref=` attribution was lost for every Google signup — even though the backend + `is_valid_ref_code` already accept staff codes (`SP-xxxxxx`). Fixed: both forward the captured ref. (Sarathi's own `/api/signup/google` already sent `referral_code` — unaffected. Password/email signup already passed it.)
3. **Name not upper-cased on Google signup.** `create_account_google` inserted `owner_name` raw; `create_account`/`submit_claim` apply `_capname`. Added `_capname`.

**Backfilled the reported account:** #72 → `MANISH RATHORE`, `branch_code=SP-GADPB2`, `source_channel=staff` → now shows on Avi's "Your Business" (signups 1 / paid 1 / ₹590). New signups are correct going forward.

## A78 — Nidaan ops attribution UX follow-ups (Aug 17 2026, commit 0706837)

Four more founder-reported items after A77:

1. **Accounts BRANCH column showed a bare code.** `get_all_accounts_admin` now LEFT-JOINs `nidaan_staff.referral_code` + `nidaan_branches.branch_code` and derives `ref_kind` (staff|branch) + `ref_name`; the ops accounts table renders "Name / 👤 staff|🏢 branch · CODE" (Manish → *Avi · 👤 staff · SP-GADPB2*).
2. **Staff "My Business" showed a count, not WHO.** New `nidaan.get_referred_accounts(code)` + `referrals[]` on `/nidaan/ops/api/my-business`; the view lists each referred subscriber (name, plan, Subscribed✓/unpaid, joined). Avi → Manish (silver, paid).
3. **Phone field accepted non-phone values.** The branch **house account** (`get_or_create_branch_house_account`) seeded `phone="HOUSE-<code>"`, which leaked into the visible profile phone when a super-admin used **↪ Enter** (impersonate → the house account's subscriber dashboard). Fixed: house phone is now BLANK (safe — the phone unique index is `WHERE phone != ''`), and **7 existing** house phones were backfilled to ''. `/nidaan/api/profile` now requires phone to be blank or a real 10-digit number (digits-only), so no code/label can land in the phone field again.
4. **Pricing ₹500+GST=₹590 vs the ₹499 the founder expected — NOT a bug, a config choice.** Silver subscription base = **₹500** (`PLAN_LIMITS.silver.price=500`, `NIDAAN_RAZORPAY_PLANS.silver.amount_paise=50000`); GST 18% is added on top by Razorpay → **₹590** (what Manish paid). The **₹499 is the per-claim REVIEW fee** (D2C one-time), a different product. Plans are super-admin editable (DB config): to make Silver read ₹499-base it'd become ₹588.82 incl-GST (ugly); cleaner to pick a round customer-facing number (e.g. keep ₹590, or set a GST-inclusive round price) and back-calc. **Left to founder — no money math changed.** [SUPERSEDED by A79 #1 — the config price now DOES drive the recurring charge.]

## A79 — Pricing→config sync, light-mode contrast, Suhana staff/branch cleanup (Aug 17 2026, commit 457bcb8 + data)

1. **Recurring subscription price now follows the super-admin config.** `create_nidaan_recurring_subscription` was pricing from the hardcoded `NIDAAN_RAZORPAY_PLANS` seed (Silver ₹500→₹590), while the pricing page + `nidaan_plans_config.price_paise` said ₹499. Fixed: base amount now = `get_plan_cfg(plan)["price_paise"]` (fallback to seed). The Razorpay plan is **versioned by the actual charged amount** (`tag …_a<paise>`), so a price edit spins up a NEW Razorpay plan and existing autopay mandates stay on their old `plan_id` → **auto-grandfathered**. New Silver = ₹499 base → **₹588** (₹499+18% GST) vs old ₹590. **OPEN founder decision:** ₹499+GST=₹588.82 isn't round — options: keep GST-on-top, make ₹499 **GST-inclusive** (customer pays exactly ₹499), or set base ₹500 (→₹590). Not decided → left as-is (config base + GST on top, matching how Manish was charged).
2. **Light-mode invisible text.** Two ops info boxes hardcoded `color:#bae6fd` (light blue) on low-opacity tint backgrounds → invisible on the light-mode near-white bg (branch-login help box + `#tgLoginBox`). Switched to `var(--nd-text-secondary)` (theme-adaptive). Boxes on SOLID dark backgrounds (toast `#065f46`, SUB badge `#1e3a8a`) were left — readable in both themes.
3. **Suhana Jain staff-vs-branch.** Confirmed model: **staff do everything from "My Business"** (refer subscribers, refer ₹499 one-time review customers, raise retail claims) — no need to also make them a Branch. Suhana (staff #12, code `SP-EE53CU`) had a mistaken **branch IND-02** (already `disabled`) with ONE orphan claim (#31 Vinay Solanki, unpaid lead, on IND-02 house #50). Migrated #31 → her staff attribution (account→SP-EE53CU house #63, branch_code→`SP-EE53CU`, name capped) so it shows on her My Business (**claims_raised 2→3**); IND-02 house now has 0 claims (orphan-free). **Left the disabled IND-02 row in place per founder ("remove later").** Note: **PUN-02 "Pawan Branch"** (disabled, personal name) is the same staff-as-branch pattern — flag for the same cleanup.

## A81 — NidaanPartner self-onboarding user guide (voice + readable), Aug 17 2026 (commits bf29ff8/0232a2b/08a94ba)

Founder ask: every Nidaan dashboard (subscriber, branch, staff) should have a **self-onboarding guide** — on landing it greets and **speaks a step-by-step walkthrough** (so users listen instead of read), **Hindi by default** + English toggle, a persistent **Listen button** to replay, and a **readable** version too. Decided (via AskUserQuestion): **voice panel + readable page** style (not a highlight tour), **browser Web Speech** TTS (free, matches homepage), **subscriber dashboard first**.
- **`static/nidaan_guide.js`** — reusable, self-contained engine: floating "📖 गाइड सुनें" button → panel with a language toggle (हिंदी default / EN, remembered in `localStorage`), Play/Pause/Stop, an intro card + numbered step cards (readable), and TTS narration that reads greeting→steps and **highlights + scrolls to the current step**. Browser autoplay policy → panel **auto-opens on first visit** (visual greeting) but voice starts on the user's **one tap**. Voice picks a hi-IN / en-IN voice (prefers female/Google/Microsoft), chunks by sentence for reliability. `NidaanGuide.init({key,title,greeting,steps})`. z-index above the PWA install banner.
- **Subscriber dashboard** (`nidaan_dashboard.html`) — mounted with **9 bilingual steps** (raise a claim review → upload docs → pay ₹499 → track status → read findings → choose a plan → save the 3 numbers → profile/settings → get help). **Verified live** (rendered logged-in as a subscriber): button present, auto-opens, 10 cards, **Hindi default** ("▶ सुनें").
- **CF cache gotcha hit + fixed:** editing `nidaan_guide.js` didn't take effect because CF serves `/static?v=1` immutably — bumped the tag to `?v=2`. (Remember to bump `?v=` on every `nidaan_guide.js` change.)
- **Account-aware (commit b1e3e97):** founder caught that a paid SUBSCRIBER was wrongly told to "pay ₹499" (that's the one-time flow). The subscriber-dashboard mount now reads `/nidaan/api/me` `account_state.type` and mounts the matching guide: **subscriber** (type=subscriber) → "your {plan} plan includes reviews, NO ₹499 per review" + a step promoting the bundled **free Sarathi-AI.com CRM**; **one-time review** (retail/new) → the "pay ₹499" step + upsell to a plan (with free CRM). Keys differ (`subscriber` vs `review`) so first-open flags don't collide. Verified live: subscriber shows no pay-499 step + CRM step; retail (#64) shows the ₹499 step + upsell.
- **Branch dashboard guide (commit b1e3e97):** `nidaan_branch.html`, gated on branch login. 7 steps: file a customer's claim → docs → track filed claims → **share referral link to bring advisors** → **"pitch the free Sarathi-AI CRM to advisors"** (grow advisor base → later upsell Sarathi-AI premium AI) → earnings/report → help. Verified live (BIAORA-01).
- **Guide v2 — mic-in-menu + Hindi-default + language sync (commits 847c063/eaf34c7).** Founder feedback: on mobile the floating button is awkward; put a **mic in the top menu**; and the Hindi voice mismatched the English UI. Rebuilt: `nidaan_guide.js` v2 mounts a **mic control into a host top-menu slot** (`cfg.mount`) — compact play/pause pill + a ▾ to expand the readable steps (floating-button fallback kept). **Two-way language sync:** `cfg.onLangChange` fires when the user switches language in the guide (→ dashboard switches too); `NidaanGuide.setLang()` lets the dashboard's own toggle drive the guide. **Default Hindi** everywhere. Subscriber dashboard: added `#guideMic` slot, wrapped its `setLang` to sync the guide, default lang → `'hi'`. **Leak fixed:** `nidaan_login/start/signup/review` defaulted to English (navigator-based) and wrote `nidaan_lang`, so the dashboard inherited `en` — flipped all four to `|| 'hi'`. **Verified live:** dashboard loads `body hi`, mic "गाइड" in the top bar, Hindi subscriber content, and clicking **EN in the guide switched the whole dashboard to English** (body + steps). ?v bumped to 3 (bump on every engine change — CF caches /static).
- **Branch dashboard migrated to the mic engine (commit a56df6e):** `#guideMic` slot added to the branch nav, `?v=3`, Hindi default; verified live (mic in nav, no floating fallback, 390px no-overflow, panel fits viewport). Branch UI is **English-only** (no bilingual toggle) so there's no dashboard language to sync — the Hindi voice+readable guide explains the English sections (helpful for Hindi users). **Note:** making branch/staff dashboards themselves fully bilingual (Hindi default) is a larger separate task, flagged to founder.
- **COMPLETE (commit 8708a92): single content source + staff guide + chatbot.** `biz_nidaan_guide.py` is the ONE source of truth (contexts: subscriber/review/branch/staff, bilingual) with `get_context()` + `kb_text()`. `GET /nidaan/api/guide?ctx=…` serves it (Nidaan-gated). All three dashboard widgets now **fetch** from it (subscriber account-aware via /me, branch, staff) instead of inlining — edit the module once, every guide updates. The **Nidaan support chatbot** (`biz_ai.nidaan_support_reply`) appends the same `kb_text()` to its KB → answers "how do I…" from the identical source (verified: asked "do I pay ₹499 if I have a plan?" → correct plan-aware answer). **Staff/ops guide live** (`#guideMic` in the ops topbar, ctx=staff, 9 steps: Overview→Claims→₹499 reviews→Tasks→Accounts/payments→Support→My Business→Branches). All verified live + mobile-clean (390px, mic in top menu, Hindi default). 
- **Audio-not-starting bug FIXED (commit 9ad6a39).** Tapping the top-menu mic played an EMPTY queue → no audio, because `buildQueue()` only ran inside applyLang's `if (G.panel)` block and the mic doesn't open the panel (the in-panel ▶ worked because opening the panel built the queue). Now buildQueue() runs on init + a safety in play(). Also replaced the look-behind sentence-split regex (breaks older mobile Safari/webviews) with a compatible match, added `speechSynthesis.resume()` after speak (mobile starts paused), and set **voice = Hindi default on all dashboards** (lang:'hi'). Bumped engine to `?v=4`. Verified live: mic-tap (panel closed) → playing state + `speechSynthesis.speaking=true`, 28 voices.
- **Founder decision (Aug 18):** NO heavy lifting — do NOT bilingual-ize branch/staff dashboards; keep each dashboard in whatever language it is; the **voice is always Hindi**. So branch/staff UIs stay English; the Hindi guide explains them. (bilingual-dashboards item closed as "won't do".)
- **Open:** founder **voice test on a real phone** (headless proves it speaks; can't judge Hindi voice quality/pacing). (their own top-menu slot + Hindi default + lang sync); optionally Hindi-default the marketing/index pages; **centralize guide content server-side** (single source) and **feed it to the chatbot** so product-help questions answer from the same content (founder ask). Plus the founder **voice test on a real phone** (headless has no audio).

## A80 — Sarathi homepage AI guide chatbot (Aug 17 2026, commit 99c37d4)

Shipped the agreed **homepage chatbot** for sarathi-ai.com — an anonymous, sales-aware product guide.
- **`biz_ai.sarathi_guide_reply(message, history, lang, facts_block)`** — Sarathi-specific KB (`_SARATHI_GUIDE_KB`: what it is, ₹199/mo + 7-day free trial, Telegram voice CRM, SOLO/Team/Enterprise, Nidaan bundle) + prompt, reusing the shared Gemini plumbing (`_ask_gemini`/`_clean_json`/`_SUPPORT_LANG_RULE`). Bilingual EN/HI/Hinglish (matches the visitor). Returns `{answer, cta, escalate}` where `cta ∈ trial|human`. Anonymous only — no account/Nidaan data.
- **`POST /api/guide/ask`** — **Sarathi host-gated** (404 on the Nidaan host, keeps the app boundary), rate-limited 20/min, stateless (client holds history, capped 8 turns), safe fallback text on AI failure.
- **`static/sarathi_guide_widget.js`** — self-contained, mobile-first (full-width bottom sheet <480px), Sarathi-teal skin, typing indicator, greeting, and CTA buttons: **"🎉 Start Free Trial"** (→ `/#pricing`) on buying intent, **"💬 Talk to our team"** (→ `/support`) on human/escalate. Mounted on `index.html` (defer).
- **Verified live:** pricing Q → correct answer + `cta:trial`; billing/refund Q → refuses account data + `cta:human` + `escalate:true`; Hinglish Q → replies in Hinglish + nudges trial; Nidaan host → 404; widget button + panel render on the mobile homepage.
- **V2 ideas (not built):** DB-backed pricing facts (currently KB-embedded ₹199), thread persistence + human-handoff into a Sarathi support ticket, richer KB, chat analytics.

## A82 — Ops fixes batch: claims-assign, ClaimShield doc API, SA impersonation, tgcrm GA, date+time (Aug 18 2026)

- **Claims assignment for admins (commit f0a99e1).** sub_super_admins saw the claim assign box but couldn't populate it — the drawer fetched `/nidaan/ops/api/staff` (super_admin-only). Switched to the all-staff `/assignees` list (via `_loadAssigneesOnce`, same source tasks use). Backend + `canAssign` already allowed all staff. Verified: admin gets 23 assignees.
- **ClaimShield doc-fetch API (commit 55a6a09).** New `GET /nidaan/api/claimshield/case/{claim_id}/documents` — inbound API for ClaimShield.in to pull an L2 claim's docs. Auth = `x-api-key: CLAIMSHIELD_PULL_KEY` (dedicated, separate from outbound key, constant-time); scoped to claims ALREADY SENT (`already_sent`); returns short-lived HMAC-signed expiring download URLs; every pull audited. **[OWNER] set `CLAIMSHIELD_PULL_KEY` in biz.env + share with ClaimShield.** Today `create_case` sends only metadata + `Nidaanpartnercasenumber`(=claim_id) — no docs; ClaimShield calls this endpoint with that case number.
- **Mark-paid audit (answered).** Tracked in `nidaan_audit_log` action=`account.mark_paid` (who/role/when/account/IP), viewable in ops Activity log (filter by action); subs stamped `MANUAL:`. 0 used so far.
- **SA impersonation FIXED (commit cc6c012).** Two bugs: `window.open()` ran AFTER `await fetch()` → browser pop-up-blocked it (looked dead); now the tab opens synchronously in the click gesture, URL set on token return, blank tab closed on failure. And ~1/3 of tenants had no `role='owner'` agent → backend 404; now falls back to any active agent.
- **Telegram CRM → GA (biz.env).** Was beta-only (`SARATHI_TGCRM_BETA_TENANTS=37`); set **`SARATHI_TGCRM_ENABLED=1`** in `/opt/sarathi/biz.env` (health-gated restart of web@1/@2 + worker). `/api/tg/status` now `enabled:true` → the Telegram CRM tab shows for ALL owners. (Server-only env; not in git.)
- **Date + TIME in ops (commit cd6b8f3).** `fmtDate()` now returns date+time IST (~20 log/history call-sites). Remaining: ~15 inline `.slice(0,10)` in ops + other dashboards → follow-up sweep; new code should use `fmtDate`/`fmtDateTime`.
- **Sarathi homepage chatbot is STATELESS** (`/api/guide/ask`) — retail chats do NOT create tickets/threads or land in a staff inbox. Sarathi has form-based `/api/support/tickets`, but a live homepage/retail **support-chat inbox** (persist thread + staff reply, like Nidaan's `nidaan_support_*`) is **yet to build**.
- **Business-visibility money model LOCKED (founder, Aug 18):** commission stays **%-based (recurring, NOT per-claim** — subscription auto-pays monthly), with the **₹ amount + calculation shown** on the staff/branch dashboard; **per-staff / per-branch overrides from /superadmin**; payment-failure/auto-pay events **trigger only the superadmins + the related staff/branch** (all channels), not everyone; staff/branch see **everything** about whomever they referred. To build phased.

## A83 — Sarathi retail support inbox + AI salesman upgrade (Aug 18 2026, commits 3eacf94/c980cb9/c2a329e/33e5eed)

Supersedes A82's "homepage chatbot is stateless" gap.

- **Capture (v1).** `/api/guide/ask` was stateless → chats vanished. Now every exchange persists to `retail_chat_threads` + `retail_chat_messages` (threaded by an **invisible client `session_key`**; >30 min idle → fresh session = new card). Surfaced in **/superadmin → Support → "💬 Homepage / Retail Chats"** (All / 🔥 Hot leads / ⚠️ Needs-human filters + Total/Today/Hot/Needs-human stats + transcript viewer). Best-effort persist never blocks the reply.
- **v2 — live two-way reply (SHIPPED, commit 95a35aa).** Superadmin transcript now has a **reply composer** → `POST /api/sa/retail-chats/{id}/reply` (stored `sender='staff'`, `staff_id`). The widget (`?v=4`) **polls `GET /api/guide/thread?session_key&after=`** every 5s while open (session-scoped, returns only new staff msgs) and renders them as **👤 Sarathi Team** bubbles. Verified full loop. Visitor sees replies live while chat open, or next visit within 30 min.
- **Threading bug fix.** Widget include was `?v=1` (CF caches `/static` immutably) → browsers ran the old build without `session_key` → one-thread-per-message. Bumped `?v=3`. RULE: bump the widget `?v=` on every `sarathi_guide_widget.js` change.
- **AI upgrade (biz_ai.`sarathi_guide_reply`).** Persona = warm salesman + genuine support. Qualifies (asks name / daily struggle), mirrors visitor language (Hinglish), nudges the free trial. Weaves in **at most one** relatable example from `_SARATHI_STORIES` (S1–S7, tagged "use when") — **never in the first reply, never a fabricated named testimonial**; anti-repeat via `seen_stories` (client-held in localStorage, sent each call; returns `story_id`). Captures **lead_name / lead_contact** + scores **intent** (cold|curious|hot|support) → stored on the thread (`name`, `intent` cols; contact). Inbox shows 📇 name/number + 🔥 hot badge. Verified live: "Rajesh…forgetting follow-ups" → name=Rajesh, intent=curious, story=S1, cta=trial.
- **Honesty guardrail (kept):** stories are illustrative "how advisors use it", not real named customers or invented figures.

## A84 — [NIDAAN] EMAIL UPDATE RADAR — build plan (owner Aug 18-19; design LOCKED, to build)

**Problem.** ~100 escalation customers each hand over a dedicated Gmail (email + app-password). Today **4–5 staff manually open all ~100 inboxes daily** just to detect whether a competent authority replied. Goal: **collapse 5→1** via a flag system + proactive AI monitoring + efficiency metrics, so the team focuses on sales/marketing. **HARD RULE: the UI never shows "IRDA/IRDAI/Lokpal" by name** — those are generic "priority senders" in a founder-managed config. See memory `project_nidaan_email_radar`.

**Locked decisions (founder).**
- **Scope = Option B**: radar (poll + AI triage + flags + dashboard) **+ one-click deep-link** into the exact Gmail thread to act. **NOT** send-as-customer (that's a later Phase C).
- **Cadence = tiered/adaptive**: open/active cases ~15 min, quiet mailboxes ~30–45 min; graceful back-off on Gmail rate-limits.
- **Silence threshold = superadmin-configurable** (N days of no priority reply on an open case → 🟡 "Chase" flag), with an in-app explainer.
- **Assignment = small PODS** (2–3 staff share a mailbox set; survives leave).
- **Working hours = reuse Nidaan support-hours config** (govt authorities don't respond off-hours → don't page staff then; 🔴 may override).
- **Lives in nidaanpartner.com ops**; superadmin/sub-superadmin assign; **modelled EXACTLY on the Tasks module.**

**Architecture (native stack — no Cloudflare/Hetzner).** Poll job in `sarathi-worker` (APScheduler, staggered) → IMAP (imaplib/aioimaplib) fetch envelope + short snippet only (data-minimisation; full body read via deep-link, not hoarded) → Gemini (`biz_ai`) triage → SQLite → new "📨 Updates" ops panel. App-passwords **encrypted at rest** (AES-GCM, key in biz.env, super-admin-only), decrypted in-memory by the worker only. (Migration path to Google OAuth later if founder prefers not to custodian passwords.)

**Flag system.** 🔴 Act-now (priority-sender / deadline detected / asks response) · 🟡 Review or Chase (needs human, or silence-timer fired) · ⚪ Auto-cleared (receipts/marketing/no-reply, collapsed). Two safety nets: (1) **priority-sender list** (founder-managed) = always 🔴 regardless of AI; (2) **silence detection** = the thing manual checking can't do. **Fail-safe: AI unsure/unavailable → 🟡 for a human, never auto-clear on doubt.**

**Tasks-module mechanics (reuse existing Tasks rails).** A 🔴/🟡 flag **auto-creates a radar-item (specialised Task)** assigned to the mailbox's pod (superadmin can reassign). **One item per CASE, not per email** — new emails append + re-notify only on material new activity (no task spam). Lifecycle New→Assigned→**Acknowledged**→**Responded** (deep-link jump to Gmail)→Closed; **auto-reopen** on a new authority email to a closed case. Notifications = Tasks' all-channel triggers to assignee + pod + superadmin, **severity + working-hours gated**. In-thread comments + ack-nudge reuse Tasks. Appears in each assignee's dashboard; superadmin monitors an ops-wide radar board.

**AI at every step:** each item pre-filled with triage verdict + one-line summary + extracted deadline + suggested next action.

**Efficiency metrics:** auto-triage rate (the 5→1 proof), mailboxes auto-checked/day, time-to-first-touch on 🔴, open backlog + aging, coverage (% polled OK / auth-health), flags cleared/person/day, AI cost/day.

**Phases:** P1 mailbox config + encryption + Test-Connection; P2 poll + AI triage + flags (radar read-only); P3 Tasks-integration (auto-create/assign/notify/ack) + deep-link; P4 silence detection + deadline board + metrics; (Phase C later = send-as-customer + AI drafts, needs consent/audit).

**BUILD STATUS (Aug 19 2026): P1+P2+P3 SHIPPED & verified** (commits bcf70e5 / 7014086 / 8d841d6). Module `biz_nidaan_radar.py`; tables `nidaan_radar_mailboxes` / `nidaan_radar_items` / `nidaan_radar_config`. Ops panel **"📨 Email Updates"** (rank-1, near top) with **Radar / Mailboxes / Settings** tabs.
- **P1**: Fernet-encrypted app-password vault (`EMAIL_VAULT_KEY` or JWT_SECRET-derived), IMAP Test-Connection, mailbox CRUD, endpoints `/nidaan/ops/api/radar/*` (admin+). Verified enc round-trip + IMAP path.
- **P2**: worker poll loop `radar_poll_loop` (RUN_SINGLETONS, 15 min, 2s stagger) → incremental IMAP fetch (envelope+snippet, **first poll = baseline only, no backfill**) → `biz_ai.radar_triage_email` (Gemini) → flag (`_decide_flag`: red=priority-sender/authority/legal/court/high; green=receipt/marketing/spam; else amber fail-safe) → `nidaan_radar_items`. Radar view = red-first cards w/ AI summary + deadline + **Open-in-Gmail deep-link** (`rfc822msgid:`). Settings = priority-sender list (always-🔴) + silence-days. Verified: authority→red+deadline, marketing→green.
- **P3**: mailbox `pod_staff_ids` (primary + watchers) + `open_task_id`; item `quick_task_id`. `ensure_task_for_item`: a red/amber item **auto-creates the mailbox's open radar-task in the existing Tasks module** (assigned to primary, pod as watchers, `on_quick_task_assigned` all-channel notify, red→high/amber→normal). **One open task per mailbox = one per case**: further emails append a note + re-notify (red); when the task is done/cancelled the next email **auto-reopens** a fresh one. Config drawer has Primary-handler dropdown + pod checkboxes (from `/assignees`). Verified: red+amber folded into the SAME task, primary-assigned, high priority.
- **P4 (SHIPPED, commit f1fe1ea)**: `run_silence_sweep` (worker every 6h) — open case with no inbound past `silence_days` → 🟡 Chase note on its task + re-notify, once per window (`last_chase_at` idempotency). `radar_metrics` → auto-triage rate (5→1 proof) + coverage + flag counts + deadlines; endpoint `/radar/metrics`; UI metrics strip + **⏰ Deadlines** filter tab. Verified: metrics/sweep/date-logic clean on empty data.
- **RADAR P1–P4 COMPLETE & verified.** Remaining = Phase C (send-as-customer + AI drafts) only, deferred (needs consent/audit).
- **[OWNER]** optionally set `EMAIL_VAULT_KEY` in biz.env; add a real customer mailbox + assign a pod + "🔄 Check now" to see it flow with live mail.

## A88 — Strategic direction (Aug 21 2026): Claimant Portal, radar sustainability, views engine, Telegram office assistant + Doc Splitter bug fix

**DISCUSSION-LOCKED, phased-build to start ~Aug 21 10:30 IST. Founder decisions captured; nothing built yet except the bug fix.** Also: **STANDING RULE reaffirmed** — the master doc + `ANNOUNCEMENTS.md` are updated on EVERY ship as part of definition-of-done, without being asked (founder wants this "auto", not on request).

### Doc Splitter bug — FIXED (commit 83c8a5b)
Broken page thumbnails + **"Job expired — please re-upload"** on export. Root cause: web units run **`PrivateTmp=true`** (each worker gets its own `/tmp`) **and nginx load-balances 8001/8002** → a job saved by one worker was invisible to the next. Fix: job files now live under **`/opt/sarathi/var/docsplit`** (shared; covered by `ReadWritePaths=/opt/sarathi`; NOT isolated by PrivateTmp) instead of `/tmp`. `TMP_ROOT` = `DOCSPLIT_TMP` env or `<app_dir>/var/docsplit`; `var/` gitignored (untracked → survives `git reset --hard` deploys). **General lesson: any per-request local-disk state must live under /opt/sarathi, never /tmp** (PrivateTmp + multi-worker).

### Email Radar — the REAL constraint (reshapes A84/A87)
Founder clarified the true risk: **(1)** customers can't draft authority emails or check inboxes — they just want results (that's why we're the consultant); **(2)** authorities **ban a domain** if many disputes arrive from it, so we **cannot** unify onto `nidaanpartner.com` (my earlier "our own domain" idea is OFF for authority-facing). Gmail is common → not doubted → that's why each policyholder uses an ordinary mailbox. So the per-policyholder-ordinary-mailbox identity is **required** for the authority side. The residual risk is **Google-side** (100 IMAP logins from one server IP looks botnet-like). Sustainable moves (legitimate, consented representation — not evasion): **(a)** provider diversity (add Yahoo now; Outlook later via OAuth as app-passwords die); **(b)** switch *reading* to **auto-forward ingest** (customer sets a one-time Gmail forward → our inbound-parse address; no stored logins, invisible to Google); **(c)** throttle/space sends + **offload most human comms to the Claimant Portal** so the mailbox is touched minimally; **(d)** later OAuth "send-as"/Gmail API (sanctioned). No magic bullet — this is managed risk; the Portal is what structurally shrinks it.

### Claimant Portal (the keystone) — DESIGN LOCKED
Mediators (branch/staff/subscriber) own the *relationship*; the **policyholder owns the *information*** → for doc-requests/follow-ups we reach the **claimant directly, mediator kept in the loop (CC/visibility)**. One **installable PWA dashboard**, mobile-first, with **heavy new-update popups** (web push). **Two provisioning paths, ONE dashboard + ONE consent flow (endpoint uniformity):**
- **Mediated claim** (branch/staff/subscriber raised): no account → **magic-link** (reuse the impersonation/magic-link auth) creates/attaches the dashboard on first click; **link IS the login**, OTP/Google sign-in only for re-entry. Greeting email explains NidaanPartner + reassures. **Do NOT explain the fee calc in the email** — only inside the dashboard.
- **Direct ₹499 claimant** (self-signup, no mediator): **no separate claimant link/page** — the dashboard already exists from signup; the L2 consent simply appears as an **action-card in their existing dashboard**. Skip the intro/greeting. Notifications identical (all channels).
- **L2 consent action-card:** shows dispute amount vs recovered amount, and on recovered amount **"Nidaan The Legal Consultant" takes 15% + 18% GST** — clear line-item calculation + **Accept button = digital acceptance** (timestamped, T&C-version, %-configurable by super-admin, grandfathered). ⚠️ **Founder to get the success-fee T&C vetted by counsel** (possible regulatory limits; I don't assert law).
- **Trigger** at **L2** (and **₹499 reviews**); **manual "re-send / push link" button on the claim** in L2 (if the claimant didn't get the email). **All involved parties notified on all channels** (email/Telegram/dashboard). Consequence: **L2 Claims grows more tabs / bigger tables → drives the Views engine below.**

### Views engine (cross-module, mobile-first) — DIRECTION AGREED
Founder wants Kanban / friendlier views that work on mobile, + per-staff view/filter customization across ALL tabular features (Tasks, Claims, Accounts, …). Plan: a **shared "view engine"** (one component, applied everywhere per endpoint-uniformity): **(1) Saved Views** = per-staff saved filter+sort+grouping with quick-switch chips; **(2) Responsive Board** = real Kanban columns on desktop, **vertically stacked collapsible status-groups on mobile** (never horizontal-scroll columns on a phone — that violates the mobile ground rule); **(3) View switcher** Table ↔ Board ↔ Cards (Cards = mobile default). Roll out on **L2 Claims first** (it's growing), then Tasks/Accounts.

### Telegram = the "office in your pocket" (Q2 expansion) — branded personal AI assistant
Map of run-the-office-from-Telegram: **[LIVE]** tasks (see/create review-gated/pings), claim-activity notify + reply-to-customer, leave/requests, announcements+👍, AI (memory/confirm-to-act/voice/calculators). **[BUILDABLE next]** claims lookup+stage-move+note → radar read/reply in bot → analytics questions per role → payments (create ₹499/link, check paid) → staff mgmt (super_admin). Brand it as each staffer's **personal AI assistant**; add an in-bot "**what do you want to manage from Telegram?**" feedback capture. Announcement updated to motivate adoption.

### A88 BUILD LOG (Aug 22 2026)
- **WHATSAPP CLOUD API LIVE — Phase 0 foundation SHIPPED (Aug 25, commit f28822d):** founder set up Meta WABA **GoLuQ – Digital Consultancy** (WABA `1942085573135209`) + number **+91 83495 04400** (Phone Number ID `1259819740549744`) — now **VERIFIED, quality GREEN, Cloud API**. Business verification done. Permanent System User token + App Secret + App ID stored in `/opt/sarathi/biz.env` (`WA_ACCESS_TOKEN`/`WA_APP_SECRET`/`WA_APP_ID`/`WA_PHONE_NUMBER_ID`/`WA_WABA_ID`; sarathi:sarathi 600, both sites health-checked 200). New isolated module **`biz_sarathi_whatsapp.py`**: `send_template` (business-initiated), `send_text` (24h session), `number_health`, `body_params`, `normalize_msisdn` — all env-configured, best-effort. **Verified end-to-end:** hello_world sent to a real number both via Meta UI AND via our module using the stored token (`ok:True`, message_id returned). **Reminder templates drafted** (renewal/EMI/lapse EN+HI, Utility category) — founder to create+submit in WhatsApp Manager. **NEXT:** send-log table (`wa_messages`) + opt-in tracking + a Sarathi "send reminder" UI (test button first) + data-driven renewal/EMI/lapse sends. Registration gotcha learned: number with 2-step PIN needs old PIN or 7-day wait; number must be off the consumer WhatsApp app first. Strategy (two-app + Nidaan branch reseller) in WHATSAPP_SUBSCRIBERS_PLAN.md §9.
- **TELEGRAM claim WRITES SHIPPED (Aug 24, commit 07f1f86):** from a claim card in the bot (admin+): **💬 Add note** (type/voice → confirm → `add_claim_note` source='telegram') and **➡️ Move stage** (pick from `_TG_STAGES` pipeline → confirm → `update_claim_status`, audited via changed_by_id=staff). Both confirm-gated + role-checked each step; bilingual. CAPABILITIES `tg_claim_actions`. Verified (note add + cleanup, stage move + revert). Customer-facing notify on bot stage-moves = follow-up.
- **TELEGRAM office assistant — claim lookup SHIPPED (Aug 24, commit 8f41de7):** new **"🔎 Find a claim"** menu button (admin+) in @NidaanOpsBot → prompts for claim number/name/phone → `_claim_search` → tap-to-view matches → read-only claim card (`_fmt_claim_card`: status, type, disputed, ClaimShield ref+status, handler), bilingual, voice-compatible. Role-gated server-side each step, NO writes. `_claim_detail`/`_claim_search` helpers. Added CAPABILITIES entry `tg_find_claim` (registry convention). Verified: search→detail→card. **Stage-move (write) deferred to a careful follow-up** (confirm-to-act).
- **CLAIMANT AUTHORIZATION FLOW SHIPPED (Aug 24, commit 9c26aa6):** redesigned per founder. (1) Claimant dashboard shows **NOTHING about fees until the claim is at L2** (`review_outcome='can_fight'` → `is_l2` in api/me); then an **"Authorization"** card with a prominent **"you do NOT need to pay anything now — just Accept"** banner (EN+HI) + the auto-calc + Accept. (2) Ops claim card split: the portal link (status/docs) is available any time; a separate **"⚖️ Fee authorization"** section appears **only at L2** showing the auto-calc (**dispute × 15% + GST**) and a **"📤 Push authorization"** button that **confirm-prompts staff to VERIFY the dispute amount** first, records **who pushed + when** (`consent_pushed_by/at`), and **emails the claimant if not yet accepted**. States shown: *pushed by X · <time>* / *accepted by claimant · <time>*. (3) Endpoint `POST /nidaan/ops/api/claims/{id}/portal/push-authorization` (sub_super_admin+, audited). Accept works on dashboard OR via emailed link → recorded + the tamper-evident **consent-proof PDF** (super-admin download) stays. Verified full push→accept→proof cycle. Auto-send toggle + manual email path from before still apply.

- **SARATHI PAYMENT BUG FOUND + FIXED + RECONCILED (Aug 24, commit 6d1d131):** founder screenshot "subscription done but Verification failed" (paywall). Diagnosis: the S key pair (`RAZORPAY_*`=rzp_live_SPruI…) is valid; payment `pay_TTVzA11HDteI6v` was **captured ₹199** (screenshot OCR'd the id wrong). ROOT CAUSE: `VerifySubscriptionRequest` **required** `razorpay_signature` (`extra=forbid`), but some subscription/UPI-mandate checkout flows **don't return a client signature** → frontend omitted it → **422 → generic "Verification failed"** despite capture. FIX (`biz_payments.verify_subscription_and_activate`): client signature is now a fast-path only; when absent/invalid, verify via the **Razorpay API** (captured in our account, for the authenticated tenant) = source of truth. Model fields optional; paywall + dashboard.html frontends fall back to created `subscription_id` + empty signature. **Reconciled** the real payment → tenant 2 activated (individual, expires 2026-09-23). Proven: robust path logged "verifying via Razorpay API" → activated. (Sarathi payment-receipt email = "not configured" — minor, separate.)
- **SARATHI thank-you page SHIPPED:** `/pay-success` (static sarathi_success.html, EN/HI, mirrors nidaanpartner.com) wired to paywall success + dashboard subscription verify.
- **SARATHI login smoothness + bundle-cache FIXED (Aug 24, commit ebfad81):** (a) **OTP "not smooth"** = email-OTP + signup-OTP `await`ed the Gmail SMTP handshake (10-15s) in-request → changed to `create_task` (background); OTP generated sync, delivery follows → button returns instantly. (b) **Bundle → "Subscription Expired"**: measured — `verify_google_id_token` is FAST (0.47s), server load ~0, so NOT the backend. `check_subscription_active` already honors `bundled_until>=today` correctly. Root of the stale screen: the **paywall (SUBSCRIPTION_EXPIRED_HTML) was served with NO cache headers** (dashboard had them) → a cached old expired screen persisted after (re)activation. Added no-cache/no-store to BOTH /dashboard branches. (Founder's own test tenant 14 had bundled_until=2026-08-05, genuinely lapsed — renew to test.) **Google sign-in ~20s: backend verify is fast → it's CLIENT-SIDE (GSI popup / dashboard SPA load / India→DE RTT). Needs browser devtools Network trace to pinpoint — advised founder.**

- **PAYMENT BUG FOUND + FIXED (Aug 24, commit da7d0c0) — was breaking activations:** founder reported "payment not happening." Diagnosis: Razorpay order-create works (200, live keys valid), webhooks authenticate, frontend uses the order's key_id (no mismatch). BUT the **Razorpay webhook was crashing**: `payment.captured` + legacy-subscription handlers did `notes.get(...)`, and **Razorpay returns EMPTY notes as `[]` (a list), not `{}`** → `AttributeError: 'list' object has no attribute 'get'` → webhook 500 → money captured at Razorpay but **never activated on our side**. Fixed: coerce `notes` to dict at both sites (sarathi_biz ~4581/4695). Also fixed `on_subscriber_signup` selecting a non-existent `plan` column from nidaan_accounts (`OperationalError` on every signup notif) — removed. NOTE: two live key sets in biz.env (`NIDAAN_*`=rzp_live_T… used; `RAZORPAY_*`=rzp_live_S… fallback) — code prefers NIDAAN_, which tested valid.
- **Post-payment THANK-YOU PAGE SHIPPED (commit 05aee5d):** new bilingual `/nidaan/success` (animated tick + `?type=` tailored message + Continue + 5s auto-redirect to dashboard). Subscription (3 redirect points) + ₹499 review now land there; claim flow already had `_claimPaidOverlay` (kept). 
- **PENDING — Authorization flow changes (founder Aug 24, TO BUILD next):** (1) claimant dashboard shows NOTHING about fee/terms until the claim is at **L2** (review_outcome='can_fight'); then show the authorization+accept with "no payment now, only accept" copy. (2) Ops L2 **"Push authorization" button** — records staff name + timestamp, prompts staff to VERIFY the dispute amount first, emails the claimant if not yet accepted. (3) Auto-calc per claimant = 15% of dispute + GST. (4) States: "authorization pushed by X" / "accepted by claimant". Accept on dashboard AND/OR via emailed link → recorded + consent-proof PDF (already built). Needs schema: consent_pushed_by/at; gate consent card on L2; reframe consent→authorization.

- **Radar sustainability — reliability slice SHIPPED (commit 67da189):** (1) **Mailbox-down alerts** — `fail_count` bumps on each failed poll, resets on OK; after **3 consecutive fails** super-admins get an all-channel alert ("mailbox not syncing — authority mail may be missed; re-check app password"), re-alerting ≤ daily until recovery (`_record_poll_failure`/`_alert_mailbox_down`, `FAIL_ALERT_THRESHOLD=3`). No more silent misses. (2) **Keep-alive** — `keepalive_sweep()` daily worker loop does a light IMAP login on active app-password mailboxes idle >20d (the activity signal that stops Google/Yahoo deactivation), stamps `last_keepalive_at`; healthy (15-min-polled) ones never qualify; failures feed the same alerting. Forwarding-only mailboxes (no creds) can't be kept alive by us. Schema: `fail_count`/`fail_alert_at`/`last_keepalive_at`. Verified: cols present, sweep runs (0 = nothing dormant), 3 units active. **NEXT radar slice (bigger):** dual-mode (one-way forwarding / two-way / both) + a single ops "updates" ingest inbox that parses the original recipient to route forwarded mail per-claim + Message-ID dedup + per-mailbox mode badges.

- **Claimant portal richer + ADMISSIBLE CONSENT PROOF SHIPPED (commits a98ac0b/9c2f1eb):** portal now has a "Your details" profile card (name/phone/email) + multi-file upload. `record_consent` now snapshots the EXACT terms text (EN+HI), device (user-agent), name, IP, IST timestamp + a **SHA-256 integrity hash** over the record (grandfathered, tamper-evident) — schema cols `consent_terms_snapshot/user_agent/name/hash`. `build_consent_proof_pdf` (fitz, core fonts, `hebo` bold) → downloadable **"Digital Consent Record" PDF**; super-admin `GET /nidaan/ops/api/claims/{id}/consent-proof` (audited) + **📄 Consent proof** button on the claim portal card. English layout (fitz core fonts can't render Devanagari) — full bilingual text is hash-covered + in DB; notes Section 65B cert available. Verified: 8.6KB valid PDF, full cycle. ⚠️ Admissibility itself is counsel's call.
- **Email Radar SOP SHIPPED (commit 7f440aa):** the connect-mailbox guide now documents **Gmail (app password, existing)**, **Yahoo (app password → Advanced → imap.mail.yahoo.com)**, and **forwarding-only steps for Gmail + Yahoo** (labelled "being added" — per-customer forwarding-ingest is part of the radar-sustainability track). Advanced hint updated for Yahoo host.
- **DISCUSSION — keep Gmail/Yahoo accounts ALIVE (founder Aug 23):** Google deactivates accounts after ~2 yrs of INACTIVITY; the worry is configured mailboxes going dormant. **Finding:** for **app-password (two-way) mailboxes our polling already logs in every 15–45 min = continuous activity → they never go inactive.** Real risk is (a) **forwarding-only** mailboxes (we never log in → can't keep alive without creds; customer must, or use app-password for longevity) and (b) mailboxes paused/purged. **Recommendation:** add a lightweight **monthly keep-alive** (scheduled) that does an IMAP login (NOOP) on every active app-password mailbox that hasn't been polled in N days — login alone is the activity signal, no test-emails needed (quieter, no deliverability/spam risk). Optional belt-and-suspenders: a quarterly self-addressed test email. TO BUILD in the radar-sustainability track.

- **Per-dashboard feature lists SHIPPED (commits ffec51e + 9fe3df1):** registry now **audience-aware** (`audience` field, default `["staff"]`; `features_for`/`speech_text_for`; `build_guide` filters to staff). **Subscriber** advisor dashboard got a "✨ Features" tab (ungated, EN/HI dual-render, per-feature Example, cached-Gemini Listen; `/nidaan/api/features[/audio]`). **Branch** portal got a self-contained bilingual "✨ What you can do here" card (its own EN/HI toggle since the page has no global lang; `/nidaan/branch/api/features[/audio]`). Verified: endpoints gated 401, no cross-audience leakage (staff↔subscriber), 6 subscriber + 5 branch features. **Claimant portal deliberately SKIPPED** (only ~3 features; the whole page already IS that). Voice = cached Gemini everywhere with browser fallback (Tier-2/3 no-Hindi-voice safety).

- **Views engine slice 2 — Saved Views SHIPPED (commit f287e1a):** per-staff named presets on L2 Claims (localStorage) capturing view mode + filters (L2 fee/ClaimShield/type) + search; quick-switch chips apply in one tap, ✕ to delete; bilingual chrome; filter selects gained ids so applying reflects in the controls. **DECISION:** Views engine considered COMPLETE on L2 Claims (the growing pipeline). Rolling the switcher into **Accounts/Tasks is DEFERRED** — both are bespoke, bulk-select/complex renderers and NOT natural pipelines; a rushed bolt-on risks breaking live flows (careful/no-break rule). Do it as a proper shared-component refactor later, not a bolt-on. Saved Views is localStorage (per-device); DB-backed cross-device sync is a later option.

- **"✨ All Features (Listen)" tab SHIPPED (commit 4a4f2c0):** founder wants users to DISCOVER features (adoption). Turns out `biz_nidaan_capabilities.py` already existed as the single-source registry powering the (renamed) ops tab + Telegram help + audio — but was task-heavy/outdated. Backfilled all recent features (Email Updates, Doc Splitter, Claimant Portal, L2 Claims, Views switcher, Deliver Assessment, Analytics, Content) → **32 features**, each with a bilingual **`u` use-case/"Example:"** line shown on-screen AND read aloud. **🔊 Listen = Gemini voice, CACHED (commit 3101cff):** `biz_tts.py` synth→WAV in `var/tts_cache` (once per role×lang, replays free), served by `GET /nidaan/ops/api/capabilities/audio`; falls back to the free browser voice on failure (also rescues Tier-2/3 phones with no Hindi TTS voice). Founder rule: Gemini quality, no ongoing cost → caching achieves both. **STANDING RULE (memory `feature_registry_convention`):** every new feature MUST add a CAPABILITIES entry — this is the founder's "auto-add going forward" (no code introspection; discipline is the mechanism). **NEXT:** per-dashboard feature lists for claimant/branch/staff/subscriber (audience-scoped + plan-gated).

- **ClaimShield API status (Aug 22, dev query):** BOTH dev asks already supported — **no code change needed.** (1) Status webhook `/nidaan/api/claimshield/status` already accepts `Nidaanpartnercasenumber` and matches on OUR claim id first (`extra="allow"`, so keying on our claim no. is the reliable path that avoids the 804203/804188 mismatch); dev should push status keyed on `Nidaanpartnercasenumber` + include `caseReferenceNumber` (self-heals their ref), auth `X-ClaimShield-Token`. (2) Doc-pull `GET /nidaan/api/claimshield/case/{claim_id}/documents` exists (x-api-key `CLAIMSHIELD_PULL_KEY` OR `X-ClaimShield-Token`), returns short-lived SIGNED URLs, scoped to already-sent cases. Next = coordinated LIVE test (create a case that HAS docs → dev pulls). Watch: signed-URL TTL if their fetch is delayed (lengthen if needed).
- **Views engine slice 1 SHIPPED (commit 50b0104):** L2 Claims now has a **Table / Board / Cards** switcher (per-staff choice in localStorage). **Responsive Kanban Board** — claims grouped by pipeline `status` as columns on desktop, **stacked collapsible groups on phone** (never horizontal-scroll columns on mobile, per ground rule; `<details open>` columns + `@media(max-width:640px)`). Cards grid = mobile-friendly. All views share the existing filters + click→drawer. Helpers `_renderClaimBoard`/`_renderClaimCards`/`_l2CardInner` + `_L2_STAGES`. NEXT slices: **Saved Views** (named per-staff filter+sort presets) + roll the switcher out to Tasks/Accounts.

- **Claimant Portal P1 SHIPPED (dormant)** — commits a5d4f84 (foundation) + cc54c1e (slice). Live but nothing links to it yet (held until counsel T&C).
  - Schema `nidaan_claimant_portal` (per-claim `access_token` = revocable magic-link + credential; digital-consent snapshot: accepted_at/terms_version/fee_pct/gst_pct/ip; link-sent tracking). Module `biz_nidaan_claimant.py` (fee_config, compute_fee line-items, ensure_portal[token|no-token], get_portal_by_token, rotate_token, mark_activated/mark_link_sent, record_consent[grandfathered snapshot], portal_state).
  - Endpoints: **claimant** (`access_token` Bearer) `GET /nidaan/claim` (page), `GET /nidaan/claim/magic?token=` (stamps first-open → `#t=` fragment), `GET /nidaan/claim/api/me`, `POST /nidaan/claim/api/consent`; **ops** `GET /nidaan/ops/api/claims/{id}/portal`, `POST …/portal/ensure` (mint+return link); **super-admin** `GET/PUT /nidaan/ops/api/claimant-terms` (fee % + counsel-owned T&C text/version).
  - Config (ops_settings, SA-editable): `claimant_success_fee_pct`=15, `claimant_terms_version`=v1-draft, `claimant_terms_html`=PLACEHOLDER. GST reuses `gst_config()` (now **enabled** on server → 18% shows). Fee calc verified: ₹5L recovered → 15% ₹75k + 18% GST ₹13.5k = ₹88.5k, claimant keeps ₹4.115L.
  - `static/nidaan_claim_portal.html`: mobile-first, **bilingual EN/HI** (full toggle), trustworthy light theme; status pill + success-fee card (dispute-based ILLUSTRATION, GST-aware) + agree-checkbox + digital Accept → `✅ accepted on <date>`. Verified: page 200, api/me 401 w/o token, bad magic → 303 expired, full mint→consent→snapshot cycle.
  - **Two provisioning paths, ONE flow:** mediated = magic-link; direct-₹499 = same consent as an action-card in their existing dashboard (access_token NULL). **Counsel gate** = founder edits `claimant_terms_html`/version in ops Content (SA); acceptances pinned to their version.
  - **Ops UI SHIPPED (commit 177f1ab):** super-admin **"⚖️ Claimant Fee & Terms" editor** in ops Content (fee %, version, T&C text; GST-state note; placeholder warning) → PUT /claimant-terms. Claim-drawer **"🔗 Claimant Portal" card** — shows state (no portal / link issued / opened / fee accepted + %) + **Create/Re-issue & copy link** button (mints magic link, shows+copies it; auto-email deferred). Verified: /admins serves the editor, endpoints gated 401.
  - **Dashboard depth SHIPPED (commit 5a7130e):** api/me now returns a friendly **status timeline** (internal-note-free) + the claimant's **own documents** (nidaan_claim_documents gains `source`; claimant uploads tagged `source='claimant'` so internal files never show; signed URLs). **Doc upload** `POST /nidaan/claim/api/documents/upload` (reuses nidaan-docs storage/validation, 5 files/10MB). **PWA install** (`/nidaan/claim/manifest.webmanifest` + SVG icon + minimal service worker at `/nidaan/claim/sw.js`, scope-guarded; page registers SW). **Heavy "new update" popup** on open (localStorage last-seen signature per claim). Verified: PWA assets correct MIME, api/me keys claim/consent/timeline/documents, fee calc correct, upload gated.
  - **Counsel T&C + Hindi-first SHIPPED (commits d2b1b1c/8be01b4):** real standard terms; contracting entity = **Nidaan The Legal Consultant LLP** (fee is the LLP's, EXPLICITLY separate from NidaanPartner.com) in EN + HI; version **v1**. Bilingual T&C (`claimant_terms_html_hi`; SA editor has both fields; consent card shows terms in the reader's language). Portal now **Hindi-default** (Tier 2/3) with a reassuring "private & secure, nothing charges you, tap when ready" banner to ease link-click fear. Bug fixed: `fee_config` passed "" as get_ops_setting default which suppressed the OPS_SETTING_DEFAULTS fallback → terms came back blank; now passes no default. ⚠️ Founder confirmed standard wording approved for the LLP.
  - **L2 auto-trigger SHIPPED (commit 4b7335f) → CLAIMANT PORTAL P1 COMPLETE.** Hook in `biz_claimshield.create_case` (after mark_case_sent; covers auto + manual paths) fires best-effort `on_claim_reached_l2` → opens portal + emails the policyholder. Greeting email = **bilingual (Hindi+English), reassuring, explains what tapping does, NO fee calc** (calc only on dashboard). Involved staff pinged all-channel via `notify_claim_watchers` (mediator's ops team stays in loop). **Gated by super-admin `claimant_autosend_enabled` (DEFAULT OFF)** — verified auto path returns `autosend_off` while off. Manual **"✉️ Email to claimant"** button (force-send, sub_super_admin) on the claim card + auto-send toggle in the SA Fee & Terms editor. Email delivery confirmed enabled (Gmail SMTP). **Deferred to P2:** subscriber/branch (non-staff mediator) direct notification; background web-push; OTP/Google re-entry.
  - **OWNER before go-live:** live-test (issue link/email → open on phone → accept → upload), then flip `claimant_autosend_enabled` ON in ops Content → ⚖️ Claimant Fee & Terms. **STILL TO WIRE (HELD on counsel T&C):** L2 auto-trigger + greeting email (NO calc in email) + all-parties all-channel notify + mediator CC. Deferred (nice-to-have): background web-push (in-app popup covers P1); OTP/Google re-entry (magic-link is the credential now). **nidaanpartner.com CONFIRMED on Google Workspace** (Aug 22) → unblocks radar auto-forward with plus-addressing/catch-all.
- **Email Radar — dual-mode per mailbox (design locked, to build in the sustainability track).** Each mailbox is **one-way (forwarding only → staff must open Gmail to reply)**, **two-way (app-password → read+reply in ops)**, or **both**. Radar shows a per-mailbox **mode badge** (➡️ one-way / 🔁 two-way / 🔗 both) + each email inherits an action hint, so staff self-serve what to do. **"Both" must DEDUPE on Message-ID** (same email arrives via forward AND IMAP → one item). Confirmed with founder: forwarding=read-only; app-password=full two-way; both is fine if deduped.

## A87 — Email Radar Phase 5: full mailbox management from ops (read + reply-as-customer + lifecycle + purge) (Aug 21 2026)

The radar stopped being read-only. Staff now manage ~100 customer mailboxes **entirely from ops — never opening Gmail**:
- **Read in-app** — click any item → `GET /radar/items/{id}/email` fetches the full email live via IMAP UID (`_imap_fetch_full`, text/plain preferred else HTML-stripped), shown in a modal.
- **Reply AS the customer** — `POST /radar/items/{id}/reply` sends via **SMTP** from the customer's own mailbox (`_smtp_send`, `smtp.` host derived from `imap.`, STARTTLS:587, `Re:`+In-Reply-To/References threading). We're the **authorized consultant**; soft consent is stamped at connect (`consent_ack_at`, migration on `nidaan_radar_mailboxes`). Every send logged to new table **`nidaan_radar_sent`** (mailbox, item, to, subject, body, message_id, sent_by). Audited (`radar.reply`).
- **Lifecycle buckets** (clean, non-messy view; default **Act now**): **🔴 Act now** = `status='new' AND flag IN(red,amber)` (needs a reply) → **🕓 Waiting on them** = `status='responded'` (we replied) → **✅ Resolved** = `set_item_status`. **A new inbound reply lands as a fresh `new` item → back to Act now automatically.** Plus ⏰ Deadlines and ⚪ Cleared (green/auto). Counts from `radar_metrics` (added `act`/`waiting`/`resolved`).
- **Disconnect + PURGE once the case is decided/awarded** — `POST /radar/mailboxes/{id}/purge` (`purge_mailbox`, **super_admin only**, audited `radar.purge`) deletes the mailbox row (creds), all its items, and all sent records. **Nothing retained** (founder policy). Replaces the old "Remove" button in the Mailboxes tab.

Files: `biz_nidaan_radar.py` (P5 block: `_smtp_host`, `_imap_fetch_full`, `_smtp_send`, `get_item`, `read_full_email`, `send_reply`, `set_item_status`, `list_sent`, `purge_mailbox`; `list_items` gained `bucket`; `radar_metrics` gained bucket counts; `upsert_mailbox` stamps `consent_ack_at`). `biz_database.py` (`nidaan_radar_sent` + index, `consent_ack_at` migration). `sarathi_biz.py` (4 endpoints). `static/nidaan_ops.html` (`_radarInBucket`, bucket filters, `openRadarEmail`/`radarSendReply`/`radarResolve`/`radarPurge`, default bucket `act`). HARD RULE still holds: **UI never shows "IRDA/IRDAI/Lokpal"** — only "priority sender".

## A86 — Nidaan Document Splitter (standalone ops tool) (Aug 20 2026, commit 2a48ac7)

Customers send a big MIXED file (discharge summary + bills + lab reports + policy copy…) as 1–3 PDFs/images; the team must send each document SEPARATELY to authorities (was manual). New standalone tool `biz_doc_splitter.py` + ops panel **"📄 Doc Splitter"** (all staff, `minRank:0`, NOT tied to a claim): upload PDF/JPG/PNG/WebP (≤12 files, 30 MB each, ≤80 pages) → `normalize_to_pdf` merges into one PDF (fitz/PyMuPDF) → `segment` = **Gemini multimodal** (`Part.from_bytes` PDF) returns each distinct document + contiguous page range → **human review** (page thumbnails via `/docsplit/{job}/thumb/{n}` + editable name/start/end list, add/remove) → `extract` splits per document (fitz) → **zip download** (`/docsplit/{job}/export`, audited). Short-lived job storage in `DOCSPLIT_TMP`. Verified: 5-page mix → 3 docs correctly (discharge p1-2, bill p3, lab p4-5). **DOC/DOCX = later (needs LibreOffice, not installed).** P2 (later) = attach separated docs straight to a claim.

## A85 — Sarathi conversational voice CRM + Nidaan urgent fixes (Aug 18–19 2026)

**Sarathi-AI.com**
- **Retail homepage chat (commits 3eacf94→95a35aa).** `/api/guide/ask` now persists to `retail_chat_threads`/`_messages` (invisible client `session_key`; >30 min idle = fresh thread). `/superadmin → Support → 💬 Homepage/Retail Chats` (All / 🔥 Hot / ⚠️ Needs-human + transcript). **AI upgrade:** salesman+support persona, honest anti-repeat stories (`_SARATHI_STORIES`, `seen_stories` in localStorage), lead name/number capture, intent scoring. **v2 live two-way reply:** superadmin composer `POST /api/sa/retail-chats/{id}/reply` → widget polls `GET /api/guide/thread` every 5s → 👤 Sarathi Team bubbles. Widget `?v=4`.
- **Impersonation fixed (859c898).** `/dashboard?_imp_token=` only authed the HTML request → SPA had no token → bounced to /login. Now plants the `sarathi_token` cookie + redirects clean (like the magic-link path).
- **Telegram voice CRM — voice REPLIES (a3d6b61).** The assistant now speaks its answers back: `_tts_voice` (Gemini `gemini-2.5-flash-preview-tts`, voice **Kore**) → PCM→WAV→**OGG/Opus via ffmpeg** → `_send_voice` (Telegram sendVoice, text as caption + buttons); falls back to text on any TTS/ffmpeg failure so the answer is never lost. Per-user pref `tg_links.voice_reply` = **auto** (speak when the advisor sent a voice note, else text) | **on** (always) | **off**; menu **🔊 Voice** toggle. `is_voice` threaded through `_process_command`; AI answers delivered via `_reply`. **Voice speaks natural HINGLISH** — `_hinglish_for_voice` renders a spoken Roman Hindi-English line (names/numbers verbatim) before TTS, because TTS reads the literal text (was English → now "Aapke aaj 3 follow-ups hain…"); caption matches. Cost ~₹0.2–0.4 per spoken reply. Verified transform + TTS→valid OGG + mode logic.
- **Voice/text CALCULATORS (38de393).** `_handle_calc`: AI maps a calc query → {calculator, params} (Indian number words → digits) → runs the REAL `biz_calculators` function (params filtered to signature) → phrases a short answer from the computed numbers (fallback to `format_*`) → spoken in Hinglish. `'calculate'` added to `_parse_intent`; routed in `_process_command`; non-calc falls back to Q&A. Covers all 12 calculators. Verified: SIP-goal→₹9,909/mo, retirement→₹7.23cr, HLV→₹1.38cr. **Remaining voice-in: send-client-message (needs a client channel — WhatsApp not built for subscribers yet); voice search largely already covered by the conversational Q&A.**
- **Telegram voice CRM — conversational (afff2ce, 9e393ab, 603499a).** `biz_sarathi_tgcrm.py` `_ask_ai` was stateless one-shot. Added: **rolling memory** (`tg_context.ai_history`, last 8 turns, 30-min TTL) so follow-ups ("and health?", "the second one") are understood; **sticky ask-mode** (a "yes"-type follow-up stays in the chat instead of bouncing to menu; a real command breaks out; nav buttons exit); warmer persona; **proactive data-grounded Ask-AI opener**; **confirm-to-act** — `_ask_ai` returns `{answer, action}`; an offered action is stashed; a short affirmation (`_is_affirmation`, EN+Hinglish) synthesizes the intent and flows through the **existing Save-confirm card** (never auto-saves). Applies to typed AND voice.

**NidaanPartner.com urgent (f6df8a2, 4ff9dab)**
- **ClaimShield key unified.** Doc-pull `GET /nidaan/api/claimshield/case/{id}/documents` now accepts **`X-ClaimShield-Token`** (= `CLAIMSHIELD_WEBHOOK_SECRET`, the status-webhook token) OR the old `x-api-key`. Dev uses ONE token for both APIs. Verified.
- **L2 ClaimShield reference self-heal.** Stored `claimshield_case_id` (from create_case's `caseReferenceNumber`) was wrong (Garvit claim#39 stored 804203, real **804188** — corrected in DB). `record_status_update` now **stores ClaimShield's caseReferenceNumber from every status push** (matched by our claim no) → stale refs auto-correct. **[OWNER/dev]** to fully resync the ~14 others: dev should either send a status webhook per case (Nidaanpartnercasenumber + caseReferenceNumber) or hand over the mapping for a one-time update.
- **Claim-activity notifications to ALL involved.** `notify_claim_watchers` now routes via `notify_staff_inapp` = dashboard bell + web push + Telegram mirror + **EMAIL** + must-ack popup (email was previously omitted), and includes the **current assignee(s)**; the assign flow now **adds assignees as watchers** so they get ongoing activity, not just the first ping.
- **Customer attachments disabled at L2.** Once a claim is `can_fight` / sent-to-ClaimShield, the customer claim drawer shows a note instead of the uploader + hides the 📎 message-attach; backed by a **server 403 guard** on the upload endpoint.
- **Claim-message two-way (70dc978).** A staffer who messages a customer becomes a claim **watcher** → a customer REPLY reaches them on all channels (popup + push + Telegram + email). A customer reply uses `event_key='claim.reply'` → the Telegram mirror gets a **"💬 Reply to customer"** button; the ops bot (`biz_nidaan_telegram.py`) `creply/crc` callbacks + `claim_reply` capture (typed or voice) → confirm card → `_do_claim_reply` posts to the claim thread → reaches the customer. Staff attend + respond from Telegram, anywhere.
- **Claims attribution + account de-dup (f273084, 9750911).** Root cause of the "Abhishek Solanki" confusion (NO data loophole — zero orphan claims): All Claims sorted `unpaid_lead` LAST so new leads were buried, and `origin` was blank on ~70% of claims. Fixes: **All Claims now sorts newest-first**; `get_claims_ops` computes a universal **`source_kind`** (branch/staff/subscriber/review/direct) → the ops **"Source / Who"** badge shows how every claim came in. **Account de-dup:** `find_duplicate_accounts` (STRONG=shared phone-last10/email via union-find; WEAK=same normalized name only) + `merge_accounts` (super_admin; moves the duplicate's claims to the keeper, archives the dup `status='merged'`/`merged_into`, never hard-deletes, blocked if dup has an active subscription, audited). Ops Accounts **"🔀 Duplicates"** modal (pick keeper → merge). Merged accts hidden from main tabs.

---

*This document is the single source of truth for the Sarathi-AI Business project. Keep it updated after every significant change.*

