"""
Public API v1 - Production-ready proxy API with filtering, caching, and rate limiting.

Base URL: /api/v1
Authentication: API Key via X-API-Key header or ?api_key= query param
Rate Limits: Guest 100/hr, Free 1000/day, Premium unlimited
"""

import hashlib
import json
import time
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Response, HTTPException, Query, Depends
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select, func, desc, distinct

from app.core.database import async_session
from app.core.redis import redis_client
from app.models.models import Proxy
from app.models.api_models import APIKey
from app.services.api_keys import api_key_service, TIER_LIMITS
from app.services.api_usage import api_usage

logger = logging.getLogger(__name__)
router = APIRouter()

CACHE_TTL = 30  # seconds


# ─── Middleware / Dependencies ────────────────────────────────────────────────


async def get_api_key_from_request(request: Request) -> tuple[APIKey | None, str]:
    """Extract and validate API key from request."""
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not key:
        return None, "guest"

    api_key = await api_key_service.validate_key(key)
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")

    return api_key, api_key.tier


async def enforce_rate_limit(request: Request) -> tuple[APIKey | None, dict]:
    """Validate API key and enforce rate limits."""
    api_key, tier = await get_api_key_from_request(request)

    # For guests, rate limit by IP
    rate_key = api_key.key if api_key else f"guest:{request.client.host if request.client else 'unknown'}"

    allowed, info = await api_key_service.check_rate_limit(rate_key, tier)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Tier": tier,
                "X-RateLimit-Remaining": "0",
                "Retry-After": "60",
            },
        )

    return api_key, info


# ─── Cache Helpers ────────────────────────────────────────────────────────────


async def get_cached(cache_key: str) -> dict | None:
    """Get cached response from Redis."""
    data = await redis_client.get(cache_key)
    if data:
        return json.loads(data)
    return None


async def set_cached(cache_key: str, data: dict, ttl: int = CACHE_TTL):
    """Store response in Redis cache."""
    await redis_client.setex(cache_key, ttl, json.dumps(data, default=str))


def make_cache_key(prefix: str, params: dict) -> str:
    """Generate a deterministic cache key from request parameters."""
    param_str = json.dumps(sorted(params.items()), default=str)
    h = hashlib.md5(param_str.encode()).hexdigest()[:12]
    return f"apicache:{prefix}:{h}"


def build_etag(data: dict) -> str:
    """Generate ETag from response data."""
    content = json.dumps(data, default=str, sort_keys=True)
    return hashlib.md5(content.encode()).hexdigest()[:16]


# ─── Response Builder ─────────────────────────────────────────────────────────


