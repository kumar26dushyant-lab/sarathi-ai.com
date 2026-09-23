# Razorpay webhook is being blocked at Cloudflare — what to do

**Raised:** 23 Sep 2026 · **Status:** cause confirmed by Razorpay, fix not yet applied
**Money at risk:** none — see "Why this is not an emergency" below.

---

## What is actually wrong

Razorpay sends a webhook to `https://nidaanpartner.com/nidaan/api/webhook` every time a payment
is captured. Since **22 Sep 23:13** not one has arrived.

Razorpay's delivery log for `pay_TfPq2skEiSuArv` (23 Sep 14:24 UTC) shows why:

```
status_code: 403
response:    <!DOCTYPE html><html lang="en-US"><head><title>Just a moment...</title>
```

That is a **Cloudflare challenge page**. The request is stopped at the edge and our application
never sees it. Razorpay retried; the answer did not change.

**The cause is our own security checklist.** `deploy/CLOUDFLARE_WAF_RECOMMENDATIONS.md` §1 says
"Bot Fight Mode → On (both domains)". Bot Fight Mode challenges automated callers — and a payment
provider's webhook agent is an automated caller. It cannot tell ours from a scraper.

### Why our own check said otherwise

The payment guardian's `webhook_self_test()` POSTs to that URL with a bad signature and expects a
400. It got one, and reported **"✅ NOT our side"**. That sentence was wrong and it cost a day
with Razorpay support.

An edge challenge scores the **caller**, not the path. A request from our own server, with our
own user agent, is not scored like Razorpay's. The test proved *our app answers us*. It was never
able to prove *a third party gets through*, and it should not have said so.

Fixed: the self-test now recognises a challenge page by name, and a pass can no longer claim the
fault is elsewhere. Pinned by `_tools/test_webhook_selftest.py` (11 checks), which was run
against the old code first and fails 4 of them there.

---

## Why this is not an emergency

The payment guardian reads the Razorpay API directly **every 5 minutes**, compares it to our
ledger, and recovers anything missing — subscriptions, branch L2 fees, ₹499 reviews and shared
payment links. That is what found and recovered the two ₹588.82 payments on 23 Sep.

So: **no payment is lost while the webhook is down.** What is lost is *promptness* — a
confirmation can be up to 5 minutes late — and, more seriously, **a second independent path**.
Right now reconciliation is the only way money reaches our books. Fix the webhook and there are
two again.

---

## The fix — Cloudflare dashboard, ~5 minutes

Everything here is on `dash.cloudflare.com` → **nidaanpartner.com**. There is no API token for
Cloudflare anywhere in this repo, so this cannot be scripted from the app server.

### Step 1 — confirm it with your own eyes (30 seconds)

**Security → Events**, filter the last 24h by path `/nidaan/api/webhook`.
You should see blocked/challenged requests from Razorpay. Note the **Service** column — that
names which product stopped it (expect "Bot Fight Mode").

> If the Service says something else — a custom rule, Security Level, Under Attack Mode — fix
> that instead, and the rest of this runbook still applies in shape.

### Step 2 — turn Bot Fight Mode off for this zone

**Security → Bots → Bot Fight Mode → Off.**

On the free plan Bot Fight Mode runs *before* WAF custom rules and Configuration Rules, so a
"Skip" rule does **not** rescue a blocked path. Off is the only free-tier lever.

Leave it **On** for `sarathi-ai.com` — that zone has no provider webhooks in use today.

### Step 3 — put protection back, minus the webhooks

**Security → WAF → Custom rules → Create rule** (free plan allows 5):

| Field | Value |
|---|---|
| Name | `challenge-bots-except-webhooks` |
| Expression | `(not cf.client.bot) and not (http.request.uri.path in {"/nidaan/api/webhook" "/api/payments/webhook" "/nidaan/api/wa/webhook" "/api/whatsapp/v2/webhook"})` |
| Action | **Managed Challenge** |

Managed Challenge, not Block — a false positive should cost a real person a second, not a sale.

### Step 4 — prove it, by outcome

Do **not** read a setting and call it done. Three ways, cheapest first:

1. **Razorpay dashboard** → Settings → Webhooks → the endpoint → recent deliveries.
   A **2xx** means it is through. A 403 with `Just a moment...` means it is not.
2. **Ask Razorpay support to re-deliver** `pay_TfPq2skEiSuArv` — they offered, and it is a real
   request from their real infrastructure, which is the only vantage point that counts.
3. **Make a ₹1 payment** and watch for the Telegram confirmation within seconds rather than
   minutes. Fastest to read, costs a rupee.

### Step 5 — tell the app it is fixed

Nothing to do. `razorpay_webhook_last_at` is stamped on arrival, so the
"No Razorpay webhook in 24 hours" alarm closes by itself on the first delivery.

---

## If Bot Fight Mode is NOT the culprit

Check in this order — each is a thing that can turn a caller away before the app sees it:

1. **Security → Settings → Security Level.** If it is *High* or *I'm Under Attack*, that alone
   serves "Just a moment..." to anything with a poor IP reputation. Set it to *Medium*.
2. **Custom rules** — any rule whose expression happens to match `/nidaan/api/webhook`.
   The `admin-india-only` rule in our checklist matches paths containing `/admin` and would
   **not** match this one, but check the live rules rather than the document.
3. **Rate limiting** — a burst of renewals could trip a limit meant for login.
4. **Origin lock.** `deploy/lock-origin-to-cloudflare.sh` restricts ports 80/443 to Cloudflare
   ranges. That is correct and should stay; it is *not* the cause here, because Cloudflare
   answered rather than timing out. It does mean **do not "fix" this by pointing Razorpay at the
   origin IP** — that would expose the origin and undo the lock.

---

## What must not be done

- **Do not give Razorpay an unproxied hostname.** It exposes the origin IP and undoes the origin
  lock. The webhook is signature-verified, but the origin's address is worth more than the
  convenience.
- **Do not disable signature verification** to "see if it helps". It is the only thing standing
  between our ledger and anybody who can POST.
- **Do not turn off the guardian** once the webhook works. Two independent paths is the point.
