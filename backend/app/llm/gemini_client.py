"""
Gemini chat client.

Talks to Google's Generative Language REST API (`:generateContent`) over HTTP.
Kept dependency-light (httpx only, exactly like `OllamaClient`) so the production
provider adds no heavy SDK and behaves identically from the call site's point of
view — it implements the same `LLMClient` contract and returns the same
normalized `LLMResponse`.

Used when `LLM_PROVIDER=gemini`. Supports Gemini 2.5 Flash (default) and
Gemini 2.5 Pro (set `GEMINI_MODEL`).
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMResponse, Role

logger = get_logger(__name__)


def _to_gemini_contents(messages: List[ChatMessage]) -> tuple[Optional[Dict], List[Dict]]:
    """Split chat messages into (systemInstruction, contents).

    Gemini carries the system prompt in a dedicated `systemInstruction` field and
    uses role "model" (not "assistant") for prior model turns. We merge all
    system messages into one instruction and map the rest into `contents`.
    """

    system_parts: List[str] = []
    contents: List[Dict] = []
    for m in messages:
        if m.role == Role.SYSTEM:
            system_parts.append(m.content)
            continue
        role = "model" if m.role == Role.ASSISTANT else "user"
        contents.append({"role": role, "parts": [{"text": m.content}]})

    system_instruction = (
        {"parts": [{"text": "\n\n".join(system_parts)}]} if system_parts else None
    )
    return system_instruction, contents


class GeminiClient(LLMClient):
    """Synchronous Gemini chat client for a single model (REST, httpx-only)."""

    def __init__(
        self,
        model: str,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        settings = get_settings().gemini
        self.model = model
        self._api_key = api_key if api_key is not None else settings.api_key.get_secret_value()
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
        timeout: Optional[float] = None,
    ) -> LLMResponse:
        if not self._api_key:
            raise LLMError("GEMINI_API_KEY is not set; cannot call the Gemini API.")

        system_instruction, contents = _to_gemini_contents(messages)
        generation_config: Dict = {
            "temperature": self._default_temperature if temperature is None else temperature,
            "maxOutputTokens": max_tokens or self._default_max_tokens,
        }
        if stop:
            generation_config["stopSequences"] = stop

        payload: Dict = {"contents": contents, "generationConfig": generation_config}
        if system_instruction:
            payload["systemInstruction"] = system_instruction

        url = f"{self._base_url}/models/{self.model}:generateContent"
        effective_timeout = timeout or self._timeout
        start = time.perf_counter()
        try:
            with httpx.Client(timeout=effective_timeout) as client:
                resp = client.post(
                    url,
                    params={"key": self._api_key},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Gemini request failed for model=%s: %s", self.model, exc)
            raise LLMError(f"Gemini request failed: {exc}") from exc

        latency_ms = (time.perf_counter() - start) * 1000.0
        candidates = data.get("candidates") or []
        content = ""
        finish_reason = None
        if candidates:
            first = candidates[0]
            finish_reason = first.get("finishReason")
            parts = (first.get("content") or {}).get("parts") or []
            content = "".join(p.get("text", "") for p in parts)

        usage = data.get("usageMetadata") or {}
        prompt_tokens = int(usage.get("promptTokenCount", 0) or 0)
        completion_tokens = int(usage.get("candidatesTokenCount", 0) or 0)
        # Definitive proof that Gemini actually served this request.
        logger.info(
            "[GEMINI] model=%s responded in %.0fms (prompt_tokens=%d, completion_tokens=%d)",
            self.model,
            latency_ms,
            prompt_tokens,
            completion_tokens,
        )
        return LLMResponse(
            content=content,
            model=self.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            finish_reason=finish_reason,
            raw=data,
        )

    def health(self) -> bool:
        """Return True if the Gemini API is reachable and the key is accepted."""

        if not self._api_key:
            return False
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self._base_url}/models", params={"key": self._api_key})
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def list_models(self) -> List[str]:
        """Return available Gemini model names (e.g. ``["gemini-2.5-flash"]``).

        Empty on any failure. Names are returned without the ``models/`` prefix
        so they compare directly against config values.
        """

        if not self._api_key:
            return []
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(f"{self._base_url}/models", params={"key": self._api_key})
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Could not list Gemini models: %s", exc)
            return []
        names = []
        for m in data.get("models") or []:
            name = m.get("name", "")
            names.append(name.split("/", 1)[1] if name.startswith("models/") else name)
        return [n for n in names if n]
