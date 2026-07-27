"""
Production-quality DNS management API endpoints.

Provides:
- CRUD operations for DNS records (with audit logging)
- Batch create/update/delete with rollback
- DNS propagation verification
- SSL certificate deployment
- Audit log queries
- WebSocket endpoint for live DNS events
"""

import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel, Field

from app.core.security import get_current_admin
from app.services.namecom import namecom_client, DNSRecord, NamecomError
from app.services.dns_propagation import (
    verify_propagation,
    quick_check,
    PropagationStatus,
)
from app.services.ssl_manager import ssl_manager, SSLStatus
from app.services.dns_audit import dns_audit, DNSAction
from app.services.dns_batch import dns_batch, BatchOperation, BatchOperationType
from app.services.dns_events import dns_events, DNSEventType

router = APIRouter()


# ─── Request/Response Schemas ─────────────────────────────────────────────────


class DNSRecordCreate(BaseModel):
    host: str = Field(..., description="Hostname (e.g., 'www', '' for apex)")
    record_type: str = Field(..., pattern="^(A|AAAA|CNAME|MX|TXT|NS|SRV)$")
    answer: str = Field(..., description="Record value")
    ttl: int = Field(default=300, ge=60, le=86400)
    priority: int | None = Field(default=None, ge=0, le=65535)


class DNSRecordUpdate(BaseModel):
    host: str | None = None
    record_type: str | None = Field(default=None, pattern="^(A|AAAA|CNAME|MX|TXT|NS|SRV)$")
    answer: str | None = None
    ttl: int | None = Field(default=None, ge=60, le=86400)
    priority: int | None = Field(default=None, ge=0, le=65535)


class DNSRecordResponse(BaseModel):
    id: int
    domain_name: str
    host: str
    fqdn: str
    record_type: str
    answer: str
    ttl: int
    priority: int | None = None


class PropagationCheckRequest(BaseModel):
    fqdn: str = Field(..., description="Fully qualified domain name")
    record_type: str = Field(..., pattern="^(A|AAAA|CNAME|MX|TXT|NS)$")
    expected_value: str = Field(..., description="Expected DNS record value")
    timeout_seconds: int = Field(default=300, ge=10, le=600)
    poll_interval: int = Field(default=10, ge=5, le=60)


class PropagationQuickCheckRequest(BaseModel):
    fqdn: str
    record_type: str = Field(..., pattern="^(A|AAAA|CNAME|MX|TXT|NS)$")
    expected_value: str


class SSLDeployRequest(BaseModel):
    domain: str = Field(..., description="Base domain (e.g., 'example.com')")
    subdomain: str = Field(default="", description="Subdomain (e.g., 'www')")
    propagation_timeout: int = Field(default=300, ge=60, le=600)


class BatchOperationItem(BaseModel):
    operation: str = Field(..., pattern="^(create|update|delete)$")
    host: str = Field(default="")
    record_type: str = Field(default="A", pattern="^(A|AAAA|CNAME|MX|TXT|NS|SRV)$")
    answer: str = Field(default="")
    ttl: int = Field(default=300, ge=60, le=86400)
    priority: int | None = None
    record_id: int | None = None


class BatchRequest(BaseModel):
    operations: list[BatchOperationItem] = Field(..., min_length=1, max_length=100)
    stop_on_failure: bool = Field(default=False)


class RollbackRequest(BaseModel):
    batch_id: str = Field(..., min_length=1, max_length=64)


# ─── Helper ───────────────────────────────────────────────────────────────────


def _record_to_response(record: DNSRecord) -> DNSRecordResponse:
    return DNSRecordResponse(
        id=record.id,
        domain_name=record.domain_name,
        host=record.host,
        fqdn=record.fqdn,
        record_type=record.record_type,
        answer=record.answer,
        ttl=record.ttl,
        priority=record.priority,
    )


def _get_operator(admin: dict) -> str:
    return admin.get("sub", "admin")


