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


# ─────────────────────────────────────────────────────────────────────────────
# The founder's flow map, walked branch by branch:
#
#   Escalated ──no reply──> reminder 1 → 2 → 3 ──> Lokpal
#             └─reply──┬── yes ──────────────────> Complete
#                      ├── no ───────────────────> Lokpal
#                      └── query ──> we answer ──┬─ yes ─> Complete
#                                                └─ no ──> Lokpal
reply = _j("escalation_reply", "What the insurer said decides where the case goes", "staff")


async def _esc_ready(ctx, sub="escalated"):
    """A claim sitting in Escalation at the step we want to test from."""
    import aiosqlite as _sq
    from datetime import datetime as _dt, timedelta as _td
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row
        r = await (await c.execute(
            "SELECT claim_id FROM nidaan_claims WHERE COALESCE(pipeline_stage,'')!='' "
            "AND COALESCE(archived,0)=0 LIMIT 1")).fetchone()
    if not r:
        raise Skip("no claim is in the pipeline")
    cid = int(dict(r)["claim_id"])
    async with _sq.connect(ctx["db"]) as c:
        await c.execute("UPDATE nidaan_claims SET pipeline_stage='escalation', pipeline_sub=? "
                        "WHERE claim_id=?", (sub, cid))
        await c.execute("DELETE FROM nidaan_claim_fields WHERE claim_id=? AND field_key LIKE "
                        "'esc%'", (cid,))
        await c.execute(
            "INSERT INTO nidaan_claim_fields (claim_id, field_key, value, updated_at) "
            "VALUES (?,'escalation_date',?,CURRENT_TIMESTAMP)",
            (cid, (_dt.utcnow() - _td(days=35)).strftime("%Y-%m-%d")))
        await c.commit()
    return cid


@reply.step("a reply cannot be recorded before we have escalated")
async def _r1(ctx):
    import aiosqlite as _sq
    cid = await _esc_ready(ctx, "pending")
    res = await ctx["buckets"].escalation_reply(cid, "accepted", note="Too early.",
                                                actor="journey-test", actor_role="super_admin")
    assert not res.get("ok"), "a reply was accepted before the case had been escalated"


@reply.step("every reply has to say what they wrote")
async def _r2(ctx):
    cid = await _esc_ready(ctx)
    res = await ctx["buckets"].escalation_reply(cid, "accepted", note="",
                                                actor="journey-test", actor_role="super_admin")
    assert not res.get("ok") and "what they wrote" in (res.get("error") or "")


@reply.step("they agreed → the case is Complete, settled at escalation")
async def _r3(ctx):
    import aiosqlite as _sq
    cid = await _esc_ready(ctx)
    res = await ctx["buckets"].escalation_reply(
        cid, "accepted", note="Insurer agreed to settle in full.",
        actor="journey-test", actor_role="super_admin")
    assert res.get("ok"), res.get("error")
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row          # without this, dict() gets a bare tuple
        r = dict(await (await c.execute(
            "SELECT pipeline_stage, pipeline_sub FROM nidaan_claims WHERE claim_id=?",
            (cid,))).fetchone())
    assert r["pipeline_stage"] == "completed", "went to '%s'" % r["pipeline_stage"]
    assert r["pipeline_sub"] == "escalation_settlement", \
        "landed on '%s' instead of the escalation-settlement step" % r["pipeline_sub"]


