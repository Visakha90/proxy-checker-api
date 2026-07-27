"""
DNS Propagation Verification Service.

Verifies that DNS records have propagated to major public resolvers:
- Google DNS (8.8.8.8, 8.8.4.4)
- Cloudflare DNS (1.1.1.1, 1.0.0.1)

Supports polling with configurable timeout and interval.
"""

import asyncio
import logging
import struct
import socket
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

# DNS resolver endpoints
RESOLVERS = {
    "google_primary": ("8.8.8.8", 53),
    "google_secondary": ("8.8.4.4", 53),
    "cloudflare_primary": ("1.1.1.1", 53),
    "cloudflare_secondary": ("1.0.0.1", 53),
}

# DNS record type codes
DNS_RECORD_TYPES = {
    "A": 1,
    "AAAA": 28,
    "CNAME": 5,
    "MX": 15,
    "TXT": 16,
    "NS": 2,
    "SRV": 33,
}


class PropagationStatus(str, Enum):
    PENDING = "pending"
    PARTIAL = "partial"
    PROPAGATED = "propagated"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class ResolverResult:
    resolver_name: str
    resolver_ip: str
    resolved: bool
    answers: list[str]
    error: str | None = None


@dataclass
class PropagationResult:
    fqdn: str
    record_type: str
    expected_value: str
    status: PropagationStatus
    resolver_results: list[ResolverResult]
    propagated_count: int
    total_resolvers: int
    elapsed_seconds: float


def _build_dns_query(domain: str, record_type: int, query_id: int = 0x1234) -> bytes:
    """Build a raw DNS query packet."""
    # Header: ID, flags (standard query, recursion desired), counts
    header = struct.pack(
        ">HHHHHH",
        query_id,   # Transaction ID
        0x0100,     # Flags: standard query, recursion desired
        1,          # Questions count
        0,          # Answers count
        0,          # Authority count
        0,          # Additional count
    )

    # Question section: encode domain name
    question = b""
    for label in domain.rstrip(".").split("."):
        question += struct.pack("B", len(label)) + label.encode("ascii")
    question += b"\x00"  # Root label

    # Type and class
    question += struct.pack(">HH", record_type, 1)  # IN class

    return header + question


def _parse_dns_response(data: bytes) -> list[str]:
    """Parse answers from a raw DNS response packet."""
    answers = []

    if len(data) < 12:
        return answers

    # Parse header
    answer_count = struct.unpack(">H", data[6:8])[0]
    if answer_count == 0:
        return answers

    # Skip header (12 bytes) and question section
    offset = 12

    # Skip question section
    while offset < len(data):
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length >= 0xC0:  # Pointer
            offset += 2
            break
        offset += length + 1
    offset += 4  # Skip QTYPE and QCLASS

    # Parse answer records
    for _ in range(answer_count):
        if offset >= len(data):
            break

        # Skip name (handle pointers)
        if data[offset] >= 0xC0:
            offset += 2
        else:
            while offset < len(data) and data[offset] != 0:
                if data[offset] >= 0xC0:
                    offset += 2
                    break
                offset += data[offset] + 1
            else:
                offset += 1

        if offset + 10 > len(data):
            break

        rtype = struct.unpack(">H", data[offset:offset + 2])[0]
        offset += 2
        offset += 2  # Class
        offset += 4  # TTL
        rdlength = struct.unpack(">H", data[offset:offset + 2])[0]
        offset += 2

        if offset + rdlength > len(data):
            break

        rdata = data[offset:offset + rdlength]
        offset += rdlength

        # Parse based on type
        if rtype == 1 and rdlength == 4:  # A record
            answers.append(socket.inet_ntoa(rdata))
        elif rtype == 28 and rdlength == 16:  # AAAA record
            answers.append(socket.inet_ntop(socket.AF_INET6, rdata))
        elif rtype == 5:  # CNAME
            answers.append(_parse_dns_name(data, offset - rdlength))
        elif rtype == 16:  # TXT
            # TXT records have length-prefixed strings
            txt_offset = 0
            txt_parts = []
            while txt_offset < rdlength:
                txt_len = rdata[txt_offset]
                txt_offset += 1
                txt_parts.append(rdata[txt_offset:txt_offset + txt_len].decode("utf-8", errors="replace"))
                txt_offset += txt_len
            answers.append("".join(txt_parts))
        elif rtype == 15:  # MX
            if rdlength >= 2:
                # Skip priority (2 bytes), parse exchange
                answers.append(_parse_dns_name(data, offset - rdlength + 2))
        elif rtype == 2:  # NS
            answers.append(_parse_dns_name(data, offset - rdlength))

    return answers


