# ⚖️ LexAegis AI

**Agentic Legal Intelligence Platform — ask questions about your legal documents and get grounded, cited, confidence-scored answers.**

Upload contracts, policies, regulations, or compliance manuals, then ask in plain
English ("How long do confidentiality obligations survive termination?"). LexAegis
retrieves the relevant clauses, reasons over **only that retrieved text**, and
returns an answer with inline `[S1]` citations, a confidence breakdown, and
groundedness checks — never free-form hallucination. Built with input/output
safety, PII masking, observability, and evaluation in the box.

> **Live in production:** Next.js on **Vercel**, FastAPI on **Railway**, **Supabase**
> auth, **Gemini 2.5 Flash** inference.

---

## ▶️ Try it in 60 seconds

- **Live demo:** https://lex-aegis-ai.vercel.app -->
- **Demo login:** open the app → **Sign in** page → click **Try demo** → **Sign in**
  (fills `demo@lexaegis.ai`). Or paste a Supabase access token via the dev-token box.
- **Then:** Upload a PDF/DOCX/TXT on **Upload** → ask a question on **Legal Chat** →
  inspect quality on **Evaluation** and latency/cost on **Dashboard**.

---

## What it does

- 📄 **Document ingestion** — PDF/DOCX/TXT → structure-aware *legal* chunking that
  preserves section / clause / page so citations are precise.
- 🔎 **Hybrid retrieval** — dense embeddings (BGE) **+** BM25 keyword search, merged
  with Reciprocal Rank Fusion, de-duplicated, and reranked.
- 🤖 **Agentic reasoning** — a LangGraph workflow (input guard **+ 8 agents**)
  produces a context-only, cited answer with an explainable confidence score.
- 🛡️ **Safety & PII** — prompt-injection/unsafe-input guard, Presidio PII masking
  (at ingest, query, and output), and a grounded-output gate that blocks
  ungrounded/uncited answers.
- 📊 **Observability & cost** — in-process latency tracing, cache stats, and
  estimated LLM spend, all surfaced on the dashboard.
- 🧪 **Evaluation** — a benchmark harness + dashboard (offline lexical metrics by
  default; optional RAGAS / DeepEval with a Gemini judge).
- 🔌 **One-switch portability** — the same code runs **fully offline** (deterministic
  light backends) or on production backends by changing environment variables only.

---

## How it works

```
 ┌─────────────────────────────────────────────────────────────────────────┐
 │ L1 INGRESS     FastAPI · Supabase JWT · rate limiting · multi-tenant      │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ L2 SAFETY      input guard · Presidio PII masking · grounded-output gate  │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ L3 RETRIEVAL   loaders → legal chunking → dense + BM25 → RRF →            │
 │                compression → rerank → top-K                               │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ L4 AGENTS      LangGraph: guard + 8 agents → grounded, cited answer       │
 ├─────────────────────────────────────────────────────────────────────────┤
 │ L5 QUALITY     legal benchmark + evaluation dashboard (RAGAS/DeepEval opt)│
 ├─────────────────────────────────────────────────────────────────────────┤
 │ L6 OPS         in-process tracing + cost metering + cache (Phoenix opt)   │
 └─────────────────────────────────────────────────────────────────────────┘
```

**One chat turn:** verify JWT → input safety + PII mask → query understanding →
hybrid retrieval → rerank → reason over context (Gemini) → attach citations →
groundedness + confidence → output-safety release.

Deep dive: **[PROJECT_DETAILS.md](PROJECT_DETAILS.md)** · [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/AGENT_WORKFLOW.md](docs/AGENT_WORKFLOW.md)

---

## Tech stack (as deployed)

