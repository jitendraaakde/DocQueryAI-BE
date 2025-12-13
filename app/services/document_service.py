"""Document service for file handling and processing."""

import os
import hashlib
import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from pathlib import Path
import aiofiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, UploadFile, status
import logging

from app.models.document import Document, DocumentChunk, DocumentStatus
from app.schemas.document import DocumentCreate, DocumentUpdate, DocumentListResponse, DocumentResponse
from app.services.weaviate_service import weaviate_service
from app.services.storage_service import storage_service
from app.core.config import settings
from app.utils.text_extractor import extract_text_from_file
from app.utils.text_chunker import chunk_text

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document-related operations."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.upload_dir = Path(settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
    
    async def upload_document(
        self,
        file: UploadFile,
        user_id: int,
        metadata: Optional[DocumentCreate] = None
    ) -> Document:
        """Upload and process a document."""
        # Validate file
        await self._validate_file(file)
        
        # Generate unique filename
        file_ext = file.filename.split('.')[-1].lower()
        unique_filename = f"{uuid.uuid4()}.{file_ext}"
        storage_path = f"{user_id}/{unique_filename}"
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Calculate content hash
        content_hash = hashlib.sha256(content).hexdigest()
        
        # Check for duplicate
        existing = await self._check_duplicate(user_id, content_hash)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This document has already been uploaded"
            )
        
        # Determine content type
        content_type_map = {
            "pdf": "application/pdf",
            "txt": "text/plain",
            "md": "text/markdown",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
        content_type = content_type_map.get(file_ext, "application/octet-stream")
        
        # Upload to Supabase Storage
        file_url = await storage_service.upload_file(
            content=content,
            path=storage_path,
            content_type=content_type
        )
        logger.info(f"File uploaded to Supabase: {file_url}")
        
        # Create document record with Supabase URL
        document = Document(
            user_id=user_id,
            filename=unique_filename,
            original_filename=file.filename,
            file_path=file_url,  # Store Supabase public URL
            file_type=file_ext,
            file_size=file_size,
            content_hash=content_hash,
            title=metadata.title if metadata else None,
            description=metadata.description if metadata else None,
            status=DocumentStatus.PENDING,
            weaviate_collection=weaviate_service.COLLECTION_NAME
        )
        
        self.db.add(document)
        await self.db.flush()
        await self.db.refresh(document)
        
        logger.info(f"Document {document.id} uploaded successfully")
        
        # Process document asynchronously (in production, use background task)
        await self.process_document(document)
        
        # Refresh document to load all attributes after processing
        await self.db.refresh(document)
        
        return document
    
    async def process_document(self, document: Document):
        """Process a document: extract text, chunk, and vectorize."""
        try:
            # Update status
            document.status = DocumentStatus.PROCESSING
            await self.db.flush()
            
            # Extract text
            text = await extract_text_from_file(document.file_path, document.file_type)
            
            if not text or len(text.strip()) == 0:
                raise ValueError("No text could be extracted from the document")
            
            # Chunk text
            chunks = chunk_text(text)
            
            # Save chunks to PostgreSQL
            db_chunks = []
            for i, chunk_data in enumerate(chunks):
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=i,
                    content=chunk_data["content"],
                    start_page=chunk_data.get("page_number"),
                    end_page=chunk_data.get("page_number")
                )
                self.db.add(chunk)
                db_chunks.append(chunk)
            
            await self.db.flush()
            
            # Add to Weaviate
            weaviate_ids = await weaviate_service.add_chunks(
                chunks=chunks,
                document_id=document.id,
                user_id=document.user_id,
                document_name=document.original_filename
            )
            
            # Update chunk records with Weaviate IDs
            for i, chunk in enumerate(db_chunks):
                if i < len(weaviate_ids):
                    chunk.weaviate_id = weaviate_ids[i]
            
            # Update document status
            document.status = DocumentStatus.COMPLETED
            document.chunk_count = len(chunks)
            document.processed_at = datetime.utcnow()
            
            await self.db.flush()
            logger.info(f"Document {document.id} processed successfully with {len(chunks)} chunks")
            
        except Exception as e:
            logger.error(f"Failed to process document {document.id}: {e}")
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            await self.db.flush()
            raise
    
    async def get_document(self, document_id: int, user_id: int) -> Document:
        """Get a document by ID."""
        result = await self.db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id
            )
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        return document
    
    async def get_documents(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 10,
        status_filter: Optional[DocumentStatus] = None
    ) -> DocumentListResponse:
        """Get paginated list of documents for a user."""
        # Build query
        query = select(Document).where(Document.user_id == user_id)
        count_query = select(func.count(Document.id)).where(Document.user_id == user_id)
        
        if status_filter:
            query = query.where(Document.status == status_filter)
            count_query = count_query.where(Document.status == status_filter)
        
        # Get total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination
        offset = (page - 1) * page_size
        query = query.order_by(Document.created_at.desc()).offset(offset).limit(page_size)
        
        result = await self.db.execute(query)
        documents = result.scalars().all()
        
        total_pages = (total + page_size - 1) // page_size
        
        return DocumentListResponse(
            documents=[DocumentResponse.model_validate(doc) for doc in documents],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    async def delete_document(self, document_id: int, user_id: int):
        """Delete a document and its chunks."""
        document = await self.get_document(document_id, user_id)
        
        # Delete from Weaviate
        try:
            await weaviate_service.delete_document_chunks(document_id)
        except Exception as e:
            logger.warning(f"Failed to delete chunks from Weaviate: {e}")
        
        # Delete file from Supabase Storage
        try:
            if storage_service.is_supabase_url(document.file_path):
                await storage_service.delete_file(document.file_path)
            elif os.path.exists(document.file_path):
                # Fallback for legacy local files
                os.remove(document.file_path)
        except Exception as e:
            logger.warning(f"Failed to delete file: {e}")
        
        # Delete from database (cascade will delete chunks)
        await self.db.delete(document)
        await self.db.flush()
        
        logger.info(f"Document {document_id} deleted successfully")
    
    async def update_document(
        self,
        document_id: int,
        user_id: int,
        data: DocumentUpdate
    ) -> Document:
        """Update document metadata."""
        document = await self.get_document(document_id, user_id)
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(document, field, value)
        
        await self.db.flush()
        await self.db.refresh(document)
        
        return document
    
    async def _validate_file(self, file: UploadFile):
        """Validate uploaded file."""
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No filename provided"
            )
        
        file_ext = file.filename.split('.')[-1].lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed. Allowed types: {', '.join(settings.ALLOWED_EXTENSIONS)}"
            )
        
        # Check file size (read and reset)
        content = await file.read()
        await file.seek(0)
        
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE / (1024*1024):.1f}MB"
            )
    
    async def _check_duplicate(self, user_id: int, content_hash: str) -> Optional[Document]:
        """Check if a document with the same content already exists."""
        result = await self.db.execute(
            select(Document).where(
                Document.user_id == user_id,
                Document.content_hash == content_hash
            )
        )
        return result.scalar_one_or_none()
