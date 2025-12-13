"""Health check API routes."""

from fastapi import APIRouter
from app.services.weaviate_service import weaviate_service
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """Basic health check."""
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


@router.get("/detailed")
async def detailed_health_check():
    """Detailed health check for all services."""
    from sqlalchemy import text
    from app.core.database import async_session_maker
    
    health = {
        "status": "healthy",
        "services": {}
    }
    
    # Check PostgreSQL
    try:
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        health["services"]["postgresql"] = {"status": "healthy"}
    except Exception as e:
        health["services"]["postgresql"] = {"status": "unhealthy", "error": str(e)}
        health["status"] = "degraded"
    
    # Check Weaviate
    try:
        weaviate_healthy = await weaviate_service.health_check()
        if weaviate_healthy:
            health["services"]["weaviate"] = {"status": "healthy"}
        else:
            health["services"]["weaviate"] = {"status": "unhealthy"}
            health["status"] = "degraded"
    except Exception as e:
        health["services"]["weaviate"] = {"status": "unhealthy", "error": str(e)}
        health["status"] = "degraded"
    
    # Check LLM
    if settings.GEMINI_API_KEY:
        health["services"]["llm"] = {"status": "configured", "provider": "gemini"}
    elif settings.OPENAI_API_KEY:
        health["services"]["llm"] = {"status": "configured", "provider": "openai"}
    else:
        health["services"]["llm"] = {"status": "not_configured"}
    
    return health
