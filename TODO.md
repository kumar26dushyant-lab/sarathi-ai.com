# SARATHI BUSINESS — LIVING TO-DO

_Auto-maintained by Claude **every conversation**, alongside `PROJECT_MASTER_CONTEXT.md`._
_**Two-terminal workflow:** work 🟦 NidaanPartner items in one VS Code terminal, 🟩 Sarathi items in another. Each app's section is self-contained so both can progress simultaneously without collision._
_Legend: 🔴 blocked/awaiting owner · 🟡 in progress · 🟢 next/planned · ✅ done_

**Last updated:** 2026-08-29 (number removed everywhere; claim activity timeline live; WA message composer built; Sarathi Embedded-Signup design added)

---

## 🟦 NIDAANPARTNER.COM

### 🟡 In progress — CLAIM ARCHITECTURE & DATA CLARITY (build carefully, no breakage)
- ✅ Fixes: All Claims search lag (client-side), Staff filter populated, L2 Paid/Due filter, **All Claims stuck-loading** (staff-filter await was blocking the fetch → non-blocking). Sidebar grouped into labeled zones (Accounts in Work). Official Numbers archived (unused ~52d). Save-number banner → Meta-WABA informational message.
- **Claim raise forms at ALL endpoints — review + align data (NEXT, careful):** capture with clarity → **Claimant (mobile+email MANDATORY** — explain in-form why: they provide documents later; **insured mobile optional)**, Subscriber (email+mobile), Branch (code+mobile+email), referral + staff-referral codes. Goal: WhatsApp/email always reach the RIGHT person. Review every form (branch raise, subscriber, ops, ₹499, review-request) for field completeness.
- **Comms routing map:** define which message goes to whom at each stage; if the **claimant doesn't respond → escalate to whoever referred them** (subscriber/branch/staff/My-Business) explaining why + what's needed; send across all channels.
- **Claim pipeline (one workspace, stage+origin views)** replacing the 3-section confusion — build TILL L2 now; **leave space AFTER L2** for post-L2 stages (drafting, Lokpal: 3 insurer reminders + 30-day wait, claimant email-ID creation tied to the email-forwarding radar). Then resolved.
- **Accounts stays separate** (people directory) but keep the **plan/paid/capping double-check** visible.
- Awaiting: founder's **document list per claim type** → load into checklist templates for the WhatsApp bot.


### 🟡 In progress — PAYMENT RELIABILITY (founder: "I don't want any payment issue in future")
- ✅ Removed stale artifacts: success email showed "10 claims / quarter" + "auto-renews every quarter" → now LIVE quota (3/month silver·gold, 10/month platinum) + cycle-aware. billing_cycle default monthly. (Dead `nidaan_signup.html` route redirects to /start — not served.)
- ✅ Thank-you page auto-continues in **3s** (was 5s).
- **ROOT CAUSE of "thank-you not showing":** lost client callback (UPI app-switch / low network) — payment completes via webhook (email sent) but the browser never runs the success handler → no redirect. **NEXT: recovery-on-return** — on dashboard load, detect an activated-but-unconfirmed payment → show the thank-you.
- ✅ **#1 recovery-on-return SHIPPED** — `/nidaan/api/payment/confirm-check` + dashboard INLINE congrats banner (loop-proof, per sub_id). Fixes "thank-you not showing" on lost callback.
- ✅ **#4 payment watchdog + #5 health funnel SHIPPED** — `biz_nidaan_payment_watch.py` (deterministic: amount↔plan mismatch, stuck captured-but-unrecorded, failure spike; snapshot; 15-min loop; exception-only alerts on bell+email+Telegram; NO LLM in money path). Revenue → 🩺 Payment Health funnel + re-scan.
- **Remaining:** (2) dead-end elimination (already-paid → guide; partly done via the already-subscribed guide — extend to gateway re-entry); (3) user-guidance for every failure mode (timeout/low-net/failed/wrong-page/double-submit); (6) My-Business/branch performance monitor bot.

