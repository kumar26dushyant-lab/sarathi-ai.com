# NidaanPartner.com — the project brief

**Read this first, every session.** It is the standing context for NidaanPartner: what it is,
how it is built, the rules it is built under, where the work has got to and what comes next.

> Sarathi-AI.com is a **separate product** with its own brief in `CLAUDE.sarathi.md`. The two
> shared one codebase until 27 September 2026. They no longer do. Do not mix them.

---

## What this is

A **live** insurance-claim legal ERP for **Nidaan Legal India LLP** (Indore). Real claims, real
staff, real money, real medical documents belonging to real people. Nothing here is a sandbox.

Claimants are mostly **not our customers** — they are the insured person on a claim a branch or
a subscriber brought to us. They never signed up with us, and they hold the most sensitive data
in the system with the fewest routes back to us.

**Registered entity:** Nidaan Legal India LLP · 79/A Ranjeet Hanuman Road, Dravid Nagar Colony,
Scheme 71, Indore, MP 452009 · enquiries@nidaanlegalindia.com · +91 95844 68804 · courts at
Indore. NidaanPartner.com is its **technology operations wing**, built by GoLuQ.com Digital
Consultancy.

---

## The founder's rules — these win over speed, always

1. **Never delete data without asking.** Archive, soft-delete, mark inactive. `archived=1` and
   `deleted_at` exist and are the pattern. A migration that drops a column *is* a deletion.
2. **Every change strengthens the foundation.** Scalable, not temporary. Fix the cause in one
   place. Look for the sibling — a change to a shared concept applies at *every* endpoint that
   does it.
3. **A check must read an OUTCOME, not a configuration.** "The key is set" is not "email
   arrives". This has cost two outages.
4. **Tight security against external attack.** Every new endpoint hostile until proven: auth on
   the route, authorisation on the record id, validation at the boundary, a rate limit if public.
   Fail closed. Never log a credential.
5. **No live deploys while the IST team is working.** Build, test, commit — deploy after 6pm IST
   or when he says go.
6. **Mobile first. Both themes. Three languages** (English, Hindi, Hinglish — total conversion,
   no leftover strings). **Confirm before anything destructive.**
7. **Tests never reach real people** — `NIDAAN_NO_OUTBOUND=1` on any run against live data.
8. **Say what is unproven.** Reading the code is not evidence that a message arrived.

---

## How it runs, today

| | |
|---|---|
| Host | Oracle Mumbai `161.118.186.201`, `ssh -i ~/.ssh/id_nidaan_oracle ubuntu@…` |
| App | `nidaan_app.py` — **its own file since 27 Sep 2026** |
| Web | `nidaan-web@1` / `@2`, ports **8031/8032** |
| Worker | still the shared `sarathi-worker` — **the last thing not yet split** |
| Database | `/opt/sarathi/sarathi_biz.db` (SQLite, WAL) |
| Documents | `/opt/sarathi/uploads`, 1.5 GB, served by nginx directly |
| Deploy | `git push` → `sudo systemctl start sarathi-deploy.service` |
| Fallback | 8001/8002 still run the old combined app, warm — revert is one nginx edit |

**Run something with the app's environment without reading secrets:**
```
sudo systemd-run --quiet --wait --pipe --collect --uid=sarathi \
  --property=EnvironmentFile=/opt/sarathi/biz.env \
  --property=WorkingDirectory=/opt/sarathi /opt/sarathi/venv/bin/python <script>
```
**Read the live DB:** `sudo -u sarathi sqlite3 /opt/sarathi/sarathi_biz.db "PRAGMA query_only=1; …"`
(WAL needs write access, so `mode=ro` fails.)

**Local Python:** `py -3.13` for verifiers, `py -3.14` for async tests (it has aiosqlite, httpx).

---

## The product, in the founder's own model

**Part 1 — intake.** Every correct detail, document and authorisation, up to Consolidation.
**Part 2 — the assembly line.** Level-2 → Settlement. Less automation, ask-and-manual-trigger.

### The claim pipeline (buckets)

`live` → `pending_draft` → `pending_docs` → `escalation` → **`lokpal`** → `completed` →
`pending_payment`

Each bucket has **internal statuses**, its own **recorded fields**, and query-raising mechanics.
All of it is defined in one place: `biz_nidaan_buckets.py`.

**Lokpal** (Insurance Ombudsman), completed 27 Sep 2026 against the founder's drawing:
- statuses: pending → registered → ann5_pending → ann5_replied → ann6_pending → ann6_replied →
  **hearing OR consent** (alternatives, never both required) → **award**
- fields: BHP number *(keeps that name — staff know it; the bracket explains it)*, registration
  date, Annexure 5/6 number + received + replied, hearing date, consent date, **award number,
  date and amount**, dispatch POD
