"""
Proxy Scraper Service.

Fetches proxies from multiple sources and stores them in PostgreSQL.

Deadlock Prevention Strategy:
1. SORT all proxies by (ip, port) before inserting — deterministic lock order
2. Use small batches (200 rows) with separate short transactions
3. Automatic retry on DeadlockDetectedError with exponential backoff
4. Never hold a transaction open while doing network I/O
"""

import asyncio
import re
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session
from app.models.models import Proxy, ProxySource

logger = logging.getLogger(__name__)

PROXY_PATTERN = re.compile(
    r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})$"
)

# Deadlock retry config
MAX_RETRIES = 5
BASE_DELAY = 0.1  # seconds

# Batch size for upserts (small = short lock time = fewer deadlocks)
UPSERT_BATCH_SIZE = 200

DEFAULT_SOURCES = [
    {"url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", "name": "TheSpeedX HTTP", "proxy_type": "http"},
    {"url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt", "name": "ShiftyTR HTTP", "proxy_type": "http"},
    {"url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "name": "Monosans HTTP", "proxy_type": "http"},
    {"url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt", "name": "Monosans SOCKS4", "proxy_type": "socks4"},
    {"url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "name": "Monosans SOCKS5", "proxy_type": "socks5"},
    {"url": "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&limit=5000&format=text&timeout=5000", "name": "ProxyScrape HTTP", "proxy_type": "http"},
    {"url": "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks4&limit=5000&format=text&timeout=5000", "name": "ProxyScrape SOCKS4", "proxy_type": "socks4"},
    {"url": "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks5&limit=5000&format=text&timeout=5000", "name": "ProxyScrape SOCKS5", "proxy_type": "socks5"},
    {"url": "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/http/data.txt", "name": "ProxyScrape CDN HTTP", "proxy_type": "http"},
    {"url": "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/socks4/data.txt", "name": "ProxyScrape CDN SOCKS4", "proxy_type": "socks4"},
    {"url": "https://cdn.jsdelivr.net/gh/proxyscrape/free-proxy-list@main/proxies/socks5/data.txt", "name": "ProxyScrape CDN SOCKS5", "proxy_type": "socks5"},
    {"url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/http/data.txt", "name": "Proxifly HTTP", "proxy_type": "http"},
    {"url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/socks4/data.txt", "name": "Proxifly SOCKS4", "proxy_type": "socks4"},
    {"url": "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/socks5/data.txt", "name": "Proxifly SOCKS5", "proxy_type": "socks5"},
    {"url": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/http.txt", "name": "iplocate HTTP", "proxy_type": "http"},
    {"url": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/socks4.txt", "name": "iplocate SOCKS4", "proxy_type": "socks4"},
    {"url": "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/socks5.txt", "name": "iplocate SOCKS5", "proxy_type": "socks5"},
    {"url": "https://api.openproxylist.xyz/http.txt", "name": "OpenProxyList HTTP", "proxy_type": "http"},
    {"url": "https://api.openproxylist.xyz/socks4.txt", "name": "OpenProxyList SOCKS4", "proxy_type": "socks4"},
    {"url": "https://api.openproxylist.xyz/socks5.txt", "name": "OpenProxyList SOCKS5", "proxy_type": "socks5"},
    {"url": "https://vakhov.github.io/fresh-proxy-list/http.txt", "name": "Vakhov HTTP", "proxy_type": "http"},
    {"url": "https://vakhov.github.io/fresh-proxy-list/socks4.txt", "name": "Vakhov SOCKS4", "proxy_type": "socks4"},
    {"url": "https://vakhov.github.io/fresh-proxy-list/socks5.txt", "name": "Vakhov SOCKS5", "proxy_type": "socks5"},
    {"url": "https://stormsia.github.io/proxy-list/http.txt", "name": "Stormsia HTTP", "proxy_type": "http"},
    {"url": "https://stormsia.github.io/proxy-list/socks5.txt", "name": "Stormsia SOCKS5", "proxy_type": "socks5"},
    {"url": "https://stormsia.github.io/proxy-list/socks4.txt", "name": "Stormsia SOCKS4", "proxy_type": "socks4"},
    {"url": "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt", "name": "clarketm Raw", "proxy_type": "http"},
    {"url": "https://www.proxy-list.download/api/v1/get?type=http", "name": "ProxyListDownload HTTP", "proxy_type": "http"},
    {"url": "https://www.proxy-list.download/api/v1/get?type=socks4", "name": "ProxyListDownload SOCKS4", "proxy_type": "socks4"},
    {"url": "https://www.proxy-list.download/api/v1/get?type=socks5", "name": "ProxyListDownload SOCKS5", "proxy_type": "socks5"},
    {"url": "https://raw.githubusercontent.com/hproxy-com/free-proxy-list/main/proxies/http/data.txt", "name": "HProxy HTTP", "proxy_type": "http"},
    {"url": "https://raw.githubusercontent.com/hproxy-com/free-proxy-list/main/proxies/socks4/data.txt", "name": "HProxy SOCKS4", "proxy_type": "socks4"},
    {"url": "https://raw.githubusercontent.com/hproxy-com/free-proxy-list/main/proxies/socks5/data.txt", "name": "HProxy SOCKS5", "proxy_type": "socks5"},
]


async def _execute_with_deadlock_retry(coro_factory, description: str = "DB operation"):
    """
    Execute a coroutine with automatic retry on DeadlockDetectedError.
    Uses exponential backoff: 0.1s, 0.2s, 0.4s, 0.8s, 1.6s
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return await coro_factory()
        except Exception as e:
            error_str = str(e)
            is_deadlock = "DeadlockDetectedError" in error_str or "deadlock detected" in error_str.lower()

            if is_deadlock and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(f"Deadlock on {description} (attempt {attempt}/{MAX_RETRIES}), retrying in {delay:.2f}s")
                await asyncio.sleep(delay)
                continue

            raise


class ProxyScraper:
    def __init__(self):
        self.running = False
        self._task: asyncio.Task | None = None

    async def ensure_default_sources(self):
        """Insert default proxy sources if none exist."""
        async with async_session() as session:
            result = await session.execute(select(ProxySource).limit(1))
            if result.scalar_one_or_none() is None:
                for src in DEFAULT_SOURCES:
                    stmt = pg_insert(ProxySource).values(**src).on_conflict_do_nothing(
                        index_elements=["url"]
                    )
                    await session.execute(stmt)
                await session.commit()
                logger.info("Inserted default proxy sources")

    async def get_enabled_sources(self) -> list[ProxySource]:
        async with async_session() as session:
            result = await session.execute(
                select(ProxySource).where(ProxySource.enabled == True)
            )
            return result.scalars().all()

    async def fetch_source(self, client: httpx.AsyncClient, source: ProxySource) -> list[dict]:
        """Fetch and parse proxies from a single source URL."""
        proxies = []
        try:
            response = await client.get(source.url, timeout=30)
            response.raise_for_status()
            lines = response.text.strip().split("\n")

            for line in lines:
                line = line.strip()
                match = PROXY_PATTERN.match(line)
                if match:
                    ip, port = match.group(1), int(match.group(2))
                    if 1 <= port <= 65535:
                        proxies.append({
                            "ip": ip,
                            "port": port,
                            "proxy_type": source.proxy_type,
                            "source_url": source.url,
                        })

            logger.info(f"Fetched {len(proxies)} proxies from {source.name or source.url}")
        except Exception as e:
            logger.error(f"Error fetching {source.url}: {e}")

        return proxies

    async def _upsert_batch(self, batch: list[dict], now: datetime):
        """
        Upsert a single batch of proxies in ONE short transaction.
        Batch is already sorted by (ip, port) for deterministic lock ordering.
        """
        async with async_session() as session:
            for proxy_data in batch:
                stmt = pg_insert(Proxy).values(
                    ip=proxy_data["ip"],
                    port=proxy_data["port"],
                    proxy_type=proxy_data["proxy_type"],
                    source_url=proxy_data["source_url"],
                    first_seen=now,
                    last_seen=now,
                ).on_conflict_do_update(
                    index_elements=["ip", "port"],
                    set_={
                        "last_seen": now,
                        "source_url": proxy_data["source_url"],
                    },
                )
                await session.execute(stmt)
            await session.commit()

    async def scrape_all(self):
        """Scrape all enabled sources and store unique proxies."""
        sources = await self.get_enabled_sources()

        if not sources:
            logger.warning("No enabled proxy sources found")
            return 0

        # Phase 1: Fetch all sources (network I/O, no DB transaction held)
        all_proxies = []
        async with httpx.AsyncClient(
            follow_redirects=True,
            headers={"User-Agent": "ProxyChecker/1.0"},
        ) as client:
            tasks = [self.fetch_source(client, source) for source in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                if isinstance(result, list):
                    all_proxies.extend(result)

        # Phase 2: Update source metadata (short independent transactions)
        for i, result in enumerate(results):
            if isinstance(result, list):
                async with async_session() as session:
                    await session.execute(
                        update(ProxySource)
                        .where(ProxySource.id == sources[i].id)
                        .values(
                            last_scraped=datetime.now(timezone.utc),
                            proxy_count=len(result),
                        )
                    )
                    await session.commit()

        # Phase 3: Deduplicate
        seen = set()
        unique_proxies = []
        for proxy in all_proxies:
            key = f"{proxy['ip']}:{proxy['port']}"
            if key not in seen:
                seen.add(key)
                unique_proxies.append(proxy)

        # Phase 4: SORT by (ip, port) for deterministic lock ordering
        # This is the KEY deadlock prevention: all writers lock rows in the
        # same order, so circular wait is impossible.
        unique_proxies.sort(key=lambda p: (p["ip"], p["port"]))

        # Phase 5: Batch upsert with short transactions + deadlock retry
        if unique_proxies:
            now = datetime.now(timezone.utc)
            inserted = 0

            for i in range(0, len(unique_proxies), UPSERT_BATCH_SIZE):
                batch = unique_proxies[i:i + UPSERT_BATCH_SIZE]

                async def do_batch(b=batch, t=now):
                    await self._upsert_batch(b, t)

                try:
                    await _execute_with_deadlock_retry(do_batch, f"upsert batch {i//UPSERT_BATCH_SIZE}")
                    inserted += len(batch)
                except Exception as e:
                    logger.error(f"Batch {i//UPSERT_BATCH_SIZE} failed after retries: {e}")

            logger.info(f"Scraped {inserted}/{len(unique_proxies)} unique proxies from {len(sources)} sources")
            return inserted

        return 0

    async def start(self, interval: int = 10):
        """Start the scraper loop."""
        self.running = True
        await self.ensure_default_sources()
        logger.info(f"Proxy scraper started with interval={interval}s")

        while self.running:
            try:
                await self.scrape_all()
            except Exception as e:
                logger.error(f"Scraper error: {e}")
            await asyncio.sleep(interval)

    def stop(self):
        """Stop the scraper loop."""
        self.running = False
        if self._task:
            self._task.cancel()
        logger.info("Proxy scraper stopped")


scraper_instance = ProxyScraper()
