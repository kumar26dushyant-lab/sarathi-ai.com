# DPDP gap assessment — NidaanPartner.com

**Written for:** the founder, and whoever he asks to review this legally.
**Date:** 26 September 2026 · **Assessed against:** Digital Personal Data Protection Act, 2023.
**Status:** findings only. Nothing in this document has been changed in the product yet.

This is written to be uncomfortable where it should be. Every line is something checked in the
running system, not something the code says about itself. Where something is unknown, it says so
rather than guessing — a compliance document that flatters us is worse than none, because it is
the thing we would hand a regulator.

---

## What we actually hold

Counted on the live database, 26 Sep 2026.

| Data | Rows | Oldest still held |
|---|---|---|
| Claim **documents** — discharge summaries, bills, reports | **931** | 13 Jun 2026 |
| Claims (name, phone, policy, disputed amount, medical detail) | 197 | 8 Jul 2026 |
| Claimant portal links | 103 | — |
| Subscriber accounts | 138 | — |
| WhatsApp message history | 574 | 3 Sep 2026 |
| Notifications (carry names, amounts, claim detail) | **27,050** | 13 Jun 2026 |
| Staff | 34 | — |

Under DPDP we are a **Data Fiduciary**. Claim documents are health data about people who are
mostly **not our customers** — they are the insured person on a claim a branch or subscriber
brought to us. They never signed up with us, and that is the population with the fewest routes
to us and the most sensitive data in the system.

---

## Findings

### 🔴 1. nidaanpartner.com publishes the wrong company's privacy policy — live right now

```
https://nidaanpartner.com/privacy → "Privacy Policy — Sarathi-AI Business Technologies"
https://nidaanpartner.com/terms   → "Terms of Service — Sarathi-AI Business Technologies"
```

A person on a legal-services site, about to hand over their medical records, is told a
**different company** decides what happens to their data. The correct pages exist at
`/nidaan/privacy` and `/nidaan/terms`, but the bare `/privacy` and `/terms` routes carry no host
check, so they answer on both domains and win for anyone who types the obvious address or follows
a generic link.

**This is the single worst item here** and it is a ten-line fix.

### ✅ 2. The published policy names an entity that may not be ours — SETTLED

> **1 Oct 2026:** the founder confirmed the registered name is **"Nidaan The Legal Consultants
> LLP"**, which is what the legal pages, the logo and the authorization letter now say. The LLPIN is
> still not recorded anywhere. The original note follows.

The live page says **"Nidaan – The Legal Consultants LLP"**. The founder states the legal entity
is **"Nidaan Legal India LLP"**.

Those are different names. A privacy policy that names the wrong Data Fiduciary is not a
technicality — it is the identity of the party accepting the legal obligation.

**❓ This is the one thing I will not guess.** The exact registered name and LLPIN, as on the
incorporation certificate, is needed before anything is published.

### 🔴 3. Nothing is ever deleted

There is no retention period, no purge job, and no expiry on any personal data. The oldest
medical document we hold is from **13 June 2026** and it will still be there in ten years.

DPDP requires erasure once the purpose is served. For a claim that settled or was withdrawn,
the purpose is served.

There is no legally correct number I can invent here. The honest position: **legal-services
records generally need multi-year retention** for limitation and professional-conduct reasons,
which is a real and defensible basis — but "we never thought about it" is not that basis, and
27,050 notification rows carrying names and amounts are certainly not covered by it.

### 🟠 4. Claim documents are sent to Google for AI analysis, and nobody is told

`biz_doc_splitter` and `biz_nidaan_doc_intake` send document contents to
`generativelanguage.googleapis.com` (Gemini) to work out what each document is and whether it is
legible. That is **health data leaving India to a US processor**.

This is a legitimate processing purpose and the feature is genuinely useful. The problems are
that it is **not disclosed to anyone**, and there is no processor agreement on record.

### 🟠 5. Only half the claimant consents are recorded

`nidaan_claimant_portal` has a well-built consent trail — timestamp, terms version, IP, user
agent, a hash and a snapshot of the exact wording shown. That is better than most.

**56 of 103** portal links carry a consent record. The other 47 do not.

*Unverified:* whether those 47 are links that were simply never opened, or claimants whose
documents we hold without a recorded consent. **This needs checking before it is written down
anywhere** — the answer changes whether this is a non-issue or the most serious item on the list.

### 🟠 6. Subscribers can erase themselves. Claimants cannot reach us at all

Right-to-erasure is genuinely implemented for account holders: self-service from the dashboard,
soft-delete with a 7-day undo, a sweep that purges claims, documents and PII and keeps an
anonymised billing shell. Tested. Good.

But a **claimant** — the person whose medical records those actually are — has no account, no
login, and no route to ask for access, correction or erasure. DPDP gives them all three.

### 🟠 7. No breach notification path exists

DPDP requires notifying the Data Protection Board **and** every affected person. There is no
defined procedure, no template, no decision-maker named, and no rehearsal. The one thing you
cannot improvise is the thing you have to do within a deadline.

### 🟡 8. No cookie policy, and no named Grievance Officer

The page mentions grievances and gives `info@nidaanpartner.com`. DPDP expects a **named person**
with contact details. A shared inbox is not a person.

No cookie policy exists at all.

### 🟡 9. Processors are not named

Personal data reaches: **Razorpay** (payments), **Google** (Gemini, OAuth sign-in), **Telegram**
(staff notifications and now claim documents), **Meta/WhatsApp** (claimant messaging),
**Fast2SMS**, and our hosting in **Oracle Mumbai**. DPDP expects these to be disclosed.

---

## What is already right

Worth saying, because it is unusual:

- **The consent trail that exists is well designed** — snapshotting the exact terms text shown,
  with IP, user agent and a hash, is stronger than most Indian SaaS.
- **Right-to-erasure is real code with a real test**, not a paragraph in a policy.
- **Claim documents sit behind signed URLs**, not guessable paths.
- **Payment credentials are encrypted at rest**; the bot token leak found on 26 Sep was closed
  the same day and was never reachable from outside a staff login.
- **Every sensitive ops action is audit-logged** with actor, target and IP.

---

## Recommended order

Cheapest and most exposed first. This is a recommendation, not a decision.

| # | Action | Effort |
|---|---|---|
| 1 | Host-gate `/privacy` and `/terms` so nidaanpartner.com serves its own | minutes |
| 2 | Confirm the registered entity name + LLPIN, correct every page | founder |
| 3 | Check what those 47 consent-less portal links actually are | hours |
| 4 | Name a Grievance Officer with a real contact | founder |
| 5 | Write Privacy / Terms / Cookie / Refund to match **what we actually do**, naming every processor and the Gemini transfer | days |
| 6 | Agree a retention schedule per data type, then build the purge to enforce it | days |
| 7 | A claimant-facing route to request access / correction / erasure | days |
| 8 | A written breach procedure, with a named decision-maker | hours |

**Order matters:** the pages (5) must come *after* the retention decision (6) is made, or we
publish a promise we do not keep — which is worse than publishing nothing, because it is then a
statement we can be held to.
