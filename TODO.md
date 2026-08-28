# SARATHI BUSINESS — LIVING TO-DO

_Auto-maintained by Claude **every conversation**, alongside `PROJECT_MASTER_CONTEXT.md`._
_**Two-terminal workflow:** work 🟦 NidaanPartner items in one VS Code terminal, 🟩 Sarathi items in another. Each app's section is self-contained so both can progress simultaneously without collision._
_Legend: 🔴 blocked/awaiting owner · 🟡 in progress · 🟢 next/planned · ✅ done_

**Last updated:** 2026-08-28 (superadmin WhatsApp section + registry backfill shipped; homepage number removed; email live)

---

## 🟦 NIDAANPARTNER.COM

### 🔴 Blocked / awaiting owner
- **WhatsApp number `9183686384` — Meta verification (needs SIM, ~Aug 29).** Then: create/verify the WABA, set display name "NidaanPartner", grab Phone Number ID + WABA ID + System User token + App Secret + choose Verify Token → add to `biz.env` (`WA_NIDAAN_ACCESS_TOKEN`/`PHONE_NUMBER_ID`/`WABA_ID`/`APP_SECRET`/`VERIFY_TOKEN`) → point Meta webhook to `https://nidaanpartner.com/nidaan/api/wa/webhook` + subscribe to `messages`. **Claude will guide click-by-click.**
- **NidaanPartner.com WhatsApp Business CAMPAIGN alignment** — the big campaign setup discussed earlier; large work, do once the number(s) are verified/available.
- Flip `claimant_autosend_enabled` ON when ready to auto-email claimants their L2 authorization link.
- ClaimShield live doc-pull test (once a real L2 case is ready).
- Counsel-vet the success-fee T&C (claimant consent card copy).
- Send staff announcements (drafts ready in `ANNOUNCEMENTS.md`).

### 🟡 In progress — Claimant WhatsApp doc-collection
- **Phase 0 ✅ shipped** (module + inbound flow + tables + webhook; inert until number configured).
- **Phase 1 — orchestrator (NEXT BUILD):** guided one-doc-at-a-time on the checklist spine; Gemini **right-doc + quality gate** (reject wrong/old/blurry doc with a specific nudge); `normalize_to_pdf`+`segment` → name `NP-{claim}_{doc_key}.pdf` → `mark_doc_received(via='whatsapp')`; conversational layer (Hinglish default, switchable).
- **Message triggers (founder Aug 27):** (a) first time a valid active phone enters the system → **welcome** message (treat as lead); (b) on payment → **thank-you** + trust-restore; (c) on claim register → **update** to claimant + subscriber + branch + staff with the **registration number**; (d) all other status/reminder notifications.
- **Activity log ON the claim:** record every automation message/reminder sent + every customer response (+ status/notification events) as a claim timeline — "feels like a human is managing it." (Foundation building now.)
- **Phase 2:** reminder engine (daily, quiet hours, stop-on-complete) + escalation ladder (→ subscriber + staff after N days) + subscriber FYI digest.
- **Human handoff:** "take over this chat" in ops, with notifications on email + web + Telegram.
- **Superadmin WhatsApp section:** ✅ shipped (skeleton) — new '💬 WhatsApp Automation' panel: connection status, opt-in/message stats, editable doc-collection defaults, recent-messages log. (Templates list + live orchestration wire in with Phase 1.)
- Bilingual **template approvals** (reminder / received-OK / quality-issue / all-complete).

### 🟢 Next / planned
- Deliverability upgrade: move Nidaan email to a `@nidaanpartner.com` sender (Resend/Brevo, DKIM-aligned) so it doesn't land in spam.
- Decide whether to remove +91-98272 84804 from the **About page** + **dashboard "Nidaan Cases" copy-number** too (removed from home page ✅).

### ✅ Recently shipped (this session)
Unified payment ledger + reconciliation · governance/mark-paid audit · super-admin re-attribution tool · already-subscribed guide · Phase 2 (claimant email+mobile mandatory, verified via magic-link) · Phase 3 (ClaimShield gated on acceptance, manual override) · branch-claim all-channel alerts (verified) · Tasks-panel crash fix · claim archive (+ Archived view/restore) · **business-critical subscription-vs-review link fix** · WA doc-collection Phase 0 · **SMTP configured (email live)**.

---

## 🟩 SARATHI-AI.COM

### 🟢 Next / planned
- **WhatsApp premium add-on** (subscriber's OWN number → their customers) — separate from the NidaanPartner claimant WA. Plans/pricing TBD after testing; Nidaan-bundle users pay a recurring WA plan, Sarathi-only users pay WA plan + Meta charges; full detail inside the Sarathi dashboard WhatsApp window.
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
