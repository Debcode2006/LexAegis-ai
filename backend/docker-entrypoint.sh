#!/usr/bin/env sh
# ============================================================================
# Backend container startup script.
#
# 1. Prints which LLM provider is active (sanity check in `docker logs`).
# 2. Launches Uvicorn. The app's lifespan runs run_startup_checks() +
#    run_llm_health_check(), which validate the selected provider (Ollama or
#    Gemini) and degrade gracefully if it is unreachable.
# ============================================================================
set -e

echo "=============================================================="
echo " LexAegis AI backend starting"
echo "   ENVIRONMENT   = ${ENVIRONMENT:-local}"
echo "   LLM_PROVIDER  = ${LLM_PROVIDER:-ollama}"
if [ "${LLM_PROVIDER:-ollama}" = "gemini" ]; then
  echo "   GEMINI_MODEL  = ${GEMINI_MODEL:-gemini-2.5-flash}"
else
  echo "   OLLAMA_BASE_URL = ${OLLAMA_BASE_URL:-http://localhost:11434}"
fi
echo "   PORT          = ${PORT:-8000}"
echo "=============================================================="

exec uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
