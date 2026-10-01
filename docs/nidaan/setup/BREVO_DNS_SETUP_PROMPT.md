# Brevo + Cloudflare Email Authentication — Handoff Prompt

> Paste everything below the line into your Claude extension (the one with browser access).
> It authenticates `nidaanpartner.com` for Brevo so branded email stops going to spam.

---

## TASK: Authenticate nidaanpartner.com for Brevo email sending

You are fixing email deliverability for **NidaanPartner** (Nidaan – The Legal Consultants LLP).
Work in two places: **Brevo** (the email provider) and **Cloudflare** (the DNS host).

### Background — what is wrong right now

`nidaanpartner.com` currently publishes this SPF record:

```
v=spf1 include:_spf.google.com ~all
```

That authorises **Google only**. Brevo is not listed, and Brevo has no DKIM record for the
domain. So every email sent through Brevo claiming to be `From: info@nidaanpartner.com` fails
SPF and DKIM, and Gmail files it as spam. Signup/verification codes were being sent successfully
and never arriving for exactly this reason.

Current verified state (already checked — do not re-diagnose, just fix):

| Item | Current value |
|---|---|
| DNS host | **Cloudflare** (`bristol.ns.cloudflare.com`, `keaton.ns.cloudflare.com`) |
| SPF | `v=spf1 include:_spf.google.com ~all` — Brevo **missing** |
| Google DKIM | present ✅ |
| Brevo DKIM | **absent** ❌ |
| DMARC | `v=DMARC1; p=none; rua=mailto:info@nidaanpartner.com; fo=1` |
| Brevo validated sender | only a gmail address — `info@nidaanpartner.com` **not** validated |
| Brevo credits | showing **0** (free tier = 300/day) |

---

### ⚠️ The one thing that must not go wrong

**There must be exactly ONE SPF record on the domain.**

In Step 3 you must **EDIT the existing SPF TXT record**. Do **not** create a second one.
Two SPF records make SPF fail for *everything*, which would also break the Google mail that is
currently working correctly. If you find more than one `v=spf1` record, merge them into one and
say so in your report.

---

### Step 1 — Brevo: add the domain

1. Log in to Brevo.
2. Go to **Senders, Domains & Dedicated IPs** → **Domains** tab.
3. Click **Add a domain** and enter: `nidaanpartner.com`
4. Brevo will display DNS records to add — typically:
   - a **`brevo-code`** TXT record (domain ownership proof)
   - a **DKIM** TXT record (usually at `mail._domainkey`)
   - possibly a DMARC suggestion (we already have DMARC — see Step 5)
5. **Copy each record's exact Name/Host and Value.** Record them in your report.

### Step 2 — Cloudflare: add Brevo's records

1. Log in to Cloudflare and select **nidaanpartner.com**.
2. Go to **DNS → Records**.
3. For each record Brevo gave you: **Add record** → Type **TXT** → paste the Name and Value
   exactly as Brevo showed them → **Save**.
   - If Cloudflare auto-appends the domain to the Name, do not type it twice
     (enter `mail._domainkey`, not `mail._domainkey.nidaanpartner.com`).
   - TXT records have no proxy option — ignore anything about the orange cloud.

### Step 3 — Cloudflare: EDIT the existing SPF record (do not add a new one)

1. Still in **DNS → Records**, find the existing **TXT** record for the root domain whose
   content starts with `v=spf1`. It currently reads:
   ```
   v=spf1 include:_spf.google.com ~all
   ```
2. Click **Edit** on that record and change the content to:
   ```
   v=spf1 include:_spf.google.com include:spf.brevo.com ~all
   ```
3. **Save.** Confirm afterwards that only ONE `v=spf1` record exists on the domain.

### Step 4 — Brevo: verify the domain

1. Return to Brevo → **Domains**.
2. Click **Authenticate** / **Verify** next to `nidaanpartner.com`.
3. Cloudflare propagates quickly, but if it fails, wait ~15 minutes and retry.
4. Continue until the domain shows as **authenticated / verified**.

### Step 5 — Brevo: validate the sending address

1. Brevo → **Senders, Domains & Dedicated IPs** → **Senders** tab.
2. **Add a sender**: name `Nidaan Partner`, email `info@nidaanpartner.com`.
3. Brevo emails a confirmation link to that address — open it and confirm.
4. Confirm the sender shows as **active**.

### Step 6 — Brevo: check the sending allowance

1. Brevo → account/plan page.
2. Report the **plan type** and **remaining daily credits**.
3. The free tier is 300 emails/day and the account recently showed **0 credits** with 257 sent in
   one day. If credits are exhausted or close to it, say so clearly and recommend a top-up or
   upgrade — do **not** purchase anything yourself.

### Step 7 — Report back

Report, concisely:
- The exact DNS records you added (name + type; values may be truncated).
- Confirmation that **only one** SPF record exists, and its final content.
- Whether the Brevo domain shows **authenticated**.
- Whether `info@nidaanpartner.com` shows as a **validated sender**.
- The Brevo plan and remaining daily credits.
- Anything that failed or looked unexpected.

Do **not** change any other DNS record, and do **not** alter the DMARC record — the developer
will tighten DMARC to `p=quarantine` separately once both senders are confirmed aligned.
