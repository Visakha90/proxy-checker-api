"""
Webhook Notifications, Scheduled Exports, Custom Check Targets,
Telegram Bot, and Discord Bot services.
"""

import asyncio
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update

from app.core.database import async_session
from app.core.config import get_settings
from app.models.models import Proxy
from app.models.user_models import Webhook, ScheduledExport, User

logger = logging.getLogger(__name__)
settings = get_settings()


class WebhookService:
    """Sends webhook notifications to user-defined URLs."""

    async def trigger(self, webhook: Webhook, payload: dict):
        """Send a webhook notification."""
        headers = {"Content-Type": "application/json", "X-Webhook-Event": webhook.event_type}

        if webhook.secret:
            body = json.dumps(payload, default=str)
            sig = hmac.new(webhook.secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={sig}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(webhook.url, json=payload, headers=headers)
                logger.info(f"Webhook {webhook.id} triggered: {r.status_code}")

            async with async_session() as session:
                await session.execute(
                    update(Webhook)
                    .where(Webhook.id == webhook.id)
                    .values(
                        last_triggered_at=datetime.now(timezone.utc),
                        trigger_count=Webhook.trigger_count + 1,
                    )
                )
                await session.commit()
        except Exception as e:
            logger.error(f"Webhook {webhook.id} failed: {e}")

    async def trigger_event(self, event_type: str, payload: dict):
        """Trigger all active webhooks for a given event type."""
        async with async_session() as session:
            result = await session.execute(
                select(Webhook).where(Webhook.event_type == event_type, Webhook.is_active == True)
            )
            webhooks = result.scalars().all()

        for wh in webhooks:
            asyncio.create_task(self.trigger(wh, payload))

    async def create_webhook(self, user_id: int, name: str, url: str, event_type: str, secret: str | None = None) -> Webhook:
        """Create a new webhook."""
        import secrets as sec
        async with async_session() as session:
            wh = Webhook(
                user_id=user_id,
                name=name,
                url=url,
                event_type=event_type,
                secret=secret or sec.token_hex(16),
            )
            session.add(wh)
            await session.commit()
            await session.refresh(wh)
            return wh

    async def list_webhooks(self, user_id: int) -> list[Webhook]:
        """List user's webhooks."""
        async with async_session() as session:
            result = await session.execute(
                select(Webhook).where(Webhook.user_id == user_id).order_by(Webhook.created_at.desc())
            )
            return result.scalars().all()

    async def delete_webhook(self, webhook_id: int, user_id: int) -> bool:
        """Delete a webhook."""
        async with async_session() as session:
            wh = await session.get(Webhook, webhook_id)
            if not wh or wh.user_id != user_id:
                return False
            await session.delete(wh)
            await session.commit()
            return True


class TelegramService:
    """Send notifications via Telegram Bot API."""

    def __init__(self):
        self.bot_token = settings.telegram_bot_token if hasattr(settings, "telegram_bot_token") else ""
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"

    async def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML"):
        """Send a message to a Telegram chat."""
        if not self.bot_token:
            logger.warning("Telegram bot token not configured")
            return False

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(
                    f"{self.api_url}/sendMessage",
                    json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
                )
                return r.status_code == 200
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False

    async def notify_users(self, event: str, message: str):
        """Send notification to all users with Telegram enabled."""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(
                    User.notification_enabled == True,
                    User.telegram_chat_id.isnot(None),
                )
            )
            users = result.scalars().all()

        for user in users:
            await self.send_message(user.telegram_chat_id, message)


class DiscordService:
    """Send notifications via Discord webhooks."""

    async def send_embed(self, webhook_url: str, title: str, description: str, color: int = 0x10b981):
        """Send a Discord embed message."""
        if not webhook_url:
            return False

        payload = {
            "embeds": [{
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "ProxyChecker"},
            }]
        }

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(webhook_url, json=payload)
                return r.status_code in (200, 204)
        except Exception as e:
            logger.error(f"Discord send failed: {e}")
            return False

    async def notify_users(self, event: str, title: str, description: str):
        """Send notification to all users with Discord enabled."""
        async with async_session() as session:
            result = await session.execute(
                select(User).where(
                    User.notification_enabled == True,
                    User.discord_webhook_url.isnot(None),
                )
            )
            users = result.scalars().all()

        for user in users:
            await self.send_embed(user.discord_webhook_url, title, description)


