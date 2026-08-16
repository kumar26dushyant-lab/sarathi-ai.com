# Sarathi-AI — Telegram Voice CRM for Subscribers (Design Spec)

> **Status:** DRAFT for founder review (Aug 16 2026). No code until approved.
> **Related:** `project_sarathi_tgcrm` memory, PROJECT_MASTER_CONTEXT §73, reuse patterns from `biz_nidaan_telegram.py`.

---

## 1. Goal & principles

Let a Sarathi-AI subscriber run their **entire CRM from Telegram** using **their own bot**, voice-note-first, with team members able to operate a **tightly-scoped** slice — and with **airtight data isolation** between firms as a stated trust guarantee.

**Principles**
1. **Mobile-first, voice-first.** Every common action is doable by voice note; buttons are large, plain-worded (Tier-II/III), bilingual EN/HI/Hinglish.
2. **One permission model** shared by web + Telegram (no drift — endpoint-uniformity rule).
3. **Single-firm agents.** An agent belongs to exactly one firm at a time. To join another firm they must first leave the current one. This is the data-security promise, surfaced in the invite copy.
4. **Additive & reversible.** New module + new tables; existing web CRM and the old generic bot are untouched until we deliberately retire them. Feature-flagged rollout.
5. **Careful/no-break.** Reuse the proven Nidaan voice/AI/button stack; every scenario tested on staging first.

---

## 2. Architecture

