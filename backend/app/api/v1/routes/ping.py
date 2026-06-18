"""
Ping test route.

A tiny, unauthenticated diagnostic endpoint used to confirm the API is reachable
and to exercise request-id propagation end-to-end. It echoes an optional `msg`
query parameter back to the caller along with a server timestamp.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request

from app import __version__
from app.core.config import get_settings

router = APIRouter(tags=["diagnostics"])


@router.get("/ping", summary="Connectivity test route")
async def ping(
    request: Request,
    msg: str = Query(default="pong", max_length=200, description="Message to echo back."),
) -> dict:
    return {
        "pong": True,
        "echo": msg,
        "service": get_settings().app_name,
        "version": __version__,
        "request_id": getattr(request.state, "request_id", "-"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
