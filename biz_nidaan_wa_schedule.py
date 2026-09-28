# =============================================================================
#  biz_nidaan_wa_schedule.py — asking for documents when the person can answer
# =============================================================================
#
#  The founder's reasoning, which is the whole design:
#
#    "a person normally stuck in their job from morning to evening, typical times
#     are 9 am to 8 pm ... most people have doc at home and they spend less time
#     at home ... intelligently our team can setup reminder for document
#     collection for Sunday morning between 8am to 11am ... but again it's very
#     subjective, possible we have claim of a breakfast counter person who's very
#     busy on Sunday morning, so let's leave it to the staff's wisdom."
#
#  So this module schedules nothing by itself. A person who has spoken to the
#  complainant picks the moment, and we keep it. Everything here exists to make
#  that choice easy to express and safe to leave running:
#
#    • once, or repeating — every week on a chosen day, or every N days
#    • it stops ON ITS OWN when the documents are all in (nobody is chased for
#      papers they already sent)
#    • it stops after a set number of tries, so a schedule cannot run for ever
#    • it can be paused and restarted without losing what it was
#    • the send goes through the SAME door as every other message: the 2-a-day
#      cap, the STOP list, the template rules. A scheduled message is not a
#      privileged message.
#
#  Times are stored in UTC and shown in IST, because staff think "Sunday 9am"
#  and the server thinks in UTC — that gap is exactly where a reminder lands at
#  3am if nobody is careful.
# =============================================================================
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.wa.schedule")

DB_PATH = db.DB_PATH
IST = timezone(timedelta(hours=5, minutes=30))

MAX_SENDS_DEFAULT = 6        # a schedule that has asked six times needs a person, not a seventh
LOOK_AHEAD_MIN = 5           # the worker runs every few minutes; anything due by now goes
REPEATS = ("once", "weekly", "days")

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def ist_to_utc(date_str: str, time_str: str) -> Optional[str]:
    """'2026-09-20' + '09:00' (IST, what the staffer typed) → UTC for storage."""
    try:
        naive = datetime.strptime("%s %s" % (date_str.strip(), time_str.strip()), "%Y-%m-%d %H:%M")
        return naive.replace(tzinfo=IST).astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def utc_to_ist(ts: str) -> str:
    """Stored UTC → what a person here reads. Never show a staffer a UTC time."""
    try:
        d = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return d.astimezone(IST).strftime("%a %d %b, %I:%M %p")
    except Exception:
        return str(ts or "")


