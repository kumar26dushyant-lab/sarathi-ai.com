"""
biz_nidaan_notifications.py  —  NidaanPartner Notification + Comms Hub
─────────────────────────────────────────────────────────────────────────────
Phase 4 (Jun 2026).  Central event-driven dispatcher for all Nidaan
notifications (claim updates, task events, document acknowledgements, etc.).

Channels
  • Dashboard       — always written to nidaan_notifications + thread (no transport)
  • WhatsApp        — via Evolution API, routed through 3 official Nidaan numbers
  • Email           — Gmail SMTP fallback when WA fails / not opted-in

Routing
  • Subscribers     — sticky-per-account assignment to ONE of the 3 numbers.
                      Failover only if assigned number unhealthy 3+ minutes.
  • Staff           — round-robin across the 3 numbers (load balanced).

Adaptive cap
  • active_count=3  → per-number cap = base
  • active_count=2  → per-number cap = base × 1.5  (total = base × 3)
  • active_count=1  → per-number cap = base × 2    (total = base × 2)
  • active_count=0  → all WA fails; email fallback kicks in
  • Warm-up baseline:  day 1-7 = 30, day 8-30 = 100, day 31+ = 200 per number
  • When per-number usage > 70% → defer P2 to next-day queue
  • When per-number usage > 90% → defer P1 too; only P0 ships

Priority
  • P0  always sent (OTPs, payment receipts, urgent legal deadlines, security)
  • P1  important   (claim status, task assigned, doc received confirmation)
  • P2  informational (notes added, FYI, weekly digest)

Quiet hours (system flags quiet_hours_start / quiet_hours_end)
  • No WA/SMS during quiet window. Email and dashboard still send.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, time, timezone, timedelta, date
from typing import Optional, Any

import aiosqlite

import biz_database as db
import biz_nidaan_tasks as ntasks

logger = logging.getLogger("sarathi.nidaan.notifications")


# ═════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═════════════════════════════════════════════════════════════════════════════
PRIORITY_P0 = "P0"   # Always
PRIORITY_P1 = "P1"   # Defer at <10% budget
PRIORITY_P2 = "P2"   # Defer at <30% budget

CHANNEL_DASHBOARD = "dashboard"
CHANNEL_WHATSAPP  = "whatsapp"
CHANNEL_EMAIL     = "email"

RECIPIENT_SUBSCRIBER = "subscriber"
RECIPIENT_STAFF      = "staff"


# IST is UTC+5:30 — used for quiet-hours calc.
IST = timezone(timedelta(hours=5, minutes=30))


# ═════════════════════════════════════════════════════════════════════════════
#  Phone normalization
# ═════════════════════════════════════════════════════════════════════════════
def _norm_phone(p: str) -> str:
    """Strict Indian-mobile normaliser. Returns a clean 10-digit number, or ''
    if the input is not a valid mobile. CRITICAL: we must NEVER silently
    truncate a malformed number (e.g. an 11-digit typo) into a different but
    deliverable number — that risks messaging a stranger. So we only strip a
    recognised country/trunk prefix and otherwise reject."""
    digits = re.sub(r"[^0-9]", "", str(p or ""))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]            # +91XXXXXXXXXX
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]            # 0XXXXXXXXXX (STD trunk prefix)
    # A valid Indian mobile is exactly 10 digits starting 6-9.
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return ""


def _to_wa_jid(p: str) -> str:
    n = _norm_phone(p)
    return f"91{n}@s.whatsapp.net" if n else ""


# ═════════════════════════════════════════════════════════════════════════════
#  Official instance registry
# ═════════════════════════════════════════════════════════════════════════════
async def list_official_instances() -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_official_instances ORDER BY instance_slot")
        return [dict(r) for r in await cur.fetchall()]


async def get_official_instance(slot: int) -> Optional[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_official_instances WHERE instance_slot=?", (slot,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def upsert_official_instance(*, instance_slot: int,
                                   evolution_instance: str,
                                   display_name: str = "",
                                   phone_number: str = "") -> dict:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO nidaan_official_instances
              (instance_slot, evolution_instance, display_name, phone_number,
               health_state, warmup_started_at)
            VALUES (?, ?, ?, ?, 'disconnected', datetime('now'))
            ON CONFLICT(instance_slot) DO UPDATE SET
              evolution_instance=excluded.evolution_instance,
              display_name=excluded.display_name,
              phone_number=excluded.phone_number,
              updated_at=datetime('now')
        """, (instance_slot, evolution_instance, display_name, phone_number))
        await conn.commit()
    return await get_official_instance(instance_slot) or {}


async def delete_official_instance(slot: int) -> bool:
    """Remove an official number registration (and best-effort logout in
    Evolution so the SIM's WhatsApp is unlinked)."""
    inst = await get_official_instance(slot)
    if not inst:
        return False
    try:
        import biz_whatsapp_evolution as wa_evo
        await wa_evo.logout_instance(inst["evolution_instance"])
    except Exception:
        pass  # logout is best-effort; still remove the registration
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM nidaan_official_instances WHERE instance_slot = ?", (slot,))
        await conn.commit()
    return True


async def update_instance_health(slot: int, *, state: str, own_jid: str = "",
                                 phone_number: str = "") -> None:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        sets = ["health_state = ?", "updated_at = datetime('now')"]
        vals: list[Any] = [state]
        if state in ("open", "connected"):
            sets.append("last_connected_at = datetime('now')")
        elif state in ("close", "disconnected", "refused", "logout"):
            sets.append("last_disconnected_at = datetime('now')")
        if own_jid:
            sets.append("own_jid = ?"); vals.append(own_jid)
        if phone_number:
            sets.append("phone_number = ?"); vals.append(phone_number)
        vals.append(slot)
        await conn.execute(
            f"UPDATE nidaan_official_instances SET {', '.join(sets)} WHERE instance_slot=?",
            vals)
        await conn.commit()


def _is_healthy(state: str) -> bool:
    return (state or "").lower() in ("open", "connected")


async def _list_healthy_instances() -> list[dict]:
    insts = await list_official_instances()
    out = []
    for i in insts:
        if not _is_healthy(i.get("health_state", "")):
            continue
        # Honour temporary paused_until
        if i.get("paused_until"):
            try:
                pu = datetime.fromisoformat(str(i["paused_until"]).replace(" ", "T"))
                if pu > datetime.utcnow():
                    continue
            except Exception:
                pass
        out.append(i)
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  Adaptive cap
# ═════════════════════════════════════════════════════════════════════════════
async def _per_number_base_cap(instance: dict) -> int:
    """Base cap depending on warm-up day."""
    started = instance.get("warmup_started_at")
    if not started:
        # Treat as fresh — warm-up
        warmup_cap = int(await ntasks.get_flag("nidaan_wa_warmup_day_cap", "30") or "30")
        return warmup_cap
    try:
        started_dt = datetime.fromisoformat(str(started).replace(" ", "T"))
        days = max(1, (datetime.utcnow() - started_dt).days + 1)
    except Exception:
        days = 1
    if days <= 7:
        return int(await ntasks.get_flag("nidaan_wa_warmup_day_cap", "30") or "30")
    if days <= 30:
        return int(await ntasks.get_flag("nidaan_wa_ramp_day_cap", "100") or "100")
    return int(await ntasks.get_flag("nidaan_wa_steady_day_cap", "200") or "200")


async def compute_effective_caps() -> dict:
    """Returns per-slot effective daily cap given active-count adjustment.
    Schema:
      {
        "active_count": N,
        "by_slot": { slot: {effective_cap, base_cap, sent_today, usage_pct, defer_p2, defer_p1} },
        "total_remaining": int
      }
    """
    healthy = await _list_healthy_instances()
    active_count = len(healthy)
    multiplier = {3: 1.0, 2: 1.5, 1: 2.0}.get(active_count, 0.0)
    p1_thresh = int(await ntasks.get_flag("nidaan_wa_defer_threshold_p1", "10") or "10")
    p2_thresh = int(await ntasks.get_flag("nidaan_wa_defer_threshold_p2", "30") or "30")
    today = date.today().isoformat()
    out: dict = {"active_count": active_count, "by_slot": {}, "total_remaining": 0}
    for i in healthy:
        # Reset daily count if rolled over
        sent_today = i.get("daily_sent_count", 0) or 0
        last_reset = i.get("daily_count_reset_at")
        if str(last_reset) != today:
            sent_today = 0
        base_cap = await _per_number_base_cap(i)
        effective_cap = int(round(base_cap * multiplier))
        remaining = max(0, effective_cap - sent_today)
        usage_pct = 0 if effective_cap == 0 else int(100 * sent_today / effective_cap)
        defer_p2 = usage_pct >= (100 - p2_thresh)
        defer_p1 = usage_pct >= (100 - p1_thresh)
        out["by_slot"][i["instance_slot"]] = {
            "evolution_instance": i["evolution_instance"],
            "effective_cap": effective_cap,
            "base_cap": base_cap,
            "sent_today": sent_today,
            "remaining": remaining,
            "usage_pct": usage_pct,
            "defer_p2": defer_p2,
            "defer_p1": defer_p1,
        }
        out["total_remaining"] += remaining
    return out


async def wa_send_health() -> dict:
    """Per-slot 'can this number actually SEND?' health, derived from recent WhatsApp
    send outcomes in the notification log. Evolution can report state 'open' while
    every send fails with SessionError — a ghost connection. Returns
    {slot: {broken, session_error, last_error, failed_recent, sent_recent}}."""
    out: dict = {}
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT instance_slot, status, error FROM nidaan_notifications "
            "WHERE channel='whatsapp' AND instance_slot IS NOT NULL "
            "AND created_at >= datetime('now','-24 hours') "
            "ORDER BY notif_id DESC")).fetchall()
    by_slot: dict = {}
    for r in rows:
        by_slot.setdefault(r["instance_slot"], []).append(dict(r))
    for slot, attempts in by_slot.items():
        newest = attempts[0]
        sent_recent = sum(1 for a in attempts if a["status"] == "sent")
        failed_recent = sum(1 for a in attempts if a["status"] == "failed")
        # Honest CURRENT health: judge by the latest streak, not "any success in the
        # last 24h" (a line that sent this morning but fails every send now must read
        # as DOWN). Count consecutive failures from newest back to the last success.
        newest_failed = newest["status"] == "failed"
        newest_err = (newest.get("error") or "").lower()
        newest_session = ("session" in newest_err) or ("no sessions" in newest_err)
        consec_fail = 0
        for a in attempts:
            if a["status"] == "failed":
                consec_fail += 1
            elif a["status"] == "sent":
                break
            # other statuses (deferred/suppressed) don't count either way
        # Down now if the newest send failed AND either it's a session error (line is
        # dead) or there's a run of failures with no success since.
        broken = bool(newest_failed and (newest_session or consec_fail >= 2))
        last_fail = next((a for a in attempts if a["status"] == "failed"), None)
        last_err = ((last_fail or {}).get("error") or "")
        session_err = ("session" in last_err.lower()) or ("no sessions" in last_err.lower())
        out[slot] = {
            "broken": broken,
            "session_error": session_err,
            "last_error": last_err[:120],
            "failed_recent": failed_recent,
            "sent_recent": sent_recent,
        }
    return out


# ═════════════════════════════════════════════════════════════════════════════
#  WhatsApp line WATCHDOG — self-monitoring / auto-recovery / escalation / resume
#  A deterministic orchestrator (NOT an LLM — you never want an AI guessing whether
#  to restart a line). Each cycle it: detects a line that can't send (from real send
#  outcomes), tries an automatic restart, escalates to super-admins via email + app
#  + dashboard (never the dead WhatsApp) when it can't self-heal, and announces
#  recovery so WhatsApp resumes on its own.
# ═════════════════════════════════════════════════════════════════════════════
async def _all_registered_instances() -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT instance_slot, evolution_instance, phone_number, display_name, health_state "
            "FROM nidaan_official_instances ORDER BY instance_slot")).fetchall()
        return [dict(r) for r in rows]


async def _super_admin_staff() -> list[dict]:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await (await conn.execute(
            "SELECT staff_id, name, phone, "
            "       COALESCE(NULLIF(notify_email,''), email) AS email "
            "FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') "
            "AND status='active' AND deleted_at IS NULL")).fetchall()
        return [dict(r) for r in rows]


async def _wd_load(slot: int) -> dict:
    import biz_nidaan as _nid
    raw = (await _nid.get_ops_setting(f"wa_wd_slot{slot}", "") or "")
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


async def _wd_save(slot: int, st: dict) -> None:
    import biz_nidaan as _nid
    try:
        await _nid.set_ops_setting(f"wa_wd_slot{slot}", json.dumps(st))
    except Exception as e:
        logger.warning("watchdog state save failed slot %s: %s", slot, e)


async def _wd_probe(slot: int) -> Optional[bool]:
    """Real send to the configured probe number. While a line is DOWN this fails
    silently (nothing is delivered); on recovery it delivers exactly one message and
    returns True — so it doubles as the 'it's back' ping. None if no probe target."""
    import biz_nidaan as _nid
    probe_num = (await _nid.get_ops_setting("wa_probe_number", "") or "").strip()
    if not probe_num:
        for s in await _super_admin_staff():
            if s.get("phone"):
                probe_num = s["phone"]; break
    if not probe_num:
        return None
    jid = _to_wa_jid(probe_num)
    if not jid:
        return None
    ok, _wid, _err = await _send_wa(
        instance_slot=slot, jid=jid,
        message="🔧 Nidaan WhatsApp health check — this line is back online.")
    return bool(ok)


