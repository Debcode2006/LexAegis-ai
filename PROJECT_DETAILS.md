# LexAegis AI — Project Details (Single Source of Truth)

> This document is written to be the **only** context another reader (human or
> LLM) needs to understand LexAegis AI. Every claim below was verified against the
> source in this repository. File paths are clickable references to the exact
> implementation.
>
> **Legend for status labels used throughout:**
> - **Implemented** — present and wired into the running system.
> - **Partially implemented** — code exists but is not fully active in the
>   deployed configuration (or a documented sub-feature is not wired in).
> - **Planned** — described in code/docs as a future step; not built.
> - **Abandoned / not deployed** — built or scaffolded but intentionally not used
>   in production due to a constraint.

---

## SECTION 1 — PROJECT OVERVIEW

**Project name:** LexAegis AI — Agentic Legal Intelligence Platform.

**One-paragraph summary.** LexAegis AI lets an authenticated user upload legal
documents (contracts, compliance manuals, regulations, policies) and ask natural-
language legal questions about them. Each question is processed by a LangGraph
workflow — an input-safety guard followed by eight agents — running over a hybrid
retrieval pipeline (dense embeddings + BM25, fused with Reciprocal Rank Fusion,
compressed, and reranked). The system returns a **grounded, citation-backed,
confidence-scored** answer, with PII masking, input/output safety gating,
in-process observability (latency, cache, estimated cost), and an offline
evaluation harness. It runs **fully locally** with deterministic light backends
and switches to production backends (Gemini, ChromaDB, Presidio) by environment
variables with no code change.

**Problem statement.** Legal professionals need answers that are *traceable to
source text*. A generic chatbot that paraphrases from parametric memory is unsafe
for legal use: it can hallucinate clauses, omit citations, and leak personal data.
LexAegis is built around the constraint that **every answer must be grounded in
retrieved document text and cite its sources**, and must refuse when it cannot.

**Why legal document intelligence is difficult.**
- Legal meaning lives in structure — *which* section/clause a statement belongs to
  changes its meaning. Naive fixed-size chunking destroys that structure.
- Exact terms matter (defined terms, statute numbers, clause references) where
  pure semantic embeddings blur; lexical matching matters where embeddings shine.
  Neither alone is sufficient.
- Answers must be auditable: a number ("five years", "30 days") must point back to
  the clause it came from.
- Documents contain PII that must not be embedded, logged, or echoed back.
- Unsupported claims ("hallucinations") are unacceptable, so generation must be
  constrained to retrieved context and validated before release.

**Goals of the system.**
1. Grounded, cited answers with an explainable confidence score.
2. Hybrid retrieval that respects legal document structure.
3. Safety on both the input (prompt injection / unsafe requests / PII) and the
   output (groundedness, citation coverage, PII leakage).
4. Run end-to-end locally with zero heavy dependencies, then flip to production
   backends with one config change.
5. Observability and cost visibility built in, plus an evaluation harness.

**Intended users.** Legal/compliance reviewers and the engineers/judges
evaluating the platform. Multi-tenant by design (tenant derived from the auth
token), so different tenants' documents are isolated.

**Key differentiators (all verified in code).**
- A **Protocol + light-fallback** architecture: every heavy component (embeddings,
  vector store, reranker, PII, input guard, LLM) sits behind an interface with a
  deterministic, dependency-free fallback — so the entire pipeline runs offline
  and is unit-testable without model downloads.
- **Provider-agnostic LLM layer**: Ollama (local) ↔ Gemini (production) selected
  by a single env var, no call-site changes ([backend/app/llm/factory.py](backend/app/llm/factory.py)).
- **Always-on grounding/citation enforcement** independent of the LLM
  ([backend/app/safety/output_safety.py](backend/app/safety/output_safety.py)).
- **Transparent confidence** as a returned weighted breakdown, not a black box
  ([backend/app/agents/confidence.py](backend/app/agents/confidence.py)).

---

## SECTION 2 — FINAL SYSTEM ARCHITECTURE

**Deployed topology** (verified in [docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md)
and [docker-compose.production.yml](docker-compose.production.yml)):

| Component | Role | Production host |
|---|---|---|
| Frontend | Next.js UI (login, dashboard, upload, chat, documents, evaluation) | **Vercel** |
| Backend | FastAPI: ingress, agents, retrieval, safety, observability | **Railway** (container) |
| Vector DB | ChromaDB (dense vectors) | **Railway** container + volume |
| LLM | Reasoning + input-guard classifier | **Gemini API** (`gemini-2.5-flash`) |
| Auth | Supabase Auth (JWT) | **Supabase** (managed, never containerized) |

```
                 ┌───────────────────────────────┐
 Browser ───────►│  Frontend — Vercel (Next.js)  │
                 └───────────────┬───────────────┘
                   HTTPS  Authorization: Bearer <Supabase JWT>
                                 │  NEXT_PUBLIC_API_BASE
                                 ▼
                 ┌───────────────────────────────┐
                 │  Backend — Railway (FastAPI)  │
                 │  Ingress → Safety → Retrieval │
                 │  → 8 Agents → Output Safety   │
                 │  LLM_PROVIDER=gemini          │
                 └───┬───────────────────┬───────┘
       Chroma HTTP   │                   │  HTTPS REST :generateContent
                     ▼                   ▼
        ┌──────────────────────┐  ┌──────────────────────────┐
        │ ChromaDB — Railway   │  │  Gemini API (Google)     │
        │ persistent volume    │  │  gemini-2.5-flash        │
        └──────────────────────┘  └──────────────────────────┘

 Auth (JWT verify) ───────────────►  Supabase (managed cloud)
```

**Component descriptions.**
- **Ingress** ([backend/app/main.py](backend/app/main.py)): FastAPI app factory;
  middleware stack (request-context → CORS → tenant), exception envelopes, v1
  router. CORS sits above auth so preflight is answered before auth runs.
- **Auth** ([backend/app/auth/supabase.py](backend/app/auth/supabase.py)):
  verifies Supabase JWTs (HS256 shared-secret or JWKS RS256/ES256).
- **Retrieval** ([backend/app/retrieval/pipeline.py](backend/app/retrieval/pipeline.py)):
  dense + BM25 → RRF → compression → rerank → top-K.
- **Agents** ([backend/app/agents/graph.py](backend/app/agents/graph.py)):
  LangGraph `StateGraph` (or a sequential fallback) threading a single
  `AgentState`.
- **LLM** ([backend/app/llm/provider.py](backend/app/llm/provider.py),
  [backend/app/llm/gemini_client.py](backend/app/llm/gemini_client.py)):
  provider-agnostic chat with primary/fallback + caching + cost metering.
- **Safety** ([backend/app/safety/](backend/app/safety/)): input guard, PII
  masking, output validation.
- **Observability** ([backend/app/observability/](backend/app/observability/)):
  in-process span recorder + cost meter; optional OTLP/Phoenix export.
- **Evaluation** ([evaluation/](evaluation/)): offline benchmark harness +
  dashboard report.

**Request flow** is summarized in [docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md)
§4 and detailed in Section 5 below.

---

## SECTION 3 — FRONTEND ARCHITECTURE

Next.js App Router, TypeScript, Tailwind, shadcn-style UI. Entry layout
[frontend/app/layout.tsx](frontend/app/layout.tsx) wraps the app in `AuthProvider`
and renders the top `Nav`.

**Pages** (all under [frontend/app/](frontend/app/), all `"use client"`):

| Route | File | Purpose |
|---|---|---|
| `/` | [frontend/app/page.tsx](frontend/app/page.tsx) | Redirects to `/dashboard` if a token exists, else `/login`. |
| `/login` | [frontend/app/login/page.tsx](frontend/app/login/page.tsx) | Email/password (Supabase) **or** paste-a-dev-token login; "Try demo" fills demo creds. |
| `/dashboard` | [frontend/app/dashboard/page.tsx](frontend/app/dashboard/page.tsx) | Doc count + observability tiles (latency, request count, cache hit-rate, trace count) + usage/cost (estimated $, prompt/completion tokens) + navigation tiles. |
| `/upload` | [frontend/app/upload/page.tsx](frontend/app/upload/page.tsx) | Upload PDF/DOCX/TXT + document type; shows chunks indexed, pages, PII masked. |
| `/chat` | [frontend/app/chat/page.tsx](frontend/app/chat/page.tsx) | Multi-conversation legal chat with document-scope picker, citations, confidence/intent/groundedness badges. |
| `/documents` | [frontend/app/documents/page.tsx](frontend/app/documents/page.tsx) | Table of ingested documents (name, type, pages, chunks, PII masked). |
| `/evaluation` | [frontend/app/evaluation/page.tsx](frontend/app/evaluation/page.tsx) | Quality metrics + per-sample results from the latest evaluation report. |

