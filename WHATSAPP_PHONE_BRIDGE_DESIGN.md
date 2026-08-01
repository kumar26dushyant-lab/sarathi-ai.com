# Sarathi WhatsApp — Phone-as-Server Design (APK-Bridge)

**Status:** DESIGN for review · **Date:** 2026-07-31 · **Author:** engineering
**Context:** The Evolution API + residential-proxy path is a confirmed dead end
(datacenter IP → WhatsApp refuses the QR handshake; v2.2.3 *and* v2.3.7 both fail to
apply the proxy at runtime — `/proxy/set` hangs, only container-boot loads it). Per the
founder's call, we pivot to **using a real phone as the WhatsApp endpoint**.

> **No infra changes are proposed here — this is a plan to review before any build.**

---

## 1. TL;DR / Recommendation

Adopt the **APK-Bridge** ("phone-as-client") model that is **already ~80% built** in
this repo (`biz_wa_agent.py` + `apk/` Android app + `wa_agent_*` tables + `/ws/agent`).
The agent's own phone runs **normal WhatsApp**; a lightweight Sarathi Android app reads
incoming message **notifications** and sends AI replies back **into the same chat via the
notification's reply box**. The backend does the thinking (AI, rate-limits, business
hours, human-takeover detection); the phone is just the real device WhatsApp trusts.

This is the **most ban-resistant** option possible: a real handset, a real SIM/number,
a real carrier IP, the real WhatsApp app — nothing WhatsApp can fingerprint as a bot.
It also **sidesteps every problem** we just hit (no datacenter IP, no Baileys, no proxy).

**We should NOT** pursue "phone as a network proxy for Evolution" (see §3, Model B) — it
keeps Baileys (ban risk) and is fiddly for little gain.

---

## 2. What the founder asked for (requirements)

From earlier direction, the WhatsApp automation must be **ban-preventive** and:

1. **Reactive** — reply within ~3 min *only* when the AI knows the answer or it's
   policy-related; mostly respond, don't initiate.
2. **Escalate out-of-scope** — if a lead/customer raises something outside scope, the AI
   nudges the **subscriber's/admin's own WhatsApp number** instead of guessing.
3. **Quiet-if-manual** — if the admin is already chatting with that lead by hand, the AI
   stays silent.
4. **Active-hours window** — subscriber picks the hours the AI may respond (default 24/7);
   connected-but-AI-disabled ⇒ AI silent.
5. **Proactive only for**: renewal reminders / pending discussions / lead-journey nudges —
   human-style, never spammy campaigns.
6. **One number per subscriber**, ~50–100 customers each.

§6 maps each of these to a component and marks **built / verify / gap**.

---

## 3. Two interpretations of "phone as server" — pick A

**Model A — Phone-as-Client (APK-Bridge)  ✅ recommended, mostly built**
- Phone runs real WhatsApp. Sarathi APK is a `NotificationListenerService`: reads the WA
  notification (sender + text), ships it to the backend over a signed WebSocket, gets the
  AI reply, and fires it back through the notification's **RemoteInput** reply action.
- No Baileys, no Evolution, no QR-linking of a "WhatsApp Web" session. WhatsApp sees only
  the genuine app on a genuine device.
- **Trade-off:** the phone must stay on, online, and running the app (foreground service +
  boot-restart already handle this). Replies go into the specific chat that notified.

**Model B — Phone-as-Proxy (network egress)  ❌ not recommended**
- Phone shares its mobile-data connection; Evolution/Baileys routes WhatsApp-Web traffic
  out through the phone's carrier IP.
- Still uses Baileys (the thing WhatsApp bans), still needs the flaky Evolution proxy
  plumbing, and adds a phone-tethering/proxy server to maintain. Strictly worse than A.

Everything below assumes **Model A**.

---

## 4. Architecture (Model A)

```
 Customer's WhatsApp
        │  (message)
        ▼
 Agent's phone — real WhatsApp app  ──posts notification──►  Sarathi APK
                                                              (NotificationListenerService)
        ▲                                                          │  signed WS (HMAC)
        │  reply typed into the chat                               ▼
        │  via notification RemoteInput            Backend  /ws/agent  (biz_wa_agent.py)
        │                                             │  • auth device (HMAC key)
        └─────────── AI reply text ◄──────────────────┤  • business-hours / active-window gate
                                                       │  • human-takeover check (stay quiet)
                                                       │  • rate-limit (daily/hourly caps)
                                                       │  • smart_inbound_handler → Gemini reply
                                                       │      (policy/CRM context from DB)
                                                       │  • else → escalate: nudge admin's number
                                                       └──► log to wa_agent_conversations
```

**Key components already present**
- Backend: `biz_wa_agent.py` (1514 lines) — device credentials + HMAC (`generate_device_credentials`,
  `authenticate_device`, `sign_message`/`verify_message`), rate limits (`check_rate_limit`),
  business hours (`is_business_hours`), takeover (`detect_takeover`, `DEFAULT_TAKEOVER_KEYWORDS`),
  AI reply (`smart_inbound_handler`, `get_customer_ai_reply` → Gemini, with policy/lead context),
  CRM voice/text commands, conversation logging, pending-event queue + `deliver_pending`.
- Endpoints (wired): `POST /api/wa-agent/connect` (mint device creds/QR), `GET /api/wa-agent/status`,
  `DELETE /api/wa-agent/disconnect`, `PATCH /api/wa-agent/settings` (auto_reply, business_hours,
  takeover_keywords, daily/hourly caps), `GET /api/wa-agent/conversations`, and the live
  `WS /ws/agent` (HMAC-signed frames).
