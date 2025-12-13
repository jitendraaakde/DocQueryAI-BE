"""Analytics API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.analytics_service import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/stats")
async def get_user_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get user usage statistics."""
    return await analytics_service.get_user_stats(db, current_user.id, days)


@router.get("/timeline")
async def get_activity_timeline(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get daily activity timeline."""
    return await analytics_service.get_activity_timeline(db, current_user.id, days)


@router.get("/top-documents")
async def get_top_documents(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """Get most used documents."""
    return await analytics_service.get_top_documents(db, current_user.id, limit)


@router.get("/rate-limit")
async def get_rate_limit_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current rate limit status."""
    return await analytics_service.check_rate_limit(db, current_user.id)
