"""LLM abstraction tests: Ollama client parsing and provider fallback."""

from __future__ import annotations

import httpx

from app.llm.base import ChatMessage, LLMError, LLMResponse, Role
from app.llm.ollama_client import OllamaClient
from app.llm.provider import LLMProvider


class _StubClient:
    def __init__(self, model: str, response=None, fail=False):
        self.model = model
        self._response = response
        self._fail = fail
        self.calls = 0

    def chat(self, messages, *, temperature=None, max_tokens=None, stop=None):
        self.calls += 1
        if self._fail:
            raise LLMError("boom")
        return self._response or LLMResponse(content="ok", model=self.model)


def test_provider_uses_primary_when_healthy():
    primary = _StubClient("qwen3", LLMResponse(content="primary", model="qwen3"))
    fallback = _StubClient("llama3.1")
    provider = LLMProvider(primary=primary, fallback=fallback)
    resp = provider.chat([ChatMessage(role=Role.USER, content="hi")])
    assert resp.content == "primary"
    assert fallback.calls == 0


def test_provider_falls_back_on_primary_failure():
    primary = _StubClient("qwen3", fail=True)
    fallback = _StubClient("llama3.1", LLMResponse(content="fallback", model="llama3.1"))
    provider = LLMProvider(primary=primary, fallback=fallback)
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
