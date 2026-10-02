# SARATHI BUSINESS — LIVING TO-DO

_Auto-maintained by Claude **every conversation**, alongside `PROJECT_MASTER_CONTEXT.md`._
_**Two-terminal workflow:** work 🟦 NidaanPartner items in one VS Code terminal, 🟩 Sarathi items in another. Each app's section is self-contained so both can progress simultaneously without collision._
_Legend: 🔴 blocked/awaiting owner · 🟡 in progress · 🟢 next/planned · ✅ done_

## 📌 PENDING WORK — the standing list

_Anything raised and not finished lives here until it is done, so an interruption does not lose
it. Newest first within each group._

### ▶ 2 Oct (afternoon) — the whole journey, end to end (founder)

> "when we are improving things, we should improve all other things too for users ... our app
> should look professional, built by professionals ... a true user should not face any challenge
> due to our tight security." His decisions on I13 / the on-behalf letter rule / Marathi-Punjabi /
> WhatsApp: all OK as recommended.

| # | What | Notes |
|---|---|---|
| J1 | **WhatsApp claim-raise**: a complainant raises a claim on WhatsApp - the same 7 core details (biz_nidaan_intake), asked one at a time in their language, each important one read back ("please check"), the letter sent as a photo/PDF in the chat, then the claim is created through the same rulebook | 🟢 Build |
| J2 | **Keep every claim on track**: one watchdog over the whole journey (initiate -> settlement) - finds claims that are misrouted, in conflict or crossing paths (e.g. in a Level-2 bucket without the L2 step, archived but with open work, two claims for one case, stuck waiting), puts right what is safe to put right, and FLAGS the founder + App Health for the rest | 🟢 Build |
| J3 | **Homepage -> the right plan**: advisor vs policyholder cards; a confirmation before paying ("you chose the Rs 499 one-time review for a policyholder - right?"); a super-admin way to correct a person who chose the wrong one later | 🟢 Audit, then build |
| J4 | **Payments end to end**: a thank-you page after every payment and the right next screen for the plan bought - on every device and browser (UPI app switching, popups, reloads, slow networks) | 🟢 Audit, then fix |
| J5 | **Every login and code**: email OTP, Google, WhatsApp, AP, staff; email + WhatsApp templates (content, format, routing); a clear "please wait" wherever we make someone wait (Google sign-in buffers) | 🟢 Audit, then fix |
| J6 | **No double tap, anywhere - built in, not remembered**: one shared guard every page loads + a check that FAILS the build if a page does not; buttons say what they are doing while they work | 🟢 First |
| J7 | Deploy tonight (after 6 pm): the intake work `44fbc2a..8369acb` | Waiting for 6 pm |

**Audits of 2 Oct (payments, sign-in, homepage -> plan, the claim journey) - what they found, in order:**

| # | What | Status |
|---|---|---|
| K1 | 🔴 SECURITY - payment verify routes trust the browser: the old one-time subscribe verify activates ANY plan for any valid Nidaan signature (pay Rs 499 -> Platinum Annual); the recurring verify trusts body.plan; claim / L2 / review verifies do not check the order was for THIS claim (one payment can unlock several). Fix: one check binding payment -> order -> product -> claim; retire the dead one-time routes; recurring plan read from Razorpay's own subscription notes; a mismatch is refused and reported | ✅ fixed `c3d9a78` (test fails 9/10 on the old code: claim 8 really was marked paid with claim 7's payment, Platinum really activated). Live data: no sign of use |
| K2 | 🔴 SECURITY - the one-tap pay link (/nidaan/pay/{id}) gives a FULL dashboard session; Telegram one-tap staff login can be phished (no "approve this browser?"); staff tokens never expire; /nidaan/confirm-email confirms on a GET (mail scanners click it); subscriber passwords are salted SHA-256 with no lockout; rate limits may key on Cloudflare's IP, not the visitor's (check nginx) | next |
| K3 | 🔴 BROKEN - a new person who clicks "Choose Silver" signs up and the checkout NEVER opens (switchPlan compares against a plan we stored before payment); Google sign-up stores "silver" for everyone and the welcome email says "Silver Plan"; subscription messages are written into a hidden window (dismiss / failure / pay-by-link fallback invisible); dead /nidaan/start#plans links | next |
| K4 | 🔴 BROKEN - the claim-page code email's button opens "link invalid/expired"; the claim page's identity step has no "I already have a code" (WhatsApp in-app browser loop); the WhatsApp bot says "code sent" when the email failed (and sends a complainant's code to the advisor's email) | next |
| K5 | Sign-in polish: Google sign-in never gives up when blocked (polls every 0.8 s, "Loading..." forever), nothing for in-app browsers; registration uses the code before checking referral / duplicate phone and then wipes the form ("Email already registered" for a duplicate phone); Enter key skips the double-tap guard; English-only server errors on Hindi pages; 429s shown as "Failed"; silent session expiry; /nidaan/logout does not log out; legacy login/signup/review pages still served | after K1-K4 |
| K6 | One thank-you page `/nidaan/paid` for every payment: re-verifies with Razorpay, says what was bought and shows the next step for THAT plan; pending -> "confirming"; every path (checkout, UPI app switch, killed tab, payment links) lands there; no alert(); pay buttons held for the whole flow; no new order while one is unpaid; retry emails only if still unpaid after 15 min; guardian recovers Rs 499 claim payments too; ops L2 order missing payment_capture | after K3 |
| K7 | "Is this you?" before any payment (who the plan is for, what they get, refund rule) + the advisor/policyholder choice saved on the account + a super-admin "correct this account's choice" (money-safe: owner-approved refund/credit, ledger never edited, customer told) | design ready; money rules to confirm with founder |
| K8 | Journey watchdog (J2): 20 conflict checks mapped (fee not covered in a bucket, closed but on the board, lost in Hold, archived with live chases, duplicates, paid-but-no-ledger ...); auto-fix only the provably safe ones; the rest flagged once to the founder + App Health | after K6 |
| K9 | Templates + email routing: one brand spelling, one code-email builder with Hindi, Sarathi headers off Nidaan mail, "Branch Portal" wording, contact-confirm by "reply YES" not a do-not-share code | with K5 |
| K7a | **His money rules (2 Oct)**: a policyholder who bought an advisor plan -> the plan is stopped and becomes ONE review (Rs 499 + GST); an advisor who bought the Rs 499 review -> it counts against their first month's plan | Decided |
| L1 | **No entitlement, no new claim - at EVERY door** (dashboard, Get started, Raise for a Subscriber, My Business on a subscriber, WhatsApp claim-raise, anything on-behalf): a subscription that has lapsed (autopay cancelled and the paid period over, or expired) or whose cap is used up, and a one-time review that is used, keep FULL access to their existing claims and services but cannot raise a new one; the dashboard freezes "raise a claim" with words and a renew / buy option; "Raise for a Subscriber" shows the same flag and refuses | 🟢 audit, then build |
| L2 | **GST, one switch**: every plan and fee is quoted EXCLUDING GST ("*All plans exclude GST" on the homepage); GST is added ONCE, by us, from the ops GST setting (on/off, rate, our GSTIN) - at every endpoint (plans, Rs 499, review, L2 fee, payment links, renewals); changing the setting in ops changes every charge with no code change; never twice. Note: Razorpay never adds GST by itself - the amount we send is what is charged; the GSTIN in Razorpay only prints on its invoice | 🟢 audit, then build |
| L3 | **Payment messages go to the person who PAID, and say what really happened**: on success a thank-you on WhatsApp + email (from info@nidaanpartner.com) and the thank-you page; a cancel / plan change minutes later is answered as such; if reconciliation with Razorpay finds a payment failed, reversed, refunded or dropped, the payer is told on email + WhatsApp. Never a payment message to a complainant / patient who did not pay (AP, My Business and subscriber cases are paid by the AP / staff / subscriber) | 🟢 audit, then build |
| L4 | **Forwarded documents on WhatsApp** (staff or AP forwarding a registered claim's papers to our number): find the right claim (claim number in the caption, or the sender's own claims - asked "which claim?" with a short list when not clear), unpack a ZIP and file each paper, tell the sender what was filed where, and thank the complainant ("thank you for the documents ... reach us on this official number if you need help; we will contact you if we need anything more") | 🟢 check what exists (staff forwarding with a claim number in the caption is live since 1 Oct), then build |

### ▶ 2 Oct — URGENT: one claim intake standard at every door (founder)

| # | What | Notes |
|---|---|---|
| I1 | **My Business form says "Customer" - no patient, no complainant** | Not changed recently: it has asked for ONE "customer" since it was built (10 Aug, `4c5f6a9`); the server stores that one person as BOTH patient and complainant. The AP form asks for them separately - the forms drifted |
| I2 | **The same core intake at EVERY door** (direct / subscriber, AP, CP, My Business, Raise for a Subscriber, Rs 499 review, WhatsApp, ...): (1) patient/insured name REQUIRED, mobile + email optional; (2) complainant name + mobile + email ALL REQUIRED, with a soft "double-check these - we use them for the whole case" nudge and OTP verification of at least one (email or WhatsApp) from our official email / WhatsApp; the welcome goes after verification; (3) insurance type - all standard types (health, motor, travel, fire, ...); (4) insurance company; (5) disputed amount; (6) policy no. optional; (7) rejection letter REQUIRED. Everything else is per door | Founder: "basic details ... unified at all places and other details as per the scenario" |
| I3 | **The AP's name in EMAIL signatures too, for AP cases** (as in WhatsApp) | Built 1 Oct for both email and WhatsApp (`b6e6944`) - confirm it covers the welcome email once I2 sends it after verification |
| I4 | **Advise on industry best practice** for a strong, reliable product on every device (Android, iOS, tablet, web, mobile web, installed web app that feels like a Play Store app) | Founder asked for recommendations, not just execution |
| I5 | **AP form had NO insurance-company field since 13 Sep** - the picker box was never filled in (found while mapping I2; 17 of 105 AP claims arrived without an insurer, staff filled most later). Fixed: the picker is mounted on load and after each submit; `uitest/ap-insurer-picker.js` fails if any form reads an insurer box it never mounted | Fix ready - deploy as hotfix or tonight, his call |
| I6 | **His decisions (2 Oct, 13:40)**: (1) insurance type = every standard Indian type, one drop-down; (2) disputed amount REQUIRED, with a double-check prompt (people get the zeros wrong) - and a soft "please check" on WhatsApp for every mandatory detail it collects; (3) complainant confirmation = BOTH ways: an automatic confirm link/code, and staff can confirm for them (code read out on a call); (4) rejection letter: NO exception, except AP and My Business may raise with "no letter - give the reason, send it as soon as possible"; the claim is ARCHIVED (never deleted) after 7 days without it; reminders: AP on WhatsApp, the raising staffer on Telegram | Decided |
| I7 | **WhatsApp in the person's language** (Hindi / English / Hinglish / Marathi / Punjabi / others): the bot answers in their language; every message is ALSO recorded in English for the team; a **Translate** switch in the inbox and the claim's chat (super-admin ops); staff write in English / Hinglish / Hindi and it reaches the person in their language; emails stay English. Templates (first messages) only go in the languages Meta has approved | Founder, 2 Oct |
| I8 | **No double messages when the patient and the complainant are the same person** (same number / same email) - one message, not two | Founder, 2 Oct - check every fan-out |
| I10 | ✅ **Built 2 Oct (not yet deployed)**: P1 server rulebook + the letter first + the 7-day rule + rate limits on the AP and My Business routes; P2 the shared form block on all five forms (My Business, Raise for a Subscriber, AP portal, subscriber dashboard, Get started); P3 confirm first, then welcome; I8 one person, one message (claim updates, status changes, document asks, one-time WhatsApp messages; every Rs 499 website claim was getting "claim registered" TWICE from the alert sweep). Tests: `test_intake` (every door over HTTP), `test_welcome`, `test_one_message`, `uitest/intake-block.js` (375 px, both themes), `uitest/mybiz-form.js` - each proven to fail without its fix | An independent pre-deploy review found 12 problems (worst: LIFE claims call their letter 'decision_letter', so they would have been archived with the letter in hand) - all fixed in `8369acb`, tests proven. Deploy after 6 pm (commits 44fbc2a..8369acb) |
| I11 | ✅ **Old Rs 499 review page retired** (`/nidaan/get-reviewed`): it asked for no complainant and no letter, nothing linked to it (every Rs 499 button already goes to Get started), 1 claim ever. The page now leads to Get started (keeping ?ref=); its public sign-up answers 410 (no account / purchase made). Earlier purchases can still be paid from the dashboard. Also closes an unescaped name/notes in the admin email it sent | Done 2 Oct |
| I12 | ✅ **WhatsApp in their language, recorded in English** (built 2 Oct): the bot follows the language they write in (12 languages; Marathi + Punjabi fixed lines added - a native speaker should read them once); every message gets an English copy (Translate switch in the inbox AND the claim's chat); staff write in English/Hinglish/Hindi, see the translation, then send - their own words are the record. Templates stay English/Hindi (Meta-approved). The soft "please check" on WhatsApp waits for a WhatsApp claim-raise: WhatsApp collects no claim details today | Deploy with I10 |
| I13 | ⚠️ **"Staff can do it for them" - built the SAFE way**: staff ask the complainant to send "Hi" on WhatsApp (proves the mobile at once) or resend the link/code. NOT "read the code to me on a call" - that trains people to share codes, which is how fraud calls work, and our own emails promise we never ask. His call if he still wants the read-out | Tell him |
| I9 | **Build order**: (P1) one server rulebook `biz_nidaan_intake` - types, the 7 fields, the letter uploaded and virus-checked FIRST (single-use token bound to who uploaded it) so a claim cannot exist without it; the 7-day letter rule; rate limits on the AP and My Business routes; (P2) the shared form block (EN/HI, amount in words in lakh/crore, the double-check prompt) on every form; (P3) complainant confirmation + welcome only after it; (P4) WhatsApp language + translation (I7) and soft checks; (P5) contract tests per door + a checker that no page hard-codes its own type list | 🟡 P1 in progress |

### ▶ 2 Oct (morning) — decisions and the next discussion

| # | What | Notes |
|---|---|---|
| H1 | ✅ **14 numbers marked as consenting without writing to us -> not consented** (his yes; done 04:16 IST, opt_source `staff_start_no_consent`, nothing deleted) | |
| H2 | ✅ **Homepage figures confirmed correct** (95%+ success, 5,000+ policyholders, 2,000+ cases) - the bots quote them | |
| H3 | ✅ **Case email password stays as it is** (no encryption) - his call: these mailboxes are created only for insurer correspondence. E14 closed | |
| H4 | ✅ **Claim-level WhatsApp = a real chat window like the inbox** (`39accd0`) - header, take over / give back, search, the same bubbles, the reply box always there (greyed with the reason), emojis, quiet refresh | His screenshots, 2 Oct |
| H5 | 🟢 **TEST KIT - discuss** (his ask: "sample claims only for testing each and every feature ... in live environment"). Proposal: (1) a **Test** flag on a claim (super-admin sets it; claim 92 and the "TEST..." claims first); (2) a test claim is **never counted** (dashboards, analytics, revenue, the 8 pm summary, App Health) and **never reaches a real person** - every WhatsApp / email / SMS for it goes only to a short list of staff test numbers and inboxes he names; (3) a **kit of 6 sample claims**, one at each point of the line (intake, review, L2 waiting, Live Cases, Escalation with a query, Lokpal), with names starting "TEST -" and staff test numbers as their phones; (4) **"Fresh test kit"** (super-admin): the old kit is archived, never deleted, and a new one is made in its starting places; (5) a yellow **TEST CLAIM** band on the claim so nobody mistakes it; (6) a one-page checklist per new feature ("open TEST - Escalation, raise a query, answer it ..."). Questions for him: which staff numbers/inboxes receive test messages; who may mark a claim as Test (super-admins only?) | Decide, then build |
| H6 | Mobile numbers written with a leading 0 (07869350978) are now understood as +91 (`39accd0`) | One claim's number was being messaged as written |

### ▶ 2 Oct — the founder's list (sent after the 19:10 deploy), in order

Deployed 03:37 IST 2 Oct (`7439bdf`): G1-G10 + the review fixes; suite clean; outside checks as expected; App Health 0 errors.

| # | What | Founder's words / notes |
|---|---|---|
| G1 | ✅ **Escalation Query -> Escalation Query Responded** (`8e257dc`) | The step dropdown opens the query box; the words + who raised/answered are kept (nidaan_bucket_queries); the escalation team and the claim's people are told; answering moves to the new step and tells whoever raised it; every step is a filter chip, even at zero |
| G2 | ✅ **The 8 pm voice reads the WHOLE summary** (`29232cf`) | It read a separate short script, cut at 1,500 characters. Now the voice IS the message, read in pieces joined into one recording; long text goes out as several messages |
| G3 | ✅ **Summary: real work, blockers with owners, "worth a look"** (`29232cf`) | More real work counted (chases, calls, WhatsApp collection, replies, files sorted, case email/password, blockers); a gist save that changed nothing is not work; "Blockers on our side" names who owns each - NOBODY first (dry run on live: 86 stuck, 53 with nobody); "Worth a look" flags saves that changed nothing, claims edited two days running without progress, moves there-and-back, statuses flipped back - never super-admins, never test claims |
| G4 | ✅ **Why is this claim waiting?** (`0fcb323`) | Automatic: documents (have/need + missing by name), L2 fee unpaid, authorization not accepted. Ticked: Query - complainant, Reply - insurer, Our team, Other (own words). Chips on every list, a filter on each bucket, the box on the case sheet and in the drawer; history kept |
| G5 | ✅ **Days = the full time in a bucket, every stay added up** (`8e257dc`) | pipeline_bucket_at (set only by a bucket change) + earlier stays from the move log; claims already in a bucket back-filled from the log (since 30 Sep) else their step clock - older history was not kept |
| G6 | ✅ **A past escalation date is the super admin's call** (`d877485`) | Others are told to ask a super admin. (A request-and-approve flow, like the CP change, can follow if wanted) |
| G7 | ✅ **Inbox like WhatsApp** (`1ca38ec`) | Search all chats + inside a chat, ✓/✓✓/blue ✓✓ ticks, Indian time am/pm with day separators, good-emoji row, NidaanMitra. **Next:** open received photos/files from the thread (a safe download path) |
| G8 | ✅ **Both bots are NidaanMitra, one set of facts, a stranger is a lead** (`12c006b`) | Track record + links in Content (both bots read it); WhatsApp strangers get NidaanMitra in lead mode (one question at a time, track record, start link, customer stories), the CRM lead learns name + need; trap + injection rules on both. **Please confirm the homepage figures are accurate: 95%+ success, 5,000+ policyholders, 2,000+ cases** - both bots now quote them |
| G9 | ✅ **Claim-level WhatsApp window** (`1ca38ec`) | In the drawer and the case sheet: the same messages as the inbox (both numbers), reply (duty only), Start collection, open in inbox |
| G10 | ✅ **Start WhatsApp collection: preview first, Send to confirm** (`6253462`) | Who, which number, how, every document, warnings (junk name, unconfirmed number); a staff start is no longer recorded as the complainant's consent; a person handling the chat stops the bot on every path; the send caps counted only 'sent' and undercounted. **His call: 14 numbers are marked as consenting though they never wrote to us (they are in campaign audiences) - set them to not-consented?** |
| G11 | 🟡 **App Health - honest answer** | It reads real outcomes for login codes, WhatsApp replies, payments, backups, scheduled jobs, disk. Still CONFIGURATION, not outcome: "Email (Brevo) API key configured", "SMTP configured", "AI (Gemini) configured", "Payments configured". Next: each to read its last real success (an email delivered, a Gemini answer, a payment captured). It does not repair anything by itself - it links to the screen that fixes each item |
| G12 | Days in a bucket can over-count if a stay's exit was never logged, or after a bucket is renamed (review, 2 Oct, low) | Close an open stay at the next logged entry elsewhere; map renamed keys |

### ▶ 1 Oct EVENING — the founder's decisions and list (after the 18:00 deploy), in order

| # | What | Founder's words / notes |
|---|---|---|
| E1 | ✅ **Account deletion is NOT claim deletion** - DEPLOYED 19:00 IST (`2a27b7f`) | Erasing an account anonymises it; every claim stays ARCHIVED with documents, authorization, notes and files. The 30-day unpaid-lead document purge is OFF (setting `lead_document_purge`, fails closed) and so is its "will be deleted" notice. Ops and subscriber deletion texts corrected (EN/HI). Live before the fix: 18 accounts had been erased WITH their claims, 37 leads had documents purged (gone - only backups could tell); account 86 (3 claims) was due 7 Oct and is now safe |
| E2 | ✅ AP name on ALL responses on AP claims, staff replies included - as built | |
| E3 | ✅ **One Edit window with every AP field** (`d9bab43`, DEPLOYED 19:10 IST) | Person, city, state, office name, login email, WhatsApp, share % (super admin), status. The code stays fixed - it is on every referral link and claim |
| E4 | ✅ **Claim 87's authorization re-filed** (doc 1479, hash verified, timeline note). **Claim 92 NOT filed - it is a test claim** (insured "TESTING........", account "YASHVARDHAN Tester") | Archive claim 92? His call |
| E5 | 🟡 **"Why is this claim waiting?"** - ADVICE given, waiting for his OK on the reasons | Proposal: a "Waiting on" tick-list on every claim (several at once), shown as chips with days in every list + a filter. Automatic where we already know (documents short with what is missing, fee unpaid, authorization not accepted); ticked by staff for: Query - complainant, Reply - insurer, Our team, Other (a short note). Ticks are kept as history, never deleted |
| E6 | ✅ **Email "unverified" after verifying** - FIXED + DEPLOYED (`0ed7341`) | Claim #202: three sends in 90 s voided each other, so earlier links said "expired" and codes "not right". Now every link/code for the current address works until it expires; "I already have a code" on the claim page. (The mobile showed verified because a WhatsApp sign-in proves the phone only.) |
| E7 | ✅ **Flicker** - silent refresh (`d9bab43`, DEPLOYED 19:10 IST) | WhatsApp inbox first (no "Opening..." every 25 s, no jump, no double-open, Back stays Back); shared `ndPaint` for other screens to adopt one by one |
| E8 | ✅ **Escalation date cannot be before today** - DEPLOYED (`d048fa4`) | Only a changed value is checked, so dates already on file still save. Note: a REAL escalation done yesterday can no longer be back-dated - say if that is ever needed |
| E9 | ✅ **Days-in-bucket filter on every bucket** (0-10, 11-20, 21-30, more than 30, with counts) - DEPLOYED (`00d1ef0`) | "Days" counts from when the claim entered its current STEP (a step change restarts it) - say if it should count from entering the bucket instead |
| E10 | ✅ **Escalation step filter** - DEPLOYED (`d048fa4`) | A claim re-entering Escalation with its date is "Escalated"; a stale filter from another bucket no longer carries over |
| E11 | ✅ **Buckets listed once** - in the left menu with live counts - DEPLOYED (`00d1ef0`) | |
| E12 | ✅ **Layout Planner** at nidaanpartner.com/nidaan/ops/layout-planner (`d9bab43`, DEPLOYED 19:10 IST) | The team arranges, saves under their name; a super admin chooses. Rebuilding the real menu from the chosen layout is the next step, after his review |
| E13 | ✅ Folder: NidaanPartner keeps `C:\sarathi-business`; Sarathi moves out (M7a path) | |
| E14 | Case email password - PARTLY FIXED 1 Oct: never in an ordinary page load for any role ("Show it" is the only, audited, way; it now really shows it), only super/sub-super admins can change it (audited), and a WhatsApp-captured password is taken out of the chat copy | **Still plain text in the database.** Encrypting at rest (AES-256-GCM) needs a key that is never lost - a dedicated key in biz.env, backed up off-site with the DB backup passphrase, never derived from the login-token secret (rotating that would make every stored password unreadable). His decision; then a one-off migration. Older WhatsApp messages from before today still hold any password sent in them |

### ▶ 1 Oct AFTERNOON — the founder's list (after the 13:30 deploy), "we'll try to do it all today"
Deployed 13:30 IST (`14b0f23`): outside checks all as expected, App Health 0 errors. Hotfix `4d233a4` (P1) deployed 14:00 IST. Evening deploy 18:00 IST (`60fa9e1`): outside checks as expected, App Health 0 errors, existing letters verified unchanged (v1), 0 of 15 APs have a person's name yet.

| # | What | Founder's words / notes |
|---|---|---|
| P1 | ✅ **Re-subscribed subscriber blocked from raising a claim** (Deepika Yadav, acct 105) - FIXED + DEPLOYED `4d233a4` 14:00 IST | One rule (`quota_used`) for every door; a lapsed plan that renews starts fresh (`active_since`); plain EN/HI words instead of codes. Verified on live: Deepika can raise claims; the 6 other blocked subscribers each really used 3 claims under their current plan |
| P2 | ✅ **3-strike rule - understood and confirmed in code**; the website chat's forced handover after 6 messages is now a runaway ceiling of 15 (`4e76d48`, DEPLOYED 18:00 IST) | The 3 holding messages fire ONLY after the bot has handed the chat to a person (escalated / human takeover / bot cannot discuss the claim). Normal questions are answered in or out of hours. The AI hands over by intent; a repeated question hands over at once |
| P3 | ✅ **AP identity + the AP's name on every message about their claims** - DEPLOYED 18:00 IST (`b6e6944`, `60fa9e1`) | Person's name + state on every AP (create form requires them; "edit details" window with a live preview). "Rakesh Sharma, Authorized Partner of NidaanPartner.com, Pune (MH)" replaces the team sign-off on email + WhatsApp for AP-raised and AP-referred (code or shared link) claims; never on OTPs, staff My Business claims, messages to the AP itself. **After deploy: add the person's name + state for every existing AP** (App Health lists the missing ones). Meta templates cannot carry it - new templates with a name variable would have to be submitted |
| P4 | ✅ **Authorization letter v2** - DEPLOYED 18:00 IST (`1b45887`) | Letterhead (Nidaan The Legal Consultants LLP + logo), registered office footer, the complainant who accepted, the tentative fee on the disputed amount frozen at acceptance and in the hash. Letters accepted before stay exactly as they were. Thank-you now goes to the complainant. Terms text: firm name spelt as registered, terms version v2 |
| P5 | ✅ **Doc 62 -> claim 50** - linked on live 1 Oct (guarded UPDATE, 1 row) | |
| P6 | ✅ **Docs sorted** - every .md in its product's folder, `docs/README.md` is the map (`b6e99e7`); CLAUDE.nidaan.md brought up to 1 Oct (entity name corrected, AP signature, letter, claim cap, files to sort, menu) | |
| P7 | ✅ **The 1 Oct staff message is in the SOP as a sample** (EN/HI) - deployed 14:04 IST (`101b036`) | nidaanpartner.com/sop-whats-new (ops sign-in) |
| P8 | Explain the folder split: today ONE folder (`C:\sarathi-business`), two products served separately on the server; the two-folder move (M7/M7a) is not done yet | Needs his call: which product keeps this folder |
| P9 | ✅ **Signed authorizations could be hard-deleted** by any team member, and by the complainant from their own page - FIXED `45903c2` (DEPLOYED 18:00 IST) | Found while mapping P4. 2 of 70 signed acceptances on live have NO PDF on file: claims **87** and **92**. Their consent snapshot (terms, fee %, time, IP, hash) is intact in `nidaan_claimant_portal`, so the PDF can be re-filed from it - additive, needs his yes |
| P10 | **The dashboard chat AI is given `claims_used_this_month`** (`biz_ai.nidaan_support_reply`, account context) with no instruction to keep it to itself | Standing rule: never tell a subscriber how much of their plan they have used. Remove it from the context (the AI does not need it to help) - needs a careful look at what the dashboard passes |
| P11 | **15% is hard-coded in 4 places besides the setting** (terms default text, ops push-authorization confirm text, ops fallback, dashboard reward copy) | If the super-admin changes the fee %, those would disagree with the letter. Fill them from `claimant_success_fee_pct` |
| P12 | **AP name on WhatsApp TEMPLATES** (cold messages outside 24 h) | Meta templates have fixed text. Needs new templates with a variable for the partner line, submitted to Meta by him; then `wa_journey` passes it |
| P13 | **Two other paths still remove authorization records**: account erasure (`biz_nidaan.py` ~6164, DPDP) and the unpaid-lead purge (`biz_nidaan_retention.py` ~102) | Founder's call: erasure is probably meant to (a person's right to be forgotten) - but the firm may need the consent proof while a fee is owed. Decide before changing |
| P14 | ✅ FIXED + DEPLOYED 18:00 IST 1 Oct - **Security (older): the AP and My Business document-delete routes passed `allow_any=True`**, so the claim id in the URL is never matched to the document - an AP can delete another claim's document by its number (`sarathi_biz.py` ~5079, ~11144) | Pre-deploy review 1 Oct. Fix: pass the claim scope (claim_id match) instead of allow_any, after checking the caller owns the claim |
| P15 | **Confirm with him**: the AP's name also signs staff replies typed in the WhatsApp inbox and every bot reply in document collection, on AP claims | That is what "all communications" means as built; say if staff replies should stay signed by the team |
| P4a | **Authorization letter - facts (1 Oct map)** | There is no paper letter: the complainant accepts a fee card in the claim portal (checkbox + button, after a code to their phone/email) and we file a plain "DIGITAL CONSENT RECORD" PDF (`biz_nidaan_claimant.build_consent_proof_pdf`) - no logo, no letterhead, no footer, no rupee figures. The SCREEN already shows the tentative calculation on the disputed amount (15% + 18% GST, `compute_fee`); the PDF does not, and the figures shown are not frozen at signing. Bugs: the PDF names the INSURED not the complainant who signed; its phone is always "-"; the thank-you goes to the insured's email/WhatsApp; the ops "consent-proof" download re-renders with today's layout and live claim data (must serve the filed copy / version the renderer so old letters never change). 15% is hard-coded in 4 copies besides the setting. Entity name conflict: code, logo and legal pages say **"Nidaan The Legal Consultants LLP"** (test cites his registration document, 28 Sep); CLAUDE.nidaan.md said "Nidaan Legal India LLP". No LLPIN/GSTIN anywhere in the code |
| P3a | **AP identity + signature - facts (1 Oct map)** | `nidaan_branches` has code, city, name (an office label like "Pune Branch"), email, phone, share %, status - NO person name, NO state; name/city cannot be edited after creation. Claims link to an AP by `claim.branch_code`, else the account's referral `branch_code`, and only if the code is a real AP (staff `SP-` codes also use origin='branch'). WhatsApp has one send point (`biz_nidaan_whatsapp._post`); Meta templates have fixed text ("- NidaanPartner") - an AP name on templates needs NEW templates submitted to Meta. Email has no single point (~15 customer builders, 5 different sign-offs). OTPs: template + a free-text fallback in `claim_access._send` that must be excluded. Side bugs: AP-raised claims send "subscriber" emails to the dead house address `branch.<code>@house.nidaanpartner.internal`; an AP CC'd on a document request would receive its own signature |

### ▶ 1 Oct MORNING — the founder's list (01:55 IST message), in order
Done overnight: NP-123 - Brajesh Gupta's 8 WhatsApp files (sent after his chat went to a person) were being DROPPED; fixed (`39bd4f9`, files during a takeover are saved, bot silent, staff told once) and all 8 recovered onto the claim (11 -> 19 documents). Edit Advisor hidden on house accounts (`089edb9`).

| # | What | Founder's words / notes |
|---|---|---|
| A1 | **Out-of-hours rule for EVERY customer-facing bot** (homepage chat, dashboard chat, WhatsApp) - TODAY | Founder, 1 Oct: outside 10:00-18:00 IST (or when no person is free), the bot tells them our office hours and that someone from the team will reach out, then hands over - the LAST message is the bot's, never a silent handover. Repeated chatter: the same office-hours line at most 3 times, then silent. Staff Telegram about a waiting chat: only 2 notices per chat, not every hour |
| A2 | **Deploy 1 Oct at 13:30 IST** (staff lunch) | Founder's time, not a hotfix window - build/test before |
| A3 | **SOP page on nidaanpartner.com for everything that changed** - examples and scenarios | Before the 13:30 deploy so staff read it when they are back |
| A4 | **CRM transformation and revamp** - think it through, then plan | Founder, 1 Oct. Earlier notes: memory "Project: Nidaan CRM" (reuse Tasks + leads pipeline, voice-first, bot-role daily assistant) |
| A5 | **Working rule: capture every urgent interruption here before acting on it, then come back to this list** | "many time we off-track what we're doing due to urgent requests" |
| — | **1 Oct morning, built (deploy 13:30 IST)** | M9 Files to sort + staff forwarding with NP-123 caption; N8 Rs 499 review documents onto the claim; subscriber Features tab fixed; A1 office-hours bot rule + 2 staff notices per chat; A3 /sop-whats-new; M1 summary per claim; M2 office menu + screen-open counting; M3 "All open claims (whole line)" / "Not yet at Level-2 (coming)"; M4 App Health per person + errors apart from warnings; M5 duty roster in two groups; M6 a Support reply on a WhatsApp chat is SENT on WhatsApp (it was saved only); CRM record routes authorised (any team member could open/edit any lead) |
| A4a | **CRM revamp - the facts to design from** (1 Oct review) | Five places hold prospects with five vocabularies: CRM leads, WhatsApp contacts, unpaid_lead claims, Payment Follow-up, website-chat lead threads - none linked or de-duplicated. No follow-up reminders at all (`due_followups()` is never called). "Mark Won" never links an account. WhatsApp-captured leads have no owner. Stages hard-coded. Telegram has no CRM. Propose: ONE prospect record all five feed, owner always set, follow-ups on the evening/"Your day" message, won = linked account |
| M2b | **Retire unused tabs on evidence** | Screen opens counted from 1 Oct (`/nidaan/ops/api/ui/usage`, super-admin). Review on ~8 Oct; archive (never delete) what nobody opened |
| M4b | App Health real gaps to fill (data, not code) | 4 Authorized Partners with neither email nor mobile (IND-HO, PUN-01, MUM-01, CHD-01) cannot log in; 12 have no WhatsApp |
| M7a | **Split - agreed facts** | Smallest path to two folders: (1) worker runs loops by owner (`deploy/loop-ownership.json`, env switch), (2) Nidaan worker + deploy script use `nidaan_app.py`, retire the 8001/8002 fallback, (3) freeze generation - nidaan_app.py / sarathi_app.py become hand-edited source, archive sarathi_biz.py + extract-app.py, (4) copy Sarathi into `C:\sarathi-ai` as its own repo, (5) cut lazy imports so Nidaan needs no Sarathi file. DB split later. FIRST settle: which product keeps this folder (SPLIT_PLAN says Nidaan stays; CLAUDE.sarathi.md:108 says the opposite) |
| B1 | **In-app "Updates for you" can hold 40 notes, each needing "Got it"** (seen 1 Oct on a sub-super-admin) | Same over-notifying as Telegram, in the bell. Fold into "Your day": claim notes become a per-claim digest, acknowledgement only for what truly needs it |
| R1 | **Shared docs (SOPs, design pages) are also served raw at `/static/<file>.html`** by nginx and the app's /static mount - the `_DOC_KEYS` share-key gate is bypassed and Cloudflare caches them 7 days | Pre-existing (review 1 Oct). Move them out of /static so only the gated route serves them. Until then: NO customer data on any of them (rule) |
| R2 | **N3 follow-up buttons - built and tested on branch `n3-followup-buttons` (worktree C:\sarathi-n3)** | Merge after today's deploy settles; run gen:apps after merging (split-surface) |
| R3 | `submit_claim` links "the most recent paid purchase" to a new claim, so an account with two paid unconverted reviews can link the wrong one | Pre-existing (review 1 Oct); uploads no longer follow that link, but the link itself should be deterministic |
| T1 | `uitest/flow.mjs` still mints its token on the OLD Contabo server (84.247.172.252) | Point it at Oracle 161.118.186.201 before relying on browser tests |
| M0 | **Someone must reply to Brajesh Gupta (NP-123)** - his chat is with a person (bot paused) since 30 Sep 18:12 IST; he asked "Apko kya chahiye clear kare" | The Telegram nudges were right |
| M0b | One WhatsApp file lost on 18 Sep from the number on claims #114/#169 - ask them to send it again | Unrecoverable (sent before media ids were kept) |
| M1 | **Evening summary must say WHAT was done on each claim**, not counts: moves from->to, documents received/checked, follow-ups made (messages, calls, reminders), queries raised/answered, handovers, notes - and not count trivial edits as achievement | "we need to capture actual work, movement, progress, followup" |
| M2 | **Ops revamp - an office model**: left navigation as foldable groups with sub-items; Consolidation's buckets inside its own fold; find unused/redundant tabs (from real usage) and retire them | "a lot of garbage tabs... proper office model" |
| M3 | **One definition per number**: queues and buckets each with their own counts, SLA, statuses, filters; "Before Level-2 139" = open claims not yet at Level-2 (intake + review + L2 waiting) - rename/explain; All Claims = the whole journey view | "multiple numbers at multiple places not giving correct visibility" |
| M4 | **App Health**: list every check that shows red, tie each to a real outcome, remove the ones that measure nothing | "not sure how well app health is connected with real features" |
| M5 | **Duty, explained and simplified**: ONE roster table - channel duties (Support chat, WhatsApp inbox, Intake, Review, Conversion) and bucket duties (Live Cases, Pending Draft...) are rows of the same roster; show them as two clear groups | Support screen roster = same data as bucket duty |
| M6 | **Support vs WhatsApp**: a WhatsApp chat handed to a person also opens a Support thread - that is why the nudge says "WhatsApp Automation / Customer Support". Make one place to answer it | |
| M7 | **Split Nidaan and Sarathi into two folders** (docs/split/SPLIT_PLAN.md: worker, then databases, then folder move) so Sarathi can be revamped in its own session | "can we move completely on nidaanpartner.com independently" |
| M8a | **Unused-code list ready for his yes** - `docs/nidaan/ARCHIVE_CANDIDATES.md` (each item checked three ways) | Approve per group: A module, B Nidaan functions, D unreachable screens (My Desk, Case Board, old Pipeline); decide E1 (old admin-key API - recommend archive), E2 (Evolution numbers), F (routes with no caller). C is for the Sarathi session |
| S1 | **WhatsApp files: the claim path stores a file UNSCANNED if the virus scanner itself is unreachable** (`biz_nidaan_doc_intake.accept`) | Founder's call: fail closed (keep the Meta id, tell staff, store nothing) like the new "to sort" inbox, or keep storing and flagging |
| M8 | **Lean codebase**: inventory unused code (routes nobody calls, modules nothing imports, dead functions like `_save_wa_doc`), check 2-3 times, ARCHIVE (never delete), list for his yes | "archive not delete" |
| M9 | **WhatsApp "to sort" inbox** - unmatched files kept and attached with one tap; staff forwarding from ANY staff number allowed (decided 1 Oct) | |

