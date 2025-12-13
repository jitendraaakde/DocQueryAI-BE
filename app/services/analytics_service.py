"""Analytics and usage tracking service."""

import logging
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import select, func, update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.document import Document
from app.models.query import Query
from app.models.chat import ChatSession, ChatMessage

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Service for tracking and analyzing usage statistics."""
    
    async def get_user_stats(
        self,
        db: AsyncSession,
        user_id: int,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get comprehensive stats for a user."""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Document stats
        doc_result = await db.execute(
            select(
                func.count(Document.id).label('total_docs'),
                func.sum(Document.file_size).label('total_size'),
                func.avg(Document.word_count).label('avg_word_count')
            ).where(
                Document.user_id == user_id,
                Document.created_at >= since_date
            )
        )
        doc_stats = doc_result.first()
        
        # Query stats
        query_result = await db.execute(
            select(
                func.count(Query.id).label('total_queries'),
                func.avg(Query.total_time_ms).label('avg_response_time'),
                func.avg(Query.confidence_score).label('avg_confidence')
            ).where(
                Query.user_id == user_id,
                Query.created_at >= since_date
            )
        )
        query_stats = query_result.first()
        
        # Chat stats
        chat_result = await db.execute(
            select(func.count(ChatSession.id)).where(
                ChatSession.user_id == user_id,
                ChatSession.created_at >= since_date
            )
        )
        chat_count = chat_result.scalar() or 0
        
        # Message count
        msg_result = await db.execute(
            select(func.count(ChatMessage.id))
            .join(ChatSession)
            .where(
                ChatSession.user_id == user_id,
                ChatMessage.created_at >= since_date
            )
        )
        message_count = msg_result.scalar() or 0
        
        return {
            "period_days": days,
            "documents": {
                "total": doc_stats.total_docs or 0,
                "total_size_bytes": int(doc_stats.total_size or 0),
                "avg_word_count": int(doc_stats.avg_word_count or 0)
            },
            "queries": {
                "total": query_stats.total_queries or 0,
                "avg_response_time_ms": int(query_stats.avg_response_time or 0),
                "avg_confidence": round(query_stats.avg_confidence or 0, 2)
            },
            "chat": {
                "sessions": chat_count,
                "messages": message_count
            }
        }
    
    async def get_activity_timeline(
        self,
        db: AsyncSession,
        user_id: int,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """Get daily activity timeline."""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        # Queries per day
        result = await db.execute(
            select(
                func.date(Query.created_at).label('date'),
                func.count(Query.id).label('query_count')
            ).where(
                Query.user_id == user_id,
                Query.created_at >= since_date
            ).group_by(func.date(Query.created_at))
            .order_by(func.date(Query.created_at))
        )
        
        timeline = []
        for row in result:
            timeline.append({
                "date": row.date.isoformat() if row.date else None,
                "queries": row.query_count
            })
        
        return timeline
    
    async def get_top_documents(
        self,
        db: AsyncSession,
        user_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get most queried documents."""
        # This requires tracking document_ids in queries
        # For now, return most recent documents
        result = await db.execute(
            select(Document)
            .where(Document.user_id == user_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
        )
        
        docs = result.scalars().all()
        return [
            {
                "id": doc.id,
                "filename": doc.original_filename,
                "word_count": doc.word_count,
                "created_at": doc.created_at.isoformat() if doc.created_at else None
            }
            for doc in docs
        ]
    
    async def check_rate_limit(
        self,
        db: AsyncSession,
        user_id: int
    ) -> Dict[str, Any]:
        """Check if user has exceeded rate limit."""
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            return {"allowed": False, "reason": "User not found"}
        
        # Check if we need to reset daily counter
        today = date.today()
        if user.last_query_reset is None or user.last_query_reset.date() < today:
            # Reset counter
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(queries_today=0, last_query_reset=datetime.utcnow())
            )
            await db.flush()
            return {
                "allowed": True,
                "remaining": user.daily_query_limit,
                "limit": user.daily_query_limit
            }
        
        # Check current usage
        if user.queries_today >= user.daily_query_limit:
            return {
                "allowed": False,
                "reason": "Daily limit exceeded",
                "remaining": 0,
                "limit": user.daily_query_limit,
                "reset_at": (datetime.combine(today + timedelta(days=1), datetime.min.time())).isoformat()
            }
        
        return {
            "allowed": True,
            "remaining": user.daily_query_limit - user.queries_today,
            "limit": user.daily_query_limit
        }
    
    async def increment_query_count(
        self,
        db: AsyncSession,
        user_id: int
    ) -> None:
        """Increment user's daily query count."""
        await db.execute(
            update(User)
            .where(User.id == user_id)
            .values(queries_today=User.queries_today + 1)
        )
        await db.flush()


# Singleton instance
analytics_service = AnalyticsService()
