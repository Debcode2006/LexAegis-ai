# Architecture

LexAegis AI is organized as **six cooperating layers**. Each layer is a clear
module boundary in `backend/app`, and each external dependency sits behind a
Protocol so a light local implementation and a production implementation are
interchangeable by configuration.

## The six layers

### Layer 1 — Ingress (`app/api`, `app/auth`, `app/middleware`, `app/services/rate_limiter.py`)
- FastAPI gateway and routing.
- Supabase JWT verification (HS256 secret or RS256/JWKS).
- Request validation, per-request correlation id, structured access logs.
- Tenant routing + isolation (JWT `app_metadata.tenant_id`, reconciled with the
  `X-Tenant-ID` header).
- Token-bucket rate limiting — **per-user and per-tenant** (both must pass).

### Layer 2 — Safety (`app/safety`)
- **Input safety** (LlamaGuard / heuristic): prompt injection, jailbreak, unsafe
  request detection.
- **PII** (Presidio / regex): detection + masking at ingestion, query, and
  output time. Includes Indian identifiers (PAN, Aadhaar, Passport).
- **Output safety**: groundedness, citation coverage, unsupported-claim, and PII
  leakage checks before any answer is released.

### Layer 3 — Retrieval (`app/ingestion`, `app/retrieval`)
- Loaders: PDF / DOCX / TXT (page-preserving).
- Legal-aware chunking: section / clause / heading detection with metadata.
- Dense retrieval: BGE embeddings + ChromaDB.
- Sparse retrieval: BM25, per tenant.
- Fusion: Reciprocal Rank Fusion (RRF).
- Compression: near-duplicate removal.
- Reranking: BGE cross-encoder.

### Layer 4 — Generation & Orchestration (`app/agents`, `app/llm`)
- LangGraph `StateGraph` wiring **8 agents**:
  Query Understanding → Planner → Retrieval → Legal Reasoning → Citation →
  Groundedness → Confidence → Output Safety, fronted by an Input Guard node.
- LLM abstraction: Qwen3 primary, Llama 3.1 fallback, via Ollama.

### Layer 5 — Quality & Evaluation (`evaluation/`)
- RAGAS (Faithfulness, Answer Relevancy, Context Precision/Recall).
- DeepEval (Groundedness, Hallucination, Answer Quality).
- Sample legal benchmark + an offline lexical evaluator that always runs locally.

### Layer 6 — Observability & Operations (`app/observability`, `app/cache`)
- Arize Phoenix + OpenInference tracing (OTLP exporter) with an always-on
  in-process span recorder.
- GPTCache semantic caching of LLM and chat outputs, with hit/miss metrics.

## Request lifecycle (a `/chat` call)

```
HTTP → middleware (req-id, CORS, tenant)
     → deps: rate limit + JWT verify + tenant reconcile
     → ChatService (span + response cache)
     → LegalAgentWorkflow (LangGraph)
         guard → query_understanding → planner → retrieval
              → reasoning → citation → groundedness → confidence → output_safety
     → ChatResponse (answer, intent, citations, confidence, groundedness)
```

## Design principles

1. **Config is the only switch.** `app/core/config.py` is the single source of
   truth; nothing reads `os.environ` directly. Backend selection (light vs.
   production) is purely configuration.
2. **Protocols + fallbacks.** Every heavy dependency has a `Protocol` and two
   implementations. The system is always runnable.
3. **Tenant isolation everywhere.** Dense and sparse retrieval both filter on
   `tenant_id`; the API rejects cross-tenant access.
4. **Grounded by construction.** Reasoning answers only from retrieved context;
   an always-on output gate blocks ungrounded or PII-leaking answers.
5. **Observable by default.** Every agent step is a span; latency and key
   attributes are recorded even without Phoenix.

See [BACKEND_GUIDE](BACKEND_GUIDE.md) for module-level detail.
