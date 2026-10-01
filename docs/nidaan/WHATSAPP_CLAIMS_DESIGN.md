# Taking claims on WhatsApp — design for discussion

_Draft 3 · 30 Sep 2026 · nothing here is built yet. The page version (flows + fallbacks) is at
https://claude.ai/artifact/AvFK6bxXWtmRGPr8XH9FQC._

## Draft 3 — founder's decisions and findings, 30 Sep 2026

**Decided:** OTP from the registered number once per 30-day session (any other number: every
time). All other recommendations accepted: insurer top-12 list, CP owned by the staff member who
registered them (backup: on-duty intake), a small local model allowed for message sorting.

**Never mention plan or quota usage.** No "Silver plan, 1 of 3 claims used". The bot greets and
asks what they need; limits are checked silently at the end with the same server rules as the
website, and if one is hit the bot offers upgrade / Rs 499 + GST single review / "our team will
call you" — without counting anything.

**Same intake as the website.** Every door writes through `submit_claim`, but the six web doors
check different things around it (review of 30 Sep):

| Door | Complainant mobile/email checked | Checklist made | Rejection letter ticked | Who is told |
|---|---|---|---|---|
| Subscriber dashboard | insured only | yes | no (untyped upload) | staff + admin email |
| Start page (lead) | same route | yes | yes | lead alert |
| AP portal | yes | no | no | staff |
| Staff for a subscriber | **none** | only with a typed upload | yes | staff; **subscriber not told** |
| Staff My Business | yes | no | no | staff |
| Rs 499 review | purchaser email by code | no | — | only on the page-verify path |

Plan: one `intake` module (checks + the "after" step: checklist, timeline, event, notifications)
called by every door; WhatsApp is the seventh door on the same two calls. Fix first: Rs 499
review documents stay on the purchase and never reach the claim; Rs 499 payments confirmed by
webhook/recovery do not write the ledger (verify against live first); the raw
`quota_exceeded_<plan>` code shown to subscribers; the plan's amount cap is page-only.

**Documents:** complainant page should show every file on their claim (today only files uploaded
on that page — WhatsApp files are missing); staff document access should follow the per-claim
rule; referrers see received/missing, not files (proposed).

**People who have left (done 30 Sep):** subscriber and AP tokens re-checked per request
(`biz_nidaan_access`, fails closed); staff check fails closed; inactive staff get no Telegram or
push; WhatsApp does not recognise suspended accounts or disabled APs; Cancel stops the Razorpay
autopay (it did not — the next charge re-activated the plan), so does ops' erase. **Proposed:**
plan ended + 3-day grace → dashboard shows only welcome-back/renew; registered claims keep being
worked for the complainant; past subscribers on WhatsApp get a warm welcome and a renew link,
nothing private; former staff are first-time visitors. **Open:** staff logins never expire
(recommend a "logins before this moment are void" stamp); archived claims' portal links; 48 h
signed document links; legacy shared admin key.

**Follow-up restart (proposed):** automatic reminders are off globally on live; after two
reminders a claim is handed to staff and cannot be restarted. Buttons: *Start reminders again*
(fresh cycle on this claim, even with the global switch off), *I'll follow up myself* (no
automatic messages; the staffer is reminded on Telegram on a date they pick), *Book the
customer's time* (built).

**"Your day" (for agreement, not built):** one Telegram message ~9:30 IST, at most 5 items —
overdue tasks, claims not moved for 5+ days, new documents to check, a customer waiting 4+ working
hours, calls due, unconfirmed contacts (folded in), dates within 3 days; nothing on a quiet day or
on leave; super-admins get the team view. Each item: Done / Later today / Not my focus → someone
else (suggested reassignment, nothing moves on its own) / waiting on customer (aside until reply
or 3 days) / already done (listed weekly as a recording gap) / other (aside 3 days, reason on the
timeline). Rules only, no AI.

## Founder's decisions, 29 Sep 2026

1. **Verification: WhatsApp OTP** to the registered WhatsApp number (approved template
   `np_login_code`). Note: from the registered number itself it is a deliberate confirmation;
   from any other number it is mandatory. 3 wrong codes -> 30-min lock + super-admins told.
2. **Minimum to register:** insured/patient name, complainant mobile (who talks to us), claim
   type, insurer (pick from a numbered list), what happened, other required details, and the
   **rejection letter**. Everything else is a named pending item.