@reply.step("they refused → Lokpal")
async def _r4(ctx):
    import aiosqlite as _sq
    cid = await _esc_ready(ctx)
    res = await ctx["buckets"].escalation_reply(
        cid, "refused", note="Insurer upheld the repudiation.",
        actor="journey-test", actor_role="super_admin")
    assert res.get("ok"), res.get("error")
    async with _sq.connect(ctx["db"]) as c:
        stage = (await (await c.execute(
            "SELECT pipeline_stage FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone())[0]
    assert stage == "lokpal", "a refusal went to '%s'" % stage


@reply.step("they asked a question → the case stays, marked Escalation Query")
async def _r5(ctx):
    import aiosqlite as _sq
    cid = await _esc_ready(ctx)
    res = await ctx["buckets"].escalation_reply(
        cid, "query", note="Insurer wants the original discharge summary.",
        actor="journey-test", actor_role="super_admin")
    assert res.get("ok") and res.get("stayed"), "a query should not move the case"
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row          # without this, dict() gets a bare tuple
        r = dict(await (await c.execute(
            "SELECT pipeline_stage, pipeline_sub FROM nidaan_claims WHERE claim_id=?",
            (cid,))).fetchone())
    assert r["pipeline_stage"] == "escalation" and r["pipeline_sub"] == "query", \
        "ended at %s/%s" % (r["pipeline_stage"], r["pipeline_sub"])
    ctx["q_cid"] = cid


@reply.step("while they wait on us, we stop chasing them")
async def _r6(ctx):
    if not ctx.get("q_cid"):
        raise Skip("no queried claim")
    d = await ctx["buckets"].escalation_due()
    assert not [r for r in d["reminders"] if r["claim_id"] == ctx["q_cid"]], \
        "still sending reminders to an insurer who is waiting on our answer"
    assert [r for r in d["owed"] if r["claim_id"] == ctx["q_cid"]], \
        "a query we owe an answer to is not surfaced anywhere"


@reply.step("and after we answer, their yes still completes it")
async def _r7(ctx):
    import aiosqlite as _sq
    if not ctx.get("q_cid"):
        raise Skip("no queried claim")
    res = await ctx["buckets"].escalation_reply(
        ctx["q_cid"], "accepted", note="Sent the summary; insurer agreed to pay.",
        actor="journey-test", actor_role="super_admin")
    assert res.get("ok"), res.get("error")
    async with _sq.connect(ctx["db"]) as c:
        stage = (await (await c.execute(
            "SELECT pipeline_stage FROM nidaan_claims WHERE claim_id=?",
            (ctx["q_cid"],))).fetchone())[0]
    assert stage == "completed", "after a query was answered it went to '%s'" % stage


# ─────────────────────────────────────────────────────────────────────────────
# The work screen has to say WHOSE desk a claim is on and WHAT KIND of claim it is. A bucket says
# what stage it is at, which is not the same thing: "somebody in Drafting will pick it up" is how
# a claim goes quiet. These pin the contract the columns read.
own = _j("ownership", "The board says who holds each claim", "staff")


@own.step("the board returns the claim type")
async def _o1(ctx):
    b = await ctx["buckets"].board()
    assert b.get("items") is not None or b.get("rows") is not None, "the board returned nothing"
    rows = b.get("items") or b.get("rows") or []
    if not rows:
        raise Skip("no claims in the pipeline")
    assert "claim_type" in rows[0], "the board no longer carries claim_type"
    ctx["board_rows"] = rows


@own.step("and who it is assigned to")
async def _o2(ctx):
    if not ctx.get("board_rows"):
        raise Skip("no rows")
    assert "assigned_to" in ctx["board_rows"][0], "the board no longer carries assigned_to"


@own.step("only real claim handlers can be offered")
async def _o3(ctx):
    import biz_nidaan_doc_checklist as _ck
    # The dropdown offers exactly the types the checklist can build a document list for; any
    # other would be refused on save, which is a refusal we could have predicted.
    offered = {"health", "motor", "life", "travel", "property", "marine", "other"}
    known = set(_ck.TEMPLATES.keys())
    assert offered <= known, "the screen offers types with no document list: %s" % (offered - known)


@own.step("assigning a claim sticks, and unassigning it does too")
async def _o4(ctx):
    import biz_nidaan_case_state as _cs
    import aiosqlite as _sq
    _cs.DB_PATH = ctx["db"]
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row
        st = await (await c.execute(
            "SELECT staff_id FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
            "LIMIT 1")).fetchone()
    if not st or not ctx.get("board_rows"):
        raise Skip("no staff or no claims to assign")
    cid = int(ctx["board_rows"][0]["claim_id"])
    sid = int(dict(st)["staff_id"])
    res = await _cs.assign(cid, sid, actor="journey-test")
    assert res.get("ok"), res.get("error")
    async with _sq.connect(ctx["db"]) as c:
        got = (await (await c.execute(
            "SELECT assigned_to_staff_id FROM nidaan_claims WHERE claim_id=?", (cid,))).fetchone())[0]
    assert got == sid, "assignment did not stick"
    res = await _cs.assign(cid, None, actor="journey-test")
    assert res.get("ok"), "a claim could not be handed back to nobody"


@own.step("being handed a claim tells the person, once")
async def _o5(ctx):
    import biz_nidaan_case_state as _cs
    import aiosqlite as _sq
    _cs.DB_PATH = ctx["db"]
    if not ctx.get("board_rows"):
        raise Skip("no claims")
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row
        st = [dict(r) for r in await (await c.execute(
            "SELECT staff_id FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
            "LIMIT 2")).fetchall()]
    if len(st) < 2:
        raise Skip("need two staff to tell one about the other")
    cid = int(ctx["board_rows"][0]["claim_id"])
    giver, taker = int(st[0]["staff_id"]), int(st[1]["staff_id"])
    async with _sq.connect(ctx["db"]) as c:
        before = (await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_notifications WHERE event_key='case.assigned' "
            "AND claim_id=?", (cid,))).fetchone())[0]
    res = await _cs.assign(cid, taker, actor="journey-test", actor_id=giver)
    assert res.get("ok"), res.get("error")
    async with _sq.connect(ctx["db"]) as c:
        after = (await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_notifications WHERE event_key='case.assigned' "
            "AND claim_id=?", (cid,))).fetchone())[0]
    assert after > before, "the person handed the claim was never told"