def _parse_dns_name(data: bytes, offset: int) -> str:
    """Parse a DNS name with pointer support."""
    labels = []
    seen_offsets = set()
    while offset < len(data):
        if offset in seen_offsets:
            break
        seen_offsets.add(offset)

        length = data[offset]
        if length == 0:
            break
        if length >= 0xC0:
            # Pointer
            pointer = struct.unpack(">H", data[offset:offset + 2])[0] & 0x3FFF
            offset = pointer
            continue
        offset += 1
        labels.append(data[offset:offset + length].decode("ascii", errors="replace"))
        offset += length

    return ".".join(labels)


async def resolve_dns(
    fqdn: str,
    record_type: str,
    resolver_ip: str,
    resolver_port: int = 53,
    timeout: float = 5.0,
) -> list[str]:
    """
    Resolve a DNS record using a specific resolver via UDP.

    Args:
        fqdn: Fully qualified domain name
        record_type: Record type (A, AAAA, CNAME, etc.)
        resolver_ip: IP address of the DNS resolver
        resolver_port: Port of the DNS resolver (default 53)
        timeout: Query timeout in seconds

    Returns:
        List of resolved values
    """
    rtype = DNS_RECORD_TYPES.get(record_type.upper())
    if rtype is None:
        raise ValueError(f"Unsupported record type: {record_type}")

    query = _build_dns_query(fqdn, rtype)

    loop = asyncio.get_event_loop()

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    sock.settimeout(0)

    try:
        await loop.run_in_executor(None, sock.sendto, query, (resolver_ip, resolver_port))

        # Wait for response
        response_data = await asyncio.wait_for(
            loop.run_in_executor(None, sock.recv, 4096),
            timeout=timeout,
        )
        return _parse_dns_response(response_data)
    except asyncio.TimeoutError:
        return []
    except Exception as e:
        logger.debug(f"DNS resolve error ({resolver_ip}): {e}")
        return []
    finally:
        sock.close()


async def check_resolver(
    fqdn: str,
    record_type: str,
    expected_value: str,
    resolver_name: str,
    resolver_addr: tuple[str, int],
) -> ResolverResult:
    """Check a single resolver for the expected DNS record."""
    resolver_ip, resolver_port = resolver_addr
    try:
        answers = await resolve_dns(fqdn, record_type, resolver_ip, resolver_port)

        # Normalize comparison
        normalized_expected = expected_value.lower().rstrip(".")
        normalized_answers = [a.lower().rstrip(".") for a in answers]

        resolved = normalized_expected in normalized_answers

        return ResolverResult(
            resolver_name=resolver_name,
            resolver_ip=resolver_ip,
            resolved=resolved,
            answers=answers,
        )
    except Exception as e:
        return ResolverResult(
            resolver_name=resolver_name,
            resolver_ip=resolver_ip,
            resolved=False,
            answers=[],
            error=str(e),
        )


