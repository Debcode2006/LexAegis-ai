"""
Centralized application configuration.

All runtime configuration flows through `Settings`, a Pydantic-Settings model
that loads values from environment variables (and a local `.env` file during
development). Configuration is grouped into cohesive nested models so that each
subsystem (auth, rate limiting, retrieval, LLM, observability, ...) owns its own
namespace. Only the configuration relevant to Phase 1 is *consumed* yet, but the
full surface is declared so later phases require no breaking changes.

Design rules:
- Never read `os.environ` directly anywhere else in the codebase. Import
  `get_settings()` instead.
- `get_settings()` is cached (lru_cache) so the environment is parsed exactly
  once per process.
- Secrets use `SecretStr` to avoid accidental logging.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from typing_extensions import Annotated

# Comma-separated env lists: `NoDecode` disables pydantic-settings' default JSON
# decoding so our `mode="before"` validators receive the raw string and split it.
CsvList = Annotated[List[str], NoDecode]

# --- Deterministic .env resolution ------------------------------------------
# The .env file is resolved *relative to this module*, never relative to the
# current working directory. This guarantees identical behaviour whether the
# process is launched by uvicorn (from backend/), a script (from the repo root),
# pytest (from CI), or a container/Railway (from /app). config.py lives at
# backend/app/core/config.py, so parents[2] is the backend/ directory.
BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_DIR / ".env"


def _config(**overrides: object) -> SettingsConfigDict:
    """Shared settings config: every model (top-level *and* nested) loads from
    the same absolute `.env` path.

    Declaring `env_file` on the nested models too is essential: nested settings
    are built via `default_factory`, which constructs them independently — if
    they did not name `env_file` they would read only `os.environ` and silently
    miss `.env` values (e.g. SUPABASE_JWT_SECRET).
    """

    base: dict = dict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )
    base.update(overrides)
    return SettingsConfigDict(**base)  # type: ignore[arg-type]


class Environment(str, Enum):
    """Deployment environment selector."""

    LOCAL = "local"
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SupabaseSettings(BaseSettings):
    """Supabase Auth configuration.

    Two verification modes are supported:
    - HS256 with a shared `jwt_secret` (Supabase legacy/standard JWT secret).
    - RS256/JWKS with `jwks_url` for asymmetric verification.
    The auth layer auto-selects based on which value is present.
    """

    model_config = _config(env_prefix="SUPABASE_")

    url: str = Field(default="", description="Supabase project URL.")
    anon_key: SecretStr = Field(default=SecretStr(""), description="Public anon key.")
    service_role_key: SecretStr = Field(
        default=SecretStr(""), description="Service-role key (server-side only)."
    )
    jwt_secret: SecretStr = Field(
        default=SecretStr(""), description="JWT secret for HS256 verification."
    )
    jwks_url: str = Field(default="", description="JWKS endpoint for RS256 verification.")
    jwt_audience: str = Field(default="authenticated", description="Expected JWT `aud`.")
    jwt_issuer: str = Field(default="", description="Expected JWT `iss` (optional).")
    # ES256 included because Supabase's modern asymmetric "JWT signing keys"
    # issue ES256 (ECC P-256) access tokens by default. The auth layer scopes
    # this allowlist per verification mode (HS* vs JWKS) at decode time.
    jwt_algorithms: CsvList = Field(default_factory=lambda: ["HS256", "RS256", "ES256"])

    @field_validator("jwt_algorithms", mode="before")
    @classmethod
    def _split_algorithms(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class RateLimitSettings(BaseSettings):
    """Token-bucket rate limiting configuration.

    Limits are expressed as "requests per window_seconds". Per-user and
    per-tenant limits are enforced independently; a request must satisfy both.
    """

    model_config = _config(env_prefix="RATE_LIMIT_")

    enabled: bool = Field(default=True)
    backend: str = Field(default="memory", description="memory | redis")
    redis_url: str = Field(default="", description="Redis DSN when backend=redis.")

    # Per-user limits.
    user_requests: int = Field(default=120, ge=1)
    user_window_seconds: int = Field(default=60, ge=1)

    # Per-tenant limits (aggregate across all users of a tenant).
    tenant_requests: int = Field(default=1200, ge=1)
    tenant_window_seconds: int = Field(default=60, ge=1)

    # Burst allowance multiplier applied to the steady-state bucket capacity.
    burst_multiplier: float = Field(default=1.5, ge=1.0)


class OllamaSettings(BaseSettings):
    """LLM (Ollama) configuration — declared now, consumed in Phase 2."""

    model_config = _config(env_prefix="OLLAMA_")

    base_url: str = Field(default="http://localhost:11434")
    primary_model: str = Field(default="qwen3")
    fallback_model: str = Field(default="llama3.1")
    # Default per-call timeout (kept short so a hung/missing Ollama fails fast).
    request_timeout_seconds: int = Field(default=15, ge=1)
    # Reasoning generates long answers and may load the model into VRAM, so it
    # gets its own, more generous timeout (the default above stays short).
    reasoning_timeout_seconds: int = Field(default=90, ge=1)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1)


class GeminiSettings(BaseSettings):
    """Google Gemini configuration — used when LLM_PROVIDER=gemini.

    The Gemini client talks to the Generative Language REST API directly (httpx
    only), mirroring the OllamaClient so no heavy SDK is added. `primary_model`
    is used for reasoning/understanding; `fallback_model` is tried if the primary
    call fails (e.g. transient 5xx / quota). Set `api_key` via GEMINI_API_KEY.
    """

    model_config = _config(env_prefix="GEMINI_")

    api_key: SecretStr = Field(default=SecretStr(""), description="Google AI Studio API key.")
    base_url: str = Field(default="https://generativelanguage.googleapis.com/v1beta")
    # Gemini 2.5 Flash is the recommended production default (fast + cheap).
    # Gemini 2.5 Pro is available for higher-quality reasoning (set GEMINI_MODEL).
    # Accept both GEMINI_MODEL (the documented name) and GEMINI_PRIMARY_MODEL.
    primary_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("GEMINI_MODEL", "GEMINI_PRIMARY_MODEL"),
    )
    fallback_model: str = Field(default="gemini-2.5-flash")
    request_timeout_seconds: int = Field(default=30, ge=1)
    # Reasoning generates long answers, so it gets a more generous budget.
    reasoning_timeout_seconds: int = Field(default=90, ge=1)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1)


class ChromaSettings(BaseSettings):
    """Vector database (ChromaDB) configuration — consumed in Phase 2."""

    model_config = _config(env_prefix="CHROMA_")

    host: str = Field(default="localhost")
    port: int = Field(default=8001, ge=1, le=65535)
    collection: str = Field(default="lexaegis_documents")
    persist_directory: str = Field(default="./.data/chroma")
    use_http_client: bool = Field(default=False)


class EmbeddingSettings(BaseSettings):
    """Embedding + reranker model configuration — consumed in Phase 2."""

    model_config = _config(env_prefix="EMBEDDING_")

    # Defaults are sized for a memory-constrained host: bge-small loads in ~0.15GB
    # vs ~1.3GB for bge-large, so a small Railway instance is not OOM-killed on the
    # first upload. Override EMBEDDING_DENSE_MODEL / EMBEDDING_RERANKER_MODEL to
    # scale up quality when more RAM is available (see deployment/production.env.example).
    dense_model: str = Field(default="BAAI/bge-small-en-v1.5")
    reranker_model: str = Field(default="BAAI/bge-reranker-base")
    device: str = Field(default="cpu", description="cpu | cuda")
    batch_size: int = Field(default=16, ge=1)
    normalize: bool = Field(default=True)
    # backend: "bge" (sentence-transformers) | "hashing" (deterministic, light).
    backend: str = Field(default="bge")
    dimension: int = Field(default=1024, ge=8, description="Hashing-embedder dim.")
    # Prefix prepended to passages/queries per BGE retrieval recommendation.
    query_instruction: str = Field(
        default="Represent this sentence for searching relevant passages: "
    )


class RetrievalSettings(BaseSettings):
    """Hybrid retrieval tuning — consumed in Phase 2/3."""

    model_config = _config(env_prefix="RETRIEVAL_")

    dense_top_k: int = Field(default=20, ge=1)
    sparse_top_k: int = Field(default=20, ge=1)
    rrf_k: int = Field(default=60, ge=1)
    rerank_top_k: int = Field(default=8, ge=1)
    final_top_k: int = Field(default=5, ge=1)
    dedup_threshold: float = Field(default=0.95, ge=0.0, le=1.0)
    # Stores / rerankers can be swapped for light local backends.
    vector_store: str = Field(default="chroma", description="chroma | memory")
    # 'lexical' (no model, zero extra RAM) by default so a small instance never
    # OOMs. Set to 'bge' (loads EMBEDDING_RERANKER_MODEL, ~1.1-2.2GB) on a host
    # with ≥2GB for cross-encoder reranking quality.
    reranker_backend: str = Field(default="lexical", description="bge | lexical")
    enable_reranker: bool = Field(default=True)
    enable_compression: bool = Field(default=True)
    # Chunking controls.
    chunk_max_chars: int = Field(default=1200, ge=200)
    chunk_overlap_chars: int = Field(default=150, ge=0)


class SafetySettings(BaseSettings):
    """Safety subsystem configuration — consumed in Phase 2."""

    model_config = _config(env_prefix="SAFETY_")

    llama_guard_model: str = Field(default="llama-guard3")
    enable_input_safety: bool = Field(default=True)
    enable_output_safety: bool = Field(default=True)
    enable_pii_masking: bool = Field(default=True)
    presidio_language: str = Field(default="en")
    # spaCy model Presidio loads for NER. Pinned EXPLICITLY (rather than letting
    # Presidio default to en_core_web_lg) so the engine only ever loads a model
    # that was installed at image-build time — never triggering a runtime download.
    presidio_spacy_model: str = Field(default="en_core_web_sm")
    # Backend selectors: production defaults + light fallbacks for local/test.
    pii_backend: str = Field(default="presidio", description="presidio | regex")
    input_guard_backend: str = Field(default="llama_guard", description="llama_guard | heuristic")
    pii_score_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    # Output-safety thresholds.
    min_citation_coverage: float = Field(default=0.5, ge=0.0, le=1.0)
    block_on_pii_leak: bool = Field(default=True)
    pii_entities: CsvList = Field(
        default_factory=lambda: [
            "PERSON",
            "EMAIL_ADDRESS",
            "PHONE_NUMBER",
            "LOCATION",
            "IN_PAN",
            "IN_PASSPORT",
            "IN_AADHAAR",
            "ORGANIZATION",
        ]
    )

    @field_validator("pii_entities", mode="before")
    @classmethod
    def _split_entities(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class ObservabilitySettings(BaseSettings):
    """Phoenix + caching configuration — consumed in Phase 3/4."""

    model_config = _config(env_prefix="OBSERVABILITY_")

    phoenix_endpoint: str = Field(default="http://localhost:6006")
    # OTLP collector endpoint Phoenix listens on (gRPC default 4317).
    otlp_endpoint: str = Field(default="http://localhost:6006/v1/traces")
    enable_tracing: bool = Field(default=True)
    service_name: str = Field(default="lexaegis-ai")
    trace_buffer_size: int = Field(default=200, ge=1, description="In-proc recent-span buffer.")
    gptcache_dir: str = Field(default="./.data/gptcache")
    enable_semantic_cache: bool = Field(default=True)
    # backend: gptcache (production) | memory (light/local/test) | off
    cache_backend: str = Field(default="memory")
    cache_similarity_threshold: float = Field(default=0.92, ge=0.0, le=1.0)
    cache_max_entries: int = Field(default=1000, ge=1)


class Settings(BaseSettings):
    """Top-level application settings aggregating all subsystem configs."""

    model_config = _config()

    # --- Application metadata -------------------------------------------------
    app_name: str = Field(default="LexAegis AI")
    environment: Environment = Field(default=Environment.LOCAL)
    debug: bool = Field(default=True)
    api_v1_prefix: str = Field(default="/api/v1")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)

    # --- Logging --------------------------------------------------------------
    log_level: LogLevel = Field(default=LogLevel.INFO)
    log_json: bool = Field(default=True)

    # --- CORS -----------------------------------------------------------------
    # Exact-match allowlist. Browsers send `Origin: scheme://host[:port]` with NO
    # trailing slash, so configured values are normalized to match (a trailing
    # slash is the most common silent cause of preflight 400s).
    cors_origins: CsvList = Field(default_factory=lambda: ["http://localhost:3000"])
    # Optional regex for origins that are NOT fixed — e.g. Vercel preview deploys
    # get a unique host per build (https://<app>-<hash>-<scope>.vercel.app) that a
    # static list can't enumerate. Matched in addition to cors_origins.
    cors_origin_regex: str = Field(default="")

    # --- Multi-tenancy --------------------------------------------------------
    default_tenant_id: str = Field(default="public")
    tenant_header: str = Field(default="X-Tenant-ID")
    enforce_tenant_isolation: bool = Field(default=True)

    # --- Nested subsystem settings -------------------------------------------
    # --- Evaluation -----------------------------------------------------------
    evaluation_dataset_path: str = Field(default="../evaluation/datasets/legal_benchmark.json")
    evaluation_results_path: str = Field(default="../evaluation/results/latest.json")

    # --- Agent orchestration --------------------------------------------------
    # orchestrator: "langgraph" (production) | "sequential" (no LangGraph dep).
    agent_orchestrator: str = Field(default="langgraph")
    # Inference backend selector. "ollama" (local dev) | "gemini" (production).
    # Switching this is the ONLY change needed to move between local Ollama and
    # the hosted Gemini API — no application code changes.
    llm_provider: str = Field(default="ollama")
    # Query understanding defaults to the deterministic heuristic: its output
    # (intent/entities) is advisory only and does not change retrieval or the
    # answer, so the LLM call is pure latency. Reasoning stays LLM-backed.
    use_llm_for_understanding: bool = Field(default=False)
    use_llm_for_reasoning: bool = Field(default=True)
    # Master switch for LlamaGuard input safety. When false, the fast regex
    # heuristic guard is used instead (no ~20s/request Ollama call).
    enable_llamaguard: bool = Field(default=True)

    supabase: SupabaseSettings = Field(default_factory=SupabaseSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    gemini: GeminiSettings = Field(default_factory=GeminiSettings)
    chroma: ChromaSettings = Field(default_factory=ChromaSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    safety: SafetySettings = Field(default_factory=SafetySettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            value = [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            # Drop trailing slashes so "https://app.vercel.app/" matches the
            # browser's "Origin: https://app.vercel.app". "*" is left untouched.
            return [o.rstrip("/") if o != "*" else o for o in value]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide cached Settings instance."""

    return Settings()


def config_status() -> dict:
    """Non-secret summary of how configuration resolved, for startup logging.

    Never returns secret *values* — only booleans indicating presence and the
    resolved `.env` path. Safe to log.
    """

    settings = get_settings()
    sup = settings.supabase
    return {
        "jwt_secret_loaded": bool(sup.jwt_secret.get_secret_value()),
        "jwks_configured": bool(sup.jwks_url),
        "env_file_path": str(ENV_FILE),
        "env_file_exists": ENV_FILE.is_file(),
        "cors_origins": list(settings.cors_origins),
        "cors_origin_regex": settings.cors_origin_regex or "",
    }