### 🔴 Blocked / awaiting owner
- **WhatsApp number ✅ LIVE** — +91 91836 86384 connected as "NidaanPartner" (VERIFIED), creds in `biz.env`. **ONE step left (owner):** Meta → Webhooks → callback `https://nidaanpartner.com/nidaan/api/wa/webhook`, verify token `np_wa_0d8cac5997584755d553`, subscribe to `messages`. Then inbound flows.
- **WA orchestrator ✅ LIVE (in-session guided flow).** `biz_nidaan_wa_orchestrator.py`: claimant messages number → matched to claim by phone → greet + ask next pending doc → inbound doc → download → PDF → Gemini right-doc/quality gate → save + mark checklist → ask next/complete; recorded on claim timeline. Manual start: drawer "💬 Start WhatsApp collection" + `POST /claims/{id}/wa/start`. Webhook verified.
  - **REMAINING for full automation (needs Meta template approval):** submit templates (welcome / doc_reminder / received / quality / complete) so COLD-START + out-of-session **daily reminders** work (free-form only delivers inside the 24h session). Then wire the **reminder loop** (Phase 2) + welcome/thank-you/claim-registered triggers. Composer copy is ready to become templates.
- **NidaanPartner.com WhatsApp Business CAMPAIGN alignment** — the big campaign setup discussed earlier; large work, do once the number(s) are verified/available.
- Flip `claimant_autosend_enabled` ON when ready to auto-email claimants their L2 authorization link.
- ClaimShield live doc-pull test (once a real L2 case is ready).
- Counsel-vet the success-fee T&C (claimant consent card copy).
- Send staff announcements (drafts ready in `ANNOUNCEMENTS.md`).

### 🟡 In progress — In-house L2 model (NidaanPartner)
- **ClaimShield routing PAUSED ✅** (master switch `claimshield_routing_enabled=0`; Workflow Settings toggle). L2 claims stay in NidaanPartner. Resume anytime.
- **Contact capture for nudging:** new claims ✅ (claimant email+mobile mandatory). GAP: **48/58 existing claims lack `insured_email`**, **50/85 accounts lack phone** → ops must fill before email/WA doc-collection can reach them.
  - NEXT: "needs claimant contact" flag on L2 claims + gate doc-collection on a reachable claimant.
- **Email doc-collection path** (buildable now — SMTP live; WA path blocked on SIM): remind claimant of pending checklist docs by email with the portal upload link.
- "What processes after docs are collected" — founder to specify later.

### 🟡 In progress — Claimant WhatsApp doc-collection
- **Phase 0 ✅ shipped** (module + inbound flow + tables + webhook; inert until number configured).
- **Phase 1 — orchestrator (in progress):** guided one-doc-at-a-time on the checklist spine; Gemini **right-doc + quality gate** (reject wrong/old/blurry doc with a specific nudge); `normalize_to_pdf`+`segment` → name `NP-{claim}_{doc_key}.pdf` → `mark_doc_received(via='whatsapp')`; conversational layer (Hinglish default, switchable). **Message composer ✅ built** (`biz_nidaan_wa_messages.py` — bilingual welcome/claim-registered/thank-you/doc-reminder/received/wrong-doc/quality/complete; pure + tested). Remaining: wire composer + checklist "next-doc" logic + Gemini vision gate + reminder loop into the live number.
- **Message triggers (founder Aug 27):** (a) first time a valid active phone enters the system → **welcome** message (treat as lead); (b) on payment → **thank-you** + trust-restore; (c) on claim register → **update** to claimant + subscriber + branch + staff with the **registration number**; (d) all other status/reminder notifications.
- **Activity log ON the claim:** record every automation message/reminder sent + every customer response (+ status/notification events) as a claim timeline — "feels like a human is managing it." (Foundation building now.)
- **Phase 2:** reminder engine (daily, quiet hours, stop-on-complete) + escalation ladder (→ subscriber + staff after N days) + subscriber FYI digest.
- **Human handoff:** "take over this chat" in ops, with notifications on email + web + Telegram.
- **Superadmin WhatsApp section:** ✅ shipped (skeleton) — new '💬 WhatsApp Automation' panel: connection status, opt-in/message stats, editable doc-collection defaults, recent-messages log. (Templates list + live orchestration wire in with Phase 1.)
- Bilingual **template approvals** (reminder / received-OK / quality-issue / all-complete).

