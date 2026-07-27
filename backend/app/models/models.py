from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class ProxySource(Base):
    __tablename__ = "proxy_sources"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String(1024), unique=True, nullable=False)
    name = Column(String(255), nullable=True)
    proxy_type = Column(String(10), nullable=False, default="http")
    enabled = Column(Boolean, default=True)
    last_scraped = Column(DateTime(timezone=True), nullable=True)
    proxy_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Proxy(Base):
    __tablename__ = "proxies"
    __table_args__ = (
        Index("idx_proxy_ip_port", "ip", "port", unique=True),
        Index("idx_proxy_type", "proxy_type"),
        Index("idx_proxy_alive", "is_alive"),
        Index("idx_proxy_country", "country"),
        Index("idx_proxy_anonymity", "anonymity_level"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(45), nullable=False)
    port = Column(Integer, nullable=False)
    proxy_type = Column(String(10), nullable=False, default="http")
    source_url = Column(String(1024), nullable=True)

    is_alive = Column(Boolean, default=False)
    latency = Column(Float, nullable=True)
    status_code = Column(Integer, nullable=True)
    country = Column(String(100), nullable=True)
    country_code = Column(String(5), nullable=True)
    isp = Column(String(255), nullable=True)
    anonymity_level = Column(String(20), nullable=True)
    ssl_support = Column(Boolean, default=False)

    fail_count = Column(Integer, default=0)
    check_count = Column(Integer, default=0)
    first_seen = Column(DateTime(timezone=True), default=utcnow)
    last_seen = Column(DateTime(timezone=True), default=utcnow)
    last_checked = Column(DateTime(timezone=True), nullable=True)

    check_history = relationship("CheckHistory", back_populates="proxy", cascade="all, delete-orphan")


class CheckHistory(Base):
    __tablename__ = "check_history"

    id = Column(Integer, primary_key=True, index=True)
    proxy_id = Column(Integer, ForeignKey("proxies.id", ondelete="CASCADE"), nullable=False)
    is_alive = Column(Boolean, nullable=False)
    latency = Column(Float, nullable=True)
    status_code = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    checked_at = Column(DateTime(timezone=True), default=utcnow)

    proxy = relationship("Proxy", back_populates="check_history")


class Statistics(Base):
    __tablename__ = "statistics"

    id = Column(Integer, primary_key=True, index=True)
    total_proxies = Column(Integer, default=0)
    alive_proxies = Column(Integer, default=0)
    dead_proxies = Column(Integer, default=0)
    http_count = Column(Integer, default=0)
    https_count = Column(Integer, default=0)
    socks4_count = Column(Integer, default=0)
    socks5_count = Column(Integer, default=0)
    elite_count = Column(Integer, default=0)
    anonymous_count = Column(Integer, default=0)
    transparent_count = Column(Integer, default=0)
    avg_latency = Column(Float, default=0.0)
    recorded_at = Column(DateTime(timezone=True), default=utcnow)


class DownloadLog(Base):
    __tablename__ = "download_logs"

    id = Column(Integer, primary_key=True, index=True)
    file_type = Column(String(20), nullable=False)
    ip_address = Column(String(45), nullable=True)
    downloaded_at = Column(DateTime(timezone=True), default=utcnow)


class AppSettings(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
