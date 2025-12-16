"""API router aggregation."""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.documents import router as documents_router
from app.api.queries import router as queries_router
from app.api.health import router as health_router
from app.api.chat import router as chat_router
from app.api.collections import router as collections_router
from app.api.streaming import router as streaming_router
from app.api.analytics import router as analytics_router
from app.api.templates import router as templates_router
from app.api.otp import router as otp_router
from app.api.url_upload import router as url_upload_router

api_router = APIRouter()

# Include all routers
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(documents_router)
api_router.include_router(queries_router)
api_router.include_router(health_router)
api_router.include_router(chat_router)
api_router.include_router(collections_router)
api_router.include_router(streaming_router)
api_router.include_router(analytics_router)
api_router.include_router(templates_router)
api_router.include_router(otp_router)
api_router.include_router(url_upload_router)