async def build_proxy_response(
    request: Request,
    response: Response,
    api_key: APIKey | None,
    rate_info: dict,
    proxy_type: str | None = None,
    extra_filters: dict | None = None,
):
    """Core query builder for proxy endpoints."""
    start_time = time.monotonic()

    # Parse query parameters
    country = request.query_params.get("country")
    city = request.query_params.get("city")
    p_type = request.query_params.get("type") or proxy_type
    anonymity = request.query_params.get("anonymity")
    alive = request.query_params.get("alive")
    ssl = request.query_params.get("ssl")
    timeout_param = request.query_params.get("timeout")
    latency_lt = request.query_params.get("latency_lt")
    latency_gt = request.query_params.get("latency_gt")
    limit = min(int(request.query_params.get("limit", "100")), 1000)
    page = max(int(request.query_params.get("page", "1")), 1)
    sort = request.query_params.get("sort", "latency")

    # Build cache key
    params = {
        "type": p_type, "country": country, "city": city, "anonymity": anonymity,
        "alive": alive, "ssl": ssl, "latency_lt": latency_lt, "latency_gt": latency_gt,
        "limit": limit, "page": page, "sort": sort, "timeout": timeout_param,
    }
    cache_key = make_cache_key("proxies", params)

    # Check ETag
    if_none_match = request.headers.get("If-None-Match")

    # Try cache
    cached = await get_cached(cache_key)
    if cached:
        etag = build_etag(cached)
        if if_none_match and if_none_match == etag:
            return Response(status_code=304)
        response.headers["ETag"] = etag
        response.headers["X-Cache"] = "HIT"
        await _log_request(request, api_key, rate_info, 200, start_time, cached)
        return _add_rate_headers(cached, response, rate_info)

    # Query database
    async with async_session() as session:
        query = select(Proxy)
        count_query = select(func.count(Proxy.id))

        # Default: alive only
        if alive is None or alive.lower() == "true":
            query = query.where(Proxy.is_alive == True)
            count_query = count_query.where(Proxy.is_alive == True)
        elif alive.lower() == "false":
            query = query.where(Proxy.is_alive == False)
            count_query = count_query.where(Proxy.is_alive == False)

        if p_type:
            query = query.where(Proxy.proxy_type == p_type.lower())
            count_query = count_query.where(Proxy.proxy_type == p_type.lower())
        if country:
            query = query.where(Proxy.country_code == country.upper())
            count_query = count_query.where(Proxy.country_code == country.upper())
        if anonymity:
            query = query.where(Proxy.anonymity_level == anonymity.lower())
            count_query = count_query.where(Proxy.anonymity_level == anonymity.lower())
        if ssl and ssl.lower() == "true":
            query = query.where(Proxy.ssl_support == True)
            count_query = count_query.where(Proxy.ssl_support == True)
        if latency_lt:
            query = query.where(Proxy.latency <= float(latency_lt))
            count_query = count_query.where(Proxy.latency <= float(latency_lt))
        if latency_gt:
            query = query.where(Proxy.latency >= float(latency_gt))
            count_query = count_query.where(Proxy.latency >= float(latency_gt))
        if timeout_param:
            query = query.where(Proxy.latency <= float(timeout_param) * 1000)
            count_query = count_query.where(Proxy.latency <= float(timeout_param) * 1000)

        # Sorting
        sort_map = {
            "latency": Proxy.latency.asc().nullslast(),
            "-latency": Proxy.latency.desc().nullslast(),
            "port": Proxy.port.asc(),
            "last_checked": Proxy.last_checked.desc().nullslast(),
        }
        order = sort_map.get(sort, Proxy.latency.asc().nullslast())
        query = query.order_by(order)

        total = await session.scalar(count_query) or 0
        offset = (page - 1) * limit
        query = query.offset(offset).limit(limit)

        result = await session.execute(query)
        proxies = result.scalars().all()

    # Build response
    data = {
        "success": True,
        "count": len(proxies),
        "page": page,
        "total": total,
        "data": [
            {
                "ip": p.ip,
                "port": p.port,
                "type": p.proxy_type,
                "country": p.country or None,
                "country_code": p.country_code or None,
                "city": None,
                "anonymity": p.anonymity_level,
                "latency": round(p.latency, 2) if p.latency else None,
                "ssl": p.ssl_support,
                "alive": p.is_alive,
                "last_checked": p.last_checked.isoformat() if p.last_checked else None,
            }
            for p in proxies
        ],
    }

    # Cache the result
    await set_cached(cache_key, data)
    etag = build_etag(data)
    response.headers["ETag"] = etag
    response.headers["X-Cache"] = "MISS"

    await _log_request(request, api_key, rate_info, 200, start_time, data)
    return _add_rate_headers(data, response, rate_info)


def _add_rate_headers(data: dict, response: Response, rate_info: dict) -> dict:
    """Add rate limit headers to response."""
    response.headers["X-RateLimit-Tier"] = rate_info.get("tier", "guest")
    if "daily_remaining" in rate_info:
        remaining = rate_info["daily_remaining"]
        response.headers["X-RateLimit-Remaining"] = str(remaining) if remaining >= 0 else "unlimited"
    if "hourly_remaining" in rate_info:
        response.headers["X-RateLimit-Hourly-Remaining"] = str(rate_info["hourly_remaining"])
    response.headers["Content-Encoding"] = "identity"
    return data


async def _log_request(
    request: Request, api_key: APIKey | None, rate_info: dict,
    status_code: int, start_time: float, data: dict,
):
    """Log the API request for analytics."""
    elapsed = round((time.monotonic() - start_time) * 1000, 2)
    response_bytes = len(json.dumps(data, default=str).encode())

    try:
        await api_usage.log_request(
            api_key_id=api_key.id if api_key else None,
            api_key_str=api_key.key if api_key else None,
            endpoint=request.url.path,
            method=request.method,
            status_code=status_code,
            response_time_ms=elapsed,
            response_bytes=response_bytes,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            query_params=str(request.query_params),
        )
        if api_key:
            await api_key_service.record_usage(
                api_key.id, request.client.host if request.client else None
            )
    except Exception as e:
        logger.warning(f"Failed to log API request: {e}")


# ─── Public Endpoints ─────────────────────────────────────────────────────────


@router.get("/proxies", summary="Get proxies with filters", tags=["Proxies"])
async def get_proxies(request: Request, response: Response):
    """
    Get a list of proxies with optional filtering.

    Filters: country, type, anonymity, alive, ssl, latency_lt, latency_gt, timeout, limit, page, sort
    """
    api_key, rate_info = await enforce_rate_limit(request)
    return await build_proxy_response(request, response, api_key, rate_info)


