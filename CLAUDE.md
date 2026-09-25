# Working rules for NidaanPartner.com and Sarathi-AI.com

These are the founder's own standing rules, in his words where it matters. They sit in the repo
so they survive any session, any assistant, any machine. They are **in addition to** the global
rules in `~/.claude/CLAUDE.md`, and where they overlap, these are the stricter ones.

This is a **live** insurance-claim ERP. Real claims, real staff, real money, real medical
documents belonging to real people. Nothing here is a sandbox.

---

## 1. Never delete data without asking

> *"you'll not delete any data without my permission, make it global rule."* — 25 Sep 2026

- No `DELETE`, `DROP`, `TRUNCATE`, `rm -rf`, or a blanking `UPDATE` against the live database or
  the server without asking first and getting a yes.
- **Prefer archive / soft-delete / mark-inactive**, in new features too. `archived=1` and
  `deleted_at` already exist and are the pattern.
- A migration that drops or rewrites a column **is** a deletion. Ask.
- Scratch files in `/tmp` or a scratchpad are yours to clean up. Anything under `/opt/sarathi`,
  the database, or tracked repo files is not.
- If a fix appears to need data removed: say so, show exactly which rows, and wait.

## 2. Every change strengthens the foundation

> *"solutions should be scalable not temporary"* · *"make foundation strong for app to work
> flawlessly without bugs, without data loss, without security issues."*

Habits that have caught real faults in this codebase:

- **Fix the cause, in one place.** Two copies of a rule is how the notify panel came to show
  green ticks that meant nothing, and how the bucket chips came to renumber themselves.
- **A check must read an OUTCOME, not a configuration.** "The key is set" is not "email arrives".
  "WhatsApp: CONNECTED" was green for days while nobody was being answered.
- **Prove a test can fail before trusting it.** Several here have passed on an empty string.
- **Look for the sibling.** A change to a shared concept applies at *every* endpoint that does it.
- **Check the fresh-install path.** Six columns were added by `ALTER` before their table was
  created — production was fine and only a restore would have broken.
- **Say what is unproven.** Reading the code is not evidence that a message arrived.

## 3. Tight security against external attack

> *"we cannot compromise on cybersecurity, it's trust factor"* · *"if anyone wants to enter
> intentionally surface the fact and take actions and update superadmins"*

- **Every new endpoint is hostile until proven otherwise:** auth on the route, authorisation on
  the record id, validation at the boundary, a rate limit if it is public. Never `extra="allow"`.
- **Fail closed.** A missing token, an unexpected branch or an error ends in *denied*. A webhook
  here returned `True` when no token was configured and accepted unauthenticated writes on both
  domains for months — that is the shape to hunt for.
- **Never log a credential.** Libraries put the secret in their own error text; `_scrub_secrets()`
  redacts by shape. A token that reached the journal is burnt — say so and get it rotated.
- **Never weaken the edge to fix a delivery problem.** No unproxied hostname (it exposes the
  origin and undoes `deploy/lock-origin-to-cloudflare.sh`); never disable signature verification.
- **Check the whole surface, not the one reported.** A hole found on one host: test the other
  product and the sibling routes.
- **Surface the attempt.** A blocked intrusion nobody hears about teaches us nothing.

## 4. Deploying

- **No live deploys while the IST team is working.** Build, test, commit — deploy after 6pm IST
  or when he says go.
- Verify from **outside**, and verify the OUTCOME: both sites answering, the new code actually
  served, no tracebacks, the specific thing fixed behaving on real data.
- `git push` → `sudo systemctl start sarathi-deploy.service` on `161.118.186.201`.

## 5. The rest, briefly

- **Mobile first.** Every change works at phone width.
- **Both themes.** Every badge and colour readable in dark *and* light. Theme variables, never
  literals.
- **Both languages.** User-facing copy in English and Hindi, plain enough for a Tier II/III
  reader. Words over ambiguous icons.
- **Confirm before anything destructive**, in the UI as well as in code.
- **Keep `TODO.md` and `PROJECT_MASTER_CONTEXT.md` current** as work happens, and draft bilingual
  staff announcements in `ANNOUNCEMENTS.md` for him to send — never send them automatically.
- **Tests never reach real people.** `NIDAAN_NO_OUTBOUND=1` on any run against a copy of live
  data; never in production.

---

## Checks to run before every commit

```
npm run check:all          # page JS (no-undef), python names, notification registry
py -3.13 deploy/verify-ops-buttons.py        # no dead or duplicated handlers
py -3.13 deploy/verify-claim-statuses.py     # one status list, one stylesheet, one version
py -3.13 deploy/verify-notify-routing.py     # who hears what
node uitest/*.js                              # pager, bucket chrome, form layout, pills
py -3.14 _tools/test_*.py                     # the behaviour tests
```

`py -3.13` lacks `aiosqlite`/`httpx`; `py -3.14` has them. Verifiers run on 3.13, the async
behaviour tests on 3.14.
