"""Collection Pydantic schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# Collection schemas
class CollectionBase(BaseModel):
    """Base collection schema."""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    color: str = "#6366f1"
    icon: str = "folder"


class CollectionCreate(CollectionBase):
    """Schema for creating a new collection."""
    document_ids: Optional[List[int]] = []


class CollectionUpdate(BaseModel):
    """Schema for updating a collection."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    is_public: Optional[bool] = None


class CollectionResponse(CollectionBase):
    """Schema for collection response."""
    id: int
    user_id: int
    is_public: bool
    document_count: int = 0
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CollectionWithDocuments(CollectionResponse):
    """Collection with document IDs included."""
    document_ids: List[int] = []


class CollectionList(BaseModel):
    """List of collections."""
    collections: List[CollectionResponse]
    total: int


# Collection sharing schemas
class CollectionShareCreate(BaseModel):
    """Schema for sharing a collection."""
    user_email: str  # Email of user to share with
    permission: str = Field("view", pattern="^(view|edit|admin)$")


class CollectionShareResponse(BaseModel):
    """Schema for share response."""
    id: int
    collection_id: int
    shared_with_user_id: int
    shared_with_email: str
    shared_with_username: str
    permission: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class CollectionShareUpdate(BaseModel):
    """Schema for updating share permission."""
    permission: str = Field(..., pattern="^(view|edit|admin)$")


# Add/remove documents
class CollectionDocumentsUpdate(BaseModel):
    """Schema for adding/removing documents from collection."""
    document_ids: List[int]
    action: str = Field(..., pattern="^(add|remove)$")
