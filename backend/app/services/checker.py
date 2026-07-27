"""
Proxy Checker Service.

Features:
- Async checking with configurable concurrency (500+)
- HTTP, HTTPS, SOCKS4, SOCKS5 support via httpx[socks]
- Graceful SOCKS skip if socksio is unavailable
- Startup protocol verification
- Log spam reduction (batch error counters instead of per-proxy logs)
- Deadlock-safe: sorted small-batch writes with retry
"""

import asyncio
import time
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update, func

from app.core.database import async_session
from app.core.config import get_settings
from app.models.models import Proxy, CheckHistory, Statistics

logger = logging.getLogger(__name__)

JUDGE_URL = "http://httpbin.org/ip"
HTTPS_JUDGE = "https://httpbin.org/ip"

# ─── SOCKS Support Detection ─────────────────────────────────────────────────

SOCKS_AVAILABLE = False
try:
    import socksio  # noqa: F401
    SOCKS_AVAILABLE = True
except ImportError:
    pass


def verify_protocol_support():
    """Log supported protocols at startup."""
    logger.info("═══ Protocol Support ═══")
    logger.info("  HTTP support:   OK")
    logger.info("  HTTPS support:  OK")
    if SOCKS_AVAILABLE:
        logger.info("  SOCKS4 support: OK")
        logger.info("  SOCKS5 support: OK")
    else:
        logger.warning("  SOCKS4 support: UNAVAILABLE (install httpx[socks] or socksio)")
        logger.warning("  SOCKS5 support: UNAVAILABLE (install httpx[socks] or socksio)")
    logger.info("════════════════════════")


