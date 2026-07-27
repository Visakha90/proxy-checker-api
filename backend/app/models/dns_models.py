"""
Database models for DNS management features.
"""

from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Index
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class DNSAuditLog(Base):
    """Audit log for all DNS operations."""

    __tablename__ = "dns_audit_logs"
    __table_args__ = (
        Index("idx_dns_audit_domain", "domain"),
        Index("idx_dns_audit_action", "action"),
        Index("idx_dns_audit_operator", "operator"),
        Index("idx_dns_audit_created", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), nullable=False)
    domain = Column(String(255), nullable=False)
    record_type = Column(String(10), nullable=True)
    record_id = Column(Integer, nullable=True)
    host = Column(String(255), nullable=True)
    before_state = Column(Text, nullable=True)
    after_state = Column(Text, nullable=True)
    operator = Column(String(100), nullable=False, default="system")
    ip_address = Column(String(45), nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    metadata_ = Column("metadata", Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class DNSRollbackSnapshot(Base):
    """Stores snapshots of DNS state for rollback operations."""

    __tablename__ = "dns_rollback_snapshots"
    __table_args__ = (
        Index("idx_dns_rollback_domain", "domain"),
        Index("idx_dns_rollback_batch", "batch_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    batch_id = Column(String(64), nullable=False)
    domain = Column(String(255), nullable=False)
    operation = Column(String(20), nullable=False)  # create, update, delete
    record_id = Column(Integer, nullable=True)
    previous_state = Column(Text, nullable=True)  # JSON of record before change
    new_state = Column(Text, nullable=True)  # JSON of record after change
    rolled_back = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    rolled_back_at = Column(DateTime(timezone=True), nullable=True)
