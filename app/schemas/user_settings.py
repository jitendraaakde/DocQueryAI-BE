"""Schemas for user settings."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# Available models for each provider (text-only)
LLM_MODELS = {
    "groq": [
        {"value": "llama-3.3-70b-versatile", "label": "Llama 3.3 70B Versatile"},
        {"value": "llama-3.1-8b-instant", "label": "Llama 3.1 8B Instant"},
        {"value": "mixtral-8x7b-32768", "label": "Mixtral 8x7B"},
        {"value": "gemma2-9b-it", "label": "Gemma 2 9B"},
    ],
    "openai": [
        {"value": "gpt-4o", "label": "GPT-4o"},
        {"value": "gpt-4o-mini", "label": "GPT-4o Mini"},
        {"value": "gpt-4-turbo", "label": "GPT-4 Turbo"},
        {"value": "gpt-3.5-turbo", "label": "GPT-3.5 Turbo"},
    ],
    "anthropic": [
        {"value": "claude-3-5-sonnet-latest", "label": "Claude 3.5 Sonnet"},
        {"value": "claude-3-5-haiku-latest", "label": "Claude 3.5 Haiku"},
        {"value": "claude-3-opus-latest", "label": "Claude 3 Opus"},
    ],
    "gemini": [
        {"value": "gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
        {"value": "gemini-1.5-pro", "label": "Gemini 1.5 Pro"},
        {"value": "gemini-1.5-flash", "label": "Gemini 1.5 Flash"},
    ],
}

LLM_PROVIDERS = [
    {"value": "groq", "label": "Groq", "description": "Fast inference with Llama models", "requires_key": False},
    {"value": "openai", "label": "OpenAI", "description": "GPT-4 and GPT-3.5 models", "requires_key": True},
    {"value": "anthropic", "label": "Anthropic", "description": "Claude models", "requires_key": True},
    {"value": "gemini", "label": "Google Gemini", "description": "Gemini Pro models", "requires_key": True},
]


class UserSettingsBase(BaseModel):
    """Base settings schema."""
    llm_provider: Optional[str] = Field(default="groq", description="LLM provider")
    llm_model: Optional[str] = Field(default="llama-3.3-70b-versatile", description="LLM model")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2, description="Temperature")
    max_tokens: Optional[int] = Field(default=4096, ge=256, le=32768, description="Max tokens")


class UserSettingsCreate(UserSettingsBase):
    """Settings to create/update."""
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None


class UserSettingsUpdate(UserSettingsBase):
    """Settings to update (all optional)."""
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None


class UserSettingsResponse(UserSettingsBase):
    """Settings response (masks API keys)."""
    id: int
    user_id: int
    has_openai_key: bool = False
    has_anthropic_key: bool = False
    has_gemini_key: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserSettingsWithModels(BaseModel):
    """Response with settings and available models."""
    settings: Optional[UserSettingsResponse] = None
    providers: list = Field(default_factory=lambda: LLM_PROVIDERS)
    models: dict = Field(default_factory=lambda: LLM_MODELS)
    defaults: UserSettingsBase = Field(default_factory=UserSettingsBase)