### ▶ 30 Sep (late night) — built and deployed; what is left for discussion
Done: evening summary per person + team (text + voice, EN/HI/Hinglish, rupees never dollars) with
a bucket-move record (`nidaan_bucket_move_log`); L2 header says what each number counts; duty
follows leave and cover, archived staff never "on duty", people told when rostered; CP add/remove
on an existing My Business claim with super-admin approval; claim #245 - automatic WhatsApp
replies are not answered and do not confirm a mobile, the double reply race is closed, timeline
in plain words; incoming WhatsApp files keep their media id; fresh-install columns fixed.

| # | Open | Notes |
|---|---|---|
| D1 | **Forwarded / unmatched WhatsApp documents** - discuss | Today a file from a subscriber, staff member, partner or unknown number is DROPPED (media id now kept on the row, ~30 days at Meta). Proposal: keep every file in a "to sort" inbox; staff attach it to a claim (one tap); a staff member forwarding a customer's papers writes the claim number in the caption and it files itself after a check |
| D2 | **Claim-level WhatsApp conversation window** - discuss | Possible. Needs inbound rows tagged with claim_id (today NULL) and a thread view inside the claim; the inbox stays for unmatched numbers |
| D3 | **WhatsApp automation for existing claims** | Confirmed: off by default; a staff member starts it per claim. Restart-follow-up buttons (N3) still to build |
| D4 | **"Your day" (N4)** - the morning focus message; the evening summary is its twin | Build next, with the no-bombarding rules: at most one morning message, bucket-move alerts folded in |
| D5 | Telegram quiet hours for staff (non-urgent alerts held 21:00-08:00) | Part of D4 |
| D6 | The L2 row note says "Rs 499 + GST" even when the fee is the Rs 2000 tier | Small |

### ▶ NEXT SESSION (30 Sep, founder's answers - all decided, build in this order)
| # | What | Founder's answer |
|---|---|---|
| N1 | **Plan ended**: 3-day grace, then the dashboard shows only welcome-back / renew; registered claims keep being worked for the complainant; ex-subscriber gets no updates; WhatsApp warm welcome + renew link, nothing private | "we do keep working the claims already registered ... with a 3-day grace" |
| N2 | **Referrers see documents**: APs and staff see which documents are in / missing on customers they referred **and the files too** (read-only; per-claim scope via referral match; audit each open) | "should see only which documents are in or missing ... and files too" |
| N3 | **Follow-up buttons**: Start reminders again / I'll follow up myself / Book the customer's time; every switch on/off recorded with who; the Follow-up box summarises what other staff did so far | "yes ... switch on switch off who did what should be recorded" |
| N4 | **"Your day"**: adopt the scenarios as written on the draft-3 page; change later if needed | "so far good let's adopt it" |
| N5 | **Staff sessions expire** and ask to relogin (add `exp` + a "void before" stamp on archive / role change / password reset). Passwords CANNOT be listed - they are stored as one-way bcrypt hashes; offer a "set a temporary password" / reset flow for anyone who forgets | "we should expire the session and ask to relogin" |
| N6 | **Remove the legacy `NIDAAN_ADMIN_TOKEN` routes** (`/nidaan/api/admin/*`). Checked 30 Sep: the key is not set on the server, so they already refuse everyone - dispose of the dead code | "check and secure or dispose if not in use" |
| N7 | **WhatsApp intake**: all "decide" points as per recommendations; Phase 0 (one intake for the six web doors) first | "all are as per your best recommendations" |
| N8 | Rs 499 review documents onto the claim; verify ledger rows for webhook/recovery-confirmed Rs 499 payments on live data | from the 30 Sep review |

