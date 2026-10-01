# Sarathi-AI Business Technologies — Role-Based Flow Completeness Audit

**Date:** 2025-01-XX  
**Scope:** Full codebase read-only audit  
**Auditor:** Automated code analysis  
**Files Audited:** `biz_bot.py` (5307 lines), `sarathi_biz.py` (2284 lines), `biz_database.py` (1691 lines), `biz_auth.py` (~500 lines), `biz_i18n.py` (415 lines), `static/admin.html` (611 lines), `static/dashboard.html` (844 lines), `static/index.html` (2103 lines), `static/onboarding.html` (521 lines)

---

## EXECUTIVE SUMMARY

The codebase implements a **two-role model** (`'owner'` and `'agent'`), not the four-role model (Super Admin, Admin/Owner, Agent, Individual) that the product concept implies. The "Super Admin" is an environment-variable API key holder with no DB identity. The "Individual" (solo advisor) is simply an `'owner'` with `max_agents=1`. There is no `'admin'`, `'super_admin'`, or `'individual'` role value in the database. Authorization is consistently **thin** — most features are accessible to all registered users regardless of role, with only a handful of owner-only gates.

**Critical gap count:** 5  
**High gap count:** 10  
**Medium gap count:** 8  
**Low gap count:** 4  

---

## SECTION A: COMPLETE ROLE FLOW TRACES

### A1. SUPER ADMIN ROLE

**Existence:** ❌ Does NOT exist as a database role  
**Implementation:** API-key-based auth via `ADMIN_API_KEY` env variable (default: `"sarathi-admin-2024-secure"`)

#### Entry Flow
1. User navigates to `/admin` → `sarathi_biz.py` line 306: serves `admin.html` with **NO authentication check** on page load
2. `admin.html` line 155–162: Shows login screen with password field ("Enter Admin API Key")
3. `admin.html` line 310–330: `doLogin()` validates key by calling `GET /api/admin/stats?key=<key>`
4. Backend auth: `biz_auth.py` `require_admin()` checks `Authorization: Bearer admin:<key>` header OR `?key=` query param against `ADMIN_API_KEY` env var

#### Available Capabilities
| Capability | Endpoint | Auth |
|---|---|---|
| View all tenants | `GET /api/admin/tenants` | API key |
| Platform stats | `GET /api/admin/stats` | API key |
| Extend trial | `POST /api/admin/tenant/{id}/extend` | API key |
| Activate subscription | `POST /api/admin/tenant/{id}/activate` | API key |
| Deactivate tenant | `POST /api/admin/tenant/{id}/deactivate` | API key |
| List running bots | `GET /api/admin/bots` | API key |
| Restart tenant bot | `POST /api/admin/tenant/{id}/bot/restart` | API key |
| Stop tenant bot | `POST /api/admin/tenant/{id}/bot/stop` | API key |

#### What's Missing
- **No DB identity** — admin is whoever has the key; no audit trail of which person acted
- **No Telegram bot commands** for super admin (no `/admin` command in bot)
- **No user-management** — cannot create/delete tenants from admin panel
- **No ability to view individual agent data** or impersonate tenants
- **No revenue/MRR reporting** — stats only show counts
- **No role-based admin levels** — single shared key for all admin users

---

### A2. ADMIN (FIRM OWNER) ROLE

