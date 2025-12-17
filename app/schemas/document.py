"""Document schemas for request/response validation."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.document import DocumentStatus


class DocumentCreate(BaseModel):
    """Schema for document creation (metadata)."""
    title: Optional[str] = None
    description: Optional[str] = None


class DocumentChunkResponse(BaseModel):
    """Schema for document chunk response."""
    id: int
    chunk_index: int
    content: str
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    
    class Config:
        from_attributes = True


class DocumentResponse(BaseModel):
    """Schema for document response."""
    id: int
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    title: Optional[str] = None
    description: Optional[str] = None
    status: DocumentStatus
    error_message: Optional[str] = None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime] = None
    # Summary fields
    summary_brief: Optional[str] = None
    word_count: Optional[int] = None
    reading_time_minutes: Optional[int] = None
    
    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Schema for paginated document list response."""
    documents: List[DocumentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DocumentDetailResponse(DocumentResponse):
    """Schema for detailed document response with chunks."""
    chunks: List[DocumentChunkResponse] = []
    
    class Config:
        from_attributes = True


class DocumentSummaryResponse(BaseModel):
    """Schema for document summary response."""
    id: int
    original_filename: str
    summary_brief: Optional[str] = None
    summary_detailed: Optional[str] = None
    key_points: Optional[List[str]] = None
    word_count: Optional[int] = None
    reading_time_minutes: Optional[int] = None
    complexity_score: Optional[float] = None
    
    class Config:
        from_attributes = True


class DocumentUpdate(BaseModel):
    """Schema for document update."""
    title: Optional[str] = None
    description: Optional[str] = None


class ActionItem(BaseModel):
    """Schema for a single action item."""
    task: str
    priority: str = "medium"  # high/medium/low
    deadline: Optional[str] = None
    category: str = "task"  # task/decision/commitment/follow-up


class ActionItemsResponse(BaseModel):
    """Schema for action items response."""
    id: int
    original_filename: str
    action_items: List[ActionItem] = []
    total_items: int = 0
