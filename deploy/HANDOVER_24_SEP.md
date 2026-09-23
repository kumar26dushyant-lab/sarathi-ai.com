# Steps for the extension — 24 Sep 2026

Hand this whole file over. Steps are in order. **Step 1 is the urgent one.**

Nothing here needs a decision from you. If a step fails, stop at that step and report — don't
improvise around it.

---

## Step 1 — URGENT: close an open door on the WhatsApp webhook (Cloudflare, 3 min)

### What is wrong

`POST /api/whatsapp/v2/webhook` accepts **unauthenticated** requests from anyone on the internet,
on **both** domains. Verified from outside just now:

```
POST https://sarathi-ai.com/api/whatsapp/v2/webhook      -> 200 {"ok":true}
POST https://nidaanpartner.com/api/whatsapp/v2/webhook   -> 200 {"ok":true}
```

The code does check a shared secret — but `validate_webhook_token()` **returns True when no token
is configured** ("dev only" in the comment), and `EVOLUTION_WEBHOOK_TOKEN` is not set in
production. It fails open.

What a caller can reach through it: `connection.update` writes to `wa_instances` and
`nidaan_official_instances` (so our WhatsApp numbers can be flipped to connected/disconnected),
and `messages.upsert` routes into `handle_official_inbound` — the **Nidaan document-ingestion
handler**. That is a path to injecting a fabricated inbound WhatsApp message against a live claim.

> Honest limit: `messages.upsert` only proceeds if the caller names a real Evolution instance, so
> it needs a guess at the instance name. That is a weak barrier, not a control.

Evolution API runs on **our own server** (`EVOLUTION_API_URL` = `http://localhost:8080`). Nothing
legitimate calls this path from the public internet.

### Do this — Cloudflare, BOTH zones (`nidaanpartner.com` and `sarathi-ai.com`)

Security → WAF → Custom rules → **Create rule**

| Field | Value |
|---|---|
| Name | `block-public-evolution-webhook` |
| Expression | `(http.request.uri.path eq "/api/whatsapp/v2/webhook") and (ip.src ne 161.118.186.201)` |
| Action | **Block** |

Put this rule **above** the `Allow payment webhooks (skip)` rule.

**Why this is safe either way:** if Evolution posts to `localhost`, the request never reaches
Cloudflare and the rule cannot affect it. If Evolution posts to the public URL, the request comes
from our own server (`161.118.186.201`) and the rule allows it. Everything else is blocked.

### Then verify (expect **403**, not 200)

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://sarathi-ai.com/api/whatsapp/v2/webhook \
  -H "Content-Type: application/json" -d '{"event":"probe"}'
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://nidaanpartner.com/api/whatsapp/v2/webhook \
  -H "Content-Type: application/json" -d '{"event":"probe"}'
```

**Then check WhatsApp still works** — send a message to the Nidaan number and confirm a reply.
If it stops, the rule is wrong for our setup: **delete the rule** and report, don't debug live.

---

## Step 2 — tighten the payment-webhook rule you already made (Cloudflare, 1 min)

The rule is correct and working. One word:

- Change `starts_with(http.request.uri.path, "/nidaan/api/webhook")`
- To `http.request.uri.path eq "/nidaan/api/webhook"`

`starts_with` also matches `/nidaan/api/webhookanything`, which skips the WAF on paths we never
meant to open. `eq` matches only the real route. Keep the `and http.request.method eq "POST"`.

Also add Sarathi's payment webhook to the same rule, or make a second one — it is the identical
endpoint on the other product and will hit the identical problem the first time Bot Fight Mode
scores it badly:

```
(http.request.uri.path in {"/nidaan/api/webhook" "/api/payments/webhook"}) and http.request.method eq "POST"
```

> Your rule is already better than the runbook's in one way: **Skip** with Bot Fight Mode off is
> belt and braces. Keep it.

---

## Step 3 — deploy the code (5 min)

Run from `C:\sarathi-business` on the Windows machine:

```bash
git push origin master
```

Then on the server:

```bash
ssh -i ~/.ssh/id_nidaan_oracle ubuntu@161.118.186.201 \
  'sudo systemctl start sarathi-deploy.service && sleep 45 && cd /opt/sarathi && git log --oneline -1'
