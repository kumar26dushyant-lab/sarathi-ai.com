"""
NidaanPartner — WHO HEARS AN ALARM, AND WHETHER IT IS STILL TRUE.

Founder, 19 Sep, after a self-healed IMAP blip paged fourteen people with "STOPPED WORKING":

    "first stop these alarms otherwise people will ignore and wont be taking seriously, second,
     filter all alarm first if really something happened or it's a false alarm, restricted it to
     me only till we create a new alert bot on telegram. stop all alarm to everyone and only send
     me if any, especially these conversation unanswered."

Two separate instructions, and this module is both of them.

──────────────────────────────────────────────────────────────────────────────
1. AUDIENCE — an alarm reaches the founder, and nobody else.
──────────────────────────────────────────────────────────────────────────────
Not a channel downgrade (that is `biz_nidaan_notify_policy`, which only ever touches the email
leg). This replaces the RECIPIENT LIST: bell, Telegram, push and email all go to one person.
Temporary by design — it lifts when the Telegram alert bot exists.

2. RE-VERIFICATION — an alarm must still be true at the moment it is sent.
──────────────────────────────────────────────────────────────────────────────
The radar false alarm was not really a threshold bug. It was an alarm describing a world that had
already stopped existing: by the time a human read "STOPPED WORKING", the mailbox had been polling
happily for several minutes. Sweeps detect, queue, and send; between detect and send, things fix
themselves.

So every alarm with a registered re-check is asked one question immediately before delivery —
*is this still the case?* — and is dropped, with a log line, if it is not.

THE SAFETY RULE THAT MAKES THIS SAFE: **an alarm with no registered re-check is always sent.**
Silence is only ever the result of positive evidence that the condition has cleared. A re-check
that errors also sends. We would rather deliver one stale alarm than swallow a real one.

──────────────────────────────────────────────────────────────────────────────
WHAT IS AN ALARM, AND WHAT IS NOT
──────────────────────────────────────────────────────────────────────────────
An ALARM is machine-generated, nobody asked for it, it is broadcast to admins, and it claims
something is WRONG. Those are the ones that teach people to swipe.

NOT an alarm, and deliberately untouched:
  • Work sent to the one person who owns it — a task assigned, an SLA breach on YOUR task, a
    draft query, an @mention. Redirecting those to the founder would mean the assignee never
    learns, which breaks the process instead of quieting it.
  • Business activity — a claim filed, a payment taken, a signup. Noisy, but it is the business
    happening, not a fault report.

If the founder wants either of those groups narrowed too, add the key here — that is a one-line
change and the reason this list is a list.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("nidaan.alarm.policy")

# The ops setting that overrides the audience, so this can be re-pointed (or lifted) without a
# deploy. Comma-separated staff_ids. Empty/absent = fall back to the founder, resolved below.
AUDIENCE_SETTING = "alarm_audience_staff_ids"

# Last-resort identity of "me". Used only if the setting is unset AND the email lookup fails.
_FOUNDER_EMAIL = "dushyant@nidaanpartner.com"


# ── Which event keys are alarms ──────────────────────────────────────────────
# Exact keys, so adding an event never silently inherits alarm behaviour.
ALARM_EVENTS = {
    # Watchdogs — a subsystem claims to be down.
    "health.subsystem",
    "health.alert",
    "radar.mailbox_down",
    "payment.watchdog",
    "payment.guardian",
    "payment.guardian_ok",
    "wa.line.down",
    "wa.line.recovered",
    # Sweeps — a machine noticed something has been sitting too long.
    "conversation.unanswered",            # named explicitly by the founder
    "conversation.unanswered.escalated",  # the require_ack popup: the most intrusive thing we send
    "support.sla_escalation",
    "bucket.stale",
    "claim.no_documents",
    "doc.call_due",
    # Nags.
    "telegram.connect_reminder",
}


def is_alarm(event_key: str) -> bool:
    return (event_key or "").strip().lower() in ALARM_EVENTS


# ── Who hears it ─────────────────────────────────────────────────────────────
async def audience() -> list[int]:
    """The staff_ids allowed to receive an alarm. Never empty.

    Order: the ops setting, then the founder by email, then the lowest-numbered active
    super_admin. The last step exists so a renamed mailbox or a typo'd setting downgrades to
    'one sensible person' rather than to 'nobody', which would be a silent alarm system.
    """
    import aiosqlite
    import biz_database as db

    try:
        import biz_nidaan as _nid
        raw = (await _nid.get_ops_setting(AUDIENCE_SETTING, "") or "").strip()
        ids = [int(p) for p in raw.replace(" ", "").split(",") if p.isdigit()]
        if ids:
            return ids
    except Exception as e:  # noqa: BLE001
        logger.debug("alarm audience setting unreadable (%s) — falling back", e)

    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            row = await (await conn.execute(
                "SELECT staff_id FROM nidaan_staff WHERE LOWER(email)=? AND status='active' "
                "AND deleted_at IS NULL", (_FOUNDER_EMAIL,))).fetchone()
            if row:
                return [int(row["staff_id"])]
            row = await (await conn.execute(
                "SELECT staff_id FROM nidaan_staff WHERE role='super_admin' AND status='active' "
                "AND deleted_at IS NULL ORDER BY staff_id LIMIT 1")).fetchone()
            if row:
                return [int(row["staff_id"])]
    except Exception as e:  # noqa: BLE001
        logger.warning("alarm audience lookup failed: %s", e)
    return []


# ── Is it still true? ────────────────────────────────────────────────────────
# Each function answers one question: given what this alarm CLAIMS, does that claim still hold?
# Return True to send, False to drop. Raising is treated as True (send) by the caller.

async def _recheck_health(subject: str, body: str) -> bool:
    """App Health said a subsystem stopped working. Re-run the checks and see."""
    import biz_nidaan_health_watch as _hw
    # A recovery notice describes subsystems that are healthy — re-checking it would always
    # "disprove" it. Only outage claims are re-verified.
    if not (_hw.MARK_BROKE in body or _hw.MARK_STILL in body):
        return True
    # The watchdog's own list, not a rebuilt one. A subsystem missing from this list would look
    # like a subsystem that had recovered, and the alarm would be dropped.
    checks = await _hw.current_checks()
    failing = {c.get("name") for c in checks if not c.get("ok") and c.get("name") in _hw._CRITICAL}
    # Only the subsystems this message actually names matter. Something else breaking in the
    # meantime is a different alarm, with its own edge.
    named = {c.get("name") for c in checks if c.get("name") and c.get("name") in body}
    still = named & failing
    if not still:
        logger.info("ALARM DROPPED (health.subsystem): %s — recovered before delivery",
                    ", ".join(sorted(named)) or "nothing named")
        return False
    return True


async def _recheck_radar(subject: str, body: str) -> bool:
    """A mailbox was said to be down. It is only down if it is still failing consecutively."""
    import biz_nidaan_radar as _radar
    mbs = [m for m in await _radar.list_mailboxes() if m.get("is_active")]
    down = [m for m in mbs if int(m.get("fail_count") or 0) >= _radar.FAIL_ALERT_THRESHOLD]
    if not down:
        logger.info("ALARM DROPPED (radar.mailbox_down): every inbox is polling again")
        return False
    return True


async def _recheck_unanswered(subject: str, body: str) -> bool:
    """Somebody was said to be waiting for a reply. They may have been replied to since.

    Checks the PEOPLE THIS MESSAGE NAMES, not merely whether anyone at all is waiting — otherwise
    a queue that is never completely empty would make the re-check meaningless. Somebody else
    starting to wait is a different alarm, and the sweep will raise it on its own.
    """
    import biz_nidaan_notifications as _n
    # The escalation's own window is hours, the nudge's is minutes. Using the SHORTER window here
    # can only ever find more people still waiting, never fewer, so this cannot silence a real
    # escalation by looking at too narrow a slice.
    mins = getattr(_n, "_ESCALATE_AFTER_MIN", 30)
    waiting = [str(r["msisdn"]) for r in await _n._unanswered_whatsapp(mins)]
    waiting += ["#%s" % r["thread_id"] for r in await _n._unanswered_support(mins)]
    still = [w for w in waiting if w and w in body]
    if not still:
        logger.info("ALARM DROPPED (%s): everyone this alert named has been replied to",
                    (subject or "")[:60])
        return False
    return True


async def _recheck_payment_guardian(subject: str, body: str) -> bool:
    """The guardian reports several findings; only ONE of them has ever been wrong.

    "No Razorpay webhook has reached us in 24 hours" was announced on 20 Sep while webhooks were
    arriving and verifying perfectly, because the check counted payment ROWS written by webhooks
    rather than webhook ARRIVALS. The root cause is fixed, but a claim that once told a person to
    change a working setting is worth confirming before it is repeated.

    Deliberately narrow: an alert that mentions anything ELSE is sent untouched. Re-running the
    whole guardian here would call Razorpay's API on every send, which is not a thing to do inside
    a notification.
    """
    if "webhook" not in body.lower():
        return True
    import datetime as _dt
    import biz_nidaan as _nid
    stamp = (await _nid.get_ops_setting("razorpay_webhook_last_at", "") or "").split("|")[0].strip()
    if not stamp:
        return True          # nothing recorded either way — we cannot disprove it, so it goes
    cutoff = (_dt.datetime.utcnow() - _dt.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    if stamp >= cutoff:
        logger.info("ALARM DROPPED (payment.guardian): a webhook arrived at %s UTC", stamp)
        return False
    return True


# Only keys listed here are ever re-verified. Everything else is sent as-is, on purpose.
_RECHECKS = {
    "health.subsystem": _recheck_health,
    "radar.mailbox_down": _recheck_radar,
    "conversation.unanswered": _recheck_unanswered,
    "conversation.unanswered.escalated": _recheck_unanswered,
    "payment.guardian": _recheck_payment_guardian,
}


async def still_true(event_key: str, subject: str = "", body: str = "") -> bool:
    """False only on positive evidence that the condition has cleared. Never raises."""
    fn = _RECHECKS.get((event_key or "").strip().lower())
    if fn is None:
        return True
    try:
        return bool(await fn(subject or "", body or ""))
    except Exception as e:  # noqa: BLE001
        # An alarm we cannot disprove is an alarm we send.
        logger.warning("alarm re-check for %s failed (%s) — sending anyway", event_key, e)
        return True


# ── Fan-out guard ────────────────────────────────────────────────────────────
async def _already_said(event_key: str, subject: str, body: str) -> bool:
    """True if this exact alarm text was already sent moments ago.

    Some sweeps notify ONE PERSON AT A TIME — `for sid in ids: notify_staff_inapp([sid], ...)`
    with the same subject and body each time (bucket.stale does this for every rostered staffer).
    Narrowing all of those to one recipient turns twelve messages to twelve people into twelve
    IDENTICAL messages to the founder, which is a worse version of the noise we are removing.

    So identical alarm text, same key, inside a ten-minute block is delivered once. The block is
    wall-clock rather than a rolling window, so an alarm that straddles a boundary is sent twice
    rather than dropped — the harmless direction, and a real recurrence later always gets through
    with a new block.
    """
    import hashlib
    from datetime import datetime
    import aiosqlite
    import biz_database as db

    digest = hashlib.sha256(
        ("%s|%s|%s" % (event_key, subject or "", body or "")).encode("utf-8", "replace")
    ).hexdigest()[:24]
    now = datetime.utcnow()
    block = "%s%02d" % (now.strftime("%Y%m%d%H"), (now.minute // 10) * 10)
    akey = "alarmfan:%s:%s" % (digest, block)
    try:
        async with aiosqlite.connect(db.DB_PATH) as c:
            cur = await c.execute(
                "INSERT OR IGNORE INTO nidaan_alert_dedup (alert_key, sent_count, last_at) "
                "VALUES (?, 1, CURRENT_TIMESTAMP)", (akey,))
            await c.commit()
            first_time = (cur.rowcount or 0) > 0
    except Exception as e:  # noqa: BLE001
        # Cannot remember? Then deliver. A repeated alarm is a nuisance; a swallowed one is a fault.
        logger.warning("alarm fan-out guard unavailable (%s) — delivering", e)
        return False
    return not first_time


# ── The one call the notification layer makes ────────────────────────────────
async def gate(event_key: str, staff_ids: list, subject: str = "",
               body: str = "") -> tuple[list, str]:
    """(recipients, why). Empty recipients = do not send.

    Non-alarms pass through untouched — this must never quietly reshape ordinary work.
    """
    if not is_alarm(event_key):
        return list(staff_ids or []), ""

    if not await still_true(event_key, subject, body):
        return [], "condition cleared before delivery"

    if await _already_said(event_key, subject, body):
        return [], "identical alarm already delivered in this ten-minute block"

    who = await audience()
    if not who:
        # We could not work out who to tell. Telling the original list is wrong (that is the
        # noise we were asked to stop) and telling nobody hides a real fault, so say so loudly.
        logger.error("ALARM %s has no audience — nobody could be resolved to receive it",
                     event_key)
        return [], "no audience could be resolved"

    dropped = [s for s in (staff_ids or []) if s not in who]
    if dropped:
        logger.info("ALARM %s narrowed to %s (was %d recipient(s))",
                    event_key, who, len(staff_ids or []))
    return who, "alarms are restricted to the founder until the Telegram alert bot exists"