(The README refers to "6 pages"; that counts the six navigable pages — `/login`
plus the five in the nav — alongside the `/` redirect.)

**Authentication & state** ([frontend/lib/auth.tsx](frontend/lib/auth.tsx)):
React context holding `{ token, email }`, persisted to `localStorage`
(`lexaegis_token`, `lexaegis_email`). `loginWithPassword` calls Supabase's REST
endpoint `POST {NEXT_PUBLIC_SUPABASE_URL}/auth/v1/token?grant_type=password`
directly and stores the returned `access_token`. There is **no Supabase JS SDK**
and **no Next.js middleware route-guard**: route protection is enforced by the
backend (401 on missing/invalid token). Pages call APIs only when a token is
present (`if (!token) return;`).

**API integration** ([frontend/lib/api.ts](frontend/lib/api.ts),
[frontend/lib/utils.ts](frontend/lib/utils.ts)): a thin typed fetch wrapper. Base
URL is `NEXT_PUBLIC_API_BASE` (default `http://localhost:8000/api/v1`). All
authenticated calls send `Authorization: Bearer <token>`. Methods: `ping`,
`whoami`, `chat`, `uploadDocument`, `listDocuments`, `metrics`, `evaluation`.

**Chat history** ([frontend/lib/chatHistory.ts](frontend/lib/chatHistory.ts)):
multi-conversation history is **client-side only**, persisted in `localStorage`
(`lexaegis_conversations`). The backend `/chat` endpoint is stateless — it does
not store conversations.

**Major components.** [frontend/components/nav.tsx](frontend/components/nav.tsx)
(top nav, hidden on `/login`), [frontend/components/confidence-badge.tsx](frontend/components/confidence-badge.tsx)
(colored confidence pill), and shadcn-style primitives in
[frontend/components/ui/](frontend/components/ui/) (`button`, `card`, `input`).

---

## SECTION 4 — BACKEND ARCHITECTURE

FastAPI application, package root [backend/app/](backend/app/).

**App factory & middleware** — [backend/app/main.py](backend/app/main.py):
builds the app, configures CORS (exact allowlist + optional regex), adds
`TenantMiddleware` and `RequestContextMiddleware`, registers exception handlers,
mounts the v1 router under `/api/v1`, and runs startup checks + LLM health check
in the lifespan.

**Routers** — registered in [backend/app/api/router.py](backend/app/api/router.py):
`health`, `ping`, `auth`, `documents`, `chat`, `observability`, `evaluation`, and
a `debug` retrieval-inspection route. Route modules live in
[backend/app/api/v1/routes/](backend/app/api/v1/routes/). DI providers
(`get_current_principal`, `get_current_tenant`, `enforce_rate_limit`) are in
[backend/app/api/deps.py](backend/app/api/deps.py).

**Services** — [backend/app/services/](backend/app/services/):
- [chat_service.py](backend/app/services/chat_service.py) — runs the workflow,
  wraps it in a span, caches the full response per (tenant, normalized query,
  scope), maps `AgentState` → `ChatResponse`.
- [document_registry.py](backend/app/services/document_registry.py) — **in-memory**
  per-tenant catalog of uploaded documents (powers the Documents page + chat
  scope picker).
- [rate_limiter.py](backend/app/services/rate_limiter.py) — token-bucket limiter.

**Providers (LLM)** — [backend/app/llm/](backend/app/llm/):
`base.py` (the `LLMClient` Protocol, `ChatMessage`, `LLMResponse`),
`factory.py` (provider selection by role), `provider.py` (`LLMProvider`:
primary→fallback routing, cache, cost metering), `gemini_client.py`,
`ollama_client.py`, `runtime.py` (process-wide availability flag).

**Storage.** Dense vectors → ChromaDB (persistent) or in-memory
([vector_store.py](backend/app/retrieval/vector_store.py)); sparse → in-memory
BM25 ([sparse.py](backend/app/retrieval/sparse.py)); document catalog → in-memory
registry. **Supabase/Postgres is used for auth only**, not for app data.

**Configuration** — [backend/app/core/config.py](backend/app/core/config.py):
a Pydantic-Settings tree. Every subsystem owns a nested settings model with an env
prefix. `get_settings()` is `lru_cache`d. Secrets use `SecretStr`. The `.env` path
is resolved relative to the module (deterministic across uvicorn/pytest/Railway).

**Caching** — [backend/app/cache/semantic_cache.py](backend/app/cache/semantic_cache.py):
an LRU cache with hit/miss accounting (see the important caveat in Section 10).

**Evaluation** — served by [backend/app/api/v1/routes/evaluation.py](backend/app/api/v1/routes/evaluation.py)
(reads the offline report; resolves several candidate paths). Generated by the
[evaluation/](evaluation/) harness.

**Observability** — [backend/app/observability/](backend/app/observability/):
`tracing.py` (in-process recorder + optional OTLP/Phoenix), `cost.py` (cost
meter).

---

## SECTION 5 — END-TO-END REQUEST FLOW

**1. Login.** User signs in on [frontend/app/login/page.tsx](frontend/app/login/page.tsx).
`loginWithPassword` ([frontend/lib/auth.tsx](frontend/lib/auth.tsx)) calls Supabase
`/auth/v1/token?grant_type=password`; the returned `access_token` is stored in
`localStorage`. (Alternatively, paste a dev token from
[scripts/generate_dev_token.py](scripts/generate_dev_token.py).)

**2. Document upload.** `POST /api/v1/documents/upload`
([backend/app/api/v1/routes/documents.py](backend/app/api/v1/routes/documents.py)).
Auth + tenant + rate-limit dependencies run; the file extension is validated
against `{.pdf,.docx,.txt}` and size against a 25 MB cap.

**3. Ingestion** ([backend/app/ingestion/pipeline.py](backend/app/ingestion/pipeline.py)):
load bytes → page text ([loaders.py](backend/app/ingestion/loaders.py)) →
ingestion-time PII masking ([safety/pii.py](backend/app/safety/pii.py)) →
legal-aware chunking with section/clause/heading/page metadata
([chunking.py](backend/app/ingestion/chunking.py)) → embed + index into the dense
store and BM25 ([retrieval/pipeline.py `index_chunks`](backend/app/retrieval/pipeline.py)).
An `IngestionReport` (pages, chunks indexed, PII masked) is registered in the
in-memory `DocumentRegistry`.

**4. Retrieval** (triggered by chat) ([backend/app/retrieval/pipeline.py](backend/app/retrieval/pipeline.py)
`run_stages`): store-population check → dense search → BM25 search →
Reciprocal Rank Fusion ([fusion.py](backend/app/retrieval/fusion.py)) →
compression/near-dup removal ([compression.py](backend/app/retrieval/compression.py)) →
rerank ([reranker.py](backend/app/retrieval/reranker.py)) → top-K selection.

**5. Answer generation** ([backend/app/agents/reasoning.py](backend/app/agents/reasoning.py)):
the reasoning agent builds a context block from the selected chunks and asks the
LLM (Gemini in production) to answer **using only that context**, citing `[S1]`,
`[S2]`, …. If the LLM is disabled/unavailable, a deterministic extractive fallback
composes a cited answer from the top chunk.

**6. Citation generation** ([backend/app/agents/citation.py](backend/app/agents/citation.py)):
parses `[S#]` tags from the answer and builds structured citations (document,
section, clause, page, snippet) for the referenced sources.

**7. Validation & release.** Groundedness
([backend/app/agents/groundedness.py](backend/app/agents/groundedness.py) →
[safety/output_safety.py](backend/app/safety/output_safety.py)) scores per-sentence
support, citation coverage, and PII leakage. Confidence
([confidence.py](backend/app/agents/confidence.py)) blends five signals. Output
safety ([output_safety_agent.py](backend/app/agents/output_safety_agent.py))
releases the answer or replaces it with a safe fallback (capping confidence at
0.2).

**8. Observability collection.** [chat_service.py](backend/app/services/chat_service.py)
wraps the turn in a `chat.turn` span; each agent node is wrapped in an
`agent.<name>` span ([agents/graph.py](backend/app/agents/graph.py)). LLM calls
record token usage to the cost meter ([observability/cost.py](backend/app/observability/cost.py)).
All of this is exposed at `/api/v1/observability/metrics` and `/traces`.

