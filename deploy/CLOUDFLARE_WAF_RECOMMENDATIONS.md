# Cloudflare WAF + Security Recommendations

Free-tier Cloudflare gives us a serious edge-layer of security with very little
configuration. This document is the **manual checklist** for what to enable in
the Cloudflare dashboard for `sarathi-ai.com` and `nidaanpartner.com`.

Estimated time: 30 minutes total (one-time setup; takes minutes to test).

---

## 0. ⚠️ READ FIRST — machine callers we WANT

Everything below is about turning automated traffic away. Some automated traffic is
**ours and must get through**, and Cloudflare cannot tell the difference:

| Path | Who calls it | What happens if it is blocked |
|---|---|---|
| `/nidaan/api/webhook` | Razorpay (Nidaan) | Payment confirmations never arrive |
| `/api/payments/webhook` | Razorpay (Sarathi) | Same, on the other product |
| `/nidaan/api/wa/webhook` | Meta / WhatsApp Cloud API | Inbound complainant messages never arrive. **GET too** — Meta re-verifies the endpoint |
| `/api/whatsapp/v2/webhook` | Meta (Sarathi) | Same, on the other product |
| `/nidaan/telegram/webhook/*` | Telegram | Ops bot goes silent. Only if webhook mode is in use — `@NidaanOpsBot` currently long-polls, so nothing to open today |
| `/api/telegram/webhook/*` | Telegram (Sarathi) | Same |

Routes confirmed in `sarathi_biz.py` on 23 Sep 2026; re-grep `@app.post("/.*webhook` before
trusting this table, because a path written from memory into a firewall rule is a hole or an
outage.

**This has already cost us once.** On 23 Sep 2026 Razorpay's webhook for
`pay_TfPq2skEiSuArv` was served a Cloudflare **"Just a moment..."** challenge and a **403**, on
every retry, for days. Razorpay's own delivery log is what proved it. Money was never lost — the
payment guardian reconciles against the Razorpay API every 5 minutes and recovers — but every
confirmation was late, and a day was spent with Razorpay support because our own self-test said
the fault was theirs.

**Before enabling anything below, confirm each path above answers a plain POST from outside our
network.** A test from the server itself does not count: an edge challenge scores the CALLER, not
the path, so our own request sails through while a provider's is stopped.

---

## 1. Security → Bots

> ⚠️ **Bot Fight Mode has no exception list on the free plan.** WAF custom rules and
> Configuration Rules run AFTER it, so a "Skip" rule does not rescue a blocked webhook. If a
> provider webhook is being challenged, the only free-tier answer is to turn Bot Fight Mode
> **off** for that zone and replace it with a custom rule that excludes the webhook paths
> (pattern below). Verify on the dashboard rather than trusting this line — Cloudflare's free
> tier changes.

**Enable: Bot Fight Mode** (free) — `sarathi-ai.com` only, unless the webhook paths above are
confirmed reachable.

- Cloudflare → sarathi-ai.com → Security → Bots → Bot Fight Mode → **On**
- **nidaanpartner.com: leave OFF** while it carries the Razorpay, WhatsApp and Telegram
  webhooks, or verify each one end to end immediately after turning it on.

Blocks crawlers/scrapers/automated tools that aren't allowed list bots (Google,
Bing). Doesn't affect real users. **It does affect payment providers.**

### Replacement for nidaanpartner.com — a custom rule that spares the webhooks

| Field | Value |
|---|---|
| Name | `challenge-bots-except-webhooks` |
| Expression | `(cf.client.bot_score lt 30) and not (http.request.uri.path in {"/nidaan/api/webhook" "/api/payments/webhook" "/nidaan/api/wa/webhook" "/api/whatsapp/v2/webhook"}) and not (starts_with(http.request.uri.path, "/nidaan/telegram/webhook/")) and not (starts_with(http.request.uri.path, "/api/telegram/webhook/"))` |
| Action | Managed Challenge |

`cf.client.bot_score` needs Bot Management; on free tier use
`(not cf.client.bot) and not (http.request.uri.path in {...})` or rely on the rate limits in
§2 instead. **Whatever is used, the webhook paths must be excluded by name.**

### After ANY change here, prove the webhook still arrives

Do not read a setting — read an outcome. Make a real ₹1 payment, or in the Razorpay dashboard
(Settings → Webhooks → the endpoint → recent deliveries) confirm a **2xx**. A 403 carrying
`Just a moment...` means the edge is still eating it.

---

## 2. Security → WAF → Custom Rules

Free plan includes 5 custom rules. Recommended:

### Rule 1: Block obvious SQL injection attempts on any path

| Field | Value |
|---|---|
| Name | `block-sqli-attempts` |
| Expression | `(http.request.uri.query contains "union+select") or (http.request.uri.query contains "or+1=1") or (http.request.uri.path contains "../../") or (http.request.body.raw contains "DROP TABLE")` |
| Action | Block |

### Rule 2: Rate-limit auth endpoints aggressively (free tier: 10 req/10s per IP)

| Field | Value |
|---|---|
| Name | `auth-rate-limit` |
| Expression | `(http.request.uri.path contains "/api/auth/") or (http.request.uri.path contains "/nidaan/api/login") or (http.request.uri.path contains "/nidaan/api/signup") or (http.request.uri.path contains "/api/sa/login")` |
| Action | Managed Challenge (CAPTCHA-like, blocks bots but lets real users through) |

### Rule 3: Geo-restrict ALL admin paths to India only

Pre-launch you don't have global users. Block everything except India from
hitting admin endpoints:

