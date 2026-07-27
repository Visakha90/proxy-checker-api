"""
Internal Team Platform Security.

Role-Based Access Control (RBAC):
  - admin:   Full access. User management, system config, all operations.
  - manager: Can manage sources, trigger scrapes/checks, view all data, download.
  - analyst: Can view all data, download, run tests. Cannot modify system config.
  - viewer:  Read-only dashboard and proxy list. No downloads or tests.

All endpoints require JWT authentication. No anonymous access.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import async_session

settings = get_settings()
security = HTTPBearer(auto_error=True)


class Role(str, Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    ANALYST = "analyst"
    VIEWER = "viewer"


# Role hierarchy: higher index = more permissions
ROLE_HIERARCHY = {
    Role.VIEWER: 0,
    Role.ANALYST: 1,
    Role.MANAGER: 2,
    Role.ADMIN: 3,
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _has_role(user_role: str, required_role: Role) -> bool:
    """Check if user_role meets or exceeds required_role in hierarchy."""
    user_level = ROLE_HIERARCHY.get(Role(user_role), -1)
    required_level = ROLE_HIERARCHY.get(required_role, 99)
    return user_level >= required_level


# ─── FastAPI Dependencies ─────────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Extract and validate the current authenticated user from JWT.
    Returns the token payload: {sub, user_id, role, exp}
    ALL endpoints use this — no anonymous access.
    """
    payload = verify_token(credentials.credentials)
    if not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return payload


async def require_viewer(user: dict = Depends(get_current_user)) -> dict:
    """Minimum role: viewer (any authenticated user)."""
    return user


async def require_analyst(user: dict = Depends(get_current_user)) -> dict:
    """Minimum role: analyst."""
    if not _has_role(user.get("role", ""), Role.ANALYST):
        raise HTTPException(status_code=403, detail="Analyst role or higher required")
    return user


async def require_manager(user: dict = Depends(get_current_user)) -> dict:
    """Minimum role: manager."""
    if not _has_role(user.get("role", ""), Role.MANAGER):
        raise HTTPException(status_code=403, detail="Manager role or higher required")
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Minimum role: admin."""
    if not _has_role(user.get("role", ""), Role.ADMIN):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# Legacy alias for backward compatibility
get_current_admin = require_admin
