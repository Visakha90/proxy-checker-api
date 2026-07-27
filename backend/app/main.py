import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.api.routes import router as api_router
from app.api.admin import router as admin_router
from app.api.dns import router as dns_router
from app.api.v1 import router as v1_router
from app.api.monitoring import router as monitoring_router
from app.api.features import router as features_router
from app.api.admin_v2 import router as admin_v2_router
from app.api.platform import router as platform_router
from app.api.websocket import router as ws_router, broadcast_stats
from app.services.scraper import scraper_instance
from app.services.checker import checker_instance
from app.services.cleaner import cleaner_instance
from app.services.proxy_cache import proxy_cache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
settings = get_settings()

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start background tasks."""
    logger.info("Starting ProxyChecker API...")

    # Auto-create tables for SQLite (local dev)
    if "sqlite" in settings.database_url:
        from app.core.database import engine, Base
        from app.models.models import (
            Proxy, ProxySource, CheckHistory, Statistics, DownloadLog, AppSettings
        )
        from app.models.dns_models import DNSAuditLog, DNSRollbackSnapshot
        from app.models.api_models import APIKey, APIRequestLog, APIUsageDaily
        from app.models.user_models import User, Webhook, ScheduledExport, ProxyUptime, ProxyChain
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("SQLite tables created")

    # Start background services (skip checker concurrency on SQLite to avoid blocking)
    _is_sqlite = "sqlite" in settings.database_url

    scraper_task = None
    if not _is_sqlite:
        scraper_task = asyncio.create_task(
            scraper_instance.start(settings.scrape_interval_seconds)
        )
    else:
        # Run scraper once asynchronously with a delay to not block startup
        async def delayed_scrape():
            await asyncio.sleep(5)
            try:
                await scraper_instance.scrape_all()
            except Exception as e:
                logger.error(f"Initial scrape error: {e}")

        scraper_task = asyncio.create_task(delayed_scrape())

    broadcast_task = asyncio.create_task(broadcast_stats())

    # Start proxy cache auto-refresh (every 5 min)
    cache_task = asyncio.create_task(proxy_cache.start_auto_refresh(300))

    checker_task = None
    cleanup_task = None

    if not _is_sqlite:
        checker_task = asyncio.create_task(
            checker_instance.start(settings.check_interval_seconds)
        )

        async def cleanup_loop():
            while True:
                await asyncio.sleep(300)
                try:
                    await cleaner_instance.run_cleanup()
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")

        cleanup_task = asyncio.create_task(cleanup_loop())
    else:
        logger.info("SQLite mode: checker and cleanup disabled for stability")

    logger.info("All background services started")
    yield

    # Shutdown
    scraper_instance.stop()
    scraper_task.cancel()
    broadcast_task.cancel()
    cache_task.cancel()
    proxy_cache.stop()
    if checker_task:
        checker_instance.stop()
        checker_task.cancel()
    if cleanup_task:
        cleanup_task.cancel()
    logger.info("ProxyChecker API shut down")


app = FastAPI(
    title="ProxyChecker — Internal Platform",
    description="Internal team proxy operations dashboard. All endpoints require JWT authentication.",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "https://kaliptosal.dev"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes — Internal Team Platform (all require authentication)
# Auth is the only unauthenticated endpoint (login)
from app.api.internal_auth import router as internal_auth_router
app.include_router(internal_auth_router, prefix="/api/auth", tags=["Auth"])

# Core proxy operations (require at least viewer role)
app.include_router(api_router, prefix="/api", tags=["Proxies"])
app.include_router(v1_router, prefix="/api/v1", tags=["API v1"])
app.include_router(features_router, prefix="/api/v1", tags=["Features"])

# Admin operations
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(admin_v2_router, prefix="/api/admin/v2", tags=["Admin V2"])
app.include_router(dns_router, prefix="/api/dns", tags=["DNS"])
app.include_router(platform_router, prefix="/api/v1", tags=["Platform"])

# Monitoring (health is public for load balancers, rest require auth)
app.include_router(monitoring_router, tags=["Monitoring"])
app.include_router(ws_router, tags=["WebSocket"])


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ProxyChecker API"}
