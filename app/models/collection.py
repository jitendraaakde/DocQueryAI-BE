"""Collection database models for organizing documents."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Table, func
from sqlalchemy.orm import relationship
from app.core.database import Base


# Many-to-many relationship between collections and documents
collection_documents = Table(
    'collection_documents',
    Base.metadata,
    Column('collection_id', Integer, ForeignKey('collections.id', ondelete='CASCADE'), primary_key=True),
    Column('document_id', Integer, ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True),
    Column('added_at', DateTime(timezone=True), server_default=func.now())
)


class Collection(Base):
    """Collection model for organizing documents into folders/projects."""
    
    __tablename__ = "collections"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Collection info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String(7), default="#6366f1")  # Hex color
    icon = Column(String(50), default="folder")  # Icon name
    
    # Visibility
    is_public = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="collections")
    documents = relationship("Document", secondary=collection_documents, back_populates="collections")
    chat_sessions = relationship("ChatSession", back_populates="collection")
    shares = relationship("CollectionShare", back_populates="collection", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Collection(id={self.id}, name='{self.name}')>"


class CollectionShare(Base):
    """Collection sharing model for team collaboration."""
    
    __tablename__ = "collection_shares"
    
    id = Column(Integer, primary_key=True, index=True)
    collection_id = Column(Integer, ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    shared_with_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Permission level
    permission = Column(String(20), default="view")  # 'view', 'edit', 'admin'
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    collection = relationship("Collection", back_populates="shares")
    shared_with_user = relationship("User", back_populates="shared_collections")
    
    def __repr__(self):
        return f"<CollectionShare(collection_id={self.collection_id}, user_id={self.shared_with_user_id})>"
