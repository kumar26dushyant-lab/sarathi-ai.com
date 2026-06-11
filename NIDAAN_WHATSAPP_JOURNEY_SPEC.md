# Nidaan WhatsApp Journey — Design Spec

> Status: APPROVED (decisions locked with user 2026-06-11). Build in phases.
> Principle: **template-first, never message the wrong person, never hallucinate
> claim facts.** WhatsApp is the primary channel because users won't open the
> dashboard.

---

## 1. Customer segments & journey types

| # | Who | Journey type | Account holder | Who provides docs |
|---|-----|-------------|----------------|-------------------|
| 1 | Insured, no advisor (online buyer) | **Self-service** | The insured | The insured |
| 2 | Insured whose advisor is unresponsive | **Self-service** | The insured | The insured |
| 3 | Advisor subscribes on behalf of a client | **Advisor-managed** | The advisor | The customer (insured) |

Segments 1 & 2 are identical mechanically (insured = account holder).
Segment 3 is the **two-party** case: advisor (account holder) + customer (insured).

---

## 2. Identity model (the wrong-person-safety foundation)

**Data we already have:**
- `nidaan_accounts.phone` = account-holder phone (= advisor in advisor-managed,
  = insured in self-service)
- `nidaan_claims.insured_phone` = the customer's phone (always the insured)

**Inbound identity resolution (NEW — currently only matches account.phone):**
For an inbound WhatsApp from phone `P`, resolve in this order:
1. `account.phone == P` → role = **ACCOUNT_HOLDER** (advisor or self-service insured)
2. else `claim.insured_phone == P` for some active claim → role = **CUSTOMER**,
   bound to that claim's account
3. else → **UNKNOWN** → polite "please register" reply (already exists)

The resolver returns `(account_id, role, matched_claim_ids[])`. Role + claim
binding is **explicit**, never inferred from message content.

**Outbound safety invariant (unchanged, already enforced):**
Every outbound message is addressed to an explicit
`(claim_id, recipient_role, phone)` tuple read from the DB. The dispatcher
never infers a recipient.

**Recipient roles (extend the existing enum):**
- `RECIPIENT_SUBSCRIBER` (exists) — the account holder
- `RECIPIENT_STAFF` (exists) — Nidaan ops team
- `RECIPIENT_CUSTOMER` (NEW) — the insured when ≠ account holder (advisor-managed)

---

## 3. Bifurcation matrix (advisor-managed claims) — APPROVED

| Message type | Customer | Advisor | Notes |
|---|---|---|---|
| Claim status update | ✅ | ✅ | Customer = reassurance, advisor = oversight |
| "We need document X" nudge | ✅ (primary) | ✅ (CC) | Customer holds the docs |
| Billing / payment / renewal | ❌ | ✅ | Advisor pays |
| Support reply | → whoever asked | → whoever asked | Reply goes to the inbound sender |

For **self-service**, customer == advisor == account holder, so all of the above
collapse to one recipient. No special-casing needed — same code path.

Future option (not now): per-advisor "I am sole point of contact" toggle that
suppresses direct-to-customer messages. Schema-ready via subscriber_prefs.

---

## 4. Consent flow (DPDP) — APPROVED

- `nidaan_subscriber_prefs.wa_opt_in` already exists (0/1 + timestamp).
- **Self-service:** the insured signs up themselves → opt-in captured at signup
  (checkbox / first-message YES).
- **Advisor-managed:** the customer did NOT opt in themselves. The **first**
  outbound to a customer is an **opt-in prompt**:
  > "Namaste 🙏 Nidaan – The Legal Consultants is handling your insurance claim
  >  on behalf of [advisor/firm]. Reply YES to receive updates here. Reply STOP
  >  to opt out."
  No further messages until they reply YES. STOP sets opt-out.
- Opt-in state is per-**phone** (so a customer under multiple advisors isn't
  re-prompted needlessly — keyed by phone, not just account).

---

## 5. Welcome + save-number flow (anti-ban / anti-spam-report) — APPROVED

WhatsApp bans numbers that get reported as spam. To prevent this:

1. **On signup (any segment):** show a dashboard popup:
   > "You may receive WhatsApp updates from one of our official Nidaan numbers.
   >  Please save it so messages arrive trusted. You can always find our official
   >  numbers in your dashboard under Support."
2. **First WhatsApp message = a warm, branded welcome** that asks them to save
   the contact (with the official display name) BEFORE any transactional nudges.
   Tracked by `saved_official_numbers_at` (column exists).
3. **Official numbers shown in dashboard** under a "Customer Support / Our
   Official Numbers" card — so users can verify any number that messages them is
   genuinely Nidaan (anti-impersonation + builds trust).
4. Rate caps + warmup + quiet-hours already protect the numbers
   (`nidaan_official_instances` + `compute_effective_caps`).