| Field | Value |
|---|---|
| Name | `admin-india-only` |
| Expression | `(http.request.uri.path contains "/api/sa/") or (http.request.uri.path contains "/nidaan/ops/") or (http.request.uri.path contains "/admin")` and `ip.geoip.country ne "IN"` |
| Action | Block |

After you go international, change to allow your office countries.

### Rule 4: Block known scanner User-Agents

| Field | Value |
|---|---|
| Name | `block-known-scanners` |
| Expression | `(http.user_agent contains "sqlmap") or (http.user_agent contains "nikto") or (http.user_agent contains "nmap") or (http.user_agent contains "masscan") or (http.user_agent contains "fimap") or (http.user_agent eq "")` |
| Action | Block |

Empty UA is suspicious; real browsers always send one.

### Rule 5: Block requests to non-existent admin paths (honeypot)

| Field | Value |
|---|---|
| Name | `honeypot-admin-probes` |
| Expression | `(http.request.uri.path eq "/wp-admin") or (http.request.uri.path eq "/wp-login.php") or (http.request.uri.path eq "/phpmyadmin") or (http.request.uri.path eq "/.env") or (http.request.uri.path eq "/.git/config") or (http.request.uri.path eq "/admin.php")` |
| Action | Block + add IP to "naughty list" custom rule (manual review) |

These are bot probes; legitimate users would never hit them. Logs from this rule
tell you who's scanning you.

---

## 3. Security → DDoS → HTTP DDoS Attack Protection

- Sensitivity: **High**
- Action: **Block**

(Free; this is Cloudflare's L7 DDoS shield. Default settings are conservative;
"High" is safe for low-traffic sites.)

---

## 4. SSL/TLS → Edge Certificates

- Minimum TLS Version: **TLS 1.2** (you're already on Full Strict, good)
- Opportunistic Encryption: **On**
- TLS 1.3: **On**
- HSTS: **Enable** with these settings:
  - Max-Age: **6 months** (start lower; increase to 12 months once you're confident)
  - Apply HSTS policy to subdomains: **No** (until you've verified all subdomains work over HTTPS)
  - Preload: **No** initially. Enable + submit to hstspreload.org only after running 6+ months on max-age 12 months stable.

---

## 5. DNS — Email security (carry-over from Sprint D)

**These are STILL pending — Cloudflare → sarathi-ai.com → DNS:**

| Record | Action |
|---|---|
| SPF for nidaanpartner.com | Update to: `v=spf1 include:_spf.google.com include:_spf.mx.cloudflare.net ~all` |
| DMARC sarathi-ai.com | Once Sprint D `rua=` reports show no surprises for 2 weeks, change `p=none` → `p=quarantine` |
| DMARC nidaanpartner.com | Same |
| DKIM | Only possible with Google Workspace. If not on Workspace, skip — SPF alone is acceptable |

---

## 6. Speed → Optimization

- Auto Minify: **JS, CSS, HTML** all on
- Brotli: **On**
- Early Hints: **On**

Not security-related directly, but smaller payloads = less attack surface for
buffer-overflow / parser-confusion attacks.

---

## 7. Rules → Page Rules (free tier: 3 rules)

### Rule 1: Always cache static assets (with cache-busting via filename hash)

| Field | Value |
|---|---|
| URL | `sarathi-ai.com/static/*` |
| Setting | Cache Level: Cache Everything; Edge Cache TTL: 1 month |

### Rule 2: Bypass cache for HTML and API

| Field | Value |
|---|---|
| URL | `sarathi-ai.com/*` |
| Setting | Cache Level: Bypass |

(Order matters: the more specific `/static/*` rule must be ABOVE the catch-all.)

### Rule 3: Force HTTPS on both domains

Already enabled by default; verify under SSL/TLS → Edge Certificates → Always Use HTTPS = **On**.

---

## 8. Analytics → Security Events

After 24 hours of having the rules above, check:
- Cloudflare → Analytics → Security
- Look at "Threats stopped"
- If a real user got blocked, their IP/UA shows up here → adjust the rule

---

## 9. What we're NOT doing (and why)

- **Cloudflare Access** (Zero Trust SSO) — paid tier. Would let us SSO-protect `/api/sa/*` admin routes. Defer until first paying enterprise customer.
- **Cloudflare Argo / Smart Routing** — paid; latency improvement, not security
- **mTLS** — overkill for our threat model right now
- **Rate Limiting beyond 5 free rules** — paid tier gives unlimited rules. Defer until traffic grows.

---

## Checklist for the user

Once you have 30 min, work through this. Mark each as done:

- [ ] Bot Fight Mode → On (**sarathi-ai.com only** — see §0; it blocked Razorpay's webhook on nidaanpartner.com for days)
- [ ] Razorpay / WhatsApp / Telegram webhook paths verified reachable FROM OUTSIDE after every edge change
- [ ] WAF Rule 1: block SQLi patterns
- [ ] WAF Rule 2: rate-limit auth endpoints
- [ ] WAF Rule 3: geo-restrict admin to India
- [ ] WAF Rule 4: block scanner UAs
- [ ] WAF Rule 5: honeypot admin paths
- [ ] DDoS sensitivity: High
- [ ] HSTS enabled (max-age 6 months, no subdomains yet, no preload)
- [ ] SPF for nidaanpartner.com updated with `_spf.google.com`
- [ ] Page Rules: static cache + bypass HTML
- [ ] After 24h: check Security Analytics for false positives

Once you've ticked these off, ping me and I'll verify by hitting your prod from
different test vectors.