def _next_after(current_utc: str, repeat: str, every: int, weekday: Optional[int]) -> Optional[str]:
    """When this schedule should fire again, or None if it was a one-off.

    Weekly keeps the TIME OF DAY the staffer chose and moves to the next chosen weekday — worked
    out in IST, so "Sunday 9am" stays Sunday 9am even across a UTC date boundary."""
    try:
        cur = datetime.strptime(str(current_utc)[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc).astimezone(IST)
    except Exception:
        return None
    if repeat == "weekly":
        target = weekday if weekday is not None else cur.weekday()
        ahead = (target - cur.weekday()) % 7
        nxt = cur + timedelta(days=(ahead or 7))
    elif repeat == "days":
        nxt = cur + timedelta(days=max(1, int(every or 1)))
    else:
        return None
    return nxt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def create(claim_id: int, *, when_date: str, when_time: str, repeat: str = "once",
                 every: int = 7, weekday: Optional[int] = None, note: str = "",
                 max_sends: int = MAX_SENDS_DEFAULT, stop_when_complete: bool = True,
                 by: str = "", by_id=None) -> dict:
    repeat = (repeat or "once").strip().lower()
    if repeat not in REPEATS:
        return {"ok": False, "error": "Choose once, weekly, or every few days."}
    at = ist_to_utc(when_date, when_time)
    if not at:
        return {"ok": False, "error": "That date and time did not make sense."}
    if at <= datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"):
        return {"ok": False, "error": "That moment has already passed — pick a later one."}
    if repeat == "weekly" and weekday is None:
        # Default to the weekday they picked, so "weekly" means "this day, every week".
        try:
            weekday = datetime.strptime(when_date.strip(), "%Y-%m-%d").weekday()
        except Exception:
            weekday = None
    async with aiosqlite.connect(DB_PATH) as conn:
        cur = await conn.execute(
            """INSERT INTO nidaan_wa_schedule
               (claim_id, next_at, repeat_rule, repeat_every, repeat_weekday, note,
                max_sends, stop_when_complete, created_by, created_by_name, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,'active')""",
            (int(claim_id), at, repeat, int(every or 7), weekday, (note or "")[:300],
             max(1, int(max_sends or MAX_SENDS_DEFAULT)), 1 if stop_when_complete else 0,
             str(by_id or ""), (by or "")[:80]))
        await conn.commit()
        sch_id = cur.lastrowid
    try:
        import biz_nidaan as _n
        await _n.record_claim_activity(
            claim_id, "wa_scheduled", channel="system", actor=by or "staff",
            summary="Document reminder scheduled for %s%s" % (
                utc_to_ist(at),
                (" and then %s" % _describe(repeat, every, weekday)) if repeat != "once" else ""))
    except Exception:
        pass
    return {"ok": True, "sch_id": sch_id, "next_at": at, "next_ist": utc_to_ist(at)}


def _describe(repeat: str, every: int, weekday: Optional[int]) -> str:
    if repeat == "weekly":
        return "every %s" % (WEEKDAYS[weekday] if weekday is not None and 0 <= weekday < 7 else "week")
    if repeat == "days":
        return "every %d days" % max(1, int(every or 1))
    return "once"


async def listing(claim_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT * FROM nidaan_wa_schedule WHERE claim_id=? ORDER BY sch_id DESC LIMIT 20",
            (int(claim_id),))).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["next_ist"] = utc_to_ist(d.get("next_at")) if d.get("next_at") else ""
        d["last_ist"] = utc_to_ist(d.get("last_sent_at")) if d.get("last_sent_at") else ""
        d["describes"] = _describe(d.get("repeat_rule") or "once", d.get("repeat_every") or 7,
                                   d.get("repeat_weekday"))
        out.append(d)
    return out


async def set_status(sch_id: int, status: str, *, by: str = "") -> dict:
    if status not in ("active", "paused", "cancelled"):
        return {"ok": False, "error": "Unknown status."}
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT claim_id, status FROM nidaan_wa_schedule WHERE sch_id=?", (int(sch_id),))).fetchone()
        if not row:
            return {"ok": False, "error": "That reminder no longer exists."}
        await conn.execute("UPDATE nidaan_wa_schedule SET status=?, updated_at=CURRENT_TIMESTAMP "
                           "WHERE sch_id=?", (status, int(sch_id)))
        await conn.commit()
    try:
        import biz_nidaan as _n
        await _n.record_claim_activity(
            dict(row)["claim_id"], "wa_scheduled", channel="system", actor=by or "staff",
            summary="Document reminder %s" % {"active": "restarted", "paused": "paused",
                                              "cancelled": "cancelled"}[status])
    except Exception:
        pass
    return {"ok": True, "status": status}


async def due(limit: int = 25) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            """SELECT s.* FROM nidaan_wa_schedule s
                 JOIN nidaan_claims c ON c.claim_id = s.claim_id
                WHERE s.status='active' AND s.next_at IS NOT NULL
                  AND s.next_at <= datetime('now', ?)
                  AND COALESCE(c.archived,0)=0
                  AND COALESCE(c.status,'') NOT IN ('closed','withdrawn')
                ORDER BY s.next_at LIMIT ?""",
            ("+%d minutes" % LOOK_AHEAD_MIN, int(limit)))).fetchall()
    return [dict(r) for r in rows]


async def _finish(conn, sch_id: int, reason: str) -> None:
    await conn.execute(
        "UPDATE nidaan_wa_schedule SET status='done', next_at=NULL, done_reason=?, "
        "updated_at=CURRENT_TIMESTAMP WHERE sch_id=?", (reason[:120], int(sch_id)))
    await conn.commit()


