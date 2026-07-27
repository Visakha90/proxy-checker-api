"""
Integration tests for DNS API endpoints.

Tests the full request/response cycle through FastAPI's test client,
with mocked Name.com API and database.
"""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.security import create_access_token
from app.services.namecom import DNSRecord, NamecomError
from app.services.dns_propagation import PropagationResult, PropagationStatus, ResolverResult


@pytest.fixture
def admin_token():
    """Generate a valid admin JWT token for testing."""
    return create_access_token(data={"sub": "admin", "role": "admin"})


@pytest.fixture
def auth_headers(admin_token):
    """Auth headers with admin token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
def sample_record():
    return DNSRecord(
        id=12345,
        domain_name="example.com",
        host="www",
        fqdn="www.example.com.",
        record_type="A",
        answer="1.2.3.4",
        ttl=300,
        priority=None,
    )


class TestListDomains:
    @pytest.mark.asyncio
    async def test_list_domains_success(self, auth_headers):
        with patch("app.api.dns.namecom_client") as mock_client:
            mock_client.list_domains = AsyncMock(return_value=[
                {"domainName": "example.com", "expireDate": "2025-01-01"},
            ])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/dns/domains", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data["domains"]) == 1
        assert data["domains"][0]["domainName"] == "example.com"

    @pytest.mark.asyncio
    async def test_list_domains_unauthorized(self):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/dns/domains")

        assert response.status_code == 403


class TestListRecords:
    @pytest.mark.asyncio
    async def test_list_records_success(self, auth_headers, sample_record):
        with patch("app.api.dns.namecom_client") as mock_client:
            mock_client.list_records = AsyncMock(return_value=[sample_record])

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/dns/domains/example.com/records", headers=auth_headers
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == 12345
        assert data[0]["record_type"] == "A"
        assert data[0]["answer"] == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_list_records_api_error(self, auth_headers):
        with patch("app.api.dns.namecom_client") as mock_client:
            mock_client.list_records = AsyncMock(
                side_effect=NamecomError(404, "Domain not found")
            )

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/dns/domains/nonexistent.com/records", headers=auth_headers
                )

        assert response.status_code == 404
        assert "Domain not found" in response.json()["detail"]


class TestCreateRecord:
    @pytest.mark.asyncio
    async def test_create_record_success(self, auth_headers, sample_record):
        with patch("app.api.dns.namecom_client") as mock_client, \
             patch("app.api.dns.dns_audit") as mock_audit, \
             patch("app.api.dns.dns_events") as mock_events:
            mock_client.create_record = AsyncMock(return_value=sample_record)
            mock_audit.log = AsyncMock()
            mock_events.emit_record_created = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/dns/domains/example.com/records",
                    headers=auth_headers,
                    json={
                        "host": "www",
                        "record_type": "A",
                        "answer": "1.2.3.4",
                        "ttl": 300,
                    },
                )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == 12345
        assert data["record_type"] == "A"
        mock_audit.log.assert_called_once()
        mock_events.emit_record_created.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_record_invalid_type(self, auth_headers):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/dns/domains/example.com/records",
                headers=auth_headers,
                json={
                    "host": "www",
                    "record_type": "INVALID",
                    "answer": "1.2.3.4",
                },
            )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_record_invalid_ttl(self, auth_headers):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/dns/domains/example.com/records",
                headers=auth_headers,
                json={
                    "host": "www",
                    "record_type": "A",
                    "answer": "1.2.3.4",
                    "ttl": 10,  # Below minimum of 60
                },
            )

        assert response.status_code == 422


class TestUpdateRecord:
    @pytest.mark.asyncio
    async def test_update_record_success(self, auth_headers, sample_record):
        updated = DNSRecord(
            id=12345, domain_name="example.com", host="www",
            fqdn="www.example.com.", record_type="A",
            answer="5.6.7.8", ttl=600,
        )

        with patch("app.api.dns.namecom_client") as mock_client, \
             patch("app.api.dns.dns_audit") as mock_audit, \
             patch("app.api.dns.dns_events") as mock_events:
            mock_client.get_record = AsyncMock(return_value=sample_record)
            mock_client.update_record = AsyncMock(return_value=updated)
            mock_audit.log = AsyncMock()
            mock_events.emit_record_updated = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.put(
                    "/api/dns/domains/example.com/records/12345",
                    headers=auth_headers,
                    json={"answer": "5.6.7.8", "ttl": 600},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["answer"] == "5.6.7.8"
        assert data["ttl"] == 600
        # Verify audit logged with before/after states
        audit_call = mock_audit.log.call_args
        assert audit_call[1]["before_state"]["answer"] == "1.2.3.4"
        assert audit_call[1]["after_state"]["answer"] == "5.6.7.8"


class TestDeleteRecord:
    @pytest.mark.asyncio
    async def test_delete_record_success(self, auth_headers, sample_record):
        with patch("app.api.dns.namecom_client") as mock_client, \
             patch("app.api.dns.dns_audit") as mock_audit, \
             patch("app.api.dns.dns_events") as mock_events:
            mock_client.get_record = AsyncMock(return_value=sample_record)
            mock_client.delete_record = AsyncMock()
            mock_audit.log = AsyncMock()
            mock_events.emit_record_deleted = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.delete(
                    "/api/dns/domains/example.com/records/12345",
                    headers=auth_headers,
                )

        assert response.status_code == 204
        mock_events.emit_record_deleted.assert_called_once()


class TestBatchEndpoint:
    @pytest.mark.asyncio
    async def test_batch_create(self, auth_headers, sample_record):
        with patch("app.api.dns.dns_batch") as mock_batch, \
             patch("app.api.dns.dns_events") as mock_events:
            mock_batch.execute_batch = AsyncMock(return_value=MagicMock(
                batch_id="test123",
                domain="example.com",
                total_operations=2,
                successful=2,
                failed=0,
                rollback_available=True,
                results=[
                    MagicMock(
                        index=0, operation=MagicMock(value="create"),
                        success=True, record=sample_record, error=None,
                    ),
                    MagicMock(
                        index=1, operation=MagicMock(value="create"),
                        success=True, record=sample_record, error=None,
                    ),
                ],
            ))
            mock_events.emit_batch_started = AsyncMock()
            mock_events.emit_batch_completed = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/dns/domains/example.com/records/batch",
                    headers=auth_headers,
                    json={
                        "operations": [
                            {"operation": "create", "host": "a", "record_type": "A", "answer": "1.1.1.1"},
                            {"operation": "create", "host": "b", "record_type": "A", "answer": "2.2.2.2"},
                        ]
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["batch_id"] == "test123"
        assert data["successful"] == 2
        assert data["rollback_available"] is True

    @pytest.mark.asyncio
    async def test_batch_validation_empty(self, auth_headers):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/dns/domains/example.com/records/batch",
                headers=auth_headers,
                json={"operations": []},
            )

        assert response.status_code == 422


class TestRollbackEndpoint:
    @pytest.mark.asyncio
    async def test_rollback_success(self, auth_headers):
        with patch("app.api.dns.dns_batch") as mock_batch, \
             patch("app.api.dns.dns_events") as mock_events:
            mock_batch.rollback_batch = AsyncMock(return_value={
                "batch_id": "abc123",
                "rolled_back": 3,
                "errors": [],
                "total_snapshots": 3,
            })
            mock_events.emit = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/dns/domains/example.com/records/batch/rollback",
                    headers=auth_headers,
                    json={"batch_id": "abc123"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["rolled_back"] == 3

    @pytest.mark.asyncio
    async def test_rollback_not_found(self, auth_headers):
        with patch("app.api.dns.dns_batch") as mock_batch:
            mock_batch.rollback_batch = AsyncMock(return_value={
                "error": "No rollback snapshots found for this batch",
                "rolled_back": 0,
            })

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/dns/domains/example.com/records/batch/rollback",
                    headers=auth_headers,
                    json={"batch_id": "nonexistent"},
                )

        assert response.status_code == 404


class TestPropagationEndpoints:
    @pytest.mark.asyncio
    async def test_quick_check(self, auth_headers):
        mock_result = PropagationResult(
            fqdn="www.example.com",
            record_type="A",
            expected_value="1.2.3.4",
            status=PropagationStatus.PROPAGATED,
            resolver_results=[
                ResolverResult("google_primary", "8.8.8.8", True, ["1.2.3.4"]),
                ResolverResult("cloudflare_primary", "1.1.1.1", True, ["1.2.3.4"]),
            ],
            propagated_count=2,
            total_resolvers=4,
            elapsed_seconds=0.5,
        )

        with patch("app.api.dns.quick_check", new_callable=AsyncMock) as mock_qc:
            mock_qc.return_value = mock_result

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/dns/propagation/check",
                    headers=auth_headers,
                    json={
                        "fqdn": "www.example.com",
                        "record_type": "A",
                        "expected_value": "1.2.3.4",
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "propagated"
        assert data["propagated_count"] == 2
        assert len(data["resolvers"]) == 2


class TestSSLEndpoints:
    @pytest.mark.asyncio
    async def test_deploy_ssl(self, auth_headers):
        from app.services.ssl_manager import SSLCertificate, SSLStatus
        from datetime import datetime, timezone

        mock_cert = SSLCertificate(
            domain="www.example.com",
            status=SSLStatus.ISSUED,
            issued_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            cert_path="/app/certs/www.example.com/fullchain.pem",
            key_path="/app/certs/www.example.com/privkey.pem",
        )

        with patch("app.api.dns.ssl_manager") as mock_ssl, \
             patch("app.api.dns.dns_audit") as mock_audit, \
             patch("app.api.dns.dns_events") as mock_events:
            mock_ssl.deploy_ssl = AsyncMock(return_value=mock_cert)
            mock_audit.log = AsyncMock()
            mock_events.emit_ssl_started = AsyncMock()
            mock_events.emit_ssl_completed = AsyncMock()

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.post(
                    "/api/dns/ssl/deploy",
                    headers=auth_headers,
                    json={"domain": "example.com", "subdomain": "www"},
                )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "issued"
        assert data["cert_path"] is not None


class TestAuditEndpoints:
    @pytest.mark.asyncio
    async def test_get_audit_logs(self, auth_headers):
        mock_log = MagicMock()
        mock_log.id = 1
        mock_log.action = "create"
        mock_log.domain = "example.com"
        mock_log.record_type = "A"
        mock_log.record_id = 12345
        mock_log.host = "www"
        mock_log.before_state = None
        mock_log.after_state = json.dumps({"id": 12345, "answer": "1.2.3.4"})
        mock_log.operator = "admin"
        mock_log.ip_address = "127.0.0.1"
        mock_log.success = True
        mock_log.error_message = None
        mock_log.metadata = None
        mock_log.created_at = MagicMock(isoformat=MagicMock(return_value="2024-01-01T00:00:00+00:00"))

        with patch("app.api.dns.dns_audit") as mock_audit:
            mock_audit.get_logs = AsyncMock(return_value=([mock_log], 1))

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get(
                    "/api/dns/audit?domain=example.com",
                    headers=auth_headers,
                )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["logs"][0]["action"] == "create"
        assert data["logs"][0]["domain"] == "example.com"
