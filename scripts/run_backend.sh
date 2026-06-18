#!/usr/bin/env bash
# Start the FastAPI backend with hot reload (local development).
set -euo pipefail

cd "$(dirname "$0")/../backend"

export PYTHONPATH="${PYTHONPATH:-.}"
exec uvicorn app.main:app --reload --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
