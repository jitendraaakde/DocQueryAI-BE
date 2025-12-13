"""Query templates API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from pydantic import BaseModel, Field

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.template import QueryTemplate, DEFAULT_TEMPLATES

router = APIRouter(prefix="/templates", tags=["templates"])


# Schemas
class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    template_text: str = Field(..., min_length=1)
    description: Optional[str] = None
    category: str = "custom"
    icon: str = "sparkles"


class TemplateUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    template_text: Optional[str] = Field(None, min_length=1)
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    is_favorite: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: int
    user_id: int
    name: str
    template_text: str
    description: Optional[str]
    category: str
    icon: str
    is_default: bool
    is_favorite: bool
    use_count: int
    
    class Config:
        from_attributes = True


# Routes
@router.get("", response_model=List[TemplateResponse])
async def list_templates(
    category: Optional[str] = None,
    include_defaults: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all templates for the current user."""
    query = select(QueryTemplate).where(QueryTemplate.user_id == current_user.id)
    
    if category:
        query = query.where(QueryTemplate.category == category)
    
    result = await db.execute(query.order_by(QueryTemplate.is_favorite.desc(), QueryTemplate.use_count.desc()))
    templates = list(result.scalars().all())
    
    # Add default templates if requested and user has none
    if include_defaults and not templates:
        await seed_default_templates(db, current_user.id)
        result = await db.execute(query)
        templates = list(result.scalars().all())
    
    return templates


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    data: TemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create a new template."""
    template = QueryTemplate(
        user_id=current_user.id,
        name=data.name,
        template_text=data.template_text,
        description=data.description,
        category=data.category,
        icon=data.icon,
        is_default=False
    )
    db.add(template)
    await db.flush()
    await db.refresh(template)
    return template


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific template."""
    result = await db.execute(
        select(QueryTemplate).where(
            QueryTemplate.id == template_id,
            QueryTemplate.user_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return template


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    data: TemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update a template."""
    result = await db.execute(
        select(QueryTemplate).where(
            QueryTemplate.id == template_id,
            QueryTemplate.user_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(template, field, value)
    
    await db.flush()
    await db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Delete a template."""
    result = await db.execute(
        select(QueryTemplate).where(
            QueryTemplate.id == template_id,
            QueryTemplate.user_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    await db.delete(template)
    await db.flush()


@router.post("/{template_id}/use", response_model=TemplateResponse)
async def use_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a template as used (increment use_count)."""
    result = await db.execute(
        select(QueryTemplate).where(
            QueryTemplate.id == template_id,
            QueryTemplate.user_id == current_user.id
        )
    )
    template = result.scalar_one_or_none()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    template.use_count += 1
    await db.flush()
    await db.refresh(template)
    return template


# Helper
async def seed_default_templates(db: AsyncSession, user_id: int):
    """Seed default templates for a user."""
    for template_data in DEFAULT_TEMPLATES:
        template = QueryTemplate(
            user_id=user_id,
            **template_data
        )
        db.add(template)
    await db.flush()
