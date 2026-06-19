# ⚖️ LexAegis AI

**A Production-Grade Agentic Legal Intelligence Platform.**

LexAegis AI lets users upload legal documents (contracts, compliance manuals,
regulations, policies) and ask legal questions, compare clauses, analyze risk,
and retrieve evidence — returning **grounded, cited, confidence-scored** answers
produced by an 8-agent LangGraph workflow over a hybrid retrieval pipeline, with
input/output safety, observability, semantic caching, and evaluation built in.

> This repository is built to run **fully locally first**. Every heavy component
> (BGE embeddings, ChromaDB, Presidio, LlamaGuard, Phoenix, GPTCache, RAGAS,
> DeepEval) sits behind a Protocol with a deterministic light fallback, so you
> can run and test the entire system offline, then flip a config flag to use the
> production backend. Dockerization comes after local validation.

---

## Architecture at a glance (six layers)

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ Layer 1 — INGRESS    FastAPI · Supabase JWT · rate limiting · tenants     │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ Layer 2 — SAFETY     LlamaGuard input safety · Presidio PII · output gate │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ Layer 3 — RETRIEVAL  loaders → legal chunking → dense+sparse → RRF →      │
 │                       compression → rerank → top-K                        │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ Layer 4 — AGENTS     LangGraph: 8 agents → grounded, cited answer         │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ Layer 5 — QUALITY    RAGAS · DeepEval · benchmark dataset                 │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ Layer 6 — OPS        Arize Phoenix tracing · OpenInference · GPTCache     │
 └─────────────────────────────────────────────────────────────────────────┘
```

Full detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Repository layout

```
lexaegis-ai/
├─ backend/          FastAPI + agents + retrieval + safety + observability
├─ frontend/         Next.js + TypeScript + Tailwind (6 pages)
├─ evaluation/       Benchmark dataset + RAGAS / DeepEval / offline runners
├─ docs/             Full documentation set (14 guides)
├─ scripts/          Local run helpers
├─ docker/           (reserved — deployment comes later)
└─ .env.example      Every environment variable, documented
```

---

## Tech stack

| Concern | Technology |
|---|---|
| API gateway | FastAPI |
| Auth | Supabase Auth (JWT) |
| Agents | LangGraph |
| Vector DB | ChromaDB |
| Dense embeddings | BAAI/bge-large-en-v1.5 |
| Reranker | BAAI/bge-reranker-large |
| Sparse retrieval | BM25 (rank_bm25) |
| LLM | Ollama — Qwen3 (primary), Llama 3.1 (fallback) |
| Safety | LlamaGuard, Microsoft Presidio |
| Caching | GPTCache (semantic) |
| Observability | Arize Phoenix + OpenInference |
| Evaluation | RAGAS, DeepEval |
| Frontend | Next.js, TypeScript, Tailwind, shadcn-style UI |

---

## Quick start (fully local, no model downloads)

### 1. Backend

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate   |  *nix: source .venv/bin/activate

pip install -r backend/requirements-phase1.txt
pip install numpy rank-bm25 langgraph langchain-core   # light pipeline deps

cp .env.example backend/.env          # set SUPABASE_JWT_SECRET (any value for local tests)

cd backend
uvicorn app.main:app --reload         # http://localhost:8000/docs
```

Smoke test (no auth):
```bash
curl "http://localhost:8000/api/v1/ping?msg=hello"
```

### 2. Evaluation (offline, end-to-end)

```bash
python evaluation/evaluate_local.py    # writes evaluation/results/latest.json
```

### 3. Frontend

```bash
cd frontend
cp .env.local.example .env.local       # set NEXT_PUBLIC_API_BASE (+ Supabase if used)
npm install
npm run dev                            # http://localhost:3000
```

### 4. Tests

```bash
cd backend
pip install pytest pytest-asyncio
pytest                                 # 57 passed — fully offline
```

---

## Going to production backends

No code changes — flip config in `backend/.env` (see the table in
[backend/README.md](backend/README.md) §5) and install the heavy stack:

```bash
pip install -r backend/requirements.txt
ollama pull qwen3 && ollama pull llama3.1 && ollama pull llama-guard3
python -m spacy download en_core_web_lg     # Presidio NER
```

Setup guides: [OLLAMA_SETUP](docs/OLLAMA_SETUP.md) ·
[SUPABASE_SETUP](docs/SUPABASE_SETUP.md) · [PHOENIX_SETUP](docs/PHOENIX_SETUP.md).

---

## Documentation

| Guide | What it covers |
|---|---|
| [ARCHITECTURE](docs/ARCHITECTURE.md) | The six layers and how they fit together |
| [BACKEND_GUIDE](docs/BACKEND_GUIDE.md) | Backend modules, config, request flow |
| [FRONTEND_GUIDE](docs/FRONTEND_GUIDE.md) | Next.js app, pages, API client, auth |
| [DEVELOPER_HANDBOOK](docs/DEVELOPER_HANDBOOK.md) | Setup, conventions, adding features |
| [INGESTION_PIPELINE](docs/INGESTION_PIPELINE.md) | Loaders → PII mask → chunk → index |
| [AGENT_WORKFLOW](docs/AGENT_WORKFLOW.md) | The 8 agents and the LangGraph |
| [RETRIEVAL_PIPELINE](docs/RETRIEVAL_PIPELINE.md) | Hybrid retrieval internals |
| [OBSERVABILITY_GUIDE](docs/OBSERVABILITY_GUIDE.md) | Tracing + caching + metrics |
| [EVALUATION_GUIDE](docs/EVALUATION_GUIDE.md) | RAGAS / DeepEval / offline metrics |
| [SECURITY_GUIDE](docs/SECURITY_GUIDE.md) | Auth, tenancy, safety, PII |
| [SUPABASE_SETUP](docs/SUPABASE_SETUP.md) | Auth project setup |
| [OLLAMA_SETUP](docs/OLLAMA_SETUP.md) | Local LLM setup |
| [PHOENIX_SETUP](docs/PHOENIX_SETUP.md) | Tracing UI setup |

---

## Status

Built and verified through **local validation** (backend, agents, retrieval,
safety, observability, caching, evaluation, frontend). Dockerization, Kubernetes,
and Terraform are intentionally **out of scope** until local behavior is signed
off.
