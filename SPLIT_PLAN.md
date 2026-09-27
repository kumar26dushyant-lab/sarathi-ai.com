# Separating NidaanPartner from Sarathi

**Written for:** the founder, and whoever reviews this before stage 2.
**Revised:** 27 September 2026, after he said the thing that changes everything.

> *"I am not worried about sarathi-ai.com if anything breaks... but nidaanpartner.com is
> critical."*

That single sentence inverts the plan, and makes it far safer.

---

## The inversion

My first draft moved **Nidaan out** and left Sarathi in place. That was wrong, and I had it
backwards for a reason worth stating: I assumed the thing being separated is the thing that
moves. It is not. **The thing that moves is the thing you can afford to break.**

So:

### NidaanPartner does not move. Sarathi is extracted from around it.

| | NidaanPartner (critical) | Sarathi (no active users) |
|---|---|---|
| Folder | **stays** | moves out |
| Database | **stays** `sarathi_biz.db` | new `sarathi.db` |
| 1.5 GB of claim documents | **never moves** | n/a |
| systemd units, ports | **unchanged** | new units |
| nginx routing | **untouched** | repointed |
| 461 routes | **stay exactly where they are** | 357 move |
| Deploy | **the same one that works today** | new one |

Every risky operation now happens to the app you said you can afford to break. The live,
paying, medically-sensitive one is left alone — and at the end it is alone, in a folder
containing only itself, which is what you asked for.

The end state is identical. The route there is not.

**The one cosmetic consequence:** the folder is currently named `sarathi-business` and the
server path is `/opt/sarathi`. Renaming those is the *last* step, after everything works, and it
is the only step that touches Nidaan at all.

---

## The mechanics you asked for — "identify and fix it later"

Three nets, in order of how much they catch.

### 1. The route census — **built and proven today**

`deploy/route-census.py` has recorded all **854** routes (461 Nidaan · 357 Sarathi · 36 shared),
each with the file, the function, and **what it demands of a caller** — host gate, staff role,
rate limit.

After every stage it compares. **Missing is failure. A changed gate is failure.** New is fine.

Proven by hiding one route and running it:

```
!! 1 ROUTE(S) NO LONGER EXIST - this is the failure that hides:
   GET /nidaan/ops/api/telegram/pending-count   was nidaan-host,staff:super_admin
```

This is the net that matters, because a route that vanishes **does not error**. It is simply
gone, and you find out weeks later when somebody says "the button does nothing".

### 2. Nidaan never stops serving

Because Nidaan does not move, there is no cutover for it — no window where it is down, no
moment where traffic is switched to something new. Sarathi is the one being lifted out, and if
Sarathi is down for an hour, nobody notices.

### 3. Reverting is one command, at every stage

Nothing is deleted. The old units, the old rows and the old paths stay until their replacement
has been running for a week and you say otherwise.

---

## The stages

Each is independently shippable. **If we stop after any of them, what is live still works.**

| Stage | What happens | Touches Nidaan? | Revert |
|---|---|---|---|
| **0** ✅ | Route census recorded. Restore-test the backup. | no | n/a |
| **1** | Split `biz.env` into shared / nidaan / sarathi — same values, three files | config only | restore one file |
| **2** | Move the **357 Sarathi routes** out of `sarathi_biz.py` into `sarathi_app.py`, still one process | **no** | git revert |
| **3** | Sarathi gets its **own process, port and deploy unit**; nginx points sarathi-ai.com at it | **no** | repoint nginx |
| **4** | Sarathi's bots and schedulers move to their own worker | **no** | re-enable |
| **5** | **Sarathi's tables copy out** to `sarathi.db`; `product_link` becomes a small authenticated API | reads only | old tables stay |
| **6** | What remains is Nidaan-only. Delete nothing — archive the Sarathi files out of the folder | files only | git |
| **7** | Rename folder and `/opt` path; update the deploy unit | **yes — the only stage that does** | rename back |

Stage 7 is the only one that touches the live app, it is last, it is a rename, and by then
everything else is proven.

---

## What is genuinely risky, honestly

**R1 — a route quietly disappearing.** Covered by the census, which is why it was built first.
Residual risk: low, and *detectable in minutes* rather than weeks.

**R2 — two apps, one database, for the duration of stages 3–5.** SQLite in WAL handles it, but
a second writer raises the chance of a busy timeout, and payments are written under load. This
is the reason to keep stages 3 and 5 in the same week rather than "eventually".

**R3 — the shared `JWT_SECRET`.** Splitting it naively logs everyone out of both products at
once. It is split with both secrets accepted for a grace period, then the old one retired.

**R4 — the 36 "shared" routes.** `/privacy`, `/terms`, `/login`, service-worker and manifest
files. Each needs a decision, not a rule. This is the fiddly part and it is where I will come
back to you with a list rather than guess.

**R5 — a shared function neither product owns.** 66 modules are named for neither product.
Stage 2 will find the ones both import. Each becomes: copied to both (if small and stable), or
kept as a shared library both install (if it is real infrastructure like AV scanning).

---

## What I need from you before stage 1

1. **Nothing, for stage 1.** Splitting the env file is reversible in one command and touches no
   behaviour. I can do it and prove it with the census.
2. **Before stage 3** — a 30-minute window where Sarathi may be down. Nidaan will not be.
3. **Before stage 5** — confirmation that `product_link` (your bundle login) is the *only* thing
   that must keep working across the two. If there is anything else, it is much cheaper to know
   now than to find out.

**My recommendation: stages 0 and 1 now, then stage 2 in one sitting with the census run after
every file moved.** Stage 2 is the long one — 357 routes — and it is where care pays. Nidaan is
not touched by any of it.
