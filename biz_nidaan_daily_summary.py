"""
NidaanPartner DAILY OPS SUMMARY — an AI "watch on top" of the superadmin ops.

At ~8pm IST the AI gathers everything that HAPPENED on the ops app today (who did what, from
the audit log + tasks + claim status changes + payments), plus a short pendency flag, writes a
crisp Gemini summary in each super-admin's preferred language, and delivers it on Telegram as
text + an optional voice note. If nothing happened, it says so briefly (or stays silent).

This reports SYSTEM activity only — it can't see off-system progress, so the founder may nudge
staff to log progress on claims. Never raises to the scheduler.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
import os
from datetime import datetime, timedelta, timezone

import aiosqlite

import biz_database as db

logger = logging.getLogger("nidaan.daily_summary")
DB_PATH = db.DB_PATH
IST = timezone(timedelta(hours=5, minutes=30))


async def _gather(day_start_utc: str, day_end_utc: str) -> dict:
    """Collect today's ops activity. Each source guarded so one failure can't sink the digest."""
    out: dict = {"audit": [], "tasks_created": 0, "tasks_done": 0, "claims_new": 0,
                 "status_changes": [], "payments_n": 0, "payments_rs": 0.0,
                 "overdue_tasks": 0, "l2_unassigned": 0}
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        async def q(sql, args=()):
            try:
                return await (await c.execute(sql, args)).fetchall()
            except Exception as e:  # noqa: BLE001
                logger.info("daily_summary query skipped: %s", e); return []
        # Who did what (audit log) — grouped by actor + action.
        out["audit"] = [dict(r) for r in await q(
            "SELECT actor_name, actor_role, action, COUNT(*) n FROM nidaan_audit_log "
            "WHERE created_at>=? AND created_at<? GROUP BY actor_name, action "
            "ORDER BY n DESC LIMIT 40", (day_start_utc, day_end_utc))]
        # Tasks created + completed today.
        r = await q("SELECT COUNT(*) n FROM nidaan_quick_tasks WHERE created_at>=? AND created_at<?",
                    (day_start_utc, day_end_utc)); out["tasks_created"] = (r[0]["n"] if r else 0)
        r = await q("SELECT COUNT(*) n FROM nidaan_quick_tasks WHERE completed_at>=? AND completed_at<?",
                    (day_start_utc, day_end_utc)); out["tasks_done"] = (r[0]["n"] if r else 0)
        # New claims + claim status changes today.
        r = await q("SELECT COUNT(*) n FROM nidaan_claims WHERE created_at>=? AND created_at<?",
                    (day_start_utc, day_end_utc)); out["claims_new"] = (r[0]["n"] if r else 0)
        out["status_changes"] = [dict(r) for r in await q(
            "SELECT to_status, COUNT(*) n FROM nidaan_claim_status_log "
            "WHERE changed_at>=? AND changed_at<? GROUP BY to_status ORDER BY n DESC LIMIT 15",
            (day_start_utc, day_end_utc))]
        # Money received today.
        r = await q("SELECT COUNT(*) n, COALESCE(SUM(total_paise),0) p FROM nidaan_payments "
                    "WHERE created_at>=? AND created_at<? AND status!='refunded'",
                    (day_start_utc, day_end_utc))
        if r:
            out["payments_n"] = r[0]["n"]; out["payments_rs"] = round((r[0]["p"] or 0) / 100.0, 2)
        # Pendency flags (point-in-time, not day-scoped).
        _today = datetime.now(IST).strftime("%Y-%m-%d")
        r = await q("SELECT COUNT(*) n FROM nidaan_quick_tasks WHERE status NOT IN ('done','cancelled') "
                    "AND due_date IS NOT NULL AND due_date<?", (_today,)); out["overdue_tasks"] = (r[0]["n"] if r else 0)
        r = await q("SELECT COUNT(*) n FROM nidaan_claims WHERE review_outcome='can_fight' "
                    "AND COALESCE(assigned_to_staff_id,0)=0 AND status NOT IN "
                    "('closed','withdrawn','resolved_won','resolved_lost')"); out["l2_unassigned"] = (r[0]["n"] if r else 0)
    return out


def _has_activity(a: dict) -> bool:
    return bool(a["audit"] or a["tasks_created"] or a["tasks_done"] or a["claims_new"]
               or a["status_changes"] or a["payments_n"])


def _facts_text(a: dict, date_label: str) -> str:
    lines = [f"Date: {date_label} (NidaanPartner ops)"]
    if a["audit"]:
        lines.append("Actions by staff:")
        for r in a["audit"]:
            lines.append(f"  - {r.get('actor_name') or 'someone'} ({r.get('actor_role') or ''}): "
                         f"{r.get('action')} x{r.get('n')}")
    lines.append(f"Tasks created: {a['tasks_created']}, completed: {a['tasks_done']}")
    lines.append(f"New claims: {a['claims_new']}")
    if a["status_changes"]:
        lines.append("Claim status changes: " + ", ".join(f"{r['to_status']}:{r['n']}" for r in a["status_changes"]))
    if a["payments_n"]:
        lines.append(f"Payments received: {a['payments_n']} (Rs.{a['payments_rs']})")
    lines.append(f"Pendency: {a['overdue_tasks']} overdue task(s), {a['l2_unassigned']} unassigned L2 claim(s)")
    return "\n".join(lines)


async def _summarize(facts: str, lang: str) -> str:
    """Gemini → a crisp end-of-day digest for a super-admin, in their language."""
    lang_name = {"hi": "Hindi", "hinglish": "Hinglish (Roman-script Hindi)"}.get(lang, "English")
    prompt = (
        "You are the NidaanPartner ops watch-assistant. Write a SHORT end-of-day summary for a "
        "super-admin from the raw activity below — only what happened on the ops app today: who "
        "did what, notable progress, and flag high pendency. Be concise (6-10 bullet lines max), "
        "concrete, no fluff, no invented details. If activity is thin, say so in one line. "
        f"Write it in {lang_name}. Start with a one-line headline.\n\n=== ACTIVITY ===\n" + facts)
    try:
        import biz_ai
        txt = await biz_ai._ask_gemini(prompt)
        return (txt or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("daily_summary gemini failed: %s", e)
        # Fallback: send the raw facts so the digest still goes out.
        return "📊 Today's ops activity:\n" + facts


def _wav_to_ogg(wav: bytes) -> "bytes | None":
    """Convert WAV → Opus/OGG via ffmpeg for a Telegram voice note. None on any failure."""
    wp = op = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav); wp = f.name
        op = wp[:-4] + ".ogg"
        subprocess.run(["ffmpeg", "-y", "-i", wp, "-c:a", "libopus", "-b:a", "32k", op],
                       check=True, capture_output=True, timeout=90)
        with open(op, "rb") as f:
            return f.read()
    except Exception as e:  # noqa: BLE001
        logger.info("daily_summary wav->ogg failed: %s", e); return None
    finally:
        for p in (wp, op):
            try:
                if p and os.path.exists(p):
                    os.unlink(p)
            except Exception:
                pass


async def _voice_bytes(text: str, lang: str) -> "bytes | None":
    """TTS the summary → OGG voice bytes. Best-effort."""
    try:
        import biz_tts
        wav = await biz_tts.cached_wav(text[:1500], voice="Kore")
        return _wav_to_ogg(wav) if wav else None
    except Exception as e:  # noqa: BLE001
        logger.info("daily_summary tts failed: %s", e); return None


async def run_daily_ops_summary(force: bool = False) -> dict:
    """Build + deliver today's ops summary to every super-admin on Telegram (text + voice)."""
    # Master switch (super-admin can turn the whole thing off).
    try:
        import biz_nidaan as _n
        if not force and str(await _n.get_ops_setting("daily_summary_enabled", "1")).strip().lower() \
                not in ("1", "true", "on", "yes"):
            return {"ok": False, "error": "disabled"}
    except Exception:
        pass
    now_ist = datetime.now(IST)
    start_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_ist.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    end_utc = now_ist.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    date_label = now_ist.strftime("%d %b %Y")
    activity = await _gather(start_utc, end_utc)

    import biz_nidaan_telegram as _tg
    async with aiosqlite.connect(DB_PATH) as c:
        c.row_factory = aiosqlite.Row
        admins = [dict(r) for r in await (await c.execute(
            "SELECT staff_id, name, telegram_chat_id, COALESCE(telegram_lang,'en') lang "
            "FROM nidaan_staff WHERE role IN ('super_admin','sub_super_admin') AND status='active' "
            "AND deleted_at IS NULL AND COALESCE(telegram_chat_id,'')<>''")).fetchall()]
    if not activity_flag_or_silence(activity):
        return {"ok": True, "sent": 0, "reason": "no_activity"}

    facts = _facts_text(activity, date_label)
    sent = 0
    _cache: dict = {}
    for a in admins:
        lang = a.get("lang") or "en"
        if lang not in _cache:
            summary = await _summarize(facts, lang)
            header = {"hi": f"🌙 *NidaanPartner — आज की गतिविधि* ({date_label})",
                      "hinglish": f"🌙 *NidaanPartner — aaj ki activity* ({date_label})"}.get(
                          lang, f"🌙 *NidaanPartner — today's ops activity* ({date_label})")
            _cache[lang] = {"text": header + "\n\n" + summary,
                            "voice": await _voice_bytes(summary, lang)}
        pack = _cache[lang]
        try:
            ok, _ = await _tg.send_message(str(a["telegram_chat_id"]), pack["text"])
            if ok:
                sent += 1
            if pack["voice"]:
                await _tg.send_voice(str(a["telegram_chat_id"]), pack["voice"])
        except Exception as e:  # noqa: BLE001
            logger.info("daily_summary send to %s failed: %s", a.get("name"), e)
    logger.info("🌙 Daily ops summary sent to %d super-admin(s)", sent)
    return {"ok": True, "sent": sent}


def activity_flag_or_silence(a: dict) -> bool:
    """Send even a 'quiet day' line so admins know the watch is alive — unless there is truly
    nothing at all (no activity AND no pendency), in which case stay silent."""
    return _has_activity(a) or bool(a["overdue_tasks"] or a["l2_unassigned"])
