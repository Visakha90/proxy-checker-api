import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.models import Proxy, ProxySource, Statistics, DownloadLog, AppSettings
from app.schemas.schemas import (
    ProxyResponse,
    ProxyListResponse,
    StatsResponse,
    ProxyTestRequest,
    ProxyTestResult,
    ProxySourceCreate,
    ProxySourceResponse,
)
from app.services.scraper import scraper_instance
from app.services.checker import checker_instance
from app.services.tester import tester_instance
from app.services.cleaner import cleaner_instance

router = APIRouter()


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get current proxy statistics."""
    total = await db.scalar(select(func.count(Proxy.id))) or 0
    alive = await db.scalar(select(func.count(Proxy.id)).where(Proxy.is_alive == True)) or 0
    dead = total - alive

    http_count = await db.scalar(
        select(func.count(Proxy.id)).where(Proxy.proxy_type == "http", Proxy.is_alive == True)
    ) or 0
    https_count = await db.scalar(
        select(func.count(Proxy.id)).where(Proxy.proxy_type == "https", Proxy.is_alive == True)
    ) or 0
    socks4_count = await db.scalar(
        select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks4", Proxy.is_alive == True)
    ) or 0
    socks5_count = await db.scalar(
        select(func.count(Proxy.id)).where(Proxy.proxy_type == "socks5", Proxy.is_alive == True)
    ) or 0
    elite_count = await db.scalar(
        select(func.count(Proxy.id)).where(Proxy.anonymity_level == "elite", Proxy.is_alive == True)
    ) or 0
    anonymous_count = await db.scalar(
        select(func.count(Proxy.id)).where(Proxy.anonymity_level == "anonymous", Proxy.is_alive == True)
    ) or 0
    transparent_count = await db.scalar(
        select(func.count(Proxy.id)).where(Proxy.anonymity_level == "transparent", Proxy.is_alive == True)
    ) or 0
    avg_latency = await db.scalar(
        select(func.avg(Proxy.latency)).where(Proxy.is_alive == True, Proxy.latency.isnot(None))
    ) or 0.0

    newest = await db.scalar(select(func.max(Proxy.first_seen)))
    last_update = await db.scalar(select(func.max(Proxy.last_checked)))

    return StatsResponse(
        total_proxies=total,
        alive_proxies=alive,
        dead_proxies=dead,
        http_count=http_count,
        https_count=https_count,
        socks4_count=socks4_count,
        socks5_count=socks5_count,
        elite_count=elite_count,
        anonymous_count=anonymous_count,
        transparent_count=transparent_count,
        avg_latency=round(avg_latency, 2),
        newest_proxy=newest,
        last_update=last_update,
    )


@router.get("/proxies", response_model=ProxyListResponse)
async def get_proxies(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    proxy_type: str | None = Query(None, pattern="^(http|https|socks4|socks5)$"),
    is_alive: bool | None = None,
    country: str | None = None,
    anonymity: str | None = Query(None, pattern="^(elite|anonymous|transparent)$"),
    min_latency: float | None = None,
    max_latency: float | None = None,
    search: str | None = None,
    sort_by: str = Query("last_checked", pattern="^(latency|last_checked|first_seen|port)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated proxy list with filters."""
    query = select(Proxy)
    count_query = select(func.count(Proxy.id))

    # Apply filters
    if proxy_type:
        query = query.where(Proxy.proxy_type == proxy_type)
        count_query = count_query.where(Proxy.proxy_type == proxy_type)
    if is_alive is not None:
        query = query.where(Proxy.is_alive == is_alive)
        count_query = count_query.where(Proxy.is_alive == is_alive)
    if country:
        query = query.where(Proxy.country.ilike(f"%{country}%"))
        count_query = count_query.where(Proxy.country.ilike(f"%{country}%"))
    if anonymity:
        query = query.where(Proxy.anonymity_level == anonymity)
        count_query = count_query.where(Proxy.anonymity_level == anonymity)
    if min_latency is not None:
        query = query.where(Proxy.latency >= min_latency)
        count_query = count_query.where(Proxy.latency >= min_latency)
    if max_latency is not None:
        query = query.where(Proxy.latency <= max_latency)
        count_query = count_query.where(Proxy.latency <= max_latency)
    if search:
        query = query.where(
            Proxy.ip.ilike(f"%{search}%") | Proxy.country.ilike(f"%{search}%")
        )
        count_query = count_query.where(
            Proxy.ip.ilike(f"%{search}%") | Proxy.country.ilike(f"%{search}%")
        )

    # Sorting
    sort_column = getattr(Proxy, sort_by)
    if sort_order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(sort_column)

    # Pagination
    total = await db.scalar(count_query) or 0
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    proxies = result.scalars().all()

    return ProxyListResponse(
        proxies=[ProxyResponse.model_validate(p) for p in proxies],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/download/{file_type}")
async def download_proxies(
    file_type: str,
    request: Request,
    format: str = Query("txt", pattern="^(txt|csv|json)$"),
    db: AsyncSession = Depends(get_db),
):
    """Download live proxies as text file."""
    type_map = {
        "http": ("http",),
        "https": ("https",),
        "socks4": ("socks4",),
        "socks5": ("socks5",),
        "elite": None,
        "anonymous": None,
        "all": None,
    }

    if file_type not in type_map:
        raise HTTPException(status_code=400, detail="Invalid file type")

    query = select(Proxy).where(Proxy.is_alive == True)

    if file_type in ("http", "https", "socks4", "socks5"):
        query = query.where(Proxy.proxy_type == file_type)
    elif file_type == "elite":
        query = query.where(Proxy.anonymity_level == "elite")
    elif file_type == "anonymous":
        query = query.where(Proxy.anonymity_level == "anonymous")

    result = await db.execute(query)
    proxies = result.scalars().all()

    # Log download
    log = DownloadLog(
        file_type=file_type,
        ip_address=request.client.host if request.client else None,
    )
    db.add(log)

    if format == "json":
        import json
        content = json.dumps([
            {
                "ip": p.ip,
                "port": p.port,
                "type": p.proxy_type,
                "country": p.country,
                "anonymity": p.anonymity_level,
                "latency": p.latency,
            }
            for p in proxies
        ], indent=2)
        media_type = "application/json"
        filename = f"{file_type}.json"
    elif format == "csv":
        lines = ["ip,port,type,country,anonymity,latency"]
        for p in proxies:
            lines.append(f"{p.ip},{p.port},{p.proxy_type},{p.country or ''},{p.anonymity_level or ''},{p.latency or ''}")
        content = "\n".join(lines)
        media_type = "text/csv"
        filename = f"{file_type}.csv"
    else:
        content = "\n".join(f"{p.ip}:{p.port}" for p in proxies)
        media_type = "text/plain"
        filename = f"{file_type}.txt"

    from fastapi.responses import Response
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/scrape")
async def trigger_scrape(admin: dict = Depends(get_current_admin)):
    """Manually trigger a scrape cycle."""
    count = await scraper_instance.scrape_all()
    return {"message": f"Scraped {count} unique proxies"}


@router.post("/check")
async def trigger_check(admin: dict = Depends(get_current_admin)):
    """Manually trigger a check cycle."""
    asyncio.create_task(checker_instance.run_check_cycle())
    return {"message": "Check cycle started"}


@router.post("/test", response_model=list[ProxyTestResult])
async def test_proxies(request: ProxyTestRequest):
    """Test proxies against a target URL."""
    results = await tester_instance.test_proxies(
        target_url=request.target_url,
        method=request.method,
        timeout=request.timeout,
        proxy_type=request.proxy_type,
        limit=request.limit,
    )
    return [ProxyTestResult(**r) for r in results]


@router.get("/sources", response_model=list[ProxySourceResponse])
async def get_sources(
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get all proxy sources."""
    result = await db.execute(select(ProxySource).order_by(ProxySource.created_at.desc()))
    return result.scalars().all()


@router.post("/sources", response_model=ProxySourceResponse)
async def add_source(
    source: ProxySourceCreate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a new proxy source."""
    existing = await db.scalar(
        select(ProxySource).where(ProxySource.url == source.url)
    )
    if existing:
        raise HTTPException(status_code=409, detail="Source URL already exists")

    new_source = ProxySource(**source.model_dump())
    db.add(new_source)
    await db.flush()
    await db.refresh(new_source)
    return new_source


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: int,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a proxy source."""
    source = await db.get(ProxySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    await db.delete(source)
    return {"message": "Source deleted"}


@router.patch("/sources/{source_id}/toggle")
async def toggle_source(
    source_id: int,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enable/disable a proxy source."""
    source = await db.get(ProxySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    source.enabled = not source.enabled
    return {"enabled": source.enabled}


@router.post("/clean")
async def trigger_clean(admin: dict = Depends(get_current_admin)):
    """Manually trigger cleanup."""
    result = await cleaner_instance.run_cleanup()
    return result


@router.get("/history")
async def get_stats_history(
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Get statistics history for charts."""
    result = await db.execute(
        select(Statistics).order_by(desc(Statistics.recorded_at)).limit(limit)
    )
    stats = result.scalars().all()
    return [
        {
            "total_proxies": s.total_proxies,
            "alive_proxies": s.alive_proxies,
            "dead_proxies": s.dead_proxies,
            "http_count": s.http_count,
            "https_count": s.https_count,
            "socks4_count": s.socks4_count,
            "socks5_count": s.socks5_count,
            "avg_latency": s.avg_latency,
            "recorded_at": s.recorded_at.isoformat() if s.recorded_at else None,
        }
        for s in reversed(stats)
    ]