3. **Quota / cap exceeded:** offer upgrade or Rs 499 + GST single review in conversation; no
   interest -> "talk to us" and the team is notified.
4. **CP:** staff take responsibility. The bot drafts; the responsible staff member is told on
   Telegram; their replies (Telegram or dashboard) go to the CP over the official WhatsApp.
5. **Staff:** Telegram bot, web dashboard, mobile web app - never WhatsApp.
6. **Nudges:** two automatic, then a staff task.
7. **AI:** review the whole bot; intake uses no AI; rules first, a small local model next, an
   outside model only for wording with placeholders - never real PII or documents.


Founder, 29 Sep: *"can we start taking claims on whatsapp from paid subscribers? guiding them step
by step … identify the right person raising claims for whom … if it's subscriber we can take claims
as per their subscription, if it's AP then there is a different flow, if it's a staff … asking for
CP if it's raised by CP … collect payment also for L2 claims … registered at right place and make
the correct history … superadmins should have ability to correct (but our system should also be
capable to surface things)."*

---

## 1. Five rules the whole flow keeps

1. **Know who is writing before collecting anything.** A phone match only makes someone a
   *candidate* (numbers get recycled, phones get shared). Registering a claim spends a subscriber's
   quota and lands in someone's book, so it needs a **verified** person — the existing code sent to
   the account's registered contact (`biz_nidaan_wa_auth`).
2. **Nothing typed is ever lost.** Every answer is saved to a draft the moment it arrives. A person
   who stops halfway picks up where they left off; staff can see the draft.
3. **Register only what is complete enough; flag the rest.** A claim is created when the minimum
   is there (§5). Anything still missing is written on the claim as a named, visible *pending item*
   — never silently left blank.
4. **No AI on claim content.** Buttons, lists and local rules only — the same rule as claim
   documents. *(Today the bot's free-text replies go through Gemini; claim intake must bypass it
   entirely. That existing path deserves its own review — see §11.)*
5. **Every step is history.** Each action writes to the claim timeline with the channel
   (WhatsApp), the direction, and who did it (name + role). The raw conversation stays in
   `nidaan_wa_messages`.

---

## 2. Who is writing — identified from the number

| The number belongs to | What the bot does | Where the claim lands |
|---|---|---|
| **Subscriber** (account phone) | Verify once (code), then the subscriber flow (§4) | Their account; counts against their plan; **no Level-2 fee** |
| **AP / Authorized Partner** (branch contact phone) | Verify, then the AP flow (§6) | AP's house account, `origin=branch`; Level-2 fee applies at the GO step |
| **Channel Partner (CP)** (approved CP phone) | Verify, then the CP flow (§7) — **DECIDE** | **DECIDE** |
| **Staff** | Today: redirected to the Telegram ops bot | Recommend: keep staff on Telegram (§8) |
| **Complainant** with an existing claim | Document collection (already live) | Their existing claim |
| **More than one of the above** | Ask: *"You are registered as a subscriber and as a complainant on NP-155. What would you like to do?"* | Whichever they pick |
| **Unknown number** | Three buttons (below) | — |

**Unknown number — first message:**
> *Namaste 🙏 Who are you writing as?*
> `[My own / family claim]` `[I am an advisor (subscriber)]` `[I am a partner (AP / CP)]`

- **Own / family claim** → the D2C route: explain the ₹499 expert review and send the review link
  (payment on the website, where the flow already exists).
- **Advisor** → *"Please write the mobile number you registered with."* → verification code → if
  it matches, continue as that subscriber. Not registered → signup link (with a referral code if
  they have one).
- **Partner** → *"Please write your AP / CP code."* → verify against the partner's registered
  contact → continue; otherwise hand to a person.

---

## 3. Verification — **DECIDE**

The code goes to the **registered email** today. Many Tier II/III subscribers do not open email.

| Option | For | Against |
|---|---|---|
| A. Email code (as today) | Built, free | People stall here |
| B. SMS OTP | Familiar to everyone | SMS is **not configured** (`FAST2SMS_API_KEY` missing); costs per SMS |
| C. Registered-phone match + a 4-digit PIN they set once on the website | No SMS cost; fast after first time | Needs a PIN screen; forgotten PINs |

**Recommendation:** B if we switch SMS on, else A with a clear "check your email" message and a
staff fallback. One verification lasts **30 days** on that number (a session), so a subscriber is
not asked every time.

