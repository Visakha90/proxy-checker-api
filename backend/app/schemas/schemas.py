from pydantic import BaseModel, Field
from datetime import datetime


class ProxySourceCreate(BaseModel):
    url: str = Field(..., max_length=1024)
    name: str | None = None
    proxy_type: str = Field(default="http", pattern="^(http|https|socks4|socks5)$")
    enabled: bool = True


class ProxySourceResponse(BaseModel):
    id: int
    url: str
    name: str | None
    proxy_type: str
    enabled: bool
    last_scraped: datetime | None
    proxy_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class ProxyResponse(BaseModel):
    id: int
    ip: str
    port: int
    proxy_type: str
    is_alive: bool
    latency: float | None
    status_code: int | None
    country: str | None
    country_code: str | None
    isp: str | None
    anonymity_level: str | None
    ssl_support: bool
    first_seen: datetime
    last_seen: datetime
    last_checked: datetime | None

    class Config:
        from_attributes = True


class ProxyListResponse(BaseModel):
    proxies: list[ProxyResponse]
    total: int
    page: int
    page_size: int


class StatsResponse(BaseModel):
    total_proxies: int
    alive_proxies: int
    dead_proxies: int
    http_count: int
    https_count: int
    socks4_count: int
    socks5_count: int
    elite_count: int
    anonymous_count: int
    transparent_count: int
    avg_latency: float
    newest_proxy: datetime | None
    last_update: datetime | None


class ProxyTestRequest(BaseModel):
    target_url: str = Field(..., max_length=2048)
    timeout: int = Field(default=10, ge=1, le=60)
    method: str = Field(default="GET", pattern="^(GET|POST)$")
    proxy_type: str | None = Field(default=None, pattern="^(http|https|socks4|socks5)$")
    limit: int = Field(default=100, ge=1, le=10000)


class ProxyTestResult(BaseModel):
    ip: str
    port: int
    proxy_type: str
    working: bool
    latency: float | None
    status_code: int | None
    error: str | None


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SettingsUpdate(BaseModel):
    scrape_interval_seconds: int | None = None
    check_interval_seconds: int | None = None
    check_concurrency: int | None = None
    check_timeout: int | None = None
    max_failures_before_delete: int | None = None
    max_proxy_age_hours: int | None = None
    retry_count: int | None = None
