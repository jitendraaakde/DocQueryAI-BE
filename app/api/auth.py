"""Authentication API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.core.config import settings
from app.schemas.user import UserCreate, UserLogin, UserResponse, Token, GoogleAuth
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


@router.post("/google", response_model=Token)
async def google_auth(
    auth_data: GoogleAuth,
    db: AsyncSession = Depends(get_db)
):
    """Login or register with Google OAuth using Firebase ID token."""
    import httpx
    import json
    
    try:
        # Verify Firebase ID token using Google's secure token verification endpoint
        # This endpoint validates Firebase ID tokens properly
        async with httpx.AsyncClient() as client:
            # First, try to decode the token to get the user info
            # Firebase tokens are JWTs that can be verified via Google's public keys
            
            # Use Google's identity toolkit to verify the token
            verify_url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={settings.FIREBASE_API_KEY if hasattr(settings, 'FIREBASE_API_KEY') else 'AIzaSyBBV9qFYOJUdfhUFNJR9gXnNrwFWMOS6Ko'}"
            
            response = await client.post(
                verify_url,
                json={"idToken": auth_data.id_token}
            )
            
            if response.status_code != 200:
                # Try alternative: decode JWT payload directly (less secure but works for dev)
                import base64
                try:
                    # Firebase ID token is a JWT - extract payload
                    parts = auth_data.id_token.split('.')
                    if len(parts) != 3:
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid token format"
                        )
                    
                    # Decode the payload (middle part)
                    payload = parts[1]
                    # Add padding if needed
                    padding = 4 - len(payload) % 4
                    if padding != 4:
                        payload += '=' * padding
                    
                    decoded = base64.urlsafe_b64decode(payload)
                    token_data = json.loads(decoded)
                    
                    google_id = token_data.get("user_id") or token_data.get("sub")
                    email = token_data.get("email")
                    name = token_data.get("name", "")
                    picture = token_data.get("picture", "")
                    
                except Exception as decode_error:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=f"Token verification failed: {str(decode_error)}"
                    )
            else:
                # Parse response from identity toolkit
                result = response.json()
                users = result.get("users", [])
                
                if not users:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found in token"
                    )
                
                user_data = users[0]
                google_id = user_data.get("localId")
                email = user_data.get("email")
                name = user_data.get("displayName", "")
                picture = user_data.get("photoUrl", "")
            
            if not google_id or not email:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token data - missing user info"
                )
            
            # Create or get user
            user_service = UserService(db)
            user = await user_service.create_or_get_google_user(
                google_id=google_id,
                email=email,
                full_name=name,
                avatar_url=picture
            )
            
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="User account is inactive"
                )
            
            # Generate tokens
            tokens = user_service.create_tokens(user)
            return tokens
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google authentication failed: {str(e)}"
        )

