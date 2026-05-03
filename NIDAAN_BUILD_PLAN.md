# NIDAAN PARTNER — BUILD PLAN

> **Companion to:** `PROJECT_MASTER_CONTEXT.md` Section 30
> **Status:** Locked spec. Phase 1a ready to begin on approval.
> **Last Updated:** May 2, 2026

---

## 0. SUMMARY OF LOCKED DECISIONS

| # | Decision | Value |
|---|----------|-------|
| 1 | Architecture | **Plug-and-play v2.** One FastAPI app, one SQLite DB. Sarathi tables untouched. New `nidaan_*` tables. Single bridge table `product_link`. Two Nginx server-blocks routed by `Host:` header. |
| 2 | Domain | `nidaanpartner.com` (just purchased on Cloudflare; DNS not yet pointed). |
| 3 | Sarathi schema impact | **2 columns only**: `tenants.plan_source` ('self_paid'\|'nidaan_bundle') + `tenants.bundled_until` DATE. |
| 4 | Bundling rule | Nidaan plan auto-grants matching Sarathi tier (Silver→Solo, Gold→Team, Platinum→Enterprise). Daily cron downgrades Sarathi to trial 30 days after Nidaan sub lapses. |
| 5 | Per-claim direct-to-consumer fee | **₹999** one-time legal review. |
| 6 | SMS provider | **Fast2SMS** (DLT registration in progress; awaiting Jio response). |
| 7 | Sub-super-admin spending cap | **₹0** — all refunds require super-admin approval. |
| 8 | Bilingual | EN + HI on every Nidaan-facing page; same toggle pattern as Sarathi (`localStorage.nidaan_lang`, auto-detect from `navigator.language`). |
| 9 | Sensitive docs | **NOT stored.** Only insured contact info captured. Nidaan legal team collects documents offline. |
| 10 | Admin roles | Super-admin (you / Nidaan owner), Sub-super-admin (operations head), Legal-agent (team member assigned claims). |
| 11 | Phase 1 first deliverable | **(a) Homepage + DNS + Nginx first** (visible quick win for Nidaan LLP team validation). DB + admin scaffolding in parallel. |
| 12 | Brochure source | `c:\Users\imdus\Downloads\NIDAAN BROCHER HINDI.pdf` — extract claim categories, positioning, credentials, FAQ. Translate Hindi-only content to English. |

---

## 1. PLUG-AND-PLAY ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────┐
│  ONE FastAPI codebase, ONE VM (Oracle Cloud), ONE SQLite DB         │
│  Two Nginx server-blocks → same backend on port 8001                │
│  Routing decided by request.headers['host']                         │
└─────────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────────────────┴───────────────────────┐
        │                                               │
   sarathi-ai.com                                 nidaanpartner.com
   (SARATHI product)                              (NIDAAN product)
        │                                               │
   ┌────▼────────┐                               ┌─────▼──────────┐
   │ tenants     │                               │ nidaan_accounts│
   │ users       │                               │ nidaan_users   │
   │ leads       │                               │ nidaan_subs    │
   │ policies    │                               │ nidaan_claims  │
   │ ...         │                               │ nidaan_admins  │
   │ (UNCHANGED) │                               │ ...            │
   └─────────────┘                               └────────────────┘
              ╲                                          ╱
               ╲       ┌──────────────────────────────╲ ╱
                ╲      │  product_link (THIN BRIDGE)  │
                 ╲     │ ─────────────────────────────│
                  ─────│ link_id PK                   │
                       │ nidaan_account_id FK         │
                       │ sarathi_tenant_id FK NULL    │
                       │ source 'nidaan_bundle' |     │
                       │        'sarathi_addon'       │
                       │ active, linked_at,           │
                       │ unlinked_at                  │
                       └──────────────────────────────┘
