"""
API Usage Tracking and Analytics Service.

Records every request for dashboard analytics:
- Request counts per endpoint
- Bandwidth tracking
- Response time percentiles
- Error rates
- Geographic distribution
"""

import json
import logging
import time
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, desc, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.api_models import APIRequestLog, APIUsageDaily, APIKey

logger = logging.getLogger(__name__)


class APIUsageService:
    """Tracks and aggregates API usage for dashboard and billing."""

    async def log_request(
        self,
        api_key_id: int | None,
        api_key_str: str | None,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: float,
        response_bytes: int,
        ip_address: str | None,
        user_agent: str | None,
        query_params: str | None,
        error_message: str | None = None,
    ):
        """Log an API request."""
        async with async_session() as session:
            log = APIRequestLog(
                api_key_id=api_key_id,
                api_key_str=api_key_str,
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                response_time_ms=response_time_ms,
                response_bytes=response_bytes,
                ip_address=ip_address,
                user_agent=user_agent,
                query_params=query_params,
                error_message=error_message,
            )
            session.add(log)
            await session.commit()

        # Update bandwidth on API key
        if api_key_id:
            async with async_session() as session:
                from sqlalchemy import update
                await session.execute(
                    update(APIKey)
                    .where(APIKey.id == api_key_id)
                    .values(bandwidth_bytes=APIKey.bandwidth_bytes + response_bytes)
                )
                await session.commit()

        # Update Redis counters for real-time dashboard
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pipe = redis_client.pipeline()
        pipe.incr(f"api:requests:total:{today}")
        pipe.expire(f"api:requests:total:{today}", 172800)
        pipe.incr(f"api:requests:endpoint:{endpoint}:{today}")
        pipe.expire(f"api:requests:endpoint:{endpoint}:{today}", 172800)
        if status_code >= 400:
            pipe.incr(f"api:errors:{today}")
            pipe.expire(f"api:errors:{today}", 172800)
        await pipe.execute()

    async def get_dashboard_stats(self) -> dict:
        """Get real-time API dashboard statistics."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

        # From Redis (real-time)
        today_requests = int(await redis_client.get(f"api:requests:total:{today}") or 0)
        today_errors = int(await redis_client.get(f"api:errors:{today}") or 0)
        yesterday_requests = int(await redis_client.get(f"api:requests:total:{yesterday}") or 0)

        # From database
        async with async_session() as session:
            total_keys = await session.scalar(select(func.count(APIKey.id))) or 0
            active_keys = await session.scalar(
                select(func.count(APIKey.id)).where(APIKey.is_active == True)
            ) or 0
            total_requests = await session.scalar(
                select(func.sum(APIKey.requests_total))
            ) or 0
            total_bandwidth = await session.scalar(
                select(func.sum(APIKey.bandwidth_bytes))
            ) or 0

            # Average response time today
            avg_response = await session.scalar(
                select(func.avg(APIRequestLog.response_time_ms))
                .where(APIRequestLog.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0))
            ) or 0.0

            # Top endpoints today
            top_endpoints_result = await session.execute(
                select(
                    APIRequestLog.endpoint,
                    func.count(APIRequestLog.id).label("count")
                )
                .where(APIRequestLog.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0))
                .group_by(APIRequestLog.endpoint)
                .order_by(desc("count"))
                .limit(10)
            )
            top_endpoints = [
                {"endpoint": row.endpoint, "count": row.count}
                for row in top_endpoints_result.all()
            ]

            # Top users today
            top_users_result = await session.execute(
                select(
                    APIRequestLog.api_key_str,
                    func.count(APIRequestLog.id).label("count")
                )
                .where(
                    APIRequestLog.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0),
                    APIRequestLog.api_key_str.isnot(None),
                )
                .group_by(APIRequestLog.api_key_str)
                .order_by(desc("count"))
                .limit(10)
            )
            top_users = [
                {"key": row.api_key_str[:12] + "..." if row.api_key_str else "guest", "count": row.count}
                for row in top_users_result.all()
            ]

        return {
            "today_requests": today_requests,
            "today_errors": today_errors,
            "yesterday_requests": yesterday_requests,
            "total_keys": total_keys,
            "active_keys": active_keys,
            "total_requests_all_time": total_requests,
            "total_bandwidth_bytes": total_bandwidth,
            "avg_response_time_ms": round(avg_response, 2),
            "top_endpoints": top_endpoints,
            "top_users": top_users,
            "error_rate": round(today_errors / max(today_requests, 1) * 100, 2),
        }

    async def get_usage_history(self, days: int = 30) -> list[dict]:
        """Get daily usage history."""
        async with async_session() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            result = await session.execute(
                select(APIUsageDaily)
                .where(APIUsageDaily.created_at >= cutoff)
                .order_by(APIUsageDaily.date)
                .limit(days * 100)
            )
            rows = result.scalars().all()

            # Aggregate by date
            daily: dict[str, dict] = {}
            for row in rows:
                if row.date not in daily:
                    daily[row.date] = {"date": row.date, "requests": 0, "bandwidth": 0, "errors": 0}
                daily[row.date]["requests"] += row.requests
                daily[row.date]["bandwidth"] += row.bandwidth_bytes
                daily[row.date]["errors"] += row.errors

            return list(daily.values())

    async def get_recent_requests(self, limit: int = 50, api_key_id: int | None = None) -> list[dict]:
        """Get recent API requests."""
        async with async_session() as session:
            query = select(APIRequestLog).order_by(desc(APIRequestLog.created_at)).limit(limit)
            if api_key_id:
                query = query.where(APIRequestLog.api_key_id == api_key_id)

            result = await session.execute(query)
            logs = result.scalars().all()

            return [
                {
                    "id": log.id,
                    "endpoint": log.endpoint,
                    "method": log.method,
                    "status_code": log.status_code,
                    "response_time_ms": log.response_time_ms,
                    "response_bytes": log.response_bytes,
                    "ip_address": log.ip_address,
                    "api_key": log.api_key_str[:12] + "..." if log.api_key_str else "guest",
                    "created_at": log.created_at.isoformat() if log.created_at else None,
                    "error": log.error_message,
                }
                for log in logs
            ]


api_usage = APIUsageService()
