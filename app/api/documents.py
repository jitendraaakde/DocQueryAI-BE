"""Document API routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.document import DocumentStatus
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
    DocumentListResponse,
    DocumentDetailResponse,
    DocumentUpdate
)
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Upload a new document."""
    metadata = DocumentCreate(title=title, description=description)
    
    document_service = DocumentService(db)
    document = await document_service.upload_document(
        file=file,
        user_id=user_id,
        metadata=metadata
    )
    
    return document


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    page: int = 1,
    page_size: int = 10,
    status_filter: Optional[DocumentStatus] = None,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """List user's documents with pagination."""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 10
    
    document_service = DocumentService(db)
    result = await document_service.get_documents(
        user_id=user_id,
        page=page,
        page_size=page_size,
        status_filter=status_filter
    )
    
    return result


@router.get("/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific document with its chunks."""
    document_service = DocumentService(db)
    document = await document_service.get_document(document_id, user_id)
    
    # Load chunks
    from sqlalchemy import select
    from app.models.document import DocumentChunk
    
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = result.scalars().all()
    
    return DocumentDetailResponse(
        id=document.id,
        filename=document.filename,
        original_filename=document.original_filename,
        file_type=document.file_type,
        file_size=document.file_size,
        title=document.title,
        description=document.description,
        status=document.status,
        error_message=document.error_message,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
        updated_at=document.updated_at,
        processed_at=document.processed_at,
        chunks=chunks
    )


@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: int,
    update_data: DocumentUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Update document metadata."""
    document_service = DocumentService(db)
    document = await document_service.update_document(
        document_id=document_id,
        user_id=user_id,
        data=update_data
    )
    
    return document


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Delete a document and its chunks."""
    document_service = DocumentService(db)
    await document_service.delete_document(document_id, user_id)


@router.post("/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Reprocess a failed document."""
    document_service = DocumentService(db)
    document = await document_service.get_document(document_id, user_id)
    
    if document.status not in [DocumentStatus.FAILED, DocumentStatus.PENDING]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only failed or pending documents can be reprocessed"
        )
    
    # Reset status and reprocess
    document.status = DocumentStatus.PENDING
    document.error_message = None
    await db.flush()
    
    await document_service.process_document(document)
    
    await db.refresh(document)
    return document


@router.get("/{document_id}/download")
async def download_document(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Download a document file for viewing."""
    from fastapi.responses import Response
    from app.services.storage_service import storage_service
    
    document_service = DocumentService(db)
    document = await document_service.get_document(document_id, user_id)
    
    # Download file content
    try:
        content = await storage_service.download_file(document.file_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found: {str(e)}"
        )
    
    # Determine content type
    content_types = {
        "pdf": "application/pdf",
        "txt": "text/plain",
        "md": "text/markdown",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
    content_type = content_types.get(document.file_type, "application/octet-stream")
    
    # Return file with Content-Disposition for inline viewing
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Content-Disposition": f"inline; filename=\"{document.original_filename}\"",
            "Access-Control-Expose-Headers": "Content-Disposition"
        }
    )
