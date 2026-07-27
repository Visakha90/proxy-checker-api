"""
Name.com REST API client for DNS record management - Production Quality.

Uses the official Name.com v4 API:
https://www.name.com/api-docs

Features:
- Retry logic with exponential backoff
- Structured error handling
- Comprehensive logging
- Credential isolation via environment variables

Credentials are read exclusively from environment variables:
  - NAMECOM_USERNAME
  - NAMECOM_API_TOKEN
"""

import asyncio
import logging
import time
from dataclasses import dataclass, asdict
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
BASE_DELAY = 1.0  # seconds
MAX_DELAY = 60.0  # seconds
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class NamecomError(Exception):
    """Raised when the Name.com API returns an error."""

    def __init__(self, status_code: int, message: str, details: dict | None = None):
        self.status_code = status_code
        self.message = message
        self.details = details or {}
        super().__init__(f"Name.com API error {status_code}: {message}")


class NamecomRetryExhausted(NamecomError):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, status_code: int, message: str, attempts: int):
        self.attempts = attempts
        super().__init__(
            status_code=status_code,
            message=f"{message} (exhausted {attempts} retries)",
        )


@dataclass
class DNSRecord:
    """Represents a DNS record from Name.com."""

    id: int
    domain_name: str
    host: str
    fqdn: str
    record_type: str
    answer: str
    ttl: int
    priority: int | None = None

    @classmethod
    def from_api(cls, data: dict) -> "DNSRecord":
        return cls(
            id=data.get("id", 0),
            domain_name=data.get("domainName", ""),
            host=data.get("host", ""),
            fqdn=data.get("fqdn", ""),
            record_type=data.get("type", ""),
            answer=data.get("answer", ""),
            ttl=data.get("ttl", 300),
            priority=data.get("priority"),
        )

    def to_dict(self) -> dict:
        return asdict(self)


