#!/usr/bin/env python3
"""Exercise NidaanPartner's real functions against a given DB and print a comparable fingerprint.

Run on BOTH machines against a byte-identical database. Any difference in the output is then a
difference in the platform or the code, not in the data and not in live activity.

DB-only by design: anything that would call Gemini, Razorpay or WhatsApp is excluded, because the
two boxes hold different credentials and would differ for reasons that mean nothing.

Runs against a COPY with outbound disabled, so a stray write is contained and a send is impossible.
"""
import asyncio
import hashlib
import os
import sys

DB = sys.argv[1]
os.environ["DB_PATH"] = DB
os.environ["NIDAAN_NO_OUTBOUND"] = "1"
sys.path.insert(0, "/opt/sarathi")

import aiosqlite
import biz_database as db

db.DB_PATH = DB
OUT = []


def fp(v):
    """Stable fingerprint: shape and size, not volatile detail."""
    try:
        if v is None or isinstance(v, bool):
            return str(v)
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, dict):
            keys = sorted(str(k) for k in v)[:14]
            return "{" + ",".join("%s=%s" % (k, fp(v.get(k))) for k in keys) + "}"
        if isinstance(v, (list, tuple, set)):
            return "list[%d]" % len(v)
        s = str(v)
        if len(s) <= 60:
            return s
        return "str#" + hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()[:10]
    except Exception:
        return "?"


def rec(name, value):
    OUT.append("%-54s %s" % (name, fp(value)))


async def call(name, fn, *args, **kw):
    if fn is None:
        return
    try:
        r = fn(*args, **kw)
        if asyncio.iscoroutine(r):
            r = await r
        rec(name, r)
    except Exception as e:
        rec(name, "RAISED %s: %s" % (type(e).__name__, str(e)[:48]))


MODULES = (
    "biz_nidaan", "biz_nidaan_buckets", "biz_nidaan_doc_checklist", "biz_nidaan_doc_request",
    "biz_nidaan_stats", "biz_nidaan_claimant", "biz_nidaan_claim_access", "biz_nidaan_case_state",
    "biz_nidaan_claim_parties", "biz_nidaan_channel_partners", "biz_nidaan_capabilities",
    "biz_nidaan_wa_messages", "biz_nidaan_notify_policy", "biz_nidaan_alarm_policy",
    "biz_nidaan_login_health", "biz_nidaan_guide", "biz_nidaan_stage_guide",
    "biz_nidaan_doc_collect", "biz_nidaan_wa_identity", "biz_nidaan_wa_guard",
    "biz_nidaan_tasks", "biz_nidaan_retention", "biz_nidaan_crm", "biz_nidaan_wa_inbox",
    "biz_nidaan_wa_schedule", "biz_nidaan_daily_summary", "biz_platform_bridge",
    "biz_nidaan_health_watch", "biz_nidaan_notifications",
)


