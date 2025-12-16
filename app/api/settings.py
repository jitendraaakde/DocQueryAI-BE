"""User settings API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.models.user_settings import UserSettings
from app.schemas.user_settings import (
    UserSettingsCreate,
    UserSettingsUpdate,
    UserSettingsResponse,
    UserSettingsWithModels,
    UserSettingsBase,
    LLM_PROVIDERS,
    LLM_MODELS,
)

router = APIRouter(prefix="/settings", tags=["Settings"])
logger = logging.getLogger(__name__)


def settings_to_response(settings: UserSettings) -> UserSettingsResponse:
    """Convert UserSettings model to response with masked keys."""
    return UserSettingsResponse(
        id=settings.id,
        user_id=settings.user_id,
        llm_provider=settings.llm_provider,
        llm_model=settings.llm_model,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        has_openai_key=bool(settings.openai_api_key),
        has_anthropic_key=bool(settings.anthropic_api_key),
        has_gemini_key=bool(settings.gemini_api_key),
        created_at=settings.created_at,
        updated_at=settings.updated_at,
    )


@router.get("", response_model=UserSettingsWithModels)
async def get_settings(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Get user settings with available providers and models."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    
    return UserSettingsWithModels(
        settings=settings_to_response(settings) if settings else None,
        providers=LLM_PROVIDERS,
        models=LLM_MODELS,
        defaults=UserSettingsBase(),
    )


@router.put("", response_model=UserSettingsResponse)
async def update_settings(
    data: UserSettingsUpdate,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Create or update user settings."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        # Create new settings
        settings = UserSettings(user_id=user_id)
        db.add(settings)
    
    # Update fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:  # Don't update fields that weren't sent
            setattr(settings, field, value)
    
    await db.flush()
    await db.refresh(settings)
    
    logger.info(f"Updated settings for user {user_id}: provider={settings.llm_provider}, model={settings.llm_model}")
    
    return settings_to_response(settings)


@router.delete("/api-key/{provider}")
async def delete_api_key(
    provider: str,
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    """Delete a specific API key."""
    if provider not in ["openai", "anthropic", "gemini"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider: {provider}"
        )
    
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Settings not found"
        )
    
    key_field = f"{provider}_api_key"
    setattr(settings, key_field, None)
    
    await db.flush()
    
    logger.info(f"Deleted {provider} API key for user {user_id}")
    
    return {"message": f"{provider.capitalize()} API key deleted"}


@router.get("/providers")
async def get_providers():
    """Get available LLM providers and their models."""
    return {
        "providers": LLM_PROVIDERS,
        "models": LLM_MODELS,
    }
