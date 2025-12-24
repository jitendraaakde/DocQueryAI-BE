"""LLM service for generating responses with multi-provider support using direct API calls."""

import logging
from typing import List, Dict, Any, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM-based response generation supporting multiple providers via REST APIs."""
    
    def __init__(self):
        # Default to env config
        self._default_provider = settings.LLM_PROVIDER
        self._default_groq_key = settings.GROQ_API_KEY
        self._default_gemini_key = getattr(settings, 'GEMINI_API_KEY', None)
    
    async def generate_response(
        self,
        query: str,
        context_chunks: List[Dict[str, Any]],
        chat_history: Optional[List[Dict[str, str]]] = None,
        user_settings: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a response based on the query and context.
        
        Args:
            query: User's question
            context_chunks: Relevant document chunks
            chat_history: Previous conversation messages
            user_settings: Optional user settings dict with keys:
                - llm_provider: groq/openai/anthropic/gemini
                - llm_model: model identifier
                - temperature: float 0-2
                - max_tokens: int
                - openai_api_key, anthropic_api_key, gemini_api_key
        """
        # Determine provider and settings
        provider = "groq"  # Default
        model = "llama-3.3-70b-versatile"
        temperature = 0.7
        max_tokens = 4096
        api_key = self._default_groq_key
        
        if user_settings:
            provider = user_settings.get('llm_provider', provider)
            model = user_settings.get('llm_model', model)
            temperature = user_settings.get('temperature', temperature)
            max_tokens = user_settings.get('max_tokens', max_tokens)
            
            # Get appropriate API key
            if provider == 'openai':
                api_key = user_settings.get('openai_api_key')
            elif provider == 'anthropic':
                api_key = user_settings.get('anthropic_api_key')
            elif provider == 'gemini':
                api_key = user_settings.get('gemini_api_key') or self._default_gemini_key
            elif provider == 'groq':
                api_key = self._default_groq_key  # Groq uses our key
        
        # Validate we have an API key
        if not api_key and provider != 'groq':
            logger.warning(f"No API key for provider {provider}, falling back to Groq")
            provider = 'groq'
            model = 'llama-3.3-70b-versatile'
            api_key = self._default_groq_key
        
        if not api_key:
            logger.error("No API key available for any provider")
            return self._fallback_response(query, context_chunks)
        
        # Build context and prompt
        context = self._build_context(context_chunks)
        prompt = self._build_prompt(query, context, chat_history)
        
        try:
            response = await self._generate_async(
                provider=provider,
                model=model,
                prompt=prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key
            )
            return response
            
        except Exception as e:
            logger.error(f"LLM generation failed with {provider}/{model}: {e}")
            return self._fallback_response(query, context_chunks)
    
    async def _generate_async(
        self,
        provider: str,
        model: str,
        prompt: str,
        temperature: float,
        max_tokens: int,
        api_key: str
    ) -> str:
        """Generate response asynchronously for a specific provider."""
        try:
            if provider == "groq":
                return await self._generate_groq(model, prompt, temperature, max_tokens, api_key)
            elif provider == "openai":
                return await self._generate_openai(model, prompt, temperature, max_tokens, api_key)
            elif provider == "anthropic":
                return await self._generate_anthropic(model, prompt, temperature, max_tokens, api_key)
            elif provider == "gemini":
                return await self._generate_gemini(model, prompt, temperature, max_tokens, api_key)
            else:
                logger.error(f"Unknown provider: {provider}")
                return "LLM provider not supported"
        except Exception as e:
            logger.error(f"Generation error with {provider}: {e}")
            raise
    
    async def _generate_groq(self, model: str, prompt: str, temperature: float, max_tokens: int, api_key: str) -> str:
        """Generate with Groq (Llama/Mixtral models) using REST API."""
        url = "https://api.groq.com/openai/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    
    async def _generate_openai(self, model: str, prompt: str, temperature: float, max_tokens: int, api_key: str) -> str:
        """Generate with OpenAI (GPT models) using REST API."""
        url = "https://api.openai.com/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
    
    async def _generate_anthropic(self, model: str, prompt: str, temperature: float, max_tokens: int, api_key: str) -> str:
        """Generate with Anthropic (Claude models) using REST API."""
        url = "https://api.anthropic.com/v1/messages"
        
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["content"][0]["text"]
    
    async def _generate_gemini(self, model: str, prompt: str, temperature: float, max_tokens: int, api_key: str) -> str:
        """Generate with Google Gemini using REST API."""
        # Use the model name or default to gemini-pro
        model_name = model if model.startswith("gemini") else "gemini-pro"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens
            }
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            
            # Extract text from response
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    return parts[0].get("text", "")
            
            return "No response generated"
    
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

RESPONSE GUIDELINES:
1. Answer based ONLY on the provided context
2. If no relevant info found, say "I couldn't find information about that in the provided documents."
3. Be concise - get to the point quickly, generate short responses but contains required information.
4. Synthesize information naturally
5. Use a professional, helpful tone"""

        prompt_parts = [system_prompt]
        
        if chat_history:
            prompt_parts.append("\n## Previous Conversation:")
            for msg in chat_history[-5:]:
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
    
    def get_model_name(self, user_settings: Optional[Dict[str, Any]] = None) -> str:
        """Get the current model name."""
        if user_settings:
            return user_settings.get('llm_model', 'llama-3.3-70b-versatile')
        return "llama-3.3-70b-versatile"


# Singleton instance
llm_service = LLMService()
