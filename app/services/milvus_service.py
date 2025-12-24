"""Milvus/Zilliz Cloud service using REST API for vector database operations."""

import httpx
from typing import List, Dict, Any, Optional
import logging
import json

from app.core.config import settings

logger = logging.getLogger(__name__)


class MilvusService:
    """Service for Zilliz Cloud vector database operations using REST API."""
    
    COLLECTION_NAME = "DocQueryChunks"
    VECTOR_DIM = 1024  # jina-embeddings-v3 dimension
    
    def __init__(self):
        self._base_url: Optional[str] = None
        self._token: Optional[str] = None
        self._connected = False
    
    async def connect(self):
        """Initialize connection settings for Zilliz Cloud."""
        if self._connected:
            return
        
        try:
            if not settings.ZILLIZ_CLOUD_URI or not settings.ZILLIZ_CLOUD_TOKEN:
                raise ValueError(
                    "Zilliz Cloud credentials not configured. "
                    "Set ZILLIZ_CLOUD_URI and ZILLIZ_CLOUD_TOKEN in .env"
                )
            
            # Extract base URL from URI (remove any trailing paths)
            uri = settings.ZILLIZ_CLOUD_URI
            if uri.endswith('/'):
                uri = uri[:-1]
            self._base_url = uri
            self._token = settings.ZILLIZ_CLOUD_TOKEN
            
            logger.info(f"Connecting to Zilliz Cloud at {self._base_url}")
            
            self._connected = True
            logger.info("Connected to Zilliz Cloud successfully")
            
            # Initialize collection
            await self._ensure_collection()
            
        except Exception as e:
            logger.error(f"Failed to connect to Zilliz Cloud: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Zilliz Cloud."""
        self._connected = False
        logger.info("Disconnected from Zilliz Cloud")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests."""
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        timeout: float = 60.0
    ) -> Dict[str, Any]:
        """Make HTTP request to Zilliz Cloud REST API."""
        url = f"{self._base_url}/v2/vectordb{endpoint}"
        
        async with httpx.AsyncClient(timeout=timeout) as client:
            if method == "POST":
                response = await client.post(url, headers=self._get_headers(), json=data)
            elif method == "GET":
                response = await client.get(url, headers=self._get_headers())
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            result = response.json()
            
            if response.status_code != 200:
                logger.error(f"Zilliz API error: {result}")
                raise Exception(f"Zilliz API error: {result.get('message', 'Unknown error')}")
            
            # Check for API-level errors
            if result.get("code") != 0 and result.get("code") is not None:
                error_msg = result.get("message", "Unknown error")
                # Ignore "collection already exists" errors
                if "already exist" not in error_msg.lower():
                    logger.error(f"Zilliz API error: {error_msg}")
                    raise Exception(f"Zilliz API error: {error_msg}")
            
            return result
    
    async def _ensure_collection(self):
        """Ensure the document chunks collection exists."""
        try:
            # Check if collection exists
            result = await self._make_request(
                "POST",
                "/collections/has",
                {"collectionName": self.COLLECTION_NAME}
            )
            
            if result.get("data", {}).get("has", False):
                logger.info(f"Collection {self.COLLECTION_NAME} already exists")
                return
            
            # Create collection with schema
            schema = {
                "autoId": True,
                "enableDynamicField": False,
                "fields": [
                    {
                        "fieldName": "id",
                        "dataType": "Int64",
                        "isPrimary": True,
                        "autoId": True
                    },
                    {
                        "fieldName": "content",
                        "dataType": "VarChar",
                        "elementTypeParams": {"max_length": "65535"}
                    },
                    {
                        "fieldName": "document_id",
                        "dataType": "Int64"
                    },
                    {
                        "fieldName": "user_id",
                        "dataType": "Int64"
                    },
                    {
                        "fieldName": "chunk_index",
                        "dataType": "Int64"
                    },
                    {
                        "fieldName": "document_name",
                        "dataType": "VarChar",
                        "elementTypeParams": {"max_length": "1024"}
                    },
                    {
                        "fieldName": "page_number",
                        "dataType": "Int64"
                    },
                    {
                        "fieldName": "vector",
                        "dataType": "FloatVector",
                        "elementTypeParams": {"dim": str(self.VECTOR_DIM)}
                    }
                ]
            }
            
            # Create collection
            await self._make_request(
                "POST",
                "/collections/create",
                {
                    "collectionName": self.COLLECTION_NAME,
                    "schema": schema,
                    "indexParams": [
                        {
                            "fieldName": "vector",
                            "indexType": "AUTOINDEX",
                            "metricType": "COSINE"
                        }
                    ]
                }
            )
            
            logger.info(f"Created collection: {self.COLLECTION_NAME}")
                
        except Exception as e:
            logger.error(f"Failed to ensure collection: {e}")
            raise
    
    async def add_chunks(
        self,
        chunks: List[Dict[str, Any]],
        document_id: int,
        user_id: int,
        document_name: str
    ) -> List[str]:
        """Add document chunks to Zilliz Cloud with embeddings from Jina API."""
        logger.debug(f"Adding {len(chunks)} chunks for document {document_id}")
        
        if not self._connected:
            await self.connect()
        
        try:
            from app.services.embedding_service import get_embedding_service
            logger.info(f"[Step 1] Getting embedding service for {len(chunks)} chunks")
            embedding_service = get_embedding_service()
            
            # Get embeddings for all chunks
            chunk_texts = [chunk["content"] for chunk in chunks]
            logger.info(f"[Step 2] Calling embedding_service.get_embeddings with {len(chunk_texts)} texts")
            embeddings = await embedding_service.get_embeddings(chunk_texts)
            logger.info(f"[Step 3] Got {len(embeddings)} embeddings")
            
            # Debug: Log embedding dimensions
            if embeddings:
                logger.info(f"[Step 4] Embedding dimension: {len(embeddings[0])}, expected: {self.VECTOR_DIM}")
            
            # Prepare data for insertion
            logger.info("[Step 5] Preparing data for insertion")
            data = []
            for i, chunk in enumerate(chunks):
                # Ensure embedding is a plain list of floats
                vector = [float(x) for x in embeddings[i]]
                
                row = {
                    "content": str(chunk["content"])[:65535],
                    "document_id": int(document_id),
                    "user_id": int(user_id),
                    "chunk_index": int(chunk.get("chunk_index", i)),
                    "document_name": str(document_name)[:1024],
                    "page_number": int(chunk.get("page_number") or 0),
                    "vector": vector
                }
                data.append(row)
            
            # Insert data via REST API
            logger.info(f"[Step 6] Inserting {len(data)} records into Milvus collection {self.COLLECTION_NAME}")
            result = await self._make_request(
                "POST",
                "/entities/insert",
                {
                    "collectionName": self.COLLECTION_NAME,
                    "data": data
                },
                timeout=120.0  # Longer timeout for inserts
            )
            
            # Extract inserted IDs
            insert_data = result.get("data", {})
            inserted_ids = insert_data.get("insertIds", [])
            milvus_ids = [str(id) for id in inserted_ids]
            
            logger.info(f"Added {len(chunks)} chunks for document {document_id}")
            return milvus_ids
            
        except Exception as e:
            logger.error(f"Failed to add chunks: {e}")
            raise
    
    async def search(
        self,
        query: str,
        user_id: int,
        document_ids: Optional[List[int]] = None,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Search for relevant chunks using vector similarity search."""
        if not self._connected:
            await self.connect()
        
        try:
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            
            # Get query embedding
            query_vector = await embedding_service.get_query_embedding(query)
            
            logger.info(f"Performing vector search for query: {query[:50]}...")
            
            # Build filter expression
            filter_expr = f"user_id == {user_id}"
            if document_ids:
                doc_ids_str = ", ".join(str(d) for d in document_ids)
                filter_expr += f" and document_id in [{doc_ids_str}]"
            
            # Perform search via REST API
            result = await self._make_request(
                "POST",
                "/entities/search",
                {
                    "collectionName": self.COLLECTION_NAME,
                    "data": [query_vector],
                    "filter": filter_expr,
                    "limit": limit,
                    "outputFields": ["content", "document_id", "document_name", "chunk_index", "page_number"]
                }
            )
            
            # Format results
            formatted_results = []
            search_data = result.get("data", [])
            
            for hit in search_data:
                formatted_results.append({
                    "milvus_id": str(hit.get("id", "")),
                    "content": hit.get("content", ""),
                    "document_id": hit.get("document_id"),
                    "document_name": hit.get("document_name", ""),
                    "chunk_index": hit.get("chunk_index", 0),
                    "page_number": hit.get("page_number", 0),
                    "score": 1 - hit.get("distance", 0),  # Convert distance to similarity
                    "distance": hit.get("distance", 0)
                })
            
            logger.info(f"Found {len(formatted_results)} results for query: {query[:50]}...")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
    
    async def delete_document_chunks(self, document_id: int):
        """Delete all chunks for a document."""
        if not self._connected:
            await self.connect()
        
        try:
            # Delete entities by filter
            await self._make_request(
                "POST",
                "/entities/delete",
                {
                    "collectionName": self.COLLECTION_NAME,
                    "filter": f"document_id == {document_id}"
                }
            )
            
            logger.info(f"Deleted chunks for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete chunks: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check if Zilliz Cloud is healthy."""
        try:
            if not self._connected:
                await self.connect()
            
            # Check if collection exists as health indicator
            result = await self._make_request(
                "POST",
                "/collections/has",
                {"collectionName": self.COLLECTION_NAME}
            )
            return result.get("data", {}).get("has", False)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def get_schema(self) -> Dict[str, Any]:
        """Get the current schema of the collection for debugging."""
        if not self._connected:
            await self.connect()
        
        try:
            result = await self._make_request(
                "POST",
                "/collections/describe",
                {"collectionName": self.COLLECTION_NAME}
            )
            return {"collection": self.COLLECTION_NAME, "description": result.get("data", {})}
        except Exception as e:
            logger.error(f"Failed to get schema: {e}")
            return {"error": str(e)}
    
    async def reset_collection(self) -> bool:
        """Delete and recreate the collection with the correct schema."""
        if not self._connected:
            await self.connect()
        
        try:
            # Check if collection exists
            result = await self._make_request(
                "POST",
                "/collections/has",
                {"collectionName": self.COLLECTION_NAME}
            )
            
            if result.get("data", {}).get("has", False):
                # Drop the existing collection
                await self._make_request(
                    "POST",
                    "/collections/drop",
                    {"collectionName": self.COLLECTION_NAME}
                )
                logger.info(f"Dropped collection: {self.COLLECTION_NAME}")
            
            # Recreate the collection
            await self._ensure_collection()
            logger.info(f"Recreated collection: {self.COLLECTION_NAME}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset collection: {e}")
            return False


# Singleton instance
milvus_service = MilvusService()
