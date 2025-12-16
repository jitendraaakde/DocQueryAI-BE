"""YouTube Upload API routes - Fetch transcripts from YouTube videos."""

from typing import Optional
import re
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


class YouTubeUploadRequest(BaseModel):
    """Request body for YouTube upload."""
    url: str
    title: Optional[str] = None


def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'  # Direct video ID
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    raise ValueError("Could not extract video ID from URL")


def fetch_transcript(video_id: str) -> str:
    """Fetch transcript from YouTube video."""
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable
    )
    
    try:
        # Create API instance (new API in v1.0+)
        ytt_api = YouTubeTranscriptApi()
        
        # Try to get English transcript first
        try:
            fetched_transcript = ytt_api.fetch(video_id, languages=['en', 'en-US', 'en-GB'])
        except NoTranscriptFound:
            # Try to list available transcripts and get any available
            try:
                transcript_list = ytt_api.list(video_id)
                # Get first available transcript
                transcript = None
                for t in transcript_list:
                    transcript = t
                    break
                
                if transcript:
                    # Try to translate if possible
                    if transcript.is_translatable:
                        try:
                            translated = transcript.translate('en')
                            fetched_transcript = translated.fetch()
                        except Exception:
                            fetched_transcript = transcript.fetch()
                    else:
                        fetched_transcript = transcript.fetch()
                else:
                    raise NoTranscriptFound(video_id, ['en'], None)
            except Exception as list_error:
                # Fallback: try fetching without language preference
                fetched_transcript = ytt_api.fetch(video_id)
        
        # Convert to raw data and combine all text segments
        if hasattr(fetched_transcript, 'to_raw_data'):
            transcript_data = fetched_transcript.to_raw_data()
        else:
            # Handle if it's already a list
            transcript_data = list(fetched_transcript)
        
        full_text = ""
        for segment in transcript_data:
            if isinstance(segment, dict):
                text = segment.get('text', '')
                start = segment.get('start', 0)
            else:
                # Handle FetchedTranscriptSnippet objects
                text = getattr(segment, 'text', '')
                start = getattr(segment, 'start', 0)
            
            # Add timestamp markers every few minutes for context
            minutes = int(start // 60)
            if minutes > 0 and start % 60 < 5:  # Near minute mark
                full_text += f"\n[{minutes}:00] "
            
            full_text += text + " "
        
        return full_text.strip()
        
    except TranscriptsDisabled:
        raise ValueError("Transcripts are disabled for this video")
    except NoTranscriptFound:
        raise ValueError("No transcript available for this video")
    except VideoUnavailable:
        raise ValueError("Video is unavailable or private")
    except Exception as e:
        raise ValueError(f"Failed to fetch transcript: {str(e)}")


@router.post("/from-youtube", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_from_youtube(
    request: YouTubeUploadRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create a document from a YouTube video transcript."""
    
    # Extract video ID
    try:
        video_id = extract_video_id(request.url.strip())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Fetch transcript
    try:
        transcript = fetch_transcript(video_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    if not transcript or len(transcript.strip()) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript too short or empty"
        )
    
    # Calculate content hash
    content_hash = hashlib.sha256(transcript.encode()).hexdigest()
    
    # Generate title
    title = request.title or f"YouTube Video - {video_id}"
    
    try:
        # Create document record
        document = Document(
            user_id=user_id,
            filename=f"youtube_{video_id}.txt",
            original_filename=title,
            file_path=f"https://youtube.com/watch?v={video_id}",  # Store source URL
            file_type="txt",
            file_size=len(transcript.encode('utf-8')),
            content_hash=content_hash,
            title=title,
            description=f"Transcript from YouTube video: {video_id}",
            status=DocumentStatus.PROCESSING,
            weaviate_collection=milvus_service.COLLECTION_NAME
        )
        
        db.add(document)
        await db.flush()
        await db.refresh(document)
        
        logger.info(f"Created YouTube document {document.id} for video {video_id}")
        
        # Chunk text
        chunks = chunk_text(transcript)
        
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
        
        logger.info(f"YouTube document {document.id} processed with {len(chunks)} chunks")
        
        return document
        
    except Exception as e:
        logger.error(f"Failed to process YouTube upload: {e}")
        if 'document' in locals():
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process transcript: {str(e)}"
        )
