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
    DocumentUpdate,
    DocumentSummaryResponse,
    ActionItemsResponse,
    ActionItem
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


@router.get("/{document_id}/summary", response_model=DocumentSummaryResponse)
async def get_document_summary(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get AI-generated summary for a document."""
    import json
    
    document_service = DocumentService(db)
    document = await document_service.get_document(document_id, user_id)
    
    # Parse key_points from JSON string if present
    key_points = None
    if document.key_points:
        try:
            key_points = json.loads(document.key_points) if document.key_points.startswith('[') else eval(document.key_points)
        except:
            key_points = [document.key_points] if document.key_points else None
    
    return DocumentSummaryResponse(
        id=document.id,
        original_filename=document.original_filename,
        summary_brief=document.summary_brief,
        summary_detailed=document.summary_detailed,
        key_points=key_points,
        word_count=document.word_count,
        reading_time_minutes=document.reading_time_minutes,
        complexity_score=document.complexity_score
    )


@router.post("/{document_id}/summary/regenerate", response_model=DocumentSummaryResponse)
async def regenerate_document_summary(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Regenerate AI summary for a document."""
    import json
    from app.services.summarization_service import summarization_service
    
    document_service = DocumentService(db)
    document = await document_service.get_document(document_id, user_id)
    
    if document.status != DocumentStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be processed before generating summary"
        )
    
    # Regenerate summary
    success = await summarization_service.summarize_document(db, document_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate summary"
        )
    
    # Refresh document
    await db.refresh(document)
    
    # Parse key_points
    key_points = None
    if document.key_points:
        try:
            key_points = json.loads(document.key_points) if document.key_points.startswith('[') else eval(document.key_points)
        except:
            key_points = [document.key_points] if document.key_points else None
    
    return DocumentSummaryResponse(
        id=document.id,
        original_filename=document.original_filename,
        summary_brief=document.summary_brief,
        summary_detailed=document.summary_detailed,
        key_points=key_points,
        word_count=document.word_count,
        reading_time_minutes=document.reading_time_minutes,
        complexity_score=document.complexity_score
    )


@router.get("/{document_id}/action-items", response_model=ActionItemsResponse)
async def get_document_action_items(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get extracted action items for a document."""
    import json
    
    document_service = DocumentService(db)
    document = await document_service.get_document(document_id, user_id)
    
    # Parse action_items from JSON string if present
    items = []
    if document.action_items:
        try:
            raw_items = json.loads(document.action_items)
            items = [ActionItem(**item) for item in raw_items]
        except:
            pass
    
    return ActionItemsResponse(
        id=document.id,
        original_filename=document.original_filename,
        action_items=items,
        total_items=len(items)
    )


@router.post("/{document_id}/action-items/extract", response_model=ActionItemsResponse)
async def extract_document_action_items(
    document_id: int,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Extract action items from a document using AI."""
    import json
    from app.services.action_item_service import action_item_service
    
    document_service = DocumentService(db)
    document = await document_service.get_document(document_id, user_id)
    
    if document.status != DocumentStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be processed before extracting action items"
        )
    
    # Extract action items
    success = await action_item_service.extract_and_store_action_items(db, document_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extract action items"
        )
    
    # Refresh document
    await db.refresh(document)
    
    # Parse action_items
    items = []
    if document.action_items:
        try:
            raw_items = json.loads(document.action_items)
            items = [ActionItem(**item) for item in raw_items]
        except:
            pass
    
    return ActionItemsResponse(
        id=document.id,
        original_filename=document.original_filename,
        action_items=items,
        total_items=len(items)
    )