async def _wd_alert_admins(*, subject: str, body: str, event_key: str) -> None:
    """Alert every super-admin via dashboard bell + web push + email. NEVER WhatsApp
    (the whole point is that WhatsApp is down)."""
    admins = await _super_admin_staff()
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    for a in admins:
        try:
            await _record_notification(
                event_key=event_key, priority=PRIORITY_P1,
                recipient_type=RECIPIENT_STAFF, recipient_id=a["staff_id"],
                channel=CHANNEL_DASHBOARD, subject=subject, body=body,
                status="sent", sent_at=ts)   # dashboard record also fires web push
        except Exception as e:
            logger.warning("watchdog bell alert failed for staff %s: %s", a.get("staff_id"), e)
        if a.get("email"):
            try:
                await _send_email(to_email=a["email"], subject=f"[Nidaan] {subject}",
                                  html_body=body.replace("\n", "<br>"), text_body=body)
            except Exception:
                pass


async def run_wa_watchdog_cycle() -> dict:
    """One monitoring pass over all official WhatsApp lines. Enabled by flag
    nidaan_wa_watchdog_enabled (default on)."""
    if (await ntasks.get_flag("nidaan_wa_watchdog_enabled", "1")) != "1":
        return {"skipped": "disabled"}
    import biz_whatsapp_evolution as wa_evo
    health = await wa_send_health()
    result: dict = {}
    instances = await _all_registered_instances()
    # Drop watchdog state for slots that no longer exist (number removed), so a
    # deleted line can't linger as a phantom "down" record.
    try:
        import biz_nidaan as _nid
        _live = {i["instance_slot"] for i in instances}
        for _slot in range(1, 4):
            if _slot not in _live and (await _nid.get_ops_setting(f"wa_wd_slot{_slot}", "")):
                await _nid.set_ops_setting(f"wa_wd_slot{_slot}", "")
    except Exception:
        pass
    for inst in instances:
        slot = inst["instance_slot"]
        name = inst.get("display_name") or f"Line {slot}"
        phone = inst.get("phone_number") or ""
        st = await _wd_load(slot)
        prev_status = st.get("status", "ok")

        # (1) Evolution socket state
        evo_open = False
        try:
            state = await wa_evo.get_connection_state(inst["evolution_instance"])
            cur = (state.get("instance", {}) or {}).get("state") or state.get("state") or ""
            evo_open = (cur == "open")
        except Exception:
            evo_open = False

        # (2) Can it actually SEND? (from real send outcomes)
        h = health.get(slot, {})
        if not evo_open:
            working: Optional[bool] = False
        elif "broken" in h:
            working = not h.get("broken")
        else:
            working = None   # no recent traffic → unknown

        # (3) Broken → try automatic restart, then probe to confirm
        if working is False:
            tries = int(st.get("restart_tries", 0))
            if tries < 3:
                try:
                    await wa_evo.restart_instance(inst["evolution_instance"])
                    await asyncio.sleep(6)
                except Exception:
                    pass
                st["restart_tries"] = tries + 1
            if await _wd_probe(slot) is True:
                working = True
        elif working is None and prev_status == "down":
            # Was down, no fresh traffic — probe to catch recovery.
            p = await _wd_probe(slot)
            if p is True:
                working = True
            elif p is False:
                working = False

        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        # (4) Transitions + alerting (alert once per outage; announce recovery)
        if working is True:
            if prev_status == "down":
                await _wd_alert_admins(
                    subject=f"✅ WhatsApp back online — {name}",
                    body=(f"The WhatsApp line {name} ({phone}) is working again. "
                          f"WhatsApp notifications on it resume automatically now."),
                    event_key="wa.line.recovered")
                logger.info("🟢 WA watchdog: %s recovered", name)
            await _wd_save(slot, {"status": "ok", "last_ok_at": now,
                                  "alerted": 0, "restart_tries": 0})
            result[slot] = "ok"
        elif working is False:
            down_since = st.get("down_since") or now
            if not int(st.get("alerted", 0)):
                await _wd_alert_admins(
                    subject=f"⛔ WhatsApp DOWN — {name} (re-pair needed)",
                    body=(f"WhatsApp line {name} ({phone}) is NOT sending and an "
                          f"automatic restart did not recover it.\n\n"
                          f"WhatsApp on this line is paused — email + app notifications "
                          f"continue normally, so nothing is missed.\n\n"
                          f"To restore WhatsApp: Ops → Official Numbers → {name} → "
                          f"Re-pair (QR), and scan from the genuine WhatsApp app on a "
                          f"phone that stays online.\n\n{NIDAAN_BASE_URL}/admin"),
                    event_key="wa.line.down")
                logger.warning("🔴 WA watchdog: %s DOWN — super-admins alerted", name)
            await _wd_save(slot, {"status": "down", "down_since": down_since,
                                  "alerted": 1, "restart_tries": st.get("restart_tries", 0)})
            result[slot] = "down"
        else:
            result[slot] = "unknown"
    return result


# ═════════════════════════════════════════════════════════════════════════════
#  Quiet hours
# ═════════════════════════════════════════════════════════════════════════════
async def _in_quiet_hours_now() -> bool:
    qs = int(await ntasks.get_flag("quiet_hours_start", "21") or "21")
    qe = int(await ntasks.get_flag("quiet_hours_end",   "8")  or "8")
    now_h = datetime.now(IST).hour
    if qs <= qe:
        return qs <= now_h < qe
    # Wraps midnight (e.g., 21..8)
    return now_h >= qs or now_h < qe


# ═════════════════════════════════════════════════════════════════════════════
#  Subscriber WA sticky assignment
# ═════════════════════════════════════════════════════════════════════════════
async def _assign_subscriber_to_slot(account_id: int) -> Optional[int]:
    """Pick a slot for a new subscriber (round-robin across healthy instances).
    Returns the slot or None if none healthy."""
    healthy = await _list_healthy_instances()
    if not healthy:
        return None
    # Count current sticky assignments per slot to balance new subscribers
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("""
            SELECT instance_slot, COUNT(*) AS c FROM nidaan_subscriber_wa_assignment
            GROUP BY instance_slot
        """)
        counts = {r[0]: r[1] for r in await cur.fetchall()}
        # Pick healthy slot with FEWEST current subscribers
        chosen = min(healthy, key=lambda h: counts.get(h["instance_slot"], 0))
        await conn.execute("""
            INSERT INTO nidaan_subscriber_wa_assignment (account_id, instance_slot, last_used_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(account_id) DO UPDATE SET instance_slot=excluded.instance_slot,
              failover_count = failover_count + 1
        """, (account_id, chosen["instance_slot"]))
        await conn.commit()
    return chosen["instance_slot"]


async def get_subscriber_slot(account_id: int) -> Optional[dict]:
    """Returns the assigned (sticky) instance for a subscriber, picking one if
    unassigned. Performs auto-failover if the current sticky number is unhealthy."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT instance_slot FROM nidaan_subscriber_wa_assignment WHERE account_id=?",
            (account_id,))
        row = await cur.fetchone()
    if row:
        inst = await get_official_instance(row["instance_slot"])
        if inst and _is_healthy(inst["health_state"]):
            return inst
    # Not assigned, or current assignment unhealthy → reassign
    slot = await _assign_subscriber_to_slot(account_id)
    if slot is None:
        return None
    return await get_official_instance(slot)


# ═════════════════════════════════════════════════════════════════════════════
#  Staff round-robin
# ═════════════════════════════════════════════════════════════════════════════
_staff_rr_idx = 0
_staff_rr_lock = asyncio.Lock()

async def pick_staff_slot() -> Optional[dict]:
    """Round-robin among healthy instances for staff-direction messages. Prefers
    lines that are actually SENDING — a line 'open' but failing every send (ghost)
    is skipped when at least one working line remains, so we route through a line
    that works instead of wasting the first attempt on a dead one (failover in
    _send_wa_failover still covers the rest)."""
    global _staff_rr_idx
    async with _staff_rr_lock:
        healthy = await _list_healthy_instances()
        if not healthy:
            return None
        try:
            sh = await wa_send_health()
            working = [h for h in healthy if not sh.get(h.get("instance_slot"), {}).get("broken")]
            if working:
                healthy = working
        except Exception:
            pass
        chosen = healthy[_staff_rr_idx % len(healthy)]
        _staff_rr_idx = (_staff_rr_idx + 1) % max(1, len(healthy))
        return chosen


# ═════════════════════════════════════════════════════════════════════════════
#  Subscriber prefs
# ═════════════════════════════════════════════════════════════════════════════
async def get_subscriber_prefs(account_id: int) -> dict:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM nidaan_subscriber_prefs WHERE account_id=?", (account_id,))
        row = await cur.fetchone()
    if row:
        return dict(row)
    # Default — opt-in defaults from system flag
    default_optin = (await ntasks.get_flag("subscriber_wa_default_opt_in", "0") or "0") == "1"
    return {
        "account_id": account_id,
        "wa_opt_in": int(default_optin),
        "wa_opt_in_at": None,
        "email_enabled": 1,
        "saved_official_numbers_at": None,
    }


async def set_subscriber_pref(account_id: int, *, wa_opt_in: Optional[bool] = None,
                              email_enabled: Optional[bool] = None,
                              saved_numbers: Optional[bool] = None) -> dict:
    cur = await get_subscriber_prefs(account_id)
    wa = int(cur["wa_opt_in"]) if wa_opt_in is None else int(bool(wa_opt_in))
    em = int(cur["email_enabled"]) if email_enabled is None else int(bool(email_enabled))
    sv_clause = ""
    if saved_numbers:
        sv_clause = ", saved_official_numbers_at = datetime('now')"
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(f"""
            INSERT INTO nidaan_subscriber_prefs (account_id, wa_opt_in, wa_opt_in_at, email_enabled{', saved_official_numbers_at' if saved_numbers else ''})
            VALUES (?, ?, CASE WHEN ?=1 THEN datetime('now') ELSE NULL END, ?{', datetime(\"now\")' if saved_numbers else ''})
            ON CONFLICT(account_id) DO UPDATE SET
              wa_opt_in=excluded.wa_opt_in,
              wa_opt_in_at=CASE WHEN excluded.wa_opt_in=1 AND nidaan_subscriber_prefs.wa_opt_in=0 THEN datetime('now') ELSE nidaan_subscriber_prefs.wa_opt_in_at END,
              email_enabled=excluded.email_enabled
              {sv_clause},
              updated_at=datetime('now')
        """, (account_id, wa, wa, em))
        await conn.commit()
    return await get_subscriber_prefs(account_id)


async def set_comm_lang(account_id: int, lang: str) -> None:
    """Persist the subscriber's preferred comm language (en|hi|mr) for templates."""
    lang = lang if lang in ("en", "hi", "mr") else "en"
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO nidaan_subscriber_prefs (account_id, comm_lang)
            VALUES (?, ?)
            ON CONFLICT(account_id) DO UPDATE SET comm_lang=excluded.comm_lang,
              updated_at=datetime('now')
        """, (account_id, lang))
        await conn.commit()


# ═════════════════════════════════════════════════════════════════════════════
#  Notification log helpers
# ═════════════════════════════════════════════════════════════════════════════
async def _record_notification(**kw) -> int:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute("""
            INSERT INTO nidaan_notifications
              (event_key, priority, claim_id, task_id, recipient_type, recipient_id,
               recipient_phone, recipient_email, channel, subject, body,
               status, instance_slot, wa_message_id, error, sent_at, deferred_until)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (kw.get("event_key"), kw.get("priority", "P1"),
              kw.get("claim_id"), kw.get("task_id"),
              kw.get("recipient_type"), kw.get("recipient_id"),
              kw.get("recipient_phone"), kw.get("recipient_email"),
              kw.get("channel"), kw.get("subject"), kw.get("body"),
              kw.get("status", "queued"),
              kw.get("instance_slot"), kw.get("wa_message_id"),
              kw.get("error"), kw.get("sent_at"), kw.get("deferred_until")))
        await conn.commit()
        notif_id = cur.lastrowid
    # Web Push + Telegram mirror: only for a real staff dashboard notification.
    if (kw.get("channel") == CHANNEL_DASHBOARD
            and kw.get("recipient_type") == RECIPIENT_STAFF
            and kw.get("recipient_id")):
        tid, cid, aid = kw.get("task_id"), kw.get("claim_id"), kw.get("account_id")
        # Deep-link into the OPS PWA at /admin (its own installable scope) so a push
        # tap opens the installed app. Account link lands on the subscriber account.
        url = (f"/admin?qt={tid}" if tid
               else f"/admin?account={aid}" if aid
               else f"/admin?claim={cid}" if cid else "/admin")
        _fire_push([kw.get("recipient_id")],
                   kw.get("subject") or "Nidaan Ops",
                   kw.get("body") or "",
                   url, kw.get("event_key") or "nidaan")
        # Telegram: the reliable internal-ops channel (official Bot API, no ban risk).
        # Fire-and-forget so a slow/edge Telegram call never blocks the request.
        try:
            _tg_text = ((kw.get("subject") or "Nidaan Ops") + "\n\n" + (kw.get("body") or "")).strip()
            asyncio.create_task(_telegram_mirror(kw.get("recipient_id"), _tg_text,
                                                 NIDAAN_BASE_URL + url))
        except Exception:
            pass
    return notif_id


