"""Query schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SourceChunk(BaseModel):
    """Schema for a source chunk in query response."""
    document_id: int
    document_name: str
    chunk_id: int
    content: str
    relevance_score: float
    page: Optional[int] = None


class QueryCreate(BaseModel):
    """Schema for creating a new query."""
    query_text: str = Field(..., min_length=1, max_length=2000)
    document_ids: Optional[List[int]] = None  # Filter to specific documents


class QueryResponse(BaseModel):
    """Schema for query response."""
    id: int
    query_text: str
    response_text: str
    sources: List[SourceChunk]
    confidence_score: Optional[float] = None
    search_time_ms: Optional[int] = None
    generation_time_ms: Optional[int] = None
    total_time_ms: Optional[int] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class QueryHistoryResponse(BaseModel):
    """Schema for query history list."""
    queries: List[QueryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class QueryFeedback(BaseModel):
    """Schema for query feedback."""
    rating: int = Field(..., ge=1, le=5)
    feedback: Optional[str] = None
