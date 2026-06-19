# Developer Handbook

Everything you need to get productive.

## Prerequisites
- Python 3.10+ (developed on 3.12)
- Node.js 18+ (for the frontend)
- (Optional, production) Ollama, ChromaDB, Phoenix

## First-time setup

```bash
# Backend
python -m venv .venv
# Windows:  .venv\Scripts\activate    |  *nix: source .venv/bin/activate
pip install -r backend/requirements-phase1.txt
pip install numpy rank-bm25 langgraph langchain-core pytest pytest-asyncio
cp .env.example backend/.env

# Frontend
cd frontend && cp .env.local.example .env.local && npm install && cd ..
```

## Day-to-day commands

```bash
# Run the API (from backend/)
uvicorn app.main:app --reload

# Run tests (from backend/)
pytest                       # 57 tests, offline

# Run evaluation (from repo root)
python evaluation/evaluate_local.py

# Run the frontend (from frontend/)
npm run dev
```

Helper scripts: `scripts/run_backend.sh` / `scripts/run_backend.ps1`.

## Project conventions

- **Config**: never read `os.environ` directly; use `get_settings()`.
- **Errors**: raise `AppError` subclasses; the handlers produce the uniform
  envelope. Don't return ad-hoc error dicts.
- **Logging**: `get_logger(__name__)`; structured extras via `extra={"ctx_*": ...}`.
- **Heavy deps behind Protocols**: add a production impl + a light fallback, and
  select via config. Keep modules importable without the heavy dependency
  (import lazily inside methods).
- **Singletons**: stateful collaborators expose `get_*()` accessors and a
  `reset()` for tests.
- **Tenant isolation**: any new data path must filter by `tenant_id`.

## Adding a feature

### A new API route
1. Create `app/api/v1/routes/<name>.py` with an `APIRouter`.
2. Add auth/rate-limit dependencies as needed.
3. Register it in `app/api/router.py`.
4. Add tests in `backend/tests/`.

### A new agent
See [AGENT_WORKFLOW](AGENT_WORKFLOW.md) → "Extending".

### A new retrieval backend
Implement the relevant Protocol in `app/retrieval/*`, add a `build_*` factory
branch, and a config selector. See [RETRIEVAL_PIPELINE](RETRIEVAL_PIPELINE.md).

## Testing strategy
- **Unit**: config, chunking, fusion, compression, PII, agents, LLM provider.
- **Integration**: retrieval pipeline, full agent workflow (both orchestrators).
- **Endpoint**: health/ping, auth+tenant, rate limit, upload/list, chat,
  observability, evaluation.

Tests run on light backends and mint local HS256 tokens — no external services.

## Troubleshooting
- `ModuleNotFoundError: app` — run pytest/uvicorn from `backend/` (or set
  `PYTHONPATH=backend`).
- CSV env list parse error — list fields use `NoDecode`; pass comma-separated
  values, not JSON.
- LangGraph not installed — the workflow falls back to the sequential
  orchestrator automatically.
- Evaluation report not showing — run `python evaluation/evaluate_local.py`; the
  backend resolves `EVALUATION_RESULTS_PATH` relative to its cwd (`backend/`).

## Directory reference
See [ARCHITECTURE](ARCHITECTURE.md) and [BACKEND_GUIDE](BACKEND_GUIDE.md).
