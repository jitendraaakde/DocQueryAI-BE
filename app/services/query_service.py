"""Query service for document search and response generation."""

import time
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import logging

from app.models.query import Query
from app.schemas.query import QueryCreate, QueryResponse, QueryHistoryResponse, SourceChunk
from app.services.milvus_service import milvus_service
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


def build_sources(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build sources list from search results. Full content preserved."""
    return [
        {
            "document_id": result["document_id"],
            "document_name": result["document_name"],
            "chunk_id": result["chunk_index"],
            "content": result["content"],  # Full content, no truncation
            "relevance_score": result["score"],
            "page": result.get("page_number")
        }
        for result in search_results
    ]


def calculate_confidence(results: List[Dict[str, Any]]) -> float:
    """Calculate confidence score based on search results."""
    if not results:
        return 0.0
    
    weights = [1.0, 0.8, 0.6, 0.4, 0.2]
    weighted_sum = 0.0
    weight_total = 0.0
    
    for i, result in enumerate(results):
        if i >= len(weights):
            break
        score = result.get("score", 0)
        weighted_sum += score * weights[i]
        weight_total += weights[i]
    
    if weight_total == 0:
        return 0.0
    
    return round(min(1.0, weighted_sum / weight_total), 3)


class QueryService:
    """Service for query processing and response generation."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def process_query(
        self,
        query_data: QueryCreate,
        user_id: int
    ) -> QueryResponse:
        """Process a user query and generate a response."""
        start_time = time.time()
        
        # Search for relevant chunks
        search_start = time.time()
        search_results = await milvus_service.search(
            query=query_data.query_text,
            user_id=user_id,
            document_ids=query_data.document_ids,
            limit=3
        )
        search_time = int((time.time() - search_start) * 1000)
        
        # Generate response
        generation_start = time.time()
        response_text = await llm_service.generate_response(
            query=query_data.query_text,
            context_chunks=search_results
        )
        generation_time = int((time.time() - generation_start) * 1000)
        total_time = int((time.time() - start_time) * 1000)
        
        # Build sources and calculate confidence
        sources = build_sources(search_results)
        confidence_score = calculate_confidence(search_results)
        
        # Save query to database
        query_record = Query(
            user_id=user_id,
            query_text=query_data.query_text,
            response_text=response_text,
            sources=sources,
            confidence_score=confidence_score,
            search_time_ms=search_time,
            generation_time_ms=generation_time,
            total_time_ms=total_time
        )
        
        self.db.add(query_record)
        await self.db.flush()
        await self.db.refresh(query_record)
        
        logger.info(f"Query {query_record.id} processed in {total_time}ms")
        
        return QueryResponse(
            id=query_record.id,
            query_text=query_data.query_text,
            response_text=response_text,
            sources=[SourceChunk(**s) for s in sources],
            confidence_score=confidence_score,
            search_time_ms=search_time,
            generation_time_ms=generation_time,
            total_time_ms=total_time,
            created_at=query_record.created_at
        )
    
    async def get_query_history(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20
    ) -> QueryHistoryResponse:
        """Get paginated query history for a user."""
        count_result = await self.db.execute(
            select(func.count(Query.id)).where(Query.user_id == user_id)
        )
        total = count_result.scalar()
        
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(Query)
            .where(Query.user_id == user_id)
            .order_by(Query.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        queries = result.scalars().all()
        total_pages = (total + page_size - 1) // page_size
        
        return QueryHistoryResponse(
            queries=[
                QueryResponse(
                    id=q.id,
                    query_text=q.query_text,
                    response_text=q.response_text or "",
                    sources=[SourceChunk(**s) for s in (q.sources or [])],
                    confidence_score=q.confidence_score,
                    search_time_ms=q.search_time_ms,
                    generation_time_ms=q.generation_time_ms,
                    total_time_ms=q.total_time_ms,
                    created_at=q.created_at
                )
                for q in queries
            ],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages
        )
    
    async def rate_query(
        self,
        query_id: int,
        user_id: int,
        rating: int,
        feedback: Optional[str] = None
    ):
        """Rate a query response."""
        result = await self.db.execute(
            select(Query).where(Query.id == query_id, Query.user_id == user_id)
        )
        query = result.scalar_one_or_none()
        
        if not query:
            raise ValueError("Query not found")
        
        query.rating = rating
        query.feedback = feedback
        await self.db.flush()
        logger.info(f"Query {query_id} rated {rating}/5")
    
    async def query_documents(
        self,
        db: AsyncSession,
        user_id: int,
        query_text: str,
        document_ids: Optional[List[int]] = None,
        chat_context: Optional[List[dict]] = None,
    ) -> Dict[str, Any]:
        """Process a query with optional chat context (for chat integration)."""
        start_time = time.time()
        
        search_results = await milvus_service.search(
            query=query_text,
            user_id=user_id,
            document_ids=document_ids,
            limit=3
        )
        
        sources = build_sources(search_results)
        
        response_text = await llm_service.generate_response(
            query=query_text,
            context_chunks=search_results,
            chat_history=chat_context
        )
        
        generation_time = int((time.time() - start_time) * 1000)
        
        return {
            "response": response_text,
            "sources": sources,
            "model": llm_service.get_model_name(),
            "generation_time_ms": generation_time
        }


# Singleton for chat integration
query_service = QueryService(None)  # db will be passed per request
