from fastapi import APIRouter, Depends

from money_coach.api.deps import get_database_pool
from money_coach.api.schemas import HealthResponse
from money_coach.infrastructure.database import DatabasePool

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(db: DatabasePool = Depends(get_database_pool)) -> HealthResponse:
    return HealthResponse(
        database="connected" if db.is_connected else "disconnected",
    )
