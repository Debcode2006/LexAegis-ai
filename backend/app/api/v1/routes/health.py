"""Health and readiness endpoints (unauthenticated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_settings_dep
from app.core.config import Settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health(settings: Settings = Depends(get_settings_dep)) -> HealthResponse:
    from app import __version__

    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment.value,
    )


@router.get("/ready", response_model=HealthResponse, summary="Readiness probe")
async def ready(settings: Settings = Depends(get_settings_dep)) -> HealthResponse:
    # In later phases this will check Chroma/Ollama/Supabase connectivity.
    from app import __version__

    return HealthResponse(
        status="ready",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment.value,
    )
