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

# Phase 2: select light, deterministic backends so the full retrieval/safety
# pipeline runs in tests without downloading models or running services.
os.environ.setdefault("EMBEDDING_BACKEND", "hashing")
os.environ.setdefault("EMBEDDING_DIMENSION", "256")
os.environ.setdefault("RETRIEVAL_VECTOR_STORE", "memory")
os.environ.setdefault("RETRIEVAL_RERANKER_BACKEND", "lexical")
os.environ.setdefault("SAFETY_PII_BACKEND", "regex")
os.environ.setdefault("SAFETY_INPUT_GUARD_BACKEND", "heuristic")


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

    from app.cache.semantic_cache import get_semantic_cache
    from app.main import create_app
    from app.observability.tracing import get_trace_recorder
    from app.retrieval.sparse import get_bm25_index
    from app.retrieval.vector_store import get_vector_store
    from app.services.document_registry import get_document_registry
    from app.services.rate_limiter import get_rate_limiter

    # Reset all in-memory singletons between tests for isolation.
    for obj in (
        get_rate_limiter(),
        get_vector_store(),
        get_bm25_index(),
        get_document_registry(),
        get_semantic_cache(),
        get_trace_recorder(),
    ):
        if hasattr(obj, "reset"):
            obj.reset()  # type: ignore[attr-defined]

    return TestClient(create_app())
