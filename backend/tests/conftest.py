"""Shared pytest fixtures.

Sets a deterministic environment *before* settings are first loaded, then builds
a TestClient and a helper to mint Supabase-style HS256 tokens for auth tests.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import jwt
import pytest

# Configure a hermetic test environment before any app import triggers settings.
_TEST_JWT_SECRET = "test-jwt-secret-please-change"
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("SUPABASE_JWT_SECRET", _TEST_JWT_SECRET)
os.environ.setdefault("SUPABASE_JWT_AUDIENCE", "authenticated")
os.environ.setdefault("RATE_LIMIT_USER_REQUESTS", "5")
os.environ.setdefault("RATE_LIMIT_USER_WINDOW_SECONDS", "60")
os.environ.setdefault("RATE_LIMIT_BURST_MULTIPLIER", "1.0")


@pytest.fixture(scope="session")
def jwt_secret() -> str:
    return _TEST_JWT_SECRET


@pytest.fixture
def make_token(jwt_secret: str):
    def _make(
        sub: str = "user-123",
        email: str = "user@example.com",
        tenant_id: str = "public",
        role: str = "authenticated",
        audience: str = "authenticated",
        expires_in: int = 3600,
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        now = int(time.time())
        payload: Dict[str, Any] = {
            "sub": sub,
            "email": email,
            "role": role,
            "aud": audience,
            "iat": now,
            "exp": now + expires_in,
            "app_metadata": {"tenant_id": tenant_id},
            "user_metadata": {},
        }
        if extra:
            payload.update(extra)
        return jwt.encode(payload, jwt_secret, algorithm="HS256")

    return _make


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.services.rate_limiter import get_rate_limiter

    # Reset rate-limiter buckets between tests for isolation.
    limiter = get_rate_limiter()
    if hasattr(limiter, "reset"):
        limiter.reset()  # type: ignore[attr-defined]

    return TestClient(create_app())
