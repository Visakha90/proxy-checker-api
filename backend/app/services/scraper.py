import asyncio
import re
import logging
from datetime import datetime, timezone
import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import async_session
from app.models.models import Proxy, ProxySource

logger = logging.getLogger(__name__)

PROXY_PATTERN = re.compile(
    r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d{1,5})$"
)

DEFAULT_SOURCES = [
    {
        "url": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "name": "TheSpeedX HTTP",
        "proxy_type": "http",
    },
    {
        "url": "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
        "name": "ShiftyTR HTTP",
        "proxy_type": "http",
    },
    {
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "name": "Monosans HTTP",
        "proxy_type": "http",
    },
    {
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
        "name": "Monosans SOCKS4",
        "proxy_type": "socks4",
    },
    {
        "url": "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "name": "Monosans SOCKS5",
        "proxy_type": "socks5",
    },
]


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

    async def get_enabled_sources(self, session: AsyncSession) -> list[ProxySource]:
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

    async def scrape_all(self):
        """Scrape all enabled sources and store unique proxies."""
        async with async_session() as session:
            sources = await self.get_enabled_sources(session)

            if not sources:
                logger.warning("No enabled proxy sources found")
                return 0

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
                        # Update source metadata
                        await session.execute(
                            update(ProxySource)
                            .where(ProxySource.id == sources[i].id)
                            .values(
                                last_scraped=datetime.now(timezone.utc),
                                proxy_count=len(result),
                            )
                        )

            # Deduplicate by ip:port
            seen = set()
            unique_proxies = []
            for proxy in all_proxies:
                key = f"{proxy['ip']}:{proxy['port']}"
                if key not in seen:
                    seen.add(key)
                    unique_proxies.append(proxy)

            # Batch upsert into database
            if unique_proxies:
                now = datetime.now(timezone.utc)
                batch_size = 1000
                for i in range(0, len(unique_proxies), batch_size):
                    batch = unique_proxies[i:i + batch_size]
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

            logger.info(f"Scraped {len(unique_proxies)} unique proxies from {len(sources)} sources")
            return len(unique_proxies)

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
