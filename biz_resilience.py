# =============================================================================
#  biz_resilience.py — Sarathi-AI: Network Resilience & Bot Recovery Engine
# =============================================================================
#
#  Handles:
#    - Automatic retry with exponential backoff for all API calls
#    - Graceful degradation when services are unavailable
#    - Bot conversation recovery after network interruptions
#    - Message queue for offline/low-network scenarios
#    - Health monitoring for external services
#
# =============================================================================

import asyncio
import functools
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Callable, Optional

import aiosqlite

logger = logging.getLogger("sarathi.resilience")

DB_PATH = os.path.join(os.path.dirname(__file__), "sarathi_biz.db")

# =============================================================================
#  RETRY DECORATOR — Exponential backoff for any async function
# =============================================================================

def retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (
        ConnectionError, TimeoutError, OSError,
        asyncio.TimeoutError,
    ),
    fallback_value: Any = None,
    service_name: str = "",
):
    """
    Decorator: retry async functions with exponential backoff.
    
    Usage:
        @retry_async(max_retries=3, service_name="Gemini")
        async def call_gemini(prompt):
            ...
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            svc = service_name or func.__name__

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = min(base_delay * (backoff_factor ** attempt),
                                    max_delay)
                        logger.warning(
                            "⚡ %s attempt %d/%d failed (%s). "
                            "Retrying in %.1fs...",
                            svc, attempt + 1, max_retries + 1,
                            type(e).__name__, delay)
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "❌ %s failed after %d attempts: %s",
                            svc, max_retries + 1, e)
                except Exception as e:
                    # Non-retryable exception — fail immediately
                    logger.error("❌ %s non-retryable error: %s", svc, e)
                    if fallback_value is not None:
                        return fallback_value
                    raise

            # All retries exhausted — use fallback or raise
            if fallback_value is not None:
                logger.info("📋 %s using fallback value", svc)
                return fallback_value
            raise last_error
        return wrapper
    return decorator


# =============================================================================
#  MESSAGE QUEUE — Hold messages when network is down, deliver when back
# =============================================================================

async def init_message_queue():
    """Create the message_queue table if it doesn't exist."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS message_queue (
                queue_id    INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id   INTEGER,
                agent_id    INTEGER,
                channel     TEXT NOT NULL DEFAULT 'whatsapp',
                recipient   TEXT NOT NULL,
                message     TEXT NOT NULL,
                metadata    TEXT,
                status      TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 5,
                created_at  TEXT DEFAULT (datetime('now')),
                next_retry  TEXT DEFAULT (datetime('now')),
                sent_at     TEXT,
                error       TEXT
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mq_status
            ON message_queue(status, next_retry)
        """)
        await conn.commit()
    logger.info("📬 Message queue initialized")


async def enqueue_message(
    channel: str, recipient: str, message: str,
    tenant_id: int = None, agent_id: int = None,
    metadata: dict = None, max_retries: int = 5,
) -> int:
    """
    Add a message to the delivery queue.
    Returns the queue_id.
    """
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """INSERT INTO message_queue
               (tenant_id, agent_id, channel, recipient, message, metadata, max_retries)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tenant_id, agent_id, channel, recipient, message,
             json.dumps(metadata) if metadata else None, max_retries))
        await conn.commit()
        qid = cursor.lastrowid
    logger.debug("📬 Queued message %d → %s via %s", qid, recipient, channel)
    return qid


async def get_pending_messages(limit: int = 50) -> list:
    """Get messages that are ready to send (pending + next_retry <= now)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM message_queue
               WHERE status = 'pending'
                 AND next_retry <= datetime('now')
               ORDER BY created_at ASC
               LIMIT ?""",
            (limit,))
        return [dict(row) for row in await cursor.fetchall()]


async def mark_sent(queue_id: int):
    """Mark a queued message as successfully sent."""
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute(
            """UPDATE message_queue
               SET status = 'sent', sent_at = datetime('now')
               WHERE queue_id = ?""",
            (queue_id,))
        await conn.commit()


