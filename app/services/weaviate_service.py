"""Weaviate service for vector database operations."""

import weaviate
from weaviate.classes.init import Auth
from weaviate.classes.config import Configure, Property, DataType, VectorDistances
from weaviate.classes.query import MetadataQuery, Filter
import weaviate.classes as wvc
from typing import List, Dict, Any, Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class WeaviateService:
    """Service for Weaviate vector database operations."""
    
    COLLECTION_NAME = "DocQueryChunks"
    
    def __init__(self):
        self.client = None
        self._connected = False
    
    async def connect(self):
        """Connect to Weaviate."""
        if self._connected and self.client:
            return
        
        try:
            host = settings.WEAVIATE_HOST
            
            # Check if WEAVIATE_HOST is a full URL (for cloud/production deployments)
            if host.startswith("https://") or host.startswith("http://"):
                # Parse the URL - it's a cloud deployment (e.g., Railway)
                from urllib.parse import urlparse
                parsed = urlparse(host)
                
                is_secure = parsed.scheme == "https"
                hostname = parsed.hostname or host.replace("https://", "").replace("http://", "")
                # For cloud deployments, use standard ports
                http_port = parsed.port or (443 if is_secure else 80)
                
                logger.info(f"Connecting to cloud Weaviate at {hostname} (secure={is_secure}, http_port={http_port})")
                
                # For Railway deployments, gRPC is not exposed, so we skip init checks
                # and use HTTP-only communication
                additional_config = wvc.init.AdditionalConfig(
                    timeout=wvc.init.Timeout(init=30, query=60, insert=120)
                )
                
                if settings.WEAVIATE_API_KEY:
                    self.client = weaviate.connect_to_custom(
                        http_host=hostname,
                        http_port=http_port,
                        http_secure=is_secure,
                        grpc_host=hostname,
                        grpc_port=http_port,  # Same port, but we skip init checks
                        grpc_secure=is_secure,
                        auth_credentials=Auth.api_key(settings.WEAVIATE_API_KEY),
                        skip_init_checks=True,
                        additional_config=additional_config
                    )
                else:
                    self.client = weaviate.connect_to_custom(
                        http_host=hostname,
                        http_port=http_port,
                        http_secure=is_secure,
                        grpc_host=hostname, 
                        grpc_port=http_port,  # Same port, but we skip init checks
                        grpc_secure=is_secure,
                        skip_init_checks=True,
                        additional_config=additional_config
                    )
            else:
                # Local deployment (localhost or IP address)
                logger.info(f"Connecting to local Weaviate at {host}:{settings.WEAVIATE_PORT}")
                
                if settings.WEAVIATE_API_KEY:
                    self.client = weaviate.connect_to_custom(
                        http_host=host,
                        http_port=settings.WEAVIATE_PORT,
                        http_secure=False,
                        grpc_host=host,
                        grpc_port=settings.WEAVIATE_GRPC_PORT,
                        grpc_secure=False,
                        auth_credentials=Auth.api_key(settings.WEAVIATE_API_KEY)
                    )
                else:
                    self.client = weaviate.connect_to_local(
                        host=host,
                        port=settings.WEAVIATE_PORT,
                        grpc_port=settings.WEAVIATE_GRPC_PORT
                    )
            
            self._connected = True
            logger.info("Connected to Weaviate successfully")
            
            # Initialize collection
            await self._ensure_collection()
            
        except Exception as e:
            logger.error(f"Failed to connect to Weaviate: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Weaviate."""
        if self.client:
            self.client.close()
            self._connected = False
            logger.info("Disconnected from Weaviate")
    
    async def _ensure_collection(self):
        """Ensure the document chunks collection exists."""
        try:
            if not self.client.collections.exists(self.COLLECTION_NAME):
                self.client.collections.create(
                    name=self.COLLECTION_NAME,
                    description="Document chunks for semantic search",
                    vectorizer_config=Configure.Vectorizer.none(),  # Embeddings provided via Jina API
                    vector_index_config=Configure.VectorIndex.hnsw(
                        distance_metric=VectorDistances.COSINE
                    ),
                    properties=[
                        Property(
                            name="content",
                            data_type=DataType.TEXT,
                            description="The text content of the chunk"
                        ),
                        Property(
                            name="document_id",
                            data_type=DataType.INT,
                            description="Reference to the document in PostgreSQL"
                        ),
                        Property(
                            name="user_id",
                            data_type=DataType.INT,
                            description="Reference to the user who owns the document"
                        ),
                        Property(
                            name="chunk_index",
                            data_type=DataType.INT,
                            description="Index of the chunk within the document"
                        ),
                        Property(
                            name="document_name",
                            data_type=DataType.TEXT,
                            description="Name of the source document"
                        ),
                        Property(
                            name="page_number",
                            data_type=DataType.INT,
                            description="Page number if applicable"
                        )
                    ]
                )
                logger.info(f"Created collection: {self.COLLECTION_NAME}")
            else:
                logger.info(f"Collection {self.COLLECTION_NAME} already exists")
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
        """Add document chunks to Weaviate with embeddings from Jina API."""
        if not self._connected:
            await self.connect()
        
        collection = self.client.collections.get(self.COLLECTION_NAME)
        weaviate_ids = []
        
        try:
            # Generate embeddings for all chunks using Jina API
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            
            chunk_texts = [chunk["content"] for chunk in chunks]
            embeddings = await embedding_service.get_embeddings(chunk_texts)
            
            with collection.batch.dynamic() as batch:
                for i, chunk in enumerate(chunks):
                    properties = {
                        "content": chunk["content"],
                        "document_id": document_id,
                        "user_id": user_id,
                        "chunk_index": chunk.get("chunk_index", i),
                        "document_name": document_name,
                        "page_number": chunk.get("page_number", 0)
                    }
                    
                    # Include the embedding vector
                    uuid = batch.add_object(
                        properties=properties,
                        vector=embeddings[i]
                    )
                    weaviate_ids.append(str(uuid))
            
            logger.info(f"Added {len(chunks)} chunks with embeddings for document {document_id}")
            return weaviate_ids
            
        except Exception as e:
            logger.error(f"Failed to add chunks to Weaviate: {e}")
            raise
    
    async def search(
        self,
        query: str,
        user_id: int,
        document_ids: Optional[List[int]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for relevant chunks using vector search with Jina embeddings."""
        if not self._connected:
            await self.connect()
        
        collection = self.client.collections.get(self.COLLECTION_NAME)
        
        try:
            # Get query embedding from Jina API
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            query_vector = await embedding_service.get_query_embedding(query)
            
            # Build filter
            filters = Filter.by_property("user_id").equal(user_id)
            
            if document_ids:
                doc_filters = None
                for doc_id in document_ids:
                    doc_filter = Filter.by_property("document_id").equal(doc_id)
                    if doc_filters is None:
                        doc_filters = doc_filter
                    else:
                        doc_filters = doc_filters | doc_filter
                
                filters = filters & doc_filters
            
            # Perform vector search with the query embedding
            response = collection.query.near_vector(
                near_vector=query_vector,
                filters=filters,
                limit=limit,
                return_metadata=MetadataQuery(distance=True)
            )
            
            results = []
            for obj in response.objects:
                results.append({
                    "weaviate_id": str(obj.uuid),
                    "content": obj.properties.get("content", ""),
                    "document_id": obj.properties.get("document_id"),
                    "document_name": obj.properties.get("document_name", ""),
                    "chunk_index": obj.properties.get("chunk_index", 0),
                    "page_number": obj.properties.get("page_number", 0),
                    "score": 1 - obj.metadata.distance if obj.metadata.distance else 0.0,  # Convert distance to similarity
                    "distance": obj.metadata.distance if obj.metadata.distance else 0.0
                })
            
            logger.info(f"Found {len(results)} results for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
    
    async def delete_document_chunks(self, document_id: int):
        """Delete all chunks for a document."""
        if not self._connected:
            await self.connect()
        
        collection = self.client.collections.get(self.COLLECTION_NAME)
        
        try:
            collection.data.delete_many(
                where=Filter.by_property("document_id").equal(document_id)
            )
            logger.info(f"Deleted chunks for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete chunks: {e}")
            raise
    
    async def health_check(self) -> bool:
        """Check if Weaviate is healthy."""
        try:
            if not self._connected:
                await self.connect()
            return self.client.is_ready()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


# Singleton instance
weaviate_service = WeaviateService()
