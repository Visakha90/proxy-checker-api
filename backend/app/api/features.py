"""
Feature API endpoints: rotation, chains, uptime, webhooks, exports,
geolocation enrichment, speed tiers, reputation, payments.
"""

import logging
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field

from app.api.users import get_current_user
from app.models.user_models import User
from app.services.geolocation import geo_service, speed_service, reputation_service
from app.services.rotation import rotation_service, chain_service, uptime_service
from app.services.notifications import webhook_service, export_service
from app.services.payments import payment_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Rotation ─────────────────────────────────────────────────────────────────


@router.get("/rotate")
async def rotate_proxy(request: Request):
    """Get the next proxy in round-robin rotation."""
    proxy_type = request.query_params.get("type")
    country = request.query_params.get("country")
    speed_tier = request.query_params.get("speed_tier")
    api_key = request.headers.get("X-API-Key")

    result = await rotation_service.get_next(
        user_id=api_key, proxy_type=proxy_type, country=country, speed_tier=speed_tier
    )
    if not result:
        raise HTTPException(status_code=404, detail="No matching proxy available")

    return {"success": True, "data": result}


# ─── Speed Tiers ──────────────────────────────────────────────────────────────


@router.get("/speed-tiers")
async def get_speed_tiers():
    """Get proxy counts by speed tier."""
    counts = await speed_service.get_tier_counts()
    return {"success": True, "data": counts}


# ─── Reputation ───────────────────────────────────────────────────────────────


@router.get("/reputation/top")
async def get_top_reputation(limit: int = 50):
    """Get top proxies by reputation score."""
    proxies = await reputation_service.get_top_proxies(limit=min(limit, 200))
    return {"success": True, "count": len(proxies), "data": proxies}


@router.get("/reputation/{proxy_id}")
async def get_proxy_reputation(proxy_id: int):
    """Get reputation score for a specific proxy."""
    score = await reputation_service.calculate_score(proxy_id)
    return {"success": True, "data": {"proxy_id": proxy_id, "reputation_score": score}}


# ─── Uptime ───────────────────────────────────────────────────────────────────


@router.get("/uptime/{proxy_id}")
async def get_proxy_uptime(proxy_id: int, days: int = 7):
    """Get uptime history for a proxy."""
    history = await uptime_service.get_uptime(proxy_id, days=min(days, 30))
    overall = await uptime_service.get_overall_uptime(proxy_id)
    return {"success": True, "data": {"overall_uptime_pct": overall, "history": history}}


# ─── Geolocation ──────────────────────────────────────────────────────────────


@router.post("/geo/enrich")
async def enrich_proxies(user: User = Depends(get_current_user)):
    """Trigger geolocation enrichment for proxies without location data."""
    if user.role not in ("admin", "premium"):
        raise HTTPException(status_code=403, detail="Premium feature")
    count = await geo_service.enrich_proxies(limit=200)
    return {"success": True, "enriched": count}


@router.get("/geo/lookup/{ip}")
async def lookup_ip(ip: str):
    """Look up geolocation for a single IP."""
    result = await geo_service.lookup_single(ip)
    if not result:
        raise HTTPException(status_code=404, detail="Could not resolve IP")
    return {"success": True, "data": result}


# ─── Proxy Chains ─────────────────────────────────────────────────────────────


@router.get("/chains")
async def list_chains(user: User = Depends(get_current_user)):
    """List user's proxy chains."""
    chains = await chain_service.list_chains(user.id)
    return {"success": True, "data": chains}


class ChainCreate(BaseModel):
    name: str = Field(..., max_length=255)
    proxy_ids: list[int] = Field(..., min_length=2, max_length=10)


