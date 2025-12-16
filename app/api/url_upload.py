"""URL Upload API routes."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import tempfile
import os
from urllib.parse import urlparse

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas.document import DocumentResponse, DocumentCreate
from app.services.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["Documents"])


class UrlUploadRequest(BaseModel):
    """Request body for URL upload."""
    url: str
    title: Optional[str] = None
    description: Optional[str] = None


@router.post("/from-url", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_from_url(
    request: UrlUploadRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Download a document from URL and upload it."""
    
    # Validate URL
    try:
        parsed_url = urlparse(request.url)
        if not parsed_url.scheme in ['http', 'https']:
            raise ValueError("Invalid URL scheme")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL format"
        )
    
    # Get filename from URL
    path = parsed_url.path
    filename = os.path.basename(path) or "document"
    
    # Validate file extension
    allowed_extensions = ['pdf', 'txt', 'md', 'doc', 'docx']
    extension = filename.split('.')[-1].lower() if '.' in filename else ''
    
    if extension not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Download file from URL
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            response = await client.get(request.url)
            response.raise_for_status()
            
            # Check content length (max 50MB)
            content_length = len(response.content)
            if content_length > 50 * 1024 * 1024:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="File too large. Maximum size is 50MB."
                )
            
            # Get content type
            content_type = response.headers.get('content-type', '').lower()
            
            # Validate content type matches extension
            valid_types = {
                'pdf': ['application/pdf'],
                'txt': ['text/plain'],
                'md': ['text/markdown', 'text/plain'],
                'doc': ['application/msword'],
                'docx': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document']
            }
            
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{extension}') as tmp_file:
                tmp_file.write(response.content)
                tmp_path = tmp_file.name
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to download file: HTTP {e.response.status_code}"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to download file: {str(e)}"
        )
    
    try:
        # Create a file-like object for upload
        from fastapi import UploadFile
        from io import BytesIO
        
        # Re-read the file content
        with open(tmp_path, 'rb') as f:
            file_content = f.read()
        
        # Create UploadFile-like object
        file_obj = BytesIO(file_content)
        
        # Create upload file
        upload_file = UploadFile(
            file=file_obj,
            filename=filename,
            size=len(file_content)
        )
        
        # Use document service to upload
        metadata = DocumentCreate(
            title=request.title or filename,
            description=request.description
        )
        
        document_service = DocumentService(db)
        document = await document_service.upload_document(
            file=upload_file,
            user_id=user_id,
            metadata=metadata
        )
        
        return document
        
    finally:
        # Clean up temp file
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
