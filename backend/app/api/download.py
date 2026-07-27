"""
Public Proxy Download API — Redis-Only Architecture.

This endpoint NEVER queries PostgreSQL directly.
All data comes from the pre-ranked Redis cache.
Designed for high concurrency and low latency.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response

from app.core.redis import redis_client
from app.services.proxy_cache import proxy_cache

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/download/stats")
async def download_stats():
    """
    Get download page statistics.
    Shows cache health, proxy counts, quality metrics, and download stats.
    """
    meta = await proxy_cache.get_cache_meta()

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    downloads_today = int(await redis_client.get(f"downloads:total:{today}") or 0)
    downloads_http = int(await redis_client.get(f"downloads:http:{today}") or 0)
    downloads_socks4 = int(await redis_client.get(f"downloads:socks4:{today}") or 0)
    downloads_socks5 = int(await redis_client.get(f"downloads:socks5:{today}") or 0)

    return {
        "success": True,
        "cache": meta,
        "downloads": {
            "today_total": downloads_today,
            "today_http": downloads_http,
            "today_socks4": downloads_socks4,
            "today_socks5": downloads_socks5,
        },
        "quality_note": "Only the top-ranked live proxies are served. Ranked by success rate, latency, uptime, and anonymity level.",
    }


@router.get("/download/{proxy_type}")
async def download_proxies(
    proxy_type: str,
    format: str = Query("txt", pattern="^(txt|csv|json)$"),
    limit: int = Query(500, ge=1, le=10000),
):
    """
    Download top-quality live proxies.

    Only serves the highest-ranked proxies from the Redis cache.
    Types: http, socks4, socks5, all
    Formats: txt (ip:port), csv, json
    """
    valid_types = ("http", "socks4", "socks5", "all")
    if proxy_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid type. Use: {', '.join(valid_types)}")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await redis_client.incr(f"downloads:{proxy_type}:{today}")
    await redis_client.expire(f"downloads:{proxy_type}:{today}", 172800)
    await redis_client.incr(f"downloads:total:{today}")
    await redis_client.expire(f"downloads:total:{today}", 172800)

    if format == "txt":
        content = await proxy_cache.get_proxies_text(proxy_type, limit=limit)
        media_type = "text/plain"
        ext = "txt"
    elif format == "csv":
        content = await proxy_cache.get_proxies_csv(proxy_type, limit=limit)
        media_type = "text/csv"
        ext = "csv"
    else:
        content = await proxy_cache.get_proxies_json(proxy_type, limit=limit)
        media_type = "application/json"
        ext = "json"

    if not content or content.strip() == "" or content.strip() == "[]":
        raise HTTPException(status_code=503, detail="Cache is warming up. Try again in a few minutes.")

    proxy_count = content.count("\n") + 1 if format == "txt" else len(content)

    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename={proxy_type}_proxies.{ext}",
            "X-Proxy-Count": str(proxy_count),
            "X-Cache-Source": "redis",
            "X-Quality": "top-ranked",
            "Cache-Control": "public, max-age=300",
        },
    )
