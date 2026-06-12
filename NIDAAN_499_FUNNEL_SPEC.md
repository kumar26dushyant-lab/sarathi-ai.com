# Nidaan ₹499 Claim-Review Funnel — "Value-First, Pay-to-Unlock" Redesign

> Status: **DECISIONS LOCKED 2026-06-12** (see §6). Ready to build in the §7
> sequence — checklist engine first. Specced end-to-end (all pipes) before code,
> per the first-pass-yield rule.

---

## 1. The shift (what changes)

**Current flow:** Pay ₹499 first → then submit claim + documents → review.
**New flow:** Free signup → submit claim + documents free → **pay ₹499 to unlock the
review**. The user does the work first; we ask for money at the moment of payoff
(the "Canva / photo-app" pattern — you build it, you pay to download it).

**Why:** more leads (effort already invested = higher intent + higher conversion),
and a captured lead record even if they don't pay.

---

## 2. End-to-end journey (the happy path)

1. **Discovery → Free signup.** Hero/CTA → signup page that shows an easy
   **1-2-3 steps** explainer: *"3 steps, ~2 minutes of your time. Then sit back —
   NidaanPartner.com does the rest for your unsettled / underpaid claim."*
   No payment. Account + free dashboard created.
2. **WhatsApp kicks in.** Standard onboarding flow (welcome + save-number +
   language pick + — if advisor-managed — consent). [Phase 2 of WA journey.]
3. **Claim details + document collection.** Required documents are requested on
   BOTH the dashboard AND via WhatsApp. The customer can upload through either
   channel.
4. **Cross-channel de-dup (critical).** Before EVERY "please upload X" nudge
   (dashboard banner or WhatsApp message), the system checks whether that
   document is already received (from either channel). Already have it → never
   ask again. This needs a per-claim **required-document checklist** with a
   received/▢ state per item.
5. **All required docs in → Pay gate appears.** A prominent button:
   **"Pay ₹499 & unlock your review report"** with a curiosity/hope hook:
   *"Your claim may qualify for a fight — you could recover your full claim amount.
   Unlock the expert review to find out."*
6. **Payment.** ₹499 via Razorpay (UPI/cards/netbanking).
7. **Post-payment.** Message: *"Payment received ✓ Your claim is now under expert
   review. Please check back within 48 hours — or our team will reach out to you
   directly."* (dashboard + WhatsApp, in the user's language).
8. **Ops fulfilment.** On payment, the lead becomes a **paid, prioritized** case;
   super-admin + admin get an assignment notification; a legal reviewer is
   assigned; the written review/report is delivered within the SLA.

---

## 3. Lead vs Paid — the ops-portal model

| Stage | Ops-portal status | Notify |
|---|---|---|
| Free signup, no claim yet | `lead_new` | — |
| Claim submitted, docs incomplete | `lead_collecting_docs` | — |
| All required docs in, awaiting payment | `lead_ready_unpaid` | (optional: sales nudge) |
| Paid ₹499 | `paid_under_review` → assign | **SA + admin: assign now** |
| Review delivered | `review_delivered` | customer |

- **Leads are visible in the ops portal from signup onward** (not just after
  payment) — so the team sees the pipeline and can nudge `lead_ready_unpaid`
  cases. Paid cases are visually prioritized (top, badge, sound/notification).
- Payment flips status + fires the assignment notification (reuse the existing
  `biz_nidaan_notifications.dispatch` + `on_claim_filed`/assignment events).

---

## 4. The required-document checklist (the engine of de-dup + the pay gate)

This is the new core data structure. Proposed:

```
nidaan_claim_doc_checklist(
  claim_id        INTEGER,
  doc_key         TEXT,      -- e.g. 'policy_copy','rejection_letter','hospital_bill','id_proof'
  label_en/hi/mr  TEXT,
  required        INTEGER,   -- 1 = required for the pay-gate
  received        INTEGER,   -- 0/1
  received_via    TEXT,      -- 'dashboard' | 'whatsapp'
  received_doc_id INTEGER,   -- FK to nidaan_documents
  PRIMARY KEY(claim_id, doc_key)
)
```

- The **required set depends on claim_type** (health vs motor vs life vs property…).
  We seed the checklist when a claim is created, from a per-type template.
- "All required docs in" = no row with `required=1 AND received=0`.
- De-dup nudges read this table; uploads (either channel) flip `received=1`.
- The pay-gate button appears only when the checklist is complete.

**Decision needed:** the per-claim-type required-document lists (see §6 Q1).

---

## 5. All the pipes (first-pass-yield wiring map)

Building this touches every layer — each must be wired + tested, not assumed:

