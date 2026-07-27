"""
Production-grade Proxy Cache Layer.

Architecture:
- Maintains a Redis cache of the top 10,000 highest-quality live proxies.
- Refreshes automatically every 5 minutes from PostgreSQL.
- Public download API reads ONLY from Redis (never touches PG directly).
- Proxies are ranked by: success_rate, latency, uptime, last_check, anonymity.
- Designed for high concurrency and millions of stored proxies in PG.

Cache Keys:
- proxy_cache:http       -> sorted set of HTTP proxies (score = quality rank)
- proxy_cache:socks4     -> sorted set of SOCKS4 proxies
- proxy_cache:socks5     -> sorted set of SOCKS5 proxies
- proxy_cache:all        -> sorted set of all proxies
- proxy_cache:meta       -> hash with cache metadata (last_refresh, counts, health)
- proxy_cache:stats      -> hash with aggregate stats
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select, func, desc

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.models import Proxy

logger = logging.getLogger(__name__)

MAX_CACHE_SIZE = 10000
REFRESH_INTERVAL = 300  # 5 minutes
CACHE_PREFIX = "proxy_cache"


def _calculate_quality_score(proxy) -> float:
    """
    Calculate quality score 0-100 for ranking.
    
    Weights:
    - Success rate (checks alive / total checks): 35%
    - Latency (lower is better): 25%
    - Recency of last check: 20%
    - Anonymity level: 10%
    - Uptime longevity: 10%
    """
    score = 0.0

    # Success rate (35 points)
    if proxy.check_count and proxy.check_count > 0:
        success_rate = 1.0 - (proxy.fail_count / proxy.check_count)
        score += success_rate * 35
    elif proxy.is_alive:
        score += 20  # New proxy, assume decent

    # Latency score (25 points) — lower latency = higher score
    if proxy.latency and proxy.latency > 0:
        if proxy.latency < 200:
            score += 25
        elif proxy.latency < 500:
            score += 22
        elif proxy.latency < 1000:
            score += 18
        elif proxy.latency < 2000:
            score += 12
        elif proxy.latency < 5000:
            score += 6
        else:
            score += 2

    # Recency (20 points) — more recent check = higher score
    if proxy.last_checked:
        age_seconds = (datetime.now(timezone.utc) - proxy.last_checked.replace(tzinfo=timezone.utc)).total_seconds()
        if age_seconds < 60:
            score += 20
        elif age_seconds < 300:
            score += 18
        elif age_seconds < 900:
            score += 14
        elif age_seconds < 3600:
            score += 8
        else:
            score += 3

    # Anonymity (10 points)
    anonymity_scores = {"elite": 10, "anonymous": 7, "transparent": 3}
    score += anonymity_scores.get(proxy.anonymity_level or "", 1)

    # Longevity (10 points) — how long has this proxy been seen alive
    if proxy.first_seen:
        age_hours = (datetime.now(timezone.utc) - proxy.first_seen.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        if age_hours > 168:  # > 1 week
            score += 10
        elif age_hours > 48:
            score += 8
        elif age_hours > 12:
            score += 5
        elif age_hours > 1:
            score += 3

    return round(score, 2)


def _serialize_proxy(proxy) -> str:
    """Serialize proxy to compact JSON for Redis storage."""
    return json.dumps({
        "ip": proxy.ip,
        "port": proxy.port,
        "type": proxy.proxy_type,
        "country": proxy.country_code,
        "country_name": proxy.country,
        "anonymity": proxy.anonymity_level,
        "latency": round(proxy.latency, 1) if proxy.latency else None,
        "ssl": proxy.ssl_support,
        "last_checked": proxy.last_checked.isoformat() if proxy.last_checked else None,
        "checks": proxy.check_count,
        "fails": proxy.fail_count,
    }, separators=(",", ":"))


class ProxyCacheService:
    """
    Manages the Redis proxy cache.
    
    Public downloads read exclusively from this cache.
    The cache is refreshed from PostgreSQL every 5 minutes with the top-ranked proxies.
    """

    def __init__(self):
        self._running = False
        self._last_refresh: datetime | None = None
        self._refresh_duration_ms: float = 0

    async def refresh_cache(self):
        """
        Refresh the Redis cache from PostgreSQL.
        
        Queries the top MAX_CACHE_SIZE alive proxies ranked by quality score,
        and replaces the entire cache atomically using Redis pipelines.
        """
        start = time.monotonic()
        logger.info("Refreshing proxy cache...")

        async with async_session() as session:
            # Fetch all alive proxies — we score and rank in Python
            result = await session.execute(
                select(Proxy)
                .where(Proxy.is_alive == True, Proxy.latency.isnot(None))
                .order_by(Proxy.fail_count.asc(), Proxy.latency.asc())
                .limit(MAX_CACHE_SIZE * 2)  # Fetch extra for scoring
            )
            proxies = result.scalars().all()

        # Score and rank
        scored = [(p, _calculate_quality_score(p)) for p in proxies]
        scored.sort(key=lambda x: x[1], reverse=True)
        top_proxies = scored[:MAX_CACHE_SIZE]

        # Categorize
        by_type: dict[str, list[tuple]] = {"http": [], "socks4": [], "socks5": [], "all": []}
        stats = {"total": 0, "http": 0, "socks4": 0, "socks5": 0, "avg_latency": 0.0, "avg_score": 0.0, "success_rate": 0.0}
        total_latency = 0.0
        total_score = 0.0
        total_success = 0.0
        count = 0

        for proxy, score in top_proxies:
            serialized = _serialize_proxy(proxy)
            entry = (score, serialized)

            ptype = proxy.proxy_type
            if ptype in by_type:
                by_type[ptype].append(entry)
            by_type["all"].append(entry)

            if proxy.latency:
                total_latency += proxy.latency
            total_score += score
            if proxy.check_count and proxy.check_count > 0:
                total_success += (1 - proxy.fail_count / proxy.check_count)
            count += 1

        # Atomic cache update via pipeline
        pipe = redis_client.pipeline()

        # Clear old cache
        for key in ["http", "socks4", "socks5", "all"]:
            pipe.delete(f"{CACHE_PREFIX}:{key}")

        # Insert new data
        for ptype, entries in by_type.items():
            if entries:
                for score, data in entries:
                    pipe.zadd(f"{CACHE_PREFIX}:{ptype}", {data: score})
            stats[ptype if ptype != "all" else "total"] = len(entries)

        stats["total"] = len(by_type["all"])
        stats["avg_latency"] = round(total_latency / max(count, 1), 1)
        stats["avg_score"] = round(total_score / max(count, 1), 1)
        stats["success_rate"] = round(total_success / max(count, 1) * 100, 1)

        # Metadata
        now = datetime.now(timezone.utc)
        pipe.hset(f"{CACHE_PREFIX}:meta", mapping={
            "last_refresh": now.isoformat(),
            "refresh_duration_ms": str(round((time.monotonic() - start) * 1000)),
            "total_proxies": str(stats["total"]),
            "http_count": str(stats["http"]),
            "socks4_count": str(stats["socks4"]),
            "socks5_count": str(stats["socks5"]),
            "avg_latency": str(stats["avg_latency"]),
            "avg_score": str(stats["avg_score"]),
            "success_rate": str(stats["success_rate"]),
            "cache_health": "healthy",
        })

        # TTL on all keys (auto-expire if refresh stops)
        for key in ["http", "socks4", "socks5", "all", "meta"]:
            pipe.expire(f"{CACHE_PREFIX}:{key}", REFRESH_INTERVAL * 3)

        await pipe.execute()

        elapsed = round((time.monotonic() - start) * 1000, 1)
        self._last_refresh = now
        self._refresh_duration_ms = elapsed
        logger.info(f"Cache refreshed: {stats['total']} proxies in {elapsed}ms")

    async def get_proxies(self, proxy_type: str = "all", limit: int = 500, offset: int = 0) -> list[dict]:
        """
        Get proxies from Redis cache (PUBLIC endpoint).
        Returns top-ranked proxies only. Never touches PostgreSQL.
        """
        key = f"{CACHE_PREFIX}:{proxy_type}" if proxy_type in ("http", "socks4", "socks5") else f"{CACHE_PREFIX}:all"

        # Get from sorted set (highest score first)
        raw = await redis_client.zrevrange(key, offset, offset + limit - 1)

        proxies = []
        for item in raw:
            try:
                proxies.append(json.loads(item))
            except (json.JSONDecodeError, TypeError):
                continue

        return proxies

    async def get_proxies_text(self, proxy_type: str = "all", limit: int = 5000) -> str:
        """Get proxies as ip:port text (for TXT downloads)."""
        proxies = await self.get_proxies(proxy_type, limit=limit)
        return "\n".join(f"{p['ip']}:{p['port']}" for p in proxies)

    async def get_proxies_csv(self, proxy_type: str = "all", limit: int = 5000) -> str:
        """Get proxies as CSV."""
        proxies = await self.get_proxies(proxy_type, limit=limit)
        lines = ["ip,port,type,country,anonymity,latency,ssl"]
        for p in proxies:
            lines.append(f"{p['ip']},{p['port']},{p['type']},{p.get('country','')},{p.get('anonymity','')},{p.get('latency','')},{p.get('ssl','')}")
        return "\n".join(lines)

    async def get_proxies_json(self, proxy_type: str = "all", limit: int = 5000) -> str:
        """Get proxies as JSON."""
        proxies = await self.get_proxies(proxy_type, limit=limit)
        return json.dumps(proxies, indent=2)

    async def get_cache_meta(self) -> dict:
        """Get cache metadata for the download page."""
        meta = await redis_client.hgetall(f"{CACHE_PREFIX}:meta")
        if not meta:
            return {
                "cache_health": "cold",
                "total_proxies": 0,
                "http_count": 0,
                "socks4_count": 0,
                "socks5_count": 0,
                "avg_latency": 0,
                "avg_score": 0,
                "success_rate": 0,
                "last_refresh": None,
                "refresh_duration_ms": 0,
            }

        return {
            "cache_health": meta.get("cache_health", "unknown"),
            "total_proxies": int(meta.get("total_proxies", 0)),
            "http_count": int(meta.get("http_count", 0)),
            "socks4_count": int(meta.get("socks4_count", 0)),
            "socks5_count": int(meta.get("socks5_count", 0)),
            "avg_latency": float(meta.get("avg_latency", 0)),
            "avg_score": float(meta.get("avg_score", 0)),
            "success_rate": float(meta.get("success_rate", 0)),
            "last_refresh": meta.get("last_refresh"),
            "refresh_duration_ms": float(meta.get("refresh_duration_ms", 0)),
        }

    async def get_count(self, proxy_type: str = "all") -> int:
        """Get proxy count from cache."""
        key = f"{CACHE_PREFIX}:{proxy_type}" if proxy_type in ("http", "socks4", "socks5") else f"{CACHE_PREFIX}:all"
        return await redis_client.zcard(key) or 0

    async def start_auto_refresh(self, interval: int = REFRESH_INTERVAL):
        """Start the background cache refresh loop."""
        self._running = True
        logger.info(f"Proxy cache auto-refresh started (interval={interval}s)")

        while self._running:
            try:
                await self.refresh_cache()
            except Exception as e:
                logger.error(f"Cache refresh failed: {e}")
                # Mark cache as degraded
                await redis_client.hset(f"{CACHE_PREFIX}:meta", "cache_health", "degraded")
            await asyncio.sleep(interval)

    def stop(self):
        """Stop the auto-refresh loop."""
        self._running = False


proxy_cache = ProxyCacheService()