---

## 6. Language model (en / hi / mr) — APPROVED

- NEW column `nidaan_subscriber_prefs.comm_lang TEXT DEFAULT 'en'` (en|hi|mr).
- Optionally per-claim override `nidaan_claims.comm_lang` for advisor-managed
  (the customer may prefer a different language than the advisor) — Phase 1
  adds the account-level pref; per-claim is a Phase 3 refinement.
- **Language selection:** asked once — at signup (dropdown) AND offered in the
  welcome WhatsApp message ("Reply 1 English / 2 हिंदी / 3 मराठी").
- ALL templates authored in en/hi/mr. AI responses (Phase 4) generated in the
  user's `comm_lang`.

---

## 7. Anti-hallucination rules (legal/claims context) — APPROVED

**Template-first.** Free-form AI is allowed ONLY to:
1. **Classify intent** of an inbound free-text message (e.g. "where is my claim",
   "I want to add a document", "talk to a human", "change language").
2. **Route / escalate** — map intent to a template reply or to a human handoff
   ("I'll have our team reply to you shortly").

**AI must NEVER, in generated prose:**
- State claim status, stage, or timeline (only templates filled from DB do this)
- Give legal opinion or predict claim outcome
- State what documents are required (templates from the case checklist only)
- Quote amounts, dates, or policy specifics

If intent is unclear or off-script → escalate to human, never improvise.
Every AI-classified action is logged with the inbound text + chosen intent for
audit.

---

## 8. Evolution API fallback (already built — verify in Phase 5)

- `dispatch()` tries WhatsApp via the account's pinned slot; on failure falls
  back to **email** (`_send_wa` → `_send_email`).
- `nidaan_official_instances` tracks per-number health; unhealthy/paused numbers
  are skipped; `_list_healthy_instances` + `compute_effective_caps` pick a live one.
- `retry_deferred_notifications()` re-attempts deferred sends (Evolution down).
- Quiet-hours suppression + daily caps prevent bans.
- **Gap to verify:** behavior when ALL instances are down (should defer + email,
  not drop). Test in Phase 5.

---

## 9. Gap analysis — what's built vs new

| Capability | Status |
|---|---|
| 3 official numbers + slot pinning | ✅ Built |
| Inbound identity by account phone | ✅ Built |
| Two-party inbound (match insured_phone, tag role) | ❌ **NEW (Phase 1)** |
| Document ingestion + multi-claim disambiguation | ✅ Built |
| WhatsApp→email fallback + retry queue | ✅ Built |
| Quiet hours + rate caps + warmup | ✅ Built |
| Consent column (wa_opt_in) | ✅ Built |
| Consent opt-in PROMPT flow for advisor-managed customers | ❌ **NEW (Phase 2)** |
| Welcome / save-number message + dashboard popup | ❌ **NEW (Phase 2)** |
| Official-numbers dashboard card (support) | ❌ **NEW (Phase 2)** |
| Language preference (en/hi/mr) | ❌ **NEW (Phase 1+2)** |
| Bifurcation: customer vs advisor recipients | ❌ **NEW (Phase 3)** |
| Constrained AI intent-classify + escalate | ❌ **NEW (Phase 4)** |
| Template library in en/hi/mr | ❌ **NEW (Phases 2-4)** |
| Inbound bot generates NO free prose (anti-hallucination) | ✅ Built (preserve) |

---

## 10. Build phases (each = one deploy + smoke test, bug-free discipline)

- **Phase 1 — Foundation:** `comm_lang` column; two-party identity resolver
  returning `(account_id, role, claim_ids)`; unit-test the resolver against
  self-service + advisor-managed fixtures. No behavior change to outbound yet.
- **Phase 2 — Onboarding:** welcome + save-number + consent opt-in + language
  select; dashboard popup + official-numbers support card. Templates en/hi/mr.
- **Phase 3 — Bifurcation:** extend dispatch with `RECIPIENT_CUSTOMER`; wire the
  matrix into each event (status update → both; doc nudge → customer+CC advisor;
  billing → advisor; support → sender).
- **Phase 4 — Constrained AI:** intent classifier + escalation, en/hi/mr,
  guard-railed to never emit claim facts. Audit log.
- **Phase 5 — Go live:** configure the 3 official Evolution numbers, warmup,
  end-to-end self-service + advisor-managed live test, all-instances-down
  fallback test.

---

## 11. Hero (Ask A) — separate frontend track

₹499 B2C insured is the revenue engine → hero leads with the insured. Messaging:
trusted, hopeful, positive, problem-solver. A distinct "For Insurance Advisors &
Consultants" band follows, with the positive framing: advisors who use expert
claim-handling (Nidaan) see higher revenue / upsell / cross-sell, more referrals,
and deliver excellent extended customer service alongside sales. Independent of
the WhatsApp track; can ship anytime.