### 🟢 Next / planned
- **AI Daily Ops Summary ✅ shipped** — 20:00 IST, Telegram (text + voice, per-language) to super-admins: who-did-what from audit log + tasks + claim status changes + payments + pendency flags; Gemini-summarized; silent on a truly empty day; master flag `daily_summary_enabled`. Tested. (Voice via TTS→ffmpeg OGG.)
- **CRM MODULE (marketing/sales) — ✅ Phase 1 SHIPPED.** 🎯 CRM panel: pipeline kanban (stages as columns) + counts + search + New-lead + lead drawer (editable stage/owner/next-action/follow-up + comments + Mark Won). `nidaan_crm_leads`/`nidaan_crm_activity`; owner-assignment notifies bell+email+Telegram; team_member sees own, admin all.
  - **Phase 2 (AI Team-Lead "bot role"):** daily per-owner "today's follow-ups + overdue + next best action" digest; comment-aware **next-response suggestion** in the staffer's language as a **voice note on Telegram + web dashboard**; configurable stages; manual+automation follow-up cadence; stage-change notifications; convert→link account. So no lead or follow-up is ever missed. Reuse the Tasks module wholesale (assignment, comments, @mentions, approval, bell+Telegram+email notifications) + add CRM entities: **Leads** with a **pipeline of stages as sub-modules** (New → Contacted → Interested → Demo → Negotiation → Won/Lost), owner, next-follow-up date + action, source, and a per-lead timeline. **Voice-first** — create a lead, log a follow-up, set the next action, move a stage, all by **voice note** (extend the Telegram voice→Gemini pipeline + web). **Top-notch notifications at every step** (Telegram + email) to involved staff. **Bot role:** a daily + real-time assistant that tells each staffer their new leads, today's follow-ups, overdue items, and the next best action — visibility at every step, every day, flexible. Dashboard: pipeline/kanban, per-owner, conversion funnel, overdue follow-ups. Link a won lead → their `nidaan_account`. *Design discussion open — founder to refine stages, roles, and scope.*
- Deliverability upgrade: move Nidaan email to a `@nidaanpartner.com` sender (Resend/Brevo, DKIM-aligned) so it doesn't land in spam.
- Decide whether to remove +91-98272 84804 from the **About page** + **dashboard "Nidaan Cases" copy-number** too (removed from home page ✅).

### ✅ Recently shipped (this session)
Unified payment ledger + reconciliation · governance/mark-paid audit · super-admin re-attribution tool · already-subscribed guide · Phase 2 (claimant email+mobile mandatory, verified via magic-link) · Phase 3 (ClaimShield gated on acceptance, manual override) · branch-claim all-channel alerts (verified) · Tasks-panel crash fix · claim archive (+ Archived view/restore) · **business-critical subscription-vs-review link fix** · WA doc-collection Phase 0 · **SMTP configured (email live)**.

---

## 🟩 SARATHI-AI.COM

### 🟢 Next / planned
- **WhatsApp premium add-on — MULTI-TENANT (Embedded Signup) design.** Each subscriber connects THEIR OWN number to THEIR OWN WABA; our platform is a Meta **Tech Provider** using **Embedded Signup** (few-click onboarding), routing inbound by `phone_number_id` to the right tenant. Prereqs: Meta Business verification + Tech Provider/Solution Partner setup. Per-tenant: templates + automation flow + billing (Nidaan-bundle users pay a recurring WA plan; Sarathi-only pay WA plan + Meta charges). GoLuQ number can be the pilot tenant. Caution: a number on Cloud API is a one-way-door off the consumer app — subscribers should dedicate a business number. Separate from the NidaanPartner claimant WA and from goluq.com consultancy (which keeps its own WABA). Full detail inside the Sarathi dashboard WhatsApp window.
- Sarathi homepage: add **premium, non-bundled** features (not in the NidaanPartner bundle).
- Wire the 6 approved WA templates (renewal/EMI/lapse reminders) → send-log + opt-in + manual test-send UI + data-driven sends.

### 🟡 In progress
- **TGCRM** (Telegram Voice CRM for subscribers): P0 secure backend built + staged; next phases (per-firm bot, roles, onboarding/deboarding).

### 🔴 Blocked / awaiting owner
- Sarathi WhatsApp pilot number: GoLuQ +91 83495 04400 (a team account testing it).

---

## ⚙️ SHARED / INFRA
- ✅ **SMTP live** (Gmail app-password via `nidaanpartner@gmail.com`; secured in `biz.env`).
- Staging env (port 8003, `staging` branch): awaiting DNS + TLS.
- Off-server encrypted backups: live.