class NamecomClient:
    """
    Production-ready async client for the Name.com REST API.

    Features:
    - Automatic retry with exponential backoff on transient failures
    - Connection pooling via shared httpx client
    - Structured error handling with specific exception types
    - Comprehensive request/response logging

    All credentials are sourced from environment variables via Settings.
    """

    def __init__(self):
        settings = get_settings()
        self._username = settings.namecom_username
        self._token = settings.namecom_api_token
        self._base_url = settings.namecom_api_url
        self._client: httpx.AsyncClient | None = None

        if not self._username or not self._token:
            logger.warning(
                "Name.com credentials not configured. "
                "Set NAMECOM_USERNAME and NAMECOM_API_TOKEN environment variables."
            )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30,
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self):
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _auth(self) -> tuple[str, str]:
        """Return basic auth tuple for requests."""
        return (self._username, self._token)

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        json_data: dict | None = None,
        params: dict | None = None,
        max_retries: int = MAX_RETRIES,
    ) -> dict[str, Any]:
        """
        Make an authenticated request with exponential backoff retry.

        Retries on:
        - Network errors (timeouts, connection failures)
        - HTTP 429 (rate limited)
        - HTTP 5xx (server errors)

        Does NOT retry on:
        - HTTP 4xx (client errors, except 429)
        """
        url = f"{self._base_url}{path}"
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                client = await self._get_client()
                start_time = time.monotonic()

                response = await client.request(
                    method=method,
                    url=url,
                    auth=self._auth(),
                    json=json_data,
                    params=params,
                )

                elapsed_ms = round((time.monotonic() - start_time) * 1000, 2)
                logger.debug(
                    f"Name.com API {method} {path} -> {response.status_code} ({elapsed_ms}ms)"
                )

                # Success
                if response.status_code < 400:
                    if response.status_code == 204:
                        return {}
                    return response.json()

                # Parse error
                try:
                    error_body = response.json()
                    message = error_body.get("message", response.text)
                    details = error_body.get("details", {})
                except Exception:
                    message = response.text
                    details = {}

                # Retryable server error
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = NamecomError(response.status_code, message, details)
                    delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)

                    # Respect Retry-After header if present
                    retry_after = response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            delay = max(delay, float(retry_after))
                        except ValueError:
                            pass

                    logger.warning(
                        f"Name.com API {method} {path} returned {response.status_code}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable client error
                logger.error(
                    f"Name.com API error: {method} {path} -> {response.status_code} {message}"
                )
                raise NamecomError(response.status_code, message, details)

            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                last_error = e
                delay = min(BASE_DELAY * (2 ** (attempt - 1)), MAX_DELAY)
                logger.warning(
                    f"Name.com API {method} {path} network error: {e}. "
                    f"Retrying in {delay:.1f}s (attempt {attempt}/{max_retries})"
                )
                await asyncio.sleep(delay)
                continue

        # All retries exhausted
        logger.error(
            f"Name.com API {method} {path} failed after {max_retries} attempts. "
            f"Last error: {last_error}"
        )
        if isinstance(last_error, NamecomError):
            raise NamecomRetryExhausted(
                last_error.status_code, last_error.message, max_retries
            )
        raise NamecomRetryExhausted(
            status_code=503,
            message=f"Network error: {last_error}",
            attempts=max_retries,
        )

    # ─── DNS Record Operations ────────────────────────────────────────────

    async def list_records(self, domain: str, page: int = 1, per_page: int = 1000) -> list[DNSRecord]:
        """
        List all DNS records for a domain.

        Args:
            domain: The domain name (e.g., "example.com")
            page: Page number for pagination
            per_page: Number of records per page (max 1000)

        Returns:
            List of DNSRecord objects
        """
        logger.info(f"Listing DNS records for domain: {domain}")

        data = await self._request_with_retry(
            "GET",
            f"/domains/{domain}/records",
            params={"page": page, "perPage": per_page},
        )

        records = [DNSRecord.from_api(r) for r in data.get("records", [])]
        logger.info(f"Found {len(records)} DNS records for {domain}")
        return records

    async def get_record(self, domain: str, record_id: int) -> DNSRecord:
        """
        Get a specific DNS record by ID.

        Args:
            domain: The domain name
            record_id: The record ID

        Returns:
            DNSRecord object
        """
        logger.info(f"Getting DNS record {record_id} for domain: {domain}")
        data = await self._request_with_retry("GET", f"/domains/{domain}/records/{record_id}")
        return DNSRecord.from_api(data)

    async def create_record(
        self,
        domain: str,
        host: str,
        record_type: str,
        answer: str,
        ttl: int = 300,
        priority: int | None = None,
    ) -> DNSRecord:
        """
        Create a new DNS record.

        Args:
            domain: The domain name (e.g., "example.com")
            host: The hostname (e.g., "www" for www.example.com, "" for apex)
            record_type: Record type (A, AAAA, CNAME, MX, TXT, NS, SRV)
            answer: The record value (IP address, hostname, etc.)
            ttl: Time to live in seconds (default 300)
            priority: Priority for MX/SRV records

        Returns:
            The created DNSRecord
        """
        logger.info(
            f"Creating DNS record: {record_type} {host}.{domain} -> {answer} (TTL={ttl})"
        )

        payload: dict[str, Any] = {
            "host": host,
            "type": record_type,
            "answer": answer,
            "ttl": ttl,
        }
        if priority is not None:
            payload["priority"] = priority

        data = await self._request_with_retry(
            "POST", f"/domains/{domain}/records", json_data=payload
        )
        record = DNSRecord.from_api(data)
        logger.info(f"Created DNS record ID={record.id} for {domain}")
        return record

    async def update_record(
        self,
        domain: str,
        record_id: int,
        host: str | None = None,
        record_type: str | None = None,
        answer: str | None = None,
        ttl: int | None = None,
        priority: int | None = None,
    ) -> DNSRecord:
        """
        Update an existing DNS record.

        Args:
            domain: The domain name
            record_id: The record ID to update
            host: New hostname (optional)
            record_type: New record type (optional)
            answer: New record value (optional)
            ttl: New TTL (optional)
            priority: New priority (optional)

        Returns:
            The updated DNSRecord
        """
        logger.info(f"Updating DNS record {record_id} for domain: {domain}")

        payload: dict[str, Any] = {}
        if host is not None:
            payload["host"] = host
        if record_type is not None:
            payload["type"] = record_type
        if answer is not None:
            payload["answer"] = answer
        if ttl is not None:
            payload["ttl"] = ttl
        if priority is not None:
            payload["priority"] = priority

        data = await self._request_with_retry(
            "PUT", f"/domains/{domain}/records/{record_id}", json_data=payload
        )
        record = DNSRecord.from_api(data)
        logger.info(f"Updated DNS record ID={record.id} for {domain}")
        return record

    async def delete_record(self, domain: str, record_id: int) -> None:
        """
        Delete a DNS record.

        Args:
            domain: The domain name
            record_id: The record ID to delete
        """
        logger.info(f"Deleting DNS record {record_id} for domain: {domain}")
        await self._request_with_retry("DELETE", f"/domains/{domain}/records/{record_id}")
        logger.info(f"Deleted DNS record {record_id} from {domain}")

    # ─── Convenience Methods ──────────────────────────────────────────────

    async def list_domains(self) -> list[dict]:
        """List all domains in the Name.com account."""
        logger.info("Listing domains from Name.com account")
        data = await self._request_with_retry("GET", "/domains")
        domains = data.get("domains", [])
        logger.info(f"Found {len(domains)} domains")
        return domains

    async def set_a_record(self, domain: str, host: str, ip: str, ttl: int = 300) -> DNSRecord:
        """Convenience method to create or update an A record."""
        records = await self.list_records(domain)
        existing = next(
            (r for r in records if r.host == host and r.record_type == "A"),
            None,
        )
        if existing:
            return await self.update_record(
                domain, existing.id, host=host, record_type="A", answer=ip, ttl=ttl
            )
        return await self.create_record(domain, host, "A", ip, ttl)

    async def set_cname_record(
        self, domain: str, host: str, target: str, ttl: int = 300
    ) -> DNSRecord:
        """Convenience method to create or update a CNAME record."""
        records = await self.list_records(domain)
        existing = next(
            (r for r in records if r.host == host and r.record_type == "CNAME"),
            None,
        )
        if existing:
            return await self.update_record(
                domain, existing.id, host=host, record_type="CNAME", answer=target, ttl=ttl
            )
        return await self.create_record(domain, host, "CNAME", target, ttl)


# Singleton instance
namecom_client = NamecomClient()
