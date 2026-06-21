"""LLM abstraction tests: Ollama client parsing and provider fallback."""

from __future__ import annotations

import httpx

from app.cache.semantic_cache import SemanticCache
from app.llm.base import ChatMessage, LLMError, LLMResponse, Role
from app.llm.gemini_client import GeminiClient, _to_gemini_contents
from app.llm.ollama_client import OllamaClient
from app.llm.provider import LLMProvider


def _fresh_cache() -> SemanticCache:
    cache = SemanticCache()
    cache.reset()
    return cache


class _StubClient:
    def __init__(self, model: str, response=None, fail=False):
        self.model = model
        self._response = response
        self._fail = fail
        self.calls = 0

    def chat(self, messages, *, temperature=None, max_tokens=None, stop=None, timeout=None):
        self.calls += 1
        if self._fail:
            raise LLMError("boom")
        return self._response or LLMResponse(content="ok", model=self.model)


def test_cost_meter_aggregates_real_calls_only():
    from app.observability.cost import get_cost_meter

    meter = get_cost_meter()
    meter.reset()
    primary = _StubClient(
        "gemini-2.5-flash",
        LLMResponse(content="x", model="gemini-2.5-flash", prompt_tokens=1000, completion_tokens=200),
    )
    provider = LLMProvider(primary=primary, fallback=_StubClient("fb"), cache=_fresh_cache())
    msg = [ChatMessage(role=Role.USER, content="hi")]

    provider.chat(msg)
    stats = meter.stats()
    assert stats["calls"] == 1
    assert stats["total_prompt_tokens"] == 1000
    assert stats["total_completion_tokens"] == 200
    # 1000 * 0.30/1M + 200 * 2.50/1M = 0.0003 + 0.0005 = 0.0008
    assert stats["total_cost_usd"] == 0.0008

    # Identical query is a cache hit -> no API call -> no extra cost recorded.
    provider.chat(msg)
    assert primary.calls == 1
    assert meter.stats()["calls"] == 1
    meter.reset()


def test_provider_uses_primary_when_healthy():
    primary = _StubClient("qwen3", LLMResponse(content="primary", model="qwen3"))
    fallback = _StubClient("llama3.1")
    provider = LLMProvider(primary=primary, fallback=fallback, cache=_fresh_cache())
    resp = provider.chat([ChatMessage(role=Role.USER, content="hi")])
    assert resp.content == "primary"
    assert fallback.calls == 0


def test_provider_falls_back_on_primary_failure():
    primary = _StubClient("qwen3", fail=True)
    fallback = _StubClient("llama3.1", LLMResponse(content="fallback", model="llama3.1"))
    provider = LLMProvider(primary=primary, fallback=fallback, cache=_fresh_cache())
    resp = provider.chat([ChatMessage(role=Role.USER, content="hi")])
    assert resp.content == "fallback"
    assert fallback.calls == 1


def test_ollama_client_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "Hello there"},
                "prompt_eval_count": 12,
                "eval_count": 5,
                "done_reason": "stop",
            },
        )

    transport = httpx.MockTransport(handler)
    client = OllamaClient("qwen3")

    # Patch httpx.Client to use the mock transport.
    import app.llm.ollama_client as mod

    original = httpx.Client
    httpx.Client = lambda *a, **k: original(transport=transport)  # type: ignore
    try:
        resp = client.chat([ChatMessage(role=Role.USER, content="hi")])
    finally:
        httpx.Client = original

    assert resp.content == "Hello there"
    assert resp.prompt_tokens == 12
    assert resp.completion_tokens == 5
    assert resp.total_tokens == 17


def test_gemini_message_mapping():
    system, contents = _to_gemini_contents(
        [
            ChatMessage(role=Role.SYSTEM, content="be precise"),
            ChatMessage(role=Role.USER, content="hi"),
            ChatMessage(role=Role.ASSISTANT, content="hello"),
        ]
    )
    assert system == {"parts": [{"text": "be precise"}]}
    assert contents == [
        {"role": "user", "parts": [{"text": "hi"}]},
        {"role": "model", "parts": [{"text": "hello"}]},
    ]


def test_gemini_client_parses_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("key") == "test-key"
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {"role": "model", "parts": [{"text": "Grounded answer"}]},
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 8, "candidatesTokenCount": 3},
            },
        )

    transport = httpx.MockTransport(handler)
    client = GeminiClient("gemini-2.5-flash", api_key="test-key")

    original = httpx.Client
    httpx.Client = lambda *a, **k: original(transport=transport)  # type: ignore
    try:
        resp = client.chat([ChatMessage(role=Role.USER, content="hi")])
    finally:
        httpx.Client = original

    assert resp.content == "Grounded answer"
    assert resp.prompt_tokens == 8
    assert resp.completion_tokens == 3
    assert resp.finish_reason == "STOP"


def test_gemini_client_requires_api_key():
    client = GeminiClient("gemini-2.5-flash", api_key="")
    try:
        client.chat([ChatMessage(role=Role.USER, content="hi")])
        assert False, "expected LLMError when API key missing"
    except LLMError:
        pass
