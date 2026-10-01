# Where every document lives

One folder per product, so each can move with its product when the two are split into their own
folders (`docs/split/SPLIT_PLAN.md`). Nothing here was deleted on 1 Oct 2026 — the loose files at
the root were moved into these folders with `git mv`, and every reference was updated.

## At the root — the living documents (read and updated every session)

| File | What it is |
|---|---|
| `CLAUDE.md` | The founder's standing rules for both products. Loaded into every session. |
| `CLAUDE.nidaan.md` | **NidaanPartner.com — the project brief.** What it is, how it runs, the modules, where the work is. Read first. |
| `CLAUDE.sarathi.md` | Sarathi-AI.com — its brief. |
| `TODO.md` | The standing list: anything raised and not finished, newest first. |
| `PROJECT_MASTER_CONTEXT.md` | The long history and design record (8,000+ lines). Search it; do not read it end to end. |
| `ANNOUNCEMENTS.md` | Bilingual staff messages drafted for the founder to send. Never sent automatically. |

## `docs/nidaan/` — NidaanPartner.com

| File | What it is |
|---|---|
| `COMPLIANCE_DPDP.md` | DPDP (data protection) gaps and what to do about them |
| `NIDAAN_BUILD_PLAN.md` | The original build plan (June 2026) — companion to the master doc |
| `NIDAAN_499_FUNNEL_SPEC.md` | The Rs 499 review funnel |
| `NIDAAN_WHATSAPP_JOURNEY_SPEC.md` | The complainant's WhatsApp journey (June 2026) |
| `WHATSAPP_CLAIMS_DESIGN.md` | WhatsApp on existing claims — the current design (Sep 2026) |
| `ARCHIVE_CANDIDATES.md` | Unused code, checked three ways, waiting for the founder's yes to archive |
| `setup/` | One-time setup: Meta/WhatsApp Cloud API, message templates to submit, Brevo email DNS |

Staff-facing SOPs are web pages, not markdown: `static/nidaan_sop_*.html`, served behind the ops
sign-in at `nidaanpartner.com/sop-<name>` (`_DOC_KEYS` in `sarathi_biz.py`).

## `docs/sarathi/` — Sarathi-AI.com

Current designs (`SARATHI_AI_CONTEXT.md`, `SARATHI_TGCRM_DESIGN.md`, `WHATSAPP_SUBSCRIBERS_PLAN.md`,
`WHATSAPP_PHONE_BRIDGE_DESIGN.md`) and, in `history/`, the first build's documents (May–June 2026:
build log, audits, feature inventory, test scenarios, tester guide). The history files describe
Sarathi as it was then — check the code before trusting them.

## `docs/split/` — separating the two products

`SPLIT_PLAN.md` (the staged plan) and `SPLIT_DECISIONS.md` (which product owns each route).

## `docs/infra/` and `deploy/`

`docs/infra/DEPLOY_ORACLE_CLOUD.md` is the original Oracle guide. The live runbooks stay in
`deploy/` beside the scripts they describe: cutover, zero-downtime deploy, secret rotation,
Cloudflare WAF, Razorpay webhook, DMARC records.

## Adding a document

Put it in the product's folder, add a line here, and link it from that product's CLAUDE brief if a
future session must read it. A document that only one session needs belongs in `TODO.md` instead.