@own.step("but handing it to yourself tells you nothing")
async def _o6(ctx):
    import biz_nidaan_case_state as _cs
    import aiosqlite as _sq
    _cs.DB_PATH = ctx["db"]
    if not ctx.get("board_rows"):
        raise Skip("no claims")
    cid = int(ctx["board_rows"][0]["claim_id"])
    async with _sq.connect(ctx["db"]) as c:
        c.row_factory = _sq.Row
        st = await (await c.execute(
            "SELECT staff_id FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL "
            "LIMIT 1")).fetchone()
        before = (await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_notifications WHERE event_key='case.assigned' "
            "AND claim_id=?", (cid,))).fetchone())[0]
    me = int(dict(st)["staff_id"])
    await _cs.assign(cid, me, actor="journey-test", actor_id=me)
    async with _sq.connect(ctx["db"]) as c:
        after = (await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_notifications WHERE event_key='case.assigned' "
            "AND claim_id=?", (cid,))).fetchone())[0]
    assert after == before, "somebody was told about something they did themselves"


# ─────────────────────────────────────────────────────────────────────────────
# The gap between "we told them they have a case" and "they paid us to fight it". 17 winnable
# claims were sitting in it, averaging nine days, with nobody counting.
fee = _j("awaiting_fee", "Reviewed claims waiting to be paid for are visible", "staff")


@fee.step("the list builds")
async def _af1(ctx):
    d = await ctx["stats"].awaiting_fee()
    assert d.get("ok"), "the awaiting-fee list would not build"
    ctx["fee"] = d


@fee.step("it counts what is waiting, and what is winnable")
async def _af2(ctx):
    d = ctx["fee"]
    for k in ("waiting", "winnable", "disputed_total"):
        assert isinstance(d.get(k), int), "it does not report '%s'" % k
    assert d["winnable"] <= d["waiting"], "more winnable claims than claims"


@fee.step("every row carries the three dates the founder asked for")
async def _af3(ctx):
    rows = ctx["fee"]["rows"]
    if not rows:
        raise Skip("nothing is awaiting a fee right now")
    r = rows[0]
    for k in ("started_at", "review_delivered_at", "paid_at", "days_since_review"):
        assert k in r, "a row is missing '%s'" % k
    assert r["review_delivered_at"], "a claim reached this list without a review date"


@fee.step("a claim already paid for never appears here")
async def _af4(ctx):
    import aiosqlite as _sq
    ids = [r["claim_id"] for r in ctx["fee"]["rows"]]
    if not ids:
        raise Skip("empty list")
    marks = ",".join("?" * len(ids))
    async with _sq.connect(ctx["db"]) as c:
        n = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claims WHERE claim_id IN (%s) AND "
            "(LOWER(COALESCE(l2_payment_status,''))='paid' OR "
            " LOWER(COALESCE(payment_status,'')) IN ('paid','subscription'))" % marks,
            ids)).fetchone()
    assert int(n[0]) == 0, "%s claim(s) that are already paid for are being chased" % n[0]


