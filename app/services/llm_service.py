"""LLM service for generating responses."""

import logging
import asyncio
from functools import partial
from typing import List, Dict, Any, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM-based response generation."""
    
    def __init__(self):
        self.provider = settings.LLM_PROVIDER
        self._initialized = False
        self._client = None
        self._model = None
    
    def _initialize(self):
        """Initialize the LLM provider."""
        if self._initialized:
            return
        
        if self.provider == "groq" and settings.GROQ_API_KEY:
            from groq import Groq
            self._client = Groq(api_key=settings.GROQ_API_KEY)
            self._model = settings.GROQ_MODEL
            self._initialized = True
            logger.info(f"Initialized Groq LLM with model: {self._model}")
        elif self.provider == "gemini" and settings.GEMINI_API_KEY:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._client = genai.GenerativeModel('gemini-2.0-flash')
            self._model = "gemini-2.0-flash"
            self._initialized = True
            logger.info("Initialized Gemini LLM")
        else:
            logger.warning("No LLM provider configured")
    
    async def generate_response(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Generate a response based on the query and context."""
        self._initialize()
        
        if not self._initialized or not self._client:
            return self._fallback_response(query, context_chunks)
        
        # Build context
        context = self._build_context(context_chunks)
        
        # Build prompt
        prompt = self._build_prompt(query, context, chat_history)
        
        try:
            # Run in executor to not block
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                partial(self._generate, prompt)
            )
            
            return response
            
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return self._fallback_response(query, context_chunks)
    
    def _generate(self, prompt: str) -> str:
        """Generate response synchronously."""
        if self.provider == "groq":
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1024
            )
            return response.choices[0].message.content
        elif self.provider == "gemini":
            response = self._client.generate_content(prompt)
            return response.text
        else:
            return "LLM provider not configured"
    
    def _build_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Build context string from chunks."""
        context_parts = []
        
        for i, chunk in enumerate(chunks, 1):
            source_info = f"[Source {i}: {chunk.get('document_name', 'Unknown')}]"
            if chunk.get('page_number'):
                source_info += f" (Page {chunk['page_number']})"
            
            context_parts.append(f"{source_info}\n{chunk['content']}")
        
        return "\n\n---\n\n".join(context_parts)
    
    def _build_prompt(
        self,
        query: str,
        context: str,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """Build the prompt for the LLM."""
        system_prompt = """You are DocQuery AI, an intelligent document assistant. Answer questions based on the provided document context.

CRITICAL FORMATTING RULES (MUST FOLLOW):
- Add a BLANK LINE between each paragraph and section for readability
- Use **bold** for key terms, names, and important information
- Use bullet points (•) or numbered lists when listing multiple items
- Use markdown headings (## or ###) to organize different topics
- Keep each paragraph short (2-3 sentences max)
- DO NOT include source citations like "(Source 1, Source 2)" - sources are shown separately

RESPONSE STRUCTURE:
- Start with a brief intro paragraph
- (blank line)
- Use headings for different topics/people/sections
- (blank line between each section)
- End with key takeaways if appropriate

RESPONSE GUIDELINES:
1. Answer based ONLY on the provided context
2. If no relevant info found, say "I couldn't find information about that in the provided documents."
3. Be concise - get to the point quickly
4. Synthesize information naturally
5. Use a professional, helpful tone"""

        prompt_parts = [system_prompt]
        
        if chat_history:
            prompt_parts.append("\n## Previous Conversation:")
            for msg in chat_history[-5:]:  # Last 5 messages
                role = "User" if msg["role"] == "user" else "Assistant"
                prompt_parts.append(f"{role}: {msg['content']}")
        
        prompt_parts.append(f"\n## Document Context:\n{context}")
        prompt_parts.append(f"\n## User Question:\n{query}")
        prompt_parts.append("\n## Your Response:")
        
        return "\n".join(prompt_parts)
    
    def _fallback_response(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Generate a simple fallback response without LLM."""
        if not chunks:
            return "I couldn't find any relevant information in your documents to answer this question."
        
        response_parts = [
            "Based on your documents, I found the following relevant information:\n"
        ]
        
        for i, chunk in enumerate(chunks[:3], 1):
            doc_name = chunk.get('document_name', 'Unknown document')
            content = chunk['content'][:500]
            if len(chunk['content']) > 500:
                content += "..."
            
            response_parts.append(f"\n**Source {i}: {doc_name}**\n{content}\n")
        
        response_parts.append(
            "\n*Note: AI-powered response generation is not available. "
            "Please configure an LLM provider for more intelligent answers.*"
        )
        
        return "\n".join(response_parts)
    
    def get_model_name(self) -> str:
        """Get the current model name."""
        self._initialize()
        return self._model or "unknown"


# Singleton instance
llm_service = LLMService()
