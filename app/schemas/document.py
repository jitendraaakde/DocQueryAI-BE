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


class DocumentUpdate(BaseModel):
    """Schema for document update."""
    title: Optional[str] = None
    description: Optional[str] = None