@router.get("/http", summary="Get HTTP proxies", tags=["Proxies"])
async def get_http_proxies(request: Request, response: Response):
    """Get all alive HTTP proxies."""
    api_key, rate_info = await enforce_rate_limit(request)
    return await build_proxy_response(request, response, api_key, rate_info, proxy_type="http")


@router.get("/https", summary="Get HTTPS proxies", tags=["Proxies"])
async def get_https_proxies(request: Request, response: Response):
    """Get all alive HTTPS proxies."""
    api_key, rate_info = await enforce_rate_limit(request)
    return await build_proxy_response(request, response, api_key, rate_info, proxy_type="https")


@router.get("/socks4", summary="Get SOCKS4 proxies", tags=["Proxies"])
async def get_socks4_proxies(request: Request, response: Response):
    """Get all alive SOCKS4 proxies."""
    api_key, rate_info = await enforce_rate_limit(request)
    return await build_proxy_response(request, response, api_key, rate_info, proxy_type="socks4")


@router.get("/socks5", summary="Get SOCKS5 proxies", tags=["Proxies"])
async def get_socks5_proxies(request: Request, response: Response):
    """Get all alive SOCKS5 proxies."""
    api_key, rate_info = await enforce_rate_limit(request)
    return await build_proxy_response(request, response, api_key, rate_info, proxy_type="socks5")


@router.get("/random", summary="Get a random proxy", tags=["Proxies"])
async def get_random_proxy(request: Request, response: Response):
    """Get a random alive proxy. Supports type and country filters."""
    api_key, rate_info = await enforce_rate_limit(request)
    start_time = time.monotonic()

    p_type = request.query_params.get("type")
    country = request.query_params.get("country")

    async with async_session() as session:
        query = select(Proxy).where(Proxy.is_alive == True)
        if p_type:
            query = query.where(Proxy.proxy_type == p_type.lower())
        if country:
            query = query.where(Proxy.country_code == country.upper())

        query = query.order_by(func.random()).limit(1)
        result = await session.execute(query)
        proxy = result.scalar_one_or_none()

    if not proxy:
        raise HTTPException(status_code=404, detail="No matching proxy found")

    data = {
        "success": True,
        "data": {
            "ip": proxy.ip,
            "port": proxy.port,
            "type": proxy.proxy_type,
            "country": proxy.country,
            "country_code": proxy.country_code,
            "city": None,
            "anonymity": proxy.anonymity_level,
            "latency": round(proxy.latency, 2) if proxy.latency else None,
            "ssl": proxy.ssl_support,
            "alive": proxy.is_alive,
            "last_checked": proxy.last_checked.isoformat() if proxy.last_checked else None,
        },
    }

    await _log_request(request, api_key, rate_info, 200, start_time, data)
    _add_rate_headers(data, response, rate_info)
    return data


