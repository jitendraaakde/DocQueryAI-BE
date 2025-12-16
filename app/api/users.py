"""User API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
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


@router.post("/me/avatar", response_model=UserResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Upload user avatar image to Supabase S3."""
    import boto3
    from botocore.config import Config
    import uuid
    from app.core.config import settings
    
    # Validate file type
    allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file type. Only JPEG, PNG, GIF, and WebP are allowed."
        )
    
    # Validate file size (max 5MB)
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 5MB."
        )
    
    try:
        # Initialize S3 client for Supabase
        s3_client = boto3.client(
            's3',
            endpoint_url=settings.SUPABASE_S3_ENDPOINT,
            aws_access_key_id=settings.SUPABASE_S3_ACCESS_KEY,
            aws_secret_access_key=settings.SUPABASE_S3_SECRET_KEY,
            region_name=settings.SUPABASE_S3_REGION,
            config=Config(signature_version='s3v4')
        )
        
        # Generate unique filename
        file_extension = file.filename.split('.')[-1] if '.' in file.filename else 'jpg'
        unique_filename = f"avatars/{user_id}/{uuid.uuid4()}.{file_extension}"
        
        # Upload to Supabase S3
        s3_client.put_object(
            Bucket=settings.SUPABASE_BUCKET,
            Key=unique_filename,
            Body=content,
            ContentType=file.content_type
        )
        
        # Generate public URL
        # Supabase uses a specific URL format for public files
        base_url = settings.SUPABASE_S3_ENDPOINT.replace('/storage/v1/s3', '')
        avatar_url = f"{base_url}/storage/v1/object/public/{settings.SUPABASE_BUCKET}/{unique_filename}"
        
        # Update user avatar_url in database
        user_service = UserService(db)
        user = await user_service.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        user.avatar_url = avatar_url
        await db.flush()
        await db.refresh(user)
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload avatar: {str(e)}"
        )
