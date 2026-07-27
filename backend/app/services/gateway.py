"""
Auto-Rotating Proxy Gateway, Smart Load Balancer, and Fingerprint Detection.

- Gateway: Single endpoint that forwards requests through a rotating proxy
- Load Balancer: Picks the best proxy based on target site, latency, and success rate
- Fingerprint: Detects if a proxy IP is blacklisted on major sites
"""

import asyncio
import hashlib
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update, func

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.models import Proxy

logger = logging.getLogger(__name__)

# Sites to check fingerprint/blacklist against
FINGERPRINT_TARGETS = [
    {"name": "Google", "url": "https://www.google.com/search?q=test", "block_indicators": ["captcha", "unusual traffic", "sorry"]},
    {"name": "Cloudflare", "url": "https://challenges.cloudflare.com/", "block_indicators": ["challenge", "ray id", "blocked"]},
    {"name": "Amazon", "url": "https://www.amazon.com/", "block_indicators": ["robot", "captcha", "automated"]},
    {"name": "LinkedIn", "url": "https://www.linkedin.com/", "block_indicators": ["challenge", "security verification"]},
]


class ProxyGateway:
    """
    Auto-rotating proxy gateway.

    Acts as a forward proxy: client sends request to the gateway,
    gateway picks a proxy and forwards the request through it.
    Each request gets a different proxy automatically.
    """

    async def forward_request(
        self,
        target_url: str,
        method: str = "GET",
        headers: dict | None = None,
        body: bytes | None = None,
        proxy_type: str | None = None,
        country: str | None = None,
        speed_tier: str | None = None,
        sticky_session: str | None = None,
    ) -> dict:
        """Forward a request through a rotating proxy."""
        start_time = time.monotonic()

        # Get proxy
        proxy = await self._select_proxy(proxy_type, country, speed_tier, sticky_session)
        if not proxy:
            return {"success": False, "error": "No available proxy", "status_code": 503}

        proxy_url = f"{proxy.proxy_type}://{proxy.ip}:{proxy.port}"

        try:
            async with httpx.AsyncClient(
                proxy=proxy_url, timeout=15, verify=False, follow_redirects=True
            ) as client:
                response = await client.request(
                    method=method,
                    url=target_url,
                    headers=headers or {},
                    content=body,
                )

            elapsed = round((time.monotonic() - start_time) * 1000, 2)

            # Track success for load balancer scoring
            await self._record_success(proxy.id, elapsed)

            return {
                "success": True,
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text[:10000],
                "proxy_used": f"{proxy.ip}:{proxy.port}",
                "proxy_country": proxy.country_code,
                "latency_ms": elapsed,
            }

        except httpx.TimeoutException:
            await self._record_failure(proxy.id)
            return {"success": False, "error": "Proxy timeout", "proxy_used": f"{proxy.ip}:{proxy.port}", "status_code": 504}
        except Exception as e:
            await self._record_failure(proxy.id)
            return {"success": False, "error": str(e)[:200], "proxy_used": f"{proxy.ip}:{proxy.port}", "status_code": 502}

    async def _select_proxy(
        self, proxy_type: str | None, country: str | None, speed_tier: str | None, sticky: str | None
    ) -> Proxy | None:
        """Select the best proxy using the load balancer."""

        # Sticky session: same proxy for same session key
        if sticky:
            cached_id = await redis_client.get(f"sticky:{sticky}")
            if cached_id:
                async with async_session() as session:
                    proxy = await session.get(Proxy, int(cached_id))
                    if proxy and proxy.is_alive:
                        return proxy

        async with async_session() as session:
            query = select(Proxy).where(Proxy.is_alive == True)
            if proxy_type:
                query = query.where(Proxy.proxy_type == proxy_type)
            if country:
                query = query.where(Proxy.country_code == country.upper())
            if speed_tier == "fast":
                query = query.where(Proxy.latency < 500, Proxy.latency.isnot(None))
            elif speed_tier == "medium":
                query = query.where(Proxy.latency >= 500, Proxy.latency < 2000)

            # Smart load balance: order by least failures + lowest latency
            query = query.order_by(
                Proxy.fail_count.asc(),
                Proxy.latency.asc().nullslast(),
            ).limit(20)

            result = await session.execute(query)
            candidates = result.scalars().all()

        if not candidates:
            return None

        # Round-robin from top candidates
        idx_key = f"gw:rr:{proxy_type or 'all'}:{country or 'any'}"
        idx = int(await redis_client.incr(idx_key)) % len(candidates)
        await redis_client.expire(idx_key, 3600)

        proxy = candidates[idx]

        # Set sticky session
        if sticky:
            await redis_client.setex(f"sticky:{sticky}", 300, str(proxy.id))

        return proxy

    async def _record_success(self, proxy_id: int, latency: float):
        """Record successful gateway request for scoring."""
        await redis_client.incr(f"gw:success:{proxy_id}")
        await redis_client.expire(f"gw:success:{proxy_id}", 3600)

    async def _record_failure(self, proxy_id: int):
        """Record failed gateway request."""
        await redis_client.incr(f"gw:fail:{proxy_id}")
        await redis_client.expire(f"gw:fail:{proxy_id}", 3600)