```

Expect the last line to be the newest commit. Six commits are waiting:

```
2af87d7  notify panel: how we reach people, not what we hold
1d567e0  the webhook self-test can no longer exonerate us   <- and the docs commit after it
114d60a  status colours: weight, not just contrast
6c72f52  the undo button was on a list that is now always empty
```

### Verify the deploy — these must all pass

```bash
# 1. the site is up, and it is the right product answering
curl -s -o /dev/null -w "nidaan  %{http_code}\n" https://nidaanpartner.com/nidaan/ops
curl -s -o /dev/null -w "sarathi %{http_code}\n" https://sarathi-ai.com/

# 2. the new stylesheet is being served (must contain --nd-pill-loud-bg)
curl -s "https://nidaanpartner.com/static/nidaan_design.css?cb=$RANDOM" | grep -c "nd-pill-loud-bg"

# 3. the payment webhook still answers correctly from outside
curl -s -X POST https://nidaanpartner.com/nidaan/api/webhook \
  -H "Content-Type: application/json" -H "X-Razorpay-Signature: bad" -d '{}'
```

Expect: `200`, `200`, `1`, and `{"detail":"Invalid signature"}`.

> ⚠️ Use `?cb=$RANDOM` on step 2, **never** `?v=6`. Cloudflare caches `/static` immutably for 7
> days, and polling `?v=6` mid-deploy poisons that exact version for every user.

---

## Step 4 — prove the Razorpay webhook is genuinely fixed (Razorpay, 2 min)

Already confirmed from outside: `POST /nidaan/api/webhook` returns
`400 {"detail":"Invalid signature"}` in 0.5s, with Razorpay's own user agent, no challenge page.
The block is gone.

What is still worth doing, because it is the only fully end-to-end proof:

1. Reply to Razorpay's email and ask them to **re-deliver `pay_TfPq2skEiSuArv`**. They offered.
2. In the Razorpay dashboard → Settings → Webhooks → the endpoint → recent deliveries, confirm a
   **2xx**.
3. In Cloudflare → Security → Events, that path should now show **Skip**, not Managed Challenge.

No code change is needed afterwards. `razorpay_webhook_last_at` is stamped on arrival, so the
"No Razorpay webhook in 24 hours" alarm closes by itself on the first delivery.

---

## Step 5 — after the deploy, run these three checks and paste the output back

```bash
ssh -i ~/.ssh/id_nidaan_oracle ubuntu@161.118.186.201 \
  "sqlite3 'file:/opt/sarathi/sarathi_biz.db?mode=ro' -header -column \
   \"SELECT event_key, COUNT(*) n, SUM(telegram_sent) tg, SUM(email_sent) em, MAX(created_at) last \
     FROM nidaan_notifications WHERE event_key LIKE '%mention%' \
       AND created_at > datetime('now','-30 days') GROUP BY event_key;\""
```
→ Does tagging a teammate actually **arrive**? Code says yes; this reads the outcome. `tg` should
be close to `n`.

```bash
ssh -i ~/.ssh/id_nidaan_oracle ubuntu@161.118.186.201 \
  "sqlite3 'file:/opt/sarathi/sarathi_biz.db?mode=ro' -header -column \
   \"SELECT COUNT(*) unannounced FROM nidaan_payments WHERE COALESCE(announced_at,'')='';\""
```
→ Should be `0`.

```bash
ssh -i ~/.ssh/id_nidaan_oracle ubuntu@161.118.186.201 \
  'sudo journalctl -u sarathi-worker --since "20 min ago" | grep -iE "guardian|webhook|traceback" | tail -20'
```
→ No tracebacks.

---

## Step 6 — NOT yet. Needs the founder first.

Closing the fail-open in code (`validate_webhook_token`) must happen **after** a real token
exists on both sides, or inbound WhatsApp stops:

1. generate a secret, put it in `/opt/sarathi/biz.env` as `EVOLUTION_WEBHOOK_TOKEN=...`
   (then `chown sarathi:sarathi` + `chmod 600` + health-curl — that file has taken both sites
   down twice)
2. re-register each Evolution instance so it sends the header (existing instances keep the old
   webhook config; setting the env alone does nothing)
3. only then change `validate_webhook_token()` to refuse when no token is configured

Step 1's Cloudflare rule holds the door shut meanwhile. Do not do step 6 tonight.
