# Code that looks unused — for the founder's yes before anything is archived

_1 Oct 2026. Nothing has been changed. Archive means moving to `archive/` with a note of why —
never deleting. Founder's rule: "check twice or thrice to be sure ... archive not delete"._

Every item below was checked three ways: (1) no caller in any Python file (words inside strings
count, so getattr/log references are covered); (2) no caller in any page (`static/*.html`, `*.js`);
(3) a plain search of tests, tools, deploy scripts and the Android app. Line numbers drift as code
changes — search by name.

## Ready to archive (high confidence) — say yes per group

**A. A whole module nothing imports**
- `biz_sarathi_whatsapp.py` (105 lines, Sarathi Meta sender) — not imported anywhere.

**B. Functions nobody calls — NidaanPartner**
`biz_nidaan.py`: set_branch_status, assign_claim, list_task_watchers,
create_nidaan_razorpay_subscription, get_claim_watcher_ids, count_unread_messages_for_subscriber,
mark_overdue_followups · `biz_nidaan_case_state.py`: enter_pipeline ·
`biz_nidaan_claim_access.py`: _codes_this_hour · `biz_nidaan_claim_parties.py`:
contact_gaps_for_account, contact_gaps_for_branch · `biz_nidaan_crm.py`: due_followups (keep — the
CRM revamp will use it) · `biz_nidaan_daily_summary.py`: _actions_text · `biz_nidaan_doc_checklist.py`:
why_hi_for, pay_gate_ready · `biz_nidaan_doc_collect.py`: contact_status · `biz_nidaan_doc_store.py`:
touch_job · `biz_nidaan_notifications.py`: on_sla_overdue, _alert_allowed, _alert_clear ·
`biz_nidaan_radar.py`: list_sent · `biz_nidaan_stage_guide.py`: guide_for_bucket, label_for_bucket ·
`biz_nidaan_tasks.py`: request_qc, upsert_transition · `biz_nidaan_telegram.py`: _request_phone ·
`biz_nidaan_wa_auth.py`: is_verified · `biz_nidaan_wa_orchestrator.py`: _save_wa_doc ·
`sarathi_biz.py`: _nidaan_ops_page_with_role.

**C. Functions nobody calls — Sarathi / shared** (for the Sarathi session to decide)
biz_auth (5 OTP/permission helpers + 4 OTP storage functions they alone use), biz_database
(16 Sarathi queries), biz_calculators (9 format_*_result), biz_bot_manager (3), biz_email
(send_founding_welcome, send_trial_reminder, send_renewal_success), biz_resilience (6 + 4),
biz_whatsapp (7 + 1), biz_whatsapp_evolution (3), biz_whatsapp_safety (2), biz_marketing (3),
biz_quotes (1), biz_lapse (1), biz_i18n (1), biz_doc_splitter._sanitize, sarathi_biz._empty_dashboard.

**D. Ops screens nobody can reach** (`static/nidaan_ops.html`)
- My Desk (panel-desk + loadDesk, deskRender, deskGuide, deskMoveOn, deskMoveAll,
  cbOpenSheetFromDesk, _deskStyles) — every link to it is redirected to Consolidation since 14 Sep.
- Case Board (panel-board + loadCaseBoard only — the cb* helpers are still used inside Consolidation).
- The old Pipeline screen code (_loadPipelineRetired, _renderPipeline, pipeSetOrigin/Cust/Search).

## Needs a decision

**E1. The old shared-key admin API** — six `/nidaan/api/admin/*` routes behind `NIDAAN_ADMIN_TOKEN`.
The key is not set on the server (checked 30 Sep), so they refuse everyone; the only page that
called them (`static/nidaan_admin.html`) is no longer served. Recommendation: archive the six
routes, the helper and the page. Security-relevant, so: your yes first.

**E2. Evolution "official numbers"** — the old WhatsApp gateway. Sending from it is still wired
(App Health's "Manage" button, a fallback sender), but its inbound handler now lives only in the
Sarathi app, and it was removed from the menu on 1 Sep as unused (last send 11 Jul). Decide:
retire it from NidaanPartner completely, or keep it as a fallback.

**F. Routes with no caller found** (likely leftovers — confirm none are linked from outside)
The old ₹499 Razorpay review flow (`/nidaan/api/review-request`, `/pay`, `/verify` — replaced by
`/nidaan/start` on 14 Jun); `/nidaan/get-reviewed` (maybe bookmarked); mobile-first signup
(`/nidaan/api/check-phone`, `/nidaan/api/signup/mobile`); `/nidaan/api/support/attach`;
`/nidaan/api/doc-checklist`; `/nidaan/api/official-vcard`; ops: `cases/{id}/state`,
`wa/contacts/{msisdn}/lead`, `escalation/due`, `payments/guardian/run`, PATCH/DELETE
`status-config/{slug}`.
Kept on purpose (tools without a screen): `ui/usage`, `notifications/explain`, `doc/readers`,
`grievance-officer`, `docsplit/upload`.

**G. Ops tabs** — decided by evidence, not by this list: screen opens are counted from 1 Oct
(`/nidaan/ops/api/ui/usage`). Review around 8 Oct.

## Found on the way (fixed, not archived)
- The subscriber dashboard's Features tab called `/features` (a Sarathi page) and was empty for
  every subscriber — fixed 1 Oct (`9f8894b`).
