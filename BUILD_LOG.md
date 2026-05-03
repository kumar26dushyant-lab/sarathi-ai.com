# Sarathi-AI Business Technologies — Build Log
# ═══════════════════════════════════════════════════════════════
# PURPOSE: Machine-readable session continuity file.
# Any AI assistant or developer reads THIS FILE FIRST to understand:
#   1. Current system state
#   2. What was changed, when, why
#   3. What's pending
#   4. Known issues & decisions made
#
# UPDATE RULE: Append to this file at the END of every change.
# NEVER delete history — only append.
# ═══════════════════════════════════════════════════════════════

## SYSTEM IDENTITY
- **Product**: Sarathi-AI Business Technologies (sarathi-ai.com)
- **Type**: Multi-tenant Financial Advisor CRM SaaS
- **Stack**: Python 3.12, FastAPI, aiosqlite, python-telegram-bot, Gemini 2.0 Flash, Razorpay
- **Deployed**: Oracle Cloud VM, Nginx + Certbot SSL, systemd
- **Working Dir**: `c:\sarathi-business` (local) → `/opt/sarathi` (server)
- **DB**: SQLite `sarathi_biz.db` (21 tables)
- **Endpoints**: 152 API routes, 14 HTML pages, 30+ bot commands

## MULTI-TENANT HIERARCHY
```
Super Admin (sarathi-ai.com team)
  └─ Tenant/Admin (firm owner) ← one per tenant
       └─ Advisors/Agents ← 0 (Solo), 5 (Team), 25 (Enterprise)
```

## PLAN STRUCTURE (as of Phase 1)
| Plan | Price | Admin | Advisors | Total max_agents |
|------|-------|-------|----------|-----------------|
| trial | Free 14d | 1 | 0 | 1 |
| individual (Solo) | ₹199/mo | 1 | 0 | 1 |
| team | ₹799/mo | 1 | 5 | 6 |
| enterprise | ₹1,999/mo | 1 | 25 | 26 |

## AUTH MODEL
- **Super Admin**: Phone whitelist (SUPERADMIN_PHONES env) + password → SA JWT (sa_token cookie)
- **Tenant Owner/Agent**: Phone OTP → JWT pair (sarathi_token cookie) with role in token
- **Legacy Admin**: API key (ADMIN_API_KEY) — to be deprecated

## KEY FILES
| File | Purpose | Lines |
|------|---------|-------|
| sarathi_biz.py | FastAPI server, all API routes | ~3900 |
| biz_bot.py | Telegram bot, all commands | ~5500 |
| biz_database.py | SQLite DB layer, 21 tables | ~2700 |
| biz_auth.py | JWT, OTP, access control | ~560 |
| biz_bot_manager.py | Per-tenant bot lifecycle | ~340 |
| biz_payments.py | Razorpay integration | ~600 |
| biz_whatsapp.py | WhatsApp Cloud API | ~745 |
| biz_calculators.py | 9 financial calculators | ~609 |
| biz_reminders.py | Background scheduler | ~575 |

---

## CHANGE LOG

### Session: 2026-03-06 (Phase 1 — Foundation Fixes)

**Audit completed. Issues found:**
- 5 CRITICAL, 5 HIGH, 6 MEDIUM severity issues
- Root cause: web signup creates tenant but NO agent record
- Bot handlers bypass @registered decorator in 8 places
- Subscription not enforced on API endpoints
- check_subscription_active() doesn't recognize 'paid' status
- Unauthenticated /api/dashboard access via ?tenant_id=X
- max_agents counts include admin (should be admin + N)

**Phase 1 Changes:**

#### P1.1 — Signup creates agent + tenant together
- **File**: `sarathi_biz.py` (api_signup function)
- **File**: `biz_database.py` (create_tenant_with_owner function)
- **What**: Web signup now creates both tenant AND owner agent record (with telegram_id=NULL)
- **Why**: Without an agent record, the entire CRM is unusable for web-only users
- **Wire**: When owner later does /start on Telegram, bot matches by phone and links telegram_id to existing agent

#### P1.2 — Fix subscription status check
- **File**: `biz_database.py` (check_subscription_active function)
- **What**: Added 'paid' to accepted statuses alongside 'active' and 'trial'
- **Why**: Payment webhook sets status to 'paid' but check only accepted 'active'/'trial'

#### P1.3 — Subscription enforcement middleware
- **File**: `sarathi_biz.py` (new middleware)
- **What**: Server-side middleware checks subscription on all /api/ routes except auth, payments, subscription, health
- **Why**: Previously only HTML pages checked subscription; APIs were unprotected

#### P1.4 — Fix unauthenticated dashboard access
- **File**: `sarathi_biz.py` (api_dashboard function)
- **What**: Removed fallback to ?tenant_id query param; JWT is now mandatory
- **Why**: Anyone could access data via /api/dashboard?tenant_id=X without authentication

#### P1.5 — Fix all bot handler auth gaps
- **File**: `biz_bot.py` (8 handlers)
- **What**: Applied @registered decorator to cmd_claims, cmd_claimstatus, cmd_claim, _voice_to_action, _csv_import_handler, greet_callback, _voice_callback
- **Why**: These handlers bypassed is_active/subscription/tenant isolation checks

