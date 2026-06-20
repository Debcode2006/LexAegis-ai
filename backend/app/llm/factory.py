"""
LLM client factory — the single place provider selection happens.

`LLM_PROVIDER` (ollama | gemini) decides which concrete `LLMClient` is built for
a given logical role. Every other module asks the factory for clients by role and
never imports a concrete client directly, so switching providers is a one-line
env change with no application code changes.

Roles:
- "primary"   — reasoning / understanding primary model
- "fallback"  — model retried when the primary fails
- "guard"     — input-safety classifier model
"""

from __future__ import annotations

from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import LLMClient

logger = get_logger(__name__)

OLLAMA = "ollama"
GEMINI = "gemini"


def active_provider() -> str:
    """Return the normalized active provider name (defaults to ollama)."""

    provider = (get_settings().llm_provider or OLLAMA).strip().lower()
    if provider not in (OLLAMA, GEMINI):
        logger.warning(
            "[LLM] Unknown LLM_PROVIDER=%r — falling back to '%s'. Valid values: ollama, gemini.",
            provider,
            OLLAMA,
        )
        return OLLAMA
    return provider


def model_for_role(role: str, provider: Optional[str] = None) -> str:
    """Return the configured model name for a logical role under a provider."""

    settings = get_settings()
    provider = provider or active_provider()
    if provider == GEMINI:
        cfg = settings.gemini
        if role == "fallback":
            return cfg.fallback_model
        if role == "guard":
            # Gemini has built-in safety; we reuse the primary model as a
            # prompt-based classifier when an explicit guard is requested.
            return cfg.primary_model
        return cfg.primary_model
    # Ollama
    if role == "fallback":
        return settings.ollama.fallback_model
    if role == "guard":
        return settings.safety.llama_guard_model
    return settings.ollama.primary_model


def create_client(
    role: str = "primary",
    *,
    model: Optional[str] = None,
    provider: Optional[str] = None,
) -> LLMClient:
    """Build an `LLMClient` for `role` (or an explicit `model`) on the active provider."""

    provider = provider or active_provider()
    resolved_model = model or model_for_role(role, provider)

    if provider == GEMINI:
        from app.llm.gemini_client import GeminiClient

        return GeminiClient(resolved_model)

    from app.llm.ollama_client import OllamaClient

    return OllamaClient(resolved_model)
