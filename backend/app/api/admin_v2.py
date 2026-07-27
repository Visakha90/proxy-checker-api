"""
Enhanced Admin API v2.

Provides:
- Full system overview
- User management (list, ban, unban, change plan)
- Bulk operations (purge dead, reset stats, purge logs)
- IP banning
- Announcements
- Maintenance mode
- Telegram admin controls
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel, Field

from app.core.security import get_current_admin
from app.services.admin_enhanced import enhanced_admin
from app.services.telegram_admin import admin_bot

router = APIRouter()


# ─── System ───────────────────────────────────────────────────────────────────

@router.get("/system")
async def system_overview(admin: dict = Depends(get_current_admin)):
    """Full system overview with all metrics."""
    data = await enhanced_admin.get_system_overview()
    return {"success": True, "data": data}


# ─── User Management ──────────────────────────────────────────────────────────

@router.get("/users")
async def list_users(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(get_current_admin),
):
    """List all registered users."""
    users, total = await enhanced_admin.list_users(limit=limit, offset=offset)
    return {"success": True, "total": total, "data": users}


class BanRequest(BaseModel):
    reason: str = ""


@router.post("/users/{user_id}/ban")
async def ban_user(user_id: int, body: BanRequest, admin: dict = Depends(get_current_admin)):
    """Ban a user (deactivate account + keys)."""
    ok = await enhanced_admin.ban_user(user_id, body.reason)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "message": "User banned"}


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: int, admin: dict = Depends(get_current_admin)):
    """Unban a user."""
    ok = await enhanced_admin.unban_user(user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "message": "User unbanned"}


class PlanChange(BaseModel):
    plan: str = Field(..., pattern="^(free|pro|enterprise)$")


@router.post("/users/{user_id}/plan")
async def change_plan(user_id: int, body: PlanChange, admin: dict = Depends(get_current_admin)):
    """Admin override: change user plan."""
    ok = await enhanced_admin.change_user_plan(user_id, body.plan)
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
    return {"success": True, "message": f"Plan changed to {body.plan}"}


# ─── Bulk Operations ──────────────────────────────────────────────────────────

@router.post("/bulk/purge-dead")
async def purge_dead(admin: dict = Depends(get_current_admin)):
    """Delete all dead proxies."""
    count = await enhanced_admin.purge_dead_proxies()
    return {"success": True, "deleted": count}


@router.post("/bulk/reset-stats")
async def reset_stats(admin: dict = Depends(get_current_admin)):
    """Reset all statistics and check history."""
    await enhanced_admin.reset_all_stats()
    return {"success": True, "message": "Stats reset"}


@router.post("/bulk/purge-logs")
async def purge_logs(days: int = Query(7, ge=1, le=90), admin: dict = Depends(get_current_admin)):
    """Delete old API request logs."""
    count = await enhanced_admin.purge_old_logs(days=days)
    return {"success": True, "deleted": count}


# ─── IP Banning ───────────────────────────────────────────────────────────────

class IPBanRequest(BaseModel):
    ip: str
    reason: str = ""
    duration_hours: int = Field(default=24, ge=1, le=8760)


@router.post("/ip-ban")
async def ban_ip(body: IPBanRequest, admin: dict = Depends(get_current_admin)):
    """Ban an IP address."""
    await enhanced_admin.ban_ip(body.ip, body.reason, body.duration_hours)
    return {"success": True, "message": f"IP {body.ip} banned for {body.duration_hours}h"}


@router.delete("/ip-ban/{ip}")
async def unban_ip(ip: str, admin: dict = Depends(get_current_admin)):
    """Unban an IP address."""
    await enhanced_admin.unban_ip(ip)
    return {"success": True, "message": f"IP {ip} unbanned"}


@router.get("/ip-bans")
async def list_bans(admin: dict = Depends(get_current_admin)):
    """List all banned IPs."""
    bans = await enhanced_admin.list_banned_ips()
    return {"success": True, "data": bans}


# ─── Announcements ────────────────────────────────────────────────────────────

class AnnouncementRequest(BaseModel):
    message: str = Field(..., max_length=500)
    type: str = Field(default="info", pattern="^(info|warning|error|success)$")


@router.post("/announcement")
async def set_announcement(body: AnnouncementRequest, admin: dict = Depends(get_current_admin)):
    """Set a system-wide announcement."""
    await enhanced_admin.set_announcement(body.message, body.type)
    return {"success": True}


@router.delete("/announcement")
async def clear_announcement(admin: dict = Depends(get_current_admin)):
    """Clear the announcement."""
    await enhanced_admin.clear_announcement()
    return {"success": True}


@router.get("/announcement")
async def get_announcement():
    """Get current announcement (public)."""
    data = await enhanced_admin.get_announcement()
    return {"success": True, "data": data}


# ─── Maintenance ──────────────────────────────────────────────────────────────

class MaintenanceRequest(BaseModel):
    message: str = Field(default="System maintenance in progress", max_length=500)


@router.post("/maintenance/enable")
async def enable_maintenance(body: MaintenanceRequest, admin: dict = Depends(get_current_admin)):
    """Enable maintenance mode."""
    await enhanced_admin.enable_maintenance(body.message)
    return {"success": True, "message": "Maintenance mode enabled"}


@router.post("/maintenance/disable")
async def disable_maintenance(admin: dict = Depends(get_current_admin)):
    """Disable maintenance mode."""
    await enhanced_admin.disable_maintenance()
    return {"success": True, "message": "Maintenance mode disabled"}


@router.get("/maintenance")
async def maintenance_status():
    """Check maintenance mode status (public)."""
    active, msg = await enhanced_admin.is_maintenance()
    return {"success": True, "maintenance": active, "message": msg if active else None}


# ─── Telegram ─────────────────────────────────────────────────────────────────

class TelegramMessage(BaseModel):
    message: str = Field(..., max_length=1000)


@router.post("/telegram/send")
async def send_telegram(body: TelegramMessage, admin: dict = Depends(get_current_admin)):
    """Send a custom message to admin Telegram."""
    ok = await admin_bot.send(body.message)
    return {"success": ok, "message": "Sent" if ok else "Failed (check bot token and chat ID)"}


@router.post("/telegram/test")
async def test_telegram(admin: dict = Depends(get_current_admin)):
    """Test Telegram connection."""
    ok = await admin_bot.send("🔔 <b>Test notification</b>\nAdmin panel connection working!")
    return {"success": ok, "configured": admin_bot.enabled}


@router.post("/telegram/daily-report")
async def send_daily_report(admin: dict = Depends(get_current_admin)):
    """Manually trigger the daily stats report."""
    await enhanced_admin.send_daily_report()
    return {"success": True, "message": "Daily report sent"}