def _why_not(res: dict) -> str:
    """The complainant's own line from a send result, in words: why they were not reached."""
    if res.get("asked_recently"):
        return "a colleague asked them very recently"
    if not res.get("ok"):
        return str(res.get("error") or "not sent")[:120]
    for r in res.get("results") or []:
        if r.get("kind") == "to" and r.get("whatsapp") and r.get("whatsapp") != "sent":
            return str(r["whatsapp"])[:120]
    return "not delivered"


async def _send_template(claim_id: int, claim: dict, pending: list) -> tuple:
    """The approved np_doc_reminder, for when the 24-hour window is closed. (ok, why_not)."""
    try:
        import biz_nidaan_doc_request as _dr
        import biz_nidaan_wa_orchestrator as _orch
        lang = await _dr._lang_for(claim_id, claim)
        first = (pending or [{}])[0]
        label = ((first.get("hi") if lang == "hi" else None) or first.get("en")
                 or first.get("key") or "document")
        r = await _orch.wa_journey(claim_id, "doc_reminder",
                                   extra={"doc_label": label, "done": 0, "total": len(pending)})
        return bool(r.get("ok")), ("" if r.get("ok") else str(r.get("error") or "not sent"))
    except Exception as e:  # noqa: BLE001
        logger.warning("scheduled reminder template failed for claim %s: %s", claim_id, e)
        return False, "template send failed"


async def _nudge_setter(s: dict, claim_id: int, claim: dict, *, sent_ok: bool, how: str,
                        why: str, next_ist: str) -> None:
    """Tell the person who set the reminder what happened - bell and Telegram, never email.

    If it did not get through, that is the moment for a phone call, so the message says so and
    gives the number. A schedule set by nobody in particular goes to whoever is on duty.
    """
    try:
        import biz_nidaan_notifications as _nnot
        ids = []
        by = str(s.get("created_by") or "").strip()
        if by.isdigit():
            ids = [int(by)]
        if not ids:
            # Whoever is on duty for the claim's stage - the same rule as the "time to call" flag.
            import biz_nidaan as _n
            stage = (claim.get("pipeline_stage") or "").strip()
            try:
                ids = list(await _n.on_duty_rep_ids(stage)) if stage else []
            except Exception:  # noqa: BLE001
                ids = []
        if not ids:
            ids = [a["staff_id"] for a in await _nnot._super_admin_staff()]
        if not ids:
            return
        who = (claim.get("complainant_name") or claim.get("insured_name") or "").strip()
        if sent_ok:
            subject = "\u23f0 NP-%s \u2014 your document reminder went out" % claim_id
            body = ["Sent to %s as a %s." % (who or "the complainant", how)]
            if next_ist:
                body.append("Next reminder: %s." % next_ist)
            body.append("If documents arrive, the reminders stop on their own.")
        else:
            import biz_nidaan_doc_request as _dr
            phone = _dr.valid_phone(claim.get("complainant_phone") or claim.get("insured_phone"))
            subject = "\U0001f4de NP-%s \u2014 the reminder did not reach them, please call" % claim_id
            body = ["Your scheduled document reminder could not get through: %s." % (why or "not delivered"),
                    "", "Please call: %s %s" % (who or "the complainant",
                                               phone or "(no number on file)"),
                    "", "Write down what they say on the claim afterwards."]
        await _nnot.notify_staff_inapp(ids, subject, "\n".join(body),
                                       event_key="doc.schedule_due", email=False,
                                       claim_id=claim_id)
    except Exception as e:  # noqa: BLE001 - a failed nudge must not stop the schedule loop
        logger.warning("schedule nudge failed for claim %s: %s", claim_id, e)


