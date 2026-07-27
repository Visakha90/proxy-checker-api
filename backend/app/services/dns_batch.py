"""
Batch DNS Operations with Rollback Support.

Handles batch create, update, and delete operations with:
- Atomic-like behavior (best-effort rollback on failure)
- State snapshots before each operation
- Full rollback capability per batch
- Audit trail integration
"""

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.dns_models import DNSRollbackSnapshot
from app.services.namecom import namecom_client, DNSRecord, NamecomError
from app.services.dns_audit import dns_audit, DNSAction

logger = logging.getLogger(__name__)


class BatchOperationType(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


@dataclass
class BatchOperation:
    """A single operation within a batch."""
    operation: BatchOperationType
    host: str
    record_type: str
    answer: str
    ttl: int = 300
    priority: int | None = None
    record_id: int | None = None  # Required for update/delete


@dataclass
class BatchOperationResult:
    """Result of a single operation in the batch."""
    index: int
    operation: BatchOperationType
    success: bool
    record: DNSRecord | None = None
    error: str | None = None


@dataclass
class BatchResult:
    """Result of an entire batch operation."""
    batch_id: str
    domain: str
    total_operations: int
    successful: int
    failed: int
    results: list[BatchOperationResult]
    rollback_available: bool


class DNSBatchService:
    """
    Manages batch DNS operations with rollback capability.

    Each batch:
    1. Generates a unique batch ID
    2. Snapshots current state before each operation
    3. Executes all operations
    4. On partial failure, offers rollback of completed operations
    """

    async def execute_batch(
        self,
        domain: str,
        operations: list[BatchOperation],
        operator: str = "admin",
        ip_address: str | None = None,
        stop_on_failure: bool = False,
    ) -> BatchResult:
        """
        Execute a batch of DNS operations.

        Args:
            domain: The domain to operate on
            operations: List of BatchOperation to execute
            operator: Username performing the operation
            ip_address: IP address of the requester
            stop_on_failure: If True, stop executing after first failure

        Returns:
            BatchResult with per-operation results
        """
        batch_id = str(uuid.uuid4())[:16]
        logger.info(
            f"Starting batch {batch_id}: {len(operations)} operations on {domain} "
            f"by {operator}"
        )

        results: list[BatchOperationResult] = []
        successful = 0
        failed = 0

        for i, op in enumerate(operations):
            try:
                result = await self._execute_single(
                    batch_id=batch_id,
                    domain=domain,
                    operation=op,
                    index=i,
                    operator=operator,
                    ip_address=ip_address,
                )
                results.append(result)

                if result.success:
                    successful += 1
                else:
                    failed += 1
                    if stop_on_failure:
                        logger.warning(
                            f"Batch {batch_id}: stopping on failure at operation {i}"
                        )
                        # Mark remaining as skipped
                        for j in range(i + 1, len(operations)):
                            results.append(BatchOperationResult(
                                index=j,
                                operation=operations[j].operation,
                                success=False,
                                error="Skipped due to previous failure",
                            ))
                            failed += 1
                        break

            except Exception as e:
                logger.error(f"Batch {batch_id} operation {i} unexpected error: {e}")
                results.append(BatchOperationResult(
                    index=i,
                    operation=op.operation,
                    success=False,
                    error=str(e),
                ))
                failed += 1
                if stop_on_failure:
                    for j in range(i + 1, len(operations)):
                        results.append(BatchOperationResult(
                            index=j,
                            operation=operations[j].operation,
                            success=False,
                            error="Skipped due to previous failure",
                        ))
                        failed += 1
                    break

        # Log batch completion
        batch_action = DNSAction.BATCH_CREATE
        if all(op.operation == BatchOperationType.UPDATE for op in operations):
            batch_action = DNSAction.BATCH_UPDATE
        elif all(op.operation == BatchOperationType.DELETE for op in operations):
            batch_action = DNSAction.BATCH_DELETE

        await dns_audit.log(
            action=batch_action,
            domain=domain,
            operator=operator,
            ip_address=ip_address,
            success=failed == 0,
            error_message=f"{failed} operations failed" if failed > 0 else None,
            metadata={
                "batch_id": batch_id,
                "total": len(operations),
                "successful": successful,
                "failed": failed,
            },
        )

        logger.info(
            f"Batch {batch_id} complete: {successful} succeeded, {failed} failed"
        )

        return BatchResult(
            batch_id=batch_id,
            domain=domain,
            total_operations=len(operations),
            successful=successful,
            failed=failed,
            results=results,
            rollback_available=successful > 0,
        )

    async def _execute_single(
        self,
        batch_id: str,
        domain: str,
        operation: BatchOperation,
        index: int,
        operator: str,
        ip_address: str | None,
    ) -> BatchOperationResult:
        """Execute a single operation within a batch, with snapshot."""

        if operation.operation == BatchOperationType.CREATE:
            return await self._execute_create(
                batch_id, domain, operation, index, operator, ip_address
            )
        elif operation.operation == BatchOperationType.UPDATE:
            return await self._execute_update(
                batch_id, domain, operation, index, operator, ip_address
            )
        elif operation.operation == BatchOperationType.DELETE:
            return await self._execute_delete(
                batch_id, domain, operation, index, operator, ip_address
            )
        else:
            return BatchOperationResult(
                index=index,
                operation=operation.operation,
                success=False,
                error=f"Unknown operation type: {operation.operation}",
            )

    async def _execute_create(
        self, batch_id: str, domain: str, op: BatchOperation,
        index: int, operator: str, ip_address: str | None,
    ) -> BatchOperationResult:
        """Execute a create operation with snapshot."""
        try:
            record = await namecom_client.create_record(
                domain=domain,
                host=op.host,
                record_type=op.record_type,
                answer=op.answer,
                ttl=op.ttl,
                priority=op.priority,
            )

            # Snapshot for rollback (rollback = delete this record)
            await self._save_snapshot(
                batch_id=batch_id,
                domain=domain,
                operation="create",
                record_id=record.id,
                previous_state=None,
                new_state=record.to_dict(),
            )

            await dns_audit.log(
                action=DNSAction.CREATE,
                domain=domain,
                record_type=op.record_type,
                record_id=record.id,
                host=op.host,
                after_state=record.to_dict(),
                operator=operator,
                ip_address=ip_address,
            )

            return BatchOperationResult(
                index=index, operation=op.operation, success=True, record=record
            )
        except NamecomError as e:
            await dns_audit.log(
                action=DNSAction.CREATE,
                domain=domain,
                record_type=op.record_type,
                host=op.host,
                operator=operator,
                ip_address=ip_address,
                success=False,
                error_message=e.message,
            )
            return BatchOperationResult(
                index=index, operation=op.operation, success=False, error=e.message
            )

    async def _execute_update(
        self, batch_id: str, domain: str, op: BatchOperation,
        index: int, operator: str, ip_address: str | None,
    ) -> BatchOperationResult:
        """Execute an update operation with snapshot."""
        if op.record_id is None:
            return BatchOperationResult(
                index=index, operation=op.operation, success=False,
                error="record_id required for update",
            )

        try:
            # Snapshot current state
            current = await namecom_client.get_record(domain, op.record_id)
            before_state = current.to_dict()

            record = await namecom_client.update_record(
                domain=domain,
                record_id=op.record_id,
                host=op.host,
                record_type=op.record_type,
                answer=op.answer,
                ttl=op.ttl,
                priority=op.priority,
            )

            await self._save_snapshot(
                batch_id=batch_id,
                domain=domain,
                operation="update",
                record_id=op.record_id,
                previous_state=before_state,
                new_state=record.to_dict(),
            )

            await dns_audit.log(
                action=DNSAction.UPDATE,
                domain=domain,
                record_type=op.record_type,
                record_id=op.record_id,
                host=op.host,
                before_state=before_state,
                after_state=record.to_dict(),
                operator=operator,
                ip_address=ip_address,
            )

            return BatchOperationResult(
                index=index, operation=op.operation, success=True, record=record
            )
        except NamecomError as e:
            await dns_audit.log(
                action=DNSAction.UPDATE,
                domain=domain,
                record_type=op.record_type,
                record_id=op.record_id,
                host=op.host,
                operator=operator,
                ip_address=ip_address,
                success=False,
                error_message=e.message,
            )
            return BatchOperationResult(
                index=index, operation=op.operation, success=False, error=e.message
            )

    async def _execute_delete(
        self, batch_id: str, domain: str, op: BatchOperation,
        index: int, operator: str, ip_address: str | None,
    ) -> BatchOperationResult:
        """Execute a delete operation with snapshot."""
        if op.record_id is None:
            return BatchOperationResult(
                index=index, operation=op.operation, success=False,
                error="record_id required for delete",
            )

        try:
            # Snapshot current state before deletion
            current = await namecom_client.get_record(domain, op.record_id)
            before_state = current.to_dict()

            await namecom_client.delete_record(domain, op.record_id)

            await self._save_snapshot(
                batch_id=batch_id,
                domain=domain,
                operation="delete",
                record_id=op.record_id,
                previous_state=before_state,
                new_state=None,
            )

            await dns_audit.log(
                action=DNSAction.DELETE,
                domain=domain,
                record_type=current.record_type,
                record_id=op.record_id,
                host=current.host,
                before_state=before_state,
                operator=operator,
                ip_address=ip_address,
            )

            return BatchOperationResult(
                index=index, operation=op.operation, success=True
            )
        except NamecomError as e:
            await dns_audit.log(
                action=DNSAction.DELETE,
                domain=domain,
                record_id=op.record_id,
                operator=operator,
                ip_address=ip_address,
                success=False,
                error_message=e.message,
            )
            return BatchOperationResult(
                index=index, operation=op.operation, success=False, error=e.message
            )

    async def _save_snapshot(
        self,
        batch_id: str,
        domain: str,
        operation: str,
        record_id: int | None,
        previous_state: dict | None,
        new_state: dict | None,
    ):
        """Save a rollback snapshot to the database."""
        async with async_session() as session:
            snapshot = DNSRollbackSnapshot(
                batch_id=batch_id,
                domain=domain,
                operation=operation,
                record_id=record_id,
                previous_state=json.dumps(previous_state) if previous_state else None,
                new_state=json.dumps(new_state) if new_state else None,
            )
            session.add(snapshot)
            await session.commit()

    async def rollback_batch(
        self,
        batch_id: str,
        operator: str = "admin",
        ip_address: str | None = None,
    ) -> dict:
        """
        Rollback all operations in a batch.

        - Created records are deleted
        - Updated records are reverted to previous state
        - Deleted records are re-created

        Args:
            batch_id: The batch ID to rollback
            operator: Username performing the rollback
            ip_address: IP address of the requester

        Returns:
            Summary of rollback results
        """
        logger.info(f"Starting rollback of batch {batch_id} by {operator}")

        async with async_session() as session:
            result = await session.execute(
                select(DNSRollbackSnapshot)
                .where(
                    DNSRollbackSnapshot.batch_id == batch_id,
                    DNSRollbackSnapshot.rolled_back == False,
                )
                .order_by(DNSRollbackSnapshot.id.desc())  # Reverse order
            )
            snapshots = result.scalars().all()

        if not snapshots:
            return {"error": "No rollback snapshots found for this batch", "rolled_back": 0}

        rolled_back = 0
        errors = []

        for snapshot in snapshots:
            try:
                if snapshot.operation == "create" and snapshot.record_id:
                    # Rollback create = delete
                    await namecom_client.delete_record(snapshot.domain, snapshot.record_id)
                    rolled_back += 1

                elif snapshot.operation == "update" and snapshot.previous_state:
                    # Rollback update = restore previous state
                    prev = json.loads(snapshot.previous_state)
                    await namecom_client.update_record(
                        domain=snapshot.domain,
                        record_id=snapshot.record_id,
                        host=prev.get("host"),
                        record_type=prev.get("record_type"),
                        answer=prev.get("answer"),
                        ttl=prev.get("ttl"),
                        priority=prev.get("priority"),
                    )
                    rolled_back += 1

                elif snapshot.operation == "delete" and snapshot.previous_state:
                    # Rollback delete = re-create
                    prev = json.loads(snapshot.previous_state)
                    await namecom_client.create_record(
                        domain=snapshot.domain,
                        host=prev.get("host", ""),
                        record_type=prev.get("record_type", "A"),
                        answer=prev.get("answer", ""),
                        ttl=prev.get("ttl", 300),
                        priority=prev.get("priority"),
                    )
                    rolled_back += 1

                # Mark as rolled back
                async with async_session() as session:
                    await session.execute(
                        update(DNSRollbackSnapshot)
                        .where(DNSRollbackSnapshot.id == snapshot.id)
                        .values(
                            rolled_back=True,
                            rolled_back_at=datetime.now(timezone.utc),
                        )
                    )
                    await session.commit()

            except NamecomError as e:
                error_msg = f"Rollback failed for snapshot {snapshot.id}: {e.message}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Audit the rollback
        domain = snapshots[0].domain if snapshots else "unknown"
        await dns_audit.log(
            action=DNSAction.ROLLBACK,
            domain=domain,
            operator=operator,
            ip_address=ip_address,
            success=len(errors) == 0,
            error_message="; ".join(errors) if errors else None,
            metadata={
                "batch_id": batch_id,
                "rolled_back": rolled_back,
                "errors": len(errors),
            },
        )

        logger.info(
            f"Rollback of batch {batch_id} complete: "
            f"{rolled_back} rolled back, {len(errors)} errors"
        )

        return {
            "batch_id": batch_id,
            "rolled_back": rolled_back,
            "errors": errors,
            "total_snapshots": len(snapshots),
        }

    async def get_batch_history(self, domain: str | None = None, limit: int = 50) -> list[dict]:
        """Get batch operation history."""
        async with async_session() as session:
            query = select(DNSRollbackSnapshot)
            if domain:
                query = query.where(DNSRollbackSnapshot.domain == domain)
            query = query.order_by(DNSRollbackSnapshot.created_at.desc()).limit(limit)

            result = await session.execute(query)
            snapshots = result.scalars().all()

            # Group by batch_id
            batches: dict[str, list] = {}
            for s in snapshots:
                if s.batch_id not in batches:
                    batches[s.batch_id] = []
                batches[s.batch_id].append({
                    "id": s.id,
                    "operation": s.operation,
                    "record_id": s.record_id,
                    "rolled_back": s.rolled_back,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                })

            return [
                {"batch_id": bid, "operations": ops, "domain": domain}
                for bid, ops in batches.items()
            ]


# Singleton instance
dns_batch = DNSBatchService()
