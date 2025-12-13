"""Chat session and message service."""

from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import List, Optional
from datetime import datetime
import json

from app.models.chat import ChatSession, ChatMessage
from app.models.document import Document
from app.schemas.chat import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatMessageCreate,
    MessageFeedback,
)


class ChatService:
    """Service for managing chat sessions and messages."""
    
    # ==================== SESSION CRUD ====================
    
    async def create_session(
        self,
        db: AsyncSession,
        user_id: int,
        data: ChatSessionCreate
    ) -> ChatSession:
        """Create a new chat session."""
        session = ChatSession(
            user_id=user_id,
            title=data.title or "New Chat",
            description=data.description,
            document_ids=data.document_ids or [],
            collection_id=data.collection_id,
        )
        db.add(session)
        await db.flush()
        await db.refresh(session)
        return session
    
    async def get_session(
        self,
        db: AsyncSession,
        session_id: int,
        user_id: int,
        include_messages: bool = False
    ) -> Optional[ChatSession]:
        """Get a chat session by ID."""
        query = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id
        )
        if include_messages:
            query = query.options(selectinload(ChatSession.messages))
        
        result = await db.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_sessions(
        self,
        db: AsyncSession,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        include_active_only: bool = True
    ) -> tuple[List[ChatSession], int]:
        """Get all sessions for a user with pagination."""
        query = select(ChatSession).where(ChatSession.user_id == user_id)
        
        if include_active_only:
            query = query.where(ChatSession.is_active == True)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_query)).scalar() or 0
        
        # Get paginated results
        query = query.order_by(desc(ChatSession.last_message_at), desc(ChatSession.created_at))
        query = query.offset((page - 1) * per_page).limit(per_page)
        
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        return list(sessions), total
    
    async def update_session(
        self,
        db: AsyncSession,
        session_id: int,
        user_id: int,
        data: ChatSessionUpdate
    ) -> Optional[ChatSession]:
        """Update a chat session."""
        session = await self.get_session(db, session_id, user_id)
        if not session:
            return None
        
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(session, field, value)
        
        await db.flush()
        await db.refresh(session)
        return session
    
    async def delete_session(
        self,
        db: AsyncSession,
        session_id: int,
        user_id: int
    ) -> bool:
        """Delete a chat session (soft delete by setting is_active=False)."""
        session = await self.get_session(db, session_id, user_id)
        if not session:
            return False
        
        session.is_active = False
        await db.flush()
        return True
    
    async def hard_delete_session(
        self,
        db: AsyncSession,
        session_id: int,
        user_id: int
    ) -> bool:
        """Permanently delete a chat session."""
        session = await self.get_session(db, session_id, user_id)
        if not session:
            return False
        
        await db.delete(session)
        await db.flush()
        return True
    
    # ==================== MESSAGE CRUD ====================
    
    async def add_message(
        self,
        db: AsyncSession,
        session_id: int,
        role: str,
        content: str,
        sources: Optional[List[dict]] = None,
        generation_time_ms: Optional[int] = None,
        tokens_used: Optional[int] = None,
        model_used: Optional[str] = None
    ) -> ChatMessage:
        """Add a message to a session."""
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            sources=sources,
            generation_time_ms=generation_time_ms,
            tokens_used=tokens_used,
            model_used=model_used,
        )
        db.add(message)
        
        # Update session stats
        await db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(
                message_count=ChatSession.message_count + 1,
                last_message_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        )
        
        await db.flush()
        await db.refresh(message)
        return message
    
    async def get_session_messages(
        self,
        db: AsyncSession,
        session_id: int,
        user_id: int,
        limit: Optional[int] = None
    ) -> List[ChatMessage]:
        """Get all messages in a session."""
        # First verify user owns session
        session = await self.get_session(db, session_id, user_id)
        if not session:
            return []
        
        query = select(ChatMessage).where(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at)
        
        if limit:
            query = query.limit(limit)
        
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def submit_feedback(
        self,
        db: AsyncSession,
        message_id: int,
        user_id: int,
        feedback_data: MessageFeedback
    ) -> Optional[ChatMessage]:
        """Submit feedback for a message."""
        # Get message and verify ownership via session
        query = select(ChatMessage).join(ChatSession).where(
            ChatMessage.id == message_id,
            ChatSession.user_id == user_id
        )
        result = await db.execute(query)
        message = result.scalar_one_or_none()
        
        if not message:
            return None
        
        message.feedback = feedback_data.feedback
        message.feedback_text = feedback_data.feedback_text
        
        await db.flush()
        await db.refresh(message)
        return message
    
    # ==================== UTILITIES ====================
    
    async def auto_generate_title(
        self,
        db: AsyncSession,
        session_id: int,
        first_message: str
    ) -> str:
        """Auto-generate a title from the first message."""
        # Truncate to first 50 chars and add ellipsis
        title = first_message[:50]
        if len(first_message) > 50:
            title += "..."
        
        await db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(title=title)
        )
        await db.flush()
        return title
    
    async def get_session_context(
        self,
        db: AsyncSession,
        session_id: int,
        user_id: int,
        max_messages: int = 10
    ) -> List[dict]:
        """Get recent messages for context in new queries."""
        messages = await self.get_session_messages(
            db, session_id, user_id, limit=max_messages
        )
        
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]


# Singleton instance
chat_service = ChatService()