async def mark_failed(queue_id: int, error: str):
    """Mark a queued message as failed; schedule retry with backoff."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT retry_count, max_retries FROM message_queue WHERE queue_id=?",
            (queue_id,))
        row = await cursor.fetchone()
        if not row:
            return

        retries = row["retry_count"] + 1
        if retries >= row["max_retries"]:
            await conn.execute(
                """UPDATE message_queue
                   SET status = 'failed', error = ?, retry_count = ?
                   WHERE queue_id = ?""",
                (error, retries, queue_id))
        else:
            # Exponential backoff: 1min, 2min, 4min, 8min, 16min
            delay_minutes = min(2 ** retries, 60)
            await conn.execute(
                """UPDATE message_queue
                   SET retry_count = ?, error = ?,
                       next_retry = datetime('now', '+' || ? || ' minutes')
                   WHERE queue_id = ?""",
                (retries, error, delay_minutes, queue_id))
        await conn.commit()


async def process_message_queue():
    """
    Background task: process pending messages in the queue.
    Called periodically by the reminder scheduler.
    """
    import biz_whatsapp as wa

    pending = await get_pending_messages(limit=20)
    if not pending:
        return 0

    sent_count = 0
    for msg in pending:
        try:
            if msg["channel"] == "whatsapp":
                result = await wa.send_text(msg["recipient"], msg["message"])
                if result.get("success"):
                    await mark_sent(msg["queue_id"])
                    sent_count += 1
                else:
                    error = str(result.get("error", "Unknown"))
                    await mark_failed(msg["queue_id"], error)
            else:
                # Unknown channel — mark failed
                await mark_failed(msg["queue_id"], f"Unknown channel: {msg['channel']}")
        except Exception as e:
            await mark_failed(msg["queue_id"], str(e))

    if sent_count:
        logger.info("📬 Queue: delivered %d/%d messages", sent_count, len(pending))
    return sent_count


# =============================================================================
#  BOT CONVERSATION RECOVERY — Keep bot on track after interruptions
# =============================================================================

# Stores the last known valid state for each user
_user_state_cache: dict = {}  # telegram_user_id → {command, step, timestamp}

def save_user_state(user_id: int, command: str, step: str, data: dict = None):
    """Save the user's current conversation state for recovery."""
    _user_state_cache[user_id] = {
        "command": command,
        "step": step,
        "data": data or {},
        "timestamp": time.time(),
    }


def get_user_state(user_id: int) -> Optional[dict]:
    """Get the user's last saved conversation state."""
    state = _user_state_cache.get(user_id)
    if state:
        # Expire states older than 30 minutes
        if time.time() - state["timestamp"] > 1800:
            del _user_state_cache[user_id]
            return None
    return state


def clear_user_state(user_id: int):
    """Clear the user's saved state (conversation completed)."""
    _user_state_cache.pop(user_id, None)


async def handle_bot_recovery(update, context) -> bool:
    """
    Check if the user was in the middle of something and offer to resume.
    Called from the catch-all handler when unrecognized input arrives.
    
    Returns True if recovery message was sent, False otherwise.
    """
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    if not state:
        return False

    command = state.get("command", "")
    step = state.get("step", "")
    age_secs = time.time() - state.get("timestamp", 0)

    # If state is very recent (< 60 seconds), user probably had a network glitch
    if age_secs < 60:
        from telegram import ParseMode
        await update.message.reply_text(
            f"🔄 <i>It looks like you were in the middle of <b>{command}</b>.</i>\n"
            f"Please continue from where you left off, or type /cancel to start fresh.",
            parse_mode=ParseMode.HTML)
        return True

    # Older state — offer to restart
    if age_secs < 1800:  # within 30 min
        from telegram import ParseMode
        await update.message.reply_text(
            f"🔄 <i>You were previously using <b>{command}</b> ({step}).</i>\n"
            f"Type /{command.lstrip('/')} to restart, or continue with something else.",
            parse_mode=ParseMode.HTML)
        clear_user_state(user_id)
        return True

    # Too old — just clear
    clear_user_state(user_id)
    return False


# =============================================================================
#  GRACEFUL DEGRADATION — Service status tracking
# =============================================================================

class ServiceHealth:
    """Track health of external services for graceful degradation."""

    def __init__(self):
        self._status: dict = {}  # service_name → {healthy, last_check, failures}

    def mark_healthy(self, service: str):
        self._status[service] = {
            "healthy": True,
            "last_check": time.time(),
            "failures": 0,
        }

    def mark_unhealthy(self, service: str, error: str = ""):
        current = self._status.get(service, {"failures": 0})
        self._status[service] = {
            "healthy": False,
            "last_check": time.time(),
            "failures": current.get("failures", 0) + 1,
            "last_error": error,
        }

    def is_healthy(self, service: str) -> bool:
        info = self._status.get(service)
        if not info:
            return True  # Assume healthy if never checked
        return info.get("healthy", True)

    def get_status(self) -> dict:
        """Get all service health statuses."""
        return {
            svc: {
                "healthy": info["healthy"],
                "failures": info.get("failures", 0),
                "last_check": datetime.fromtimestamp(
                    info["last_check"]).isoformat() if info.get("last_check") else None,
                "last_error": info.get("last_error", ""),
            }
            for svc, info in self._status.items()
        }


# Global service health tracker
service_health = ServiceHealth()


# =============================================================================
#  SMART SEND — Try API first, fallback to queue if network is down
# =============================================================================

