# ============================================================================
# LexAegis AI — Backend image (FastAPI + Uvicorn)
#
# Multi-stage build:
#   builder  -> install Python deps into a venv (keeps the final image clean)
#   runtime  -> copy the venv + app, run as a non-root user
#
# Works for BOTH modes:
#   - local dev  (LLM_PROVIDER=ollama, backend reaches host Ollama)
#   - production (LLM_PROVIDER=gemini, no Ollama needed)
# The image is provider-agnostic; behaviour is chosen entirely by env vars.
# ============================================================================

# --- Stage 1: builder -------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Longer timeout + retries so a flaky connection doesn't abort the (large)
    # torch download with IncompleteRead/ProtocolError.
    PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5

# Build tools needed by some wheels (e.g. tokenizers / FlagEmbedding).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Isolated virtualenv so we can copy a self-contained tree into the runtime.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY requirements.txt ./
# IMPORTANT: install CPU-only PyTorch FIRST, from the dedicated CPU wheel index.
# sentence-transformers + FlagEmbedding depend on torch; the DEFAULT Linux torch
# wheel bundles CUDA and drags in multi-GB nvidia_*_cu13 packages we never use
# (everything runs on CPU — EMBEDDING_DEVICE=cpu). Installing the CPU build up
# front means the later `-r requirements.txt` sees torch already satisfied and
# never pulls the CUDA stack. Saves ~3-4 GB and most of the build time.
RUN pip install --upgrade pip && \
    pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install -r requirements.txt

# --- Stage 2: runtime -------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# curl is used by the container HEALTHCHECK below.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 appuser

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . /app

# Persistent data (chroma PersistentClient fallback, gptcache) lives here; the
# compose file mounts a volume over it. Owned by the non-root runtime user.
RUN mkdir -p /app/.data && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Liveness/readiness for orchestrators (compose, Railway). Hits the FastAPI
# health route through the same port the app serves on.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# Invoked via `sh` so the script runs regardless of the file's exec bit (the
# build context may come from a Windows checkout that doesn't preserve +x).
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