---

## SECTION 6 — THE SIX-LAYER ARCHITECTURE

### LAYER 1 — INGRESS
**Purpose.** Authenticate, isolate tenants, rate-limit, validate, and route every
request before any business logic runs.

- **Authentication** — [backend/app/auth/supabase.py](backend/app/auth/supabase.py):
  Supabase JWT verification. HS256 (shared `SUPABASE_JWT_SECRET`) or asymmetric
  (RS256/ES256/etc.) via JWKS. The verification algorithm family is scoped to the
  token's own `alg` (closes alg-confusion / `alg=none`). Builds a `Principal`
  (`user_id`, `email`, `role`, `tenant_id` from `app_metadata.tenant_id`).
- **Rate limiting** — [backend/app/services/rate_limiter.py](backend/app/services/rate_limiter.py)
  enforced in [backend/app/api/deps.py](backend/app/api/deps.py): per-user
  (default 120/60s) **and** per-tenant (default 1200/60s) token buckets, burst
  multiplier 1.5; both must pass. Backend is in-memory (Redis configurable, not
  deployed).
- **Validation** — bearer presence ([deps.py](backend/app/api/deps.py)); upload
  type/size ([documents.py](backend/app/api/v1/routes/documents.py)); request
  bodies via Pydantic schemas ([backend/app/schemas/](backend/app/schemas/)).
- **Routing** — [backend/app/api/router.py](backend/app/api/router.py),
  middleware in [backend/app/main.py](backend/app/main.py) and
  [backend/app/middleware/](backend/app/middleware/) (request id + tenant hint).
- **Production behavior.** CORS exact-allowlist + regex for Vercel previews;
  trailing slashes normalized. Tenant isolation enforced
  ([deps.py `get_current_tenant`](backend/app/api/deps.py)). Startup warns on
  misconfig ([core/startup.py](backend/app/core/startup.py)).

### LAYER 2 — SAFETY & GUARDRAILS
**Purpose.** Protect both inbound and outbound text.

- **Input protection** — [backend/app/safety/input_safety.py](backend/app/safety/input_safety.py):
  `ModelGuard` (LLM-backed classifier — LlamaGuard3 via Ollama locally, or the
  Gemini model as a prompt classifier in production) with a regex `HeuristicGuard`
  fallback. Master switch `ENABLE_LLAMAGUARD`; auto-falls back to heuristic if the
  LLM is unreachable. Wired as the graph entry node
  ([agents/guard.py](backend/app/agents/guard.py)).
- **Prompt protection.** The reasoning system prompt
  ([agents/reasoning.py](backend/app/agents/reasoning.py)) forbids facts not in
  context and requires inline citations; the input guard screens for prompt
  injection/jailbreak patterns.
- **PII handling** — [backend/app/safety/pii.py](backend/app/safety/pii.py):
  `PresidioPIIDetector` (Microsoft Presidio + spaCy NER, plus custom Indian
  identifiers PAN/Aadhaar/Passport) with a `RegexPIIDetector` fallback. Masking is
  applied at **ingestion** (before embed/store), **query** (before retrieval/log),
  and **output** (final check). Typed placeholders, e.g. `<EMAIL_ADDRESS>`.
- **Output protection / moderation** — [backend/app/safety/output_safety.py](backend/app/safety/output_safety.py):
  per-sentence lexical grounding, citation presence, unsupported-claim detection,
  and PII-leak check. Below `SAFETY_MIN_CITATION_COVERAGE` (default 0.5) or on PII
  leak (`SAFETY_BLOCK_ON_PII_LEAK`), the answer is **not allowed** and the Output
  Safety agent substitutes a safe fallback.
- **Production behavior.** Production config
  ([deployment/production.env.example](deployment/production.env.example)):
  `SAFETY_PII_BACKEND=presidio`, `SAFETY_INPUT_GUARD_BACKEND=llama_guard`
  (→ Gemini classifier), input+output safety + PII masking on.

### LAYER 3 — RETRIEVAL
**Purpose.** Turn an uploaded corpus and a query into the smallest set of
highly-relevant, structure-aware context chunks. (Full deep-dive in Section 7.)

- **Ingestion / chunking** — [backend/app/ingestion/chunking.py](backend/app/ingestion/chunking.py):
  structure-first legal chunker (detects ARTICLE/Section/clause/(a)/heading
  boundaries; carries context across pages; merges tiny title blocks; splits
  oversized blocks into overlapping windows; max 1200 chars / 150 overlap by
  default).
- **Embeddings** — [backend/app/retrieval/embeddings.py](backend/app/retrieval/embeddings.py):
  `BGEEmbedder` (sentence-transformers; production default `BAAI/bge-small-en-v1.5`)
  or `HashingEmbedder` (deterministic, light).
- **Storage** — [backend/app/retrieval/vector_store.py](backend/app/retrieval/vector_store.py):
  `ChromaVectorStore` (production, cosine) or `InMemoryVectorStore`; both
  tenant-filtered. Sparse: per-tenant BM25
  ([sparse.py](backend/app/retrieval/sparse.py), `rank_bm25`).
- **Hybrid retrieval + fusion** — RRF
  ([fusion.py](backend/app/retrieval/fusion.py)), default `rrf_k=60`.
- **Reranking** — [backend/app/retrieval/reranker.py](backend/app/retrieval/reranker.py):
  `BGEReranker` (cross-encoder, FlagEmbedding) or `LexicalReranker` (IDF-weighted
  token overlap blended with the RRF prior). **The documented production config
  defaults to `lexical`** to stay within memory limits; the BGE cross-encoder is
  available behind `RETRIEVAL_RERANKER_BACKEND=bge`.
- **Context assembly** — top-K selection (`final_top_k=5`) feeds the reasoning
  context block ([reasoning.py `build_context_block`](backend/app/agents/reasoning.py)).
- **Production behavior.** `RETRIEVAL_VECTOR_STORE=chroma`,
  `EMBEDDING_BACKEND=bge` (bge-small), reranker `lexical` by default, compression
  on. Stage-by-stage diagnostics logged; the `debug` route returns them verbatim.

### LAYER 4 — GENERATION & ORCHESTRATION
**Purpose.** Coordinate the agents and generate the grounded answer. (Deep-dive in
Section 8.)

- **Orchestration** — [backend/app/agents/graph.py](backend/app/agents/graph.py):
  LangGraph `StateGraph` (`AGENT_ORCHESTRATOR=langgraph`) or a behaviorally
  identical sequential fallback; one shared `AgentState`
  ([state.py](backend/app/agents/state.py)).
- **Query understanding** — [backend/app/agents/query_understanding.py](backend/app/agents/query_understanding.py):
  intent (7 classes) + legal task + entities. LLM JSON path when
  `USE_LLM_FOR_UNDERSTANDING=true`; **heuristic by default** (advisory output).
- **Planner** — [backend/app/agents/planner.py](backend/app/agents/planner.py):
  rule-based intent → workflow/strategy/tools (advisory hints).
- **Answer generation** — [backend/app/agents/reasoning.py](backend/app/agents/reasoning.py):
  context-only LLM generation (Gemini in prod) with extractive fallback.
- **Citation** — [backend/app/agents/citation.py](backend/app/agents/citation.py).
- **Confidence scoring** — [backend/app/agents/confidence.py](backend/app/agents/confidence.py):
  weighted blend (retrieval 0.20, reranker 0.25, source agreement 0.15, citation
  coverage 0.20, groundedness 0.20), returned as a breakdown.
- **Model routing** — [backend/app/llm/provider.py](backend/app/llm/provider.py)
  + [factory.py](backend/app/llm/factory.py): primary→fallback on failure.
- **Production behavior.** Only **reasoning** (and the **input guard**, if model
  guard is on) call the LLM in the default production config; understanding stays
  heuristic.

### LAYER 5 — EVALUATION
**Purpose.** Measure retrieval + answer quality on a fixed benchmark. (Section 9.)

- **Current implementation** — [evaluation/](evaluation/): a shared harness
  ([_harness.py](evaluation/_harness.py)) runs the real workflow over a benchmark
  dataset ([evaluation/datasets/legal_benchmark.json](evaluation/datasets/legal_benchmark.json))
  using **light backends** (hashing embedder, in-memory store, lexical reranker,
  **no LLM** → extractive answers). Three runners: offline lexical
  ([evaluate_local.py](evaluation/evaluate_local.py) + [offline_metrics.py](evaluation/offline_metrics.py)),
  RAGAS ([run_ragas.py](evaluation/run_ragas.py)), DeepEval
  ([run_deepeval.py](evaluation/run_deepeval.py)).
