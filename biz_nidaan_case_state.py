"""
NidaanPartner — WHERE IS THIS CASE, AND WHAT IS IT WAITING FOR.

`status` answers "what happened last". It does not answer the two questions the office actually
runs on: where the case sits in the legal journey, and who owes the next move. Those got carried
in people's heads, which is why a case can sit for eight weeks without anyone noticing.

Three fields, deliberately independent:

  STAGE    where it is in the journey        one value, moves forward
  BLOCKER  what we are waiting for RIGHT NOW one value, changes often
  FLAGS    what is wrong or urgent           any number at once

The important one is BLOCKER. When it reads `none`, nobody outside is holding this up — WE owe
the next move, and the case belongs at the top of somebody's list today. That single field turns
"what should I work on" from a judgement call into a sort order.

DERIVED FIRST, OVERRIDDEN WHEN A PERSON KNOWS BETTER.
Stage and blocker are computed from columns the live flows already maintain, so every case has a
sensible state from day one with no backfill to get wrong. On top of that, a person can say what
a case is actually waiting for — no derivation can know what someone was told on a phone call.
An empty override means "keep deriving", which is why adding this to live cases changed none of
them.

A park is the one override with a rule attached: it needs a reason and an end date, and when the
date passes the case rejoins the queue by itself. An open-ended park is precisely how a case
disappears for a year.

Every rule here is arithmetic over dates and existing values. No AI decides where a case is.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.case_state")
DB_PATH = db.DB_PATH

# ── the journey ──────────────────────────────────────────────────────────────
STAGES = ("intake", "review", "conversion", "consolidation", "documentation", "drafting",
          "representation", "escalation", "lokpal", "outcome", "settlement", "closed")

STAGE_LABEL = {
    "intake": "Intake", "review": "Review", "conversion": "Conversion",
    "consolidation": "Consolidation", "documentation": "Documents", "drafting": "Drafting",
    "representation": "With the insurer", "escalation": "Escalation", "lokpal": "Ombudsman",
    "outcome": "Outcome", "settlement": "Settlement", "closed": "Closed",
}

# Who we are waiting for. `none` means us.
BLOCKERS = ("none", "complainant", "insurer", "lokpal", "internal", "hold")
BLOCKER_LABEL = {
    "none": "Us — nobody else is holding this up",
    "complainant": "The complainant",
    "insurer": "The insurance company",
    "lokpal": "The Ombudsman's office",
    "internal": "A reviewer or approver here",
    "hold": "Paused deliberately",
}

# How long a stage should take before it is worth looking at. Days.
# Deliberately generous — a flag that fires on everything is a flag nobody reads.
STAGE_PATIENCE = {
    "intake": 2, "review": 5, "conversion": 7, "consolidation": 5,
    "documentation": 20, "drafting": 5, "representation": 35,
    "escalation": 20, "lokpal": 90, "outcome": 7, "settlement": 14,
}

FLAG_LABEL = {
    "stalled": "Nothing has moved for too long",
    "no_contact": "We cannot reach this person",
    "fee_unpaid": "Work is waiting on a fee",
    "filing_window": "The one-year Ombudsman window is closing",
    "unreviewed": "Waiting on a reviewer",
    "docs_short": "Documents still outstanding",
    "no_email": "No email address — insurer and Ombudsman mail has nowhere to go",
    "no_phone": "No phone number — we cannot reach or verify this person",
    "no_timeline": "Nothing recorded on this case",
    "hold_expired": "The park has ended — this is ours again",
    "awaiting_l2_start": "Paid and winnable — Level-2 work has not been started",
}

# Blockers that mean the next move is OURS. Both are internal; the difference is only who.
OURS = ("none", "internal")

# ── the post-L2 pipeline ─────────────────────────────────────────────────────
# Up to L2, the stage can be worked out: a review outcome and a payment are facts we already
# hold. After L2 it cannot. "The consolidation is finished" is a judgement, and no column proves
# it — so from here a case moves because a person says it moved, bucket by bucket.
#
# This is also the gate. A case is in a pipeline bucket ONLY once it has been put there, which is
# what stops Drafting and Documents from filling up with the whole book. `pipeline_stage` empty
# means "not in the pipeline"; the pre-L2 stages carry on being derived exactly as before.
PIPELINE = ("consolidation", "documentation", "drafting", "representation",
            "escalation", "lokpal", "outcome", "settlement")

# Stages that exist before the pipeline. These stay derived.
PRE_L2 = ("intake", "review", "conversion")


def next_stage(stage: str) -> str:
    """The bucket after this one. "" at the end of the line (settlement → closed is its own act)."""
    try:
        i = PIPELINE.index(stage)
    except ValueError:
        return ""
    return PIPELINE[i + 1] if i + 1 < len(PIPELINE) else ""


def l2_ready(claim: dict) -> bool:
    """Is this case qualified to enter the post-L2 pipeline?

    Two facts, both already recorded, both required: we reviewed it and said it can be fought,
    AND the L2 fee was paid. Reviewing alone is not qualification — 45 live cases sit at
    can_fight with no payment, and putting those into the pipeline would bury the work that has
    actually been bought.
    """
    return ((claim.get("review_outcome") or "").lower() == "can_fight"
            and (claim.get("l2_payment_status") or "").lower() == "paid")


def in_pipeline(claim: dict) -> bool:
    return (claim.get("pipeline_stage") or "").strip().lower() in PIPELINE


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(str(ts)[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _days_since(ts) -> int | None:
    t = _parse(ts)
    return None if not t else max(0, (datetime.utcnow() - t).days)


def _parse_day(v):
    """A plain YYYY-MM-DD, as DATE columns hand it back. None if it is not one."""
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# Calendar dates belong to the calendar the office and the complainant share, which is IST.
# The server stores timestamps in UTC and runs on European local time, so three different
# "today"s exist at once — between 18:30 and midnight IST, UTC is still on yesterday. A park
# validated against UTC would reject a date the user can plainly see is tomorrow, or accept one
# that has already gone. Anything a human picks off a calendar is compared in IST.
IST = timezone(timedelta(hours=5, minutes=30))


def _today_ist():
    return datetime.now(IST).date()


def derive(claim: dict, *, docs_done: int = 0, docs_total: int = 0,
           last_activity=None) -> dict:
    """Where this case is, what it waits for, and what is wrong with it.

    Pure function over one claim row — no I/O, so it is cheap to run over a whole list and
    trivial to reason about. `claim` is a nidaan_claims row as a dict.
    """
    status = (claim.get("status") or "").lower()
    outcome = (claim.get("review_outcome") or "").lower()
    l2 = (claim.get("l2_payment_status") or "").lower()
    flags: list[str] = []

    # ── stage ────────────────────────────────────────────────────────────────
    if claim.get("archived"):
        stage, blocker = "closed", "none"
    elif status in ("closed", "withdrawn", "resolved_lost"):
        stage, blocker = "closed", "none"
    elif status == "resolved_won":
        stage, blocker = "settlement", "complainant"
    elif outcome == "no_scope":
        stage, blocker = "closed", "none"
    elif status == "in_negotiation":
        stage, blocker = "representation", "insurer"
    elif outcome == "can_fight":
        # Everything here is pre-pipeline by definition: a case that HAS been started is caught by
        # the pipeline override further down. So this branch never reaches past Conversion.
        #
        # It used to derive paid cases straight into Documents or Drafting, which put cases into
        # post-L2 buckets that nobody had started — the buckets then held a mixture of work being
        # done and work merely qualified for, and "who is on duty for Documents" became a question
        # about a number that was not real. A paid case waits at the gate until someone starts it.
        stage = "conversion"
        if l2 != "paid":
            # Reviewed, we said we can fight, and the work has not been paid for. This is the
            # gap the whole business is losing cases in.
            blocker = "complainant"
            flags.append("fee_unpaid")
        else:
            # Paid and winnable, and not yet begun. Nobody outside is holding this up — we are.
            blocker = "internal"
            flags.append("awaiting_l2_start")
            if docs_total and docs_done < docs_total:
                flags.append("docs_short")
    elif status in ("intimated", "assigned", "in_review", "review_delivered"):
        stage, blocker = "review", "internal"
        flags.append("unreviewed")
    else:
        stage, blocker = "intake", "none"

    # ── the pipeline wins, once a person has put the case in it ──────────────
    # Derivation is a good guess about a case nobody has taken charge of. The moment someone
    # moves a case into a bucket, the guess is no longer the truth — their decision is. Kept
    # above the blocker override on purpose: the two are independent, and a case can be parked
    # or waiting on the insurer while sitting in any bucket.
    pipe = (claim.get("pipeline_stage") or "").strip().lower()
    if pipe in PIPELINE and stage != "closed":
        stage = pipe
        if pipe == "representation":
            blocker = "insurer"
        elif pipe == "lokpal":
            blocker = "lokpal"
        elif pipe in ("documentation", "settlement"):
            blocker = "complainant"
        else:
            blocker = "internal"

    # ── an explicit override beats the derivation ────────────────────────────
    # No derivation can know what someone was told on a phone call. When a person says what a
    # case is waiting for, that wins — until a park expires, at which point the case rejoins the
    # queue on its own rather than staying quietly hidden.
    override = (claim.get("blocker") or "").strip().lower()
    if override == "hold":
        until = _parse_day(claim.get("hold_until"))
        if until and until >= _today_ist():
            blocker = "hold"
        else:
            flags.append("hold_expired")      # the park ran out; it is ours again
    elif override in BLOCKERS and stage != "closed":
        blocker = override

    # ── flags ────────────────────────────────────────────────────────────────
    # Age is measured from the last thing that ACTUALLY happened, not from any touch: a remark
    # or a re-read must never look like progress, or the number becomes gameable.
    # In the pipeline, age is measured from the moment the case entered THIS bucket. A case three
    # weeks into drafting is a different problem from one three weeks into the pipeline, and the
    # patience figures are per-bucket, so they have to be compared against a per-bucket clock.
    if pipe in PIPELINE and claim.get("pipeline_stage_at"):
        age = _days_since(claim.get("pipeline_stage_at"))
    else:
        age = _days_since(last_activity or claim.get("last_status_at") or claim.get("created_at"))
    patience = STAGE_PATIENCE.get(stage)
    if age is not None and patience and age > patience and stage != "closed":
        flags.append("stalled")

    # "Nothing recorded" is not the same as "nothing happened". The activity timeline is written
    # only by the WhatsApp and document flows today — a review, a payment or a status change
    # leaves no row. So this flag means the case has no history we can SEE, which is worth
    # knowing either way: it is either genuinely untouched, or being worked somewhere the system
    # cannot observe. The second is the more useful finding.
    if not last_activity and (_days_since(claim.get("created_at")) or 0) > 2 and stage != "closed":
        flags.append("no_timeline")

    # Split, because a missing phone and a missing email have different consequences and
    # different fixes: one blocks reaching the person, the other blocks the entire correspondence
    # the case runs on.
    phone = (claim.get("complainant_phone") or claim.get("insured_phone") or "").strip()
    email = (claim.get("complainant_email") or claim.get("insured_email") or "").strip()
    if stage != "closed":
        if not phone:
            flags.append("no_phone")
        if not email:
            flags.append("no_email")

    # The one-year window to reach the Ombudsman, counted from the insurer's rejection.
    # No rejection date is captured today — claim_event_date is the closest proxy the schema has.
    # When intake starts capturing the insurer's rejection date (it must, for this clock to mean
    # anything), it is read here first and the proxy falls away.
    rej = _parse(claim.get("rejection_date")) or _parse(claim.get("claim_event_date"))
    if rej and stage not in ("closed", "settlement", "outcome"):
        left = 365 - (datetime.utcnow() - rej).days
        if left <= 90:
            flags.append("filing_window")

    # Can we PROVE this bucket's work is finished? Only where a column says so. Documents is the
    # one honest case: the checklist is complete. Everywhere else the answer is a judgement, and
    # claiming otherwise would move cases forward on a guess.
    ready = bool(pipe == "documentation" and docs_total and docs_done >= docs_total)

    return {
        "stage": stage,
        "stage_label": STAGE_LABEL.get(stage, stage),
        "blocker": blocker,
        "blocker_label": BLOCKER_LABEL.get(blocker, blocker),
        "flags": sorted(set(flags)),
        "age_days": age,
        "patience_days": patience,
        "over_by": (age - patience) if (age is not None and patience and age > patience) else 0,
        # Pipeline facts, so every screen answers "can this move, and to where?" the same way.
        "in_pipeline": pipe in PIPELINE,
        "l2_ready": l2_ready(claim),
        "next_stage": next_stage(pipe) if pipe in PIPELINE else "",
        "next_stage_label": STAGE_LABEL.get(next_stage(pipe), "") if pipe in PIPELINE else "",
        "ready_to_move": ready,
        "pipeline_by": (claim.get("pipeline_by") or ""),
    }


async def _checklist_counts(claim_ids: list) -> dict:
    """{claim_id: (done, total)} for required documents. Best-effort — never blocks the board."""
    out: dict = {}
    if not claim_ids:
        return out
    try:
        ph = ",".join("?" * len(claim_ids))
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            rows = await (await c.execute(
                f"SELECT claim_id, COUNT(*) total, "
                f"COALESCE(SUM(CASE WHEN received=1 THEN 1 ELSE 0 END),0) done "
                f"FROM nidaan_claim_doc_checklist WHERE claim_id IN ({ph}) AND required=1 "
                f"GROUP BY claim_id", list(claim_ids))).fetchall()
        for r in rows:
            d = dict(r)
            out[d["claim_id"]] = (int(d["done"] or 0), int(d["total"] or 0))
    except Exception as e:  # noqa: BLE001
        logger.info("checklist counts unavailable: %s", e)
    return out


async def _last_activity(claim_ids: list) -> dict:
    """{claim_id: timestamp} of the last REAL event, ignoring pure chatter.

    Notes and reads are excluded on purpose: if writing a remark counted as progress, the
    stalled flag could be silenced without the case moving an inch.
    """
    out: dict = {}
    if not claim_ids:
        return out
    try:
        ph = ",".join("?" * len(claim_ids))
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            rows = await (await c.execute(
                f"SELECT claim_id, MAX(created_at) last_at FROM nidaan_claim_activity "
                f"WHERE claim_id IN ({ph}) AND kind NOT IN ('note','wa_ack','view') "
                f"GROUP BY claim_id", list(claim_ids))).fetchall()
        for r in rows:
            d = dict(r)
            out[d["claim_id"]] = d["last_at"]
    except Exception as e:  # noqa: BLE001
        logger.info("activity lookup unavailable: %s", e)
    return out


async def board(*, stage: str = "", blocker: str = "", flag: str = "",
                assigned_to=None, limit: int = 300) -> dict:
    """Every open case with its derived state, plus counts for the filter chips.

    Ordered so the answer to "what do I do next" is the top of the list: cases nobody else is
    holding up, oldest first.
    """
    limit = max(1, min(int(limit or 300), 1000))
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT claim_id, account_id, claim_type, insured_name, complainant_name, "
            "complainant_phone, complainant_email, insured_phone, insured_email, insurer_name, "
            "status, review_outcome, l2_payment_status, disputed_amount, branch_code, "
            "assigned_to_staff_id, archived, created_at, last_status_at, "
            "blocker, blocker_note, blocker_by, hold_until, "
            "pipeline_stage, pipeline_entered_at, pipeline_stage_at, pipeline_by, "
            "raised_by_staff_id, raised_by_name, raised_via "
            "FROM nidaan_claims WHERE COALESCE(archived,0)=0 "
            "ORDER BY claim_id DESC LIMIT 2000")).fetchall()]

    ids = [r["claim_id"] for r in rows]
    counts = await _checklist_counts(ids)
    acts = await _last_activity(ids)

    items = []
    for r in rows:
        done, total = counts.get(r["claim_id"], (0, 0))
        st = derive(r, docs_done=done, docs_total=total, last_activity=acts.get(r["claim_id"]))
        items.append({
            "claim_id": r["claim_id"],
            "who": (r.get("complainant_name") or r.get("insured_name") or "").strip(),
            "insurer": r.get("insurer_name") or "",
            "claim_type": r.get("claim_type") or "",
            "amount": r.get("disputed_amount") or 0,
            "branch_code": r.get("branch_code") or "",
            "assigned_to": r.get("assigned_to_staff_id"),
            # The RAW override, so the sheet can show what a person chose rather than what was
            # worked out. Empty means nobody has overridden it.
            "blocker_set": (r.get("blocker") or ""),
            "blocker_note": (r.get("blocker_note") or ""),
            "blocker_by": (r.get("blocker_by") or ""),
            "hold_until": (r.get("hold_until") or ""),
            "docs": {"done": done, "total": total},
            "raised_by": (r.get("raised_by_name") or ""),
            "raised_via": (r.get("raised_via") or ""),
            **st,
        })

    tally_stage: dict = {}
    tally_blocker: dict = {}
    tally_flag: dict = {}
    for it in items:
        if it["stage"] == "closed":
            continue
        tally_stage[it["stage"]] = tally_stage.get(it["stage"], 0) + 1
        tally_blocker[it["blocker"]] = tally_blocker.get(it["blocker"], 0) + 1
        for f in it["flags"]:
            tally_flag[f] = tally_flag.get(f, 0) + 1

    open_items = [it for it in items if it["stage"] != "closed"]
    mine_total = 0
    if assigned_to is not None:
        try:
            _aid = int(assigned_to)
            mine_total = sum(1 for it in open_items if it["assigned_to"] == _aid)
            open_items = [it for it in open_items if it["assigned_to"] == _aid]
        except (TypeError, ValueError):
            pass
    if stage:
        open_items = [it for it in open_items if it["stage"] == stage]
    if blocker:
        open_items = [it for it in open_items if it["blocker"] == blocker]
    if flag:
        open_items = [it for it in open_items if flag in it["flags"]]

    # Ours first, then by how long it has been waiting.
    open_items.sort(key=lambda i: (i["blocker"] not in OURS, -(i["age_days"] or 0)))

    return {
        "items": open_items[:limit],
        "shown": min(len(open_items), limit),
        "matching": len(open_items),
        "open_total": sum(tally_stage.values()),
        "ours": sum(v for k, v in tally_blocker.items() if k in OURS),
        "mine_total": mine_total,
        "by_stage": tally_stage,
        "by_blocker": tally_blocker,
        "by_flag": tally_flag,
        "stage_order": [s for s in STAGES if s != "closed"],
        "labels": {"stage": STAGE_LABEL, "blocker": BLOCKER_LABEL, "flag": FLAG_LABEL},
    }


async def for_claim(claim_id: int) -> dict:
    """Derived state for one case — for the claim drawer."""
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT * FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    if not r:
        return {}
    row = dict(r)
    done, total = (await _checklist_counts([claim_id])).get(claim_id, (0, 0))
    last = (await _last_activity([claim_id])).get(claim_id)
    return derive(row, docs_done=done, docs_total=total, last_activity=last)


# ── moving a case ────────────────────────────────────────────────────────────
# Three actions, and every one of them writes to the case timeline. That is deliberate: the
# board found 40 cases with no recorded history because only the WhatsApp and document flows
# ever wrote a row. Anything a person does from the board should leave a trace, or the same
# blindness comes straight back.

async def _log(claim_id: int, kind: str, summary: str, actor: str) -> None:
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "INSERT INTO nidaan_claim_activity (claim_id, kind, channel, direction, actor, summary) "
                "VALUES (?,?,?,?,?,?)",
                (int(claim_id), kind, "web", "", (actor or "staff")[:80], summary[:400]))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("case activity log failed for %s: %s", claim_id, e)


async def _open_claim(claim_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, status, archived FROM nidaan_claims WHERE claim_id=?",
            (int(claim_id),))).fetchone()
    if not r:
        return None
    d = dict(r)
    if d.get("archived") or (d.get("status") or "") in ("closed", "withdrawn"):
        return None
    return d


async def set_blocker(claim_id: int, blocker: str, *, note: str = "", hold_until: str = "",
                      actor: str = "", actor_id: str = "") -> dict:
    """Record what a case is waiting for. Pass blocker='' to go back to deriving it.

    A park (`hold`) always needs a reason and an end date — an open-ended park is exactly how a
    case disappears for a year, so the system will not create one.
    """
    blocker = (blocker or "").strip().lower()
    if blocker and blocker not in BLOCKERS:
        return {"ok": False, "error": "That is not something a case can wait for."}
    if not await _open_claim(claim_id):
        return {"ok": False, "error": "That case is closed or does not exist."}

    if blocker == "hold":
        if not (note or "").strip():
            return {"ok": False, "error": "Say why this case is being paused — it will be read later."}
        day = _parse_day(hold_until)
        if not day:
            return {"ok": False, "error": "Pick the date this case should come back."}
        if day < _today_ist():
            return {"ok": False, "error": "That date has already passed. Pick a future date."}
        hold_until = day.strftime("%Y-%m-%d")
    else:
        hold_until = ""

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "UPDATE nidaan_claims SET blocker=?, blocker_note=?, hold_until=?, "
                "blocker_at=CURRENT_TIMESTAMP, blocker_by=? WHERE claim_id=?",
                (blocker, (note or "").strip()[:400], hold_until or None,
                 (actor or "")[:80], int(claim_id)))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("set_blocker failed for %s: %s", claim_id, e)
        return {"ok": False, "error": "Could not save that. Try again."}

    if not blocker:
        summary = "Cleared the manual status — back to being worked out automatically"
    elif blocker == "hold":
        summary = f"Paused until {hold_until} — {note.strip()}"
    else:
        summary = f"Waiting on: {BLOCKER_LABEL.get(blocker, blocker)}" + (f" — {note.strip()}" if note.strip() else "")
    await _log(claim_id, "case_blocker", summary, actor)
    return {"ok": True, "blocker": blocker, "hold_until": hold_until}


async def assign(claim_id: int, staff_id, *, actor: str = "") -> dict:
    """Hand a case to someone, or to nobody. Only an active staff member can hold a case."""
    if not await _open_claim(claim_id):
        return {"ok": False, "error": "That case is closed or does not exist."}

    name = ""
    sid = None
    if staff_id not in (None, "", 0, "0"):
        try:
            sid = int(staff_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "That is not a valid person."}
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            r = await (await c.execute(
                "SELECT name FROM nidaan_staff WHERE staff_id=? AND status='active' "
                "AND deleted_at IS NULL", (sid,))).fetchone()
        if not r:
            return {"ok": False, "error": "That person is not an active staff member."}
        name = dict(r).get("name") or f"staff #{sid}"

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute("UPDATE nidaan_claims SET assigned_to_staff_id=? WHERE claim_id=?",
                            (sid, int(claim_id)))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("assign failed for %s: %s", claim_id, e)
        return {"ok": False, "error": "Could not save that. Try again."}

    await _log(claim_id, "case_assign",
               (f"Assigned to {name}" if sid else "Assignment removed"), actor)
    return {"ok": True, "assigned_to": sid, "assigned_name": name}


async def _pipeline_row(claim_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        r = await (await c.execute(
            "SELECT claim_id, status, archived, review_outcome, l2_payment_status, "
            "pipeline_stage, pipeline_stage_at, complainant_name, insured_name "
            "FROM nidaan_claims WHERE claim_id=?", (int(claim_id),))).fetchone()
    if not r:
        return None
    d = dict(r)
    if d.get("archived") or (d.get("status") or "") in ("closed", "withdrawn"):
        return None
    return d


async def enter_pipeline(claim_id: int, *, actor: str = "") -> dict:
    """Start L2 processing — the act that puts a case into the buckets.

    Deliberately a separate decision from paying the fee. Payment says the work is bought; this
    says the office is starting it. Refused unless the case is genuinely L2-qualified, because
    the whole value of the buckets is that everything in them is work we have been paid to do.
    """
    row = await _pipeline_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case is closed or does not exist."}
    if in_pipeline(row):
        return {"ok": False, "error": "This case is already in the pipeline.",
                "stage": row.get("pipeline_stage")}
    if not l2_ready(row):
        outcome = (row.get("review_outcome") or "").lower()
        if outcome != "can_fight":
            return {"ok": False,
                    "error": "The review has not said this case can be fought yet."}
        return {"ok": False,
                "error": "The Level-2 fee has not been paid, so the work has not been bought yet."}

    first = PIPELINE[0]
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "UPDATE nidaan_claims SET pipeline_stage=?, pipeline_entered_at=CURRENT_TIMESTAMP, "
                "pipeline_stage_at=CURRENT_TIMESTAMP, pipeline_by=? WHERE claim_id=?",
                (first, (actor or "")[:80], int(claim_id)))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("enter_pipeline failed for %s: %s", claim_id, e)
        return {"ok": False, "error": "Could not save that. Try again."}

    await _log(claim_id, "case_stage",
               f"Level-2 processing started — now in {STAGE_LABEL[first]}", actor)
    return {"ok": True, "stage": first, "stage_label": STAGE_LABEL[first],
            "next_stage": next_stage(first)}


async def move_stage(claim_id: int, *, to: str = "", note: str = "", actor: str = "") -> dict:
    """Move a case to the next bucket, or to a named one.

    Backwards is allowed on purpose. Work comes back — a draft gets returned, a document turns
    out to be wrong — and a pipeline that only moves forward gets worked around within a week,
    at which point it stops describing reality. Every move is logged with who made it.
    """
    row = await _pipeline_row(claim_id)
    if not row:
        return {"ok": False, "error": "That case is closed or does not exist."}
    cur = (row.get("pipeline_stage") or "").strip().lower()
    if cur not in PIPELINE:
        return {"ok": False,
                "error": "This case has not started Level-2 processing yet."}

    to = (to or "").strip().lower() or next_stage(cur)
    if not to:
        return {"ok": False,
                "error": "This is the last bucket. Close the case from the claim itself."}
    if to not in PIPELINE:
        return {"ok": False, "error": "That is not a bucket a case can be in."}
    if to == cur:
        return {"ok": False, "error": f"This case is already in {STAGE_LABEL[cur]}."}

    back = PIPELINE.index(to) < PIPELINE.index(cur)
    if back and not (note or "").strip():
        # Forward is routine. Backward is an exception, and an exception with no reason recorded
        # is how the same mistake gets repeated.
        return {"ok": False,
                "error": "Say why this case is going back — it will be read later."}

    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute(
                "UPDATE nidaan_claims SET pipeline_stage=?, pipeline_stage_at=CURRENT_TIMESTAMP, "
                "pipeline_by=? WHERE claim_id=?",
                (to, (actor or "")[:80], int(claim_id)))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("move_stage failed for %s: %s", claim_id, e)
        return {"ok": False, "error": "Could not save that. Try again."}

    arrow = "sent back to" if back else "moved to"
    summary = f"{STAGE_LABEL[cur]} → {arrow} {STAGE_LABEL[to]}"
    if (note or "").strip():
        summary += f" — {note.strip()}"
    await _log(claim_id, "case_stage", summary, actor)
    return {"ok": True, "stage": to, "stage_label": STAGE_LABEL[to],
            "from": cur, "back": back, "next_stage": next_stage(to)}


async def auto_advance_ready(*, actor: str = "system") -> dict:
    """Move on every case whose current bucket can be PROVEN finished.

    Exactly one transition qualifies today: Documents → Drafting, when the checklist is complete.
    Nothing else is provable from a column, and moving a case on a guess is worse than leaving it
    where a person can see it. Returns what moved so the caller can say so out loud.
    """
    b = await board(limit=1000)
    moved = []
    for it in (b.get("items") or []):
        if it.get("in_pipeline") and it.get("ready_to_move") and it.get("next_stage"):
            r = await move_stage(it["claim_id"], to=it["next_stage"],
                                 actor=actor, note="every required document is in")
            if r.get("ok"):
                moved.append({"claim_id": it["claim_id"], "who": it.get("who") or "",
                              "from": it["stage"], "to": r["stage"]})
    if moved:
        logger.info("auto-advance moved %d case(s)", len(moved))
    return {"moved": moved, "count": len(moved)}


async def assignable_staff() -> list[dict]:
    """Who a case can be handed to — active staff only, with their current open load.

    The load is here for balancing, not ranking: one person holding two thirds of the work is a
    capacity problem to fix, not a performance score to publish.
    """
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            rows = [dict(r) for r in await (await c.execute(
                "SELECT s.staff_id, s.name, s.role, "
                "  (SELECT COUNT(*) FROM nidaan_claims cl WHERE cl.assigned_to_staff_id=s.staff_id "
                "     AND COALESCE(cl.archived,0)=0 "
                "     AND cl.status NOT IN ('closed','withdrawn')) open_cases "
                "FROM nidaan_staff s WHERE s.status='active' AND s.deleted_at IS NULL "
                "ORDER BY s.name")).fetchall()]
        return rows
    except Exception as e:  # noqa: BLE001
        logger.warning("assignable_staff failed: %s", e)
        return []


# ── My Desk: one screen that answers "what do I do today" ────────────────────
# The old system was folders, and people were good at it. This keeps that shape - buckets, and
# which buckets are yours today - while the machine underneath does the counting, the clocks and
# the flags. Nobody has to learn the words "stage" or "blocker" to use it.

ADMIN_ROLES = ("super_admin", "sub_super_admin")


async def coverage_gaps(buckets: list, rota: dict, lang: str = "en") -> list:
    """Buckets that have work and nobody who will actually be there to do it.

    Three different problems, and they are not equally urgent:
      NOBODY    the bucket has work and no one is rostered at all.
      ON LEAVE  everyone rostered on it is on approved leave TODAY. On paper it is covered; in
                the room it is not. This is the one that goes unnoticed, precisely because the
                rota still shows a name against it.
      SOON      everyone rostered goes on leave within the fortnight and nobody else is on it.

    Ordered by how much is actually waiting, so the first line is the one worth acting on.
    """
    import biz_nidaan as _n
    import biz_nidaan_stage_guide as _g

    on_leave_now: dict = {}
    upcoming: dict = {}
    try:
        for lv in await _n.list_staff_on_leave_now():
            on_leave_now[int(lv.get("staff_id") or 0)] = lv
    except Exception as e:  # noqa: BLE001
        logger.warning("coverage: leave-now lookup failed: %s", e)
    try:
        for lv in await _n.list_upcoming_leaves(14):
            sid = int(lv.get("staff_id") or 0)
            if sid and sid not in on_leave_now and sid not in upcoming:
                upcoming[sid] = lv
    except Exception as e:  # noqa: BLE001
        logger.warning("coverage: upcoming-leave lookup failed: %s", e)

    out = []
    for bk in buckets:
        key = bk.get("key")
        waiting = bk.get("total") or 0
        if not waiting:
            continue                       # an empty bucket cannot be a coverage problem
        on = rota.get(key) or []
        ours = bk.get("ours") or 0
        stalled = bk.get("stalled") or 0
        # Work that is OURS outranks work someone else is holding up, and anything already
        # overdue outranks both. Coverage is only worth chasing where the absence actually costs.
        heat = waiting + ours * 2 + stalled * 5

        if not on:
            out.append({"key": key, **_g.label(key, lang), "kind": "nobody",
                        "waiting": waiting, "ours": ours, "stalled": stalled,
                        "who": [], "cover": "", "until": "", "heat": heat + 10})
            continue

        away = [x for x in on if int(x.get("staff_id") or 0) in on_leave_now]
        if away and len(away) == len(on):
            lv = on_leave_now[int(away[0]["staff_id"])]
            out.append({"key": key, **_g.label(key, lang), "kind": "on_leave",
                        "waiting": waiting, "ours": ours, "stalled": stalled,
                        "who": [x.get("name") for x in away],
                        "cover": lv.get("cover_name") or "",
                        "until": lv.get("end_date") or "", "heat": heat + 40})
            continue

        soon = [x for x in on if int(x.get("staff_id") or 0) in upcoming]
        if soon and len(soon) == len(on):
            lv = upcoming[int(soon[0]["staff_id"])]
            out.append({"key": key, **_g.label(key, lang), "kind": "soon",
                        "waiting": waiting, "ours": ours, "stalled": stalled,
                        "who": [x.get("name") for x in soon],
                        "cover": lv.get("cover_name") or "",
                        "until": lv.get("start_date") or "", "heat": heat})

    out.sort(key=lambda g: -g["heat"])
    return out


async def desk(staff_id, role: str = "", lang: str = "en") -> dict:
    """Everything one person needs on opening ops: am I on duty, what is on fire, what is mine."""
    import biz_nidaan as _n
    import biz_nidaan_stage_guide as _g

    b = await board(limit=1000)
    items = b.get("items") or []

    # Who is on which duty today, so nobody has to ask across the room.
    rota: dict = {}
    mine: list = []
    try:
        for r in await _n.list_support_reps():
            if not r.get("on_duty"):
                continue
            d = r.get("duty") or "support"
            rota.setdefault(d, []).append({"staff_id": r.get("staff_id"),
                                           "name": r.get("staff_name") or ("#%s" % r.get("staff_id"))})
            if staff_id and int(r.get("staff_id") or 0) == int(staff_id):
                mine.append(d)
    except Exception as e:  # noqa: BLE001
        logger.warning("desk rota failed: %s", e)

    def _count(stage):
        rows = [i for i in items if i["stage"] == stage]
        return {
            "total": len(rows),
            "ours": sum(1 for i in rows if i["blocker"] in OURS),
            "stalled": sum(1 for i in rows if "stalled" in i["flags"]),
            "mine": sum(1 for i in rows if staff_id and i.get("assigned_to") == int(staff_id)),
        }

    # Who sees what. An admin runs the floor and needs every bucket. Everyone else gets the
    # buckets they are rostered on - a screen showing another team's work is a screen that buries
    # your own. A person always keeps sight of cases assigned to them by name, wherever those sit,
    # because an assignment is a promise that outlives a rota.
    is_admin = (role or "") in ADMIN_ROLES
    mine_set = set(mine)
    has_assigned = {i["stage"] for i in items
                    if staff_id and i.get("assigned_to") == int(staff_id)}

    all_buckets = []
    for st in STAGES:
        if st == "closed":
            continue
        c = _count(st)
        if not c["total"] and st not in mine_set:
            continue          # an empty bucket nobody is rostered on is just noise
        all_buckets.append({"key": st, **_g.label(st, lang), "guide": _g.guide(st, lang),
                            "on_duty": rota.get(st, []), "yours": st in mine_set, **c})

    if is_admin:
        buckets = all_buckets
    else:
        buckets = [b for b in all_buckets
                   if b["key"] in mine_set or b["key"] in has_assigned]

    # THE MAP. The detailed cards above are deliberately filtered - an empty bucket nobody is on
    # is noise on a working screen. But filtering them away also hid the SHAPE of the journey, so
    # a person looking at three cards could not tell there are eleven stages or what order they
    # run in. This is the whole route, always, counts and all, with the empty ones visibly empty.
    # Everyone sees it: it is a map, not case data.
    journey = []
    for st in PRE_L2 + PIPELINE:
        c = _count(st)
        journey.append({"key": st, **_g.label(st, lang),
                        "total": c["total"], "ours": c["ours"], "stalled": c["stalled"],
                        "on_duty": [x["name"] for x in rota.get(st, [])],
                        "yours": st in mine_set,
                        "gate": st == PIPELINE[0],     # where L2 begins
                        "pre_l2": st in PRE_L2})

    # The channels a person can be rostered onto sit alongside the case buckets.
    channels = []
    for ch in ("support", "whatsapp"):
        if not is_admin and ch not in mine_set:
            continue
        channels.append({"key": ch, **_g.label(ch, lang), "guide": _g.guide(ch, lang),
                         "on_duty": rota.get(ch, []), "yours": ch in mine_set})

    # ON FIRE — deliberately short. A list of forty is a list nobody reads, so this is capped and
    # every line says WHY in words, not in a flag name.
    def _why(i):
        if "hold_expired" in i["flags"]:
            return "the pause has ended - it is ours again"
        if "filing_window" in i["flags"]:
            return "the one-year Ombudsman window is closing"
        if "no_email" in i["flags"] and i["stage"] in ("consolidation", "representation", "escalation", "lokpal"):
            return "no email address, and this stage runs on email"
        if i["blocker"] in OURS and i.get("over_by", 0) > 0:
            return "waiting on us for %d days longer than it should" % i["over_by"]
        if "stalled" in i["flags"]:
            return "nothing has moved for %d days" % (i.get("age_days") or 0)
        if "awaiting_l2_start" in i["flags"]:
            return "paid and winnable, but nobody has started the Level-2 work"
        if "fee_unpaid" in i["flags"]:
            return "we said we can win it, but the fee has not been paid"
        if "unreviewed" in i["flags"]:
            return "waiting for a reviewer to decide"
        if "docs_short" in i["flags"]:
            d = i.get("docs") or {}
            return "%d of %d documents still to come" % (
                max(0, (d.get("total") or 0) - (d.get("done") or 0)), d.get("total") or 0)
        if "no_email" in i["flags"]:
            return "no email address on file"
        if "no_phone" in i["flags"]:
            return "no phone number on file"
        if "no_timeline" in i["flags"]:
            return "nothing has ever been recorded on this case"
        return "needs a look"

    def _heat(i):
        h = i.get("over_by", 0) or 0
        if "filing_window" in i["flags"]:
            h += 500                       # a legal deadline outranks everything
        if "hold_expired" in i["flags"]:
            h += 100
        if i["blocker"] in OURS:
            h += 50                        # nobody else is holding this up
        return h

    hot = sorted([i for i in items if i["flags"] or i.get("over_by", 0) > 0],
                 key=_heat, reverse=True)
    # Today's list is scoped exactly like the buckets: an admin sees the floor, everyone else
    # sees their own buckets and their own cases. Being shown work you are not allowed to touch
    # is how a priority list stops being read.
    if not is_admin:
        hot = [i for i in hot
               if i["stage"] in mine_set or (staff_id and i.get("assigned_to") == int(staff_id))]
    mine_hot = [i for i in hot if staff_id and i.get("assigned_to") == int(staff_id)]
    on_fire = (mine_hot + [i for i in hot if i not in mine_hot])[:8]

    # Cases sitting in a finished bucket, waiting only for someone to press the button.
    ready = [i for i in items if i.get("ready_to_move")
             and (is_admin or i["stage"] in mine_set
                  or (staff_id and i.get("assigned_to") == int(staff_id)))]

    # Paid for, reviewed as winnable, and not started. This is money already taken with no work
    # begun against it, so it is named separately rather than left inside a stage count.
    waiting_start = [i for i in items
                     if i.get("l2_ready") and not i.get("in_pipeline") and i["stage"] != "closed"]

    # Coverage is an admin's problem to fix, so only an admin is shown it. Computed over EVERY
    # bucket, not the visible ones, or an admin filtered to their own duties would stop seeing
    # the floor they are responsible for.
    coverage = await coverage_gaps(all_buckets, rota, lang) if is_admin else []

    return {
        "lang": lang,
        "is_admin": is_admin,
        "my_duties": [{"key": d, **_g.label(d, lang)} for d in mine],
        "rota": rota,
        # Buckets with work and nobody there to do it - including the case where the rota shows
        # a name but that person is on leave today.
        "coverage": coverage,
        "gaps": [{"key": g["key"], "icon": g.get("icon", ""), "name": g.get("name", ""),
                  "waiting": g["waiting"]} for g in coverage if g["kind"] == "nobody"],
        "ready_to_move": [{"claim_id": i["claim_id"], "who": i["who"], "stage": i["stage"],
                           **_g.label(i["stage"], lang),
                           "next_stage": i.get("next_stage"),
                           "next_label": i.get("next_stage_label")} for i in ready[:8]],
        "ready_count": len(ready),
        "waiting_start": [{"claim_id": i["claim_id"], "who": i["who"],
                           "age_days": i.get("age_days")} for i in waiting_start[:8]],
        "waiting_start_count": len(waiting_start),
        "buckets": buckets,
        "journey": journey,
        "channels": channels,
        "on_fire": [{"claim_id": i["claim_id"], "who": i["who"], "stage": i["stage"],
                     **_g.label(i["stage"], lang),
                     "why": _why(i), "age_days": i.get("age_days"),
                     "mine": bool(staff_id and i.get("assigned_to") == int(staff_id))}
                    for i in on_fire],
        "totals": {"open": b.get("open_total", 0), "ours": b.get("ours", 0),
                   "mine": sum(1 for i in items if staff_id and i.get("assigned_to") == int(staff_id))},
    }
