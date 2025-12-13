"""Query templates model for saved prompts."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class QueryTemplate(Base):
    """Query template model for saving reusable prompts."""
    
    __tablename__ = "query_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Template info
    name = Column(String(100), nullable=False)
    template_text = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    
    # Categorization
    category = Column(String(50), default="custom")  # summary, analysis, extraction, custom
    icon = Column(String(50), default="sparkles")
    
    # Flags
    is_default = Column(Boolean, default=False)  # System-provided templates
    is_favorite = Column(Boolean, default=False)
    use_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="query_templates")
    
    def __repr__(self):
        return f"<QueryTemplate(id={self.id}, name='{self.name}')>"


# Default templates to seed
DEFAULT_TEMPLATES = [
    {
        "name": "Summarize Document",
        "template_text": "Please provide a comprehensive summary of this document, highlighting the main points and key takeaways.",
        "category": "summary",
        "icon": "file-text",
        "is_default": True
    },
    {
        "name": "Extract Key Points",
        "template_text": "List the key points and main arguments presented in this document as bullet points.",
        "category": "extraction",
        "icon": "list",
        "is_default": True
    },
    {
        "name": "Find Action Items",
        "template_text": "Identify and list all action items, tasks, or recommendations mentioned in this document.",
        "category": "extraction",
        "icon": "check-square",
        "is_default": True
    },
    {
        "name": "Compare Information",
        "template_text": "Compare and contrast the different perspectives, arguments, or data points presented in these documents.",
        "category": "analysis",
        "icon": "git-compare",
        "is_default": True
    },
    {
        "name": "Explain Simply",
        "template_text": "Explain the main concepts in this document in simple terms that anyone can understand.",
        "category": "summary",
        "icon": "lightbulb",
        "is_default": True
    }
]
