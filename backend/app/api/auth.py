from fastapi import APIRouter, HTTPException, status
from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.schemas.schemas import LoginRequest, TokenResponse

router = APIRouter()
settings = get_settings()

# Store hashed password at startup
_admin_password_hash = get_password_hash(settings.admin_password)


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Admin login endpoint."""
    if request.username != settings.admin_username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not verify_password(request.password, _admin_password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    token = create_access_token(
        data={"sub": request.username, "role": "admin"}
    )
    return TokenResponse(access_token=token)
