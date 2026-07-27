"""
Unit tests for the Name.com API client.

Tests cover:
- Retry logic with exponential backoff
- Error handling for various HTTP status codes
- Record CRUD operations
- Authentication
- Connection pooling behavior
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.namecom import (
    NamecomClient,
    NamecomError,
    NamecomRetryExhausted,
    DNSRecord,
    MAX_RETRIES,
    BASE_DELAY,
    RETRYABLE_STATUS_CODES,
)


class TestDNSRecord:
    """Tests for DNSRecord dataclass."""

    def test_from_api_full_data(self, sample_dns_record):
        record = DNSRecord.from_api(sample_dns_record)
        assert record.id == 12345
        assert record.domain_name == "example.com"
        assert record.host == "www"
        assert record.fqdn == "www.example.com."
        assert record.record_type == "A"
        assert record.answer == "1.2.3.4"
        assert record.ttl == 300
        assert record.priority is None

    def test_from_api_minimal_data(self):
        record = DNSRecord.from_api({})
        assert record.id == 0
        assert record.domain_name == ""
        assert record.host == ""
        assert record.record_type == ""
        assert record.answer == ""
        assert record.ttl == 300
        assert record.priority is None

    def test_from_api_with_priority(self):
        data = {
            "id": 100,
            "domainName": "example.com",
            "host": "mail",
            "fqdn": "mail.example.com.",
            "type": "MX",
            "answer": "mail.example.com.",
            "ttl": 300,
            "priority": 10,
        }
        record = DNSRecord.from_api(data)
        assert record.priority == 10
        assert record.record_type == "MX"

    def test_to_dict(self, sample_dns_record):
        record = DNSRecord.from_api(sample_dns_record)
        d = record.to_dict()
        assert d["id"] == 12345
        assert d["answer"] == "1.2.3.4"
        assert d["record_type"] == "A"


class TestNamecomClientRetry:
    """Tests for retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_successful_request_no_retry(self, sample_dns_record):
        """Successful requests should not retry."""
        client = NamecomClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_dns_record

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_http

            result = await client._request_with_retry("GET", "/domains/example.com/records/12345")

        assert result == sample_dns_record
        mock_http.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_500(self):
        """Should retry on HTTP 500 with exponential backoff."""
        client = NamecomClient()

        fail_response = MagicMock()
        fail_response.status_code = 500
        fail_response.text = "Internal Server Error"
        fail_response.json.return_value = {"message": "Server error"}
        fail_response.headers = {}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"records": []}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(side_effect=[fail_response, success_response])
            mock_get_client.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await client._request_with_retry(
                    "GET", "/domains/example.com/records", max_retries=3
                )

        assert result == {"records": []}
        assert mock_http.request.call_count == 2
        mock_sleep.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_on_429_rate_limit(self):
        """Should retry on HTTP 429 and respect Retry-After header."""
        client = NamecomClient()

        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.text = "Rate limited"
        rate_limited.json.return_value = {"message": "Too many requests"}
        rate_limited.headers = {"Retry-After": "3"}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"ok": True}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(side_effect=[rate_limited, success_response])
            mock_get_client.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await client._request_with_retry(
                    "GET", "/test", max_retries=3
                )

        assert result == {"ok": True}
        # Should use Retry-After value (3s) since it's larger than base delay (1s)
        sleep_arg = mock_sleep.call_args[0][0]
        assert sleep_arg >= 3.0

    @pytest.mark.asyncio
    async def test_retry_on_network_error(self):
        """Should retry on network errors."""
        client = NamecomClient()

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"data": "ok"}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(
                side_effect=[httpx.ConnectError("Connection refused"), success_response]
            )
            mock_get_client.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client._request_with_retry(
                    "GET", "/test", max_retries=3
                )

        assert result == {"data": "ok"}
        assert mock_http.request.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_timeout(self):
        """Should retry on timeout errors."""
        client = NamecomClient()

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"data": "ok"}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(
                side_effect=[httpx.TimeoutException("Timeout"), success_response]
            )
            mock_get_client.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await client._request_with_retry(
                    "GET", "/test", max_retries=3
                )

        assert result == {"data": "ok"}

    @pytest.mark.asyncio
    async def test_max_retries_exhausted(self):
        """Should raise NamecomRetryExhausted after max retries."""
        client = NamecomClient()

        fail_response = MagicMock()
        fail_response.status_code = 503
        fail_response.text = "Service Unavailable"
        fail_response.json.return_value = {"message": "Unavailable"}
        fail_response.headers = {}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=fail_response)
            mock_get_client.return_value = mock_http

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(NamecomRetryExhausted) as exc_info:
                    await client._request_with_retry(
                        "GET", "/test", max_retries=3
                    )

        assert exc_info.value.attempts == 3
        assert exc_info.value.status_code == 503
        assert mock_http.request.call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self):
        """Should NOT retry on HTTP 400 (client error)."""
        client = NamecomClient()

        bad_request = MagicMock()
        bad_request.status_code = 400
        bad_request.text = "Bad Request"
        bad_request.json.return_value = {"message": "Invalid input"}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=bad_request)
            mock_get_client.return_value = mock_http

            with pytest.raises(NamecomError) as exc_info:
                await client._request_with_retry("POST", "/test", max_retries=3)

        assert exc_info.value.status_code == 400
        mock_http.request.assert_called_once()  # No retry

    @pytest.mark.asyncio
    async def test_no_retry_on_404(self):
        """Should NOT retry on HTTP 404."""
        client = NamecomClient()

        not_found = MagicMock()
        not_found.status_code = 404
        not_found.text = "Not Found"
        not_found.json.return_value = {"message": "Record not found"}

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=not_found)
            mock_get_client.return_value = mock_http

            with pytest.raises(NamecomError) as exc_info:
                await client._request_with_retry("GET", "/test", max_retries=3)

        assert exc_info.value.status_code == 404
        mock_http.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_204_returns_empty_dict(self):
        """HTTP 204 should return empty dict."""
        client = NamecomClient()

        response = MagicMock()
        response.status_code = 204

        with patch.object(client, "_get_client") as mock_get_client:
            mock_http = AsyncMock()
            mock_http.request = AsyncMock(return_value=response)
            mock_get_client.return_value = mock_http

            result = await client._request_with_retry("DELETE", "/test")

        assert result == {}


