# -*- coding: utf-8 -*-
"""Every morning: yesterday's payments at Razorpay, against our books - said out loud.

Founder, 29 Sep: "calculation of payment and revenue should be correct, our intelligent bot should
confirm payment from razorpay ledger and update everyday or at schedule time."

The Payment Guardian (biz_nidaan_pay_guard) already compares Razorpay with the ledger every five
minutes and RECOVERS a captured payment we missed. But it speaks only when something is wrong, so
a quiet day and a guardian that has stopped looking feel the same from the outside. This is the
other half: one message a day that says what was checked and that it matched - or exactly what did
not. A check must read an outcome, not a configuration; "the guardian is on" is not "the money is
right".

What it compares, for one IST day:
  * Razorpay: every CAPTURED payment that is ours (pay_guard._is_ours - one Razorpay account also
    serves Sarathi), all pages of it;
  * our ledger (nidaan_payments), matched BY PAYMENT ID - the only comparison that cannot be fooled
    by two windows cut at slightly different moments;
  * and it lists what was recorded by hand, which Razorpay cannot vouch for.

It READS only. It never records, refunds or changes anything; recovering a missing payment stays
the guardian's job, and the message says so.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import aiosqlite

import biz_database as db

logger = logging.getLogger("sarathi.nidaan.pay_daily")

IST = timezone(timedelta(hours=5, minutes=30))
SEND_HOUR_IST = 9
LAST_KEY = "pay_daily_check_last"      # the IST day last reported, so a restart never repeats it
PAGE = 100
MAX_PAGES = 20

_KIND = {"subscription": "Subscription", "subscription_renewal": "Renewal",
         "per_claim_review": "Claim review fee", "branch_l2": "Level-2 fee",
         "payment_link": "Payment link"}


def _db() -> str:
    return db.DB_PATH


def day_bounds(day: date) -> tuple:
    """(epoch start, epoch end, utc start text, utc end text) for one IST calendar day."""
    start = datetime(day.year, day.month, day.day, tzinfo=IST)
    end = start + timedelta(days=1)
    fmt = "%Y-%m-%d %H:%M:%S"
    return (int(start.timestamp()), int(end.timestamp()),
            start.astimezone(timezone.utc).strftime(fmt), end.astimezone(timezone.utc).strftime(fmt))


async def razorpay_day(day: date) -> tuple:
    """(payments, ok) - every payment Razorpay has for that IST day, all pages."""
    import httpx
    import biz_nidaan_pay_guard as pg
    key, sec = pg._rzp_auth()
    if not (key and sec):
        return [], False
    frm, to, _a, _b = day_bounds(day)
    out = []
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            for page in range(MAX_PAGES):
                r = await c.get("https://api.razorpay.com/v1/payments",
                                params={"from": frm, "to": to - 1, "count": PAGE,
                                        "skip": page * PAGE}, auth=(key, sec))
                if r.status_code != 200:
                    logger.warning("daily check: razorpay %s", r.status_code)
                    return out, False
                items = (r.json() or {}).get("items") or []
                out += items
                if len(items) < PAGE:
                    break
    except Exception as e:  # noqa: BLE001
        logger.warning("daily check: razorpay unreachable: %s", e)
        return out, False
    return out, True


async def check_day(day: date, *, payments: Optional[list] = None, ok: bool = True) -> dict:
    """Compare one IST day. `payments` may be supplied (tests); otherwise Razorpay is asked."""
    import biz_nidaan_pay_guard as pg
    if payments is None:
        payments, ok = await razorpay_day(day)
    _f, _t, utc_a, utc_b = day_bounds(day)
    async with aiosqlite.connect(_db()) as c:
        ledger = {r[0]: (int(r[1] or 0), r[2] or "") for r in await (await c.execute(
            "SELECT razorpay_payment_id, total_paise, source FROM nidaan_payments "
            "WHERE COALESCE(razorpay_payment_id,'')<>''")).fetchall()}
        by_hand = [(int(r[0] or 0), r[1] or "") for r in await (await c.execute(
            "SELECT total_paise, source FROM nidaan_payments WHERE created_at >= ? "
            "AND created_at < ? AND COALESCE(verified,0)=0", (utc_a, utc_b))).fetchall()]
    ours = [p for p in (payments or [])
            if p.get("status") == "captured" and pg._is_ours(p, p.get("id") in ledger)]
    missing = [p for p in ours if p.get("id") not in ledger]
    differs = [p for p in ours if p.get("id") in ledger
               and ledger[p["id"]][0] != int(p.get("amount") or 0)]
    kinds: dict = {}
    for p in ours:
        k = _KIND.get((ledger.get(p.get("id")) or (0, ""))[1], "Not in our books")
        kinds[k] = kinds.get(k, 0) + 1
    return {
        "day": day.isoformat(), "reached": bool(ok),
        "count": len(ours), "total_paise": sum(int(p.get("amount") or 0) for p in ours),
        "booked": len(ours) - len(missing),
        "booked_paise": sum(ledger[p["id"]][0] for p in ours if p.get("id") in ledger),
        "missing": [{"id": p.get("id"), "paise": int(p.get("amount") or 0)} for p in missing],
        "differs": [{"id": p.get("id"), "paise": int(p.get("amount") or 0),
                     "ours": ledger[p["id"]][0]} for p in differs],
        "by_kind": kinds, "by_hand": by_hand,
        "match": bool(ok) and not missing and not differs,
    }


def _rs(paise: int) -> str:
    v = paise / 100.0
    return "Rs " + (("{:,.2f}".format(v)).rstrip("0").rstrip(".") if v % 1 else "{:,.0f}".format(v))


def message(r: dict) -> tuple:
    """(subject, body) - plain words, one screen."""
    d = datetime.strptime(r["day"], "%Y-%m-%d").strftime("%a %d %b")
    if not r["reached"]:
        return ("⚠️ Payments check %s — could not reach Razorpay" % d,
                "Razorpay did not answer, so yesterday's payments could not be checked.\n"
                "The Payment Guardian keeps checking every 5 minutes and will alert on anything "
                "wrong. If this repeats tomorrow, the Razorpay keys need a look.")
    head = ("✅ Payments check %s — all match" % d if r["match"]
            else "\U0001f6a8 Payments check %s — something does not match" % d)
    lines = ["Razorpay captured: %d payment(s) · %s" % (r["count"], _rs(r["total_paise"])),
             "In our books:      %d payment(s) · %s" % (r["booked"], _rs(r["booked_paise"]))]
    if r["by_kind"]:
        lines.append("By type: " + " · ".join("%s %d" % kv for kv in sorted(r["by_kind"].items())))
    if r["count"] == 0:
        lines.append("No payments yesterday.")
    for m in r["missing"]:
        lines.append("• Taken at Razorpay, NOT in our books: …%s %s"
                     % (str(m["id"])[-6:], _rs(m["paise"])))
    for m in r["differs"]:
        lines.append("• Amount differs: …%s Razorpay %s, ours %s"
                     % (str(m["id"])[-6:], _rs(m["paise"]), _rs(m["ours"])))
    if r["missing"]:
        lines.append("The Payment Guardian recovers a missing payment on its own - check "
                     "Payment Health that it did.")
    if r["by_hand"]:
        lines.append("Recorded by hand (Razorpay cannot confirm these): %d · %s"
                     % (len(r["by_hand"]), _rs(sum(p for p, _s in r["by_hand"]))))
    lines.append("")
    lines.append("Revenue in ops reads these same books.")
    return head, "\n".join(lines)


async def run_daily(today: Optional[date] = None, *, force: bool = False) -> dict:
    """Check yesterday (IST) and tell the super admins - once per day, whatever restarts."""
    import biz_nidaan as _n
    import biz_nidaan_notifications as _nn
    today = today or datetime.now(IST).date()
    day = today - timedelta(days=1)
    if not force and str(await _n.get_ops_setting(LAST_KEY, "") or "") == day.isoformat():
        return {"skipped": "already reported", "day": day.isoformat()}
    r = await check_day(day)
    subject, body = message(r)
    ids = [a["staff_id"] for a in await _nn._super_admin_staff()]
    if ids:
        await _nn.notify_staff_inapp(ids, subject, body, event_key="payment.daily_check",
                                     email=False)
    # Stamped only after sending: a crash before this repeats the report, never skips it.
    await _n.set_ops_setting(LAST_KEY, day.isoformat())
    return {"day": day.isoformat(), "match": r["match"], "reached": r["reached"],
            "count": r["count"], "told": len(ids)}