Done 30 Sep (night): "Claims used" relabelled "Claims filed with us" / "हमारे साथ दर्ज क्लेम"; new house accounts named "Authorized Partner X" / "Staff SP-X" and the 19 existing ones renamed (display name only, founder's yes).

### Waiting on the founder
| # | What | Why it is waiting |
|---|---|---|
| 1 | **Turn on "Complainant picks reminder time"** after the 29 Sep run-through | He said yes (29 Sep). Deployed OFF; flip it when he says the run-through is done (WhatsApp → Doc-collection defaults) |
| 2 | **Rotate the doc share key** | It was printed into a task log on 28 Sep. Rotating breaks existing shared SOP links, so it is his call |
| 3 | **Send the 29 Sep announcement** | The SHORT one at the top of `ANNOUNCEMENTS.md` (five points, EN + HI) |
| 3b | **Deploy `1329aaa` after 6pm IST** (or on his go) | Referrers' "still missing" shown only when the claim really collects documents. Committed and pushed, NOT deployed - it was working hours |
| 3e | **Historic ledger rows with an odd GST split** (Aug - mid Sep: Rs 588.00 / 589.00 / 590, a few with no GST) | Not touched - needs his and the accountant's say before any correction |
| 3f | **Draft 3 of the WhatsApp/intake page - 5 decisions** (30 Sep) | https://claude.ai/artifact/AvFK6bxXWtmRGPr8XH9FQC "For you to decide": plan ended -> keep working registered claims + 3-day grace; referrers see received/missing not files; the three follow-up buttons; "Your day" scenarios; rename the existing "Branch XYZ - house account" names (display only) |
| 3c | **WhatsApp claim intake** - all 29 Sep points decided 30 Sep (OTP once per 30-day session; rest as recommended; never mention plan/quota usage) | Build order in the page: Phase 0 = one intake for the six web doors first |
| 3d | **1 claim raised on behalf of a subscriber whose plan is not active** | Found checking L2 exemptions (origin `ops_on_behalf`, 22 claims, 21 on an active plan). Not wrong by itself - worth a look |
| 3a | **Automatic document reminders are OFF for everyone** (`wa_doc_collection_enabled` never set) | Staff now SEE this in "Follow-up so far". Turning it on is his decision |
| 4 | **Test the radar** with authority-sounding wording once forwarding lands | He said he will; the code is ready for direct and forwarded mail |
| 3 | **Sarathi-AI in its own VS Code session** | Needs the source split first - see below. Today both products are generated from one `sarathi_biz.py`, so two sessions would collide |

### Nidaan — built, not finished
| # | What | State |
|---|---|---|
| 1 | **One intake for every door (Phase 0)** | Review 30 Sep: six web doors check different things around `submit_claim`. Build one `intake` module (checks + after-step) all doors call; then WhatsApp. Fix first: Rs 499 review docs never reach the claim; raw `quota_exceeded_<plan>` shown to subscribers; plan amount cap page-only |
| 1b | **Rs 499 payments confirmed by webhook/recovery write no ledger row** (agent finding, 30 Sep) | Verify on live before changing - the daily Razorpay check may already be reconciling these |
| 1c | **Access, still open** | Staff logins never expire and a re-created login ID can revive an old token (add a "void before" stamp on archive / role change / password reset); archived claims' portal links; 48 h signed doc links; legacy `NIDAAN_ADMIN_TOKEN` API - check whether it is set on the server |
| 1d | **Subscriber profile says "Claims used"** (all-time count) | Founder, 30 Sep: never remind subscribers of usage. Ask whether to relabel or drop it |
| 2 | **Correction Support** — fixing a claim's chain (My Business / subscriber / direct / branch / CP / staff) | Discussed, not designed. Must handle commission and revenue impact |
| 3 | **DPDP 10-day advance reminder** to super-admin Telegram | Raised 27 Sep, not built |
| 4 | **Splitter: rules do not yet re-run on an open job** | Teaching a rule improves the NEXT file. Re-reading the open one is a small addition |
| 5 | **`biz_nidaan_wa_flow` has few tests** | `failure_reason` is tested now (29 Sep); the inbound routing still is not |
| 7 | **Claim sets: hospital case papers** (consent, assessment, IPD file) go to a person | On purpose - an IPD file holds several documents. "DC" is settled: discharge card = Discharge summary (DS), founder 29 Sep. A "Hospital records" type would let the rest be filed; ask him first |
| 8 | **Claim sets: 11 files named `Document_1.pdf` on claim 39** | Nothing to read in the name; the pages decide. Worth checking why a source names every file the same |
| 9 | **WhatsApp: 72 free messages + 22 templates failed in two weeks, reason never kept** | Now kept. Look again in a week: 131047 means the 24-hour rule, 131026 means a number not on WhatsApp - opposite fixes |
| 6 | **@SarathiBizBot token still dead** | Separate from the Nidaan bot, which is fine |

### The app split — where it actually stands
Stages **0–4 are done**: 460 Nidaan routes and 357 Sarathi routes are separated, each product has
its **own app file, own process, own port and own deploy unit** (`nidaan-web@N` on 8031/8032,
`sarathi-new-web@N` on 8021/8022), and nginx sends each domain to its own.

**What is NOT done, and why there is still one folder:**
| Stage | What | Blocking what |
|---|---|---|
| **5** | Sarathi's tables copy out to their own database | Nothing urgent |
| **6** | Sarathi's files move out of the folder | **This is what blocks a separate VS Code session** |
| **7** | Rename the folder and `/opt` path | Cosmetic, last |

The real blocker is not the folder: `nidaan_app.py` and `sarathi_app.py` are **generated** from
`sarathi_biz.py` by `deploy/extract-app.py`. Both products' code still lives in that one file, so
two sessions editing "their own" product would both be editing it. To work on Sarathi separately,
`sarathi_app.py` has to become a **source** file rather than a build output, and Sarathi's code has
to leave `sarathi_biz.py`. That is a real piece of work, not a folder move - estimate and plan
needed before starting.

### Known-fragile, worth a session
- **11 → 0 test failures fixed 28 Sep**, but `deploy/verify-parity.py` still needs a DB argument
  and is not in any routine.
- **`tempfile` imported and unused** in `biz_doc_splitter.py`; `'e' assigned but never used` in
  `biz_nidaan_radar.py` - both pre-existing, both harmless, both noise in every lint run.

---

**Last updated:** 2026-09-29 17:30 IST — 💰 **one price for every payment** (guard before every
charge + guardian after; Khushbu paid Rs 588.82 correctly, the notice said Rs 499); 🔔 subscriber
claim alerts crashed from 21 Sep (fixed + build check); 📄 **splitter**: every format, 40 files,
background reading, mixed files page by page, "Other" kept aside; 💬 WhatsApp claims design page
with the founder's decisions: https://claude.ai/artifact/AvFK6bxXWtmRGPr8XH9FQC

**Before that:** 2026-09-29 13:00 IST — 👥 **referrers see their customers' claims** (staff My
Business + AP dashboard; Trivesh now sees 16 incl. #233); 💰 **daily 9am payment check** against
Razorpay (first run: 28 Sep, 3 payments, all match); WhatsApp claim intake **design** for discussion.
⚠️ Deployed 866e63b at 12:48 IST - inside working hours, against the rule; check the clock first.

**Before that:** 2026-09-29 04:05 IST — 🔔 **notifications fixed**: from 25 Sep the first
person on every list (staff #1, the founder) and every one-person notice were silently dropped;
payment notices now also reach the claim's handler and the referring staff; a branch Level-2
fee's notice says "Payment RECEIVED" first. Test notice to the founder recorded and sent.

**Earlier, 2026-09-29 (early morning)** — 🗂️ **Each document (zip)**: one PDF per
document in every set; **DC = Discharge summary (DS)**; 🧭 **"Follow-up so far"** on every claim
(who asked, when, what next - and says when automatic reminders are off); SOP opens with the
team's action items; short announcement drafted.

**Before that, 2026-09-29 (night)** — 🚫 **"Don't send this page"** and the download now
matches the screen; file names read first (claims 204/39/151: 35/39, 14/28, 12/25 recognised);
⚡ **fast-track** wording + the staff ask in the reader's language; ⏰ scheduled reminders say if
they LANDED, fall back to the approved template past 24 hours, and nudge whoever set them;
complainant-picks-the-time built and deployed **OFF**; page linter hole closed.

**Earlier on 29 Sep:** 📂 **Claim-level sets LIVE**: the three bundles build
themselves from the documents already on a claim, with a per-claim arrange switch. 📘 SOP
updated and fixed (it never opened for a signed-in staff member). 📢 Announcement drafted.

### 🔐 30 Sep — ACCESS ENDS WHEN THE ACCOUNT ENDS; "BRANCH" IS "AUTHORIZED PARTNER"

Founder: *"if anyone not paid or cancelled their subscription, their access should be revoked...
once access changed or any user of nidaanpartner.com deleted or disabled they should not have
access for anything"* and *"we have not converted 'branch' word to 'Authorized Partner'... fix
this on priority everywhere"*.

- **Rename** (`a7e1771`, `d90d920`): every word a person reads - EN, HI (अधिकृत पार्टनर), Hinglish.
  Routes, columns, event keys unchanged. App Health check names renamed in all five places at
  once (their stored state is keyed by name: a renamed check starts fresh). First pass also
  rewrote `API('/branches')` and `?ctx=branch` - caught in review and repaired before commit.
- **`biz_nidaan_access.still_open(kind, key)`** - one per-request answer for subscriber accounts
  (allowlist: active, deletion_pending), Authorized Partners (active) and staff (active, not
  archived); 30 s cache; FAILS CLOSED and does not cache the failure. `_nidaan_bearer`,
  `_branch_bearer` and `_staff_still_active` all call it. Before: subscriber tokens were
  signature-only for 30 days, AP tokens for 7, and the staff check let everyone in on a DB error.
- **Cancel stops the autopay.** `cancel_nidaan_subscription` now asks Razorpay first
  (`stop_razorpay_autopay`, the only copy of that call); if Razorpay will not confirm, super-admins
  get `payment.autopay_stop_failed`. Before: dashboard Cancel stopped nothing at Razorpay and the
  next `subscription.charged` flipped the row back to active. Ops' erase now cancels too.
- **Inactive staff hear nothing:** `tg.notify_staff` and `push_to_staff` join `nidaan_staff`
  on active status - the single doors every staff Telegram message and push goes through.
- **WhatsApp:** identity and code lookups skip suspended accounts and disabled APs.
- Test: `_tools/test_access_revoke.py` (44 checks; sabotage of the allowlist and the WA filter
  fails it). `test_pricing` scan now 18 s (was a 5-min timeout).

### 📂 29 Sep — THE SETS ARE ON THE CLAIM

Staff open the claim → **Documents**, and beside the checklist there is **Ready to send**: the
three bundles built from what is already attached. No uploading, no joining files.

- **One doubtful page holds the whole claim** and is NAMED. A set that is nearly right is the
  dangerous kind — nobody checks it.
- **Corrections stick**, and are keyed to (document, page inside it) rather than the merged page
  number — which moves the moment another document arrives.
- **The arrange switch is per claim, off by default**, and a person can always change a page by
  hand afterwards — the audit case.
- **Teaching a rule is admin-only**; correcting a page is anyone's own work.
- Every change writes to the claim's **own remarks timeline**, beside "Renamed a document".

### 🔧 29 Sep — THE SOP NEVER OPENED FOR STAFF, AND THE CODE SAID IT DID

`_get_staff_from_request` reads only the `Authorization: Bearer` header; the ops token lives in
browser storage and is attached by JavaScript. So a signed-in staff member opening any shared
document in a tab always looked like a stranger — true of `/l2-manual`, `/end-to-end` and the
rest since the first one, while the docstring promised the opposite. I repeated that promise to
the founder as advice. Fixed with a loader that uses the token on that origin; the gate still
decides on the server.

**Previously:** 2026-09-28 (evening, 2) — 📘 **SOP published** at
`nidaanpartner.com/sop-documents` (share key or staff login). 📡 **Email radar re-read**: the
screen went from 8 red + 41 amber of noise to **4 amber**. 🧰 Splitter deployed. ⚖️ Entity
name corrected everywhere.

### 📘 28 Sep — HOW DOCUMENTS ACTUALLY REACH A CLAIM, AND THE SOP FOR IT

Checked against the data rather than assumed. Every document on the system, by how it arrived:

| How | Count | What it is |
|---|---|---|
| Staff attaching by hand | **934** | The overwhelming majority, from before source tracking |
| Authorization PDFs | 59 | Generated by us, automatic, well named |
| **Official WhatsApp number** | **20** | Since 22 Sep - the automated path, and it works |
| Claimant's own claim page | 25 | They upload on the link we send |

**So the answer to "which are they doing" is: both.** The automated WhatsApp path is live and
attaching documents to claims by itself - 20 so far, most recently today. But 934 hand-attached
documents say the habit is still the phone call and the manual attach.

**What the automated path does today:** claimant sends to our official number → matched to their
claim by phone number → attached → they get *"Got it - [file] attached to your case #123"* → the
associate is notified. If they have two open claims it asks which. The file **keeps the name it
arrived with**.

**What it does NOT do:** rename by document type. That happens in the Splitter, where a person
confirms it. Deliberate - and the right order, because the rules the Splitter learns are what
will eventually make automatic naming trustworthy.

🔧 **A regression of mine, found and fixed today:** my intake change on 28 Sep stored every
inbound batch as `document.pdf`, throwing away the sender's own filename. A claimant's file is
often already called `Insurance_Policy_Schedule.pdf`, which is the single best clue anybody -
staff or the Splitter - gets about what it is. It now keeps that name.

### 📡 28 Sep — THE RADAR, RE-READ

| | before | after |
|---|---|---|
| 🔴 red | 8 | **0** |
| 🟡 amber | 41 | **4** |
| ⚪ cleared | 6 | **51** |

**All 8 "act now" items were false alarms** - six our own system emails, two Google notices. 55
rows re-read; 3 that a person had already acted on were left alone; the previous flags are backed
up on the server at `/tmp/radar_flags_before_*.json`.

**On the rules that "were not working":** they were never saved. Both `priority_senders` and
`custom_rules` are empty, and there is **no `radar.config` entry in the audit log, ever** - so
nothing could have conflicted with the built-in lists. The save handler itself is correctly wired.

The division is now written on the settings screen: **the authorities are in the code** (Ombudsman,
IRDAI, `gov.in`, the statutory phrases - facts about the regulator, not preferences), and **the box
is for what changes** (a particular insurer, an officer's address). They cannot fight, because
what is typed is additive: a rule or a listed sender only ever makes the radar show *more*.

**Previously:** 2026-09-28 (evening) — 🧰 **The doc splitter set-builder is BUILT**:
inbox of three, review screen with the three ready-made sets, and a rules screen you can read and
undo. ✅ Sudoers fixed — and it uncovered that **deploys had been skipping live sites at random**.
🔴 Not deployed yet.

### 🧰 28 Sep (evening) — THE SPLITTER NOW HANDS BACK SETS, AND REMEMBERS CORRECTIONS

Everything below is built, tested and committed. **Not deployed** — say the word.

**The inbox.** Three files open per person. A fourth is refused and *names* the one it would put
away, offering to open or close it; closing confirms first and archives. Jobs now **belong to
somebody** — a real hole, this: all four splitter routes asked only "are you staff?", so anyone on
the team could open anyone else's uploaded claimant documents by job id. Refused with 404 rather
than 403, so the endpoint cannot be used to learn whose uploads exist.

**The review screen.** Every page with what it was read as, and the three sets those types compose
into — **CIO documents**, **All documents merged**, **Claim set** — each downloadable. A set is
composed **by type, not by page range**: "every bill in this file" is pages 4, 9 and 17, so this
needed a new cut-by-page-numbers function. The sets recompute after every correction, which is the
whole reason for showing sets rather than a pile of files — you can see what your correction did.

**Two taps, not drag-and-drop.** Tap the page, tap the right name. Half the team is on a phone in a
hospital corridor; dragging is a desktop idea. Each type is its **name**, never an icon.

**Read once.** Classifying costs ~15s a scanned page, and the answer used to be thrown away —
reopening a 40-page bundle cost ten minutes again. It is saved beside the working PDF as plain
JSON. That is also what makes a correction stick: a re-read would silently put the machine's
answer back.

**The rules screen.** A correction can be taught, and then it reads as a sentence: *"filed as a
Final bill when at least 4 of these words appear: total, payable, consumables… — taught by Asha,
used 12 times"*. With an undo next to it, which **archives** — "removed" and "turned off" are
different promises.

**The six-hour delete is gone.** Every upload used to run a sweep removing any job folder older
than six hours — no owner, no record, nobody asked, on a working copy of a real claimant's hospital
file. Nothing automatic replaces it: `reclaimable()` *reports* what could be freed, and
`discard_job_file()` refuses a live job even when asked directly.

**Tests:** `test_doc_store` (30), `test_job_files` (16), `test_docsplit_routes` (23),
`test_doc_review` (20, end-to-end on a real PDF), `uitest/splitter-inbox.js` (31). Each was proven
to fail against the code as it was.

**Previously:** 2026-09-28 (afternoon) — 🚨 **The claimant portal had been dead for two
days** (a module-name collision I caused on 26 Sep) — found, fixed, **deployed** and verified from
outside. 🍪 **Cookie consent shipped** on advisor and policyholder pages: Google Analytics no
longer runs until somebody says yes. 🔒 The bot's "Ask AI" no longer sends task records out.

### 🚨 28 Sep — THE CLAIMANT PORTAL WAS DEAD FOR TWO DAYS, AND THE DEPLOY WAS NOT DEPLOYING

**What you saw:** claim 153, *"this link is invalid or has expired"*. The link was perfect.
`/nidaan/claim/api/verify/where` had been returning **HTTP 500 to every claimant** since 26 Sep
13:10 IST — three different people, two different claims, every request, all day.

**Cause, and it was mine.** I added a staff-authorisation module named
`biz_nidaan_claim_access.py` — a name already used by the module that verifies a COMPLAINANT by
sending a code to the number on their claim. It did not shadow it, it replaced it: 375 lines gone,
along with `channels`, `start`, `check`, `SESSION_MIN` and `PREVIEW_MIN`. Restored byte-for-byte
from `04cc829`; mine is now `biz_nidaan_claim_authz.py`, with the collision written into its
docstring.

**Three things let it run for two days. All now closed:**
- `verify-code-email` and `verify-22sep-list` would have caught it on **day one**, but were in
  nobody's routine → now `npm run check:portal`, inside `check:all`.
- Nothing checked that a `module.attribute` a route reaches for actually exists → new
  `check:attrs`: 655 references across 43 modules. It runs on **3.14**, because on 3.13 most of
  these modules will not import and it would pass without looking at anything.
- **`auto-deploy.sh` restarted `sarathi-web@1/2`, which has served neither domain since the
  split.** Every deploy since 27 Sep pulled the code and loaded none of it. It now rolls
  `nidaan-web@N` (8031/2) and `sarathi-new-web@N` (8021/2) as well, one at a time, health-gated,
  and a unit that is not installed is skipped **with a line saying so**.

**The second fault made it worse.** The page turned our 500 into *"your link is invalid — contact
NidaanPartner for a fresh link"*, so claimants asked staff for new links, staff reissued, and the
new links failed identically. Now 401/404 means "ask us for a fresh one" and 5xx means "this is
our problem, your claim and documents are safe, you do **not** need a new link" — English + Hindi.

**Verified from outside after deploying:** magic link 303, portal 200, `verify/where` 200 with the
right claim and both masked channels, a bogus token still refused 401, sarathi-ai.com still up.

### 🍪 28 Sep — COOKIE CONSENT, ON BOTH AUDIENCES

Google Analytics had been loading on five public pages **the moment they opened**, setting `_ga`
cookies on people who had never been asked. A banner on its own would have been decoration over
tracking that had already started.

- `nidaan_ga.js` loads **nothing** until analytics is allowed; refusing later **deletes** `_ga`.
- The banner is on 12 advisor and policyholder pages, and loads **before** GA — a gate that loads
  second is not a gate.
- **Accept all / Only essential / Choose what to allow**, same size, side by side. Nothing
  pre-ticked. Ignoring it consents to nothing.
- **Cookie policy** at `/nidaan/cookies`, English + Hindi, listing the cookies we really set —
  read out of the `set_cookie` calls, not written from memory. A policy naming cookies we do not
  use is a false statement to a regulator.
- **Cookie settings** in the footer of every page including the claimant portal, so a yes can be
  withdrawn. 44 checks, proven to fail against the ungated version.

🔴 **Still your call:** `affiliate_token` is classified **essential** — "remembers which
partner referred you, so they are credited". Commission depends on it. If your counsel would
rather it were optional, that is a one-line change; but a visitor who then refused would cost that
partner their credit.

### 🧪 28 Sep — A TEST SWEEP THAT MEANT NOTHING

Eleven tests had been failing for long enough that nobody read the output — and a sweep nobody
believes is where a real failure hides. It did: not one check said a word about the dead portal.
`_tools/test_*.py` held three different things: local logic tests, tests that need the live
database, and manual toolkits (one of which deletes an account).

- Server-only tests now **skip with a sentence saying what was not checked** and how to run it
  there. Skipping is honest; failing for the wrong reason is not.
- `test_step5_pay` prints its usage instead of crashing on `sys.argv[1]`.
- `test_doc_checklist` was both stale and broken: its fixture never created the documents table
  its module joins to, and its numbers were from when a health claim needed 5 documents — it
  needs 8 (7 required + `other_docs`). **13 passed/9 failed → 23 passed/0 failed.**
- `test_wa_flow` **retired**: it tested a Marathi language menu and helpers the rewritten module
  no longer has. 🔴 **`biz_nidaan_wa_flow` is now untested** — written here so the gap stays
  visible rather than quietly disappearing.

**Previously:** 2026-09-28 (morning) — 🔒 **No claim document goes to Google any more.**
Intake, the splitter and the WhatsApp pipeline now read pages **on our own server**, and nothing is
filed automatically — a person says what each document is. 🔴 **Not deployed** (team is working;
after 6pm IST).

### 🔒 28 Sep — MEDICAL DOCUMENTS NO LONGER LEAVE THE SERVER, AND THE MACHINE NO LONGER FILES THEM

> *"nidaanpartner.com carries medical data, so we cannot plug AI directly to see doc and identify
> and do the all doc splitter bot work live."* · *"make it simplify and staff to use it rather
> multiple automations keep staff confused about process."*

**What was happening until today.** Every document a complainant sent — discharge summaries,
hospital bills, lab reports — was uploaded to Google's Gemini to be named, and anything the model
was 75% sure of was **ticked off the checklist automatically**. The staff splitter did the same
with whole bundles, and an "🤖 AI tasks" panel would send an entire hospital file out to be
summarised.

**Two separate decisions, and the second one matters more.**

1. **Nothing leaves the server.** Reading is now done here — the PDF's own text layer where there
   is one, local `tesseract` (English + Hindi) where there is not.
2. **Nothing is filed automatically.** Measured on this firm's own 1,242 documents, the local
   reader agrees with staff **about two times in three**. That is a useful *suggestion* on a screen
   where somebody presses yes — which is why the Telegram upload still offers one — and a
   mis-filed claim on the claimant path, where nobody checks. So intake stores the document and
   asks a person. **A guess that is right two times in three is worse than no guess**, because no
   guess is honest and brings somebody to look.

**What a complainant still hears** is the one thing only they can fix: if not a word can be read
on what they sent, we ask for a clearer photograph. That needs no classification.

**One trap this created, and closed.** With nothing ticked automatically, the outstanding list is a
snapshot from *before* a person looked — so an unqualified "Still needed: discharge summary" would
go to somebody who had **just sent** exactly that. The WhatsApp reply now says our team will open
them and update the list, usually within a few hours, and frames what is outstanding as *"as far as
we know … if you have just sent any of these, it will come off this list"* — in all three
languages.

**Two real faults found by the new tests rather than by the team:**
- **OCR would have taken the site down.** The old call was one network round trip; reading pages is
  blocking CPU work at ~15s a page. Awaited straight from a request, one scanned 40-page bundle
  would have frozen **every other request on that worker** for ten minutes. Now: a worker thread,
  plus a **120s OCR budget per file** (`NIDAAN_OCR_BUDGET_S`) after which remaining pages are
  returned honestly marked "not read" rather than timing out.
- **An unread page was inheriting its neighbour's document type.** A page nobody could read was
  being called "page 2 of the bill above" and would have been filed into that bundle. It now stays
  unknown and goes to a person.

**Removed:** the `🤖 AI tasks on this file` panel and its two routes, and a dead Gemini
`classify_document` in the WhatsApp orchestrator that nothing had called for weeks.

**The splitter review screen now reads as three numbered steps** rather than "the AI split it into
the documents below", per *"we need to run staff step by step … kind of a baby step."*

**Tests:** `_tools/test_intake_no_ai.py` (21 checks) and `_tools/test_ocr_budget.py` (8 checks).
Both were **proven to fail** against yesterday's code — and the first version of the no-tick check
passed on this machine for the wrong reason (no API key), so it now forces a *certain* matcher and
asserts no classifier is consulted at all.

**🔴 Two things for you:**
1. **The bot's "🤖 Ask AI" still sends task records to Gemini** — titles, names and up to 220
   characters of a task's description, which here routinely name a claimant. No documents, and out
   of scope for today's change, but it is the same question and it is your call. Options: leave it,
   strip names before sending, or move it to the local engine (it would get notably weaker).
2. **11 behaviour tests were already failing before today** and are not related to this work: they
   need a schema-bearing database this dev checkout does not have, and `test_wa_flow.py` calls
   `parse_language_choice`, which no longer exists. Worth a session to fix or retire — a red suite
   teaches nothing.

**Previously:** 2026-09-26 (afternoon) — ✅ New bot **@NidaanPartnerOpsBot** live and verified (`getMe` 200, `poll_active=1`). **"Ask everyone to connect" deployed** — 23 pending, 23 reachable. ✅ **All six Telegram pieces built and tested** — claim authorisation, rate limits + audit, document upload, bot wiring, splitter, Hinglish. 🔴 **Not deployed.**

### 💰 26 Sep — REVENUE WAS Rs 11,776 TOO HIGH (`da50597`, built, NOT deployed)

Founder asked why he keeps getting "One payment recorded twice" emails. **The email he
screenshotted was a false alarm. What it was mixed in with was not.**

| | |
|---|---|
| Revenue shown | ₹ 86,377.98 |
| Actually collected | ₹ 74,601.98 |
| **Phantom** | **₹ 11,776.00 (13.6%)** |
| Customers charged twice | **none** — Razorpay reports `paid_count=1` for all 14 |

**The false one (#127/#128):** Razorpay confirms two *different* captured UPI payments, claims
**214** and **213**, a branch clearing two claims 29 seconds apart. The rule matched on
account + source + 10 minutes and never looked at the claim or the payment id.

**Cause of the real one:** `record_payment()` is idempotent on `dedup_key`, and the subscription
path built it as `(razorpay_payment_id or razorpay_subscription_id)` — so the key depended on
*which id that code path happened to hold*. Activation writes `sub_xxx`, webhook writes
`pay_yyy`, neither finds the other. Three key shapes for one event.

**Two things worth keeping from how this was fixed:**
- **Not fixed by changing the key shape.** That would orphan every existing row and the next late
  webhook would write a *third*. The keys stay; the existence check got smarter.
- **The first version of the fix was wrong**, caught by running it against live data before
  believing it: matching on `source` found only 9 of 14, because five were a `subscription` row
  and a `subscription_renewal` row **four seconds apart**. A renewal four seconds after
  activation is not a renewal. The real invariant is simpler — *every real charge has a Razorpay
  payment id*, and a row without one is a placeholder. The real payment now **completes** it in
  place rather than being refused (refusing would keep the row with no payment id and the rounded
  ₹589.00 where the charge was ₹588.82).

🔴 **AWAITING THE FOUNDER:** the 14 phantom rows are still live. Marking them
`status='duplicate'` excludes them from Revenue, deletes nothing, and is reversible — but it is
financial data, so it is his call. Revenue will **drop by ₹11,776**, which is the true number.

### 🗓️ UPCOMING — flagged by the founder 26 Sep, for the foundation-strong programme

1. **🟢 Lokpal bucket, end to end** — internal statuses, query-raising mechanics like the other
   buckets, and the path through to settlement. Building next week.
2. **🟢 /superadmin ops needs organising** — "too messy, not user-friendly". Align it, remove or
   merge features, make it feel like a modern, elite app rather than an accumulation of screens.
   *After* end-to-end is built.
3. **🟢 A team of bots on auto-pilot** — watching each department the way a person would: are
   logins working, are payments completing correctly, is the L2 claim queue moving as expected.
   Alert only when a human is actually needed. Discussion to open.
4. **🟡 Legal + DPDP compliance pages** — Terms, Privacy, Cookie Policy, and being genuinely
   DPDP-compliant rather than only claiming it. **Discussion first, founder finalises, then
   execute.** See the compliance note below.

### 📦 26 Sep — TELEGRAM: DOCUMENT UPLOAD, SPLITTER, HINGLISH

**The finding that saved the most work: the bot did not need rebuilding.** Only the Telegram-side
bot was deleted; all 2,277 lines survived. It already does tasks (pending/by me/involved/archived/
create), find claim, claim notes, stage changes with confirmation, approvals, leave, WFH, AI ask,
broadcast, audio guide, **voice notes transcribed and routed like typed text**, and **133
translated strings** EN/HI with role-aware menus. It needed the 23 staff reconnected, not a rewrite.

**Decisions taken with the founder (26 Sep):** team members may upload only to claims they are
**on**; the bot **shows the claim's current document status and waits for a yes** before saving;
**security foundation first**, then upload, then splitter, then Hinglish.

| # | Piece | State |
|---|---|---|
| 1 | `biz_nidaan_claim_access.py` — "may this person touch this claim" | ✅ `daec213`, 20 checks |
| 2 | `biz_nidaan_bot_guard.py` — rate limits + audit trail | ✅ `ceb6508`, 34 checks |
| 3 | `biz_nidaan_bot_docs.py` — look, warn, wait, save | ✅ `45239b5`, 21 checks |
| 4 | Bot wiring: menu, claim number, file, confirm | ✅ `430893c`, 34 checks |
| 5 | Doc splitter via bot | ✅ `0191160`, 21 checks |
| 6 | Hinglish — all 150 strings + 3-way picker | ✅ `2f380f5`, 22 checks |
| 7 | Capabilities registered (upload / split / language) | ✅ 76 total |

**🔴 ALL SIX BUILT, NOTHING DEPLOYED SINCE `04cc829`.** Awaiting the founder's go.

**Decisions he took on the way:** Hinglish = **Hindi in Roman letters** (not English with Hindi words); the splitter **sends pieces back to check** rather than attaching them straight to a claim — a wrong split on a real case is unpicked by hand.

**What the last three pieces found:**
- The file check had to sit **before** the "no text, give up" line — a document message carries no text, so behind it every photo anybody sent would have vanished in silence.
- `telegram_lang` is **shared with the web profile and the daily summary**, so Hinglish had to land in the endpoint pattern and the profile buttons too, not just the bot.
- `biz_nidaan_daily_summary.py` already used the word **"hinglish"** — so that is the value, rather than a shorter code invented here that would mean two things in two modules.
- A check in `test_bot_docs` grepped for `"key":` and broke when the table was rewritten with single quotes. The code was fine; the check's assumption was not. It parses now.

**What the foundation work actually found, none of it theoretical:**
- **Nothing in this codebase could answer "may this person touch this claim?"** Web and bot both
  decided by role alone; a claim id was never checked against the person holding it. Fine while
  every door was a signed-in browser; not fine once a phone can attach a file by typing a number.
- **The bot had NO rate limiting of any kind.** Every HTTP route sits behind slowapi; the bot is
  a long-polling loop, so none of it applied. A linked phone could ask Gemini a thousand
  questions or walk claim numbers one by one, unthrottled and unrecorded.
- **`clnc:` (claim note confirm) had no role check**, leaning entirely on server-side pending
  state, while its sibling `clsc:` always had one. Protection by state is one code path away
  from no protection.
- **`commit()` imported the PDF library before checking authorisation** — so refusing someone
  depended on an unrelated dependency importing. The cheapest answer (no) must never be the one
  most likely to fail.

**Design rules now written into the code**, for the AI-driven rebuild to inherit:
- Authorisation **fails CLOSED**; notification routing **fails OPEN**. Opposite on purpose: a
  wrong yes is somebody's medical file, a wrong yes there is a noisy phone.
- Bot **navigation** fails open (a broken limiter must not take the bot down over menu taps);
  **money, files and claim lookups** fail closed.
- "That claim is not yours" reads **identically** to "no such claim" — otherwise the bot is a
  way to enumerate real claim numbers from a phone.
- Refusals are audited as well as successes; a trail holding only successes cannot show an attempt.
- Telegram is a **door onto** `doc_intake.accept()`, never a second intake.

**Previously:** 2026-09-26 (02:45 IST) — ✅ **DEPLOYED & VERIFIED** (`83a8545`). The settings leak is closed, proven from outside with a genuine **team_member** session: 49 settings returned, **zero credentials**, `task_create_min_role` and `branch_l2_fee` still delivered. Worker now logs *"❌ Telegram REJECTED the bot token"*; `telegram_poll_active=0`, `telegram_last_error=Unauthorized`, so the panel shows the red banner instead of a green lie. Both products serving correctly, 0 tracebacks.
🔴 **@NidaanOpsBot is DELETED** — replacement bot still to be created **from a company-owned Telegram account**. Safe to do now that the leak is closed. Needs the founder in BotFather; see below. App-side honesty fix built and committed.

### 🚨 26 Sep — THE BOT IS GONE, NOT JUST REVOKED. AND WE WERE LEAKING ITS TOKEN

**The bot account is DELETED.** Telegram shows the @NidaanOpsBot chat as *"Deleted Account"*, and
the founder's BotFather `/mybots` lists only @GoLuQ_client_bot, @GoLuQ_Bot and @SarathiAIBot —
**@NidaanOpsBot is not there.** So this is not a rotated token. The bot no longer exists.

**Why it is not in his BotFather.** `nidaan_audit_log` #165: the bot was configured in our app on
**21 Jul 2026 06:29 UTC by ANNAPURNA KASERA** (staff 19, super_admin), `same_bot=False` — the
first and only time a bot was set. BotFather lists only the bots owned by the account you message
it from, so @NidaanOpsBot was almost certainly **created from her personal Telegram account**, not
the founder's. *Inference from who pasted the token — ask her to confirm.*

**Nothing in our app did it.** Zero audit rows in the whole deletion window (25 Sep 11:00–15:00
UTC). A bot token grants total control of a bot but **never the right to delete it** — that needs
the owning Telegram account in BotFather. Deletion and disclosure are separate events.

**🔥 THE GOVERNANCE FAULT, which is the real lesson.** A production bot carrying customer names,
mobile numbers, disputed amounts, payment alerts and leave requests was owned by **one
individual's personal Telegram account**. BotFather ownership **cannot be transferred**. So the
company never controlled its own notification channel and had no recovery path when that account
or bot went away. **@SarathiBizBot is dead the same way** — 672 criticals in 7 days, and it is
also absent from his list.

**🚨 AND WE WERE HANDING THE TOKEN OUT (`3b2bbc2`, fixed).** `nidaan_ops_settings` holds policy
and credentials in one table. `get_all_ops_settings()` returned all of it, and five endpoints hand
that to the client — including `GET /nidaan/ops/api/ops-settings`, which needs only
`_require_staff(request)` (**any role**) and which the ops page fetches **whenever anyone opens
the Tasks panel**, to read one value: `task_create_min_role`.
→ So the **live bot token was delivered into the browser of all 23 active staff** (7 team members,
13 sub super admins, 3 super admins), routinely, for as long as that code existed. `doc_share_key`
went with it. **Disclosure is proven; misuse is not.** The realistic risk is **impersonation** —
anyone holding it could send messages to all 21 linked staff *as the bot*, with convincing
approve-style buttons.
→ Fixed in the **accessor**, not the five endpoints, because the sixth is not written yet.
Credentials are **omitted**, recognised by NAME so a future secret is covered, while a timestamp
that merely sounds alarming is not withheld. 11 checks, watched failing on exactly the four that
count.

**🔴 FOUNDER ACTIONS, in order:**
1. **Revoke the token visible in your second screenshot** (@GoLuQ_client_bot) — it is in a shared
   image now. BotFather → that bot → **Revoke current token**. Never paste a token into a chat.
2. **Create the replacement ops bot from a COMPANY-controlled Telegram account** — a number the
   business owns, not any individual's. That account's phone number *is* the ownership.
3. Paste it into ops → **✈️ Telegram Bot**. ⚠️ **This is a different bot, so all 21 staff links
   are cleared and everyone must reconnect** — unlike a same-bot token swap. That is correct
   behaviour (a chat_id only means something to the bot that issued it), not a bug.
4. **Ask Annapurna what happened to the bot** — plainly, not as an accusation. It may be entirely
   innocent (a deleted account, a changed number, a mis-tapped `/deletebot`).
5. **Rotate `doc_share_key`** after deploy — it was in the same leak. It gates internal
   documentation pages only (checked: not claim documents), and rotating **breaks existing share
   links**, so it is your call.

**Still open:** whether any tenant/firm bot token is reachable the same way (`tg_firm_bots`,
`SELECT * FROM tenants` helpers) — **not audited yet, not claimed clean**.

### 🔴 26 Sep — THE OPS TELEGRAM BOT IS DEAD, AND THE SCREEN SAID IT WAS FINE

**What happened.** Telegram answers **401 Unauthorized** to every call with the stored
@NidaanOpsBot token. Last healthy health check **25 Sep 13:00:44 UTC**, first failure **13:15:45**
— so the token was revoked or regenerated in **BotFather at about 18:30–18:45 IST on 25 Sep**.

**Not ours, and checked rather than assumed:** the stored token is well formed, its bot id still
matches `8728919108`, it is **not** in the repo or in git history, it was **never** printed to the
journal (`grep -c` = 0), **no deploy ran** in that window, and the ops audit log has **zero** rows
in it. Nothing in this system touched it.

**🔴 FOUNDER ACTION — one minute, no deploy needed, nobody has to re-link:**
1. Telegram → **@BotFather** → `/mybots` → **@NidaanOpsBot** → **API Token**
   (if it only shows a revoked one, press **Revoke current token** to mint a fresh one).
2. NidaanPartner ops → **✈️ Telegram Bot** → paste it → save.
The worker picks it up within ~8 seconds. Because the **bot id is unchanged**, all **21 connected
staff stay connected** — `ops_telegram_save_token` only clears links when the bot *identity*
changes, and this is the same bot.

**What WAS ours — the silence.** The health monitor did its job: it calls `getMe`, marked it
**critical**, and emailed once before the throttle correctly took over. The screen is what lied.
- `run_polling_loop` treated 401 exactly like a timeout — sleep 3s, retry, **log nothing**. Five
  and a half hours, roughly **six thousand** calls with a dead token, not one line written.
- `telegram_poll_active` was set to `1` the moment a token was **seen**, never when Telegram
  **answered**, and never cleared on failure.
- So **Settings → ✈️ Telegram Bot showed a green "✅ Connected to @NidaanOpsBot"** the entire
  time. That banner asked whether a token had been *saved* — configuration — and reported it as
  if it were delivery. Exactly the rule in `CLAUDE.md` §2.

**Fixed (`33f9702`, committed, not deployed):** a 401/403 is told apart from a blip and reported
**once** with Telegram's own words and the time; the loop backs off to 60s instead of hammering a
dead token; the flag the screen reads now means *"Telegram answered us"*; the panel shows a red
banner naming the reason, the fix, and that the connected staff survive. 11 checks in
`_tools/test_telegram_token_revoked.py`, watched failing before it passed.

**Also visible while looking:** the OTHER critical, **"Master Bot not running"** (the Sarathi
`@SarathiBizBot`), has been raised **672 times in 7 days and emailed 524 times**. That is the
source of the health-alert noise, it is the separate known bad token, and it is still open.

**Previously:** 2026-09-25 (afternoon) — ✅ **the notification controller is built and checked**; the switches on Settings → 🔔 Notifications are live in code. 🟡 **awaiting deploy, after 6pm IST** (founder: no deploying while the team is working).

**Previously:** 2026-09-22 — 🟢 **CUTOVER COMPLETE. NidaanPartner.com and Sarathi-AI.com are LIVE on Oracle Mumbai (161.118.186.201, aarch64).** Contabo parked as rollback, untouched.

### ✅ SHIPPED 2026-09-22 (3) — the founder's 16-item screenshot list
Grouped by ROOT CAUSE rather than by screenshot, because several were the same fault twice.

**✅ Batch 1 — dates (#6, #7, #13).** Two reports, one bug, and it is not obvious: an
`<input type="date">` fires `change` as **each segment** is completed. Proven with a real
keyboard (`uitest/date-typing.js`) — typing `28` into the day of 2026-05-25 fires change twice,
first with **2026-05-02**, then 2026-05-28; typing the year 2026 fires with **0002**, 0020, 0202.
So the app was saving, and validating, what somebody was still typing:
  - **#6** a correct discharge of 28-05-2026 reported itself as before the admission;
  - **#13** NP-39 recorded its escalation as **"0002-09-22"** — the year 2.

  Fixed at both ends: the screen sends a date when the person has FINISHED (on leaving the field,
  or when they stop), and `set_field` refuses anything outside 1900-2100 whatever the route —
  because a rule that lives only in a browser holds until somebody writes a second one.
  **#7** added in the same place: a rejection cannot predate the admission it rejects. Checked
  first — of 4 live claims holding both dates, exactly **one** breaks it: NP-39, the claim in his
  screenshot. No claim is holding an impossible date, so nothing needed repairing.

**✅ Batch 2 — queries (#10, #11, #12, #15, #16).** Three faults, all about a query outliving
its bucket.
  - **#10** the server accepts a draft query being answered only from **Pending Draft**; the
    screen only offered the button on **Live Cases**. One rule written twice, disagreeing — so
    the button was never anywhere it worked and a query could be raised and never answered.
  - **#11, #12, #15** leaving Pending Draft marked an **open** query "resolved", using the move
    note as its answer — so Escalation showed a green *Draft query resolved* for a query nobody
    answered, for the rest of the claim's life. The query now **ends** with the bucket, and if it
    was still open the remarks say so in those words.
  - **#16** an escalation query had no way back to Escalated. There is now the other half of the
    button.
  - **⚠️ Two live claims were already wearing the badge** — NP-39 and NP-118. Cleared by a
    one-time correction; **live worker log confirms `'fixed': 2`**.

**✅ Batch 3 — the Live bucket (#5, #8, #9, #14, and the sequencing).**
  - **The sequencing**, his headline: **five of his fifteen are not bucket fields at all** —
    Company Name, Policy type, Disputed Amount and Assign To are columns on the claim, so they
    were never in the list the bucket renders. The screen is now built **from `CSR_GIST`**, which
    already holds his fifteen in his order, so the form, this screen, the assessment sheet and the
    case report all read the same way round. Proven by `uitest/live-sequence.js`.
  - **#5** the case email was asked for **twice** on a Live Cases claim — once in the block that
    owns it, once in the generic field list, because it IS a Live Cases field.
  - **#8** moving into Pending Draft always arrives on **Drafting**.
  - **#9** Pending Docs off the rail — guarded on being **empty**, so it can never strand a claim.
  - **#14** the three reminder dates **back**, as dates a person types, not required to move on.
  - **Live worker log confirms `'fixed': 4`.**
  - The six page suites moved out of a scratch folder into `uitest/` — **nine browser suites**
    now, runnable by anyone.

**✅ Batch 4 — the complainant's side.**
  - **#3 was not "failing to send" — it never tried.** `/portal/ensure`, which is what
    *Re-issue & copy link* calls, created the link, called `mark_link_sent()` and emailed nobody;
    its own docstring said *"Does NOT itself email yet"*. So the screen reported **"sent 2×"** for
    two emails that were never written. It now sends, and says which of create/send happened. The
    link is still returned when there is no email on file — copying it into WhatsApp is a real
    thing staff do — but that case says so instead of claiming success.
  - 🐞 **The test for #3 found something bigger.** `send_greeting_email()` read `insured_email`
    and nothing else. The complainant is often a different person, and the dashboard, documents
    and fee authorisation are all **theirs** — so putting their address on a claim sent the link
    to the insured, or to **nobody** while the screen showed the claim as having an email. It now
    goes to the complainant's address when there is one, addressed to their name.
  - **#3b** putting an email on a claim that had none sends the link **there and then** — only
    when the address actually changed, and never allowed to fail the edit. The screen says whether
    it went, because *saved* and *they were told* are different things.
  - **#1** the Edit button edited the **insured's** phone; the founder's arrow was on the
    **complainant's**, which was editable nowhere. Name, phone and email, together.
  - **#2** the code email now names the page the code is typed into, as a button with the plain
    address under it. **Deliberately not a sign-in link** — the code is the security.
    `deploy/verify-code-email.py` renders the template, because a stray `%` in the new CSS would
    only fail at the moment somebody is waiting to get in.
  - **#4** a document now carries `submitted_at`: NULL while they are still choosing, stamped on
    **Save and submit**, which asks first. Their page tags each unsent file, explains in an amber
    box that we do not have them yet, and afterwards says plainly that we do and they can close
    the page. Staff **see** the unsubmitted files, marked *not submitted* — a staffer on the phone
    needs to see what is happening at the moment somebody rings up, and the founder's report IS
    that moment. Staff are told **once**, on submit.
  - ⚠️ **The test caught my own migration:** the backfill ran on EVERY save, so saving one file
    stamped every file somebody was still choosing — quietly undoing the feature while looking
    like it worked. It now runs only when the column is first created.
  - **Coming back needs nothing new:** the greeting email already carries their claim-page link
    and the code email now names the page, so somebody who removed two of four files can return,
    sign in with a code, and add more.

### 🟡 RAISED 23 Sep (afternoon) — built locally, AWAITING DEPLOY

⚠️ Two commits are on `master` and **not on the server**: `6c72f52` (undo button) and `114d60a`
(status colours). The deploy step and live-DB reads were both refused by the sandbox this
session — they need the founder's go-ahead. Nothing below is live yet.

1. ✅ **Status colours: weight, not just contrast.** — `114d60a`
   The fault was structural, not a bad hue: thirteen statuses shared one recipe (12% tint, 25%
   border), so a claim blocked on a complainant looked exactly like one that settled three weeks
   ago. Colour said WHICH status and nothing said whether anybody had to act.
   - **Three weights now.** Loud = solid fill, white text, only for blocked-on-somebody-outside
     (Review Query, Overdue). Live = 18% tint + firm border, work is moving. Done = 7% tint +
     hairline, settled and filed.
   - **Written once, in `nidaan_design.css`.** The rules were duplicated in `nidaan_ops.html`
     and `nidaan_dashboard.html` with *different tints in each* — which is how the same status
     came to look heavier on one screen than the other. Each page keeps only its own SHAPE.
   - **Withdrawn/Closed were 3.15:1 on dark**, under what small bold text needs. `--nd-text-muted`
     instead of `--nd-text-faint` → **4.95:1**. Solid fills carry white text at 5.1:1 and 6.5:1.
   - **`?v=6` on all eleven pages.** Cloudflare holds `/static` for 7 days; shipping without the
     bump would have changed nothing for anyone who had been there before.
   - **Checked, not eyeballed.** `uitest/status-pills.js` now measures PRESENCE as well as
     contrast and asserts the ramp in both themes; `verify-claim-statuses.py` (18 checks) refuses
     a page that forks the colours or asks for a stale version. **Both new checks were proven to
     fail before being trusted.**
2. ✅ **Advisor & Channel says WHO, WHEN and HOW** — `2bc9ce0`
   ⚠️ **The headline was WRONG on 64 claims.** The panel said *"Came in as: 🏢 Branch ·
   SP-GJG7BA"*. **SP-GJG7BA is not a branch — it is TAMANNA VASHISHTHA.** Under the
   staff-as-branch referral scheme a colleague's referral code sits in the same column an office
   code does, and the screen called all of them a branch. Live data: **64 claims carry a STAFF
   referral code, 23 carry a real branch.** The most common thing that screen said about a
   claim's origin was wrong.
   > My first attempt made it *worse* — it reported "no branch on file for SP-GJG7BA" on 64
   > claims. True, and useless. Caught by running it against every SHAPE of claim we hold before
   > it reached a screen, not the one claim I picked.
   - `biz_nidaan.claim_origin()` — **one resolver**. The claims LIST already turned a code into a
     name; the DETAIL never did, so the one screen where somebody works a claim was the one that
     could only show a code.
   - staff codes resolved **before** branch codes · *"Raised on the branch portal"* not *"a
     branch raised it"* (how it arrived and who brought it are two facts) · a hand-typed referrer
     **name** still finds its person · **59 claims have no channel at all** and those say the
     answer was WORKED OUT — a blank line reads as "nothing to see" instead of "never recorded"
   - branch name + city + contact · subscriber name + number · who raised it and via what · the
     referrer · **and WHEN** — all in both languages.
   - `_tools/test_claim_origin.py`, 20 checks.
3. **Payment notifications, pass AND fail.**
   - super-admins: every payment, but **not repeated into irritation**
   - branch / my-business / subscriber / CP: only THEIR claims
   - every failure **recorded in Payment Follow-up** with the real reason, and repeats of the
     same failure kept as history + attempt count, so it can be worked rather than just seen
4. **Tagging a staff member on a claim → bell + Telegram to THAT person**, not everyone.
   Code read end to end and it is correct: `ops_add_note` splits the room in two — the
   @mentioned get `claim_note.mention`, everyone else already watching gets
   `notify_claim_watchers` with the mentioned explicitly excluded, so nobody is told twice and
   nobody uninvolved is told at all. Routing verifier: 29 checks, 0 wrong. **Still unproven:**
   whether the message actually ARRIVES — that needs a live read of
   `nidaan_notifications WHERE event_key='claim_note.mention'`, which the sandbox refused. This
   is exactly the failure class that cost us two outages (a provider returning 201 and delivering
   nothing), so it stays open until an OUTCOME is read.
   - ⚠️ Noticed while reading: **`@app.get("/admin")` is defined twice** in `sarathi_biz.py`
     (l.6914 and l.16802). FastAPI serves the first; the second is dead code nobody can reach.
     Not touched — worth a look on its own, not folded into a colour change.
5. **WhatsApp automation screen does not list messages we sent.** The NP-96 query went out and
   was READ (np_doc_reminder, 23 Sep 08:07:38) — delivery is fine, visibility is not.
7. ✅ **Super-admin can send a Live Case back to L2 Claims, with a reason.** — `6c72f52`
   It already existed, and I nearly built it twice — `verify-ops-buttons.py` caught the duplicate
   and the second copy was reverted. `POST /cases/{id}/handover/undo` is super-admin only, demands
   a reason, and records the real person behind an impersonation via `_actor_label`.
   `undo_handover()` deliberately allows a claim sitting UNTOUCHED in the entry bucket, which is
   exactly how NP-84 was stuck twice.
   **What was missing was reach.** The one button calling it sat on the *waiting* list — and a
   hand-over now drops a claim STRAIGHT into Live Cases, so that list is almost always empty and
   the button was unreachable from where the founder actually was. Same function, now on the
   claim panel, gated on `is_super` + entry bucket (past that the server refuses it anyway, so
   offering it would be a lie).

6. **SURAJ MALVIYA (claims 114/169): no payment at Razorpay in 7 days.** The founder reports one
   was made via the Pay button's QR. Nothing captured under either claim or that number — needs
   the date/amount or a Razorpay payment id from him to trace.

### ✅ 24 Sep 02:30 — THE ALARM THAT COULD NOT DIE — ROOT CAUSE FIXED, RESOLVED LIVE (`3380eb8`)

The founder tapped "👀 Seen — I'm on it" and it kept firing. **His tap DID land** (acked_by
Dushyant Sharma 20:52, next alert pushed to 22:52) — the messages he saw were just before it.
Two bugs behind the rest, and the second was about to restart the first at 22:52.

**ROOT CAUSE — a date window on the wrong question.** "Is this payment already in our books?"
was answered from a map built with `AND created_at > datetime('now','-54 hours')`. That window is
on **our row's** created_at. `pay_TfAr9LNYpxJFzL` **is** in the ledger — row 22, with its payment
id — but the row was written **20 August** and stamped with the id later. The map missed it → the
guardian called a recorded payment missing → "recovered" it → got `dup` → raised the finding →
alarmed → repeat, for ever.
> A payment id is unique for all time. Asking "have we got this id" and then qualifying it with
> "…but only if we wrote the row recently" is **two questions**, and the second has nothing to do
> with the first. Window removed — the table holds 113 rows; it was never about size.

**THE ACK WAS WIPED BY THE ALERT ITSELF.** `_alert_due` ran
`SET alert_count=alert_count+1, status='open'` **unconditionally, every time it spoke**.
`acknowledge()` sets `'acked'` + 2h; the 2h reminder then reset it to `'open'` and dropped it back
to every 10 minutes, printing *"nobody has tapped Seen yet"* on a message somebody had tapped Seen
on. **The button could never end anything — it could only buy two hours.** `status` is no longer
touched when alerting; an acked incident waits the full reminder period.

**VERIFIED LIVE:** `{'findings': 0, 'opened': 0, 'closed': 1, 'alerts_sent': 0}` · incident 7
`resolved` · **0 open incidents** · one `payment.guardian_ok` all-clear to the founder alone ·
0 tracebacks.

⚠️ **Noted for the notification controller:** `claim.l2_queued` fired to **16 super-admins** for
one event. Not a repeat — but 16 people for one claim being queued is the "overwhelming everyone"
shape the founder is asking to control.

### ✅ 24 Sep 01:40 — THE NOTIFICATION MACHINE-GUN, STOPPED AND DEPLOYED

Founder, 01:27: *"it's really irritating if these messages firing again and again to others too
... do control notifications and do intelligently, do[n't] fire gun continuously from any
notification channel to anyone."*

**Measured before fixing: 16 rows every 5 minutes — 16 super-admins × the SAME one message.
~192 notifications an hour, for one payment.** My bug, two faults stacked:
- `_recover_payment` ignored `activate_from_razorpay_webhook`'s return value, so a charge already
  recorded (`"dup"` — nothing recovered) was announced anyway, on every guardian pass.
- Nothing remembered having spoken.

Three guards (`80f41d3`): say nothing when nothing was recovered · once per payment id **ever** ·
a hard **ceiling of 3/hour** across all payments. The third is a fuse, not a volume knob — the
first two reason about one payment, and what he described is a **channel** failure.
⚠️ **The trap:** finding 7 alarms on any row without `announced_at`, so going quiet without
stamping would have swapped a message repeating every 5 min for an ALARM repeating every 5 min —
the one that fired 21 times on 23 Sep. `announced_at` now means "nobody needs telling again".
`_tools/test_recovery_once.py` (10). Its first run caught my quota counting `DISTINCT subject` —
and the subject is only the amount, so two ₹588.82 payments shared one.

**DEPLOYED and verified live:** guardian logged `result=dup` and said nothing; **0 messages sent
since**.

### 🔴 24 Sep — 235 TELEGRAM MESSAGES A DAY WERE BEING DESTROYED — `99e0cbe`

Found while proving on live data that tagging reaches Telegram:
`Bad Request: inline keyboard button URL '/nidaan/ops' is invalid: URL host is empty`.

**Telegram refuses a relative button URL and rejects THE WHOLE MESSAGE with it.** `dispatch()`
builds `NIDAAN_BASE_URL + url` and is fine; three callers bypassed it with a bare `/nidaan/ops`
(`payment_watch:255`, `pay_guard:871,918`) — **all three are the payment guardian's own alarms,
and not one has ever arrived.**

⚠️ **Why it hid for so long:** it logged at **INFO**, on a line shared with three outcomes that
genuinely aren't errors (not linked, disabled, no chat id). A real delivery failure wore the same
clothes as "this person has no Telegram", at a level nobody greps — and the bell showed the
alert, so from the inside it looked delivered. **Same class as the 201-and-delivers-nothing
outage.**
Fixed so no future caller can repeat it: a non-absolute URL is repaired; if still unusable the
message goes **without** the button; a failed send is retried plain; failures log at WARNING.
`verify-python-names.py` caught `os` undefined in payment_watch — second time this session.

⚠️ **STILL OPEN — `channel='telegram'` is never recorded.** 7-day channel counts: dashboard 4055,
email 280, **telegram 0**. Telegram is a side-effect of the bell, so the DB cannot answer "did
Telegram deliver?" — which is exactly why 235 failures a day were invisible. **The founder is
standardising staff notifications on Telegram; that channel has no delivery record at all.**
This belongs in the notification-controller work.

### 🚨 24 Sep — AN OPEN DOOR, FOUND WHILE VERIFYING THE CLOUDFLARE FIX

`POST /api/whatsapp/v2/webhook` accepts **unauthenticated requests on BOTH domains**. Verified
from outside: `200 {"ok":true}` to an empty, unsigned body. `validate_webhook_token()` returns
**True when no token is configured** ("dev only"), and `EVOLUTION_WEBHOOK_TOKEN` is unset in
production — it **fails open**, against the standing axiom that an unexpected branch ends in
"denied".

Reachable through it: `connection.update` (writes `wa_instances` + `nidaan_official_instances`)
and `messages.upsert`, which routes into `handle_official_inbound` — the Nidaan
document-ingestion handler. Honest limit: `messages.upsert` needs the caller to name a real
Evolution instance. A guess, not a control.

- 🔴 **Step 1 of `deploy/HANDOVER_24_SEP.md` — Cloudflare block, 3 min.** Safe in either
  configuration: Evolution runs on `localhost`, so legitimate traffic never reaches Cloudflare;
  if it posts to the public URL it comes from our own IP and is allowed.
- 🔴 **Then, NOT tonight:** set `EVOLUTION_WEBHOOK_TOKEN`, re-register each Evolution instance
  (existing ones keep their old webhook config — the env alone does nothing), and only then make
  `validate_webhook_token` refuse without a token. That order matters: reversed, inbound WhatsApp
  stops.

### ✅ 24 Sep — RAZORPAY WEBHOOK UNBLOCKED (founder's extension, verified from outside)

Bot Fight Mode off for nidaanpartner.com + a Skip rule on the webhook path. **Proved by outcome,
from outside our network, with Razorpay's own user agent:**
`POST /nidaan/api/webhook → 400 {"detail":"Invalid signature"} in 0.5s`, no challenge page.
All four webhook paths (both Razorpay, both WhatsApp) and the Meta GET verification now reach the
app. Remaining: ask Razorpay to re-deliver `pay_TfPq2skEiSuArv` for a true end-to-end 2xx.

### 🟡 24 Sep — "WHO GETS NOTIFIED" TOLD US WHAT WE HOLD, NOT WHO WE REACH — `2af87d7`

Founder: *"are we notifying everyone whom we are marking green on notifications?"* **No.** The
tick was `!!phone` / `!!email`. Three lies, all in his screenshot:
- **staff are reached on Telegram and the dashboard bell, and neither appeared** — a staffer with
  no phone and no email showed two red chips and read as unreachable while being notified twice;
- **staff email showed flat green**, though the policy deliberately does not email claim chatter;
- **a number that replied STOP showed green**, though the sender skips it.
Now: `reach` per party, three states (yes / maybe-with-reason / no-with-reason), built from the
same rules the sender follows. Chips were `#064e3b`/`#7c2d12` literals → theme variables.
`_tools/test_party_reach.py`, 13 checks. Also: **"Who gets notified" moved to the Conversation &
history column** on his ask — a move between two title regexes, no HTML relocated.

### 🟢 OPEN QUESTION — "Tag a teammate" vs "Involve a colleague"

They do different things and neither label says so. **Tag** = the people this NOTE is for; they
get `claim_note.mention` (bell + Telegram) with the text, *and* become involved. **Involve** =
start following the claim, no message. So tagging is a superset. Recommendation is in the reply;
awaiting the founder's word before merging, because silently adding a supervisor is a real
workflow.

### 🔴 RAZORPAY WEBHOOK — CAUSE CONFIRMED, FIX NEEDS THE CLOUDFLARE DASHBOARD

**Razorpay replied 23 Sep** on `pay_TfPq2skEiSuArv`: the webhook fired, our server answered
**403** with a Cloudflare **"Just a moment..."** challenge page, and answered that to every
retry. The request never reached the application.

**The cause is item 1 of our own checklist** — `CLOUDFLARE_WAF_RECOMMENDATIONS.md` §1, "Bot Fight
Mode → On (both domains)". It challenges automated callers; a payment provider's webhook agent
is an automated caller.

⚠️ **I told the founder it was not our side, and that was wrong.** `webhook_self_test()` POSTs to
our public URL, got its 400, and said "✅ NOT our side". An edge challenge scores the **caller**,
not the path — our own server with our own user agent is not scored like Razorpay's. The test
proved *our app answers us*; it could never prove a third party gets through. That is this
project's own rule — **read an outcome, not a configuration** — broken by my own checker, and it
cost a day with Razorpay support.

- ✅ **Fixed so it cannot recur** (`1d567e0`): the self-test names a challenge page on any status
  code (a 503 carrying one used to read as "webhook secret not configured" — sending somebody to
  edit a correct secret), and a pass may no longer claim the fault is elsewhere.
  `_tools/test_webhook_selftest.py`, 11 checks, **proven to fail 4 against the old code**.
- ✅ **The checklist now carries the exception above the instruction that caused it**, with the
  webhook paths grepped out of `sarathi_biz.py` rather than written from memory.
- 🔴 **`deploy/RAZORPAY_WEBHOOK_BLOCKED_RUNBOOK.md` — FOUNDER ACTION.** There is **no Cloudflare
  API token anywhere in this repo**, so this cannot be scripted from the app server. Dashboard,
  ~5 minutes: Security → Events to confirm, Bot Fight Mode **off for nidaanpartner.com only**,
  replace with a custom rule that excludes the webhook paths, then prove it by **outcome** (a 2xx
  in Razorpay's delivery log, or a ₹1 payment).
- **No money is at risk meanwhile.** The guardian reconciles against the Razorpay API every 5
  minutes and recovers. What is lost is promptness, and the second independent path — right now
  reconciliation is the *only* way money reaches our books.
- ❌ **Never "fix" this by giving Razorpay an unproxied hostname.** It exposes the origin IP and
  undoes `lock-origin-to-cloudflare.sh`.

### 🔴 WHATSAPP CHARTER — foundation, security, alerting (founder, 23 Sep)

**✅ Done today**
  - **Blue ticks.** We never told WhatsApp a message was read, so every complainant saw theirs
    sit on "delivered" — which reads as *nobody is there*. `mark_read()` now fires the moment an
    inbound is logged. Deliberately outside the send guard: a receipt is not a message and must
    never be rate-limited or held.
  - **"WhatsApp bot replies"** in App Health — reads OUTCOMES: of the people who wrote in the
    last 24h, how many got a reply within 15 minutes. **Silence is not a failure** (low-traffic
    number, a quiet Sunday must not page anybody); somebody writing in and getting nothing is.
  - **The webhook now logs what arrived** (field names + counts, never content). The question
    "did the message reach us or did we drop it" was previously unanswerable.
  - ⚠️ **Why the existing check missed it:** "WhatsApp Cloud API" read CONNECTED / GREEN
    the whole time, because it asks Meta about the NUMBER. The number was fine. Nobody was being
    answered. **A check must read an outcome, not a configuration.**

**🔴 Still to do — security and conduct**
  1. **Identity before information.** Today the bot matches an inbound number to a claim and
     starts giving case detail. A recycled or spoofed number would get somebody's medical claim
     information. Needs a verification step — **design question for the founder below.**
  2. **Stage-aware answers.** Once a claim reaches **Consolidation**, the bot must stop giving
     detail and say: *the case is in the legal process, it will take time, thank you for your
     patience.* Document collection is the ONLY thing it should transact, and only while
     something is genuinely pending.
  3. **Frustration → a human.** If the complainant is impatient or upset, hand off to the
     on-duty support staff and tell the super-admins. The bot must not keep answering.
  4. **Unexplained:** the founder's first two messages (12:45, 12:46 IST) were never recorded —
     no webhook carrying them ever arrived. The two at 1:17/1:20 were handled in the same second.
     Now answerable from the log if it recurs.
  5. **25 outbound `failed` on 22 Sep with a BLANK error field** — the reason was never recorded.
     Same silent-failure pattern; worth closing.

### 🟡 24 Sep — NOTIFICATION REGISTER: THE LIST NOBODY HAD — `b889a81`

**75 event keys across 12 modules, and nothing anywhere could list them.** That is the whole
reason nobody could see, the night of 23 Sep, that three separate paths were each choosing their
own cadence. `notify_policy.summary()` claims in its own docstring to be *"surfaced in ops so the
rules are visible, not folklore"* — **it was wired to nothing.**

- `biz_nidaan_notify_registry.py` — all 75 named in **both languages**, with who receives each
  and whether it may ever be switched off. **Not a second copy of the routing rules:** whether an
  event emails is still decided by `notify_policy` and the register *asks* it. Two sources of
  truth for one question is how the "who gets notified" panel came to show ticks that meant
  nothing.
- **Auto-registration is ENFORCED, not hoped for.** `verify-notify-registry.py` greps for
  `event_key="…"` and fails the build on any key with no entry — and refuses an entry for a
  notification that does not exist, because a toggle that controls nothing is worse than no
  toggle. Folded into `check:all`. **Proven both ways:** an unregistered notification fails it
  and names the file; unlocking `payment.failed` fails it.
- **Money, security and health are LOCKED**, and say why in both languages.
- Settings shows the list, grouped, key under each name. **Read-only on purpose.**

🟢 **TWO ANSWERS NEEDED BEFORE THE SWITCHES GO LIVE:**
  1. Control **per notification**, or per notification **per role**? (e.g. super-admins keep
     `claim.status`, team members turn it off)
  2. Beyond money / security / system health — anything else that must **never** be silenceable?

⚠️ **Latent weakness found in the audit, not yet fixed:** the alarm policy's repeat-hold
(`_repeat_held`) compares messages **word for word**, and the guardian's body contained *"Said 9
times… Said 10 times…"* — so the text changed every time and **the hold never matched**. The new
cadence bounds it at source; the shared gate is still defeatable by any counter in a message
body. Belongs with the switches work.

### ✅ 24 Sep — SERVICE CHECKS SAY "IS IT WORKING", NOT "IS THERE WORK" — `7c7f47c`

Founder: *"it's showing whatsapp not replied, that should not be here."* The panel had two states,
so "1 of 4 still waiting for a reply", "11 branches with no WhatsApp number" and "the database is
unreachable" all rendered identically and all counted as failing subsystems. **Red that is
usually nothing is how a real outage gets scrolled past.**
Three states now — `down` (the only thing that counts) / `attention` (amber, and says WHERE) /
`ok`. The WhatsApp check keeps its teeth: if **nobody** who wrote got an answer, that is a dead
bot, still `down`.

**And severity now means what he said it means.** 11 of 14 findings were `critical` — including
*"we found a payment the webhook missed and already fixed it"*, a success reported as an
emergency. critical backs off (10m→30m→2h→6h, never silent) · warn twice then quiet · info once
ever. ⚠️ The due query was `COALESCE(next_alert_at,'') <= now` and `''` ≤ every timestamp — so
NULL, meaning *"say no more"*, would have made an incident **permanently due**. Silence as an
infinite loop. `_tools/test_alert_cadence.py` (19) exercises the real SQL and proves it.

### ✅ 24 Sep — HEALTH ALERT: 96 EMAILS/DAY → 2 — `058068c`
`if critical > 0: send`, every 15 min, no state. 97 identical "Master bot not running" emails in
24h. Now: mails when the problem CHANGES, restates every 12h, one all-clear when green.
**Verified live:** `Health: 1 critical, unchanged — not emailing again`, no email sent.
⚠️ **The alert is TRUE** — `@SarathiBizBot`'s token is **rejected by Telegram**. Needs rotating in
BotFather + `biz.env`. Nidaan's ops bot is separate and unaffected.
🔒 **A live bot token was being written to journald in plaintext** on every restart — the library
puts it in its own error message. `_scrub_secrets()` redacts by SHAPE now. That token is already
dead; **rotate anyway**, it has been in the journal.

### 📋 RAISED 24 Sep (afternoon) — deploy after 6pm IST

Ground rule restated by the founder: *"whatever we are fixing/changing/enhancing, we should be
doing it in a way we move towards making the foundation strong ... solutions should be scalable
not temporary."*

#### 🔴 A. WRONG — a screen saying something untrue

**A1 · "Branch SP-GJG7BA — house account" on a staff-raised claim.** My own label, shipped this
morning. The account row is a *house account* created for a staff referral, and calling it
"Branch" re-introduces exactly the confusion `2bc9ce0` set out to remove. Needs to read as what
it is — a house account standing behind a colleague's referral — **without breaking the real
branch case.**

**A2 · Escalation chips recount inside the filter.** *All 6 · Escalation Pending 5 · Escalation
Query 0 · Escalated 1* — click "Escalation Pending" and it becomes *All 5 · … · Escalated 0*.
The chips are counting the **filtered** set instead of the bucket, so the numbers move when you
touch them and "Escalated" reads 0 when there is 1. Counts must come from the bucket, always.

**A3 · Payment shows "Due" after a QR payment.** NP-200 (PRITI PAWAR) — *"Awaiting branch ₹499 +
GST L2 fee"* and *"Fee not paid yet"*, but it was paid against a shared QR.
  - **Investigate first:** which QR? A Razorpay payment link (we create those and they carry
    `notes`) or a static personal/UPI QR (no link id, nothing to reconcile against)?
  - Founder's ask: it should flip to paid **automatically** when the money lands; and where that
    is impossible, let the staff member who shared the QR **attach the payment screenshot** and
    have the system record it.
  - ⚠️ A screenshot is **not** proof of payment and must never write the ledger on its own. Design
    needs a verified path (Razorpay) and a **claimed-and-pending** path (screenshot → a person
    confirms) that are visibly different. This is money; it gets the careful treatment.

  **✅✅ ANSWERED PROPERLY (2nd pass, after the founder said staff insist they generated a QR).**
  **Both sides are telling the truth.** Razorpay's ORDERS api settles it — three orders exist for
  claim 200:

  | order | created | status | paid | **attempts** |
  |---|---|---|---|---|
  | `order_TfONH3olENyEQV` | 23 Sep 07:14 | created | ₹0 | **0** |
  | `order_TfOqfe7GWuHsHE` | 23 Sep 07:42 | created | ₹0 | **0** |
  | `order_TfoSgqKvRFmB51` | 24 Sep 08:46 | created | ₹0 | **0** |

  - **Staff are right:** they initiated and a QR was generated — three times.
  - **The system is right:** no money arrived. `attempts=0` means nobody ever *tried* to pay
    against that QR. Not a failure — **not a single attempt.**
  - So the complainant paid *somewhere that was not our QR*, or has not actually paid.
  - Nothing from their number (9575244166) anywhere at Razorpay in 7 days. And every
    unattributed ₹588.82 payment resolves to a real `subscription_id` — checked at Razorpay, not
    assumed. ₹499+GST being BOTH the L2 fee and the Silver price is what made that worth checking.

  🔴 **AND IT IS A PATTERN, not one claim.** Of 22 L2 fee orders in 5 days: **9 paid, 13 unpaid
  with zero attempts.** Claim 194 has **six orders created inside the same minute** — a button
  that does not disable while it works. We generate QR after QR that nobody ever scans, and
  nothing on any screen says so.

  **What to build (scalable, not a patch):**
  1. **Show the fee link/QR ON the claim with its real state** — "shared by X at Y · not yet
     attempted". Then the conflict answers itself on the screen instead of by me querying an API.
  2. **Prefer the payment LINK over a raw checkout order** for sharing: a link is durable, has
     its own status, survives being sent on WhatsApp, and Razorpay tracks it.
  3. **Stop the six-orders-a-minute** — disable the button while it is working.

  **(1st pass, kept because the mechanism note is still right:)**
  - Claim 200 has **no payment anywhere** — not in our ledger, not at Razorpay. The money never
    reached our account. (The note-less ₹588.82 payments I first suspected turned out to be
    **subscriptions** — ₹499+GST is both prices. Checked before concluding.)
  - `POST /my-claims/{id}/l2-payment-link` and the branch portal's equivalent **already** create a
    Razorpay link whose notes carry `purpose=l2`, `claim_id` and `branch`. When one of those is
    paid, the webhook/guardian attaches it and **the claim flips to paid by itself**. No
    screenshot needed. It is exactly what he asked for.
  - 🔴 **Nobody can reach it.** `ops_my_l2_payment_link` is referenced by **no HTML at all** — an
    endpoint built and never given a button. The branch-portal one has been used **5 times ever,
    none since 8 Sept**. Meanwhile 15 branch L2 payments landed in the last 7 days by other
    routes. So staff share *some other* QR — personal UPI, or the generic Settings link generator,
    which offers only `review499 / subscription / custom` and **cannot attach a claim**.
  - **Fix (small, high value):** put the claim-bound "Share ₹499+GST link / QR" button on the
    claim, where "Fee not paid yet" is already printed. Then the automatic conversion he
    described happens on its own.
  - **Screenshot path stays SECOND** and separate: for money that genuinely arrived outside
    Razorpay there is already an offline-payment recorder — it must be claim-scoped and marked
    *claimed, awaiting confirmation*, never silently trusted.

#### 🟡 B. AWKWARD — costs the team time every day

**B4 · "Open" is off the right edge of every bucket table.** Everyone scrolls right, clicks Open,
scrolls back. **A click anywhere on the row should open the claim.** Must not break the controls
inside the row (Move…, the type dropdown, Query) — those keep their own click.

**B5 · Pagination everywhere.** All Claims, L2 Claims, the buckets, Accounts. User picks
**10 / 20 / 30 per page, default 30**. Founder frames it as growth: scrolling gets worse every
week. Server already takes `LIMIT`/`OFFSET` on the claims query — this is mostly wiring.

**B6 · "Send the query to complainant" needs to be a conversation, not a one-shot.**
  - the tick-boxes should decide **who is notified**, and it should be sendable **more than once**
  - **the whole history lives in that panel** — who sent what, to whom, on which channel, when —
    so the next person can see the last ask before adding another.
  - Today it warns *"A query already went to the complainant"* but shows only the most recent.

**B7 · My Business → raise a claim: Insurance Company and Disputed Amount overlap.**
  ⚠️ **No screenshot received for this one** (seven arrived, this was the eighth). Will find the
  form and check its layout at phone and desktop widths.

#### ✅ SHIPPED 24 Sep evening — A1 · A2 · A3 · B4 · B5 · B6 · B7

`6dbf955` and before. All deployed after 6pm IST, all verified live, 0 tracebacks.

| | what it was | what it is now |
|---|---|---|
| **A1** | "Branch SP-GJG7BA — house account" on a colleague's claim | "🏠 House account · SP-GJG7BA · opened for TAMANNA VASHISHTHA" |
| **A2** | chips recounted inside their own filter — "Escalated 0" about a claim that exists | counts come from the bucket; only the list narrows. **21 checks** |
| **A3** | fee said Due after a real payment | see below — the customer **did** pay, Razorpay refunded it |
| **B4** | Open was off the right edge of every bucket table | any row opens on click, keyboard too, controls inside keep their own click |
| **B5** | one long scroll | **default 30**, choices 10/20/30/50, remembered. **14 checks** |
| **B6** | each query **overwrote** the last — no history existed | `nidaan_claim_queries`, one row per ask, reply lands on its own ask. **14 checks** |
| **B7** | Insurance Company sat on top of Disputed amount | grid arithmetic fixed; **measured** at 1280/760/360. **12 checks** |

**A3, the whole story.** UTR `511846804526` from his screenshot = `pay_TfOQly6xXZmGqJ`:
`description: QRv2 Payment` · `order_id: None` · `captured: False` · refunded **the same minute**
· Razorpay's reason: **"The checkout order associated to the QR is closed"**.
Staff opened pay-now, screenshotted the QR, closed the window. **A checkout QR dies with its
window** — whoever scans it later is auto-refunded *after* being shown "Transaction Successful".
Everyone was telling the truth.
⚠️ **And we could never have known:** the guardian only ever looked at `captured`. Now it raises
`bounced_payment:<id>`, and on deploy it found this one, told **the founder alone**, said it
**once**, and went quiet — the notify policy and the new severity cadence both working on a real
incident. **Swept 60 days: 1 occurrence in 149 payments.** Not a pattern.

⚠️ **Found on the way:** six columns on `nidaan_claimant_portal` are added by `ALTER` at
`init_db` line 2838, and the table is not created until line 3325 — so **a fresh database never
gets them** and All Claims would fail outright on a restored schema. Production has them, which
is why nobody could notice. Fixed in the CREATE.

#### 🟢 C. ANSWERED WITH NUMBERS — the founder decides, nothing cut yet

Live data, tonight:

```
not in Level-2 yet  136        live_cases     12  (sub-state: none on all 12)
live_cases          12         pending_draft   3  (all 3 'drafting')
escalation           6         escalation      6  (5 pending, 1 escalated)
pending_draft        3
```

**C8 · "BEFORE LEVEL-2: Intake 0 · Review 44 · Conversion 86" — it DOES work.** Clicking one
opens a real filtered list (the Case Board, pinned to that stage). It is not decoration.
**But:** it puts **136 claims that are not Level-2 work** across the top of the Level-2
workspace, above the **21** that are. That is the "overbuilt" feeling — the screen is trying to
be both the whole line and the Level-2 desk.
→ **Proposal:** keep the information, lose the prominence. One collapsed line — *"136 before
Level-2 — Review 44 · Conversion 86"* — that expands on click, instead of three buttons ranked
equally with the buckets. **Founder's call.**

**C9 · The chip strip** (*3 in this bucket · 3 draft queries · 1 window closing · 3 ours to move ·
1 short of documents · 3 missing something we need*). Six chips describing **three claims** —
more chips than claims. And *"3 in this bucket"* repeats the number already on the sidebar button
that was just clicked.
→ **Proposal:** drop *"in this bucket"* (duplicate), and show a chip only when it is **non-zero
AND actionable**. On a busy bucket they earn their place; on a bucket of three they are noise.

**C10 · The sub-state tabs** — *"how well we are utilizing these internal bucket statuses?"*
The numbers answer it: **Escalation's are carrying real information** (5 / 1). **Pending Draft
shows four tabs for three claims all in one state.** **Live Cases has tabs and not one of its 12
claims uses them.**
→ **Proposal, and it is the scalable one:** do not delete anything. **Hide a sub-state tab while
it is empty**, so tabs appear as the workflow actually starts being used and vanish when it is
not. The bucket designer keeps every state; the screen stops showing four doors into an empty
room. Reversible, and it makes the UI reflect how the office really works rather than how the
design imagined it.

#### 🟢 C. (original questions, for reference)

**C8 · "BEFORE LEVEL-2: Intake 0 · Review 44 · Conversion 86".** *"why we are showing them? if we
are showing them what purpose they are solving?"*

**C9 · The chip strip:** *3 in this bucket · 3 draft queries · 1 window closing · 3 ours to move ·
1 short of documents · 3 missing something we need.* Same question.

**C10 · The sub-filters:** *All 3 · Drafting 3 · With Medical Officer 0 · Draft Query 0 ·
Approved 0.* *"how well we are utilizing these internal bucket statuses and filters? ... how
better we can manage these statuses/filters without overbuilding but keep things simple?"*

→ **These three are one question: is the bucket screen earning its complexity?** The answer should
come from evidence — which of these is ever clicked — not from my taste. **Nothing gets deleted
until we can say what it was for and who used it.** Proposal to follow, not a unilateral cut.

### 📋 RAISED 25 Sep — and the two answers I was waiting for

#### ✅ BUILT 25 Sep — THE NOTIFICATION CONTROLLER (awaiting deploy, after 6pm IST)

The switches are real. Settings → **🔔 Notifications** is no longer a read-only list: every one of
the **75** notifications has a **tickbox per job** (Super admins · Sub admins · Team). Untick it
and that job stops being told, on Telegram and email. The dashboard bell keeps the record either
way — that is the difference between quiet and blind, and this project has paid to learn it once.

| Piece | Where |
|---|---|
| The resolver — the precedence chain | `biz_nidaan_notify_prefs.py` (new) |
| One row per switch, addressed by scope | `nidaan_notify_prefs` + `idx_nprefs_addr` (unique on the COALESCEd address, so a re-flip updates instead of piling up rows) |
| Both send paths ask it | `biz_nidaan_notifications.py` → `resolve(..., channel=…)` |
| Set · clear · **explain** | `POST`/`DELETE`/`GET /nidaan/ops/api/notifications/prefs`, `…/explain` |
| The screen | `static/nidaan_ops.html` → `npToggle()` |
| In the feature list | `biz_nidaan_capabilities.py` → `notification_control` |

**Decisions worth keeping:**
- **Money, security and system health draw no tickbox at all** — nothing to click that could not
  take effect. A switch set against one through the API is *stored and reported*, never silently
  dropped: the person set it, and hiding that it will not apply is how a screen starts lying.
- **Roles on this screen, on purpose.** Per-person and per-claim switches exist in the API and in
  the resolver, and belong beside the person and the claim. 75 events × every colleague is a grid
  nobody can read, and therefore nobody trusts.
- **An unreadable preferences table fails towards being told.** The failure people notice is
  noise; the failure that costs money is the message that never came.
- **`daily` is accepted but behaves as immediate** — nothing drains a digest yet, so the screen
  deliberately offers on/off only. A verifier check now *enforces* that, and is the reminder to
  lift it the day the digest exists.
- Super-admin only, and every flip is in the audit trail: this is a map of everyone else's
  attention, and one person quietly silencing a colleague is an outage arranged by accident.
- **Caught on the phone, not in the code.** The first screenshot at 390px showed the fault: the
  job columns are only reachable by scrolling sideways, and the notification's *name* went with
  them — you would be ticking a box with no idea which row it belonged to. The name column is now
  pinned, and that is a check in the suite, not a note.

**Checked:** 30 precedence checks (`_tools/test_notify_prefs.py`, py -3.14) · 43 routing +
wiring checks (`deploy/verify-notify-routing.py`) · 13 register checks · `npm run check:all` ·
`verify-ops-buttons.py` 435 handlers, 0 unreachable · **16 browser checks on a 390px phone in both
themes** (`uitest/notify-switches.js`, offline — safe to run while the team is working). The wiring checks are the dead-button guard:
a tickbox that renders, accepts a click and reaches nothing looks identical to one that works, so
every link — tickbox → POST → route → super-admin gate → audit → resolver — is asserted alone.

🔴 **Still owed on this:** the daily digest (then `daily` can be offered); per-person switches on a
staff member's page and per-claim switches on the claim, both of which the API already supports;
`channel='telegram'` is **still never recorded** in `nidaan_notifications`, so there is no delivery
record for the channel we are standardising on — that is measurement, not control, and it means a
switch's *effect* cannot yet be proven from the data.

#### 🟢 ANSWERED — what unblocked it

He answered both open questions in one line:
> *"per event per role and per event per specific user involved, of course claim level settings
> will take precedence."*

And said why it matters:
> *"just so I should not depend on notification thing on you every time to do code changes until
> anything breaks."*

**So the resolution chain is, most specific first:**
```
1. claim × user      "stop telling ME about claim 200"      ← highest
2. user              "never send ME claim.status"
3. role              "team members do not get bucket.move"
4. the registry      what the policy does today              ← default
```
**Locked events (money · security · system health) ignore all of it** — that was settled on
24 Sep and the registry already enforces it.
Also wanted: **frequency** ("which notification, to which, frequency, when") — stored, honest
about not being live, and listed above as still owed.
✅ **Built 25 Sep**, ahead of churn analytics, at his explicit request. See the section above.

#### 🔴 D1 · "Send the query to the complainant" must become a real tool

Currently: one free-text ask, fixed recipients, WhatsApp/Email/one lumped "copy by email"
tickbox, and only the LAST send visible.

He wants:
- **Per-RECIPIENT tick boxes** — complainant · branch · subscriber · staff · *any other party on
  the claim to this point* — not one all-or-nothing "copy to" line.
- **Per-CHANNEL choice** per recipient: email, WhatsApp, and **internal staff on Telegram only**.
- **History in the window**: when it was last sent, and how many times.
  ✅ The store for this shipped 24 Sep (`nidaan_claim_queries`, `970ccab`) and the panel already
  lists it — what is missing is the per-recipient part and the count.
- **A schedule option**, the same one the claim already has.
- **The whole thread recorded inside the claim**, with the rest of its communication history.

→ Deliberately AFTER the notification controller: both answer "who gets what, on which channel",
and building this first would be the second copy of that rule.

#### 🟡 D2 · WhatsApp automation — HE ASKED TO THINK FIRST, NOT BUILD

> *"all these we need to think first and then move on whatsapp charter."*

What he described, with the numbers from the screen (33 opted in · 412 sent · 138 replies ·
39 conversations · 9 with a person · 1 waiting):

1. **The missing piece is GUIDANCE, not delivery.** Staff exhaust their WhatsApp attempts, then
   *phone* the complainant from another number to talk them through sending a document. The bot
   asks; it does not teach. That call is the real cost and it is invisible to the system.
2. **Each party must be identifiable** when staff and several parties are all on a claim — today
   a conversation is a number, not a role on a case.
3. **Marathi.** Maharashtra complainants and external parties are coming. Today: Hinglish / Hindi
   / English. Needs to be picked up intelligently, not asked for.
4. **Staff do not know how to use it.** A training/《how this works》piece, not a code change.
5. ⚠️ **Verification: EXPIRED** on the live number (+91 91836 86384), Quality GREEN. Worth
   checking what that limits before volume grows.

→ **Discussion owed before more charter work.** Nothing built beyond what shipped on 25 Sep.

### ⚡ PERFORMANCE — MEASURED 24 Sep, NOTHING BUILT YET

Founder: *"multiple payments are happening at the same time, the application is busy ... a few
people are using old machines, old versions ... filters should work faster in loading."*

**Measured first, because the obvious suspects were all innocent.**

| Layer | TTFB | Total |
|---|---|---|
| Our app, direct (`:8001`) | **14 ms** | 15 ms — full 1.3 MB |
| + nginx, gzipped | **22 ms** | 51 ms — 342 KB |
| + Cloudflare, from outside | **1,000–1,600 ms** | **1,800–2,500 ms** |

**It is NOT:**
- **the server** — load `0.03` on 2 cores, 9.4 GB free, measured at 12:28 IST on a working day
- **the database** — 22 MB, **188 claims**, and `nidaan_claims` already has 4 indexes
- **our code** — the app answers in `x-response-time-ms: 13`

**It IS, in order of impact:**

1. 🔴 **The page is 1.27 MB of HTML+JS in ONE file, and it is `no-cache`.**
   Response headers: `Cache-Control: no-cache, must-revalidate` · `cf-cache-status: DYNAMIC` ·
   `Content-Encoding: br`. So **Cloudflare Brotli-compresses 1.3 MB on every single page load**
   and can never reuse the result, and the browser re-downloads 326 KB and **re-parses and
   re-executes 1.3 MB of JavaScript every time**. That parse cost is the same on every machine
   and it is exactly what an old laptop feels.
   ⚠️ **AND IT IS WILDLY VARIABLE.** Four consecutive samples of the same page, same machine:
   **0.79 s · 3.57 s · 12.70 s · 11.96 s** — plus two outright stalls earlier, 89 s and >120 s.
   Every one of them served by an app that answered in 13 ms. **That variance is what the team
   reports as "sometimes it is slow", and it is entirely outside our code.**
   - **Fix:** move the JavaScript out of `nidaan_ops.html` into a versioned immutable
     `nidaan_ops.js?v=N`. The HTML drops to a few KB (cheap to revalidate); the JS is cached by
     Cloudflare **and** the browser, downloaded once per release, and old machines get to reuse
     the browser's compiled-code cache.
   - **HIGH LIFT, and genuinely risky:** 427 handlers in one global scope. Must be a pure
     extraction — same code, same order, same scope — proven by `check:pages` + `verify-ops-buttons`
     before and after. **Not a refactor. A move.** Do it on a quiet evening, not mid-week.

2. 🔴 **Every filter change refetches the server AND rebuilds the whole panel.**
   `applyClaimFilters()` → `loadClaims()` → re-fetches the branch list, re-renders the filter bar,
   re-fetches `/claims` (**32.6 KB**), re-renders the entire table. **130 calls / 4.14 MB today.**
   - ⚠️ **Two of those filters need no server at all.** `claimOriginFilter` and `claimCustFilter`
     are applied *in the browser* on rows already loaded — the code says so in its own comment —
     and they still trigger the full round-trip.
   - **Fix (LOW lift, high payoff):** filter the rows already in memory; only go to the server
     when the search text or a server-side filter actually changes. Keep the filter bar mounted
     instead of re-rendering it.

3. 🟡 **No latency measurement exists.** nginx defines a `timed` log format with
   `rt=$request_time urt=$upstream_response_time` — **and never applies it.** The live log is
   plain `combined`. We cannot currently answer "what was slow at 3pm yesterday".
   - **Fix (tiny):** apply `access_log ... timed` to both sites. One line. Do this FIRST — it is
     how we will know whether anything else worked.

4. 🟡 **~4 polling requests per 45 s per open tab.** Today: `/changes` 1402, `/notifications` 667,
   `/broadcasts` 665, `/notifications/pending-ack` 660, `/pulse` 657 ≈ **4,000 requests**.
   The `/changes` sequence-check is a good pattern (cheap, `document.hidden`-aware); the other
   three could ride on it instead of polling independently.

5. 🟢 **`nidaan_notifications` is 26,323 rows** and growing — most of it from the alert floods.
   Indexed on status/recipient/event, so it is not slow *yet*. Needs a retention policy before it
   becomes the reason the bell is slow.

6. 🟢 **Duplicate security headers** — nginx and the app both set `x-content-type-options`,
   `x-frame-options`, `referrer-policy`, `strict-transport-security` (with *different* max-ages).
   Harmless for speed, untidy, and the conflicting HSTS values should be reconciled.

**Suggested order when we start:** 3 (see it) → 2 (cheap, fixes his actual complaint) → 1 (the
big one, on a quiet evening) → 4 → 5 → 6.

### 🔴 NEXT UP — agreed with the founder, in this order

1. **🔴 WhatsApp Business not replying** (23 Sep, priority). See the investigation below.
2. **Churn analytics.** Why a subscription cancelled or did not renew: user cancelled, bank
   declined (and WHY), transaction not compliant. Plus a fallback so we can approach the customer
   in time to retain them.
   - We ALREADY handle `subscription.cancelled / halted / pending / charged` and `payment.failed`
     (which carries Razorpay's real error reason). **`nidaan_subscriptions` has only
     `cancelled_at` — no reason column anywhere, and no churn table.** The signals arrive and
     the reasons are discarded. Recording them is the work; this is not a new subsystem.
3. **App Health** — each module declares its own check instead of one hand-written list; a small
   history table so "it was down from 3 to 4" is answerable; and **security observability folded
   in here** rather than as a separate screen (founder, 23 Sep: medical data, protective without
   being heavy, surface an intrusion attempt and tell the super-admins).
   - Standing rule proved twice on 22–23 Sep: **a check must read an OUTCOME, not a
     configuration.** "The key is set" is not "email is arriving".
4. ~~**Notification registry**~~ — ✅ **CLOSED 25 Sep.** All 75 keys register themselves (the build
   refuses a new one that does not), both questions answered by the founder, and the switches are
   real: per event per job on the screen, per person and per claim in the API, claim beating person
   beating job. See *THE NOTIFICATION CONTROLLER* above for what is still owed (the daily digest,
   the two narrower screens, and a delivery record for Telegram).
   - `notify_policy.summary()` is now wired — it is what the register screen reads.

### ✅ SHIPPED 2026-09-23 (2) — Revenue reads the ledger (it was showing 36% of the money)

**Measured before touching anything:** Revenue screen **₹29,257**, ledger **₹80,488**. Gap
**₹51,231**. Not a wrong sum — **two separate accounts of the same money**, and the screen read
the older one.

| Missed | Amount |
|---|---|
| branch Level-2 fees, in none of the three source tables | ₹22,963 / 39 payments |
| **EXPIRED** subscriptions, dropped by `status IN ('active','cancelled')` | ₹14,034 / 9 subs |
| renewals | ₹5,214 / 6 |
| ₹499 reviews: 12 in the ledger, **2 rows** in the purchase table | ₹6,477 |

The expired one matters most: **money already collected does not stop having been collected when
a plan lapses.** That filter made total revenue **fall over time** — backwards, and the kind of
number that quietly destroys trust in every other number on the screen.

  - **Founder's definition (23 Sep): collected to date**, everything that ever came in, branch L2
    included. The screen now says so in words.
  - **GST is separate.** ₹9,873 of the ₹80,488 is collected for the government, not earned —
    calling it revenue overstates by 12%. The split's **basis** is configurable so this is decided,
    not assumed, and **defaults to the old behaviour** so nothing moved silently on ship day.
  - **The split is configurable** and drawn from the data — "80:20" was typed into the HTML in
    **four places**, which is exactly what made it not flexible. **Owner-only still**, until the
    numbers have been watched: a number that moves every other day teaches people to doubt it.
  - 🐞 **Everything sums in PAISE now, converted once.** The test's first run found a
    **₹1 drift** from rounding five sources separately. A rupee today is visible drift at ten
    times the volume.
  - `_tools/test_revenue_ledger.py` — **22 checks** on a copy of live, including exact paise and
    that a broken split config falls back rather than hiding money.
  - `deploy/verify-revenue.py` stays as a **data-drift report**: the legacy tables still drive
    other screens and 11 of 12 ₹499 reviews have no purchase row.

**⏳ Next, agreed with the founder:** churn analytics. We already handle
`subscription.cancelled / halted / pending / charged` and `payment.failed` — **but
`nidaan_subscriptions` has only `cancelled_at` and no reason column anywhere.** The signals arrive
and the reasons are thrown away. Recording them is the work, not building a new subsystem.

### ✅ SHIPPED 2026-09-23 — the retry link, notification routing, and two names that did not exist

**✅ The payment retry link had NEVER been sent.** 27 failures since 17 Aug, zero retry rows.
It looked for the address under `account_id`/`acct_id` and **not one of our five products writes
either key**; a UPI payment carries no email on the Razorpay entity, so the notes were the only
route and the only route looked in the wrong place. `_retry_contact()` now tries every route each
product really provides. `_tools/test_retry_contact.py` — 13 checks, every product shape resolves.
  - On the timing question: **we set no timeout anywhere.** No `timeout` on checkout, no
    `expire_by` on any order. The "could not complete it in time" is the UPI collect window
    between the customer and their bank app, and it cannot be extended from here.
  - Of 20 people who failed, **10 later paid** — including the one in his screenshot.
  - ⚠️ `payment_failed` events carry a phone and no account_id; `payment_success` carries an
    account_id and no phone. **They cannot be joined**, and my first answer to "did they pay
    later" was wrong because of it. Worth fixing in the events spine.

**✅ Internal notices go to Telegram + bell, not email.** Measured first: **550 emails in 24h**,
and **not through Brevo at all** — every one over SMTP, so the 200/day Brevo ceiling was never
today's constraint; a Gmail limit is. `dispatch()` decided email by "did WhatsApp work?", and for
staff WhatsApp is never up, so everything became email to all 16 admins. The policy module had
classed this as chatter since the day it was written and `dispatch` **never consulted it**. Now it
does, for staff only, and the chatter rule sits above the super-admin rule.
`deploy/verify-notify-routing.py` — 29 checks.

**🚨 Two names that did not exist, both swallowed by a bare `except`.**
  - `datetime.utcnow()` in the webhook handler — `datetime` is not a name in that file. The
    arrival stamp was **never written once**, so the guardian read a frozen timestamp and emailed
    **"No Razorpay webhook in 24 hours" 44×/day for three days** while webhooks were arriving and
    working normally.
  - `_asyncio` in `ops_update_claim_status` — so the **status-change fan-out has never run**,
    which is exactly why `nidaan_notifications` holds **zero** rows for `claim.status`.

**✅ `deploy/verify-python-names.py`** — eslint's `no-undef`, for Python. **Scope is the whole
point:** the first two versions asked "is this name bound anywhere in the file", answered yes
because eight other functions import `datetime` inside themselves, and would have passed the very
bug they were written for. Run against the broken file before being trusted: 2 problems then, 0
now. `npm run check:py`.

**✅ An alarm that is still true says it once, then holds 6 hours.** Word for word is the test —
any change in the text goes straight through, so a worsening situation is never held behind a
copy of the better one. Tunable from ops settings; 0 disables. Held repeats are counted. A broken
table delivers. `_tools/test_alarm_repeat.py` — 8 checks.

### ✅ SHIPPED 2026-09-22 (7) — a draft can be copied into an email as TEXT

Founder: copying a draft and pasting it into Gmail produced a non-editable **image** instead of
text. Gmail falls back to a picture when the clipboard offers it one and no usable `text/html`.

  - **Checked first, and the page is not the culprit.** `uitest/draft-copy.js` renders the real
    editor with a real stored draft, copies it by hand, and reads the clipboard back:
    `text/plain, text/html`, **no image flavour**. The stored drafts are clean too — `<p>`,
    `<b>`, `<u>` only, because `_csrCleanPaste` strips everything else on the way IN.
    So I could not reproduce the image; what I could do is remove the variable.
  - **📋 Copy text**, in the toolbar beside B / I / U, on the editable draft AND on a
    locked one — a finished draft is the one most likely to be sent. It writes BOTH flavours
    explicitly with the async Clipboard API, with a copy-event fallback for any browser without
    it. No more depending on what a hand-drag through a scrolling box happens to produce.
  - **Nothing is re-styled on the way out**: no classes, no colours, no widths for Gmail's
    sanitiser to argue with, so it lands in Gmail's own font, aligned with the rest of the
    message, bold and underlines intact. `<meta charset="utf-8">` leads, or the Hindi draft
    arrives as mojibake.
  - The plain flavour keeps real line breaks (blocks → `
` before the tags are dropped),
    so anywhere that takes no formatting still gets readable prose rather than a wall.
  - The button says **✔ Copied** on itself for a moment. A toast on a long draft appears
    where nobody is looking, and "did that work?" is what makes somebody press four more times.
  - `ClipboardItem` added to the eslint browser globals — a real global the checker did not know.

  ⚠️ **Still open:** the image behaviour is unreproduced. If it happens again WITH the
  button, the next thing to ask is which browser and whether an extension is in the way.

### ✅ SHIPPED 2026-09-22 (6) — the Live bucket asks SEVENTEEN, not fifteen

The founder corrected the sequence he gave this morning: **On Behalf of at 2** and **Claim Type
at 12**. Both had been switched OFF that same morning when his list ran to fifteen — and
switching off rather than deleting is exactly why putting them back was a config change and not
a rebuild. Three claims already held a relationship, three a claim type; all of it was still
there.

**The order, as it now reads down the page:**
`1 Company Name · 2 On Behalf of · 3 Policy type · 4 Policy No. · 5 Policy inception Date ·
6 Disputed Amount · 7 Name Of Hospital · 8 Date of Admission · 9 Date Of Discharge ·
10 Diagnosis · 11 Patient Complaint · 12 Claim Type · 13 Claim No. · 14 Rejection Date ·
15 Rejection Reason · 16 Comment · 17 Assign To`

  - **His dropdowns, not the seeded ones.** On Behalf of goes from generic to named — Self,
    Father, Mother, Wife, Husband, Children, Brother, Sister, Friend — replacing
    Spouse/Parent/Sibling. Which matters: this line ends up in a legal letter, where nobody
    writes "spouse". Claim Type becomes Reimbursement, Deduction, Rejection, Query, Delay in
    process; **Consumer** removed as he asked.
  - **Two live claims hold Spouse and Sibling**, which are not on the new list. Neither is lost:
    the field already renders an unrecognised value as the selected option, so the staffer sees
    the old word and can change it. Nothing is rewritten behind anybody's back.
  - **sort_order was moved as well as the form.** The form reads `CSR_GIST`, but the case report,
    the assessment sheet and the bucket designer all read `sort_order` — the two disagreeing is
    how the report stopped matching the screen the first time. `relationship`→**10**,
    `rejection_type`→**105**; both slots were free.
  - Verified on a copy of the live database and run **twice**: `fixed: 2`, then `fixed: 0`.
    A correction that keeps matching would report "fixed" on every worker start for ever.
  - ⚠️ **One thing worth watching:** the form now carries both **"Policy type"** (health /
    motor / life, 3rd) and **"Claim Type"** (the kind of dispute, 12th). Those two names are one
    word apart. The hint under Claim Type says *"What KIND of dispute this is — not the policy
    type above"*, but if staff mix them up, the answer is to rename one of them.
  - 🐞 **Three tests asserted the OLD spec** and failed — correctly. `gist-fields.js`
    asserted the two fields were ABSENT; it and `live-sequence.js` and `verify-22sep-list.py`
    were rewritten to the new spec, by **name and index**, not loosened until they passed.

### ✅ SHIPPED 2026-09-22 (5) — the code screen, latency, statuses, test claims

**✅ OTP: one tap is one code.** The complainant taps, nothing visibly happens, they tap again.
`sendCode()` disabled nothing — five taps in five seconds sent five codes, spent the whole hour's
allowance and locked somebody out of their own claim page. The only reply was a red line telling
them they had asked for too many, for a limit no screen had ever mentioned.
  - **The limit is 5 per claim per rolling hour** (`MAX_CODES_PER_HOUR`). It stays: it stops a
    leaked link ringing somebody's phone all day, and with a freeze in place five is plenty.
  - Both buttons freeze the moment one is pressed, **before the request goes out** — the gap
    between the tap and the reply is exactly where the extra taps land.
  - The wait counts down. The allowance is shown: *"Send it again (3 left)"*.
  - When the wait ends with no code, the screen says what to do — spam folder, signal — and gives
    **+91-98260 11116**, the number already published in the site footer.
  - The server now sends what the page cannot know: `left`, `cooldown_sec`, and the **real**
    `retry_after_sec`. The window ROLLS, so the wait is usually minutes; *"about 22 minutes"*
    replaces *"please wait a little"*, which is not an instruction anybody can follow.
  - A send that FAILS unfreezes at once — the server deletes that row, so it costs them nothing
    and a wait would punish them for our outage.
  - **App Health now reads login_health's outcomes**, so the watchdog tells staff when codes stop
    arriving instead of waiting for a complainant to ring up. Checked live the same day:
    **portal 23 sent, 0 failed** — delivery was never the problem, the taps were.
  - `uitest/claim-code.js`: six taps produce one code, in both languages.

**✅ Latency — measured, and it is not the server.** Origin answers `/nidaan/ops` in **24 ms**,
the box sits at **load 0.29** on two cores, the database is **21 MB**, 9.4 GB RAM free.
  - **The ops page is ONE 1.25 MB file sent with `no-store`** — re-downloaded in full on every
    open and every refresh. Now `no-cache` + `ETag` + `Last-Modified`: the browser still asks us
    every single time, so a deploy is picked up exactly as before, but an unchanged page costs a
    **304 with no body** instead of 320 KB. Verified live: `code=304 wire=0B`.
  - 🐞 **The ETag alone was worth nothing.** Cloudflare re-compresses with Brotli and
    STRIPS the ETag when it does, so the browser got no validator at all. `Last-Modified`
    survives the transform; both go out now. Only caught by checking through Cloudflare rather
    than at the origin.
  - **nginx had gzip ON with its defaults, and the default `gzip_types` is `text/html` ALONE** —
    so every `.js` and `.css` went out raw. Now compressed: page assets **70 KB → 21 KB**, ops
    page **410 KB → 336 KB** at `comp_level 5`.
  - The access log had **no timings at all**, so "is it us or the network" was unanswerable. It
    now records `rt=` and `urt=`.
  - ⚠️ **My own measurement was misleading and is corrected here.** The per-request numbers
    I first quoted came through a **Boston** Cloudflare edge (`CF-RAY: ...-BOS`), not Mumbai.
    Staff in India see materially better figures; do not quote those numbers to them.
  - Polling was **not** the problem, contrary to first impressions: `/changes` answers in 13
    bytes, and the panel actually reloads about once a minute, not every ten seconds.

**✅ Statuses — and the colour complaint was two different bugs.** Counting the live database
first changed the whole job: `review_delivered` holds **115 claims, the majority**, and appeared
in **no dropdown, no pill stylesheet and no board column list**. It rendered as a bare lowercase
word. That was never a colour bug; it was four hand-kept copies of one list.
  - The offered list is now **Intimated · Assigned · In Review · Review Query · Review Query
    Resolved · Review Delivered · Withdrawn** (founder's six, plus `review_delivered`, which he
    agreed to keep rather than migrate 115 claims).
  - `in_negotiation`, `resolved_won`, `resolved_lost`, `closed` leave the **dropdowns** and stay
    in the **code** (his decision). `resolved_won` is what moves a case to `pending_payment` in
    `biz_nidaan_case_state`; deleting it would change what happens to such a case rather than
    tidy a menu. One live claim is `in_negotiation` and still works.
  - A raised query now waits on the **customer**, not on us; an answered one comes back to us.
    Without that, a new status fell through to `intake`/`none`.
  - 🐞 **The colour bug was in the design system, not the pill.** `--nd-orange-text`
    (`#fdba74`) is defined for dark and **never redefined for light** — the one `*-text`
    variable missing its light pair. Measured **1.37:1** against a 3:1 floor. Fixed at source
    (`#c2410c`), which fixes everything else using orange too.
  - `uitest/status-pills.js` renders **every** status in **both** themes and computes the real
    contrast ratio. All 22 pass; the worst is now 3.15:1.
  - `deploy/verify-claim-statuses.py` fails if the server list, the page list, the pill rules or
    either language's labels ever drift apart again.

**✅ NP-118, NP-112, NP-44, NP-119, NP-39 archived** (founder: testing claims). Checked first:
**zero payment rows** across all five, so Revenue is untouched. NP-44 carried
`l2_payment_status='paid'` with no ledger row behind it — itself the mark of a hand-set test.
Three of them sit on **LAKSHYA PARDESHI's own staff account**, which was deliberately NOT
touched. Archived = hidden from every working view, never deleted, restorable. Contacts left
alone (his answer): a claim's phone/email carry no uniqueness, so they were always reusable.

### ✅ SHIPPED 2026-09-22 (4) — one dead name, and several features that came back

**🚨 The big one: the ops page threw a ReferenceError on EVERY load, and had been doing it
for days.** `csrFocus()` was deleted on 22 Sep - it jumped to a Live Cases field that is not on
the escalation screen, so it had never worked - but the line that handed it to window stayed:

    window.escQuery = escQuery; window.csrFocus = csrFocus;

Script evaluation reaches that line, throws, and **everything below it in the block never runs**.
`function` declarations are hoisted; `let` and `const` are not. So these stayed in the temporal
dead zone for the life of every page load:

  - `_dwClaim` and friends → **"Ask the complainant for what is missing" did nothing.** That is
    the button in the founder's screenshot. Its first line is `_dwClaim = claimId`, which threw
    `Cannot access '_dwClaim' before initialization` before anything could open.
  - `_cbState`, `_cbBusy`, `_cbLast`, `_cbSheet`, `CB_BUCKETS` → the **Case Board**
  - `_waiSel`, `_WAI_SENDER`, `_waiOnDuty`, `_waiMayReply` → the **WhatsApp inbox**
  - `_lineStatsAt`, `_lineStatsData`, `_qrPollTimer`

**🚨 And the check that exists to catch exactly this had been blind for months.**
`npm run check:pages` missed it twice over:
  1. it skips any inline block containing a `{{NAME}}` placeholder, because an unrendered
     server-side template is not JavaScript. But the pattern also matches **`{{1}}`**, and
     nidaan_ops.html describes a WhatsApp template - *"a single {{1}}=name variable"* - inside an
     HTML title attribute. On that one word it skipped the page's **entire 18,500-line script
     block** while printing *"nothing reported"*.
  2. it harvests `window.foo = ...` as a global, so `window.csrFocus = csrFocus;` **registered
     the broken name as valid and then declared its own line fine.**

  Both closed. A placeholder now only counts if the block also fails to COMPILE, and inside the
  page's own code `window.foo = foo;` is treated as an export, not a declaration - it is a
  separate `.js` file where that line is real evidence. Re-run proves it: the checker now reports
  `line 16614 no-undef 'csrFocus' is not defined` on the old file, and nothing on the new one.

  **`uitest/ask-complainant.js`** is the regression guard: it loads the real page over a real
  HTTP origin and fails if **anything at all** is thrown while loading, then walks the journey.

**✅ A confirmation before the complainant is asked** (founder, 22 Sep: *"if accidently anyone
clicked it then it goes to customer unnecessary"*). Nothing ever went out on one tap - the
request window has its own read-back gate and the server refuses a send without the checksum that
screen was issued. But nobody on the team had seen it work, so the button now asks, and the
asking is where the reassurance goes: *"Nothing reaches the complainant yet."* **Go back** returns
to the documents window, so a stray tap costs one tap and not your place.

**✅ Razorpay: the two products can no longer share an account in silence (A, B, C).**
  - Checked first, and the answer is good: `NIDAAN_RAZORPAY_KEY_ID` **is** set on the server and
    is **not** the same as `RAZORPAY_KEY_ID`. NidaanPartner and Sarathi are on separate accounts.
  - **A.** But the fallback that would hide it was silent, and the check for it was pointed at
    the wrong product: Nidaan's own ops health page read **`RAZORPAY_KEY_ID`** - Sarathi's key -
    so Nidaan's payments could be entirely unconfigured and the light would still be green. It
    now reads Nidaan's, and says *"Running on Sarathi's Razorpay account"* if the fallback is
    ever live. Startup logs the same.
  - **B.** Razorpay returns a `short_url` with every subscription - its own hosted page for that
    subscription. Sarathi's code has always kept it; Nidaan's **threw it away**.
  - **C.** So somebody whose checkout sheet fails - a blocked script, an in-app WhatsApp or
    Instagram browser, a UPI app-switch that kills the tab - now gets that link, in Hindi or
    English, when they close the sheet, when the payment fails, and if the sheet cannot open at
    all. **Not** a way around account settings: the hosted page is the same account and offers
    the same methods. It is a way through a broken screen.
  - **`deploy/verify-razorpay-split.py`** is re-runnable and fails the moment a Nidaan route
    starts reading Sarathi's keys.

**✅ NP-84 pulled back out of Level-2** (founder: moved to Live Cases in error). Done through
`undo_handover()`, not with SQL - it checks that no Level-2 work has started, demands a reason,
and writes the reason on the claim's own log. Rehearsed on a copy of the live database first.
State now: `pipeline_stage` empty, `l2_handover_at` null, back on the **L2 Claims** list. The
documents tick (22 Sep 07:57) was deliberately left alone - "every paper is in" is a separate
fact, untickable by hand if it was also premature.

  ⚠️ **There is no button for this.** `POST /cases/{id}/handover/undo` exists and is
  super-admin only, but nothing in the ops page calls it. Worth adding if this happens again.

### ✅ THE 16-ITEM LIST IS CLOSED (22 Sep)
#1 · #2 · #3 · #4 · #5 · #6 · #7 · #8 · #9 · #10 · #11 · #12 · #13 · #14 · #15 · #16, and the Live
bucket sequencing. Four batches, each shipped and verified against a copy of the live database
before deploying, with the live worker log confirming the one-time corrections landed.

### ✅ SHIPPED 2026-09-22 (2) — the bucket screen on real devices, and the Sarathi cleanup

- ✅ **The bucket screen works on a phone, a tablet and a laptop.** Measured first, on the real
  screen at the sizes people hold:

  | | sideways drag | tap targets under 44px |
  |---|---|---|
  | Android 360 | **638px** | 31 |
  | iPhone 390 | 609px | 31 |
  | iPhone landscape 844 | 154px | 31 |
  | iPad portrait 768 | 231px | 31 |
  | iPad landscape 1024 | — | 31 |
  | Laptop 1440 | — | 31 |

  Ten columns do not fit a phone. Below 900px — and on **any touch screen up to 1200px** — each
  row is now a **card**: claim and person at the top, then the company, then the pairs that belong
  together (amount with age, type with step), then why it is waiting, then full-width buttons.
  **ONE MARKUP:** it is still a table; the cells carry their column name in `data-label` and CSS
  does the rest, so rotating a tablet or dragging a window narrow just works, and a phone can
  never drift away from what the desk shows.
  - **The pointer decides, not the width.** Touch needs 44px controls and 44px controls need
    room, so an iPad in landscape gets cards while a 1024px *desktop* window keeps the table. I
    first tried shaving padding to make the table fit an iPad: 24px of overflow became **117px**.
    I was shaving pixels off a wall.
  - **The 12px floor is set where the sizes are set**, not shouted over from a media query —
    `.l2why .nt` is two classes deep and beat my one-class override, which is why the note was
    still 11.8px after I had "fixed" it.
  - **Now 0 problems across all six devices, in both themes.**
- ✅ **`uitest/device-audit.js`** — the measurement, kept. Six sizes, both themes, screenshots on
  demand (`SHOTS=1`), each device measured against **its** standard (44px for a finger, 24px for
  a mouse — measuring a laptop against a fingertip is measuring the wrong thing). It also checks
  every piece of text against the colour actually behind it, because *works in both themes* is a
  ground rule here and dark-on-dark is how it gets broken.
  - ⚠️ **It caught two faults in itself before it caught any in the product:** it reported
    *"0 problems across 6 devices"* while rendering **nothing** (a SyntaxError — it now proves
    claims are on screen before measuring), and a fixture claiming 1 claim late and 2 red, which
    is impossible, which made the summary render **"-1 need looking at"**. I nearly went and
    "fixed" correct code.
- ✅ **One real fault it surfaced:** a bucket with no guidance text rendered an **empty coloured
  banner** — a bar of screen spent on silence.

- ✅ **Sarathi cockpit: every page now passes `no-undef`.** Four faults of the shape that cost two
  days on the Nidaan side. `toast && toast(...)` reads like a guard and is not one — reading an
  undeclared name **throws**; this page's helper is `showToast`. **Two of them threw before the
  line that refreshes the list:**
  - *Move a lead to Customers* → threw before `loadLeads()`, so the lead stayed on screen and the
    move looked as though it had failed.
  - *Add a customer* → threw before `loadCustomers()`, so the new customer was nowhere to be seen.

  Which is exactly the double-tap cause the founder described: a person told nothing, who sees
  nothing change, does it again. Also `loadDMLeadList()` never existed, so the Send-DM-to-segment
  window sat on *"Loading leads…"* for ever (it is `mktLoadLeads`); and three i18n keys were
  defined twice with the second silently winning — the WhatsApp wizard's **Next** showed as
  *"Next →"*, and the ticket window read *"Description *:"*.
  - 🟡 **One left for the founder to decide:** `index.html` defines `fc_title`/`fc_desc` twice with
    **different copy**, so the homepage heading that says *"First 500 Founding Customers"* in the
    markup renders as *"Partner & Earn Program"*. Which he wants is a content decision, not a bug
    with one right answer — **nothing visible was changed**; the pair that renders today is
    untouched, the pair that never rendered is renamed and kept.
  - `microsite.html` is a server-side **template** (`bio: {{BIO_JSON}}`), so the checker skips a
    templated block and says so. A check that reports a non-problem is one people learn to ignore.

**Not yet audited for devices:** the claim panel, the gist window and the documents window. The
bucket board was the founder's "especially", and it is done; those three are the next pass.

### ✅ SHIPPED 2026-09-22 — the case email, and the ten items closed
- ✅ **One tap, one action (founder, 22 Sep: *"most are impatient they tap/click multiple times,
  so we dont want any glitch"*).** The cause is worth naming: people tap again because **nothing
  visibly happened**. A move takes half a second on a good connection and three on a phone in a
  basement, and in that gap the button looks exactly as it did before. So the guard does two
  things — it swallows the extra taps, and it **shows that the first one landed**.
  - **One place, capture phase**, before any onclick runs. A guard added button by button is one
    somebody forgets on the button that mattered. Covers buttons, claim rows, board and task
    cards and tabs.
  - **How long it stays shut** is the part that needed care: it watches the requests **that tap**
    started (those beginning in the 200ms after it) and reopens when they finish — not "any
    request in flight", or the background notification poll would leave every button dead. A
    button that sends nothing reopens after 200ms. **Ten-second ceiling** so a hung request can
    never leave somebody unable to move a claim: noisy is recoverable, stuck is not.
  - **The other shape of it:** tap *Move*, a dialog appears under the finger already coming down,
    and the second tap lands on *Yes*. Dialog buttons are not live for 280ms — no flicker,
    nothing greyed; the guard just ignores a tap nobody could have aimed.
  - **Server side checked, not assumed:** a move to the bucket a claim is already in, a second
    handover, a second draft query and a second start are each refused — so two people racing
    cannot double-apply anything either.
  - **18 assertions in a real browser**, kept as `uitest/one-tap.js`. Run it after any change to
    that guard or to `openModal`.
- ✅ **The case email, answered (founder, 22 Sep: it comes from WhatsApp AND from staff typing
  it).** The value was already single — one row in `nidaan_claim_fields`, written by the WhatsApp
  handler and by staff through the same `set_field()`, read by every screen. **There are no copies
  to keep in step**, which is the only way "changed in one place, changed everywhere" is ever
  actually true. What was not flexible was WHERE a person could see it: the block lived on the
  **Escalation screen alone**, so a staffer in Pending Docs with the complainant on the phone had
  nowhere to type it. It is on the claim now, in **every bucket**.
  - 🐞 **And the WhatsApp side had a real gap.** The capture only ran while the checklist still
    *wanted* the credentials — so the first message was taken, the line was ticked, and a later
    message **correcting a typo in the address was read and thrown away in silence**. Every letter
    to the insurer goes from that mailbox. A genuine correction now lands and is recorded **as a
    correction**, naming what it was before; the same address sent twice writes nothing.
  - Also removed a message that can no longer be true: a failed save told the claim *"the gist is
    locked — a super admin has to put them on the claim"*. Those fields are in `NEVER_LOCK` now,
    so that message would have sent somebody hunting for a lock that is not there.

### ✅ THE TEN SCREENSHOT ITEMS (21 Sep) — ALL CLOSED
Re-checked on 22 Sep against the file a browser actually receives, not against notes:
**1** With off the board and on the claim · **2** the escalation question box saves (the two
`NameError` endpoints) · **3** the Pending Draft button — and with it **every** forward move,
which had been dead for two days · **4** no "To start" step · **5** downloads keep their name ·
**6** the case report reads 1-15 · **7** the Escalation query button · **8** 10/20/30 day flags,
no reminder ledger · **9** a pencil on each field where it is read · **10** Escalation does not
go back to Live Cases.

### ✅ SHIPPED 2026-09-22 — the gaps document is finished, page by page
Re-read end to end against the code, not against notes. Everything in it is now either done or a
question the founder marked for discussion.

- ✅ **Page 10 — the Live bucket asks for his fifteen, in his order, in his words.** Company Name
  · Policy type · Policy No. · Policy inception Date · Disputed Amount · Name Of Hospital · Date of
  Admission · Date Of Discharge · Diagnosis · Patient Complaint · Claim No. · Rejection Date ·
  Rejection Reason · Comment · **Assign To**. The bucket's own fields are relabelled and reordered
  in the database too, so the claim panel, the assessment sheet and the case report read the same
  way round as the form. Two of the fifteen are not ordinary fields: **Policy type** re-seeds the
  document checklist, so it calls that endpoint rather than writing the column behind its back;
  **Assign To** calls the same assignment endpoint the claim panel uses.
  - **Company Name is now the SHARED picker** (`nidaan_insurers.js`) in all four places that ask
    it — claim header, gist, draft form, claim edit. I had written a second dropdown with the same
    rules; two copies of one rule is how a company ends up spelled four ways.
  - **Off the form:** "On behalf of" and the old ClaimShield "Claim Type" (the kind of *dispute*)
    — deactivated, not deleted; **6 claims** still hold values and still show them. And the **case
    email stops being required to leave Live Cases** — it is not one of the fifteen, and pages 7-8
    put it on the Escalation screen. **Both** claims sitting in Live Cases were blocked by exactly
    that.
- ✅ **Pages 7-8 — the case email and password are correctable where they are used.** They were
  already shown on the Escalation screen, behind a "Correct" button that jumped to a **Live Cases**
  field which is not on that screen — so it had never done anything. Each line now has its own
  pencil and edits in place. No pencil on the password for someone who cannot see it.
  **The credentials never lock**: everything else locks once a claim moves past its bucket because
  it is finished work; an email account is not a finding, it is how we write to the insurer.
- ✅ **Page 7 — the Escalation board says what was DONE.** A green
  *"✅ Escalated on 18-09-2026 · 4 days ago"*, the same shape as the draft-query-resolved badge.
  Every other column answers "what is missing"; once we have written to the insurer nothing is.
- ✅ **#6 — the case report reads 1 to 15.** Its case-details block was in ClaimShield's order.
  Money is now its own section; the company, claim number, amount and rejection reason were
  printed **twice** in two different orders and are printed once. The assessment sheet drops the
  two lines it can no longer fill instead of printing them empty on every new claim.
- ✅ **Page 1 — "All documents received" asks before it speaks in your name.** It never moved the
  claim; what it does is unlock Move and put the ticker's **name** against "every paper is in". One
  stray click on a dense card list did both silently. Both places that tick it now ask, through
  the shared `ndConfirm`, and **saying no puts the checkbox back** — without that, cancelling
  leaves a tick that does not match the server, which is worse than never asking.
- ✅ **Caught before shipping:** moving Company Name to the shared picker turned it into a mount
  point, and the **Draft form** draws its facts in one go and mounted nothing — it would have
  shipped a blank space where a dropdown was. Found by asking who else renders a shared control.

**Already done, confirmed on re-read:** page 1 L2-Claims filters (authorisation / complainant
dashboard / email verified — `insured_email_verified` is a real column set when they open the
portal from that email) · page 2 Past Medical Records removed · page 3 back-option on stacked
windows and the insurer's own claim number on Live Cases · page 4 discharge-before-admission and
the no-return-to-Live-Cases fence · page 5 Approved by / Approved on removed · page 6 Draft button
hidden in Live Cases, draft query moves nothing, step picker gone.

**Page 2's open question is now answered** — see the case-email entry above.

### ✅ SHIPPED 2026-09-21 — the bucket screens do what the founder actually described
Founder's ten-item list, with screenshots. His framing: *"every step is manual… at this stage any
incorrect flow or incorrect processing we cannot afford. Nidaan client is upset due to not setup
the bucketing system correctly as per their expectations. most times we overbuilded rather to keep
things simple and manual."* So the pattern through all of it is **take decisions away from the
software and give them back to the person.**

- ✅ **#2 — the escalation question box and the reminder clock were both 500ing.** Two endpoints
  (`ops_escalation_reply`, `ops_escalation_due`) used `bk.` with nothing of that name imported — a
  `NameError` on every call, which the screen showed as *"could not record"*. Both now
  `import biz_nidaan_buckets as _bk`. Live: `escalation_due()` returns reminders=1, owed=1.
- ✅ **#5 — downloaded documents keep their name.** `_doc_download_name()` + a
  `Content-Disposition` with RFC 5987 `filename*`, so a Hindi or bracketed name survives the trip.
  (Cost an outage on the way: the helper was inserted *between* `@app.middleware("http")` and its
  function, which handed the decorator the wrong callable. **Never insert above a decorated
  function.** The health gate stopped the rollout at slot 1 and both sites stayed up.)
- ✅ **#7 + #8 — Escalation stops deciding things.** Out: *"What did the insurer say?"* with
  **They agreed** / **They refused**, which closed the case or sent it to Lokpal on the software's
  reading. Out: the three *"reminder sent on"* date fields. In: **10 / 20 / 30 days gone** flags
  computed from the escalation date — visibility only, they send nothing and move nothing — and an
  **❓ Escalation query** button in the same shape as Pending Draft's, for when the insurer is
  waiting on *us*. Lokpal is a button a person presses. The reminder fields are **deactivated, not
  deleted**, so dates already recorded stay readable.
- ✅ **#10 — an escalated claim does not go back to Live Cases.** `NO_RETURN_TO_LIVE` in
  `biz_nidaan_buckets.py`; a super admin still can, with a reason. 8/8 on live data, and checked
  that nothing *else* got fenced: Escalation → Lokpal and Live Cases → Pending Draft untouched.
- ✅ **#9 — the Gist is a page you read, with a pencil on each line.** It used to open as nineteen
  input boxes and one Submit; changing one fact re-submitted the other eighteen, and the remark it
  left said *"Case details updated by X (7 items)"* and named none of them. Now every line shows
  its value as text with **✏️ Change** beside it, opening that line alone — same controls as
  before, so the insurer list, the date pickers and the admission-before-discharge check all still
  apply. **Each change writes its own remark**, naming the field and both values:
  *"✏️ Hospital name: “Apollo” → “Fortis”"*. Re-submitting an unchanged box writes nothing.
- ✅ **#1 — *With (assign staff)* is off the board and on the claim.** The board is a list you
  scan, and ten columns is more than anyone reads across on a phone. The picker now sits on the
  claim panel, under the facts of the case, labelled **With — who is working on this**. It is on
  the claim in **every** bucket, not only Pending Draft: a claim has to be assignable wherever it
  is sitting, and the panel is one click from every row, so nothing is lost. *Claim type* stays a
  column, as asked. (Also fixed on the way: the list of people was only loaded when the board
  drew, so a claim opened from a link or a search would have shown an empty picker.)
- ✅ **#4 — there is no *To start* step.** Handing a claim over from L2 Claims now puts it straight
  into **Live Cases**. Two acts did one job, and between them the claim belonged to nobody. The
  waiting list is **not deleted**, deliberately: if starting ever fails, or a claim was already
  waiting when this shipped, it must not become invisible. The rail entry appears **only when
  something is stuck**, reads *"Handed over, not started"*, and in normal running nobody sees it.
  Pulling back an accidental handover still works while the claim is untouched in Live Cases, and
  is refused once it has been moved on — 20 assertions on a copy of the live DB, including that
  the documents tick and the handover note are still the real gates.
- ✅ **#3 — the Pending Draft button, and why NOTHING happened.** `l2Move()` tested
  `to !== 'escalation'` when its parameter is called **`toKey`**. There is no `to` in that
  function — it exists in four *other* functions, which is why nothing page-wide noticed. The
  ReferenceError was thrown while building the move window, so the call died **before** anything
  appeared: no window, no error on the page, nothing to say why. And because `&&` stops at the
  first false, it only threw when the destination had **more than one step** — which is every
  bucket except Live Cases. **So since 19 Sep no claim could be moved forward from the ops screen
  at all**, by the row shortcut or by the *Move…* menu. Proven both ways: the deployed file
  throws `to is not defined`, the fixed one opens the window with all four Pending Draft steps.
  **I introduced this on 19 Sep** in the escalation-screen commit (`3caeaac`).
- ✅ **And the rest of "check all buttons".** Every one of the **418** handlers the page names is
  now reachable from a click; **one was not** — *Open* on the **Reviewed · fee due** list called
  `viewClaim`, which has never existed anywhere in the page, so that button has always done
  nothing. It now calls `openClaimDrawer`, like every other Open on the screen. No duplicate
  top-level function names. New `deploy/verify-ops-buttons.py` keeps it that way.
  ⚠️ **It does not catch the `to`/`toKey` kind** — that needs a real JavaScript linter with scope
  analysis (eslint `no-undef`). A regex version reported 2,000 false names and was thrown away; a
  check people learn to skip is worse than none. **Worth deciding on: adding eslint.**
- ✅ **Page 5 — the person holding a claim hears about it every time it moves.** A move used to
  tell whoever is **on duty** for the bucket the claim arrived in — useful, but not the same
  person. The assignee now gets their own notice, worded as theirs (*"Your claim NP-65 is now in
  Pending Draft"*) and carrying **what that step needs**, taken from the bucket's own guide so
  they do not have to go and look it up. They are removed from the roster list, so nobody is told
  the same thing twice. Rides the existing `bucket.move` key — Telegram and bell, no email —
  rather than inventing a key whose email behaviour nobody has decided. An unassigned claim
  behaves exactly as before, and a failed lookup is logged and ignored: **a claim must never fail
  to move because a notification could not work out who to tell.** 10 assertions on a copy with
  `notify_staff_inapp` replaced by a recorder, so nothing left the process.
- ✅ **#9 REDONE — the pencil is on the field, not behind two buttons.** My first attempt was the
  wrong shape: correcting a wrong hospital name meant *open claim → open Gist → find the line →
  Change → type → Save*. Five steps to fix one word that was already on the screen. Now the facts
  at the top of a claim — **Complainant, Patient, Insurance Co., Disputed, Policy No.** — each
  carry their own ✏️. See it wrong, press it, type, **Save**. Two steps. Same endpoint, same
  rules, same remark. **Phone has no pencil on purpose** (it is the number our messages go to and
  stays with the admin-only claim edit), and a field locked as finished work shows 🔒 instead.
  Locks come from `for_claim`'s own `locked` map — the same function the Gist uses, not a second
  copy of the rule. 15 assertions rendering the real function under node.
- ✅ **eslint added — and it found four more of the same bug.** One rule, `no-undef`: *does every
  name this code uses actually exist?* Style is deliberately left alone, because a linter that
  also complains about spacing is one people switch off. `deploy/verify-page-js.mjs` joins a
  page's inline scripts (they share one scope in the browser, so they must be checked together),
  discovers what the page's own script files put on `window` rather than keeping a list that
  rots, and maps line numbers back to the HTML. **Run it with `npm run check:pages`.**
  Proof it works: run against Friday's file it reports `'to' is not defined` at line 13918 — the
  two-day outage, found in under a second.
  - 🐞 **nidaan_start.html** — `setLang(saved || sys)`. `sys` never existed. A **first-time
    visitor** (nothing saved) arriving after the DOM was parsed hit a ReferenceError and the
    language was never applied, so they saw whichever language the markup starts in rather than
    Hindi. On the signup page.
  - 🐞 **nidaan_review.html** — the ₹499 review page sent `ref_code: (typeof _ref !== 'undefined'
    && _ref) ? _ref : ''`, and **`_ref` was never defined on that page**. The `typeof` guard meant
    it failed silently: **every ₹499 review started at `/nidaan/get-reviewed` was recorded with no
    referrer**, showing as a Direct lead instead of crediting the branch or staff member. It now
    reads the code exactly as `nidaan_start.html` does (`?ref=` / `?branch=`, falling back to
    NidaanTrack's first-touch), and the page now loads `nidaan_track.js` so that fallback exists.
  - 🐞 **partner.html** — the cross-signup CTA read `a.name` where `a` is declared **inside** a
    try block and the CTA sits outside it. ReferenceError every time, so that CTA has never been
    shown to a partner.
  - 🐞 **partner.html** — `_regEmail` was never declared. It works by accident (sloppy-mode
    implicit global) and is one `'use strict'` away from breaking OTP verification. Now explicit.
- ✅ **The password check you allowed.** 3 case-email passwords stored, **0 overwritten with
  dots**, 0 blank. Nothing was damaged; the `set_field` guard is preventive only.

**Still on the lint list, NOT yet fixed** (Sarathi side, and lower risk — worth a pass before the
project closes): `dashboard.html` calls a bare `toast(` in 5 places, plus `showSignupConflict`
and `loadDMLeadList` which are not defined anywhere; `microsite.html` has a script block that
does not parse.
- 🔒 **Found while building #9: a row of dots could overwrite the case email password.** Anyone
  without credential rights reads that field as `••••••••`; nothing stopped the form sending the dots
  back as the new value, which would have locked the team out of the case mailbox with nothing in
  the log to say why. Guard added in **`set_field`** — the one door every field write passes
  through — so it holds at every endpoint, not just the gist form. 8/8 on a copy of the live DB.
- ✅ **Two journeys stopped crying wolf** at ordinary staff work (a real query raised, a real
  reminder recorded), and the escalation journey was **rewritten to the new model** rather than
  deleted — it now proves the day count is arithmetic anyone can check, and that however many
  flags have passed, **the claim does not move on its own**. 19 passed, 0 failed, 1 skipped.

**Still open from the ten-item list:**

### ✅ SHIPPED 2026-09-19 — messages that say less, alarms that mean more
- ✅ **The ₹588 leak closed at one choke point.** A branch paid us ₹588 and charged the complainant ₹1,200; our confirmation showed the complainant **₹588**. Founder's ruling was wider than the bug — *"only welcome message should go to all parties, not containing the amount or plan or whatever… whosoever is doing payment they will get payment message from their bank."* `_strip_money()` in the WhatsApp orchestrator, `thank_you_payment` rewritten money-free, money out of the funnel notifications. **Price nudges suppressed when a branch or CP is the payer** (`_paid_for_by_an_intermediary()` — 71 branch claims protected from being asked for a fee somebody else owes). **Subscription email names the plan, not the amount.**
- ✅ **Alarms split into two kinds.** An **incident** broke and acting now would fix it: it pages, and it repeats. A **gap** is a standing fact a person fills in when they get to it — it stays RED in App Health, where the work is done, and **never pages**. `_GAPS` (8 entries) vs `_CRITICAL` in `biz_nidaan_health_watch.py`. Verified: the branch-login gap had paged 3× on 18–19 Sep; its next 12-hour re-notify came due and correctly did not fire.
- ✅ **Unanswered-conversation alarm survived its own fix** — stickers/reactions/empty messages were excluded from the listed rows but **not** from the correlated subquery deciding `last_dir`. Rewritten as a CTE; live reading "unanswered: 0".
- ✅ **Email Radar false alarm (today's trigger).** One failed IMAP poll of `np@` sent "🔴 STOPPED WORKING" to **14** super/sub-super admins; the next poll, 15 minutes later, succeeded. Radar's own alerting correctly stayed quiet — it waits for 3 consecutive failures. **App Health now reads that threshold from radar**: one mailbox, one opinion. A wobble is named in the panel note and pages nobody; at the threshold both fire together. The blip also left **no trace in the log** — failed polls now log a warning with the mailbox and consecutive count whether or not they alert.
- ✅ **74 of 158 claims had no document-checklist rows**, so every tick a staffer made vanished silently. `mark_doc_received` now seeds a missing checklist and retries.
- ✅ **`journeys/` — the safety net.** 15 journeys, 96 steps, each a thing a real person does, run against a **copy** of the live DB. Refuses to run without `NIDAAN_NO_OUTBOUND=1`; `_assert_no_live_db()` refuses if any module bound `db.DB_PATH` to the live file at import. `cd /tmp/jr && NIDAAN_NO_OUTBOUND=1 /opt/sarathi/venv/bin/python -m journeys.run --overlay /tmp/jr --quiet`

- ✅ **ALARMS NOW REACH ONE PERSON, AND ONLY IF STILL TRUE** (founder: *"stop these alarms otherwise people will ignore and wont be taking seriously… filter all alarm first if really something happened or it's a false alarm, restricted it to me only till we create a new alert bot on telegram"*). New `biz_nidaan_alarm_policy.py`, gated at the one point every alarm passes through (`notify_staff_inapp`):
  - **Audience** — 15 alarm keys route to the founder alone. Not a channel downgrade: the recipient list itself is replaced, so bell, Telegram, push and email all land in one place. Change it without a deploy via ops setting **`alarm_audience_staff_ids`**; that is also how this lifts when the Telegram alert bot exists.
  - **Re-verification** — every alarm with a registered re-check is asked, immediately before delivery, whether it is *still* the case. Registered: `health.subsystem`, `radar.mailbox_down`, both `conversation.unanswered` keys — which re-check **the people the message names**, not merely whether anyone at all is waiting.
  - **Fan-out guard** — some sweeps notify one person at a time with identical text (`bucket.stale` did this for 12 staff). Same key + same text inside a ten-minute block is delivered once, so narrowing does not turn 12 messages to 12 people into 12 copies to one.
  - **Three rules prevent silence:** an alarm with no re-check is always sent; a re-check that errors sends; a gate that fails sends unfiltered. Noisy is recoverable, silent is not.
  - **Untouched on purpose:** work sent to the one person who owns it (task assigned, SLA breach on *your* task, @mention, draft query) and business activity (claim filed, payment taken, signup). Redirecting those would break the process rather than quieten it.
  - Caught before shipping: the re-check rebuilt the subsystem list from `_subsystem_checks()`, which **omits Disk** — so a genuine disk-full alarm would have looked like a recovery and been swallowed. Now one source of truth, `health_watch.current_checks()`.
  - **39 assertions** across two suites on a copy of the live DB + 15 journeys green. Live audience verified = `[1] Dushyant Sharma`.

### ✅ SHIPPED 2026-09-20 — the gaps document is closed, 33 of 33
Verified item by item against the code and the live database, not against notes. Four were still open on re-check; all four are now done.
- ✅ **C1 was worse than "not done".** Dropping *Past Medical Records* from the health template was half the job: `effective_docs()` re-adds **any** checklist row the template does not recognise as a **custom** document, so on **55 live claims** the line came back reading *"Prior Medical — Asked for on this case."* — as though a staffer had specifically demanded it. Now marked **removed, not deleted**, so it leaves the list the way a staffer's own removal does, with a name and a readable reason. Guarded on `received=0`; all 77 rows backed up as INSERTs at `/opt/sarathi/backups/manual/prior_medical_rows_20260920.sql`. **Live: 0 still showing, 77 removed, backup intact.**
- ✅ **C5** — the 📝 Draft button is gone from Live Cases. That bucket builds the gist; every other bucket still reaches the draft.
- ✅ **C6** — Live Cases loses its one-click *"→ Pending Draft"*. Checked before removing: the **Move…** menu builds its list independently, so the destination is unchanged, just one deliberate click further away.
- ✅ **F7-i** — the document window now says **who asked last and when, before the message is written**. The cooling-off refusal always worked, but people only met it *after* composing, which reads as obstruction. Told first it is information. Fetched separately and never allowed to block the window.
- Verified: 10 assertions on C1 on a copy of the live DB (incl. idempotency and that no other claim type moved), `node --check` clean, no duplicate globals, 15 journeys green, ops page 200 on both slots.
- ⚠️ **Correction to an earlier claim:** Q5 of the work order ("25 claims marked all-documents-received with nothing attached") was **wrong** — it queried `nidaan_documents`, an empty legacy table. The real table is `nidaan_claim_documents`. Truth: 17 claims marked complete, all hold documents. Nothing needed clearing.

### ✅ PAYMENT ALARM — 2026-09-20 (founder-reported: "app health shows okay but I keep getting these emails")
- **Nothing was broken. Payments and webhooks are healthy.** The guardian claimed *"No Razorpay webhook has reached us in 24 hours — check the webhook URL and secret"*. Evidence says otherwise: nginx logged signed Razorpay POSTs returning **200 at 19 Sep 23:30**, and there have been **zero signature failures in a week**.
- **Root cause:** the check counted payment ROWS with `verify_method='webhook'` in 24h. That is a different question — `record_payment` is idempotent, so a webhook for a payment the browser checkout already recorded writes **no row, by design**. On a day when every payment completed in the browser, a healthy webhook looks dead. Live proof: 17 webhook-created rows in 14 days, last one 19 Sep 08:10.
- **Worse than noise:** it told a person to go and change a webhook URL and secret that were correct.
- **Fixed:** the handler now stamps `razorpay_webhook_last_at` the moment a correctly-signed webhook is parsed, whatever the event does. The guardian takes the **newer** of that stamp and the old row signal — strictly more accurate, no transition window (before the first stamp it behaves exactly as before). Seeded with the true last arrival from the nginx log. Plus a narrow send-time re-check: an alert mentioning anything *other* than the webhook is sent untouched.
- **Verified:** 6 assertions on a copy of the live DB (incl. a genuinely dead webhook still alarms, and an amount-mismatch finding is never re-checked away). **Guardian now returns 0 findings live.**
- Same family as the Email Radar false alarm: *a check whose question did not match its claim.*

### 🔒 SECURITY + DISK — 2026-09-20 (found while sizing the Oracle migration)
- ✅ **A bug was the only thing keeping our secrets off GitHub.** The six-hourly `git-backup.service` runs `git add -A` and push. It was trying to commit **seven `biz.env.bak.*`** (live SMTP passwords, API keys, JWT secret, backup passphrase), **nine ~500 MB server tarballs**, **`db-backup-repo/`** (the encrypted DB blob), **`.gnupg/`** and `.gitconfig`. **Nothing ever reached GitHub** — verified across every blob in every ref. The reason is not a safeguard: one `.bak` was root-owned, the service runs as `sarathi`, `git add` aborted with *Permission denied*. **The obvious fix — chown it so the backup works — would have published everything on the next run.**
- ✅ `.gitignore` secret patterns are now **prefix**-based (`biz.env*`); `backups/`, `db-backup-repo/`, `.gnupg/`, `.gitconfig`, `*.bak*` excluded. The old `biz.env` (exact) + `*.env` (suffix) matched neither `biz.env.bak.1785960845` nor the tarballs.
- ✅ `.bak` files moved to **`/root/secrets-archive`** (700, root) — out of any git working tree. Live `biz.env` untouched.
- ✅ **41 GB → 25 MB.** Each failed run abandoned a ~3 GB temp pack: 17 of them, ~11 GB/day. Disk **54 G → 14 G**. Repo `git fsck` clean, 1014 commits intact, working tree clean, both sites 200.
- ✅ **Code backup fixed and silently-failing-jobs made visible.** It had been failing every 6h since ~16 Sep with every dashboard green. New App Health check **"Scheduled jobs"** (`systemctl is-failed` over 7 units) — critical, so it pages (founder only, re-verified at send). Proven by making a unit fail on purpose and watching it detected, then cleaning it up.
- ℹ️ The encrypted **DB** backup was never affected — ran clean 02:30 today, as every day.

### ✅ SARATHI SAFETY NET — 20 JOURNEYS, BOTH HALVES COVERED (2026-09-20)
All 15 journeys were NidaanPartner. Before cutting a 29k-line file in half, the other half needed a net. **5 new journeys, 20 total, all green** — deployed and verified against deployed code.
- **The seam first.** 37 of 59 Sarathi tenants were created by somebody buying NidaanPartner, so the bundle handover is not an edge case — it is how most tenants exist. Covered: plan grants the bundle → link resolves → tenant live → somebody is actually in it; provisioning creates a usable owner; **buying again refreshes the same tenant** instead of accumulating duplicates; bundle expiry **can only shorten** (an unattended sweep moving the date forward would hand out months nobody sold); no dangling links or orphan agents; and the Nidaan→Sarathi wall holds in real SQL.
- **The SSO mechanism is already cross-domain** — `/nidaan/api/sarathi/access` mints a Sarathi JWT and redirects to `sarathi-ai.com/dashboard?token=...`. Not a shared cookie. **It survives the split as-is**; after splitting, step 4 (minting) moves to Sarathi or the two share the JWT secret. The founder's worry is genuinely the last domino, not the first.
- **Three defects found — all in my tests, none in the code:**
  1. `shorten_bundle_tenant` refused my call and was **right** (only shortens; I passed a later date). The never-extend guarantee is now its own assertion.
  2. The boundary check flagged `biz_nidaan_crm.py` for the words *"update leads"* in a **docstring**. Now reads only non-docstring string literals via `ast`.
  3. **The boundary check could not fail at all** — `glob()` ran against the working directory, so under `--overlay` it scanned the **deployed** code, not the code under test. Proven by injecting a real `FROM tenants` and watching it stay green. Now scans the tree the run actually loaded and **refuses to pass if it finds nothing**. Same family as the overlay bug of 19 Sep.
- Scoped to **active** tenants/links deliberately: wiped test tenant #14 (`product_link.active=0`, expired) has no agent, and asserting over every row would have cried wolf on day one.
- Live invariants confirmed healthy: 27 active bundle tenants, every one with an owner agent; 35 active links, none dangling; 0 orphan agents.

### ✅ PHASE 1 COMPLETE — THE ORACLE BOX IS A REAL SERVER (2026-09-20)
**https://new.nidaanpartner.com** serves the full stack over real TLS. Nothing points at production; Contabo untouched and live.
- **Built from source, never copied.** `git clone` over a **read-only deploy key** scoped to this box (not the broad PAT that sits in Contabo's git config). Result: **zero CRLF**, and `nidaan_ops.html` is **byte-identical to production** (`2bfe0807…`, 1,231,837 b). The Windows `git archive` copy was deleted first so nothing could mistake it for a deployment.
- **venv identical to production** — all **101 packages**, same versions, installed `--no-deps` because the live set does not re-resolve (moviepy pins `pillow<12`, production runs 12.2). A migration is the wrong moment to find out what changes when pip picks differently.
- **Live:** nginx + TLS (Let's Encrypt, auto-renew armed), `sarathi-worker` + blue-green `sarathi-web@1/@2`, fail2ban on SSH, 2 GB swap, unattended security upgrades. nginx config is **production's file with exactly two changes** (server_name, cert path) so the test exercises the real rate limits, static aliases, signed-doc guard and deny rules.
- **Verified from the public internet:** `/health` 200, `/` 200, `/static/nidaan_ops.html` **200 / 1,231,837 b**, HTTP→HTTPS 301, certificate valid. Resource use with everything running: **1.2 GB of 11 GB RAM, 6.4 GB of 45 GB disk, load 0.24**.
- **Neutralised `biz.env`** — all 74 production keys present so nothing is missing at startup, every credential a placeholder. No live secret exists on this box and none will until cutover. Ownership `sarathi:sarathi 600`, matching the production rule.
- ⚠️ **Finding: a missing `TELEGRAM_BOT_TOKEN` kills the WEB tier.** `main()` does `sys.exit(1)` on an empty token regardless of `APP_ROLE`, so both web instances crash-looped until a placeholder was set. **A typo when rotating the Telegram token would take the whole website down, not just the bot.** Not changed mid-migration; worth fixing separately.
- ⚠️ **Deliberate deviation: no UFW.** This Oracle image ships its own persisted iptables ruleset; layering UFW means two managers writing the same tables, which is how you lock yourself out of a box in Mumbai. Protection is equivalent — OCI security list (22/80/443) + host iptables + fail2ban.

### ✅ BOTH PRODUCTS SERVE CORRECTLY ON ORACLE, BY HOSTNAME (2026-09-20)
The pinned-Host landmine is **structurally gone** — replaced by the real cutover shape: one nginx server block per product, chosen by `server_name`.
- **https://new.nidaanpartner.com** → Nidaan (`/` 200 · `/nidaan/ops` **Nidaan Ops — Internal Portal** 1,231,837b · `/admins` same)
- **https://new.sarathi-ai.com** → Sarathi (`/` 200 · `/superadmin` **Cockpit — Sarathi-AI** 87,928b · `/partner` 92,917b)
- Both over valid TLS (`ssl_verify_result 0`), both certificates issued, `sites-enabled` holds exactly **one** file (a stray duplicate upstream takes nginx down).
- Earlier, app-level: **30 routes × 2 products = 60 checks, ZERO differences** vs production, and content fingerprinted — identical product, title and byte size on all ten key pages.
- **Memory measured, answering "do we need more for Sarathi":** web@1 205 MB, web@2 206 MB, worker 238 MB = **~650 MB** (production: ~750 MB). After the split, two apps ≈ **1.3 GB of 11.9 GB**. **No Oracle increase needed** — and since the free A1 pool is full, increasing would cost money for headroom the numbers say is unnecessary.
- Only test-only difference left: each block sends its product's real hostname as `Host` (the app selects product from Host, and the test names are not the production names). Becomes `$host` at cutover; documented in the config header.

### 🟢 CUTOVER COMPLETE — BOTH SITES LIVE ON ORACLE (2026-09-20, Sunday evening)
Window: **16:24–16:31 UTC — about 7 minutes**, of which the user-visible outage was the gap between freezing Contabo and the Cloudflare flip landing.
- **No data loss, measured not assumed:** snapshot md5 `da30f2ca…` identical either side of the wire; **158 tables, 79,613 rows** identical; `integrity_check ok`; **824 claim documents**, 914 MB uploads in place.
- **Both products verified through Cloudflare:** `nidaanpartner.com` (Nidaan) · `/nidaan/ops` **Nidaan Ops 1,232,775b** · `/admins` · `/nidaan/dashboard` — and `sarathi-ai.com` (Sarathi-AI) · `/superadmin` **Cockpit** · `/partner` · `/login`. Each serving **its own** product.
- **20/20 journeys pass on live production data.** App Health: 21 checks, 2 failing — both known GAPS, **"would page: nobody"**, exactly matching Contabo.
- **Integrations live with real credentials:** `@NidaanOpsBot` Telegram polling active · Email Radar polling 2 mailboxes · reminder scheduler started · WAL mode, DB and `uploads/nidaan-docs` writable.
- **Send-block lifted and PROVEN gone from the running processes** (not just the file) — the failure mode where the site looks healthy and silently delivers nothing.
- **Backup ownership transferred cleanly:** Contabo's timers disabled, Oracle's enabled, and **both proven by running them immediately** — encrypted DB pushed to git, and a **912 MB full backup (DB + 914 MB documents) to Oracle Object Storage**, keyless. Remote pruning ran.
- **Origin locked to Cloudflare:** direct access to `161.118.186.201` on 80/443 now **refused (000)**, both sites 200 through Cloudflare, SSH intact. This control existed on Contabo and would otherwise have been silently lost.
- **`max_fails=0` had to be re-applied** — installing Contabo's nginx config verbatim reintroduced the 502-on-deploy bug. Caught by my own check, not by luck.
- **Rollback stays available:** Contabo powered, services **stopped** (so it cannot take writes and diverge), data intact at 162 claims, 374 GB free. Rollback IP **`84.247.172.252`**, read off the DNS records themselves.
- ℹ️ `staging.*` deliberately still points at Contabo — it is a separate service there, and retires with the box.
- ℹ️ Pre-existing, NOT caused by the move: the legacy Sarathi bot token is rejected by Telegram (**96 times in 7 days on Contabo**). The app continues without it; scheduler, Nidaan bot and digests unaffected.

### ✅ DONE — claim documents now have a working, proven off-site backup (2026-09-20)
- **Chosen: Oracle Object Storage, same tenancy, Mumbai** — data residency kept, Always Free includes 20 GB, and with **instance-principal auth no access key or secret is ever created or stored anywhere**. The server proves its own identity.
- Ubuntu's packaged rclone (1.60.1+dfsg) **strips the Oracle backend**, so the official build is installed instead — v1.75.1, **checksum verified against the published SHA256SUMS**, and the installed binary confirmed to be the one from the verified archive. Backend is `oos` (not `oracleobjectstorage`; my first grep looked for the wrong name and wrongly reported it missing).
- **`backup.sh` fixed, two faults:** (1) only *local* copies were pruned, so the remote would grow past a 20 GB tier in ~3 weeks; (2) a failed offsite **logged a warning and exited 0**, which is exactly why Contabo's has been silently broken since at least 17 Sep. Now exits non-zero so App Health's *Scheduled jobs* check can see it — a warning in a log file is not something a dashboard can watch. "Not configured" still exits 0: a decision, not a fault.
- Verified on the new box: 870 MB archive, offsite correctly *skipped*, service result **success**.
- ⚠️ **Deploying this to Contabo will correctly turn its backup unit RED**, because its offsite genuinely is failing. That is the intent, and it goes green once the bucket exists. Holding that deploy until then so we do not create a red that is only waiting on us.
- 🔵 **Founder steps issued** (bucket + dynamic group + policy). On confirmation: configure rclone keyless, wire it in, run a real backup, and **restore from it** to prove it — same standard as the database backup.
- ✅ **LIVE AND PROVEN.** Bucket `sarathi-backups-mumbai` (namespace `bmfkx9t4tmgd`), dynamic group + policy scoped to that **one bucket**, rclone authenticating as the instance itself — **no access key or secret exists anywhere**. Verified list / write / read-back / delete with zero credentials.
- ✅ **First real backup: 912 MB encrypted object written in ~14 seconds**, then **restored from it**: `integrity_check ok`, **162 claims, 159 tables, 824 claim documents, 914 MB uploads**, and a real PDF opening with the correct magic bytes. Remote pruning ran. Timer armed for 02:01 daily.
- **This is the first time the claim documents have had an off-site copy at all.** Contabo's offsite has never worked — `rclone.conf` does not exist on that machine — so the 914 MB lived only on one disk. Nothing needs migrating; the cutover is what fixes it.
- `ListBuckets` is correctly **denied** — the policy grants two verbs on one bucket, not tenancy-wide listing. The denial is the control working.
- ⚠️ **My heredoc ate the line-continuation backslashes** when first patching `backup.sh`, silently joining lines. Still valid bash and `bash -n` passed, so nothing would have complained. Reverted and redone via a file-based patch that keeps backslashes out of literals; continuations verified present in the raw bytes afterwards.

### ✅ VIRUS SCANNING NOW COVERS EVERY PATH, ON BOTH BOXES (2026-09-20)
Founder: *"Virus scan at upload and at any other places we're using, must also be working."* Auditing "any other places" found two real holes.
- **All 11 HTTP upload paths** already used the single `validate_upload_scanned()` gate — confirmed, no upload path bypasses it.
- ❌ **But `biz_av_scan` was imported by exactly ONE module: `sarathi_biz`.** Two paths wrote files from strangers straight to disk, unscanned, and staff then open them on an authenticated machine:
  - **WhatsApp documents from complainants** (`biz_nidaan_doc_intake._store`)
  - **Email Radar attachments from customer mailboxes** (`biz_nidaan_radar`)
- **Both now scan AS RECEIVED**, before `normalize_to_pdf`, so the verdict is on the artefact the sender actually sent rather than our re-rendering of it. A zip is expanded first, so members are judged individually instead of as one opaque blob. Fail-closed, matching every other path.
- **Nothing is said back to the complainant** — a refusal is ours to explain, so it reaches staff via `rejected` + notes, never as an accusation. **One bad file does not sink the batch**: clean files in the same batch are still filed.
- **Proven with EICAR on the DEPLOYED code of both boxes: 9/9 each.** Infected file stores nothing and is reported; clean file gets through; mixed batch keeps the good one. App Health: *"clamd reachable — every upload is scanned"* green on both.
- ⚠️ **My first version of that test passed for the wrong reason** — it loaded the *deployed* module (no fix in it) and the "infected file stored nothing" PASS was actually a permissions failure on the write. Now it prints which copy is under test and, with `AV_REQUIRE_OVERLAY=1`, refuses to run against the wrong one. Kept as `deploy/verify-av-paths.py`.
- **Shipped to production too**, deliberately: the gap was real on Contabo as well, and doing the code change now keeps the cutover a pure infrastructure move with identical code both sides. Production deploy: **50/50 polls green**, both boxes on `ce810a2`, 20/20 journeys still passing.

### 🔴 FOUND ON CONTABO — CLAIM DOCUMENTS HAVE NO OFF-SITE BACKUP (2026-09-20)
**Pre-existing on production, not caused by the migration.** Found while proving backup parity.
- The nightly tarball (**873 MB**: database + `uploads` + `generated_pdfs` + videos) is encrypted with GPG and copied to `s3mumbai:sarathi-backups-mumbai` via rclone. **That copy has never worked** — `rclone.conf` **does not exist anywhere on the server**, so the `s3mumbai` remote is undefined. The log shows *"Offsite rclone FAILED"* on 17, 18, 19 and 20 Sep.
- The off-site backup that *does* work (`sarathi-db-backups`, proven restorable today) contains **only the database** — a 3.1 MB encrypted blob.
- **Net effect: the 914 MB of claim documents exist only on the server**, plus 9 local tarballs spanning 12–20 Sep on the *same disk*. Lose the machine and the documents go with it — while the database survives.
- **Why nothing caught it:** `backup-db.service` exits **0** even when the rclone step fails; it only logs a warning. So the new "Scheduled jobs" check would not catch it either — the unit did not fail. Another member of the silent-failure family: the dashboard is honest about what it measures, and it was measuring the wrong thing.
- 🔵 **FOUNDER ACTION:** this needs an S3/B2 bucket and `rclone config` — credentials I do not have. Worth doing before cutover if convenient, but **not a blocker**: the migration itself gives a second full copy of the documents on two machines for the 2–4 week overlap, which is more redundancy than exists today.

### ✅ CLAMAV — A BROKEN FLOW CAUGHT BEFORE CUTOVER (2026-09-20)
**Every document upload would have been refused on the new box.** Uploads are virus-scanned and the code **refuses when the scanner is down**; ClamAV simply was not installed. Neither the 20 journeys nor the 124 function checks touch the upload path, so nothing had caught it.
- Installed, definitions fetched (85 MB main + 23 MB daily), and configured to match production **exactly** — `StreamMaxLength 64M`, `MaxFileSize 64M`, `MaxScanSize 256M`, `MaxThreads 12`. Not cosmetic: uploads are capped at 25 MB and clamd refuses a stream longer than `StreamMaxLength`, so a stock 25M default would start rejecting documents at exactly the size the product allows.
- **Proven through the app's own scanner on both boxes:** clean PDF `(True, '')`, EICAR `(False, 'Eicar-Test-Signature')` — identical.
- Systematic follow-up: audited every external binary the code invokes. Only `node` (used by a dev-only JS syntax check) and `rclone` (above) differ; nothing else load-bearing is missing.

### ✅ OFF-SITE ENCRYPTED BACKUP PROVEN ON THE NEW BOX (2026-09-20)
The last pre-cutover blocker is closed. **A backup that cannot be restored is not a backup**, so the whole chain was proven, not just the push.
- Write deploy key added (founder's extension **correctly challenged my instruction** — I had said "the previous key was read-only", which was true of the *code* repo, not this one. The existing `sarathi-db-backup` key is **Contabo's**, verified by fingerprint, 3 successful pushes in 3 days. Left untouched; per-machine keys so each can be revoked independently).
- **Round-trip verified:** encrypt → commit → push → pull → decrypt → open as SQLite. **162 claims, 159 tables, `integrity_check` ok.**
- Rehearsed on a **throwaway branch** so `master` stayed Contabo-owned — both machines push the *same single blob*, so a push from here would have made the off-site tip an older snapshot. Branch deleted; `master` tip is still Contabo's `a40d410`.
- 🔒 **`git-db-backup.timer` deliberately DISABLED on the new box.** Both boxes fire at 02:30; armed together they race, or the snapshot overwrites the newer backup. **One machine owns the off-site backup at a time** — new runbook **Step 8b** transfers ownership (Contabo off, Oracle on, prove immediately). `backup-db.timer` (local tarballs) is safe on both and armed on each.
- ⚠️ **I did NOT copy the full real `biz.env`**, as originally planned — checking first showed `NIDAAN_NO_OUTBOUND` guards `send_message` but **not** Telegram's `getUpdates`, and the worker long-polls. The real bot token here would have made two workers fight over the same bot and **broken Telegram for staff on the live system**. Only `BACKUP_ENC_PASSPHRASE` was copied, **server-to-server, never through my machine, never printed**. The full env goes on at cutover per the runbook.

### ✅ NIDAANPARTNER VERIFIED ON ORACLE WITH REAL DATA (2026-09-20)
Founder: *"it should work as it was working in contabo."* Everything before this was tested against an **empty database** — page shells, not the product. Now tested with the real thing.
- **Real data loaded:** 162 claims, **914 MB** uploads (884 files), 898 pdfs, 689 apk — counts matching production exactly.
- **All 20 journeys pass on ARM against real live data.**
- **Byte-identical behaviour, proved properly.** Copied the *same DB file* to both machines (md5 `36ec0d7f…`) and ran NidaanPartner's real logic on each — so any difference would be the platform, not live activity. **28 metrics, zero differences:** every bucket board, awaiting-fee (19 waiting / 17 winnable / ₹22,97,315), document desk (115 waiting, 113 never asked), escalation clock, and 8 real claim checklists.
- **Every NidaanPartner surface identical** with real data: `/` 155,126b · `/nidaan/ops` 1,231,837b · `/admins` 1,231,837b · `/nidaan/dashboard` 209,034b · branch portal, ₹499 review, start, terms, privacy, about · `/superadmin` → 302 · all matching Contabo byte for byte.
- **Signed-URL document guard works identically** — a real claim PDF requested without a signature returns **403** on both boxes.
- 🔒 **The box holds real data, so every service now runs with `NIDAAN_NO_OUTBOUND=1`** (verified in the running process environment, not just the file). Without it, a rehearsal with the real `biz.env` would have **two servers messaging the same complainants**. **Removing it is now runbook Step 4**, with Step 5 proving it is gone from the processes — left in, the live site looks healthy and silently delivers nothing.
- All comparison copies of the live DB shredded from `/tmp` on both boxes and locally.

### ✅ PRE-CUTOVER WORK DONE (2026-09-20) — runbook: `deploy/CUTOVER_RUNBOOK.md`
- ✅ **Backups armed and proven.** `backup-db.timer` live (02:01 daily), run once for real — a 61 KB archive landed. **Rescued into git: `git-db-backup.service`/`.timer` existed only on Contabo**, so a rebuild-from-source produced a box with **no encrypted off-site DB backup and nothing to say so**. Second time this shape has bitten (the script itself was untracked until a `git clean` deleted it 22 Jul). Every other unit audited — these two were the only gaps.
- ✅ **Deploy mechanism installed and tested end to end** — narrow sudoers (5 exact commands, `visudo -c` validated), `sarathi-deploy.path` armed, SSH config so `git fetch` works non-interactively. A real deploy ran and rolled both web instances.
- ✅ **A 502 found and fixed.** The first rolling deploy produced one 502 in 60 polls. Cause: restarting web@1 earned two refused connections, nginx benched 8001 for `fail_timeout=5s`, and when web@2 restarted four seconds later 8001 was **healthy again but still benched** — "no live upstreams". Fixed with `max_fails=0` (loopback peers + health-gated deploy make passive detection worthless, while `proxy_next_upstream` retries instantly). **Re-measured: 180/180 polls green across BOTH products during a full deploy.** *Production still has this defect — the move itself fixes it.*
- ✅ **Origin-lock control captured** — `deploy/lock-origin-to-cloudflare.sh`. Contabo allows 80/443 **only from Cloudflare ranges**; the new box was open to the world. That control lived only in the old server's firewall, so migrating as-is would have been a **silent security downgrade**. Idempotent, with status/undo, adds ACCEPT rules before withdrawing the open one, and refuses to run on a truncated range list.
- ✅ **~1 GB pre-staged** — uploads **884**, generated_pdfs **898**, apk **689** files, counts matching production exactly. Staged in `/opt/sarathi/.stage` (`700`, owned by ubuntu, outside the nginx alias) so **nothing is web-reachable until cutover** — verified: `/.stage/` returns **403**. Shortens the window to a delta sync.
- ⚠️ **My mistake, owned:** a sloppy first rsync copied 133 MB of claim documents into world-readable `/tmp` on the new box. Caught on my own check minutes later, shredded, and a filesystem sweep confirmed none reached the nginx-served path (`/opt/sarathi/uploads` still had **0 files**). The staging design exists precisely so this could not happen; I bypassed it by writing the command carelessly.
- ✅ **Master doc A109** written; memory updated (incl. correcting a stale index line claiming we were already on Oracle ARM64).

### 🔴 BLOCKED ON OWNER — Task F
**Off-site encrypted DB backup cannot be armed** until the write deploy key is added to `kumar26dushyant-lab/sarathi-db-backups` (key issued 20 Sep, **"Allow write access" must be ticked**). Until then the new box has local backups only — which is not enough to call it production-ready.

### 📋 PENDING — the honest list (2026-09-20)
**Before cutover:**
1. **Data sync plan** — new box has none of it: DB 1.6 MB (fresh schema) vs **20 MB**, uploads **20 KB vs 914 MB**, pdfs 4 KB vs 9 MB, apk 2.9 MB vs 98 MB, docsplit 8 KB vs 5.6 MB.
2. **Backups not armed on the new box** — only `certbot` and the OS dpkg timer are running. `backup-db`, `git-backup` and the encrypted off-site `git-db-backup` all need installing + keys.
3. **Real `biz.env`** — currently 74 placeholder keys. Real secrets go on at cutover, never before.
4. **Deploy mechanism** — `sarathi-deploy.service`/`.path` not installed or tested on the new box.
5. **Cutover runbook** — not written: exact order, verification at each step, rollback at each step.
6. **Integrations to re-verify with real credentials** — Email Radar IMAP, WhatsApp Cloud webhook, Razorpay webhook, Telegram bot. Same domain, so DNS carries them, but each must be proven after the flip.

**At cutover (the window):** stop app → final DB + uploads sync → real biz.env → start → flip Cloudflare origin → verify both products → Contabo stays warm.

**After cutover:** soak 2–4 weeks → remove `new.*` DNS records and their certs → restore `proxy_set_header Host $host` and real `server_name`s → then decommission Contabo.

**The split (separate project, after the move settles):** cut plan for `sarathi_biz.py` (450 Nidaan / 394 Sarathi endpoints, 5 contiguous runs) → second repo + C-drive folder → two deploys → the 7 shared modules.

**Deliberately deferred (not during a migration):** IST consolidation + 9 naive `datetime.now()` call sites · `TELEGRAM_BOT_TOKEN` killing the web tier · Brevo exhausted · 5 branches with no contact · conversation-on-claim panel · immune-system phases · Pending-Draft approval gate.

### ⚠️ CAUGHT BY THE FOUNDER — new.nidaanpartner.com was serving the Sarathi site (2026-09-20)
**Not a migration fault — the monolith working exactly as designed, and a gap in MY verification.**
- The app picks its product from the **Host header**: `_is_nidaan_host()` matches exactly `nidaanpartner.com` and `www.nidaanpartner.com`; the `home()` docstring says *"Sarathi homepage everywhere else."* `new.nidaanpartner.com` is neither, so it served Sarathi and **every `/nidaan/` route returned 404**.
- **Why I missed it:** I verified `/health`, `/` and `/static/nidaan_ops.html`. Static is served **from disk by nginx**, bypassing the app entirely — so the one check that looked most convincing (byte-identical ops page) never touched the host gate at all. Checking status codes without checking *which product answered* is not verification.
- **Fix (test box only, no code change):** nginx now presents a fixed `Host: nidaanpartner.com` to the app. Better than adding the test hostname to `_is_nidaan_host` — no production change, and the app now sees exactly what it will see after cutover.
- 🚩 **LANDMINE, marked in the config itself:** that fixed Host **must be removed at cutover**. Both products will live on this box, and a pinned Host would make **sarathi-ai.com serve Nidaan**. A banner is at the top of `/etc/nginx/sites-available/nidaan-new` so it cannot be missed.
- **Re-verified properly:** every Nidaan surface now returns the same status as production — `/` 200, `/nidaan/api/plans` 200, `/nidaan/login` 302, `/nidaan/ops` 200, `/nidaan/dashboard` 200, `/static/nidaan_ops.html` 200, `/health` 200 — and the homepage `<title>` is identical to production's.
- **Standing lesson:** for the rest of this migration, "it returns 200" is not a check. The check is *"did the right product answer, and does it match production?"*

### 🕒 TIMEZONE — founder: "we need IST time to show" (2026-09-20)
**The box was set to UTC, then deliberately put BACK to Europe/Berlin to match Contabo.** Reason: real business logic gates on naive `datetime.now().hour` — marketing send windows, reminder sweeps, and the **bundle teardown nudge**, which fires at `now.hour == 9` and whose own comment claims "09:23 UTC ≈ 14:53 IST" while actually running at **07:23 UTC** on a Berlin box. Moving to UTC would have shifted all of them two hours at cutover: a behaviour change disguised as an infrastructure change.
**Audit of what staff and customers actually see:**
- **Ops screen is already correct** — `fmtDateTime`/`fmtDate` append `Z` (treating stored times as UTC) then render with `timeZone: 'Asia/Kolkata'`.
- **Branch portal** parses UTC correctly but renders in the *viewer's* timezone — right for Indian users, wrong for anyone abroad.
- **Server-side** human-facing formatting is IST-aware where it matters (claimant PDF stamps "IST", WA schedule, daily summary) — but IST is defined **four different ways** across files (`timezone(timedelta(5,30))`, `ZoneInfo("Asia/Kolkata")`, inline offsets).
**Recommendation, as a separate piece of work AFTER cutover:** (1) keep storing UTC — already true; (2) display IST through **one** helper per side (one server `IST`/`to_ist()`, one browser `parseServerTime`/`fmtIST`), replacing the scattered definitions; (3) replace every naive `datetime.now()` that gates a decision with explicit `datetime.now(IST)` or `utcnow()` — about **9 call sites**. Only then set the server to UTC, where it belongs. Doing this *during* the move would make it impossible to tell which change caused a shift.

### ✅ PHASE 0 COMPLETE — ARM64 PROVEN ON ORACLE MUMBAI (2026-09-20)
Box: **`nidaanpartner-mumbai-01` · 161.118.186.201 · ap-mumbai-1 · VM.Standard.A1.Flex aarch64 · 2 OCPU / 12 GB / 45 GB · Ubuntu 24.04**, dedicated `nidaanpartner-vcn`, isolated from goluq/sarathi. Key at `~/.ssh/id_nidaan_oracle`.
- ✅ **R2 CLEARED — outbound SMTP works.** 587 and 465 **OPEN** (25 blocked, we do not use it). This was the potential showstopper: Oracle restricts mail egress and login codes depend on it. Also reachable: Razorpay, graph.facebook.com (WhatsApp Cloud), Telegram, Gemini, imap.gmail.com (Email Radar), GitHub.
- ✅ **R1 CLEARED — the whole stack runs on ARM.** All **101 packages** installed at the exact live versions; only `http_ece` needed compiling and it built. `sarathi_biz` imports with **856 routes**. **All 15 journeys pass** against a copy of the live DB. Real HTTP served: health 200, nidaanpartner.com 200, sarathi-ai.com 200, ops page 200.
- ⚠️ **The live venv cannot be rebuilt with pip's resolver on.** `moviepy 2.2.1` requires `pillow<12` but live runs `pillow 12.2.0` — a pre-existing inconsistency that only survives because nothing re-resolves it. Installed with `--no-deps` to reproduce live exactly. **`moviepy`/`imageio` belong to `biz_video.py` = Sarathi marketing studio, so the Nidaan repo drops them and the conflict disappears with the split.**
- ⚠️ **Never ship code from the Windows laptop.** `git archive` on Windows rewrote **every line to CRLF** (29,046 lines in `sarathi_biz.py`). It ran fine, but that is exactly the silent difference that must not reach production. **Phase 1 rule: the target box `git clone`s from GitHub. Files are never pushed from the laptop.**
- 🔴 **THE A1 FREE POOL IS NOW FULL.** goluq-mumbai (2/12) + nidaanpartner-mumbai-01 (2/12) = the entire Always-Free A1 allocation (4 OCPU / 24 GB). **There is no free A1 capacity left for Sarathi-AI.com.** The existing `sarathi-ai` instance is an E2.1.Micro (1/8 OCPU, 1 GB) — far too small. Founder decision needed; see below.
- **Resolves the apparent tension:** separate *repos, builds and deploys* do **not** require separate *machines*. Two systemd services on one box give independent deploy, restart and blast radius — which is what was actually asked for. A second machine can come later and changes nothing about the split.

### 🟢 DISCUSSION OPEN — Contabo → Oracle, and splitting the two apps (2026-09-20)
Document: **https://claude.ai/code/artifact/94bc5aeb-64e3-4b98-a9de-2cf9aebc1280**
- **Measured, not remembered:** Contabo `84.247.172.252` is **x86_64** (project notes said Oracle ARM64 — stale, corrected; old box `140.238.246.0` does not answer). 8 vCPU / 23 GB / 387 GB, **96% idle**. DB **20 MB**; real payload to move **1.1 GB**.
- **The move is x86 → ARM**, not a lift-and-shift. Phase 0 = a throwaway Oracle box that proves the stack builds on aarch64 and that **outbound SMTP (587) is not blocked** — Oracle blocks mail egress, and login codes are our most fragile path.
- **Recommended order:** Phase 0 prove → Phase 1 rebuild (never clone; copy data, not the machine) → Phase 2 short night cutover via Cloudflare origin flip → Phase 3 watch 2–4 weeks → then cancel Contabo. **Then STOP** — the split is a separate project.
- **The split is in better shape than expected:** 91 `nidaan_*` vs 67 Sarathi tables, 40 vs 33 modules, and **zero** Nidaan→Sarathi table violations (the Aug 17 rule held). The one knot is `sarathi_biz.py` — 29k lines, 844 endpoints (450 `/nidaan/*`). So it is a routing problem, not a data-untangling problem.
- **Bundle SSO:** step 1 (two processes, one DB, nginx routes by host) changes **nothing** for bundle subscribers. Only splitting the database breaks it — which is why that step goes last, or never.
- **Open questions for the founder:** what drives the move (cost vs performance); will the tenancy go **Pay As You Go** (recommended precondition — stops idle reclamation); does the Oracle account still exist and in which region; when can we take a night window; and does he want the full split once he sees step 1.

### 🔴 AWAITING OWNER — 2026-09-19
- 🔴 **The Telegram alert bot** — the alarm narrowing above is explicitly temporary and is the thing it is waiting for. When it exists, re-point `alarm_audience_staff_ids` (or lift the gate) rather than reverting the re-verification, which is worth keeping regardless of who listens.
- 🟡 **Still broadcast to all admins, and arguably noise** — not alarms, so deliberately left alone, but worth a decision: `claim.filed.admin` (**182** in 48h), `claim.l2_moved` (154), `account.signup` (98), `claim.l2_queued` (70), `bucket.move` (64), `payment.success` (56). These are the business happening rather than fault reports; say the word and any of them can join the narrowing.
- 🔴 **Brevo free plan exhausted** — not load-bearing (Workspace/Gmail carry the mail), but the allowance now warns below 50 instead of at zero.
- 🔴 **5 branches have neither an email nor a mobile** (IND-HO, PUN-01, MUM-01, CHD-01, HYD-01) and cannot log in at all; only 3 of 15 have mobiles. This is a **gap**, so it no longer pages — it stays red in App Health.

### 🟢 PARKED — resume when the founder is ready
- 🟢 **Conversation-on-claim panel** — each claim owning its WhatsApp conversation, and what to do about intermediaries (branch/CP) who span many claims and receive FYI copies. FYI policy agreed = first ask + when we escalate to asking them directly. We do **not** capture WhatsApp `context` (quoted reply) today; that is part of this work. Parked until the document flow has been tested.
- 🟢 **Immune system, phases 1–5** — design agreed in discussion only, nothing live. Principle: we auto-fix only what is provably safe and reversible; everything else is surfaced to super-admins on Telegram with what broke and why. Prototype in `prototype/immune/` (uncommitted).
- 🟢 **Approval gate on Pending Draft** — `approved_by` was removed as a `required_exit`; whether a *gate* should be restored is undecided.
- 🟢 **Deploy vs `git-backup.sh`** contend for `/opt/sarathi/.git/index.lock`. Waited rather than forced (forcing would corrupt the backup); needs a real fix.

### ✅ SHIPPED 2026-09-10 — attachments, duty roster, Email Radar
- ✅ **Attachment limits raised everywhere at once** — 5 files/10 MB → **20 files/25 MB**, per-claim cap 40 → 60. Applied to all **five** upload endpoints via one `_guard_upload_batch()` (branch, claim portal, review purchase, claim docs, My Business) plus every piece of user-facing copy on 6 surfaces — the endpoint-uniformity rule. **Why 25 MB and not 100:** every stored file is virus-scanned in memory before it is written, and clamd refuses a stream past `StreamMaxLength`. 100 MB would have meant refusing files in the gap or storing them unscanned. Instead **clamd was raised to 64M** (`/root/clamd.conf.bak.*` kept) and proved: a 25 MB stream scans clean in 4.4s and **EICAR is still detected**. Browser now **splits a large set into batches** under the nginx 50M body cap, so a big upload succeeds instead of hitting an opaque 413; a partial upload reports what actually landed.
- ✅ **"Set duty" landed on a screen that could not do the job** (founder-reported). The roster UI hard-coded `{support, whatsapp}`, so all 11 case-stage buckets were un-rosterable even though `DUTIES` and the API already knew them. Labels now come from the server (`duty_labels` on `/support/reps`), the picker is grouped Conversations / Case stages, and clicking **Set duty** on a bucket **pre-selects that bucket**.
- ✅ **Email Radar readability + trust.** HTML bodies were run through a strip-every-tag regex, which **destroyed every `href`** — a confirmation mail whose content is a "Confirm" button arrived as the word "Confirm" and nothing else (it also leaked CSS and `<script>` text into the body). New `_html_to_text()` keeps links as `text (url)`, drops script/style, and single-part `text/html` mail is converted at all (it used to render as raw markup). Bodies are **escaped first and linkified second** — only `http(s)` ever becomes clickable — and a **🔗 Links** block lists every destination with its domain, so a staffer sees where a link goes before clicking. Every row now carries a plain-language **why** line.
- ✅ **✅ Confirmations bucket** — receipts/acknowledgements are proof something was filed; they were being auto-cleared into a pile nobody opens.
- ✅ **Founder-written surfacing rules** (`custom_rules`) — one rule per line, `from:` / `subject:` / `text:` or bare words. A match forces 🔴 Act now **over** the AI, and the row names the rule that caught it. Rules are **literal substrings, never regexes**, so a typed `(` or `.*` cannot break the poll for every mailbox; sub-3-character rules are dropped and the save reports how many are actually in force. Settings tab now explains, in order, exactly how the radar decides.
- ✅ Migration verified against a **copy of the live DB** (ALTER path, not the fresh-schema path): both columns added, all 18 existing radar items preserved, other settings untouched.

### ✅ SHIPPED 2026-09-11 — the post-L2 pipeline
- ✅ **L2 is now a gate, not a guess.** Up to L2 the stage is DERIVED (a review outcome and a payment are facts we hold); after it nothing in the data can say "the consolidation is finished", so a case enters the pipeline by an explicit act and moves bucket by bucket. New `pipeline_stage` (empty = not in the pipeline) is what keeps Drafting/Documents holding **L2-qualified work only**. Entry requires `review_outcome='can_fight'` **AND** `l2_payment_status='paid'` — live that is **21 of 87** open cases; the 45 sitting at can_fight with no payment are deliberately kept out.
- ✅ **Movement**: `enter_pipeline()` + `move_stage()` across Consolidation → Documents → Drafting → With the insurer → Escalation → Ombudsman → Outcome → Settlement. **Backwards is allowed and needs a reason** — work does come back, and a forward-only pipeline gets worked around within a week. Ageing is **per-bucket** (`pipeline_stage_at`), because three weeks in Drafting is a different problem from three weeks in the pipeline. The blocker override stays independent: a case can be parked or waiting on the insurer in any bucket (asserted in tests).
- ✅ **Auto-advance, honestly scoped.** Exactly one transition is provable from a column — Documents → Drafting when the checklist is complete. That one is offered one-click (per case, or all at once); everything else stays manual because moving a case on a guess is worse than leaving it visible.
- ✅ **Who sees what.** Admins see every bucket and the whole floor; everyone else sees the buckets they are **rostered on** plus cases assigned to them by name. Today's priority list is scoped the same way — being shown work you cannot touch is how a priority list stops being read.
- ✅ **Leave-aware coverage.** Three distinct problems, ranked by work actually waiting: **nobody** rostered, **on leave** (everyone rostered is on approved leave TODAY — the one that goes unnoticed because the rota still shows a name), and **soon** (all rostered go on leave within a fortnight). Built on the existing `nidaan_leave_requests` + `cover_staff_id`, no second leave system.
- ✅ **Raise a claim for a subscriber** who will not use the dashboard. Restricted to accounts with a **live** subscription (an expired one could not be honoured), banner stays on screen for the whole form, and `raised_by_staff_id` / `raised_by_name` / `raised_via` are written onto the claim permanently — the first line of case history now names the staff member instead of saying "submitted by advisor". **Verified it spends the subscriber's own quota** (second attempt returned `quota_exceeded_silver`) — on-behalf is not a free extra.
- ✅ **Regression proof**: the live code was run against a pristine copy, then the new code against the migrated copy — all **87** open cases sit at the identical stage AND blocker. Adding the pipeline moved nothing.
- 🟢 **NEXT (blocked on the founder):** Lokpal bucket behaviour + what happens after Lokpal — "after lokpal we'll update you how to create buckets and staff assignment".

### ✅ SHIPPED 2026-09-12 — wording, and the buckets telling the truth
- ✅ **"claimant" → "complainant" — 148 lines, 16 files.** Every occurrence a PERSON reads: labels, headings, email bodies, WhatsApp text, hints, comments, docstrings. **Deliberately NOT renamed** (invisible to users, breakable): the live `nidaan_claimant_portal` table (**22 real consent records**), `biz_nidaan_claimant.py` + its `as claimant` alias, `claimant_portal`/`claimantPortal`//claimant/ identifiers and paths, and the literal `"claimant"` **written into `nidaan_claim_activity.actor`** — changing that would split case history into two spellings of one thing. **No DB column contains "claimant", so there was zero data risk.** A dry run first caught three real defects before anything was written (the module alias being renamed, `CLAIMANT` becoming `Complainant`, and the architecture doc's own row about the rename turning into nonsense). Verified: 148 insertions / 148 deletions exactly, everything compiles, both HTML pages pass `node --check`, portal rows intact.
- ✅ **"Insurer" → "Insurance Company"** on every form a complainant fills — dashboard claim form, free intake, branch raise, My Business, raise-for-a-subscriber. Hindi बीमाकर्ता (formal register) → बीमा कंपनी (what people actually say). Internal ops tables keep "Insurer".
- ✅ **The journey map on My Desk** (founder question: "the rota offers 13 duties but My Desk shows 5"). Cause: a bucket with no cases AND nobody rostered was hidden as noise — correct for a working screen, but it also hid the SHAPE of the process. All 11 stages are now drawn in order, always, with counts, who is on duty, and the L2 gate marked; the empty ones are visibly empty. Detailed cards stay filtered to what needs a person today.
- ✅ **Post-L2 buckets now hold ONLY started work.** `derive()` was putting `can_fight`+paid cases straight into Documents/Drafting, so those buckets mixed work being *done* with work merely *qualified for* — which contradicted the founder's rule that post-L2 buckets contain only L2-qualified, started cases. Everything pre-start now waits in **Conversion** with flag `awaiting_l2_start`. **This deliberately moved 21 cases (Documents → Conversion; Conversion 46→67)** — the first intentional state change of this work, and the buckets are now provably empty until someone presses Start.
- ✅ **Quota confirmed (founder ruling):** an on-behalf claim spends the subscriber's **own** quota — never a bypass. Re-verified live (`quota_exceeded_silver` on the second attempt).
- ✅ **PROJECT_MASTER_CONTEXT.md was stale** — its header said Aug 19 and its footer said May 25 while A92 (Sep 4) was already in the file. Added **A93** covering Sep 10–12 and corrected both dates.

### ✅ SHIPPED 2026-09-18 — the staff complaint was real: a provider that lies about success
- ✅ **Checked before changing anything, as asked.** The complaint ("OTP problem in Authorization on WhatsApp and Email") is **NOT** a staff misunderstanding. Hard evidence: **49 authorization codes sent, 7 portals opened** (`nidaan_claim_activity`), claim 105 alone asked **9 times** and never got in.
- ✅ **Root cause — Brevo ran out of sends and does not say so.** Free plan `credits: 0`; a live send today returned `201 {"messageId": ...}` and delivered nothing. Same message to a gmail account we own: **Brevo → NOWHERE, Workspace → INBOX.** Every log line read "Brevo ✓".
- ✅ **Already half-fixed by accident**: yesterday's Workspace sender switch moved all Nidaan mail off Brevo, so authorization codes have been arriving since ~17:25 on 17 Sep. Verified INBOX.
- ✅ **`brevo_credits()` gate** (cached 15 min) — at zero, Brevo is skipped for a transport that really sends; an unknown balance never blocks sending. App Health reports the allowance and warns **below 50, not at zero**; the watchdog treats it as critical. This is the only failure class that cannot be detected after the fact — only in advance.
- ✅ **Authorization flow gaps closed**: WhatsApp codes use the approved template (**no 24-hour window** — telling a locked-out person to "message us first" was never an answer; STOP still honoured and that check **fails open**); the authorization email was the **only** code path missing `delivery_critical`; portal codes now feed the login-health recorder so App Health can see the channel at all.
- ✅ **43 tests** (13 Brevo-gate + 30 login-health) + 9 watchdog. Both sites health-checked.
- 🔴 **Owner action:** Brevo free plan is exhausted — top it up or leave it dead. It is no longer load-bearing (Workspace/Gmail SMTP carries Nidaan mail), so this is not urgent, but **2 subscriber login codes went via Brevo before the fix and almost certainly never arrived**.
- 🟡 **Intake data quality, evidenced:** Brevo's suppression list holds `ashishja502@gamil.com` (typo), `9669711797@gmail.com` (a phone number in the email field), `hdfhdgbhfdgb@gmail.com` (mash) — plus **9 `@nidaanpartner.com` staff login-IDs that hard-bounced** because they are usernames, not mailboxes. Part 1 failures that surface much later as an un-authorisable complainant.

### 🟢 OPEN DISCUSSION — an immune system instead of a bug-fix loop (founder, 18 Sep)
His ask: *"a system that alert us before breaking anything and proactively fix itself if see something is breaking (whatever in its scope), whatever cannot be fixed by our mechanics and dependency is on a human must be surfaced to superadmins on telegram."*
Agreed principle: **auto-fix only what is provably safe and reversible; surface everything else with what broke and why.** A wrong automatic repair is worse than a clear alarm.
Proposed phases (awaiting his go-ahead):
1. **Judge outcomes, not configuration** — extend the login-health pattern (record what actually happened, check the record) to payments, document uploads, WhatsApp sends and claim creation. Configuration checks cannot see a silent success.
2. **Leading indicators** — quota/credit/expiry style checks that fire BEFORE zero: Brevo allowance (done), WhatsApp template + token validity, disk, certificate expiry, Razorpay key age.
3. **Deploy gate** — run the test suites automatically on deploy and refuse/alert on failure. Directly targets "we fix one thing and another breaks".
4. **A narrow self-heal allow-list** — only idempotent, reversible actions already proven safe (re-run seeds, clear cache, re-poll radar, WA re-pair, skip an exhausted transport). Every action audited and announced, never silent.
5. **One Telegram voice to super-admins** — edge-triggered (already built), saying what broke, why, what was auto-fixed, and what needs a human.

### ✅ SHIPPED 2026-09-17 (3) — branch login, and App Health learning to see the ways in
- ✅ **Root cause, proved not guessed.** Three identical mails to a mailbox we can read over IMAP, same minute: Brevo with our own domain in the From → **NOWHERE**; Brevo from a gmail From → **Spam**; Gmail SMTP direct → **Inbox**. Google Workspace silently discards mail arriving from outside that claims to be from our own domain. Every branch login address is `@nidaanpartner.com`, so every branch code vanished while the API reported success. Fix: **anything addressed to our own domain goes via Gmail SMTP** (`biz_email.py`), customer mail untouched.
- ✅ **And it reaches the INBOX now, not spam** — verified end-to-end after the header fixes (Message-ID domain matching the sender; no Reply-To across domains, no List-Unsubscribe, no marketing X-Mailer on a one-to-one login mail). The earlier "delivered but in Spam" result is closed.
- ✅ **WhatsApp as the second way in** (founder: "one of them will be working"). Two buttons on the branch login page; the code still lives against the branch email so verification is unchanged. Two limits stated rather than hidden: no mobile on file, and the 24-hour WhatsApp window (no authentication template approved at Meta yet) — when shut, the page offers one tap to open it. **Shipped after the backend**, because the request body forbids unknown fields.
- ✅ **App Health can see the ways in** (`biz_nidaan_login_health.py` + `_login_checks()`). Every login code now records what actually happened to it — which transport carried it, or why it failed — in a rolling window (no new table, code never stored, addresses masked). Six checks: branch (a way in / delivery), subscriber (a way in / delivery), staff, complainant portal. **Delivery is judged on the codes we really sent in the last 24h**, because on 17 Sep every key was configured and nothing worked.
- ✅ **It is an alarm, not a dashboard.** The checks live in `_subsystem_checks()`, which the **watchdog** also runs, so a login outage now wakes a super-admin. The WhatsApp-fallback gap is reported but deliberately NOT alarm-worthy.
- ✅ **Fixable from App Health**: a failing row links to the screen holding the missing data, and **✉️ Test login delivery** sends a real message down the exact branch-code path to the super-admin's own address and names the transport — inbox vs spam is a difference no config check can see.
- ✅ **37 tests** (28 login-health + 9 watchdog integration) against a copy of the live DB with `NIDAAN_NO_OUTBOUND=1`, including the 17 Sep case itself ("ALL 2 codes in the last 24h failed"), partial failure, bounded ring, and "no six-digit code is ever stored".
- ✅ **The sender name** (founder: *"ideally it should trigger from info@nidaanpartner.com"*). He is right — the Gmail From was my doing, the price of getting delivery working. Both routes to put our own name back were measured: authenticating **as info@ through Workspace → still 535**, and gmail-auth-with-info@-in-the-From → **Gmail rewrote it straight back** (so info@ is not a verified alias there either). Mail to our own domain now **prefers Workspace as info@** and keeps Gmail only as fallback; proved a bad password with the switch on **still delivers**, because a sender fix that locks branches out would be worse than the problem. App Health refuses to call it healthy just because the switch is on — if the last code went out on the fallback it says Workspace is refusing the password.
- 🔴 **For the founder — ONE action unblocks the sender name:** generate a Google **app password** for `info@nidaanpartner.com` (2-Step Verification must be on for that mailbox), put it in `biz.env` as `NIDAAN_SMTP_PASSWORD`, add `NIDAAN_SMTP_ENABLED=1`, restart, then press **🪪 Test the sender** in App Health. Until then codes keep arriving — just under the Gmail name.
- 🔴 **For the founder — five branches cannot log in at all** (IND-HO, PUN-01, MUM-01, CHD-01, HYD-01): no email AND no mobile. Only **3 of 15** branches have a mobile at all (JIRAPUR-01, PUNJAB-01, RATLAM-01), so WhatsApp cannot become the primary way in yet.
- ✅ **The WhatsApp code now reaches a branch COLD** (founder: *"Submit meta authentication template"*). `np_login_code` submitted in **en + hi** — both **APPROVED instantly**, because Meta owns and localises the wording of authentication templates; we choose only the security line, the 10-minute expiry and the copy-code button. `COPY_CODE`, not one-tap: autofill needs a signed Android app we do not have. `message_send_ttl_seconds=600` so an undeliverable code is dropped rather than arriving dead. **Verified against a number whose 24-hour window was SHUT — it delivered.** The window gate and the "message us first" help text are gone; free-form is kept only as a last resort. The one remaining refusal is a branch with no mobile on file.
- 🟢 **Deferred by the founder:** *"We'll ask later all valid branches to have mobile no."* — until then email stays the primary way in and WhatsApp covers the 3 branches that have a number.

### ✅ SHIPPED 2026-09-17 (2) — his four answers: analytics, views, and the schedule module
- ✅ **Rejection letter, his call — ask-and-allow-with-a-reason.** The on-behalf form asks for it and lets the claim through if you say why (the reason lands on the claim). A failed attach is reported, not swallowed.
- ✅ **The line's numbers** (`biz_nidaan_stats.py`, `GET /ops/api/stats/line`) on both work screens. Every number answers "is this moving?"; anything not honestly derivable is left out. Live on the day: **82 waiting, oldest 70 days, 5 of 82 with all documents**, avg 7.5 days to hand over; 4 in the line, 4 moved this week, 0 stuck.
- ✅ **Cards / Table / Kanban** on Consolidation — same filtered list, same filters, nothing refetched on switch; Kanban columns in the line's order. Choice remembered.
- ✅ **Scheduled document reminders** (`biz_nidaan_wa_schedule.py`) — staff pick the moment (once / weekly / every N days, IST), it stops when the documents are in, after N asks, or when the claim closes; re-reads the checklist at send time; obeys the 2-a-day cap and the STOP list like any other message. Worker every 5 minutes. **26 tests.**
- 🟢 **Phase 4 next:** case email + password — captured from WhatsApp, recorded on document collection, auto-filled into the draft. His answer on access: **super admins and sub-super-admins**. Encrypted at rest, every reveal logged (my recommendation, unless he says otherwise).
- 🟢 **Later, his words:** capture profession + free time at intake so reminder timing can be suggested rather than guessed. Manual version first, deliberately.
- 🟢 **Phase 6:** the notification control centre (A97).
- 🔴 **Still open for him:** the **16 open claims with no documents at all** (several at "review delivered") — chase or close, a decision not a code change.

### ✅ SHIPPED 2026-09-17 — attachments everywhere, the empty claim, the homepage ribbon
- ✅ **Remove on all EIGHT upload surfaces** (documents window, claim panel, note attachments, task attachments, raise-claim staging, complainant portal, ₹499 intake, subscriber dashboard). It was missing from the Documents window — the one the founder hit on NP-167.
- ✅ **Deleting a document now reopens the checklist line it ticked.** Four delete paths fixed; a wrong file removed used to leave a green tick, so the right document was never asked for again.
- ✅ **NP-167 root cause:** the branch form creates the claim, THEN uploads the rejection letter inside `catch(_){}` — the upload failed and the branch still read "Claim submitted ✓". Now the failure is said out loud; the ₹499 intake (same swallow) names anything that did not upload; and `sweep_empty_claims()` flags a claim still empty after 20 minutes, once, to super admins.
- 🔴 **Backlog to work deliberately:** **16 open claims older than 48h have NO documents at all** (the sweep deliberately leaves them alone — flagging them would be an alert storm, not information). List available on request.
- ✅ **Consolidation** column + **Move to Consolidation** button; **Notes + Involved merged** into one box under Assign to staff; the 20-name tag chip wall is a **dropdown**; attachment copy trimmed to two facts; three stale "10 MB" messages corrected to 25 MB.
- ✅ **Verified, not changed:** "Raise for a Subscriber" is already available to every staff member (tested with a live team-member token).
- ✅ **Homepage ribbon aligned at every width** — labels no longer break mid-phrase, spacing and logo tighten at ≤1280, burger menu covers everything up to 1240px. New `uitest/home.mjs` measures 8 device widths.
- 🟢 **Phase 3 (next, needs his answer):** scheduled WhatsApp document collection — staff choose when the complainant is actually free (his Sunday-morning example), one-off or repeating.
- 🟢 **Phase 4:** case email + password captured from WhatsApp → recorded in document collection → auto-fills the draft (ClaimShield already works this way; our gist form already has both fields).
- 🟢 **Phase 5:** analytics strip on L2 Claims + Consolidation — **sample shown, nothing built until he approves**.
- 🟢 **Phase 6:** the notification control centre (A97) — he confirmed it is still wanted.
- 🔴 **His open question to answer:** should the rejection letter BLOCK a staff-raised/on-behalf claim (as it blocks the branch form), or ask-and-allow-with-a-reason?

### ✅ SHIPPED 2026-09-16 (3) — the founder's 14-item claim-panel round (items 1–6, 8–14)
- ✅ **Wording that means something.** "Insured" follows the claim type — a health claim says **Patient**, motor/life/fire say **Insured**, mixed lists say "Insured / Patient". The public ₹499 intake form says it in both words, both languages.
- ✅ **The complainant is on the panel.** `complainant_name`/`complainant_phone` existed and were never shown; the row says "same as the patient" when they match and gives a tap-to-call number when they differ.
- ✅ **Insurance company is a dropdown** on the claim's own Edit form (the shared `NidaanInsurers` list of 40 + "Other" that the branch/dashboard/intake forms already used). A company not in the list stays selectable; an empty picker on a claim that HAS a company sends nothing rather than blanking it.
- ✅ **Advisor name + firm read-only** (they decide referral credit); email/phone still editable. The endpoint still accepts a name change for the Accounts screen, which has a legitimate reason.
- ✅ **Assign is a dropdown of six** — Dr.Ashish, Ashwin, Harish Bhatia, Ambikesh, Chayan, Yamini — served from the setting `claim_handler_ids` so a super admin can change it **without a deploy**; empty/garbled falls back to the six, and if none are active it offers everyone. **17 live claims sit with 7 people outside that list**: they stay as removable chips, because a screen that forgot them would read "unassigned".
- ✅ **Involved is a dropdown** (new `POST /claims/{id}/watchers`), not only an @mention buried in a note. They are told once and follow the claim until they mute.
- ✅ **ONE documents box**, not three (a button box, a second list, and a collection block hidden inside the Portal). Assessment sheet button removed from here — the gist that produces it is prepared in Consolidation, where the button still is.
- ✅ **Every checklist line is tickable by hand.** A line could only go green if the document's name was chosen from a dropdown during upload — hence "9 files attached, 3 of 5 ticked". Manual **by the founder's choice** ("no automation, simple manual work"): guessing from a file name would mean silently not asking for a paper we never got. Un-ticking breaks the link to the file that answered it.
- ✅ **The health list is his eight**, in his order, with the four existing keys unchanged — **not one of the 33 live ticks lost**. `other_docs` is optional (a catch-all can never be "complete"); Past Medical Records stays as an optional line (PED allegation is the commonest rejection ground).
- ✅ **The case email ID explains itself** — create a NEW account, what we use it for, and that they can change the password or delete it when the case ends — in Hindi, Hinglish or English, from the language their WhatsApp contact already remembers.
- ✅ **Removing a checklist line no longer demands a sentence**; nothing notifies anyone on removal or delete (nothing ever did). A plain confirm stays, and who removed it, when, is still recorded, restorable.
- ✅ **Review delivered is readable on the claim** — 100 claims carried the text sent to the customer with nowhere on this panel to read it.
- ✅ **Follow-ups and Tasks & reminders off the panel** (3 follow-ups ever, last 1 Sep; 2 claims ever had a task, last 25 Jul). The Tasks module — 657 tasks, used daily — is untouched.
- ✅ **The handover's confirm tick-boxes are gone, the note stays.** "All documents received" is ticked a step earlier and is the real gate. A caller that still sends the ticks is still told what was not confirmed.
- ✅ **A handed-over claim leaves L2 Claims** (it was in both lists); the metrics and CSV follow the same rule, and a **send-back brings it straight back**.
- ✅ **All Claims: "Where it is & last activity"** — the Consolidation bucket plus the newest thing that actually happened. Two indexed sub-selects; 300 claims still load in **0.11s**.
- ✅ **"Level-2 → Settlement" is "Consolidation"** everywhere: 4 screen labels, 8 capability entries, 36 lines of the staff manual. No bucket carries that name, so nothing collides.
- ✅ **His item 7, done last on purpose — the portal link is no longer a key.** It used to BE the credential: whoever held the URL could open the claim and accept the success-fee terms. Now the link only reaches “is this you?”; a 6-digit code goes to the number or email **already on the claim** (their choice of channel, shown masked), and only the session that code buys opens the page, uploads a document or accepts the terms. Codes are stored as peppered HMACs, die after 5 wrong tries or 10 minutes, and are capped at 5 an hour per claim. **Staff never need the complainant's code:** ops mints its own 20-minute read-only preview session, which the consent endpoint refuses — this replaces the old `?staff=1` flag anyone could type. First-open now means the complainant actually proved who they are. Checked first: all 36 live portals have a phone, 28 also an email, **none have neither**. 36 tests.

### ✅ SHIPPED 2026-09-16 (2) — how often we are allowed to speak first
- ✅ **One gate, at the one place every Nidaan WhatsApp message passes through** (`biz_nidaan_wa_guard` consulted inside `_post`) — a cap anywhere else is a cap with a way around it.
- ✅ **The founder's numbers:** we start at most **2 messages a day, 5 a week** with one complainant. Capped: journey messages, reminders to someone not in session, campaign sends. **Not capped, deliberately:** a staff member's typed reply (silence is worse than a message); the bot answering inside the 24h window the complainant OPENED (document collection is a back-and-forth THEY started) — with a **12/day burst guard** against a runaway loop; **money and access** (failed payment, an authorisation they just gave) sent as `critical`; staff and branch partners, who are colleagues, not an audience.
- ✅ **The way out, and the way back.** STOP now answers with what it costs — *"no claim updates here; we would still call or email you"* — and how to return; it is sent as `consent` so it reaches someone who has just opted out. START turns it back on and says so. The **STOP line rides along every 3rd message we start, and the first**, so nobody learns of it only after the fourth. Templates carry their own approved wording, so the line goes on free-form text.
- ✅ **A held message is not lost** — it is written on the claim's timeline with the reason, and deliberately NOT into the WhatsApp thread (that thread is what was actually exchanged). Campaigns count held as **skipped, not failed**.
- ✅ **Two silent doors fixed:** the **D2C ₹499 review funnel** and **raise-on-behalf** created claims and told the complainant nothing. Both now send claim-registered — every channel behaves the same.
- ✅ **Ops sees it before typing:** the query screen shows **"STOPPED — no WhatsApp"** (and unticks WhatsApp), or how many messages are left today and this week.
- ✅ **Fail-open by design:** if the guard cannot read the database it lets the message through. A guard that silences the platform on a query error is a worse outage than one extra message.
- ✅ **Proof:** 30 cap tests with **fake Meta credentials AND a stubbed HTTP client** (either alone failing would mean messaging live complainants from a test), the six other suites re-run, 183/183 in the browser. Live check after deploy: the person who messaged us reads as *conversation*, everyone else as *initiated* with a full allowance — history is not counted, so the caps start from today.

### ✅ SHIPPED 2026-09-16 — the Payment Guardian, and attachments that take what people have
- ✅ **Payment Guardian** (`biz_nidaan_pay_guard.py`) — 12 checks over 48h, every 5 min on the worker, heartbeat every 10 on web. Judges **only what happened since it started watching**, and only **our** mechanics (`_is_ours`: Sarathi products skipped; must carry claim/account/purchase). Telegram to super-admins with a **Seen** button, **repeating every 10 min** until one presses it (who + when recorded), and **back after 2 hours** if still unresolved — the founder's design exactly. Verified clean against production.
- ✅ **Four real payment bugs fixed underneath it** — subscription payments never announced; 8 duplicate ledger pairs (₹6,474); a **first** charge treated as a renewal (5 customers, ₹4,714 + a free month); NP-151's Level-2 fee handled twice. Exact-paise ledger, once-per-payment `dedup_key` + conditional UPDATE, first-charge/7-day guards, `announced_at` stamped on the row.
- ✅ **One event, one message** — a branch Level-2 fee was announced twice (its own message **and** a ledger "Payment RECEIVED"). The ledger now stays quiet for `branch_l2` and that message stamps `announced_at` itself, so the Guardian still counts it as announced.
- ✅ **Attachments take what people actually have.** The founder's own repudiation letter — a real PDF with stray bytes before its header — was being refused. Uploads now decide from **the file's own bytes** (`_sniff_file`; `_ALLOWED_MIME` deleted): everything **except video**, 25 MB a file, and a refusal says what to do instead. **HEIC → JPG** on the way in (keeping the phone's name); HTML stored as `.txt` so nothing can run from our domain. ClamAV, signed expiring links, nosniff and the attachment disposition unchanged.
- ✅ **Documents open where staff are standing** — click to read a PDF, photo, or **Word letter** (text extracted server-side, escaped by the page; the file itself is never rendered). **Rename** a badly-named file in place — stored file and real extension untouched, rename written to claim activity. Download still one click away.
- ✅ **Caught in testing:** `io` was never imported in `sarathi_biz.py` (DOCX + HEIC failed silently) and `claimId` was used outside its scope in `docsRender` — neither visible to `node --check`.
- ✅ **Proof:** test_attach 26 · test_guard 29 · test_payments 23 · test_dups 16 · test_query 29 · test_lock 41 (fresh copy of the live DB, `NIDAAN_NO_OUTBOUND=1`) + **183/183** in the browser on the live site.
- 🟢 **NEXT (founder-decided, not started):** plan terms grandfathered at purchase (upgrades reach everyone, downgrades only new, impacted subscribers named before saving + flagged to super-admins); the claim-registered WhatsApp to complainants with caps (**2/day, 5/week**, reasonable messages only) + a STOP option with consequences and a restart path.
- 🔴 **OWNER:** submit the WhatsApp **authentication** template to Meta (push stays manual for now; WhatsApp OTP login on hold until the structure is stronger).

### ✅ SHIPPED 2026-09-13 — the Level-2 bucket system
- ✅ **Buckets are DATA** (`biz_nidaan_buckets.py`, 5 tables): 11 ClaimShield-named buckets, 28 sub-states, 60 fields, 37 routes, seeded on boot. Re-seeding **never overwrites an edit** (asserted: rename a bucket, re-seed, the name survives), so a super-admin owns them once written. Claim answers live in `nidaan_claim_fields`, so inventing a field never means an ALTER on `nidaan_claims`.
- ✅ **Two steps, two people.** Intake **hands over** from L2 Claims (probing questions built from that claim's own readiness + two judgement questions no check can answer + a mandatory note) → lands in **To start** → Level-2 **starts** it. `start_l2` refuses a claim nobody handed across. Handing over twice is refused and names who did it first.
- ✅ **Readiness gate.** BLOCK vs FIX. Live findings: **0 of 22 fully ready, 13 BLOCKED** (all with no insurance company recorded), 22 with no checklist, 21 with no authorisation. The insurer check caught two live claims holding a PERSON in that field (NP-146 "RASHMI TIWARI", NP-79 "REENA KUSHLANI").
- ✅ **Any bucket, any direction.** Configured routes decide what is offered FIRST, not what is permitted — an off-route move is allowed and recorded as *"(off the usual path)"*. Refusing it would only teach people to work around the system.
- ✅ **GROUND RULE: every move carries a comment**, forwards as well as backwards. The prompt changes with direction ("what you did and what is still pending" / "what is wrong?" / "why paused?").
- ✅ **Arrivals notify the receiving bucket's on-duty staff** (bell + Telegram). Nobody rostered → goes to super-admins *and says so*. A backward move also tells the person who sent it forward.
- ✅ **Parking wakes itself** — remembers its bucket, hourly worker returns it on the date.
- ✅ **Sub-state clocks override the bucket's** — Annexure 5 Pending goes amber at 5 days inside a bucket measured in months.
- ✅ **One writer, one vocabulary.** Found a REAL claim in the first-generation stage names (NP-44, started by ASHWIN 12 Sep) — migrated on boot, old endpoints now delegate to the bucket engine.
- ✅ **Corrected course twice on founder feedback:** built a separate "Hand to Level-2" screen when a *button on L2 Claims* was asked for (removed, folded into the row); and had made forward moves silent (now every move needs a comment).
- ✅ **🧩 Bucket Designer (super-admin, Configuration).** The process is data, so the office owns it: create/rename/retire buckets, set the amber & red clocks and who we are waiting on, write the four lines of guidance staff read, add or retire the steps inside a bucket and the fields captured in it, open or close the usual next steps — no release needed. **The rule the screen enforces: nothing is deleted while it holds work.** A bucket with claims refuses to be turned off *and says how many*; a field somebody has already answered is turned **off**, never removed, and every answer already recorded survives (that record is what a case is argued from). Retired items stay listed, greyed, and come back on one click — `substates()`/`fields()` gained `include_inactive`, used only by the designer. Closing a route traps nothing: any bucket is still reachable, it just stops being offered first. Every route created here needs a comment, so the ground rule cannot be opted out of by adding a new route. **46 checks against a copy of the live DB + 22 against the live app, all passing**, including "an answered field survives being turned off with its answer intact" and "Live Cases, holding 1 claim, refuses to disappear".
- ✅ **Channel Partner approval actually runs now.** It never had: `ops_cp_create` required `sub_super_admin` **and** the editor lived inside the super-admin-only Content panel — so only super-admins could create one, and a super-admin's own entry auto-approves. CPs now have their own screen (**🤝 Channel Partners**, under People, every staff member), anyone else's proposal starts PENDING and stays invisible on the claim form until a super-admin approves, and **the proposer keeps seeing their own pending entry** instead of watching it vanish and adding it twice (which hit the duplicate guard and looked like a bug).
- ✅ **📄 Pending-document window** (`biz_nidaan_doc_request.py`, opened from the docs count on any L2 row). Three columns from the founder's drawing: **what we still need · who it goes to · what we will say**. Claim type at the top (correcting it re-seeds the standard list without touching anything received or added by hand); arrived docs go green; add anything; remove anything **with a reason that is kept on the claim under the remover's name**. Recipients = every channel the claim came through, complainant as TO and everyone else CC'd, extra mobiles/emails **add AND remove**, all validated server-side. **The Send button does not send** — it opens the read-back, and the server issues a checksum for that exact list+wording+recipients and refuses without it, so editing anything afterwards returns you to the check. 54 checks on a live-DB copy + 28 live.
- ✅ **The chase stops and becomes a phone call** — 3 days, twice, then bell+Telegram to the bucket's duty staff to phone; note required, and it closes the chase. Every nudge carries *"if you have already shared all the required documents, please ignore this message"* in EN+HI. Everything arriving switches the clock off.
- ✅ **Checklist is per-claim, not per-type.** `pending_required_docs`/`checklist_status` walked the TYPE TEMPLATE and looked rows up by key, so a doc added for one case was invisible to the chase, the dashboard and the pay-gate. Both now walk one merged list (`effective_docs`). **Channel Partner added to `get_claim_parties`** — the one party it never resolved, approved partners only.
- ✅ **THE WHOLE JOURNEY VERIFIED END TO END** (Sep 14) — one real claim walked
  L2 Claims → handover → refused and sent back → handed again → Start Level-2 → Live Cases →
  Pending Docs → Pending Draft → Escalation → Lokpal → Completed → Pending Payment →
  CP Payment → Finished → pulled back → parked → woke itself → jumped off the usual path.
  **61 checks, all passing**: every move refused without a comment, every move told somebody,
  every step landed on a real sub-state, and the claim's whole story reads back with a name
  against each line. Business-critical flow is sound.
- ✅ **`/l2-manual` rewritten** — it still described Consolidation / Documents / Drafting /
  With the insurance company / Ombudsman / Outcome / Settlement, none of which exist, and had no
  CP Payment or Finished at all. Both languages rebuilt against the nine real buckets with the
  amber-day counts read from the database.
- ✅ **Intake IS a rosterable duty** — done as a side-effect of the duty-vocabulary repair;
  staff #8 is on it now.
- ✅ **Claim Pipeline retired**, its two good ideas (*Brought by* / *Customer* + unpaid leads)
  moved into All Claims first. Claims Dashboard stays: it is the only claims screen a
  `team_member` can open.
- 🟢 **NEXT:** claim panel redesign (one popup, no scrolling), claim communication redesign
  (complainant + CC every channel), Notification Control Centre, folding Claims Dashboard in.

### ✅ SHIPPED 2026-09-14 — live testing with the founder, rounds 1–3
_The founder tests step by step on real claims and reports; each fix is proved through the real
routes on a copy of the live DB and in a real browser (`uitest/flow.mjs`, **125/125**) before the report goes back._
- ✅ **Round 1 — L2 Claims → Level-2.** Manual **attach documents** on the claim panel (any claim,
  virus-scanned, 25 MB guard, can tick the checklist line it answers). **"All documents received"
  tick** on every L2 Claims row, in all three views (table / board / cards — Board and Cards had
  no Move controls at all). The tick is what lets a claim move to Level-2 (founder's rule); the
  handover itself is never otherwise blocked. **WhatsApp document collection fixed**: it messaged
  the wrong number (insured, not complainant), sent free text outside the 24-hour window (refused
  by WhatsApp, reported as success), and now uses the approved template cold, the guided chat
  in-session, and reports honestly who it went to and what failed.
- ✅ **Round 2 — the ClaimShield case record.** Gist form, Initial Claim Assessment Sheet, Draft form
  (Draft + Lokpal Draft, formatted) and the Case Report, filling in as each bucket completes, same
  layout as ClaimShield. Drafts are formatted HTML **sanitised on write and on read** (allowlist of
  11 tags, every attribute dropped, script/style/iframe bodies removed); a draft over 60,000
  characters is **refused, never truncated** (the old box silently cut at 8,000).
- ✅ **Round 3 — (founder, 14 Sep).**
  - Report **Manager** = the claim's chain (origin · via partner · branch). Operation officer left as is.
  - **Processing Fees** from the payment ledger: "Subscriber raised — no processing fee", "₹X paid
    (review fee / branch Level-2 fee)", or "Not paid".
  - **No pending-documents talk after Level-2 begins** — documents are gathered in L2 Claims now. The
    why-line only mentions documents in Pending Docs itself; rows show **files attached** (NP-119
    had 8 files and read "0/4"); Live Cases' next step is **Pending Draft** (route tombstoned).
  - **Documents open in the page, not as downloads.** PDFs are served inline **only** when the viewer
    asks (`?inline=1`) and only for files proven PDF by their own first bytes at upload; nosniff +
    `frame-ancestors 'self'`. Everything else still downloads under the sandbox CSP. Images show
    via `<img>`. Verified in real Edge: 0 downloads. Escape closes the viewer and keeps the case sheet.
  - **Gist form**: Consultation %, CF amount, Review fee (PF), PF transaction no. removed (fields
    retired, answers kept); **Policy No. + Policy Inception Date** added, saved on the claim.
  - **Full claim ↗ opens in its own window** straight onto the claim.
  - **Drafts as two big equal boxes side by side** (32rem each) — on the case sheet and the Draft form.
  - **Escape closes whatever is really on top** (visible layers only, by z-index) — an account
    drawer hidden with display:none had been swallowing it.
- ✅ **Round 4 — the same alert twice (NP-151).** Every staff bell already mirrored to Telegram;
  a 12 Sep change added a second mirror in `notify_staff_inapp`, and 11 callers ran a third loop.
  Now ONE Telegram per bell (the bell's own), `telegram=False` finally honoured, and
  `_telegram_mirror` drops identical text to the same person within 2 min. **The Level-2 fee
  was handled twice** (branch verify + Razorpay webhook, `mark_l2_paid` True to both): the
  complainant got the thank-you WhatsApp twice. `on_branch_l2_paid` is now once per payment
  (dedup key on the claim's payment id) and the write is conditional. **The WhatsApp inbox now
  shows the words a template sent** (approved wording from Meta, cached 6 h, values filled in).
- ✅ **Round 5 — one screen for the whole line; the claim as a popup.** My Desk and Case Board
  folded into **Level-2 → Settlement** (landing page): rail = All open claims · Before Level-2
  (Intake/Review/Conversion — 94 of 97 open claims live here) · To start · the buckets · Paused;
  Case Board's list/filters/"Change status or owner" sheet reused as-is; My Desk's Today strip
  (on duty, not covered, on fire) on top; Set duty per bucket. Old links redirect; nothing deleted.
  **Claim panel = centred popup on ≥768px** (3 columns ≥1200px: who & what | the work |
  conversation & history; 2 on tablets), sections moved not redrawn; phones keep the side panel;
  tasks/leads/QR keep the side panel. Browser test serves a local build against live data
  (`--local-html`) so screens are proved before deploy — 137/137.
- ✅ **Round 6 (15 Sep) — windows, drafts, the line.** Only a window's own ✕/Cancel closes it
  (capture-phase guards: background click + Escape do nothing, all windows incl. overlays and ndUI;
  phone menu shade exempt). **NP-112's Lokpal Draft was refused 8× (422)**: Word paste of a
  2.4k letter = 89k chars > request cap. Fix: paste cleaner (`_csrCleanPaste`), raw cap 400k with
  the 60k limit on the sanitised text, autosave 1.5 s + on blur (version-checked), failures red +
  toast + ask-before-close. **Case sheet shows "Built so far"** (other buckets' fields in line
  order, drafts as the editable pair, password masked). Browser 162/162; nothing written to live
  claims (save route answered in-browser).
- ✅ **Round 7 (15 Sep) — finished work locks.** Past its owning bucket, work locks for all but
  the 3 super admins (gist + core facts open through Pending Draft, then lock with the drafts);
  enforced server-side at the field save, Gist/Draft forms and claim-info edit. Back moves flagged
  (who/from/why/super) until the next forward move; restart = clock + steps + unlock, nothing
  erased; Pending Docs keeps documents. **Request a change** → super admins (bell/Telegram/email)
  + remarks. **`NIDAAN_NO_OUTBOUND=1`** stops Telegram/email/WhatsApp/push for test runs (some
  suites had stubbed only WhatsApp — earlier test runs may have sent staff real Telegram/email
  about test moves). Tests 41 + 423; browser 168/168.
- ✅ **Round 8 (15-16 Sep) — payments, the draft query loop, filters, no flicker.**
  **Payments:** no "payment received" alert ever fired for subscriptions (now from `record_payment`,
  every source, once); webhook first activation recorded twice (rounded `sub_` row + exact `pay_` row);
  first charge taken for a renewal when the subscriber's confirmation won the race (+30 days, counted
  twice); "Plan Activated!" emailed 3×. All fixed (22 scenario tests). **Draft query:** Raise (Pending
  Draft → Live Cases, loud alert, pinned red, daily reminder, super admins at 3 days) → Resolve (pick
  doctor/advocate → Pending Draft) → clears on moving on. **Ask the complainant:** call or ONE message
  (np_doc_reminder template carrying the exact words / email, CC branch+subscriber by email; 2nd refused
  while unanswered 24 h); WhatsApp reply → 3 super admins + sender. **Filters** kept per person
  (`nd_keep_<staff>` in localStorage) until Clear filters; refresh returns to the same screen. **No
  flicker:** `nidaan_change_seq` (20 SQLite triggers) + `GET /changes` every 10 s → ghost-swap refresh.
- 🔴 **FOUNDER DECISION — payment ledger correction (nothing changed yet):** (A) mark 8 rounded webhook
  duplicates duplicate: pay_id 44, 58, 63, 72, 76, 79, 82, 84 (₹6,474); (B) mark 5 rounded first-payment
  rows duplicate 48, 50, 60, 66, 69 and relabel 49, 51, 61, 67, 70 renewal→subscription (₹4,714);
  (C) 5 customers got an extra month — accounts 116 BHARTI JAIN (platinum), 118 LAKSHYA PARDESHI,
  123 LOKESH SHARMA, 126 MILIND GUNJAL, 127 AMRIT LAL BALANI: keep as goodwill or pull back 30 days;
  (D) account 85: two ₹588 rows on two subscriptions (19/20 Aug) — check whether they paid twice.
- 🟢 **Letter drafting from the gist** — the Draft form's case facts already fill from earlier
  buckets; the two letters are typed. Possible next step: a starting letter composed from the
  gist facts for the drafter to edit (founder to decide).
- ℹ️ **Sarathi side, for that terminal:** a DNS blip at the host (14 Sep 17:04) made the Sarathi
  Razorpay plan lookup fail at startup, and it created a new `individual_annual` plan
  (plan_TbxZG9cdrwKcBJ) instead of finding the existing one - check which plan id new Sarathi
  subscriptions now use.
- 🔴 **Security hygiene (Sarathi side):** the legacy Sarathi bot's startup error prints its bot
  token into the journal (token is already rejected by Telegram, so dead) - redact exception
  text from Telegram library errors before logging.
- ℹ️ **Data notes for the founder:** Dr. Ashish's NP-119 draft (1,875 chars) was typed into the old
  one-line box and lost its line breaks — words intact, re-paste restores the layout. ANNAPURNA
  KASERA saved an empty Lokpal draft.

### 🔵 QUEUED (founder, Sep 13 2026) — 🔔 Notification Control Centre

### 🔴 FOUND ON NP-112 (founder, Sep 13 2026) — two definitions of one fact, and a wall
- ✅ **The screens disagreed about who had paid.** The claim screens have always shown "L2
  covered" when the **L2 fee is paid OR the claim came in on a subscription OR the claim itself
  is paid** — three routes we genuinely sell the work through. `l2_ready()` accepted only
  `l2_payment_status='paid'`. NP-112 is a **subscription** claim: the subscriber had already
  paid, L2 Claims said so, and the handover refused it. Not rare — **of 72 can_fight claims, 23
  are subscriptions and 14 otherwise paid**, so the office was seeing 23 qualified where it
  should have seen 60. One definition now (`l2_fee_covered`), and `case_state`'s second copy of
  the rule now calls it instead of restating it. **Pending-handover list: 23 → 59.**
- ✅ **The live smoke test then caught what the unit tests could not:** four queries selected
  `l2_payment_status` but not `payment_status`, so the new rule read `None` and NP-112 *still*
  failed inside the handover. Unit rows came from `SELECT *`; the endpoint's did not.
  `pending_handover()` also had the old single-route rule hardcoded in its SQL `WHERE`.
- ✅ **NOTHING BLOCKS A MOVE** (founder's rule, stated twice). Handover no longer refuses on
  payment / readiness / unticked questions; Start Level-2 no longer refuses on payment /
  readiness / missing handover; a forward move with required fields blank no longer refuses.
  Each collects what is outstanding, **shows it**, and lets the person through on a written
  reason — which lands on the claim with their name, travels to Level-2 in
  `l2_handover_checks._open`, and is written onto the timeline (`STARTED WITH THESE STILL
  OPEN…`, `[left blank: …]`). The only two things that still ask for a sentence are the two that
  would make the move meaningless without one: **no comment at all**, and **a park with no
  return date**. Both ask; neither forbids. And the ask now names the blank fields in the same
  breath, instead of making somebody write a note, press again, and only then learn what was
  blank.
- ✅ **Every popup has a way out.** The shared modal had **no close button** — it closed on a
  backdrop click and on whatever buttons the caller passed, so a dialog whose buttons all *do*
  something was a trap (which is what the handover dialog was on a phone). Now: an **X** that
  stays put while the body scrolls, **Escape** closes the top-most overlay, and the footer
  **always** carries a Close even when the caller passes none. Audited all **19** hand-built
  overlays — 18 already had an X or Cancel; the one-time onboarding modal had neither (its only
  exit saved a phone number first, so a rejected number was a dead end). All 19 tagged for
  Escape. *(25 checks on a live-DB copy + 6 live on NP-112 itself.)*

### 🟢 COURSE CORRECTION (founder, Sep 13 2026) — copy ClaimShield, add the visibility
> *"why we are making it complicated... we only create visibility and proper notifications
> that's it"* — and: the bucket designer is a once-or-twice exercise, not a product.

**What the office actually needs:** the ClaimShield process they already know, with the one
thing ClaimShield never gave them — **when a claim sits in a bucket, why is it sitting there,
and how many others like it?**

- ✅ **Every claim says WHY it is waiting.** One plain sentence per row, from facts already
  computed: the closing one-year window first, then a pause and its date, then documents, then a
  required field still blank, then who-we-are-waiting-for-and-how-long. Plus **the comment the
  last person left when they moved it**. Replaced the Origin column — nobody triages by origin.
- ✅ **Every bucket says what is IN it**, not just how many: ours to move · short of documents
  · past the limit · window closing. A count is the size of the pile; this is a briefing.
- ✅ **Reimbursement retired** (founder: drop it — documents now arrive through the many intake
  channels). Retired, not deleted, so it can come back. `pending_draft` now goes onward to
  `escalation`; **no bucket left without a way onward**. Test bucket removed.
- ❌ **DROPPED, deliberately:** drag-to-reorder, declared forks, on-arrival action lists, exit
  conditions. The buckets get set up once or twice and then never touched — building a process
  designer for a once-a-year act is the complexity the founder is objecting to. The existing
  designer already creates, renames, retires and reorders by sort_order; that is enough.
- 🟢 **NEXT:** notifications to match — the other half of *"visibility and proper
  notifications"*. See the Notification Control Centre below.

### 🔵 QUEUED (founder, Sep 13 2026) — 🔔 Notification Control Centre
One super-admin screen that owns **who receives what, on which channel** — and a per-claim
override that beats it.

**The grid.** Rows = every event we can raise (`event_key`: `bucket.move`, `bucket.sent_back`,
`doc.call_due`, `cp.pending`, `payment.*`, `support.*`, `wa.*`, `task.*`, `leave.*`, `radar.*`…).
Columns = every channel (**web bell · Telegram · email · WhatsApp**). Cells = who
(**super-admin · sub-super-admin · the bucket's on-duty staff · the assigned staff · the claim's
parties**). A super-admin ticks the grid; nothing else in the app decides this any more.

**Precedence — the rule that matters, in order:**
1. **Per-claim setting wins**, whenever somebody has changed it on that claim by hand.
2. Otherwise the **global grid** decides.
3. Consent always wins over both: WhatsApp STOP and email unsubscribe are never overridden by
   any setting, by anybody. That is a legal line, not a preference.

**Why it is needed:** the rules are currently spread across `biz_nidaan_notifications`
(`_super_admin_staff`, `notify_staff_inapp(..., email=)`), `biz_nidaan_notify_policy`,
per-call-site `email=True/False` flags, and `_notify_move`'s own fallback — so "why did fourteen
people get that email?" has no single place to look, and turning one thing off means finding
every call site. This screen becomes that single place.

**Build notes:** new table `nidaan_notify_rules` (event_key, channel, audience, on) +
`nidaan_claim_notify` (claim_id, event_key, channel, audience, on, set_by, set_at) for the
override; one resolver `who_gets(event_key, channel, claim_id=None)` that every notify call goes
through; a "what would happen" preview per event so a super-admin can see the effect before
saving; and every change audited. **Nothing ships until the existing call sites are migrated to
the resolver** — a half-migrated policy is worse than the spread-out one, because it looks
authoritative and is not.

### 🧭 DECIDED (Sep 13 2026) — what happens to My Desk / Case Board / Claim Pipeline
Surveyed all four work screens before answering. **Keep My Desk. Fold Case Board into Level-2 → Settlement. Retire Claim Pipeline.**
- **Claim Pipeline goes.** 81 lines, read-only, and it *never reads `pipeline_stage`* — it recomputes a stage in the browser from status+payment+outcome using ten names that match neither the buckets nor `case_state`. Two columns (`drafting`, `escalation`) are hardcoded empty placeholders. Its own header still claims it "replaces the split Dashboard/All Claims/L2 views". **Worth keeping:** the *Brought by* (source_kind) and *Customer* (subscription/₹499/unpaid-lead) filters, and unpaid leads — all three belong in the merged claims view.
- **Case Board folds in.** Unique: blocker, assignment, problem flags. But `waits_on` on the bucket already models the blocker, and the L2 screen has substates, fields, rule-driven moves and readiness that Case Board has no equivalent of. Two screens disagreeing about one claim is exactly what just bit us.
- **My Desk stays** — sole owner of the on-duty chips, leave-coverage alerts, the on-fire list with a written reason per case, the journey map and the EN/हिंदी toggle.
- 🔴 **DISCUSSION OPEN:** pending-document collection window — `/doc-collect` (Q14–Q17); one claims view — `/claims-view` (Q11–Q13 answered, build pending).

### 🔴 FOUND & FIXED THIS SESSION — three live defects
- ✅ **WhatsApp was dead in BOTH directions (not a code bug — 2 Meta setup steps were never done).** Diagnosis: phone `status=PENDING`/`platform_type=NOT_APPLICABLE` → number was **never registered on Cloud API** (every send failed `#133010 Account not registered`); `subscribed_apps=[]` and the app was subscribed to the **`user`** object instead of `whatsapp_business_account/messages` → **0 inbound messages ever**. Fixed via Graph API: registered the number (**2FA PIN `481902` — record this**), subscribed the app to the WABA, and subscribed `whatsapp_business_account`→`messages` to our callback. Now `status=CONNECTED`, `platform_type=CLOUD_API`. **Also fixed in code:** an inbound from a number with no claim got NO reply (`handle_inbound_text`→`no_claim`, nothing sent) → now answers (first touch = full value message, later = short follow-up) + one-time ops alert + CRM lead.
- ✅ **Subscription RENEWALS were a silent no-op (caught 3 days before the first one).** `activate_from_razorpay_webhook` returned early whenever the subscription row existed, so every `subscription.charged` skipped period extension, GST **and** the payment ledger — a paying customer would have shown **expired** and the renewal never reached Revenue. Split activation vs renewal; renewal extends `current_period_end` from the LATER of now/current end, records GST + `record_payment`. `record_payment`'s return value is the idempotency gate (duplicate webhooks / the activated+charged pair can't double-count). Period now from live `nidaan_plans_config` (monthly=30d, was defaulting to 92d).
- ✅ **Pipeline "Subscriber 0"** — real but misleading: `source_kind` is an attribution chain where a branch/staff referrer outranks subscriber, so all 9 subscription claims counted as Branch/Staff. Split into two honest filter rows: **Brought by** (source_kind) and **Customer** (subscription / ₹499 paid / unpaid lead).

### 🟡 Multi-party claim notifications (founder Sep 3) — P1 shipped, P2 next
- ✅ **P1** `biz_nidaan_claim_parties.py` — `get_claim_parties(claim_id)` resolves complainant / subscriber / branch-My-Business / referring+assigned staff with usable contacts; `notify_claim_parties()` fans ONE update to all of them (email+dashboard via the engine, WhatsApp via Cloud API, STOP always respected). **Contact gaps first-class:** deliver on the channel we have, ask for the missing one in-message, and `contact_gaps_for_account/branch()` expose it for a dashboard nudge. Added `nidaan_branches.contact_phone` (branches were email-only). Wired into **claim status change** (`roles=[complainant,branch,staff]`, so the existing account-holder email isn't duplicated). **Verified live:** claim 98 → complainant + branch house account + BIAORA BRANCH + staff, and correctly flags every branch as missing WhatsApp.
- ✅ **P2a shipped** — **"🔔 Who gets notified"** panel in the claim drawer (`GET /claims/{id}/parties`): every party + a ✓/⚠ chip per channel so the case handler can chase what's missing. **Branch WhatsApp now enterable** — `contact_phone` wired end-to-end (list query, Branches table column with add/edit, `PATCH /branches/{code}`); it existed in the schema but nothing read or wrote it, so every branch was permanently "missing WhatsApp". **No-backlog rule honoured:** notifications only fire on live events — adding a contact starts the flow from that moment, nothing historical is replayed.
- 🟢 **P2b NEXT:** wire the same fan-out into **review delivered, document request/received, comment/note updates**; **subscriber-side dashboard nudge** to capture a missing number/email; add a **`np_claim_update`** Meta template so cold party WhatsApp works.

### 🟡 WhatsApp as the full customer channel (founder Sep 4) — self-service LIVE, rest queued
- ✅ **Dead-end killed.** A handoff set `human_takeover=1` and the bot then went permanently silent (claim 16 — cleared). Now it acknowledges at most once every 2h under takeover, and most questions never reach a handoff at all.
- ✅ **Verified self-service** (`biz_nidaan_wa_identity.py`). WhatsApp proves number possession, so a number matching our records IS an authenticated identity. `resolve()` → complainant / subscriber / branch / staff / unknown; `safe_context()` returns a **support-desk view** (friendly stage wording, what we still need, plan validity, branch book) and deliberately NOT internal notes, colleague names, legal opinion or settlement figures. Decided outcomes + no-scope reviews are `handoff_only` so a person delivers them. Staff are redirected to the **Telegram office bot** (staff never work from WhatsApp). **Verified live:** "mera claim ka kya status hai?" → real answer (NP-0016, reviewed, 3 docs pending); "kitna paisa milega?" → handoff.
- ⏸️ **PAUSED ON FOUNDER'S INSTRUCTION (Sep 4) — L2 process and beyond.** Do NOT resume without a fresh go-ahead. Parked: signup/onboarding on WhatsApp, payment links + confirmation in-chat, **L2 authorization/consent capture**, richer prospect sales flow, and the post-L2 pipeline stages (drafting / escalation columns are reserved but empty). Already live and unaffected: campaigns, doc-collection, journey alerts, lead capture, verified self-service support.

### ✅ WhatsApp conversation quality (founder Sep 3, live-tested)
- ✅ **Repeat loop killed** — `start_or_continue` greeted on EVERY inbound (the "greet once" comment was never implemented) and `handle_inbound_text` ignored the message text entirely. Now greets once ever, throttles a repeated doc ask (90 min) unless the customer says they're sending it.
- ✅ **Conversation brain** (`biz_nidaan_wa_brain.py`) — reads the message → `answer | continue_docs | refuse | handoff`. Anti-hallucination locked (service facts only; claim status/money/legal outcome ⇒ handoff, never a guess; AI failure ⇒ handoff). Abuse/off-topic ⇒ decline **once** in their language, then silent 3h. Handoff opens a **Support thread** (channel=whatsapp) + escalates + sets `human_takeover` so the bot never talks over staff.
- ✅ **Language is remembered** — "can you talk in english" used to be answered in English once then revert. Brain returns `set_lang`; orchestrator persists it to `nidaan_wa_contacts`, so all later replies/asks/reminders follow it until changed. **No script mixing:** `_doc_label` picks the document name in the same script as the sentence (Hinglish ⇒ Roman/English label, not Devanagari mid-sentence). Verified live: en/hi switch both detected + applied.
- 🔴 **OWNER — display name:** "NidaanPartner" was REJECTED by Meta; founder resubmitting as **"Nidaan Legal Consultants"** (matches the LLP, best approval odds). Put that name visibly on nidaanpartner.com before/near resubmission; avoid rapid retries (repeat rejections can lock changes ~30 days). Sending is unaffected — number is CONNECTED, templates approved.
- ✅ **Pipeline counts VERIFIED correct** against the DB: active total 48 (29 archived excluded) = Subscriber 10 + ₹499 paid 11 + Lead 27, and Brought-by 21+18+0+5+4. "Self 0" is honest — every subscriber came via a branch/staff referrer.
- ✅ **L2 "Subscriber / Referred by" split into two columns** (table + CSV); a partner house account now reads "(partner-raised)" instead of posing as a subscriber.

---

## 🟦 NIDAANPARTNER.COM

### ✅ Notification decision layer (Sep 5)
`biz_nidaan_notify_policy.py` decides the **email leg per event AND per recipient**. Bell + Telegram are **never** suppressed — only email is downgraded, so nobody is left uninformed.
- **Always email:** `payment.*`, `claim.doc*`, `doc.*`, `leave.*`, `health.*`, `cp.*`, `security.*`, `subscription.*`, `claim.filed*`, `claim.l2*`, `claim.review*`, `support.*` (founder: money, documents and leave must always trigger).
- **Super-admins keep email on everything** — they're the backstop.
- **Telegram + bell only:** `quick_task.comment`, `.comment_ack`, `.status`, `.created`, `.mention`, `claim_note.mention`.
- **Unrecognised event ⇒ still emails.** Silence must be deliberate, never inherited by a new key. Policy is wrapped so it can never itself silence a real alert.
- **Measured:** staff email **53/day → 26/day** (≈792/month saved, 50%). Less than before but honest — the 3 super-admins still receive chatter by design, and `leave.requested` (416/mo) is kept per instruction.
- 🟢 Next: an ops screen showing the live policy (`summary()` already returns it) so the rules are visible rather than folklore.

### ✅ WhatsApp public/verified split — email-OTP identity + leak guard (Sep 7, DONE)
Anyone can now find NidaanPartner on WhatsApp and chat with the bot, without that opening a door to customer data.
- 🔴 **The old model called a phone match "authenticated"** — the identity module said so in its own docstring. Behind those roles sit other people's claims by name (the branch view lists a partner's whole book). Numbers get recycled, SIMs swapped, phones shared. Fixed: `resolve()` returns `verified: False` always; a match is a *candidate*.
- **PUBLIC mode** (default, every unknown number): service, pricing, claim types, how to start. Nothing about any customer/claim/staff/branch/ops — and it will not confirm or deny whether someone is our customer, since that is what a fisher wants.
- **VERIFIED mode** (12h, earned): 6-digit code to the **registered email**, not the phone — a factor the SIM holder does not automatically have. Codes are HMAC-hashed with a server secret (refuses to hash if none configured), single-use, 10-min expiry, 5 attempts then burned, 5/number/day, `compare_digest`.
- **Three layers, since a prompt is not a security control:** (1) STARVE — `safe_context()` returns nothing unverified, gated *inside* the function so no caller can forget; (2) INSTRUCT — separate public system prompt; (3) INSPECT — every reply to an unverified number scanned for claim refs / emails / phones / branch codes / policy numbers / non-public amounts, and **replaced whole** (never trimmed). Layer 3 holds when 1 and 2 fail.
- Ops UI: Verified / Not verified badge on every conversation + filters; the thread header tells staff plainly what they may not type into an unverified chat.
- Page now carries a **step-by-step "How to run a campaign"** guide and a plain-language explainer of the two modes.
- Verified on the server: 13 auth checks + 7 routing checks pass. The routing test forces the model to emit `NP-0042` to an unverified number and asserts the customer never sees it.
- 🟡 Open: `_asks_private()` is keyword-based (deliberately over-triggering — a false positive costs one verification step, a false negative costs a leak). Staff on WhatsApp are still pointed to the Telegram office bot rather than served ops data.

### ✅ Payment noise cut + failure chase (Sep 7, DONE)
- **Money emails: 14 → 4 per failure.** `payment.*` now emails super-admins + whoever owns the item; everyone else keeps bell + Telegram. Nobody owns a failure that lands in thirteen inboxes, and it was eating the allowance login codes depend on. Documents and leave are untouched — still broad.
- **Unrecovered failures are chased on Telegram** — up to 3 nudges, 12h apart, 7-day window, stopping the instant a `payment_success` event appears for that contact. Telegram only, never email.
- 🔴 **`payment_success` events were never written.** The ops funnel showed pay_opened → 0 successes forever, so every conversion rate it displayed was wrong. `record_payment` now emits them.
- 🟠 **Still worth knowing:** the watchdog's "stuck payment" check compares `payment_success` events against ledger rows. Now that both are written by the same call it can never disagree — it is a **tautology, not a guarantee**. Real capture-vs-ledger reconciliation has to come from the Razorpay API (`_tools/razorpay_webhook_reconcile.py`). Worth doing properly.
- 🟡 Still missing: **WhatsApp/SMS retry for phone-only customers** — 9 of 13 failures got no retry link at all because we only had their number.

### ✅ WhatsApp Inbox — structured chats, bot/human visibility, takeover (Sep 7, DONE)
The WhatsApp panel showed one flat table of the last 25 messages across every number. Now: conversation list + thread + takeover + reply-from-ops. Building it surfaced three real defects, all fixed:
- 🔴 **Outbound was NEVER logged.** `nidaan_wa_messages` held 27 inbound rows and **zero** outbound — every reply the bot ever sent was invisible and "Messages sent" had always read 0. Logging moved into `_post()`, the single choke point every send passes through. Failed sends log too (a message the customer never got must be visible).
- 🔴 **Takeover could not mute a claimless chat.** `human_takeover` lived only on `nidaan_wa_claim_settings`, so a prospect or branch — no claim to hang it off — kept getting AI replies after being handed to a human. Takeover now belongs to the conversation (msisdn); the document-reminder loop respects it too.
- 🔴 **No way to answer.** Staff had to open WhatsApp on a phone. They can now reply from ops, attributed to the real person even under impersonation; the first hand-typed reply takes the chat over automatically.
- Consent is checked **before** connection state — whether WhatsApp happens to be configured must never decide whether we honour a STOP. The 24h reply window is shown with time left and refuses sends WhatsApp would drop.
- Access: inbox = `sub_super_admin` (takeover needs available humans); settings + campaigns stay `super_admin`.
- Verified on the server against a throwaway DB: 12 inbox checks + 5 outbound-logging checks pass. Live smoke test returns real conversations with identity resolution.
- 🟡 Open: no template-send from the inbox yet (closed-window chats must go via Bulk campaign); inbox copy is English-only like the rest of ops.

### ✅ Payment failures audited (Sep 7) — none were ours
13 failures in 30 days, **every one user- or bank-side**: 8 timeouts/cancellations, 2 insufficient balance, 1 wrong OTP, 1 bank decline, 1 unconfirmed autopay mandate. Zero Razorpay errors in the logs, all 41 payments `verified=1`, watchdog reports no stuck and no mismatched rows — no money taken without being recorded.
- 🔴 **The real gap is recovery, not failure:** only **4 of 13** got a retry link, because `_send_customer_retry_link` needs an email and 9 of them were phone-only. Retry email is now `delivery_critical`; **a WhatsApp/SMS retry for phone-only customers is still missing** and is the highest-value fix here.
- 🟡 One failed payment fans out **14 staff emails** (all 13 staff + the customer's retry). Worth narrowing to super-admins + the assigned owner.

### ✅ Email deliverability + guaranteed fallback (Sep 5, DONE)
**DNS is authenticated** (owner completed): SPF is a single record `v=spf1 include:_spf.google.com include:spf.brevo.com ~all`, Brevo DKIM CNAMEs (`brevo1`/`brevo2`) live, `info@nidaanpartner.com` verified as a Brevo sender. Branded mail now passes SPF **and** DKIM.
- ✅ **Branding restored** — delivery-critical mail is no longer forced off Brevo; it keeps `From: info@nidaanpartner.com`.
- ✅ **Guaranteed fallback** — if every transport fails (most likely Brevo's 300/day free cap mid-day), delivery-critical mail is re-sent from the authenticated Google account with the branded address moved to Reply-To. Covers **login codes, verification codes, branch login links, subscription-activated and auto-pay-failed**.
- 🔴 **Testing found the fallback was a lie** — with Brevo simulated exhausted it did NOT deliver: `aiosmtplib` timed out on `smtp.gmail.com:587`, which this host throttles. The code's own comment already said 465 is the reliable path on cloud hosts. `_smtp_send` now retries on 465 when the configured port fails. **Re-verified: Brevo-down ⇒ still delivered.**
- 🟢 Brevo free tier is 300/day and hit 0 on 5 Sep. The fallback covers critical mail, but bulk/notification mail still needs a top-up or paid plan.

### ✅ OWNER — Brevo/DNS handoff (COMPLETED)
**`docs/nidaan/setup/BREVO_DNS_SETUP_PROMPT.md`** — paste-ready for the Claude extension. Authenticates `nidaanpartner.com` in Brevo + Cloudflare (domain add, DKIM records, **SPF edited not duplicated**, verify, validate `info@` sender, report credits). Verification codes already work meanwhile via the Google transport.


### 🔴 OWNER ACTION — DNS fix for email deliverability
**Signup/login codes were sent successfully but never reached inboxes.** Root cause is DNS, not code: `nidaanpartner.com` publishes `v=spf1 include:_spf.google.com ~all`, which authorises **Google only**. Every mail sent through **Brevo** while claiming `From: info@nidaanpartner.com` fails SPF, so Gmail spam-folders it — which is why every send logged `Brevo ✓` yet nothing arrived. Brevo also has **0 send credits** and no `@nidaanpartner.com` validated sender (only a gmail address).
- ✅ **Worked around in code:** delivery-critical mail (OTP/verification) now sends via the authenticated Google account so the envelope aligns, with `info@nidaanpartner.com` kept in **Reply-To**. Verified live: `SMTP ✓ ... from nidaanpartner@gmail.com`.
- 🔴 **The real fix (DNS):** set SPF to `v=spf1 include:_spf.google.com include:spf.brevo.com ~all` and add Brevo's **DKIM** records, then validate `info@nidaanpartner.com` as a Brevo sender. After that, branded `From:` works on every transport and **all** Nidaan mail (not just OTPs) stops landing in spam. Brevo credits also need topping up (free tier = 300/day; **257 sent today**).

### ✅ ClamAV on every upload (Sep 5)
Type checks prove a file is a well-formed PDF; they cannot prove it is safe — and we pass documents on to insurers, hospitals and staff, so we are a **distribution point**. `clamav-daemon` installed with full definitions; `biz_av_scan.py` talks to clamd over its UNIX socket.
- Scans **bytes in memory before anything touches disk** — an infected file never lands on the server.
- **FAILS CLOSED**: scanner unreachable ⇒ upload refused, so knocking the scanner over cannot switch scanning off.
- `validate_upload_scanned()` backs **all 10 storing upload paths**, so a future endpoint can't quietly skip it.
- App Health gains a **Virus scanner** check (fail-closed means a dead clamd blocks uploads — must be loudly visible).
- **Verified:** clean PDF allowed · **EICAR test virus BLOCKED** · scanner-down ⇒ refused.


### ✅ Sep 5 batch — CP, cache, uploads
- ✅ **Partner Documents column was invisible — a CACHE bug, not a missing feature.** It shipped, but the shared component loads as `nidaan_partner_claims.js?v=2` and Cloudflare caches `/static` `max-age=604800, immutable`. Browsers got a 2-day-old copy (`cf-cache-status: HIT`) while the origin had the new one. Bumped to `?v=3`. **Rule: any change to a /static asset MUST bump its `?v=`** or nobody sees it. (`/nidaan/ops` itself is `DYNAMIC`, so page changes land immediately.)
- ✅ **Stale WhatsApp alarm removed** — the legacy Evolution "no official numbers configured" check ran forever on a decommissioned subsystem; WhatsApp is Cloud API now (own green check). A permanent false alarm trains people to ignore the panel.
- ✅ **Channel Partners (CP)** — replaced the free-text roster with `nidaan_channel_partners` + approval gate. Sub-admin **proposes**, only a **super-admin approves**, and **who approved is recorded** (this is a name commission gets paid against). Pending CPs alert super-admins. Managed in ops → Content → Channel Partners; shown as "🤝 via \<name\>" in Source/Who. **INTEGRITY:** the claim form posts a `channel_partner_id` and the server resolves the name from an **approved** partner only — it previously posted free text, which would have walked straight past the gate. Old `associate_referrers` key retired + row deleted (two places to name a partner = how a bypass creeps back).
- ✅ **Uploads: one shared gate** (`validate_upload`). Rules were re-implemented per endpoint and had drifted — `/me/profile-pic` took the extension from the client filename with its own allow-list and never checked bytes; claim-note and quick-task attachments did the same with no content check; docsplit accepted arbitrary bytes. Now all enforce **size + real magic bytes + extension-from-bytes + MIME agreement**, with rate limits added. **Every NidaanPartner upload endpoint passes size+mime+magic+rate+auth.** Tested against HTML phishing pages, script-bearing SVG, .exe, shell scripts, a PDF whose MIME lies as text/html, oversize files and a PDF posing as a profile picture — all rejected.
- 🟢 **Remaining (Sarathi surface, lower risk):** `/api/marketing/upload-photo`, `/api/marketing/upload-logo`, `/api/microsite/upload-photo`, `/api/quotes/upload-ratecard` still lack size/mime/magic. Same `validate_upload` helper applies — separate app surface, do in a Sarathi pass.
- 🔴 **Still not done: antivirus scanning.** An *authenticated* user can still upload a malicious-but-well-formed PDF/DOCX. Bounded (identified users, audited, downloads rather than renders) but ClamAV on the upload path is the real close.


### ✅ Claim alerts reaching nobody — root cause + self-heal (Sep 5)
Claim **#108 produced ZERO staff notifications** while claims 101–106 each got the full 13. Cause: `on_claim_filed` runs in a **fire-and-forget asyncio task** and did the SUBSCRIBER dispatch first — that sends an email and took ~3s. #108 was filed inside that window **during a deploy**, so the process restarted before the admin loop ran and all 13 staff alerts vanished silently; nothing retried, nothing recorded them as missing.
- ✅ **Order fixed** — staff first (a fast local insert), subscriber second. Added the **Telegram mirror** the subscriber-filed path never had (only branch/ops had it) — which is why no Telegram arrived either.
- ✅ **Self-heal** — `sweep_missed_claim_alerts()` on a 20-min worker loop finds any recent claim with no `claim.filed.admin` row and sends it. Idempotent. **It recovered 4 claims on first run** (incl. #108), so this had been silently biting more than once.

### ✅ Associate referrer on My Business claims (founder Sep 5)
Staff contacts inside insurers/agencies send us business but don't want to appear as subscribers, so their introduction was invisible — no way to settle commission or track who refers whom. Added: content key **`associate_referrers`** (ops → Content, super-admin, one name per line — curated, not free text), `nidaan_claims.associate_referrer`, a dropdown on the My Business claim form (hidden entirely while the roster is empty), and **"🤝 via \<name\>" in the Source / Who column**. **OWNER:** add the names in ops → Content to switch the dropdown on.
- 🔒 **Privacy catch:** `public_content()` backs an **unauthenticated** homepage endpoint and would have published the whole roster — the exact names these agents want off the record. Added `_PRIVATE_CONTENT_KEYS`; verified live the roster is absent from `/nidaan/api/content`.

### ✅ Journal purged after the credential-logging fix (Sep 5)
118 leaked secret lines → **0**, 1.7 GB freed, 12h of operational logs kept. Rotation judged **unnecessary** on evidence: backups carry no logs, the journal is root-only, the app user can't read it, there are no other human shell accounts — and `biz.env` already holds the same secrets in plaintext readable by that same root, so the logging widened *where* the secret sat, not *who* could reach it.


### 🔴 SECURITY — OWNER ACTION REQUIRED: rotate two credentials
Found in the Sep 4 review: HTTP client libraries log every request URL at INFO, and **both Meta Graph and Google Gemini take their credential as a QUERY PARAMETER**. So the systemd journal contained live secrets — **10 `access_token=` (WhatsApp) and 64 `key=AIza` (Gemini) lines over 30 days** — and therefore so does every log backup / shipper. The WhatsApp token alone can message the entire customer base *as NidaanPartner*.
- ✅ **Future leakage stopped** — request-URL logging silenced for httpx/httpcore/urllib3/openai/google_genai. Verified live: the same credentialed calls now print **0** secrets.
- 🔴 **STILL TO DO (owner):** the historical journal still holds the old values, so treat both as exposed and **ROTATE** them — Meta (WhatsApp access token) and Google (Gemini API key). Update `/opt/sarathi/biz.env`, keeping `sarathi:sarathi 600`, then health-curl both sites.

### ✅ Proactive health watchdog (Sep 4)
`biz_nidaan_health_watch.py` on the worker, every 30 min — App Health only spoke when a human looked, which is exactly how the WhatsApp number sat dead for days. Alerts super-admins (bell + email + Telegram) the moment a subsystem breaks. **Edge-triggered**: one alert per outage, one on recovery, silent while green, re-arms once after 12h so a long outage isn't forgotten. State in `nidaan_ops_settings` (survives restart, no schema change). Extracted `_subsystem_checks()` so the panel and the watchdog run the **same** checks — a monitor that disagrees with the dashboard is worse than no monitor. Logic unit-tested incl. the corrupt-timestamp path. **Live run:** 10 subsystems checked, only "Contact reachability" failing (data completeness, deliberately not in the critical set), correctly stayed silent.

### ✅ XSS audit of the ops/dashboard/branch/portal surfaces (Sep 4)
Result is **reassuring**: every server-side field reaching `innerHTML` already passes through `esc()`. Two real but low-severity hits fixed — client-controlled **filenames** rendered raw into `innerHTML` on the dashboard file pickers (self-XSS, same class as the upload bug). Radar subject/snippet, claim names, message bodies, CRM fields all verified escaped.


### ✅ Urgent fixes batch (founder Sep 4)
- ✅ **Partner document upload/view/delete — the urgent one.** Branches could raise a claim but never attach paperwork afterwards, and could not see what was already on file, so they re-sent duplicates. The branch upload+delete endpoints existed but **no UI ever exposed them**, and **no list endpoint existed at all**. Added `GET /nidaan/branch/api/claims/{id}/documents` and `GET`+`DELETE` for `/nidaan/ops/api/my-claims/{id}/documents` (staff My Business had upload only), each scoped to the caller's own claims. UI went into the **shared** `nidaan_partner_claims.js`, so branch AND My Business both got it in one place: a Documents column opening an inline panel that lists what is attached, uploads more, and removes a wrong one. Each page injects its own multipart uploader (the JSON API helpers would set Content-Type and break the boundary). Subscriber + ops claim panel already had list/upload/delete.
- ✅ **Homepage FAQ never folded.** The language toggle's `body.en .en{display:block!important}` outranked `.faq-a{display:none}`, so every English answer was permanently open (arrow turned, nothing moved); the Hindi answers carried an inline `display:none` no class rule could beat. Scoped the fold rules per language, removed the 10 inline styles.
- ✅ **Privacy + Terms existed only as 404s.** Every Nidaan footer linked `/nidaan/privacy` and `/nidaan/terms`, which did not exist — and `/privacy` serves the **Sarathi-AI** policy, the wrong legal entity for an LLP handling medical records. Wrote NidaanPartner's own Privacy Policy (DPDP-aligned: what we collect, health data, sharing, retention, rights, grievance) and Terms (no guaranteed outcome, fees, refunds, partner duties, liability), host-gated. **Founder should have counsel review the wording.**
- ✅ **Support chats deduplicated.** A signed-in customer who lost their thread key (new device/cleared storage) spawned a second thread, and every WhatsApp handoff opened another — so one person appeared as several conversations. `find_open_support_thread()` reuses the open thread on both paths. **Security:** it returns `thread_key` (the per-thread read secret), so it matches only a **proven** identity — authenticated `account_id`, or a WhatsApp msisdn (Meta verifies possession). A typed-in contact from an anonymous visitor is deliberately never matched, which would otherwise let anyone guessing an email read that person's chat.
- ✅ **Read receipts, both sides.** `read_by_subscriber_at` / `read_by_staff_at` were already recorded and simply never shown. Ops now sees ✓ sent / ✓✓ blue read on our messages (read time on hover); the customer sees the same on theirs.
- ✅ **Unsend.** `DELETE /claims/{id}/messages/{message_id}` + a control on our own bubbles. **Soft** delete — a legal practice must keep the record, so the row is retained (`deleted_at`, `deleted_by_staff_id`) and filtered from the thread. A subscriber's message can never be removed by staff. Audited.
- ✅ **Support read receipts done.** The customer side already had `sub_last_seen_msg_id`; staff had none, so neither party could tell the other had read it. Added `staff_last_seen_msg_id` + `mark_support_read()` / `get_support_read_marks()`; opening a thread advances that side's pointer and both views return the marks, so replies show ✓ sent / ✓✓ read.
- ✅ **Support-chat attachments SHIPPED (authenticated surfaces).** `nidaan_support_messages.attachment_doc_id` reusing the SAME hardened store + signed short-TTL URLs as claim docs. **Customer upload requires a real signed-in account AND thread ownership — deliberately NOT `thread_key` alone**: thread_key is a *read* capability that can be copied from a URL or a shared device, so letting it grant write-to-disk would hand an upload endpoint to anyone who ever saw a link. Caps: 10 MB, MIME allow-list, magic check, 15 files/thread, rate limits (10/min customer, 20/min staff), closed threads refused, staff uploads audited. **Anonymous web-bot upload remains intentionally unbuilt** — revisit only with a deliberate decision on abuse controls.
- 🔴 **SECURITY FIX found while scoping the above — stored XSS in ALL uploads.** Six upload paths validated the magic bytes but took the stored file's **extension from the client filename**. Those are independent, so a PDF/HTML *polyglot* named `x.html` passed validation, was stored as `<uuid>.html`, and was served as text/html **from our own origin** — a staffer opening the “document” would run attacker JS inside their authenticated ops session (token theft; ops holds everything). Fixed with `_doc_ext_for(content)` deriving the extension from the bytes at all 6 sites (verified: polyglot → `.pdf`; HTML/SVG/ELF rejected), plus defence-in-depth on the serving guard: `Content-Disposition: attachment`, `nosniff`, `CSP sandbox; default-src 'none'`. **Live-tested:** unsigned doc URL → 403; well-formed upload with no token → 401; forged bearer → 401; zero `.html/.svg/.exe` in the store.


### ✅ App Health rebuilt + full security audit (founder Sep 4)
**App Health** had not been revisited since WhatsApp Cloud API, Email Radar, Doc Splitter, CRM and the party-notification rails were added — it still reported only the decommissioned Evolution slots. Now also checks: **WhatsApp Cloud API** (status/platform_type, so an unregistered number silently failing every send with `133010` is visible), **WA journey** master switch + templates wired, **Email Radar** inbox connectivity, **Gemini** (radar triage / WA brain / doc splitter all depend on it), **Doc Splitter** job-dir writability, **SMTP**, **subscription renewals past period end** (renewal webhook not landing), **contact reachability** (branches with no WhatsApp, claims with no phone), **backup freshness**. Added a failing-subsystem banner + self-serve actions: **poll radar, test mailboxes, payment re-scan, toggle WA journey**. Verified live — all green (WA CONNECTED/CLOUD_API/GREEN, 6/6 templates, 2 inboxes ok, Gemini ok, SMTP ok, backup 8h old).
Two bugs found while writing the checks: `number_health()` never requested the `status` field (CONNECTED vs PENDING was invisible — the exact thing that hid the dead number for days), and the backup check globbed `*.db` when backups are `.tar.gz`.

**Security audit — findings:**
- ✅ **Authorization: clean.** All **241** `/nidaan/ops/api` routes enforce auth. The 14 without a literal `_require_staff` use `_staff_claim_code` (which calls it) or the stricter `_require_owner` (super_admin + owner-email). No gap.
- ✅ **SQL injection: clean.** Every f-string SQL interpolation is a hardcoded/whitelisted table or field name; all values parameterized (CSV export uses an explicit table whitelist, CRM/task updates whitelist field names).
- ✅ **Secret leakage: clean.** `list_mailboxes` excludes the password; no endpoint returns `enc_password`/`password_hash`. App-password vault is Fernet-encrypted.
- ✅ **CSP already strong** — set by **nginx** (default-src self, pinned hosts, form-action self, object-src none, base-uri self, frame-ancestors self, upgrade-insecure-requests). An app-level duplicate was added then **removed** (two CSP headers make browsers enforce the intersection — confusing to debug). Single header verified live.
- ✅ **Fixed: missing rate limits** — change-password 10/h, staff reset-password 10/h, manual refund 10/min. Ops login was already 5/min; portfolio token already limited.
- 🟢 **Next security pass:** proactive alerting (a worker loop that runs these checks and alerts super-admins on Telegram when one fails — currently the panel is reactive/pull-only), and an XSS sweep of `innerHTML` sites in the ops page.


### 🟡 In progress — CLAIM ARCHITECTURE & DATA CLARITY (build carefully, no breakage)
- ✅ Fixes: All Claims search lag (client-side), Staff filter populated, L2 Paid/Due filter, **All Claims stuck-loading** (staff-filter await was blocking the fetch → non-blocking). Sidebar grouped into labeled zones (Accounts in Work). Official Numbers archived (unused ~52d). Save-number banner → Meta-WABA informational message.
- **TERMINOLOGY (founder Sep 2):** **Insured** = the PATIENT (treatment/policy). **Complainant** = the person PRESENTING the case + providing documents + our comms point (self/family/subscriber/branch/staff). "Claimant" → "complainant" everywhere going forward.
- ✅ **Phase 1 schema shipped** — `complainant_name/phone/email/role` on nidaan_claims + idempotent backfill (complainant := insured for existing 71 claims). Safe/additive.
- **Claim raise forms — Complainant/Insured (in progress, endpoint-by-endpoint):**
  - ✅ **Form #1 branch raise SHIPPED + verified** — Complainant block (name, mobile*, email* + "why") + "Insured is different?" toggle; `submit_claim` stores `complainant_*`; ops my-claims falls back cleanly.
  - NEXT: #2 subscriber (dashboard+start), #3 ops my-claims form UI, #4 ₹499 review + review-request. Then: **comms use complainant contact** (doc-collect/orchestrator/notifications prefer complainant_phone/email); ops claim drawer shows Complainant + Insured; escalation routing (complainant silent → referrer subscriber/branch/staff → ops, all channels).
- **Comms routing map:** define which message goes to whom at each stage; if the **claimant doesn't respond → escalate to whoever referred them** (subscriber/branch/staff/My-Business) explaining why + what's needed; send across all channels.
- ✅ **Claim pipeline SHIPPED (one workspace, stage columns + origin filter)** — new "🗂️ Claim Pipeline" panel (Work zone, first claim item). Reuses the SAME `/claims` endpoint + `_uPay` + `openClaimDrawer`, so a claim reads identically everywhere. `_pipeStage(c)` derives ONE canonical stage from `payment_status`+`status`+`review_outcome`+L2 coverage: Leads → New → Assigned → In Review → L2 fee-due → L2 active → **[Drafting / Escalation reserved post-L2]** → Resolved (+ No-scope lane). Origin chips (subscriber/branch/staff/₹499/direct) + search. Built THROUGH L2; post-L2 columns reserved (no "Lokpal"/"IRDA" labels per policy). OLD Dashboard/All Claims/L2 views kept for now (additive/no-break) — retire once validated.
- **Accounts stays separate** (people directory) but keep the **plan/paid/capping double-check** visible.
- Awaiting: founder's **document list per claim type** → load into checklist templates for the WhatsApp bot.
- ✅ Authorization notifications no longer say ClaimShield/L2/release → "taking the claim forward for further processing"; claimant gets a thank-you (email + WA) on acceptance.
- ✅ **Forwarding codes solved (Sep 4).** Google/Yahoo send the forwarding verification to the **destination** address — i.e. to `cs@`/`np@` (us), NOT the customer — so **no extra passwords are needed anywhere**; both inboxes are already connected (`last_sync_status=ok`). New **📮 Forwarding codes** filter in the Radar surfaces those verification emails with the code parsed out (big + copyable) so staff read it back to the customer or click the confirm link. SOP block is now **open by default + highlighted** instead of collapsing once a mailbox exists.
- ✅ **Per-role dashboard links in every party notification** (`dashboard_link`): complainant → magic link straight into their claim (upload there), subscriber → dashboard (bulk upload across cases), branch → branch dashboard, staff → My Business. Staff on a My-Business-sourced claim already receive the same fan-out as a branch.
- ✅ **Email attachments → claim SHIPPED (human-confirmed, never auto-guessed).** Opening a radar email now lists its attachments, **suggests** the claim (explicit `NP-####`/`#nn` reference, else a sender address matching a claim's own contacts — and the claim must actually exist), and files only after an explicit confirm. Each file is normalised to PDF, saved as a claim document (`source='email'`) and recorded on the claim timeline. Caps: 10 files, 25 MB each; inline/calendar/signature parts skipped. **Deliberately NOT automatic** — an attachment on the wrong claim is a privacy + data-integrity bug. Verified: NP-0093→93, #84→84, NP-16 in body→16, no-reference→no match, non-existent NP-999999→no match. (WhatsApp documents were already fully auto-filed with the Gemini right-doc/quality gate.)
- ✅ **Email radar — switched to the TWO-INBOX FORWARDING model (founder Sep 4).** The Mailboxes tab still taught the OLD per-customer model (one Gmail + app password per case). Now: exactly **two collection inboxes** — `cs@nidaanpartner.com` (old / ClaimShield.in cases) and `np@nidaanpartner.com` (all NEW cases) — that customers **forward** their claim mail into. Tab rewritten with the full story (the idea, what goes where, Step A connect-an-inbox via app password, Step B set forwarding on the customer's Gmail/Yahoo), two preset Connect cards with live connected state, relabelled form + table. Read-only and no-backlog guarantees stated in-product. **OWNER:** connect both inboxes with their app passwords.
- **Email radar — ALREADY BUILT & LIVE (verified Sep 3); reconciled to read-only.** `biz_nidaan_radar.py` + worker `radar_poll_loop` (every 15 min) + panel "📨 Email Updates". Read-only IMAP (`BODY.PEEK`, `readonly=True`), encrypted app-password mailboxes (connect your 2 IDs in the **Mailboxes** tab; forwarding-only also supported), `biz_ai.radar_triage_email` → 🔴/🟡 authority/urgent flags + auto-Task per case + silence 'Chase' sweep + metrics. **No IRDA/Lokpal names in UI.** ✅ **Reply-as-customer (Phase C) HIDDEN** per founder read-only intent — endpoint returns 403, reply UI removed (send code retained, easy re-enable). **OWNER ACTION:** connect the 2 app-password mailboxes.

### 🟢 Doc Splitter & Collator (ops-only tool — all 3 phased; AI cost logged, not billed)
- ✅ **Phase (a) Collator SHIPPED** — `GET /nidaan/ops/api/docsplit/{job}/pdf` returns the merged batch as ONE clean PDF (zero-AI, deterministic). UI "⬇ Merge → one PDF" button; tool retitled "Splitter & Collator".
- ✅ **Phase (b) Splitter accuracy SHIPPED** — `segment` rewritten to **page-level classification** (label each page + `new_doc` flag → fold into contiguous docs), far better boundaries on stacked/interleaved docs; same single Gemini call (no extra cost). **AI cost logged** to `ai_usage_log` (feature `nidaan_docsplit`, source `nidaan_ops`) via `usage_metadata`.
- ✅ **Phase (c) Prompt-library SHIPPED** — `AI_TASKS` in the splitter (summarise / bill-extract / doc-inventory / missing-docs / chronology); `GET /docsplit/tasks` + `POST /docsplit/{job}/ai-task`. UI: "🤖 AI tasks on this file" cards after upload → AI reads the file & returns text (copy-result + copy-prompt affordances). Cost logged to `ai_usage_log`.


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
  - **Journey notifier ✅ BUILT** — `wa_journey(claim_id, event)` in the orchestrator composes the bilingual message for the COMPLAINANT (complainant_phone, fallback insured), sends free-form in-session / template-gated when cold, and records to the claim timeline. **Wired: `claim_registered`** fires on every claim raise (branch/ops via `on_ops_claim_raised`, subscriber via `on_claim_filed`) → welcome + claim-registered to the complainant.
  - **Templates SUBMITTED to Meta (owner, Sep 3 via Claude extension) + code WIRED LIVE.** `JOURNEY_TEMPLATES` now filled (np_welcome/np_intro_value/np_claim_registered/np_payment_thanks/np_payment_failed/np_doc_reminder); `wa_journey` builds the correct per-event `{{1}}..{{3}}` params + picks the Meta language (hinglish→hi Devanagari). **Master switch `wa_journey_enabled` (default ON)** in the WA panel — pauses ALL automatic customer messages instantly. Deviations noted by owner: Meta reclassified np_welcome Utility→Marketing (harmless to code); np_intro_value + np_payment_failed needed a "Hi {{1}}," prefix (still 1 var — params unaffected). **Watch:** a few variants were still "In review" (np_payment_thanks EN, np_doc_reminder) — cold sends for those fail gracefully until approved; HI variants generally approved. **Owner to reconfirm:** final approval status of the in-review ones + that np_welcome (HI) content wasn't accidentally edited.
  - **Payment-event → complainant WA ✅ WIRED (de-duped + consent-safe).** `wa_journey` now takes `skip_phones` (won't double-message a number the subscriber dispatch already owns) + skips contacts who replied STOP (`nidaan_wa_contacts.status='stopped'`). Wired: **success** → `on_branch_l2_paid` (branch/ops L2, customer≠subscriber) + `on_funnel_paid` (guarded, self-service skips); **failure** → payment.failed webhook resolves `claim_id` from Razorpay notes → `payment_failed` reassurance ("no money deducted").
  - **Campaigns + lead-capture ✅ SHIPPED (superadmin).** `biz_nidaan_wa_campaigns.py`: audience = opted-in & non-stopped `nidaan_wa_contacts` (filters: language, has-claim/no-claim); per-recipient send reuses `wa_journey` gate (in-session → free-form composer; cold → approved template; STOP always skipped); `nidaan_wa_campaigns` summary + live stats; runs in background with pacing. UI in 💬 panel: 📣 Bulk campaign (preview count, send-test, launch) + campaigns table. **Lead-capture:** inbound unknown WhatsApp numbers auto-recorded as CRM leads (`source='whatsapp'`, deduped, gated by `wa_lead_capture_enabled`); manual promote via `POST /wa/contacts/{msisdn}/lead`. Bulk cold sends still need approved templates.
  - **Templates handoff ✅** — `docs/nidaan/setup/WA_META_SETUP_PROMPT.md` (paste into Claude extension to set up all 6 on Meta).
  - **REMAINING:** (1) reminder loop (Phase 2, template-gated). (2) escalation routing (complainant silent → referrer subscriber/branch/staff → ops, all channels).
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

### 🔴 INFRA MIGRATION + COST CUT (founder — do ~Sep 3 holiday)
- **Move whole stack (Sarathi + NidaanPartner + GoLuQ) Contabo → Oracle Always-Free**, then separate apps. Apps are tiny (DB 15M, disk 5%, RAM 7% on Contabo) — fits free tier easily. Domains unchanged → WhatsApp + Razorpay webhooks need NO reconfig, only DNS→new IP.
- Plan: (1) cancel unused paid extras first — **Evolution VPS + proxies dead** (on official Meta WA now), marketing-studio big-server on hold → **need founder's list of paid services (Hetzner + what each runs)**; (2) lift-and-shift to Oracle in PARALLEL, copy 15M DB, verify, DNS cutover (near-zero downtime, instant rollback), keep encrypted off-server backups; (3) app separation on Oracle — define level: (a) independent services same box / (b) separate DBs / (c) separate codebases. GoLuQ (`goluq.service` + /opt/goluq) is on Contabo too → moves with it.
- Risks: Oracle Always-Free ARM reclaim-if-idle (mitigate: keep active + backups), TLS + Oracle security-list ports (deploy guide covers). `docs/infra/DEPLOY_ORACLE_CLOUD.md` exists.

- ✅ **SMTP live** (Gmail app-password via `nidaanpartner@gmail.com`; secured in `biz.env`).
- Staging env (port 8003, `staging` branch): awaiting DNS + TLS.
- Off-server encrypted backups: live.