---

## 4. The subscriber flow, step by step

Every step: buttons first, typing only where needed; **"Change"**, **"Talk to a person"** and
**"Continue later"** always available; answers saved as they come.

| Step | Bot asks | Checks |
|---|---|---|
| S0 | *"Namaste Uttam ji 🙏 Raise a new claim?"* `[Yes]` `[Something else]` — **never** the plan name or claims used (30 Sep) | Plan active and limits are checked silently at S9 (§4a) |
| S1 | *Whose claim is it? Write the insured person's full name.* | 2–80 letters |
| S2 | *Their mobile number* (the complainant — we will send them updates) | 10 digits; not the subscriber's own unless they say so |
| S3 | *Type of claim* `[Health]` `[Life]` `[Motor]` `[Other]` | — |
| S4 | *Insurance company* — list of the top insurers + "Other (type it)" | Matched to our insurer list |
| S5 | *What happened?* `[Rejected]` `[Paid less]` `[Delayed]` | — |
| S6 | *Amount in dispute* (accepts "1.5 lakh", "150000") | **Within the plan's cap** (§4a) |
| S7 | *Policy number* `[I don't have it now]` | Optional → becomes a pending item |
| S8 | *Date of the rejection / event* `[Don't know]` | Optional → pending item |
| S9 | Summary card, in their language → `[Register claim]` `[Change something]` | Duplicate check (§5b) |
| S10 | **Registered: NP-240.** Then documents, one at a time — rejection letter first (the existing document bot takes over). | — |

**4a. Plan limits, said plainly — never a dead end:**
- Plan **not active / expired** → *"Your plan has ended. Renew here: (link). Your answers are saved
  — once you renew, reply here and we continue."* Draft kept.
- **Quota used up** → *"This claim is not covered by your current plan. Two easy ways forward:"*
  `[Upgrade plan]` `[₹499 + GST review of this claim]` `[Talk to us]` — no counts, ever (30 Sep).
- **Amount above the plan cap** (Silver ≤ ₹5 L, Gold ≤ ₹10 L, Platinum ≤ ₹50 L) → same three
  options, with the reason.

After registration the complainant gets the existing introduction + consent message (their
language), and staff are notified exactly as for a web claim.

---

## 5. When is a claim "registered"?

**5a. Minimum to register — DECIDE (proposal):** verified identity · insured name · complainant
mobile · claim type · insurer · what happened. Everything else (policy number, amount, event
date, documents) may follow and is written on the claim as **pending items**, each with who
should supply it.

**5b. Duplicate guard:** same account + same insured name or policy number + a claim still open →
*"Is this about NP-212 (Ramesh Kumar, Star Health)?"* `[Yes, same claim]` `[No, a new one]`.
"Yes" routes them to that claim's documents instead of creating a second one.

**5c. What staff see:** a new queue, **"WhatsApp claims needing completion"** — drafts that
stopped, and registered claims with pending items — with what is filled, what is not, how long
it has waited, and one button to call.

---

## 6. The AP flow

Same questions as §4, plus S1b *"Your customer's name and mobile"* (the AP is not the insured).

- Lands on the AP's house account, `origin=branch`, `raised_via=whatsapp` — **exactly** as if
  raised from the AP dashboard, so commission, the referral view and the Level-2 rules are
  unchanged.
- **Level-2 fee** (₹499, or ₹2000 above the threshold; the super-admin's policy decides whether to
  charge) is asked **only at the GO step**, by payment link (§9).
- The AP sees the claim on their dashboard as usual.

---

## 7. The CP flow — **DECIDE**

A Channel Partner has no subscription and today is only *credited* on a claim a staff member raises
from My Business. For a CP raising directly on WhatsApp we need three answers:
1. Which account does the claim land on — the staff member who onboarded the CP (My Business), or
   a house account?
2. Who pays the Level-2 fee — the CP (payment link to the CP), or the customer?
3. Does the CP see progress (like an AP), and where?

**Recommendation until decided:** a CP's WhatsApp claim is saved as a **draft for staff** — the bot
collects everything, then a staff member registers it from My Business with the CP credited. No
rules are invented for money we have not agreed.

---

## 8. Staff — keep them on Telegram

