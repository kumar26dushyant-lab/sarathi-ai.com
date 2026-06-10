# Secret Rotation Playbook

Step-by-step runbooks for rotating each production secret. Designed to be
executable in **5 minutes per secret** so rotation is never the bottleneck.

Last rotation drill: 2026-06-10 (Evolution API key — successful, zero downtime).

---

## Why rotate

- Secret appeared in a commit (gitleaks alert, PR review caught it, etc.)
- Quarterly rotation hygiene (set a calendar reminder)
- Employee/contractor offboarding
- Suspected compromise

---

## TL;DR — Severity ladder

| Secret | If leaked | Rotate within | Playbook |
|---|---|---|---|
| Evolution WhatsApp API key | WhatsApp account permanently banned by Meta | 1 hour | [§1](#1-evolution-whatsapp-api-key) |
| RAZORPAY_KEY_SECRET | Money loss — attacker creates fake orders | 1 hour | [§2](#2-razorpay-key-secret) |
| RAZORPAY_WEBHOOK_SECRET | Attacker spoofs webhook events | 4 hours | [§3](#3-razorpay-webhook-secret) |
| JWT_SECRET | All current sessions forge-able | 4 hours (but logs out all users) | [§4](#4-jwt-secret) |
| GEMINI_API_KEY | Quota burn, billed to your Google project | 24 hours | [§5](#5-gemini-api-key) |
| SMTP App Password | Spam from your Gmail address | 24 hours | [§6](#6-smtp-app-password-gmail) |
| Webshare proxy creds | Proxy quota burn | 1 week | [§7](#7-webshare-proxy-credentials) |
| GitHub PAT | Repo write access | 1 hour | [§8](#8-github-pat) |
| Razorpay TEST key id | (not sensitive — test keys are public) | n/a | — |

---

## 1. Evolution WhatsApp API key

**Lives in:**
- Hetzner `/opt/evolution/.env` → `EVOLUTION_API_KEY=...`
- Hetzner `/opt/evolution/internal.env` → `AUTHENTICATION_API_KEY=...` (mirror)
- Contabo `/opt/sarathi/biz.env` → `EVOLUTION_API_KEY=...`

**Steps:**
```bash
# 1. On Hetzner — generate + update + restart
ssh root@5.223.64.25
cd /opt/evolution
cp .env .env.bak.$(date +%Y%m%d-%H%M%S)
NEW_KEY=$(openssl rand -hex 32)
sed -i "s|^EVOLUTION_API_KEY=.*|EVOLUTION_API_KEY=$NEW_KEY|" .env
sed -i "s|^AUTHENTICATION_API_KEY=.*|AUTHENTICATION_API_KEY=$NEW_KEY|" internal.env
docker compose up -d --force-recreate evolution-api
sleep 10
# Verify old key is dead
curl -s -o /dev/null -w "%{http_code}" -H "apikey: <OLD_KEY>" http://localhost:8080/instance/fetchInstances  # expect 401
# Verify new key works
curl -s -o /dev/null -w "%{http_code}" -H "apikey: $NEW_KEY"   http://localhost:8080/instance/fetchInstances  # expect 200
echo "$NEW_KEY"      # copy for next step

# 2. On Contabo — update biz.env + restart sarathi
ssh root@84.247.172.252
cp /opt/sarathi/biz.env /opt/sarathi/biz.env.bak.$(date +%Y%m%d-%H%M%S)
sed -i "s|^EVOLUTION_API_KEY=.*|EVOLUTION_API_KEY=<NEW_KEY>|" /opt/sarathi/biz.env
systemctl restart sarathi
sleep 3
systemctl is-active sarathi    # expect: active
journalctl -u sarathi --since "60 seconds ago" | grep -i evolution    # expect: "Evolution API client ready"
```

**Acceptance:** Old key returns 401, new key returns 200 from both Hetzner-local AND Contabo curl. Sarathi service active, no errors in logs.

---

## 2. RAZORPAY_KEY_SECRET

**Lives in:**
- Contabo `/opt/sarathi/biz.env` → `RAZORPAY_KEY_SECRET=...`
- Razorpay dashboard

**Steps:**
1. Razorpay Dashboard → Settings → API Keys → Regenerate Live Key
2. Copy NEW key secret (key id stays the same; that's fine — it's public)
3. On Contabo:
   ```bash
   ssh root@84.247.172.252
   sed -i "s|^RAZORPAY_KEY_SECRET=.*|RAZORPAY_KEY_SECRET=<NEW>|" /opt/sarathi/biz.env
   systemctl restart sarathi
   ```
4. Test payment flow: open subscribe modal on dashboard, run through Razorpay test mode

**Acceptance:** A real (small) ₹1 test payment goes through successfully end-to-end.

---

## 3. RAZORPAY_WEBHOOK_SECRET

Note: this is a **separate** secret from `RAZORPAY_KEY_SECRET`. Razorpay assigns it per-webhook.

**Steps:**
1. Razorpay Dashboard → Settings → Webhooks → Edit webhook → Set new secret
2. Copy the new secret
3. On Contabo:
   ```bash
   sed -i "s|^RAZORPAY_WEBHOOK_SECRET=.*|RAZORPAY_WEBHOOK_SECRET=<NEW>|" /opt/sarathi/biz.env
   systemctl restart sarathi
   ```
4. Razorpay Dashboard → Webhooks → "Send test webhook"

**Acceptance:** Test webhook from dashboard returns 200 from your endpoint. Sarathi logs show signature verified.

---

## 4. JWT_SECRET

⚠️ **This logs out ALL users.** Plan accordingly (off-hours, send a heads-up to active users via a banner first).

```bash
ssh root@84.247.172.252
NEW=$(openssl rand -hex 32)
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$NEW|" /opt/sarathi/biz.env
systemctl restart sarathi
```

**Acceptance:** Active sessions logged out; new logins issue tokens signed with the new key.

---

## 5. GEMINI_API_KEY

1. https://aistudio.google.com/app/apikey → revoke old → create new
2. On Contabo:
   ```bash
   sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=<NEW>|" /opt/sarathi/biz.env
   systemctl restart sarathi
   ```
3. Test: send a voice note in Telegram bot or via Sarathi dashboard

**Acceptance:** Voice → AI response works. Logs show no `401` from Gemini.

---

## 6. SMTP App Password (Gmail)

1. https://myaccount.google.com/apppasswords → revoke "Sarathi-AI Server" → generate new
2. On Contabo:
   ```bash
   sed -i "s|^SMTP_PASSWORD=.*|SMTP_PASSWORD=<NEW>|" /opt/sarathi/biz.env
   systemctl restart sarathi
   ```
3. Test: trigger any "send OTP" flow and confirm delivery

**Acceptance:** OTP email arrives in test inbox.

---

## 7. Webshare proxy credentials

Note: Webshare uses HTTP Basic Auth on the SOCKS5/HTTP proxy. There's no "API key" concept.

1. Webshare Dashboard → Proxy List → regenerate proxy user/pass
2. On Hetzner (where the proxy is used by Evolution via `redsocks`):
   ```bash
   ssh root@5.223.64.25
   # Edit redsocks config OR docker-compose.yml depending on setup
   # (See /opt/evolution/docker-compose.yml for the actual proxy reference)
   ```
3. Restart Evolution container

**Acceptance:** Evolution still successfully connects out to WhatsApp servers (logs show no proxy errors).

---

## 8. GitHub PAT

If the PAT was used for the git-backup service:

1. github.com → Settings → Developer Settings → Tokens (classic) → revoke → create new (scope: `repo`)
2. On Contabo:
   ```bash
   sed -i "s|^GITHUB_PAT=.*|GITHUB_PAT=<NEW>|" /opt/sarathi/biz.env
   systemctl daemon-reload
   systemctl restart git-backup.timer
   ```

**Acceptance:** Manually trigger the backup unit and check the GitHub repo received the push.

---

## After ANY rotation

1. **Confirm `gitleaks` clean on master:**
   ```bash
   gitleaks detect --config .gitleaks.toml --no-git
   ```
2. **Update master doc rotation log** (so we know the date the secret was last rotated):
   `PROJECT_MASTER_CONTEXT.md` → §39.4 Rotation Log table.
3. **If the leak triggered the rotation**, scrub the value from the doc:
   ```bash
   grep -n '<the leaked value>' PROJECT_MASTER_CONTEXT.md
   # Replace with [REDACTED] and commit
   ```

---

## Calendar reminders to set

- Every **90 days**: rotate JWT_SECRET, GEMINI_API_KEY, GitHub PAT
- Every **180 days**: rotate Evolution API key, Razorpay secrets, SMTP password
- **Immediately** on suspicion or gitleaks alert

---

## Rotation log (append each rotation here)

| Date (UTC) | Secret | Reason | Operator |
|---|---|---|---|
| 2026-06-10 | Evolution API key | gitleaks-equivalent finding via Sprint D audit (leaked in commit d005034) | Claude + user |
