"""Chat session and message database models."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, JSON, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class ChatSession(Base):
    """Chat session model for grouping conversations."""
    
    __tablename__ = "chat_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Session info
    title = Column(String(255), nullable=True)  # Auto-generated or user-defined
    description = Column(Text, nullable=True)
    
    # Document context (which documents this chat is about)
    document_ids = Column(JSON, default=list)  # List of document IDs
    collection_id = Column(Integer, ForeignKey("collections.id", ondelete="SET NULL"), nullable=True)
    
    # Session state
    is_active = Column(Boolean, default=True)
    is_pinned = Column(Boolean, default=False)
    
    # Message count for quick access
    message_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")
    collection = relationship("Collection", back_populates="chat_sessions")
    
    def __repr__(self):
        return f"<ChatSession(id={self.id}, title='{self.title}')>"


class ChatMessage(Base):
    """Chat message model for individual messages in a session."""
    
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    
    # Message content
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system'
    content = Column(Text, nullable=False)
    
    # Source citations (for assistant messages)
    sources = Column(JSON, nullable=True)  # List of {document_id, chunk_id, page, text}
    
    # Feedback
    feedback = Column(String(20), nullable=True)  # 'thumbs_up', 'thumbs_down', 'reported'
    feedback_text = Column(Text, nullable=True)
    
    # Performance metrics
    generation_time_ms = Column(Integer, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    
    # LLM info
    model_used = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")
    
    def __repr__(self):
        return f"<ChatMessage(id={self.id}, role='{self.role}')>"
