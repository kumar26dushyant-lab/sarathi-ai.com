"""
NidaanPartner PAYMENT GUARDIAN — watches OUR payment mechanics, end to end, around the clock.

Founder, 15 Sep: "anything not working correctly (in our mechanics), flag and notify superadmins on
telegram ... it should trigger every 10 min until any superadmin sees it ... payment is serious."

WHAT IT IS, AND WHAT IT DELIBERATELY IS NOT
  * It READS, it ALERTS, and — since 23 Sep — it RECOVERS ONE THING: a payment Razorpay has
    captured that never reached our ledger (a subscription charge, a branch Level-2 fee, or a
    Rs499 review). Nothing else. It still never retries,
    refunds, or cancels, and if this module dies the payment paths carry on untouched (a
    heartbeat, checked from the web processes, notices the silence).

    That exception exists because reporting alone was not enough. On 23 Sep a customer paid
    Rs 588.82 by UPI; Razorpay captured it; our system had no row, no subscription, and showed
    him "PAID (LTV) Rs 0" on his own account page. A UPI payment switches app, so the browser
    that was meant to confirm it is gone by the time the money moves, and the webhook — the
    thing that exists to catch exactly that — had not delivered for twelve hours. A guardian
    that only raises this needs a person awake to be worth anything.

    The recovery runs the webhook's own function and is idempotent on the Razorpay payment id,
    so a late webhook changes nothing. The money is provably taken before it runs — Razorpay
    says captured — so the risk is not "might invent a payment", it is "might record a real one
    twice", and that is what the idempotency key is for.
  * Every finding is a FACT from Razorpay's own records or our database - never a guess.
  * One problem is ONE incident, keyed, so repeated runs can never produce a flood.
  * Customer-side trouble (a declined card, an abandoned checkout) is NOT for this: that lives in
    Payment Follow-up. This is only for OUR mechanics breaking.

THE CHECKS (each one caught, or would have caught, a real bug)
  1  paid_not_recorded   Razorpay captured it; our ledger has no row.
  2  amount_mismatch     Our row's amount differs from what Razorpay actually charged.
  3  ledger_not_at_rzp   We hold a verified row Razorpay does not know, or has not captured.
  4  no_effect           Money in, nothing happened: no active plan / claim not unlocked / L2 not queued.
  5  duplicate_row       The same charge recorded twice (the 20 Aug - 15 Sep subscription bug).
  6  period_wrong        A subscription's period does not match its plan (the "free extra month" bug).
  7  not_announced       A payment nobody was told about (subscriptions, silent since August).
  8  renewal_overdue     An active plan past its end date with no renewal charge.
  9  webhook_silent      Razorpay captured payments but no webhook reached us.
  10 gateway_unreachable Razorpay keys missing/rejected, or the API unreachable twice in a row.
  11 plan_config         An active plan with no price, or a price that cannot make a valid charge.
  12 guardian_silent     (checked from the web processes) this guardian has not run for 15 minutes.

ALERTS
  Telegram to every super admin with a "👀 Seen" button, plus the dashboard bell. Unseen, it
  repeats every 10 minutes for as long as it takes. The first tap records who saw it, stops the
  repeats for everyone, and tells the others. If it is still not fixed 2 hours later, it speaks up
  again (founder's rule). When the fact stops being true, it says so once and closes itself.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone

import aiosqlite
import httpx

import biz_database as db
import biz_nidaan as _n

logger = logging.getLogger("nidaan.pay_guard")

# Telegram rejects a relative button URL and drops the message with it.
_OPS_URL = (os.getenv("NIDAAN_BASE_URL", "https://nidaanpartner.com").rstrip("/")
            + "/nidaan/ops")
DB_PATH = db.DB_PATH
IST = timezone(timedelta(hours=5, minutes=30))

ALERT_EVERY_MIN = 10        # unseen: the FIRST gap for a critical incident
REMIND_AFTER_ACK_H = 2      # seen but still broken: speak up again after this long

# How long before an incident may speak AGAIN, by severity, indexed by how many times it has
# already spoken. The last entry repeats for critical; for anything else, running off the end of
# the list means it stops talking altogether.
#
#   critical : 10 min, 30 min, 2h, then every 6h - backs off, never goes silent
#   warn     : once, then once more a day later, then quiet
#   info     : once, ever
#
# Founder, 24 Sep: "1-2 alerts are fine now, not in every 5 min continuously."
_CADENCE = {
    "critical": [ALERT_EVERY_MIN, 30, 120, 360],
    "warning":  [1440],
    "warn":     [1440],
    "info":     [],
}


def _next_gap_minutes(severity: str, said_count: int):
    """Minutes until this may be said again, or None for 'it has said its piece'.

    None does NOT mean resolved. The incident stays open and stays on the Payment Health screen;
    it simply stops interrupting people. Critical never returns None - something that is actually
    broken has to keep asking.
    """
    plan = _CADENCE.get((severity or "").lower(), _CADENCE["warn"])
    if said_count < len(plan):
        return plan[said_count]
    return plan[-1] if ((severity or "").lower() == "critical" and plan) else None
LOOK_BACK_H = 48            # how far back the reconciliation looks
HEARTBEAT_KEY = "pay_guard_heartbeat"
SINCE_KEY = "pay_guard_since"    # it judges what happens from the moment it starts watching
HEARTBEAT_STALE_MIN = 15
_RZP_FAIL_KEY = "pay_guard_rzp_fails"


# ── the incident store ───────────────────────────────────────────────────────
async def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


async def open_incidents(include_resolved: bool = False, limit: int = 100) -> list[dict]:
    q = ("SELECT * FROM nidaan_pay_incidents"
         + ("" if include_resolved else " WHERE status <> 'resolved'")
         + " ORDER BY CASE severity WHEN 'critical' THEN 0 ELSE 1 END, last_seen DESC LIMIT ?")
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        return [dict(r) for r in await (await c.execute(q, (int(limit),))).fetchall()]


async def _sync(findings: list[dict], checks_ran: set) -> dict:
    """Write what is true now. A check that could not run never closes its incidents - silence is
    not evidence that a problem went away."""
    now = await _now()
    seen_keys = {f["key"] for f in findings}
    opened, closed = [], []
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        for f in findings:
            row = await (await c.execute(
                "SELECT inc_id, status FROM nidaan_pay_incidents WHERE key=?", (f["key"],))).fetchone()
            if row and dict(row)["status"] != "resolved":
                await c.execute(
                    "UPDATE nidaan_pay_incidents SET last_seen=?, detail=?, amount_paise=? WHERE inc_id=?",
                    (now, f.get("detail", "")[:2000], f.get("amount_paise") or 0, dict(row)["inc_id"]))
                continue
            cur = await c.execute(
                "INSERT INTO nidaan_pay_incidents (key, check_name, severity, title, detail, claim_id, "
                "account_id, amount_paise, first_seen, last_seen, status, next_alert_at, alert_count) "
                "VALUES (?,?,?,?,?,?,?,?,?,?, 'open', ?, 0) "
                "ON CONFLICT(key) DO UPDATE SET status='open', last_seen=excluded.last_seen, "
                "detail=excluded.detail, next_alert_at=excluded.next_alert_at, resolved_at=NULL",
                (f["key"], f["check"], f.get("severity", "critical"), f["title"][:200],
                 f.get("detail", "")[:2000], f.get("claim_id"), f.get("account_id"),
                 f.get("amount_paise") or 0, now, now, now))
            opened.append(f["key"])
        # Close what is no longer true, but only for checks that actually ran.
        rows = [dict(r) for r in await (await c.execute(
            "SELECT inc_id, key, check_name, title FROM nidaan_pay_incidents "
            "WHERE status <> 'resolved'")).fetchall()]
        for r in rows:
            if r["key"] in seen_keys or r["check_name"] not in checks_ran:
                continue
            await c.execute("UPDATE nidaan_pay_incidents SET status='resolved', resolved_at=? "
                            "WHERE inc_id=?", (now, r["inc_id"]))
            closed.append(r)
        await c.commit()
    return {"opened": opened, "closed": closed}


async def _since() -> str:
    """The guardian judges payments from the moment it first ran - never the backlog behind it.

    Without this it would open an incident for every historical duplicate and every payment made
    before the announcements were fixed, and then repeat them every 10 minutes: noise about things
    already known, which is how people learn to ignore alerts. Those are handled once, by hand."""
    val = await _n.get_ops_setting(SINCE_KEY, "") or ""
    if not val:
        val = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        await _n.set_ops_setting(SINCE_KEY, val)
    window = (datetime.utcnow() - timedelta(hours=LOOK_BACK_H)).strftime("%Y-%m-%d %H:%M:%S")
    return max(val, window)


def _is_ours(p: dict, in_ledger: bool) -> bool:
    """One Razorpay account serves NidaanPartner and Sarathi. Judge only what is ours; an
    unrecognised payment is left alone rather than reported as a problem."""
    if in_ledger:
        return True
    notes = p.get("notes") or {}
    prod = str(notes.get("product") or "").lower()
    if prod.startswith("nidaan"):
        return True
    if "sarathi" in prod:
        return False
    # Sarathi's payments carry tenant_id/plan_key and product=sarathi-ai-crm (excluded above);
    # ours carry the claim or the account they are for. `nidaan_account_id` is what the
    # subscription actually writes - the other spellings are kept for anything older.
    if (notes.get("claim_id") or notes.get("account_id") or notes.get("purchase_id")
            or notes.get("nidaan_account_id")):
        return True
    # A SUBSCRIPTION CHARGE CARRIES NO NOTES AT ALL. Razorpay puts notes on the subscription and
    # does not copy them onto the payment - checked on the live account, 23 Sep: `notes: []`.
    # So every recurring payment we have ever taken failed this test and the guardian was blind
    # to all of them, which is how Rs 588.82 sat captured at Razorpay and absent from our books
    # with nothing saying so.
    #
    # An invoice_id means a subscription charge. It is ours when we are looking at OUR OWN
    # Razorpay account - which is the normal case and is verified here rather than assumed,
    # because the Nidaan keys fall back to the shared ones if they are ever unset, and on a
    # shared account this would claim Sarathi's subscriptions too.
    if p.get("invoice_id"):
        _nk = (os.getenv("NIDAAN_RAZORPAY_KEY_ID") or "").strip()
        _sk = (os.getenv("RAZORPAY_KEY_ID") or "").strip()
        return bool(_nk and _nk != _sk)
    return False


# ── the checks ───────────────────────────────────────────────────────────────
def _rzp_auth() -> tuple:
    key = os.getenv("NIDAAN_RAZORPAY_KEY_ID") or os.getenv("RAZORPAY_KEY_ID", "")
    sec = os.getenv("NIDAAN_RAZORPAY_KEY_SECRET") or os.getenv("RAZORPAY_KEY_SECRET", "")
    return key, sec


async def _rzp_payments(hours: int) -> tuple:
    """Razorpay's own list of payments in the window. (payments, ok) - ok=False means we could not
    ask, which is itself something to watch rather than a reason to accuse anyone."""
    key, sec = _rzp_auth()
    if not (key and sec):
        return [], False
    # A REAL POSIX EPOCH. datetime.utcnow() is naive, and .timestamp() reads a naive datetime as
    # LOCAL time - so on this server (+0200, TZ unset) it lands two hours in the past, and the
    # window we asked Razorpay for ENDED two hours ago. Every payment taken in the last two
    # hours was invisible to this guardian, which is how Rs 588.82 sat captured at Razorpay on
    # 23 Sep with nothing in our books and nothing saying so.
    #
    # The same trap is called out at biz_nidaan.create_branch_magic_token - it was found once,
    # for short-lived tokens, and this caller was missed.
    now = int(time.time())
    params = {"from": now - hours * 3600, "to": now + 300, "count": 100}
    out = []
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get("https://api.razorpay.com/v1/payments", params=params, auth=(key, sec))
        if r.status_code != 200:
            logger.warning("razorpay payments list %s: %s", r.status_code, r.text[:200])
            return [], False
        out = (r.json() or {}).get("items") or []
    except Exception as e:  # noqa: BLE001
        logger.warning("razorpay payments list failed: %s", e)
        return [], False
    return out, True


# What an edge challenge page says about itself. Cloudflare serves "Just a moment..." with a 403
# or 503; the application never sees the request at all.
_CHALLENGE_MARKS = ("just a moment", "cf-browser-verification", "cf_chl_", "checking your browser",
                    "attention required", "__cf_chl")


async def webhook_self_test() -> tuple:
    """Can our webhook endpoint answer at all - and is anything in front of it turning callers away?

    Founder, 23 Sep: "at least we get telegram confirmation ... stating problem from Razorpay
    side, if any (double check it's not from our side)."

    READ WHAT THIS CAN AND CANNOT TELL YOU. We POST to our own public webhook URL with a
    deliberately invalid signature. A healthy application answers 400 - it read the body, checked
    the signature and refused.

    A 400 proves the application is up and reachable FROM HERE. It does NOT prove Razorpay can
    reach it, and on 23 Sep it wrongly said so. Razorpay's webhook was being served a Cloudflare
    "Just a moment..." challenge and 403 on every retry, while this same test passed - because an
    edge challenge scores the CALLER, not the path, and our own server calling itself with our own
    user agent is not scored like a payment provider's webhook agent. So the pass is reported as
    "our app is up", never as "not our side".

    What it CAN catch outright is a challenge served to us too, which is now detected by name.

    Nothing is written and no event is processed: an invalid signature is rejected before the
    payload is even parsed. Returns (app_is_answering, one line saying what happened).
    """
    url = (os.getenv("NIDAAN_BASE_URL", "https://nidaanpartner.com").rstrip("/")
           + "/nidaan/api/webhook")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(url, json={"event": "selftest", "payload": {}},
                             headers={"X-Razorpay-Signature": "self-test-not-a-real-signature",
                                      "User-Agent": "NidaanPaymentGuardian/selftest"})
    except Exception as e:  # noqa: BLE001
        return False, "our endpoint could not be reached at all (%s)" % str(e)[:80]

    # Look at the BODY, not only the code. A challenge page is a 403 that never reached the app,
    # and it is the one failure this test can name with certainty.
    body = (r.text or "")[:2000].lower()
    if any(m in body for m in _CHALLENGE_MARKS):
        return False, ("Cloudflare is serving a challenge page on the webhook path (HTTP %s) - "
                       "the request never reaches the app. Turn off Bot Fight Mode for "
                       "nidaanpartner.com, or exempt /nidaan/api/webhook." % r.status_code)
    if r.status_code == 400:
        return True, ("our app answered correctly from here (it refused a bad signature) - but "
                      "this cannot prove Razorpay gets through, because an edge block scores the "
                      "caller, not the path")
    if r.status_code == 503:
        return False, "our endpoint says the webhook secret is not configured"
    return False, "our endpoint answered %s to a signature check it should have refused" % r.status_code


# How many "payment recovered" messages may leave this module in an hour, whatever happens.
# Not a tuning knob for volume - a fuse. If twelve payments are recovered at once the news is
# "something is badly wrong", and that is one message, not twelve.
_RECOVERY_MAX_PER_HOUR = 3


async def _announced_already(pid: str) -> bool:
    """Have we already told the office about THIS payment? Read from what we actually sent.

    No new table: a sent notification is the durable record of having spoken, and its body
    carries the payment id. Payment ids are unique and high-entropy, so the LIKE is exact in
    practice.

    Fails CLOSED - if we cannot tell, we stay quiet. That is the right way round here. A recovery
    that goes unannounced is still in the guardian's findings, in the ledger, and on the portal;
    a message that repeats every five minutes teaches everyone to ignore the channel, and then
    the one that matters is ignored too.
    """
    if not pid:
        return True
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            row = await (await c.execute(
                "SELECT 1 FROM nidaan_notifications WHERE event_key='payment.recovered' "
                "AND body LIKE ? LIMIT 1", ("%Payment: " + pid + "%",))).fetchone()
        return bool(row)
    except Exception as e:  # noqa: BLE001
        logger.warning("could not check whether %s was announced - staying quiet: %s", pid, e)
        return True


async def _recovery_quota_left() -> bool:
    """The fuse. True while this hour still has room for another recovery message."""
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            # DISTINCT on the BODY, not the subject. notify_staff_inapp writes one row per
            # recipient, so raw rows would count three per message - and the subject is only the
            # amount, so two different payments of the same size shared one. The body carries the
            # payment id, which is what makes each message distinct.
            row = await (await c.execute(
                "SELECT COUNT(DISTINCT COALESCE(body,'')) FROM nidaan_notifications "
                "WHERE event_key='payment.recovered' "
                "AND created_at > datetime('now','-1 hour')")).fetchone()
        return int((row or [0])[0] or 0) < _RECOVERY_MAX_PER_HOUR
    except Exception as e:  # noqa: BLE001
        logger.warning("could not read the recovery quota - staying quiet: %s", e)
        return False


async def _stamp_announced(pid: str) -> None:
    """Mark this payment as DEALT WITH, whether or not a message went out.

    `announced_at` means "nobody needs telling about this again", not "a message was sent". The
    difference matters: finding 7 raises "a payment nobody was told about" for any unstamped row,
    so staying quiet without stamping would swap a message that repeats every five minutes for an
    ALARM that repeats every five minutes. That alarm fired 21 times on 23 Sep for exactly this
    reason. Silence has to be recorded as a decision, or it reads as a gap.
    """
    if not pid:
        return
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            await c.execute("UPDATE nidaan_payments SET announced_at=CURRENT_TIMESTAMP "
                            "WHERE razorpay_payment_id=? AND COALESCE(announced_at,'')=''", (pid,))
            await c.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("could not stamp %s as announced: %s", pid, e)


async def _announce_recovery(p: dict, what: str) -> None:
    """Tell the office, on Telegram, that money arrived and the webhook did not.

    Two payments were recovered on 23 Sep and NEITHER produced a message - the money was in the
    books and nobody was told, which left the "a payment nobody was told about" alarm repeating
    21 times about a payment that had in fact been handled. record_payment announces ledger
    writes, but skips branch_l2 on purpose (it has its own Level-2 message, which this path does
    not send). Rather than chase two announcement routes, the recovery says its own piece - and
    it is a different piece anyway: this one is about the WEBHOOK, not about the sale.
    """
    pid = str(p.get("id") or "")
    # Once per payment, ever. Checked before anything else is done, including the self-test,
    # which makes an outbound HTTP request we have no reason to repeat either.
    if await _announced_already(pid):
        logger.info("recovery of %s was already announced - not saying it again", pid)
        await _stamp_announced(pid)
        return
    if not await _recovery_quota_left():
        logger.warning("recovery announcements are over the hourly ceiling - %s not sent. "
                       "The recovery itself is recorded and in the findings.", pid)
        await _stamp_announced(pid)
        return
    ok, why = await webhook_self_test()
    amt = int(p.get("amount") or 0) / 100.0
    body = (
        "₹%s has been recorded from Razorpay's own record - %s.\n\n"
        "The customer has paid and has what they bought. Nothing is owed to them.\n\n"
        "WHY THIS WAS NEEDED: no Razorpay webhook reached us for it.\n"
        "%s %s\n\n"
        "Payment: %s  ·  method: %s"
        % (("%.2f" % amt).rstrip("0").rstrip("."), what,
           ("✅ NOT our side —" if ok else "⚠️ OUR SIDE —"), why,
           p.get("id", ""), p.get("method", "") or "?"))
    subject = ("\U0001f4b0 Payment recovered — ₹%s (webhook did not deliver)"
               % ("%.2f" % amt).rstrip("0").rstrip("."))
    try:
        import biz_nidaan_notifications as _nnot
        ids = [s["staff_id"] for s in await _nnot._super_admin_staff()]
        if ids:
            await _nnot.notify_staff_inapp(ids, subject, body, event_key="payment.recovered",
                                           email=False, claim_id=_claim_of(p))
    except Exception as e:  # noqa: BLE001
        logger.warning("could not announce the recovery of %s: %s", p.get("id"), e)
    # Stamped whether the send worked or not. A send that failed is a logged problem; retrying it
    # every five minutes for the rest of the week is a worse one.
    await _stamp_announced(pid)


def _claim_of(p: dict):
    try:
        return int((p.get("notes") or {}).get("claim_id") or 0) or None
    except (TypeError, ValueError):
        return None


async def _recover_payment(p: dict) -> str:
    """Razorpay took money we never heard about. Record it, do not just report it.

    23 Sep: a customer paid Rs 588.82 by UPI, Razorpay captured it, and our system had nothing -
    no ledger row, no subscription, "PAID (LTV) Rs 0" on his own account page. TWO things had to
    fail together and both did: a UPI payment switches app, so the browser that was meant to call
    verify is gone by the time the money moves; and the webhook, the very thing that exists to
    catch that, had not delivered for twelve hours.

    A guardian that only RAISES this is a guardian that needs a person awake to be worth
    anything. The money is provably taken - Razorpay says captured - so the safe thing is to
    record it and say we did.

    Runs the webhook's own function, which is idempotent on the Razorpay payment id: if the
    webhook turns up later it changes nothing. Returns "" on success, or a reason it could not.
    """
    pid = p.get("id") or ""
    notes = p.get("notes") or {}
    prod = str(notes.get("product") or "")

    # ── a claim payment: the branch Level-2 fee, or a Rs499 review ───────────
    # These carry their identity in the ORDER's notes, so nothing has to be looked up. 23 Sep,
    # a second one the same day: claim #204's Rs 588.82 went through on UPI and our screen still
    # asked the branch to pay. Each runs exactly what the webhook's payment.captured branch runs.
    if prod == "nidaan_branch_l2":
        try:
            cid = int(notes.get("claim_id") or 0)
        except (TypeError, ValueError):
            cid = 0
        branch = str(notes.get("branch") or "")
        if not (cid and branch):
            return "branch_l2 payment with no claim/branch in its notes"
        try:
            pricing = await _n.branch_l2_fee_for_claim(cid)
            ok = await _n.mark_l2_paid(cid, branch, int(pricing["fee"]), pid)
        except Exception as e:  # noqa: BLE001
            return "could not mark L2 paid: %s" % str(e)[:90]
        if not ok:
            return "mark_l2_paid declined claim %s (already paid?)" % cid
        logger.warning("RECOVERED a branch L2 payment the webhook never delivered: %s -> "
                       "claim %s branch %s", pid, cid, branch)
        await _announce_recovery(p, "a branch Level-2 fee on claim #%s" % cid)
        return ""

    if prod == "nidaan_review_999":
        try:
            pur = int(notes.get("purchase_id") or 0)
        except (TypeError, ValueError):
            pur = 0
        if not pur:
            return "review payment with no purchase_id in its notes"
        try:
            async with aiosqlite.connect(DB_PATH) as c:
                await c.execute(
                    "UPDATE nidaan_per_claim_purchase SET status='paid', "
                    "reviewed_at=CURRENT_TIMESTAMP WHERE purchase_id=? AND status='pending_payment'",
                    (pur,))
                await c.commit()
            await _n.ensure_claim_for_paid_purchase(pur)
        except Exception as e:  # noqa: BLE001
            return "could not finalise purchase %s: %s" % (pur, str(e)[:80])
        logger.warning("RECOVERED a review payment the webhook never delivered: %s -> purchase %s",
                       pid, pur)
        await _announce_recovery(p, "a ₹499 review (purchase #%s)" % pur)
        return ""

    # ── a shared payment LINK: the "Share link" button in my-business / branch ──────
    # These record through payment_link.paid, a different webhook event from the rest - so when
    # the webhook is down, a link the staff shared and the customer paid leaves the screen still
    # asking for money. Checked BEFORE the subscription branch below, because a payment link
    # carries an invoice_id too and would otherwise be mistaken for a subscription charge.
    if prod == "nidaan_plink":
        purpose = str(notes.get("purpose") or "")
        try:
            cid = int(notes.get("claim_id") or 0)
        except (TypeError, ValueError):
            cid = 0
        branch = str(notes.get("branch") or "")
        if purpose != "l2" or not (cid and branch):
            return ("payment link (purpose=%r) needs a person: only the Level-2 fee can be "
                    "applied from the link alone" % purpose)
        try:
            pricing = await _n.branch_l2_fee_for_claim(cid)
            ok = await _n.mark_l2_paid(cid, branch, int(pricing["fee"]), pid)
        except Exception as e:  # noqa: BLE001
            return "could not mark L2 paid from the link: %s" % str(e)[:80]
        if not ok:
            return "mark_l2_paid declined claim %s (already paid?)" % cid
        # Close the link too, so the screen stops offering it and the links list tells the truth.
        try:
            async with aiosqlite.connect(DB_PATH) as c:
                c.row_factory = aiosqlite.Row
                row = await (await c.execute(
                    "SELECT plink_id FROM nidaan_payment_links WHERE claim_id=? AND purpose='l2' "
                    "AND status <> 'paid' ORDER BY created_at DESC LIMIT 1", (cid,))).fetchone()
            if row:
                await _n.mark_payment_link_paid(dict(row)["plink_id"], pid)
        except Exception as e:  # noqa: BLE001
            logger.info("could not close the payment link for claim %s: %s", cid, e)
        logger.warning("RECOVERED a shared-link payment the webhook never delivered: %s -> "
                       "claim %s branch %s", pid, cid, branch)
        await _announce_recovery(p, "a shared payment link on claim #%s" % cid)
        return ""

    # ── a subscription charge: identity lives on the SUBSCRIPTION, not the payment ──
    inv = p.get("invoice_id") or ""
    if not inv:
        return "unrecognised payment (product=%r, no invoice)" % prod
    key, sec = _rzp_auth()
    if not (key and sec):
        return "no Razorpay credentials"
    try:
        async with httpx.AsyncClient(timeout=20, auth=(key, sec)) as c:
            r = await c.get("https://api.razorpay.com/v1/invoices/%s" % inv)
            sub_id = ((r.json() or {}).get("subscription_id") or "")
            if not sub_id:
                return "invoice %s carries no subscription" % inv
            r = await c.get("https://api.razorpay.com/v1/subscriptions/%s" % sub_id)
            notes = ((r.json() or {}).get("notes") or {})
    except Exception as e:  # noqa: BLE001
        return "could not read Razorpay: %s" % str(e)[:80]

    acct = str(notes.get("nidaan_account_id") or notes.get("account_id") or "").strip()
    plan = str(notes.get("nidaan_plan") or notes.get("plan") or "").strip()
    if not (acct.isdigit() and plan):
        return "subscription %s has no account/plan in its notes" % sub_id
    try:
        res = await _n.activate_from_razorpay_webhook(
            sub_id, int(acct), plan, int(p.get("amount") or 0), razorpay_payment_id=pid)
    except Exception as e:  # noqa: BLE001
        return "activation failed: %s" % str(e)[:90]
    logger.warning("RECOVERED a payment the webhook never delivered: %s -> account %s plan %s "
                   "(Rs %s) result=%s", pid, acct, plan, int(p.get("amount") or 0) / 100, res)
    # "dup" means this charge was ALREADY recorded - nothing was recovered, so there is nothing
    # to announce. The return value was being logged and then ignored, which is what made this
    # path shout every five minutes about a payment that had been handled hours earlier.
    if str(res) != "dup":
        await _announce_recovery(p, "a %s subscription (account %s)" % (plan, acct))
    return ""


async def _check_reconcile(findings: list, ran: set) -> None:
    """Razorpay's record against ours, both ways."""
    pays, ok = await _rzp_payments(LOOK_BACK_H)
    if not ok:
        fails = int(await _n.get_ops_setting(_RZP_FAIL_KEY, "0") or 0) + 1
        await _n.set_ops_setting(_RZP_FAIL_KEY, str(fails))
        if fails >= 2:      # one blip is the internet; two in a row is ours to look at
            findings.append({
                "key": "gateway_unreachable", "check": "gateway", "severity": "critical",
                "title": "Razorpay cannot be reached (or the keys are refused)",
                "detail": "Two checks in a row could not read Razorpay's payment list. Payments may "
                          "still be going through, but we cannot verify them. Check the keys in "
                          "biz.env and Razorpay's status."})
        return
    await _n.set_ops_setting(_RZP_FAIL_KEY, "0")
    ran.update({"gateway", "reconcile", "webhook", "bounced"})
    since = await _since()
    captured = [p for p in pays if (p.get("status") or "") == "captured"]

    # ── MONEY THAT ARRIVED AND BOUNCED STRAIGHT BACK ────────────────────────
    # 23 Sep, claim 200: a complainant paid Rs 588.82, saw "Transaction Successful" on PhonePe,
    # and sent the screenshot. Razorpay refunded it the SAME MINUTE, with the reason
    # "The checkout order associated to the QR is closed" - the staff member had screenshotted
    # the checkout QR and closed the window, so by the time it was scanned the order was dead.
    #
    # Nobody knew. This guardian only ever looked at `captured`, so a payment that arrived and
    # was auto-refunded was invisible to us, while the customer believed they had paid and the
    # claim went on reading "Fee not paid yet" for two days.
    #
    # It is the worst shape a payment problem can take: the customer is sure, we are sure, and
    # both are right. So it is surfaced the moment it happens.
    for p in pays:
        if (p.get("status") or "") != "refunded" or p.get("captured"):
            continue          # a deliberate refund of a real payment is somebody's decision
        when = (datetime.utcfromtimestamp(int(p.get("created_at") or 0))
                .strftime("%Y-%m-%d %H:%M:%S") if p.get("created_at") else "")
        if when and when < since:
            continue
        why = ""
        try:
            key, sec = _rzp_auth()
            async with httpx.AsyncClient(timeout=15, auth=(key, sec)) as _c:
                _r = await _c.get("https://api.razorpay.com/v1/payments/%s/refunds" % p.get("id"))
                for rf in ((_r.json() or {}).get("items") or []):
                    why = (rf.get("notes") or {}).get("refund_reason") or ""
                    if why:
                        break
        except Exception:  # noqa: BLE001 — the reason is a nicety, the alert is not
            pass
        findings.append({
            "key": "bounced_payment:%s" % p.get("id"), "check": "bounced", "severity": "warn",
            "title": "A customer paid ₹%s and it bounced straight back"
                     % (int(p.get("amount") or 0) / 100),
            "amount_paise": int(p.get("amount") or 0),
            "detail": "%s (%s) was paid at %s UTC and refunded automatically — the customer saw "
                      "'successful' on their phone and has a screenshot.\n\n"
                      "Razorpay's reason: %s\n\n"
                      "This is what happens when a CHECKOUT QR is screenshotted and sent on: the "
                      "QR dies with the browser window, and anyone who scans it later is refunded. "
                      "Use \"Share fee link\" on the claim instead — a link stays alive and comes "
                      "back attached to the claim.\n\n"
                      "Nothing is owed to the customer; their money is already back. They need "
                      "telling, and the fee still needs paying."
                      % (p.get("id"), p.get("method") or "?", when,
                         why or "not given by Razorpay")})

    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        # EVERY payment id we hold, with no date window on it. The window used to be on OUR
        # row's created_at, which answers a different question: a row written in August and
        # stamped with its payment id in September fell outside it, so a payment that IS in the
        # books read as missing and was "recovered" every five minutes for ever. A payment id is
        # unique for all time - either we have it or we do not.
        ledger = {r["razorpay_payment_id"]: dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_payments "
            "WHERE COALESCE(razorpay_payment_id,'') <> ''")).fetchall()}
        recent_rows = [dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_payments WHERE created_at > datetime('now', ?) "
            "AND status <> 'duplicate'", ("-%d hours" % LOOK_BACK_H,))).fetchall()]

    for p in captured:
        pid = p.get("id") or ""
        row = ledger.get(pid)
        amt = int(p.get("amount") or 0)
        who = (p.get("email") or p.get("contact") or "")[:60]
        when = datetime.utcfromtimestamp(int(p.get("created_at") or 0)).strftime("%Y-%m-%d %H:%M:%S")             if p.get("created_at") else ""
        if when and when < since:
            continue                      # before we started watching - handled by hand, not here
        if not _is_ours(p, bool(row)):
            continue                      # Sarathi's, or unrecognisable: not ours to judge
        if not row:
            # FIX IT, then say so. Reporting alone leaves a paying customer with nothing until
            # somebody reads an alert - which on 23 Sep was twelve hours and counting.
            why_not = await _recover_payment(p)
            if not why_not:
                findings.append({
                    "key": "recovered_payment:%s" % pid, "check": "reconcile",
                    # We found it AND fixed it. That is news once, not an emergency - it was
                    # this finding, repeating, that put ~192 messages an hour on the founder's
                    # phone. (24 Sep)
                    "severity": "info",
                    "title": "Recovered a payment the webhook never delivered — ₹%s" % (amt / 100),
                    "amount_paise": amt,
                    "detail": "Razorpay captured %s (₹%s, %s) and no webhook reached us, so it "
                              "has been recorded and the plan activated from Razorpay's own "
                              "record. Nothing is owed to the customer. The WEBHOOK is what "
                              "needs looking at." % (pid, amt / 100, who)})
                continue
            findings.append({
                "key": "paid_not_recorded:%s" % pid, "check": "reconcile", "severity": "critical",
                "title": "Money taken, not in our ledger — ₹%s" % (amt / 100),
                "amount_paise": amt,
                "detail": "Razorpay captured %s (₹%s, %s) but we have no ledger row for it, and "
                          "it could not be recovered automatically (%s). The customer has paid "
                          "and may be waiting for what they bought."
                          % (pid, amt / 100, who, why_not)})
        elif int(row.get("total_paise") or 0) != amt:
            findings.append({
                "key": "amount_mismatch:%s" % pid, "check": "reconcile", "severity": "critical",
                "title": "Amount does not match Razorpay — ₹%s vs ₹%s"
                         % (int(row["total_paise"]) / 100, amt / 100),
                "amount_paise": amt, "account_id": row.get("account_id"), "claim_id": row.get("claim_id"),
                "detail": "Ledger row #%s says ₹%s; Razorpay charged ₹%s for %s."
                          % (row["pay_id"], int(row["total_paise"]) / 100, amt / 100, pid)})

    rzp_ids = {p.get("id") for p in pays}
    rzp_captured_ids = {p.get("id") for p in captured}
    for row in recent_rows:
        if str(row.get("created_at") or "") < since:   # (>= since is watched; before it, by hand)
            continue
        pid = (row.get("razorpay_payment_id") or "").strip()
        if not pid or pid.upper().startswith("MANUAL") or (row.get("gateway") or "") != "razorpay":
            continue
        if pid not in rzp_ids:
            continue          # older than the window Razorpay returned - not evidence of anything
        if pid not in rzp_captured_ids:
            findings.append({
                # Bookkeeping to investigate, not an outage: nobody is being charged wrongly
                # and nothing is down. It needs a person, today, not tonight.
                "key": "ledger_not_at_rzp:%s" % pid, "check": "reconcile", "severity": "warn",
                "title": "We recorded a payment Razorpay has not captured",
                "amount_paise": int(row.get("total_paise") or 0),
                "account_id": row.get("account_id"), "claim_id": row.get("claim_id"),
                "detail": "Ledger row #%s (%s, ₹%s) but Razorpay's status for %s is not 'captured'."
                          % (row["pay_id"], row["source"], int(row.get("total_paise") or 0) / 100, pid)})

    # The webhook is how late captures and renewals reach us at all.
    #
    # ASK WHETHER IT ARRIVED, NOT WHETHER IT WROTE A ROW. This check used to count payment rows
    # with verify_method='webhook' in the last 24h. But record_payment is idempotent: a webhook
    # for a payment the browser checkout already recorded writes NO row, by design. So on a day
    # when every payment completed in the browser, a perfectly healthy webhook looked dead — and
    # the alarm told a person to go and change the webhook URL and secret, which were correct.
    # (20 Sep: nginx had logged webhooks arriving 11 hours earlier, with zero signature failures
    # in a week.) An alarm that prescribes breaking a working thing is worse than silence.
    #
    # The webhook handler now stamps `razorpay_webhook_last_at` on arrival. We take the NEWER of
    # that stamp and the old row-based signal, so this is strictly more accurate than before and
    # needs no transition period: before the first stamp exists, it behaves exactly as it used to.
    if captured:
        async with aiosqlite.connect(DB_PATH) as c:
            row = await (await c.execute(
                "SELECT MAX(created_at) FROM nidaan_payments WHERE verify_method='webhook'"
            )).fetchone()
        last_row = str((row or [None])[0] or "")
        try:
            last_seen = (await _n.get_ops_setting("razorpay_webhook_last_at", "") or "").split("|")[0].strip()
        except Exception:
            last_seen = ""
        newest = max(last_row, last_seen)          # ISO strings compare correctly
        cutoff = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        if not newest or newest < cutoff:
            _self_ok, _self_why = await webhook_self_test()
            findings.append({
                # NOT critical by the founder's definition: money is still reaching us and
                # nothing is owed to any customer - the guardian reconciles against Razorpay
                # every 5 minutes and recovers. What is lost is promptness and the second
                # independent path. Worth saying twice, not worth a siren.
                "key": "webhook_silent", "check": "webhook", "severity": "warn",
                "title": "No Razorpay webhook has reached us in 24 hours",
                # WHERE TO LOOK, said plainly. On 20 Sep this alarm told a person to go and
                # change a webhook URL and secret that were correct. On 23 Sep it did the
                # opposite and told him it was Razorpay's problem, on the strength of a self-test
                # that can only ever prove our app answers US. It was Cloudflare's Bot Fight Mode
                # serving Razorpay a challenge page. So the alarm now names the THREE places the
                # request can die and says which one the evidence rules out, and never exonerates
                # us from a test taken inside our own network.
                "detail": "Razorpay captured %d payment(s) in the last %dh, and no webhook has "
                          "reached us in 24h%s.\n\n%s %s\n\n"
                          "%s\n\n"
                          "Payments are still being recorded — the guardian reads Razorpay "
                          "directly every 5 minutes and recovers anything missing — so no "
                          "money is at risk. The webhook is what needs fixing."
                          % (len(captured), LOOK_BACK_H,
                             (" (last seen %s UTC)" % newest) if newest else " — none on record",
                             ("🔎 OUR APP IS UP —" if _self_ok else "⚠️ BLOCKED BEFORE THE APP —"),
                             _self_why,
                             ("Next place to look: the Cloudflare edge. It sits in front of this "
                              "path and can turn a caller away without the app ever seeing it — "
                              "Bot Fight Mode did exactly that on 23 Sep. Check "
                              "Security → Bots and the WAF events for /nidaan/api/webhook."
                              if _self_ok else
                              "Fix the block above first; nothing else can be judged until "
                              "requests reach the app."))})


