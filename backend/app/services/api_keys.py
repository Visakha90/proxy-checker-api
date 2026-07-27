"""
API Key Management Service.

Handles creation, validation, rotation, and quota tracking for public API keys.
Supports tiered rate limiting: guest (100/hr), free (1000/day), premium (unlimited).
"""

import secrets
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.api_models import APIKey

logger = logging.getLogger(__name__)

TIER_LIMITS = {
    "guest": {"hourly": 100, "daily": -1},
    "free": {"hourly": -1, "daily": 1000},
    "premium": {"hourly": -1, "daily": -1},
}


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    return f"pc_{secrets.token_hex(24)}"


class APIKeyService:
    """Manages API keys with Redis-backed rate limiting."""

    async def create_key(
        self,
        name: str,
        user_id: str,
        tier: str = "free",
        quota_daily: int | None = None,
        expires_days: int | None = None,
    ) -> APIKey:
        """Create a new API key."""
        key = generate_api_key()

        if quota_daily is None:
            quota_daily = TIER_LIMITS.get(tier, TIER_LIMITS["free"]).get("daily", 1000)

        expires_at = None
        if expires_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

        async with async_session() as session:
            api_key = APIKey(
                key=key,
                name=name,
                user_id=user_id,
                tier=tier,
                quota_daily=quota_daily if quota_daily != -1 else -1,
                expires_at=expires_at,
            )
            session.add(api_key)
            await session.commit()
            await session.refresh(api_key)
            logger.info(f"Created API key '{name}' for user '{user_id}' (tier={tier})")
            return api_key

    async def validate_key(self, key: str) -> APIKey | None:
        """Validate an API key and check if it's active and not expired."""
        async with async_session() as session:
            result = await session.execute(
                select(APIKey).where(APIKey.key == key, APIKey.is_active == True)
            )
            api_key = result.scalar_one_or_none()

            if not api_key:
                return None

            if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
                return None

            return api_key

    async def check_rate_limit(self, key: str, tier: str) -> tuple[bool, dict]:
        """
        Check rate limit using Redis sliding window.

        Returns (allowed, info) where info contains remaining quota.
        """
        now = datetime.now(timezone.utc)
        limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

        info = {"tier": tier, "hourly_limit": limits["hourly"], "daily_limit": limits["daily"]}

        # Check hourly limit
        if limits["hourly"] > 0:
            hourly_key = f"ratelimit:hourly:{key}:{now.strftime('%Y%m%d%H')}"
            count = await redis_client.incr(hourly_key)
            if count == 1:
                await redis_client.expire(hourly_key, 3600)
            info["hourly_remaining"] = max(0, limits["hourly"] - count)
            if count > limits["hourly"]:
                return False, info

        # Check daily limit
        if limits["daily"] > 0:
            daily_key = f"ratelimit:daily:{key}:{now.strftime('%Y%m%d')}"
            count = await redis_client.incr(daily_key)
            if count == 1:
                await redis_client.expire(daily_key, 86400)
            info["daily_remaining"] = max(0, limits["daily"] - count)
            if count > limits["daily"]:
                return False, info
        else:
            info["daily_remaining"] = -1  # unlimited

        return True, info

    async def record_usage(self, key_id: int, ip: str | None = None):
        """Record API key usage."""
        async with async_session() as session:
            await session.execute(
                update(APIKey)
                .where(APIKey.id == key_id)
                .values(
                    requests_today=APIKey.requests_today + 1,
                    requests_total=APIKey.requests_total + 1,
                    last_used_at=datetime.now(timezone.utc),
                    last_ip=ip,
                )
            )
            await session.commit()

    async def get_key(self, key_id: int) -> APIKey | None:
        """Get an API key by ID."""
        async with async_session() as session:
            return await session.get(APIKey, key_id)

    async def get_keys_by_user(self, user_id: str) -> list[APIKey]:
        """Get all API keys for a user."""
        async with async_session() as session:
            result = await session.execute(
                select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
            )
            return result.scalars().all()

    async def list_all_keys(self, limit: int = 100, offset: int = 0) -> tuple[list[APIKey], int]:
        """List all API keys (admin)."""
        async with async_session() as session:
            total = await session.scalar(select(func.count(APIKey.id))) or 0
            result = await session.execute(
                select(APIKey).order_by(APIKey.created_at.desc()).offset(offset).limit(limit)
            )
            return result.scalars().all(), total

    async def regenerate_key(self, key_id: int) -> APIKey | None:
        """Regenerate an API key (new key, same settings)."""
        async with async_session() as session:
            api_key = await session.get(APIKey, key_id)
            if not api_key:
                return None
            new_key = generate_api_key()
            api_key.key = new_key
            api_key.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(api_key)
            logger.info(f"Regenerated API key ID={key_id}")
            return api_key

    async def delete_key(self, key_id: int) -> bool:
        """Delete an API key."""
        async with async_session() as session:
            result = await session.execute(
                delete(APIKey).where(APIKey.id == key_id)
            )
            await session.commit()
            return result.rowcount > 0

    async def deactivate_key(self, key_id: int) -> bool:
        """Deactivate an API key."""
        async with async_session() as session:
            result = await session.execute(
                update(APIKey).where(APIKey.id == key_id).values(is_active=False)
            )
            await session.commit()
            return result.rowcount > 0

    async def reset_daily_counters(self):
        """Reset daily request counters (call at midnight)."""
        async with async_session() as session:
            await session.execute(
                update(APIKey).values(requests_today=0)
            )
            await session.commit()
            logger.info("Reset daily API key counters")


api_key_service = APIKeyService()
