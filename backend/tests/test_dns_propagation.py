"""
Unit tests for DNS propagation verification service.

Tests cover:
- DNS query building and response parsing
- Resolver checking logic
- Propagation polling behavior
- Quick check (non-polling) mode
- Timeout handling
"""

import asyncio
import struct
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.services.dns_propagation import (
    _build_dns_query,
    _parse_dns_response,
    resolve_dns,
    check_resolver,
    verify_propagation,
    quick_check,
    PropagationStatus,
    ResolverResult,
    RESOLVERS,
    DNS_RECORD_TYPES,
)


class TestDNSQueryBuilding:
    """Tests for raw DNS query packet construction."""

    def test_build_query_a_record(self):
        query = _build_dns_query("example.com", DNS_RECORD_TYPES["A"])
        assert len(query) > 12  # At least header + question
        # Check header flags (standard query, recursion desired)
        flags = struct.unpack(">H", query[2:4])[0]
        assert flags == 0x0100
        # Check question count = 1
        qdcount = struct.unpack(">H", query[4:6])[0]
        assert qdcount == 1

    def test_build_query_contains_domain(self):
        query = _build_dns_query("test.example.com", DNS_RECORD_TYPES["A"])
        # Domain should be encoded as labels
        assert b"\x04test" in query
        assert b"\x07example" in query
        assert b"\x03com" in query

    def test_build_query_different_types(self):
        a_query = _build_dns_query("x.com", DNS_RECORD_TYPES["A"])
        aaaa_query = _build_dns_query("x.com", DNS_RECORD_TYPES["AAAA"])
        # Last 2 bytes before class should differ (record type)
        assert a_query != aaaa_query


class TestDNSResponseParsing:
    """Tests for DNS response packet parsing."""

    def _build_a_response(self, ip: str, domain: str = "example.com") -> bytes:
        """Build a minimal DNS response with an A record."""
        # Header
        header = struct.pack(
            ">HHHHHH",
            0x1234,  # ID
            0x8180,  # Flags: response, recursion desired+available
            1,       # Questions
            1,       # Answers
            0, 0,    # Authority, Additional
        )
        # Question section
        question = b""
        for label in domain.split("."):
            question += struct.pack("B", len(label)) + label.encode()
        question += b"\x00"
        question += struct.pack(">HH", 1, 1)  # Type A, Class IN

        # Answer section (using pointer to question name)
        answer = struct.pack(">H", 0xC00C)  # Pointer to offset 12
        answer += struct.pack(">HH", 1, 1)  # Type A, Class IN
        answer += struct.pack(">I", 300)     # TTL
        answer += struct.pack(">H", 4)       # RDLENGTH
        # IP address
        parts = [int(p) for p in ip.split(".")]
        answer += struct.pack("BBBB", *parts)

        return header + question + answer

    def test_parse_a_record(self):
        response = self._build_a_response("1.2.3.4")
        answers = _parse_dns_response(response)
        assert "1.2.3.4" in answers

    def test_parse_multiple_a_records(self):
        # Build response with 2 answers
        header = struct.pack(">HHHHHH", 0x1234, 0x8180, 1, 2, 0, 0)
        question = b"\x07example\x03com\x00" + struct.pack(">HH", 1, 1)

        answer1 = struct.pack(">H", 0xC00C) + struct.pack(">HHIH", 1, 1, 300, 4)
        answer1 += struct.pack("BBBB", 1, 2, 3, 4)

        answer2 = struct.pack(">H", 0xC00C) + struct.pack(">HHIH", 1, 1, 300, 4)
        answer2 += struct.pack("BBBB", 5, 6, 7, 8)

        data = header + question + answer1 + answer2
        answers = _parse_dns_response(data)
        assert "1.2.3.4" in answers
        assert "5.6.7.8" in answers

    def test_parse_empty_response(self):
        # Header with 0 answers
        header = struct.pack(">HHHHHH", 0x1234, 0x8180, 1, 0, 0, 0)
        question = b"\x07example\x03com\x00" + struct.pack(">HH", 1, 1)
        answers = _parse_dns_response(header + question)
        assert answers == []

    def test_parse_truncated_data(self):
        answers = _parse_dns_response(b"\x00" * 5)
        assert answers == []


