# Separating NidaanPartner from Sarathi — risk first, then the route

**Written for:** the founder, deciding whether and how to proceed.
**Date:** 27 September 2026.
**Goal he set:** *"genuinely two apps, two deploys, eventually two databases"* — and
*"without disturbing a single even small function"*.

Nothing here has been done. This is the assessment he asked for before anything moves.

---

## The honest headline

**This is more separable than it looks, and the danger is not where you would expect.**

Measured, not guessed:

| | |
|---|---|
| Routes in `sarathi_biz.py` | **854** — 460 `/nidaan/*`, 357 `/api/*` (Sarathi), 37 shared |
| `nidaan_*` tables | 45 |
| **Foreign keys crossing the products** | **one** — `product_link.sarathi_tenant_id → tenants` |
| Nidaan modules importing Sarathi code | **4**, one of which is the deliberate bridge |
| Live database | 23 MB |
| Uploaded documents | **1.5 GB** |
| Processes serving both today | `sarathi-web@1`, `sarathi-web@2`, `sarathi-worker` |

The two products were built with a boundary in mind, and it largely held. The path prefixes
are clean. The tables are clean. **The data is already separable.**

**The risk is concentrated in one file:** `sarathi_biz.py`, 30,029 lines, holding both products'
routes and 465 `_is_nidaan_host()` decisions. That file is the entanglement.

---

## The risks, worst first

### 🔴 R1 — A route that silently stops existing

854 routes. If the split misses one, nothing errors at deploy: the route is simply gone, and you
find out when a staff member says "the button does nothing" — possibly weeks later, possibly on
a payment path.

*This is the one that actually bites.* It is invisible to tests that only check what exists.

**Mitigation:** capture all 854 route signatures **before** anything moves, and assert after each
step that every Nidaan route still answers and still returns the same shape. A route census, run
as a check, not as a memory.

### 🔴 R2 — Two apps writing one database

Until the databases split, both apps write `sarathi_biz.db`. SQLite in WAL mode handles multiple
writers, but a second process doubles the chance of a busy timeout under load — and payments are
written under load, by definition.

**Mitigation:** do not run two apps against one database for longer than one deploy window, and
keep the database split immediately after the app split rather than "eventually". The gap is the
risk, not either end of it.

### 🟠 R3 — 1.5 GB of documents

Claim documents are 1.5 GB on disk and nginx serves `/uploads` directly, bypassing the app. Move
them wrong and every claim document 404s, or worse, becomes readable at a guessable path.

**Mitigation:** the documents move **last**, after both apps are running, by copy-then-verify-
then-switch — never move-then-hope. Old path stays readable until the new one is proven.

### 🟠 R4 — The bundle login

`product_link` maps a Nidaan account to a Sarathi tenant. It is the one thing that genuinely
must keep working across the boundary, and it is the thing he explicitly wants to preserve.

**Mitigation:** it becomes a small authenticated API between the two apps rather than a shared
table read. That is more work than a join, and it is the correct answer — it is the only piece
that should survive as a dependency.

### 🟠 R5 — One `biz.env`, shared secrets

Both products read one environment file. Razorpay keys are already separate
(`NIDAAN_RAZORPAY_*`), but `JWT_SECRET` is shared, so a session minted by one app is currently
valid in the other.

**Mitigation:** split the env first — it is cheap, reversible, and it makes every later step
honest. **The JWT secret must be split carefully**: doing it naively logs every user out of both
products at once.

### 🟡 R6 — Deploy, backup and monitoring all assume one app

`sarathi-deploy.service`, the encrypted off-site backup, the payment guardian, the health
monitor and the notification routing all currently assume one application. Each needs a second
instance, and a half-migrated monitor is a monitor that watches nothing while reporting green —
the exact failure this project has paid for twice.

**Mitigation:** the monitoring moves with each app, and the first check after every stage is
"does the guardian still see this product".

### 🟡 R7 — Working on a moving target

Lokpal, the superadmin overhaul and the bot team are all queued. A long-running split branch
diverges from live work and merges badly.

**Mitigation:** the split proceeds in **small, independently shippable steps on master**, not a
long-lived branch. If we stop after any step, what is live still works.

---

## The route, in reversible steps

Each step is independently deployable and independently revertible. **No step begins until the
one before it is verified live.**

| Stage | What happens | Reversible by | Risk |
|---|---|---|---|
| **0** | **Route census + full backup.** Record all 854 routes and their shapes as a check. Verify the off-site encrypted backup restores. | n/a — adds only | none |
| **1** | **Split `biz.env`** into shared / Nidaan / Sarathi. Same values, three files. | restore one file | 🟡 |
| **2** | **Extract Nidaan routes** from `sarathi_biz.py` into `nidaan_app.py`, mounted by the same process. One app still, two route files. | git revert | 🟠 |
| **3** | **Second process.** `nidaan-web@1/@2` on new ports, own deploy unit; nginx routes nidaanpartner.com to it. Still one database. | point nginx back | 🔴 |
| **4** | **Split the worker** — Nidaan's bot, guardian and schedulers move to `nidaan-worker`. | re-enable the old one | 🟠 |
| **5** | **Split the database.** `nidaan.db` gets the 45 `nidaan_*` tables; `product_link` becomes an API. | keep the old DB read-only until proven | 🔴 |
| **6** | **Move `/uploads`** by copy-verify-switch. | old path still serves | 🟠 |
| **7** | **Separate the folder** — `C:\nidaanpartner` and its own repo, with no Sarathi code but the bundle-login client. | n/a by then | 🟢 |

**The folder move he asked for is stage 7, not stage 1.** Moving files first would mean a
half-separated codebase deploying from two places with the entanglement still inside it — the
riskiest possible order, and the most tempting, because it looks like progress.

---

## What makes this safe rather than merely careful

- **A restore is tested before anything moves** (stage 0). A backup nobody has restored is a
  belief, not a backup.
- **Every stage is verified from outside**, by outcome — which product answers, does this exact
  route still return this exact shape — not by reading config.
- **The route census is a check that runs**, so a route that quietly stops existing fails the
  build rather than a staff member's afternoon.
- **Live work continues on master between stages.** The split never becomes the thing blocking
  Lokpal.
- **Nothing is deleted at any stage.** The old database, the old upload path and the old units
  stay until their replacement is proven, then they are archived — and the founder says when.

---

## What I need before stage 0

1. **A maintenance window** for stages 3 and 5 — the two that touch what is serving. Each needs
   perhaps 30 minutes of accepted risk, ideally late evening IST.
2. **A decision on the Sarathi side.** Sarathi keeps the existing folder, repo, database and
   units — Nidaan is the one that moves out. Cheaper and lower risk than moving both, but it
   means the *Sarathi* repo keeps the name `sarathi-business`.
3. **Confirmation that "eventually two databases" means now-ish.** If the two apps share one
   database for weeks, R2 is live that whole time. I would rather do stages 3 and 5 in the same
   week.

**My recommendation:** do stage 0 and 1 immediately — they are pure gain and carry no risk to
anything live. Then pause, look at the route census together, and decide stage 2 onward with
real numbers in front of us.
