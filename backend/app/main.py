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
    from app.core.startup import run_llm_health_check, run_startup_checks
    from app.observability.tracing import init_observability

    # Emit configuration diagnostics + validate subsystems before serving so
    # missing deps/config surface as clear warnings, never as obscure crashes.
    run_startup_checks()
    # Probe Ollama (reachability + required models) and set LLM availability.
    run_llm_health_check()

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
    # Order (outer->inner): RequestContext -> CORS -> Tenant -> router/auth. CORS
    # sits ABOVE Tenant and the route dependencies, so it answers preflight
    # OPTIONS itself and short-circuits before auth ever runs. A preflight that
    # returns 400 therefore means CORS rejected it (origin/method/headers not
    # allowed) — NOT an auth failure.
    cors_origins = list(settings.cors_origins)
    cors_origin_regex = settings.cors_origin_regex or None

    # `allow_credentials=True` is incompatible with a wildcard origin: browsers
    # refuse "Access-Control-Allow-Origin: *" on credentialed requests, and
    # Starlette won't echo the caller's origin in that mode. Disable credentials
    # if someone configures "*" so the wildcard at least works for simple calls.
    allow_credentials = "*" not in cors_origins
    if not allow_credentials:
        get_logger("app.cors").warning(
            "CORS_ORIGINS contains '*': disabling allow_credentials (wildcard + "
            "credentials is rejected by browsers). Set explicit origins to use cookies/auth."
        )

    app.add_middleware(TenantMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=cors_origin_regex,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    get_logger("app.cors").info(
        "CORS configured: origins=%s origin_regex=%s allow_credentials=%s",
        cors_origins,
        cors_origin_regex or "<none>",
        allow_credentials,
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"service": settings.app_name, "version": __version__, "docs": "/docs"}

    return app


app = create_app()
