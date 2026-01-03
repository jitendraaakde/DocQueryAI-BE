"""User service for authentication and user management."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from typing import Optional

from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash, verify_password, create_access_token, create_refresh_token


class UserService:
    """Service for user-related operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        # Validate passwords match
        if user_data.password != user_data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Passwords do not match"
            )
        
        # Check if email already exists
        existing_user = await self.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Check if username already exists
        existing_username = await self.get_user_by_username(user_data.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
        
        # Create user
        hashed_password = get_password_hash(user_data.password)
        user = User(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            hashed_password=hashed_password
        )
        
        try:
            self.db.add(user)
            await self.db.flush()
            await self.db.refresh(user)
            return user
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User could not be created"
            )
    
    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        """Authenticate a user by email and password."""
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not user.hashed_password:
            return None  # User registered via OAuth only
        if not verify_password(password, user.hashed_password):
            return None
        return user
    
    async def check_user_auth_method(self, email: str) -> dict:
        """Check if a user exists and their authentication method.
        
        Returns a dict with:
        - exists: bool - whether the user exists
        - auth_provider: str - 'local', 'google', etc.
        - has_password: bool - whether the user has a password set
        - is_verified: bool - whether email is verified
        """
        user = await self.get_user_by_email(email)
        if not user:
            return {
                "exists": False,
                "auth_provider": None,
                "has_password": False,
                "is_verified": False
            }
        
        return {
            "exists": True,
            "auth_provider": user.auth_provider or "local",
            "has_password": bool(user.hashed_password),
            "is_verified": user.is_verified
        }
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        result = await self.db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Get a user by ID."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    
    async def update_user(self, user_id: int, user_data: UserUpdate) -> User:
        """Update user profile."""
        user = await self.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        update_data = user_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(user, field, value)
        
        await self.db.flush()
        await self.db.refresh(user)
        return user
    
    def create_tokens(self, user: User) -> dict:
        """Create access and refresh tokens for a user."""
        access_token = create_access_token(subject=user.id)
        refresh_token = create_refresh_token(subject=user.id)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer"
        }
    
    async def get_user_by_google_id(self, google_id: str) -> Optional[User]:
        """Get a user by Google ID."""
        result = await self.db.execute(
            select(User).where(User.google_id == google_id)
        )
        return result.scalar_one_or_none()
    
    async def create_or_get_google_user(
        self,
        google_id: str,
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> User:
        """Create a new user from Google OAuth or return existing user."""
        # Check if user exists by Google ID
        user = await self.get_user_by_google_id(google_id)
        if user:
            # Update avatar if provided
            if avatar_url and user.avatar_url != avatar_url:
                user.avatar_url = avatar_url
                await self.db.flush()
            return user
        
        # Check if email already exists
        existing_user = await self.get_user_by_email(email)
        if existing_user:
            # Link existing account with Google
            existing_user.google_id = google_id
            existing_user.auth_provider = "google"
            existing_user.is_verified = True
            if avatar_url:
                existing_user.avatar_url = avatar_url
            await self.db.flush()
            return existing_user
        
        # Create new user with Google auth
        # Generate unique username from email
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while await self.get_user_by_username(username):
            username = f"{base_username}{counter}"
            counter += 1
        
        user = User(
            email=email,
            username=username,
            full_name=full_name,
            google_id=google_id,
            auth_provider="google",
            is_verified=True,
            is_active=True,
            avatar_url=avatar_url
        )
        
        try:
            self.db.add(user)
            await self.db.flush()
            await self.db.refresh(user)
            return user
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User could not be created"
            )