- **Dashboard / report** — the backend serves the latest report
  ([backend/app/api/v1/routes/evaluation.py](backend/app/api/v1/routes/evaluation.py));
  the frontend renders it ([frontend/app/evaluation/page.tsx](frontend/app/evaluation/page.tsx)).
- **Production behavior.** The deployed dashboard reads a **pre-generated
  `offline_lexical` report** baked into the image
  ([evaluation/results/latest.json](evaluation/results/latest.json) /
  [backend/evaluation/results/latest.json](backend/evaluation/results/latest.json)).
- **Known limitations.** RAGAS/DeepEval are **offline scripts, not run in the
  deployed service**; the benchmark exercises the **light** pipeline (extractive
  answers), not the production BGE+Gemini path. See Section 9.

### LAYER 6 — OBSERVABILITY & OPERATIONS
**Purpose.** Make latency, cost, cache behavior, and per-agent timing visible.

- **Tracing** — [backend/app/observability/tracing.py](backend/app/observability/tracing.py):
  an always-on bounded in-process span recorder (ring buffer, default 200 spans)
  **plus** an optional OpenTelemetry/OTLP exporter to Arize Phoenix.
- **Latency / request metrics** — derived from the `chat.turn` span and
  `agent.<name>` spans; summarized by `TraceRecorder.summary()`.
- **Cost metering** — [backend/app/observability/cost.py](backend/app/observability/cost.py):
  thread-safe accumulator of prompt/completion tokens × Gemini 2.5 Flash pricing
  (default $0.30 / $2.50 per 1M tokens). Only real LLM calls are metered (cache
  hits excluded).
- **Cache metrics** — [backend/app/cache/semantic_cache.py](backend/app/cache/semantic_cache.py)
  `stats()` (enabled, backend, entries, hits, misses, hit-rate).
- **Logs** — structured logging ([backend/app/core/logging.py](backend/app/core/logging.py)),
  JSON in production.
- **Surface** — `GET /api/v1/observability/metrics` and `/traces`
  ([observability.py](backend/app/api/v1/routes/observability.py)); rendered on
  the dashboard ([frontend/app/dashboard/page.tsx](frontend/app/dashboard/page.tsx)).
- **Known limitations.** All counters are **process-local and reset on restart**;
  Phoenix export is **off by default** in production
  ([deployment/production.env.example](deployment/production.env.example):
  `OBSERVABILITY_ENABLE_TRACING=false`) and needs an external collector.

---

## SECTION 7 — RETRIEVAL PIPELINE DEEP DIVE

**Document lifecycle (upload → searchable):**
1. **Upload** — `POST /documents/upload`
   ([documents.py](backend/app/api/v1/routes/documents.py)): validates type
   (`.pdf/.docx/.txt`) and 25 MB cap.
2. **Parsing** — [backend/app/ingestion/loaders.py](backend/app/ingestion/loaders.py):
   `pypdf` (per-page text, page numbers preserved), `python-docx` (single page,
   paragraph structure), or UTF-8 text. Returns `PageText[]`.
3. **PII masking (ingestion-time)** — [backend/app/ingestion/pipeline.py](backend/app/ingestion/pipeline.py)
   masks each page before chunking, so PII is never embedded or stored.
4. **Chunking** — [backend/app/ingestion/chunking.py](backend/app/ingestion/chunking.py):
   structure-first. Detects sections (`ARTICLE IV`, `Section 5`, `5.`), clauses
   (`5.1`, `(a)`, `Clause 7.2`), and headings (Title/ALL-CAPS). Each chunk carries
   `section`, `clause`, `heading`, `page_number`, `chunk_index`. Oversized blocks
   are split on paragraph/sentence boundaries into overlapping windows
   (`chunk_max_chars=1200`, `chunk_overlap_chars=150`).
5. **Embedding generation** — [backend/app/retrieval/embeddings.py](backend/app/retrieval/embeddings.py):
   `BGEEmbedder` (lazy-loaded sentence-transformers; query-instruction prefix) or
   `HashingEmbedder`.
6. **Vector indexing** — [backend/app/retrieval/vector_store.py](backend/app/retrieval/vector_store.py):
   ChromaDB (cosine, tenant + optional document filter) or in-memory; **and**
   per-tenant BM25 ([sparse.py](backend/app/retrieval/sparse.py)). Both updated by
   the single write path `HybridRetriever.index_chunks`.

**Search (query → context):** ([pipeline.py `run_stages`](backend/app/retrieval/pipeline.py))
1. Store-population counts (vector + BM25) — diagnoses an empty index.
2. **Dense** search (`dense_top_k=20`) and **sparse** BM25 (`sparse_top_k=20`),
   both tenant/document scoped.
3. **RRF fusion** ([fusion.py](backend/app/retrieval/fusion.py)) — rank-based merge
   (`1/(k+rank)`, `rrf_k=60`); source dense/BM25 scores carried for transparency.
4. **Compression** ([compression.py](backend/app/retrieval/compression.py)) —
   near-duplicate removal (`dedup_threshold=0.95`).
5. **Reranking** ([reranker.py](backend/app/retrieval/reranker.py)) — top
   `rerank_top_k=8` candidates re-scored; `final_top_k=5` kept. Lexical (default
   prod) or BGE cross-encoder.
6. **Final output** — `RetrievalResult` (selected chunks + per-stage counts +
   `reranked` flag).

**Observability hook.** `run_stages` is shared by production retrieval **and** the
`POST /api/v1/debug/retrieval` endpoint
([backend/app/api/v1/routes/debug.py](backend/app/api/v1/routes/debug.py)), which
returns every intermediate stage + `first_empty_stage()` to pinpoint where context
disappears.

---

## SECTION 8 — LLM PIPELINE DEEP DIVE

**Model provider abstraction.** Agents and safety depend only on the
`LLMClient`/`LLMProvider` interfaces ([backend/app/llm/base.py](backend/app/llm/base.py),
[provider.py](backend/app/llm/provider.py)). The factory
([factory.py](backend/app/llm/factory.py)) builds a concrete client per role
(`primary`/`fallback`/`guard`) from `LLM_PROVIDER` (`ollama` | `gemini`).

**Prompt construction & context injection.** Reasoning
([reasoning.py](backend/app/agents/reasoning.py)) sends a system prompt (context-
only, citation-required) + a user message containing the numbered context block
(`[S1] doc (section, clause, p.N): text …`) and the question.

**Answer generation (Gemini).** [backend/app/llm/gemini_client.py](backend/app/llm/gemini_client.py)
calls the Generative Language REST API `:generateContent` over `httpx` (no SDK).
It maps `system`→`systemInstruction`, `assistant`→`model`, passes
`temperature`/`maxOutputTokens`, and parses `candidates[0].content.parts[].text`.

**Citation attachment.** [citation.py](backend/app/agents/citation.py) extracts
`[S#]` markers and builds structured citations; if no tags are present, all
retrieved sources are exposed for traceability.

**Token accounting & cost metering.** Gemini's `usageMetadata`
(`promptTokenCount`, `candidatesTokenCount`) populates `LLMResponse`; `LLMProvider`
records it into the cost meter ([cost.py](backend/app/observability/cost.py)) on
each real call. Cache hits are not metered.

**Fallback logic.**
- **Provider fallback** — primary model failure → retry on fallback model
  ([provider.py](backend/app/llm/provider.py)). (In the production example,
  `GEMINI_FALLBACK_MODEL=gemini-2.5-flash`, i.e. the same model.)
- **Stage fallback** — if the LLM is unavailable/disabled
  ([runtime.py](backend/app/llm/runtime.py) flag set by
  [startup.py](backend/app/core/startup.py)): understanding → heuristic, reasoning
  → extractive, input guard → heuristic. The system never hard-fails on a dead
  LLM.
- **Output cache** — `LLMProvider.chat` caches completions keyed on
  model + serialized conversation (see Section 10 caveat).

---

## SECTION 9 — EVALUATION SYSTEM

**What runs the predictions.** All three runners share
[evaluation/_harness.py](evaluation/_harness.py), which forces **light, offline
backends** (`EMBEDDING_BACKEND=hashing`, `RETRIEVAL_VECTOR_STORE=memory`,
`RETRIEVAL_RERANKER_BACKEND=lexical`, regex PII, heuristic guard), ingests the
benchmark docs, and runs the **real** `LegalAgentWorkflow` with `provider=None`
(so answers are the **extractive fallback**, not LLM-generated).