@router.get("/stats", summary="Get proxy statistics", tags=["Stats"])
async def get_stats(request: Request, response: Response):
    """Get current proxy statistics."""
    api_key, rate_info = await enforce_rate_limit(request)
    start_time = time.monotonic()

    cache_key = "apicache:stats"
    cached = await get_cached(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        await _log_request(request, api_key, rate_info, 200, start_time, cached)
        return _add_rate_headers(cached, response, rate_info)

    async with async_session() as session:
        total = await session.scalar(select(func.count(Proxy.id))) or 0
        alive = await session.scalar(select(func.count(Proxy.id)).where(Proxy.is_alive == True)) or 0
        http_c = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "http", Proxy.is_alive == True)) or 0
        https_c = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "https", Proxy.is_alive == True)) or 0
        socks4_c = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks4", Proxy.is_alive == True)) or 0
        socks5_c = await session.scalar(select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks5", Proxy.is_alive == True)) or 0
        avg_lat = await session.scalar(select(func.avg(Proxy.latency)).where(Proxy.is_alive == True, Proxy.latency.isnot(None))) or 0.0

    data = {
        "success": True,
        "data": {
            "total_proxies": total,
            "alive_proxies": alive,
            "dead_proxies": total - alive,
            "http": http_c,
            "https": https_c,
            "socks4": socks4_c,
            "socks5": socks5_c,
            "average_latency_ms": round(avg_lat, 2),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        },
    }

    await set_cached(cache_key, data, ttl=15)
    response.headers["X-Cache"] = "MISS"
    await _log_request(request, api_key, rate_info, 200, start_time, data)
    return _add_rate_headers(data, response, rate_info)


@router.get("/countries", summary="Get available countries", tags=["Stats"])
async def get_countries(request: Request, response: Response):
    """Get list of countries with proxy counts."""
    api_key, rate_info = await enforce_rate_limit(request)
    start_time = time.monotonic()

    cache_key = "apicache:countries"
    cached = await get_cached(cache_key)
    if cached:
        response.headers["X-Cache"] = "HIT"
        await _log_request(request, api_key, rate_info, 200, start_time, cached)
        return _add_rate_headers(cached, response, rate_info)

    async with async_session() as session:
        result = await session.execute(
            select(
                Proxy.country_code,
                Proxy.country,
                func.count(Proxy.id).label("count"),
            )
            .where(Proxy.is_alive == True, Proxy.country_code.isnot(None))
            .group_by(Proxy.country_code, Proxy.country)
            .order_by(desc("count"))
        )
        rows = result.all()

    data = {
        "success": True,
        "count": len(rows),
        "data": [
            {"country_code": r.country_code, "country": r.country, "proxy_count": r.count}
            for r in rows
        ],
    }

    await set_cached(cache_key, data, ttl=60)
    response.headers["X-Cache"] = "MISS"
    await _log_request(request, api_key, rate_info, 200, start_time, data)
    return _add_rate_headers(data, response, rate_info)


@router.get("/sources", summary="Get proxy source count", tags=["Stats"])
async def get_sources_info(request: Request, response: Response):
    """Get information about proxy sources."""
    api_key, rate_info = await enforce_rate_limit(request)
    start_time = time.monotonic()

    from app.models.models import ProxySource
    async with async_session() as session:
        total = await session.scalar(select(func.count(ProxySource.id))) or 0
        enabled = await session.scalar(
            select(func.count(ProxySource.id)).where(ProxySource.enabled == True)
        ) or 0

    data = {
        "success": True,
        "data": {
            "total_sources": total,
            "active_sources": enabled,
        },
    }

    await _log_request(request, api_key, rate_info, 200, start_time, data)
    return _add_rate_headers(data, response, rate_info)


# ─── Download Endpoints ───────────────────────────────────────────────────────


@router.get("/download/{file_type}", summary="Download proxies", tags=["Download"])
async def download_proxies(
    file_type: str,
    request: Request,
    response: Response,
    format: str = Query("txt", pattern="^(txt|csv|json)$"),
):
    """
    Download alive proxies as a file.

    Types: http, https, socks4, socks5, all
    Formats: txt (ip:port), csv, json
    """
    api_key, rate_info = await enforce_rate_limit(request)
    start_time = time.monotonic()

    valid_types = ("http", "https", "socks4", "socks5", "all")
    if file_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid type. Use: {', '.join(valid_types)}")

    async with async_session() as session:
        query = select(Proxy).where(Proxy.is_alive == True)
        if file_type != "all":
            query = query.where(Proxy.proxy_type == file_type)

        # Apply filters from query params
        country = request.query_params.get("country")
        anonymity = request.query_params.get("anonymity")
        if country:
            query = query.where(Proxy.country_code == country.upper())
        if anonymity:
            query = query.where(Proxy.anonymity_level == anonymity.lower())

        query = query.order_by(Proxy.latency.asc().nullslast())
        result = await session.execute(query)
        proxies = result.scalars().all()

    if format == "json":
        content = json.dumps([
            {
                "ip": p.ip, "port": p.port, "type": p.proxy_type,
                "country": p.country_code, "anonymity": p.anonymity_level,
                "latency": round(p.latency, 2) if p.latency else None,
                "ssl": p.ssl_support,
            }
            for p in proxies
        ], indent=2)
        media_type = "application/json"
    elif format == "csv":
        lines = ["ip,port,type,country,anonymity,latency,ssl"]
        for p in proxies:
            lines.append(
                f"{p.ip},{p.port},{p.proxy_type},{p.country_code or ''},"
                f"{p.anonymity_level or ''},{p.latency or ''},{p.ssl_support}"
            )
        content = "\n".join(lines)
        media_type = "text/csv"
    else:
        content = "\n".join(f"{p.ip}:{p.port}" for p in proxies)
        media_type = "text/plain"

    # Log
    log_data = {"success": True, "count": len(proxies), "format": format}
    await _log_request(request, api_key, rate_info, 200, start_time, log_data)

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={file_type}_proxies.{format}",
            "X-Proxy-Count": str(len(proxies)),
            **{k: v for k, v in response.headers.items()},
        },
    )


# ─── API Key Management Endpoints ────────────────────────────────────────────


