"""
Platform services: Leaderboard, Map Data, Comparison, CAPTCHA,
Dedicated Pools, White-Label, Status Page, Blog/SEO,
Discord Bot, User Sources, Analytics Emails, Overage Alerts.
"""

import asyncio
import json
import logging
import secrets
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy import select, func, desc, update

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.models import Proxy, ProxySource
from app.models.user_models import User
from app.models.api_models import APIKey
from app.services.telegram_admin import admin_bot

logger = logging.getLogger(__name__)


# ─── Leaderboard ──────────────────────────────────────────────────────────────

class LeaderboardService:
    """Public proxy leaderboard showing top performers."""

    async def get_fastest(self, limit: int = 100) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Proxy)
                .where(Proxy.is_alive == True, Proxy.latency.isnot(None), Proxy.latency > 0)
                .order_by(Proxy.latency.asc())
                .limit(limit)
            )
            proxies = result.scalars().all()
        return [
            {"rank": i + 1, "ip": p.ip, "port": p.port, "type": p.proxy_type,
             "country": p.country_code, "latency_ms": round(p.latency, 1),
             "anonymity": p.anonymity_level, "uptime_checks": p.check_count, "fails": p.fail_count}
            for i, p in enumerate(proxies)
        ]

    async def get_most_reliable(self, limit: int = 100) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Proxy)
                .where(Proxy.is_alive == True, Proxy.check_count >= 5)
                .order_by(Proxy.fail_count.asc(), Proxy.latency.asc().nullslast())
                .limit(limit)
            )
            proxies = result.scalars().all()
        return [
            {"rank": i + 1, "ip": p.ip, "port": p.port, "type": p.proxy_type,
             "country": p.country_code, "latency_ms": round(p.latency, 1) if p.latency else None,
             "checks": p.check_count, "fails": p.fail_count,
             "reliability_pct": round((1 - p.fail_count / max(p.check_count, 1)) * 100, 1)}
            for i, p in enumerate(proxies)
        ]


# ─── Map Data ─────────────────────────────────────────────────────────────────

class MapDataService:
    """Provides data for 3D globe visualization."""

    async def get_proxy_locations(self) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(Proxy.country_code, Proxy.country, func.count(Proxy.id).label("count"))
                .where(Proxy.is_alive == True, Proxy.country_code.isnot(None))
                .group_by(Proxy.country_code, Proxy.country)
                .order_by(desc("count"))
            )
            return [{"country_code": r.country_code, "country": r.country, "count": r.count} for r in result.all()]


# ─── Comparison Tool ──────────────────────────────────────────────────────────

class ComparisonService:
    """Compare proxy quality metrics."""

    async def compare_types(self) -> dict:
        async with async_session() as session:
            types = ["http", "https", "socks4", "socks5"]
            comparison = {}
            for t in types:
                count = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == t, Proxy.is_alive == True)) or 0
                avg_lat = await session.scalar(select(func.avg(Proxy.latency)).where(Proxy.proxy_type == t, Proxy.is_alive == True, Proxy.latency.isnot(None))) or 0
                comparison[t] = {"count": count, "avg_latency_ms": round(avg_lat, 1)}
        return comparison

    async def compare_countries(self, limit: int = 20) -> list[dict]:
        async with async_session() as session:
            result = await session.execute(
                select(
                    Proxy.country_code, Proxy.country,
                    func.count(Proxy.id).label("count"),
                    func.avg(Proxy.latency).label("avg_latency"),
                )
                .where(Proxy.is_alive == True, Proxy.country_code.isnot(None))
                .group_by(Proxy.country_code, Proxy.country)
                .order_by(desc("count"))
                .limit(limit)
            )
            return [
                {"country_code": r.country_code, "country": r.country,
                 "count": r.count, "avg_latency_ms": round(r.avg_latency or 0, 1)}
                for r in result.all()
            ]


# ─── CAPTCHA Solving ──────────────────────────────────────────────────────────