@fee.step("and a claim we said has no case is marked, not chased")
async def _af5(ctx):
    rows = ctx["fee"]["rows"]
    if not rows:
        raise Skip("empty list")
    for r in rows:
        assert isinstance(r.get("fightable"), bool), "a row does not say whether it is winnable"
    # The money total counts only the winnable ones — chasing a fee for a case we said cannot be
    # fought would be worse than not chasing at all.
    total = sum(int(r["amount"] or 0) for r in rows if r["fightable"])
    assert ctx["fee"]["disputed_total"] == total, "the total includes claims we said have no case"


@own.step("the board carries the insurer's own claim number")
async def _o7(ctx):
    # Every letter, email and Ombudsman form quotes it, so it belongs on the row rather than
    # three clicks inside the claim.
    b = await ctx["buckets"].board()
    rows = b.get("items") or b.get("rows") or []
    if not rows:
        raise Skip("no claims in the pipeline")
    assert "insurer_claim_no" in rows[0], "the board does not carry insurer_claim_no"


@own.step("and it is the value recorded on the claim, not a guess")
async def _o8(ctx):
    import aiosqlite as _sq
    b = await ctx["buckets"].board()
    rows = b.get("items") or b.get("rows") or []
    withnum = [r for r in rows if (r.get("insurer_claim_no") or "").strip()]
    if not withnum:
        raise Skip("no claim has an insurer claim number recorded yet")
    r = withnum[0]
    async with _sq.connect(ctx["db"]) as c:
        got = await (await c.execute(
            "SELECT value FROM nidaan_claim_fields WHERE claim_id=? AND field_key=?",
            (r["claim_id"], "insurer_claim_no"))).fetchone()
    assert got and (got[0] or "").strip() == r["insurer_claim_no"], \
        "the board shows a different claim number from the one on the claim"


# ─────────────────────────────────────────────────────────────────────────────
rem = _j("removals", "Fields nobody needed are gone", "staff")


@rem.step("the corrections apply, and only once")
async def _rm1(ctx):
    first = await ctx["buckets"]._apply_config_fixes()
    second = await ctx["buckets"]._apply_config_fixes()
    assert second == 0, "not idempotent — a second pass changed %d row(s)" % second


@rem.step("Approved by / Approved on are gone from Pending Draft")
async def _rm2(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        n = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_bucket_fields WHERE bucket_key='pending_draft' "
            "AND field_key IN ('approved_by','approved_on') AND active=1")).fetchone()
    assert int(n[0]) == 0, "%s approval field(s) are still shown" % n[0]


@rem.step("and they no longer block a claim leaving the bucket")
async def _rm3(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        n = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_bucket_fields WHERE field_key IN "
            "('approved_by','approved_on') AND required_exit=1")).fetchone()
    assert int(n[0]) == 0, "a removed field is still required before a claim can move on"


@rem.step("but what was already recorded is still readable")
async def _rm4(ctx):
    import aiosqlite as _sq
    async with _sq.connect(ctx["db"]) as c:
        n = await (await c.execute(
            "SELECT COUNT(*) FROM nidaan_claim_fields WHERE field_key IN "
            "('approved_by','approved_on')")).fetchone()
    # Deactivating a field must never delete what people wrote into it.
    assert int(n[0]) >= 1, "the values recorded against the approval fields were destroyed"


@rem.step("the health list no longer asks for past medical records")
async def _rm5(ctx):
    import biz_nidaan_doc_checklist as _ck
    keys = {d["key"] for d in _ck.doc_template_for("health")}
    assert "prior_medical" not in keys, "Past Medical Records is still on the health list"
    # And the list did not lose anything else on the way out.
    for must in ("rejection_letter", "policy_doc", "claim_form", "mail_credentials"):
        assert any(k.startswith(must[:8]) for k in keys), "the health list lost '%s'" % must