async def _telegram_mirror(staff_id: int, text: str, url: str) -> None:
    """Best-effort Telegram delivery for a staff notification. Silent when the bot
    isn't configured or the staffer hasn't linked — those aren't errors."""
    try:
        import biz_nidaan_telegram as _tg
        ok, err = await _tg.notify_staff(staff_id, text, url=url)
        if not ok and err not in ("not_linked", "telegram_disabled", "no_chat_id"):
            logger.info("Telegram notify failed for staff %s: %s", staff_id, err)
    except Exception as e:
        logger.info("Telegram mirror error: %s", e)


# ── Web Push (PWA push notifications) ────────────────────────────────────────
def _vapid_private() -> str: return os.environ.get("VAPID_PRIVATE_KEY", "")
def _vapid_public() -> str:  return os.environ.get("VAPID_PUBLIC_KEY", "")
def _vapid_subject() -> str: return os.environ.get("VAPID_SUBJECT", "mailto:info@nidaanlegalindia.com")


async def save_push_subscription(staff_id: int, sub: dict, ua: str = "") -> None:
    """Store (or refresh) a browser push subscription for a staff device."""
    keys = sub.get("keys") or {}
    endpoint = sub.get("endpoint") or ""
    p256dh, auth = keys.get("p256dh") or "", keys.get("auth") or ""
    if not (endpoint and p256dh and auth):
        return
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("""
            INSERT INTO nidaan_push_subscriptions (staff_id, endpoint, p256dh, auth, ua)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(endpoint) DO UPDATE SET
              staff_id=excluded.staff_id, p256dh=excluded.p256dh,
              auth=excluded.auth, ua=excluded.ua
        """, (staff_id, endpoint, p256dh, auth, ua[:300]))
        await conn.commit()


async def delete_push_subscription(endpoint: str) -> None:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute("DELETE FROM nidaan_push_subscriptions WHERE endpoint=?", (endpoint,))
        await conn.commit()


def _send_one_push(row: dict, payload: str) -> tuple[bool, bool]:
    """Blocking send of one web-push. Returns (ok, gone) — gone=True if the
    subscription is dead (404/410) and should be pruned."""
    try:
        from pywebpush import webpush, WebPushException
    except Exception:
        return (False, False)
    sub = {"endpoint": row["endpoint"],
           "keys": {"p256dh": row["p256dh"], "auth": row["auth"]}}
    try:
        webpush(subscription_info=sub, data=payload,
                vapid_private_key=_vapid_private(),
                vapid_claims={"sub": _vapid_subject()})
        return (True, False)
    except WebPushException as e:
        code = getattr(getattr(e, "response", None), "status_code", None)
        return (False, code in (404, 410))
    except Exception:
        return (False, False)


async def push_to_staff(staff_ids: list[int], title: str, body: str,
                        url: str = "/nidaan/ops", tag: str = "nidaan") -> int:
    """Fire a Web Push to every device of the given staff. Best-effort, never
    raises. Prunes dead subscriptions. Returns number of successful sends."""
    if not (_vapid_private() and _vapid_public() and staff_ids):
        return 0
    ids = [int(s) for s in staff_ids if s]
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = [dict(r) for r in await (await conn.execute(
            f"SELECT sub_id, endpoint, p256dh, auth FROM nidaan_push_subscriptions "
            f"WHERE staff_id IN ({ph})", ids)).fetchall()]
    if not rows:
        return 0
    payload = json.dumps({"title": title, "body": (body or "")[:300],
                          "url": url, "tag": tag})
    loop = asyncio.get_event_loop()
    ok_count, dead = 0, []
    for r in rows:
        ok, gone = await loop.run_in_executor(None, _send_one_push, r, payload)
        if ok:
            ok_count += 1
        elif gone:
            dead.append(r["sub_id"])
    if dead:
        dph = ",".join("?" * len(dead))
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                f"DELETE FROM nidaan_push_subscriptions WHERE sub_id IN ({dph})", dead)
            await conn.commit()
    if ok_count:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                f"UPDATE nidaan_push_subscriptions SET last_ok_at=CURRENT_TIMESTAMP "
                f"WHERE staff_id IN ({ph})", ids)
            await conn.commit()
    return ok_count


def _fire_push(staff_ids, title, body, url="/nidaan/ops", tag="nidaan") -> None:
    """Schedule a non-blocking push (never blocks the caller's DB write)."""
    try:
        asyncio.create_task(push_to_staff(list(staff_ids), title, body, url, tag))
    except RuntimeError:
        pass  # no running loop (sync context) — skip push, dashboard row still saved


# ── Ops notification bell + broadcast ────────────────────────────────────────
async def _broadcast_wa_mirror(staff: list[dict], sender_name: str, message: str):
    """Mirror a broadcast to staff WhatsApp — ONLY if an official line is connected.
    If none is connected it simply doesn't send (no backlog). Each send goes through
    _send_wa (staff-only allow-list + verify-before-send), so no misrouting."""
    try:
        inst = await pick_staff_slot()
        if not inst:
            return  # no connected line → die silently
        text = f"📢 *{sender_name}*\n{message}"
        for r in staff:
            ph = r.get("phone")
            if not ph:
                continue
            jid = _to_wa_jid(ph)
            if not jid:
                continue
            try:
                await _send_wa(instance_slot=inst["instance_slot"], jid=jid, message=text)
            except Exception:
                pass
    except Exception:
        pass


async def record_broadcast(sender_id: int, sender_name: str, message: str,
                           tone: str = "") -> int:
    """Post a broadcast to EVERY active staffer's bell (dashboard + push), and — if an
    official WhatsApp line is connected — mirror it to their WhatsApp too. When no
    line is connected the WhatsApp part is skipped (no queue/backlog). Returns
    recipient count."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Canonical broadcast row (for the feed + reactions).
        await conn.execute(
            "INSERT INTO nidaan_broadcasts (sender_staff_id, sender_name, message) VALUES (?, ?, ?)",
            (sender_id, sender_name, message))
        rows = await (await conn.execute(
            "SELECT staff_id, phone FROM nidaan_staff WHERE status='active' AND deleted_at IS NULL")).fetchall()
        staff = [dict(r) for r in rows]
        staff_ids = [r["staff_id"] for r in staff]
        subj = f"📢 {sender_name}"
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        for sid in staff_ids:
            await conn.execute("""
                INSERT INTO nidaan_notifications
                  (event_key, priority, recipient_type, recipient_id, channel,
                   subject, body, status, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'sent', ?)
            """, ("broadcast", PRIORITY_P2, RECIPIENT_STAFF, sid,
                  CHANNEL_DASHBOARD, subj, message, now))
        await conn.commit()
    _fire_push(staff_ids, subj, message, "/admin", "broadcast")
    # WhatsApp mirror (background; connection-aware, flag-gated, no backlog).
    try:
        if (await ntasks.get_flag("nidaan_broadcast_wa", "1")) == "1":
            asyncio.create_task(_broadcast_wa_mirror(staff, sender_name, message))
    except Exception:
        pass
    return len(staff_ids)


async def list_broadcasts(viewer_staff_id: int, limit: int = 20):
    """Recent broadcasts with emoji-reaction summary + the viewer's reaction."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        bl = [dict(r) for r in await (await conn.execute(
            "SELECT broadcast_id, sender_name, message, created_at "
            "FROM nidaan_broadcasts ORDER BY broadcast_id DESC LIMIT ?", (limit,))).fetchall()]
        if not bl:
            return bl
        ids = [b["broadcast_id"] for b in bl]
        ph = ",".join("?" * len(ids))
        rrows = await (await conn.execute(
            f"SELECT br.broadcast_id, br.emoji, br.staff_id, s.name AS staff_name "
            f"FROM nidaan_broadcast_reactions br "
            f"LEFT JOIN nidaan_staff s ON s.staff_id=br.staff_id "
            f"WHERE br.broadcast_id IN ({ph})", ids)).fetchall()
        react, mine, reactors = {}, {}, {}
        for r in rrows:
            bid, em = r["broadcast_id"], r["emoji"]
            react.setdefault(bid, {})
            react[bid][em] = react[bid].get(em, 0) + 1
            reactors.setdefault(bid, {}).setdefault(em, []).append(r["staff_name"] or "Someone")
            if r["staff_id"] == viewer_staff_id:
                mine[bid] = em
        for b in bl:
            b["reactions"] = react.get(b["broadcast_id"], {})
            b["reactors"] = reactors.get(b["broadcast_id"], {})   # {emoji: [names]}
            b["my_reaction"] = mine.get(b["broadcast_id"], "")
        return bl


async def react_broadcast(broadcast_id: int, staff_id: int, emoji: str) -> None:
    """Set/toggle the viewer's single emoji reaction on a broadcast."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT emoji FROM nidaan_broadcast_reactions WHERE broadcast_id=? AND staff_id=?",
            (broadcast_id, staff_id))
        row = await cur.fetchone()
        if row and row[0] == emoji:   # toggle off
            await conn.execute(
                "DELETE FROM nidaan_broadcast_reactions WHERE broadcast_id=? AND staff_id=?",
                (broadcast_id, staff_id))
        else:
            await conn.execute(
                "INSERT INTO nidaan_broadcast_reactions (broadcast_id, staff_id, emoji) "
                "VALUES (?, ?, ?) ON CONFLICT(broadcast_id, staff_id) "
                "DO UPDATE SET emoji=excluded.emoji, created_at=CURRENT_TIMESTAMP",
                (broadcast_id, staff_id, emoji))
        await conn.commit()


async def list_staff_notifications(staff_id: int, limit: int = 40):
    """Recent dashboard notifications for the bell + the unread count."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT notif_id, event_key, subject, body, task_id, claim_id, read_at, created_at "
            "FROM nidaan_notifications "
            "WHERE recipient_type='staff' AND recipient_id=? AND channel='dashboard' "
            "ORDER BY notif_id DESC LIMIT ?", (staff_id, limit))
        rows = [dict(r) for r in await cur.fetchall()]
        uc = await (await conn.execute(
            "SELECT COUNT(*) FROM nidaan_notifications "
            "WHERE recipient_type='staff' AND recipient_id=? AND channel='dashboard' "
            "AND read_at IS NULL", (staff_id,))).fetchone()
    return rows, (uc[0] if uc else 0)


async def mark_staff_notifications_read(staff_id: int) -> None:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE nidaan_notifications SET read_at=CURRENT_TIMESTAMP "
            "WHERE recipient_type='staff' AND recipient_id=? AND channel='dashboard' "
            "AND read_at IS NULL", (staff_id,))
        await conn.commit()


async def _bump_sent_count(slot: int) -> None:
    async with aiosqlite.connect(db.DB_PATH) as conn:
        today = date.today().isoformat()
        await conn.execute("""
            UPDATE nidaan_official_instances
            SET daily_sent_count = CASE
                  WHEN daily_count_reset_at = ? THEN COALESCE(daily_sent_count,0) + 1
                  ELSE 1
                END,
                daily_count_reset_at = ?,
                updated_at = datetime('now')
            WHERE instance_slot = ?
        """, (today, today, slot))
        await conn.commit()


# ═════════════════════════════════════════════════════════════════════════════
#  Channel senders
# ═════════════════════════════════════════════════════════════════════════════
def _digits_only(s: str) -> str:
    return "".join(c for c in (s or "") if c.isdigit())


async def _is_registered_staff_phone(dest_digits: str) -> bool:
    """True only if the destination is an ACTIVE, non-deleted staff member's
    registered mobile (matched on the last 10 digits)."""
    d10 = dest_digits[-10:]
    if len(d10) < 10:
        return False
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT 1 FROM nidaan_staff "
            "WHERE status='active' AND deleted_at IS NULL "
            "AND substr(replace(replace(phone,' ',''),'+',''), -10) = ? LIMIT 1",
            (d10,))
        return (await cur.fetchone()) is not None


async def _is_official_number(dest_digits: str) -> bool:
    """True if the destination is one of our official WhatsApp lines (any slot).
    These are always allowed through the staff-only gate."""
    d10 = dest_digits[-10:]
    if len(d10) < 10:
        return False
    async with aiosqlite.connect(db.DB_PATH) as conn:
        cur = await conn.execute(
            "SELECT 1 FROM nidaan_official_instances "
            "WHERE substr(replace(replace(phone_number,' ',''),'+',''), -10) = ? LIMIT 1",
            (d10,))
        return (await cur.fetchone()) is not None


