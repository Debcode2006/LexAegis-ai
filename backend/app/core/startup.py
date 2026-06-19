"""
Startup validation.

Surfaces missing/optional dependencies and unconfigured subsystems as clear,
actionable warnings at application startup — so operators never hit an obscure
`ModuleNotFoundError` or silent 401 deep inside a request.

Design rules:
- **Never raises.** A missing optional backend degrades the relevant feature; it
  must not prevent the process from booting. (Boot-blocking misconfiguration is
  reported as a warning, not an exception.)
- Dependency presence is checked with `importlib.util.find_spec`, which does not
  import the (often heavy) module — so checks stay fast and side-effect free.
- Each warning names the concrete remediation (e.g. the exact `pip install`).
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import List

from app.core.config import config_status, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _missing(module: str) -> bool:
    """True if an import of `module` would fail (not installed)."""

    try:
        return find_spec(module) is None
    except (ImportError, ValueError):  # pragma: no cover - malformed install
        return True


def collect_startup_warnings() -> List[str]:
    """Return a list of human-readable startup warnings (empty == all good)."""

    settings = get_settings()
    warnings: List[str] = []

    # --- JWT / Supabase auth -------------------------------------------------
    sup = settings.supabase
    if not sup.jwt_secret.get_secret_value() and not sup.jwks_url:
        warnings.append(
            "JWT auth is not configured: neither SUPABASE_JWT_SECRET (HS256) nor "
            "SUPABASE_JWKS_URL (RS256) is set. All authenticated endpoints will "
            "reject every request with 401.\n"
            "  Fix: set SUPABASE_JWT_SECRET in backend/.env (any non-empty value "
            "works for local dev)."
        )
    if not sup.url:
        warnings.append(
            "Supabase URL not configured (SUPABASE_URL empty). Token verification "
            "still works, but Supabase server-side calls will fail."
        )

    # --- Vector store / ChromaDB --------------------------------------------
    if settings.retrieval.vector_store == "chroma" and _missing("chromadb"):
        warnings.append(
            "ChromaDB unavailable but RETRIEVAL_VECTOR_STORE=chroma. Retrieval "
            "will fail at query time.\n"
            "  Fix: pip install chromadb   (or set RETRIEVAL_VECTOR_STORE=memory)."
        )

    # --- Embedding model -----------------------------------------------------
    if settings.embedding.backend == "bge" and _missing("sentence_transformers"):
        warnings.append(
            "Embedding backend is 'bge' but sentence-transformers is not "
            "installed. Dense embedding will fail.\n"
            "  Fix: pip install sentence-transformers   (or set "
            "EMBEDDING_BACKEND=hashing for a light local fallback)."
        )
    if settings.retrieval.reranker_backend == "bge" and _missing("FlagEmbedding"):
        warnings.append(
            "Reranker backend is 'bge' but FlagEmbedding is not installed. "
            "Reranking will fail.\n"
            "  Fix: pip install FlagEmbedding   (or set "
            "RETRIEVAL_RERANKER_BACKEND=lexical)."
        )

    # --- Ollama / LLM --------------------------------------------------------
    llm_enabled = settings.use_llm_for_understanding or settings.use_llm_for_reasoning
    if llm_enabled and not settings.ollama.base_url:
        warnings.append(
            "LLM stages are enabled but OLLAMA_BASE_URL is empty. The agents will "
            "fall back to deterministic heuristics.\n"
            "  Fix: set OLLAMA_BASE_URL (default http://localhost:11434) and run "
            "Ollama, or set USE_LLM_FOR_*=false."
        )

    # --- PII / Presidio ------------------------------------------------------
    if settings.safety.pii_backend == "presidio" and _missing("presidio_analyzer"):
        warnings.append(
            "PII backend is 'presidio' but presidio-analyzer is not installed. "
            "PII detection/masking will fail.\n"
            "  Fix: pip install presidio-analyzer presidio-anonymizer   (or set "
            "SAFETY_PII_BACKEND=regex)."
        )

    # --- Semantic cache ------------------------------------------------------
    if settings.observability.cache_backend == "gptcache" and _missing("gptcache"):
        warnings.append(
            "Cache backend is 'gptcache' but gptcache is not installed. Semantic "
            "caching will fail.\n"
            "  Fix: pip install gptcache   (or set OBSERVABILITY_CACHE_BACKEND=memory)."
        )

    # --- Tracing export (degrades gracefully, so this is informational) ------
    if settings.observability.enable_tracing and _missing("opentelemetry"):
        warnings.append(
            "Tracing is enabled but OpenTelemetry is not installed. Spans are still "
            "recorded in the in-process buffer, but nothing is exported to Phoenix.\n"
            "  Fix: pip install opentelemetry-sdk opentelemetry-exporter-otlp "
            "openinference-instrumentation."
        )

    return warnings


def run_startup_checks() -> List[str]:
    """Log the configuration summary + any startup warnings. Returns warnings."""

    status = config_status()
    # Required, non-secret startup diagnostics.
    logger.info("JWT Secret Loaded: %s", status["jwt_secret_loaded"])
    logger.info("JWKS Configured: %s", status["jwks_configured"])
    logger.info("Environment File Path: %s", status["env_file_path"])
    if not status["env_file_exists"]:
        logger.warning(
            "No .env file found at %s — using environment variables and defaults only.",
            status["env_file_path"],
        )

    warnings = collect_startup_warnings()
    for warning in warnings:
        logger.warning("[STARTUP] %s", warning)
    if not warnings:
        logger.info("Startup validation passed: all configured subsystems are available.")
    else:
        logger.warning("Startup validation found %d issue(s) - see warnings above.", len(warnings))
    return warnings
