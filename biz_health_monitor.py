"""
biz_health_monitor.py — Tier 2 Proactive Health Monitor
Runs every 15 minutes, checks all system components,
auto-fixes safe issues, emails alerts for critical problems.
"""

import asyncio
import logging
import os
import time
import uuid
import shutil
from datetime import datetime, timedelta

import aiosqlite

import biz_database as db
import biz_email as email_svc
import biz_resilience as resilience

logger = logging.getLogger("health_monitor")

SA_EMAIL = os.getenv("SA_ALERT_EMAIL", "kumar26.dushyant@gmail.com")

# ─── Utility ──────────────────────────────────────────────────────────────────

def _run_id() -> str:
    return datetime.utcnow().strftime("%Y%m%d%H%M") + "-" + uuid.uuid4().hex[:6]


# ─── Health Check Engine ─────────────────────────────────────────────────────

async def run_full_health_check(manual: bool = False) -> dict:
    """Run all health checks, store results, auto-fix safe issues, email alerts."""
    rid = _run_id()
    results = []
    t0 = time.time()

    # Run all check categories
    results += await _check_server(rid)
    results += await _check_database(rid)
    results += await _check_email(rid)
    results += await _check_bots(rid)
    results += await _check_queue(rid)
    results += await _check_disk(rid)
    results += await _check_data_integrity(rid)
    results += await _check_payments(rid)
    results += await _check_auth(rid)

    # Store all results
    async with aiosqlite.connect(db.DB_PATH) as conn:
        for r in results:
            await conn.execute(
                """INSERT INTO health_checks
                   (run_id, category, check_name, status, detail, response_ms,
                    auto_fixable, fix_applied, fix_detail)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (rid, r["category"], r["name"], r["status"], r.get("detail", ""),
                 r.get("ms", 0), 1 if r.get("auto_fixable") else 0,
                 1 if r.get("fix_applied") else 0, r.get("fix_detail", "")))
        await conn.commit()

    total_ms = int((time.time() - t0) * 1000)
    healthy = sum(1 for r in results if r["status"] == "healthy")
    warnings = sum(1 for r in results if r["status"] == "warning")
    critical = sum(1 for r in results if r["status"] == "critical")
    fixed = sum(1 for r in results if r.get("fix_applied"))

    # Create alerts for non-healthy items
    alert_items = [r for r in results if r["status"] in ("critical", "warning")]
    if alert_items:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            for a in alert_items:
                await conn.execute(
                    """INSERT INTO health_alerts (run_id, severity, title, detail)
                       VALUES (?,?,?,?)""",
                    (rid, a["status"], a["name"], a.get("detail", "")))
            await conn.commit()

    # Email alert if critical issues found
    if critical > 0:
        await _send_alert_email(rid, results, critical, warnings, fixed)

    summary = {
        "run_id": rid,
        "total_checks": len(results),
        "healthy": healthy,
        "warnings": warnings,
        "critical": critical,
        "auto_fixed": fixed,
        "duration_ms": total_ms,
        "manual": manual,
        "checks": results,
    }

    logger.info("Health check %s: %d checks, %d healthy, %d warn, %d critical, %d fixed (%dms)",
                rid, len(results), healthy, warnings, critical, fixed, total_ms)
    return summary


# ═══ Individual Check Categories ═════════════════════════════════════════════

async def _check_server(rid: str) -> list:
    """Check server health — uptime, memory, response."""
    results = []
    try:
        import psutil
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.5)

        # Memory check
        mem_pct = mem.percent
        if mem_pct > 90:
            results.append({"category": "server", "name": "Memory Usage",
                            "status": "critical", "detail": f"{mem_pct:.0f}% used ({mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB)", "ms": 0})
        elif mem_pct > 75:
            results.append({"category": "server", "name": "Memory Usage",
                            "status": "warning", "detail": f"{mem_pct:.0f}% used", "ms": 0})
        else:
            results.append({"category": "server", "name": "Memory Usage",
                            "status": "healthy", "detail": f"{mem_pct:.0f}% used", "ms": 0})

        # CPU check
        if cpu > 90:
            results.append({"category": "server", "name": "CPU Usage",
                            "status": "critical", "detail": f"{cpu:.0f}% load", "ms": 0})
        elif cpu > 70:
            results.append({"category": "server", "name": "CPU Usage",
                            "status": "warning", "detail": f"{cpu:.0f}% load", "ms": 0})
        else:
            results.append({"category": "server", "name": "CPU Usage",
                            "status": "healthy", "detail": f"{cpu:.0f}% load", "ms": 0})
    except ImportError:
        # psutil not available, basic check only
        results.append({"category": "server", "name": "Server Process",
                        "status": "healthy", "detail": "Running (psutil not installed)", "ms": 0})
    except Exception as e:
        results.append({"category": "server", "name": "Server Process",
                        "status": "warning", "detail": str(e)[:120], "ms": 0})
    return results


async def _check_database(rid: str) -> list:
    """Check database connectivity, size, and response time."""
    results = []
    t0 = time.time()
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            cur = await conn.execute("SELECT COUNT(*) FROM tenants")
            cnt = (await cur.fetchone())[0]
        ms = int((time.time() - t0) * 1000)
        db_size = os.path.getsize(db.DB_PATH) if os.path.exists(db.DB_PATH) else 0

        if ms > 2000:
            results.append({"category": "database", "name": "Database Response",
                            "status": "critical", "detail": f"Query took {ms}ms — very slow", "ms": ms})
        elif ms > 500:
            results.append({"category": "database", "name": "Database Response",
                            "status": "warning", "detail": f"Query took {ms}ms — slow", "ms": ms})
        else:
            results.append({"category": "database", "name": "Database Response",
                            "status": "healthy", "detail": f"{ms}ms, {cnt} tenants, {db_size // 1024}KB", "ms": ms})

        # Check WAL size
        wal_path = db.DB_PATH + "-wal"
        if os.path.exists(wal_path):
            wal_size = os.path.getsize(wal_path)
            if wal_size > 50 * 1024 * 1024:  # 50MB WAL
                results.append({"category": "database", "name": "WAL Size",
                                "status": "warning", "detail": f"WAL is {wal_size // (1024*1024)}MB — needs checkpoint",
                                "auto_fixable": True, "ms": 0})
                # Auto-fix: checkpoint
                try:
                    async with aiosqlite.connect(db.DB_PATH) as conn:
                        await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    results[-1]["fix_applied"] = True
                    results[-1]["fix_detail"] = "WAL checkpoint applied"
                    results[-1]["status"] = "healthy"
                except Exception:
                    pass
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        results.append({"category": "database", "name": "Database Connection",
                        "status": "critical", "detail": f"Cannot connect: {str(e)[:100]}", "ms": ms})
    return results


async def _check_email(rid: str) -> list:
    """Check email system availability."""
    results = []
    if email_svc.is_enabled():
        results.append({"category": "email", "name": "SMTP Configuration",
                        "status": "healthy", "detail": "SMTP configured and ready", "ms": 0})
    else:
        results.append({"category": "email", "name": "SMTP Configuration",
                        "status": "critical", "detail": "Email not configured — OTP and notifications disabled", "ms": 0})
    return results


async def _check_bots(rid: str) -> list:
    """Check Telegram bot health + auto-restart failed bots."""
    results = []
    try:
        from biz_bot_manager import bot_manager
        if not bot_manager:
            results.append({"category": "bots", "name": "Bot Manager",
                            "status": "warning", "detail": "Bot manager not initialized", "ms": 0})
            return results

        # Master bot
        master_ok = bot_manager._master_bot is not None and bot_manager._master_bot.running
        if master_ok:
            results.append({"category": "bots", "name": "Master Bot",
                            "status": "healthy", "detail": "@SarathiBizBot running", "ms": 0})
        else:
            results.append({"category": "bots", "name": "Master Bot",
                            "status": "critical", "detail": "Master bot not running", "ms": 0})

        # Tenant bots
        total = len(bot_manager._bots) if bot_manager._bots else 0
        running = len([b for b in bot_manager._bots.values() if b.running]) if bot_manager._bots else 0
        stopped = total - running

        if total == 0:
            results.append({"category": "bots", "name": "Tenant Bots",
                            "status": "healthy", "detail": "No tenant bots configured", "ms": 0})
        elif stopped == 0:
            results.append({"category": "bots", "name": "Tenant Bots",
                            "status": "healthy", "detail": f"{running}/{total} running", "ms": 0})
        else:
            results.append({"category": "bots", "name": "Tenant Bots",
                            "status": "warning", "detail": f"{running}/{total} running, {stopped} stopped",
                            "auto_fixable": True, "ms": 0})
            # Auto-fix: restart stopped bots
            fixed_count = 0
            async with aiosqlite.connect(db.DB_PATH) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(
                    "SELECT tenant_id, tg_bot_token FROM tenants WHERE tg_bot_token IS NOT NULL AND tg_bot_token != '' AND is_active = 1")
                tenants = [dict(r) for r in await cursor.fetchall()]
            for t in tenants:
                tid = t["tenant_id"]
                if tid in bot_manager._bots and not bot_manager._bots[tid].running:
                    try:
                        ok = await bot_manager.restart_tenant_bot(tid, t["tg_bot_token"])
                        if ok:
                            fixed_count += 1
                    except Exception:
                        pass
            if fixed_count > 0:
                results[-1]["fix_applied"] = True
                results[-1]["fix_detail"] = f"Restarted {fixed_count} bot(s)"
                if fixed_count == stopped:
                    results[-1]["status"] = "healthy"
    except Exception as e:
        results.append({"category": "bots", "name": "Bot Health",
                        "status": "warning", "detail": str(e)[:120], "ms": 0})
    return results


async def _check_queue(rid: str) -> list:
    """Check message queue health + auto-clear stuck messages."""
    results = []
    try:
        stats = await resilience.get_queue_stats()
        pending = stats.get("pending", 0)
        failed = stats.get("failed", 0)
        oldest = stats.get("oldest_pending")

        # Check for stuck messages (older than 2 hours)
        stuck = False
        if oldest:
            try:
                oldest_dt = datetime.fromisoformat(oldest)
                if datetime.utcnow() - oldest_dt > timedelta(hours=2):
                    stuck = True
            except Exception:
                pass

        if failed > 20:
            results.append({"category": "queue", "name": "Dead Letters",
                            "status": "warning", "detail": f"{failed} failed messages in queue",
                            "auto_fixable": True, "ms": 0})
            # Auto-fix: clear old dead letters (>7 days)
            try:
                async with aiosqlite.connect(resilience.DB_PATH) as conn:
                    cur = await conn.execute(
                        "DELETE FROM message_queue WHERE status = 'failed' AND created_at < datetime('now', '-7 days')")
                    cleaned = cur.rowcount
                    await conn.commit()
                if cleaned > 0:
                    results[-1]["fix_applied"] = True
                    results[-1]["fix_detail"] = f"Cleaned {cleaned} old dead letters"
            except Exception:
                pass
        elif failed > 0:
            results.append({"category": "queue", "name": "Dead Letters",
                            "status": "healthy", "detail": f"{failed} failed (within normal range)", "ms": 0})

        if stuck:
            results.append({"category": "queue", "name": "Stuck Messages",
                            "status": "warning", "detail": f"{pending} pending, oldest: {oldest}",
                            "auto_fixable": True, "ms": 0})
            # Auto-fix: retry stuck messages by resetting retry count
            try:
                async with aiosqlite.connect(resilience.DB_PATH) as conn:
                    await conn.execute(
                        "UPDATE message_queue SET retry_count = 0 WHERE status = 'pending' AND created_at < datetime('now', '-2 hours')")
                    await conn.commit()
                results[-1]["fix_applied"] = True
                results[-1]["fix_detail"] = "Reset retry count on stuck messages"
            except Exception:
                pass
        elif pending > 50:
            results.append({"category": "queue", "name": "Queue Backlog",
                            "status": "warning", "detail": f"{pending} messages pending", "ms": 0})
        else:
            results.append({"category": "queue", "name": "Message Queue",
                            "status": "healthy", "detail": f"{pending} pending, {failed} failed", "ms": 0})
    except Exception as e:
        results.append({"category": "queue", "name": "Queue Health",
                        "status": "warning", "detail": str(e)[:120], "ms": 0})
    return results


async def _check_disk(rid: str) -> list:
    """Check disk space."""
    results = []
    try:
        disk = shutil.disk_usage(os.path.dirname(os.path.abspath(db.DB_PATH)))
        free_gb = disk.free / (1024 ** 3)
        used_pct = (disk.used / disk.total) * 100

        if free_gb < 1:
            results.append({"category": "disk", "name": "Disk Space",
                            "status": "critical", "detail": f"{free_gb:.1f}GB free ({used_pct:.0f}% used)", "ms": 0})
        elif free_gb < 5:
            results.append({"category": "disk", "name": "Disk Space",
                            "status": "warning", "detail": f"{free_gb:.1f}GB free ({used_pct:.0f}% used)", "ms": 0})
        else:
            results.append({"category": "disk", "name": "Disk Space",
                            "status": "healthy", "detail": f"{free_gb:.1f}GB free ({used_pct:.0f}% used)", "ms": 0})
    except Exception as e:
        results.append({"category": "disk", "name": "Disk Space",
                        "status": "warning", "detail": str(e)[:120], "ms": 0})
    return results


async def _check_data_integrity(rid: str) -> list:
    """Check for common data integrity issues and auto-clean expired sessions."""
    results = []
    try:
        async with aiosqlite.connect(db.DB_PATH) as conn:
            # Expired trials still marked active
            cur = await conn.execute(
                """SELECT COUNT(*) FROM tenants
                   WHERE subscription_status = 'trial' AND is_active = 1
                   AND trial_ends_at < datetime('now')""")
            expired_trials = (await cur.fetchone())[0]

            if expired_trials > 0:
                results.append({"category": "data", "name": "Expired Trials",
                                "status": "warning", "detail": f"{expired_trials} expired trials still active",
                                "auto_fixable": True, "ms": 0})
            else:
                results.append({"category": "data", "name": "Data Integrity",
                                "status": "healthy", "detail": "No expired trials left active", "ms": 0})

            # Orphan agents (tenant deleted or inactive)
            cur = await conn.execute(
                """SELECT COUNT(*) FROM agents a
                   LEFT JOIN tenants t ON a.tenant_id = t.tenant_id
                   WHERE t.tenant_id IS NULL AND a.tenant_id > 0""")
            orphan_agents = (await cur.fetchone())[0]

            if orphan_agents > 0:
                results.append({"category": "data", "name": "Orphan Agents",
                                "status": "warning", "detail": f"{orphan_agents} agents without valid tenant", "ms": 0})

            # Clean expired OTP codes (>30 min old)
            try:
                cur = await conn.execute(
                    """DELETE FROM login_requests
                       WHERE created_at < datetime('now', '-30 minutes')""")
                cleaned = cur.rowcount
                await conn.commit()
                if cleaned > 0:
                    results.append({"category": "data", "name": "OTP Cleanup",
                                    "status": "healthy", "detail": f"Cleaned {cleaned} expired OTPs",
                                    "auto_fixable": True, "fix_applied": True,
                                    "fix_detail": f"Removed {cleaned} expired OTP codes", "ms": 0})
            except Exception:
                pass  # table might not exist yet

    except Exception as e:
        results.append({"category": "data", "name": "Data Integrity",
                        "status": "warning", "detail": str(e)[:120], "ms": 0})
    return results


async def _check_payments(rid: str) -> list:
    """Check payment gateway status."""
    results = []
    try:
        import biz_payments as payments
        if payments.is_enabled():
            mode = "Test" if payments.is_test_mode() else "Live"
            results.append({"category": "payments", "name": "Razorpay Gateway",
                            "status": "healthy", "detail": f"{mode} mode active", "ms": 0})
        else:
            results.append({"category": "payments", "name": "Razorpay Gateway",
                            "status": "warning", "detail": "Not configured", "ms": 0})
    except Exception as e:
        results.append({"category": "payments", "name": "Payment Gateway",
                        "status": "warning", "detail": str(e)[:120], "ms": 0})
    return results


async def _check_auth(rid: str) -> list:
    """Check authentication system."""
    results = []
    google_ok = bool(os.getenv("GOOGLE_CLIENT_ID"))
    email_ok = email_svc.is_enabled()

    if email_ok and google_ok:
        results.append({"category": "auth", "name": "Authentication",
                        "status": "healthy", "detail": "Email OTP + Google Sign-In active", "ms": 0})
    elif email_ok:
        results.append({"category": "auth", "name": "Authentication",
                        "status": "healthy", "detail": "Email OTP active (Google Sign-In not configured)", "ms": 0})
    else:
        results.append({"category": "auth", "name": "Authentication",
                        "status": "critical", "detail": "No auth method available", "ms": 0})
    return results


# ─── Alert Email ──────────────────────────────────────────────────────────────

async def _send_alert_email(rid: str, results: list, critical: int, warnings: int, fixed: int):
    """Send alert email to SA when critical issues detected."""
    critical_items = [r for r in results if r["status"] == "critical"]
    warning_items = [r for r in results if r["status"] == "warning"]
    fixed_items = [r for r in results if r.get("fix_applied")]

    rows = ""
    for r in critical_items:
        rows += f'<tr style="background:#fef2f2"><td style="padding:10px;border-bottom:1px solid #e2e8f0"><strong>🔴 {r["name"]}</strong></td><td style="padding:10px;border-bottom:1px solid #e2e8f0">{r.get("detail","")}</td></tr>'
    for r in warning_items:
        rows += f'<tr style="background:#fffbeb"><td style="padding:10px;border-bottom:1px solid #e2e8f0"><strong>🟡 {r["name"]}</strong></td><td style="padding:10px;border-bottom:1px solid #e2e8f0">{r.get("detail","")}</td></tr>'
    for r in fixed_items:
        rows += f'<tr style="background:#f0fdf4"><td style="padding:10px;border-bottom:1px solid #e2e8f0"><strong>🟢 {r["name"]}</strong></td><td style="padding:10px;border-bottom:1px solid #e2e8f0">Auto-fixed: {r.get("fix_detail","")}</td></tr>'

    html = f"""
    <h2>⚠️ Health Monitor Alert</h2>
    <p>The automated health check detected issues that need attention.</p>
    <div class="highlight">
        <strong>Run ID:</strong> {rid}<br>
        <strong>🔴 Critical:</strong> {critical} &nbsp; <strong>🟡 Warnings:</strong> {warnings} &nbsp; <strong>🟢 Auto-fixed:</strong> {fixed}
    </div>
    <table style="width:100%;border-collapse:collapse;margin:20px 0">
        <tr style="background:#f1f5f9"><th style="padding:10px;text-align:left;border-bottom:2px solid #e2e8f0">Check</th><th style="padding:10px;text-align:left;border-bottom:2px solid #e2e8f0">Detail</th></tr>
        {rows}
    </table>
    <p><a href="https://sarathi-ai.com/superadmin" class="btn">Open Cockpit →</a></p>
    """

    await email_svc.send_email(
        SA_EMAIL,
        f"🚨 Health Alert: {critical} critical issue(s) detected",
        email_svc._wrap_template("Health Monitor Alert", html))

    # Mark alert as emailed
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "UPDATE health_alerts SET emailed = 1 WHERE run_id = ?", (rid,))
        await conn.commit()


# ─── API Helpers ──────────────────────────────────────────────────────────────

async def get_latest_checks() -> dict:
    """Get the latest health check run results."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Get latest run_id
        cur = await conn.execute(
            "SELECT DISTINCT run_id FROM health_checks ORDER BY created_at DESC LIMIT 1")
        row = await cur.fetchone()
        if not row:
            return {"run_id": None, "checks": [], "summary": {}}

        run_id = row["run_id"]
        cur = await conn.execute(
            "SELECT * FROM health_checks WHERE run_id = ? ORDER BY category, check_name", (run_id,))
        checks = [dict(r) for r in await cur.fetchall()]

        healthy = sum(1 for c in checks if c["status"] == "healthy")
        warnings = sum(1 for c in checks if c["status"] == "warning")
        critical = sum(1 for c in checks if c["status"] == "critical")
        fixed = sum(1 for c in checks if c["fix_applied"])

        return {
            "run_id": run_id,
            "created_at": checks[0]["created_at"] if checks else None,
            "total": len(checks),
            "healthy": healthy,
            "warnings": warnings,
            "critical": critical,
            "auto_fixed": fixed,
            "checks": checks,
        }


async def get_check_history(limit: int = 20) -> list:
    """Get history of health check runs."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("""
            SELECT run_id, created_at,
                   COUNT(*) as total,
                   SUM(CASE WHEN status='healthy' THEN 1 ELSE 0 END) as healthy,
                   SUM(CASE WHEN status='warning' THEN 1 ELSE 0 END) as warnings,
                   SUM(CASE WHEN status='critical' THEN 1 ELSE 0 END) as critical,
                   SUM(fix_applied) as auto_fixed
            FROM health_checks
            GROUP BY run_id
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(r) for r in await cur.fetchall()]


async def get_alerts(limit: int = 50) -> list:
    """Get recent health alerts."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute(
            "SELECT * FROM health_alerts ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in await cur.fetchall()]


async def cleanup_old_data(days: int = 30):
    """Clean up health check data older than N days."""
    async with aiosqlite.connect(db.DB_PATH) as conn:
        await conn.execute(
            "DELETE FROM health_checks WHERE created_at < datetime('now', ?)",
            (f"-{days} days",))
        await conn.execute(
            "DELETE FROM health_alerts WHERE created_at < datetime('now', ?)",
            (f"-{days} days",))
        await conn.commit()
