"""
DNS Audit Logging Service.

Records every DNS operation with full context for compliance and debugging.
Supports querying audit history with filtering and pagination.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.dns_models import DNSAuditLog

logger = logging.getLogger(__name__)


class DNSAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    BATCH_CREATE = "batch_create"
    BATCH_UPDATE = "batch_update"
    BATCH_DELETE = "batch_delete"
    ROLLBACK = "rollback"
    PROPAGATION_CHECK = "propagation_check"
    SSL_DEPLOY = "ssl_deploy"


class DNSAuditService:
    """
    Audit logging for all DNS operations.

    Every create, update, delete, batch operation, and rollback is logged
    with full before/after state, operator identity, and timestamps.
    """

    async def log(
        self,
        action: DNSAction,
        domain: str,
        record_type: str | None = None,
        record_id: int | None = None,
        host: str | None = None,
        before_state: dict | None = None,
        after_state: dict | None = None,
        operator: str = "system",
        ip_address: str | None = None,
        success: bool = True,
        error_message: str | None = None,
        metadata: dict | None = None,
    ) -> DNSAuditLog:
        """
        Log a DNS operation to the audit trail.

        Args:
            action: The type of DNS action performed
            domain: The domain affected
            record_type: DNS record type (A, CNAME, etc.)
            record_id: The Name.com record ID (if applicable)
            host: The hostname affected
            before_state: Record state before the operation
            after_state: Record state after the operation
            operator: Username of the operator
            ip_address: IP address of the requester
            success: Whether the operation succeeded
            error_message: Error details if failed
            metadata: Additional context

        Returns:
            The created audit log entry
        """
        import json

        async with async_session() as session:
            entry = DNSAuditLog(
                action=action.value,
                domain=domain,
                record_type=record_type,
                record_id=record_id,
                host=host,
                before_state=json.dumps(before_state) if before_state else None,
                after_state=json.dumps(after_state) if after_state else None,
                operator=operator,
                ip_address=ip_address,
                success=success,
                error_message=error_message,
                metadata_=json.dumps(metadata) if metadata else None,
            )
            session.add(entry)
            await session.commit()
            await session.refresh(entry)

            log_level = logging.INFO if success else logging.ERROR
            logger.log(
                log_level,
                f"DNS Audit: {action.value} {record_type or ''} {host or ''}.{domain} "
                f"by {operator} - {'SUCCESS' if success else 'FAILED'}"
                f"{f': {error_message}' if error_message else ''}"
            )

            return entry

    async def get_logs(
        self,
        domain: str | None = None,
        action: str | None = None,
        operator: str | None = None,
        success: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[DNSAuditLog], int]:
        """
        Query audit logs with optional filtering.

        Returns:
            Tuple of (logs list, total count)
        """
        async with async_session() as session:
            query = select(DNSAuditLog)
            count_query = select(func.count(DNSAuditLog.id))

            if domain:
                query = query.where(DNSAuditLog.domain == domain)
                count_query = count_query.where(DNSAuditLog.domain == domain)
            if action:
                query = query.where(DNSAuditLog.action == action)
                count_query = count_query.where(DNSAuditLog.action == action)
            if operator:
                query = query.where(DNSAuditLog.operator == operator)
                count_query = count_query.where(DNSAuditLog.operator == operator)
            if success is not None:
                query = query.where(DNSAuditLog.success == success)
                count_query = count_query.where(DNSAuditLog.success == success)

            total = await session.scalar(count_query) or 0
            query = query.order_by(desc(DNSAuditLog.created_at)).offset(offset).limit(limit)
            result = await session.execute(query)
            logs = result.scalars().all()

            return logs, total

    async def get_log_by_id(self, log_id: int) -> DNSAuditLog | None:
        """Get a specific audit log entry."""
        async with async_session() as session:
            return await session.get(DNSAuditLog, log_id)

    async def get_recent_for_domain(self, domain: str, limit: int = 50) -> list[DNSAuditLog]:
        """Get recent audit entries for a domain."""
        async with async_session() as session:
            result = await session.execute(
                select(DNSAuditLog)
                .where(DNSAuditLog.domain == domain)
                .order_by(desc(DNSAuditLog.created_at))
                .limit(limit)
            )
            return result.scalars().all()


# Singleton instance
dns_audit = DNSAuditService()
