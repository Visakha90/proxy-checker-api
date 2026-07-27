"""
Database models for the Public API platform.
Covers API keys, usage tracking, and request logs.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, DateTime, Text, Index, BigInteger
)
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class APIKey(Base):
    """API key for public API access."""

    __tablename__ = "api_keys"
    __table_args__ = (
        Index("idx_api_key_key", "key", unique=True),
        Index("idx_api_key_user", "user_id"),
        Index("idx_api_key_tier", "tier"),
    )

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(64), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    user_id = Column(String(100), nullable=False)
    tier = Column(String(20), nullable=False, default="free")  # guest, free, premium
    is_active = Column(Boolean, default=True)

    # Quota
    requests_today = Column(Integer, default=0)
    requests_total = Column(BigInteger, default=0)
    quota_daily = Column(Integer, default=1000)  # -1 for unlimited
    bandwidth_bytes = Column(BigInteger, default=0)

    # Metadata
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    last_ip = Column(String(45), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class APIRequestLog(Base):
    """Log of every API request for analytics."""

    __tablename__ = "api_request_logs"
    __table_args__ = (
        Index("idx_api_log_key", "api_key_id"),
        Index("idx_api_log_endpoint", "endpoint"),
        Index("idx_api_log_created", "created_at"),
        Index("idx_api_log_status", "status_code"),
    )

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    api_key_id = Column(Integer, nullable=True)
    api_key_str = Column(String(64), nullable=True)
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False, default="GET")
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Float, nullable=True)
    response_bytes = Column(Integer, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(512), nullable=True)
    country = Column(String(100), nullable=True)
    query_params = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class APIUsageDaily(Base):
    """Aggregated daily usage per API key."""

    __tablename__ = "api_usage_daily"
    __table_args__ = (
        Index("idx_api_usage_key_date", "api_key_id", "date", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    api_key_id = Column(Integer, nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    requests = Column(Integer, default=0)
    bandwidth_bytes = Column(BigInteger, default=0)
    errors = Column(Integer, default=0)
    avg_response_ms = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
