"""Health endpoint tests (unauthenticated)."""

from __future__ import annotations


def test_health_ok(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert "X-Request-ID" in resp.headers


def test_ready_ok(client):
    resp = client.get("/api/v1/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "service" in resp.json()
