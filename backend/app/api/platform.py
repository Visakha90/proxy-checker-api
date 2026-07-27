"""
Platform API: Leaderboard, Map, Comparison, CAPTCHA, Pools, White-label,
Status, Blog, Discord, User Sources, Alerts, Gateway, Fingerprint.
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from pydantic import BaseModel, Field

from app.api.users import get_current_user
from app.core.security import get_current_admin
from app.models.user_models import User
from app.services.gateway import gateway, fingerprint_service, load_balancer
from app.services.platform import (
    leaderboard_service, map_service, comparison_service, captcha_service,
    pool_service, whitelabel_service, status_service, blog_service,
    discord_bot, user_source_service, alert_service,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Gateway ──────────────────────────────────────────────────────────────────

class GatewayRequest(BaseModel):
    url: str = Field(..., max_length=2048)
    method: str = Field(default="GET", pattern="^(GET|POST|PUT|DELETE|HEAD)$")
    headers: dict | None = None
    body: str | None = None
    proxy_type: str | None = None
    country: str | None = None
    speed_tier: str | None = None
    sticky_session: str | None = None


@router.post("/gateway")
async def proxy_gateway(req: GatewayRequest, user: User = Depends(get_current_user)):
    """Forward a request through the auto-rotating proxy gateway."""
    if user.plan == "free" and user.role != "admin":
        raise HTTPException(status_code=403, detail="Gateway requires Pro plan or higher")
    result = await gateway.forward_request(
        target_url=req.url, method=req.method, headers=req.headers,
        body=req.body.encode() if req.body else None,
        proxy_type=req.proxy_type, country=req.country,
        speed_tier=req.speed_tier, sticky_session=req.sticky_session,
    )
    return {"success": result["success"], "data": result}


# ─── Fingerprint ──────────────────────────────────────────────────────────────

class FingerprintRequest(BaseModel):
    ip: str
    port: int
    type: str = "http"


@router.post("/fingerprint")
async def check_fingerprint(req: FingerprintRequest, user: User = Depends(get_current_user)):
    """Check if a proxy IP is blacklisted on major websites."""
    result = await fingerprint_service.check_fingerprint(req.ip, req.port, req.type)
    return {"success": True, "data": result}


# ─── Load Balancer ────────────────────────────────────────────────────────────

@router.get("/best-for/{domain}")
async def best_proxies_for_domain(domain: str, count: int = Query(5, ge=1, le=20)):
    """Get the best proxies for a specific target domain."""
    proxies = await load_balancer.get_best_for_target(domain, count=count)
    return {"success": True, "domain": domain, "data": proxies}


# ─── Leaderboard ──────────────────────────────────────────────────────────────

@router.get("/leaderboard/fastest")
async def leaderboard_fastest(limit: int = Query(50, ge=1, le=200)):
    """Get fastest proxies leaderboard."""
    data = await leaderboard_service.get_fastest(limit)
    return {"success": True, "count": len(data), "data": data}


@router.get("/leaderboard/reliable")
async def leaderboard_reliable(limit: int = Query(50, ge=1, le=200)):
    """Get most reliable proxies leaderboard."""
    data = await leaderboard_service.get_most_reliable(limit)
    return {"success": True, "count": len(data), "data": data}


# ─── Map ──────────────────────────────────────────────────────────────────────

@router.get("/map")
async def map_data():
    """Get proxy location data for globe visualization."""
    data = await map_service.get_proxy_locations()
    return {"success": True, "data": data}


# ─── Comparison ───────────────────────────────────────────────────────────────

@router.get("/compare/types")
async def compare_types():
    """Compare proxy types (HTTP vs SOCKS etc)."""
    data = await comparison_service.compare_types()
    return {"success": True, "data": data}


@router.get("/compare/countries")
async def compare_countries(limit: int = Query(20, ge=1, le=50)):
    """Compare proxy availability by country."""
    data = await comparison_service.compare_countries(limit)
    return {"success": True, "data": data}


# ─── CAPTCHA ──────────────────────────────────────────────────────────────────

class CaptchaRequest(BaseModel):
    site_key: str
    page_url: str


@router.post("/captcha/solve")
async def solve_captcha(req: CaptchaRequest, user: User = Depends(get_current_user)):
    """Solve a reCAPTCHA using 2Captcha integration."""
    if user.plan == "free" and user.role != "admin":
        raise HTTPException(status_code=403, detail="CAPTCHA solving requires Pro plan")
    result = await captcha_service.solve_recaptcha(req.site_key, req.page_url)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "data": result}


# ─── Dedicated Pools ──────────────────────────────────────────────────────────

class PoolCreate(BaseModel):
    name: str = Field(..., max_length=255)
    proxy_type: str | None = None
    country: str | None = None
    size: int = Field(default=100, ge=10, le=5000)


@router.post("/pools")
async def create_pool(body: PoolCreate, user: User = Depends(get_current_user)):
    """Create a dedicated proxy pool."""
    if user.plan not in ("pro", "enterprise") and user.role != "admin":
        raise HTTPException(status_code=403, detail="Dedicated pools require Pro plan")
    result = await pool_service.create_pool(user.id, body.name, body.proxy_type, body.country, body.size)
    return {"success": True, "data": result}


@router.get("/pools/{pool_id}")
async def get_pool_proxies(pool_id: str, user: User = Depends(get_current_user)):
    """Get proxies from a dedicated pool."""
    proxies = await pool_service.get_pool_proxies(pool_id)
    if not proxies:
        raise HTTPException(status_code=404, detail="Pool not found or empty")
    return {"success": True, "count": len(proxies), "data": proxies}


# ─── White-Label ──────────────────────────────────────────────────────────────

class WhiteLabelCreate(BaseModel):
    domain: str = Field(..., max_length=255)
    brand_name: str = Field(..., max_length=100)


@router.post("/whitelabel")
async def create_whitelabel(body: WhiteLabelCreate, user: User = Depends(get_current_user)):
    """Create a white-label API configuration."""
    if user.plan != "enterprise" and user.role != "admin":
        raise HTTPException(status_code=403, detail="White-label requires Enterprise plan")
    result = await whitelabel_service.create_whitelabel(user.id, body.domain, body.brand_name)
    return {"success": True, "data": result}


# ─── Status Page ──────────────────────────────────────────────────────────────

@router.get("/status")
async def service_status():
    """Public service status page."""
    data = await status_service.get_status()
    return {"success": True, "data": data}


# ─── Blog/SEO ─────────────────────────────────────────────────────────────────

@router.get("/blog/posts")
async def blog_posts():
    """Get auto-generated SEO blog post list."""
    posts = await blog_service.generate_posts()
    return {"success": True, "data": posts}


# ─── Discord ──────────────────────────────────────────────────────────────────

class DiscordCommand(BaseModel):
    command: str
    args: list[str] = []
    webhook_url: str = ""


@router.post("/discord/command")
async def discord_command(body: DiscordCommand):
    """Handle a Discord bot command."""
    result = await discord_bot.handle_command(body.command, body.args, body.webhook_url)
    return {"success": True, "response": result}


# ─── User Sources ─────────────────────────────────────────────────────────────

class SourceSubmission(BaseModel):
    url: str = Field(..., max_length=1024)
    proxy_type: str = Field(default="http", pattern="^(http|https|socks4|socks5)$")
    description: str = Field(default="", max_length=500)


@router.post("/sources/submit")
async def submit_source(body: SourceSubmission, user: User = Depends(get_current_user)):
    """Submit a proxy source for review."""
    result = await user_source_service.submit_source(user.id, body.url, body.proxy_type, body.description)
    return {"success": True, "data": result}


@router.get("/sources/pending")
async def pending_sources(admin: dict = Depends(get_current_admin)):
    """List pending source submissions (admin only)."""
    data = await user_source_service.list_pending()
    return {"success": True, "data": data}


@router.post("/sources/approve/{sub_id}")
async def approve_source(sub_id: str, admin: dict = Depends(get_current_admin)):
    """Approve a submitted source (admin only)."""
    ok = await user_source_service.approve_source(sub_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Submission not found")
    return {"success": True, "message": "Source approved and added"}
