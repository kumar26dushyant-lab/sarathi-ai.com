# WhatsApp for Subscribers — Plan for Review (v1, 2026‑08‑21)

**Status: PLAN ONLY. Nothing built. Awaiting founder sign‑off before any code.**

This is the rail that lets a **paying Sarathi‑AI advisor (a "subscriber") reach their own clients on WhatsApp** — and it's what unlocks *"advisor speaks a message → it's sent to their client."*

Founder decisions already locked (2026‑08‑21):
- **Hosting model: OUR WABA, multi‑number — we host + bill.** We are effectively the provider; each subscriber's WhatsApp number lives under infrastructure we manage.
- **Phase 1 scope: I recommend the sequencing below.**

---

## 1. The honest part first — the one‑way doors

These are decisions that are painful or impossible to reverse. Naming them up front so we go in with eyes open.

| One‑way door | Why it's sticky | How we de‑risk |
|---|---|---|
| **The phone number a client sees** | Once clients know an advisor at `+91‑XXXX`, changing it later = lost trust + re‑opt‑in. A number registered on WhatsApp API **cannot** be moved back to the normal WhatsApp app. | Decide numbering scheme once (below). Treat every number as permanent. Never register an advisor's *personal* WhatsApp. |
| **Meta WABA / business verification** | Tied to *our* Meta Business, our legal entity, our quality rating. If our WABA gets flagged for spam, **every** subscriber's messaging degrades at once. | Strict opt‑in + template discipline (below). Per‑subscriber throttles. Isolate risk so one bad advisor can't sink the shared rating. |
| **Billing relationship** | We pay Meta per‑conversation and re‑bill subscribers. Underpricing locks us into a loss; overpricing kills adoption. | Simple, transparent per‑message/'‑conversation pack pricing; start with a small margin, revisit after pilot. |
| **Opt‑in provenance** | Meta can demand proof that each client agreed to be messaged. No proof = number banned. | We store *how & when* each client opted in, per number. Non‑negotiable from day one. |

**Nothing here blocks us — but all four must be designed once, correctly.** That's why this is a plan, not a quick build.

---

## 2. What "our WABA, multi‑number" means technically

- We operate as a **Tech/Solution Provider**: one Meta Business Portfolio, one or more **WhatsApp Business Accounts (WABAs)** we own, each holding **multiple phone numbers** (Meta allows a batch per WABA; more on request).
- Each subscriber is onboarded via **Embedded Signup** → their dedicated **business number** registers under a WABA we manage. They never touch Meta directly; we host + bill.
- Messaging runs on the **WhatsApp Cloud API** (Meta‑hosted; no on‑prem infra for us) — HTTPS send + a **webhook** for inbound + delivery/read receipts.
- **Two message types** (this shapes everything):
  - **Template messages (HSM):** pre‑approved by Meta. The *only* way to start or re‑open a conversation. Used for reminders (renewal/EMI/lapse) and re‑engagement.
  - **Session/free‑form messages:** allowed **only within 24h** of the client's last message. This is the window where the advisor's *free voice message* can be delivered as‑is.

> Implication for the voice ask: an advisor can freely voice‑message a client **only if that client messaged them in the last 24h**. Outside the window, the first touch must be an approved template (or a template that invites the client to reply, opening the window). The plan handles both paths.

---

## 3. Compliance rail (built once, protects everyone)

1. **Opt‑in capture** — every client number must have a recorded opt‑in (source + timestamp): collected at claim intake, via a link, or the client messaging first. No opt‑in → cannot be messaged. Stored per number.
2. **Template library** — a small set of Meta‑approved templates in EN + HI (renewal due, EMI reminder, policy lapse warning, "your advisor sent an update — reply to continue"). Submitted for approval up front.
3. **Quality & throttling** — per‑subscriber send caps + our own spam heuristics, so one careless advisor can't tank the shared quality rating. Alert + auto‑pause a number trending toward "flagged."
4. **STOP handling** — automatic opt‑out on "STOP/बंद करो"; blocked thereafter. Required by Meta.
5. **Audit** — every outbound (who/which advisor/which client/template‑or‑session/cost) logged, same discipline as the radar's `nidaan_radar_sent`.

---

## 4. Phased plan — **my recommended sequencing**

I recommend we **prove the rail with low‑risk, high‑value automation first**, then open free‑form voice once the WABA has a healthy quality rating and real opt‑in data. Rationale: the voice‑to‑client feature is the *riskiest* (free‑form, advisor‑authored, easiest to get flagged) and the *most dependent* on everything else being live. Doing it first would put our shared WABA rating at risk before we've proven deliverability.

