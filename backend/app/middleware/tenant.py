"""
Tenant routing middleware.

Resolves the active tenant for each request and stores it on `request.state` so
downstream dependencies and (later) retrieval can enforce tenant isolation.

Resolution order:
1. Verified JWT `app_metadata.tenant_id` (authoritative; set by the auth
   dependency once it runs — middleware runs first, so here we use a header hint
   and let the auth dependency reconcile/override).
2. The configured tenant header (e.g. `X-Tenant-ID`).
3. The configured default tenant.

This middleware performs *resolution only*; authoritative enforcement (that the
JWT tenant matches the requested tenant) happens in `deps.get_current_tenant`.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import get_settings


class TenantMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        header_tenant = request.headers.get(settings.tenant_header)
        request.state.tenant_hint = header_tenant or settings.default_tenant_id
        return await call_next(request)
