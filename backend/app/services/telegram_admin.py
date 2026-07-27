"""
Telegram Admin Notification Service.

Sends all important events to the admin Telegram account @kaliptoz.
Notifications include: new users, payments, errors, proxy stats, alerts.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

ADMIN_CHAT_ID = settings.telegram_admin_chat_id if hasattr(settings, "telegram_admin_chat_id") else ""
BOT_TOKEN = settings.telegram_bot_token if hasattr(settings, "telegram_bot_token") else ""


class TelegramAdminBot:
    """
    Sends real-time admin notifications to @kaliptoz via Telegram.

    Events:
    - New user registration
    - Payment received / subscription change
    - System errors / service down
    - Daily stats summary
    - Proxy count drops below threshold
    - API key created/deleted
    - High error rate alerts
    - Scraper/checker status changes
    """

    def __init__(self):
        self.bot_token = BOT_TOKEN
        self.admin_chat_id = ADMIN_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.enabled = bool(self.bot_token and self.admin_chat_id)

    async def send(self, text: str, parse_mode: str = "HTML"):
        """Send a message to the admin."""
        if not self.enabled:
            logger.debug(f"Telegram disabled. Would send: {text[:50]}...")
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.admin_chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True,
                    },
                )
                if r.status_code == 200:
                    return True
                logger.warning(f"Telegram send failed: {r.status_code} {r.text}")
                return False
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    # ─── Event Notifications ──────────────────────────────────────────────

    async def notify_new_user(self, username: str, email: str):
        await self.send(
            f"👤 <b>New User Registered</b>\n"
            f"Username: <code>{username}</code>\n"
            f"Email: <code>{email}</code>\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )

    async def notify_payment(self, username: str, plan: str, amount: str):
        await self.send(
            f"💰 <b>Payment Received</b>\n"
            f"User: <code>{username}</code>\n"
            f"Plan: <b>{plan.upper()}</b>\n"
            f"Amount: {amount}\n"
            f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )

    async def notify_subscription_cancelled(self, username: str, plan: str):
        await self.send(
            f"❌ <b>Subscription Cancelled</b>\n"
            f"User: <code>{username}</code>\n"
            f"Plan: {plan}"
        )

    async def notify_error(self, service: str, error: str):
        await self.send(
            f"🚨 <b>System Error</b>\n"
            f"Service: <code>{service}</code>\n"
            f"Error: <code>{error[:200]}</code>"
        )

    async def notify_service_status(self, service: str, status: str):
        icon = "✅" if status == "started" else "⛔"
        await self.send(f"{icon} <b>{service}</b> {status}")

    async def notify_daily_stats(self, stats: dict):
        await self.send(
            f"📊 <b>Daily Stats Summary</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Total Proxies: <b>{stats.get('total', 0):,}</b>\n"
            f"Alive: <b>{stats.get('alive', 0):,}</b>\n"
            f"Dead: <b>{stats.get('dead', 0):,}</b>\n"
            f"HTTP: {stats.get('http', 0):,}\n"
            f"SOCKS4: {stats.get('socks4', 0):,}\n"
            f"SOCKS5: {stats.get('socks5', 0):,}\n"
            f"Avg Latency: {stats.get('avg_latency', 0):.0f}ms\n"
            f"API Calls Today: {stats.get('api_calls', 0):,}\n"
            f"Total Users: {stats.get('users', 0)}\n"
            f"━━━━━━━━━━━━━━━━━━"
        )

    async def notify_proxy_alert(self, alive_count: int, threshold: int):
        await self.send(
            f"⚠️ <b>Proxy Count Alert</b>\n"
            f"Alive proxies dropped to <b>{alive_count}</b>\n"
            f"Threshold: {threshold}\n"
            f"Action needed!"
        )

    async def notify_high_error_rate(self, rate: float, endpoint: str):
        await self.send(
            f"🔥 <b>High Error Rate</b>\n"
            f"Rate: <b>{rate:.1f}%</b>\n"
            f"Endpoint: <code>{endpoint}</code>"
        )

    async def notify_api_key_created(self, username: str, key_name: str, tier: str):
        await self.send(
            f"🔑 <b>API Key Created</b>\n"
            f"User: <code>{username}</code>\n"
            f"Name: {key_name}\n"
            f"Tier: {tier}"
        )

    async def notify_scraper_result(self, count: int, sources: int):
        await self.send(
            f"🔄 <b>Scrape Complete</b>\n"
            f"Proxies: <b>{count:,}</b> from {sources} sources"
        )

    async def notify_cleanup(self, removed: dict):
        total = sum(removed.values())
        if total > 0:
            await self.send(
                f"🧹 <b>Cleanup Done</b>\n"
                f"Dead removed: {removed.get('dead_removed', 0)}\n"
                f"Old removed: {removed.get('old_removed', 0)}\n"
                f"Invalid removed: {removed.get('invalid_removed', 0)}"
            )

    async def notify_custom(self, title: str, message: str):
        await self.send(f"📢 <b>{title}</b>\n{message}")


# Singleton
admin_bot = TelegramAdminBot()
