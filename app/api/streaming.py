"""Streaming response API for real-time chat."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List, AsyncGenerator
import json
import asyncio
import time

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.chat_service import chat_service
from app.services.weaviate_service import weaviate_service
from app.services.llm_service import llm_service
from app.core.config import settings

router = APIRouter(prefix="/stream", tags=["streaming"])


async def generate_stream(
    session_id: int,
    message: str,
    document_ids: List[int],
    user_id: int,
    db: AsyncSession
) -> AsyncGenerator[str, None]:
    """Generate streaming response with SSE format."""
    
    # First, add user message
    user_msg = await chat_service.add_message(db, session_id, "user", message)
    
    # Send user message confirmation
    yield f"data: {json.dumps({'type': 'user_message', 'id': user_msg.id})}\n\n"
    
    # Auto-generate title if needed
    session = await chat_service.get_session(db, session_id, user_id)
    if session and session.message_count <= 1:
        await chat_service.auto_generate_title(db, session_id, message)
    
    # Send thinking indicator
    yield f"data: {json.dumps({'type': 'thinking', 'content': 'Searching documents...'})}\n\n"
    
    start_time = time.time()
    
    # Search for relevant chunks
    search_results = await weaviate_service.search(
        query=message,
        user_id=user_id,
        document_ids=document_ids if document_ids else None,
        limit=5
    )
    
    yield f"data: {json.dumps({'type': 'thinking', 'content': 'Generating response...'})}\n\n"
    
    # Build sources
    sources = [
        {
            "document_id": result["document_id"],
            "document_name": result["document_name"],
            "chunk_id": result["chunk_index"],
            "content": result["content"][:300] + "..." if len(result["content"]) > 300 else result["content"],
            "relevance_score": result["score"],
            "page": result.get("page_number")
        }
        for result in search_results
    ]
    
    # Get chat context
    context = await chat_service.get_session_context(db, session_id, user_id, max_messages=10)
    
    # Generate response (streaming from LLM if supported)
    try:
        # For now, we'll simulate streaming by chunking the response
        # In production, you'd integrate with LLM streaming APIs
        full_response = await llm_service.generate_response(
            query=message,
            context_chunks=search_results,
            chat_history=context[:-1] if len(context) > 1 else None
        )
        
        # Simulate streaming by sending in chunks
        words = full_response.split(' ')
        accumulated = ""
        
        for i, word in enumerate(words):
            accumulated += word + " "
            
            # Send chunk every few words
            if i % 3 == 0 or i == len(words) - 1:
                yield f"data: {json.dumps({'type': 'content', 'content': word + ' '})}\n\n"
                await asyncio.sleep(0.02)  # Small delay for smooth streaming effect
        
        generation_time = int((time.time() - start_time) * 1000)
        
        # Save complete message to database
        ai_message = await chat_service.add_message(
            db=db,
            session_id=session_id,
            role="assistant",
            content=full_response.strip(),
            sources=sources,
            generation_time_ms=generation_time,
            model_used=llm_service.get_model_name()
        )
        
        # Send completion with message ID and sources
        yield f"data: {json.dumps({'type': 'complete', 'message_id': ai_message.id, 'sources': sources, 'generation_time_ms': generation_time})}\n\n"
        
    except Exception as e:
        error_msg = f"Error generating response: {str(e)}"
        
        # Save error message
        ai_message = await chat_service.add_message(
            db=db,
            session_id=session_id,
            role="assistant",
            content=error_msg
        )
        
        yield f"data: {json.dumps({'type': 'error', 'content': error_msg, 'message_id': ai_message.id})}\n\n"
    
    # End stream
    yield f"data: {json.dumps({'type': 'done'})}\n\n"


@router.get("/chat/{session_id}")
async def stream_chat_response(
    session_id: int,
    message: str,
    document_ids: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Stream a chat response using Server-Sent Events."""
    
    # Verify session ownership
    session = await chat_service.get_session(db, session_id, current_user.id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    # Parse document IDs
    doc_ids = []
    if document_ids:
        try:
            doc_ids = [int(x) for x in document_ids.split(',') if x.strip()]
        except ValueError:
            doc_ids = []
    
    # Use session document IDs if none provided
    if not doc_ids and session.document_ids:
        doc_ids = session.document_ids
    
    return StreamingResponse(
        generate_stream(session_id, message, doc_ids, current_user.id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