@router.post("/chains")
async def create_chain(body: ChainCreate, user: User = Depends(get_current_user)):
    """Create a multi-hop proxy chain."""
    try:
        chain = await chain_service.create_chain(user.id, body.name, body.proxy_ids)
        return {"success": True, "data": {"id": chain.id, "name": chain.name}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/chains/{chain_id}/test")
async def test_chain(chain_id: int, user: User = Depends(get_current_user)):
    """Test a proxy chain."""
    result = await chain_service.test_chain(chain_id, user.id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return {"success": True, "data": result}


@router.delete("/chains/{chain_id}")
async def delete_chain(chain_id: int, user: User = Depends(get_current_user)):
    """Delete a proxy chain."""
    deleted = await chain_service.delete_chain(chain_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chain not found")
    return {"success": True}


# ─── Webhooks ─────────────────────────────────────────────────────────────────


class WebhookCreate(BaseModel):
    name: str = Field(..., max_length=255)
    url: str = Field(..., max_length=1024)
    event_type: str = Field(..., pattern="^(proxy_down|new_elite|count_drop|check_complete)$")


@router.get("/webhooks")
async def list_webhooks(user: User = Depends(get_current_user)):
    """List user's webhooks."""
    webhooks = await webhook_service.list_webhooks(user.id)
    return {
        "success": True,
        "data": [
            {"id": w.id, "name": w.name, "url": w.url, "event_type": w.event_type,
             "is_active": w.is_active, "trigger_count": w.trigger_count,
             "last_triggered_at": w.last_triggered_at.isoformat() if w.last_triggered_at else None}
            for w in webhooks
        ],
    }


@router.post("/webhooks")
async def create_webhook(body: WebhookCreate, user: User = Depends(get_current_user)):
    """Create a webhook notification."""
    wh = await webhook_service.create_webhook(user.id, body.name, body.url, body.event_type)
    return {"success": True, "data": {"id": wh.id, "secret": wh.secret}}


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: int, user: User = Depends(get_current_user)):
    """Delete a webhook."""
    deleted = await webhook_service.delete_webhook(webhook_id, user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"success": True}


# ─── Scheduled Exports ────────────────────────────────────────────────────────


class ExportCreate(BaseModel):
    name: str = Field(..., max_length=255)
    schedule: str = Field(..., pattern="^(hourly|daily|weekly)$")
    proxy_type: str | None = None
    format: str = Field(default="txt", pattern="^(txt|csv|json)$")
    delivery_method: str = Field(default="webhook", pattern="^(webhook|telegram)$")
    delivery_target: str = Field(..., max_length=512)


@router.get("/exports")
async def list_exports(user: User = Depends(get_current_user)):
    """List user's scheduled exports."""
    exports = await export_service.list_exports(user.id)
    return {
        "success": True,
        "data": [
            {"id": e.id, "name": e.name, "schedule": e.schedule, "format": e.format,
             "delivery_method": e.delivery_method, "is_active": e.is_active,
             "last_run_at": e.last_run_at.isoformat() if e.last_run_at else None}
            for e in exports
        ],
    }


@router.post("/exports")
async def create_export(body: ExportCreate, user: User = Depends(get_current_user)):
    """Create a scheduled export."""
    export = await export_service.create_export(
        user_id=user.id, name=body.name, schedule=body.schedule,
        proxy_type=body.proxy_type, format=body.format,
        delivery_method=body.delivery_method, delivery_target=body.delivery_target,
    )
    return {"success": True, "data": {"id": export.id, "name": export.name}}


# ─── Payments ─────────────────────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern="^(pro|enterprise)$")


@router.post("/billing/checkout")
async def create_checkout(body: CheckoutRequest, user: User = Depends(get_current_user)):
    """Create a Stripe checkout session for plan upgrade."""
    result = await payment_service.create_checkout_session(
        user_id=user.id,
        plan=body.plan,
        success_url="http://localhost:3000/dashboard?upgraded=true",
        cancel_url="http://localhost:3000/pricing",
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "data": result}


@router.post("/billing/portal")
async def billing_portal(user: User = Depends(get_current_user)):
    """Get Stripe billing portal URL."""
    result = await payment_service.create_portal_session(
        user_id=user.id, return_url="http://localhost:3000/dashboard"
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"success": True, "data": result}


@router.get("/billing/status")
async def billing_status(user: User = Depends(get_current_user)):
    """Get current subscription status."""
    result = await payment_service.get_subscription_status(user.id)
    return {"success": True, "data": result}


@router.post("/billing/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    result = await payment_service.handle_webhook(payload, sig)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ─── Multi-Region Checking ────────────────────────────────────────────────────


REGIONS = [
    {"id": "us-east", "name": "US East", "endpoint": "http://httpbin.org/ip"},
    {"id": "us-west", "name": "US West", "endpoint": "http://httpbin.org/ip"},
    {"id": "eu-west", "name": "EU West", "endpoint": "http://httpbin.org/ip"},
    {"id": "ap-south", "name": "Asia Pacific", "endpoint": "http://httpbin.org/ip"},
]


@router.get("/regions")
async def list_regions():
    """List available check regions."""
    return {"success": True, "data": REGIONS}


@router.post("/check/multi-region")
async def multi_region_check(request: Request, user: User = Depends(get_current_user)):
    """Check a proxy from multiple regions."""
    if user.plan not in ("pro", "enterprise") and user.role != "admin":
        raise HTTPException(status_code=403, detail="Multi-region checking requires Pro plan")

    body = await request.json()
    proxy_ip = body.get("ip")
    proxy_port = body.get("port")
    proxy_type = body.get("type", "http")

    if not proxy_ip or not proxy_port:
        raise HTTPException(status_code=400, detail="ip and port required")

    import httpx, time, asyncio
    results = []
    proxy_url = f"{proxy_type}://{proxy_ip}:{proxy_port}"

    for region in REGIONS:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(proxy=proxy_url, timeout=10, verify=False) as client:
                r = await client.get(region["endpoint"])
                elapsed = (time.monotonic() - start) * 1000
                results.append({
                    "region": region["id"],
                    "name": region["name"],
                    "status": "ok",
                    "latency_ms": round(elapsed, 2),
                    "status_code": r.status_code,
                })
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            results.append({
                "region": region["id"],
                "name": region["name"],
                "status": "failed",
                "latency_ms": round(elapsed, 2),
                "error": str(e)[:100],
            })

    return {"success": True, "proxy": f"{proxy_ip}:{proxy_port}", "data": results}
