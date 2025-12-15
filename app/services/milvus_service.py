"""Milvus/Zilliz Cloud service for vector database operations."""

from pymilvus import MilvusClient, DataType
from typing import List, Dict, Any, Optional
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class MilvusService:
    """Service for Milvus/Zilliz Cloud vector database operations."""
    
    COLLECTION_NAME = "DocQueryChunks"
    VECTOR_DIM = 1024  # jina-embeddings-v3 dimension
    
    def __init__(self):
        self.client: Optional[MilvusClient] = None
        self._connected = False
    
    async def connect(self):
        """Connect to Zilliz Cloud."""
        if self._connected and self.client:
            return
        
        try:
            if not settings.ZILLIZ_CLOUD_URI or not settings.ZILLIZ_CLOUD_TOKEN:
                raise ValueError(
                    "Zilliz Cloud credentials not configured. "
                    "Set ZILLIZ_CLOUD_URI and ZILLIZ_CLOUD_TOKEN in .env"
                )
            
            logger.info(f"Connecting to Zilliz Cloud at {settings.ZILLIZ_CLOUD_URI}")
            
            self.client = MilvusClient(
                uri=settings.ZILLIZ_CLOUD_URI,
                token=settings.ZILLIZ_CLOUD_TOKEN
            )
            
            self._connected = True
            logger.info("Connected to Zilliz Cloud successfully")
            
            # Initialize collection
            await self._ensure_collection()
            
        except Exception as e:
            logger.error(f"Failed to connect to Zilliz Cloud: {e}")
            raise
    
    async def disconnect(self):
        """Disconnect from Zilliz Cloud."""
        if self.client:
            self.client.close()
            self._connected = False
            logger.info("Disconnected from Zilliz Cloud")
    
    async def _ensure_collection(self):
        """Ensure the document chunks collection exists."""
        try:
            if not self.client.has_collection(self.COLLECTION_NAME):
                # Create schema
                schema = MilvusClient.create_schema(
                    auto_id=True,
                    enable_dynamic_field=False,
                )
                
                # Add fields
                schema.add_field(
                    field_name="id",
                    datatype=DataType.INT64,
                    is_primary=True,
                    auto_id=True
                )
                schema.add_field(
                    field_name="content",
                    datatype=DataType.VARCHAR,
                    max_length=65535,
                    description="The text content of the chunk"
                )
                schema.add_field(
                    field_name="document_id",
                    datatype=DataType.INT64,
                    description="Reference to the document in PostgreSQL"
                )
                schema.add_field(
                    field_name="user_id",
                    datatype=DataType.INT64,
                    description="Reference to the user who owns the document"
                )
                schema.add_field(
                    field_name="chunk_index",
                    datatype=DataType.INT64,
                    description="Index of the chunk within the document"
                )
                schema.add_field(
                    field_name="document_name",
                    datatype=DataType.VARCHAR,
                    max_length=1024,
                    description="Name of the source document"
                )
                schema.add_field(
                    field_name="page_number",
                    datatype=DataType.INT64,
                    description="Page number if applicable"
                )
                schema.add_field(
                    field_name="vector",
                    datatype=DataType.FLOAT_VECTOR,
                    dim=self.VECTOR_DIM,
                    description="Jina embedding vector"
                )
                
                # Prepare index parameters
                index_params = self.client.prepare_index_params()
                
                # Add index for vector field
                index_params.add_index(
                    field_name="vector",
                    index_type="AUTOINDEX",
                    metric_type="COSINE"
                )
                
                # Add indexes for filter fields
                index_params.add_index(field_name="document_id")
                index_params.add_index(field_name="user_id")
                
                # Create collection
                self.client.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    schema=schema,
                    index_params=index_params
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
                
                # Explicitly cast all values to correct types
                content_val = str(chunk["content"])[:65535]
                doc_id_val = int(document_id)
                user_id_val = int(user_id)
                chunk_idx_val = int(chunk.get("chunk_index", i))
                doc_name_val = str(document_name)[:1024]
                page_num_val = int(chunk.get("page_number") or 0)  # Handle None
                
                row = {
                    "content": content_val,
                    "document_id": doc_id_val,
                    "user_id": user_id_val,
                    "chunk_index": chunk_idx_val,
                    "document_name": doc_name_val,
                    "page_number": page_num_val,
                    "vector": vector
                }
                data.append(row)
            
            # Debug: Log first row's field types
            if data:
                logger.info(f"[Step 5b] First row field types:")
                for key, val in data[0].items():
                    if key == "vector":
                        logger.info(f"  {key}: list[{type(val[0]).__name__}] len={len(val)}")
                    else:
                        logger.info(f"  {key}: {type(val).__name__} = {str(val)[:50]}")
            
            # Insert data
            logger.info(f"[Step 6] Inserting {len(data)} records into Milvus collection {self.COLLECTION_NAME}")
            result = self.client.insert(
                collection_name=self.COLLECTION_NAME,
                data=data
            )
            
            # Extract inserted IDs
            milvus_ids = [str(id) for id in result["ids"]]
            
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
            
            # Perform search
            results = self.client.search(
                collection_name=self.COLLECTION_NAME,
                data=[query_vector],
                filter=filter_expr,
                limit=limit,
                output_fields=["content", "document_id", "document_name", "chunk_index", "page_number"]
            )
            
            # Format results
            formatted_results = []
            if results and len(results) > 0:
                for hit in results[0]:
                    entity = hit.get("entity", {})
                    formatted_results.append({
                        "milvus_id": str(hit.get("id", "")),
                        "content": entity.get("content", ""),
                        "document_id": entity.get("document_id"),
                        "document_name": entity.get("document_name", ""),
                        "chunk_index": entity.get("chunk_index", 0),
                        "page_number": entity.get("page_number", 0),
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
            self.client.delete(
                collection_name=self.COLLECTION_NAME,
                filter=f"document_id == {document_id}"
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
            return self.client.has_collection(self.COLLECTION_NAME)
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    async def get_schema(self) -> Dict[str, Any]:
        """Get the current schema of the collection for debugging."""
        if not self._connected:
            await self.connect()
        
        try:
            if self.client.has_collection(self.COLLECTION_NAME):
                desc = self.client.describe_collection(self.COLLECTION_NAME)
                return {"collection": self.COLLECTION_NAME, "description": desc}
            return {"error": "Collection not found"}
        except Exception as e:
            logger.error(f"Failed to get schema: {e}")
            return {"error": str(e)}
    
    async def reset_collection(self) -> bool:
        """Delete and recreate the collection with the correct schema."""
        if not self._connected:
            await self.connect()
        
        try:
            # Delete the existing collection if it exists
            if self.client.has_collection(self.COLLECTION_NAME):
                self.client.drop_collection(self.COLLECTION_NAME)
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
