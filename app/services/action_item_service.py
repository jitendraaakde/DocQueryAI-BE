"""Action item extraction service using LLM."""

import logging
import json
from typing import Optional, List, Dict, Any
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class ActionItemService:
    """Service for extracting action items from documents using AI."""
    
    async def extract_action_items(
        self,
        db: AsyncSession,
        document_id: int,
        chunks: List[DocumentChunk]
    ) -> List[Dict[str, Any]]:
        """Extract action items from document chunks.
        
        Returns a list of action items with:
        - task: The action item description
        - priority: high/medium/low
        - deadline: Optional date/deadline mentioned
        - category: task/decision/commitment/follow-up
        """
        
        if not chunks:
            return []
        
        # Combine chunk contents (limit to avoid token limits)
        combined_text = ""
        for chunk in chunks[:25]:  # Limit to first 25 chunks
            combined_text += chunk.content + "\n\n"
        
        # Truncate if too long
        max_chars = 12000
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars] + "..."
        
        # Build prompt for action item extraction
        prompt = self._build_extraction_prompt(combined_text)
        
        try:
            response = await llm_service.generate_response(
                query=prompt,
                context_chunks=[{"content": combined_text, "document_name": "Document"}]
            )
            
            # Parse the response
            action_items = self._parse_action_items(response)
            
            return action_items
            
        except Exception as e:
            logger.error(f"Failed to extract action items: {e}")
            return []
    
    async def extract_and_store_action_items(
        self,
        db: AsyncSession,
        document_id: int,
        user_id: int
    ) -> bool:
        """Extract and store action items for a document."""
        from sqlalchemy import select
        
        # Get document
        result = await db.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id
            )
        )
        document = result.scalar_one_or_none()
        
        if not document:
            return False
        
        # Get chunks
        chunks_result = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        chunks = chunks_result.scalars().all()
        
        if not chunks:
            return False
        
        # Extract action items
        action_items = await self.extract_action_items(db, document_id, list(chunks))
        
        # Store as JSON in document
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(action_items=json.dumps(action_items))
        )
        await db.flush()
        
        logger.info(f"Extracted {len(action_items)} action items for document {document_id}")
        return True
    
    def _build_extraction_prompt(self, text: str) -> str:
        """Build the action item extraction prompt."""
        return f"""Analyze the following document and extract all action items, tasks, to-dos, deadlines, commitments, and decision points.

For each item found, provide:
1. The task or action description
2. Priority (high/medium/low based on urgency/importance mentioned)
3. Deadline (if any date or timeline is mentioned)
4. Category (task/decision/commitment/follow-up)

Format your response as a JSON array. Example:
[
  {{"task": "Review quarterly report", "priority": "high", "deadline": "Dec 15", "category": "task"}},
  {{"task": "Schedule meeting with team", "priority": "medium", "deadline": null, "category": "follow-up"}}
]

If no action items are found, return an empty array: []

Document content:
{text}

Action items (JSON array only, no other text):"""
    
    def _parse_action_items(self, response: str) -> List[Dict[str, Any]]:
        """Parse action items from LLM response."""
        try:
            # Try to find JSON array in response
            response = response.strip()
            
            # Find the JSON array in the response
            start_idx = response.find('[')
            end_idx = response.rfind(']') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                items = json.loads(json_str)
                
                # Validate and clean items
                valid_items = []
                for item in items:
                    if isinstance(item, dict) and 'task' in item:
                        valid_items.append({
                            'task': item.get('task', ''),
                            'priority': item.get('priority', 'medium'),
                            'deadline': item.get('deadline'),
                            'category': item.get('category', 'task')
                        })
                
                return valid_items
            
            return []
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse action items JSON: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing action items: {e}")
            return []


# Singleton instance
action_item_service = ActionItemService()