class ProxyChecker:
    def __init__(self):
        self.running = False
        self.settings = get_settings()
        self._task: asyncio.Task | None = None
        # Error counters for log spam reduction
        self._error_counts: dict[str, int] = {}

    def _build_proxy_url(self, proxy_type: str, ip: str, port: int) -> str | None:
        """
        Build the correct proxy URL for httpx.
        
        httpx with socksio supports: http://, socks4://, socks5://
        Without socksio: only http:// and https://
        """
        if proxy_type in ("socks4", "socks5"):
            if not SOCKS_AVAILABLE:
                return None  # Skip — will be counted, not logged per-proxy
            return f"{proxy_type}://{ip}:{port}"
        else:
            return f"http://{ip}:{port}"

    async def check_single_proxy(self, proxy: dict, semaphore: asyncio.Semaphore) -> dict:
        """Check a single proxy for liveness, latency, anonymity, and SSL."""
        async with semaphore:
            result = {
                "id": proxy["id"],
                "ip": proxy["ip"],
                "port": proxy["port"],
                "is_alive": False,
                "latency": None,
                "status_code": None,
                "anonymity_level": None,
                "ssl_support": False,
                "error": None,
            }

            proxy_url = self._build_proxy_url(proxy["proxy_type"], proxy["ip"], proxy["port"])

            if proxy_url is None:
                # SOCKS not available — skip silently, count it
                result["error"] = "socks_unavailable"
                return result

            try:
                start_time = time.monotonic()
                async with httpx.AsyncClient(
                    proxy=proxy_url,
                    timeout=self.settings.check_timeout,
                    verify=False,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(JUDGE_URL)
                    elapsed = time.monotonic() - start_time

                    result["is_alive"] = True
                    result["latency"] = round(elapsed * 1000, 2)
                    result["status_code"] = response.status_code

                    # Anonymity check
                    try:
                        body = response.json()
                        origin = body.get("origin", "")
                        if proxy["ip"] in origin and "," not in origin:
                            result["anonymity_level"] = "transparent"
                        elif "," in origin:
                            result["anonymity_level"] = "anonymous"
                        else:
                            result["anonymity_level"] = "elite"
                    except Exception:
                        result["anonymity_level"] = "unknown"

                    # SSL check
                    try:
                        async with httpx.AsyncClient(
                            proxy=proxy_url, timeout=5, verify=True, follow_redirects=True
                        ) as ssl_client:
                            ssl_resp = await ssl_client.get(HTTPS_JUDGE)
                            if ssl_resp.status_code == 200:
                                result["ssl_support"] = True
                    except Exception:
                        pass

            except httpx.TimeoutException:
                result["error"] = "timeout"
            except httpx.ConnectError:
                result["error"] = "connection_refused"
            except Exception as e:
                result["error"] = str(e)[:100]

            return result

    async def check_batch(self, proxies: list[dict], concurrency: int = 500) -> list[dict]:
        """Check a batch of proxies concurrently."""
        semaphore = asyncio.Semaphore(concurrency)
        tasks = [self.check_single_proxy(p, semaphore) for p in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = []
        error_summary: dict[str, int] = {}

        for r in results:
            if isinstance(r, dict):
                valid_results.append(r)
                if r.get("error"):
                    err_key = r["error"][:50]
                    error_summary[err_key] = error_summary.get(err_key, 0) + 1
            else:
                err_key = str(r)[:50]
                error_summary[err_key] = error_summary.get(err_key, 0) + 1

        # Log error summary (reduces thousands of identical lines to a few)
        if error_summary:
            summary_parts = [f"{k}: {v}" for k, v in sorted(error_summary.items(), key=lambda x: -x[1])[:5]]
            logger.info(f"Check batch errors: {', '.join(summary_parts)} (total: {sum(error_summary.values())})")

        return valid_results

    async def update_proxies(self, results: list[dict]):
        """Update proxy records — sorted by ID, small batches, deadlock retry."""
        if not results:
            return

        sorted_results = sorted(results, key=lambda r: r["id"])
        now = datetime.now(timezone.utc)

        batch_size = 100
        for i in range(0, len(sorted_results), batch_size):
            batch = sorted_results[i:i + batch_size]

            async def do_batch(b=batch, t=now):
                async with async_session() as session:
                    for result in b:
                        # Skip SOCKS unavailable proxies (don't mark as dead)
                        if result.get("error") == "socks_unavailable":
                            continue

                        values = {
                            "is_alive": result["is_alive"],
                            "latency": result["latency"],
                            "status_code": result["status_code"],
                            "anonymity_level": result["anonymity_level"],
                            "ssl_support": result["ssl_support"],
                            "last_checked": t,
                            "check_count": Proxy.check_count + 1,
                        }
                        if result["is_alive"]:
                            values["fail_count"] = 0
                            values["last_seen"] = t
                        else:
                            values["fail_count"] = Proxy.fail_count + 1

                        await session.execute(
                            update(Proxy).where(Proxy.id == result["id"]).values(**values)
                        )

                        history = CheckHistory(
                            proxy_id=result["id"],
                            is_alive=result["is_alive"],
                            latency=result["latency"],
                            status_code=result["status_code"],
                            error=result["error"],
                            checked_at=t,
                        )
                        session.add(history)

                    await session.commit()

            try:
                await self._execute_with_retry(do_batch, f"checker batch {i//batch_size}")
            except Exception as e:
                logger.error(f"Checker batch {i//batch_size} failed: {e}")

    async def _execute_with_retry(self, coro_factory, description: str):
        """Deadlock retry with exponential backoff."""
        for attempt in range(1, 6):
            try:
                return await coro_factory()
            except Exception as e:
                if "deadlock" in str(e).lower() and attempt < 5:
                    await asyncio.sleep(0.1 * (2 ** (attempt - 1)))
                    continue
                raise

    async def update_statistics(self):
        """Calculate and store current statistics."""
        async with async_session() as session:
            total = await session.scalar(select(func.count(Proxy.id))) or 0
            alive = await session.scalar(select(func.count(Proxy.id)).where(Proxy.is_alive == True)) or 0
            dead = total - alive

            http_count = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "http", Proxy.is_alive == True)) or 0
            https_count = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "https", Proxy.is_alive == True)) or 0
            socks4_count = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks4", Proxy.is_alive == True)) or 0
            socks5_count = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks5", Proxy.is_alive == True)) or 0
            elite_count = await session.scalar(select(func.count(Proxy.id)).where(Proxy.anonymity_level == "elite", Proxy.is_alive == True)) or 0
            anonymous_count = await session.scalar(select(func.count(Proxy.id)).where(Proxy.anonymity_level == "anonymous", Proxy.is_alive == True)) or 0
            transparent_count = await session.scalar(select(func.count(Proxy.id)).where(Proxy.anonymity_level == "transparent", Proxy.is_alive == True)) or 0
            avg_latency = await session.scalar(select(func.avg(Proxy.latency)).where(Proxy.is_alive == True, Proxy.latency.isnot(None))) or 0.0

            stats = Statistics(
                total_proxies=total, alive_proxies=alive, dead_proxies=dead,
                http_count=http_count, https_count=https_count,
                socks4_count=socks4_count, socks5_count=socks5_count,
                elite_count=elite_count, anonymous_count=anonymous_count,
                transparent_count=transparent_count, avg_latency=round(avg_latency, 2),
            )
            session.add(stats)
            await session.commit()

    async def run_check_cycle(self):
        """Run a complete check cycle."""
        async with async_session() as session:
            # Build query — skip SOCKS if not available
            query = select(Proxy.id, Proxy.ip, Proxy.port, Proxy.proxy_type).order_by(Proxy.last_checked.asc().nullsfirst()).limit(5000)

            if not SOCKS_AVAILABLE:
                query = query.where(Proxy.proxy_type.in_(["http", "https"]))

            result = await session.execute(query)
            proxies = [
                {"id": r.id, "ip": r.ip, "port": r.port, "proxy_type": r.proxy_type}
                for r in result.all()
            ]

        if not proxies:
            return

        # Log what we're checking
        type_counts = {}
        for p in proxies:
            type_counts[p["proxy_type"]] = type_counts.get(p["proxy_type"], 0) + 1
        type_str = ", ".join(f"{k}={v}" for k, v in type_counts.items())
        logger.info(f"Checking {len(proxies)} proxies ({type_str}) concurrency={self.settings.check_concurrency}")

        batch_size = 1000
        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            results = await self.check_batch(batch, self.settings.check_concurrency)
            await self.update_proxies(results)

        await self.update_statistics()

        # Summary
        alive_count = sum(1 for r in results if r.get("is_alive"))
        logger.info(f"Check cycle complete: {alive_count}/{len(proxies)} alive")

    async def start(self, interval: int = 30):
        """Start the checker loop."""
        self.running = True
        verify_protocol_support()
        logger.info(f"Proxy checker started (interval={interval}s, socks={'yes' if SOCKS_AVAILABLE else 'no'})")

        while self.running:
            try:
                await self.run_check_cycle()
            except Exception as e:
                logger.error(f"Checker cycle error: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Proxy checker stopped")


checker_instance = ProxyChecker()