- the award amount is recorded separately from the settlement *because they differ* — the gap
  between awarded and received is the thing to chase

### Money

`nidaan_payments` is the ledger: **one idempotent row per payment**, whatever the source.
Revenue reads it. Every new payment path must call `record_payment`.

**Idempotency is on `dedup_key` AND on the event.** A subscription activation arriving by
webhook and by api_fetch once produced two rows under two keys — ₹11,776 of phantom revenue
across 14 subscriptions. A row with no `razorpay_payment_id` is a *placeholder*; the real
payment completes it in place rather than adding a second row.

Nidaan has its **own Razorpay account**: `NIDAAN_RAZORPAY_KEY_ID`, not `RAZORPAY_KEY_ID`.

### Notifications

`biz_nidaan_notify_prefs` resolves who hears what, most specific first:
**claim × user → user → role → policy → on by default.**
Money, security and system health **cannot be switched off**. The dashboard bell is **never**
silenced — turning it off would delete the record of having been told, not stop an interruption.
Authorisation fails **closed**; notification routing fails **open**. Opposite on purpose.

### Two module names that sound alike

    biz_nidaan_claim_access   IS THIS THE COMPLAINANT?  a code to the phone/email on the claim
    biz_nidaan_claim_authz    MAY THIS STAFFER SEE IT?  assigned, mentioned, or an admin

Opposite sides of the same counter. On 26 Sep the second was written over the first, and every
claimant who opened their link was told "this link is invalid or has expired" until 28 Sep.
`npm run check:attrs` now fails on any `module.attribute` a route reaches for that does not
exist - it runs on **3.14**, because on 3.13 most modules will not import and it would pass
without looking.

### Cookies

Consent is REAL, not a notice. `nidaan_ga.js` loads nothing until the visitor allows analytics,
and refusing later deletes the `_ga` cookies. `nidaan_cookies.js` must load BEFORE it on every
page - a gate that loads second is not a gate, and `_tools/test_cookie_consent.py` asserts the
order. The policy at `/nidaan/cookies` lists the cookies this application really sets, read out
of the `set_cookie` calls: naming one we do not use, or missing one we do, is a false statement
to a regulator. Adding any new cookie or tag means updating that page in **both languages**.

### Deploying

`git push` then `sudo systemctl start sarathi-deploy.service`. It rolls `nidaan-web@N`
(8031/8032, nidaanpartner.com) and `sarathi-new-web@N` (8021/8022, sarathi-ai.com) as well as the
old `sarathi-web@N` kept for rollback. Until 28 Sep it rolled only the last of those, so every
deploy after the split pulled the code and loaded none of it. **Verify the outcome on the ports
that serve the domain**, never just that the unit restarted.

### Claim documents

**NO CLAIM DOCUMENT LEAVES THIS SERVER.** Not to Gemini, not to any hosted model, for any purpose -
naming it, summarising it, splitting it or checking its quality. They are people's hospital papers.
Reading happens here: the PDF's own text layer first, then local `tesseract` (`eng+hin`).
`biz_nidaan_doc_brain` is the only door, `biz_nidaan_doc_local` the engine, and
`_tools/test_intake_no_ai.py` reads the source of every module on that path so a future one-line
`import biz_ai` fails a test instead of shipping.

**AND NOTHING IS FILED AUTOMATICALLY on the claimant path.** The local reader agrees with staff
about two times in three - measured on this firm's own 1,242 documents, not guessed. That is a good
*suggestion* where a person presses yes (the Telegram upload still offers one) and a mis-filed claim
on intake, where nobody checks. So `doc_intake.accept()` stores the document, runs a
**readability-only** check, and puts it in a staff queue. A guess that is right two times in three
is worse than no guess: no guess is honest and brings somebody to look.

The one thing a complainant is still told is the one thing only they can fix - nothing on it could
be read, please send a clearer photograph. Everything else is our problem, never theirs.

**Reading is blocking work, so it runs in a worker thread** with a **120s OCR budget per file**
(`NIDAAN_OCR_BUDGET_S`). Past the budget the remaining pages come back honestly marked "not read"
rather than the request timing out. Awaiting it on the loop would freeze every other request on that
worker for minutes - the hazard the local engine introduced, which the network call it replaced
never had (`_tools/test_ocr_budget.py`).

### How documents reach a claim

Four ways, and the counts as of 28 Sep: staff attaching by hand (934), authorization PDFs we
generate (59), the **official WhatsApp number** (20, since 22 Sep), the claimant's own claim page
(25). The WhatsApp path is `biz_nidaan_inbound.py` - matched to the claim by phone number,
attached, claimant told, associate notified.

