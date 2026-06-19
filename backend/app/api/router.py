"""Aggregate API router; new route modules register here."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    chat,
    documents,
    evaluation,
    health,
    observability,
    ping,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(ping.router)
api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(observability.router)
api_router.include_router(evaluation.router)
