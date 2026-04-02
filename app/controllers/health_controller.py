"""
Health check controller.
Provides status information about the application and its dependencies.
"""

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.dependencies import get_config, get_db
from app.schemas.common import HealthResponse

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Returns the health status of the application and its dependencies.",
)
async def health_check(
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_config),
) -> HealthResponse:
    """Check app health including Ollama and database connectivity."""

    # Check database
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "unhealthy"

    # Check Ollama
    ollama_status = "healthy"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            if resp.status_code != 200:
                ollama_status = "unhealthy"
    except Exception:
        ollama_status = "unreachable"

    overall = "healthy" if db_status == "healthy" and ollama_status == "healthy" else "degraded"

    return HealthResponse(
        status=overall,
        app_name=settings.APP_NAME,
        ollama_status=ollama_status,
        database_status=db_status,
    )