class CaptchaService:
    """Integrates with 2Captcha/AntiCaptcha for CAPTCHA solving."""

    def __init__(self):
        from app.core.config import get_settings
        s = get_settings()
        self.api_key = getattr(s, "captcha_api_key", "")
        self.provider = getattr(s, "captcha_provider", "2captcha")

    async def solve_recaptcha(self, site_key: str, page_url: str) -> dict:
        if not self.api_key:
            return {"error": "CAPTCHA API key not configured"}

        if self.provider == "2captcha":
            return await self._solve_2captcha(site_key, page_url)
        return {"error": f"Unknown provider: {self.provider}"}

    async def _solve_2captcha(self, site_key: str, page_url: str) -> dict:
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                # Submit
                r = await client.post("http://2captcha.com/in.php", data={
                    "key": self.api_key, "method": "userrecaptcha",
                    "googlekey": site_key, "pageurl": page_url, "json": 1,
                })
                data = r.json()
                if data.get("status") != 1:
                    return {"error": data.get("request", "Submit failed")}

                task_id = data["request"]

                # Poll for result
                for _ in range(30):
                    await asyncio.sleep(5)
                    r = await client.get(f"http://2captcha.com/res.php?key={self.api_key}&action=get&id={task_id}&json=1")
                    result = r.json()
                    if result.get("status") == 1:
                        return {"success": True, "token": result["request"]}
                    if result.get("request") != "CAPCHA_NOT_READY":
                        return {"error": result.get("request", "Unknown error")}

                return {"error": "Timeout waiting for solution"}
        except Exception as e:
            return {"error": str(e)[:200]}


# ─── Dedicated Pools ──────────────────────────────────────────────────────────

class DedicatedPoolService:
    """Manages isolated proxy pools for enterprise users."""

    async def create_pool(self, user_id: int, name: str, proxy_type: str | None, country: str | None, size: int = 100) -> dict:
        pool_id = secrets.token_hex(8)
        async with async_session() as session:
            query = select(Proxy.id).where(Proxy.is_alive == True)
            if proxy_type:
                query = query.where(Proxy.proxy_type == proxy_type)
            if country:
                query = query.where(Proxy.country_code == country.upper())
            query = query.order_by(Proxy.fail_count.asc(), Proxy.latency.asc().nullslast()).limit(size)
            result = await session.execute(query)
            proxy_ids = [r[0] for r in result.all()]

        pool_data = json.dumps({"user_id": user_id, "name": name, "proxy_ids": proxy_ids, "type": proxy_type, "country": country})
        await redis_client.setex(f"pool:{pool_id}", 86400 * 30, pool_data)
        return {"pool_id": pool_id, "name": name, "size": len(proxy_ids)}

    async def get_pool(self, pool_id: str) -> dict | None:
        data = await redis_client.get(f"pool:{pool_id}")
        if not data:
            return None
        return json.loads(data)

    async def get_pool_proxies(self, pool_id: str) -> list[dict]:
        pool = await self.get_pool(pool_id)
        if not pool:
            return []
        async with async_session() as session:
            result = await session.execute(
                select(Proxy).where(Proxy.id.in_(pool["proxy_ids"]), Proxy.is_alive == True)
            )
            proxies = result.scalars().all()
        return [{"ip": p.ip, "port": p.port, "type": p.proxy_type, "country": p.country_code, "latency": p.latency} for p in proxies]


# ─── White-Label ──────────────────────────────────────────────────────────────

class WhiteLabelService:
    """White-label API for resellers."""

    async def create_whitelabel(self, user_id: int, domain: str, brand_name: str) -> dict:
        wl_id = secrets.token_hex(6)
        data = json.dumps({"user_id": user_id, "domain": domain, "brand_name": brand_name, "created_at": datetime.now(timezone.utc).isoformat()})
        await redis_client.setex(f"whitelabel:{wl_id}", 86400 * 365, data)
        return {"whitelabel_id": wl_id, "domain": domain, "brand_name": brand_name}

    async def get_whitelabel(self, wl_id: str) -> dict | None:
        data = await redis_client.get(f"whitelabel:{wl_id}")
        return json.loads(data) if data else None