async def verify_propagation(
    fqdn: str,
    record_type: str,
    expected_value: str,
    timeout_seconds: int = 300,
    poll_interval: int = 10,
    required_resolvers: int | None = None,
) -> PropagationResult:
    """
    Verify DNS propagation by polling all resolvers until the record is found.

    Args:
        fqdn: Fully qualified domain name (e.g., "www.example.com")
        record_type: DNS record type (A, AAAA, CNAME, etc.)
        expected_value: The expected record value
        timeout_seconds: Maximum time to wait for propagation (default 300s)
        poll_interval: Time between polling attempts (default 10s)
        required_resolvers: Minimum resolvers that must confirm (default: all)

    Returns:
        PropagationResult with status and per-resolver results
    """
    if required_resolvers is None:
        required_resolvers = len(RESOLVERS)

    logger.info(
        f"Verifying DNS propagation: {record_type} {fqdn} -> {expected_value} "
        f"(timeout={timeout_seconds}s, required={required_resolvers}/{len(RESOLVERS)})"
    )

    import time
    start_time = time.monotonic()
    elapsed = 0.0

    while elapsed < timeout_seconds:
        # Query all resolvers concurrently
        tasks = [
            check_resolver(fqdn, record_type, expected_value, name, addr)
            for name, addr in RESOLVERS.items()
        ]
        results = await asyncio.gather(*tasks)

        propagated_count = sum(1 for r in results if r.resolved)

        if propagated_count >= required_resolvers:
            elapsed = time.monotonic() - start_time
            logger.info(
                f"DNS propagation confirmed for {fqdn}: "
                f"{propagated_count}/{len(RESOLVERS)} resolvers ({elapsed:.1f}s)"
            )
            return PropagationResult(
                fqdn=fqdn,
                record_type=record_type,
                expected_value=expected_value,
                status=PropagationStatus.PROPAGATED,
                resolver_results=results,
                propagated_count=propagated_count,
                total_resolvers=len(RESOLVERS),
                elapsed_seconds=round(elapsed, 2),
            )

        if propagated_count > 0:
            logger.info(
                f"Partial propagation for {fqdn}: "
                f"{propagated_count}/{len(RESOLVERS)} resolvers"
            )

        await asyncio.sleep(poll_interval)
        elapsed = time.monotonic() - start_time

    # Timeout
    elapsed = time.monotonic() - start_time
    # Final check
    tasks = [
        check_resolver(fqdn, record_type, expected_value, name, addr)
        for name, addr in RESOLVERS.items()
    ]
    final_results = await asyncio.gather(*tasks)
    final_count = sum(1 for r in final_results if r.resolved)

    status = PropagationStatus.TIMEOUT
    if final_count >= required_resolvers:
        status = PropagationStatus.PROPAGATED
    elif final_count > 0:
        status = PropagationStatus.PARTIAL

    logger.warning(
        f"DNS propagation {'partial' if final_count > 0 else 'timed out'} for {fqdn}: "
        f"{final_count}/{len(RESOLVERS)} resolvers after {elapsed:.1f}s"
    )

    return PropagationResult(
        fqdn=fqdn,
        record_type=record_type,
        expected_value=expected_value,
        status=status,
        resolver_results=final_results,
        propagated_count=final_count,
        total_resolvers=len(RESOLVERS),
        elapsed_seconds=round(elapsed, 2),
    )


async def quick_check(fqdn: str, record_type: str, expected_value: str) -> PropagationResult:
    """
    Perform a single (non-polling) propagation check across all resolvers.

    Useful for dashboard status displays without waiting.
    """
    import time
    start_time = time.monotonic()

    tasks = [
        check_resolver(fqdn, record_type, expected_value, name, addr)
        for name, addr in RESOLVERS.items()
    ]
    results = await asyncio.gather(*tasks)

    propagated_count = sum(1 for r in results if r.resolved)
    elapsed = time.monotonic() - start_time

    if propagated_count == len(RESOLVERS):
        status = PropagationStatus.PROPAGATED
    elif propagated_count > 0:
        status = PropagationStatus.PARTIAL
    else:
        status = PropagationStatus.PENDING

    return PropagationResult(
        fqdn=fqdn,
        record_type=record_type,
        expected_value=expected_value,
        status=status,
        resolver_results=results,
        propagated_count=propagated_count,
        total_resolvers=len(RESOLVERS),
        elapsed_seconds=round(elapsed, 2),
    )