**The three evaluators:**
| Runner | File | Metrics | Judge | Deployed? |
|---|---|---|---|---|
| Offline lexical | [evaluate_local.py](evaluation/evaluate_local.py) + [offline_metrics.py](evaluation/offline_metrics.py) | faithfulness, answer_relevancy, groundedness, context_precision, context_recall, intent_correct (token-overlap approximations) | none (deterministic) | **Yes** — produces the served report |
| RAGAS | [run_ragas.py](evaluation/run_ragas.py) | faithfulness, answer_relevancy, context_precision, context_recall | RAGAS judge (OpenAI by default) | No (optional offline) |
| DeepEval | [run_deepeval.py](evaluation/run_deepeval.py) | groundedness (faithfulness), answer_quality (relevancy), optional hallucination | **Gemini 2.5 Flash** (`GeminiModel`) | No (optional offline) |

**What is actually deployed.** The Evaluation Dashboard reads the report at
[evaluation/results/latest.json](evaluation/results/latest.json) (also baked at
[backend/evaluation/results/latest.json](backend/evaluation/results/latest.json)),
whose `"evaluator": "offline_lexical"`. The current report covers **5 benchmark
samples** with summary scores (e.g. faithfulness ≈ 0.747, answer_relevancy ≈ 0.725,
context_recall = 1.0, intent_correct = 0.6).

**Report serving** ([backend/app/api/v1/routes/evaluation.py](backend/app/api/v1/routes/evaluation.py)):
`GET /api/v1/evaluation/results` resolves the configured path, then the
backend/repo-root copies, then the baked report; returns an empty report
(`available:false`) if none exists, so the dashboard always renders.

**DeepEval + Gemini free-tier handling** ([run_deepeval.py](evaluation/run_deepeval.py)):
because the Gemini free tier caps `gemini-2.5-flash` (~5 req/min, ~20/day) and
intermittently returns 503, the runner throttles judge calls
(`GEMINI_MIN_INTERVAL_SECONDS=15`), retries transient errors with exponential
backoff, caps samples (`DEEPEVAL_MAX_SAMPLES=3`), keeps hallucination off by
default, and **fails fast** on per-day quota exhaustion with guidance.

**Honest limitations (do not hide):**
- Deployed metrics are **lexical approximations**, not model-judged RAGAS/DeepEval.
- The benchmark uses the **light** pipeline with **extractive** answers, so scores
  do not reflect the production BGE-embeddings + Gemini-reasoning quality.
- The dataset is small (5 samples) and the report is a **static artifact**, not
  regenerated on a live schedule.

---

## SECTION 10 — OBSERVABILITY SYSTEM

**Trace collection** — [backend/app/observability/tracing.py](backend/app/observability/tracing.py):
the `span(name, attributes)` context manager times each unit of work and appends
it to a bounded ring buffer (`OBSERVABILITY_TRACE_BUFFER_SIZE`, default 200), with
the request id. If OpenTelemetry is installed and `OBSERVABILITY_ENABLE_TRACING`
is true, the same span is exported via OTLP to Phoenix; otherwise the recorder runs
alone. Instrumentation points: `chat.turn` ([chat_service.py](backend/app/services/chat_service.py))
and `agent.<name>` for each node ([agents/graph.py](backend/app/agents/graph.py)).

**Latency & request metrics** — `TraceRecorder.summary()` aggregates count and
avg/max per span name; the dashboard reads the `chat.turn` span for request count,
avg/max latency.

**Cost tracking** — [backend/app/observability/cost.py](backend/app/observability/cost.py):
running totals of prompt/completion tokens and estimated USD (Gemini 2.5 Flash
pricing, configurable). Surfaced as `cost` in `/observability/metrics`.

**Cache tracking** — [backend/app/cache/semantic_cache.py](backend/app/cache/semantic_cache.py)
`stats()` (hits/misses/hit-rate/entries).

> **Important accuracy caveat — the "semantic" cache is currently an exact
> normalized-key LRU.** `SemanticCache.get/set` operate only on an in-memory
> `OrderedDict` keyed by a SHA-256 of the normalized (lowercased, whitespace-
> collapsed) query. When `OBSERVABILITY_CACHE_BACKEND=gptcache`, a GPTCache object
> is initialized but is **not consulted** by `get`/`set`, so embedding-similarity
> matching is **not active**. In practice the cache hits only on (near-)identical
> queries. This is a **partially implemented** feature.

**Operational visibility** — `GET /api/v1/observability/metrics` returns
`{cache, traces, cost}`; `/traces` returns recent spans. Rendered on the dashboard
([frontend/app/dashboard/page.tsx](frontend/app/dashboard/page.tsx)).

**Limitations.** Process-local (reset on restart, not shared across replicas); no
persistent metrics store; Phoenix export off by default in production.

---

## SECTION 11 — API REFERENCE

Base prefix `/api/v1` (configurable). Auth = Supabase JWT bearer unless noted.

**`POST /chat`** — [chat.py](backend/app/api/v1/routes/chat.py)
- Purpose: run the agentic RAG workflow and return a grounded, cited answer.
- Inputs: `{ query: str, document_ids?: string[], include_trace?: bool }`
  ([schemas/chat.py](backend/app/schemas/chat.py)). Auth + tenant + rate-limit.
- Outputs: `ChatResponse` — `answer`, `intent`, `confidence`,
  `confidence_breakdown`, `citations[]`, `groundedness`, `blocked`,
  `block_reason`, optional `trace`.

**`POST /documents/upload`** — [documents.py](backend/app/api/v1/routes/documents.py)
- Purpose: ingest a document (parse → mask PII → chunk → index).
- Inputs: multipart `file` (`.pdf/.docx/.txt`, ≤25 MB) + `document_type`.
- Outputs: `DocumentSummary` — `document_id`, `document_name`, `document_type`,
  `pages`, `chunks_indexed`, `pii_entities_masked`.

**`GET /documents`** — [documents.py](backend/app/api/v1/routes/documents.py)
- Purpose: list the tenant's ingested documents (from the in-memory registry).
- Outputs: `{ tenant_id, count, documents: DocumentSummary[] }`.

**`GET /evaluation/results`** — [evaluation.py](backend/app/api/v1/routes/evaluation.py)
- Purpose: latest evaluation report for the dashboard.
- Outputs: `{ generated_at, dataset, evaluator, summary, samples, available }`.

**`GET /observability/metrics`** — [observability.py](backend/app/api/v1/routes/observability.py)
- Purpose: cache + trace + cost summary. Outputs: `{ cache, traces, cost }`.

**`GET /observability/traces?limit=`** — recent spans (latency + attributes).

**`GET /auth/whoami`** — [auth.py](backend/app/api/v1/routes/auth.py)
- Purpose: canonical auth smoke test. Outputs: `Principal` (user_id, email, role,
  tenant_id, scopes).

**`POST /debug/retrieval`** — [debug.py](backend/app/api/v1/routes/debug.py)
- Purpose: diagnostic — runs the production retrieval pipeline and returns every
  stage + `first_empty_stage` + config snapshot. Inputs: `{ query, document_ids? }`.

**Utility (unauthenticated/lightweight):** `GET /health`, `GET /ready`
([health.py](backend/app/api/v1/routes/health.py)), `GET /ping`
([ping.py](backend/app/api/v1/routes/ping.py)).

---

## SECTION 12 — AUTHENTICATION SYSTEM

- **Supabase integration.** The backend verifies Supabase-issued JWTs
  ([backend/app/auth/supabase.py](backend/app/auth/supabase.py)). The frontend
  obtains a token via Supabase's REST password grant
  ([frontend/lib/auth.tsx](frontend/lib/auth.tsx)). Supabase also provides
  Postgres, but the app uses Supabase **for auth only**.
- **Session handling.** Stateless on the backend (verify per request). The
  frontend stores the access token in `localStorage` and sends it as a bearer
  token; no refresh-token rotation is implemented.
- **JWT handling.** Two auto-selected modes: HS256 (shared `SUPABASE_JWT_SECRET`)
  and asymmetric via JWKS (`SUPABASE_JWKS_URL`; RS256/ES256/PS/EdDSA). The decode
  allowlist is scoped to the token's own algorithm family (prevents alg-confusion
  and `alg=none`). Tenant comes from `app_metadata.tenant_id` (default `public`).
