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


# ─────────────────────────────────────────────────────────────────────────────
# Document intake. The rules here are the founder's (19 Sep): accept anything, never discard,
# never blame the person for our confusion, one reply per batch. These steps use no AI - they
# pin the plumbing that must hold whether or not Gemini answers.
intake = _j("doc_intake", "A complainant sends us documents", "complainant")


@intake.step("a zip is opened rather than refused")
async def _i1(ctx):
    import io as _io
    import zipfile as _zip
    buf = _io.BytesIO()
    with _zip.ZipFile(buf, "w") as z:
        z.writestr("bill.jpg", b"not really a jpeg, but the name is what routing reads")
        z.writestr("__MACOSX/._junk", b"junk")
        z.writestr("notes.txt", b"should be ignored")
    files, notes = ctx["intake"].unpack([("hospital.zip", buf.getvalue())])
    names = [n for n, _ in files]
    assert "bill.jpg" in names, "the zip was not opened: %s" % names
    assert not any(n.endswith(".txt") for n in names), "a non-document was let through"
    assert any("zip" in s for s in notes), "opening the zip was not reported"


@intake.step("an ordinary file passes straight through")
async def _i2(ctx):
    files, _ = ctx["intake"].unpack([("rejection.pdf", b"%PDF-1.4 fake")])
    assert len(files) == 1 and files[0][0] == "rejection.pdf"


@intake.step("a corrupt zip is kept whole instead of being thrown away")
async def _i3(ctx):
    files, notes = ctx["intake"].unpack([("broken.zip", b"this is not a zip at all")])
    assert len(files) == 1, "a corrupt zip lost the file"
    assert any("whole" in s for s in notes), "we did not say what happened to it"


@intake.step("an unreadable batch never claims success")
async def _i4(ctx):
    res = await ctx["intake"].accept(ctx["claim_id"], None, [("x.bin", b"\x00\x01\x02")],
                                     claim_type="health", source="journey")
    assert not res.get("ok"), "a batch of nonsense reported success"
    assert res.get("error"), "it failed without saying why"


@intake.step("and an empty batch does not crash")
async def _i5(ctx):
    res = await ctx["intake"].accept(ctx["claim_id"], None, [], claim_type="health",
                                     source="journey")
    assert not res.get("ok") and res.get("error") == "nothing_readable"


@intake.step("the reply names what arrived, not what confused us")
async def _i6(ctx):
    msg = ctx["msg"].compose("doc_batch", "en", {
        "claim_id": ctx["claim_id"], "stored": 3,
        "ticked": ["Rejection letter", "Final bill"],
        "unclear": ["KYC"], "pending": ["Claim form"]})
    assert "Rejection letter" in msg and "Final bill" in msg, "it does not say what we got"
    assert "KYC" in msg, "it does not ask for the one thing only they can fix"
    assert "Claim form" in msg, "it does not say what is still needed"
    assert "confiden" not in msg.lower() and "could not identify" not in msg.lower(), \
        "our uncertainty leaked into the complainant's message"


@intake.step("a batch we fully understood closes the loop")
async def _i7(ctx):
    msg = ctx["msg"].compose("doc_batch", "en", {
        "claim_id": ctx["claim_id"], "stored": 9,
        "ticked": ["Rejection letter"], "unclear": [], "pending": []})
    assert "everything" in msg.lower(), "a complete set was not acknowledged as complete"


@intake.step("ticking heals a claim that never had a checklist")
async def _i8(ctx):
    # 74 of 158 live claims had no checklist rows, so every tick silently did nothing. Ticking
    # now seeds the list first. Uses a claim chosen for having no rows, so the repair is real.
    import biz_nidaan_doc_checklist as _ck
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT c.claim_id, COALESCE(c.claim_type,'health') AS ct FROM nidaan_claims c "
            "WHERE COALESCE(c.claim_type,'')!='' AND NOT EXISTS "
            "(SELECT 1 FROM nidaan_claim_doc_checklist k WHERE k.claim_id=c.claim_id) "
            "LIMIT 1")).fetchone()
    if not r:
        raise Skip("every claim already has a checklist")
    row = dict(r)
    tmpl = _ck.doc_template_for(row["ct"])
    if not tmpl:
        raise Skip("no template for this claim type")
    key = tmpl[0]["key"]
    ok = await _ck.mark_doc_received(row["claim_id"], key, via="journey", doc_id=None)
    assert ok, "ticking a claim with no checklist still silently does nothing"


