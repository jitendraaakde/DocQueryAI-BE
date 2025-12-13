"""Chat session and message Pydantic schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# Chat Message schemas
class ChatMessageBase(BaseModel):
    """Base chat message schema."""
    content: str = Field(..., min_length=1)
    

class ChatMessageCreate(ChatMessageBase):
    """Schema for creating a new message."""
    role: str = "user"  # 'user' or 'system'
    

class ChatMessageResponse(ChatMessageBase):
    """Schema for message response."""
    id: int
    session_id: int
    role: str
    sources: Optional[List[dict]] = None
    feedback: Optional[str] = None
    feedback_text: Optional[str] = None
    generation_time_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    model_used: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class MessageFeedback(BaseModel):
    """Schema for submitting message feedback."""
    feedback: str = Field(..., pattern="^(thumbs_up|thumbs_down|reported)$")
    feedback_text: Optional[str] = None


# Chat Session schemas
class ChatSessionBase(BaseModel):
    """Base chat session schema."""
    title: Optional[str] = None
    description: Optional[str] = None
    

class ChatSessionCreate(ChatSessionBase):
    """Schema for creating a new chat session."""
    document_ids: Optional[List[int]] = []
    collection_id: Optional[int] = None
    

class ChatSessionUpdate(BaseModel):
    """Schema for updating a chat session."""
    title: Optional[str] = None
    description: Optional[str] = None
    is_pinned: Optional[bool] = None
    document_ids: Optional[List[int]] = None
    collection_id: Optional[int] = None


class ChatSessionResponse(ChatSessionBase):
    """Schema for session response."""
    id: int
    user_id: int
    document_ids: List[int] = []
    collection_id: Optional[int] = None
    is_active: bool
    is_pinned: bool
    message_count: int
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class ChatSessionWithMessages(ChatSessionResponse):
    """Session with all messages included."""
    messages: List[ChatMessageResponse] = []


class ChatSessionList(BaseModel):
    """List of chat sessions with pagination."""
    sessions: List[ChatSessionResponse]
    total: int
    page: int
    per_page: int


# Query in session
class SessionQueryRequest(BaseModel):
    """Request to make a query within a session."""
    message: str = Field(..., min_length=1)
    document_ids: Optional[List[int]] = None  # Override session docs
    stream: bool = False  # Enable streaming response


class SessionQueryResponse(BaseModel):
    """Response for session query."""
    message: ChatMessageResponse
    session: ChatSessionResponse


# Export schemas
class ChatExportRequest(BaseModel):
    """Request to export chat history."""
    format: str = Field(..., pattern="^(pdf|markdown|json)$")
    include_sources: bool = True


class ChatExportResponse(BaseModel):
    """Response with export download URL."""
    download_url: str
    filename: str
    format: str
    expires_at: datetime
