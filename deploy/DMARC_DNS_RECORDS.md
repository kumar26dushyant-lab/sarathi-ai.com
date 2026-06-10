# Email Security DNS Records — Cloudflare Setup
# sarathi-ai.com + nidaanpartner.com

## What these records do

| Record | Purpose |
|--------|---------|
| SPF | Tells receiving servers which IPs are allowed to send email on behalf of your domain |
| DMARC | Tells receiving servers what to do with emails that fail SPF/DKIM checks |
| DKIM | Cryptographic signature proving the email wasn't tampered in transit |

Without these, your emails from sarathi-ai.com will land in spam (Gmail, Outlook reject them).

---

## Step 1: Add to Cloudflare DNS for sarathi-ai.com

Go to: **Cloudflare → sarathi-ai.com → DNS → Add record**

### SPF Record (already partially set — UPDATE if exists)
| Field | Value |
|-------|-------|
| Type | TXT |
| Name | @ (root) |
| Content | `v=spf1 include:_spf.google.com ~all` |
| TTL | Auto |

> This authorises Google's servers to send email for @sarathi-ai.com.
> If you also send from Oracle Cloud directly, add `ip4:140.238.246.0`:
> `v=spf1 ip4:140.238.246.0 include:_spf.google.com ~all`

---

### DMARC Record (NEW — add this)
| Field | Value |
|-------|-------|
| Type | TXT |
| Name | `_dmarc` |
| Content | `v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@sarathi-ai.com; ruf=mailto:dmarc-reports@sarathi-ai.com; sp=quarantine; adkim=r; aspf=r; pct=100; fo=1` |
| TTL | Auto |

> **p=quarantine** means failing emails go to spam (not rejected outright). Once you confirm your legit emails pass, change to `p=reject`.

---

### DKIM Record (requires Google Workspace or Gmail setup)

If you send email via Gmail/Google Workspace:
1. Go to **Google Admin Console → Apps → Gmail → Authenticate email**
2. Generate DKIM key for `sarathi-ai.com`
3. Google gives you a TXT record like:
   - Name: `google._domainkey`
   - Value: `v=DKIM1; k=rsa; p=<long-key>`
4. Add that TXT record in Cloudflare

If you don't have Google Workspace (just Gmail SMTP with App Password):
- DKIM isn't available from plain Gmail SMTP
- Your emails will still pass SPF (you're using Google's servers)
- DMARC p=quarantine will work with SPF alone

---

## Step 2: Add the same records for nidaanpartner.com

Go to: **Cloudflare → nidaanpartner.com → DNS → Add record**

### SPF for nidaanpartner.com
| Field | Value |
|-------|-------|
| Type | TXT |
| Name | @ |
| Content | `v=spf1 include:_spf.google.com ~all` |

### DMARC for nidaanpartner.com
| Field | Value |
|-------|-------|
| Type | TXT |
| Name | `_dmarc` |
| Content | `v=DMARC1; p=quarantine; rua=mailto:dmarc-reports@nidaanpartner.com; sp=quarantine; adkim=r; aspf=r; pct=100` |

---

## Step 3: Verify after adding records (wait 5–30 minutes for propagation)

Run from your local terminal or any online tool:
```bash
# Check SPF
nslookup -type=TXT sarathi-ai.com

# Check DMARC
nslookup -type=TXT _dmarc.sarathi-ai.com

# Online checker: https://mxtoolbox.com/dmarc.aspx
# Enter: sarathi-ai.com
```

---

## Step 4: Add GITHUB_PAT to biz.env on the server

For the GitHub backup script to work, add to `/opt/sarathi/biz.env`:
```
GITHUB_PAT=your_personal_access_token_here
```

Generate at: **GitHub → Settings → Developer Settings → Personal Access Tokens → Tokens (classic)**
- Scopes needed: `repo` (full repository access)
- Name it: `sarathi-server-backup`
- Expiry: 1 year (set a reminder to renew)

---

## Quick reference: What goes wrong without these

| Missing | Symptom |
|---------|---------|
| SPF | Gmail marks your OTP emails as spam |
| DMARC | Yahoo, Outlook may reject your emails outright |
| DKIM | Emails flagged as potentially forged |
| All three | ~30–60% of your emails never get delivered |
