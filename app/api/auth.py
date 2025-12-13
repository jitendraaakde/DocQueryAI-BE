"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.core.config import settings
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/config")
async def get_auth_config():
    """Get authentication configuration (e.g., whether email verification is required)."""
    return {
        "email_verification_required": settings.EMAIL_VERIFICATION_REQUIRED
    }


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    user_service = UserService(db)
    user = await user_service.create_user(user_data)
    
    # Auto-verify user if email verification is disabled
    if not settings.EMAIL_VERIFICATION_REQUIRED:
        user.is_verified = True
        await db.flush()
    
    return user


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login and get access tokens."""
    user_service = UserService(db)
    user = await user_service.authenticate_user(
        email=credentials.email,
        password=credentials.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User account is inactive"
        )
    
    tokens = user_service.create_tokens(user)
    return tokens


@router.post("/refresh", response_model=Token)
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_db)
):
    """Refresh access token using refresh token."""
    try:
        payload = decode_token(refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        
        user_service = UserService(db)
        user = await user_service.get_user_by_id(int(user_id))
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        
        tokens = user_service.create_tokens(user)
        return tokens
        
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )


@router.post("/logout")
async def logout():
    """Logout user (client-side token invalidation)."""
    # In a production app, you might want to blacklist tokens
    return {"message": "Successfully logged out"}