#### P1.6 — Fix max_agents = admin + N
- **File**: `biz_database.py` (PLAN_FEATURES, PLAN_PRICING, can_add_agent)
- **What**: Solo max_agents=1, Team max_agents=6 (admin+5), Enterprise max_agents=26 (admin+25)
- **Why**: Previously Team=5 total meaning admin+4 advisors, not admin+5 as intended

**Phase 1 STATUS: ✅ ALL 6 FIXES IMPLEMENTED AND SYNTAX-VERIFIED**

DB changes (biz_database.py):
- ✅ `create_tenant_with_owner()` — new function, creates tenant+agent atomically
- ✅ `link_agent_telegram()` — new function, links telegram_id to existing phone-matched agent
- ✅ `check_subscription_active()` — accepts 'paid' status
- ✅ PLAN_FEATURES max_agents — Team:6, Enterprise:26
- ✅ PLAN_PRICING max_agents — same

Server changes (sarathi_biz.py):
- ✅ `api_signup()` — calls `create_tenant_with_owner()` instead of `create_tenant()`
- ✅ `api_dashboard()` — JWT mandatory, removed ?tenant_id unauthenticated fallback
- ✅ Subscription enforcement middleware — 403 on expired tenants for all CRM /api/ routes
  - Exempt: /api/auth/, /api/payments/, /api/subscription/, /api/signup, /api/affiliate/,
    /api/support/, /api/sa/, /api/admin/tenants, /api/admin/stats, /api/admin/bots,
    /api/bot-setup/, /api/calc/, /api/report/, /webhook, /health, /api/onboarding/

Bot changes (biz_bot.py):
- ✅ Added `_require_agent_auth()` — full auth helper (rate limit, exists, is_active, subscription, tenant isolation, plan injection) for handlers that can't use `@registered`
- ✅ 8 handlers patched: cmd_claims, cmd_claimstatus, cmd_claim, _voice_to_action,
  _csv_import_handler, greet_callback, _voice_callback, _voice_fill_text
- ✅ Removed redundant rate limit check from cmd_claim (already done in _require_agent_auth)

---

### Session: 2026-03-06 (Phase 2 — Isolation Hardening)

**Phase 2 STATUS: ✅ ALL 6 FIXES IMPLEMENTED AND SYNTAX-VERIFIED**

#### P2.2 — Role in JWT token
- **File**: `biz_auth.py` (create_access_token, create_refresh_token, create_token_pair, get_current_tenant, get_optional_tenant)
- **What**: JWT now includes `role` (owner/admin/agent) and optional `agent_id` fields
- **Why**: Previously role was never in the token — every owner check required a full DB round-trip
- **Wire**: Login handler (api_verify_otp) now looks up agent_id and passes role when creating tokens.
  Refresh handler re-fetches role from DB (in case role changed since token issued).
  /api/auth/me now returns `role` and `agent_id` to frontend.

#### P2.3 — require_owner FastAPI dependency
- **File**: `biz_auth.py` (new `require_owner` function)
- **What**: New `Depends(auth.require_owner)` — reads role from JWT, rejects if not owner/admin. Zero DB calls.
- **Why**: Old `_require_owner_role()` queried ALL agents for the tenant every time — expensive and fragile

#### P2.6 — Owner-only route protection
- **File**: `sarathi_biz.py` (14 routes updated)
- **What**: All 7 existing `_require_owner_role(tenant)` calls → `Depends(auth.require_owner)`.
  Plus 7 NEW owner-only protections added:
  - `POST /api/onboarding/whatsapp` — was accessible to any agent
  - `POST /api/onboarding/telegram-bot` — was accessible to any agent
  - `POST /api/onboarding/branding` — was accessible to any agent
  - `POST /api/subscription/cancel` — any agent could cancel
  - `POST /api/subscription/schedule-change` — any agent could change plan
  - `POST /api/subscription/upgrade` — any agent could upgrade
  - `POST /api/subscription/downgrade` — any agent could downgrade
- **Why**: Regular agents must not be able to reconfigure bot tokens, WhatsApp, branding, or change subscription

#### P2.1 — IDOR hardening on DB mutations
- **File**: `biz_database.py` (6 functions hardened)
- **What**: Added optional `tenant_id` parameter to: `update_lead`, `update_lead_stage`,
  `update_policy`, `update_claim`, `deactivate_agent`, `reactivate_agent`, `delete_lead`.
  When provided, adds `AND agent_id IN (SELECT agent_id FROM agents WHERE tenant_id=?)` to WHERE clause.
- **Why**: Previously these functions used only the record PK (e.g. lead_id) — any tenant could modify another's data by guessing sequential IDs
- **Wire**: All API callers in sarathi_biz.py now pass `tenant_id=tenant["tenant_id"]`

#### P2.4 — Bot token uniqueness + stop_bot bug
- **File**: `biz_database.py` (init_db migration), `sarathi_biz.py` (tenant delete)
- **What**: Added `CREATE UNIQUE INDEX` on `tg_bot_token` (partial — excludes NULL/empty).
  Fixed `bot_manager.stop_bot()` → `bot_manager.stop_tenant_bot()` in tenant deletion handler.