```

### Why this is plug-and-play
- Sarathi runs identically whether Nidaan exists or not.
- All Nidaan code lives in **`biz_nidaan.py`** + Nidaan routes mounted under host-header guard in `sarathi_biz.py`.
- **Removal procedure:** drop nginx server-block → delete `nidaan_*` tables → delete `biz_nidaan.py` → remove Claims buttons from Sarathi templates → set `tenants.plan_source='self_paid'`, `bundled_until=NULL` for affected rows. Zero schema rewrite. Zero downtime.

---

## 2. DATA MODEL

### 2.1 Sarathi-side change (additive only)

```sql
-- Migration: 20260502_add_plan_source.sql
ALTER TABLE tenants ADD COLUMN plan_source TEXT DEFAULT 'self_paid';
ALTER TABLE tenants ADD COLUMN bundled_until DATE NULL;
CREATE INDEX idx_tenants_plan_source ON tenants(plan_source);
```

### 2.2 New Nidaan tables (all prefixed `nidaan_`)

```sql
-- Customer firm/account (the advisor or enterprise that bought a Nidaan plan)
CREATE TABLE nidaan_accounts (
  account_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  owner_name        TEXT NOT NULL,
  firm_name         TEXT,
  email             TEXT NOT NULL UNIQUE,
  phone             TEXT NOT NULL,
  password_hash     TEXT,
  google_sub        TEXT,
  status            TEXT DEFAULT 'active',  -- active|suspended|cancelled
  notes             TEXT,                   -- super-admin only
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login_at     TIMESTAMP
);
CREATE INDEX idx_nidaan_accounts_email ON nidaan_accounts(email);

-- Sub-users under an account (Gold = up to 5, Platinum = unlimited)
CREATE TABLE nidaan_users (
  user_id           INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id        INTEGER NOT NULL REFERENCES nidaan_accounts(account_id),
  name              TEXT NOT NULL,
  email             TEXT NOT NULL,
  password_hash     TEXT,
  role              TEXT DEFAULT 'agent',   -- owner|agent
  status            TEXT DEFAULT 'invited', -- invited|active|disabled
  invited_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  joined_at         TIMESTAMP,
  UNIQUE(account_id, email)
);

-- Subscriptions (quarterly via Razorpay)
CREATE TABLE nidaan_subscriptions (
  sub_id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id                INTEGER NOT NULL REFERENCES nidaan_accounts(account_id),
  plan                      TEXT NOT NULL,  -- silver|gold|platinum
  amount_paid               INTEGER NOT NULL,         -- paise
  billing_cycle             TEXT DEFAULT 'quarterly',
  razorpay_subscription_id  TEXT,
  started_at                TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  current_period_end        TIMESTAMP,
  status                    TEXT DEFAULT 'active',    -- active|past_due|cancelled|expired
  auto_renew                INTEGER DEFAULT 1
);
CREATE INDEX idx_nidaan_subs_account ON nidaan_subscriptions(account_id);
CREATE INDEX idx_nidaan_subs_status ON nidaan_subscriptions(status);

-- Claims (lead-gen core; NO sensitive docs stored)
CREATE TABLE nidaan_claims (
  claim_id                INTEGER PRIMARY KEY AUTOINCREMENT,
  account_id              INTEGER NOT NULL REFERENCES nidaan_accounts(account_id),
  user_id                 INTEGER REFERENCES nidaan_users(user_id),
  claim_type              TEXT NOT NULL,    -- mediclaim|vehicle|life|property|travel|other
  insured_name            TEXT NOT NULL,
  insured_phone           TEXT NOT NULL,
  insured_email           TEXT,
  insurer_name            TEXT,
  policy_no               TEXT,
  disputed_amount         INTEGER,          -- rupees
  claim_event_date        DATE,
  type_specific           TEXT,             -- JSON; only NON-SENSITIVE fields per type
  notes_from_agent        TEXT,
  status                  TEXT DEFAULT 'intimated',
                          -- intimated|assigned|in_review|in_negotiation
                          -- |resolved_won|resolved_lost|closed|withdrawn
  assigned_to_legal_user_id INTEGER REFERENCES nidaan_admins(admin_id),
  created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_status_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  closed_at               TIMESTAMP
);
CREATE INDEX idx_nidaan_claims_account ON nidaan_claims(account_id);
CREATE INDEX idx_nidaan_claims_status ON nidaan_claims(status);
CREATE INDEX idx_nidaan_claims_assigned ON nidaan_claims(assigned_to_legal_user_id);
CREATE INDEX idx_nidaan_claims_created ON nidaan_claims(created_at);

