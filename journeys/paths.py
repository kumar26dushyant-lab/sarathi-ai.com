# -*- coding: utf-8 -*-
"""The journeys themselves — the handful of things the business cannot be down for.

Deliberately few. Each is a way NidaanPartner earns or serves; if one of these cannot complete we
are down, whatever any dashboard says. Every step reads like the thing a person does, so a failure
names the human consequence and not an internal symbol.

Adding a journey is cheap and adding the wrong one is expensive: a journey that depends on a
particular claim being in a particular state will cry wolf every week. Where the live data cannot
exercise a path, raise Skip rather than inventing data.
"""
from __future__ import annotations

import aiosqlite

from .harness import Journey, Skip

ALL: list = []


def _j(key, name, who):
    j = Journey(key, name, who)
    ALL.append(j)
    return j


# ─────────────────────────────────────────────────────────────────────────────
portal = _j("portal", "A complainant opens their claim page", "complainant")


@portal.step("their claim has a portal link")
async def _p1(ctx):
    p = await ctx["claimant"].ensure_portal(ctx["claim_id"])
    assert p and p.get("access_token"), "no portal token for this claim"
    ctx["token"] = p["access_token"]


@portal.step("the link resolves — this is what a click does")
async def _p2(ctx):
    assert await ctx["claimant"].get_portal_by_token(ctx["token"]), \
        "the link did not resolve to a claim"


@portal.step("the page offers a way to prove who they are")
async def _p3(ctx):
    # The step that broke on 18 Sep: channels() called a function that had been renamed, so every
    # complainant saw "this link is invalid or has expired".
    ch = await ctx["access"].channels(ctx["claim_id"])
    assert isinstance(ch, list) and ch, \
        "no way offered to verify identity — the page shows 'link expired'"
    ctx["channels"] = ch


@portal.step("at least one of those ways can deliver")
async def _p4(ctx):
    assert [c for c in ctx["channels"] if c.get("ready")], \
        "every verification channel says it cannot deliver"


# ─────────────────────────────────────────────────────────────────────────────
branch = _j("branch_login", "A branch logs in", "branch")


@branch.step("the branch has a way in")
async def _b1(ctx):
    b = ctx["branch_row"]
    if not b:
        raise Skip("no active branch with an email to test against")
    assert b.get("contact_email") or b.get("contact_phone"), \
        "this branch has neither an email nor a mobile"


@branch.step("a login code can be issued")
async def _b2(ctx):
    r = ctx["auth"].generate_email_otp((ctx["branch_row"].get("contact_email") or "").strip())
    assert "error" not in r, r.get("error")
    assert r.get("otp"), "no code was produced"
    ctx["otp"] = r["otp"]


@branch.step("that code verifies")
async def _b3(ctx):
    assert ctx["auth"].verify_email_otp(
        (ctx["branch_row"].get("contact_email") or "").strip(), ctx["otp"]), \
        "a code issued seconds ago did not verify"


# ─────────────────────────────────────────────────────────────────────────────
docs = _j("documents", "Staff open a claim's documents", "staff")


@docs.step("the documents window loads")
async def _d1(ctx):
    w = await ctx["docreq"].window(ctx["claim_id"])
    assert w.get("ok"), w.get("error") or "the documents window would not open"
    ctx["docwin"] = w


@docs.step("it knows which documents this claim needs")
async def _d2(ctx):
    assert isinstance(ctx["docwin"].get("docs"), list), "no checklist came back"


@docs.step("it knows who we would ask")
async def _d3(ctx):
    assert isinstance(ctx["docwin"].get("recipients"), list), "no recipient list came back"


@docs.step("it shows what has already been asked")
async def _d4(ctx):
    assert isinstance(ctx["docwin"].get("history"), list), \
        "no request history — staff cannot see whether a colleague already asked"


# ─────────────────────────────────────────────────────────────────────────────
board = _j("board", "Staff open the work screen and see their cases", "staff")


@board.step("the buckets are configured")
async def _w1(ctx):
    bl = await ctx["buckets"].buckets()
    assert bl, "no buckets configured — the work screen would be empty"
    ctx["bucket_keys"] = [b["bucket_key"] if "bucket_key" in b else b.get("key") for b in bl]


@board.step("Live Cases exists and can be read")
async def _w2(ctx):
    assert any(k == "live_cases" for k in ctx["bucket_keys"]), "live_cases bucket is missing"


@board.step("a claim can be read with its fields")
async def _w3(ctx):
    f = await ctx["buckets"].claim_fields(ctx["claim_id"])
    assert isinstance(f, dict), "claim fields could not be read"


# ─────────────────────────────────────────────────────────────────────────────
# The draft-query round trip. This is the behaviour groups A3/A4 change, so it is pinned BEFORE
# the change and re-run after: the point is not that it behaves one way, but that it behaves the
# way we last agreed and nothing else moved underneath it.
query = _j("draft_query", "A draft query is raised and resolved", "staff")


@query.step("a claim in Pending Draft can be found")
async def _q1(ctx):
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id FROM nidaan_claims WHERE pipeline_stage='pending_draft' "
            "LIMIT 1")).fetchone()
    if not r:
        raise Skip("no claim is sitting in Pending Draft right now")
    ctx["q_claim"] = int(dict(r)["claim_id"])


@query.step("raising a query is accepted")
async def _q2(ctx):
    res = await ctx["buckets"].raise_query(
        ctx["q_claim"], "Journey check — please ignore.", actor="journey-test",
        actor_role="super_admin")
    assert res.get("ok"), res.get("error") or "the query was refused"


