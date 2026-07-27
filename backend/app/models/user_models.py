"""
User registration and multi-user models.
Supports user accounts, webhooks, scheduled exports, and custom settings.
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, DateTime, Text, BigInteger, Index, JSON
)
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    """Registered user account."""

    __tablename__ = "users"
    __table_args__ = (
        Index("idx_user_email", "email", unique=True),
        Index("idx_user_username", "username", unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False, default="user")  # user, premium, admin
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Subscription
    plan = Column(String(20), default="free")  # free, pro, enterprise
    stripe_customer_id = Column(String(100), nullable=True)
    stripe_subscription_id = Column(String(100), nullable=True)

    # Settings
    telegram_chat_id = Column(String(50), nullable=True)
    discord_webhook_url = Column(String(512), nullable=True)
    notification_enabled = Column(Boolean, default=False)

    # Limits
    api_calls_today = Column(Integer, default=0)
    api_calls_total = Column(BigInteger, default=0)

    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_login_at = Column(DateTime(timezone=True), nullable=True)


class Webhook(Base):
    """User webhook for notifications."""

    __tablename__ = "webhooks"
    __table_args__ = (Index("idx_webhook_user", "user_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    url = Column(String(1024), nullable=False)
    event_type = Column(String(50), nullable=False)  # proxy_down, new_elite, count_drop, check_complete
    is_active = Column(Boolean, default=True)
    secret = Column(String(64), nullable=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    trigger_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ScheduledExport(Base):
    """Scheduled proxy list export."""

    __tablename__ = "scheduled_exports"
    __table_args__ = (Index("idx_export_user", "user_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    schedule = Column(String(50), nullable=False)  # hourly, daily, weekly
    proxy_type = Column(String(20), nullable=True)
    format = Column(String(10), default="txt")
    filters = Column(Text, nullable=True)  # JSON filters
    delivery_method = Column(String(20), default="webhook")  # webhook, email, telegram
    delivery_target = Column(String(512), nullable=False)
    is_active = Column(Boolean, default=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ProxyUptime(Base):
    """Proxy uptime tracking over time."""

    __tablename__ = "proxy_uptime"
    __table_args__ = (
        Index("idx_uptime_proxy", "proxy_id"),
        Index("idx_uptime_date", "date"),
    )

    id = Column(Integer, primary_key=True, index=True)
    proxy_id = Column(Integer, nullable=False)
    date = Column(String(10), nullable=False)  # YYYY-MM-DD
    checks_total = Column(Integer, default=0)
    checks_alive = Column(Integer, default=0)
    uptime_pct = Column(Float, default=0.0)
    avg_latency = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ProxyChain(Base):
    """Multi-hop proxy chain configuration."""

    __tablename__ = "proxy_chains"
    __table_args__ = (Index("idx_chain_user", "user_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    hops = Column(Text, nullable=False)  # JSON array of proxy IDs
    is_active = Column(Boolean, default=True)
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    last_latency = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
