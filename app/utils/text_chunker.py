"""Text chunking utilities for document processing."""

import re
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Chunking parameters - 200 words per chunk with 30 word overlap
DEFAULT_CHUNK_SIZE_WORDS = 200
DEFAULT_CHUNK_OVERLAP_WORDS = 30
MIN_CHUNK_SIZE_WORDS = 20


def chunk_text(
    text: str,
    chunk_size_words: int = DEFAULT_CHUNK_SIZE_WORDS,
    chunk_overlap_words: int = DEFAULT_CHUNK_OVERLAP_WORDS
) -> List[Dict[str, Any]]:
    """
    Split text into overlapping chunks for vector embedding.
    
    Args:
        text: The text to chunk
        chunk_size_words: Maximum size of each chunk in words (default 200)
        chunk_overlap_words: Number of overlapping words between chunks (default 30)
    
    Returns:
        List of chunk dictionaries with content and metadata
    """
    if not text or len(text.strip()) == 0:
        return []
    
    # Clean the text
    text = clean_text(text)
    
    # Split into words
    words = text.split()
    
    if len(words) == 0:
        return []
    
    chunks = []
    start_idx = 0
    
    while start_idx < len(words):
        # Calculate end index for this chunk
        end_idx = min(start_idx + chunk_size_words, len(words))
        
        # Get chunk words
        chunk_words = words[start_idx:end_idx]
        chunk_content = ' '.join(chunk_words)
        
        # Only add if meets minimum size
        if len(chunk_words) >= MIN_CHUNK_SIZE_WORDS or start_idx + chunk_size_words >= len(words):
            chunks.append({
                "content": chunk_content.strip(),
                "chunk_index": len(chunks),
                "page_number": None  # Can be enhanced to track page numbers
            })
        
        # Move start index forward by (chunk_size - overlap)
        start_idx += chunk_size_words - chunk_overlap_words
        
        # Prevent infinite loop
        if start_idx >= len(words):
            break
    
    logger.info(f"Created {len(chunks)} chunks from {len(words)} words")
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


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in text (rough approximation)."""
    # Rough estimate: ~4 characters per token for English
    return len(text) // 4