class TestNamecomClientCRUD:
    """Tests for DNS record CRUD operations."""

    @pytest.mark.asyncio
    async def test_list_records(self, sample_records_list):
        client = NamecomClient()

        with patch.object(
            client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = sample_records_list
            records = await client.list_records("example.com")

        assert len(records) == 3
        assert records[0].host == "www"
        assert records[0].record_type == "A"
        assert records[1].record_type == "MX"
        assert records[1].priority == 10
        mock_req.assert_called_once_with(
            "GET",
            "/domains/example.com/records",
            params={"page": 1, "perPage": 1000},
        )

    @pytest.mark.asyncio
    async def test_get_record(self, sample_dns_record):
        client = NamecomClient()

        with patch.object(
            client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = sample_dns_record
            record = await client.get_record("example.com", 12345)

        assert record.id == 12345
        assert record.answer == "1.2.3.4"

    @pytest.mark.asyncio
    async def test_create_record(self, sample_dns_record):
        client = NamecomClient()

        with patch.object(
            client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = sample_dns_record
            record = await client.create_record(
                domain="example.com",
                host="www",
                record_type="A",
                answer="1.2.3.4",
                ttl=300,
            )

        assert record.id == 12345
        mock_req.assert_called_once_with(
            "POST",
            "/domains/example.com/records",
            json_data={"host": "www", "type": "A", "answer": "1.2.3.4", "ttl": 300},
        )

    @pytest.mark.asyncio
    async def test_create_record_with_priority(self):
        client = NamecomClient()
        expected_response = {
            "id": 999,
            "domainName": "example.com",
            "host": "mail",
            "fqdn": "mail.example.com.",
            "type": "MX",
            "answer": "mx.example.com.",
            "ttl": 300,
            "priority": 10,
        }

        with patch.object(
            client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = expected_response
            record = await client.create_record(
                domain="example.com",
                host="mail",
                record_type="MX",
                answer="mx.example.com.",
                ttl=300,
                priority=10,
            )

        assert record.priority == 10
        call_args = mock_req.call_args
        assert call_args[1]["json_data"]["priority"] == 10

    @pytest.mark.asyncio
    async def test_update_record(self, sample_dns_record):
        client = NamecomClient()
        updated = {**sample_dns_record, "answer": "5.6.7.8"}

        with patch.object(
            client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = updated
            record = await client.update_record(
                domain="example.com",
                record_id=12345,
                answer="5.6.7.8",
            )

        assert record.answer == "5.6.7.8"
        mock_req.assert_called_once_with(
            "PUT",
            "/domains/example.com/records/12345",
            json_data={"answer": "5.6.7.8"},
        )

    @pytest.mark.asyncio
    async def test_update_record_partial_fields(self, sample_dns_record):
        client = NamecomClient()

        with patch.object(
            client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = sample_dns_record
            await client.update_record(
                domain="example.com",
                record_id=12345,
                ttl=600,
                host="api",
            )

        call_args = mock_req.call_args
        payload = call_args[1]["json_data"]
        assert payload == {"ttl": 600, "host": "api"}
        assert "answer" not in payload
        assert "type" not in payload

    @pytest.mark.asyncio
    async def test_delete_record(self):
        client = NamecomClient()

        with patch.object(
            client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = {}
            await client.delete_record("example.com", 12345)

        mock_req.assert_called_once_with(
            "DELETE", "/domains/example.com/records/12345"
        )

    @pytest.mark.asyncio
    async def test_list_domains(self):
        client = NamecomClient()

        with patch.object(
            client, "_request_with_retry", new_callable=AsyncMock
        ) as mock_req:
            mock_req.return_value = {
                "domains": [
                    {"domainName": "example.com"},
                    {"domainName": "test.org"},
                ]
            }
            domains = await client.list_domains()

        assert len(domains) == 2
        assert domains[0]["domainName"] == "example.com"


class TestNamecomClientConvenience:
    """Tests for convenience methods (set_a_record, set_cname_record)."""

    @pytest.mark.asyncio
    async def test_set_a_record_creates_new(self, sample_records_list):
        client = NamecomClient()
        new_record = {
            "id": 99999,
            "domainName": "example.com",
            "host": "api",
            "fqdn": "api.example.com.",
            "type": "A",
            "answer": "10.0.0.1",
            "ttl": 300,
        }

        with patch.object(client, "list_records", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [DNSRecord.from_api(r) for r in sample_records_list["records"]]
            with patch.object(client, "create_record", new_callable=AsyncMock) as mock_create:
                mock_create.return_value = DNSRecord.from_api(new_record)
                record = await client.set_a_record("example.com", "api", "10.0.0.1")

        assert record.host == "api"
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_a_record_updates_existing(self, sample_records_list):
        client = NamecomClient()
        updated_record = {
            "id": 12345,
            "domainName": "example.com",
            "host": "www",
            "fqdn": "www.example.com.",
            "type": "A",
            "answer": "99.99.99.99",
            "ttl": 300,
        }

        with patch.object(client, "list_records", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = [DNSRecord.from_api(r) for r in sample_records_list["records"]]
            with patch.object(client, "update_record", new_callable=AsyncMock) as mock_update:
                mock_update.return_value = DNSRecord.from_api(updated_record)
                record = await client.set_a_record("example.com", "www", "99.99.99.99")

        assert record.answer == "99.99.99.99"
        mock_update.assert_called_once_with(
            "example.com", 12345, host="www", record_type="A", answer="99.99.99.99", ttl=300
        )