**Database value:** `role = 'owner'` in `agents` table  
**Assigned at:** `biz_bot.py` cmd_start → onboard_firm flow (line ~400+)  
**Also at:** `sarathi_biz.py` api_signup → creates tenant, but does NOT create an agent row (agent created when user /start's the bot)

#### Entry Flow — Web Signup
1. `index.html` → Click "Start Free Trial" on any plan → `openSignup(plan)` 
2. `submitSignup()` (index.html line 1783) → `POST /api/signup` with firm_name, owner_name, phone, plan
3. `sarathi_biz.py` line 609: `api_signup()` creates tenant row (phone-locked trial), returns `tenant_id`
4. User redirected to `/onboarding?tenant_id=X&phone=Y` (onboarding.html)
5. Onboarding steps: (1) Connect Telegram bot token, (2) WhatsApp credentials, (3) Branding
6. **NO agent row created yet** — owner becomes an agent only when they `/start` the Telegram bot with the deep link

#### Entry Flow — Telegram Direct
1. User sends `/start` to @SarathiBizBot → `biz_bot.py` cmd_start (line ~290)
2. If not registered → shows "Create New Firm" vs "Join Existing Firm" buttons
3. "Create New Firm" → `onboard_firm` → `onboard_name` → `onboard_phone` → `onboard_email`
4. Creates tenant via `db.create_tenant()`, creates agent with `role='owner'`

#### Owner-Only Gates in Bot
| Feature | Location | Gate Mechanism |
|---|---|---|
| Team / Invite Agent (settings) | `biz_bot.py` ~line 2920 | `agent.get('role') == 'owner'` |
| /team command | `biz_bot.py` ~line 4530 | `agent.get('role') not in ('owner', 'admin')` |
| _team_callback | `biz_bot.py` ~line 4570 | `agent.get('role') not in ('owner', 'admin')` |
| Edit firm name in /editprofile | `biz_bot.py` ~line 3070 | `agent.get('role') == 'owner'` adds extra button |

#### Owner-Only Gates in Web API
| Feature | Endpoint | Gate |
|---|---|---|
| **NONE** — see findings below | | |

**CRITICAL FINDING:** Web API agent management endpoints (`/api/agents/{id}/deactivate`, `/api/agents/{id}/reactivate`, `/api/agents/transfer`, `/api/agents/{id}/remove`) use `Depends(auth.get_current_tenant)` which returns `{tenant_id, phone, firm}` — **NO role check**. Any authenticated user from the same tenant (including regular agents) can deactivate/remove other agents via the web API.

#### What the Owner CANNOT Do (But Should)
- **View all agents' leads/data** — dashboard always shows first agent or owner's own data
- **Override agent assignment** — no reassignment UI
- **Set per-agent permissions** — no permission model exists
- **Configure subscription from bot** — must use web

---

### A3. AGENT ROLE

**Database value:** `role = 'agent'` (default) in `agents` table  
**Assigned at:** `biz_bot.py` onboard_invite flow — when user joins via invite code

#### Entry Flow
1. Owner generates invite code via Settings → Team / Invite Agent (bot)
2. New user sends `/start` to bot → selects "Join Existing Firm" → enters invite code
3. `onboard_invite()` validates code → `onboard_name` → `onboard_phone` → `onboard_email`
4. Agent created with `role='agent'`, `tenant_id` from invite code

#### Agent Access (IDENTICAL to Owner except 4 gates above)
- **Main menu keyboard**: IDENTICAL for all roles (`biz_bot.py` line 203–220)
- **Help text**: IDENTICAL for all roles (`biz_i18n.py` line 310) — shows same commands
- **All CRM commands**: /addlead, /leads, /pipeline, /followup, /convert, /policy, /calc, /renewals, /dashboard, /greet, /wa, /wadash, /wacalc, /claim, /claims, /claimstatus, /ai, /createbot, /wasetup — NO role check
- **Data isolation**: Agent can only see their OWN leads/policies (filtered by `agent_id`), NOT other agents' data ✅

#### What Agent Can Do But Shouldn't
- Access `/api/agents/{id}/deactivate` etc. via web API (no role check)
- Access `/api/subscription/upgrade` and `/api/subscription/downgrade` (tenant-level, any authenticated user)
- See "Team / Invite Agent" button in settings keyboard (shown to all; rejected on click if not owner)

---

### A4. INDIVIDUAL (SOLO ADVISOR) ROLE

**Existence:** ❌ Does NOT exist as a distinct role  
**Implementation:** An individual is an `'owner'` with `plan='individual'` and `max_agents=1`

#### Entry Flow
1. Web: Click "Solo Advisor (₹199/mo)" on index.html → `openSignup('individual',...)`
2. Same signup flow as any other plan — creates tenant with `plan='individual'`, `max_agents=1`
3. Bot: Same `/start` flow, but if they create a firm on master bot, default plan is `'trial'`

#### Behavioral Differences
- `PLAN_FEATURES['individual']` (`biz_database.py` ~line 420): `max_agents=1`, no WhatsApp, no custom bot, no campaigns, no AI features
- Plan feature gates via `db.check_plan_feature()` — checked in some web API routes
- **Bot commands do NOT check plan features** — an individual plan user can use /ai, /calc, /wa etc. from Telegram without restriction

---

## SECTION B: SPECIFIC AREA CHECKS

### B1. `cmd_start` — Registration & Onboarding (`biz_bot.py` ~line 290–495)

**Flows covered:**
1. ✅ Already registered → shows welcome back + main menu
2. ✅ Deep link from web signup (`/start web_{tenant_id}`) → creates agent as owner for that tenant
3. ✅ Per-tenant bot → auto-registers user to that tenant
4. ✅ Master bot — new user → "Create New Firm" / "Join Existing Firm" choice
5. ✅ Create New Firm → multi-step conversation → creates tenant + owner agent
6. ✅ Join via invite code → validates code → creates agent

**Gaps:**
- ❌ No "Individual" onboarding path distinct from "Create New Firm"
- ❌ No plan selection during Telegram onboarding — always creates as `trial`
- ❌ Web signup creates tenant but NO agent row — user must also `/start` the bot
- ❌ No guidance in onboarding about which plan features are available
- ❌ Deep link `web_{tenant_id}` has no expiry/validation — anyone with the link becomes owner

### B2. `cmd_help` — Help Text (`biz_bot.py` ~line 2240; `biz_i18n.py` line 310)

```python
# biz_bot.py ~line 2240
async def cmd_help(update, context):
    agent = context.user_data.get('_agent') or await _get_agent(update)
    lang = agent.get('lang', 'en') if agent else 'en'
    await update.message.reply_text(i18n.t(lang, "help_text"), parse_mode=ParseMode.HTML)
```

**Finding:** Single help text for ALL roles. No role-based command filtering.

**Commands registered in `build_bot()` but NOT in help_text:**
| Command | Why Missing |
|---|---|
| `/settings` | Settings available but not listed |
| `/plans` | Subscription plans not listed |
| `/ai` | AI Tools not listed |
| `/team` | Owner-only team management not listed |
| `/createbot` | Bot creation guide not listed |
| `/wasetup` | WhatsApp setup guide not listed |
| `/cancel` | Cancel command not listed |

**Commands in help_text but that should be role-gated:**
- `/wa`, `/wadash`, `/wacalc` — require WhatsApp configured (plan-gated for `individual` plan but not enforced in bot)

### B3. Role-Checking Logic (`registered` decorator, `biz_bot.py` line 248–278)

```python
def registered(func):
    @wraps(func)
    async def wrapper(update, context):
        agent = await db.get_agent(user_id)
        if not agent: → prompt /start
        if agent.tenant_id: check subscription active
        if bot_tenant_id: check agent belongs to this tenant
        context.user_data['_agent'] = agent
        return await func(update, context)
```

**Finding:** The `registered` decorator has **ZERO role-based logic**. It checks:
1. ✅ Agent exists in DB
2. ✅ Subscription is active
3. ✅ Tenant isolation for per-tenant bots
4. ❌ Does NOT check role
5. ❌ Does NOT check plan features
6. ❌ Does NOT check `is_active` flag

**CRITICAL:** `is_active` is NOT checked by the `registered` decorator. A deactivated agent (`is_active=0`) can still use the bot — the decorator only checks if the agent row exists, not the `is_active` field.

### B4. Dashboard Role Sections (`static/dashboard.html`)

**Finding:** Single unified view (844 lines). NO role-based sections whatsoever.

- Auth: checks `localStorage.sarathi_token` (JWT), redirects to `/?login=1` if missing
- Data: Fetches `GET /api/dashboard` which returns agent-scoped data
- Displays: summary cards, pipeline funnel, follow-ups, renewals, quick actions
- **No admin view**, no team management tab, no agent comparison, no firm-level reporting
- Subscription banner shows trial/active/expired — same for owner and agent

### B5. `/admin` Endpoint (`sarathi_biz.py` line 306)

```python
@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    admin_file = static_dir / "admin.html"
    return HTMLResponse(admin_file.read_text(encoding="utf-8"))
```

**Finding:** Page served with **NO server-side auth check**. The full HTML (including all admin UI markup) is sent to any visitor. Auth happens client-side in JavaScript when the user enters the API key.

**Security concern:** Anyone can view the admin page HTML structure. The API key is sent as a query parameter (`?key=...`) in GET requests, which means it appears in:
- Browser URL bar
- Browser history
- Server access logs
- Proxy logs

### B6. Onboarding Endpoints (`sarathi_biz.py` lines 596–770; `static/onboarding.html`)

**Web signup flow:**
1. `POST /api/signup` — creates tenant, NO auth required (open endpoint, rate limited)
2. `/onboarding?tenant_id=X&phone=Y` — static page, NO auth check
3. `POST /api/onboarding/telegram-bot` — requires `Depends(auth.get_current_tenant)` (JWT)
4. `POST /api/onboarding/whatsapp` — requires JWT
5. `POST /api/onboarding/branding` — requires JWT

**Gap:** Steps 1 and 2 have no auth, but steps 3–5 require JWT. There's no OTP/login step between signup and onboarding — user gets redirected to `/onboarding?tenant_id=X&phone=Y` but has no JWT token yet. The onboarding page would fail on save unless user logged in separately.

**Gap:** Onboarding page accessible with `tenant_id` and `phone` as query params — no verification that the visitor is the account owner.

### B7. DB Schema — Role Model (`biz_database.py`)

```sql
-- agents table (line ~96)
CREATE TABLE IF NOT EXISTS agents (
    agent_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id      INTEGER REFERENCES tenants(tenant_id),
    telegram_id    TEXT UNIQUE NOT NULL,
    name           TEXT NOT NULL,
    phone          TEXT,
    email          TEXT,
    lang           TEXT DEFAULT 'en',
    role           TEXT DEFAULT 'agent',    -- Only 'agent' or 'owner'
    is_active      INTEGER DEFAULT 1,
    ...
)
```

**Role values actually used in code:**
| Value | Where Set | Where Checked |
|---|---|---|
| `'owner'` | `cmd_start` onboarding | settings_team, cmd_team, _team_callback, cmd_editprofile, remove_agent |
| `'agent'` | Default / invite join | (nowhere — it's the catch-all) |
| `'admin'` | **NEVER set** | cmd_team and _team_callback check `not in ('owner', 'admin')` |
| `'super_admin'` | **NEVER** | **NEVER** |
| `'individual'` | **NEVER** | **NEVER** |

**Plan-based feature gates (`biz_database.py` PLAN_FEATURES ~line 420):**
```python
PLAN_FEATURES = {
    'trial':      {'max_agents': 2, 'whatsapp': True,  'custom_bot': False, 'campaigns': False, 'ai_features': True,  ...},
    'individual': {'max_agents': 1, 'whatsapp': False, 'custom_bot': False, 'campaigns': False, 'ai_features': False, ...},
    'team':       {'max_agents': 5, 'whatsapp': True,  'custom_bot': True,  'campaigns': True,  'ai_features': True,  ...},
    'enterprise': {'max_agents': 25,'whatsapp': True,  'custom_bot': True,  'campaigns': True,  'ai_features': True,  ...},
}
```

**CRITICAL:** Individual plan disables AI features (`ai_features: False`) and WhatsApp (`whatsapp: False`), but the Telegram bot **never calls `check_plan_feature()`** — all commands work regardless of plan.

### B8. Auth Flow (`biz_auth.py`)

**JWT Token Contents:**
```python
payload = {
    "sub": str(tenant_id),    # Tenant ID
    "phone": phone,            # Owner phone
    "firm": firm_name,         # Firm name
    "type": "access",
    "iat": now, "exp": expiry
}
```

**Missing from JWT:** `role`, `agent_id`, `is_active`, `plan`

**Consequence:** Web dashboard CANNOT determine if the logged-in user is an owner or agent — JWT only identifies the tenant. All web API actions are tenant-scoped, not role-scoped.

**OTP Login:** Phone-based only. Matches against `tenants.phone` — only the owner's phone works. Agents CANNOT log in to the web dashboard unless their phone happens to be the tenant's phone.

**Admin Auth:** Completely separate system — env var API key, no identity, no audit trail.

---

## SECTION C: GAP IDENTIFICATION (Priority-Sorted)

### 🔴 CRITICAL (Security / Data Integrity)

**C1. Deactivated agents can still use the bot**  
- **Location:** `biz_bot.py` line 248–278 (`registered` decorator)
- **Issue:** `is_active` flag is NOT checked. `deactivate_agent()` sets `is_active=0` but the `registered` decorator only checks if the agent row exists.
- **Impact:** Fired/removed agents retain full CRM access.
- **Fix:** Add `if not agent.get('is_active', 1): return "Account deactivated"` to `registered` decorator.

**C2. Agent management APIs have no owner-role check**  
- **Location:** `sarathi_biz.py` lines 1840–1900 (`/api/agents/{id}/deactivate`, `/reactivate`, `/transfer`, `/remove`)
- **Issue:** These endpoints use `Depends(auth.get_current_tenant)` which returns tenant info only — no role check. Any authenticated user from the same tenant can deactivate owners or other agents.
- **Impact:** An agent could deactivate the firm owner, remove other agents, or transfer their data.
- **Note:** `remove_agent()` in DB layer does protect against removing the owner role, but deactivation has no such guard.

**C3. Admin API key in query parameters**  
- **Location:** `static/admin.html` line 315, `biz_auth.py` `require_admin()`
- **Issue:** Admin key sent as `?key=<value>` in GET requests. Logged in browser history, server access logs, proxy logs.
- **Impact:** API key exposure risk. Single shared key with no identity — cannot revoke individual access.

**C4. JWT tokens contain no role information**  
- **Location:** `biz_auth.py` `create_access_token()`
- **Issue:** JWT payload has `{sub: tenant_id, phone, firm}` but no `role`, `agent_id`, or `is_active`. Web APIs cannot distinguish owner from agent.
- **Impact:** All web API operations are tenant-scoped, not role-gated. Cannot implement proper authorization.

**C5. Plan features NOT enforced in Telegram bot**  
- **Location:** All `@registered` command handlers in `biz_bot.py`
- **Issue:** `PLAN_FEATURES` defines `ai_features: False` for `individual` plan and `whatsapp: False`, but no bot command calls `check_plan_feature()`.
- **Impact:** Individual plan users get the same features as Enterprise via Telegram — only limited via web API.

---

### 🟠 HIGH (Functional Gaps)

**H1. Only 2 roles exist; need is for 4**  
- **Location:** `biz_database.py` agents table schema
- **Issue:** Only `'owner'` and `'agent'` role values. No `'super_admin'` or `'individual'` role. The `'admin'` value is checked in code (`cmd_team`) but never assigned.
- **Impact:** Cannot implement differentiated experiences per role type.

**H2. Help text is identical for all roles**  
- **Location:** `biz_i18n.py` line 310; `biz_bot.py` cmd_help
- **Issue:** Single `help_text` string shown to everyone. 6 registered commands not listed. No owner-specific or plan-specific sections.
- **Impact:** Users don't know about advanced features (/ai, /team, /plans, /settings); owners see the same limited help as agents.

**H3. Main menu keyboard identical for all roles**  
- **Location:** `biz_bot.py` `_main_menu_keyboard()` line 203–220
- **Issue:** Same 9 buttons for all users. No owner-specific buttons (Team, Settings), no plan-based hiding.
- **Impact:** Agents see "AI Tools" button even if their plan doesn't include AI.

**H4. Dashboard has no team/admin view**  
- **Location:** `static/dashboard.html`
- **Issue:** Single-agent dashboard. Owner cannot see aggregate firm data, compare agent performance, or manage team.
- **Impact:** Owner value proposition (team oversight) is missing from web UI.

**H5. Agents cannot log into web dashboard**  
- **Location:** `biz_auth.py` OTP login; `sarathi_biz.py` api_send_otp
- **Issue:** OTP login matches on `tenants.phone` — only the owner's registered phone. Agents have their own phone in `agents.phone` but this isn't checked for login.
- **Impact:** Only the tenant owner can use the web dashboard. All agents are locked out.

**H6. Web signup creates tenant but not agent**  
- **Location:** `sarathi_biz.py` `api_signup()` line 609–695
- **Issue:** Creates `tenants` row but no `agents` row. The owner's agent record is only created when they `/start` the Telegram bot with the deep link.
- **Impact:** Owner has a tenant account but can't use the CRM until they also onboard via Telegram. Dashboard shows empty data if they skip the bot step.

**H7. `/admin` page served without auth**  
- **Location:** `sarathi_biz.py` line 306
- **Issue:** Full admin HTML served to any visitor. Auth is client-side JavaScript only.
- **Impact:** Admin page structure, API endpoint patterns, and UI logic exposed. Attacker can craft requests against admin APIs.

**H8. Onboarding page has auth gap**  
- **Location:** `sarathi_biz.py` onboarding page/API flow
- **Issue:** Signup returns `tenant_id` and redirects to `/onboarding?tenant_id=X&phone=Y`, but onboarding APIs require JWT. No OTP login inserted between signup and onboarding.
- **Impact:** Onboarding save buttons will fail because user has no JWT token after signup. Users get stuck.

**H9. Settings keyboard shows team button to all**  
- **Location:** `biz_bot.py` `_settings_keyboard()` line 227–233
- **Issue:** "Team / Invite Agent" button shown to ALL users. Only rejected at click time for non-owners.
- **Impact:** Poor UX — agents see options they can't use.

**H10. Deep link `web_{tenant_id}` has no validation**  
- **Location:** `biz_bot.py` cmd_start deep link handling
- **Issue:** Anyone who crafts a `/start web_123` message becomes the owner-agent for tenant 123.
- **Impact:** Tenant hijacking if tenant_id is guessable (auto-increment integer).

---

### 🟡 MEDIUM (UX / Completeness)

**M1. No role in audit log trail**  
- **Location:** `biz_database.py` `log_audit()` — logs `tenant_id`, `agent_id`, `action`, `detail`, `ip`
- **Issue:** No `role` field. Cannot distinguish owner vs agent actions in audit.

**M2. Subscription upgrade/downgrade accessible to any tenant user**  
- **Location:** `sarathi_biz.py` `/api/subscription/upgrade`, `/api/subscription/downgrade`
- **Issue:** JWT auth only — any authenticated user can change the plan (not just owner).

**M3. `/api/dashboard` picks "first agent" as fallback**  
- **Location:** `sarathi_biz.py` dashboard API
- **Issue:** If no `agent_id` specified, returns first found agent's data. Doesn't verify it's the caller's data.

**M4. No plan selection in Telegram onboarding**  
- **Location:** `biz_bot.py` cmd_start → Create New Firm flow
- **Issue:** Telegram-only signups always get `trial` plan. No way to choose individual/team/enterprise.

**M5. `'admin'` role check exists but role is never assignable**  
- **Location:** `biz_bot.py` cmd_team line ~4533, _team_callback line ~4571
- **Issue:** Code checks `role not in ('owner', 'admin')` but 'admin' is never set in any code path.
- **Impact:** Dead code — the 'admin' role branch can never be reached.

**M6. Invite code has no expiry**  
- **Location:** `biz_database.py` invite_codes table / `biz_bot.py` onboard_invite
- **Issue:** Generated invite codes don't appear to have TTL. An old code could be reused indefinitely.

**M7. CSV import via bot has no owner/plan check**  
- **Location:** `biz_bot.py` `_csv_import_handler()` line ~4660
- **Issue:** Any registered agent can bulk-import 500 leads. No plan-based limit check.

**M8. No CSRF protection on admin actions**  
- **Location:** `static/admin.html` admin action functions
- **Issue:** Admin actions (extend, activate, deactivate) use simple GET/POST with key in query param. No CSRF token.

---

### 🟢 LOW (Polish / Nice-to-Have)

**L1. Default admin key is hardcoded**  
- **Location:** `sarathi_biz.py` line 303: `ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "sarathi-admin-2024-secure")`
- **Issue:** If env var not set, default key is in source code.

**L2. Error handler leaks no data (good) but logs stack traces**  
- **Location:** `biz_bot.py` `_error_handler()` line ~5230
- **Status:** ✅ Correct — user gets generic message, full trace logged server-side.

**L3. Rate limiting exists but is IP-based on web, user-based on bot**  
- **Location:** Various `@limiter.limit()` decorators in `sarathi_biz.py`; `_rate_limited()` in `biz_bot.py`
- **Issue:** Inconsistent rate limiting strategies.

**L4. Password field for admin key sends as query param on login check**  
- **Location:** `admin.html` line 315: `fetch('/api/admin/stats?key=...')`
- **Issue:** Initial login validation sends key in URL. Subsequent calls also use query param.

---

## SECTION D: COMMAND REGISTRATION SUMMARY

### All registered handlers in `build_bot()` (biz_bot.py ~line 5015–5200):

| Command | Handler | Auth Decorator | Role Check | Plan Check |
|---|---|---|---|---|
| `/start` | `cmd_start` | None (open) | N/A | ❌ |
| `/addlead` | `cmd_addlead` | `@registered` | ❌ | ❌ |
| `/pipeline` | `cmd_pipeline` | `@registered` | ❌ | ❌ |
| `/leads` | `cmd_leads` | `@registered` | ❌ | ❌ |
| `/lead` | `cmd_lead` | `@registered` | ❌ | ❌ |
| `/followup` | `cmd_followup` | `@registered` | ❌ | ❌ |
| `/convert` | `cmd_convert` | `@registered` | ❌ | ❌ |
| `/policy` | `cmd_policy` | `@registered` | ❌ | ❌ |
| `/calc` | `cmd_calc` | `@registered` | ❌ | ❌ |
| `/renewals` | `cmd_renewals` | `@registered` | ❌ | ❌ |
| `/dashboard` | `cmd_dashboard` | `@registered` | ❌ | ❌ |
| `/wa` | `cmd_wa` | `@registered` | ❌ | ❌ |
| `/wacalc` | `cmd_wacalc` | `@registered` | ❌ | ❌ |
| `/wadash` | `cmd_wadash` | `@registered` | ❌ | ❌ |
| `/greet` | `cmd_greet` | `@registered` | ❌ | ❌ |
| `/lang` | `cmd_lang` | `@registered` | ❌ | ❌ |
| `/settings` | `cmd_settings` | `@registered` | ❌ | ❌ |
| `/editprofile` | `cmd_editprofile` | `@registered` | Partial* | ❌ |
| `/editlead` | `cmd_editlead` | `@registered` | ❌ | ❌ |
| `/help` | `cmd_help` | `@registered` | ❌ | ❌ |
| `/plans` | `cmd_plans` | `@registered` | ❌ | ❌ |
| `/claim` | `cmd_claim` | `@registered` | ❌ | ❌ |
| `/claims` | `cmd_claims` | `@registered` | ❌ | ❌ |
| `/claimstatus` | `cmd_claimstatus` | `@registered` | ❌ | ❌ |
| `/ai` | `cmd_ai` | `@registered` | ❌ | ❌ |
| `/team` | `cmd_team` | `@registered` | ✅ owner/admin | ❌ |
| `/createbot` | `cmd_createbot` | `@registered` | ❌ | ❌ |
| `/wasetup` | `cmd_whatsapp_setup` | `@registered` | ❌ | ❌ |
| `/cancel` | `cancel` | None | N/A | ❌ |
| Voice | `_voice_to_action` | Internal check | ❌ | ❌ |
| CSV file | `_csv_import_handler` | Internal check | ❌ | ❌ |

*`/editprofile` shows an extra "Firm Name" edit option for owners but doesn't restrict other edits.

---

## SECTION E: RECOMMENDATIONS (Priority Order)

1. **Add `is_active` check to `registered` decorator** — 1 line fix, critical security
2. **Add role field to JWT tokens** — enables web-side authorization
3. **Add owner-role checks to agent management APIs** — prevent agent self-service escalation
4. **Move admin key to header-only auth** — stop sending in query params
5. **Implement plan feature gates in bot commands** — enforce subscription value
6. **Add role-based help text** — owners see team commands, agents see their scope
7. **Add role-based menu keyboard** — hide buttons users can't use
8. **Create owner dashboard view** — team stats, agent comparison, firm-level data
9. **Enable agent login to web dashboard** — match on `agents.phone` not just `tenants.phone`
10. **Add server-side auth to `/admin` page** — redirect if not authenticated
11. **Add deep link validation** — sign or expire `web_{tenant_id}` links
12. **Implement proper 4-role model** — add `'super_admin'` and `'individual_advisor'` role values with distinct permission sets

---

*End of Audit Report*
