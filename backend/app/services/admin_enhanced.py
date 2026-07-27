"""
Enhanced Admin Service.

Provides advanced admin capabilities:
- System overview with resource usage
- User management (ban, unban, change plan, impersonate)
- Bulk operations (mass delete proxies, reset stats)
- Export system data
- Scheduled tasks control
- IP ban list
- Announcement system
- Maintenance mode
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update, delete, func

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.models import Proxy, ProxySource, CheckHistory, Statistics
from app.models.api_models import APIKey, APIRequestLog
from app.models.user_models import User, Webhook, ScheduledExport
from app.services.telegram_admin import admin_bot

logger = logging.getLogger(__name__)


class EnhancedAdminService:
    """Advanced admin operations with Telegram notifications."""

    # ─── System Overview ──────────────────────────────────────────────────

    async def get_system_overview(self) -> dict:
        """Full system status for admin dashboard."""
        async with async_session() as session:
            total_proxies = await session.scalar(select(func.count(Proxy.id))) or 0
            alive_proxies = await session.scalar(select(func.count(Proxy.id)).where(Proxy.is_alive == True)) or 0
            total_users = await session.scalar(select(func.count(User.id))) or 0
            premium_users = await session.scalar(select(func.count(User.id)).where(User.plan != "free")) or 0
            total_api_keys = await session.scalar(select(func.count(APIKey.id))) or 0
            total_sources = await session.scalar(select(func.count(ProxySource.id))) or 0
            enabled_sources = await session.scalar(select(func.count(ProxySource.id)).where(ProxySource.enabled == True)) or 0
            total_requests = await session.scalar(select(func.count(APIRequestLog.id))) or 0
            total_webhooks = await session.scalar(select(func.count(Webhook.id))) or 0

        # Redis stats
        try:
            redis_info = await redis_client.info("memory")
            redis_memory = redis_info.get("used_memory_human", "N/A")
        except Exception:
            redis_memory = "N/A"

        # Maintenance mode
        maintenance = await redis_client.get("system:maintenance") == "1"

        return {
            "proxies": {"total": total_proxies, "alive": alive_proxies, "dead": total_proxies - alive_proxies},
            "users": {"total": total_users, "premium": premium_users, "free": total_users - premium_users},
            "api": {"total_keys": total_api_keys, "total_requests": total_requests, "webhooks": total_webhooks},
            "sources": {"total": total_sources, "enabled": enabled_sources},
            "infrastructure": {"redis_memory": redis_memory, "maintenance_mode": maintenance},
        }

    # ─── User Management ──────────────────────────────────────────────────

    async def list_users(self, limit: int = 100, offset: int = 0) -> tuple[list, int]:
        """List all users with stats."""
        async with async_session() as session:
            total = await session.scalar(select(func.count(User.id))) or 0
            result = await session.execute(
                select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
            )
            users = result.scalars().all()

        return [
            {
                "id": u.id, "email": u.email, "username": u.username,
                "role": u.role, "plan": u.plan, "is_active": u.is_active,
                "api_calls_today": u.api_calls_today, "api_calls_total": u.api_calls_total,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ], total

    async def ban_user(self, user_id: int, reason: str = "") -> bool:
        """Ban a user (deactivate account + all API keys)."""
        async with async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
            user.is_active = False
            # Deactivate all their keys
            await session.execute(
                update(APIKey).where(APIKey.user_id == str(user_id)).values(is_active=False)
            )
            await session.commit()

        await admin_bot.notify_custom("User Banned", f"User: {user.username}\nReason: {reason or 'No reason'}")
        return True

    async def unban_user(self, user_id: int) -> bool:
        """Unban a user."""
        async with async_session() as session:
            result = await session.execute(
                update(User).where(User.id == user_id).values(is_active=True)
            )
            await session.commit()
            return result.rowcount > 0

    async def change_user_plan(self, user_id: int, plan: str) -> bool:
        """Change a user's plan (admin override)."""
        async with async_session() as session:
            user = await session.get(User, user_id)
            if not user:
                return False
            old_plan = user.plan
            user.plan = plan
            user.role = "premium" if plan in ("pro", "enterprise") else "user"
            await session.commit()

        await admin_bot.notify_custom(
            "Plan Changed (Admin)",
            f"User: {user.username}\nOld: {old_plan} → New: {plan}"
        )
        return True

    # ─── Bulk Operations ──────────────────────────────────────────────────

    async def purge_dead_proxies(self) -> int:
        """Delete all dead proxies."""
        async with async_session() as session:
            result = await session.execute(
                delete(Proxy).where(Proxy.is_alive == False)
            )
            await session.commit()
            count = result.rowcount

        await admin_bot.notify_custom("Bulk Delete", f"Purged {count} dead proxies")
        return count

    async def reset_all_stats(self) -> bool:
        """Reset all statistics records."""
        async with async_session() as session:
            await session.execute(delete(Statistics))
            await session.execute(delete(CheckHistory))
            await session.commit()

        await admin_bot.notify_custom("Stats Reset", "All statistics and check history cleared")
        return True

    async def purge_old_logs(self, days: int = 7) -> int:
        """Delete API request logs older than N days."""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with async_session() as session:
            result = await session.execute(
                delete(APIRequestLog).where(APIRequestLog.created_at < cutoff)
            )
            await session.commit()
            return result.rowcount

    # ─── IP Ban List ──────────────────────────────────────────────────────

    async def ban_ip(self, ip: str, reason: str = "", duration_hours: int = 24):
        """Ban an IP address from accessing the API."""
        await redis_client.setex(f"banned_ip:{ip}", duration_hours * 3600, reason or "banned")
        await admin_bot.notify_custom("IP Banned", f"IP: {ip}\nDuration: {duration_hours}h\nReason: {reason}")

    async def unban_ip(self, ip: str):
        """Unban an IP address."""
        await redis_client.delete(f"banned_ip:{ip}")

    async def is_ip_banned(self, ip: str) -> bool:
        """Check if an IP is banned."""
        return await redis_client.exists(f"banned_ip:{ip}") > 0

    async def list_banned_ips(self) -> list[dict]:
        """List all banned IPs."""
        keys = []
        async for key in redis_client.scan_iter("banned_ip:*"):
            ip = key.replace("banned_ip:", "")
            reason = await redis_client.get(key) or ""
            ttl = await redis_client.ttl(key)
            keys.append({"ip": ip, "reason": reason, "expires_in_seconds": ttl})
        return keys

    # ─── Announcements ────────────────────────────────────────────────────

    async def set_announcement(self, message: str, type: str = "info"):
        """Set a system-wide announcement (shown to all users)."""
        data = json.dumps({"message": message, "type": type, "created_at": datetime.now(timezone.utc).isoformat()})
        await redis_client.set("system:announcement", data)
        await admin_bot.notify_custom("Announcement Set", message)

    async def clear_announcement(self):
        """Clear the system announcement."""
        await redis_client.delete("system:announcement")

    async def get_announcement(self) -> dict | None:
        """Get current announcement."""
        data = await redis_client.get("system:announcement")
        if data:
            return json.loads(data)
        return None

    # ─── Maintenance Mode ─────────────────────────────────────────────────

    async def enable_maintenance(self, message: str = "System maintenance in progress"):
        """Enable maintenance mode."""
        await redis_client.set("system:maintenance", "1")
        await redis_client.set("system:maintenance_msg", message)
        await admin_bot.notify_service_status("Maintenance Mode", "ENABLED")

    async def disable_maintenance(self):
        """Disable maintenance mode."""
        await redis_client.delete("system:maintenance")
        await redis_client.delete("system:maintenance_msg")
        await admin_bot.notify_service_status("Maintenance Mode", "DISABLED")

    async def is_maintenance(self) -> tuple[bool, str]:
        """Check if maintenance mode is active."""
        active = await redis_client.get("system:maintenance") == "1"
        msg = await redis_client.get("system:maintenance_msg") or "Maintenance"
        return active, msg

    # ─── Daily Report ─────────────────────────────────────────────────────

    async def send_daily_report(self):
        """Send daily stats report to admin via Telegram."""
        async with async_session() as session:
            total = await session.scalar(select(func.count(Proxy.id))) or 0
            alive = await session.scalar(select(func.count(Proxy.id)).where(Proxy.is_alive == True)) or 0
            http_c = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "http", Proxy.is_alive == True)) or 0
            socks4_c = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks4", Proxy.is_alive == True)) or 0
            socks5_c = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks5", Proxy.is_alive == True)) or 0
            avg_lat = await session.scalar(select(func.avg(Proxy.latency)).where(Proxy.is_alive == True, Proxy.latency.isnot(None))) or 0
            users = await session.scalar(select(func.count(User.id))) or 0
            api_calls = await session.scalar(select(func.count(APIRequestLog.id))) or 0

        await admin_bot.notify_daily_stats({
            "total": total, "alive": alive, "dead": total - alive,
            "http": http_c, "socks4": socks4_c, "socks5": socks5_c,
            "avg_latency": avg_lat, "users": users, "api_calls": api_calls,
        })


enhanced_admin = EnhancedAdminService()
