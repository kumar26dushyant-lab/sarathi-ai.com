# Stage 2 — the 38 routes that need a decision

**For:** the founder. **Date:** 27 September 2026.
Everything else is decided by its path. These are not, and I said I would bring you a list
rather than guess.

---

## First, the good news, measured

`deploy/split-surface.py` walked all 865 route handlers in `sarathi_biz.py` and followed every
helper each one reaches, transitively.

| | |
|---|---|
| Names used **only** by Nidaan routes | **251** |
| Names used **only** by Sarathi routes | **111** |
| Names used by a Nidaan route **and** a Sarathi route | **6** |

The six: `app`, `limiter`, `logger`, `health`, `SERVER_START_TIME`, `_is_nidaan_host`.

**There is no shared business logic between the two products.** Framework plumbing, a health
endpoint, and the host router — which stops existing the moment each app serves one host. The
file is 30,029 lines holding two products that barely touch.

That is the whole risk assessment for stage 2, and it is much better than I expected.

---

## The 38 routes, and what I recommend

**17 are already host-gated** — they check `_is_nidaan_host` and serve a different thing per
domain. Each becomes **two routes, one in each app**, and the check disappears.

| Route | Today | Recommend |
|---|---|---|
| `/` | serves both | **split** — each app serves its own home |
| `/privacy` `/terms` | serves both | **split** — already corrected to the right entity |
| `/robots.txt` `/sitemap.xml` | serves both | **split** — different sites, different sitemaps |
| `/google3df0c…html` | serves both | **split** — Search Console per domain |
| `/admin` `/admins` `/subadmin` `/associate` `/preview` | Nidaan branches | **Nidaan** |
| `/superadmin` | serves both | **split** — you use nidaanpartner.com/superadmin daily |
| `/login` | serves both | **split** — `sarathi_login_page` also answers Nidaan |
| `/health` | not gated | **both** — each app needs its own, and the monitors must watch both |

**14 go to Sarathi** — its marketing site and app, none of it Nidaan's:
`/about` `/features` `/help` `/support` `/getting-started` `/telegram-guide` `/partner` `/demo`
`/invite` `/calculators` `/onboarding` `/dashboard` `/pay-success` `/ws/agent`

**4 more to Sarathi**, less obvious but its own: `/m/{slug}` and `/m/{slug}/lead` (agent
microsites), `/portfolio/{token}` (customer portfolio), `/manifest.json` + `/sw.js` (its PWA —
Nidaan needs its own pair, not a share).

**2 need you, because I genuinely cannot tell:**

| Route | Why I am asking |
|---|---|
| `/webhook` ×2 (`webhook_verify`, `webhook_receive`) | Not host-gated, and **WhatsApp**. Nidaan and Sarathi have separate WABAs — so does Meta call this one path for both, distinguished inside, or is it only one product's? Getting this wrong silently drops inbound customer WhatsApp. |
| `/internal/deploy` | The deploy webhook. One deploy today, two after stage 3. Does Sarathi get its own trigger, or do both keep deploying from one? |

**8 are not routes at all** — middleware and a startup hook: timing, security headers, error
capture, subscription enforcement, impersonation audit, the Nidaan document guard. **Each app
gets its own copy.** They are small, and sharing them would recreate the coupling we are
removing.

---

## What I will do once you answer

1. Lift the six shared names into `app_core.py` — the only genuinely common code.
2. Move Sarathi's 357 routes and its 111 private helpers into `sarathi_app.py`.
3. Run the route census after **every** group moved, not at the end.
4. Nidaan's 462 routes and 251 helpers **do not move**. Not one line.

Nothing about Nidaan changes in stage 2 — including its deploy, its database, its documents and
its process. If we stopped after stage 2, the only visible difference would be that
`sarathi_biz.py` is a lot shorter.