async def main():
    async with aiosqlite.connect(DB) as c:
        c.row_factory = aiosqlite.Row
        claims = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, COALESCE(claim_type,'health') AS t FROM nidaan_claims "
            "WHERE COALESCE(archived,0)=0 ORDER BY claim_id DESC LIMIT 5")).fetchall()]
        br = await (await c.execute(
            "SELECT branch_code FROM nidaan_branches WHERE status='active' LIMIT 1")).fetchone()
        ac = await (await c.execute(
            "SELECT account_id FROM nidaan_accounts ORDER BY account_id DESC LIMIT 1")).fetchone()
    BR = dict(br)["branch_code"] if br else ""
    AC = dict(ac)["account_id"] if ac else None

    mods = {}
    for name in MODULES:
        try:
            m = __import__(name)
            if getattr(m, "DB_PATH", None) not in (None, DB):
                m.DB_PATH = DB
            inner = getattr(m, "db", None)
            if inner is not None and getattr(inner, "DB_PATH", None) not in (None, DB):
                inner.DB_PATH = DB
            mods[name] = m
        except Exception as e:
            rec("IMPORT:" + name, "FAILED %s" % str(e)[:40])
    rec("modules.imported", len(mods))

    n = mods.get("biz_nidaan")
    bk = mods.get("biz_nidaan_buckets")
    dc = mods.get("biz_nidaan_doc_checklist")
    dr = mods.get("biz_nidaan_doc_request")
    st = mods.get("biz_nidaan_stats")
    ca = mods.get("biz_nidaan_claim_access")
    cp = mods.get("biz_nidaan_claim_parties")
    cs = mods.get("biz_nidaan_case_state")

    # The office: every bucket, its board, its steps, its fields, where a claim may go.
    if bk:
        await call("buckets.config", bk.config)
        cfg = await bk.config()
        for b in cfg.get("buckets", []):
            k = b["bucket_key"]
            await call("buckets.board:" + k, bk.board, k)
            await call("buckets.substates:" + k, bk.substates, k)
            await call("buckets.fields:" + k, bk.fields, k)
            await call("buckets.moves_from:" + k, bk.moves_from, k)
        await call("buckets.escalation_due", bk.escalation_due)
        for cc in claims:
            await call("buckets.missing_required:%s" % cc["claim_id"],
                       bk.missing_required, cc["claim_id"], "live_cases")

    # Documents — the longest wait in Level-2.
    if dc:
        for cc in claims:
            cid = cc["claim_id"]
            await call("checklist.effective_docs:%s" % cid, dc.effective_docs, cid, cc["t"])
            await call("checklist.removed_docs:%s" % cid, dc.removed_docs, cid)
            await call("checklist.status:%s" % cid, getattr(dc, "checklist_status", None), cid)
            await call("checklist.pending:%s" % cid, getattr(dc, "pending_required_docs", None), cid)
    if dr:
        await call("docreq.desk", dr.desk)
        for cc in claims:
            await call("docreq.recent_ask:%s" % cc["claim_id"], dr.recent_ask, cc["claim_id"])

    # Money.
    if st:
        for fn in ("awaiting_fee", "revenue_summary", "funnel_summary", "claim_stats",
                   "dashboard_stats", "overview"):
            await call("stats." + fn, getattr(st, fn, None))

    # How a complainant gets in, and who we would tell.
    if ca:
        for cc in claims:
            await call("access.channels:%s" % cc["claim_id"], ca.channels, cc["claim_id"])
    if cp:
        for cc in claims:
            await call("parties.get:%s" % cc["claim_id"], cp.get_claim_parties, cc["claim_id"])
    if cs:
        for cc in claims:
            await call("case_state.brief:%s" % cc["claim_id"],
                       getattr(cs, "_claim_brief", None), cc["claim_id"])

    # Claims, branches, plans, the bundle link.
    if n:
        for cc in claims:
            for fn in ("get_claim", "get_claim_full", "claim_timeline"):
                await call("nidaan.%s:%s" % (fn, cc["claim_id"]),
                           getattr(n, fn, None), cc["claim_id"])
        rec("nidaan.PLAN_LIMITS", sorted(n.PLAN_LIMITS.keys()))
        for fn in ("list_branches", "list_staff", "list_claims"):
            await call("nidaan." + fn, getattr(n, fn, None))
        if BR:
            await call("nidaan.get_branch:%s" % BR, getattr(n, "get_branch", None), BR)
        if AC:
            await call("nidaan.get_active_subscription", getattr(n, "get_active_subscription", None), AC)
            await call("nidaan.get_sarathi_tenant", getattr(n, "get_sarathi_tenant_for_nidaan", None), AC)

    # Pure composers and policy — same input must give the same words.
    wm = mods.get("biz_nidaan_wa_messages")
    if wm:
        ctx = {"name": "Test", "claim_id": 1, "docs": ["a", "b"], "n": 2, "count": 2}
        for key in sorted(getattr(wm, "_COMPOSERS", {}) or {})[:14]:
            await call("wa_messages.compose:" + key, getattr(wm, "compose", None), key, "hinglish", ctx)
    pol = mods.get("biz_nidaan_notify_policy")
    if pol:
        for ek in ("claim.doc.received", "payment.failed", "quick_task.comment",
                   "leave.decided", "health.subsystem", "unknown.event"):
            rec("notify_policy.should_email:" + ek, pol.should_email(ek, role="staff"))
    ap = mods.get("biz_nidaan_alarm_policy")
    if ap:
        for ek in ("health.subsystem", "task.assigned", "conversation.unanswered",
                   "payment.success", "bucket.stale"):
            rec("alarm.is_alarm:" + ek, ap.is_alarm(ek))
        await call("alarm.audience", ap.audience)
    cap = mods.get("biz_nidaan_capabilities")
    if cap:
        rec("capabilities.count", len(getattr(cap, "CAPABILITIES", []) or []))
    hw = mods.get("biz_nidaan_health_watch")
    if hw:
        rec("health.CRITICAL", sorted(getattr(hw, "_CRITICAL", set())))
        rec("health.GAPS", sorted(getattr(hw, "_GAPS", set())))

    # The bundle seam.
    pb = mods.get("biz_platform_bridge")
    if pb:
        await call("bridge.find_ending_on", pb.find_bundle_tenants_ending_on, "2026-12-01")

    print("\n".join(OUT))
    print("TOTAL_CHECKS %d" % len(OUT))


asyncio.run(main())
