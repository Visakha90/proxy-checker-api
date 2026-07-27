import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_current_admin
from app.core.config import get_settings
from app.models.models import Proxy, ProxySource, CheckHistory, Statistics, AppSettings
from app.schemas.schemas import SettingsUpdate
from app.services.scraper import scraper_instance
from app.services.checker import checker_instance
from app.services.cleaner import cleaner_instance

router = APIRouter()
settings = get_settings()


@router.get("/dashboard")
async def admin_dashboard(
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get admin dashboard overview."""
    from sqlalchemy import func

    total_sources = await db.scalar(select(func.count(ProxySource.id))) or 0
    enabled_sources = await db.scalar(
        select(func.count(ProxySource.id)).where(ProxySource.enabled == True)
    ) or 0
    total_proxies = await db.scalar(select(func.count(Proxy.id))) or 0
    total_checks = await db.scalar(select(func.count(CheckHistory.id))) or 0

    return {
        "total_sources": total_sources,
        "enabled_sources": enabled_sources,
        "total_proxies": total_proxies,
        "total_checks": total_checks,
        "scraper_running": scraper_instance.running,
        "checker_running": checker_instance.running,
    }


@router.post("/scraper/start")
async def start_scraper(admin: dict = Depends(get_current_admin)):
    """Start the proxy scraper."""
    if scraper_instance.running:
        return {"message": "Scraper is already running"}

    asyncio.create_task(scraper_instance.start(settings.scrape_interval_seconds))
    return {"message": "Scraper started"}


@router.post("/scraper/stop")
async def stop_scraper(admin: dict = Depends(get_current_admin)):
    """Stop the proxy scraper."""
    scraper_instance.stop()
    return {"message": "Scraper stopped"}


@router.post("/checker/start")
async def start_checker(admin: dict = Depends(get_current_admin)):
    """Start the proxy checker."""
    if checker_instance.running:
        return {"message": "Checker is already running"}

    asyncio.create_task(checker_instance.start(settings.check_interval_seconds))
    return {"message": "Checker started"}


@router.post("/checker/stop")
async def stop_checker(admin: dict = Depends(get_current_admin)):
    """Stop the proxy checker."""
    checker_instance.stop()
    return {"message": "Checker stopped"}


@router.post("/recheck")
async def force_recheck(admin: dict = Depends(get_current_admin)):
    """Force recheck all proxies."""
    asyncio.create_task(checker_instance.run_check_cycle())
    return {"message": "Recheck cycle started"}


@router.post("/clean")
async def run_cleanup(admin: dict = Depends(get_current_admin)):
    """Run cleanup tasks."""
    result = await cleaner_instance.run_cleanup()
    return result


@router.delete("/database")
async def clear_database(
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Clear all proxy data (dangerous operation)."""
    await db.execute(delete(CheckHistory))
    await db.execute(delete(Proxy))
    await db.execute(delete(Statistics))
    return {"message": "Database cleared"}


@router.get("/settings")
async def get_app_settings(
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get current application settings."""
    return {
        "scrape_interval_seconds": settings.scrape_interval_seconds,
        "check_interval_seconds": settings.check_interval_seconds,
        "check_concurrency": settings.check_concurrency,
        "check_timeout": settings.check_timeout,
        "max_failures_before_delete": settings.max_failures_before_delete,
        "max_proxy_age_hours": settings.max_proxy_age_hours,
        "retry_count": settings.retry_count,
    }


@router.patch("/settings")
async def update_settings(
    update: SettingsUpdate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update application settings."""
    update_data = update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)
        # Persist to database
        existing = await db.scalar(
            select(AppSettings).where(AppSettings.key == key)
        )
        if existing:
            existing.value = str(value)
        else:
            db.add(AppSettings(key=key, value=str(value)))

    return {"message": "Settings updated", "settings": update_data}


@router.get("/logs")
async def get_logs(
    admin: dict = Depends(get_current_admin),
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Get recent check history logs."""
    from sqlalchemy import desc
    result = await db.execute(
        select(CheckHistory)
        .order_by(desc(CheckHistory.checked_at))
        .limit(limit)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "proxy_id": log.proxy_id,
            "is_alive": log.is_alive,
            "latency": log.latency,
            "status_code": log.status_code,
            "error": log.error,
            "checked_at": log.checked_at.isoformat() if log.checked_at else None,
        }
        for log in logs
    ]