async def _send_wa(*, instance_slot: int, jid: str, message: str) -> tuple[bool, str, str]:
    """Returns (success, wa_message_id, error_str).
    FOOLPROOF GUARDS (a wrong-recipient send is a critical risk):
      0. Staff-only allow-list — WhatsApp goes ONLY to registered staff numbers
         (all account/subscriber WhatsApp is held off for now). Flag
         nidaan_wa_staff_only (default on).
      1. Self-send guard — never message the instance's OWN number.
      2. Verify-before-send — confirm the number is registered on WhatsApp and
         send only to the canonical JID that check returns. Fail CLOSED: if the
         number isn't on WhatsApp, or the check can't be completed, do NOT send."""
    try:
        import biz_whatsapp_evolution as wa_evo
        inst = await get_official_instance(instance_slot)
        if not inst:
            return (False, "", f"No instance for slot {instance_slot}")

        dest_digits = _digits_only(jid.split("@")[0] if "@" in jid else jid)

        # (0) Staff-only allow-list. Until a dedicated business line exists, the
        # ONLY numbers WhatsApp may reach are active staff mobiles from the Staff
        # section. Anything else (subscribers, leads, unknowns) is held off.
        staff_only = (await ntasks.get_flag("nidaan_wa_staff_only", "1")) == "1"
        if staff_only and not (await _is_registered_staff_phone(dest_digits)
                               or await _is_official_number(dest_digits)):
            return (False, "", "blocked_non_staff_recipient")

        # (1) Self-send: by default we ALLOW sending to the official number
        # itself. When a super admin shares the official line, their own
        # notifications (leave approvals, task alerts) should still reach them on
        # WhatsApp — it lands in the number's "Message yourself" chat, with full
        # details. Set flag nidaan_wa_block_self_send=1 to re-enable blocking
        # (e.g. once the official line is a dedicated, un-manned business number).
        block_self = (await ntasks.get_flag("nidaan_wa_block_self_send", "0")) == "1"
        if block_self:
            own = _digits_only(inst.get("phone_number") or inst.get("own_jid") or "")
            if own and dest_digits and (own == dest_digits or own.endswith(dest_digits) or dest_digits.endswith(own)):
                return (False, "", "blocked_self_send")

        # (2) Verify the destination is on WhatsApp; send only to its canonical JID.
        verify_on = (await ntasks.get_flag("nidaan_wa_verify_before_send", "1")) == "1"
        send_jid = jid
        if verify_on:
            try:
                canonical = await wa_evo.check_number_exists(inst["evolution_instance"], dest_digits)
            except Exception as ve:
                # Could not verify → fail closed (never risk a wrong recipient).
                return (False, "", f"verify_failed:{ve}")
            if not canonical:
                return (False, "", "number_not_on_whatsapp")
            send_jid = canonical

        result = await wa_evo.send_text(inst["evolution_instance"], send_jid, message, delay_ms=1500)
        if result and not result.get("error"):
            await _bump_sent_count(instance_slot)
            wa_id = ""
            try:
                wa_id = ((result.get("key") or {}).get("id")) or ""
            except Exception:
                pass
            return (True, wa_id, "")
        # Preserve the real reason (e.g. "SessionError: No sessions") from the
        # Evolution response detail — not just the generic http_400 — so the ops
        # UI can flag a ghost "connected-but-can't-send" number.
        _err = str((result or {}).get("error") or "unknown")
        _detail = str((result or {}).get("detail") or "").strip()
        if _detail:
            _err = f"{_err}: {_detail[:140]}"
        return (False, "", _err)
    except Exception as e:
        return (False, "", str(e))


# Errors that are SLOT-specific (the number/session is broken) — worth failing
# over to another line. Recipient-specific errors (not on WhatsApp, blocked,
# invalid) will fail identically on every slot, so we do NOT retry those.
_WA_FAILOVER_MARKERS = ("no sessions", "sessionerror", "session", "timeout",
                        "bad request", "http_4", "http_5", "connection", "econn",
                        "no instance")


async def _send_wa_failover(*, jid: str, message: str,
                            preferred_slot: int) -> tuple[bool, str, str, int]:
    """Send with automatic line-failover. Tries the preferred slot first, then the
    other healthy official lines on a slot/session error, so a single working
    number keeps WhatsApp flowing even when another line is a dead 'No sessions'
    ghost. Returns (ok, wa_message_id, error, used_slot)."""
    try:
        healthy = await _list_healthy_instances()
    except Exception:
        healthy = []
    order = [preferred_slot] + [h["instance_slot"] for h in (healthy or [])
                                if h.get("instance_slot") != preferred_slot]
    seen, slots = set(), []
    for s in order:
        if s not in seen:
            seen.add(s); slots.append(s)
    last_err, last_slot = "", preferred_slot
    for slot in slots:
        ok, wid, err = await _send_wa(instance_slot=slot, jid=jid, message=message)
        if ok:
            return (True, wid, "", slot)
        last_err, last_slot = err, slot
        if not any(m in (err or "").lower() for m in _WA_FAILOVER_MARKERS):
            break   # recipient-specific failure — another line won't help
    return (False, "", last_err, last_slot)


async def _send_email(*, to_email: str, subject: str, html_body: str,
                      text_body: str = "") -> tuple[bool, str]:
    try:
        import biz_email as email_svc
        # This module only ever sends NidaanPartner ops notifications — brand the
        # sender as "Nidaan Partner" (a name starting with "Nidaan" also routes
        # send_email to the Nidaan from-address, not the Sarathi default).
        ok = await email_svc.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            from_name="Nidaan Partner")
        return (bool(ok), "" if ok else "email send returned False")
    except Exception as e:
        return (False, str(e))


# ═════════════════════════════════════════════════════════════════════════════
#  Main dispatch entry — call this from anywhere in the app
# ═════════════════════════════════════════════════════════════════════════════
async def dispatch(*, event_key: str, priority: str = PRIORITY_P1,
                   recipient_type: str, recipient_id: Optional[int] = None,
                   recipient_phone: str = "", recipient_email: str = "",
                   subject: str = "", body: str = "",
                   claim_id: Optional[int] = None, task_id: Optional[int] = None,
                   force_urgent: bool = False, force_email: bool = False) -> dict:
    """
    Fire-and-forget notification dispatch. Routes through enabled channels.
    Always writes a dashboard notification record. Returns summary dict.
    """
    summary: dict = {"event_key": event_key, "priority": priority, "channels": {}}
    # Always record a dashboard row
    dash_id = await _record_notification(
        event_key=event_key, priority=priority,
        claim_id=claim_id, task_id=task_id,
        recipient_type=recipient_type, recipient_id=recipient_id,
        channel=CHANNEL_DASHBOARD, subject=subject, body=body, status="sent",
        sent_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    summary["channels"][CHANNEL_DASHBOARD] = {"status": "sent", "notif_id": dash_id}

    # Quiet hours
    quiet = await _in_quiet_hours_now()

    # Global pause check
    paused = (await ntasks.get_flag("wa_automation_paused", "0")) == "1"

    # ── WhatsApp ────────────────────────────────────────────────────────────
    wa_status = "skipped"
    wa_err = ""
    chosen_slot: Optional[int] = None
    wa_sent_ok = False
    if recipient_phone and not paused:
        # Quiet hours — only P0 + force_urgent escape
        if quiet and not (priority == PRIORITY_P0 or force_urgent):
            wa_status = "suppressed_quiet_hours"
        else:
            # Pick a slot
            if recipient_type == RECIPIENT_SUBSCRIBER and recipient_id:
                inst = await get_subscriber_slot(recipient_id)
            else:
                inst = await pick_staff_slot()
            if not inst:
                wa_status = "no_active_instance"
                wa_err = "All 3 official numbers offline"
            else:
                chosen_slot = inst["instance_slot"]
                # Adaptive cap check
                caps = await compute_effective_caps()
                slot_info = caps["by_slot"].get(chosen_slot, {})
                defer = False
                if priority == PRIORITY_P2 and slot_info.get("defer_p2"):
                    defer = True
                elif priority == PRIORITY_P1 and slot_info.get("defer_p1"):
                    defer = True
                if defer and not force_urgent:
                    wa_status = "deferred"
                    deferred_until = (datetime.utcnow() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
                    await _record_notification(
                        event_key=event_key, priority=priority,
                        claim_id=claim_id, task_id=task_id,
                        recipient_type=recipient_type, recipient_id=recipient_id,
                        recipient_phone=recipient_phone, channel=CHANNEL_WHATSAPP,
                        subject=subject, body=body,
                        status="deferred", instance_slot=chosen_slot,
                        deferred_until=deferred_until)
                else:
                    jid = _to_wa_jid(recipient_phone)
                    if not jid:
                        wa_status = "invalid_phone"
                    else:
                        ok, wa_id, err, used_slot = await _send_wa_failover(
                            jid=jid, message=body, preferred_slot=chosen_slot)
                        chosen_slot = used_slot   # record the line that actually sent
                        wa_status = "sent" if ok else "failed"
                        wa_err = err
                        wa_sent_ok = ok
                        await _record_notification(
                            event_key=event_key, priority=priority,
                            claim_id=claim_id, task_id=task_id,
                            recipient_type=recipient_type, recipient_id=recipient_id,
                            recipient_phone=recipient_phone, channel=CHANNEL_WHATSAPP,
                            subject=subject, body=body,
                            status=wa_status, instance_slot=chosen_slot,
                            wa_message_id=wa_id, error=err,
                            sent_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if ok else None)
    elif paused:
        wa_status = "paused_globally"
    summary["channels"][CHANNEL_WHATSAPP] = {"status": wa_status, "error": wa_err, "slot": chosen_slot}

    # ── Email fallback ──────────────────────────────────────────────────────
    email_fallback_enabled = (await ntasks.get_flag("nidaan_email_fallback_enabled", "1")) == "1"
    email_status = "skipped"
    email_err = ""
    # Always send email unless WA already succeeded for a non-P0 message and email_enabled is off
    if recipient_email and email_fallback_enabled:
        # For P0, ALWAYS send email regardless. For P1/P2, send if WA didn't
        # succeed — OR if the caller forced email (e.g. task assignee should get
        # both the WhatsApp nudge AND an email record).
        should_email = (priority == PRIORITY_P0) or force_email or (not wa_sent_ok)
        if should_email:
            subj = subject if subject.startswith("[Nidaan]") else f"[Nidaan] {subject}"
            ok, err = await _send_email(
                to_email=recipient_email, subject=subj,
                html_body=body, text_body=re.sub(r"<[^>]+>", "", body))
            email_status = "sent" if ok else "failed"
            email_err = err
            await _record_notification(
                event_key=event_key, priority=priority,
                claim_id=claim_id, task_id=task_id,
                recipient_type=recipient_type, recipient_id=recipient_id,
                recipient_email=recipient_email, channel=CHANNEL_EMAIL,
                subject=subj, body=body,
                status=email_status, error=err,
                sent_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S") if ok else None)
    summary["channels"][CHANNEL_EMAIL] = {"status": email_status, "error": email_err}

    return summary


# ═════════════════════════════════════════════════════════════════════════════
#  Event-shape builders (called from Phase 3 hooks)
# ═════════════════════════════════════════════════════════════════════════════
async def on_claim_filed(claim_id: int, account_id: int):
    """Subscriber filed a new claim. Notify subscriber + alert SA/Admin."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT c.*, a.owner_name, a.email AS account_email, a.phone AS account_phone
            FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id
            WHERE c.claim_id=?
        """, (claim_id,))
        row = await cur.fetchone()
        if not row: return
        claim = dict(row)
        cur = await conn.execute(
            "SELECT staff_id, name, phone, email FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') AND status='active'")
        admins = [dict(r) for r in await cur.fetchall()]

    # Subscriber: friendly confirmation
    prefs = await get_subscriber_prefs(account_id)
    if prefs.get("wa_opt_in"):
        wa_phone = claim.get("account_phone") or claim.get("insured_phone")
    else:
        wa_phone = ""
    await dispatch(
        event_key="claim.filed", priority=PRIORITY_P1,
        recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=account_id,
        recipient_phone=wa_phone, recipient_email=claim.get("account_email") or "",
        subject=f"Case received: {claim.get('insured_name','')}",
        body=(f"Hello {claim.get('owner_name','')},\n\n"
              f"We've received your case for *{claim.get('insured_name','')}* "
              f"({claim.get('claim_type','')}). Our team will review within 24 hours "
              f"and reach out with next steps.\n\n— Nidaan – The Legal Consultants LLP"),
        claim_id=claim_id)
    # Admins: internal alert
    for a in admins:
        await dispatch(
            event_key="claim.filed.admin", priority=PRIORITY_P1,
            recipient_type=RECIPIENT_STAFF, recipient_id=a["staff_id"],
            recipient_phone=a.get("phone") or "",
            recipient_email=a.get("email") or "",
            subject=f"New claim #{claim_id} — {claim.get('insured_name','')}",
            body=(f"🆕 New claim filed.\n\n"
                  f"Case: #{claim_id} {claim.get('insured_name','')} ({claim.get('claim_type','')})\n"
                  f"Subscriber: {claim.get('owner_name','')} ({claim.get('account_email','')})\n\n"
                  f"Open: /admin?account={account_id}"),
            claim_id=claim_id, account_id=account_id)


async def on_subscriber_signup(account_id: int):
    """A new subscriber account was created — alert SA/Sub-admin on their bell
    (dashboard + push), deep-linked straight to the account. Dashboard-only so we
    don't WhatsApp/email admins on every single signup."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        acct = await (await conn.execute(
            "SELECT account_id, owner_name, email, phone, plan FROM nidaan_accounts WHERE account_id=?",
            (account_id,))).fetchone()
        if not acct:
            return
        acct = dict(acct)
        admins = [r["staff_id"] for r in await (await conn.execute(
            "SELECT staff_id FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') "
            "AND status='active' AND deleted_at IS NULL")).fetchall()]
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    subj = f"🆕 New signup — {acct.get('owner_name') or acct.get('email','')}"
    body = (f"A new user just signed up.\n"
            f"Name: {acct.get('owner_name','') or '—'}\n"
            f"Email: {acct.get('email','')}\n"
            f"Phone: {acct.get('phone','') or '—'}\n\n"
            f"Open: /admin?account={account_id}")
    for sid in admins:
        await _record_notification(
            event_key="account.signup", priority=PRIORITY_P2,
            recipient_type=RECIPIENT_STAFF, recipient_id=sid,
            channel=CHANNEL_DASHBOARD, subject=subj, body=body,
            status="sent", sent_at=now, account_id=account_id)


async def on_new_claim_message(claim_id: int, account_id: int, from_type: str, preview: str):
    """A new message in a claim thread → notify the OTHER party. subscriber→ops
    pings SA/Admin bells (deep-linked to the account); staff→subscriber reaches the
    subscriber (dashboard + WhatsApp/email if opted in)."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        claim = await (await conn.execute(
            "SELECT c.insured_name, c.claim_type, a.owner_name, a.email AS account_email, "
            "a.phone AS account_phone FROM nidaan_claims c "
            "LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id WHERE c.claim_id=?",
            (claim_id,))).fetchone()
        if not claim:
            return
        claim = dict(claim)
        admins = []
        if from_type == "subscriber":
            admins = [r["staff_id"] for r in await (await conn.execute(
                "SELECT staff_id FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') "
                "AND status='active' AND deleted_at IS NULL")).fetchall()]
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    if from_type == "subscriber":
        subj = f"💬 Message — {claim.get('owner_name') or claim.get('account_email','')}"
        body = (f"Re: #{claim_id} {claim.get('insured_name','')}\n"
                f"\"{(preview or '')[:140]}\"\n\nOpen: /admin?account={account_id}")
        for sid in admins:
            await _record_notification(
                event_key="claim.message", priority=PRIORITY_P1,
                recipient_type=RECIPIENT_STAFF, recipient_id=sid,
                channel=CHANNEL_DASHBOARD, subject=subj, body=body,
                status="sent", sent_at=now, claim_id=claim_id, account_id=account_id)
    else:  # staff → subscriber
        prefs = await get_subscriber_prefs(account_id)
        wa_phone = (claim.get("account_phone") or "") if prefs.get("wa_opt_in") else ""
        await dispatch(
            event_key="claim.message.sub", priority=PRIORITY_P1,
            recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=account_id,
            recipient_phone=wa_phone, recipient_email=claim.get("account_email") or "",
            subject="New message from Nidaan on your claim",
            body=(f"Our team replied on your claim ({claim.get('insured_name','')}):\n\n"
                  f"\"{(preview or '')[:200]}\"\n\nOpen your dashboard to view & reply."),
            claim_id=claim_id)


