"""
Input safety guarding.

Screens inbound queries for prompt injection, jailbreak attempts, and unsafe
requests before they reach retrieval or the reasoning LLM.

- `LlamaGuardGuard` — production: LlamaGuard served via Ollama. The model
  returns "safe" or "unsafe\\n<categories>"; we parse that into a verdict.
- `HeuristicGuard`  — light/test fallback: curated regexes for the most common
  injection/jailbreak patterns. No model required.

Selected via `SAFETY_INPUT_GUARD_BACKEND` (llama_guard | heuristic).
"""

from __future__ import annotations

import re
from typing import List, Optional, Protocol

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMError, Role
from app.llm.provider import LLMProvider, get_llm_provider
from app.safety.models import SafetyVerdict

logger = get_logger(__name__)

# Patterns indicative of prompt injection / jailbreak / clearly unsafe intent.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(the\s+)?(system|previous)\s+prompt", re.I),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(developer|dan|jailbreak)\s*mode", re.I),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|instructions|hidden)", re.I),
    re.compile(r"\bpretend\s+you\s+have\s+no\s+(rules|restrictions|guidelines)\b", re.I),
    re.compile(r"\bbypass\s+(all\s+)?(safety|content)\s+(filters|policies)\b", re.I),
]
_UNSAFE_PATTERNS = [
    re.compile(r"\bhow\s+to\s+(make|build|synthesize)\s+(a\s+)?(bomb|explosive|weapon)\b", re.I),
    re.compile(r"\b(launder|laundering)\s+money\b", re.I),
]


class InputSafetyGuard(Protocol):
    def check(self, text: str) -> SafetyVerdict:
        ...


class HeuristicGuard(InputSafetyGuard):
    """Regex-based input guard for local/test mode."""

    def check(self, text: str) -> SafetyVerdict:
        categories: List[str] = []
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(text):
                categories.append("prompt_injection")
                break
        for pattern in _UNSAFE_PATTERNS:
            if pattern.search(text):
                categories.append("unsafe_request")
                break
        if categories:
            return SafetyVerdict(
                safe=False,
                categories=categories,
                reason="Matched input-safety heuristic pattern.",
            )
        return SafetyVerdict(safe=True)


_LLAMA_GUARD_PROMPT = (
    "You are a safety classifier. Classify the following user message as 'safe' "
    "or 'unsafe'. If unsafe, list the violated categories. Respond with the word "
    "'safe' or 'unsafe' on the first line.\n\nUser message:\n{message}"
)


class LlamaGuardGuard(InputSafetyGuard):
    """LlamaGuard-backed guard served via Ollama."""

    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        self._cfg = get_settings().safety
        # Use a dedicated client bound to the guard model.
        from app.llm.ollama_client import OllamaClient

        self._client = OllamaClient(self._cfg.llama_guard_model)
        self._fallback = HeuristicGuard()

    def check(self, text: str) -> SafetyVerdict:
        prompt = _LLAMA_GUARD_PROMPT.format(message=text)
        try:
            response = self._client.chat(
                [ChatMessage(role=Role.USER, content=prompt)],
                temperature=0.0,
                max_tokens=128,
            )
        except LLMError as exc:
            logger.warning("LlamaGuard unavailable, using heuristic guard: %s", exc)
            return self._fallback.check(text)

        content = response.content.strip().lower()
        first_line = content.splitlines()[0] if content else ""
        if first_line.startswith("unsafe"):
            categories = [
                line.strip() for line in content.splitlines()[1:] if line.strip()
            ] or ["unsafe_request"]
            return SafetyVerdict(
                safe=False, categories=categories, reason="LlamaGuard flagged content.", raw=content
            )
        return SafetyVerdict(safe=True, raw=content)


def build_input_guard() -> InputSafetyGuard:
    backend = get_settings().safety.input_guard_backend.lower()
    if backend == "heuristic":
        return HeuristicGuard()
    return LlamaGuardGuard()


_guard: Optional[InputSafetyGuard] = None


def get_input_guard() -> InputSafetyGuard:
    global _guard
    if _guard is None:
        _guard = build_input_guard()
    return _guard
