"""
Process-wide LLM availability flag.

Set once by the startup health check and read by the workflow/guard builders so
that, when the active LLM backend (Ollama or Gemini) is unreachable, the chat
path skips LLM calls entirely (no per-request timeout waits) and degrades to
deterministic heuristics + extractive reasoning.

Optimistic default: until a health check runs, LLM is assumed available so we
never wrongly disable it (e.g. in tests where the lifespan does not run).
"""

from __future__ import annotations

from typing import Optional

_llm_available: Optional[bool] = None


def set_llm_available(value: bool) -> None:
    global _llm_available
    _llm_available = value


def llm_available() -> bool:
    return True if _llm_available is None else _llm_available