async def on_task_assigned(task_id: int):
    """A task was assigned to an associate."""
    task = await ntasks.get_task(task_id)
    if not task or not task.get("assigned_to_staff_id"):
        return
    staff = await ntasks.get_staff(task["assigned_to_staff_id"])
    if not staff:
        return
    await dispatch(
        event_key="task.assigned", priority=PRIORITY_P1,
        recipient_type=RECIPIENT_STAFF, recipient_id=staff["staff_id"],
        recipient_phone=staff.get("phone") or "",
        recipient_email=staff.get("notify_email") or staff.get("email") or "",
        subject=f"Task #{task_id} assigned to you",
        body=(f"🗂️ {task.get('title','')}\n"
              f"Case #{task.get('claim_id')} — {task.get('claim_insured_name','')}\n"
              f"Status: {task.get('status_slug')}\n"
              f"Open: {NIDAAN_BASE_URL}/nidaan/ops?task={task_id}"),
        claim_id=task.get("claim_id"), task_id=task_id)


async def on_staff_welcome(staff: dict):
    """A new staff member was added — send them a welcome (email + WhatsApp)
    with their Login ID and the portal link. Password is set by the admin and
    shared separately (never messaged, for security)."""
    if not staff:
        return
    name = staff.get("name") or "there"
    role = (staff.get("role") or "").replace("_", " ")
    login_id = staff.get("email") or ""
    phone = staff.get("phone") or ""
    email = staff.get("notify_email") or staff.get("email") or ""
    portal = f"{NIDAAN_BASE_URL}/admins"
    body = (f"👋 Welcome to NidaanPartner Ops, {name}!\n"
            f"Role: {role}\n"
            f"Sign in at: {portal}\n"
            f"Your Login ID: {login_id}\n"
            f"Your password was set by your admin — please ask them for it, then "
            f"change it after your first login.")
    await dispatch(
        event_key="staff.welcome", priority=PRIORITY_P1,
        recipient_type=RECIPIENT_STAFF, recipient_id=staff.get("staff_id"),
        recipient_phone=phone, recipient_email=email,
        subject="[Nidaan] Welcome to NidaanPartner Ops",
        body=body, force_email=True)


async def on_quick_task_assigned(quick_task: dict):
    """A Quick Task was created/assigned. Notify BOTH the assignee (action needed)
    and the creator (confirmation), each with a direct deep link to the task.
    Map task priority → notification priority:
      low    → no notification (skip)
      normal → P2 (email + WA if budget healthy)
      high   → P1 (email + WA, defer only if budget critical)
      urgent → P0 (always send all channels)
    Dashboard record always written.
    """
    if not quick_task:
        return
    assignee_id = quick_task.get("assigned_to_staff_id")
    creator_id = quick_task.get("created_by_staff_id")
    task_priority = (quick_task.get("priority") or "normal").lower()
    if task_priority == "low":
        return  # explicit silence
    priority_map = {
        "normal": PRIORITY_P2,
        "high":   PRIORITY_P1,
        "urgent": PRIORITY_P0,
    }
    notif_priority = priority_map.get(task_priority, PRIORITY_P2)
    title = quick_task.get("title", "") or ""
    qid = quick_task.get("quick_task_id")
    deep_link = f"{NIDAAN_BASE_URL}/nidaan/ops?qt={qid}" if qid else f"{NIDAAN_BASE_URL}/nidaan/ops"

    def _common_lines():
        lines = []
        if quick_task.get("claim_id"):
            lines.append(f"Linked: claim #{quick_task['claim_id']} "
                         f"({quick_task.get('insured_name','')})")
        if quick_task.get("due_date"):
            lines.append(f"Due: {quick_task['due_date']}")
        return lines

    # --- Notify the ASSIGNEE (someone has work to do): WhatsApp nudge + email ---
    # Skip when self-assigned: the creator already knows, no notification noise.
    if assignee_id and assignee_id != creator_id:
        body_lines = [f"📌 {title}"]
        if quick_task.get("creator_name"):
            body_lines.append(f"From: {quick_task['creator_name']}")
        body_lines += _common_lines()
        body_lines.append(f"Open: {deep_link}")
        await dispatch(
            event_key="quick_task.assigned",
            priority=notif_priority,
            recipient_type=RECIPIENT_STAFF, recipient_id=assignee_id,
            recipient_phone=quick_task.get("assignee_phone") or "",
            recipient_email=quick_task.get("assignee_email") or "",
            subject=f"[Nidaan] Quick task: {title}",
            body="\n".join(body_lines),
            claim_id=quick_task.get("claim_id"), task_id=qid,
            force_email=True)

    # --- Notify the CREATOR (confirmation): EMAIL ONLY ---
    # The creator already initiated the task, so no WhatsApp nudge for them —
    # WhatsApp is reserved for the assignee who must act. Email is the record.
    if creator_id and creator_id != assignee_id:
        body_lines = [f"✅ Task created: {title}"]
        if quick_task.get("assignee_name"):
            body_lines.append(f"Assigned to: {quick_task['assignee_name']}")
        body_lines += _common_lines()
        body_lines.append(f"Track: {deep_link}")
        await dispatch(
            event_key="quick_task.created",
            priority=notif_priority,
            recipient_type=RECIPIENT_STAFF, recipient_id=creator_id,
            recipient_phone="",   # email only — no WhatsApp to the creator
            recipient_email=quick_task.get("creator_email") or "",
            subject=f"[Nidaan] Task created: {title}",
            body="\n".join(body_lines),
            claim_id=quick_task.get("claim_id"),
            force_email=True)


async def on_quick_task_status_changed(quick_task: dict, new_status: str,
                                        by_name: str = "", by_id: Optional[int] = None):
    """A quick task's status changed (reopened / rejected / cancelled / done, etc.)
    → notify EVERYONE involved (assignee + creator + @mentioned participants), minus
    whoever made the change and anyone who muted the task. Deep-links to the task."""
    if not quick_task:
        return
    qid = quick_task.get("quick_task_id")
    title = quick_task.get("title", "") or ""
    label = {"open": "reopened", "in_progress": "reopened", "reopened": "reopened",
             "rejected": "rejected", "cancelled": "cancelled",
             "done": "marked done", "completed": "marked done"}.get(new_status, new_status)
    body = (f"🔄 Task #{qid} \"{title}\" was {label}"
            + (f" by {by_name}" if by_name else "") + ".\n\n"
            f"Open: /admin?qt={qid}")
    await _notify_task_participants(
        quick_task=quick_task, actor_id=by_id,
        event_key="quick_task.status",
        subject=f"[Nidaan] Task #{qid} {label} — {title[:50]}", body=body)


def _task_notif_priority(quick_task: dict) -> str:
    tp = (quick_task.get("priority") or "normal").lower()
    return {"low": PRIORITY_P2, "normal": PRIORITY_P2,
            "high": PRIORITY_P1, "urgent": PRIORITY_P0}.get(tp, PRIORITY_P2)


async def _notify_task_participants(*, quick_task: dict, actor_id: Optional[int],
                                    event_key: str, subject: str, body: str,
                                    exclude_ids: Optional[set] = None):
    """Fan a task-progression notification out to everyone involved — creator +
    assignee + @mentioned participants — minus the actor and anyone who muted the
    task. This is what makes 'all parties get notified on all progression' work,
    while a participant who's done can mute to stop the noise."""
    import biz_nidaan as _nid
    qid = quick_task.get("quick_task_id")
    if not qid:
        return
    parts = await _nid.get_task_participants(qid)
    skip = set(exclude_ids or set())
    if actor_id:
        skip.add(actor_id)
    prio = _task_notif_priority(quick_task)
    for p in parts:
        sid = p.get("staff_id")
        if sid in skip or p.get("muted"):
            continue
        await dispatch(
            event_key=event_key, priority=prio,
            recipient_type=RECIPIENT_STAFF, recipient_id=sid,
            recipient_phone=p.get("phone") or "",
            recipient_email=p.get("email") or "",
            subject=subject, body=body, task_id=qid)


async def on_quick_task_mention(quick_task: dict, mentioned_ids: list,
                                by_id: int, by_name: str = "", preview: str = ""):
    """Someone @mentioned staff into a task → tell each newly-tagged person directly
    ('you were tagged'), deep-linked, so they pick up their part. dashboard + push +
    WhatsApp/email."""
    if not quick_task or not mentioned_ids:
        return
    qid = quick_task.get("quick_task_id")
    title = quick_task.get("title", "") or ""
    by_name = by_name or "Someone"
    prio = _task_notif_priority(quick_task)
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        ph = ",".join("?" * len(mentioned_ids))
        rows = await (await conn.execute(
            f"SELECT staff_id, phone, "
            f"       COALESCE(NULLIF(notify_email,''), email) AS email "
            f"FROM nidaan_staff WHERE staff_id IN ({ph}) "
            f"AND status='active' AND deleted_at IS NULL", list(mentioned_ids))).fetchall()
    body = (f"🏷️ {by_name} tagged you on task #{qid} \"{title}\""
            + (f":\n\"{preview[:160]}\"" if preview else ".") +
            f"\n\nYou can now see and work on it.\nOpen: /admin?qt={qid}")
    for r in rows:
        if r["staff_id"] == by_id:
            continue
        await dispatch(
            event_key="quick_task.mention", priority=prio,
            recipient_type=RECIPIENT_STAFF, recipient_id=r["staff_id"],
            recipient_phone=r.get("phone") or "",
            recipient_email=r.get("email") or "",
            subject=f"[Nidaan] You were tagged on task #{qid} — {title[:40]}",
            body=body, task_id=qid)


async def on_quick_task_comment(quick_task: dict, commenter_id: int, preview: str):
    """A new comment on a task → notify EVERYONE involved (creator + assignee +
    @mentioned participants), minus the commenter and anyone who muted the task:
    dashboard + push + WhatsApp/email. WhatsApp dies silently if no line is up
    (no backlog); dashboard + email still reach them."""
    if not quick_task:
        return
    qid = quick_task.get("quick_task_id")
    title = quick_task.get("title", "") or ""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cmt = await (await conn.execute(
            "SELECT name FROM nidaan_staff WHERE staff_id=?", (commenter_id,))).fetchone()
        by_name = (cmt["name"] if cmt else "") or "Someone"
    body = (f"💬 {by_name} commented on task #{qid} \"{title}\":\n"
            f"\"{(preview or '')[:160]}\"\n\nOpen: /admin?qt={qid}")
    await _notify_task_participants(
        quick_task=quick_task, actor_id=commenter_id,
        event_key="quick_task.comment",
        subject=f"[Nidaan] Comment on task #{qid} — {title[:40]}", body=body)