| Concern | Technology |
|---|---|
| Frontend | Next.js · TypeScript · Tailwind (Vercel) |
| Backend | FastAPI · Python 3.12 (Railway) |
| Auth | Supabase Auth — JWT (HS256 or JWKS RS256/ES256) |
| LLM | **Gemini 2.5 Flash** (prod) · Ollama Qwen3/Llama 3.1 (local) |
| Orchestration | LangGraph (input guard + 8 agents) |
| Vector DB | ChromaDB (persistent volume) |
| Retrieval | BGE dense embeddings + BM25 sparse + RRF + rerank |
| Safety | Microsoft Presidio (PII) · input/output guards |
| Observability | In-process tracing + cost metering · OTLP/Phoenix export optional |
| Evaluation | Offline lexical benchmark · RAGAS / DeepEval optional |

> Heavy backends sit behind interfaces with deterministic light fallbacks, so the
> whole pipeline runs and tests offline. Some components are intentionally optional
> in production (e.g. Phoenix tracing, BGE cross-encoder reranker) — see
> **[PROJECT_DETAILS.md](PROJECT_DETAILS.md)** §14, §17–18 for the exact, honest
> production configuration.

---

## Repository layout

```
lexaegis-ai/
├─ backend/          FastAPI + agents + retrieval + safety + observability
├─ frontend/         Next.js + TypeScript + Tailwind
├─ evaluation/       Benchmark dataset + offline/RAGAS/DeepEval runners
├─ docs/             Architecture, retrieval, agents, safety, deployment guides
├─ deployment/       Production env template
└─ PROJECT_DETAILS.md   Full technical reference (single source of truth)
```

---

## Run locally (offline, no model downloads)

```bash
# Backend
python -m venv .venv && . .venv/Scripts/activate      # *nix: source .venv/bin/activate
pip install -r backend/requirements-phase1.txt
pip install numpy rank-bm25 langgraph langchain-core   # light pipeline deps
cp .env.example backend/.env                           # set SUPABASE_JWT_SECRET (any value locally)
cd backend && uvicorn app.main:app --reload            # http://localhost:8000/docs

# Frontend (new terminal)
cd frontend && cp .env.local.example .env.local        # set NEXT_PUBLIC_API_BASE
npm install && npm run dev                              # http://localhost:3000

# Tests
cd backend && pytest                                    # 95 passed, fully offline
```

Generate a local auth token without Supabase: `python scripts/generate_dev_token.py`
(paste it into the login page's dev-token box or Swagger's Authorize).

**Go to production:** flip `LLM_PROVIDER=gemini` and the backend selectors in env —
no code changes. See [docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md)
and [docs/LLM_PROVIDER_GUIDE.md](docs/LLM_PROVIDER_GUIDE.md).

---

## Documentation

| Guide | What it covers |
|---|---|
| [PROJECT_DETAILS.md](PROJECT_DETAILS.md) | Complete technical reference: architecture, every layer, decisions, limitations |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | The six layers and how they fit together |
| [AGENT_WORKFLOW](docs/AGENT_WORKFLOW.md) | The input guard + 8 agents and the LangGraph |
| [RETRIEVAL_PIPELINE](docs/RETRIEVAL_PIPELINE.md) | Hybrid retrieval internals |
| [SECURITY_GUIDE](docs/SECURITY_GUIDE.md) | Auth, tenancy, safety, PII |
| [EVALUATION_GUIDE](docs/EVALUATION_GUIDE.md) | Benchmark + RAGAS / DeepEval / offline metrics |
| [DEPLOYMENT_ARCHITECTURE](docs/DEPLOYMENT_ARCHITECTURE.md) · [LLM_PROVIDER_GUIDE](docs/LLM_PROVIDER_GUIDE.md) | How local vs production are wired |

---

## Status

**Deployed and working in production** (Vercel + Railway + Supabase + Gemini). The
core path — auth → upload → ingest → retrieve → reason → cite → validate — is
implemented and validated (95 backend tests pass; frontend builds clean). Known
limitations and the precise production configuration are documented honestly in
**[PROJECT_DETAILS.md](PROJECT_DETAILS.md)**.
