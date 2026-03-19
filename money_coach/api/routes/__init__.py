from fastapi import APIRouter

from money_coach.api.routes.chat import router as chat_router
from money_coach.api.routes.health import router as health_router
from money_coach.api.routes.sessions import router as sessions_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(chat_router)
api_router.include_router(sessions_router)

__all__ = ["api_router"]
