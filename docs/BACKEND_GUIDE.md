# Backend Guide

The backend is a FastAPI application under `backend/app`. This guide maps every
module and explains the request flow. For a runnable quick-start see
[backend/README.md](../backend/README.md).

## Module map

| Module | Responsibility |
|---|---|
| `core/config.py` | Pydantic-Settings — all configuration, nested per subsystem |
| `core/logging.py` | Structured logging + per-request correlation id |
| `core/exceptions.py` | Exception hierarchy + handlers → uniform error envelope |
| `auth/supabase.py` | JWT verification (HS256 / RS256), builds `Principal` |
| `middleware/request_context.py` | `X-Request-ID` + access logging |
| `middleware/tenant.py` | Tenant resolution from header/JWT |
| `services/rate_limiter.py` | Token-bucket limiter (memory; Redis-ready Protocol) |
| `services/chat_service.py` | Runs the workflow, caches + traces the turn |
| `services/document_registry.py` | In-memory catalog for the Document Explorer |
| `api/deps.py` | DI providers: principal, tenant, rate-limit guard |
| `api/v1/routes/*` | health, ping, auth, documents, chat, observability, evaluation |
| `llm/*` | LLM abstraction (Ollama client, primary/fallback provider) |
| `ingestion/*` | loaders, legal chunking, ingestion pipeline |
| `retrieval/*` | embeddings, vector store, BM25, RRF, compression, reranker, pipeline |
| `safety/*` | PII, input safety, output safety |
| `agents/*` | the 8 agents + state + LangGraph workflow |
| `observability/*` | tracing + span recorder |
| `cache/*` | semantic cache |

## Configuration

All settings live in `core/config.py` and are documented in `.env.example`.
Settings are grouped into nested models (`supabase`, `rate_limit`, `ollama`,
`chroma`, `embedding`, `retrieval`, `safety`, `observability`). Access them via:

```python
from app.core.config import get_settings
settings = get_settings()           # cached for the process
settings.retrieval.final_top_k
```

### Backend selectors (light ↔ production)

| Setting | Light | Production |
|---|---|---|
| `EMBEDDING_BACKEND` | `hashing` | `bge` |
| `RETRIEVAL_VECTOR_STORE` | `memory` | `chroma` |
| `RETRIEVAL_RERANKER_BACKEND` | `lexical` | `bge` |
| `SAFETY_PII_BACKEND` | `regex` | `presidio` |
| `SAFETY_INPUT_GUARD_BACKEND` | `heuristic` | `llama_guard` |
| `OBSERVABILITY_CACHE_BACKEND` | `memory` | `gptcache` |
| `AGENT_ORCHESTRATOR` | `langgraph` | `langgraph` (`sequential` to drop dep) |

## API surface

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/v1/health`, `/ready` | – | probes |
| GET | `/api/v1/ping` | – | connectivity test route |
| GET | `/api/v1/auth/whoami` | ✅ | verified principal |
| POST | `/api/v1/documents/upload` | ✅ | ingest a document |
| GET | `/api/v1/documents` | ✅ | list tenant documents |
| POST | `/api/v1/chat` | ✅ | grounded legal answer |
| GET | `/api/v1/observability/metrics` | ✅ | cache + trace summary |
| GET | `/api/v1/observability/traces` | ✅ | recent spans |
| GET | `/api/v1/evaluation/results` | ✅ | latest evaluation report |

## Error envelope

Every error returns:

```json
{ "error": { "code": "rate_limit_exceeded", "message": "...", "request_id": "..." } }
```

Raise `AppError` subclasses (`AuthenticationError`, `TenantError`,
`RateLimitError`, `ValidationAppError`, `NotFoundError`) from domain code; the
handlers in `core/exceptions.py` translate them.

## Dependency injection

Routes declare dependencies in order:

```python
@router.post("", dependencies=[Depends(enforce_rate_limit)])
async def chat(payload: ChatRequest, tenant_id: str = Depends(get_current_tenant)):
    ...
```

`enforce_rate_limit` depends on `get_current_principal` + `get_current_tenant`,
so auth, tenant reconciliation, and limits all resolve before the handler runs.

## Running & testing

```bash
cd backend
uvicorn app.main:app --reload
pytest                      # 57 tests, fully offline
```
