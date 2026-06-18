"""Authenticated principal models."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Principal(BaseModel):
    """The authenticated identity attached to a request.

    Derived from a verified Supabase JWT. `tenant_id` is resolved from the JWT
    `app_metadata` (or request header fallback) by the tenant middleware.
    """

    user_id: str = Field(..., description="Supabase user UUID (JWT `sub`).")
    email: Optional[str] = Field(default=None)
    role: str = Field(default="authenticated", description="Supabase auth role.")
    tenant_id: str = Field(default="public")
    app_metadata: Dict[str, Any] = Field(default_factory=dict)
    user_metadata: Dict[str, Any] = Field(default_factory=dict)
    scopes: List[str] = Field(default_factory=list)

    @property
    def is_service_account(self) -> bool:
        return self.role in {"service_role", "supabase_admin"}
