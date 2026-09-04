"""
NidaanPartner — PROACTIVE HEALTH WATCHDOG.

App Health is a dashboard: it only tells you something is broken when a human happens to look.
That is how the WhatsApp number sat unregistered for days (every send failing 133010) and how a
renewal webhook could have silently stopped landing. This closes that gap: the worker runs the
SAME checks the panel runs and pushes an alert the moment a subsystem breaks.

Design rules that keep it useful rather than noisy:
  • EDGE-TRIGGERED — alert when a check flips healthy → failing, and again when it recovers.
    A subsystem that is broken all afternoon produces one alert, not one every cycle.
  • QUIET WHEN HEALTHY — nothing is sent while everything is green.
  • RE-ARM AFTER A LONG OUTAGE — if something stays broken past `_RENOTIFY_HOURS` we remind once,
    so a failure can't be forgotten after the first message scrolls away.
  • NEVER RAISES into the worker loop.

State lives in nidaan_ops_settings (a JSON blob), so it survives restarts and needs no schema.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger("nidaan.health.watch")

_STATE_KEY = "health_watch_state"
_RENOTIFY_HOURS = 12          # remind once if a subsystem is still broken after this long

# Subsystems worth waking a human for. Anything else is informational only.
_CRITICAL = {
    "Database", "WhatsApp Cloud API", "Email Radar", "AI (Gemini)", "SMTP (email out)",
    "Subscription renewals", "Backups", "Disk", "Payments (Razorpay)", "Doc Splitter",
}


async def _load_state() -> dict:
    try:
        import biz_nidaan as _n
        raw = await _n.get_ops_setting(_STATE_KEY, "") or ""
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


async def _save_state(state: dict) -> None:
    try:
        import biz_nidaan as _n
        await _n.set_ops_setting(_STATE_KEY, json.dumps(state)[:60000], updated_by="health_watch")
    except Exception as e:  # noqa: BLE001
        logger.debug("health watch state save failed: %s", e)


def _should_notify(prev: dict, name: str, ok: bool, now: datetime) -> tuple[bool, str]:
    """(notify?, kind) — 'broke' on a healthy→failing edge, 'recovered' on the way back,
    'still' when a long-running failure needs one reminder."""
    p = prev.get(name) or {}
    was_ok = p.get("ok", True)
    if ok and not was_ok:
        return True, "recovered"
    if not ok and was_ok:
        return True, "broke"
    if not ok and not was_ok:
        last = p.get("notified_at")
        if last:
            # Narrow catch on purpose: only a malformed stored timestamp should be tolerated.
            # A broad except here would silently swallow real bugs and quietly stop re-notifying,
            # which is the one failure mode a watchdog must never have.
            try:
                parsed = datetime.fromisoformat(last)
            except (TypeError, ValueError):
                return False, ""
            if now - parsed >= timedelta(hours=_RENOTIFY_HOURS):
                return True, "still"
    return False, ""


async def run_health_watch(*, alert: bool = True) -> dict:
    """One watchdog cycle. Returns {checked, failing, alerted}. Never raises."""
    out = {"checked": 0, "failing": [], "alerted": []}
    try:
        import sarathi_biz as _app
        checks = await _app._subsystem_checks()
        # The core services the panel checks first (DB/payments/disk) aren't in the extracted
        # helper, so add the two cheapest, highest-signal ones here.
        try:
            import shutil as _sh
            du = _sh.disk_usage(".")
            pct = round(du.used / du.total * 100, 1)
            checks.append({"name": "Disk", "ok": pct < 90, "note": f"{pct}% used"})
        except Exception:
            pass
    except Exception as e:  # noqa: BLE001
        logger.warning("health watch could not run checks: %s", e)
        return out

    now = datetime.utcnow()
    prev = await _load_state()
    new_state, to_alert = {}, []
    for c in checks:
        name, ok = c.get("name", "?"), bool(c.get("ok"))
        out["checked"] += 1
        if not ok:
            out["failing"].append(name)
        entry = {"ok": ok, "notified_at": (prev.get(name) or {}).get("notified_at")}
        if name in _CRITICAL:
            notify, kind = _should_notify(prev, name, ok, now)
            if notify:
                to_alert.append((kind, name, c.get("note", "")))
                entry["notified_at"] = now.isoformat()
        new_state[name] = entry
    await _save_state(new_state)

    if to_alert and alert:
        try:
            await _send_alert(to_alert)
            out["alerted"] = [f"{k}:{n}" for k, n, _ in to_alert]
        except Exception as e:  # noqa: BLE001
            logger.warning("health watch alert failed: %s", e)
    return out


async def _send_alert(items: list) -> None:
    """One consolidated message to every super-admin, on every channel they have."""
    broke = [(n, note) for k, n, note in items if k == "broke"]
    still = [(n, note) for k, n, note in items if k == "still"]
    fixed = [n for k, n, _ in items if k == "recovered"]

    lines = []
    if broke:
        lines.append("🔴 STOPPED WORKING")
        lines += [f"  • {n} — {note}" if note else f"  • {n}" for n, note in broke]
    if still:
        lines.append("\n🟠 STILL DOWN")
        lines += [f"  • {n} — {note}" if note else f"  • {n}" for n, note in still]
    if fixed:
        lines.append("\n✅ BACK TO NORMAL")
        lines += [f"  • {n}" for n in fixed]
    lines.append("\nOpen App Health in ops for detail — several of these have a self-serve fix button.")
    body = "\n".join(lines)
    subject = ("🔴 NidaanPartner: %d subsystem(s) down" % (len(broke) + len(still))
               if (broke or still) else "✅ NidaanPartner: subsystems recovered")

    import aiosqlite
    import biz_database as _db
    async with aiosqlite.connect(_db.DB_PATH) as conn:
        rows = await (await conn.execute(
            "SELECT staff_id FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') "
            "AND status='active' AND deleted_at IS NULL")).fetchall()
    ids = [r[0] for r in rows]
    if not ids:
        logger.warning("health watch: no super-admin to alert")
        return
    import biz_nidaan_notifications as _nnot
    await _nnot.notify_staff_inapp(ids, subject, body, event_key="health.subsystem",
                                   email=bool(broke or still))
    for sid in ids:
        try:
            await _nnot._telegram_mirror(sid, f"{subject}\n\n{body}", url="/nidaan/ops")
        except Exception:
            pass
