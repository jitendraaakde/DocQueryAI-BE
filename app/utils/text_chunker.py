"""Text chunking utilities for document processing."""

import re
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Default chunking parameters
DEFAULT_CHUNK_SIZE = 1000  # characters
DEFAULT_CHUNK_OVERLAP = 200  # characters
MIN_CHUNK_SIZE = 100  # minimum chunk size


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
) -> List[Dict[str, Any]]:
    """
    Split text into overlapping chunks for vector embedding.
    
    Args:
        text: The text to chunk
        chunk_size: Maximum size of each chunk in characters
        chunk_overlap: Number of overlapping characters between chunks
    
    Returns:
        List of chunk dictionaries with content and metadata
    """
    if not text or len(text.strip()) == 0:
        return []
    
    # Clean the text
    text = clean_text(text)
    
    # Split into paragraphs first
    paragraphs = split_into_paragraphs(text)
    
    chunks = []
    current_chunk = ""
    current_page = None
    
    for para in paragraphs:
        # Check for page markers
        page_match = re.search(r'\[Page (\d+)\]', para)
        if page_match:
            current_page = int(page_match.group(1))
            para = re.sub(r'\[Page \d+\]\s*', '', para)
        
        # If adding this paragraph would exceed chunk size
        if len(current_chunk) + len(para) > chunk_size:
            if current_chunk:
                # Save current chunk
                chunks.append({
                    "content": current_chunk.strip(),
                    "chunk_index": len(chunks),
                    "page_number": current_page
                })
                
                # Start new chunk with overlap
                overlap_text = get_overlap_text(current_chunk, chunk_overlap)
                current_chunk = overlap_text + " " + para
            else:
                # Paragraph itself is too long, split it
                para_chunks = split_long_paragraph(para, chunk_size, chunk_overlap)
                for pc in para_chunks:
                    chunks.append({
                        "content": pc.strip(),
                        "chunk_index": len(chunks),
                        "page_number": current_page
                    })
                current_chunk = ""
        else:
            # Add paragraph to current chunk
            if current_chunk:
                current_chunk += "\n\n" + para
            else:
                current_chunk = para
    
    # Don't forget the last chunk
    if current_chunk and len(current_chunk.strip()) >= MIN_CHUNK_SIZE:
        chunks.append({
            "content": current_chunk.strip(),
            "chunk_index": len(chunks),
            "page_number": current_page
        })
    
    logger.info(f"Created {len(chunks)} chunks from text of {len(text)} characters")
    return chunks


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    # Remove excessive whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Remove excessive newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Strip leading/trailing whitespace
    text = text.strip()
    
    return text


def split_into_paragraphs(text: str) -> List[str]:
    """Split text into paragraphs."""
    # Split on double newlines or page markers
    paragraphs = re.split(r'\n\n+|\[Page \d+\]', text)
    
    # Re-add page markers as separate items to preserve them
    result = []
    page_pattern = re.compile(r'\[Page (\d+)\]')
    
    for match in page_pattern.finditer(text):
        # Find where to insert the page marker
        pass
    
    # Simple split for now
    paragraphs = text.split('\n\n')
    
    # Filter out empty paragraphs
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    return paragraphs


def split_long_paragraph(
    paragraph: str,
    chunk_size: int,
    chunk_overlap: int
) -> List[str]:
    """Split a long paragraph into smaller chunks."""
    chunks = []
    
    # Try to split on sentences first
    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
    
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > chunk_size:
            if current_chunk:
                chunks.append(current_chunk.strip())
                # Get overlap from end of current chunk
                overlap = get_overlap_text(current_chunk, chunk_overlap)
                current_chunk = overlap + " " + sentence
            else:
                # Single sentence is too long, split by words
                words = sentence.split()
                word_chunk = ""
                for word in words:
                    if len(word_chunk) + len(word) > chunk_size:
                        if word_chunk:
                            chunks.append(word_chunk.strip())
                            word_chunk = word
                    else:
                        word_chunk += " " + word if word_chunk else word
                if word_chunk:
                    current_chunk = word_chunk
        else:
            current_chunk += " " + sentence if current_chunk else sentence
    
    if current_chunk:
        chunks.append(current_chunk.strip())
    
    return chunks


def get_overlap_text(text: str, overlap_size: int) -> str:
    """Get the last `overlap_size` characters of text, trying to break at word boundary."""
    if len(text) <= overlap_size:
        return text
    
    overlap = text[-overlap_size:]
    
    # Try to start at a word boundary
    space_idx = overlap.find(' ')
    if space_idx > 0 and space_idx < len(overlap) // 2:
        overlap = overlap[space_idx + 1:]
    
    return overlap


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in text (rough approximation)."""
    # Rough estimate: ~4 characters per token for English
    return len(text) // 4