# ═══════════════════════════════════════════════════════════════════════════════
# SARATHI-AI
#
# Until 20 Sep every journey here was a NidaanPartner journey. That was fine while the two
# products were one deployment with one fate — but we are about to cut a 29,000-line file in half,
# and a safety net over one half of it is not a safety net.
#
# These exercise the Sarathi side and, above all, the SEAM: the bundle. 37 of 59 tenants were
# created by somebody buying NidaanPartner, so the handover is not an edge case — it is how most
# Sarathi tenants come into existence. It is also the one thing the founder asked about by name.
#
# Scoped to ACTIVE tenants and ACTIVE links on purpose. There is a wiped test tenant (#14,
# product_link.active=0, bundled_until long past) with no agent; asserting over every row would
# have failed on day one and taught everyone to ignore the suite.
# ═══════════════════════════════════════════════════════════════════════════════

bundle_sso = _j("bundle_sso", "A bundle subscriber opens Sarathi CRM", "subscriber")


@bundle_sso.step("their Nidaan plan actually includes the Sarathi bundle")
async def _b1(ctx):
    sub = ctx.get("bundle_sub")
    if not sub:
        raise Skip("no active Nidaan subscription on a bundle plan to exercise")
    plan = sub["plan"]
    limits = ctx["nidaan"].PLAN_LIMITS.get(plan) or {}
    assert limits.get("sarathi_bundle"), \
        "plan %r is sold with Sarathi CRM but PLAN_LIMITS does not grant it" % plan
    ctx["bundle_account_id"] = sub["account_id"]


@bundle_sso.step("the link from their Nidaan account resolves to a Sarathi tenant")
async def _b2(ctx):
    tid = await ctx["nidaan"].get_sarathi_tenant_for_nidaan(ctx["bundle_account_id"])
    assert tid, ("account #%s pays for a bundle plan but no Sarathi tenant is linked — "
                 "the CRM button would 403" % ctx["bundle_account_id"])
    ctx["tenant_id"] = int(tid)


@bundle_sso.step("that tenant exists and is not a dead account")
async def _b3(ctx):
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        t = await (await c.execute(
            "SELECT tenant_id, subscription_status, bundled_until, plan_source "
            "FROM tenants WHERE tenant_id=?", (ctx["tenant_id"],))).fetchone()
    assert t, "product_link points at tenant #%s, which does not exist" % ctx["tenant_id"]
    t = dict(t)
    assert t["subscription_status"] == "active", \
        "their Sarathi tenant is %r, so the CRM opens to a dead account" % t["subscription_status"]
    ctx["tenant_row"] = t


@bundle_sso.step("somebody is actually in that tenant — the first screen is not empty")
async def _b4(ctx):
    # The bridge creates an owner agent at provisioning time precisely so the tenant is usable on
    # first login. A tenant with no agent means a paying subscriber lands in an empty product.
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        n = (await (await c.execute(
            "SELECT COUNT(*) FROM agents WHERE tenant_id=?", (ctx["tenant_id"],))).fetchone())[0]
        owners = (await (await c.execute(
            "SELECT COUNT(*) FROM agents WHERE tenant_id=? AND role='owner'",
            (ctx["tenant_id"],))).fetchone())[0]
    assert n, "tenant #%s has no agents — the subscriber logs in to nothing" % ctx["tenant_id"]
    assert owners, "tenant #%s has agents but no owner — nobody can administer it" % ctx["tenant_id"]


# ─────────────────────────────────────────────────────────────────────────────
provisioning = _j("bundle_provisioning", "Buying NidaanPartner creates a usable Sarathi account",
                  "subscriber")


@provisioning.step("the bridge provisions a brand-new tenant")
async def _p1b(ctx):
    # Runs against the COPY, with an address nobody owns, so this can never touch a real tenant.
    email = "journey-probe@example.invalid"
    tid = await ctx["bridge"].upsert_bundle_tenant(
        email=email, owner_name="Journey Probe", firm_name="Probe Firm",
        phone="", sarathi_plan="individual", bundled_until="2099-01-01")
    assert tid, "the bundle bridge returned no tenant id"
    ctx["probe_email"], ctx["probe_tid"] = email, int(tid)


@provisioning.step("and gives it an owner, so it works on first login")
async def _p2b(ctx):
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        rows = await (await c.execute(
            "SELECT role FROM agents WHERE tenant_id=?", (ctx["probe_tid"],))).fetchall()
    roles = [dict(r)["role"] for r in rows]
    assert "owner" in roles, \
        "a freshly provisioned bundle tenant has no owner agent — it would open empty"


