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
        self._cached_base_url = None
    
    @property
    def base_url(self) -> str:
        """Get cached base URL for Weaviate HTTP requests."""
        if self._cached_base_url is None:
            host = settings.WEAVIATE_HOST
            if host.startswith("https://") or host.startswith("http://"):
                self._cached_base_url = host.rstrip("/")
            else:
                self._cached_base_url = f"http://{host}:{settings.WEAVIATE_PORT}"
        return self._cached_base_url
    
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
                # gRPC port must be different from HTTP port for validation
                # We use 50051 as a dummy port since we skip init checks anyway
                grpc_port = 50051
                
                logger.info(f"Connecting to cloud Weaviate at {hostname} (secure={is_secure}, http_port={http_port})")
                
                # For Railway deployments, gRPC is not exposed, so we skip init checks
                additional_config = wvc.init.AdditionalConfig(
                    timeout=wvc.init.Timeout(init=30, query=60, insert=120)
                )
                
                if settings.WEAVIATE_API_KEY:
                    self.client = weaviate.connect_to_custom(
                        http_host=hostname,
                        http_port=http_port,
                        http_secure=is_secure,
                        grpc_host=hostname,
                        grpc_port=grpc_port,
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
                        grpc_port=grpc_port,
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
        logger.debug(f"Adding {len(chunks)} chunks for document {document_id}")
        
        if not self._connected:
            await self.connect()
        
        collection = self.client.collections.get(self.COLLECTION_NAME)
        weaviate_ids = []
        
        try:
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            
            chunk_texts = [chunk["content"] for chunk in chunks]
            embeddings = await embedding_service.get_embeddings(chunk_texts)
            
            for i, chunk in enumerate(chunks):
                properties = {
                    "content": chunk["content"],
                    "document_id": document_id,
                    "user_id": user_id,
                    "chunk_index": chunk.get("chunk_index", i),
                    "document_name": document_name,
                    "page_number": chunk.get("page_number", 0)
                }
                
                uuid = collection.data.insert(
                    properties=properties,
                    vector=embeddings[i]
                )
                weaviate_ids.append(str(uuid))
            
            logger.info(f"Added {len(chunks)} chunks for document {document_id}")
            return weaviate_ids
            
        except Exception as e:
            logger.error(f"Failed to add chunks: {e}")
            raise
    
    # GraphQL enum values that should not be quoted
    GRAPHQL_ENUMS = {"And", "Or", "Equal", "NotEqual", "GreaterThan", "GreaterThanEqual", 
                     "LessThan", "LessThanEqual", "Like", "WithinGeoRange", "IsNull", "ContainsAny", "ContainsAll"}
    
    def _to_graphql(self, obj: Any, key: str = None) -> str:
        """Convert Python object to GraphQL format (unquoted keys, enum values)."""
        import json
        if isinstance(obj, dict):
            items = []
            for k, value in obj.items():
                items.append(f"{k}: {self._to_graphql(value, k)}")
            return "{" + ", ".join(items) + "}"
        elif isinstance(obj, list):
            return "[" + ", ".join(self._to_graphql(item, key) for item in obj) + "]"
        elif isinstance(obj, str):
            # Check if this is an enum value (for 'operator' field)
            if key == "operator" and obj in self.GRAPHQL_ENUMS:
                return obj  # Don't quote enum values
            return json.dumps(obj)  # Properly escape strings
        elif isinstance(obj, bool):
            return "true" if obj else "false"
        elif obj is None:
            return "null"
        else:
            return str(obj)
    
    async def search(
        self,
        query: str,
        user_id: int,
        document_ids: Optional[List[int]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for relevant chunks using vector search with Jina embeddings via HTTP REST API."""
        if not self._connected:
            await self.connect()
        
        try:
            # Get query embedding from Jina API
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            query_vector = await embedding_service.get_query_embedding(query)
            
            logger.info(f"Performing vector search for query: {query[:50]}...")
            
            # Build where filter
            where_filter = {
                "operator": "And",
                "operands": [
                    {
                        "path": ["user_id"],
                        "operator": "Equal",
                        "valueInt": user_id
                    }
                ]
            }
            
            if document_ids:
                doc_filter = {
                    "operator": "Or",
                    "operands": [
                        {
                            "path": ["document_id"],
                            "operator": "Equal",
                            "valueInt": doc_id
                        } for doc_id in document_ids
                    ]
                }
                where_filter["operands"].append(doc_filter)
            
            # Convert to GraphQL format (unquoted keys)
            where_graphql = self._to_graphql(where_filter)
            vector_graphql = str(query_vector)
            
            # Build GraphQL query
            graphql_query = {
                "query": f"""
                {{
                    Get {{
                        DocQueryChunks(
                            nearVector: {{
                                vector: {vector_graphql}
                            }}
                            where: {where_graphql}
                            limit: {limit}
                        ) {{
                            content
                            document_id
                            user_id
                            chunk_index
                            document_name
                            page_number
                            _additional {{
                                id
                                distance
                            }}
                        }}
                    }}
                }}
                """
            }
            
            logger.debug(f"GraphQL query: {graphql_query['query']}")
            
            # Make HTTP REST request to Weaviate GraphQL endpoint
            import httpx
            
            headers = {"Content-Type": "application/json"}
            if settings.WEAVIATE_API_KEY:
                headers["Authorization"] = f"Bearer {settings.WEAVIATE_API_KEY}"
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/v1/graphql",
                    json=graphql_query,
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
            
            data = response.json()
            
            # Check for errors
            if "errors" in data and data["errors"]:
                logger.error(f"GraphQL errors: {data['errors']}")
                return []
            
            results = []
            chunks = data.get("data", {}).get("Get", {}).get("DocQueryChunks", []) or []
            
            for obj in chunks:
                additional = obj.get("_additional", {})
                distance = additional.get("distance", 0.0)
                results.append({
                    "weaviate_id": additional.get("id", ""),
                    "content": obj.get("content", ""),
                    "document_id": obj.get("document_id"),
                    "document_name": obj.get("document_name", ""),
                    "chunk_index": obj.get("chunk_index", 0),
                    "page_number": obj.get("page_number", 0),
                    "score": 1 - distance if distance else 0.0,
                    "distance": distance
                })
            
            logger.info(f"Found {len(results)} results for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise
    
    async def delete_document_chunks(self, document_id: int):
        """Delete all chunks for a document using HTTP REST API."""
        if not self._connected:
            await self.connect()
        
        try:
            import httpx
            import json
            
            headers = {"Content-Type": "application/json"}
            if settings.WEAVIATE_API_KEY:
                headers["Authorization"] = f"Bearer {settings.WEAVIATE_API_KEY}"
            
            delete_payload = {
                "match": {
                    "class": self.COLLECTION_NAME,
                    "where": {
                        "path": ["document_id"],
                        "operator": "Equal",
                        "valueInt": document_id
                    }
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Use request() with DELETE method since delete() doesn't support json body
                response = await client.request(
                    method="DELETE",
                    url=f"{self.base_url}/v1/batch/objects",
                    content=json.dumps(delete_payload),
                    headers=headers
                )
                response.raise_for_status()
                data = response.json()
            
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
    
    async def get_schema(self) -> Dict[str, Any]:
        """Get the current schema of the collection for debugging."""
        if not self._connected:
            await self.connect()
        
        try:
            import httpx
            
            headers = {"Content-Type": "application/json"}
            if settings.WEAVIATE_API_KEY:
                headers["Authorization"] = f"Bearer {settings.WEAVIATE_API_KEY}"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/v1/schema/{self.COLLECTION_NAME}",
                    headers=headers
                )
                if response.status_code == 404:
                    return {"error": "Collection not found"}
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get schema: {e}")
            return {"error": str(e)}
    
    async def reset_collection(self) -> bool:
        """Delete and recreate the collection with the correct schema."""
        if not self._connected:
            await self.connect()
        
        try:
            # Delete the existing collection if it exists
            if self.client.collections.exists(self.COLLECTION_NAME):
                self.client.collections.delete(self.COLLECTION_NAME)
                logger.info(f"Deleted collection: {self.COLLECTION_NAME}")
            
            # Recreate the collection
            await self._ensure_collection()
            logger.info(f"Recreated collection: {self.COLLECTION_NAME}")
            return True
        except Exception as e:
            logger.error(f"Failed to reset collection: {e}")
            return False


# Singleton instance
weaviate_service = WeaviateService()
