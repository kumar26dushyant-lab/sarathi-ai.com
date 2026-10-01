# Sarathi-AI.com — the project brief

**Read this first, every session.** Standing context for Sarathi-AI: what it is, how it runs,
and what state it is in.

> NidaanPartner.com is a **separate product** with its own brief in `CLAUDE.nidaan.md`. The two
> shared one codebase until 27 September 2026. They no longer do. Do not mix them.

---

## What this is

**Sarathi-AI Business Technologies** — a voice-first Telegram CRM for India's insurance
advisors. Cultural Hinglish branding: *Sarathi* = charioteer, the one who drives for you.
Telegram-forward; WhatsApp deliberately kept out of the front door.

**It has no active users.** That matters for how work is planned here: Sarathi is where risky
changes are rehearsed before they go near NidaanPartner, which is live and carries real claims.
The founder said it plainly on 27 Sep: *"I am not worried about sarathi-ai.com if anything
breaks."*

That is a licence to move fast here. It is **not** a licence to be careless — the two still
share a database and a server until the split finishes.

---

## How it runs, today

| | |
|---|---|
| Host | Oracle Mumbai `161.118.186.201` (shared with Nidaan) |
| App | `sarathi_app.py` — **its own file since 27 Sep 2026** |
| Web | `sarathi-new-web@1` / `@2`, ports **8021/8022** |
| Worker | still the shared `sarathi-worker` — not yet split |
| Database | `/opt/sarathi/sarathi_biz.db` — **still shared with Nidaan** |
| Deploy | the shared `sarathi-deploy.service` |

Both domains sit behind one nginx config and **one TLS certificate covering all four names**, so
splitting traffic needed no certbot work. Each domain now has its own `server` block and its own
upstream.

---

## What it does

- **Master Telegram bot** (`biz_bot.py`) plus per-tenant bots (`biz_bot_manager.py`)
- **Tenants and agents** — `tenants`, `agents`, `leads`, `policies`
- **Leads pipeline**, nurture sequences (`biz_nurture.py`), reminders (`biz_reminders.py`)
- **Marketing** batches and campaigns (`biz_marketing.py`, `biz_campaigns.py`)
- **TGCRM** — per-firm Telegram voice CRM (`biz_sarathi_tgcrm.py`)
- **Agent microsites** at `/m/{slug}`, customer portfolios at `/portfolio/{token}`
- **WhatsApp** via its own WABA (`WA_ACCESS_TOKEN`, `WA_PHONE_NUMBER_ID`) — separate from
  Nidaan's entirely

Its routes live under `/api/*`, `/tenant/*`, `/agent/*`, plus the marketing site (`/about`,
`/features`, `/help`, `/support`, `/dashboard`, `/onboarding`, …).

---

## Known broken

- **@SarathiBizBot's token is rejected by Telegram.** "Master bot not running" has been raised
  **672 times in 7 days and emailed 524 times** — it is the main source of health-alert noise.
  Like Nidaan's old bot, it appears to have been created on an account that is no longer around.
  **Needs a company-owned Telegram account and a fresh token.** Not yet done.
- 6 templates are still awaiting Meta approval on the WhatsApp side.

---

## The seam with Nidaan

Exactly one thing must keep working across the two products: **`product_link`**, the bundle
login, mapping `nidaan_account_id ↔ sarathi_tenant_id`. When the databases separate it becomes a
small authenticated API rather than a shared table read.

Two other tables are touched by both and need a decision at database-split time: **`leads`**
(Nidaan's CRM writes to it) and **`system_flags`**. Neither carries a `nidaan_` prefix, so a
prefix-based split would silently take them away — the founder agreed Nidaan gets its own copy
of both.

`biz_platform_bridge.py` is the only module that should touch Sarathi's tenants and agents from
the Nidaan side.

---

## Rules that still apply here

The founder's standing rules are in `CLAUDE.nidaan.md` and they are not Nidaan-only. In
particular, on Sarathi too:

- **Never delete data without asking.**
- **Fix the cause in one place**, and look for the sibling.
- **A check must read an outcome, not a configuration.**
- **Tests never reach real people** — `NIDAAN_NO_OUTBOUND=1` on anything touching live data.

The difference is tolerance for breakage, not standards.

---

## Where the work is

Sarathi is **not** where the development effort is. The founder's priority is NidaanPartner
end to end. Sarathi's near-term work is only what the split requires:

1. Its own **worker** (stage 6) — the shared one currently runs both products' loops. Sarathi
   owns 3 of the 26: `reminders.start_scheduler`, `marketing_batch_loop`, `tgcrm_digest_loop`.
2. Its own **database** (stage 7).
3. Its own **folder and repo** (stage 8) — Sarathi keeps `/opt/sarathi` and the existing repo;
   Nidaan is the one that moves out.
4. A **working bot token** from a company-owned account.

See `docs/split/SPLIT_PLAN.md` for the staged plan and `docs/split/SPLIT_DECISIONS.md` for the per-route ownership.
