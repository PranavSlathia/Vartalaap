"""Health check endpoints.

Provides:
- Basic health check (GET /health)
- Detailed health check with dependency status (GET /health/detailed)
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import text

from src.config import Settings, get_settings
from src.db.session import get_session

router = APIRouter()


class HealthResponse(BaseModel):
    """Basic health check response."""

    status: str


class DetailedHealthResponse(BaseModel):
    """Detailed health check response."""

    status: str
    checks: dict[str, str]
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Basic health check endpoint.

    Returns:
        Simple status indicating the API is running.
    """
    return HealthResponse(status="healthy")


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check(
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> DetailedHealthResponse:
    """Detailed health check including dependency status.

    Checks:
    - Database connectivity
    - Redis connectivity (if configured)
    - External service configuration status

    Returns:
        Status with individual component checks.
    """
    checks = {}

    # Database check
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {type(e).__name__}"

    # Redis check
    try:
        from arq import create_pool

        redis = await create_pool(settings.redis_settings)
        await redis.ping()
        await redis.close()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {type(e).__name__}"

    # External services (just check if configured, don't call APIs)
    checks["groq"] = "configured" if settings.groq_api_key.get_secret_value() else "missing"
    checks["deepgram"] = (
        "configured" if settings.deepgram_api_key.get_secret_value() else "missing"
    )
    checks["plivo"] = "configured" if settings.plivo_auth_id else "missing"

    # Feature flags
    checks["edge_tts"] = "enabled" if settings.edge_tts_enabled else "disabled"

    # Overall status
    status = "healthy" if checks["database"] == "ok" else "degraded"

    return DetailedHealthResponse(
        status=status,
        checks=checks,
        version="0.1.0",
    )
