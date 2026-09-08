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
}

# Blockers that mean the next move is OURS. Both are internal; the difference is only who.
OURS = ("none", "internal")


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
        if l2 != "paid":
            # Reviewed, we said we can fight, and the work has not been paid for. This is the
            # gap the whole business is losing cases in.
            stage, blocker = "conversion", "complainant"
            flags.append("fee_unpaid")
        elif docs_total and docs_done >= docs_total:
            stage, blocker = "drafting", "internal"
        else:
            stage, blocker = "documentation", "complainant"
            if docs_total:
                flags.append("docs_short")
    elif status in ("intimated", "assigned", "in_review", "review_delivered"):
        stage, blocker = "review", "internal"
        flags.append("unreviewed")
    else:
        stage, blocker = "intake", "none"

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

    return {
        "stage": stage,
        "stage_label": STAGE_LABEL.get(stage, stage),
        "blocker": blocker,
        "blocker_label": BLOCKER_LABEL.get(blocker, blocker),
        "flags": sorted(set(flags)),
        "age_days": age,
        "patience_days": patience,
        "over_by": (age - patience) if (age is not None and patience and age > patience) else 0,
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
            "blocker, blocker_note, blocker_by, hold_until "
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
