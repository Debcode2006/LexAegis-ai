"""Auth-related response schemas."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class WhoAmIResponse(BaseModel):
    user_id: str
    email: Optional[str]
    role: str
    tenant_id: str
    scopes: List[str]