- Android (`apk/`, ~650 lines Kotlin): `WANotificationService` (read WA notif + `sendReply`
  via RemoteInput, incl. Hindi reply-label detection), `WAForegroundService` (keep-alive),
  `BootReceiver` (auto-start), `CRMWebSocketClient`, Onboarding/QrScan/Status/PermissionGuide UI.
- Schema: `wa_agent_devices`, `wa_agent_pending`, `wa_agent_conversations`.
- Dashboard: full APK UI JS still in `static/dashboard.html` (`apkLoadStatus` …), currently
  **hidden** (we hid it earlier when trying Evolution) — can be re-enabled.

---

## 5. Ban-preventive design (how it stays safe)

- **Reactive-only by default.** AI replies solely to inbound messages, within a jitter'd
  ~1–3 min (human-like), and *only* when confident (policy/CRM/known-intent). Unknown →
  escalate, never bluff.
- **Human-like pacing + caps.** `check_rate_limit` enforces per-hour/per-day ceilings;
  add small randomized delays; never bulk-send; one chat at a time.
- **Quiet-if-manual.** If the admin has recently replied by hand in that chat (takeover
  detection + a "recent human activity" window), AI suppresses itself.
- **Active-hours.** Replies only inside the subscriber's configured window (default 24/7);
  master `auto_reply` off ⇒ fully silent (connected but mute).
- **Proactive = rare + purposeful.** Only renewal/pending/journey nudges, throttled, in
  hours, skippable — routed through the same device so they look native.
- Because it's the **real app on the real phone**, even if a message slips, there is no
  "unofficial client" signal for WhatsApp to ban.

---

## 6. Requirement → component status

| # | Requirement | Component | Status |
|---|-------------|-----------|--------|
| 1 | Reactive ~3-min reply when confident | `smart_inbound_handler` + `get_customer_ai_reply` | **Built** — verify the delay/jitter + confidence gate |
| 2 | Escalate out-of-scope → admin's own number | intent split in `smart_inbound_handler` (business vs answerable) | **Verify/gap** — confirm the *nudge-to-own-number* send path exists |
| 3 | Quiet-if-manual | `detect_takeover` + takeover_keywords | **Built** — add a "recent human reply in chat" suppression window |
| 4 | Active-hours + master mute | `is_business_hours` + `auto_reply` setting (`PATCH /settings`) | **Built** — surface a clean date/time picker in dashboard |
| 5 | Proactive renewal/pending/journey nudges | `send_outbound_via_apk` (transport exists) | **Gap** — needs a throttled scheduler that pushes these via the device |
| 6 | One number/subscriber, 50–100 customers | device = per agent/tenant | **Built** — model is 1 device per agent |

---

## 7. Gaps to close (engineering)

- **G1 — Proactive nudge scheduler:** a worker loop that, in-hours and throttled, sends
  renewal/pending/journey messages through `send_outbound_via_apk`. (Reactive path is done.)
- **G2 — Escalate-to-own-number:** confirm/finish the path that DMs the admin's own WhatsApp
  when a lead goes out-of-scope (vs. only tagging in CRM).
- **G3 — "Recent human reply" suppression:** track last manual reply per chat so AI backs
  off mid-conversation, not just on keywords.
- **G4 — Dashboard re-enable + UX:** un-hide the APK panel; add the active-hours picker and
  the master AI on/off toggle in Tier-II/III-clear language (words over icons), mobile-first.
- **G5 — APK build/sign/distribute:** produce a signed release APK + a dead-simple install
  guide (sideload / Play internal track) and the in-app onboarding (grant Notification
  access + battery-optimisation exemption). Verify against latest Android.
- **G6 — Reconnect/observability:** device offline detection, heartbeat, and a status badge
  so the subscriber sees "AI active / phone offline".

---

## 8. Phased plan (review-gated, nothing built until you approve)

- **P0 — Assessment (0.5 day, no code):** run the existing backend + a debug APK on one
  phone; confirm end-to-end read→AI→reply actually works today; produce a precise
  built-vs-broken list. *Exit:* we know the true starting point.
- **P1 — Backend gaps (careful, additive):** G2 + G3 + G1 (proactive scheduler behind a
  per-tenant flag, default off). All additive, backward-compatible, tested on the live path.
- **P2 — Dashboard (G4):** re-enable panel, active-hours picker, master toggle, status badge
  — mobile-first, full EN/HI language conversion.
- **P3 — APK hardening + distribution (G5/G6):** signed build, onboarding, install guide,
  reconnect/heartbeat, battery-exemption UX.
- **P4 — Single-device pilot:** one real subscriber phone, ~1 week, watch conversation logs
  + WhatsApp health; tune pacing/caps.
- **P5 — Controlled rollout:** enable per subscriber, monitored.

---

## 9. Open questions for you

1. **Whose phone / number?** Each subscriber uses their own business phone + number
   (recommended), or do we run a Sarathi-managed device per subscriber?
2. **Device availability** — subscribers must keep the phone on + online. Acceptable, or do
   we need a "spare always-on phone" story for some?
3. **Proactive nudges** — okay to build behind a default-OFF flag and enable per subscriber
   after the pilot?
4. **Distribution** — sideloaded APK (fastest) vs Play Store internal track (more trust,
   slower)?

---

## 10. What is NOT changing

- No server/infra changes from this document. Evolution stays on v2.3.7 as an idle,
  healthy baseline (not used by this design). The live app is untouched. This is a plan.
</content>
