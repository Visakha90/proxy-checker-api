"""
Internal Audit Logging Service.

Logs all security-relevant operations:
- Login attempts (success/failure)
- User management (create, disable, delete, role change)
- Downloads
- Proxy operations (scrape trigger, check trigger)
- Settings changes
- API key operations
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select, func, desc

from app.core.database import async_session
from app.models.api_models import APIRequestLog

logger = logging.getLogger(__name__)

# Reuse APIRequestLog table for audit entries with a specific convention:
# endpoint = "audit:<category>" for audit-specific entries


class AuditService:
    """Records and queries audit trail for all internal operations."""

    async def log(
        self,
        action: str,
        user: str,
        detail: str = "",
        ip_address: str | None = None,
        success: bool = True,
    ):
        """
        Record an audit event.

        Args:
            action: Category.action (e.g. "auth.login", "user.create", "download.http")
            user: Username or identifier of the actor
            detail: Human-readable description
            ip_address: Client IP
            success: Whether the action succeeded
        """
        async with async_session() as session:
            entry = APIRequestLog(
                api_key_str=user,
                endpoint=f"audit:{action}",
                method="AUDIT",
                status_code=200 if success else 403,
                response_time_ms=0,
                response_bytes=0,
                ip_address=ip_address,
                user_agent=detail,
                error_message=None if success else detail,
            )
            session.add(entry)
            await session.commit()

        level = logging.INFO if success else logging.WARNING
        logger.log(level, f"AUDIT [{action}] user={user} success={success} {detail}")

    async def get_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        action_filter: str | None = None,
        user_filter: str | None = None,
    ) -> tuple[list[dict], int]:
        """Query audit logs with optional filtering."""
        async with async_session() as session:
            query = select(APIRequestLog).where(
                APIRequestLog.endpoint.startswith("audit:")
            )
            count_query = select(func.count(APIRequestLog.id)).where(
                APIRequestLog.endpoint.startswith("audit:")
            )

            if action_filter:
                query = query.where(APIRequestLog.endpoint.contains(action_filter))
                count_query = count_query.where(APIRequestLog.endpoint.contains(action_filter))
            if user_filter:
                query = query.where(APIRequestLog.api_key_str == user_filter)
                count_query = count_query.where(APIRequestLog.api_key_str == user_filter)

            total = await session.scalar(count_query) or 0
            query = query.order_by(desc(APIRequestLog.created_at)).offset(offset).limit(limit)
            result = await session.execute(query)
            logs = result.scalars().all()

        return [
            {
                "id": log.id,
                "action": log.endpoint.replace("audit:", ""),
                "user": log.api_key_str,
                "detail": log.user_agent or "",
                "ip_address": log.ip_address,
                "success": log.status_code == 200,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ], total


audit = AuditService()
