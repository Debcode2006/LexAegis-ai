"""
Dependency-injection providers for the API layer.

These FastAPI dependencies compose the request pipeline:

    get_current_principal  -> verified Supabase identity
    get_current_tenant     -> reconciled + isolation-enforced tenant id
    enforce_rate_limit     -> per-user + per-tenant token-bucket guard

Route handlers declare the dependencies they need; FastAPI resolves them in
order and short-circuits with the appropriate error envelope on failure.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import Principal
from app.auth.supabase import SupabaseAuthenticator, get_authenticator
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError, RateLimitError, TenantError
from app.services.rate_limiter import RateLimiter, RateLimitResult, get_rate_limiter

# auto_error=False so we can raise our own enveloped AuthenticationError.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_settings_dep() -> Settings:
    return get_settings()


async def get_current_principal(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    authenticator: SupabaseAuthenticator = Depends(get_authenticator),
) -> Principal:
    """Resolve and verify the authenticated principal from the bearer token."""

    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing Authorization bearer token.")
    return authenticator.authenticate(credentials.credentials)


async def get_current_tenant(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    settings: Settings = Depends(get_settings_dep),
) -> str:
    """Reconcile the JWT tenant with the requested tenant and enforce isolation.

    If isolation is enforced and the request explicitly targets a tenant
    (via header) that differs from the principal's tenant, the request is
    rejected. Otherwise the principal's tenant is authoritative.
    """

    principal_tenant = principal.tenant_id
    requested_tenant = getattr(request.state, "tenant_hint", None)

    if (
        settings.enforce_tenant_isolation
        and requested_tenant
        and requested_tenant != settings.default_tenant_id
        and requested_tenant != principal_tenant
        and not principal.is_service_account
    ):
        raise TenantError(
            "Requested tenant does not match authenticated tenant.",
            details={"requested": requested_tenant, "principal": principal_tenant},
        )

    request.state.tenant_id = principal_tenant
    return principal_tenant


def _apply_headers(request: Request, result: RateLimitResult, scope: str) -> None:
    """Stash limit metadata on request.state for the response (best-effort)."""

    meta = getattr(request.state, "rate_limit_meta", {})
    meta[scope] = {
        "limit": result.limit,
        "remaining": result.remaining,
        "reset_after": round(result.reset_after, 3),
    }
    request.state.rate_limit_meta = meta


async def enforce_rate_limit(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    tenant_id: str = Depends(get_current_tenant),
    settings: Settings = Depends(get_settings_dep),
    limiter: RateLimiter = Depends(get_rate_limiter),
) -> None:
    """Enforce per-user and per-tenant rate limits (both must pass)."""

    cfg = settings.rate_limit
    if not cfg.enabled:
        return

    user_result = limiter.check(
        key=f"user:{principal.user_id}",
        limit=cfg.user_requests,
        window_seconds=cfg.user_window_seconds,
        burst_multiplier=cfg.burst_multiplier,
    )
    _apply_headers(request, user_result, "user")
    if not user_result.allowed:
        raise RateLimitError(
            "Per-user rate limit exceeded.",
            details={"scope": "user", "retry_after": round(user_result.retry_after, 3)},
            headers={"Retry-After": str(int(user_result.retry_after) + 1)},
        )

    tenant_result = limiter.check(
        key=f"tenant:{tenant_id}",
        limit=cfg.tenant_requests,
        window_seconds=cfg.tenant_window_seconds,
        burst_multiplier=cfg.burst_multiplier,
    )
    _apply_headers(request, tenant_result, "tenant")
    if not tenant_result.allowed:
        raise RateLimitError(
            "Per-tenant rate limit exceeded.",
            details={"scope": "tenant", "retry_after": round(tenant_result.retry_after, 3)},
            headers={"Retry-After": str(int(tenant_result.retry_after) + 1)},
        )
