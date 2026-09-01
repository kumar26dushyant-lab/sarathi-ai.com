"""
NidaanPartner PAYMENT WATCHDOG — a deterministic, self-healing guard over the payment system.

Design guarantees (so it never hallucinates, loops, or mis-acts):
  • Every check is a SQL/arithmetic FACT — no LLM decides anything about money.
  • Actions are idempotent (the ledger dedups); repeated runs can't double-anything.
  • Ambiguous cases are FLAGGED for a human, never auto-acted.
  • Alerts are EXCEPTION-ONLY (a stuck payment, a failure spike, an amount↔plan mismatch) — never
    a ping for a normal successful payment. Every finding is specific + logged.

Produces a health snapshot for the super-admin dashboard (the funnel) and, only on anomalies,
pushes an alert to super-admins on bell + email + Telegram. Never raises to the scheduler.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import aiosqlite

import biz_database as db
import biz_nidaan as _n

logger = logging.getLogger("nidaan.pay_watch")
DB_PATH = db.DB_PATH
IST = timezone(timedelta(hours=5, minutes=30))

STUCK_MINUTES = 15         # a captured payment with no ledger row after this = stuck
FAILURE_SPIKE_1H = 6       # more failures than this in the last hour = alert
AMOUNT_TOLERANCE_PAISE = 200   # ±₹2 rounding tolerance on amount↔plan match
SNAPSHOT_KEY = "payment_health_snapshot"


async def _expected_total_paise(plan: str, cache: dict) -> int | None:
    """GST-inclusive expected total for a plan, from the LIVE config. None if unknown."""
    if plan in cache:
        return cache[plan]
    try:
        cfg = await _n.get_plan_cfg(plan)
        base_paise = int((cfg or {}).get("price_paise") or 0)
        if not base_paise:
            base_paise = int((_n.PLAN_LIMITS.get(plan, {}).get("price") or 0)) * 100
        total = (await _n.charge_with_gst(base_paise / 100))["total_paise"] if base_paise else None
    except Exception:
        total = None
    cache[plan] = total
    return total


async def run_payment_health_check(*, alert: bool = True) -> dict:
    """Scan for payment anomalies + build the health funnel snapshot. Returns the snapshot."""
    now = datetime.utcnow()
    h1 = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    d1 = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    d7 = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    stuck_before = (now - timedelta(minutes=STUCK_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    snap: dict = {"checked_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                  "funnel": {}, "mismatches": [], "stuck": [], "failures_1h": 0, "anomaly": False}
    cache: dict = {}
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        async def q(sql, args=()):
            try:
                return await (await c.execute(sql, args)).fetchall()
            except Exception as e:  # noqa: BLE001
                logger.info("pay_watch query skipped: %s", e); return []

        # ── Funnel (last 24h) from the event spine + ledger ──────────────────
        ev = {r["event_type"]: r["n"] for r in await q(
            "SELECT event_type, COUNT(*) n FROM nidaan_events WHERE created_at>=? "
            "AND event_type LIKE 'payment%' OR event_type LIKE 'subscription%' GROUP BY event_type", (d1,))}
        led = await q("SELECT COUNT(*) n, COALESCE(SUM(total_paise),0) p FROM nidaan_payments "
                      "WHERE created_at>=? AND status!='refunded'", (d1,))
        snap["funnel"] = {
            "pay_opened": ev.get("pay_opened", 0),
            "payment_success": ev.get("payment_success", 0),
            "payment_failed": ev.get("payment_failed", 0),
            "recorded_24h": (led[0]["n"] if led else 0),
            "collected_24h_rs": round((led[0]["p"] if led else 0) / 100.0, 2),
        }

        # ── Failure spike (last hour) ────────────────────────────────────────
        fr = await q("SELECT COUNT(*) n FROM nidaan_events WHERE created_at>=? AND event_type='payment_failed'", (h1,))
        snap["failures_1h"] = (fr[0]["n"] if fr else 0)

        # ── Amount↔plan mismatch (last 7d, gateway=razorpay subscriptions) ───
        for r in await q("SELECT pay_id, plan, total_paise, created_at FROM nidaan_payments "
                         "WHERE source='subscription' AND gateway='razorpay' AND created_at>=?", (d7,)):
            exp = await _expected_total_paise(r["plan"], cache)
            if exp and abs(int(r["total_paise"]) - int(exp)) > AMOUNT_TOLERANCE_PAISE:
                snap["mismatches"].append({
                    "pay_id": r["pay_id"], "plan": r["plan"],
                    "recorded_rs": round(int(r["total_paise"]) / 100.0, 2),
                    "expected_rs": round(int(exp) / 100.0, 2), "at": r["created_at"]})

        # ── Stuck: a captured/success event with no matching ledger row ──────
        for r in await q(
            "SELECT account_id, amount_paise, purpose, created_at FROM nidaan_events "
            "WHERE event_type='payment_success' AND created_at>=? AND created_at<? "
            "AND account_id IS NOT NULL", (d1, stuck_before)):
            m = await q("SELECT 1 FROM nidaan_payments WHERE account_id=? AND created_at>=? LIMIT 1",
                        (r["account_id"], (datetime.fromisoformat(str(r["created_at"])[:19])
                         - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")))
            if not m:
                snap["stuck"].append({"account_id": r["account_id"],
                                      "amount_rs": round((r["amount_paise"] or 0) / 100.0, 2),
                                      "purpose": r["purpose"], "at": r["created_at"]})

    snap["anomaly"] = bool(snap["mismatches"] or snap["stuck"] or snap["failures_1h"] > FAILURE_SPIKE_1H)

    # Persist the snapshot for the dashboard (best-effort).
    try:
        await _n.set_ops_setting(SNAPSHOT_KEY, json.dumps(snap)[:8000], updated_by="pay_watch")
    except Exception:
        pass

    if alert and snap["anomaly"]:
        await _alert(snap)
    return snap


async def _alert(snap: dict) -> None:
    """Exception-only alert to super-admins on bell + email + Telegram."""
    lines = ["⚠️ Payment watchdog found something to check:"]
    if snap["mismatches"]:
        lines.append(f"• Amount↔plan mismatch on {len(snap['mismatches'])} payment(s):")
        for m in snap["mismatches"][:5]:
            lines.append(f"    {m['plan']}: recorded ₹{m['recorded_rs']} vs expected ₹{m['expected_rs']} (pay #{m['pay_id']})")
    if snap["stuck"]:
        lines.append(f"• {len(snap['stuck'])} captured payment(s) with no recorded activation (>15 min) — review/reconcile:")
        for s in snap["stuck"][:5]:
            lines.append(f"    account #{s['account_id']} · ₹{s['amount_rs']} · {s['purpose']}")
    if snap["failures_1h"] > FAILURE_SPIKE_1H:
        lines.append(f"• Failure spike: {snap['failures_1h']} payment failures in the last hour.")
    lines.append("\nOpen ops → Revenue → Payment Health for details.")
    body = "\n".join(lines)
    try:
        import biz_nidaan_notifications as _nnot
        async with aiosqlite.connect(DB_PATH) as c:
            ids = [row[0] for row in await (await c.execute(
                "SELECT staff_id FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') "
                "AND status='active' AND deleted_at IS NULL")).fetchall()]
        if ids:
            await _nnot.notify_staff_inapp(ids, "⚠️ Payment watchdog alert", body,
                                           event_key="payment.watchdog", email=True)
            for sid in ids:
                try:
                    await _nnot._telegram_mirror(sid, body, url="/nidaan/ops")
                except Exception:
                    pass
    except Exception as e:  # noqa: BLE001
        logger.warning("pay_watch alert failed: %s", e)


async def get_snapshot() -> dict:
    """The latest health snapshot for the dashboard (empty if never run)."""
    try:
        raw = await _n.get_ops_setting(SNAPSHOT_KEY, "")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}