async def _check_effects_and_duplicates(findings: list, ran: set) -> None:
    """Money in, the right thing happened - once."""
    ran.update({"effect", "duplicate", "period", "announced", "renewal", "plan_config"})
    since = await _since()
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await c.execute(
            "SELECT * FROM nidaan_payments WHERE created_at >= ? "
            "AND status NOT IN ('refunded','duplicate') ORDER BY pay_id", (since,))).fetchall()]

        for r in rows:
            src, pid = r["source"], r["pay_id"]
            # 4 - the effect the money was for
            if src in ("subscription", "subscription_renewal") and r.get("account_id"):
                sub = await (await c.execute(
                    "SELECT plan, current_period_end, started_at FROM nidaan_subscriptions "
                    "WHERE account_id=? AND status='active' ORDER BY sub_id DESC LIMIT 1",
                    (r["account_id"],))).fetchone()
                if not sub:
                    findings.append({
                        "key": "no_effect:%s" % pid, "check": "effect", "severity": "critical",
                        "title": "Subscription paid, no active plan — account #%s" % r["account_id"],
                        "account_id": r["account_id"], "amount_paise": r["total_paise"],
                        "detail": "Ledger row #%s (₹%s, %s) but this account has no active "
                                  "subscription." % (pid, int(r["total_paise"]) / 100, r["plan"] or "")})
                else:
                    sub = dict(sub)
                    # 6 - a month is a month (this is the +30 days bug)
                    try:
                        cfg = await _n.get_plan_cfg(sub["plan"]) or {}
                        days = int(cfg.get("period_days") or 0) or 30
                        st = datetime.fromisoformat(str(sub["started_at"])[:19])
                        en = datetime.fromisoformat(str(sub["current_period_end"])[:19])
                        got = (en - st).days
                        if got > days + 2:
                            findings.append({
                                "key": "period_wrong:%s:%s" % (r["account_id"], str(sub["current_period_end"])[:10]),
                                "check": "period", "severity": "critical",
                                "title": "Plan period is %d days, should be %d — account #%s"
                                         % (got, days, r["account_id"]),
                                "account_id": r["account_id"],
                                "detail": "%s runs %s → %s (%d days) on a %d-day plan. A charge may "
                                          "have been counted twice." % (sub["plan"], str(st)[:10],
                                                                        str(en)[:10], got, days)})
                    except Exception:
                        pass
            elif src == "per_claim_review" and r.get("claim_id"):
                cl = await (await c.execute(
                    "SELECT payment_status FROM nidaan_claims WHERE claim_id=?", (r["claim_id"],))).fetchone()
                if not cl or (dict(cl)["payment_status"] or "") not in ("paid", "subscription"):
                    findings.append({
                        "key": "no_effect:%s" % pid, "check": "effect", "severity": "critical",
                        "title": "Review fee paid, claim not unlocked — NP-%s" % r["claim_id"],
                        "claim_id": r["claim_id"], "amount_paise": r["total_paise"],
                        "detail": "Ledger row #%s (₹%s) but NP-%s is not marked paid."
                                  % (pid, int(r["total_paise"]) / 100, r["claim_id"])})
            elif src == "branch_l2" and r.get("claim_id"):
                cl = await (await c.execute(
                    "SELECT l2_payment_status FROM nidaan_claims WHERE claim_id=?", (r["claim_id"],))).fetchone()
                if not cl or (dict(cl)["l2_payment_status"] or "") != "paid":
                    findings.append({
                        "key": "no_effect:%s" % pid, "check": "effect", "severity": "critical",
                        "title": "Level-2 fee paid, claim not queued — NP-%s" % r["claim_id"],
                        "claim_id": r["claim_id"], "amount_paise": r["total_paise"],
                        "detail": "Ledger row #%s (₹%s) but NP-%s is not marked Level-2 paid."
                                  % (pid, int(r["total_paise"]) / 100, r["claim_id"])})

            # 7 - THIS payment was announced (the ledger row stamps itself when the office is
            # told). Five minutes of grace: the announcement goes just after the row is written.
            grace = (datetime.utcnow() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
            if not r.get("announced_at") and str(r["created_at"]) < grace:
                findings.append({
                    "key": "not_announced:%s" % pid, "check": "announced", "severity": "warn",
                    "title": "A payment nobody was told about — ₹%s" % (int(r["total_paise"]) / 100),
                    "amount_paise": r["total_paise"], "account_id": r.get("account_id"),
                    "claim_id": r.get("claim_id"),
                    "detail": "Ledger row #%s (%s, %s) has no 'Payment RECEIVED' alert beside it."
                              % (pid, r["source"], r["created_at"])})

        # 5 - the same charge twice
        dups = [dict(r) for r in await (await c.execute(
            "SELECT a.pay_id a_id, b.pay_id b_id, a.account_id, a.source a_src, b.source b_src, "
            "       a.total_paise a_amt, b.total_paise b_amt, a.created_at "
            "FROM nidaan_payments a JOIN nidaan_payments b "
            "  ON a.pay_id < b.pay_id AND a.status<>'duplicate' AND b.status<>'duplicate' "
            " AND ((a.razorpay_subscription_id <> '' AND a.razorpay_subscription_id = b.razorpay_subscription_id) "
            "      OR (a.account_id IS NOT NULL AND a.account_id = b.account_id AND a.source = b.source)) "
            " AND abs(strftime('%s', a.created_at) - strftime('%s', b.created_at)) < 600 "
            "WHERE a.created_at >= ?", (since,))).fetchall()]
        for d in dups:
            findings.append({
                "key": "duplicate_row:%s:%s" % (d["a_id"], d["b_id"]), "check": "duplicate",
                "severity": "critical", "account_id": d.get("account_id"),
                "title": "One payment recorded twice — rows #%s and #%s" % (d["a_id"], d["b_id"]),
                "amount_paise": d["a_amt"],
                "detail": "%s ₹%s and %s ₹%s for account #%s within 10 minutes (%s). Revenue is "
                          "overstated until one is marked duplicate."
                          % (d["a_src"], d["a_amt"] / 100, d["b_src"], d["b_amt"] / 100,
                             d.get("account_id"), d["created_at"])})

        # 8 - an active plan past its end with no renewal
        late = [dict(r) for r in await (await c.execute(
            "SELECT s.account_id, s.plan, s.current_period_end, a.owner_name FROM nidaan_subscriptions s "
            "LEFT JOIN nidaan_accounts a ON a.account_id=s.account_id "
            "WHERE s.status='active' AND datetime(s.current_period_end) < datetime('now','-1 day')")).fetchall()]
        for s in late:
            findings.append({
                "key": "renewal_overdue:%s:%s" % (s["account_id"], str(s["current_period_end"])[:10]),
                "check": "renewal", "severity": "warn", "account_id": s["account_id"],
                "title": "Plan still active but its period ended — account #%s" % s["account_id"],
                "detail": "%s (%s) ended %s and is still marked active with no renewal charge. Either "
                          "the renewal failed or the plan should have lapsed."
                          % (s.get("owner_name") or "", s["plan"], str(s["current_period_end"])[:10])})

    # 11 - a plan you cannot actually sell
    try:
        plans = await _n.get_plans_config() or {}
        for key, cfg in plans.items():
            if not (cfg or {}).get("active", True):
                continue
            price = int((cfg or {}).get("price_paise") or 0)
            if price <= 0:
                findings.append({
                    "key": "plan_config:%s" % key, "check": "plan_config", "severity": "critical",
                    "title": "Plan '%s' is on sale with no price" % key,
                    "detail": "Plans & Billing shows %s as active but its price is %s. A checkout "
                              "would charge nothing." % (key, price)})
    except Exception as e:  # noqa: BLE001
        logger.warning("plan config check failed: %s", e)
        ran.discard("plan_config")


# ── the run ──────────────────────────────────────────────────────────────────
async def run_guardian(*, alert: bool = True) -> dict:
    """One pass. Never raises: a guardian that crashes is worse than one that says nothing."""
    findings: list = []
    ran: set = set()
    try:
        await _check_reconcile(findings, ran)
    except Exception as e:  # noqa: BLE001
        logger.error("reconcile check failed: %s", e)
    try:
        await _check_effects_and_duplicates(findings, ran)
    except Exception as e:  # noqa: BLE001
        logger.error("effects check failed: %s", e)
    res = await _sync(findings, ran)
    try:
        await _n.set_ops_setting(HEARTBEAT_KEY, await _now())
    except Exception:
        pass
    sent = await _alert_due() if alert else 0
    # "Resolved" is an alert too: a check-only run (the Run now button, a test) says nothing.
    if res["closed"] and alert:
        await _say_resolved(res["closed"])
    return {"findings": len(findings), "checks_ran": sorted(ran), "opened": len(res["opened"]),
            "closed": len(res["closed"]), "alerts_sent": sent}


async def _supers() -> list:
    async with aiosqlite.connect(DB_PATH) as c:
        return [r[0] for r in await (await c.execute(
            "SELECT staff_id FROM nidaan_staff WHERE role='super_admin' AND status='active' "
            "AND deleted_at IS NULL")).fetchall()]


async def _alert_due() -> int:
    """Say it again, every 10 minutes, until a super admin taps Seen. After Seen, once more in two
    hours if it is still true."""
    import biz_nidaan_notifications as _nnot
    now = await _now()
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        due = [dict(r) for r in await (await c.execute(
            # `next_alert_at IS NULL` means "this one has said its piece" - it must be
            # EXCLUDED. COALESCE(next_alert_at,'') made NULL compare as '' , which is <= every
            # timestamp, so a silenced incident would have become permanently due: the exact
            # opposite of silence.
            "SELECT * FROM nidaan_pay_incidents WHERE status IN ('open','acked') "
            "AND next_alert_at IS NOT NULL AND next_alert_at <> '' "
            "AND next_alert_at <= ? ORDER BY inc_id", (now,))).fetchall()]
    if not due:
        return 0
    ids = await _supers()
    sent = 0
    for inc in due:
        again = int(inc["alert_count"] or 0)
        head = "🛑 PAYMENT" if inc["severity"] == "critical" else "⚠️ PAYMENT"
        subj = "%s — %s" % (head, inc["title"])
        body = ("%s\n\n%s\n\nFirst seen: %s%s\n\nOpen ops → Revenue → Payment Health."
                % (inc["title"], inc["detail"], inc["first_seen"],
                   ("\nSaid %d times — nobody has tapped Seen yet." % again)
                   if (again >= 1 and inc["status"] != "acked") else ""))
        if inc["status"] == "acked":
            body += "\n\n(%s tapped Seen %s and it is still not fixed.)" % (
                inc.get("acked_by_name") or "Someone", str(inc.get("acked_at") or "")[:16])
        btn = [[{"text": "👀 Seen — I'm on it", "callback_data": "pgk:%d" % inc["inc_id"]}]]
        for sid in ids:
            try:
                await _nnot._telegram_mirror(sid, subj + "\n\n" + body, url=_OPS_URL, buttons=btn)
            except Exception as e:  # noqa: BLE001
                logger.info("guardian telegram failed for %s: %s", sid, e)
        try:
            await _nnot.notify_staff_inapp(ids, subj, body, event_key="payment.guardian",
                                           email=(inc["severity"] == "critical"), telegram=False)
        except Exception as e:  # noqa: BLE001
            logger.info("guardian bell failed: %s", e)
        async with aiosqlite.connect(DB_PATH) as c:
            # status is NOT touched here. It used to be forced to 'open' on every alert, so the
            # two-hour reminder after a Seen reset the incident to unacknowledged and dropped it
            # back to every ten minutes - telling the person who had tapped Seen that nobody had.
            # An acknowledged incident stays acknowledged; only the count moves, and an acked one
            # waits the full reminder period again rather than ten minutes.
            # status is NOT touched here - it used to be forced to 'open', which wiped a Seen
            # on the very next alert.
            said = again + 1
            if inc["status"] == "acked":
                # Somebody is on it. Give them the full reminder window whatever the severity.
                await c.execute(
                    "UPDATE nidaan_pay_incidents SET alert_count=?, "
                    "next_alert_at=datetime('now', ?) WHERE inc_id=?",
                    (said, "+%d hours" % REMIND_AFTER_ACK_H, inc["inc_id"]))
            else:
                mins = _next_gap_minutes(inc["severity"], said)
                if mins is None:
                    # It has said what it has to say. Still open, still on the screen, silent.
                    logger.info("incident %s (%s) has said its piece - going quiet",
                                inc["inc_id"], inc["severity"])
                    await c.execute(
                        "UPDATE nidaan_pay_incidents SET alert_count=?, next_alert_at=NULL "
                        "WHERE inc_id=?", (said, inc["inc_id"]))
                else:
                    await c.execute(
                        "UPDATE nidaan_pay_incidents SET alert_count=?, "
                        "next_alert_at=datetime('now', ?) WHERE inc_id=?",
                        (said, "+%d minutes" % mins, inc["inc_id"]))
            await c.commit()
        sent += 1
    return sent


async def acknowledge(inc_id: int, staff_id: int, staff_name: str) -> dict:
    """A super admin has seen it: the repeats stop for everyone, and it comes back in two hours if
    it is still broken."""
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        row = await (await c.execute(
            "SELECT * FROM nidaan_pay_incidents WHERE inc_id=?", (int(inc_id),))).fetchone()
        if not row:
            return {"ok": False, "error": "That alert no longer exists."}
        inc = dict(row)
        if inc["status"] == "resolved":
            return {"ok": True, "already": "resolved", "title": inc["title"]}
        if inc["status"] == "acked":
            return {"ok": True, "already": "acked", "by": inc.get("acked_by_name") or "",
                    "title": inc["title"]}
        await c.execute(
            "UPDATE nidaan_pay_incidents SET status='acked', acked_by=?, acked_by_name=?, "
            "acked_at=CURRENT_TIMESTAMP, next_alert_at=datetime('now', ?) WHERE inc_id=?",
            (int(staff_id), (staff_name or "")[:80], "+%d hours" % REMIND_AFTER_ACK_H, int(inc_id)))
        await c.commit()
    # Tell the other super admins, so nobody duplicates the work.
    import biz_nidaan_notifications as _nnot
    for sid in await _supers():
        if sid == staff_id:
            continue
        try:
            await _nnot._telegram_mirror(
                sid, "👀 Seen by %s — %s\n\nThey are on it. If it is still not fixed in %d hours, "
                     "this will come back." % (staff_name, inc["title"], REMIND_AFTER_ACK_H),
                url=_OPS_URL)
        except Exception:
            pass
    return {"ok": True, "title": inc["title"]}


async def _say_resolved(closed: list) -> None:
    import biz_nidaan_notifications as _nnot
    ids = await _supers()
    for r in closed:
        try:
            await _nnot.notify_staff_inapp(
                ids, "✅ Payment issue resolved — %s" % r["title"],
                "The check that raised this now passes. Nothing further to do.",
                event_key="payment.guardian_ok", email=False)
        except Exception:
            pass


# ── is the guardian itself alive? (called from the web processes) ────────────
async def heartbeat_check() -> dict:
    """The guardian runs in the worker. If the worker dies, nobody would ever hear from it again -
    so the web processes check its heartbeat. The incident key is fixed, so both web processes
    checking cannot produce two alerts."""
    last = await _n.get_ops_setting(HEARTBEAT_KEY, "") or ""
    stale = True
    if last:
        try:
            stale = (datetime.utcnow() - datetime.fromisoformat(last[:19])) > timedelta(minutes=HEARTBEAT_STALE_MIN)
        except Exception:
            stale = True
    if not stale:
        await _sync([], {"heartbeat"})
        return {"ok": True, "last": last}
    await _sync([{
        "key": "guardian_silent", "check": "heartbeat", "severity": "critical",
        "title": "The payment guardian has stopped running",
        "detail": "It last ran %s. While it is silent, nothing is watching the payment mechanics. "
                  "Check the sarathi-worker service." % (last or "never"),
    }], {"heartbeat"})
    await _alert_due()
    return {"ok": False, "last": last}
