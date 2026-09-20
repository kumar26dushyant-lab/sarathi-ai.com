# SARATHI BUSINESS — LIVING TO-DO

_Auto-maintained by Claude **every conversation**, alongside `PROJECT_MASTER_CONTEXT.md`._
_**Two-terminal workflow:** work 🟦 NidaanPartner items in one VS Code terminal, 🟩 Sarathi items in another. Each app's section is self-contained so both can progress simultaneously without collision._
_Legend: 🔴 blocked/awaiting owner · 🟡 in progress · 🟢 next/planned · ✅ done_

**Last updated:** 2026-09-19 (money removed from every message that reaches an outside party; alarms split into incidents that page and gaps that do not; a 15-journey / 96-step safety net now runs against a copy of the live DB before anything ships)

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
**`BREVO_DNS_SETUP_PROMPT.md`** — paste-ready for the Claude extension. Authenticates `nidaanpartner.com` in Brevo + Cloudflare (domain add, DKIM records, **SPF edited not duplicated**, verify, validate `info@` sender, report credits). Verification codes already work meanwhile via the Google transport.


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
  - **Templates handoff ✅** — `WA_META_SETUP_PROMPT.md` (paste into Claude extension to set up all 6 on Meta).
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
- Risks: Oracle Always-Free ARM reclaim-if-idle (mitigate: keep active + backups), TLS + Oracle security-list ports (deploy guide covers). `DEPLOY_ORACLE_CLOUD.md` exists.

- ✅ **SMTP live** (Gmail app-password via `nidaanpartner@gmail.com`; secured in `biz.env`).
- Staging env (port 8003, `staging` branch): awaiting DNS + TLS.
- Off-server encrypted backups: live.