Staff already raise claims from ops and have the Telegram ops bot, which is linked to their login
and role. WhatsApp would need a second identity and permission system. **Recommendation:** staff
writing to the WhatsApp number get *"Please use the NidaanOps Telegram bot"* (as today); "raise on
behalf of a subscriber" stays in ops, where it is recorded as `ops_on_behalf` and is exempt from
the Level-2 fee.

---

## 9. Money on WhatsApp — Level-2 fees

**Who pays what (checked live, 29 Sep):** Level-2 fees have been charged only on AP / staff
My Business claims (53 claims). **None** on subscriber claims (90) or on claims staff raised for a
subscriber (22). That rule stays.

**How it is collected:**
- A **Razorpay payment link** (the AP flow already has one: `/branch/api/claims/{id}/l2-payment-link`)
  sent in the chat. Payment is confirmed **only** by Razorpay (webhook + the guardian) — never by a
  screenshot, and the bot never asks for card or UPI details.
- Paid → recorded in the ledger by the existing path → the claim moves to the legal queue → the
  payment notice goes out (now titled *"Payment RECEIVED — Level-2 fee"*).

**Reminders — not irritating:**
- Automatic: the link, then one reminder after 1 day and one after 3 days — **max 2**, never in
  quiet hours (21:00–08:00), stop on STOP, stop the moment it is paid.
- Then a **staff task**: *"Level-2 fee unpaid for NP-240 — please call."*
- Staff can **book a payment reminder** at a time the payer chose (the document-reminder schedule,
  reused).
- Past 24 hours since they last wrote, only an **approved template** can go (§10).

---

## 10. Nudges and the 24-hour rule

| Situation | Nudge | Channel |
|---|---|---|
| Stopped halfway through S1–S9 | After 2 h: *"Your claim is saved — reply to continue."* | Free text (inside 24 h) |
| Still stopped next day | One template: *"Your claim draft is waiting — tap to continue"* | Template (needs approval) |
| Still nothing | **Staff queue** (§5c) — no more messages | — |
| "Busy, remind me later" | The complainant-picks-the-time module (built, currently off) | Free text / template |
| Level-2 fee unpaid | §9 | Free text / template |

**Templates to get approved by Meta** (utility category; approval takes days, so start early):
`np_claim_draft_reminder`, `np_l2_payment_pending`. Drafts in EN and HI to follow once the flow is
agreed.

---

## 11. History, correction and surfacing

- **Timeline:** each step writes one line: *"Claim registered on WhatsApp by Uttam Singh
  (subscriber, verified) — NP-240"*, *"Policy number added on WhatsApp"*, *"Level-2 payment link
  sent to AP Indore"*.
- **Super-admin correction** — one tool, **"Correct where this claim belongs"**: change account /
  AP / CP / raised-by, with a required reason; written to the timeline and the audit log, and
  revenue and commission follow. (This is the *Correction Support* item already on the TODO — the
  WhatsApp intake makes it necessary.)
- **The system surfaces problems by itself:** a daily line in the ops summary — drafts abandoned,
  claims with pending items older than 3 days, a number matching two accounts, a suspected
  duplicate, a subscriber verified on a number that is not theirs.
- **Gemini on the existing bot:** today the WhatsApp brain sends complainants' free-text messages
  to Gemini to decide a reply. For claim intake this is bypassed; whether the rest of the bot should
  also go local is a separate decision — **DECIDE**.

---

## 12. Suggested phases

| Phase | Scope | Why this order |
|---|---|---|
| **P1** | Subscriber intake: identity + verification, S0–S10, drafts, pending items, duplicate guard, staff queue, draft nudges | Subscribers pay no Level-2 fee — no money on WhatsApp yet |
| **P2** | AP intake + Level-2 payment link + payment reminders + templates | Money, once P1 is proven |
| **P3** | CP flow (after §7 is decided); super-admin correction tool | Needs the commercial rules first |

---

## Questions for you

1. **Verification (§3):** email code, SMS OTP (needs SMS switched on), or PIN?
2. **Minimum to register (§5a):** is the proposed list right?
3. **Quota / cap exceeded (§4a):** offer upgrade, ₹499 single review, or talk to us — which?
4. **CP (§7):** which account, who pays, what they see — or drafts for staff until decided?
5. **Staff (§8):** keep them on Telegram?
6. **Nudges (§10):** two automatic, then staff — right amount?
7. **Gemini (§11):** keep claim intake local only (recommended) — and review the rest of the bot?