-- Status history per claim
CREATE TABLE nidaan_claim_status_log (
  log_id            INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id          INTEGER NOT NULL REFERENCES nidaan_claims(claim_id),
  from_status       TEXT,
  to_status         TEXT NOT NULL,
  note              TEXT,
  changed_by_type   TEXT NOT NULL,  -- advisor|legal_team|system|super_admin
  changed_by_id     INTEGER,
  changed_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  notify_sent       TEXT            -- JSON {sms_agent, sms_insured, email_agent, email_insured}
);
CREATE INDEX idx_nidaan_status_log_claim ON nidaan_claim_status_log(claim_id);

-- Nidaan internal admins (super, sub-super, legal agents)
CREATE TABLE nidaan_admins (
  admin_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name              TEXT NOT NULL,
  email             TEXT NOT NULL UNIQUE,
  password_hash     TEXT,
  google_sub        TEXT,
  role              TEXT NOT NULL,    -- super_admin|sub_super_admin|legal_agent
  status            TEXT DEFAULT 'active',
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  last_login_at     TIMESTAMP
);

-- Direct-to-consumer per-claim review (₹999)
CREATE TABLE nidaan_per_claim_purchase (
  purchase_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  insured_name      TEXT NOT NULL,
  insured_phone     TEXT NOT NULL,
  insured_email     TEXT,
  insurer_name      TEXT,
  policy_no         TEXT,
  disputed_amount   INTEGER,
  brief_description TEXT,
  amount_paid       INTEGER NOT NULL,   -- 99900 paise
  razorpay_order_id TEXT,
  review_outcome    TEXT DEFAULT 'pending', -- pending|positive|negative
  review_note       TEXT,
  converted_to_claim_id INTEGER REFERENCES nidaan_claims(claim_id),
  created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  reviewed_at       TIMESTAMP
);

