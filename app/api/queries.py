"""Query API routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas.query import QueryCreate, QueryResponse, QueryHistoryResponse, QueryFeedback
from app.services.query_service import QueryService

router = APIRouter(prefix="/queries", tags=["Queries"])


@router.post("/ask", response_model=QueryResponse)
async def ask_question(
    query_data: QueryCreate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """
    Ask a question about your documents.
    
    The system will:
    1. Search for relevant content in your documents using semantic search
    2. Generate an AI-powered answer based on the found context
    3. Return the answer with source citations
    """
    query_service = QueryService(db)
    
    try:
        result = await query_service.process_query(
            query_data=query_data,
            user_id=user_id
        )
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process query: {str(e)}"
        )


@router.get("/history", response_model=QueryHistoryResponse)
async def get_query_history(
    page: int = 1,
    page_size: int = 20,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get user's query history with pagination."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20
    
    query_service = QueryService(db)
    result = await query_service.get_query_history(
        user_id=user_id,
        page=page,
        page_size=page_size
    )
    
    return result


@router.get("/{query_id}", response_model=QueryResponse)
async def get_query(
    query_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific query by ID."""
    from sqlalchemy import select
    from app.models.query import Query
    from app.schemas.query import SourceChunk
    
    result = await db.execute(
        select(Query).where(
            Query.id == query_id,
            Query.user_id == user_id
        )
    )
    query = result.scalar_one_or_none()
    
    if not query:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Query not found"
        )
    
    return QueryResponse(
        id=query.id,
        query_text=query.query_text,
        response_text=query.response_text or "",
        sources=[SourceChunk(**s) for s in (query.sources or [])],
        confidence_score=query.confidence_score,
        search_time_ms=query.search_time_ms,
        generation_time_ms=query.generation_time_ms,
        total_time_ms=query.total_time_ms,
        created_at=query.created_at
    )


@router.post("/{query_id}/feedback")
async def submit_feedback(
    query_id: int,
    feedback_data: QueryFeedback,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Submit feedback for a query response."""
    query_service = QueryService(db)
    
    try:
        await query_service.rate_query(
            query_id=query_id,
            user_id=user_id,
            rating=feedback_data.rating,
            feedback=feedback_data.feedback
        )
        return {"message": "Feedback submitted successfully"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
