# Nidaan ₹499 Claim-Review Funnel — "Value-First, Pay-to-Unlock" Redesign

> Status: DISCUSSION (proposed 2026-06-12). Do NOT build until decisions in §6
> are confirmed. This reshapes signup, dashboard, documents, payment, WhatsApp,
> and the ops portal — so it is specced end-to-end (all pipes) before any code,
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

## 6. Decisions needed before build (these determine correctness)

1. **Required-document lists per claim type.** What documents are *required* to
   complete a review for: health, motor, life, property, travel, other? (Give me
   the lists, or approve a sensible default and we refine.) This is the engine of
   both the de-dup and the pay-gate.

2. **What does "see the review report" deliver?** Two options:
   - (a) **Payment unlocks the human review process** (no instant report). The
     curiosity line is marketing; after paying they see "under review, 48 hrs."
     *(This matches your description and is simplest + honest.)*
   - (b) Payment also reveals an **instant auto-generated preliminary assessment**
     (rules/AI) as the "report," with the human review following.
   Which one? (I recommend (a) for launch — no risk of an AI saying something
   wrong about a legal claim; (b) can come later as a teaser.)

3. **Replace or run both?** Do we **replace** the current pay-first flow entirely
   with this value-first funnel, or keep pay-first available too? (I recommend
   replace — one clean funnel.)

4. **Unpaid-lead lifecycle.** If they complete docs but don't pay within 48 hrs:
   what happens? Nudge cadence (e.g., WhatsApp reminder at 24h, 48h)? After how
   long do we archive the lead and (per DPDP) delete uploaded documents?

5. **Advisors in this funnel.** Does the same free-first funnel apply when an
   **advisor** submits on a client's behalf, or do advisors stay on the
   subscription model? (Likely: retail insured = this funnel; advisors =
   subscription. Confirm.)

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
