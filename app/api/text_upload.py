"""Text Upload API routes - Paste text directly."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import hashlib
from datetime import datetime
import logging

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas.document import DocumentResponse
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.services.milvus_service import milvus_service
from app.utils.text_chunker import chunk_text

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)


class TextUploadRequest(BaseModel):
    """Request body for text upload."""
    content: str
    title: Optional[str] = None
    description: Optional[str] = None


@router.post("/from-text", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_from_text(
    request: TextUploadRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create a document from pasted text content."""
    
    # Validate content
    content = request.content.strip()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content cannot be empty"
        )
    
    if len(content) > 500000:  # ~500KB text limit
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content too large. Maximum size is 500KB."
        )
    
    # Calculate content hash
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    
    # Generate title if not provided
    title = request.title or f"Pasted Text - {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}"
    
    try:
        # Create document record (no file storage needed for text)
        document = Document(
            user_id=user_id,
            filename=f"text_{content_hash[:8]}.txt",
            original_filename=title,
            file_path="",  # No file storage for pasted text
            file_type="txt",
            file_size=len(content.encode('utf-8')),
            content_hash=content_hash,
            title=title,
            description=request.description,
            status=DocumentStatus.PROCESSING,
            weaviate_collection=milvus_service.COLLECTION_NAME
        )
        
        db.add(document)
        await db.flush()
        await db.refresh(document)
        
        logger.info(f"Created text document {document.id} for user {user_id}")
        
        # Chunk text
        chunks = chunk_text(content)
        
        if not chunks:
            raise ValueError("No content chunks could be created")
        
        # Save chunks to PostgreSQL
        db_chunks = []
        for i, chunk_data in enumerate(chunks):
            chunk = DocumentChunk(
                document_id=document.id,
                chunk_index=i,
                content=chunk_data["content"],
                start_page=None,
                end_page=None
            )
            db.add(chunk)
            db_chunks.append(chunk)
        
        await db.flush()
        
        # Add to Milvus
        milvus_ids = await milvus_service.add_chunks(
            chunks=chunks,
            document_id=document.id,
            user_id=user_id,
            document_name=title
        )
        
        # Update chunk records with Milvus IDs
        for i, chunk in enumerate(db_chunks):
            if i < len(milvus_ids):
                chunk.weaviate_id = milvus_ids[i]
        
        # Update document status
        document.status = DocumentStatus.COMPLETED
        document.chunk_count = len(chunks)
        document.processed_at = datetime.utcnow()
        
        await db.flush()
        await db.refresh(document)
        
        logger.info(f"Text document {document.id} processed successfully with {len(chunks)} chunks")
        
        return document
        
    except Exception as e:
        logger.error(f"Failed to process text upload: {e}")
        if 'document' in locals():
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process text: {str(e)}"
        )
