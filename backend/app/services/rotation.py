"""
Proxy Rotation, Chain Builder, and Uptime Monitoring.

- Round-robin rotation: each call returns the next proxy in sequence
- Proxy chains: multi-hop routing through multiple proxies
- Uptime monitoring: tracks availability percentage over time
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, update, func

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.models import Proxy
from app.models.user_models import ProxyUptime, ProxyChain

logger = logging.getLogger(__name__)


class RotationService:
    """Round-robin proxy rotation with per-user state."""

    async def get_next(
        self,
        user_id: str | None = None,
        proxy_type: str | None = None,
        country: str | None = None,
        speed_tier: str | None = None,
    ) -> dict | None:
        """Get the next proxy in rotation."""
        # Build rotation key for this filter set
        key_parts = [user_id or "global", proxy_type or "all", country or "any", speed_tier or "any"]
        rotation_key = f"rotation:{':'.join(key_parts)}"

        # Get current offset
        offset = int(await redis_client.get(rotation_key) or 0)

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

            query = query.order_by(Proxy.latency.asc().nullslast())

            # Get total count
            count_query = select(func.count(Proxy.id)).where(Proxy.is_alive == True)
            if proxy_type:
                count_query = count_query.where(Proxy.proxy_type == proxy_type)
            if country:
                count_query = count_query.where(Proxy.country_code == country.upper())
            total = await session.scalar(count_query) or 0

            if total == 0:
                return None

            # Wrap around
            actual_offset = offset % total
            query = query.offset(actual_offset).limit(1)

            result = await session.execute(query)
            proxy = result.scalar_one_or_none()

        if not proxy:
            return None

        # Increment rotation counter
        await redis_client.set(rotation_key, str(offset + 1))
        await redis_client.expire(rotation_key, 3600)

        return {
            "ip": proxy.ip,
            "port": proxy.port,
            "type": proxy.proxy_type,
            "country": proxy.country,
            "country_code": proxy.country_code,
            "latency": round(proxy.latency, 2) if proxy.latency else None,
            "anonymity": proxy.anonymity_level,
            "ssl": proxy.ssl_support,
            "rotation_index": offset + 1,
        }


class ChainService:
    """Multi-hop proxy chain management."""

    async def create_chain(self, user_id: int, name: str, proxy_ids: list[int]) -> ProxyChain:
        """Create a proxy chain."""
        async with async_session() as session:
            # Verify all proxies exist and are alive
            for pid in proxy_ids:
                proxy = await session.get(Proxy, pid)
                if not proxy:
                    raise ValueError(f"Proxy ID {pid} not found")

            chain = ProxyChain(
                user_id=user_id,
                name=name,
                hops=json.dumps(proxy_ids),
            )
            session.add(chain)
            await session.commit()
            await session.refresh(chain)
            return chain

    async def get_chain(self, chain_id: int, user_id: int) -> dict | None:
        """Get a proxy chain with resolved proxies."""
        async with async_session() as session:
            chain = await session.get(ProxyChain, chain_id)
            if not chain or chain.user_id != user_id:
                return None

            proxy_ids = json.loads(chain.hops)
            hops = []
            for pid in proxy_ids:
                proxy = await session.get(Proxy, pid)
                if proxy:
                    hops.append({
                        "id": proxy.id,
                        "ip": proxy.ip,
                        "port": proxy.port,
                        "type": proxy.proxy_type,
                        "country": proxy.country,
                        "alive": proxy.is_alive,
                        "latency": proxy.latency,
                    })

        return {
            "id": chain.id,
            "name": chain.name,
            "hops": hops,
            "is_active": chain.is_active,
            "last_tested_at": chain.last_tested_at.isoformat() if chain.last_tested_at else None,
            "last_latency": chain.last_latency,
        }

    async def list_chains(self, user_id: int) -> list[dict]:
        """List all chains for a user."""
        async with async_session() as session:
            result = await session.execute(
                select(ProxyChain).where(ProxyChain.user_id == user_id).order_by(ProxyChain.created_at.desc())
            )
            chains = result.scalars().all()

        return [
            {
                "id": c.id,
                "name": c.name,
                "hop_count": len(json.loads(c.hops)),
                "is_active": c.is_active,
                "last_latency": c.last_latency,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in chains
        ]

    async def test_chain(self, chain_id: int, user_id: int) -> dict:
        """Test a proxy chain by connecting through each hop sequentially."""
        chain_data = await self.get_chain(chain_id, user_id)
        if not chain_data:
            return {"error": "Chain not found"}

        total_latency = 0
        results = []

        for hop in chain_data["hops"]:
            start = time.monotonic()
            proxy_url = f"http://{hop['ip']}:{hop['port']}"
            try:
                async with httpx.AsyncClient(proxy=proxy_url, timeout=10, verify=False) as client:
                    r = await client.get("http://httpbin.org/ip")
                    elapsed = (time.monotonic() - start) * 1000
                    total_latency += elapsed
                    results.append({"hop": hop["ip"], "status": "ok", "latency_ms": round(elapsed, 2)})
            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                total_latency += elapsed
                results.append({"hop": hop["ip"], "status": "failed", "error": str(e)[:100]})

        # Update chain record
        async with async_session() as session:
            await session.execute(
                update(ProxyChain)
                .where(ProxyChain.id == chain_id)
                .values(last_tested_at=datetime.now(timezone.utc), last_latency=round(total_latency, 2))
            )
            await session.commit()

        return {
            "chain_id": chain_id,
            "total_latency_ms": round(total_latency, 2),
            "hops": results,
            "all_passed": all(r["status"] == "ok" for r in results),
        }

    async def delete_chain(self, chain_id: int, user_id: int) -> bool:
        """Delete a proxy chain."""
        async with async_session() as session:
            chain = await session.get(ProxyChain, chain_id)
            if not chain or chain.user_id != user_id:
                return False
            await session.delete(chain)
            await session.commit()
            return True


class UptimeService:
    """Tracks proxy uptime percentages over time."""

    async def record_check(self, proxy_id: int, is_alive: bool, latency: float | None):
        """Record a check result for uptime tracking."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        async with async_session() as session:
            existing = await session.scalar(
                select(ProxyUptime).where(
                    ProxyUptime.proxy_id == proxy_id, ProxyUptime.date == today
                )
            )

            if existing:
                existing.checks_total += 1
                if is_alive:
                    existing.checks_alive += 1
                existing.uptime_pct = round(existing.checks_alive / existing.checks_total * 100, 2)
                if latency and existing.avg_latency:
                    existing.avg_latency = round((existing.avg_latency + latency) / 2, 2)
                elif latency:
                    existing.avg_latency = latency
            else:
                record = ProxyUptime(
                    proxy_id=proxy_id,
                    date=today,
                    checks_total=1,
                    checks_alive=1 if is_alive else 0,
                    uptime_pct=100.0 if is_alive else 0.0,
                    avg_latency=latency,
                )
                session.add(record)

            await session.commit()

    async def get_uptime(self, proxy_id: int, days: int = 7) -> list[dict]:
        """Get uptime history for a proxy."""
        async with async_session() as session:
            result = await session.execute(
                select(ProxyUptime)
                .where(ProxyUptime.proxy_id == proxy_id)
                .order_by(ProxyUptime.date.desc())
                .limit(days)
            )
            records = result.scalars().all()

        return [
            {
                "date": r.date,
                "uptime_pct": r.uptime_pct,
                "checks_total": r.checks_total,
                "checks_alive": r.checks_alive,
                "avg_latency": r.avg_latency,
            }
            for r in reversed(records)
        ]

    async def get_overall_uptime(self, proxy_id: int) -> float:
        """Get overall uptime percentage for a proxy."""
        async with async_session() as session:
            total_checks = await session.scalar(
                select(func.sum(ProxyUptime.checks_total)).where(ProxyUptime.proxy_id == proxy_id)
            ) or 0
            alive_checks = await session.scalar(
                select(func.sum(ProxyUptime.checks_alive)).where(ProxyUptime.proxy_id == proxy_id)
            ) or 0

        if total_checks == 0:
            return 0.0
        return round(alive_checks / total_checks * 100, 2)


rotation_service = RotationService()
chain_service = ChainService()
uptime_service = UptimeService()