# ─── Domain Endpoints ─────────────────────────────────────────────────────────


@router.get("/domains")
async def list_domains(admin: dict = Depends(get_current_admin)):
    """List all domains in the Name.com account."""
    try:
        domains = await namecom_client.list_domains()
        return {"domains": domains}
    except NamecomError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ─── Record CRUD Endpoints ────────────────────────────────────────────────────


@router.get("/domains/{domain}/records", response_model=list[DNSRecordResponse])
async def list_dns_records(
    domain: str,
    admin: dict = Depends(get_current_admin),
):
    """List all DNS records for a domain."""
    try:
        records = await namecom_client.list_records(domain)
        return [_record_to_response(r) for r in records]
    except NamecomError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/domains/{domain}/records/{record_id}", response_model=DNSRecordResponse)
async def get_dns_record(
    domain: str,
    record_id: int,
    admin: dict = Depends(get_current_admin),
):
    """Get a specific DNS record."""
    try:
        record = await namecom_client.get_record(domain, record_id)
        return _record_to_response(record)
    except NamecomError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/domains/{domain}/records", response_model=DNSRecordResponse, status_code=201)
async def create_dns_record(
    domain: str,
    record: DNSRecordCreate,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """Create a new DNS record with audit logging."""
    operator = _get_operator(admin)
    ip_address = request.client.host if request.client else None

    try:
        created = await namecom_client.create_record(
            domain=domain,
            host=record.host,
            record_type=record.record_type,
            answer=record.answer,
            ttl=record.ttl,
            priority=record.priority,
        )

        # Audit log
        await dns_audit.log(
            action=DNSAction.CREATE,
            domain=domain,
            record_type=record.record_type,
            record_id=created.id,
            host=record.host,
            after_state=created.to_dict(),
            operator=operator,
            ip_address=ip_address,
        )

        # WebSocket event
        await dns_events.emit_record_created(domain, created.to_dict())

        return _record_to_response(created)
    except NamecomError as e:
        await dns_audit.log(
            action=DNSAction.CREATE,
            domain=domain,
            record_type=record.record_type,
            host=record.host,
            operator=operator,
            ip_address=ip_address,
            success=False,
            error_message=e.message,
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/domains/{domain}/records/{record_id}", response_model=DNSRecordResponse)
async def update_dns_record(
    domain: str,
    record_id: int,
    record: DNSRecordUpdate,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """Update an existing DNS record with audit logging."""
    operator = _get_operator(admin)
    ip_address = request.client.host if request.client else None

    try:
        # Get current state for audit
        current = await namecom_client.get_record(domain, record_id)
        before_state = current.to_dict()

        updated = await namecom_client.update_record(
            domain=domain,
            record_id=record_id,
            host=record.host,
            record_type=record.record_type,
            answer=record.answer,
            ttl=record.ttl,
            priority=record.priority,
        )

        # Audit log
        await dns_audit.log(
            action=DNSAction.UPDATE,
            domain=domain,
            record_type=updated.record_type,
            record_id=record_id,
            host=updated.host,
            before_state=before_state,
            after_state=updated.to_dict(),
            operator=operator,
            ip_address=ip_address,
        )

        # WebSocket event
        await dns_events.emit_record_updated(domain, before_state, updated.to_dict())

        return _record_to_response(updated)
    except NamecomError as e:
        await dns_audit.log(
            action=DNSAction.UPDATE,
            domain=domain,
            record_id=record_id,
            operator=operator,
            ip_address=ip_address,
            success=False,
            error_message=e.message,
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.delete("/domains/{domain}/records/{record_id}", status_code=204)
async def delete_dns_record(
    domain: str,
    record_id: int,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """Delete a DNS record with audit logging."""
    operator = _get_operator(admin)
    ip_address = request.client.host if request.client else None

    try:
        # Get current state for audit
        current = await namecom_client.get_record(domain, record_id)
        before_state = current.to_dict()

        await namecom_client.delete_record(domain, record_id)

        # Audit log
        await dns_audit.log(
            action=DNSAction.DELETE,
            domain=domain,
            record_type=current.record_type,
            record_id=record_id,
            host=current.host,
            before_state=before_state,
            operator=operator,
            ip_address=ip_address,
        )

        # WebSocket event
        await dns_events.emit_record_deleted(domain, before_state)

    except NamecomError as e:
        await dns_audit.log(
            action=DNSAction.DELETE,
            domain=domain,
            record_id=record_id,
            operator=operator,
            ip_address=ip_address,
            success=False,
            error_message=e.message,
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)


# ─── Batch Operations ─────────────────────────────────────────────────────────


@router.post("/domains/{domain}/records/batch")
async def batch_dns_operations(
    domain: str,
    batch: BatchRequest,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """
    Execute batch DNS operations with rollback support.

    Supports mixed create/update/delete in a single request.
    Each operation is snapshotted for potential rollback.
    """
    operator = _get_operator(admin)
    ip_address = request.client.host if request.client else None

    operations = [
        BatchOperation(
            operation=BatchOperationType(op.operation),
            host=op.host,
            record_type=op.record_type,
            answer=op.answer,
            ttl=op.ttl,
            priority=op.priority,
            record_id=op.record_id,
        )
        for op in batch.operations
    ]

    # Emit batch start event
    await dns_events.emit_batch_started(domain, "pending", len(operations))

    result = await dns_batch.execute_batch(
        domain=domain,
        operations=operations,
        operator=operator,
        ip_address=ip_address,
        stop_on_failure=batch.stop_on_failure,
    )

    # Emit batch complete event
    await dns_events.emit_batch_completed(
        domain,
        result.batch_id,
        {
            "total": result.total_operations,
            "successful": result.successful,
            "failed": result.failed,
        },
    )

    return {
        "batch_id": result.batch_id,
        "domain": result.domain,
        "total_operations": result.total_operations,
        "successful": result.successful,
        "failed": result.failed,
        "rollback_available": result.rollback_available,
        "results": [
            {
                "index": r.index,
                "operation": r.operation.value,
                "success": r.success,
                "record": r.record.to_dict() if r.record else None,
                "error": r.error,
            }
            for r in result.results
        ],
    }


@router.post("/domains/{domain}/records/batch/rollback")
async def rollback_batch(
    domain: str,
    rollback: RollbackRequest,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """Rollback a previous batch operation."""
    operator = _get_operator(admin)
    ip_address = request.client.host if request.client else None

    result = await dns_batch.rollback_batch(
        batch_id=rollback.batch_id,
        operator=operator,
        ip_address=ip_address,
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    # Emit rollback event
    await dns_events.emit(
        DNSEventType.BATCH_ROLLBACK,
        {"batch_id": rollback.batch_id, **result},
        domain,
    )

    return result


@router.get("/domains/{domain}/records/batch/history")
async def get_batch_history(
    domain: str,
    limit: int = Query(50, ge=1, le=200),
    admin: dict = Depends(get_current_admin),
):
    """Get batch operation history for a domain."""
    return await dns_batch.get_batch_history(domain=domain, limit=limit)


# ─── Propagation Verification ─────────────────────────────────────────────────


@router.post("/propagation/verify")
async def verify_dns_propagation(
    check: PropagationCheckRequest,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """
    Verify DNS propagation across Google and Cloudflare resolvers.

    Polls resolvers until the expected value is confirmed or timeout is reached.
    """
    operator = _get_operator(admin)
    ip_address = request.client.host if request.client else None

    # Extract domain from fqdn for events
    parts = check.fqdn.split(".")
    domain = ".".join(parts[-2:]) if len(parts) >= 2 else check.fqdn

    await dns_events.emit_propagation_started(domain, check.fqdn, check.record_type)

    result = await verify_propagation(
        fqdn=check.fqdn,
        record_type=check.record_type,
        expected_value=check.expected_value,
        timeout_seconds=check.timeout_seconds,
        poll_interval=check.poll_interval,
    )

    # Audit log
    await dns_audit.log(
        action=DNSAction.PROPAGATION_CHECK,
        domain=domain,
        record_type=check.record_type,
        host=check.fqdn,
        operator=operator,
        ip_address=ip_address,
        success=result.status == PropagationStatus.PROPAGATED,
        metadata={
            "status": result.status.value,
            "propagated_count": result.propagated_count,
            "total_resolvers": result.total_resolvers,
            "elapsed_seconds": result.elapsed_seconds,
        },
    )

    # Emit completion event
    await dns_events.emit_propagation_completed(
        domain,
        {
            "fqdn": result.fqdn,
            "status": result.status.value,
            "propagated_count": result.propagated_count,
            "total_resolvers": result.total_resolvers,
            "elapsed_seconds": result.elapsed_seconds,
        },
    )

    return {
        "fqdn": result.fqdn,
        "record_type": result.record_type,
        "expected_value": result.expected_value,
        "status": result.status.value,
        "propagated_count": result.propagated_count,
        "total_resolvers": result.total_resolvers,
        "elapsed_seconds": result.elapsed_seconds,
        "resolvers": [
            {
                "name": r.resolver_name,
                "ip": r.resolver_ip,
                "resolved": r.resolved,
                "answers": r.answers,
                "error": r.error,
            }
            for r in result.resolver_results
        ],
    }


@router.post("/propagation/check")
async def quick_propagation_check(
    check: PropagationQuickCheckRequest,
    admin: dict = Depends(get_current_admin),
):
    """
    Quick (non-polling) propagation check across all resolvers.

    Returns immediately with current state - does not wait for propagation.
    """
    result = await quick_check(
        fqdn=check.fqdn,
        record_type=check.record_type,
        expected_value=check.expected_value,
    )

    return {
        "fqdn": result.fqdn,
        "record_type": result.record_type,
        "expected_value": result.expected_value,
        "status": result.status.value,
        "propagated_count": result.propagated_count,
        "total_resolvers": result.total_resolvers,
        "elapsed_seconds": result.elapsed_seconds,
        "resolvers": [
            {
                "name": r.resolver_name,
                "ip": r.resolver_ip,
                "resolved": r.resolved,
                "answers": r.answers,
                "error": r.error,
            }
            for r in result.resolver_results
        ],
    }


# ─── SSL Certificate Deployment ───────────────────────────────────────────────


@router.post("/ssl/deploy")
async def deploy_ssl_certificate(
    deploy: SSLDeployRequest,
    request: Request,
    admin: dict = Depends(get_current_admin),
):
    """
    Deploy SSL certificate using Let's Encrypt with DNS-01 challenge.

    Flow:
    1. Creates ACME challenge TXT record
    2. Waits for DNS propagation
    3. Requests certificate from Let's Encrypt
    4. Cleans up challenge record
    """
    operator = _get_operator(admin)
    ip_address = request.client.host if request.client else None
    fqdn = f"{deploy.subdomain}.{deploy.domain}" if deploy.subdomain else deploy.domain

    # Emit SSL start event
    await dns_events.emit_ssl_started(deploy.domain, fqdn)

    # Run deployment (may take a while due to propagation wait)
    cert = await ssl_manager.deploy_ssl(
        domain=deploy.domain,
        subdomain=deploy.subdomain,
        propagation_timeout=deploy.propagation_timeout,
    )

    # Audit log
    await dns_audit.log(
        action=DNSAction.SSL_DEPLOY,
        domain=deploy.domain,
        host=fqdn,
        operator=operator,
        ip_address=ip_address,
        success=cert.status == SSLStatus.ISSUED,
        error_message=cert.error,
        metadata={
            "status": cert.status.value,
            "cert_path": cert.cert_path,
            "key_path": cert.key_path,
        },
    )

    # Emit result event
    if cert.status == SSLStatus.ISSUED:
        await dns_events.emit_ssl_completed(
            deploy.domain,
            fqdn,
            {"cert_path": cert.cert_path, "key_path": cert.key_path},
        )
    else:
        await dns_events.emit_ssl_failed(deploy.domain, fqdn, cert.error or "Unknown error")

    return {
        "domain": fqdn,
        "status": cert.status.value,
        "cert_path": cert.cert_path,
        "key_path": cert.key_path,
        "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
        "error": cert.error,
    }


@router.get("/ssl/certificates")
async def list_ssl_certificates(admin: dict = Depends(get_current_admin)):
    """List all tracked SSL certificates."""
    certs = await ssl_manager.list_certificates()
    return [
        {
            "domain": c.domain,
            "status": c.status.value,
            "cert_path": c.cert_path,
            "key_path": c.key_path,
            "issued_at": c.issued_at.isoformat() if c.issued_at else None,
            "error": c.error,
        }
        for c in certs
    ]


# ─── Audit Logs ───────────────────────────────────────────────────────────────


@router.get("/audit")
async def get_audit_logs(
    domain: str | None = None,
    action: str | None = None,
    operator: str | None = None,
    success: bool | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(get_current_admin),
):
    """Query DNS audit logs with filtering and pagination."""
    logs, total = await dns_audit.get_logs(
        domain=domain,
        action=action,
        operator=operator,
        success=success,
        limit=limit,
        offset=offset,
    )

    return {
        "logs": [
            {
                "id": log.id,
                "action": log.action,
                "domain": log.domain,
                "record_type": log.record_type,
                "record_id": log.record_id,
                "host": log.host,
                "before_state": json.loads(log.before_state) if log.before_state else None,
                "after_state": json.loads(log.after_state) if log.after_state else None,
                "operator": log.operator,
                "ip_address": log.ip_address,
                "success": log.success,
                "error_message": log.error_message,
                "metadata": json.loads(log.metadata_) if log.metadata_ else None,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/audit/{log_id}")
async def get_audit_log_detail(
    log_id: int,
    admin: dict = Depends(get_current_admin),
):
    """Get a specific audit log entry."""
    log = await dns_audit.get_log_by_id(log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Audit log entry not found")

    return {
        "id": log.id,
        "action": log.action,
        "domain": log.domain,
        "record_type": log.record_type,
        "record_id": log.record_id,
        "host": log.host,
        "before_state": json.loads(log.before_state) if log.before_state else None,
        "after_state": json.loads(log.after_state) if log.after_state else None,
        "operator": log.operator,
        "ip_address": log.ip_address,
        "success": log.success,
        "error_message": log.error_message,
        "metadata": json.loads(log.metadata_) if log.metadata_ else None,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


# ─── DNS WebSocket ────────────────────────────────────────────────────────────


@router.websocket("/ws")
async def dns_websocket_endpoint(websocket: WebSocket, domain: str | None = None):
    """
    WebSocket endpoint for live DNS events.

    Clients receive real-time updates for DNS operations:
    - Record changes
    - Batch progress
    - Propagation status
    - SSL deployment progress

    Optional query param `domain` to filter events for a specific domain.
    """
    await websocket.accept()
    await dns_events.connect(websocket, domain)

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
                if data == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif data.startswith("subscribe:"):
                    # Allow dynamic domain subscription
                    sub_domain = data.split(":", 1)[1].strip()
                    if sub_domain:
                        if sub_domain not in dns_events._domain_subscriptions:
                            dns_events._domain_subscriptions[sub_domain] = set()
                        dns_events._domain_subscriptions[sub_domain].add(websocket)
                        await websocket.send_text(
                            json.dumps({"type": "subscribed", "domain": sub_domain})
                        )
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await dns_events.disconnect(websocket)
