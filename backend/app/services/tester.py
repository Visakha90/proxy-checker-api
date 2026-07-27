import asyncio
import time
import logging
import httpx
from sqlalchemy import select
from app.core.database import async_session
from app.models.models import Proxy

logger = logging.getLogger(__name__)


class ProxyTester:
    async def test_proxy_against_target(
        self,
        proxy: dict,
        target_url: str,
        method: str,
        timeout: int,
        semaphore: asyncio.Semaphore,
    ) -> dict:
        """Test a single proxy against the specified target URL."""
        async with semaphore:
            result = {
                "ip": proxy["ip"],
                "port": proxy["port"],
                "proxy_type": proxy["proxy_type"],
                "working": False,
                "latency": None,
                "status_code": None,
                "error": None,
            }

            proxy_type = proxy["proxy_type"]
            proxy_url = f"{proxy_type}://{proxy['ip']}:{proxy['port']}"

            try:
                start_time = time.monotonic()
                async with httpx.AsyncClient(
                    proxy=proxy_url,
                    timeout=timeout,
                    verify=False,
                    follow_redirects=True,
                ) as client:
                    if method.upper() == "POST":
                        response = await client.post(target_url)
                    else:
                        response = await client.get(target_url)

                    elapsed = time.monotonic() - start_time
                    result["working"] = True
                    result["latency"] = round(elapsed * 1000, 2)
                    result["status_code"] = response.status_code

            except httpx.TimeoutException:
                result["error"] = "timeout"
            except httpx.ConnectError:
                result["error"] = "connection_refused"
            except Exception as e:
                result["error"] = str(e)[:200]

            return result

    async def test_proxies(
        self,
        target_url: str,
        method: str = "GET",
        timeout: int = 10,
        proxy_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Test live proxies against a target URL."""
        async with async_session() as session:
            query = select(Proxy.ip, Proxy.port, Proxy.proxy_type).where(
                Proxy.is_alive == True
            )
            if proxy_type:
                query = query.where(Proxy.proxy_type == proxy_type)
            query = query.limit(limit)

            result = await session.execute(query)
            proxies = [
                {"ip": r.ip, "port": r.port, "proxy_type": r.proxy_type}
                for r in result.all()
            ]

        if not proxies:
            return []

        concurrency = min(len(proxies), 500)
        semaphore = asyncio.Semaphore(concurrency)

        tasks = [
            self.test_proxy_against_target(p, target_url, method, timeout, semaphore)
            for p in proxies
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = []
        for r in results:
            if isinstance(r, dict):
                valid_results.append(r)

        # Sort by latency (working first, then by speed)
        valid_results.sort(
            key=lambda x: (not x["working"], x["latency"] or float("inf"))
        )
        return valid_results


tester_instance = ProxyTester()
