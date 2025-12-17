"""Document database models."""

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, BigInteger, Float, func, Enum
from sqlalchemy.orm import relationship
import enum
from app.core.database import Base


class DocumentStatus(str, enum.Enum):
    """Document processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Document(Base):
    """Document model for storing uploaded files metadata."""
    
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # File info
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_type = Column(String(50), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    
    # Content info
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)  # SHA-256 hash
    
    # Document insights
    word_count = Column(Integer, nullable=True)
    reading_time_minutes = Column(Integer, nullable=True)
    complexity_score = Column(Float, nullable=True)  # 0-100
    extracted_topics = Column(Text, nullable=True)  # JSON
    extracted_entities = Column(Text, nullable=True)  # JSON
    
    # AI-generated summary
    summary_brief = Column(Text, nullable=True)
    summary_detailed = Column(Text, nullable=True)
    key_points = Column(Text, nullable=True)  # JSON list
    action_items = Column(Text, nullable=True)  # JSON list of extracted action items
    
    # Processing status
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING)
    error_message = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)
    
    # Weaviate reference
    weaviate_collection = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    owner = relationship("User", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    collections = relationship("Collection", secondary="collection_documents", back_populates="documents")
    
    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}')>"


class DocumentChunk(Base):
    """Document chunk model for storing text chunks."""
    
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    
    # Chunk info
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    start_page = Column(Integer, nullable=True)
    end_page = Column(Integer, nullable=True)
    
    # Weaviate reference
    weaviate_id = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, index={self.chunk_index})>"
