"""
FastAPI application factory.

Wires together the Phase 1 ingress stack:
- structured logging
- CORS
- request-context (correlation id) middleware
- tenant routing middleware
- exception handlers (consistent error envelopes)
- API v1 router (health + auth)

Later phases extend this factory with retrieval, agents, observability, and
evaluation routers without changing the wiring contract here.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.tenant import TenantMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger("app.lifespan")
    settings = get_settings()
    from app.observability.tracing import init_observability

    tracing_active = init_observability()
    logger.info(
        "Starting %s (env=%s, version=%s, tracing=%s)",
        settings.app_name,
        settings.environment.value,
        __version__,
        "phoenix" if tracing_active else "local",
    )
    yield
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="Agentic Legal Intelligence Platform — API gateway.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Middleware is applied bottom-up: the last added runs first (outermost).
    # We want request-context outermost so every log line is correlated.
    app.add_middleware(TenantMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"service": settings.app_name, "version": __version__, "docs": "/docs"}

    return app


app = create_app()
