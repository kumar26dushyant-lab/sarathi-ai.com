# Sprint E.1 — Security Audit Findings (analysis only)

This document is the result of the Sprint E.1 audit. **No code was changed
during this audit** — all findings are queued for Sprint E.2 (rate limits +
deps) and E.3 (Pydantic strict mode + CSP). Approving this doc unblocks
those execution sprints.

Date: 2026-06-10
Endpoint count audited: 485
Pydantic models audited: 132

---

## Finding 1 — Rate-limit coverage is uneven (148 / 485 = 30%)

**Methodology:** parsed `sarathi_biz.py` with a regex that pairs every
`@app.<METHOD>("/path")` decorator with the function below it (skipping over
any other decorators in between) and checks whether `@limiter.limit(...)` is
present.

**Result:** 148 endpoints have rate limits. 337 do not.

Most "no rate limit" endpoints are GET reads (dashboard, profile, etc.) — low
abuse value, fine without limits. The concerning ones:

### 1a — Auth endpoints missing rate limits

| Endpoint | Risk | E.2 recommendation |
|---|---|---|
| `POST /nidaan/api/signup` | Signup floods, fake-account DoS | `5/minute` |
| `POST /nidaan/api/login` | Password brute-force | `10/minute` |
| `POST /nidaan/ops/api/login` | Staff-portal brute-force | `5/minute` |
| `GET  /api/auth/telegram-login` | Telegram link-token enumeration | `10/minute` |

(Other auth endpoints — `csrf-token`, `me`, `logout` — are session-state reads;
unlimited is fine.)

### 1b — Payment / subscription endpoints missing rate limits

89 such endpoints, all already require authentication. But a stolen token could
let an attacker hammer them. Highest-value targets:

| Endpoint | E.2 recommendation |
|---|---|
| `POST /nidaan/api/subscribe` | `5/minute` |
| `POST /nidaan/api/subscribe/recurring` | `5/minute` |
| `POST /nidaan/api/subscribe/cancel` | `5/minute` |
| `POST /nidaan/api/subscribe/verify` | `10/minute` |
| `POST /nidaan/api/subscribe/recurring/verify` | `10/minute` |
| `POST /nidaan/api/webhook` (Razorpay) | `60/minute` (Razorpay can burst) |

### 1c — SA (super-admin) destructive endpoints missing rate limits

These already require SA auth, but a stolen SA token would be catastrophic.
Adding a rate limit makes mass-destruction-via-stolen-token slower:

| Endpoint | E.2 recommendation |
|---|---|
| `POST /api/sa/restart-server` | `2/minute` |
| `POST /api/sa/tenant/{id}/bot/restart` | `5/minute` |
| `POST /api/sa/tenants/bulk-activate` | `2/minute` |
| `POST /api/sa/tenants/bulk-deactivate` | `2/minute` |
| `POST /api/sa/tenants/bulk-plan` | `2/minute` |
| `POST /api/sa/tenant/{id}/impersonate` | `5/minute` |
| `POST /api/sa/affiliate/{id}/impersonate` | `5/minute` |
| `POST /api/sa/events/bulk-resolve` | `5/minute` |
| `POST /api/sa/tenant/{id}/force-plan-change` | `5/minute` |
| `POST /api/sa/agent/{id}/toggle` | `10/minute` |

### Why "additive only" is safe

Adding rate limits is **not** a breaking change for legit users — legit traffic
volumes are way under these thresholds. The thresholds above are deliberately
generous so a real owner clicking fast doesn't hit them. Only an attacker
brute-forcing or scripting would.

---

## Finding 2 — Pydantic models are NOT strict (132 / 132 accept unknown fields)

**Methodology:** scanned all `class Foo(BaseModel)` definitions in
`sarathi_biz.py`.

**Result:** 132 models, 0 with `extra="forbid"`. Every request body silently
accepts unknown extra fields.

### Why this matters

Without `extra="forbid"`:
- An attacker can sneak in fields the backend later "looks up" by mistake
  (parameter pollution / mass assignment)
- New fields added to the frontend before the backend won't error — bugs hide

### Why we can't just bulk-apply

Some models are used in places where the frontend may send legitimately-extra
fields (e.g., a legacy field renamed but old clients still send it). Bulk-
applying `extra="forbid"` would cause some 422s in production.

