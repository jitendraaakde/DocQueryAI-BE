"""User Settings database model."""

from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, func, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserSettings(Base):
    """User settings for LLM configuration and preferences."""
    
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    
    # LLM Provider Settings
    llm_provider = Column(String(50), default="groq")  # groq, openai, anthropic, gemini
    llm_model = Column(String(100), default="llama-3.3-70b-versatile")
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=4096)
    
    # API Keys (stored encrypted - users provide their own keys)
    openai_api_key = Column(Text, nullable=True)
    anthropic_api_key = Column(Text, nullable=True)
    gemini_api_key = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationship
    user = relationship("User", backref="settings")
    
    def __repr__(self):
        return f"<UserSettings(user_id={self.user_id}, provider='{self.llm_provider}')>"
