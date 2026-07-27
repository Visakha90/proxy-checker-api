import asyncio
import time
import logging
from datetime import datetime, timezone
import httpx
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session
from app.core.config import get_settings
from app.models.models import Proxy, CheckHistory, Statistics

logger = logging.getLogger(__name__)

JUDGE_URLS = [
    "http://httpbin.org/ip",
    "http://ip-api.com/json",
    "http://ipinfo.io/json",
]

HTTPS_JUDGE = "https://httpbin.org/ip"


class ProxyChecker:
    def __init__(self):
        self.running = False
        self.settings = get_settings()
        self._task: asyncio.Task | None = None

    async def check_single_proxy(
        self, proxy: dict, semaphore: asyncio.Semaphore
    ) -> dict:
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

            proxy_type = proxy["proxy_type"]
            proxy_url = f"{proxy_type}://{proxy['ip']}:{proxy['port']}"

            if proxy_type in ("socks4", "socks5"):
                transport = httpx.AsyncHTTPTransport(
                    proxy=f"socks5://{proxy['ip']}:{proxy['port']}"
                    if proxy_type == "socks5"
                    else f"socks4://{proxy['ip']}:{proxy['port']}"
                )
            else:
                transport = None

            try:
                start_time = time.monotonic()
                async with httpx.AsyncClient(
                    proxy=proxy_url if transport is None else None,
                    transport=transport,
                    timeout=self.settings.check_timeout,
                    verify=False,
                    follow_redirects=True,
                ) as client:
                    response = await client.get(JUDGE_URLS[0])
                    elapsed = time.monotonic() - start_time

                    result["is_alive"] = True
                    result["latency"] = round(elapsed * 1000, 2)
                    result["status_code"] = response.status_code

                    # Check anonymity
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

                    # Check SSL support
                    try:
                        ssl_client = httpx.AsyncClient(
                            proxy=proxy_url if transport is None else None,
                            transport=transport,
                            timeout=5,
                            follow_redirects=True,
                        )
                        async with ssl_client:
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
                result["error"] = str(e)[:200]

            return result

    async def check_batch(self, proxies: list[dict], concurrency: int = 500) -> list[dict]:
        """Check a batch of proxies concurrently."""
        semaphore = asyncio.Semaphore(concurrency)
        tasks = [self.check_single_proxy(p, semaphore) for p in proxies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = []
        for r in results:
            if isinstance(r, dict):
                valid_results.append(r)
            else:
                logger.error(f"Check error: {r}")

        return valid_results

    async def update_proxies(self, results: list[dict]):
        """Update proxy records with check results."""
        async with async_session() as session:
            now = datetime.now(timezone.utc)
            for result in results:
                values = {
                    "is_alive": result["is_alive"],
                    "latency": result["latency"],
                    "status_code": result["status_code"],
                    "anonymity_level": result["anonymity_level"],
                    "ssl_support": result["ssl_support"],
                    "last_checked": now,
                    "check_count": Proxy.check_count + 1,
                }

                if result["is_alive"]:
                    values["fail_count"] = 0
                    values["last_seen"] = now
                else:
                    values["fail_count"] = Proxy.fail_count + 1

                await session.execute(
                    update(Proxy).where(Proxy.id == result["id"]).values(**values)
                )

                # Record check history
                history = CheckHistory(
                    proxy_id=result["id"],
                    is_alive=result["is_alive"],
                    latency=result["latency"],
                    status_code=result["status_code"],
                    error=result["error"],
                    checked_at=now,
                )
                session.add(history)

            await session.commit()

    async def update_statistics(self):
        """Calculate and store current statistics."""
        async with async_session() as session:
            total = await session.scalar(select(func.count(Proxy.id)))
            alive = await session.scalar(
                select(func.count(Proxy.id)).where(Proxy.is_alive == True)
            )
            dead = total - alive if total else 0

            http_count = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.proxy_type == "http", Proxy.is_alive == True
                )
            )
            https_count = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.proxy_type == "https", Proxy.is_alive == True
                )
            )
            socks4_count = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.proxy_type == "socks4", Proxy.is_alive == True
                )
            )
            socks5_count = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.proxy_type == "socks5", Proxy.is_alive == True
                )
            )
            elite_count = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.anonymity_level == "elite", Proxy.is_alive == True
                )
            )
            anonymous_count = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.anonymity_level == "anonymous", Proxy.is_alive == True
                )
            )
            transparent_count = await session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.anonymity_level == "transparent", Proxy.is_alive == True
                )
            )
            avg_latency_result = await session.scalar(
                select(func.avg(Proxy.latency)).where(
                    Proxy.is_alive == True, Proxy.latency.isnot(None)
                )
            )

            stats = Statistics(
                total_proxies=total or 0,
                alive_proxies=alive or 0,
                dead_proxies=dead,
                http_count=http_count or 0,
                https_count=https_count or 0,
                socks4_count=socks4_count or 0,
                socks5_count=socks5_count or 0,
                elite_count=elite_count or 0,
                anonymous_count=anonymous_count or 0,
                transparent_count=transparent_count or 0,
                avg_latency=round(avg_latency_result or 0, 2),
            )
            session.add(stats)
            await session.commit()

    async def run_check_cycle(self):
        """Run a complete check cycle on all unchecked or stale proxies."""
        async with async_session() as session:
            result = await session.execute(
                select(Proxy.id, Proxy.ip, Proxy.port, Proxy.proxy_type)
                .order_by(Proxy.last_checked.asc().nullsfirst())
                .limit(5000)
            )
            proxies = [
                {"id": r.id, "ip": r.ip, "port": r.port, "proxy_type": r.proxy_type}
                for r in result.all()
            ]

        if not proxies:
            return

        logger.info(f"Checking {len(proxies)} proxies with concurrency={self.settings.check_concurrency}")

        batch_size = 1000
        for i in range(0, len(proxies), batch_size):
            batch = proxies[i:i + batch_size]
            results = await self.check_batch(batch, self.settings.check_concurrency)
            await self.update_proxies(results)

        await self.update_statistics()
        logger.info("Check cycle complete, statistics updated")

    async def start(self, interval: int = 30):
        """Start the checker loop."""
        self.running = True
        logger.info(f"Proxy checker started with interval={interval}s")

        while self.running:
            try:
                await self.run_check_cycle()
            except Exception as e:
                logger.error(f"Checker error: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        """Stop the checker loop."""
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Proxy checker stopped")


checker_instance = ProxyChecker()