class FingerprintService:
    """
    Detects if a proxy IP is blacklisted/fingerprinted by major websites.

    Checks against Google, Cloudflare, Amazon, LinkedIn for block indicators.
    Returns a fingerprint score (0=clean, 100=fully blocked).
    """

    async def check_fingerprint(self, ip: str, port: int, proxy_type: str = "http") -> dict:
        """Check a proxy against multiple targets for blacklisting."""
        proxy_url = f"{proxy_type}://{ip}:{port}"
        results = []
        blocked_count = 0

        for target in FINGERPRINT_TARGETS:
            result = {"site": target["name"], "blocked": False, "status": "unknown", "reason": None}

            try:
                async with httpx.AsyncClient(
                    proxy=proxy_url, timeout=10, verify=False, follow_redirects=True
                ) as client:
                    r = await client.get(target["url"], headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })

                body_lower = r.text.lower()
                for indicator in target["block_indicators"]:
                    if indicator in body_lower:
                        result["blocked"] = True
                        result["reason"] = f"Detected '{indicator}'"
                        blocked_count += 1
                        break

                if not result["blocked"]:
                    if r.status_code == 403:
                        result["blocked"] = True
                        result["reason"] = "HTTP 403 Forbidden"
                        blocked_count += 1
                    elif r.status_code == 429:
                        result["blocked"] = True
                        result["reason"] = "HTTP 429 Rate Limited"
                        blocked_count += 1
                    else:
                        result["status"] = "clean"

            except httpx.TimeoutException:
                result["status"] = "timeout"
                result["reason"] = "Connection timeout"
            except Exception as e:
                result["status"] = "error"
                result["reason"] = str(e)[:100]

            results.append(result)

        # Score: 0 = clean, 100 = blocked everywhere
        score = round((blocked_count / len(FINGERPRINT_TARGETS)) * 100)

        return {
            "ip": ip,
            "port": port,
            "fingerprint_score": score,
            "risk_level": "clean" if score == 0 else "low" if score <= 25 else "medium" if score <= 50 else "high",
            "blocked_sites": blocked_count,
            "total_sites": len(FINGERPRINT_TARGETS),
            "details": results,
        }

    async def batch_fingerprint(self, proxies: list[dict], concurrency: int = 10) -> list[dict]:
        """Check multiple proxies for fingerprinting."""
        semaphore = asyncio.Semaphore(concurrency)
        results = []

        async def check_one(p):
            async with semaphore:
                return await self.check_fingerprint(p["ip"], p["port"], p.get("type", "http"))

        tasks = [check_one(p) for p in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return [r for r in results if isinstance(r, dict)]


class SmartLoadBalancer:
    """
    Intelligent proxy selection based on target site characteristics.

    Learns which proxies work best for which sites and routes accordingly.
    """

    async def get_best_for_target(self, target_domain: str, count: int = 5) -> list[dict]:
        """Get the best proxies for a specific target domain."""
        # Check if we have learned preferences for this domain
        domain_hash = hashlib.md5(target_domain.encode()).hexdigest()[:8]
        cached = await redis_client.get(f"lb:domain:{domain_hash}")

        if cached:
            import json
            preferred_ids = json.loads(cached)
            async with async_session() as session:
                result = await session.execute(
                    select(Proxy).where(Proxy.id.in_(preferred_ids), Proxy.is_alive == True)
                )
                proxies = result.scalars().all()
                if proxies:
                    return [{"ip": p.ip, "port": p.port, "type": p.proxy_type, "latency": p.latency} for p in proxies]

        # Fallback: return fastest alive proxies
        async with async_session() as session:
            result = await session.execute(
                select(Proxy)
                .where(Proxy.is_alive == True, Proxy.latency.isnot(None))
                .order_by(Proxy.fail_count.asc(), Proxy.latency.asc())
                .limit(count)
            )
            proxies = result.scalars().all()

        return [{"ip": p.ip, "port": p.port, "type": p.proxy_type, "latency": p.latency} for p in proxies]

    async def record_result(self, target_domain: str, proxy_id: int, success: bool):
        """Record whether a proxy worked for a target domain."""
        import json
        domain_hash = hashlib.md5(target_domain.encode()).hexdigest()[:8]
        key = f"lb:domain:{domain_hash}"

        if success:
            # Add to preferred list
            cached = await redis_client.get(key)
            ids = json.loads(cached) if cached else []
            if proxy_id not in ids:
                ids.append(proxy_id)
                ids = ids[-20:]  # Keep last 20
            await redis_client.setex(key, 86400, json.dumps(ids))
        else:
            # Remove from preferred
            cached = await redis_client.get(key)
            if cached:
                ids = json.loads(cached)
                ids = [i for i in ids if i != proxy_id]
                await redis_client.setex(key, 86400, json.dumps(ids))


gateway = ProxyGateway()
fingerprint_service = FingerprintService()
load_balancer = SmartLoadBalancer()
