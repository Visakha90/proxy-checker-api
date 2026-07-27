"""
Unit tests for batch DNS operations and rollback.

Tests cover:
- Batch create operations
- Batch update operations
- Batch delete operations
- Mixed operation batches
- Stop on failure behavior
- Rollback of batch operations
- Snapshot persistence
"""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.dns_batch import (
    DNSBatchService,
    BatchOperation,
    BatchOperationType,
    BatchResult,
)
from app.services.namecom import DNSRecord, NamecomError


@pytest.fixture
def batch_service():
    return DNSBatchService()


@pytest.fixture
def mock_record():
    return DNSRecord(
        id=100,
        domain_name="example.com",
        host="www",
        fqdn="www.example.com.",
        record_type="A",
        answer="1.2.3.4",
        ttl=300,
        priority=None,
    )


class TestBatchCreate:
    """Tests for batch create operations."""

    @pytest.mark.asyncio
    async def test_batch_create_single(self, batch_service, mock_record):
        operations = [
            BatchOperation(
                operation=BatchOperationType.CREATE,
                host="www",
                record_type="A",
                answer="1.2.3.4",
                ttl=300,
            )
        ]

        with patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit, \
             patch.object(batch_service, "_save_snapshot", new_callable=AsyncMock):
            mock_client.create_record = AsyncMock(return_value=mock_record)
            mock_audit.log = AsyncMock()

            result = await batch_service.execute_batch(
                domain="example.com",
                operations=operations,
                operator="test_admin",
            )

        assert result.successful == 1
        assert result.failed == 0
        assert result.results[0].success is True
        assert result.results[0].record.id == 100

    @pytest.mark.asyncio
    async def test_batch_create_multiple(self, batch_service):
        records = [
            DNSRecord(id=i, domain_name="example.com", host=f"sub{i}",
                      fqdn=f"sub{i}.example.com.", record_type="A",
                      answer=f"10.0.0.{i}", ttl=300)
            for i in range(1, 4)
        ]

        operations = [
            BatchOperation(
                operation=BatchOperationType.CREATE,
                host=f"sub{i}",
                record_type="A",
                answer=f"10.0.0.{i}",
            )
            for i in range(1, 4)
        ]

        call_count = [0]

        async def mock_create(*args, **kwargs):
            r = records[call_count[0]]
            call_count[0] += 1
            return r

        with patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit, \
             patch.object(batch_service, "_save_snapshot", new_callable=AsyncMock):
            mock_client.create_record = AsyncMock(side_effect=mock_create)
            mock_audit.log = AsyncMock()

            result = await batch_service.execute_batch(
                domain="example.com",
                operations=operations,
            )

        assert result.total_operations == 3
        assert result.successful == 3
        assert result.failed == 0

    @pytest.mark.asyncio
    async def test_batch_create_partial_failure(self, batch_service, mock_record):
        operations = [
            BatchOperation(operation=BatchOperationType.CREATE, host="ok", record_type="A", answer="1.1.1.1"),
            BatchOperation(operation=BatchOperationType.CREATE, host="fail", record_type="A", answer="2.2.2.2"),
            BatchOperation(operation=BatchOperationType.CREATE, host="ok2", record_type="A", answer="3.3.3.3"),
        ]

        call_count = [0]

        async def mock_create(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise NamecomError(400, "Invalid record")
            return mock_record

        with patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit, \
             patch.object(batch_service, "_save_snapshot", new_callable=AsyncMock):
            mock_client.create_record = AsyncMock(side_effect=mock_create)
            mock_audit.log = AsyncMock()

            result = await batch_service.execute_batch(
                domain="example.com",
                operations=operations,
                stop_on_failure=False,
            )

        assert result.successful == 2
        assert result.failed == 1
        assert result.results[1].success is False
        assert result.results[1].error == "Invalid record"


class TestBatchUpdate:
    """Tests for batch update operations."""

    @pytest.mark.asyncio
    async def test_batch_update_with_snapshot(self, batch_service, mock_record):
        updated_record = DNSRecord(
            id=100, domain_name="example.com", host="www",
            fqdn="www.example.com.", record_type="A",
            answer="5.6.7.8", ttl=600,
        )

        operations = [
            BatchOperation(
                operation=BatchOperationType.UPDATE,
                host="www",
                record_type="A",
                answer="5.6.7.8",
                ttl=600,
                record_id=100,
            )
        ]

        with patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit, \
             patch.object(batch_service, "_save_snapshot", new_callable=AsyncMock) as mock_snap:
            mock_client.get_record = AsyncMock(return_value=mock_record)
            mock_client.update_record = AsyncMock(return_value=updated_record)
            mock_audit.log = AsyncMock()

            result = await batch_service.execute_batch(
                domain="example.com", operations=operations
            )

        assert result.successful == 1
        # Verify snapshot was saved with before state
        mock_snap.assert_called_once()
        snap_kwargs = mock_snap.call_args[1]
        assert snap_kwargs["previous_state"]["answer"] == "1.2.3.4"
        assert snap_kwargs["new_state"]["answer"] == "5.6.7.8"

    @pytest.mark.asyncio
    async def test_batch_update_missing_record_id(self, batch_service):
        operations = [
            BatchOperation(
                operation=BatchOperationType.UPDATE,
                host="www",
                record_type="A",
                answer="5.6.7.8",
                record_id=None,  # Missing!
            )
        ]

        with patch("app.services.dns_batch.dns_audit") as mock_audit:
            mock_audit.log = AsyncMock()

            result = await batch_service.execute_batch(
                domain="example.com", operations=operations
            )

        assert result.failed == 1
        assert "record_id required" in result.results[0].error


class TestBatchDelete:
    """Tests for batch delete operations."""

    @pytest.mark.asyncio
    async def test_batch_delete_snapshots_before_state(self, batch_service, mock_record):
        operations = [
            BatchOperation(
                operation=BatchOperationType.DELETE,
                host="www",
                record_type="A",
                answer="",
                record_id=100,
            )
        ]

        with patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit, \
             patch.object(batch_service, "_save_snapshot", new_callable=AsyncMock) as mock_snap:
            mock_client.get_record = AsyncMock(return_value=mock_record)
            mock_client.delete_record = AsyncMock(return_value=None)
            mock_audit.log = AsyncMock()

            result = await batch_service.execute_batch(
                domain="example.com", operations=operations
            )

        assert result.successful == 1
        snap_kwargs = mock_snap.call_args[1]
        assert snap_kwargs["operation"] == "delete"
        assert snap_kwargs["previous_state"]["id"] == 100


class TestStopOnFailure:
    """Tests for stop_on_failure behavior."""

    @pytest.mark.asyncio
    async def test_stop_on_failure_skips_remaining(self, batch_service, mock_record):
        operations = [
            BatchOperation(operation=BatchOperationType.CREATE, host="a", record_type="A", answer="1.1.1.1"),
            BatchOperation(operation=BatchOperationType.CREATE, host="b", record_type="A", answer="2.2.2.2"),
            BatchOperation(operation=BatchOperationType.CREATE, host="c", record_type="A", answer="3.3.3.3"),
        ]

        call_count = [0]

        async def mock_create(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise NamecomError(500, "Server error")
            return mock_record

        with patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit, \
             patch.object(batch_service, "_save_snapshot", new_callable=AsyncMock):
            mock_client.create_record = AsyncMock(side_effect=mock_create)
            mock_audit.log = AsyncMock()

            result = await batch_service.execute_batch(
                domain="example.com",
                operations=operations,
                stop_on_failure=True,
            )

        assert result.successful == 0
        assert result.failed == 3  # 1 failed + 2 skipped
        assert result.results[0].error == "Server error"
        assert "Skipped" in result.results[1].error
        assert "Skipped" in result.results[2].error


class TestRollback:
    """Tests for batch rollback."""

    @pytest.mark.asyncio
    async def test_rollback_created_records(self, batch_service):
        """Rolling back creates should delete them."""
        from app.models.dns_models import DNSRollbackSnapshot

        mock_snapshot = MagicMock()
        mock_snapshot.id = 1
        mock_snapshot.batch_id = "abc123"
        mock_snapshot.domain = "example.com"
        mock_snapshot.operation = "create"
        mock_snapshot.record_id = 100
        mock_snapshot.previous_state = None
        mock_snapshot.new_state = json.dumps({"id": 100, "host": "www"})

        with patch("app.services.dns_batch.async_session") as mock_session_ctx, \
             patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit:

            # Mock the select query to return our snapshot
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_snapshot]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_client.delete_record = AsyncMock()
            mock_audit.log = AsyncMock()

            result = await batch_service.rollback_batch("abc123", operator="admin")

        assert result["rolled_back"] == 1
        mock_client.delete_record.assert_called_once_with("example.com", 100)

    @pytest.mark.asyncio
    async def test_rollback_updated_records(self, batch_service):
        """Rolling back updates should restore previous state."""
        mock_snapshot = MagicMock()
        mock_snapshot.id = 2
        mock_snapshot.batch_id = "def456"
        mock_snapshot.domain = "example.com"
        mock_snapshot.operation = "update"
        mock_snapshot.record_id = 200
        mock_snapshot.previous_state = json.dumps({
            "id": 200, "host": "api", "record_type": "A",
            "answer": "1.1.1.1", "ttl": 300, "priority": None,
        })
        mock_snapshot.new_state = json.dumps({"id": 200, "answer": "2.2.2.2"})

        with patch("app.services.dns_batch.async_session") as mock_session_ctx, \
             patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit:

            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_snapshot]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_client.update_record = AsyncMock(return_value=MagicMock())
            mock_audit.log = AsyncMock()

            result = await batch_service.rollback_batch("def456")

        assert result["rolled_back"] == 1
        mock_client.update_record.assert_called_once_with(
            domain="example.com",
            record_id=200,
            host="api",
            record_type="A",
            answer="1.1.1.1",
            ttl=300,
            priority=None,
        )

    @pytest.mark.asyncio
    async def test_rollback_deleted_records(self, batch_service):
        """Rolling back deletes should re-create the record."""
        mock_snapshot = MagicMock()
        mock_snapshot.id = 3
        mock_snapshot.batch_id = "ghi789"
        mock_snapshot.domain = "example.com"
        mock_snapshot.operation = "delete"
        mock_snapshot.record_id = 300
        mock_snapshot.previous_state = json.dumps({
            "id": 300, "host": "old", "record_type": "CNAME",
            "answer": "target.com.", "ttl": 600, "priority": None,
        })
        mock_snapshot.new_state = None

        with patch("app.services.dns_batch.async_session") as mock_session_ctx, \
             patch("app.services.dns_batch.namecom_client") as mock_client, \
             patch("app.services.dns_batch.dns_audit") as mock_audit:

            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [mock_snapshot]
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            mock_client.create_record = AsyncMock(return_value=MagicMock())
            mock_audit.log = AsyncMock()

            result = await batch_service.rollback_batch("ghi789")

        assert result["rolled_back"] == 1
        mock_client.create_record.assert_called_once_with(
            domain="example.com",
            host="old",
            record_type="CNAME",
            answer="target.com.",
            ttl=600,
            priority=None,
        )

    @pytest.mark.asyncio
    async def test_rollback_no_snapshots(self, batch_service):
        """Rollback with no snapshots returns error."""
        with patch("app.services.dns_batch.async_session") as mock_session_ctx:
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await batch_service.rollback_batch("nonexistent")

        assert "error" in result
        assert result["rolled_back"] == 0