@intake.step("and the tick is really there afterwards")
async def _i9(ctx):
    async with aiosqlite.connect(ctx["db"]) as c:
        n = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claim_doc_checklist WHERE received=1 "
            "AND received_via='journey'")).fetchone()
    assert int(n[0]) >= 1, "the tick did not persist"


# ─────────────────────────────────────────────────────────────────────────────
# Several people work the document queue. These pin the coordination: the desk that shows the
# silence, and the guard that stops two staff chasing the same person an hour apart.
desk = _j("doc_desk", "The team sees what is waiting on paper", "staff")


@desk.step("the desk builds")
async def _dk1(ctx):
    d = await ctx["docreq"].desk()
    assert d.get("ok"), "the document desk would not build"
    ctx["desk"] = d


@desk.step("it counts what is waiting")
async def _dk2(ctx):
    d = ctx["desk"]
    for k in ("waiting", "never_asked", "gone_quiet", "needs_a_look"):
        assert isinstance(d.get(k), int), "the desk does not report '%s'" % k


@desk.step("every row says what is missing and how long it has been quiet")
async def _dk3(ctx):
    rows = ctx["desk"]["rows"]
    if not rows:
        raise Skip("nothing is waiting on documents right now")
    r = rows[0]
    for k in ("claim_id", "who", "missing", "quiet_days", "last_ask_by", "scheduled"):
        assert k in r, "a desk row is missing '%s'" % k
    assert r["missing"] > 0, "a claim with nothing outstanding reached the desk"


@desk.step("the longest silence is at the top")
async def _dk4(ctx):
    days = [r["quiet_days"] or 0 for r in ctx["desk"]["rows"]]
    assert days == sorted(days, reverse=True), \
        "the desk is not ordered by how long nobody has asked"


@desk.step("a claim nobody has ever asked is marked as such")
async def _dk5(ctx):
    rows = ctx["desk"]["rows"]
    assert all(isinstance(r["never_asked"], bool) for r in rows)