### Phase 0 — Foundations (no user‑facing feature)
Meta Business + WABA setup, business verification, Cloud API integration, webhook, one test number, template submission. Data model (§5). **Outcome:** we can send an approved template to one opted‑in test client and receive replies. *This is the gate everything else waits on — largely account/approval lead time, not code.*

### Phase 1 — **Reminders + AI support** (recommended first ship)
- **Automated utility templates** to clients on the advisor's behalf: renewal due, EMI reminder, policy lapse — the messages that clearly help and are unlikely to be marked spam. Ties into existing subscriber/client data.
- **AI support**: when a client replies (opening the 24h window), our AI assistant answers common questions in EN/HI, hands off to the advisor when needed.
- **Why first:** template‑driven, hard to abuse, builds opt‑in history + a healthy quality rating, and delivers immediate value (fewer lapses = advisor revenue). Proves billing + deliverability + compliance with the least risk.

### Phase 2 — **Voice → client message** (the original ask)
Once the rail is healthy: advisor speaks in Telegram/app → transcribe (existing STT) → clean up (existing AI) → **advisor reviews the text** → send to the client.
- **Inside 24h window:** delivered as a normal session message (free‑form) — exactly the fluid experience described.
- **Outside window:** we send an approved "your advisor has an update — reply to continue" template that opens the window, then deliver. Advisor sees which path applied. (Confirm‑to‑act, consistent with the Telegram assistant.)

### Phase 3 — **Campaigns / bulk** (deferred, explicitly)
Broadcasts to segments. Highest ban risk; only after quality rating is proven and pricing is validated. Not in early scope — matches your existing "campaigns deferred" note.

---

## 5. Data model & where it plugs into the current codebase

New, additive tables (mirroring how the radar was built — additive, backward‑compatible, nothing existing touched):
- `wa_numbers` — one per subscriber business number (subscriber_id, phone, WABA id, status, quality rating, throttle).
- `wa_client_optins` — client number, opt‑in source + timestamp, STOP state.
- `wa_messages` — every in/out message (subscriber, client, direction, template‑vs‑session, body/media ref, cost, status), audited like `nidaan_radar_sent`.
- `wa_templates` — our approved template catalogue (name, lang, status).

Integration points:
- **Sending** lives in a new `biz_sarathi_whatsapp.py` (isolated module, like `biz_nidaan_radar.py`), so it never entangles Sarathi tenant/agent code except through the existing `biz_platform_bridge.py` boundary.
- **Voice** reuses the tgcrm STT + AI cleanup already built for the voice CRM.
- **Webhook** = one new FastAPI route (Meta inbound + receipts), guarded like other bot singletons (`if RUN_SINGLETONS:`), on the worker.
- **Pilot number** in your notes: **GoLuQ.com +91 83495 04400** — use as the Phase 0/1 test number.

---

## 6. Cost model (nominal, as you asked — "best quality, low cost")

- Meta bills **per 24‑hour conversation**, priced by category (utility / marketing / service / authentication) and country. Utility & service (our Phase 1) are the cheap end; India rates are among the lowest.
- **Our line:** pass‑through + a small flat margin, sold as prepaid message/conversation packs per subscriber. Keeps it predictable for Tier‑2/3 advisors and keeps us out of a loss.
- No heavy infra cost — Cloud API is Meta‑hosted; we add only our app + DB.
- I'll put concrete per‑conversation numbers in v2 once you confirm we're proceeding (they change by Meta's current rate card; I don't want to quote stale figures here).

---

## 7. What I need from you to move (not now — when you're ready)

1. **Meta Business verification** — legal entity docs (this has lead time; it's the long pole, not code).
2. **Numbering scheme** — one shared "Sarathi" business number vs. a dedicated number per advisor. (Affects §1 one‑way door + cost + client trust. I'll recommend per‑advisor for trust, shared to start for cost — your call.)
3. **Confirm Phase 1 = Reminders + AI support first** (my recommendation) vs. jumping straight to voice.
4. **Template wording** — I'll draft the EN/HI templates for the renewal/EMI/lapse/re‑engage set for your approval before Meta submission.

---

## 8. Summary

- **Model:** our WABA, multi‑number, we host + bill (locked).
- **Sequence (recommended):** Foundations → **Reminders + AI support** → **Voice‑to‑client** → Campaigns (deferred).
- **Guardrails baked in from line one:** opt‑in provenance, template discipline, per‑subscriber throttles, STOP handling, full audit — because the shared WABA quality rating protects (or sinks) every subscriber at once.
- **Nothing is built.** On your go‑ahead I start with Phase 0 foundations (mostly Meta account/verification lead time) and draft the templates for your approval.