**A document keeps the name it arrived with.** A claimant's file is often already called
`Insurance_Policy_Schedule.pdf`, which is the best clue anybody gets about what it is. Do not
store a generic name - that was a regression on 28 Sep and it cost real information. Naming by
TYPE happens in the splitter, where a person confirms it.

The staff SOP for all of this is `static/nidaan_sop_documents.html`, served at `/sop-documents`
behind the share key. Keep it true when this changes.

### The email radar

Reads **on this server**: `biz_nidaan_radar_read.py`, a domain list and a phrase list, imports
nothing but `re`. No model - the emails are from statutory bodies about identified claimants.

**The forwarded sender is the real sender.** On a hand-forwarded letter the `From:` header is the
colleague who pressed forward; the authority is inside the body. Both are read, forwarded first.
Judging by the header alone missed exactly the mail the feature exists for.

Authorities are **in the code** (Ombudsman, IRDAI, `gov.in`, statutory phrases - facts about the
regulator). The ops config box is for what changes, and is **additive only**: a rule or listed
sender can set red, never green. Unrecognised is amber; only our own mail and service notices are
cleared.

### The document splitter

Jobs belong to a staff member (`biz_nidaan_doc_store`), three open at a time, and the fourth ASKS
before anything is put away. Every job route resolves through `_docsplit_job` and refuses with
**404, never 403** - a 403 would confirm whose uploads exist. **Nothing deletes**: closing a job
archives it, and the six-hour sweep that used to remove working files is gone.

Pages are classified ONCE at upload and saved beside the working PDF (`pages.json`). Never
re-classify a job that has an answer - it costs ~15s a scanned page AND would silently undo
corrections. A set is composed **by type**, so its pages are scattered: use `extract_pages`, not
`extract`.

Corrections are taught as **readable word rules** somebody can undo, never a score. A rule always
beats the engine's reading. Adding a document type means `DOC_TYPES` and the `SETS` orders in
`biz_nidaan_doc_sets`.

**The claim-level sets** (`biz_nidaan_claim_sets`, the "Ready to send" box) use the same engine.
Each DOCUMENT is identified once - **its file name first** (`type_from_filename`: a name a person
gave it is the best clue, and a camera name like `IMG-2026...` is ignored), then its first readable
pages - and every page takes that answer. Reading all 134 pages of a claim page by page took
minutes and was worse. `final_pages()` is the ONE place the reading meets what people decided
(type corrections and **"Don't send"** exclusions); the screen and `build_set_pdf()` both use it,
and the PDF is built by (document, page inside it), never by merged page number. The reading is
cached under a key that includes **`READER_VERSION` and the active rule ids** - bump the version
when identification changes, or claims keep yesterday's answer. Measured 29 Sep on claims
204/39/151: 35/39, 14/28 and 12/25 documents recognised; what is left is camera photos,
`Document_1.pdf` and hospital case papers, which go to a person on purpose.

Each set downloads as ONE PDF or as **one PDF per document type** in a zip (`build_set_parts`:
01 Claim form, 02 Discharge summary DS, ...) - the founder's "bundle of each document". Both use
`_render`, which runs in a worker thread. **DC is a discharge card and is filed as the Discharge
summary (DS)** - founder, 29 Sep; the type label carries "(DS)".

### The complainant's WhatsApp - reminders and the 24-hour rule

Inside 24 hours of the complainant's last message we may send free text; outside it, only an
approved template. `np_doc_reminder` is approved and delivers. A **scheduled reminder**
(`biz_nidaan_wa_schedule`) counts as sent only when the complainant was **reached** -
`doc_request.send()` says ok when it merely recorded the ask - and falls back to the template when
the window is closed. The person who set it is told what happened (`doc.schedule_due`, bell +
Telegram), with "please call" and the number when it did not land. Meta's failed receipts keep
their reason (`wa_flow.failure_reason`: 131047 = the 24-hour rule, 131026 = not on WhatsApp).

**"Follow-up so far"** (`doc_request.followup`, served in the doc window) is what the next
person reads before chasing: every ask, booked reminder, call and automatic-reminder switch on the
claim, newest first, and ONE "Next:" line computed from the same state the workers use.
Automatic reminders are OFF globally unless `wa_doc_collection_enabled` is set - it says so,
because staff waiting on a reminder that will never go is the failure it exists to prevent.

**The complainant can pick the time** (`biz_nidaan_wa_remind`, setting `wa_remind_ask_enabled`,
**off** until a super-admin turns it on). Local rules read the reply; nothing is booked without
their yes; STOP and unrelated questions are never caught.

**Wording:** "fast-tracked in our internal process" - the founder's framing. Never "same day",
never a promise about the insurer. One copy (`wa_messages.FAST_TRACK`) used by the bot and by the
staff ask, which is written in the reader's language (`doc_request._DRAFT`).