@desk.step("asking twice in a row needs a reason")
async def _dk6(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row
        r = await (await c.execute(
            "SELECT claim_id FROM nidaan_doc_requests ORDER BY req_id DESC LIMIT 1")).fetchone()
    if not r:
        raise Skip("no document ask has ever been sent, so nothing to re-ask")
    cid = int(dict(r)["claim_id"])
    last = await ctx["docreq"].recent_ask(cid)
    assert last.get("asked"), "the last ask on this claim cannot be read back"
    assert "by" in last and "days" in last, "it does not say who asked or when"


# ─────────────────────────────────────────────────────────────────────────────
# Alerts people will actually read. Both of these fired for real and told nobody anything: a
# sticker escalated as an ignored customer every three hours, and a standing data gap repeated
# itself every twelve. An alarm that cries wolf is worse than no alarm.
alerts = _j("alerts", "Alerts only fire when something is wrong", "staff")


@alerts.step("a sticker is not an unanswered conversation")
async def _al1(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        await c.execute(
            "INSERT INTO nidaan_wa_messages (direction, msisdn, msg_type, body, status, "
            "created_at, sender) VALUES ('in','919999000001','sticker','','received',"
            "datetime('now','-300 minutes'),'customer')")
        await c.commit()
    rows = await ctx["nnot"]._unanswered_whatsapp(180)
    assert not any(r["msisdn"] == "919999000001" for r in rows), \
        "a sticker is still being escalated as an ignored customer"


@alerts.step("an empty message with nothing to read is not either")
async def _al2(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        await c.execute(
            "INSERT INTO nidaan_wa_messages (direction, msisdn, msg_type, body, media_id, "
            "status, created_at, sender) VALUES ('in','919999000002','text','','','received',"
            "datetime('now','-300 minutes'),'customer')")
        await c.commit()
    rows = await ctx["nnot"]._unanswered_whatsapp(180)
    assert not any(r["msisdn"] == "919999000002" for r in rows), \
        "an empty inbound is still counted as a question"


@alerts.step("but a real question still is")
async def _al3(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        await c.execute(
            "INSERT INTO nidaan_wa_messages (direction, msisdn, msg_type, body, status, "
            "created_at, sender) VALUES ('in','919999000003','text','Sir mera claim ka kya "
            "hua?','received',datetime('now','-300 minutes'),'customer')")
        await c.commit()
    rows = await ctx["nnot"]._unanswered_whatsapp(180)
    assert any(r["msisdn"] == "919999000003" for r in rows), \
        "a real unanswered question is no longer being raised — the fix went too far"


@alerts.step("a standing data gap never pages anyone")
async def _al4(ctx):
    hw = ctx["hw"]
    for name in ("Branch login — a way in", "Email sending allowance", "Contact reachability"):
        assert name not in hw._CRITICAL, "'%s' still wakes people up" % name
        assert name in hw._GAPS, "'%s' is not classified as a gap" % name


@alerts.step("something genuinely broken still does")
async def _al5(ctx):
    hw = ctx["hw"]
    for name in ("Database", "Branch login — code delivery", "Payments (Razorpay)"):
        assert name in hw._CRITICAL, "'%s' would no longer alarm anybody" % name


# ─────────────────────────────────────────────────────────────────────────────
# Escalation. The founder's rule for this whole stage is that people act and the system only
# makes the timing visible, so these check that the clock is RIGHT and that nothing sends itself.
esc = _j("escalation", "The escalation clock tells a person what is due", "staff")


@esc.step("the config correction applies, and applies only once")
async def _e0(ctx):
    # It runs at startup via ensure_seeded(). Running it HERE proves the migration itself works
    # rather than assuming a deploy did it, and running it twice proves it is idempotent - these
    # are UPDATEs against live config, so a second pass must change nothing.
    first = await ctx["buckets"]._apply_config_fixes()
    second = await ctx["buckets"]._apply_config_fixes()
    assert second == 0, "the correction is not idempotent — it changed %d more row(s)" % second
    ctx["cfg_fixed"] = first


@esc.step("the reminders are dates, not yes/no")
async def _e1(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row
        rows = {r["field_key"]: dict(r) for r in await (await c.execute(
            "SELECT field_key, field_type, active FROM nidaan_bucket_fields "
            "WHERE bucket_key='escalation'")).fetchall()}
    for k in ("esc_reminder_1", "esc_reminder_2", "esc_reminder_3"):
        assert rows.get(k, {}).get("field_type") == "date", \
            "%s is still a %s" % (k, rows.get(k, {}).get("field_type"))


@esc.step("the grievance reference is gone")
async def _e2(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        r = await (await c.execute(
            "SELECT active FROM nidaan_bucket_fields WHERE bucket_key='escalation' "
            "AND field_key='grievance_ref'")).fetchone()
    assert (not r) or int(r[0]) == 0, "the grievance reference field is still shown"


@esc.step("no yes/no answer is left stranded in a date box")
async def _e3(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        n = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claim_fields WHERE field_key LIKE 'esc_reminder_%' "
            "AND value IN ('yes','no','Yes','No')")).fetchone()
    assert int(n[0]) == 0, "%s reminder field(s) still hold a yes/no answer" % n[0]


@esc.step("recording the escalation date IS escalating")
async def _e4(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row
        r = await (await c.execute(
            "SELECT claim_id FROM nidaan_claims WHERE pipeline_stage='escalation' "
            "LIMIT 1")).fetchone()
    if not r:
        raise Skip("no claim is in Escalation right now")
    cid = int(dict(r)["claim_id"])
    ctx["esc_claim"] = cid
    async with _sq.connect(ctx["db"]) as c:
        await c.execute("UPDATE nidaan_claims SET pipeline_sub='pending' WHERE claim_id=?", (cid,))
        await c.commit()
    from datetime import datetime as _dt, timedelta as _td
    ctx["esc_started"] = (_dt.utcnow() - _td(days=35)).strftime("%Y-%m-%d")
    res = await ctx["buckets"].set_field(cid, "escalation_date", ctx["esc_started"],
                                         actor="journey-test", role="super_admin")
    assert res.get("ok"), res.get("error")
    async with _sq.connect(ctx["db"]) as c:
        sub = (await (await c.execute(
            "SELECT pipeline_sub FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone())[0]
    assert sub == "escalated", \
        "the claim is still '%s' after its escalation date was recorded" % sub


@esc.step("the clock says which reminder is due, one at a time")
async def _e5(ctx):
    if not ctx.get("esc_claim"):
        raise Skip("no escalated claim to measure")
    d = await ctx["buckets"].escalation_due()
    assert d.get("ok")
    mine = [r for r in d["reminders"] if r["claim_id"] == ctx["esc_claim"]]
    assert mine, "a claim escalated well past day 10 is not showing a reminder as due"
    assert mine[0]["number"] == 1, "it skipped to reminder %d" % mine[0]["number"]
    assert mine[0]["overdue_by"] >= 0


@esc.step("sending reminder one moves the clock to reminder two")
async def _e6(ctx):
    if not ctx.get("esc_claim"):
        raise Skip("no escalated claim to measure")
    from datetime import datetime as _dt, timedelta as _td
    sent_on = (_dt.utcnow() - _td(days=24)).strftime("%Y-%m-%d")
    await ctx["buckets"].set_field(ctx["esc_claim"], "esc_reminder_1", sent_on,
                                   actor="journey-test", role="super_admin")
    d = await ctx["buckets"].escalation_due()
    mine = [r for r in d["reminders"] if r["claim_id"] == ctx["esc_claim"]]
    assert mine and mine[0]["number"] == 2, \
        "after the first reminder the clock should ask for the second"


@esc.step("after all three, it asks for Lokpal instead of a fourth reminder")
async def _e7(ctx):
    if not ctx.get("esc_claim"):
        raise Skip("no escalated claim to measure")
    from datetime import datetime as _dt, timedelta as _td
    for f, back in (("esc_reminder_2", 14), ("esc_reminder_3", 4)):
        on = (_dt.utcnow() - _td(days=back)).strftime("%Y-%m-%d")
        await ctx["buckets"].set_field(ctx["esc_claim"], f, on,
                                       actor="journey-test", role="super_admin")
    d = await ctx["buckets"].escalation_due()
    assert not [r for r in d["reminders"] if r["claim_id"] == ctx["esc_claim"]], \
        "it is still asking for a fourth reminder"
    assert [r for r in d["lokpal"] if r["claim_id"] == ctx["esc_claim"]], \
        "three reminders sent and no reply, but Lokpal was not raised"


@esc.step("and it still moves nothing by itself")
async def _e8(ctx):
    if not ctx.get("esc_claim"):
        raise Skip("no escalated claim to measure")
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        stage = (await (await c.execute(
            "SELECT pipeline_stage FROM nidaan_claims WHERE claim_id=?",
            (ctx["esc_claim"],))).fetchone())[0]
    assert stage == "escalation", \
        "the claim moved itself to '%s' — a Lokpal filing is a person's decision" % stage


@esc.step("claims escalated before the rule existed are corrected too")
async def _e9(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        n = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claims c WHERE c.pipeline_stage='escalation' "
            "AND COALESCE(c.pipeline_sub,'') IN ('','pending') AND EXISTS "
            "(SELECT 1 FROM nidaan_claim_fields f WHERE f.claim_id=c.claim_id "
            " AND f.field_key='escalation_date' AND TRIM(COALESCE(f.value,'')) != '')"
        )).fetchone()
    assert int(n[0]) == 0, \
        "%d claim(s) still show 'Escalation Pending' while holding an escalation date" % n[0]
