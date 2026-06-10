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
    """Last 10 digits, no plus/spaces. Returns '' if invalid."""
    digits = re.sub(r"[^0-9]", "", str(p or ""))
    return digits[-10:] if len(digits) >= 10 else ""


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
    """Round-robin among healthy instances for staff-direction messages."""
    global _staff_rr_idx
    async with _staff_rr_lock:
        healthy = await _list_healthy_instances()
        if not healthy:
            return None
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
        return cur.lastrowid


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
async def _send_wa(*, instance_slot: int, jid: str, message: str) -> tuple[bool, str, str]:
    """Returns (success, wa_message_id, error_str)."""
    try:
        import biz_whatsapp_evolution as wa_evo
        inst = await get_official_instance(instance_slot)
        if not inst:
            return (False, "", f"No instance for slot {instance_slot}")
        result = await wa_evo.send_text(inst["evolution_instance"], jid, message, delay_ms=1500)
        if result and not result.get("error"):
            await _bump_sent_count(instance_slot)
            wa_id = ""
            try:
                wa_id = ((result.get("key") or {}).get("id")) or ""
            except Exception:
                pass
            return (True, wa_id, "")
        return (False, "", str(result.get("error") if result else "unknown"))
    except Exception as e:
        return (False, "", str(e))


async def _send_email(*, to_email: str, subject: str, html_body: str,
                      text_body: str = "") -> tuple[bool, str]:
    try:
        import biz_email as email_svc
        ok = await email_svc.send_email(
            to_email=to_email,
            subject=subject,
            html_body=html_body,
            text_body=text_body)
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
                   force_urgent: bool = False) -> dict:
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
                        ok, wa_id, err = await _send_wa(
                            instance_slot=chosen_slot, jid=jid, message=body)
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
        # For P0, ALWAYS send email regardless. For P1/P2, send if WA didn't succeed.
        should_email = (priority == PRIORITY_P0) or (not wa_sent_ok)
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
                  f"Open: /nidaan/ops (Tasks)"),
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
        recipient_email=staff.get("email") or "",
        subject=f"Task #{task_id} assigned to you",
        body=(f"🗂️ {task.get('title','')}\n"
              f"Case #{task.get('claim_id')} — {task.get('claim_insured_name','')}\n"
              f"Status: {task.get('status_slug')}\n"
              f"Open: /nidaan/ops (Tasks)"),
        claim_id=task.get("claim_id"), task_id=task_id)


async def on_quick_task_assigned(quick_task: dict):
    """A Quick Task was assigned to a staff member.
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
    if not assignee_id:
        return  # unassigned — nothing to notify
    # Self-assigned: no notification noise
    if assignee_id == quick_task.get("created_by_staff_id"):
        return
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
    body_lines = [f"📌 {title}"]
    if quick_task.get("claim_id"):
        body_lines.append(f"Linked: claim #{quick_task['claim_id']} "
                          f"({quick_task.get('insured_name','')})")
    if quick_task.get("creator_name"):
        body_lines.append(f"From: {quick_task['creator_name']}")
    if quick_task.get("due_date"):
        body_lines.append(f"Due: {quick_task['due_date']}")
    body_lines.append("Open: /nidaan/ops")
    await dispatch(
        event_key="quick_task.assigned",
        priority=notif_priority,
        recipient_type=RECIPIENT_STAFF, recipient_id=assignee_id,
        recipient_phone=quick_task.get("assignee_phone") or "",
        recipient_email=quick_task.get("assignee_email") or "",
        subject=f"[Nidaan] Quick task: {title}",
        body="\n".join(body_lines),
        claim_id=quick_task.get("claim_id"))


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
                recipient_email=staff.get("email") or "",
                subject=f"Task #{task_id}: {from_status} → {to_status}",
                body=(f"Task #{task_id}: *{task.get('title','')}*\n"
                      f"Status: {from_status} → {to_status}\n"
                      + (f"Note: {note}\n" if note else "")
                      + f"Open: /nidaan/ops"),
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
