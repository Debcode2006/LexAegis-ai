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

    # --- CORS ----------------------------------------------------------------
    # A browser SPA on another origin (e.g. Vercel) cannot call the API unless its
    # origin is allow-listed. When that origin is missing, the browser's preflight
    # OPTIONS gets a 400 ("Disallowed CORS origin") BEFORE auth — looking like the
    # backend "broke" even though the request never reached a route.
    non_local_origins = [
        o for o in settings.cors_origins if "localhost" not in o and "127.0.0.1" not in o
    ]
    if settings.is_production and not non_local_origins and not settings.cors_origin_regex:
        warnings.append(
            "CORS allowlist has no non-local origin in production "
            f"(CORS_ORIGINS={list(settings.cors_origins)}). The deployed frontend's "
            "cross-origin requests will fail preflight with HTTP 400 before reaching "
            "any route.\n"
            "  Fix: set CORS_ORIGINS to your exact frontend origin, no trailing slash "
            "(e.g. https://your-app.vercel.app), and/or CORS_ORIGIN_REGEX for preview "
            "deploys (e.g. https://your-app-.*\\.vercel\\.app)."
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

    # --- LLM provider --------------------------------------------------------
    llm_enabled = (
        settings.use_llm_for_understanding
        or settings.use_llm_for_reasoning
        or settings.enable_llamaguard
    )
    provider = (settings.llm_provider or "ollama").strip().lower()
    if provider not in ("ollama", "gemini"):
        warnings.append(
            f"LLM_PROVIDER={settings.llm_provider!r} is not recognized. Valid values: "
            "ollama (local dev) | gemini (production). Defaulting to 'ollama'."
        )
    if llm_enabled and provider == "ollama" and not settings.ollama.base_url:
        warnings.append(
            "LLM stages are enabled but OLLAMA_BASE_URL is empty. The agents will "
            "fall back to deterministic heuristics.\n"
            "  Fix: set OLLAMA_BASE_URL (default http://localhost:11434) and run "
            "Ollama, or set USE_LLM_FOR_*=false."
        )
    if llm_enabled and provider == "gemini" and not settings.gemini.api_key.get_secret_value():
        warnings.append(
            "LLM_PROVIDER=gemini but GEMINI_API_KEY is empty. All LLM stages will "
            "fail and fall back to deterministic heuristics.\n"
            "  Fix: set GEMINI_API_KEY (get one at https://aistudio.google.com/apikey)."
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


def _model_installed(name: str, installed: List[str]) -> bool:
    """True if `name` matches an installed Ollama model, tolerating tags.

    Ollama lists models with a tag (e.g. "qwen3:latest"); a config value of
    "qwen3" should match "qwen3:latest". An explicit tag matches exactly.
    """

    return any(m == name or m.split(":", 1)[0] == name.split(":", 1)[0] for m in installed)


def run_llm_health_check() -> dict:
    """Probe the active LLM backend at startup: reachability + required models.

    Dispatches on `LLM_PROVIDER` (ollama | gemini). Sets the process-wide LLM
    availability flag so the chat path auto-disables LLM stages (no per-request
    timeout waits) when the backend is down. Never raises.
    """

    settings = get_settings()
    from app.llm.factory import active_provider
    from app.llm.runtime import set_llm_available

    want_llm = (
        settings.use_llm_for_understanding
        or settings.use_llm_for_reasoning
        or settings.enable_llamaguard
    )
    if not want_llm:
        set_llm_available(False)
        logger.info("[LLM HEALTH] All LLM stages disabled by config — skipping LLM probe.")
        return {"checked": False}

    provider = active_provider()
    if provider == "gemini":
        return _check_gemini(settings)
    return _check_ollama(settings)


def _check_ollama(settings) -> dict:
    """Probe Ollama: reachability + required models installed."""

    from app.llm.ollama_client import OllamaClient
    from app.llm.runtime import set_llm_available

    client = OllamaClient(settings.ollama.primary_model)
    reachable = client.health()
    set_llm_available(reachable)

    if not reachable:
        logger.warning(
            "[LLM HEALTH] Ollama UNREACHABLE at %s — LLM stages auto-disabled; "
            "chat will use heuristic understanding + extractive reasoning. "
            "Fix: start Ollama (`ollama serve`).",
            settings.ollama.base_url,
        )
        return {"provider": "ollama", "checked": True, "reachable": False}

    installed = client.list_models()
    reasoning_model = settings.ollama.primary_model
    guard_model = settings.safety.llama_guard_model
    reasoning_ok = _model_installed(reasoning_model, installed)
    guard_ok = _model_installed(guard_model, installed)

    logger.info(
        "[LLM HEALTH] Ollama reachable at %s | reasoning=%s installed=%s | "
        "llama_guard=%s installed=%s (ENABLE_LLAMAGUARD=%s) | timeouts: default=%ds reasoning=%ds",
        settings.ollama.base_url,
        reasoning_model,
        reasoning_ok,
        guard_model,
        guard_ok,
        settings.enable_llamaguard,
        settings.ollama.request_timeout_seconds,
        settings.ollama.reasoning_timeout_seconds,
    )
    if settings.use_llm_for_reasoning and not reasoning_ok:
        logger.warning(
            "[LLM HEALTH] Reasoning model '%s' is NOT installed. Fix: `ollama pull %s`.",
            reasoning_model,
            reasoning_model,
        )
    if settings.enable_llamaguard and not guard_ok:
        logger.warning(
            "[LLM HEALTH] LlamaGuard model '%s' is NOT installed. Fix: `ollama pull %s` "
            "(or set ENABLE_LLAMAGUARD=false).",
            guard_model,
            guard_model,
        )
    return {
        "provider": "ollama",
        "checked": True,
        "reachable": True,
        "reasoning_model_installed": reasoning_ok,
        "llama_guard_installed": guard_ok,
    }


def _check_gemini(settings) -> dict:
    """Probe Gemini: API key present + endpoint reachable + model available."""

    from app.llm.gemini_client import GeminiClient
    from app.llm.runtime import set_llm_available

    cfg = settings.gemini
    if not cfg.api_key.get_secret_value():
        set_llm_available(False)
        logger.warning(
            "[LLM HEALTH] LLM_PROVIDER=gemini but GEMINI_API_KEY is empty — LLM stages "
            "auto-disabled; chat will use heuristic understanding + extractive reasoning. "
            "Fix: set GEMINI_API_KEY."
        )
        return {"provider": "gemini", "checked": True, "reachable": False}

    client = GeminiClient(cfg.primary_model)
    reachable = client.health()
    set_llm_available(reachable)

    if not reachable:
        logger.warning(
            "[LLM HEALTH] Gemini API UNREACHABLE at %s (check GEMINI_API_KEY / network) — "
            "LLM stages auto-disabled; chat will use heuristic + extractive reasoning.",
            cfg.base_url,
        )
        return {"provider": "gemini", "checked": True, "reachable": False}

    installed = client.list_models()
    model_ok = any(m == cfg.primary_model or m.startswith(cfg.primary_model) for m in installed)
    logger.info(
        "[LLM HEALTH] Gemini reachable at %s | model=%s available=%s (ENABLE_LLAMAGUARD=%s) | "
        "timeouts: default=%ds reasoning=%ds",
        cfg.base_url,
        cfg.primary_model,
        model_ok,
        settings.enable_llamaguard,
        cfg.request_timeout_seconds,
        cfg.reasoning_timeout_seconds,
    )
    if not model_ok and installed:
        logger.warning(
            "[LLM HEALTH] Gemini model '%s' was not in the available-models list. "
            "Double-check GEMINI_MODEL (e.g. gemini-2.5-flash, gemini-2.5-pro).",
            cfg.primary_model,
        )
    return {
        "provider": "gemini",
        "checked": True,
        "reachable": True,
        "reasoning_model_installed": model_ok,
    }


def run_startup_checks() -> List[str]:
    """Log the configuration summary + any startup warnings. Returns warnings."""

    status = config_status()
    # Required, non-secret startup diagnostics.
    logger.info("JWT Secret Loaded: %s", status["jwt_secret_loaded"])
    logger.info("JWKS Configured: %s", status["jwks_configured"])
    logger.info("CORS Allowed Origins: %s", status["cors_origins"])
    logger.info("CORS Origin Regex: %s", status["cors_origin_regex"] or "<none>")
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