**One bot per firm.** The subscriber creates a bot in BotFather and pastes the token into their dashboard. We register a **webhook** (not long-polling — long-polling can't scale to many tenant bots on one worker).

```
Telegram → POST /api/tg/hook/{bot_id}   (bot_id = opaque per-firm id, NOT the token)
             │
             ├─ verify X-Telegram-Bot-Api-Secret-Token header (per-firm secret)
             ├─ resolve firm (tenant) by bot_id
             ├─ resolve actor (owner/agent) by telegram_user_id + firm
             ├─ enforce role + is_active (cached ~30s re-check)
             └─ dispatch → command / voice / callback handler
```

- **Why webhook, not long-polling:** the worker already runs the Nidaan ops bot on long-polling (single bot). Dozens/hundreds of subscriber bots must be webhook-driven so one HTTPS endpoint fans out by `bot_id`. Telegram calls us; we don't hold N polling loops.
- **`bot_id` in the URL, token in the DB.** The webhook path carries a non-secret opaque id; the token stays server-side. We also set Telegram's per-webhook **secret token** and verify the `X-Telegram-Bot-Api-Secret-Token` header on every update (anti-spoof).
- **Token storage:** encrypted at rest (reuse whatever secret-at-rest approach biz.env/app uses; at minimum not plaintext in a world-readable place). `tenants.tg_bot_token` column already exists — we'll move to an encrypted column or a dedicated table (see §3).
- **Reused stack:** Gemini voice transcription + intent, bilingual copy, inline-button UX, all from `biz_nidaan_telegram.py`. New module: `biz_sarathi_tgcrm.py` (kept separate from the Nidaan ops bot and from the old `biz_bot.py`).

---

## 3. Data model (additive)

New/changed tables (SQLite, ALTER-on-first-use pattern):

```
tg_firm_bots
  bot_id            TEXT PRIMARY KEY      -- opaque, in webhook URL
  tenant_id         INTEGER NOT NULL      -- the firm
  bot_token_enc     TEXT NOT NULL         -- encrypted BotFather token
  bot_username      TEXT
  webhook_secret    TEXT NOT NULL         -- per-bot secret header
  status            TEXT DEFAULT 'active' -- active | revoked | error
  last_error        TEXT
  created_by        INTEGER               -- agent_id
  created_at        TEXT

tg_links                                  -- who is bound to which firm bot
  telegram_user_id  INTEGER NOT NULL
  tenant_id         INTEGER NOT NULL
  agent_id          INTEGER NOT NULL      -- the Sarathi agent record
  role              TEXT NOT NULL         -- owner | admin | member
  status            TEXT DEFAULT 'active' -- active | revoked
  linked_at         TEXT
  UNIQUE(telegram_user_id)                -- ENFORCES single-firm: one link per TG user

tg_invites
  code              TEXT PRIMARY KEY      -- one-time, short
  tenant_id         INTEGER
  role              TEXT DEFAULT 'member'
  created_by        INTEGER
  expires_at        TEXT
  used_by           INTEGER               -- telegram_user_id once redeemed
  used_at           TEXT

tg_context                                -- multi-turn conversation memory
  telegram_user_id  INTEGER
  tenant_id         INTEGER
  last_intent       TEXT
  pending           TEXT                  -- JSON: partial action awaiting confirmation
  updated_at        TEXT
```

- `tg_links.UNIQUE(telegram_user_id)` is the **hard single-firm guarantee** at the DB level: a Telegram account can be bound to only one firm. Joining another requires the existing link be `revoked`/deleted first.
- Reuse existing `agents` (is_active, role) as the source of truth; `tg_links` maps Telegram identity → agent.

---

## 4. Roles & permissions (single matrix, web + Telegram)

| Capability | Solo admin | Team/Ent admin | Member |
|---|---|---|---|
| View/update **assigned** leads | ✅ | ✅ | ✅ |
| View **all firm** leads | ✅ | ✅ | ❌ |
| Create leads | ✅ | ✅ | ❌ |
| Log calls / notes / stage moves / follow-ups (on allowed leads) | ✅ | ✅ | ✅ (assigned only) |
| Voice-note actions (within their scope) | ✅ | ✅ | ✅ |
| Invite / remove members | ❌ (n/a) | ✅ | ❌ |
| Billing / subscription | ✅ | ✅ | ❌ |
| Export data | ✅ | ✅ | ❌ |
| Ask AI / get help (member support role) | ✅ | ✅ | ✅ |

Member scope = **assigned-leads-only** (confirmed). Same matrix drives web and Telegram — one `check_permission()` path.

---

## 5. Onboarding

1. Admin (web or bot): **"Add team member"** → generates a **one-time invite code** (`tg_invites`, short, expiring) + a deep link `https://t.me/<firmbot>?start=<code>`.
2. Admin shares the link with the member (WhatsApp/SMS/paste).
3. Member opens the **firm's bot**, taps Start → bot reads `<code>` → validates (unused, unexpired, firm active, seats available per `max_agents`).
4. **Single-firm check:** if the member's Telegram id already has an active `tg_links` row for another firm → bot refuses with a plain message: *"You're already part of <FirmX>. Ask them to remove you first — your data stays with them, and you can then join a new firm."* (This is the trust guarantee in action.)
5. On success: create/attach the `agents` record (role=member), create `tg_links` row, greet with the member's voice-first quick menu.

---

## 6. Offboarding / deactivation — one button, instant, everywhere

**Single control** (web *and* bot, admin-only): **"Remove member"** →
1. `agents.is_active = 0` (blocks web/mobile-web login — already the case).
2. `tg_links.status='revoked'` for that Telegram id → bot immediately rejects them.
3. **Instant session kill:** the new **cached ~30s `is_active` re-check** (mirrors Nidaan `_staff_still_active`) makes any open web/mobile session expire within ~30s instead of ~24h. (This is the security item #10 — built as part of this platform so the off-switch is truly unified.)
4. Member's data stays with the firm; nothing is exported to them.
5. They may now accept a new firm's invite (single-firm freed).

Same flow for the whole bot: admin can **revoke the firm's bot** (`tg_firm_bots.status='revoked'`) → webhook deleted at Telegram, all links frozen.

---

## 7. Voice-first & context-aware UX

- **Voice note → transcription (Gemini) → intent → action** with a **confirm step** for writes (Tier-II/III safety; matches Nidaan "review gate").
- **Multi-turn context** via `tg_context.pending`: e.g. *"Add a follow-up for Rajesh"* → bot: *"When?"* → *"Tomorrow 5pm"* → confirm card → done. Context persists across messages until resolved or timed out.
- **Plain, worded buttons** (no ambiguous icons): 📋 My Leads · 🎤 Speak an update · ➕ (admin) · ❓ Help.
- Everything bilingual; language follows the member's preference.

## 8. Member support role

The bot doubles as a **help assistant** for members: "How do I log a call?", "What's my pending list?", "Explain this lead's status." Grounded in a Sarathi KB (shared with the homepage chatbot work). Members can also raise a **support ticket** to their firm admin or to Sarathi support from the bot.

---

## 9. Subscriber 10-minute bot setup (in-dashboard guide)

1. Open **@BotFather** in Telegram → `/newbot` → name it (e.g. "Ramesh & Co CRM") → get **token**.
2. Copy the token → paste into **Dashboard → Team → Telegram Bot → Connect**.
3. We auto-register the webhook + secret; dashboard shows **✅ Connected** (with a live self-test).
4. (Optional) set bot picture/description in BotFather.
5. Share the member invite link. Done — CRM is live on Telegram.

Screens + copy shipped in-dashboard, bilingual, with a 60-sec explainer.

---

## 10. Fallback / error scenarios (must all be handled)

| Scenario | Behaviour |
|---|---|
| Bad/invalid token pasted | Connect fails with a clear message; nothing stored. |
| Token revoked in BotFather later | Webhook 401s → mark `status='error'`, alert admin on web + (if possible) other channel; bot shows "reconnect" flow. |
| Telegram webhook drops / not delivered | Health job re-asserts webhook; admin sees status. |
| Plan downgraded below active member count | Block new joins; existing over-limit members flagged for admin to remove (guide-don't-break). |
| Trial/subscription expired | Bot switches to read-only + renew prompt (mirrors web 402/403 gating). |
| Voice unclear / transcription fails | Bot asks to repeat or offers buttons. |
| Member tries admin action | Denied with plain message + who to ask. |
| Single-firm conflict on join | Refused with the "ask them to remove you first" message (§5.4). |
| Duplicate/att replayed webhook | Idempotency via Telegram update_id dedupe. |

---

## 11. Security

- Per-bot **webhook secret** verified on every update; `bot_id` opaque (token never in URL/logs).
- Token **encrypted at rest**; never printed.
- **Single-firm** DB constraint (`UNIQUE(telegram_user_id)`).
- **Instant deactivation** via cached is_active re-check (kills web+mobile+bot together).
- Rate-limiting per Telegram user; write-confirm gate on destructive actions (confirm-before-delete rule).
- Full audit log of bot actions (reuse activity log), incl. voice-originated ones.

---

## 12. Build phases (each staged + tested before prod)

- **P0 — Schema + webhook skeleton:** tables, `bot_id` routing, secret verification, connect/disconnect in dashboard, self-test. No CRM actions yet.
- **P1 — Identity & roles:** invites, single-firm enforcement, onboarding/offboarding, the cached is_active re-check (security #10). One deactivate button end-to-end.
- **P2 — Read flows (voice + buttons):** my leads, lead detail, pending follow-ups, help/support. Context memory.
- **P3 — Write flows (confirmed):** log call/note, stage move, set follow-up — voice-first, with confirm cards. Member scoped to assigned leads.
- **P4 — Admin extras:** create lead, all-firm view, assign leads, member management from bot.
- **P5 — Polish:** bilingual copy pass, mobile-web parity check, retire old `biz_bot.py` behind a flag.

## 13. Test matrix (scenarios to prove per phase)

Owner solo · admin+member (Team) · admin+members (Enterprise) · member assigned vs unassigned lead · single-firm join refusal · remove-member instant cut (web+bot within 30s) · token revoked · webhook drop/re-assert · plan downgrade over-limit · trial expiry read-only · voice happy-path + garbled · bilingual both languages · impersonation/audit. Each on staging (own DB) before prod.

---

## Open questions for founder

1. **Bot self-test on connect** — OK to auto-send the admin a "✅ your CRM bot is live" message from their own bot as the connection proof? (Recommended.)
2. **Members raising tickets** — route member support tickets to the **firm admin**, to **Sarathi support**, or let the member choose? (Default: choose.)
3. Anything a **member must NOT see** even on their assigned leads (e.g. customer phone/email masking)? Default: full detail on assigned leads only.
