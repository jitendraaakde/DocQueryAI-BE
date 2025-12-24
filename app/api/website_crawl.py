"""Website Crawl API routes - Scrape text content from webpages."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import hashlib
from datetime import datetime
from urllib.parse import urlparse
import logging
import re

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.schemas.document import DocumentResponse
from app.models.document import Document, DocumentChunk, DocumentStatus
from app.services.milvus_service import milvus_service
from app.utils.text_chunker import chunk_text

router = APIRouter(prefix="/documents", tags=["Documents"])
logger = logging.getLogger(__name__)


class WebsiteCrawlRequest(BaseModel):
    """Request body for website crawl."""
    url: str
    title: Optional[str] = None


def extract_text_from_html(html: str) -> str:
    """Extract readable text from HTML content."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove unwanted elements
    for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 
                          'noscript', 'iframe', 'form', 'button', 'input']):
        element.decompose()
    
    # Try to find main content areas
    main_content = None
    for selector in ['main', 'article', '[role="main"]', '.content', '#content', 
                     '.post-content', '.article-content', '.entry-content']:
        main_content = soup.select_one(selector)
        if main_content:
            break
    
    # Use main content if found, otherwise use body
    target = main_content or soup.body or soup
    
    # Get text with some structure preservation
    lines = []
    for element in target.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'li', 'td', 'th', 'blockquote', 'pre', 'code']):
        text = element.get_text(strip=True)
        if text and len(text) > 2:  # Skip very short strings
            # Add markdown-style headers for headings
            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                level = int(element.name[1])
                text = '#' * level + ' ' + text
            lines.append(text)
    
    # Join with double newlines for readability
    full_text = '\n\n'.join(lines)
    
    # Clean up excessive whitespace
    full_text = re.sub(r'\n{3,}', '\n\n', full_text)
    full_text = re.sub(r' {2,}', ' ', full_text)
    
    return full_text.strip()


def get_page_title(html: str, url: str) -> str:
    """Extract page title from HTML or generate from URL."""
    from bs4 import BeautifulSoup
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Try title tag
    title_tag = soup.find('title')
    if title_tag and title_tag.get_text(strip=True):
        return title_tag.get_text(strip=True)[:200]
    
    # Try h1
    h1 = soup.find('h1')
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)[:200]
    
    # Fallback to domain
    parsed = urlparse(url)
    return parsed.netloc or "Website Content"


@router.post("/from-website", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def crawl_website(
    request: WebsiteCrawlRequest,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create a document by crawling a webpage and extracting its text content."""
    
    # Validate URL
    url = request.url.strip()
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ['http', 'https']:
            raise ValueError("Invalid URL scheme")
        if not parsed.netloc:
            raise ValueError("Invalid URL format")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid URL format. Please enter a valid http/https URL."
        )
    
    # Fetch webpage
    try:
        async with httpx.AsyncClient(
            follow_redirects=True, 
            timeout=30.0,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; DocQueryAI/1.0; +https://docquery.ai)'
            }
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            
            # Check content type
            content_type = response.headers.get('content-type', '').lower()
            if 'text/html' not in content_type and 'text/plain' not in content_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="URL must point to an HTML page"
                )
            
            html_content = response.text
            
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch page: HTTP {e.response.status_code}"
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch page: {str(e)}"
        )
    
    # Extract text
    text_content = extract_text_from_html(html_content)
    
    if not text_content or len(text_content.strip()) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not extract enough text content from this page"
        )
    
    # Get title
    title = request.title or get_page_title(html_content, url)
    
    # Calculate content hash
    content_hash = hashlib.sha256(text_content.encode()).hexdigest()
    
    try:
        # Create document record
        document = Document(
            user_id=user_id,
            filename=f"website_{content_hash[:8]}.txt",
            original_filename=title,
            file_path=url,  # Store source URL
            file_type="txt",
            file_size=len(text_content.encode('utf-8')),
            content_hash=content_hash,
            title=title,
            description=f"Scraped from: {url}",
            status=DocumentStatus.PROCESSING,
            weaviate_collection=milvus_service.COLLECTION_NAME
        )
        
        db.add(document)
        await db.flush()
        await db.refresh(document)
        
        logger.info(f"Created website document {document.id} from {url}")
        
        # Chunk text
        chunks = chunk_text(text_content)
        
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
        
        logger.info(f"Website document {document.id} processed with {len(chunks)} chunks")
        
        return document
        
    except Exception as e:
        logger.error(f"Failed to process website crawl: {e}")
        if 'document' in locals():
            document.status = DocumentStatus.FAILED
            document.error_message = str(e)
            await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process page: {str(e)}"
        )
