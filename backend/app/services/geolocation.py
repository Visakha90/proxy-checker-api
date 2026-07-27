"""
Geolocation, Speed Tiers, and IP Reputation Scoring.

- GeoIP lookup using ip-api.com (free, no key needed, 45 req/min)
- Speed tier classification (fast/medium/slow)
- IP reputation scoring based on uptime, block rate, and consistency
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update, func

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.models import Proxy

logger = logging.getLogger(__name__)

GEOIP_API = "http://ip-api.com/batch"
GEOIP_SINGLE = "http://ip-api.com/json"

SPEED_TIERS = {
    "fast": (0, 500),
    "medium": (500, 2000),
    "slow": (2000, float("inf")),
}


class GeoLocationService:
    """Resolves proxy IP addresses to country, city, ISP using ip-api.com."""

    async def lookup_single(self, ip: str) -> dict | None:
        """Look up geolocation for a single IP."""
        cache_key = f"geo:{ip}"
        cached = await redis_client.get(cache_key)
        if cached:
            import json
            return json.loads(cached)

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(f"{GEOIP_SINGLE}/{ip}?fields=status,country,countryCode,city,isp,org")
                if r.status_code == 200:
                    data = r.json()
                    if data.get("status") == "success":
                        result = {
                            "country": data.get("country"),
                            "country_code": data.get("countryCode"),
                            "city": data.get("city"),
                            "isp": data.get("isp"),
                            "org": data.get("org"),
                        }
                        import json
                        await redis_client.setex(cache_key, 86400, json.dumps(result))
                        return result
        except Exception as e:
            logger.debug(f"GeoIP lookup failed for {ip}: {e}")
        return None

    async def lookup_batch(self, ips: list[str]) -> list[dict]:
        """Look up geolocation for a batch of IPs (max 100 per request)."""
        results = []
        for i in range(0, len(ips), 100):
            batch = ips[i:i + 100]
            try:
                payload = [{"query": ip, "fields": "status,country,countryCode,city,isp,query"} for ip in batch]
                async with httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(GEOIP_API, json=payload)
                    if r.status_code == 200:
                        data = r.json()
                        for item in data:
                            if item.get("status") == "success":
                                results.append({
                                    "ip": item.get("query"),
                                    "country": item.get("country"),
                                    "country_code": item.get("countryCode"),
                                    "city": item.get("city"),
                                    "isp": item.get("isp"),
                                })
                            else:
                                results.append({"ip": item.get("query"), "country": None})
            except Exception as e:
                logger.error(f"Batch GeoIP error: {e}")

            # Rate limit: 45 requests per minute for batch
            if i + 100 < len(ips):
                await asyncio.sleep(1.5)

        return results

    async def enrich_proxies(self, limit: int = 200):
        """Enrich proxies that don't have geolocation data."""
        async with async_session() as session:
            result = await session.execute(
                select(Proxy.id, Proxy.ip)
                .where(Proxy.country.is_(None), Proxy.is_alive == True)
                .limit(limit)
            )
            proxies = result.all()

        if not proxies:
            return 0

        ips = [p.ip for p in proxies]
        ip_to_id = {p.ip: p.id for p in proxies}

        geo_results = await self.lookup_batch(ips)
        updated = 0

        async with async_session() as session:
            for geo in geo_results:
                ip = geo.get("ip")
                if ip and ip in ip_to_id and geo.get("country"):
                    await session.execute(
                        update(Proxy)
                        .where(Proxy.id == ip_to_id[ip])
                        .values(
                            country=geo.get("country"),
                            country_code=geo.get("country_code"),
                            isp=geo.get("isp"),
                        )
                    )
                    updated += 1
            await session.commit()

        logger.info(f"Enriched {updated}/{len(proxies)} proxies with geolocation")
        return updated


class SpeedTierService:
    """Classifies proxies into speed tiers based on latency."""

    @staticmethod
    def get_tier(latency_ms: float | None) -> str:
        """Get speed tier for a given latency."""
        if latency_ms is None:
            return "unknown"
        for tier, (low, high) in SPEED_TIERS.items():
            if low <= latency_ms < high:
                return tier
        return "slow"

    async def get_tier_counts(self) -> dict:
        """Get proxy counts by speed tier."""
        async with async_session() as session:
            fast = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.is_alive == True, Proxy.latency < 500, Proxy.latency.isnot(None)
                )
            ) or 0
            medium = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.is_alive == True, Proxy.latency >= 500, Proxy.latency < 2000
                )
            ) or 0
            slow = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.is_alive == True, Proxy.latency >= 2000
                )
            ) or 0

        return {"fast": fast, "medium": medium, "slow": slow}


class ReputationService:
    """
    IP Reputation Scoring.

    Score 0-100 based on:
    - Uptime percentage (40%)
    - Average latency (20%)
    - Consistency (20%)
    - Age/longevity (20%)
    """

    async def calculate_score(self, proxy_id: int) -> int:
        """Calculate reputation score for a proxy."""
        async with async_session() as session:
            proxy = await session.get(Proxy, proxy_id)
            if not proxy:
                return 0

        score = 0

        # Uptime score (40 points max)
        if proxy.check_count > 0:
            alive_rate = max(0, 1 - (proxy.fail_count / max(proxy.check_count, 1)))
            score += int(alive_rate * 40)

        # Latency score (20 points max)
        if proxy.latency:
            if proxy.latency < 300:
                score += 20
            elif proxy.latency < 1000:
                score += 15
            elif proxy.latency < 3000:
                score += 8
            else:
                score += 3

        # Consistency - low fail count relative to checks (20 points)
        if proxy.check_count >= 5:
            consistency = 1 - (proxy.fail_count / proxy.check_count)
            score += int(consistency * 20)

        # Age/longevity (20 points max)
        if proxy.first_seen:
            age_hours = (datetime.now(timezone.utc) - proxy.first_seen.replace(tzinfo=timezone.utc)).total_seconds() / 3600
            if age_hours > 168:  # > 1 week
                score += 20
            elif age_hours > 48:
                score += 15
            elif age_hours > 12:
                score += 10
            elif age_hours > 1:
                score += 5

        return min(100, max(0, score))

    async def get_top_proxies(self, limit: int = 50) -> list[dict]:
        """Get top-rated proxies by reputation."""
        async with async_session() as session:
            result = await session.execute(
                select(Proxy)
                .where(Proxy.is_alive == True, Proxy.check_count >= 3)
                .order_by(Proxy.fail_count.asc(), Proxy.latency.asc().nullslast())
                .limit(limit)
            )
            proxies = result.scalars().all()

        scored = []
        for p in proxies:
            s = await self.calculate_score(p.id)
            scored.append({
                "id": p.id,
                "ip": p.ip,
                "port": p.port,
                "type": p.proxy_type,
                "country": p.country,
                "latency": p.latency,
                "reputation_score": s,
                "speed_tier": SpeedTierService.get_tier(p.latency),
                "checks": p.check_count,
                "fails": p.fail_count,
            })

        scored.sort(key=lambda x: x["reputation_score"], reverse=True)
        return scored


geo_service = GeoLocationService()
speed_service = SpeedTierService()
reputation_service = ReputationService()