@provisioning.step("buying again refreshes the same tenant, it does not make a second one")
async def _p3b(ctx):
    # Renewal runs this same call. If it created a duplicate every time, one subscriber would
    # accumulate tenants and their data would scatter across them.
    again = await ctx["bridge"].upsert_bundle_tenant(
        email=ctx["probe_email"], owner_name="Journey Probe", firm_name="Probe Firm",
        phone="", sarathi_plan="gold", bundled_until="2099-06-01")
    assert int(again) == ctx["probe_tid"], \
        "a second purchase created tenant #%s instead of refreshing #%s" % (again, ctx["probe_tid"])
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        t = dict(await (await c.execute(
            "SELECT plan, bundled_until, subscription_status FROM tenants WHERE tenant_id=?",
            (ctx["probe_tid"],))).fetchone())
    assert t["plan"] == "gold", "the renewed plan was not applied (still %r)" % t["plan"]
    assert t["bundled_until"] == "2099-06-01", "the new expiry was not applied"
    assert t["subscription_status"] == "active", "renewal left the tenant inactive"


# ─────────────────────────────────────────────────────────────────────────────
bundle_end = _j("bundle_end", "Bundle access ends when the subscription does", "subscriber")


@bundle_end.step("we can find the tenants whose bundle ends on a given day")
async def _e1b(ctx):
    if not ctx.get("probe_tid"):
        raise Skip("the provisioning journey did not run, so there is nothing to find")
    rows = await ctx["bridge"].find_bundle_tenants_ending_on("2099-06-01")
    assert isinstance(rows, list), "the expiry sweep did not return a list"
    assert any(int(r.get("tenant_id", 0)) == ctx["probe_tid"] for r in rows), \
        "the sweep missed a tenant whose bundle ends that day — renewals would run on nobody"


@bundle_end.step("shortening one writes a grace date rather than cutting it dead")
async def _e2b(ctx):
    if not ctx.get("probe_tid"):
        raise Skip("nothing provisioned to shorten")
    # EARLIER than the current 2099-06-01. The first version of this step asked for a LATER date
    # and read the refusal as a bug — the bridge was right and the test was wrong.
    ok = await ctx["bridge"].shorten_bundle_tenant(tenant_id=ctx["probe_tid"],
                                                   grace_until="2099-02-01")
    assert ok is True, "shortening a lapsed bundle did not happen (returned %r)" % ok
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        t = dict(await (await c.execute(
            "SELECT bundled_until, lifetime_trial_used FROM tenants WHERE tenant_id=?",
            (ctx["probe_tid"],))).fetchone())
    assert t["bundled_until"] == "2099-02-01", \
        "the grace date was not written (still %r)" % t["bundled_until"]
    assert t["lifetime_trial_used"], \
        "an ex-bundle tenant could restart a free Sarathi trial"


@bundle_end.step("and it can only ever shorten — a lapsing bundle is never extended by accident")
async def _e3b(ctx):
    if not ctx.get("probe_tid"):
        raise Skip("nothing provisioned")
    # The guarantee that actually matters: this sweep runs unattended, and a bug that moved the
    # date FORWARD would hand people months of access nobody sold them, silently.
    out = await ctx["bridge"].shorten_bundle_tenant(tenant_id=ctx["probe_tid"],
                                                    grace_until="2099-12-31")
    assert out is False, "a later date was accepted — the bundle would be silently extended"
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        t = dict(await (await c.execute(
            "SELECT bundled_until FROM tenants WHERE tenant_id=?",
            (ctx["probe_tid"],))).fetchone())
    assert t["bundled_until"] == "2099-02-01", \
        "the date moved to %r despite the call being refused" % t["bundled_until"]


# ─────────────────────────────────────────────────────────────────────────────
tenancy = _j("tenancy", "Every Sarathi account holds together", "subscriber")


@tenancy.step("no active link points at a tenant that does not exist")
async def _t1b(ctx):
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        n = (await (await c.execute(
            "SELECT COUNT(*) FROM product_link p WHERE p.active=1 AND NOT EXISTS "
            "(SELECT 1 FROM tenants t WHERE t.tenant_id=p.sarathi_tenant_id)")).fetchone())[0]
    assert n == 0, "%d active Nidaan-to-Sarathi link(s) point at a missing tenant" % n