async def on_quick_task_approval_request(quick_task: dict):
    """A task that requires approval was created → notify the approvers (super/sub
    admins, minus the creator) so they know to review it: dashboard + push + WhatsApp
    (when a line is connected). Fills the gap where a requires_approval task that is
    self-assigned notified nobody."""
    if not quick_task or not quick_task.get("requires_approval"):
        return
    qid = quick_task.get("quick_task_id")
    title = quick_task.get("title", "") or ""
    creator_id = quick_task.get("created_by_staff_id")
    approver_id = quick_task.get("approver_staff_id")
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if approver_id:
            # Creator named an approver → ping ONLY them (no more all-admins blast).
            admins = [dict(r) for r in await (await conn.execute(
                "SELECT staff_id, phone, notify_email, email FROM nidaan_staff "
                "WHERE staff_id=? AND status='active' AND deleted_at IS NULL",
                (approver_id,))).fetchall()]
        else:
            # No approver named → fall back to super-admins only.
            admins = [dict(r) for r in await (await conn.execute(
                "SELECT staff_id, phone, notify_email, email FROM nidaan_staff "
                "WHERE role='super_admin' AND status='active' "
                "AND deleted_at IS NULL")).fetchall()]
    task_priority = (quick_task.get("priority") or "normal").lower()
    notif_priority = {"low": PRIORITY_P2, "normal": PRIORITY_P2,
                      "high": PRIORITY_P1, "urgent": PRIORITY_P0}.get(task_priority, PRIORITY_P2)
    body = (f"🧾 Task #{qid} \"{title}\" needs your approval "
            f"(by {quick_task.get('creator_name','')}).\n\nOpen: /admin?qt={qid}")
    for a in admins:
        if a["staff_id"] == creator_id:
            continue  # don't ask the creator to approve their own task
        await dispatch(
            event_key="quick_task.approval_request", priority=notif_priority,
            recipient_type=RECIPIENT_STAFF, recipient_id=a["staff_id"],
            recipient_phone=a.get("phone") or "",
            recipient_email=a.get("notify_email") or a.get("email") or "",
            subject=f"[Nidaan] Approval needed — task #{qid} {title[:40]}",
            body=body, task_id=qid)


async def on_quick_task_approval(quick_task: dict, decision: str):
    """A task requiring approval was approved/rejected. Notify the creator and
    assignee with the outcome + a deep link."""
    if not quick_task:
        return
    title = quick_task.get("title", "") or ""
    qid = quick_task.get("quick_task_id")
    deep_link = f"{NIDAAN_BASE_URL}/nidaan/ops?qt={qid}" if qid else f"{NIDAAN_BASE_URL}/nidaan/ops"
    approved = (decision == "approved")
    icon = "✅" if approved else "🚫"
    word = "approved" if approved else "rejected"
    # Deduplicate recipients (creator may equal assignee).
    seen = set()
    targets = [
        (quick_task.get("created_by_staff_id"), quick_task.get("creator_phone"), quick_task.get("creator_email")),
        (quick_task.get("assigned_to_staff_id"), quick_task.get("assignee_phone"), quick_task.get("assignee_email")),
    ]
    for sid, phone, email in targets:
        if not sid or sid in seen:
            continue
        seen.add(sid)
        await dispatch(
            event_key="quick_task.approval",
            priority=PRIORITY_P1,
            recipient_type=RECIPIENT_STAFF, recipient_id=sid,
            recipient_phone=phone or "",
            recipient_email=email or "",
            subject=f"[Nidaan] Task {word}: {title}",
            body=(f"{icon} Task {word}: {title}\n"
                  f"Open: {deep_link}"),
            claim_id=quick_task.get("claim_id"))


async def _active_admins() -> list[dict]:
    """All active super_admin + sub_super_admin, with notify-email fallback."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT staff_id, name, phone, role, "
            "       COALESCE(NULLIF(notify_email,''), email) AS email "
            "FROM nidaan_staff "
            "WHERE role IN ('super_admin','sub_super_admin') AND status='active'")
        return [dict(r) for r in await cur.fetchall()]


async def on_quick_task_request(quick_task: dict):
    """An associate raised an upward request — alert every admin/SA so someone
    picks it up. Deep-linked to the task."""
    if not quick_task:
        return
    title = quick_task.get("title", "") or ""
    qid = quick_task.get("quick_task_id")
    link = f"{NIDAAN_BASE_URL}/nidaan/ops?qt={qid}" if qid else f"{NIDAAN_BASE_URL}/nidaan/ops"
    frm = quick_task.get("creator_name") or "an associate"
    subject = f"[Nidaan] Request from {frm}: {title}"
    body = ("🙋 New request from " + frm + "\n"
            f"📌 {title}\n"
            + (f"Linked: claim #{quick_task['claim_id']}\n" if quick_task.get('claim_id') else "")
            + f"Pick up: {link}")
    # EMAIL each admin; WHATSAPP only to the connected official line(s).
    for a in await _active_admins():
        await dispatch(
            event_key="quick_task.request", priority=PRIORITY_P1,
            recipient_type=RECIPIENT_STAFF, recipient_id=a["staff_id"],
            recipient_phone="",
            recipient_email=a.get("email") or "",
            subject=subject, body=body, force_email=True)
    await _whatsapp_official_lines(event_key="quick_task.request",
                                   subject=subject, body=body)


async def _whatsapp_official_lines(*, event_key: str, subject: str, body: str,
                                   priority: str = PRIORITY_P1) -> int:
    """Deliver an internal alert to every CONNECTED official WhatsApp line
    (health_state='open'). Each connected line receives it (a self-message on
    its own number) — so with 1 connected it lands on that one, and with all 3
    connected it lands on all 3. Returns how many lines were messaged.
    Email is handled separately by the caller (per-admin)."""
    insts = await list_official_instances()
    sent = 0
    for inst in insts:
        if inst.get("health_state") != "open":
            continue
        num = inst.get("phone_number")
        if not num:
            continue
        await dispatch(
            event_key=event_key, priority=priority,
            recipient_type=RECIPIENT_STAFF, recipient_id=None,
            recipient_phone=num, recipient_email="",
            subject=subject, body=body)
        sent += 1
    return sent


def _leave_when(leave: dict) -> str:
    """Human window: half-day shows the period, full-day shows the range."""
    if (leave.get("leave_type") or "full_day") == "half_day":
        period = "first half (morning)" if leave.get("half_period") == "first_half" else "second half (afternoon)"
        return f"{leave.get('start_date')} — half day, {period}"
    if leave.get("start_date") == leave.get("end_date"):
        return f"{leave.get('start_date')} (full day)"
    return f"{leave.get('start_date')} → {leave.get('end_date')} (full days)"


async def on_leave_requested(leave: dict):
    """A staffer applied for leave — alert every admin/SA for approval on
    WhatsApp + email, with the handover (tasks in hand) details."""
    if not leave:
        return
    who = leave.get("staff_name") or f"Staff #{leave.get('staff_id')}"
    when = _leave_when(leave)
    link = f"{NIDAAN_BASE_URL}/nidaan/ops?leave={leave.get('leave_id')}"
    open_tasks = leave.get("open_tasks")
    _is_wfh = (leave.get("request_kind") == "wfh")
    _kind_label = "Work-from-home" if _is_wfh else "Leave"
    _kind_icon = "🏠" if _is_wfh else "🌴"
    lines = [f"{_kind_icon} {_kind_label} request from {who}", f"When: {when}"]
    if leave.get("reason"):
        lines.append(f"Reason: {leave['reason']}")
    if open_tasks:
        lines.append(f"⚠️ {who} has {open_tasks} open task(s) in hand")
    if leave.get("cover_name"):
        lines.append(f"Suggested cover: {leave['cover_name']}")
    if leave.get("handover_notes"):
        lines.append(f"Handover: {leave['handover_notes']}")
    lines.append(f"Approve/Reject: {link}")
    body = "\n".join(lines)
    subject = f"[Nidaan] {_kind_label} request — {who} ({when})"
    # EMAIL each admin (their own inbox); WHATSAPP only to the connected official
    # line(s) — not to admins' personal numbers.
    for a in await _active_admins():
        await dispatch(
            event_key="leave.requested", priority=PRIORITY_P1,
            recipient_type=RECIPIENT_STAFF, recipient_id=a["staff_id"],
            recipient_phone="",
            recipient_email=a.get("email") or "",
            subject=subject, body=body, force_email=True)
    await _whatsapp_official_lines(event_key="leave.requested",
                                   subject=subject, body=body)


async def on_leave_decided(leave: dict, decision: str):
    """A leave request was approved/rejected — notify the requester."""
    if not leave or not leave.get("staff_id"):
        return
    approved = (decision == "approved")
    icon = "✅" if approved else "🚫"
    word = "approved" if approved else "rejected"
    when = _leave_when(leave)
    link = f"{NIDAAN_BASE_URL}/nidaan/ops?leave={leave.get('leave_id')}"
    await dispatch(
        event_key="leave.decided", priority=PRIORITY_P1,
        recipient_type=RECIPIENT_STAFF, recipient_id=leave["staff_id"],
        recipient_phone=leave.get("staff_phone") or "",
        recipient_email=leave.get("staff_email") or "",
        subject=f"[Nidaan] Leave {word}",
        body=(f"{icon} Your leave ({when}) was {word}.\n"
              + (f"Note: {leave.get('decision_note')}\n" if leave.get('decision_note') else "")
              + f"Open: {link}"),
        force_email=True)


async def on_task_status_changed(task_id: int, from_status: str, to_status: str, note: str = ""):
    """A task moved status. Notify assignee + subscriber (if status maps to stage change)."""
    task = await ntasks.get_task(task_id)
    if not task:
        return
    # Notify assignee
    if task.get("assigned_to_staff_id"):
        staff = await ntasks.get_staff(task["assigned_to_staff_id"])
        if staff:
            await dispatch(
                event_key="task.status_changed", priority=PRIORITY_P2,
                recipient_type=RECIPIENT_STAFF, recipient_id=staff["staff_id"],
                recipient_phone=staff.get("phone") or "",
                recipient_email=staff.get("notify_email") or staff.get("email") or "",
                subject=f"Task #{task_id}: {from_status} → {to_status}",
                body=(f"Task #{task_id}: *{task.get('title','')}*\n"
                      f"Status: {from_status} → {to_status}\n"
                      + (f"Note: {note}\n" if note else "")
                      + f"Open: {NIDAAN_BASE_URL}/nidaan/ops?task={task_id}"),
                claim_id=task.get("claim_id"), task_id=task_id)
    # Notify subscriber if stage changed (look up claim)
    new_status = await ntasks.get_status(to_status)
    if new_status and task.get("claim_id"):
        async with aiosqlite.connect(db.DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute("""
                SELECT c.stage AS old_stage, c.account_id, c.insured_name,
                       a.owner_name, a.email AS account_email, a.phone AS account_phone
                FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id
                WHERE c.claim_id=?""", (task["claim_id"],))
            row = await cur.fetchone()
        if row and row["old_stage"] != new_status["stage"]:
            # Update claim stage
            async with aiosqlite.connect(db.DB_PATH) as conn:
                await conn.execute(
                    "UPDATE nidaan_claims SET stage=? WHERE claim_id=?",
                    (new_status["stage"], task["claim_id"]))
                await conn.commit()
            # Notify subscriber
            prefs = await get_subscriber_prefs(row["account_id"])
            wa_phone = row["account_phone"] if prefs.get("wa_opt_in") else ""
            await dispatch(
                event_key="claim.stage_changed", priority=PRIORITY_P1,
                recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=row["account_id"],
                recipient_phone=wa_phone, recipient_email=row["account_email"] or "",
                subject=f"Case update: {row['insured_name']}",
                body=(f"Hello {row['owner_name']},\n\n"
                      f"Your case is now in: *{new_status.get('label_subscriber') or new_status['label_en']}*.\n\n"
                      f"Log in to your dashboard for details.\n\n"
                      f"— Nidaan – The Legal Consultants LLP"),
                claim_id=task["claim_id"], task_id=task_id)


async def on_qc_required(task_id: int):
    """Task is in awaiting_qc — notify senior staff for review."""
    task = await ntasks.get_task(task_id)
    if not task:
        return
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT staff_id, name, phone, email FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') AND status='active'")
        admins = [dict(r) for r in await cur.fetchall()]
    for a in admins:
        await dispatch(
            event_key="task.qc_required", priority=PRIORITY_P1,
            recipient_type=RECIPIENT_STAFF, recipient_id=a["staff_id"],
            recipient_phone=a.get("phone") or "",
            recipient_email=a.get("email") or "",
            subject=f"QC required: Task #{task_id}",
            body=(f"🔍 *QC required*\n\n"
                  f"Task #{task_id}: {task.get('title','')}\n"
                  f"Case #{task.get('claim_id')} — {task.get('claim_insured_name','')}\n\n"
                  f"Review at /nidaan/ops"),
            claim_id=task.get("claim_id"), task_id=task_id)


async def on_approval_required(task_id: int, target_status: str):
    """Task needs admin + SA approval to advance — notify both groups."""
    task = await ntasks.get_task(task_id)
    if not task:
        return
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT staff_id, name, phone, email, role FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') AND status='active'")
        admins = [dict(r) for r in await cur.fetchall()]
    for a in admins:
        await dispatch(
            event_key="task.approval_required", priority=PRIORITY_P1,
            recipient_type=RECIPIENT_STAFF, recipient_id=a["staff_id"],
            recipient_phone=a.get("phone") or "",
            recipient_email=a.get("email") or "",
            subject=f"Approval required: Task #{task_id} → {target_status}",
            body=(f"⚠️ *Dual-approval required*\n\n"
                  f"Task #{task_id}: {task.get('title','')}\n"
                  f"Target status: {target_status}\n"
                  f"Case #{task.get('claim_id')}\n\n"
                  f"Approve at /nidaan/ops (Tasks)"),
            claim_id=task.get("claim_id"), task_id=task_id)


async def on_document_received(claim_id: int, doc_id: int, source: str = "dashboard"):
    """A document was uploaded (dashboard or WA). Notify assignees of open tasks
    on this claim."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT DISTINCT t.assigned_to_staff_id AS sid, s.name, s.phone, s.email
            FROM nidaan_tasks t LEFT JOIN nidaan_staff s ON s.staff_id=t.assigned_to_staff_id
            WHERE t.claim_id=? AND t.completed_at IS NULL AND t.assigned_to_staff_id IS NOT NULL
        """, (claim_id,))
        assignees = [dict(r) for r in await cur.fetchall()]
        cur = await conn.execute("SELECT * FROM nidaan_documents WHERE doc_id=?", (doc_id,))
        doc_row = await cur.fetchone()
        doc = dict(doc_row) if doc_row else {}
    for a in assignees:
        await dispatch(
            event_key="document.received", priority=PRIORITY_P1,
            recipient_type=RECIPIENT_STAFF, recipient_id=a["sid"],
            recipient_phone=a.get("phone") or "",
            recipient_email=a.get("email") or "",
            subject=f"New document on case #{claim_id} ({source})",
            body=(f"📎 Document received\n\n"
                  f"Case: #{claim_id}\n"
                  f"File: {doc.get('original_filename','(unnamed)')}\n"
                  f"Source: {source}\n\n"
                  f"Open: /nidaan/ops"),
            claim_id=claim_id)


async def on_sla_overdue(task_id: int):
    """Scheduler hits this when a task crosses sla_due_at without completion."""
    task = await ntasks.get_task(task_id)
    if not task or task.get("completed_at"):
        return
    # Notify assignee
    if task.get("assigned_to_staff_id"):
        staff = await ntasks.get_staff(task["assigned_to_staff_id"])
        if staff:
            await dispatch(
                event_key="task.sla_overdue", priority=PRIORITY_P1, force_urgent=True,
                recipient_type=RECIPIENT_STAFF, recipient_id=staff["staff_id"],
                recipient_phone=staff.get("phone") or "",
                recipient_email=staff.get("email") or "",
                subject=f"⚠️ SLA breach: Task #{task_id}",
                body=(f"⏰ *SLA breached*\n\n"
                      f"Task #{task_id}: {task.get('title','')}\n"
                      f"Case #{task.get('claim_id')}\n"
                      f"Due: {task.get('sla_due_at','—')}\n\n"
                      f"Take action: /nidaan/ops"),
                claim_id=task.get("claim_id"), task_id=task_id)


# ═════════════════════════════════════════════════════════════════════════════
#  ₹499 value-first FUNNEL — WhatsApp parity (mirrors the dashboard journey)
#  Template-first (anti-hallucination): every message is a fixed template filled
#  from the DB. en/hi/mr. The dashboard and WhatsApp say the SAME thing.
# ═════════════════════════════════════════════════════════════════════════════
NIDAAN_BASE_URL = os.getenv("NIDAAN_BASE_URL", "https://nidaanpartner.com")


def _inr(n) -> str:
    """Indian-grouped rupee string: 400000 -> '4,00,000'."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "—"
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        import re as _re
        head = _re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = head + "," + tail
    return ("-" if n < 0 else "") + s


