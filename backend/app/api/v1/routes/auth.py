"""
Authenticated identity endpoints.

These verify the full ingress pipeline end-to-end: JWT verification, tenant
reconciliation, and rate limiting. `/auth/whoami` returns the resolved
principal; it is the canonical smoke test for the auth layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import enforce_rate_limit, get_current_principal, get_current_tenant
from app.auth.models import Principal
from app.schemas.auth import WhoAmIResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get(
    "/whoami",
    response_model=WhoAmIResponse,
    summary="Return the authenticated principal",
    dependencies=[Depends(enforce_rate_limit)],
)
async def whoami(
    principal: Principal = Depends(get_current_principal),
    tenant_id: str = Depends(get_current_tenant),
) -> WhoAmIResponse:
    return WhoAmIResponse(
        user_id=principal.user_id,
        email=principal.email,
        role=principal.role,
        tenant_id=tenant_id,
        scopes=principal.scopes,
    )
