"""
User registration, authentication, and profile management.
Supports multi-user with personal API keys.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, update

from app.core.database import async_session
from app.core.security import get_password_hash, verify_password, create_access_token, verify_token
from app.models.user_models import User
from app.services.api_keys import api_key_service

logger = logging.getLogger(__name__)
router = APIRouter()


class RegisterRequest(BaseModel):
    email: str = Field(..., max_length=255)
    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=6, max_length=128)
    display_name: str | None = None


class LoginRequest(BaseModel):
    login: str  # email or username
    password: str


class ProfileResponse(BaseModel):
    id: int
    email: str
    username: str
    display_name: str | None
    role: str
    plan: str
    is_verified: bool
    api_calls_today: int
    api_calls_total: int
    notification_enabled: bool
    telegram_chat_id: str | None
    created_at: str | None


async def get_current_user(request: Request) -> User:
    """Extract and validate user from JWT token."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_token(auth.split(" ", 1)[1])
    user_id = payload.get("user_id")
    if not user_id:
        # Legacy admin token
        if payload.get("role") == "admin":
            async with async_session() as session:
                user = await session.scalar(select(User).where(User.role == "admin").limit(1))
                if user:
                    return user
        raise HTTPException(status_code=401, detail="Invalid token")

    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Account disabled")
        return user


@router.post("/register")
async def register(req: RegisterRequest):
    """Register a new user account."""
    async with async_session() as session:
        # Check existing
        existing = await session.scalar(
            select(User).where((User.email == req.email) | (User.username == req.username))
        )
        if existing:
            raise HTTPException(status_code=409, detail="Email or username already taken")

        user = User(
            email=req.email,
            username=req.username,
            password_hash=get_password_hash(req.password),
            display_name=req.display_name or req.username,
            role="user",
            plan="free",
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Auto-create a free API key
        api_key = await api_key_service.create_key(
            name=f"{req.username}'s key",
            user_id=str(user.id),
            tier="free",
        )

        token = create_access_token(data={
            "sub": user.username, "user_id": user.id, "role": user.role
        })

        return {
            "success": True,
            "token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "plan": user.plan,
            },
            "api_key": api_key.key,
        }


@router.post("/login")
async def login(req: LoginRequest):
    """Login with email or username."""
    async with async_session() as session:
        user = await session.scalar(
            select(User).where((User.email == req.login) | (User.username == req.login))
        )
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Account disabled")

        # Update last login
        await session.execute(
            update(User).where(User.id == user.id).values(last_login_at=datetime.now(timezone.utc))
        )
        await session.commit()

        token = create_access_token(data={
            "sub": user.username, "user_id": user.id, "role": user.role
        })

        return {
            "success": True,
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "plan": user.plan,
            },
        }


@router.get("/me")
async def get_profile(user: User = Depends(get_current_user)):
    """Get current user profile."""
    return {
        "success": True,
        "data": {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "plan": user.plan,
            "is_verified": user.is_verified,
            "api_calls_today": user.api_calls_today,
            "api_calls_total": user.api_calls_total,
            "notification_enabled": user.notification_enabled,
            "telegram_chat_id": user.telegram_chat_id,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }


@router.get("/me/keys")
async def get_my_keys(user: User = Depends(get_current_user)):
    """Get current user's API keys."""
    keys = await api_key_service.get_keys_by_user(str(user.id))
    return {
        "success": True,
        "data": [
            {
                "id": k.id, "key": k.key, "name": k.name, "tier": k.tier,
                "is_active": k.is_active, "requests_today": k.requests_today,
                "requests_total": k.requests_total,
                "created_at": k.created_at.isoformat() if k.created_at else None,
            }
            for k in keys
        ],
    }


@router.post("/me/keys")
async def create_my_key(request: Request, user: User = Depends(get_current_user)):
    """Create a new API key for current user."""
    body = await request.json()
    name = body.get("name", f"{user.username}'s key")

    # Limit free users to 3 keys
    existing = await api_key_service.get_keys_by_user(str(user.id))
    max_keys = 3 if user.plan == "free" else 10 if user.plan == "pro" else 100
    if len(existing) >= max_keys:
        raise HTTPException(status_code=400, detail=f"Maximum {max_keys} keys for your plan")

    tier = "free" if user.plan == "free" else "premium"
    key = await api_key_service.create_key(name=name, user_id=str(user.id), tier=tier)

    return {"success": True, "data": {"id": key.id, "key": key.key, "name": key.name, "tier": key.tier}}


@router.patch("/me/notifications")
async def update_notifications(request: Request, user: User = Depends(get_current_user)):
    """Update notification settings."""
    body = await request.json()
    async with async_session() as session:
        values = {}
        if "telegram_chat_id" in body:
            values["telegram_chat_id"] = body["telegram_chat_id"]
        if "discord_webhook_url" in body:
            values["discord_webhook_url"] = body["discord_webhook_url"]
        if "notification_enabled" in body:
            values["notification_enabled"] = body["notification_enabled"]

        if values:
            await session.execute(update(User).where(User.id == user.id).values(**values))
            await session.commit()

    return {"success": True, "message": "Notifications updated"}
