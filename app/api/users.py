"""User API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas.user import UserResponse, UserUpdate, PasswordChange
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get current user profile."""
    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    update_data: UserUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Update current user profile."""
    user_service = UserService(db)
    user = await user_service.update_user(user_id, update_data)
    return user


@router.put("/me/password")
async def change_password(
    password_data: PasswordChange,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Change current user password."""
    from app.core.security import verify_password, get_password_hash
    
    user_service = UserService(db)
    user = await user_service.get_user_by_id(user_id)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Verify current password
    if not verify_password(password_data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password"
        )
    
    # Validate new password
    if password_data.new_password != password_data.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New passwords do not match"
        )
    
    # Update password
    user.hashed_password = get_password_hash(password_data.new_password)
    await db.flush()
    
    return {"message": "Password updated successfully"}


@router.get("/me/stats")
async def get_user_stats(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get current user statistics."""
    from sqlalchemy import select, func
    from app.models.document import Document
    from app.models.query import Query
    
    # Get document count
    doc_result = await db.execute(
        select(func.count(Document.id)).where(Document.user_id == user_id)
    )
    doc_count = doc_result.scalar()
    
    # Get query count
    query_result = await db.execute(
        select(func.count(Query.id)).where(Query.user_id == user_id)
    )
    query_count = query_result.scalar()
    
    return {
        "document_count": doc_count,
        "query_count": query_count
    }
