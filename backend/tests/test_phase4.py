"""Phase 4 tests: semantic cache, tracing, observability + evaluation endpoints."""

from __future__ import annotations

from app.cache.semantic_cache import SemanticCache, normalize_key
from app.observability.tracing import get_trace_recorder, span


def test_normalize_key_is_stable_and_namespaced():
    a = normalize_key("chat", "acme", "Hello   World")
    b = normalize_key("chat", "acme", "hello world")
    assert a == b  # case + whitespace normalized
    assert a.startswith("chat:")
    assert normalize_key("llm", "acme", "hello world") != a


def test_semantic_cache_hit_miss_accounting():
    cache = SemanticCache()
    cache.reset()
    key = normalize_key("chat", "t", "q")
    assert cache.get(key) is None         # miss
    cache.set(key, {"answer": "x"})
    assert cache.get(key) == {"answer": "x"}  # hit
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["hit_rate"] == 0.5


def test_span_records_into_recorder():
    recorder = get_trace_recorder()
    recorder.reset()
    with span("test.span", {"foo": "bar"}) as attrs:
        attrs["extra"] = 1
    recent = recorder.recent()
    assert recent
    assert recent[0]["name"] == "test.span"
    assert recent[0]["attributes"]["foo"] == "bar"
    assert recent[0]["duration_ms"] >= 0.0


def _auth(make_token):
    return {"Authorization": f"Bearer {make_token(tenant_id='acme')}"}


def test_observability_metrics_endpoint(client, make_token):
    resp = client.get("/api/v1/observability/metrics", headers=_auth(make_token))
    assert resp.status_code == 200
    body = resp.json()
    assert "cache" in body and "traces" in body
    assert "hit_rate" in body["cache"]


def test_chat_response_is_cached(client, make_token):
    headers = _auth(make_token)
    client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("d.txt", b"Section 1. TERM\n1.1 The term is five years.", "text/plain")},
        data={"document_type": "contract"},
    )
    q = {"query": "What is the term?"}
    r1 = client.post("/api/v1/chat", headers=headers, json=q)
    r2 = client.post("/api/v1/chat", headers=headers, json=q)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["answer"] == r2.json()["answer"]

    metrics = client.get("/api/v1/observability/metrics", headers=headers).json()
    assert metrics["cache"]["hits"] >= 1


def test_evaluation_results_endpoint_empty_ok(client, make_token):
    # With no report generated, the endpoint returns a clean empty payload.
    resp = client.get("/api/v1/evaluation/results", headers=_auth(make_token))
    assert resp.status_code == 200
    assert "available" in resp.json()


def test_observability_requires_auth(client):
    assert client.get("/api/v1/observability/metrics").status_code == 401