### The bot

**@NidaanPartnerOpsBot** (`biz_nidaan_telegram.py`, long-polling). Tasks, claims, notes, stage
changes, approvals, leave, AI, broadcast, voice notes, **document upload** and a **PDF splitter**.
150 strings × 3 languages. Rate-limited by `biz_nidaan_bot_guard`; claim access by
`biz_nidaan_claim_access` (fails closed; "not yours" and "no such claim" read identically, or the
bot becomes a way to enumerate claim numbers).

---

## Scars worth remembering

- **Silent success.** Providers returning 201 and delivering nothing. Check outcomes and leading
  indicators, never configuration.
- **A route that disappears does not error.** It is simply gone. `deploy/route-census.py` exists
  because of this — and it has a known blind spot: routes registered in a *loop* are invisible to
  it, so check the **running app's** route table, not the source.
- **A dead button is usually a name that is not there.** `npm run check:pages`, then
  `verify-ops-buttons.py`.
- **A bot token was handed to every staff browser** — `/ops-settings` returned the whole settings
  table and the ops page fetched it to read one value. Credentials are now filtered in the
  accessor, not in the endpoints.
- **The ops Telegram bot was owned by a staff member's personal account** and vanished when that
  account did. BotFather ownership cannot be transferred. Company-owned accounts only.
- **Git Bash heredocs mangle backslashes, and backticks get executed.** Patch scripts go through
  a file written by the editor. This has bitten six times - the sixth wrote `'Don't send'` into
  the ops page, which would have stopped its whole script.
- **The page linter skipped a broken ops page as a "template".** A block that MENTIONS `{{1}}` and
  failed to compile was skipped with "0 problems". Fixed 29 Sep: skipped only if it compiles once
  placeholders are filled. Prove a check can fail before trusting it.
- **Hindi text in these files mixes two encodings of ज़/फ़/ड़** (one character vs letter + dot).
  They look identical and do not match byte for byte - an exact-match patch anchor fails.

---

## Checks before every commit

```
npm run check:all                              # page JS, python names, notifications, routes
py -3.13 deploy/verify-ops-buttons.py          # no dead or duplicated handlers
py -3.13 deploy/verify-claim-statuses.py       # one status list, one stylesheet
py -3.13 deploy/verify-notify-routing.py       # who hears what
py -3.14 _tools/test_*.py                      # behaviour
```

---

## Where the work is

**Done and live:** notification controller · Telegram document upload + splitter + Hinglish ·
claim authorisation · bot rate limits + audit · payment idempotency (₹11,776 corrected) · DPDP
legal pages with the right entity · Grievance Officer editable from ops · Lokpal bucket completed.

**Done, awaiting deploy:** documents read on our own server, nothing filed automatically (see
**Claim documents** above). The staff-facing half - the set-builder inbox, the review screen and the
screen where a correction becomes a rule - is **still to build**; `biz_nidaan_doc_sets` has the sets
and the rule matching, and `biz_doc_splitter._learned_rules()` is the single seam where stored rules
will arrive.

**Still sends data out, and it is the founder's call:** the bot's 🤖 Ask AI reads task
records to Gemini - titles, staff names and up to 220 characters of a description, which here
routinely name a claimant. No documents. Raised 28 Sep, undecided.

**In flight — the split (`SPLIT_PLAN.md`):** stages 0–5 done. Both products run on their own
apps. **Stage 6, the worker, is mapped but not executed** — `main()` launches 26 loops and both
app files still contain all of them, so starting two workers would double-run 19 Nidaan loops.
`deploy/loop-ownership.json` has the ownership. Then stage 7 (databases — `leads` and
`system_flags` get copied to Nidaan) and stage 8 (folders and repos).

**Next, agreed with the founder:**
1. Finish the split — worker, then databases, then the folder move.
2. **Buckets end to end** through to settlement, the same treatment Lokpal just had.
3. **`/superadmin` ops is messy** — align it, merge or drop features, make it feel like a modern
   app.
4. **A team of monitoring bots** watching each department — logins, payments, the L2 queue —
   alerting only when a person is actually needed.
5. **DPDP**, from `COMPLIANCE_DPDP.md`: retention (nothing is ever deleted today), the Gemini
   transfer is undisclosed, 47 portal links with no consent record, claimants have no route to
   request anything, no breach procedure, no cookie policy.

**Living documents:** `TODO.md` (per-conversation), `PROJECT_MASTER_CONTEXT.md` (the long
history), `SPLIT_PLAN.md`, `SPLIT_DECISIONS.md`, `COMPLIANCE_DPDP.md`, `ANNOUNCEMENTS.md`
(bilingual staff drafts — the founder sends them, never automatically).