async def smart_send_whatsapp(
    to: str, message: str,
    tenant_id: int = None, agent_id: int = None,
    metadata: dict = None,
) -> dict:
    """
    Intelligent WhatsApp sender with automatic fallback:
    1. Try Cloud API (with retry)
    2. If fails → queue for later delivery
    3. Return wa.me link for immediate user action
    """
    import biz_whatsapp as wa

    # Try sending directly with retries
    for attempt in range(2):
        try:
            if wa.is_configured():
                result = await asyncio.wait_for(
                    wa.send_text(to, message), timeout=15.0)
                if result.get("success"):
                    service_health.mark_healthy("whatsapp")
                    return result
                # API error — not a network issue, don't retry
                if "error" in result:
                    error_data = result.get("error", {})
                    if isinstance(error_data, dict) and error_data.get("error", {}).get("code") in (131047, 131048):
                        # Rate limited — queue it
                        break
            else:
                break  # Not configured — go to fallback
        except (asyncio.TimeoutError, ConnectionError, OSError) as e:
            service_health.mark_unhealthy("whatsapp", str(e))
            if attempt == 0:
                await asyncio.sleep(2)  # Quick retry
                continue
            break

    # Fallback: queue for later + return wa.me link for immediate action
    qid = await enqueue_message(
        channel="whatsapp", recipient=to, message=message,
        tenant_id=tenant_id, agent_id=agent_id, metadata=metadata)

    link = wa.generate_wa_link(to, message)
    return {
        "success": True,
        "method": "queued",
        "queue_id": qid,
        "wa_link": link,
        "message": "Message queued for delivery. Click the link to send manually.",
    }


# =============================================================================
#  TELEGRAM BOT RESILIENCE — Catch and recover from network errors
# =============================================================================

async def safe_reply(update, text: str, parse_mode: str = "HTML", **kwargs) -> bool:
    """
    Safely reply to a Telegram message with automatic retry.
    Returns True if sent, False if failed.
    """
    for attempt in range(3):
        try:
            await asyncio.wait_for(
                update.message.reply_text(text, parse_mode=parse_mode, **kwargs),
                timeout=10.0)
            return True
        except asyncio.TimeoutError:
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))
                continue
            logger.error("Failed to reply after 3 attempts (timeout)")
            return False
        except Exception as e:
            if "Timed out" in str(e) or "Network" in str(e):
                if attempt < 2:
                    await asyncio.sleep(1 * (attempt + 1))
                    continue
            logger.error("Reply failed: %s", e)
            return False
    return False


async def safe_edit(query, text: str, parse_mode: str = "HTML", **kwargs) -> bool:
    """Safely edit a callback query message with retry."""
    for attempt in range(3):
        try:
            await asyncio.wait_for(
                query.edit_message_text(text, parse_mode=parse_mode, **kwargs),
                timeout=10.0)
            return True
        except asyncio.TimeoutError:
            if attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))
                continue
            return False
        except Exception as e:
            if "Message is not modified" in str(e):
                return True  # Content identical — no actual error
            if "Timed out" in str(e) and attempt < 2:
                await asyncio.sleep(1 * (attempt + 1))
                continue
            logger.error("Edit failed: %s", e)
            return False
    return False


# =============================================================================
#  STARTUP
# =============================================================================

async def init_resilience():
    """Initialize resilience systems. Call at app startup."""
    await init_message_queue()
    logger.info("🛡️ Resilience engine initialized (message queue + retry + recovery)")


async def get_queue_stats() -> dict:
    """Get message queue statistics for admin monitoring."""
    async with aiosqlite.connect(DB_PATH) as conn:
        stats = {}
        for status in ('pending', 'sent', 'failed'):
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM message_queue WHERE status = ?", (status,))
            row = await cursor.fetchone()
            stats[status] = row[0] if row else 0
        # Total retries in-flight
        cursor = await conn.execute(
            "SELECT COUNT(*), SUM(retry_count) FROM message_queue WHERE status = 'pending'")
        row = await cursor.fetchone()
        stats['pending_retries'] = row[1] or 0
        # Oldest pending
        cursor = await conn.execute(
            "SELECT MIN(created_at) FROM message_queue WHERE status = 'pending'")
        row = await cursor.fetchone()
        stats['oldest_pending'] = row[0] if row and row[0] else None
    return stats


async def get_dead_letter_messages(limit: int = 50) -> list:
    """Get permanently failed messages (dead letters) for admin review."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT * FROM message_queue
               WHERE status = 'failed'
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,))
        return [dict(row) for row in await cursor.fetchall()]


async def retry_dead_letter(queue_id: int) -> bool:
    """Re-queue a failed message for another round of retries."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            "SELECT status FROM message_queue WHERE queue_id = ?", (queue_id,))
        row = await cursor.fetchone()
        if not row or row[0] != 'failed':
            return False
        await conn.execute(
            """UPDATE message_queue
               SET status = 'pending', retry_count = 0,
                   next_retry = datetime('now'), error = NULL
               WHERE queue_id = ?""",
            (queue_id,))
        await conn.commit()
    return True


async def purge_dead_letters(older_than_days: int = 30) -> int:
    """Delete old dead-letter messages. Returns count deleted."""
    async with aiosqlite.connect(DB_PATH) as conn:
        cursor = await conn.execute(
            """DELETE FROM message_queue
               WHERE status IN ('failed', 'sent')
                 AND created_at < datetime('now', '-' || ? || ' days')""",
            (older_than_days,))
        await conn.commit()
        return cursor.rowcount