@query.step("the claim is marked with an open query")
async def _q3(ctx):
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        r = dict(await (await c.execute(
            "SELECT query_state, pipeline_stage FROM nidaan_claims WHERE claim_id=?",
            (ctx["q_claim"],))).fetchone())
    assert r["query_state"] == "open", "the claim does not show an open query"
    ctx["q_stage_after_raise"] = r["pipeline_stage"]


@query.step("the claim did NOT leave Pending Draft")
async def _q4(ctx):
    # The founder's rule (19 Sep): "Only status changing draft query, should not be moving
    # anywhere." Before that change this step is expected to fail, which is exactly why it is
    # written now — it is the specification, and the baseline run records that we do not meet it.
    assert ctx["q_stage_after_raise"] == "pending_draft", (
        "the claim moved to '%s' — a draft query must change the status only"
        % ctx["q_stage_after_raise"])


@query.step("Live Cases can resolve it without moving the claim")
async def _q5(ctx):
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        mo = await (await c.execute(
            "SELECT staff_id FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
            "LIMIT 1")).fetchone()
    if not mo:
        raise Skip("no active staff to hand the claim back to")
    res = await ctx["buckets"].resolve_query(
        ctx["q_claim"], dict(mo)["staff_id"], "Journey check — resolved.",
        actor="journey-test", actor_role="super_admin")
    assert res.get("ok"), res.get("error") or "the query could not be resolved"


@query.step("and it is still in Pending Draft afterwards")
async def _q6(ctx):
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        r = dict(await (await c.execute(
            "SELECT query_state, pipeline_stage FROM nidaan_claims WHERE claim_id=?",
            (ctx["q_claim"],))).fetchone())
    assert r["pipeline_stage"] == "pending_draft", \
        "resolving moved the claim to '%s'" % r["pipeline_stage"]
    assert r["query_state"] == "resolved", "the query was not marked resolved"


# ─────────────────────────────────────────────────────────────────────────────
fence = _j("no_drift_back", "Drafting does not drift back to Live Cases", "staff")


@fence.step("a claim in Pending Draft can be found")
async def _f1(ctx):
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id FROM nidaan_claims WHERE pipeline_stage='pending_draft' "
            "LIMIT 1")).fetchone()
    if not r:
        raise Skip("no claim is sitting in Pending Draft right now")
    ctx["f_claim"] = int(dict(r)["claim_id"])


@fence.step("ordinary staff cannot send it back to Live Cases")
async def _f2(ctx):
    res = await ctx["buckets"].move(ctx["f_claim"], "live_cases",
                                    reason="Journey check — this must be refused.",
                                    actor="journey-test", actor_role="team_member")
    assert not res.get("ok"), "a team member was allowed to send drafting back to Live Cases"
    assert "draft query" in (res.get("error") or "").lower(), \
        "the refusal does not point them at the draft query: %s" % res.get("error")


@fence.step("a super admin still can, when it truly has to move")
async def _f3(ctx):
    res = await ctx["buckets"].move(ctx["f_claim"], "live_cases",
                                    reason="Journey check — super admin pull-back.",
                                    actor="journey-test", actor_role="super_admin")
    assert res.get("ok"), "a super admin was blocked too: %s" % res.get("error")


@fence.step("forward movement is untouched")
async def _f4(ctx):
    res = await ctx["buckets"].move(ctx["f_claim"], "pending_draft",
                                    reason="Journey check — putting it back where it was.",
                                    actor="journey-test", actor_role="super_admin")
    assert res.get("ok"), "normal movement broke: %s" % res.get("error")


# ─────────────────────────────────────────────────────────────────────────────
dates = _j("dates", "A reversed treatment date is refused", "staff")


@dates.step("a claim in the pipeline can be found")
async def _dt1(ctx):
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id FROM nidaan_claims WHERE COALESCE(pipeline_stage,'')!='' "
            "LIMIT 1")).fetchone()
    if not r:
        raise Skip("no claim has started Level-2")
    ctx["dt_claim"] = int(dict(r)["claim_id"])


@dates.step("an admission date saves normally")
async def _dt2(ctx):
    res = await ctx["buckets"].set_field(ctx["dt_claim"], "admission_date", "2026-08-08",
                                         actor="journey-test", role="super_admin")
    assert res.get("ok"), res.get("error") or "a normal admission date was refused"


@dates.step("a discharge BEFORE it is refused")
async def _dt3(ctx):
    res = await ctx["buckets"].set_field(ctx["dt_claim"], "discharge_date", "2025-08-10",
                                         actor="journey-test", role="super_admin")
    assert not res.get("ok"), "a discharge date a year before admission was accepted"
    assert "before the admission" in (res.get("error") or ""), \
        "the refusal does not explain itself: %s" % res.get("error")


@dates.step("a discharge AFTER it saves normally")
async def _dt4(ctx):
    res = await ctx["buckets"].set_field(ctx["dt_claim"], "discharge_date", "2026-08-10",
                                         actor="journey-test", role="super_admin")
    assert res.get("ok"), res.get("error") or "a valid discharge date was refused"


@dates.step("and the reverse order is caught too")
async def _dt5(ctx):
    # Same pair, entered the other way round: saving an admission AFTER the stored discharge.
    res = await ctx["buckets"].set_field(ctx["dt_claim"], "admission_date", "2026-12-01",
                                         actor="journey-test", role="super_admin")
    assert not res.get("ok"), "an admission date after the discharge was accepted"
