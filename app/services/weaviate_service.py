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
        self._schema_property_types: Dict[str, str] = {}  # Cache for property types from schema
    
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
    

    
    async def search(
        self,
        query: str,
        user_id: int,
        document_ids: Optional[List[int]] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Search for relevant chunks using vector search with Jina embeddings.
        
        Uses HTTP REST API for cloud deployments where gRPC is not available.
        """
        if not self._connected:
            await self.connect()
        
        try:
            # Get query embedding from Jina API
            from app.services.embedding_service import get_embedding_service
            embedding_service = get_embedding_service()
            query_vector = await embedding_service.get_query_embedding(query)
            
            logger.info(f"Performing vector search for query: {query[:50]}...")
            
            # Ensure we have schema types cached
            if not self._schema_property_types:
                await self._cache_schema_types()
            
            # Build where filter for GraphQL with correct value types
            where_filter = {
                "operator": "And",
                "operands": [
                    self._build_filter_operand("user_id", "Equal", user_id)
                ]
            }
            
            if document_ids:
                doc_filter = {
                    "operator": "Or",
                    "operands": [
                        self._build_filter_operand("document_id", "Equal", doc_id)
                        for doc_id in document_ids
                    ]
                }
                where_filter["operands"].append(doc_filter)
            
            # Build GraphQL query
            import json
            import httpx
            
            graphql_query = {
                "query": f"""
                {{
                    Get {{
                        {self.COLLECTION_NAME}(
                            nearVector: {{
                                vector: {query_vector}
                            }}
                            where: {self._format_where_filter(where_filter)}
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
            
            # Check for errors
            if "errors" in data and data["errors"]:
                logger.error(f"GraphQL errors: {data['errors']}")
                return []
            
            results = []
            chunks = data.get("data", {}).get("Get", {}).get(self.COLLECTION_NAME, []) or []
            
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
    
    def _format_where_filter(self, filter_dict: Dict[str, Any]) -> str:
        """Format a filter dictionary to GraphQL syntax."""
        import json
        
        def to_graphql(obj, key=None):
            if isinstance(obj, dict):
                items = [f"{k}: {to_graphql(v, k)}" for k, v in obj.items()]
                return "{" + ", ".join(items) + "}"
            elif isinstance(obj, list):
                return "[" + ", ".join(to_graphql(item, key) for item in obj) + "]"
            elif isinstance(obj, str):
                # GraphQL operators should not be quoted
                if key == "operator" and obj in {"And", "Or", "Equal", "NotEqual", 
                    "GreaterThan", "LessThan", "Like", "ContainsAny", "ContainsAll"}:
                    return obj
                return json.dumps(obj)
            elif isinstance(obj, bool):
                return "true" if obj else "false"
            elif obj is None:
                return "null"
            else:
                return str(obj)
        
        return to_graphql(filter_dict)
    
    async def _cache_schema_types(self):
        """Fetch and cache schema property types from Weaviate."""
        try:
            schema = await self.get_schema()
            if "error" not in schema and "properties" in schema:
                for prop in schema["properties"]:
                    prop_name = prop.get("name", "")
                    data_types = prop.get("dataType", [])
                    if data_types:
                        # Map Weaviate dataType to GraphQL value type
                        weaviate_type = data_types[0].lower()
                        if weaviate_type in ["int", "int64"]:
                            self._schema_property_types[prop_name] = "valueInt"
                        elif weaviate_type in ["number", "float", "double"]:
                            self._schema_property_types[prop_name] = "valueNumber"
                        elif weaviate_type == "text":
                            self._schema_property_types[prop_name] = "valueText"
                        elif weaviate_type == "boolean":
                            self._schema_property_types[prop_name] = "valueBoolean"
                        else:
                            self._schema_property_types[prop_name] = "valueText"
                logger.info(f"Cached schema property types: {self._schema_property_types}")
            else:
                # Default types if schema fetch fails
                logger.warning("Schema fetch failed, using default types")
                self._schema_property_types = {
                    "user_id": "valueInt",
                    "document_id": "valueInt",
                    "chunk_index": "valueInt",
                    "page_number": "valueInt",
                    "content": "valueText",
                    "document_name": "valueText"
                }
        except Exception as e:
            logger.warning(f"Failed to cache schema types: {e}, using defaults")
            self._schema_property_types = {
                "user_id": "valueInt",
                "document_id": "valueInt",
                "chunk_index": "valueInt",
                "page_number": "valueInt",
                "content": "valueText",
                "document_name": "valueText"
            }
    
    def _build_filter_operand(self, property_name: str, operator: str, value: Any) -> Dict[str, Any]:
        """Build a filter operand with the correct value type based on schema."""
        value_type = self._schema_property_types.get(property_name, "valueInt")
        return {
            "path": [property_name],
            "operator": operator,
            value_type: value
        }
    
    async def delete_document_chunks(self, document_id: int):
        """Delete all chunks for a document using HTTP REST API.
        
        Uses HTTP REST API for cloud deployments where gRPC is not available.
        """
        if not self._connected:
            await self.connect()
        
        try:
            import httpx
            import json
            
            # Ensure we have schema types cached
            if not self._schema_property_types:
                await self._cache_schema_types()
            
            headers = {"Content-Type": "application/json"}
            if settings.WEAVIATE_API_KEY:
                headers["Authorization"] = f"Bearer {settings.WEAVIATE_API_KEY}"
            
            # Build filter operand with correct value type from schema
            filter_operand = self._build_filter_operand("document_id", "Equal", document_id)
            
            delete_payload = {
                "match": {
                    "class": self.COLLECTION_NAME,
                    "where": filter_operand
                }
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.request(
                    method="DELETE",
                    url=f"{self.base_url}/v1/batch/objects",
                    content=json.dumps(delete_payload),
                    headers=headers
                )
                response.raise_for_status()
            
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
