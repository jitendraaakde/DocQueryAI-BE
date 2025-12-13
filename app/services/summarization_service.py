"""Document summarization service using LLM."""

import logging
from typing import Optional, List
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.services.llm_service import llm_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class SummarizationService:
    """Service for generating document summaries and insights."""
    
    async def generate_summary(
        self,
        db: AsyncSession,
        document_id: int,
        chunks: List[DocumentChunk],
        length: str = "brief"  # "brief" or "detailed"
    ) -> dict:
        """Generate a summary for a document from its chunks."""
        
        if not chunks:
            return {"summary": "", "key_points": []}
        
        # Combine chunk contents (limit to avoid token limits)
        combined_text = ""
        for chunk in chunks[:20]:  # Limit to first 20 chunks
            combined_text += chunk.content + "\n\n"
        
        # Truncate if too long
        max_chars = 15000 if length == "detailed" else 8000
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars] + "..."
        
        # Generate summary
        prompt = self._build_summary_prompt(combined_text, length)
        
        try:
            summary = await llm_service.generate_response(
                query=prompt,
                context_chunks=[{"content": combined_text, "document_name": "Document"}]
            )
            
            # Parse response for key points
            key_points = self._extract_key_points(summary)
            
            return {
                "summary": summary,
                "key_points": key_points
            }
            
        except Exception as e:
            logger.error(f"Failed to generate summary: {e}")
            return {"summary": "", "key_points": []}
    
    async def summarize_document(
        self,
        db: AsyncSession,
        document_id: int,
        user_id: int
    ) -> bool:
        """Generate and store summaries for a document."""
        from sqlalchemy import select
        from app.models.document import Document, DocumentChunk
        
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
        
        # Generate brief summary
        brief_result = await self.generate_summary(db, document_id, list(chunks), "brief")
        
        # Generate detailed summary
        detailed_result = await self.generate_summary(db, document_id, list(chunks), "detailed")
        
        # Calculate insights
        insights = self._calculate_insights(list(chunks))
        
        # Update document
        await db.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                summary_brief=brief_result["summary"],
                summary_detailed=detailed_result["summary"],
                key_points=str(brief_result["key_points"]),
                word_count=insights["word_count"],
                reading_time_minutes=insights["reading_time"],
                complexity_score=insights["complexity"]
            )
        )
        await db.flush()
        
        logger.info(f"Generated summaries for document {document_id}")
        return True
    
    def _build_summary_prompt(self, text: str, length: str) -> str:
        """Build the summarization prompt."""
        if length == "brief":
            return f"""Provide a brief summary (2-3 sentences) of the following document content. Focus on the main topic and key takeaway.

Document content:
{text}

Brief summary:"""
        else:
            return f"""Provide a comprehensive summary of the following document content. Include:
1. Main topic and purpose
2. Key findings or arguments
3. Important details
4. Conclusions

Document content:
{text}

Detailed summary:"""
    
    def _extract_key_points(self, summary: str) -> List[str]:
        """Extract key points from the summary."""
        # Simple extraction - look for numbered items or bullet points
        lines = summary.split('\n')
        key_points = []
        
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
                # Clean up the line
                clean = line.lstrip('0123456789.-•) ').strip()
                if clean and len(clean) > 10:
                    key_points.append(clean)
        
        # If no structured points found, split summary into sentences
        if not key_points and summary:
            sentences = summary.replace('\n', ' ').split('.')
            key_points = [s.strip() + '.' for s in sentences[:5] if len(s.strip()) > 20]
        
        return key_points[:5]  # Limit to 5 key points
    
    def _calculate_insights(self, chunks: List[DocumentChunk]) -> dict:
        """Calculate document insights from chunks."""
        total_words = 0
        total_sentences = 0
        total_syllables = 0
        
        for chunk in chunks:
            words = chunk.content.split()
            total_words += len(words)
            total_sentences += chunk.content.count('.') + chunk.content.count('!') + chunk.content.count('?')
            
            # Estimate syllables (rough approximation)
            for word in words:
                total_syllables += max(1, len([c for c in word.lower() if c in 'aeiou']))
        
        # Calculate reading time (avg 250 words per minute)
        reading_time = max(1, total_words // 250)
        
        # Calculate complexity (Flesch Reading Ease approximation)
        if total_sentences > 0 and total_words > 0:
            avg_words_per_sentence = total_words / total_sentences
            avg_syllables_per_word = total_syllables / total_words
            complexity = 206.835 - (1.015 * avg_words_per_sentence) - (84.6 * avg_syllables_per_word)
            complexity = max(0, min(100, complexity))  # Normalize to 0-100
        else:
            complexity = 50  # Default middle complexity
        
        return {
            "word_count": total_words,
            "reading_time": reading_time,
            "complexity": round(complexity, 1)
        }


# Singleton instance
summarization_service = SummarizationService()