# ─── Status Page ──────────────────────────────────────────────────────────────

class StatusPageService:
    """Public status page showing service health."""

    async def get_status(self) -> dict:
        services = {}

        # Backend API
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get("http://localhost:8000/health")
                services["api"] = {"status": "operational" if r.status_code == 200 else "degraded", "latency_ms": r.elapsed.total_seconds() * 1000}
        except Exception:
            services["api"] = {"status": "down", "latency_ms": None}

        # Database
        try:
            async with async_session() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
            services["database"] = {"status": "operational"}
        except Exception:
            services["database"] = {"status": "down"}

        # Redis
        try:
            await redis_client.ping()
            services["cache"] = {"status": "operational"}
        except Exception:
            services["cache"] = {"status": "down"}

        # Scraper
        from app.services.scraper import scraper_instance
        services["scraper"] = {"status": "operational" if scraper_instance.running else "stopped"}

        overall = "operational" if all(s.get("status") == "operational" for s in services.values()) else "degraded"
        return {"overall": overall, "services": services, "last_checked": datetime.now(timezone.utc).isoformat()}


# ─── Blog/SEO ─────────────────────────────────────────────────────────────────

class BlogService:
    """Auto-generated SEO blog posts based on proxy data."""

    async def generate_posts(self) -> list[dict]:
        async with async_session() as session:
            countries = await session.execute(
                select(Proxy.country, func.count(Proxy.id).label("c"))
                .where(Proxy.is_alive == True, Proxy.country.isnot(None))
                .group_by(Proxy.country).order_by(desc("c")).limit(10)
            )
            top_countries = countries.all()

        posts = [
            {"slug": "best-free-proxies-today", "title": "Best Free Proxies Today", "type": "dynamic",
             "description": "Updated list of the fastest free proxies available right now."},
            {"slug": "http-vs-socks5-proxies", "title": "HTTP vs SOCKS5 Proxies: Which to Use?", "type": "static",
             "description": "Complete comparison of HTTP and SOCKS5 proxy protocols."},
            {"slug": "elite-anonymous-proxies", "title": "Elite Anonymous Proxies", "type": "dynamic",
             "description": "High-anonymity proxies that hide your real IP completely."},
        ]
        for country in top_countries[:5]:
            name = country.country
            posts.append({
                "slug": f"best-proxies-{name.lower().replace(' ', '-')}",
                "title": f"Best Proxies in {name}",
                "type": "dynamic",
                "description": f"Top {country.c} working proxies located in {name}.",
            })
        return posts


# ─── Discord Community Bot ────────────────────────────────────────────────────

class DiscordBotService:
    """Discord bot commands for community proxy access."""

    async def handle_command(self, command: str, args: list[str], webhook_url: str) -> str:
        if command == "proxy":
            proxy_type = args[0] if args else "http"
            async with async_session() as session:
                result = await session.execute(
                    select(Proxy).where(Proxy.is_alive == True, Proxy.proxy_type == proxy_type)
                    .order_by(func.random()).limit(1)
                )
                proxy = result.scalar_one_or_none()
            if proxy:
                return f"`{proxy.ip}:{proxy.port}` ({proxy.proxy_type.upper()}, {proxy.latency:.0f}ms)" if proxy.latency else f"`{proxy.ip}:{proxy.port}` ({proxy.proxy_type.upper()})"
            return "No proxy available"

        elif command == "stats":
            async with async_session() as session:
                total = await session.scalar(select(func.count(Proxy.id))) or 0
                alive = await session.scalar(select(func.count(Proxy.id)).where(Proxy.is_alive == True)) or 0
            return f"Total: {total:,} | Alive: {alive:,} | Dead: {total - alive:,}"

        elif command == "fast":
            async with async_session() as session:
                result = await session.execute(
                    select(Proxy).where(Proxy.is_alive == True, Proxy.latency < 500, Proxy.latency.isnot(None))
                    .order_by(Proxy.latency.asc()).limit(5)
                )
                proxies = result.scalars().all()
            if proxies:
                lines = [f"`{p.ip}:{p.port}` - {p.latency:.0f}ms" for p in proxies]
                return "**Fastest proxies:**\n" + "\n".join(lines)
            return "No fast proxies available"

        return "Unknown command. Try: /proxy, /stats, /fast"


