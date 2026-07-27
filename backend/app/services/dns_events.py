"""
WebSocket Event Broadcasting for DNS Operations.

Broadcasts real-time events to connected clients for:
- Record changes (create, update, delete)
- Propagation status updates
- SSL deployment progress
- Batch operation progress
- Audit log entries
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class DNSEventType(str, Enum):
    RECORD_CREATED = "dns.record.created"
    RECORD_UPDATED = "dns.record.updated"
    RECORD_DELETED = "dns.record.deleted"
    BATCH_STARTED = "dns.batch.started"
    BATCH_PROGRESS = "dns.batch.progress"
    BATCH_COMPLETED = "dns.batch.completed"
    BATCH_ROLLBACK = "dns.batch.rollback"
    PROPAGATION_STARTED = "dns.propagation.started"
    PROPAGATION_PROGRESS = "dns.propagation.progress"
    PROPAGATION_COMPLETED = "dns.propagation.completed"
    SSL_STARTED = "dns.ssl.started"
    SSL_PROGRESS = "dns.ssl.progress"
    SSL_COMPLETED = "dns.ssl.completed"
    SSL_FAILED = "dns.ssl.failed"
    ERROR = "dns.error"


class DNSEventBroadcaster:
    """
    Manages WebSocket connections and broadcasts DNS events in real-time.

    Clients subscribe to DNS events and receive updates as operations occur.
    Supports topic-based filtering (e.g., subscribe to events for a specific domain).
    """

    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._domain_subscriptions: dict[str, set[WebSocket]] = {}
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._broadcaster_task: asyncio.Task | None = None

    @property
    def connected_count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket, domain: str | None = None):
        """Register a new WebSocket client."""
        self._clients.add(websocket)
        if domain:
            if domain not in self._domain_subscriptions:
                self._domain_subscriptions[domain] = set()
            self._domain_subscriptions[domain].add(websocket)
        logger.info(
            f"DNS WebSocket client connected. "
            f"Total: {len(self._clients)}, Domain filter: {domain}"
        )

    async def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket client."""
        self._clients.discard(websocket)
        for domain_clients in self._domain_subscriptions.values():
            domain_clients.discard(websocket)
        logger.info(f"DNS WebSocket client disconnected. Total: {len(self._clients)}")

    async def emit(
        self,
        event_type: DNSEventType,
        data: dict[str, Any],
        domain: str | None = None,
    ):
        """
        Emit a DNS event to all connected clients.

        Args:
            event_type: The type of DNS event
            data: Event payload data
            domain: Optional domain to target specific subscribers
        """
        event = {
            "type": event_type.value,
            "data": data,
            "domain": domain,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        message = json.dumps(event, default=str)

        # Determine target clients
        if domain and domain in self._domain_subscriptions:
            targets = self._domain_subscriptions[domain] | self._clients
        else:
            targets = self._clients.copy()

        disconnected = set()
        for client in targets:
            try:
                await client.send_text(message)
            except Exception:
                disconnected.add(client)

        # Cleanup disconnected clients
        for client in disconnected:
            await self.disconnect(client)

        if targets:
            logger.debug(
                f"DNS event {event_type.value} broadcast to "
                f"{len(targets) - len(disconnected)} clients"
            )

    # ─── Convenience Emitters ─────────────────────────────────────────────

    async def emit_record_created(self, domain: str, record: dict):
        """Emit record creation event."""
        await self.emit(DNSEventType.RECORD_CREATED, record, domain)

    async def emit_record_updated(self, domain: str, before: dict, after: dict):
        """Emit record update event."""
        await self.emit(
            DNSEventType.RECORD_UPDATED,
            {"before": before, "after": after},
            domain,
        )

    async def emit_record_deleted(self, domain: str, record: dict):
        """Emit record deletion event."""
        await self.emit(DNSEventType.RECORD_DELETED, record, domain)

    async def emit_batch_started(self, domain: str, batch_id: str, total_ops: int):
        """Emit batch operation start event."""
        await self.emit(
            DNSEventType.BATCH_STARTED,
            {"batch_id": batch_id, "total_operations": total_ops},
            domain,
        )

    async def emit_batch_progress(
        self, domain: str, batch_id: str, completed: int, total: int
    ):
        """Emit batch progress event."""
        await self.emit(
            DNSEventType.BATCH_PROGRESS,
            {"batch_id": batch_id, "completed": completed, "total": total},
            domain,
        )

    async def emit_batch_completed(self, domain: str, batch_id: str, result: dict):
        """Emit batch completion event."""
        await self.emit(
            DNSEventType.BATCH_COMPLETED,
            {"batch_id": batch_id, **result},
            domain,
        )

    async def emit_propagation_started(self, domain: str, fqdn: str, record_type: str):
        """Emit propagation check start."""
        await self.emit(
            DNSEventType.PROPAGATION_STARTED,
            {"fqdn": fqdn, "record_type": record_type},
            domain,
        )

    async def emit_propagation_progress(
        self, domain: str, fqdn: str, confirmed: int, total: int
    ):
        """Emit propagation progress."""
        await self.emit(
            DNSEventType.PROPAGATION_PROGRESS,
            {"fqdn": fqdn, "confirmed": confirmed, "total": total},
            domain,
        )

    async def emit_propagation_completed(self, domain: str, result: dict):
        """Emit propagation verification result."""
        await self.emit(DNSEventType.PROPAGATION_COMPLETED, result, domain)

    async def emit_ssl_started(self, domain: str, fqdn: str):
        """Emit SSL deployment start."""
        await self.emit(DNSEventType.SSL_STARTED, {"fqdn": fqdn}, domain)

    async def emit_ssl_progress(self, domain: str, fqdn: str, status: str):
        """Emit SSL deployment progress."""
        await self.emit(
            DNSEventType.SSL_PROGRESS, {"fqdn": fqdn, "status": status}, domain
        )

    async def emit_ssl_completed(self, domain: str, fqdn: str, cert_info: dict):
        """Emit SSL certificate issuance success."""
        await self.emit(
            DNSEventType.SSL_COMPLETED, {"fqdn": fqdn, **cert_info}, domain
        )

    async def emit_ssl_failed(self, domain: str, fqdn: str, error: str):
        """Emit SSL deployment failure."""
        await self.emit(
            DNSEventType.SSL_FAILED, {"fqdn": fqdn, "error": error}, domain
        )

    async def emit_error(self, domain: str, message: str, details: dict | None = None):
        """Emit a DNS error event."""
        await self.emit(
            DNSEventType.ERROR,
            {"message": message, "details": details or {}},
            domain,
        )


# Singleton instance
dns_events = DNSEventBroadcaster()
