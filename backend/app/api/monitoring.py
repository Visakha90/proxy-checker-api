"""
Monitoring and metrics endpoints.

Provides:
- /health - Health check
- /metrics - Prometheus-compatible metrics
- /ready - Readiness probe
"""

import time
import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import select, func, text

from app.core.database import async_session, engine
from app.core.redis import redis_client
from app.models.models import Proxy
from app.models.api_models import APIKey, APIRequestLog

logger = logging.getLogger(__name__)
router = APIRouter()

_start_time = time.time()


@router.get("/health", tags=["Monitoring"])
async def health_check():
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "service": "ProxyChecker API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.time() - _start_time, 2),
    }


@router.get("/ready", tags=["Monitoring"])
async def readiness_check():
    """Readiness probe - checks database and Redis connectivity."""
    checks = {"database": False, "redis": False}

    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")

    try:
        await redis_client.ping()
        checks["redis"] = True
    except Exception as e:
        logger.warning(f"Redis health check failed: {e}")

    all_healthy = all(checks.values())
    return {
        "status": "ready" if all_healthy else "degraded",
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics", tags=["Monitoring"])
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    from fastapi.responses import PlainTextResponse

    async with async_session() as session:
        total_proxies = await session.scalar(select(func.count(Proxy.id))) or 0
        alive_proxies = await session.scalar(
            select(func.count(Proxy.id)).where(Proxy.is_alive == True)
        ) or 0
        total_api_keys = await session.scalar(select(func.count(APIKey.id))) or 0
        total_requests = await session.scalar(
            select(func.count(APIRequestLog.id))
        ) or 0

    uptime = round(time.time() - _start_time, 2)

    metrics = f"""# HELP proxychecker_uptime_seconds Service uptime in seconds
# TYPE proxychecker_uptime_seconds gauge
proxychecker_uptime_seconds {uptime}

# HELP proxychecker_proxies_total Total number of proxies in database
# TYPE proxychecker_proxies_total gauge
proxychecker_proxies_total {total_proxies}

# HELP proxychecker_proxies_alive Number of alive proxies
# TYPE proxychecker_proxies_alive gauge
proxychecker_proxies_alive {alive_proxies}

# HELP proxychecker_proxies_dead Number of dead proxies
# TYPE proxychecker_proxies_dead gauge
proxychecker_proxies_dead {total_proxies - alive_proxies}

# HELP proxychecker_api_keys_total Total API keys
# TYPE proxychecker_api_keys_total gauge
proxychecker_api_keys_total {total_api_keys}

# HELP proxychecker_api_requests_total Total API requests served
# TYPE proxychecker_api_requests_total counter
proxychecker_api_requests_total {total_requests}
"""

    return PlainTextResponse(content=metrics, media_type="text/plain; charset=utf-8")