@router.post("/keys", summary="Create API key", tags=["API Keys"])
async def create_api_key(request: Request):
    """Create a new API key. Requires admin auth."""
    from app.core.security import get_current_admin
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")

    from app.core.security import verify_token
    token = auth_header.split(" ", 1)[1]
    payload = verify_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    body = await request.json()
    name = body.get("name", "Default")
    tier = body.get("tier", "free")
    user_id = body.get("user_id", payload.get("sub", "admin"))
    expires_days = body.get("expires_days")

    if tier not in TIER_LIMITS:
        raise HTTPException(status_code=400, detail=f"Invalid tier. Use: {', '.join(TIER_LIMITS.keys())}")

    api_key = await api_key_service.create_key(
        name=name, user_id=user_id, tier=tier, expires_days=expires_days
    )

    return {
        "success": True,
        "data": {
            "id": api_key.id,
            "key": api_key.key,
            "name": api_key.name,
            "tier": api_key.tier,
            "quota_daily": api_key.quota_daily,
            "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
            "created_at": api_key.created_at.isoformat() if api_key.created_at else None,
        },
    }


@router.get("/keys", summary="List API keys", tags=["API Keys"])
async def list_api_keys(request: Request):
    """List all API keys. Requires admin auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")

    from app.core.security import verify_token
    token = auth_header.split(" ", 1)[1]
    payload = verify_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    keys, total = await api_key_service.list_all_keys()
    return {
        "success": True,
        "total": total,
        "data": [
            {
                "id": k.id,
                "key": k.key[:12] + "...",
                "name": k.name,
                "tier": k.tier,
                "is_active": k.is_active,
                "requests_today": k.requests_today,
                "requests_total": k.requests_total,
                "bandwidth_bytes": k.bandwidth_bytes,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in keys
        ],
    }


@router.post("/keys/{key_id}/regenerate", summary="Regenerate API key", tags=["API Keys"])
async def regenerate_api_key(key_id: int, request: Request):
    """Regenerate an API key. Requires admin auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")

    from app.core.security import verify_token
    token = auth_header.split(" ", 1)[1]
    verify_token(token)

    api_key = await api_key_service.regenerate_key(key_id)
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    return {"success": True, "data": {"id": api_key.id, "key": api_key.key}}


@router.delete("/keys/{key_id}", summary="Delete API key", tags=["API Keys"])
async def delete_api_key(key_id: int, request: Request):
    """Delete an API key. Requires admin auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")

    from app.core.security import verify_token
    token = auth_header.split(" ", 1)[1]
    verify_token(token)

    deleted = await api_key_service.delete_key(key_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found")

    return {"success": True, "message": "API key deleted"}


# ─── API Dashboard Endpoints ──────────────────────────────────────────────────


@router.get("/dashboard", summary="API usage dashboard", tags=["Dashboard"])
async def api_dashboard(request: Request):
    """Get API usage dashboard stats. Requires admin auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")

    from app.core.security import verify_token
    token = auth_header.split(" ", 1)[1]
    verify_token(token)

    stats = await api_usage.get_dashboard_stats()
    return {"success": True, "data": stats}


@router.get("/dashboard/requests", summary="Recent API requests", tags=["Dashboard"])
async def api_recent_requests(request: Request, limit: int = Query(50, ge=1, le=500)):
    """Get recent API requests. Requires admin auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")

    from app.core.security import verify_token
    token = auth_header.split(" ", 1)[1]
    verify_token(token)

    requests_list = await api_usage.get_recent_requests(limit=limit)
    return {"success": True, "data": requests_list}


@router.get("/dashboard/usage", summary="API usage history", tags=["Dashboard"])
async def api_usage_history(request: Request, days: int = Query(30, ge=1, le=90)):
    """Get daily API usage history. Requires admin auth."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Admin token required")

    from app.core.security import verify_token
    token = auth_header.split(" ", 1)[1]
    verify_token(token)

    history = await api_usage.get_usage_history(days=days)
    return {"success": True, "data": history}


# ─── SDK Examples Endpoint ────────────────────────────────────────────────────


@router.get("/sdk/{language}", summary="Get SDK example", tags=["SDK"])
async def get_sdk_example(language: str):
    """Get SDK code example for a specific language."""
    from app.api.sdk_examples import EXAMPLES

    valid = list(EXAMPLES.keys())
    if language not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid language. Available: {', '.join(valid)}",
        )

    return {
        "success": True,
        "language": language,
        "code": EXAMPLES[language],
    }


@router.get("/sdk", summary="List SDK languages", tags=["SDK"])
async def list_sdk_languages():
    """List available SDK example languages."""
    from app.api.sdk_examples import EXAMPLES

    return {
        "success": True,
        "languages": list(EXAMPLES.keys()),
    }
