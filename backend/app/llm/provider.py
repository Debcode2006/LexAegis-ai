"""
LLM provider with primary/fallback routing.

`LLMProvider` wraps a primary model (Qwen3) and a fallback (Llama 3.1). On a
primary failure (server down, timeout, error) it transparently retries the same
request against the fallback model. Agents depend only on `LLMProvider.chat`,
so the routing/fallback policy lives in exactly one place.
"""

from __future__ import annotations

from typing import List, Optional

from app.cache.semantic_cache import SemanticCache, get_semantic_cache, normalize_key
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMResponse
from app.llm.ollama_client import OllamaClient

logger = get_logger(__name__)


class LLMProvider:
    """Route chat requests to primary, falling back on failure."""

    def __init__(
        self,
        primary: Optional[LLMClient] = None,
        fallback: Optional[LLMClient] = None,
        cache: Optional[SemanticCache] = None,
    ) -> None:
        settings = get_settings().ollama
        self._primary = primary or OllamaClient(settings.primary_model)
        self._fallback = fallback or OllamaClient(settings.fallback_model)
        self._cache = cache or get_semantic_cache()

    @property
    def primary_model(self) -> str:
        return self._primary.model

    @property
    def fallback_model(self) -> str:
        return self._fallback.model

    def chat(
        self,
        messages: List[ChatMessage],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> LLMResponse:
        # LLM-output cache: keyed on model + full conversation.
        serialized = "\n".join(f"{m.role.value}:{m.content}" for m in messages)
        cache_key = normalize_key("llm", self._primary.model, serialized)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            response = self._primary.chat(
                messages, temperature=temperature, max_tokens=max_tokens, stop=stop
            )
            self._cache.set(cache_key, response)
            return response
        except LLMError as exc:
            logger.warning(
                "Primary model '%s' failed; falling back to '%s': %s",
                self._primary.model,
                self._fallback.model,
                exc,
            )
            response = self._fallback.chat(
                messages, temperature=temperature, max_tokens=max_tokens, stop=stop
            )
            self._cache.set(cache_key, response)
            return response


_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    """Return the process-wide LLM provider."""

    global _provider
    if _provider is None:
        _provider = LLMProvider()
    return _provider