-- Quota cache (rolling 30-day window per account)
CREATE TABLE nidaan_plan_quota (
  account_id            INTEGER PRIMARY KEY REFERENCES nidaan_accounts(account_id),
  current_window_start  DATE NOT NULL,
  claims_this_window    INTEGER DEFAULT 0,
  updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- THE BRIDGE — only join between Sarathi and Nidaan
CREATE TABLE product_link (
  link_id              INTEGER PRIMARY KEY AUTOINCREMENT,
  nidaan_account_id    INTEGER NOT NULL REFERENCES nidaan_accounts(account_id),
  sarathi_tenant_id    INTEGER NULL REFERENCES tenants(tenant_id),
  source               TEXT NOT NULL,   -- 'nidaan_bundle' | 'sarathi_addon'
  active               INTEGER DEFAULT 1,
  linked_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  unlinked_at          TIMESTAMP
);
CREATE INDEX idx_product_link_nidaan ON product_link(nidaan_account_id);
CREATE INDEX idx_product_link_sarathi ON product_link(sarathi_tenant_id);
```

### 2.3 type_specific JSON shape (NO sensitive fields)

```jsonc
// Mediclaim
{ "hospital_name": "Apollo Indore", "treatment_summary": "Cardiac surgery" }
// Vehicle
{ "vehicle_no": "MP09 AB 1234", "accident_summary": "Rear-end collision" }
// Life
{ "nature_of_claim": "death|maturity|disability", "nominee_name": "..." }
// Property
{ "property_type": "home|shop|warehouse", "incident_summary": "..." }
// Travel
{ "trip_country": "...", "incident_summary": "..." }
```

---

## 3. SUBSCRIPTION & BUNDLING LIFECYCLE

### 3.1 Plans

| Plan | Price (quarterly) | Annual | Claims/month | Sarathi tier granted | Logins |
|------|-------------------|--------|--------------|----------------------|--------|
| **Silver**   | ₹1,500 | ₹6,000  | 3        | Solo       | 1 |
| **Gold**     | ₹3,000 | ₹12,000 | 6        | Team       | 5 |
| **Platinum** | ₹6,000 | ₹24,000 | Unlimited (soft cap 100/yr to flag abuse) | Enterprise | Unlimited |

### 3.2 On Nidaan plan purchase (Razorpay webhook)

```
1. Insert nidaan_subscription (status=active)
2. Map plan -> Sarathi tier (silver→solo, gold→team, platinum→enterprise)
3. Find or create Sarathi tenant by email match
4. Set tenants.plan = mapped_tier
       tenants.plan_source = 'nidaan_bundle'
       tenants.bundled_until = current_period_end
5. Insert into product_link(nidaan_account_id, sarathi_tenant_id, source='nidaan_bundle', active=1)
6. Send welcome email + SMS (bilingual)
```

### 3.3 Nidaan sub lapses (daily cron)

```
For each tenant where plan_source='nidaan_bundle' AND bundled_until < today:
   - Check linked nidaan_subscription.status
   - If still active: extend bundled_until to new period_end
   - If expired/cancelled: enter 30-day grace
       day -7: warn email "Your Sarathi-AI access ends in 7 days"
       day -1: warn email
       day  0: downgrade tenants.plan='trial', plan_source='self_paid', bundled_until=NULL
               keep all data; advisor can self-subscribe to keep features
   - Mark product_link.active=0, set unlinked_at
```

### 3.4 Partnership ends entirely (manual admin script)

```
python -m biz_nidaan.scripts.deactivate_bundle --notice-days=30
  - For each tenant where plan_source='nidaan_bundle':
      bundled_until = today + 30
      send email "Nidaan bundle ending. Self-subscribe in dashboard to keep access."
  - After 30 days the standard cron downgrades them to trial
  - Then ops can: drop nidaan_* tables, remove nginx server-block, delete biz_nidaan.py
```

---

## 4. ROUTING & HOST ROUTING

### 4.1 Nginx (production)

```nginx
# /etc/nginx/sites-available/nidaanpartner.com
server {
    listen 443 ssl http2;
    server_name nidaanpartner.com www.nidaanpartner.com;

    ssl_certificate     /etc/letsencrypt/live/nidaanpartner.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nidaanpartner.com/privkey.pem;

    # Same hardening as sarathi-ai.com
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header Content-Security-Policy "default-src 'self' https:; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https:; script-src 'self' 'unsafe-inline' https:; font-src 'self' https: data:;" always;

    client_max_body_size 5M;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name nidaanpartner.com www.nidaanpartner.com;
    return 301 https://$host$request_uri;
}
```

### 4.2 FastAPI host-header dispatch

A small middleware in `sarathi_biz.py` (or a dependency) maps `request.headers["host"]` → `request.state.product = "nidaan" | "sarathi"`. Routes can then guard themselves:

```python
def require_nidaan_host(request: Request):
    host = request.headers.get("host", "").lower().split(":")[0]
    if not host.endswith("nidaanpartner.com"):
        raise HTTPException(404)

@app.get("/", include_in_schema=False)
async def root(request: Request):
    if request.state.product == "nidaan":
        return FileResponse("static/nidaan_index.html")
    return FileResponse("static/index.html")
```

All Nidaan API routes prefixed `/api/nidaan/...` and gated by `require_nidaan_host`.

---

## 5. SMS / EMAIL AUTOMATION

### 5.1 Triggers

| Event | SMS to advisor | SMS to insured | Email to both |
|-------|----------------|----------------|---------------|
| Claim filed | ✅ confirmation + claim# | ✅ "Your advisor has registered your dispute…" | ✅ |
| Claim assigned | ✅ "Assigned to legal team" | ✅ "Lawyer assigned, expect call in 24h" | ✅ |
| Status: in_review | ✅ | ✅ | ✅ |
| Status: in_negotiation | ✅ | ✅ | ✅ |
| Status: resolved_won/lost | ✅ | ✅ | ✅ |
| Status: withdrawn | ✅ | optional | ✅ |

Nidaan official ops number is also SMS-notified on every new claim.

### 5.2 Fast2SMS DLT templates needed (you'll get these registered)

All templates bilingual (we register HI + EN variants separately under Fast2SMS DLT).

| Template ID (placeholder) | Trigger | Body |
|---------------------------|---------|------|
| `NIDAAN_CLAIM_NEW_AGENT` | Claim filed | "Claim #{var1} received for {var2}. Nidaan team will respond in 24 hrs. View: {var3}" |
| `NIDAAN_CLAIM_NEW_INSURED` | Claim filed | "Hi {var1}, your advisor {var2} has registered your insurance dispute with Nidaan Legal. Our team will call {var3} within 24 hrs. Ref #{var4}" |
| `NIDAAN_CLAIM_NEW_OPS` | Claim filed | "New claim #{var1} | {var2} | {var3} | Disputed Rs.{var4}. Insured: {var5} {var6}" |
| `NIDAAN_STATUS_AGENT` | Status change | "Claim #{var1} status: {var2}. Notes: {var3}" |
| `NIDAAN_STATUS_INSURED` | Status change | "Update on your claim #{var1}: {var2}. {var3}" |
| `NIDAAN_PERCLAIM_RECEIPT` | ₹999 review purchase | "Payment received Rs.999. Review #{var1}. Outcome by {var2}" |
| `NIDAAN_PERCLAIM_OUTCOME` | Review done | "Review #{var1} outcome: {var2}. {var3}" |

**Sender ID:** Apply for `NIDAAN` (6 chars, transactional). Your Jio DLT registration unlocks this. Once Jio confirms, we'll register all 7 templates on Fast2SMS dashboard.

### 5.3 SMS abstraction

`biz_sms.py` currently a stub. Phase 3 work:
- Add `Fast2SMSProvider` class with `.send(template_id, to_phone, vars: list)`.
- Configurable via env: `FAST2SMS_API_KEY`, `FAST2SMS_SENDER_ID=NIDAAN`, `FAST2SMS_DLT_ENTITY_ID`.
- All Nidaan SMS calls go through `biz_sms.send_nidaan(template_id, to, vars)` — provider swap is a 50-line change.

---

## 6. ROLES & PERMISSIONS (NIDAAN ADMIN SIDE)

| Role | Capabilities |
|------|--------------|
| **Super Admin** | Everything. Manage admins, freeze partnership, refund any amount, view all accounts/claims/revenue. |
| **Sub-Super Admin** | Same as super-admin EXCEPT: cannot manage admins, cannot freeze partnership, **cannot refund any amount** (₹0 cap → all refunds need super-admin). |
| **Legal Agent** | View claims assigned to them, update status, add internal notes, mark resolved. Cannot see other agents' claims unless granted by sub-super-admin. Cannot see billing. |
| **Account Owner** | File claims, view own claims, manage sub-users (Gold/Platinum), view subscription, cancel/upgrade. |
| **Sub-User** | File claims (counts against account quota), view own claims, cannot manage subscription. |

---

## 7. DPDP / SECURITY

- **Sensitive docs are NOT stored** by us. The only PII captured is insured contact (name, phone, email) and case metadata (insurer, policy #, disputed amount, brief summary).
- **Consent checkbox** at claim submission: *"I confirm the insured has consented to share their contact details with Nidaan – The Legal Consultants LLP for the purpose of dispute resolution."* → logged in `nidaan_claim_status_log` first row.
- **Claim records retention:** 7 years from `closed_at` then auto-purge.
- **Audit log:** every status change, refund, plan change → `audit_log` (existing table) with `category='nidaan'`.
- **Rate limits:** `/api/nidaan/*` 60/min default, `/api/nidaan/claim/file` 10/min, `/api/nidaan/per-claim/checkout` 5/min.
- **Webhook auth:** Razorpay HMAC + Fast2SMS callback IP allowlist.

---

## 8. PHASED BUILD

### Phase 1a — Domain + Homepage (visible quick win, NO DB changes)

**Acceptance criteria:**
- `https://nidaanpartner.com` resolves and serves a polished bilingual EN+HI homepage.
- Cert auto-renews via certbot.
- FastAPI host-header dispatch works (Sarathi continues to serve unchanged on its own domain).
- Homepage content sourced from brochure parse + matches positioning agreed.
- Page is shareable with Nidaan LLP team for validation.

**Deliverables:**
1. **Cloudflare DNS:** A-record `nidaanpartner.com` → `140.238.246.0`, A-record `www.nidaanpartner.com` → same. Proxy mode = "DNS only" (gray cloud) initially so cert challenge works.
2. **Certbot:** `sudo certbot certonly --nginx -d nidaanpartner.com -d www.nidaanpartner.com`.
3. **Nginx:** `/etc/nginx/sites-available/nidaanpartner.com` (template in §4.1) → symlink → reload.
4. **FastAPI:** add host-aware dispatch in `sarathi_biz.py`, route `/` for Nidaan host → `static/nidaan_index.html`.
5. **Brochure parse:** read `c:\Users\imdus\Downloads\NIDAAN BROCHER HINDI.pdf`, extract:
   - Claim categories handled
   - Positioning lines
   - Credentials / track-record / stats
   - FAQ content
   Translate Hindi-only items to English (and create proper Hindi versions where the source is English-flavored).
6. **`static/nidaan_index.html`:** mobile-first, EN/HI toggle (`localStorage.nidaan_lang`, auto-detect), sections per §9 below, deep-navy + cyan palette, Nidaan logo asset placed at `static/nidaan_logo.png`.
7. **`deploy/nginx-nidaan.conf`** committed (so future redeploys keep config).
8. **Master-doc update** with Phase 1a completion log.

**Out of scope for 1a:** any DB tables, signup, login, payment, dashboard, claim form. Pure marketing site only.

---

### Phase 1b — DB foundation + admin scaffold (parallel to 1a)

**Acceptance criteria:**
- All Nidaan tables created via additive migration.
- Sarathi gets `plan_source` + `bundled_until` columns.
- `biz_nidaan.py` module skeleton with stub functions.
- One super-admin row seeded for you.
- `/api/nidaan/_health` returns OK.

**Deliverables:**
1. Migration script `_migrate_nidaan_v1.py` creating all tables in §2.
2. `biz_nidaan.py` with module skeleton: imports, health check, helpers placeholder.
3. Seed super-admin (your email + bcrypt-hashed password from env).
4. Tests in `_test_nidaan_schema.py` verifying table existence.

---

### Phase 2 — Auth + Subscriptions

**Acceptance criteria:**
- Customer can sign up on nidaanpartner.com (Email OTP + Google Sign-In, mirroring Sarathi auth).
- Customer can pick a plan and pay via Razorpay (test mode first).
- On success, `nidaan_subscription` row + matching Sarathi tenant + `product_link` row are created.
- Bundling rules (§3.2) honored.
- Cross-product SSO handoff works: signed token → other domain → cookie set.
- Two prominent buttons on each dashboard: "Open Sarathi-AI CRM" / "Open Nidaan Partner Dashboard".

**Deliverables:**
1. Razorpay subscription SKUs: `nidaan_silver_q`, `nidaan_gold_q`, `nidaan_platinum_q`.
2. Webhook handler `POST /api/nidaan/webhook/razorpay` (HMAC-verified).
3. Signup pages: `static/nidaan_signup.html`, `static/nidaan_login.html`.
4. SSO endpoint: `GET /sso?token=...` on both domains; token signed with `JWT_SECRET`, 60s TTL, single-use.
5. Daily bundling cron entry in `biz_reminders.py` (§3.3 logic).
6. Audit-log entries for subscribe / upgrade / downgrade / SSO use.

---

### Phase 3 — Nidaan dashboard + claim filing

**Acceptance criteria:**
- Logged-in account owner sees Nidaan dashboard with quota meter + "File New Claim" CTA.
- Dynamic claim form switches fields by `claim_type`.
- Quota enforced: 403 + upsell modal when exceeded.
- On submit: SMS + email automation fires (§5.1) and ops number is notified.
- Legal-agent admin view shows assigned-to-me queue.
- Status updates by legal agent fire SMS + email and append to `nidaan_claim_status_log`.

**Deliverables:**
1. `static/nidaan_dashboard.html` (advisor side).
2. `static/nidaan_admin.html` (super / sub-super / legal-agent — role-based panels).
3. Routes:
   - `POST /api/nidaan/claim/file`
   - `GET /api/nidaan/claim/list`
   - `GET /api/nidaan/claim/{id}`
   - `POST /api/nidaan/claim/{id}/status` (admin only)
   - `POST /api/nidaan/claim/{id}/assign` (super/sub-super)
4. Quota check helper + modal HTML.
5. Fast2SMS provider class in `biz_sms.py`.
6. DLT templates registered (§5.2) — operational dependency on Jio response.

---

### Phase 4 — Per-claim direct-to-consumer + analytics

**Acceptance criteria:**
- Public page `nidaanpartner.com/get-claim-reviewed` accepts insured details + ₹999 Razorpay payment.
- On payment success, super-admin sees the entry in `nidaan_per_claim_purchase`.
- Outcome update by admin sends bilingual SMS + email.
- Revenue dashboard shows MRR, claims-by-status, conversion.

**Deliverables:**
1. `static/nidaan_perclaim.html` + checkout flow.
2. `POST /api/nidaan/per-claim/checkout`, Razorpay one-time order.
3. Admin endpoint to record outcome.
4. `GET /api/nidaan/admin/revenue`, `GET /api/nidaan/admin/funnel`.

---

### Phase 5 — Sarathi cross-promo

**Acceptance criteria:**
- Sarathi homepage gets a "🛡️ Claims" CTA → Nidaan homepage.
- Sarathi dashboard gets a "Claims" tab with two states: "Add Claims Service" (no Nidaan link) or "Open Nidaan Partner" (linked).
- Per-claim purchase entry from inside Sarathi dashboard for non-bundled customers.

---

## 9. NIDAAN HOMEPAGE STRUCTURE (Phase 1a)

Bilingual EN+HI. Toggle in nav + auto-detect from `navigator.language`. Storage key `localStorage.nidaan_lang`.

1. **Top nav** — Nidaan logo + tagline "The Legal Consultants LLP" + EN/हिं toggle + "Login" + "Get Started" CTA.
2. **Hero**
   - HI: *"क्या आपके क्लाइंट का इंश्योरेंस क्लेम रिजेक्ट हुआ है?"*
   - EN: *"Has your client's insurance claim been rejected, underpaid, or stuck?"*
   - Subline: *"You're not a lawyer. You shouldn't have to be. Hand it to Nidaan — India's specialists in insurance dispute resolution."*
   - Tagline: *"Subscribe once. Sleep peacefully forever."*
   - CTAs: `🛡️ Start with Silver — ₹1,500/quarter` + `▶ Watch how it works (60s)`
   - Bonus banner: *"🎁 Sarathi-AI CRM (worth ₹199–₹1,999/month) is FREE with every Nidaan plan"*.
3. **The Problem** — emotional 3-line story.
4. **The Nidaan Solution** — 4 cards: legal experts, IRDAI/Ombudsman expertise, courtroom track record, transparent process.
5. **How It Works** — 3 steps: Subscribe → Click "File Claim" → Nidaan team takes over.
6. **Plans** — Silver / Gold / Platinum with claim quota + Sarathi-AI bundle highlighted.
7. **Why Sarathi-AI is bundled** — feature cards + "Saves ₹X per year".
8. **Trust strip** — case studies (anonymized), Nidaan LLP credentials, IRDAI Ombudsman win-rate.
9. **Testimonials** — 3 placeholders to start.
10. **FAQ** — 10–12 questions.
11. **Direct-to-consumer block** — "Are you an insurance customer with a rejected claim? Get a paid legal review for ₹999 →".
12. **Footer** — Nidaan LLP credentials, CIN, contact, privacy, terms.

---

## 10. ENV VARS NEEDED (Phase 2 onward)

```
# Nidaan
NIDAAN_DOMAIN=nidaanpartner.com
NIDAAN_OPS_PHONE=+91XXXXXXXXXX        # ops number for new-claim SMS
NIDAAN_OPS_EMAIL=ops@nidaanlegalindia.com
NIDAAN_SUPER_ADMIN_EMAIL=...          # for seed
NIDAAN_SUPER_ADMIN_PASSWORD=...       # one-time seed, then changed via UI

# Razorpay (additional plan IDs)
RAZORPAY_PLAN_NIDAAN_SILVER_Q=plan_xxx
RAZORPAY_PLAN_NIDAAN_GOLD_Q=plan_xxx
RAZORPAY_PLAN_NIDAAN_PLATINUM_Q=plan_xxx

# Fast2SMS
FAST2SMS_API_KEY=...
FAST2SMS_SENDER_ID=NIDAAN
FAST2SMS_DLT_ENTITY_ID=...
FAST2SMS_TEMPLATE_CLAIM_NEW_AGENT=...
FAST2SMS_TEMPLATE_CLAIM_NEW_INSURED=...
FAST2SMS_TEMPLATE_CLAIM_NEW_OPS=...
FAST2SMS_TEMPLATE_STATUS_AGENT=...
FAST2SMS_TEMPLATE_STATUS_INSURED=...
FAST2SMS_TEMPLATE_PERCLAIM_RECEIPT=...
FAST2SMS_TEMPLATE_PERCLAIM_OUTCOME=...
```

---

## 11. RISK REGISTER

| Risk | Mitigation |
|------|------------|
| Jio DLT approval delay blocks Phase 3 SMS | Phase 1+2 ship without SMS dependency. SMS is added after templates approved. |
| Nidaan team doesn't push status updates → insured loses trust | Build internal admin UI so Nidaan team has zero-friction status updates. Add a "Pending status update > 7 days" alert to super-admin. |
| Cookie scope across two domains | Use server-side SSO handoff (signed 60s token), not shared cookies. |
| Sensitive doc accidentally captured in `notes_from_agent` | Add UI hint + server-side regex strip of obvious patterns (Aadhaar 12-digit, PAN format) before save. |
| Tenant linked by email — what if advisor uses a different email on each side? | On Nidaan signup, ask "Do you already have a Sarathi account? Link it" → manual link via OTP to existing Sarathi email. |
| Partnership ends mid-quarter for paying customers | Refunds via Razorpay (super-admin only); 30-day grace for bundled Sarathi access. |

---

## 12. NEXT IMMEDIATE ACTION

**On approval, begin Phase 1a in this order:**
1. Cloudflare DNS records (you action) → confirm with `dig nidaanpartner.com` from VM.
2. Brochure parse — extract content while DNS propagates.
3. Nginx server-block + certbot.
4. FastAPI host-header dispatch.
5. Build `static/nidaan_index.html` (bilingual).
6. Verify end-to-end: `curl https://nidaanpartner.com` returns Nidaan homepage; `curl https://sarathi-ai.com` unchanged.
7. Commit + deploy.
8. Update master doc Section 30 with Phase 1a completion log.

---

*End of plan. Maintain this doc alongside `PROJECT_MASTER_CONTEXT.md` Section 30.*