@tenancy.step("no agent belongs to a tenant that does not exist")
async def _t2b(ctx):
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        n = (await (await c.execute(
            "SELECT COUNT(*) FROM agents a WHERE NOT EXISTS "
            "(SELECT 1 FROM tenants t WHERE t.tenant_id=a.tenant_id)")).fetchone())[0]
    assert n == 0, "%d agent(s) belong to no tenant — their data is unreachable" % n


@tenancy.step("every LIVE bundle tenant has somebody who can use it")
async def _t3b(ctx):
    import aiosqlite
    async with aiosqlite.connect(ctx["db"]) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT t.tenant_id FROM tenants t WHERE t.plan_source='nidaan_bundle' "
            "AND t.subscription_status='active' AND NOT EXISTS "
            "(SELECT 1 FROM agents a WHERE a.tenant_id=t.tenant_id)")).fetchall()]
    assert not rows, ("%d active bundle tenant(s) have no agent: %s — those subscribers would "
                      "open the CRM and find nothing"
                      % (len(rows), ", ".join("#%s" % r["tenant_id"] for r in rows)))


# ─────────────────────────────────────────────────────────────────────────────
boundary = _j("boundary", "The wall between the two products still stands", "staff")


@boundary.step("no NidaanPartner module reaches into Sarathi's tables")
async def _w1(ctx):
    # The rule that makes a clean split possible at all (founder, 17 Aug: keep them separate).
    # Cheap to check and expensive to rediscover: every violation is a line that would have to be
    # rewritten under time pressure on the day the two apps are actually pulled apart.
    import ast as _ast
    import glob
    import os as _os
    import re as _re
    bad = []
    pat = _re.compile(r"\b(?:FROM|JOIN|INTO|UPDATE)\s+(tenants|agents|leads|customers|policies)\b",
                      _re.I)

    def _sql_literals(tree):
        """Every string literal EXCEPT docstrings — SQL lives in the first, English in the second.

        The first version of this scanned raw file text and flagged biz_nidaan_crm.py, because its
        module docstring says "create/list/update leads". A boundary check that fires on prose is
        one people switch off within a week.
        """
        docs = set()
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.Module, _ast.ClassDef, _ast.FunctionDef,
                                 _ast.AsyncFunctionDef)):
                body = getattr(node, "body", None) or []
                first = body[0] if body else None
                if isinstance(first, _ast.Expr) and isinstance(first.value, _ast.Constant) \
                        and isinstance(first.value.value, str):
                    docs.add(id(first.value))
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Constant) and isinstance(node.value, str) \
                    and id(node) not in docs:
                yield node.value

    # Scan the tree the RUN ACTUALLY LOADED, not the working directory. A bare
    # glob("biz_nidaan*.py") reads whatever cwd happens to be — which under --overlay is the
    # deployed app, not the code under test. Proven by injecting a real `FROM tenants` into the
    # overlay and watching this step stay green; same family as the overlay bug of 19 Sep.
    # biz_nidaan is always imported and rebound by the runner, so its own location is the truth.
    root = _os.path.dirname(_os.path.abspath(ctx["nidaan"].__file__))
    scanned = sorted(glob.glob(_os.path.join(root, "biz_nidaan*.py")))
    assert scanned, "found no Nidaan modules to check in %s — this check would pass blindly" % root
    ctx["boundary_scanned"] = len(scanned)
    for f in scanned:
        try:
            tree = _ast.parse(open(f, encoding="utf-8", errors="replace").read())
        except (OSError, SyntaxError):
            continue
        for lit in _sql_literals(tree):
            for m in pat.finditer(lit):
                bad.append("%s -> %s" % (_os.path.basename(f), m.group(1)))
    assert not bad, ("Nidaan code now reads Sarathi tables directly: %s. Route it through "
                     "biz_platform_bridge.py instead." % "; ".join(sorted(set(bad))[:6]))


@boundary.step("the bridge still offers everything Nidaan needs from Sarathi")
async def _w2(ctx):
    for fn in ("upsert_bundle_tenant", "shorten_bundle_tenant", "find_bundle_tenants_ending_on"):
        assert hasattr(ctx["bridge"], fn), \
            "biz_platform_bridge lost %s() — Nidaan's bundle path depends on it" % fn