def _funnel_lang(lang: str) -> str:
    return lang if lang in ("en", "hi", "mr") else "en"


def _doc_lines(pending: list[dict], claim_type: str, lang: str) -> str:
    import biz_nidaan_doc_checklist as _ck
    if not pending:
        return ""
    return "\n".join(f"  • {_ck.label(d['key'], claim_type, lang)}" for d in pending)


async def on_lead_filed(claim_id: int, account_id: int):
    """Free ₹499 lead submitted (unpaid_lead). WhatsApp + email: warm welcome,
    save-our-number, the documents still needed, and the hope/hook — mirroring
    the dashboard checklist card. No price pressure yet; pay-gate comes after docs."""
    import biz_nidaan_doc_checklist as _ck
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT c.*, a.owner_name, a.email AS account_email, a.phone AS account_phone "
            "FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id "
            "WHERE c.claim_id=?", (claim_id,))).fetchone()
    if not row:
        return
    claim = dict(row)
    prefs = await get_subscriber_prefs(account_id)
    lang = _funnel_lang(prefs.get("comm_lang") or "en")
    ctype = claim.get("claim_type", "")
    pending = await _ck.pending_required_docs(claim_id, ctype)
    docs = _doc_lines(pending, ctype, lang)
    name = (claim.get("owner_name") or "").split(" ")[0]
    dash = f"{NIDAAN_BASE_URL}/nidaan/dashboard"
    disp = _inr(claim.get("disputed_amount")) if claim.get("disputed_amount") else ""

    if lang == "hi":
        body = (f"नमस्ते {name} 🙏\n\n"
                f"हमें आपका *{claim.get('insured_name','')}* का क्लेम मिल गया है। "
                f"कृपया इस नंबर को *Nidaan* नाम से सेव कर लें ताकि सभी अपडेट यहीं भरोसे के साथ मिलें।\n\n"
                f"📋 *अभी ये दस्तावेज़ बाकी हैं:*\n{docs}\n\n"
                f"इन्हें यहाँ अपलोड करें: {dash}\n\n"
                f"एक बार दस्तावेज़ पूरे होते ही हमारे कानूनी विशेषज्ञ आपके केस की समीक्षा शुरू कर देंगे। "
                f"रिजेक्शन का अंत यहीं नहीं है — आपके क्लेम में अब भी दम बाकी है। 💪\n\n"
                f"बंद करने के लिए STOP भेजें।\n— Nidaan – The Legal Consultants LLP")
    elif lang == "mr":
        body = (f"नमस्कार {name} 🙏\n\n"
                f"आम्हाला तुमचा *{claim.get('insured_name','')}* चा क्लेम मिळाला आहे. "
                f"कृपया हा नंबर *Nidaan* नावाने सेव्ह करा म्हणजे सर्व अपडेट्स विश्वासाने इथेच मिळतील.\n\n"
                f"📋 *अजून हे कागदपत्र बाकी आहेत:*\n{docs}\n\n"
                f"ती इथे अपलोड करा: {dash}\n\n"
                f"कागदपत्र पूर्ण होताच आमचे कायदेतज्ज्ञ तुमच्या केसची समीक्षा सुरू करतील. "
                f"नकार म्हणजे शेवट नाही — तुमच्या क्लेममध्ये अजून ताकद आहे. 💪\n\n"
                f"थांबवण्यासाठी STOP पाठवा.\n— Nidaan – The Legal Consultants LLP")
    else:
        body = (f"Hello {name} 🙏\n\n"
                f"We've received your claim for *{claim.get('insured_name','')}*. "
                f"Please save this number as *Nidaan* so every update reaches you here, trusted.\n\n"
                f"📋 *Documents still needed:*\n{docs}\n\n"
                f"Upload them here: {dash}\n\n"
                f"The moment your documents are in, our legal experts start reviewing your case. "
                f"A rejection isn't the end — your claim still has a fighting chance. 💪\n\n"
                f"Reply STOP to opt out.\n— Nidaan – The Legal Consultants LLP")

    wa_phone = (claim.get("insured_phone") or claim.get("account_phone") or "") if prefs.get("wa_opt_in") else ""
    await dispatch(
        event_key="funnel.lead_filed", priority=PRIORITY_P1,
        recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=account_id,
        recipient_phone=wa_phone, recipient_email=claim.get("account_email") or "",
        subject="Your claim is in — a few documents to upload",
        body=body, claim_id=claim_id)

    # Alert SA/Sub-admin on their bell (deep-linked to the account): a new ₹499
    # lead with payment/docs pending, so they can chase + convert. Dashboard-only.
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        _admins = [r["staff_id"] for r in await (await conn.execute(
            "SELECT staff_id FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') "
            "AND status='active' AND deleted_at IS NULL")).fetchall()]
    _now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    _asubj = f"📝 New ₹499 lead — {claim.get('insured_name','')}"
    _abody = (f"New ₹499 review lead (payment pending).\n"
              f"Case: #{claim_id} {claim.get('insured_name','')} ({ctype})\n"
              f"Subscriber: {claim.get('owner_name','')} ({claim.get('account_email','')})\n"
              f"Documents pending: {len(pending)}\n\n"
              f"Open: /admin?account={account_id}")
    for _sid in _admins:
        await _record_notification(
            event_key="funnel.lead_filed.admin", priority=PRIORITY_P2,
            recipient_type=RECIPIENT_STAFF, recipient_id=_sid,
            channel=CHANNEL_DASHBOARD, subject=_asubj, body=_abody,
            status="sent", sent_at=_now, claim_id=claim_id, account_id=account_id)


async def on_funnel_pay_ready(claim_id: int, account_id: int):
    """All required documents are in (pay-gate). WhatsApp + email: hope/hook
    (disputed amount vs ₹499) + a ONE-TAP pay link so the user never has to
    return to the dashboard. Mirrors the dashboard pay-gate card."""
    import biz_nidaan as _nd
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT c.*, a.owner_name, a.email AS account_email, a.phone AS account_phone "
            "FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id "
            "WHERE c.claim_id=?", (claim_id,))).fetchone()
    if not row:
        return
    claim = dict(row)
    if claim.get("payment_status") != "unpaid_lead":
        return  # already paid/subscription — no pay nudge
    # Idempotent: only the FIRST time the pay-gate opens for this claim.
    async with aiosqlite.connect(db.DB_PATH) as conn:
        seen = await (await conn.execute(
            "SELECT 1 FROM nidaan_notifications WHERE claim_id=? AND event_key='funnel.pay_ready' LIMIT 1",
            (claim_id,))).fetchone()
    if seen:
        return
    prefs = await get_subscriber_prefs(account_id)
    lang = _funnel_lang(prefs.get("comm_lang") or "en")
    name = (claim.get("owner_name") or "").split(" ")[0]
    disp = _inr(claim.get("disputed_amount")) if claim.get("disputed_amount") else ""
    tok = _nd.create_pay_link_token(claim_id, account_id)
    pay_link = f"{NIDAAN_BASE_URL}/nidaan/pay/{claim_id}?t={tok}"

    if lang == "hi":
        contrast = (f"आपका विवादित क्लेम *₹{disp}* — समीक्षा सिर्फ़ *₹499*।\n\n" if disp
                    else "आपकी समीक्षा सिर्फ़ *₹499*।\n\n")
        body = (f"शाबाश {name}! ✅ आपके सभी दस्तावेज़ मिल गए।\n\n"
                f"🎯 आपका क्लेम लड़ने लायक मज़बूत दिखता है।\n"
                f"{contrast}"
                f"अभी ₹499 दें और अपनी विशेषज्ञ समीक्षा शुरू करें — रिपोर्ट *24-48 कार्य-घंटों* में, "
                f"यहीं WhatsApp पर और डैशबोर्ड पर।\n\n"
                f"👉 एक टैप में भुगतान करें: {pay_link}\n\n"
                f"अपना पैसा यूँ ही मत छोड़िए।\n— Nidaan – The Legal Consultants LLP")
    elif lang == "mr":
        contrast = (f"तुमचा वादातील क्लेम *₹{disp}* — समीक्षा फक्त *₹499*।\n\n" if disp
                    else "तुमची समीक्षा फक्त *₹499*।\n\n")
        body = (f"छान {name}! ✅ तुमची सर्व कागदपत्रे मिळाली.\n\n"
                f"🎯 तुमचा क्लेम लढण्याइतका मजबूत दिसतो.\n"
                f"{contrast}"
                f"आता ₹499 भरा आणि तुमची तज्ज्ञ समीक्षा सुरू करा — अहवाल *24-48 कामकाजाच्या तासांत*, "
                f"इथे WhatsApp वर आणि डॅशबोर्डवर.\n\n"
                f"👉 एका टॅपमध्ये पैसे भरा: {pay_link}\n\n"
                f"तुमचे पैसे असेच सोडू नका.\n— Nidaan – The Legal Consultants LLP")
    else:
        contrast = (f"Your disputed claim is *₹{disp}* — the review is just *₹499*.\n\n" if disp
                    else "Your review is just *₹499*.\n\n")
        body = (f"Well done {name}! ✅ We have all your documents.\n\n"
                f"🎯 Your claim looks strong enough to fight.\n"
                f"{contrast}"
                f"Pay ₹499 now to start your expert review — your report arrives within "
                f"*24-48 business hours*, here on WhatsApp and on your dashboard.\n\n"
                f"👉 Pay in one tap: {pay_link}\n\n"
                f"Don't leave your money on the table.\n— Nidaan – The Legal Consultants LLP")

    wa_phone = (claim.get("insured_phone") or claim.get("account_phone") or "") if prefs.get("wa_opt_in") else ""
    await dispatch(
        event_key="funnel.pay_ready", priority=PRIORITY_P1,
        recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=account_id,
        recipient_phone=wa_phone, recipient_email=claim.get("account_email") or "",
        subject="Your case is ready — pay ₹499 to start your review",
        body=body, claim_id=claim_id)