class TestResolverCheck:
    """Tests for individual resolver checking."""

    @pytest.mark.asyncio
    async def test_check_resolver_success(self):
        with patch("app.services.dns_propagation.resolve_dns", new_callable=AsyncMock) as mock:
            mock.return_value = ["1.2.3.4"]
            result = await check_resolver(
                fqdn="www.example.com",
                record_type="A",
                expected_value="1.2.3.4",
                resolver_name="test",
                resolver_addr=("8.8.8.8", 53),
            )

        assert result.resolved is True
        assert result.resolver_name == "test"
        assert "1.2.3.4" in result.answers

    @pytest.mark.asyncio
    async def test_check_resolver_not_found(self):
        with patch("app.services.dns_propagation.resolve_dns", new_callable=AsyncMock) as mock:
            mock.return_value = ["9.9.9.9"]
            result = await check_resolver(
                fqdn="www.example.com",
                record_type="A",
                expected_value="1.2.3.4",
                resolver_name="test",
                resolver_addr=("8.8.8.8", 53),
            )

        assert result.resolved is False

    @pytest.mark.asyncio
    async def test_check_resolver_case_insensitive(self):
        with patch("app.services.dns_propagation.resolve_dns", new_callable=AsyncMock) as mock:
            mock.return_value = ["mail.EXAMPLE.COM."]
            result = await check_resolver(
                fqdn="www.example.com",
                record_type="CNAME",
                expected_value="mail.example.com",
                resolver_name="test",
                resolver_addr=("8.8.8.8", 53),
            )

        assert result.resolved is True

    @pytest.mark.asyncio
    async def test_check_resolver_error(self):
        with patch("app.services.dns_propagation.resolve_dns", new_callable=AsyncMock) as mock:
            mock.side_effect = Exception("Network error")
            result = await check_resolver(
                fqdn="www.example.com",
                record_type="A",
                expected_value="1.2.3.4",
                resolver_name="test",
                resolver_addr=("8.8.8.8", 53),
            )

        assert result.resolved is False
        assert result.error is not None


class TestVerifyPropagation:
    """Tests for the full propagation verification polling."""

    @pytest.mark.asyncio
    async def test_immediate_propagation(self):
        """All resolvers confirm immediately."""
        with patch("app.services.dns_propagation.check_resolver", new_callable=AsyncMock) as mock:
            mock.return_value = ResolverResult(
                resolver_name="test", resolver_ip="8.8.8.8",
                resolved=True, answers=["1.2.3.4"]
            )

            result = await verify_propagation(
                fqdn="www.example.com",
                record_type="A",
                expected_value="1.2.3.4",
                timeout_seconds=5,
                poll_interval=1,
            )

        assert result.status == PropagationStatus.PROPAGATED
        assert result.propagated_count == len(RESOLVERS)

    @pytest.mark.asyncio
    async def test_timeout_no_propagation(self):
        """No resolvers confirm within timeout."""
        with patch("app.services.dns_propagation.check_resolver", new_callable=AsyncMock) as mock:
            mock.return_value = ResolverResult(
                resolver_name="test", resolver_ip="8.8.8.8",
                resolved=False, answers=[]
            )

            result = await verify_propagation(
                fqdn="www.example.com",
                record_type="A",
                expected_value="1.2.3.4",
                timeout_seconds=2,
                poll_interval=1,
            )

        assert result.status == PropagationStatus.TIMEOUT
        assert result.propagated_count == 0

    @pytest.mark.asyncio
    async def test_partial_propagation(self):
        """Some resolvers confirm, not all."""
        call_count = [0]

        async def mock_check(*args, **kwargs):
            call_count[0] += 1
            # First 2 resolve, rest don't
            return ResolverResult(
                resolver_name="test", resolver_ip="8.8.8.8",
                resolved=(call_count[0] % 3 == 0), answers=["1.2.3.4"] if call_count[0] % 3 == 0 else []
            )

        with patch("app.services.dns_propagation.check_resolver", side_effect=mock_check):
            result = await verify_propagation(
                fqdn="www.example.com",
                record_type="A",
                expected_value="1.2.3.4",
                timeout_seconds=3,
                poll_interval=1,
                required_resolvers=len(RESOLVERS),  # Require all
            )

        assert result.status in (PropagationStatus.PARTIAL, PropagationStatus.TIMEOUT)


class TestQuickCheck:
    """Tests for non-polling quick check."""

    @pytest.mark.asyncio
    async def test_quick_check_all_propagated(self):
        with patch("app.services.dns_propagation.check_resolver", new_callable=AsyncMock) as mock:
            mock.return_value = ResolverResult(
                resolver_name="test", resolver_ip="8.8.8.8",
                resolved=True, answers=["1.2.3.4"]
            )

            result = await quick_check("www.example.com", "A", "1.2.3.4")

        assert result.status == PropagationStatus.PROPAGATED

    @pytest.mark.asyncio
    async def test_quick_check_none_propagated(self):
        with patch("app.services.dns_propagation.check_resolver", new_callable=AsyncMock) as mock:
            mock.return_value = ResolverResult(
                resolver_name="test", resolver_ip="8.8.8.8",
                resolved=False, answers=[]
            )

            result = await quick_check("www.example.com", "A", "1.2.3.4")

        assert result.status == PropagationStatus.PENDING