async def run_due() -> dict:
    """The worker pass. Sends what is due, then either books the next one or finishes."""
    out = {"sent": 0, "finished": 0, "skipped": 0}
    import biz_nidaan_doc_request as _dr
    import biz_nidaan_doc_checklist as _ck

    for s in await due():
        sch_id, claim_id = s["sch_id"], s["claim_id"]
        try:
            claim = await _dr._claim(claim_id) or {}
            pending = await _ck.pending_required_docs(claim_id, claim.get("claim_type") or "")

            # Everything arrived. Stop - this is the founder's "until the documents arrive".
            if s.get("stop_when_complete") and not pending:
                async with aiosqlite.connect(DB_PATH) as conn:
                    await _finish(conn, sch_id, "all documents are in")
                out["finished"] += 1
                continue

            keys = [d["key"] for d in pending]
            if not keys:
                async with aiosqlite.connect(DB_PATH) as conn:
                    await _finish(conn, sch_id, "nothing left to ask for")
                out["finished"] += 1
                continue

            msg = await _dr.draft_message(claim_id, keys, kind="nudge",
                                          note=(s.get("note") or ""))
            pv = await _dr.preview(claim_id, doc_keys=keys, message=msg,
                                   channels=["whatsapp"])
            if not pv.get("ok"):
                # We cannot reach them this way. Do not silently retry for ever: hand it back.
                async with aiosqlite.connect(DB_PATH) as conn:
                    await _finish(conn, sch_id, (pv.get("problems") or ["cannot reach them"])[0])
                out["skipped"] += 1
                continue

            res = await _dr.send(claim_id, doc_keys=keys, message=msg, confirm=pv["confirm"],
                                 channels=["whatsapp"],
                                 actor="scheduled by %s" % (s.get("created_by_name") or "staff"),
                                 kind="nudge")
            # REACHED, not "recorded". send() says ok when it logged the ask, even if nobody got
            # it - reading that as "sent" closed schedules as done that had reached no one.
            sent_ok = bool(res.get("ok") and res.get("reached_complainant"))
            how, why = ("WhatsApp message", "") if sent_ok else ("", _why_not(res))
            if not sent_ok and not res.get("asked_recently"):
                # Past WhatsApp's 24-hour window a free message cannot be delivered at all. The
                # approved reminder template can: it names the first document still missing.
                sent_ok, why2 = await _send_template(claim_id, claim, pending)
                if sent_ok:
                    how, why = "approved WhatsApp reminder (24-hour rule)", ""
                else:
                    why = why2 or why
            sent_n = int(s.get("sent_count") or 0) + (1 if sent_ok else 0)
            nxt = _next_after(s["next_at"], s.get("repeat_rule") or "once",
                              s.get("repeat_every") or 7, s.get("repeat_weekday"))
            async with aiosqlite.connect(DB_PATH) as conn:
                if sent_ok:
                    out["sent"] += 1
                    await conn.execute(
                        "UPDATE nidaan_wa_schedule SET sent_count=?, last_sent_at=CURRENT_TIMESTAMP "
                        "WHERE sch_id=?", (sent_n, sch_id))
                finished = not nxt or sent_n >= int(s.get("max_sends") or MAX_SENDS_DEFAULT)
                if finished:
                    if nxt:
                        reason = "asked %d time(s)" % sent_n
                    elif sent_ok:
                        reason = "one-off reminder sent"
                    else:
                        reason = "could not reach them: %s" % (why or "not delivered")
                    await _finish(conn, sch_id, reason)
                    out["finished"] += 1
                else:
                    await conn.execute(
                        "UPDATE nidaan_wa_schedule SET next_at=?, updated_at=CURRENT_TIMESTAMP "
                        "WHERE sch_id=?", (nxt, sch_id))
                await conn.commit()
            if not sent_ok:
                out["not_reached"] = out.get("not_reached", 0) + 1
            await _nudge_setter(s, claim_id, claim, sent_ok=sent_ok, how=how, why=why,
                                next_ist=(utc_to_ist(nxt) if (nxt and not finished) else ""))
        except Exception as e:  # noqa: BLE001 — one bad schedule must not stop the rest
            logger.warning("scheduled reminder %s failed: %s", sch_id, e)
            out["skipped"] += 1
    return out