- **Why**: Two tenants could race to register the same token (app check exists but no DB constraint).
  Wrong method name meant deleting a tenant wouldn't stop its bot.

#### P2.5 — transfer_agent cross-tenant guard
- **File**: `biz_database.py` (transfer_agent_data, remove_agent, reassign_lead)
- **What**:
  - `transfer_agent_data` — new `tenant_id` param; when given, verifies both agents belong to same tenant before transferring
  - `remove_agent` — new `tenant_id` param; validates `transfer_to` agent belongs to same tenant
  - `reassign_lead` — now verifies the LEAD also belongs to the tenant (previously only checked target agent)
- **Why**: Cross-tenant data transfer was possible if attacker guessed agent IDs. Reassign could move leads from other tenants.

---

### Phase 3 — Endpoint Hardening & Flow Fixes (Session 3)
> **Date**: 2025-01-XX  |  **Files**: sarathi_biz.py, biz_bot.py  |  **Syntax**: ✅ Both verified

#### P3.1 — AI endpoint IDOR fix
- **File**: `sarathi_biz.py` (`/api/ai/score-lead/{lead_id}`, `/api/ai/generate-pitch/{lead_id}`)
- **What**: After fetching lead, look up `lead.agent_id` → `get_agent_by_id()` → verify `agent.tenant_id == caller's tenant_id`. Return 404 if mismatch.
- **Why**: Any authenticated user could score/pitch ANY lead by guessing lead_id across tenants.

#### P3.2 — Ticket auth + ownership enforcement
- **File**: `sarathi_biz.py` (`GET /api/support/tickets/{ticket_id}`, `POST /api/support/tickets/{ticket_id}/reply`)
- **What**: Changed from optional auth (`get_optional_tenant`, which returns None for unauthenticated) to mandatory — return 401 if no JWT. Added tenant_id ownership check so tenants can only see/reply to their own tickets.
- **Why**: Unauthenticated users could view any ticket and reply to any ticket. Even authenticated users could view/reply to other tenants' tickets.

#### P3.3 — Dashboard agent-scoped view
- **File**: `sarathi_biz.py` (`GET /api/dashboard`)
- **What**: When `?agent_id=X` is provided, non-owner/admin callers are blocked from viewing other agents' dashboards. Only owners/admins can view any agent within their tenant; regular agents can only view their own.
- **Why**: Any agent within a tenant could view any other agent's dashboard data (leads, followups, stats) by passing `?agent_id=X`.

#### P3.4 — Admin overview owner-only
- **File**: `sarathi_biz.py` (`GET /api/admin/overview`)
- **What**: Switched dependency from `get_current_tenant` to `require_owner`. Regular agents now get 403.
- **Why**: Regular agents could access full firm-level admin data including owner PII and all-agent stats.

#### P3.5 — Bot web-link flow fix (duplicate agent prevention)
- **File**: `biz_bot.py` (`onboard_email()`, web_signup branch)
- **What**: Replaced `db.upsert_agent()` with `db.link_agent_telegram(phone, user_id)` for the web_signup=True case. Falls back to upsert_agent only if link_agent_telegram returns None (phone not found).
- **Why**: Web signup creates the agent via `create_tenant_with_owner()` (Phase 1). When the owner later connects via Telegram bot, the old code called `upsert_agent()` which created a DUPLICATE agent record. `link_agent_telegram` just sets the telegram_id on the existing record.

---

### Phase 4 — Hardening, Validation & Legacy Cleanup (Session 4)
> **Date**: 2026-03-06  |  **Files**: sarathi_biz.py, biz_auth.py, biz_pdf.py, biz_gdrive.py  |  **Syntax**: ✅ All 4 verified

#### P4.1 — Contact-pref IDOR fix (HIGH)
- **File**: `sarathi_biz.py` (`GET /api/leads/{lead_id}/contact-pref`, `PUT /api/leads/{lead_id}/contact-pref`)
- **What**: Added tenant-lead ownership check (get_lead → get_agent_by_id → verify tenant_id). Return 404 if mismatch.
- **Why**: Any authenticated tenant could read/write contact preferences for any lead across all tenants by guessing lead_id.

#### P4.2 — SA password timing-safe compare (CRITICAL)
- **File**: `biz_auth.py` (`verify_sa_credentials`, `init_superadmin`)
- **What**: Replaced `password == SUPERADMIN_PASSWORD` with `hmac.compare_digest()`. Changed default password from `"jyotik"` to `""` (empty = disabled). Added critical log warning if SUPERADMIN_PASSWORD env var is not set.
- **Why**: Plain `==` is vulnerable to timing attacks. Hardcoded default "jyotik" meant anyone who reads source code has SA access if env var is unset.
- **ACTION REQUIRED**: Set `SUPERADMIN_PASSWORD` in production biz.env before deploying.

#### P4.3 — Legacy admin routes deprecated (HIGH)
- **File**: `sarathi_biz.py` (9 routes + /admin page)
- **What**: All 9 legacy `/api/admin/*` key-based routes now return HTTP 410 Gone with migration message pointing to `/api/sa/*` equivalents. `/admin` page now shows redirect to `/superadmin`.
- **Routes retired**: GET /api/admin/tenants, GET /api/admin/stats, POST extend/activate/deactivate, GET bots, POST restart/stop, POST create-firm
- **Why**: Duplicate attack surface — static API key in URLs, no audit trail, no expiration, hardcoded default key.

