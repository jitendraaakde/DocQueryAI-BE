"""Query database model."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, JSON, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Query(Base):
    """Query model for storing user queries and responses."""
    
    __tablename__ = "queries"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Query info
    query_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=True)
    
    # Search results
    sources = Column(JSON, nullable=True)  # List of source chunks used
    confidence_score = Column(Float, nullable=True)
    
    # Performance metrics
    search_time_ms = Column(Integer, nullable=True)
    generation_time_ms = Column(Integer, nullable=True)
    total_time_ms = Column(Integer, nullable=True)
    
    # Feedback
    rating = Column(Integer, nullable=True)  # 1-5 star rating
    feedback = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="queries")
    
    def __repr__(self):
        return f"<Query(id={self.id}, query='{self.query_text[:50]}...')>"
