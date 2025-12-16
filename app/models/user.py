"""User database model."""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    """User model for authentication and document ownership."""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=True)  # Nullable for OAuth users
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    avatar_url = Column(String(500), nullable=True)
    
    # OAuth fields
    auth_provider = Column(String(50), default="local")  # local, google, github
    google_id = Column(String(255), nullable=True, unique=True, index=True)
    
    # User preferences
    preferred_llm = Column(String(50), default="groq")  # groq, gemini, openai, anthropic
    theme = Column(String(20), default="dark")  # dark, light
    
    # 2FA fields
    totp_secret = Column(String(32), nullable=True)
    totp_enabled = Column(Boolean, default=False)
    backup_codes = Column(Text, nullable=True)  # JSON list
    
    # Rate limiting
    daily_query_limit = Column(Integer, default=100)
    queries_today = Column(Integer, default=0)
    last_query_reset = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    queries = relationship("Query", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    collections = relationship("Collection", back_populates="user", cascade="all, delete-orphan")
    shared_collections = relationship("CollectionShare", back_populates="shared_with_user", cascade="all, delete-orphan")
    query_templates = relationship("QueryTemplate", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"