#### P4.4 — Path traversal in PDF filenames (MEDIUM)
- **File**: `biz_pdf.py` (`save_html_report`)
- **What**: Added `re.sub(r'[^a-zA-Z0-9_-]', '', safe_name)` to strip all path-traversal chars (`/`, `\`, `..`) from `client_name` before use in filename.
- **File**: `biz_gdrive.py` (`upload_calc_report`)
- **What**: Changed `Path("generated_pdfs") / report_filename` to `Path("generated_pdfs") / Path(report_filename).name` — strips directory components from user-supplied filename.
- **Why**: User-supplied `client_name` could contain `../../etc/foo` creating files outside the intended directory.

#### P4.5 — Pydantic validation constraints (HIGH)
- **File**: `sarathi_biz.py` (6 models + bulk import)
- **Models hardened**:
  - `TicketCreateRequest`: subject (3-200), description (10-5000), category/priority enum patterns
  - `TicketReplyRequest`: message (1-5000)
  - `SATicketUpdateRequest`: status/priority enums, assigned_to (100), resolution (2000)
  - `CampaignCreateRequest`: title (2-200), message (5-5000), type/channel enums
  - `BrandingRequest`: tagline (300), cta (300), phone (15), email (200), credentials (500)
- **Bulk import** (`POST /api/import/leads`): Added per-field validation — name required + max 200 chars, all other fields truncated to 500 chars.
- **Why**: Unbounded text fields enabled DB bloat / DoS. No enum validation allowed arbitrary status/priority values.

#### P4.6 — SA cookie secure flag (HIGH)
- **File**: `sarathi_biz.py` (`sa_login`)
- **What**: SA auth cookie `secure` flag now set dynamically: `True` unless `ENVIRONMENT=development` env var is set.
- **Why**: `secure=False` meant the SA JWT cookie was sent over non-HTTPS connections, enabling interception.

#### P4.7 — Solo plan team management enforcement (MEDIUM)
- **File**: `sarathi_biz.py` (4 endpoints + helper)
- **What**: Added `_require_team_plan()` helper that rejects if plan is `trial`/`individual`. Applied to: POST deactivate, reactivate, transfer, remove agent endpoints. Returns 403 with upgrade message.
- **Why**: Team management API endpoints were accessible on Solo plan (operationally meaningless but not explicitly rejected). Now properly gated.

---

### Phase 5 — Rate Limiting, Auth Cleanup & Payment Hardening (Session 5)
> **Date**: 2026-03-06  |  **Files**: sarathi_biz.py, biz_auth.py, biz.env  |  **Syntax**: ✅ Verified

#### P5.1 — Rate limiting for 15 sensitive endpoints (HIGH)
- **File**: `sarathi_biz.py`
- **What**: Added explicit `@limiter.limit()` to: auth/refresh (20/min), payments/create-order (10/min), payments/verify (10/min), payments/create-subscription (5/min), payments/status (20/min), payments/webhook (60/min), onboarding/whatsapp (5/min), onboarding/telegram-bot (5/min), ai/verify (5/min), sa/export/* (5/min each), sa/delete-tenant (3/min), sa/create-firm (10/min), affiliate/dashboard (20/min).
- **Why**: All these were on the 200/min default — payment abuse, AI API amplification, data export flooding, and destructive SA operations had no meaningful rate protection.

#### P5.2 — Remove query param auth fallback (MEDIUM)
- **File**: `biz_auth.py` (`require_superadmin`, `verify_admin_key`)
- **What**: Removed `request.query_params.get("sa_token")` from SA auth, removed `request.query_params.get("key")` from admin key verification.
- **Why**: SA JWTs and API keys in URLs leak to server logs, browser history, Referer headers, and proxy logs. Cookie + header-only auth eliminates this vector.

#### P5.3 — Payment endpoint auth + IDOR hardening (CRITICAL)
- **File**: `sarathi_biz.py`
- **What**:
  - `POST /api/payments/create-subscription` — added `Depends(auth.get_current_tenant)` + tenant_id ownership check (was completely unauthenticated)
  - `GET /api/payments/status` — switched from `?tenant_id=` query param to JWT-based auth (was unauthenticated, any tenant_id queryable)
- **Why**: Anyone could create Razorpay subscriptions for arbitrary tenant IDs or query any tenant's payment status without authentication.

#### P5.4 — CreateFirmRequest validation + sanitization (MEDIUM)
- **File**: `sarathi_biz.py` (model + SA handler)
- **What**: Added Pydantic constraints: firm_name (2-200), owner_name (2-100), phone (Indian regex), email (200), city (100), plan (enum). SA handler now calls `sanitize_phone()` and `sanitize_email()` and `.strip()` on names before DB insert.
- **Why**: SA create-firm accepted raw unsanitized input — malformed phones, arbitrarily long strings, potential stored XSS.

#### P5.5 — Affiliate referral single-use per phone (MEDIUM)
- **File**: `sarathi_biz.py` (`POST /api/affiliate/track`)
- **What**: Before creating a referral, checks if the `referred_phone` already has a referral record under this affiliate — returns 409 Conflict if duplicate.
- **Why**: DECISIONS section stated "Referral codes should be one-time single-use". Previously the same phone could be tracked unlimited times, inflating affiliate referral counts.

---

## CHANGE LOG — Phase 6 (Defense-in-Depth, Pydantic Gaps, Client-Side XSS)

#### P6.1 — DB-layer IDOR hardening on GET functions (MEDIUM → defense-in-depth)
- **File**: `biz_database.py` (7 functions), `sarathi_biz.py` (10 call sites updated)
- **What**: Added optional `tenant_id` parameter to `get_lead()`, `get_policy()`, `get_claim()`, `get_policies_by_lead()`, `get_claims_by_lead()`, `get_lead_interactions()`, `get_lead_contact_pref()`. When provided, SQL JOINs through `agents` table to verify data belongs to tenant. Updated all API-layer callers in `sarathi_biz.py` to pass `tenant_id=tenant["tenant_id"]`, removing redundant `get_agent_by_id()` IDOR checks. Bot callers (biz_bot.py) left unchanged — they already enforce `agent_id` ownership.
- **Why**: Previous IDOR guards were only at the API handler level — a code change that skips the check would expose cross-tenant data. DB-layer scoping is defense-in-depth: even if API code changes, the SQL itself prevents cross-tenant reads.

#### P6.2 — Remaining Pydantic model field validation (MEDIUM)
- **File**: `sarathi_biz.py` (4 models)
- **What**:
  - `SACreateAffiliateRequest`: name (2-100), phone (Indian regex), email (max 200), commission_pct (0-100)
  - `SAUpdateAffiliateRequest`: name (2-100), phone (Indian regex), email (max 200), status (active|inactive enum), commission_pct (0-100), total_paid (≥0)
  - `WhatsAppConfigRequest`: wa_phone_id (digits only, max 50), wa_access_token (max 500), wa_verify_token (max 200)
  - `WaSendRequest`: phone (Indian 10-digit or 91+10), message (1-4096 chars)
- **Why**: These 4 models accepted unconstrained strings — arbitrary-length payloads, invalid phone formats, and unchecked numeric ranges could cause stored data corruption or abuse.

#### P6.3 — Client-side XSS fixes (HIGH + MEDIUM)
- **File**: `static/superadmin.html`, `static/dashboard.html`
- **What**:
  - **HIGH**: `detailItem()` function now escapes both label and value via `esc()`. Added separate `detailItemHtml()` for the two calls that legitimately pass pre-rendered HTML (`planBadge`, `statusBadge`).
  - **MEDIUM**: `deleteTenant` button — replaced inline `onclick` string interpolation of `firm_name` with `data-fn` attribute + `this.dataset.fn` to prevent HTML/JS breakout.
  - **MEDIUM**: Dashboard followup phone links — phone numbers now sanitized via `.replace(/\D/g,'')` before insertion into `href="tel:"` and `href="https://wa.me/"` attributes, preventing `javascript:` injection.
- **Why**: `detailItem()` rendered server data (owner_name, email, city, phone) into innerHTML without escaping — stored XSS via malicious firm registration. The onclick and href issues allowed limited injection via crafted firm names or phone numbers.

---

## PENDING (Phase 7+)
- [ ] Web-based invite acceptance for agents
- [ ] Phone OTP verification during bot onboarding

---

## CHANGE LOG — Phase 7 (Feature Additions: Web Agent Invite + Phone OTP)

#### P7.1 — Web-based agent invite acceptance (FEATURE)
- **Files**: `sarathi_biz.py` (3 new endpoints), `biz_database.py` (`link_agent_telegram` updated), `static/invite.html` (new), `static/dashboard.html` (invite link display)
- **What**:
  - New `GET /api/invite/validate/{code}` — public endpoint, returns firm name + plan + available slots for a given invite code
  - New `POST /api/invite/accept` — accepts invite code + name + phone + email, creates agent with placeholder `web_{tenant_id}_{phone}` telegram_id. Validated via `InviteAcceptRequest` Pydantic model (phone regex, name length, etc.)
  - Updated `POST /api/admin/invite` response to include `invite_url` field with shareable web link
  - New `static/invite.html` — clean branded page: validates code on load, shows firm badge, collects agent details, submits to API, shows success with Telegram linking instructions
  - Updated `link_agent_telegram()` to recognize `web_*` placeholder telegram_ids and replace them when agent does `/start` on Telegram
  - Dashboard invite banner now shows clickable web invite URL
- **Flow**: Owner generates invite → gets code + web URL → shares URL → agent fills form on web → agent created → agent later does `/start` on Telegram → phone matched → Telegram linked automatically
- **Why**: Previously agents could only join via Telegram bot. Web invite provides a frictionless alternative for agents without Telegram, and allows phone-based Telegram linking later.

#### P7.2 — Phone OTP verification during bot onboarding (FEATURE)
- **Files**: `biz_bot.py` (new state + handler + import)
- **What**:
  - Added new conversation state `ONBOARD_VERIFY_OTP` (state 8 in range)
  - Added `import biz_auth as auth_mod` to biz_bot.py
  - Modified `onboard_phone()`: after phone validation + duplicate checks, generates OTP via `auth_mod.generate_otp()` and sends via `wa.send_otp()` to WhatsApp. Transitions to `ONBOARD_VERIFY_OTP`
  - New handler `onboard_verify_otp()`: validates 6-digit input, calls `auth_mod.verify_otp()`. On success → proceeds to email step. On failure → allows retry or re-entering phone
  - **Graceful fallback**: If WhatsApp is not configured (`wa.is_configured()` → False) or OTP send fails, skips OTP and proceeds directly to email step (preserves existing behavior)
  - Registered `ONBOARD_VERIFY_OTP` state in the onboarding ConversationHandler
- **Why**: Previously any phone number was accepted without verification during bot onboarding. OTP ensures the agent actually owns the phone number, preventing impersonation and duplicate account abuse.

---

## PENDING (Phase 14+)
(Security hardening complete. All originally planned items are done.)

---

### Phase 13 — Agent Photo in PDF Reports
**Date**: 2026-03-07
**Files Changed**: `biz_pdf.py`, `biz_bot.py`, `sarathi_biz.py`
**What**:
- **P13.1 — PDF Template Updates** (`biz_pdf.py`, 526 lines):
  - `_brand_css()`: Added `.agent-photo` (circular 56px, object-fit cover, white border), `.header .agent-row` (flex layout for photo + name/title), `.footer .agent-block` (centered photo + name), `.footer .agent-photo` (40px, blue border)
  - `_header_html()`: New params `agent_name`, `agent_photo_url` — renders agent row below title with circular photo + "Your Financial Advisor" label (graceful fallback with `onerror` hide)
  - `_footer_html()`: New param `agent_photo_url` — renders agent photo block between brand and contact line (with `onerror` fallback)
  - All 4 generators (`generate_inflation_html`, `generate_hlv_html`, `generate_retirement_html`, `generate_emi_html`): New params `agent_name`, `agent_phone`, `agent_photo_url`, `company` — passed through to `_header_html()` and `_footer_html()`
- **P13.2 — Bot Integration** (`biz_bot.py`):
  - `_run_and_send_calc()`: Builds full agent photo URL from `agent['profile_photo']` + `SERVER_URL`, fetches `firm_name` from `db.get_tenant()`, passes `_brand` kwargs dict to all 4 PDF generators
  - Reports generated via Telegram bot now show agent's circular photo in both header and footer, plus firm name as company branding
- **P13.3 — API Integration** (`sarathi_biz.py`):
  - All 4 report endpoints (`/api/report/inflation`, `/api/report/hlv`, `/api/report/retirement`, `/api/report/emi`): Added optional query params `agent_name`, `agent_phone`, `agent_photo_url`, `company` — passed through to PDF generators
  - Web callers (dashboard, calculators) can now brand reports by passing agent info in query string
- **Why**: PDF reports are the primary client-facing deliverable. Adding the agent's photo personalizes reports, builds trust, and creates a professional branded experience. Agents who uploaded photos (Phase 10) now see them automatically in every report they generate.

---

### Phase 12 — Dashboard Dark Mode Toggle
**Date**: 2026-03-07
**Files Changed**: `static/dark-mode.css` (new), `static/dark-mode.js` (new), `static/dashboard.html`, `static/admin.html`, `static/superadmin.html`, `static/index.html`, `static/calculators.html`, `static/partner.html`, `static/help.html`, `static/support.html`, `static/onboarding.html`, `static/getting-started.html`, `static/demo.html`, `static/telegram-guide.html`, `static/privacy.html`, `static/terms.html`
**What**:
- **P12.1 — Shared Dark Mode CSS** (`static/dark-mode.css`, 509 lines):
  - 121 CSS rule blocks covering all page variants: dashboard (--bg/--card/--text), admin (--gray-*), superadmin (--text/--text2/--slate), index (--g* gray scale), and hardcoded-color pages
  - `html[data-theme="dark"]` selector pattern — overrides all `:root` CSS variables in one block
  - Explicit dark overrides for: topbar, sidebar, modals, forms/inputs, tables, alerts, stat cards, badges, tabs, navbar glass morphism, search boxes, login cards, accordion items, progress indicators, scrollbar, referral boxes
  - Theme toggle button styling (`.theme-toggle`) — 34×34px circular button, sun/moon icon, hover effects for light & dark modes
  - Footer stays dark (slightly deepened to `#020617`); sidebar deepened to `#020617→#0f172a` gradient
  - Decorative orbs reduced to 15% opacity in dark mode
  - Custom scrollbar theming for Webkit browsers
- **P12.2 — Shared Dark Mode JS** (`static/dark-mode.js`, 49 lines):
  - FOUC prevention: IIFE runs immediately in `<head>` to apply saved theme before render
  - `toggleTheme()` — cycles light↔dark, saves to `localStorage('sarathi_theme')`
  - `_updateToggleIcons()` — syncs all `.theme-toggle` buttons (🌙 light / ☀️ dark)
  - System theme detection: listens to `prefers-color-scheme` media query changes for auto-switching (only when user hasn't manually set preference)
  - DOMContentLoaded hook for icon initialization
- **P12.3 — Integration Across 14 HTML Pages**:
  - Added `<link rel="stylesheet" href="/static/dark-mode.css">` and `<script src="/static/dark-mode.js">` in `<head>` of all active pages
  - Added `<button class="theme-toggle">` in each page's header/nav area (topbar, navbar, header-right, etc.)
  - Toggle placement: dashboard topbar right, admin header-right, superadmin topbar-right, index nav-links, calculators header, public page navs, onboarding header (positioned top-right)
- **Why**: Users increasingly expect dark mode, especially for dashboards used for extended periods. Single shared CSS+JS files avoid duplication across 14+ pages. CSS variable architecture (already in place for most pages) made dark overrides clean. localStorage persistence + system theme fallback provides the best UX.

---

### Phase 11 — WhatsApp Webhook Retry Logic
**Date**: 2026-03-07
**Files Changed**: `biz_whatsapp.py`, `biz_resilience.py`, `biz_reminders.py`, `sarathi_biz.py`
**What**:
- **P11.1 — Connection Pooling** (`biz_whatsapp.py`):
  - Replaced per-request `httpx.AsyncClient` with shared pooled client (`_get_client()`) — 20 max connections, 10 keepalive
  - Added `close_client()` for graceful shutdown
  - Updated ALL send functions (`send_text`, `send_document`, `send_image`, `send_text_for_tenant`) to use pooled client
  - Added `retryable: True` flag to network error responses (`httpx.TimeoutException`, `httpx.ConnectError`, `ConnectionError`, `TimeoutError`, `OSError`) so callers know to retry
- **P11.2 — Dead-Letter Management** (`biz_resilience.py`):
  - New `get_queue_stats()` — returns pending/sent/failed counts, total retries, oldest pending timestamp
  - New `get_dead_letter_messages(limit)` — retrieves permanently failed messages for admin review
  - New `retry_dead_letter(queue_id)` — re-queues a failed message for another round (resets retry_count)
  - New `purge_dead_letters(older_than_days)` — cleans old sent/failed records
- **P11.3 — Reminder Error Handling** (`biz_reminders.py`):
  - Birthday scan: now checks `retryable` flag; logs warnings for queued messages, errors for failures (was silently swallowing)
  - Anniversary scan: same improvement
  - Renewal scan: **was completely silent** (no result check) — now checks success/retryable, enqueues failed messages via `resilience.enqueue_message()`, logs all outcomes
  - Added `import biz_resilience as resilience`
- **P11.4 — Admin API for Queue Monitoring** (`sarathi_biz.py`):
  - New `GET /api/admin/message-queue/stats` — queue statistics (pending/sent/failed counts)
  - New `GET /api/admin/message-queue/dead-letters` — view failed messages (filtered by tenant)
  - New `POST /api/admin/message-queue/{queue_id}/retry` — re-queue a dead-letter message
  - Added `wa.close_client()` to graceful shutdown sequence
- **Why**: All WhatsApp sends were fire-and-forget with zero retry. The existing `retry_async` decorator, `smart_send_whatsapp()`, and `message_queue` table in `biz_resilience.py` were built but never wired in. Reminder scans silently swallowed failures. This phase adds connection pooling, proper error classification (retryable vs permanent), dead-letter management, and admin visibility into the queue.
- **Note**: The `retry_async` decorator and `smart_send_whatsapp()` function in biz_resilience.py remain available for callers to opt into. Bot command handlers (which show errors to users inline) continue using direct `wa.send_*()` calls since the user sees the failure immediately. Background sends (reminders) now properly handle and queue failures.

---

### Phase 10 — Agent Profile Photo Upload
**Date**: 2026-03-07
**Files Changed**: `biz_database.py`, `sarathi_biz.py`, `biz_bot.py`, `static/dashboard.html`
**What**:
- **P10.1 — DB Schema** (`biz_database.py`):
  - Migration: `ALTER TABLE agents ADD COLUMN profile_photo TEXT DEFAULT ''`
  - `update_agent_profile()` allowlist updated: added `'profile_photo'`
- **P10.2 — File Storage & API** (`sarathi_biz.py`):
  - New `uploads/photos/` directory, mounted at `/uploads` via `StaticFiles`
  - New `POST /api/agent/{agent_id}/photo` — multipart image upload, 5MB limit, JPEG/PNG validation via magic bytes, tenant-scoped agent check, audit logged, rate-limited 10/min
  - New `DELETE /api/agent/{agent_id}/photo` — removes photo file + clears DB field
  - Photos saved as `agent_{id}.jpg` or `.png` (single photo per agent, overwritten on re-upload)
- **P10.3 — Telegram Bot** (`biz_bot.py`):
  - Added 📸 Profile Photo button to `/editprofile` inline keyboard
  - Profile display now shows photo status (✅ Set / ❌ Not set)
  - `editprofile_choice()` handles `editprof_photo` — prompts user to send a photo
  - New `editprofile_photo()` handler: downloads highest-res Telegram photo, saves to `uploads/photos/`, updates DB, audit logged
  - `EDITPROFILE_VALUE` state now accepts `filters.PHOTO` in addition to `filters.TEXT`
- **P10.4 — Dashboard UI** (`static/dashboard.html`):
  - Agents table shows avatar: circular photo if set, or colored initial circle as fallback
  - 📸 upload button on each agent row — file picker (JPEG/PNG), uploads via `POST /api/agent/{id}/photo`
  - `uploadAgentPhoto()` JS function with client-side type/size validation
- **Why**: Agents need visual identity in the CRM. Profile photos personalize the dashboard and can later be embedded in PDF reports and WhatsApp greetings.

---

### Phase 9 — Email OTP Verification During Onboarding
**Date**: 2026-03-07
**Files Changed**: `biz_auth.py`, `biz_bot.py`
**What**:
- **P9.1 — Email OTP functions in `biz_auth.py`**:
  - New `_email_otp_store` dict — separate in-memory store (keyed by email) to avoid collision with phone-keyed OTPs
  - New `generate_email_otp(email)` → generates 6-digit OTP, same rate-limiting (60s cooldown), 10m expiry, 5 max attempts
  - New `verify_email_otp(email, otp)` → timing-safe comparison via `hmac.compare_digest`, single-use consumption
  - Updated `clear_expired_otps()` to also clean `_email_otp_store`
- **P9.2 — New `ONBOARD_VERIFY_EMAIL_OTP` conversation state in `biz_bot.py`**:
  - Added state at index 51 (range expanded from 51 to 52)
  - Added `import biz_email as email_mod`
  - Refactored `onboard_email()`: now validates email + checks duplicates + sends OTP via `email_mod.send_otp_email()` → transitions to `ONBOARD_VERIFY_EMAIL_OTP`
  - New `onboard_verify_email_otp()` handler: validates 6-digit input, calls `auth_mod.verify_email_otp()`, on success → `_complete_registration()`, on failure → retry with helpful message
  - Extracted `_complete_registration()` helper: contains all registration logic (tenant creation, agent upsert, audit logging, plan info, bot token offer) — called by both the new OTP handler and the fallback path
  - **Graceful fallback**: If email system not configured (`email_mod.is_enabled()` → False) or OTP send fails, skips verification and proceeds directly to registration (preserves existing behavior)
  - Registered `ONBOARD_VERIFY_EMAIL_OTP` in ConversationHandler states
- **Why**: Previously email was accepted without verification. Email OTP ensures the agent owns the email address, preventing typos and impersonation. Uses the existing `send_otp_email()` branded template in `biz_email.py`.
- **Flow**: `ONBOARD_PHONE → [VERIFY_OTP] → ONBOARD_EMAIL → [VERIFY_EMAIL_OTP] → registration → [BOT_TOKEN]`

---

### Phase 8 — Bulk Lead Import (CSV/Excel)
**Date**: 2025-01-28
**Files Changed**: `sarathi_biz.py`, `biz_database.py`, `static/dashboard.html`
**What**:
- **P8.1 — Enhanced `POST /api/import/leads` endpoint** (`sarathi_biz.py`):
  - Added multipart/form-data support for file uploads from dashboard (manual boundary parsing — no python-multipart dependency)
  - Supports `text/csv`, `application/json`, and file upload content types
  - Added `?assign_to=<agent_id>` query param for team/enterprise plans to assign imported leads to a specific agent
  - Per-field validation and truncation (max 500 chars per field, 200 for name)
  - Max 500 leads per import, rate-limited to 5/min
  - BOM-safe CSV parsing (`utf-8-sig`)
  - Audit logging of every import with counts
- **P8.2 — CSV Template Download** (`sarathi_biz.py`):
  - New `GET /api/import/template` endpoint returns a downloadable CSV template with header row and 2 sample data rows
- **P8.3 — Duplicate Detection** (`biz_database.py`):
  - `bulk_add_leads()` now accepts optional `tenant_id` parameter
  - When `tenant_id` provided, pre-loads all existing phone numbers across the tenant's agents
  - Skips leads with duplicate phone numbers (both existing and within the same import batch)
  - Returns `duplicates` count in result dict alongside `imported` and `skipped`
- **P8.4 — Dashboard Import UI** (`static/dashboard.html`):
  - New "📥 Import CSV" button in leads toolbar (next to "+ Add Lead")
  - Full import modal with: instructions, file input (.csv), template download link, agent assignment dropdown (team plans only), 5-row preview table, import stats
  - Client-side CSV preview and validation before upload
  - Import results display with success/error/duplicate counts and error details
  - `parseCSV()`, `previewImport()`, `downloadTemplate()`, `importLeads()`, `showImportModal()` functions
- **Why**: Previous bulk import endpoint was minimal (raw body only, no file upload, no dedup, no UI). Financial advisors frequently need to import existing client lists from spreadsheets. This provides a complete end-to-end workflow with duplicate protection.

## DECISIONS MADE
- Affiliate program managed entirely from Super Admin (not mixed with CRM)
- Referral codes should be one-time single-use
- Web and bot are equal endpoints — both must be fully functional
- Agent isolation is strict: agents NEVER see each other's data
- Owner/Admin sees all data within their tenant only

## HOW TO USE THIS FILE
1. **New session**: Read BUILD_LOG.md FIRST before any work
2. **After changes**: Append to CHANGE LOG section with: date, files changed, what, why, wire impact
3. **Never delete**: Only append — full history preserved
4. **Key principle**: Anyone reading just this file can understand the entire project state
