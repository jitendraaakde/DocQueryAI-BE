"""Chat session and message API routes."""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
import time

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import (
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSessionResponse,
    ChatSessionWithMessages,
    ChatSessionList,
    ChatMessageResponse,
    SessionQueryRequest,
    SessionQueryResponse,
    MessageFeedback,
    ChatExportRequest,
    ChatExportResponse,
)
from app.services.chat_service import chat_service
from app.services.query_service import query_service

router = APIRouter(prefix="/chat", tags=["chat"])


# ==================== SESSION ENDPOINTS ====================

@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    data: ChatSessionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new chat session."""
    session = await chat_service.create_session(db, current_user.id, data)
    return session


@router.get("/sessions", response_model=ChatSessionList)
async def list_sessions(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all chat sessions for the current user."""
    sessions, total = await chat_service.get_user_sessions(
        db, current_user.id, page=page, per_page=per_page
    )
    return ChatSessionList(
        sessions=sessions,
        total=total,
        page=page,
        per_page=per_page
    )


@router.get("/sessions/{session_id}", response_model=ChatSessionWithMessages)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a chat session with all messages."""
    session = await chat_service.get_session(
        db, session_id, current_user.id, include_messages=True
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    return session


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
async def update_session(
    session_id: int,
    data: ChatSessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a chat session."""
    session = await chat_service.update_session(db, session_id, current_user.id, data)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: int,
    permanent: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a chat session."""
    if permanent:
        success = await chat_service.hard_delete_session(db, session_id, current_user.id)
    else:
        success = await chat_service.delete_session(db, session_id, current_user.id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )


# ==================== MESSAGE ENDPOINTS ====================

@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageResponse])
async def get_messages(
    session_id: int,
    limit: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all messages in a session."""
    messages = await chat_service.get_session_messages(
        db, session_id, current_user.id, limit=limit
    )
    return messages


@router.post("/sessions/{session_id}/messages", response_model=SessionQueryResponse)
async def send_message(
    session_id: int,
    request: SessionQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Send a message and get AI response within a session."""
    # Verify session exists
    session = await chat_service.get_session(db, session_id, current_user.id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Add user message
    user_message = await chat_service.add_message(
        db, session_id, "user", request.message
    )
    
    # Auto-generate title if first message
    if session.message_count <= 1:
        await chat_service.auto_generate_title(db, session_id, request.message)
    
    # Get document IDs (from request or session)
    document_ids = request.document_ids or session.document_ids or []
    
    # Get chat context
    context = await chat_service.get_session_context(
        db, session_id, current_user.id, max_messages=10
    )
    
    # Query with context
    start_time = time.time()
    
    suggested_questions = []
    
    try:
        # Use existing query service with chat context
        query_result = await query_service.query_documents(
            db=db,
            user_id=current_user.id,
            query_text=request.message,
            document_ids=document_ids if document_ids else None,
            chat_context=context[:-1] if len(context) > 1 else None,  # Exclude current message
        )
        
        generation_time = int((time.time() - start_time) * 1000)
        
        ai_response_content = query_result.get("response", "I couldn't find relevant information.")
        
        # Add AI response
        ai_message = await chat_service.add_message(
            db=db,
            session_id=session_id,
            role="assistant",
            content=ai_response_content,
            sources=query_result.get("sources", []),
            generation_time_ms=generation_time,
            model_used=query_result.get("model", "unknown"),
        )
        
        # Generate suggested follow-up questions (non-blocking fallback)
        try:
            suggested_questions = await chat_service.generate_suggested_questions(
                user_query=request.message,
                ai_response=ai_response_content,
                max_questions=3
            )
        except Exception:
            suggested_questions = []
        
    except Exception as e:
        # Add error message
        ai_message = await chat_service.add_message(
            db=db,
            session_id=session_id,
            role="assistant",
            content=f"I encountered an error processing your request: {str(e)}",
        )
    
    # Refresh session
    session = await chat_service.get_session(db, session_id, current_user.id)
    
    return SessionQueryResponse(
        message=ai_message, 
        session=session,
        suggested_questions=suggested_questions
    )


@router.post("/messages/{message_id}/feedback", response_model=ChatMessageResponse)
async def submit_feedback(
    message_id: int,
    feedback_data: MessageFeedback,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit feedback for a message."""
    message = await chat_service.submit_feedback(
        db, message_id, current_user.id, feedback_data
    )
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    return message


# ==================== EXPORT ENDPOINTS ====================

@router.post("/sessions/{session_id}/export", response_model=ChatExportResponse)
async def export_session(
    session_id: int,
    export_request: ChatExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Export chat session to PDF, Markdown, or JSON."""
    session = await chat_service.get_session(
        db, session_id, current_user.id, include_messages=True
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # TODO: Implement actual export logic
    # For now, return placeholder
    filename = f"chat_{session_id}_{datetime.utcnow().strftime('%Y%m%d')}.{export_request.format}"
    
    return ChatExportResponse(
        download_url=f"/api/v1/exports/{filename}",
        filename=filename,
        format=export_request.format,
        expires_at=datetime.utcnow()
    )
