"""
Internal Team Authentication & User Management API.

- Login (JWT)
- User CRUD (admin only): invite, disable, delete, reset password, change role
- Audit log queries
- No registration — users are created by admins only.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete, func

from app.core.database import async_session
from app.core.security import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, require_admin, Role,
)
from app.models.user_models import User
from app.services.audit import audit

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=6, max_length=128)
    role: str = Field(default="viewer", pattern="^(admin|manager|analyst|viewer)$")
    display_name: str | None = None


class UpdateUserRequest(BaseModel):
    role: str | None = Field(default=None, pattern="^(admin|manager|analyst|viewer)$")
    is_active: bool | None = None
    display_name: str | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=128)


# ─── Login ────────────────────────────────────────────────────────────────────

@router.post("/login")
async def login(req: LoginRequest, request: Request):
    """Authenticate and receive a JWT token. No anonymous access."""
    ip = request.client.host if request.client else None

    async with async_session() as session:
        user = await session.scalar(
            select(User).where(
                (User.username == req.username) | (User.email == req.username)
            )
        )

    if not user or not verify_password(req.password, user.password_hash):
        await audit.log("auth.login_failed", req.username, "Invalid credentials", ip, False)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        await audit.log("auth.login_disabled", req.username, "Account disabled", ip, False)
        raise HTTPException(status_code=403, detail="Account disabled. Contact admin.")

    # Update last login
    async with async_session() as session:
        await session.execute(
            update(User).where(User.id == user.id).values(last_login_at=datetime.now(timezone.utc))
        )
        await session.commit()

    token = create_access_token(data={
        "sub": user.username,
        "user_id": user.id,
        "role": user.role,
        "email": user.email,
    })

    await audit.log("auth.login", user.username, "Login successful", ip)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "display_name": user.display_name,
        },
    }


# ─── Current User ────────────────────────────────────────────────────────────

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Get current authenticated user profile."""
    async with async_session() as session:
        db_user = await session.scalar(
            select(User).where(User.username == user.get("sub"))
        )
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "role": db_user.role,
        "display_name": db_user.display_name,
        "is_active": db_user.is_active,
        "last_login_at": db_user.last_login_at.isoformat() if db_user.last_login_at else None,
        "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
    }


# ─── User Management (Admin Only) ────────────────────────────────────────────

@router.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    """List all team members."""
    async with async_session() as session:
        result = await session.execute(
            select(User).order_by(User.created_at.desc())
        )
        users = result.scalars().all()

    return {
        "total": len(users),
        "users": [
            {
                "id": u.id, "username": u.username, "email": u.email,
                "role": u.role, "display_name": u.display_name,
                "is_active": u.is_active,
                "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
    }


@router.post("/users")
async def create_user(req: CreateUserRequest, request: Request, admin: dict = Depends(require_admin)):
    """Create (invite) a new team member. Admin only."""
    ip = request.client.host if request.client else None

    async with async_session() as session:
        existing = await session.scalar(
            select(User).where((User.username == req.username) | (User.email == req.email))
        )
        if existing:
            raise HTTPException(status_code=409, detail="Username or email already exists")

        user = User(
            username=req.username,
            email=req.email,
            password_hash=get_password_hash(req.password),
            role=req.role,
            display_name=req.display_name or req.username,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    await audit.log("user.create", admin["sub"], f"Created user {req.username} (role={req.role})", ip)

    return {"id": user.id, "username": user.username, "role": user.role}


@router.patch("/users/{user_id}")
async def update_user(user_id: int, req: UpdateUserRequest, request: Request, admin: dict = Depends(require_admin)):
    """Update a team member's role or status. Admin only."""
    ip = request.client.host if request.client else None

    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        changes = []
        if req.role is not None and req.role != user.role:
            changes.append(f"role: {user.role} -> {req.role}")
            user.role = req.role
        if req.is_active is not None and req.is_active != user.is_active:
            changes.append(f"active: {user.is_active} -> {req.is_active}")
            user.is_active = req.is_active
        if req.display_name is not None:
            user.display_name = req.display_name

        await session.commit()

    if changes:
        await audit.log("user.update", admin["sub"], f"Updated {user.username}: {', '.join(changes)}", ip)

    return {"success": True, "changes": changes}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(user_id: int, req: ResetPasswordRequest, request: Request, admin: dict = Depends(require_admin)):
    """Reset a team member's password. Admin only."""
    ip = request.client.host if request.client else None

    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        user.password_hash = get_password_hash(req.new_password)
        await session.commit()

    await audit.log("user.reset_password", admin["sub"], f"Reset password for {user.username}", ip)
    return {"success": True}


@router.delete("/users/{user_id}")
async def delete_user(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    """Delete a team member. Admin only."""
    ip = request.client.host if request.client else None

    async with async_session() as session:
        user = await session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        if user.username == admin["sub"]:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        username = user.username
        await session.delete(user)
        await session.commit()

    await audit.log("user.delete", admin["sub"], f"Deleted user {username}", ip)
    return {"success": True}


# ─── Audit Logs ───────────────────────────────────────────────────────────────

@router.get("/audit")
async def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    user_filter: str | None = None,
    admin: dict = Depends(require_admin),
):
    """Query audit logs. Admin only."""
    logs, total = await audit.get_logs(limit=limit, offset=offset, action_filter=action, user_filter=user_filter)
    return {"total": total, "logs": logs}
