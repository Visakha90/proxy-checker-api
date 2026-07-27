import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import delete, select, func
from app.core.database import async_session
from app.core.config import get_settings
from app.models.models import Proxy, CheckHistory

logger = logging.getLogger(__name__)


class ProxyCleaner:
    def __init__(self):
        self.settings = get_settings()

    async def remove_dead_proxies(self) -> int:
        """Remove proxies that have exceeded maximum failure count."""
        async with async_session() as session:
            result = await session.execute(
                delete(Proxy).where(
                    Proxy.fail_count >= self.settings.max_failures_before_delete
                ).returning(Proxy.id)
            )
            deleted = result.all()
            await session.commit()
            count = len(deleted)
            if count:
                logger.info(f"Removed {count} dead proxies (fail_count >= {self.settings.max_failures_before_delete})")
            return count

    async def remove_old_proxies(self) -> int:
        """Remove proxies older than max age that are not alive."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=self.settings.max_proxy_age_hours)
        async with async_session() as session:
            result = await session.execute(
                delete(Proxy).where(
                    Proxy.last_seen < cutoff,
                    Proxy.is_alive == False,
                ).returning(Proxy.id)
            )
            deleted = result.all()
            await session.commit()
            count = len(deleted)
            if count:
                logger.info(f"Removed {count} old proxies (last_seen before {cutoff})")
            return count

    async def remove_invalid_proxies(self) -> int:
        """Remove proxies with invalid IP or port format."""
        async with async_session() as session:
            result = await session.execute(
                delete(Proxy).where(
                    (Proxy.port < 1) | (Proxy.port > 65535)
                ).returning(Proxy.id)
            )
            deleted = result.all()
            await session.commit()
            count = len(deleted)
            if count:
                logger.info(f"Removed {count} invalid proxies")
            return count

    async def trim_check_history(self, max_records_per_proxy: int = 50) -> int:
        """Keep only the latest N check history records per proxy."""
        async with async_session() as session:
            subq = (
                select(CheckHistory.id)
                .where(CheckHistory.proxy_id == Proxy.id)
                .order_by(CheckHistory.checked_at.desc())
                .offset(max_records_per_proxy)
                .correlate(Proxy)
                .scalar_subquery()
            )

            proxy_ids = await session.execute(
                select(Proxy.id).where(
                    select(func.count(CheckHistory.id))
                    .where(CheckHistory.proxy_id == Proxy.id)
                    .correlate(Proxy)
                    .scalar_subquery()
                    > max_records_per_proxy
                )
            )
            pids = [r[0] for r in proxy_ids.all()]

            total_deleted = 0
            for pid in pids:
                keep_ids = await session.execute(
                    select(CheckHistory.id)
                    .where(CheckHistory.proxy_id == pid)
                    .order_by(CheckHistory.checked_at.desc())
                    .limit(max_records_per_proxy)
                )
                keep = [r[0] for r in keep_ids.all()]

                if keep:
                    result = await session.execute(
                        delete(CheckHistory).where(
                            CheckHistory.proxy_id == pid,
                            CheckHistory.id.notin_(keep),
                        ).returning(CheckHistory.id)
                    )
                    total_deleted += len(result.all())

            await session.commit()
            if total_deleted:
                logger.info(f"Trimmed {total_deleted} old check history records")
            return total_deleted

    async def run_cleanup(self) -> dict:
        """Run all cleanup tasks."""
        dead_removed = await self.remove_dead_proxies()
        old_removed = await self.remove_old_proxies()
        invalid_removed = await self.remove_invalid_proxies()
        history_trimmed = await self.trim_check_history()

        return {
            "dead_removed": dead_removed,
            "old_removed": old_removed,
            "invalid_removed": invalid_removed,
            "history_trimmed": history_trimmed,
        }


cleaner_instance = ProxyCleaner()