# ─── User-Submitted Sources ───────────────────────────────────────────────────

class UserSourceService:
    """Allow community members to submit proxy sources."""

    async def submit_source(self, user_id: int, url: str, proxy_type: str, description: str = "") -> dict:
        submission = json.dumps({
            "user_id": user_id, "url": url, "proxy_type": proxy_type,
            "description": description, "status": "pending",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        })
        sub_id = secrets.token_hex(8)
        await redis_client.setex(f"source_submission:{sub_id}", 86400 * 7, submission)
        await admin_bot.notify_custom("New Source Submission", f"URL: {url}\nType: {proxy_type}\nID: {sub_id}")
        return {"submission_id": sub_id, "status": "pending"}

    async def approve_source(self, sub_id: str) -> bool:
        data = await redis_client.get(f"source_submission:{sub_id}")
        if not data:
            return False
        sub = json.loads(data)
        async with async_session() as session:
            source = ProxySource(url=sub["url"], proxy_type=sub["proxy_type"], name=sub.get("description", "User submitted"))
            session.add(source)
            await session.commit()
        await redis_client.delete(f"source_submission:{sub_id}")
        return True

    async def list_pending(self) -> list[dict]:
        submissions = []
        async for key in redis_client.scan_iter("source_submission:*"):
            data = await redis_client.get(key)
            if data:
                sub = json.loads(data)
                sub["id"] = key.replace("source_submission:", "")
                submissions.append(sub)
        return submissions


# ─── Analytics Emails & Overage Alerts ────────────────────────────────────────

class AlertService:
    """Monitors usage and sends overage alerts."""

    async def check_overages(self):
        """Check all users for quota overages and alert them."""
        async with async_session() as session:
            result = await session.execute(
                select(APIKey).where(
                    APIKey.is_active == True,
                    APIKey.quota_daily > 0,
                    APIKey.requests_today >= APIKey.quota_daily * 0.8,
                )
            )
            keys = result.scalars().all()

        for key in keys:
            pct = round(key.requests_today / key.quota_daily * 100)
            alert_key = f"alert:overage:{key.id}:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            already_alerted = await redis_client.exists(alert_key)

            if not already_alerted:
                await redis_client.setex(alert_key, 86400, "1")
                # Notify via Telegram if configured
                if key.requests_today >= key.quota_daily:
                    await admin_bot.notify_custom(
                        "Overage Alert",
                        f"API Key: {key.name}\nUsage: {pct}% ({key.requests_today}/{key.quota_daily})"
                    )

    async def generate_weekly_summary(self, user_id: int) -> dict:
        """Generate weekly usage summary for a user."""
        async with async_session() as session:
            keys = await session.execute(
                select(APIKey).where(APIKey.user_id == str(user_id))
            )
            user_keys = keys.scalars().all()

        total_calls = sum(k.requests_total for k in user_keys)
        total_bandwidth = sum(k.bandwidth_bytes for k in user_keys)

        return {
            "user_id": user_id,
            "period": "weekly",
            "total_api_calls": total_calls,
            "total_bandwidth_bytes": total_bandwidth,
            "active_keys": len([k for k in user_keys if k.is_active]),
        }


# Singletons
leaderboard_service = LeaderboardService()
map_service = MapDataService()
comparison_service = ComparisonService()
captcha_service = CaptchaService()
pool_service = DedicatedPoolService()
whitelabel_service = WhiteLabelService()
status_service = StatusPageService()
blog_service = BlogService()
discord_bot = DiscordBotService()
user_source_service = UserSourceService()
alert_service = AlertService()