class ScheduledExportService:
    """Manages and executes scheduled proxy exports."""

    async def create_export(
        self, user_id: int, name: str, schedule: str, proxy_type: str | None,
        format: str, delivery_method: str, delivery_target: str, filters: dict | None = None,
    ) -> ScheduledExport:
        """Create a scheduled export."""
        async with async_session() as session:
            export = ScheduledExport(
                user_id=user_id,
                name=name,
                schedule=schedule,
                proxy_type=proxy_type,
                format=format,
                filters=json.dumps(filters) if filters else None,
                delivery_method=delivery_method,
                delivery_target=delivery_target,
            )
            session.add(export)
            await session.commit()
            await session.refresh(export)
            return export

    async def execute_export(self, export: ScheduledExport):
        """Execute a scheduled export and deliver results."""
        async with async_session() as session:
            query = select(Proxy).where(Proxy.is_alive == True)
            if export.proxy_type:
                query = query.where(Proxy.proxy_type == export.proxy_type)

            if export.filters:
                filters = json.loads(export.filters)
                if filters.get("country"):
                    query = query.where(Proxy.country_code == filters["country"])
                if filters.get("anonymity"):
                    query = query.where(Proxy.anonymity_level == filters["anonymity"])

            query = query.order_by(Proxy.latency.asc().nullslast()).limit(5000)
            result = await session.execute(query)
            proxies = result.scalars().all()

        # Format output
        if export.format == "json":
            content = json.dumps([{"ip": p.ip, "port": p.port, "type": p.proxy_type} for p in proxies])
        elif export.format == "csv":
            content = "ip,port,type,country,latency\n" + "\n".join(
                f"{p.ip},{p.port},{p.proxy_type},{p.country_code or ''},{p.latency or ''}" for p in proxies
            )
        else:
            content = "\n".join(f"{p.ip}:{p.port}" for p in proxies)

        # Deliver
        if export.delivery_method == "webhook":
            async with httpx.AsyncClient(timeout=15) as client:
                await client.post(export.delivery_target, content=content.encode(),
                                  headers={"Content-Type": "text/plain"})
        elif export.delivery_method == "telegram":
            telegram = TelegramService()
            # Truncate for Telegram (4096 char limit)
            msg = f"📦 Scheduled Export: {export.name}\n{len(proxies)} proxies\n\n{content[:3000]}"
            await telegram.send_message(export.delivery_target, msg)

        # Update last_run
        async with async_session() as session:
            await session.execute(
                update(ScheduledExport)
                .where(ScheduledExport.id == export.id)
                .values(last_run_at=datetime.now(timezone.utc))
            )
            await session.commit()

        logger.info(f"Export '{export.name}' delivered: {len(proxies)} proxies")

    async def list_exports(self, user_id: int) -> list[ScheduledExport]:
        """List user's scheduled exports."""
        async with async_session() as session:
            result = await session.execute(
                select(ScheduledExport).where(ScheduledExport.user_id == user_id)
            )
            return result.scalars().all()

    async def run_due_exports(self):
        """Run all exports that are due (called by scheduler)."""
        async with async_session() as session:
            result = await session.execute(
                select(ScheduledExport).where(ScheduledExport.is_active == True)
            )
            exports = result.scalars().all()

        now = datetime.now(timezone.utc)
        for export in exports:
            should_run = False
            if not export.last_run_at:
                should_run = True
            else:
                elapsed = (now - export.last_run_at.replace(tzinfo=timezone.utc)).total_seconds()
                if export.schedule == "hourly" and elapsed >= 3600:
                    should_run = True
                elif export.schedule == "daily" and elapsed >= 86400:
                    should_run = True
                elif export.schedule == "weekly" and elapsed >= 604800:
                    should_run = True

            if should_run:
                try:
                    await self.execute_export(export)
                except Exception as e:
                    logger.error(f"Export {export.id} failed: {e}")


webhook_service = WebhookService()
telegram_service = TelegramService()
discord_service = DiscordService()
export_service = ScheduledExportService()