- **Protected routes.** Enforced at the API via FastAPI dependencies
  ([deps.py](backend/app/api/deps.py)): `get_current_principal` →
  `get_current_tenant` → `enforce_rate_limit`. The frontend has **no** route-guard
  middleware; unauthenticated pages simply make no API calls (the `/` page
  redirects to `/login` when there is no token).
- **Demo / dev access.** Login page exposes demo credentials
  `demo@lexaegis.ai` / `Demo@12345` (must exist in the Supabase project) and a
  "paste a dev token" path. [scripts/generate_dev_token.py](scripts/generate_dev_token.py)
  mints a local HS256 token signed with `SUPABASE_JWT_SECRET` (default tenant
  `demo`) for local testing without a live Supabase project.

---

## SECTION 13 — DEPLOYMENT ARCHITECTURE

(Authoritative source: [docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md),
[docs/LLM_PROVIDER_GUIDE.md](docs/LLM_PROVIDER_GUIDE.md),
[docker-compose.production.yml](docker-compose.production.yml).)

- **Vercel (frontend).** Next.js built natively (root dir `frontend`).
  `NEXT_PUBLIC_*` env vars (`NEXT_PUBLIC_API_BASE`, `NEXT_PUBLIC_SUPABASE_URL`,
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`) are **inlined at build time** — changing them
  requires a redeploy. [frontend/.env.local.example](frontend/.env.local.example).
- **Railway (backend + Chroma).** Backend built from
  [backend/Dockerfile](backend/Dockerfile) (root build context, `COPY backend/`);
  CPU-only PyTorch installed first to avoid the multi-GB CUDA stack. Chroma runs as
  a separate Railway service (`chromadb/chroma`) with a **persistent volume at
  `/data`**; the backend talks to it over the private network
  (`CHROMA_USE_HTTP_CLIENT=true`, `CHROMA_HOST`, `CHROMA_PORT`).
- **Supabase.** Managed; provides JWTs the backend verifies.
- **LLM.** Gemini API over HTTPS; no Ollama in production.
- **Environment variables.** Production template:
  [deployment/production.env.example](deployment/production.env.example) (backend),
  [frontend/.env.local.example](frontend/.env.local.example) (frontend). Full
  catalogue in [.env.example](.env.example).
- **Frontend/backend communication.** Browser → `NEXT_PUBLIC_API_BASE`
  (`https://<railway-backend>/api/v1`) with the Supabase JWT.
- **Production URLs.** Templated (`https://<your-app>.vercel.app`,
  `https://<railway-backend>`); the exact live URLs are deployment-specific and not
  committed.
- **CORS handling** ([backend/app/main.py](backend/app/main.py),
  [config.py](backend/app/core/config.py)): exact-match `CORS_ORIGINS` (no trailing
  slash) + optional `CORS_ORIGIN_REGEX` for Vercel preview hosts; wildcard `*`
  auto-disables credentials. Startup warns if production has no non-local origin
  ([startup.py](backend/app/core/startup.py)).
- **Containers.** [backend/Dockerfile](backend/Dockerfile) (multi-stage, non-root,
  healthcheck, [docker-entrypoint.sh](backend/docker-entrypoint.sh)),
  [frontend/Dockerfile](frontend/Dockerfile) (Next.js `output: "standalone"`),
  and [docker-compose.local.yml](docker-compose.local.yml) /
  [docker-compose.production.yml](docker-compose.production.yml) for self-hosting.

---

## SECTION 14 — LOCAL VS PRODUCTION DIFFERENCES

The **only** code-level switch is environment configuration; application code is
identical.

| Concern | Local (MODE A) | Production (MODE B) |
|---|---|---|
| LLM | Ollama on host (`qwen3`, `llama3.1`, `llama-guard3`) | **Gemini API** (`gemini-2.5-flash`) |
| `LLM_PROVIDER` | `ollama` (default) | `gemini` |
| Embeddings | `hashing` (light) or `bge` | `bge` (`BAAI/bge-small-en-v1.5`) |
| Vector store | `memory` or local Chroma | Chroma container + volume |
| Reranker | `lexical` (or `bge`) | `lexical` by default (BGE optional, memory-gated) |
| PII | `regex` (light) or Presidio | Presidio (`en_core_web_sm`) |
| Input guard | heuristic or LlamaGuard3 | Gemini classifier (model guard) |
| Cache backend | `memory` | `gptcache` configured (lookups still exact-key — see §10) |
| Tracing | recorder only | recorder only by default (Phoenix optional, off) |
| Auth | HS256 dev token or Supabase | Supabase (HS256 secret and/or JWKS) |
| Evaluation | run harness locally | static baked `offline_lexical` report |
| Storage durability | in-process / local volume | Chroma volume persists; **registry + BM25 + metrics in-process (ephemeral)** |

**Performance considerations.** Heavy models (BGE embedder/reranker, Presidio) are
**lazy-loaded** on first use and load into RAM on CPU (fp32). Production defaults
are sized for a memory-constrained host (bge-small + lexical reranker) to avoid
OOM-kills ([deployment/production.env.example](deployment/production.env.example),
[config.py](backend/app/core/config.py)). Understanding is heuristic to remove an
LLM round-trip; only reasoning (and optionally the guard) call Gemini.

**Key file references:** [backend/app/core/config.py](backend/app/core/config.py),
[backend/app/llm/factory.py](backend/app/llm/factory.py),
[docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md).

---

## SECTION 15 — ENGINEERING DECISIONS

- **FastAPI** — async, Pydantic-native validation, dependency injection (used for
  the auth→tenant→rate-limit chain), and auto OpenAPI docs
  ([backend/app/main.py](backend/app/main.py), [deps.py](backend/app/api/deps.py)).
- **Next.js** — App Router + native Vercel deploys; client-side pages with a thin
  typed API client ([frontend/lib/api.ts](frontend/lib/api.ts)).
- **Supabase** — managed JWT auth without running an auth server; the backend only
  needs to verify tokens (PyJWT), keeping it dependency-light
  ([backend/app/auth/supabase.py](backend/app/auth/supabase.py)).
- **Gemini (production LLM)** — hosted, no GPU needed, REST-only client (no SDK),
  and a free tier suitable for a demo; integrated behind the same `LLMClient`
  contract as Ollama ([gemini_client.py](backend/app/llm/gemini_client.py)).
- **Railway (backend + Chroma)** — container hosting with a persistent volume for
  Chroma; CPU-only, so the image installs CPU PyTorch
  ([backend/Dockerfile](backend/Dockerfile), [docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md) §G).
- **Vercel (frontend)** — first-class Next.js hosting; preview deploys handled via
  the CORS regex.
- **Hybrid retrieval (dense + BM25 + RRF + rerank)** — legal QA needs both semantic
  recall and exact-term precision; RRF avoids combining incompatible score scales
  ([fusion.py](backend/app/retrieval/fusion.py), [pipeline.py](backend/app/retrieval/pipeline.py)).
- **In-process observability** — an always-on recorder/cost-meter gives latency,
  cache, and cost visibility with **no extra service** to deploy; Phoenix export is
  optional ([tracing.py](backend/app/observability/tracing.py)).
- **In-process cost metering** — estimated spend is informational and needs no
  billing integration; it's a simple thread-safe accumulator
  ([cost.py](backend/app/observability/cost.py)).
- **Evaluation as it is** — a dependency-free lexical harness guarantees a report
  always exists for the dashboard; RAGAS/DeepEval are kept as optional offline
  runners because their dependency trees conflict with the runtime and (for
  model-judged metrics) require a judge LLM/quota
  ([evaluation/](evaluation/), [requirements-eval.txt](backend/requirements-eval.txt)).
- **Protocol + light fallback everywhere** — lets the whole system run and be
  tested offline, and lets production swap in heavy backends by config only
  (embeddings, vector store, reranker, PII, guard, LLM).

---

## SECTION 16 — CHALLENGES, CONSTRAINTS, AND PIVOTS

All items below are grounded in code/doc evidence in this repository.

**Dependency-resolution constraints (verified).**
[backend/requirements.txt](backend/requirements.txt) documents that a single
combined requirements file was **unresolvable**: RAGAS/DeepEval pull
langchain-community/-openai, openai, datasets, and a newer pydantic that conflict
with the runtime pins. **Pivot:** split into runtime
([requirements.txt](backend/requirements.txt)), offline eval
([requirements-eval.txt](backend/requirements-eval.txt), installed in a *separate*
venv), and a minimal Phase-1 set ([requirements-phase1.txt](backend/requirements-phase1.txt)).

**Railway / Presidio filesystem constraint (verified).**
[backend/app/safety/pii.py](backend/app/safety/pii.py) and
[backend/requirements.txt](backend/requirements.txt) document that Presidio's
default `AnalyzerEngine` tries to `spacy download en_core_web_lg` **at runtime**,
which on Railway writes into the root-owned `/opt/venv` while running as non-root
`appuser` → "Permission denied" → crashed upload worker. **Fixes:** pin
`en_core_web_sm` at **build time** and pin the model via
`SAFETY_PRESIDIO_SPACY_MODEL`; the detector also degrades to the regex backend
instead of crashing.

**Memory constraints / model sizing (verified).**
[deployment/production.env.example](deployment/production.env.example) and
[config.py](backend/app/core/config.py) document that loading a model larger than
the service's RAM limit gets the container **OOM-killed** (silent restart). **Pivot:**
defaults are bge-small + the zero-model lexical reranker; larger BGE models are
opt-in with a memory table in the env example.

**Gemini free-tier constraints (verified).**
[evaluation/run_deepeval.py](evaluation/run_deepeval.py) documents Gemini's free
tier (~5 req/min, ~20/day, intermittent 503). **Workarounds:** throttle judge calls
(`GEMINI_MIN_INTERVAL_SECONDS`), exponential-backoff retries on transient errors,
cap samples (`DEEPEVAL_MAX_SAMPLES=3`), hallucination metric off by default, and
**fail fast** on per-day quota exhaustion. **Impact on evaluation strategy:** the
deployed dashboard uses the offline-lexical evaluator (no judge LLM), with
RAGAS/DeepEval as optional offline runs.

**Model-hosting pivot (verified by config/docs).** The system was built
**local-first with Ollama** (`qwen3`/`llama3.1`/`llama-guard3`) — still the default
`LLM_PROVIDER=ollama`. For production it switches to the **hosted Gemini API**
because Railway runs **CPU-only, no GPU** ([docs/DEPLOYMENT_ARCHITECTURE.md](docs/DEPLOYMENT_ARCHITECTURE.md)
§G), making self-hosted LLM inference impractical there. The provider abstraction
([factory.py](backend/app/llm/factory.py)) made this a one-variable change.
*(The specific local hardware used during development is not recorded in the
codebase and is therefore not asserted here.)*

**Storage constraints (verified).** The document catalog
([document_registry.py](backend/app/services/document_registry.py)) and the BM25
index ([sparse.py](backend/app/retrieval/sparse.py)) are **in-memory and
process-local**, explicitly noted as "a production deployment would back it with
the application database / persist the corpus." **Tradeoff:** Chroma vectors
persist on the Railway volume, but the document **list** and BM25 index are lost on
a backend restart (sparse retrieval degrades until re-ingest). Conversation history
is client-side only ([chatHistory.ts](frontend/lib/chatHistory.ts)).

**Evaluation constraints (verified).** RAGAS/DeepEval dependency conflicts (above)
+ judge-model availability mean canonical model-judged metrics are not run inline.
The **deployed** solution is the deterministic offline-lexical report
([evaluation/results/latest.json](evaluation/results/latest.json)). The eval path
also had to be made robust on Railway: a relative `../evaluation` default resolved
to `/evaluation` (absent in the image) and left the dashboard empty; **fix:** a
multi-path resolver + a report baked under `backend/evaluation/`
([config.py](backend/app/core/config.py), [evaluation.py](backend/app/api/v1/routes/evaluation.py),
[.dockerignore](.dockerignore)).

**Observability constraints (verified).** Phoenix tracing is implemented as an
optional OTLP exporter but is **off by default in production** and requires a
reachable external collector ([tracing.py](backend/app/observability/tracing.py),
[deployment/production.env.example](deployment/production.env.example)). **Decision:**
ship an always-on in-process recorder so latency/cache/cost are visible with no
extra service.

**Semantic-cache constraint (verified).** GPTCache (embedding-similarity) is
scaffolded but not wired into cache lookups; the active cache is an exact
normalized-key LRU ([semantic_cache.py](backend/app/cache/semantic_cache.py)). True
semantic caching remains a future item.

**Deployment debugging (verified by code intent).** CORS preflight 400s (trailing
slash / wrong origin / Vercel previews) drove the origin normalization + regex +
startup warnings ([config.py](backend/app/core/config.py),
[main.py](backend/app/main.py), [startup.py](backend/app/core/startup.py)). JWT
"alg not allowed" errors (Supabase issuing ES256) drove per-mode algorithm scoping
([supabase.py](backend/app/auth/supabase.py)). A dedicated retrieval-debug endpoint
([debug.py](backend/app/api/v1/routes/debug.py)) was added to locate where context
"drops to zero".

**Engineering tradeoffs — planned vs shipped.**
- *Planned:* DB-backed document registry + persistent BM25. *Shipped:* in-memory.
- *Planned:* true semantic cache. *Shipped:* exact-key LRU.
- *Planned:* live RAGAS/DeepEval. *Shipped:* offline-lexical static report.
- *Planned:* BGE cross-encoder reranker in prod. *Shipped:* lexical reranker by
  default (BGE opt-in).
- *Planned:* Phoenix tracing in prod. *Shipped:* in-process recorder; Phoenix
  optional.

---

## SECTION 17 — FINAL FEATURE MATRIX

| Feature | Implemented? | Production status | Files | Notes |
|---|---|---|---|---|
| Supabase JWT auth (HS256 + JWKS) | ✅ | Active | [auth/supabase.py](backend/app/auth/supabase.py) | alg-family scoping; tenant from `app_metadata` |
| Multi-tenancy / isolation | ✅ | Active | [deps.py](backend/app/api/deps.py), [vector_store.py](backend/app/retrieval/vector_store.py) | tenant filter on store/BM25/registry |
| Rate limiting (user + tenant) | ✅ | Active (memory) | [rate_limiter.py](backend/app/services/rate_limiter.py) | Redis configurable, not deployed |
| Document upload (PDF/DOCX/TXT) | ✅ | Active | [documents.py](backend/app/api/v1/routes/documents.py), [loaders.py](backend/app/ingestion/loaders.py) | 25 MB cap |
| Legal-aware chunking | ✅ | Active | [chunking.py](backend/app/ingestion/chunking.py) | section/clause/heading/page metadata |
| Dense embeddings (BGE) | ✅ | Active | [embeddings.py](backend/app/retrieval/embeddings.py) | bge-small in prod; hashing fallback |
| Sparse BM25 | ✅ | Active (in-memory) | [sparse.py](backend/app/retrieval/sparse.py) | lost on restart |
| RRF fusion | ✅ | Active | [fusion.py](backend/app/retrieval/fusion.py) | |
| Compression (dedup) | ✅ | Active | [compression.py](backend/app/retrieval/compression.py) | |
| Reranking | ✅ (both) | Lexical default; BGE opt-in | [reranker.py](backend/app/retrieval/reranker.py) | BGE off by default (memory) |
| Vector store (Chroma) | ✅ | Active + volume | [vector_store.py](backend/app/retrieval/vector_store.py) | in-memory fallback |
| 8-agent + guard workflow | ✅ | Active | [agents/graph.py](backend/app/agents/graph.py) | LangGraph or sequential |
| Query understanding | ✅ | Heuristic by default | [query_understanding.py](backend/app/agents/query_understanding.py) | LLM path optional |
| LLM reasoning (Gemini) | ✅ | Active | [reasoning.py](backend/app/agents/reasoning.py), [gemini_client.py](backend/app/llm/gemini_client.py) | extractive fallback |
| Citations | ✅ | Active | [citation.py](backend/app/agents/citation.py) | from `[S#]` tags |
| Confidence (explainable) | ✅ | Active | [confidence.py](backend/app/agents/confidence.py) | weighted breakdown |
| Groundedness/output safety | ✅ | Active | [output_safety.py](backend/app/safety/output_safety.py) | lexical grounding |
| Input safety guard | ✅ | Active | [input_safety.py](backend/app/safety/input_safety.py) | model guard + heuristic |
| PII masking (Presidio) | ✅ | Active | [pii.py](backend/app/safety/pii.py) | regex fallback; ingest/query/output |
| Provider abstraction (Ollama/Gemini) | ✅ | Active | [factory.py](backend/app/llm/factory.py), [provider.py](backend/app/llm/provider.py) | one-var switch |
| LLM primary/fallback routing | ✅ | Active | [provider.py](backend/app/llm/provider.py) | same model by default in prod |
| In-process tracing/latency | ✅ | Active | [tracing.py](backend/app/observability/tracing.py) | ring buffer |
| Cost metering | ✅ | Active | [cost.py](backend/app/observability/cost.py) | Gemini pricing, process-local |
| Phoenix/OTLP export | ⚠️ Partial | Off by default | [tracing.py](backend/app/observability/tracing.py) | needs external collector |
| Semantic cache (similarity) | ⚠️ Partial | Exact-key LRU active | [semantic_cache.py](backend/app/cache/semantic_cache.py) | GPTCache not in lookup path |
| Document registry | ✅ (in-memory) | Ephemeral | [document_registry.py](backend/app/services/document_registry.py) | DB-backed = planned |
| Chat history | ✅ (client) | Active (localStorage) | [chatHistory.ts](frontend/lib/chatHistory.ts) | not server-persisted |
| Evaluation dashboard | ✅ | Active (offline_lexical) | [evaluation.py](backend/app/api/v1/routes/evaluation.py), [evaluation/](evaluation/) | static baked report |
| RAGAS / DeepEval | ✅ (offline) | Not in deployed service | [run_ragas.py](evaluation/run_ragas.py), [run_deepeval.py](evaluation/run_deepeval.py) | DeepEval judge = Gemini |
| Retrieval debug endpoint | ✅ | Active | [debug.py](backend/app/api/v1/routes/debug.py) | stage-by-stage diagnostics |

---

## SECTION 18 — KNOWN LIMITATIONS

1. **Cache is not semantically matched** — exact normalized-key LRU only; GPTCache
   similarity is not wired into lookups ([semantic_cache.py](backend/app/cache/semantic_cache.py)).
2. **Ephemeral in-process state** — document registry, BM25 index, traces, cost,
   and cache all reset on backend restart and are not shared across replicas
   ([document_registry.py](backend/app/services/document_registry.py),
   [sparse.py](backend/app/retrieval/sparse.py),
   [tracing.py](backend/app/observability/tracing.py)). Only Chroma vectors persist.
3. **Evaluation is lexical + small + static** — deployed metrics are token-overlap
   approximations over 5 samples using the **light/extractive** pipeline, not
   model-judged RAGAS/DeepEval over the production stack
   ([offline_metrics.py](evaluation/offline_metrics.py),
   [_harness.py](evaluation/_harness.py)).
4. **Production reranker is lexical by default** — the BGE cross-encoder is
   implemented but off by default for memory reasons
   ([deployment/production.env.example](deployment/production.env.example)).
5. **Groundedness/output safety are lexical** — token-overlap thresholds, not a
   model-based entailment check ([output_safety.py](backend/app/safety/output_safety.py)).
6. **No frontend route guards** — protection is API-side; pages render without a
   token but cannot fetch data ([frontend/lib/auth.tsx](frontend/lib/auth.tsx)).
7. **No streaming** — `/chat` is a single blocking request; the UI shows a faux
   staged "thinking" indicator ([frontend/app/chat/page.tsx](frontend/app/chat/page.tsx)).
8. **Phoenix tracing not active in production** by default
   ([deployment/production.env.example](deployment/production.env.example)).
9. **Free-tier LLM limits** can throttle/deny Gemini calls; the system degrades to
   extractive answers when the LLM is unavailable
   ([runtime.py](backend/app/llm/runtime.py), [reasoning.py](backend/app/agents/reasoning.py)).
10. **No token refresh** — the frontend stores a single access token in
    `localStorage` ([frontend/lib/auth.tsx](frontend/lib/auth.tsx)).

---

## SECTION 19 — FUTURE IMPROVEMENTS

(All are supported/foreshadowed by the codebase.)
- **Phoenix tracing in production** — enable the existing OTLP exporter against a
  deployed collector ([tracing.py](backend/app/observability/tracing.py)).
- **True semantic cache** — wire GPTCache embedding-similarity into
  `SemanticCache.get/set` ([semantic_cache.py](backend/app/cache/semantic_cache.py)).
- **Persistent metrics + cost** — externalize the in-process recorder/meter to a
  store so they survive restarts and span replicas.
- **DB-backed document registry + persistent BM25** — replace the in-memory
  catalog/index (Supabase/Postgres or an inverted-index service) as the code
  comments anticipate ([document_registry.py](backend/app/services/document_registry.py),
  [sparse.py](backend/app/retrieval/sparse.py)).
- **Production RAGAS / DeepEval** — run the existing offline runners as a scheduled
  job and publish their report to the dashboard
  ([run_ragas.py](evaluation/run_ragas.py), [run_deepeval.py](evaluation/run_deepeval.py)).
- **BGE cross-encoder reranking in prod** — enable on a larger instance
  (`RETRIEVAL_RERANKER_BACKEND=bge`).
- **LLM-based groundedness** — add a model entailment check on top of the lexical
  backstop (the Groundedness agent is the natural seam).
- **Answer streaming** — stream `/chat` tokens to replace the simulated indicator.
- **Multi-tenant hardening** — the tenant plumbing exists; add tenant-scoped
  persistence and admin tooling.
- **Additional legal workflows** — the planner already maps intents to workflows
  ([planner.py](backend/app/agents/planner.py)); add intent-specific retrieval/tools.

---

## SECTION 20 — PROJECT SUMMARY

**Technical summary.** LexAegis AI is a full-stack agentic RAG platform for legal
documents: a Next.js/Vercel frontend, a FastAPI/Railway backend, Supabase JWT auth,
ChromaDB vectors, and Gemini 2.5 Flash reasoning. A LangGraph workflow (input guard
+ 8 agents) runs over a hybrid retrieval pipeline (BGE dense + BM25 sparse → RRF →
compression → rerank) and returns grounded, cited, confidence-scored answers with
input/output safety and PII masking.

**Architecture summary.** Six layers — Ingress, Safety, Retrieval, Generation,
Evaluation, Observability — built on a Protocol + light-fallback pattern so every
heavy component has a deterministic offline substitute, and a provider abstraction
that switches Ollama↔Gemini by one environment variable with no code change.

**Production readiness summary.** The core path (auth → upload → ingest →
retrieve → reason → cite → validate) is implemented and deployed. The system
degrades gracefully when the LLM or heavy backends are unavailable. Validated:
**95 backend tests pass**; the frontend builds; all production-critical files and
deploy configs are intact. Honest caveats: ephemeral in-process state (registry,
BM25, metrics), lexical (not model-judged) evaluation, lexical default reranker,
and an exact-key (not similarity) cache.

**Lessons learned (evidence-based).** Dependency-tree conflicts forced a split
requirements strategy; PaaS constraints (CPU-only, ephemeral FS, read-only venv,
free-tier quotas) shaped the model choices, the Presidio build-time pin, and the
evaluation strategy; CORS/JWT-algorithm mismatches drove defensive ingress
handling.

**Key accomplishments.** A genuinely offline-runnable, fully-typed agentic RAG
system with grounded citations, explainable confidence, layered safety, and built-
in observability/cost — deployed across Vercel + Railway + Supabase + Gemini with a
single-variable local↔production switch.

**Final system status.** Live and working in production; documented limitations are
known and tracked as future improvements above.

---

### Verified fact appendix (defaults, for diagrams/slides)

- Intents (7): contract_review, clause_comparison, compliance_check, policy_lookup,
  regulation_search, legal_risk_analysis, document_summary
  ([state.py](backend/app/agents/state.py)).
- Retrieval defaults: dense_top_k 20, sparse_top_k 20, rrf_k 60, rerank_top_k 8,
  final_top_k 5, dedup_threshold 0.95 ([config.py](backend/app/core/config.py)).
- Chunking: max 1200 chars, overlap 150 ([config.py](backend/app/core/config.py)).
- Confidence weights: retrieval 0.20, reranker 0.25, source_agreement 0.15,
  citation_coverage 0.20, groundedness 0.20 ([confidence.py](backend/app/agents/confidence.py)).
- Rate limits: 120/min per user, 1200/min per tenant, burst ×1.5
  ([config.py](backend/app/core/config.py)).
- Upload: PDF/DOCX/TXT, ≤25 MB ([documents.py](backend/app/api/v1/routes/documents.py)).
- Cost pricing (Gemini 2.5 Flash, default): $0.30 / 1M input, $2.50 / 1M output
  ([config.py](backend/app/core/config.py)).
- Output-safety gate: min citation coverage 0.5; block on PII leak
  ([config.py](backend/app/core/config.py)).
- Graph nodes (9): guard, query_understanding, planner, retrieval, reasoning,
  citation, groundedness, confidence, output_safety
  ([graph.py](backend/app/agents/graph.py)).