async def on_funnel_paid(claim_id: int, account_id: int, sla_due_iso: str = ""):
    """₹499 paid → review started. WhatsApp + email confirmation mirroring the
    dashboard: review has begun, report within 24-48 business hours, here + WhatsApp."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT c.*, a.owner_name, a.email AS account_email, a.phone AS account_phone "
            "FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id "
            "WHERE c.claim_id=?", (claim_id,))).fetchone()
    if not row:
        return
    claim = dict(row)
    prefs = await get_subscriber_prefs(account_id)
    lang = _funnel_lang(prefs.get("comm_lang") or "en")
    name = (claim.get("owner_name") or "").split(" ")[0]

    if lang == "hi":
        body = (f"धन्यवाद {name}! ✅ आपका ₹499 भुगतान मिल गया।\n\n"
                f"आपके *{claim.get('insured_name','')}* के क्लेम की विशेषज्ञ समीक्षा अभी शुरू हो गई है। "
                f"आपकी विस्तृत रिपोर्ट *24-48 कार्य-घंटों* में मिलेगी — यहीं WhatsApp पर और डैशबोर्ड पर।\n\n"
                f"— Nidaan – The Legal Consultants LLP")
    elif lang == "mr":
        body = (f"धन्यवाद {name}! ✅ तुमचे ₹499 पेमेंट मिळाले.\n\n"
                f"तुमच्या *{claim.get('insured_name','')}* च्या क्लेमची तज्ज्ञ समीक्षा आता सुरू झाली आहे. "
                f"तुमचा सविस्तर अहवाल *24-48 कामकाजाच्या तासांत* मिळेल — इथे WhatsApp वर आणि डॅशबोर्डवर.\n\n"
                f"— Nidaan – The Legal Consultants LLP")
    else:
        body = (f"Thank you {name}! ✅ Your ₹499 payment is confirmed.\n\n"
                f"The expert review of your *{claim.get('insured_name','')}* claim has started now. "
                f"Your detailed report arrives within *24-48 business hours* — here on WhatsApp and on your dashboard.\n\n"
                f"— Nidaan – The Legal Consultants LLP")

    wa_phone = (claim.get("insured_phone") or claim.get("account_phone") or "") if prefs.get("wa_opt_in") else ""
    await dispatch(
        event_key="funnel.paid", priority=PRIORITY_P1,
        recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=account_id,
        recipient_phone=wa_phone, recipient_email=claim.get("account_email") or "",
        subject="Payment confirmed — your review has started",
        body=body, claim_id=claim_id)


async def on_report_ready(claim_id: int):
    """The legal ASSESSMENT was delivered. Notify the customer (dashboard +
    WhatsApp + email) with the outcome — can_fight (Nidaan legal team will
    contact) or no_scope (settled / no basis) — + a link to read it. en/hi/mr."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT c.*, a.owner_name, a.email AS account_email, a.phone AS account_phone "
            "FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id "
            "WHERE c.claim_id=?", (claim_id,))).fetchone()
    if not row:
        return
    claim = dict(row)
    account_id = claim["account_id"]
    prefs = await get_subscriber_prefs(account_id)
    lang = _funnel_lang(prefs.get("comm_lang") or "en")
    name = (claim.get("owner_name") or "").split(" ")[0]
    insured = claim.get("insured_name", "")
    outcome = claim.get("review_outcome")
    dash = f"{NIDAAN_BASE_URL}/nidaan/dashboard"

    if outcome == "can_fight":
        subject = "Your claim review is ready — it can be challenged"
        if lang == "hi":
            body = (f"शुभ समाचार {name}! 🎯\n\n*{insured}* के क्लेम की हमारी कानूनी समीक्षा पूरी हो गई — "
                    f"और इसमें लड़ने का मज़बूत आधार है। Nidaan की कानूनी टीम जल्द ही आपसे संपर्क करके आगे की प्रक्रिया संभालेगी।\n\n"
                    f"पूरी समीक्षा यहाँ पढ़ें: {dash}\n\n— Nidaan – The Legal Consultants LLP")
        elif lang == "mr":
            body = (f"आनंदाची बातमी {name}! 🎯\n\n*{insured}* च्या क्लेमची आमची कायदेशीर समीक्षा पूर्ण झाली — "
                    f"आणि तो लढण्यासाठी भक्कम आधार आहे. Nidaan ची कायदेशीर टीम लवकरच तुमच्याशी संपर्क साधेल.\n\n"
                    f"संपूर्ण समीक्षा इथे वाचा: {dash}\n\n— Nidaan – The Legal Consultants LLP")
        else:
            body = (f"Good news {name}! 🎯\n\nWe've completed the legal review of the *{insured}* claim — "
                    f"and it has a strong basis to be challenged. Nidaan's legal team will contact you shortly to take it forward.\n\n"
                    f"Read the full assessment here: {dash}\n\n— Nidaan – The Legal Consultants LLP")
    else:  # no_scope (or anything else → treat as completed assessment)
        subject = "Your claim review is ready"
        if lang == "hi":
            body = (f"नमस्ते {name},\n\n*{insured}* के क्लेम की हमारी कानूनी समीक्षा पूरी हो गई। हमारे आकलन के अनुसार, "
                    f"इस मामले में बीमा कंपनी से लड़ने का पर्याप्त आधार नहीं है — दावा उचित रूप से निपटाया गया प्रतीत होता है।\n\n"
                    f"पूरा आकलन यहाँ पढ़ें: {dash}\n\nआपके भरोसे के लिए धन्यवाद।\n— Nidaan – The Legal Consultants LLP")
        elif lang == "mr":
            body = (f"नमस्कार {name},\n\n*{insured}* च्या क्लेमची आमची कायदेशीर समीक्षा पूर्ण झाली. आमच्या मूल्यांकनानुसार, "
                    f"विमा कंपनीशी लढण्यासाठी पुरेसा आधार नाही — दावा योग्यरीत्या निकाली निघाल्याचे दिसते.\n\n"
                    f"संपूर्ण मूल्यांकन इथे वाचा: {dash}\n\nविश्वासाबद्दल धन्यवाद.\n— Nidaan – The Legal Consultants LLP")
        else:
            body = (f"Hello {name},\n\nWe've completed the legal review of the *{insured}* claim. Based on our "
                    f"assessment, there isn't a strong basis to challenge the insurer here — the claim appears to "
                    f"have been settled fairly.\n\nRead the full assessment here: {dash}\n\n"
                    f"Thank you for trusting us.\n— Nidaan – The Legal Consultants LLP")

    wa_phone = (claim.get("insured_phone") or claim.get("account_phone") or "") if prefs.get("wa_opt_in") else ""
    await dispatch(
        event_key="claim.review_delivered", priority=PRIORITY_P1,
        recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=account_id,
        recipient_phone=wa_phone, recipient_email=claim.get("account_email") or "",
        subject=subject, body=body, claim_id=claim_id)


async def on_lead_deletion_notice(claim_id: int, account_id: int, purge_on: str):
    """DPDP trust track: heads-up BEFORE we delete an unpaid lead's documents.
    Honest, calm, and gives a one-tap way to keep the case alive (pay → review)."""
    import biz_nidaan as _nd
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT c.*, a.owner_name, a.email AS account_email, a.phone AS account_phone "
            "FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id "
            "WHERE c.claim_id=?", (claim_id,))).fetchone()
    if not row:
        return
    claim = dict(row)
    prefs = await get_subscriber_prefs(account_id)
    lang = _funnel_lang(prefs.get("comm_lang") or "en")
    name = (claim.get("owner_name") or "").split(" ")[0]
    tok = _nd.create_pay_link_token(claim_id, account_id, hours=24 * 14)
    pay_link = f"{NIDAAN_BASE_URL}/nidaan/pay/{claim_id}?t={tok}"

    if lang == "hi":
        body = (f"नमस्ते {name},\n\n"
                f"आपने *{claim.get('insured_name','')}* का क्लेम जमा किया था पर समीक्षा अभी शुरू नहीं हुई। "
                f"DPDP Act 2023 के तहत हम आपके दस्तावेज़ ज़रूरत से ज़्यादा नहीं रखते — इसलिए *{purge_on}* को "
                f"वे सुरक्षित रूप से हटा दिए जाएँगे।\n\n"
                f"अपना केस जारी रखना है? एक टैप में ₹499 दें और समीक्षा शुरू करें:\n{pay_link}\n\n"
                f"कोई कार्रवाई न करें तो भी ठीक है — आपका डेटा कभी साझा नहीं होता।\n— Nidaan – The Legal Consultants LLP")
    elif lang == "mr":
        body = (f"नमस्कार {name},\n\n"
                f"तुम्ही *{claim.get('insured_name','')}* चा क्लेम सबमिट केला होता पण समीक्षा अजून सुरू झाली नाही. "
                f"DPDP Act 2023 नुसार आम्ही तुमची कागदपत्रे गरजेपेक्षा जास्त ठेवत नाही — म्हणून *{purge_on}* रोजी "
                f"ती सुरक्षितपणे हटवली जातील.\n\n"
                f"केस सुरू ठेवायचा? एका टॅपमध्ये ₹499 भरा आणि समीक्षा सुरू करा:\n{pay_link}\n\n"
                f"काहीही न केल्यासही हरकत नाही — तुमचा डेटा कधीही शेअर होत नाही.\n— Nidaan – The Legal Consultants LLP")
    else:
        body = (f"Hello {name},\n\n"
                f"You submitted a claim for *{claim.get('insured_name','')}* but the review hasn't started yet. "
                f"Under the DPDP Act 2023 we don't keep your documents longer than needed — so on *{purge_on}* "
                f"they'll be securely deleted.\n\n"
                f"Want to keep your case going? Start your review for ₹499 in one tap:\n{pay_link}\n\n"
                f"No action is fine too — your data is never shared.\n— Nidaan – The Legal Consultants LLP")

    wa_phone = (claim.get("insured_phone") or claim.get("account_phone") or "") if prefs.get("wa_opt_in") else ""
    await dispatch(
        event_key="funnel.lead_deletion_notice", priority=PRIORITY_P2,
        recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=account_id,
        recipient_phone=wa_phone, recipient_email=claim.get("account_email") or "",
        subject="Your uploaded documents will be securely deleted soon",
        body=body, claim_id=claim_id)


async def on_lead_data_purged(claim_id: int, account_id: int):
    """DPDP trust track: confirm we kept our word and deleted the documents."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        row = await (await conn.execute(
            "SELECT c.*, a.owner_name, a.email AS account_email, a.phone AS account_phone "
            "FROM nidaan_claims c LEFT JOIN nidaan_accounts a ON a.account_id=c.account_id "
            "WHERE c.claim_id=?", (claim_id,))).fetchone()
    if not row:
        return
    claim = dict(row)
    prefs = await get_subscriber_prefs(account_id)
    lang = _funnel_lang(prefs.get("comm_lang") or "en")
    name = (claim.get("owner_name") or "").split(" ")[0]

    if lang == "hi":
        body = (f"नमस्ते {name},\n\n"
                f"जैसा वादा था — हमने *{claim.get('insured_name','')}* के क्लेम से जुड़े आपके दस्तावेज़ "
                f"सुरक्षित रूप से हटा दिए हैं। आपका डेटा कभी साझा नहीं हुआ।\n\n"
                f"भविष्य में कभी ज़रूरत हो तो आपका स्वागत है।\n— Nidaan – The Legal Consultants LLP")
    elif lang == "mr":
        body = (f"नमस्कार {name},\n\n"
                f"वचन दिल्याप्रमाणे — आम्ही *{claim.get('insured_name','')}* च्या क्लेमशी संबंधित तुमची कागदपत्रे "
                f"सुरक्षितपणे हटवली आहेत. तुमचा डेटा कधीही शेअर झाला नाही.\n\n"
                f"भविष्यात कधीही गरज लागल्यास तुमचे स्वागत आहे.\n— Nidaan – The Legal Consultants LLP")
    else:
        body = (f"Hello {name},\n\n"
                f"As promised, we've securely deleted the documents you uploaded for the "
                f"*{claim.get('insured_name','')}* claim. Your data was never shared.\n\n"
                f"You're always welcome back whenever you need us.\n— Nidaan – The Legal Consultants LLP")

    wa_phone = (claim.get("insured_phone") or claim.get("account_phone") or "") if prefs.get("wa_opt_in") else ""
    await dispatch(
        event_key="funnel.lead_data_purged", priority=PRIORITY_P2,
        recipient_type=RECIPIENT_SUBSCRIBER, recipient_id=account_id,
        recipient_phone=wa_phone, recipient_email=claim.get("account_email") or "",
        subject="Your documents have been securely deleted",
        body=body, claim_id=claim_id)


# ═════════════════════════════════════════════════════════════════════════════
#  Deferred-queue retry — called by the existing scheduler every minute
# ═════════════════════════════════════════════════════════════════════════════
async def retry_deferred_notifications() -> int:
    """Re-attempt notifications that were deferred or failed (transient)."""
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT * FROM nidaan_notifications
            WHERE status='deferred' AND (deferred_until IS NULL OR deferred_until <= ?)
            ORDER BY created_at ASC LIMIT 20
        """, (now_str,))
        rows = [dict(r) for r in await cur.fetchall()]
    count = 0
    for r in rows:
        if r["channel"] != CHANNEL_WHATSAPP or not r["recipient_phone"]:
            continue
        # Re-check current cap
        caps = await compute_effective_caps()
        # Find any healthy instance with budget
        target_slot = None
        for slot, info in caps["by_slot"].items():
            if r["priority"] == PRIORITY_P2 and info.get("defer_p2"):
                continue
            if r["priority"] == PRIORITY_P1 and info.get("defer_p1"):
                continue
            if info.get("remaining", 0) > 0:
                target_slot = slot
                break
        if target_slot is None:
            continue
        jid = _to_wa_jid(r["recipient_phone"])
        if not jid:
            continue
        ok, wa_id, err = await _send_wa(instance_slot=target_slot, jid=jid, message=r["body"])
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute("""
                UPDATE nidaan_notifications
                SET status=?, instance_slot=?, wa_message_id=?, sent_at=?, error=?, retry_count=COALESCE(retry_count,0)+1
                WHERE notif_id=?
            """, ("sent" if ok else "failed", target_slot, wa_id,
                  now_str if ok else None, err, r["notif_id"]))
            await conn.commit()
        if ok:
            count += 1
    return count