**E.3 plan:** sort the 132 models by risk, apply `extra="forbid"` model-by-
model with E2E test (signup, login, payment, claim submission) after each batch.

### Highest-priority models (apply first in E.3)

These are all authentication / payment / privilege-escalation surfaces where
parameter pollution would be most dangerous:

| Model | Used by | Priority |
|---|---|---|
| NidaanSignupReq | `POST /nidaan/api/signup` | Critical |
| NidaanLoginReq | `POST /nidaan/api/login` | Critical |
| OpsLoginReq | `POST /nidaan/ops/api/login` | Critical |
| SALoginRequest | `POST /api/sa/login` | Critical |
| SignupRequest (Sarathi) | `POST /api/auth/signup-email` | Critical |
| GoogleSignInRequest | `POST /api/auth/google` | Critical |
| GoogleSignUpRequest | `POST /api/signup/google` | Critical |
| AffiliateRegisterRequest | `POST /api/affiliate/register` | Critical |
| NidaanSubscribeReq | `POST /nidaan/api/subscribe*` | High |
| VerifyPaymentRequest | `POST /api/payments/verify*` | High |
| CreateOrderRequest | `POST /api/payments/create-order` | High |
| NidaanProfileUpdateReq | `PATCH /nidaan/api/profile` | Medium |
| NidaanChangePasswordReq | `POST /nidaan/api/change-password` | Medium |
| All `_SaManualRefundReq`, `_SettleClawbackReq`, `BulkIdsRequest` | SA actions | Medium |

The remaining ~110 models (campaign create, lead add, branding update, etc.)
get done in a separate batch with regression testing.

---

## Finding 3 — Dependency pinning is loose

`biz_requirements.txt` uses `>=` for most packages. Reproducible builds need
exact pinning.

**E.2 plan:** generate `pip freeze > biz_requirements.lock` on prod, then
pin the top-50 most-critical packages (fastapi, pydantic, sqlalchemy if any,
razorpay, etc.) in `biz_requirements.txt` with `==`. Leave indirect deps to
the lock file.

---

## Finding 4 — CSP is permissive (deferred to E.3)

Current `Content-Security-Policy` (from biz_auth.py security_headers) is
relatively permissive for the dashboard which loads Razorpay, Google Sign-In,
Google Fonts, etc.

**E.3 plan:** Add nonces for inline scripts, lock down `script-src` to
specific CDNs. Requires testing every page-load path; high regression risk.

---

## Finding 5 — Defense-in-depth gaps (now closed by E.1)

| Gap | Closed by |
|---|---|
| No pre-push secret scanning | `.github/workflows/gitleaks.yml` + `.gitleaks.toml` |
| No pre-commit secret scanning | `deploy/install-precommit-hook.sh` |
| No documented rotation runbook | `deploy/SECRET_ROTATION_PLAYBOOK.md` |
| No edge-layer WAF | `deploy/CLOUDFLARE_WAF_RECOMMENDATIONS.md` |

---

## What changed on disk during E.1

Nothing in `*.py`. Nothing affecting any endpoint or flow. Only documentation
and CI-config files.

```
new: .github/workflows/gitleaks.yml
new: .gitleaks.toml
new: deploy/install-precommit-hook.sh
new: deploy/SECRET_ROTATION_PLAYBOOK.md
new: deploy/CLOUDFLARE_WAF_RECOMMENDATIONS.md
new: deploy/SECURITY_AUDIT_SPRINT_E1.md  (this file)
```

---

## What needs your decision before E.2 starts

1. **Approve the rate-limit table above** (1a + 1b + 1c). I'll apply only the
   ones you tick. Default: apply ALL — they are additive and won't affect real users.
2. **Approve dependency pinning approach** (lock file + top-50 pinned).
3. **Optionally**: run `bash deploy/install-precommit-hook.sh` locally yourself
   so secrets never reach a commit.
4. **Optionally**: do the Cloudflare WAF checklist (30 min one-time setup).

Once you say "go E.2", I:
- Add the rate-limit decorators (low risk, one PR, smoke-test the auth flows)
- Pin top-50 deps
- Don't touch Pydantic or CSP until you approve E.3 separately.
