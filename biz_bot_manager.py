# =============================================================================
#  biz_bot_manager.py — Sarathi-AI: Per-Tenant Telegram Bot Manager
# =============================================================================
#
#  Manages multiple Telegram bot instances — one per tenant.
#  Each tenant creates their own bot via @BotFather and configures
#  the token during onboarding. Sarathi-AI spins up a full CRM bot
#  instance for each tenant.
#
#  The master bot (@SarathiBizBot / Sarathi-AI.com) is kept for:
#    - Admin/support communications
#    - Sending trial/subscription alerts
#    - Fallback if a tenant bot is not yet configured
#
# =============================================================================

import asyncio
import hashlib
import logging
import os
from typing import Dict, Optional, Callable

import httpx
from telegram import Update
from telegram.ext import Application

import biz_database as db
import biz_bot as bot

logger = logging.getLogger("sarathi.botmgr")


class BotManager:
    """Manages per-tenant Telegram bot instances."""

    def __init__(self):
        # tenant_id → running Application instance
        self._bots: Dict[int, Application] = {}
        # tenant_id → bot token (for tracking changes)
        self._tokens: Dict[int, str] = {}
        # Master bot instance (Sarathi-AI.com)
        self._master_bot: Optional[Application] = None
        self._master_token: str = ""
        # Webhook mode
        self._webhook_base: str = ""
        # token_hash → Application (for routing webhook updates)
        self._webhook_map: Dict[str, Application] = {}
        # Lock for safe concurrent operations
        self._lock = asyncio.Lock()

    # ─────────────────────────────────────────────────────────
    #  MASTER BOT (Sarathi-AI.com — admin & alerts)
    # ─────────────────────────────────────────────────────────

    async def start_master_bot(self, token: str, webhook_base_url: str = "") -> Application:
        """Start the master Sarathi-AI admin bot."""
        self._master_token = token
        self._webhook_base = webhook_base_url
        self._master_bot = bot.build_bot(token, tenant_id=None, is_master=True)
        await self._master_bot.initialize()
        await self._master_bot.start()

        if webhook_base_url:
            # Webhook mode — register with Telegram
            secret = self._webhook_secret(token)
            wh_url = f"{webhook_base_url}/api/telegram/webhook/{self._token_hash(token)}"
            await self._set_telegram_webhook(token, wh_url, secret)
            self._webhook_map[self._token_hash(token)] = self._master_bot
            logger.info("✅ Master bot started (webhook mode)")
        else:
            # Polling mode (local dev)
            await self._master_bot.updater.start_polling(
                allowed_updates=["message", "callback_query"],
                drop_pending_updates=True,
            )
            logger.info("✅ Master bot started (polling mode)")
        return self._master_bot

    async def stop_master_bot(self):
        """Stop the master bot."""
        if self._master_bot:
            try:
                if self._webhook_base:
                    await self._delete_telegram_webhook(self._master_token)
                else:
                    await self._master_bot.updater.stop()
                await self._master_bot.stop()
                await self._master_bot.shutdown()
                logger.info("🛑 Master bot stopped")
            except Exception as e:
                logger.error("Error stopping master bot: %s", e)
            self._master_bot = None

    @property
    def master_bot(self) -> Optional[Application]:
        return self._master_bot

    # ─────────────────────────────────────────────────────────
    #  PER-TENANT BOT LIFECYCLE
    # ─────────────────────────────────────────────────────────

    async def start_tenant_bot(self, tenant_id: int, token: str) -> bool:
        """Start a bot for a specific tenant. Returns True on success."""
        async with self._lock:
            # Already running with same token?
            if tenant_id in self._bots and self._tokens.get(tenant_id) == token:
                logger.debug("Bot for tenant %d already running", tenant_id)
                return True

            # Stop existing if token changed
            if tenant_id in self._bots:
                await self._stop_bot_unsafe(tenant_id)

            try:
                app = bot.build_bot(token, tenant_id=tenant_id, is_master=False)
                await app.initialize()
                await app.start()

                if self._webhook_base:
                    # Webhook mode
                    secret = self._webhook_secret(token)
                    wh_url = f"{self._webhook_base}/api/telegram/webhook/{self._token_hash(token)}"
                    await self._set_telegram_webhook(token, wh_url, secret)
                    self._webhook_map[self._token_hash(token)] = app
                else:
                    # Polling mode (local dev)
                    await app.updater.start_polling(
                        allowed_updates=["message", "callback_query"],
                        drop_pending_updates=True,
                    )

                self._bots[tenant_id] = app
                self._tokens[tenant_id] = token
                logger.info("✅ Tenant %d bot started (token: ...%s, mode: %s)",
                            tenant_id, token[-6:],
                            "webhook" if self._webhook_base else "polling")
                return True
            except Exception as e:
                logger.error("❌ Failed to start bot for tenant %d: %s",
                             tenant_id, e, exc_info=True)
                return False

    async def stop_tenant_bot(self, tenant_id: int):
        """Stop a tenant's bot instance."""
        async with self._lock:
            await self._stop_bot_unsafe(tenant_id)

    async def _stop_bot_unsafe(self, tenant_id: int):
        """Internal stop — must be called under lock."""
        app = self._bots.pop(tenant_id, None)
        token = self._tokens.pop(tenant_id, None)
        if app:
            try:
                if self._webhook_base and token:
                    await self._delete_telegram_webhook(token)
                    # Remove from webhook map
                    thash = self._token_hash(token)
                    self._webhook_map.pop(thash, None)
                else:
                    await app.updater.stop()
                await app.stop()
                await app.shutdown()
                logger.info("🛑 Tenant %d bot stopped", tenant_id)
            except Exception as e:
                logger.error("Error stopping tenant %d bot: %s", tenant_id, e)

    async def restart_tenant_bot(self, tenant_id: int, token: str) -> bool:
        """Stop and restart a tenant's bot (e.g., after token change)."""
        await self.stop_tenant_bot(tenant_id)
        return await self.start_tenant_bot(tenant_id, token)

    # ─────────────────────────────────────────────────────────
    #  BULK OPERATIONS
    # ─────────────────────────────────────────────────────────

    async def start_all_tenant_bots(self) -> int:
        """On startup, load and start bots for all active tenants with tokens.
        Returns the number of successfully started bots."""
        import aiosqlite
        started = 0
        try:
            async with aiosqlite.connect(db.DB_PATH) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(
                    "SELECT tenant_id, tg_bot_token, firm_name "
                    "FROM tenants "
                    "WHERE tg_bot_token IS NOT NULL "
                    "AND tg_bot_token != '' "
                    "AND is_active = 1"
                )
                tenants = [dict(row) for row in await cursor.fetchall()]

            if not tenants:
                logger.info("📭 No tenant bots to start (no tokens configured)")
                return 0

            logger.info("🚀 Starting %d tenant bot(s)...", len(tenants))
            for t in tenants:
                success = await self.start_tenant_bot(
                    t['tenant_id'], t['tg_bot_token'])
                if success:
                    started += 1
                else:
                    logger.warning("⚠️ Skipped tenant %d (%s) — bot start failed",
                                   t['tenant_id'], t.get('firm_name', '?'))
                # Small delay to avoid Telegram rate limits
                await asyncio.sleep(0.5)

            logger.info("✅ %d/%d tenant bots started successfully",
                         started, len(tenants))
        except Exception as e:
            logger.error("Error starting tenant bots: %s", e, exc_info=True)
        return started

    async def stop_all(self):
        """Stop all tenant bots and the master bot. Called on shutdown."""
        logger.info("🛑 Stopping all bots...")
        async with self._lock:
            for tenant_id in list(self._bots.keys()):
                await self._stop_bot_unsafe(tenant_id)
        await self.stop_master_bot()
        logger.info("✅ All bots stopped")

    # ─────────────────────────────────────────────────────────
    #  TELEGRAM ALERT CALLBACK (for reminders)
    # ─────────────────────────────────────────────────────────

    async def send_alert(self, telegram_id: str, message: str,
                         tenant_id: int = None, reply_markup=None):
        """
        Send a Telegram alert to a user. Tries tenant bot first,
        falls back to master bot.
        """
        target_bot = None

        # Try tenant bot first
        if tenant_id and tenant_id in self._bots:
            target_bot = self._bots[tenant_id]

        # Fallback to master bot
        if not target_bot and self._master_bot:
            target_bot = self._master_bot

        if not target_bot:
            logger.warning("No bot available to send alert to %s", telegram_id)
            return

        try:
            await target_bot.bot.send_message(
                chat_id=int(telegram_id),
                text=message,
                parse_mode="MarkdownV2",
                reply_markup=reply_markup,
            )
        except Exception as e:
            # If tenant bot fails, try master as fallback
            if target_bot != self._master_bot and self._master_bot:
                try:
                    await self._master_bot.bot.send_message(
                        chat_id=int(telegram_id),
                        text=message,
                        parse_mode="MarkdownV2",
                        reply_markup=reply_markup,
                    )
                except Exception as e2:
                    logger.error("Alert failed (both bots) to %s: %s / %s",
                                 telegram_id, e, e2)
            else:
                logger.error("Alert to %s failed: %s", telegram_id, e)

    # ─────────────────────────────────────────────────────────
    #  WEBHOOK HELPERS
    # ─────────────────────────────────────────────────────────

    @staticmethod
    def _token_hash(token: str) -> str:
        """Create a safe URL-friendly hash from a bot token."""
        return hashlib.sha256(token.encode()).hexdigest()[:32]

    @staticmethod
    def _webhook_secret(token: str) -> str:
        """Generate webhook secret_token for Telegram verification."""
        return hashlib.sha256(f"sarathi-wh-{token}".encode()).hexdigest()[:48]

    async def _set_telegram_webhook(self, token: str, url: str, secret: str):
        """Register webhook URL with Telegram API."""
        api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        async with httpx.AsyncClient() as client:
            resp = await client.post(api_url, json={
                "url": url,
                "secret_token": secret,
                "allowed_updates": ["message", "callback_query"],
                "drop_pending_updates": True,
                "max_connections": 40,
            })
            data = resp.json()
            if data.get("ok"):
                logger.info("🔗 Webhook set: %s", url)
            else:
                logger.error("❌ Webhook failed: %s", data)

    async def _delete_telegram_webhook(self, token: str):
        """Remove webhook from Telegram API."""
        api_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        try:
            async with httpx.AsyncClient() as client:
                await client.post(api_url)
        except Exception as e:
            logger.warning("Failed to delete webhook: %s", e)

    async def process_webhook_update(self, token_hash: str, data: dict,
                                      secret_token: str = "") -> bool:
        """Route an incoming Telegram webhook update to the correct bot.
        Returns True if processed, False if not found."""
        app = self._webhook_map.get(token_hash)
        if not app:
            logger.warning("No bot for webhook token hash: %s...", token_hash[:8])
            return False

        # Verify secret_token if webhook mode
        # Find the actual token for this app to verify
        expected_secret = None
        if token_hash == self._token_hash(self._master_token):
            expected_secret = self._webhook_secret(self._master_token)
        else:
            for tid, tok in self._tokens.items():
                if self._token_hash(tok) == token_hash:
                    expected_secret = self._webhook_secret(tok)
                    break

        if expected_secret and secret_token != expected_secret:
            logger.warning("Invalid webhook secret for hash %s...", token_hash[:8])
            return False

        try:
            update = Update.de_json(data, app.bot)
            await app.process_update(update)
            return True
        except Exception as e:
            logger.error("Webhook update processing error: %s", e, exc_info=True)
            return False

    # ─────────────────────────────────────────────────────────
    #  STATUS
    # ─────────────────────────────────────────────────────────

    @property
    def running_count(self) -> int:
        return len(self._bots)

    def is_running(self, tenant_id: int) -> bool:
        return tenant_id in self._bots

    def get_running_tenants(self) -> list:
        return list(self._bots.keys())

    def get_bot_username(self, tenant_id: int) -> Optional[str]:
        """Get the @username of a tenant's bot."""
        app = self._bots.get(tenant_id)
        if app and app.bot:
            return app.bot.username
        return None


# Global singleton
bot_manager = BotManager()