| Layer | Work |
|---|---|
| **Signup (frontend)** | Free-signup page with 1-2-3 explainer; no payment step; creates account + free dashboard. |
| **Signup (backend)** | `nidaan_api_signup` already exists; ensure it works WITHOUT a plan/payment and creates a `lead_new` record. |
| **Claim intake** | Free claim submission (currently gated behind subscription/payment — must ungate for the lead stage). Seeds the doc checklist from the claim_type template. |
| **Documents** | Dashboard upload + WhatsApp upload both write to `nidaan_documents` AND flip the checklist. Existing `biz_nidaan_inbound._save_document` + dashboard upload endpoint — wire both to the checklist. |
| **De-dup engine** | A function `pending_required_docs(claim_id)` used by BOTH the dashboard banner and the WhatsApp nudge scheduler. Single source of truth. |
| **Pay gate** | Dashboard shows "Pay ₹499 & unlock" only when checklist complete. New/!reused Razorpay order tied to the claim. On verify → status `paid_under_review`. |
| **WhatsApp** | Standard message templates (en/hi/mr) for: doc requests (only for still-missing docs), all-docs-in + pay nudge, payment-received, under-review. Reuses Phase 2 flow + Phase 4 constrained AI. |
| **Ops portal** | Lead list with the new statuses; paid-case prioritization + SA/admin assignment notification; reviewer assignment; report delivery. |
| **Cybersecurity** | Free signup + free uploads = abuse surface. Need: signup rate limits (have), upload rate limits + size/type validation, per-account claim/upload caps, storage quota, and spam/garbage-doc guard. Auth/ownership checks on every doc + claim endpoint (IDOR). DPDP: consent + data-retention for unpaid leads (how long do we keep an unpaid lead's documents?). |
| **Tests** | Fixture-based: signup→claim→upload(dashboard)→upload(whatsapp dedup)→checklist-complete→pay→status-flip→assignment-notify. End-to-end, not per-layer-assumed. |

---

## 6. Decisions — LOCKED (2026-06-12)

1. **Required-document lists per claim type → see §8** (full templates with
   everyday-language names + trust explanations, provided by user).
2. **What "see the report" delivers → Option A**: payment unlocks the human
   review ("under review, 48 hrs"). BUT the funnel must build **psychological
   pull** so the user pictures the BIG outcome (their full claim recovered) and
   ₹499 feels trivial — see §9 (conversion framing).
3. **Replace or both → REPLACE.** One clean value-first funnel for the ₹499 path.
4. **Unpaid-lead lifecycle → keep, nudge logically, then DPDP-delete with a
   trust-building heads-up FIRST** (intimate before deletion; they may pay later)
   — see §9 (notification cadence) + §10 (retention).
5. **Advisors → separate.** Anyone choosing the **₹499 path uses this funnel**
   (advisor or insured). **Advisors who subscribe** use the standard
   **subscription funnel** (register multiple claims, monthly claim cap, feature
   gating per plan). Also: audit + tighten the per-plan claim caps + feature
   restrictions as part of this work.

---

## 8. Required-document checklist templates (the engine data)

Seeded into `nidaan_claim_doc_checklist` when a claim is created, by claim_type.
Names use everyday language; each has a short "why" to build trust. A signed
**"Document Receipt Checklist"** is generated so the user sees what's "in the bag"
vs "still missing" — and the dashboard + WhatsApp automation smart-chase only the
**missing** items (people submit in parts, so the chase must be incremental, with
fallback reminders).

> Trust line shown alongside every upload ask (en/hi/mr):
> *"🔒 Your documents are used only to fight your claim. We follow Government of
> India (DPDP Act 2023) data-protection rules — no leaks, no sharing, and your
> files are securely destroyed after your case is resolved."*

**1. Health / Medical (the "hospital case")** — prove treatment was necessary & covered
- `rejection_letter` — *The "No" letter*: the official rejection / partial-payment letter. *(Some insurers send by default, some only on request.)*
- `policy_document` — *The "rule book"*: your policy with terms — especially the Exclusions page.
- `discharge_summary` — *The hospital story*: the discharge summary (the single most important hospital paper).
- `itemized_bills` — *The money list*: original itemized bills (room rent, medicines, doctor fees shown separately).
- `prior_medical` *(conditional)* — *Proof of history*: if they allege a "pre-existing disease," old medical files / a doctor's certificate from before the policy.

**2. Life (the "death or maturity case")** — prove cause is covered & nothing was hidden
- `decision_letter` — *The "No" letter*: the insurer's decision letter.
- `policy_bond` — *The "rule book"*: the original policy bond.
- `death_certificate` — *The official record*: Municipal Corporation death certificate.
- `cause_of_death` — *The medical link*: hospital death summary / "cause of death" certificate.
- `proposal_form` — *The disclosure proof*: original proposal form + past medical history (proves truthful disclosure at purchase).

**3. Property / Fire (the "asset loss case")** — prove the loss happened & the amount is right
- `rejection_or_survey_letter` — *The "No" letter*: rejection / surveyor's assessment letter.
- `policy_schedule` — *The "rule book"*: schedule showing Sum Insured (building + contents).
- `incident_proof` — *The incident proof*: FIR (fire/theft) or Fire Brigade report.
- `damage_evidence` — *The damage evidence*: photos/videos taken right after, before cleanup.
- `purchase_bills` — *The purchase proof*: original bills/invoices for damaged items (proves value).
- `surveyor_report` — *The surveyor's report*: what the insurer's surveyor wrote after visiting (needed to contest underpayment).

**4. Marine / Transit (the "goods damage case")** — prove damage in transit
- `rejection_letter` — *The "No" letter*: rejection for damage/shortage.
- `marine_policy` — *The "rule book"*: Marine Policy / Open Cover certificate.
- `transit_papers` — *The paper trail*: Bill of Lading, Packing List, Invoices.
- `survey_report` — *The loss proof*: survey report (at port/destination).
- `delivery_protest` — *The delivery note*: protest/remark at delivery (e.g. damage noted on courier receipt).

**5. Travel (the "trip trouble case")** — prove the event happened as claimed
- `refusal_letter` — *The "No" letter*: refusal of the travel claim.
- `travel_certificate` — *The "rule book"*: the travel insurance certificate for the trip.
- `trip_proof` — *The trip proof*: flight tickets, boarding passes, passport (entry/exit stamps).
- `incident_proof` — *The incident proof*: airline delay certificate (delay) / Property Irregularity Report "PIR" (lost baggage) / original overseas medical bills (medical).

Engine notes:
- `conditional` items are required only if a trigger applies (e.g. pre-existing
  disease alleged); the ops/legal reviewer can toggle an item required/not.
- The checklist is the single source of truth: dashboard banner + WhatsApp chase
  + pay-gate all read `pending_required_docs(claim_id)`.

---

## 9. Conversion framing + notification logic (anti-spam, trust-first)

**Psychological pull (Option A done right):** throughout the funnel, anchor on the
BIG outcome, not the ₹499. Examples (en/hi/mr templates):
- After docs complete: *"Your claim looks strong enough to fight. People in cases
  like yours have recovered their FULL claim amount. Unlock your expert review for
  just ₹499 — a tiny step toward what's rightfully yours."*
- Make ₹499 feel trivial vs the claim value: show *"Disputed amount: ₹X,XX,XXX"*
  next to *"Review: ₹499"*.
- Urgency without pressure: *"Insurers count on people giving up. Don't leave your
  money on the table."*

**Payment-notification cadence (must NOT trigger spam reports):**
- Docs complete → **1** "unlock your review" message (dashboard + WhatsApp) with a
  one-tap payment link, and the report is delivered on WhatsApp after payment.
- If unpaid: **at most** a gentle reminder at **~24h** and **~48h** (2 nudges
  total), each with the quick-pay link. Then **stop** — no more payment nudges.
- Every nudge carries an easy opt-out ("Reply STOP"). Respect STOP immediately.
- All nudges are rate-capped by the existing WhatsApp caps + quiet hours.

**Quick-pay link:** a tokenized, expiring deep link to the Razorpay checkout for
that claim, so payment is one tap from WhatsApp; report auto-delivered on success.

---

## 10. DPDP retention + trust (unpaid leads)

- Keep an unpaid lead's data while it's "live." If no payment after the nudge
  window + a grace period, send a **heads-up**: *"We'll securely delete the
  documents you shared for your claim in N days as per data-protection rules. If
  you'd still like us to review it, you can unlock anytime here: <link>."*
- After the grace period with no action → **securely delete uploaded documents**
  (DPDP), keep only minimal lead metadata (or fully anonymize) per policy.
- This heads-up both honours DPDP and is a final, trust-building re-engagement.

---

## 11. Advisor subscription funnel (separate track — audit + tighten)

Advisors who subscribe (not ₹499) keep the subscription model. As part of this
work, **audit and tighten**:
- Per-plan **monthly claim caps** (Silver/Gold/Platinum) — enforce server-side.
- Per-plan **feature gating** (which features each tier unlocks).
- Confirm caps can't be bypassed (server-side check on every claim create), and
  surface remaining quota in the advisor dashboard.

---

## 7. Proposed build sequence (after §6 is answered)

1. Doc-checklist schema + per-type templates + `pending_required_docs()` engine
   (+ unit tests) — the spine.
2. Ungate free claim intake + seed checklist on claim create.
3. Dashboard: free-signup 1-2-3 page, doc-upload wired to checklist, pay-gate
   button on completion.
4. WhatsApp: doc-request / pay-nudge / payment-received templates wired to the
   same `pending_required_docs()` engine (de-dup guaranteed by single source).
5. Payment → status flip → ops prioritization + SA/admin assignment notify.
6. Ops portal: lead pipeline + paid prioritization.
7. Security pass: upload validation, caps, IDOR re-check, DPDP retention.
8. Full end-to-end fixture test before go-live.

This sequence builds the **spine (checklist engine) first**, so the dashboard and
WhatsApp both hang off one source of truth — which is what makes the cross-channel
de-dup correct by construction rather than by luck.
