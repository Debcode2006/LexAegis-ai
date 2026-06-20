"""CORS preflight behaviour tests.

Locks down the production regression where preflight OPTIONS returned 400: the
deployed frontend origin was absent from the allowlist, so Starlette's
CORSMiddleware rejected the preflight BEFORE auth/tenant/routing ran. These
tests assert the allowed-origin path returns 200 without auth, the disallowed
path returns 400, origins are normalized (trailing slash), and the regex covers
preview deploys.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from app.core.config import Settings

# The test app's default allowlist (conftest does not set CORS_ORIGINS).
_ALLOWED = "http://localhost:3000"
_DISALLOWED = "https://evil.example.com"


def _preflight(origin: str, method: str = "POST"):
    return {
        "Origin": origin,
        "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "authorization,content-type",
    }


def test_preflight_allowed_origin_returns_200(client):
    resp = client.options("/api/v1/documents/upload", headers=_preflight(_ALLOWED))
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == _ALLOWED


def test_preflight_disallowed_origin_returns_400(client):
    # This is the exact production symptom: a non-allowlisted origin -> 400.
    resp = client.options("/api/v1/observability/metrics", headers=_preflight(_DISALLOWED))
    assert resp.status_code == 400
    assert "Disallowed CORS" in resp.text


def test_preflight_does_not_run_auth(client):
    # OPTIONS preflight carries NO Authorization header by design. It must still
    # succeed for an allowed origin, proving CORS short-circuits before auth.
    resp = client.options("/api/v1/documents/upload", headers=_preflight(_ALLOWED))
    assert resp.status_code == 200
    # Sanity: the same endpoint DOES require auth for a real request.
    assert client.post("/api/v1/documents/upload").status_code == 401


def test_actual_request_carries_cors_headers(client):
    resp = client.get(
        "/api/v1/observability/metrics", headers={"Origin": _ALLOWED}
    )
    # Unauthenticated -> 401, but the CORS header must still be present so the
    # browser can read the (error) response instead of masking it as a CORS fault.
    assert resp.headers.get("access-control-allow-origin") == _ALLOWED


# --- Origin normalization (config layer) --------------------------------------

def test_trailing_slash_is_stripped():
    s = Settings(cors_origins="https://app.vercel.app/, http://localhost:3000/")
    assert s.cors_origins == ["https://app.vercel.app", "http://localhost:3000"]


def test_wildcard_origin_preserved():
    s = Settings(cors_origins="*")
    assert s.cors_origins == ["*"]


# --- Regex allowlist (Vercel preview deploys) ---------------------------------

def test_origin_regex_matches_preview_deploys():
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://app.vercel.app"],
        allow_origin_regex=r"https://app-.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/x")
    async def _x() -> dict:
        return {"ok": True}

    tc = TestClient(app)
    preview = "https://app-git-feat-abc123.vercel.app"
    resp = tc.options("/x", headers=_preflight(preview, method="GET"))
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == preview

    # An origin matching neither the list nor the regex is still rejected.
    bad = tc.options("/x", headers=_preflight("https://nope.example.com", method="GET"))
    assert bad.status_code == 400
