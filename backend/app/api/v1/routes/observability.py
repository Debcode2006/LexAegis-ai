"""Observability endpoints: cache + trace metrics and recent spans."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_principal
from app.auth.models import Principal
from app.cache.semantic_cache import get_semantic_cache
from app.observability.tracing import get_trace_recorder

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics", summary="Cache + trace summary metrics")
async def metrics(_: Principal = Depends(get_current_principal)) -> dict:
    return {
        "cache": get_semantic_cache().stats(),
        "traces": get_trace_recorder().summary(),
    }


@router.get("/traces", summary="Recent spans (latency, attributes)")
async def traces(
    limit: int = Query(default=50, ge=1, le=200),
    _: Principal = Depends(get_current_principal),
) -> dict:
    return {"spans": get_trace_recorder().recent(limit=limit)}
