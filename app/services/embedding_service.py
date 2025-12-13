"""Jina Embeddings Service for generating document embeddings.

Uses Jina AI's free embedding API (1M tokens/month free tier).
Model: jina-embeddings-v3 (768 dimensions)
"""

import httpx
from typing import List, Optional
from app.core.config import settings


class EmbeddingService:
    """Service for generating text embeddings using Jina AI API."""
    
    JINA_API_URL = "https://api.jina.ai/v1/embeddings"
    MODEL = "jina-embeddings-v3"
    DIMENSION = 1024  # jina-embeddings-v3 default dimension
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.JINA_API_KEY
        if not self.api_key:
            raise ValueError("JINA_API_KEY is required. Get a free key at https://jina.ai/embeddings/")
    
    async def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: The text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        embeddings = await self.get_embeddings([text])
        return embeddings[0]
    
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in a single API call.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.MODEL,
            "input": texts,
            "task": "retrieval.passage"  # Optimized for document retrieval
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.JINA_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            # Extract embeddings from response, sorted by index
            embeddings = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in embeddings]
    
    async def get_query_embedding(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.
        Uses 'retrieval.query' task for better search results.
        
        Args:
            query: The search query
            
        Returns:
            Embedding vector optimized for query matching
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.MODEL,
            "input": [query],
            "task": "retrieval.query"  # Optimized for search queries
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.JINA_API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            
            data = response.json()
            return data["data"][0]["embedding"]


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """Get or create the embedding service singleton."""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service
