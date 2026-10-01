# Sarathi — Official WhatsApp Cloud API Setup (step-by-step)

**Goal:** run WhatsApp automation the sustainable, ban-proof way — Meta's official Cloud API.
**Good news:** the Sarathi code is **already built** for this (multi-tenant, per-subscriber
number). It's just switched off. The work is mostly a one-time Meta-console setup.

**Your webhook URL (you'll need it in Meta):** `https://sarathi-ai.com/webhook`

---

## The model (how subscribers connect)

- **Each subscriber uses their OWN WhatsApp number** — customers see the advisor's own
  number; the AI replies from it. Nobody shares one Sarathi number.
- Sarathi already stores each subscriber's credentials **per-tenant**
  (`wa_phone_id`, `wa_access_token`, `wa_verify_token`).
- **Phase 1 (now):** you/subscriber paste their Phone-Number-ID + token into Sarathi
  (endpoint `/api/onboarding/whatsapp` — already validates against Meta before saving).
- **Phase 2 (later build):** one-click "Connect WhatsApp" popup (Meta Embedded Signup) so
  subscribers self-onboard without touching the Meta console.

---

## PHASE 0 — get ONE number live (yours), ~20 min

Do these in the Meta console. At the end you'll have **3 values** to give me.

**Step 1 — Open your app**
- Go to **developers.facebook.com** → log in → top-right **My Apps**.
- If your old app is there, open it. Else **Create app** → type **Business** →
  name it `Sarathi WhatsApp` → Create.

**Step 2 — Open WhatsApp**
- Left sidebar → **WhatsApp → API Setup** (or "Quickstart").
- You'll see a test "From" number, your **WhatsApp Business Account**, and a temporary token.

**Step 3 — Copy your Phone Number ID**
- On the API Setup page, under "Send and receive messages", the **From** field shows a
  **Phone number ID** (a long number — NOT the phone number itself). **Copy it** → this is
  value ① `WHATSAPP_PHONE_ID`.

**Step 4 — Make a PERMANENT token (so it never expires like last time)**
- Go to **business.facebook.com → Business Settings (gear) → Users → System Users**.
- **Add** → name `Sarathi API` → role **Admin** → Create.
- Select it → **Add Assets** → pick your **App** (and your **WhatsApp Account**) → give
  **Full control** → Save.
- **Generate new token** → choose your app → tick **whatsapp_business_messaging** AND
  **whatsapp_business_management** → set expiry **Never** → Generate.
- **Copy it now** (shown only once) → value ② `WHATSAPP_ACCESS_TOKEN`.

**Step 5 — Copy your App Secret**
- Your app → **Settings → Basic → App Secret → Show** → copy → value ③ `WHATSAPP_APP_SECRET`.

**Step 6 — (I do this) Wire + enable + webhook + test**
- I put the 3 values into `/opt/sarathi/biz.env`, choose a `WHATSAPP_VERIFY_TOKEN`,
  re-enable the code path, and restart.
- You add the webhook in Meta: **WhatsApp → Configuration → Webhook** →
  Callback URL `https://sarathi-ai.com/webhook`, Verify token = the one I give you →
  Subscribe to the **messages** field.
- I send a test message from the server to your phone to confirm the pipe both ways.

> ⚠️ **Don't paste the token/secret into the chat.** Either you add them to
> `/opt/sarathi/biz.env` yourself (I'll give the exact lines), or we do it over a secure
> step. Tokens in chat can be logged.

---

## PHASE 1 — onboard a real subscriber's number
Same as Phase 0 but with the subscriber's number/token, saved to THEIR tenant via the
dashboard (the onboarding endpoint validates + stores it). Repeat per subscriber.

## PHASE 2 — one-click self-onboarding (build) — CONFIRMED TARGET

Full self-serve, subscriber-branded automation (founder-confirmed vision):
a Team+ subscriber (e.g. **"Delight Financial"**) opens their Sarathi dashboard → clicks
**"Connect WhatsApp"** → a Meta **Embedded Signup** popup opens inside Sarathi → they log
into their Facebook, pick/create their WhatsApp Business Account, add their number, set the
display name to their firm ("Delight Financial"), verify by OTP → Sarathi captures their
credentials automatically → AI runs on their number, under their brand.

**What Sarathi must complete for this (the gates):**
1. **Meta Business Verification** — SUBMITTED (Aug 2026). Required before non-test users connect.
2. **App Review** for `whatsapp_business_management` + `whatsapp_business_messaging`
   (Advanced Access) — Meta reviews the app before *subscribers* (not just test users) can
   use embedded signup. The main extra gate; plan ~a week.
3. **Embedded Signup implementation** — the "Connect WhatsApp" button (Facebook Login for
   Business + WhatsApp signup config) + backend **token exchange** (swap the returned code
   for the subscriber's WABA + phone-number-id + token). Per-tenant storage already exists
   (`/api/onboarding/whatsapp`, `wa_phone_id`/`wa_access_token` columns) — just needs the
   OAuth exchange + webhook subscription per WABA.

**Per-subscriber realities to set expectations:**
- The connected number becomes **API-only** (no normal WhatsApp app on it simultaneously).
- Display name ("Delight Financial") is **Meta-reviewed** (fast; must match the business).
- **Plan-gated** to Team+ (existing plan gate in code).

**Sequence rule:** finish PHASE 0 (prove the pipe on one number, ~20 min) BEFORE building
PHASE 2 (embedded signup, multi-day + App Review). Don't build the front door before the
plumbing is proven.

---

## Reality notes (honest)
- **Business Verification:** to go past the test number / raise limits, Meta needs your
  business verified (Business Settings → Security Center). Takes ~1–3 days; submit business
  docs. Phase 0 works on the free test number before this.
- **Cost at your volume:** tiny. Service replies inside the 24-hour customer window are
  free; only business-initiated template messages (e.g. some proactive nudges) may cost a
  few paise each. 50–100 customers/advisor is well within free/near-free.
- **Templates:** proactive messages (renewal reminders outside the 24h window) must use a
  pre-approved **template** (approval is quick, done in the Meta console). Reactive replies
  need no template.
</content>
