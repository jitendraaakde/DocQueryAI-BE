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


@router.get("/weaviate/schema")
async def get_weaviate_schema():
    """Get the current Weaviate schema for debugging."""
    schema = await weaviate_service.get_schema()
    return {
        "collection": weaviate_service.COLLECTION_NAME,
        "schema": schema
    }


@router.get("/weaviate/reset")
async def reset_weaviate_collection():
    """Reset (delete and recreate) the Weaviate collection.
    
    WARNING: This will delete all vector data in the collection!
    """
    success = await weaviate_service.reset_collection()
    if success:
        return {
            "status": "success",
            "message": f"Collection {weaviate_service.COLLECTION_NAME} has been reset"
        }
    else:
        return {
            "status": "error",
            "message": "Failed to reset collection. Check logs for details."
        }
