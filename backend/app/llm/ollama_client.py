"""
Ollama chat client.

Talks to a local Ollama server over its HTTP `/api/chat` endpoint. Kept
dependency-light (httpx only) so it works against any Ollama-served model
(Qwen3, Llama 3.1, LlamaGuard, ...).
"""

from __future__ import annotations

import time
from typing import List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMResponse

logger = get_logger(__name__)


class OllamaClient(LLMClient):
    """Synchronous Ollama chat client for a single model."""

    def __init__(
        self,
        model: str,
        *,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        settings = get_settings().ollama
        self.model = model
        self._base_url = (base_url or settings.base_url).rstrip("/")
        self._timeout = timeout or settings.request_timeout_seconds
        self._default_temperature = settings.temperature
        self._default_max_tokens = settings.max_tokens

    def chat(
        self,
        messages: List[ChatMessage],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": False,
            "options": {
                "temperature": self._default_temperature if temperature is None else temperature,
                "num_predict": max_tokens or self._default_max_tokens,
            },
        }
        if stop:
            payload["options"]["stop"] = stop

        start = time.perf_counter()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Ollama request failed for model=%s: %s", self.model, exc)
            raise LLMError(f"Ollama request failed: {exc}") from exc

        latency_ms = (time.perf_counter() - start) * 1000.0
        content = (data.get("message") or {}).get("content", "")
        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(data.get("eval_count", 0) or 0),
            latency_ms=latency_ms,
            finish_reason=data.get("done_reason"),
            raw=data,
        )

    def health(self) -> bool:
        """Return True if the Ollama server is reachable."""

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except httpx.HTTPError:
            return False
