"""
LLM provider with primary/fallback routing.

`LLMProvider` wraps a primary model and a fallback. On a primary failure (server
down, timeout, error) it transparently retries the same request against the
fallback model. The concrete clients (Ollama for local dev, Gemini for
production) are built by `app.llm.factory` from `LLM_PROVIDER`, so agents depend
only on `LLMProvider.chat` and the routing/fallback policy — together with the
provider choice — lives in exactly one place.
"""

from __future__ import annotations

from typing import List, Optional

from app.cache.semantic_cache import SemanticCache, get_semantic_cache, normalize_key
from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMResponse
from app.llm.factory import active_provider, create_client

logger = get_logger(__name__)


class LLMProvider:
    """Route chat requests to primary, falling back on failure."""

    def __init__(
        self,
        primary: Optional[LLMClient] = None,
        fallback: Optional[LLMClient] = None,
        cache: Optional[SemanticCache] = None,
    ) -> None:
        self._primary = primary or create_client("primary")
        self._fallback = fallback or create_client("fallback")
        self._cache = cache or get_semantic_cache()
        logger.info(
            "[LLM] provider=%s wired (primary=%s, fallback=%s)",
            active_provider(),
            self._primary.model,
            self._fallback.model,
        )

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
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        # LLM-output cache: keyed on model + full conversation.
        serialized = "\n".join(f"{m.role.value}:{m.content}" for m in messages)
        cache_key = normalize_key("llm", self._primary.model, serialized)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.info("[LLM] cache hit for model=%s — no Ollama call made", self._primary.model)
            return cached

        try:
            logger.info("[LLM] invoking PRIMARY model=%s", self._primary.model)
            response = self._primary.chat(
                messages, temperature=temperature, max_tokens=max_tokens, stop=stop, timeout=timeout
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
            logger.info(
                "[LLM] invoking FALLBACK model=%s (primary=%s unavailable)",
                self._fallback.model,
                self._primary.model,
            )
            response = self._fallback.chat(
                messages, temperature=temperature, max_tokens=max_tokens, stop=stop, timeout=timeout
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
