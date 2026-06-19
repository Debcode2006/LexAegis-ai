# Observability Guide

Observability spans two modules: `app/observability` (tracing) and `app/cache`
(semantic caching). Both are always available and degrade gracefully.

## Tracing (`observability/tracing.py`)

Two layers:

1. **OpenTelemetry → Arize Phoenix (production).** When `arize-phoenix` + OTel
   are installed and `OBSERVABILITY_ENABLE_TRACING=true`, `init_observability()`
   registers an OTLP exporter to `OBSERVABILITY_OTLP_ENDPOINT`. Spans follow
   OpenInference conventions.
2. **In-process span recorder (always on).** Every `span()` is recorded in a
   bounded ring buffer (`OBSERVABILITY_TRACE_BUFFER_SIZE`) with its duration and
   attributes — inspectable locally even without Phoenix.

### The `span` primitive

```python
from app.observability.tracing import span

with span("chat.turn", {"tenant_id": tid}) as attrs:
    ...
    attrs["confidence"] = 0.82      # attributes attached to the span
```

### What is traced
- `chat.turn` — the whole turn (tenant, intent, confidence, retrieved count).
- `agent.<name>` — each of the 9 graph nodes (latency per agent).

### Inspecting locally
```
GET /api/v1/observability/traces?limit=50   → recent spans
GET /api/v1/observability/metrics           → cache + trace summary
```

The summary aggregates count, average latency, and per-span-name stats. See
[PHOENIX_SETUP](PHOENIX_SETUP.md) to view traces in the Phoenix UI.

## Semantic caching (`cache/semantic_cache.py`)

Caches expensive outputs keyed by a normalized, namespaced query.

| Backend | When | Behavior |
|---|---|---|
| `memory` | light/local/test | bounded LRU, normalized-string keys |
| `gptcache` | production | embedding-similarity matching |
| `off` | disabled | no-op |

Cached:
- **LLM outputs** — in `LLMProvider.chat` (namespace `llm`).
- **Chat responses** — in `ChatService.answer` (namespace `chat`).

(Embedding caching can be layered the same way; the cache is generic.)

### Metrics
`SemanticCache.stats()` exposes `enabled`, `backend`, `entries`, `hits`,
`misses`, `hit_rate`. Surfaced at `/observability/metrics` and on the dashboard.

### Config
```
OBSERVABILITY_ENABLE_SEMANTIC_CACHE=true
OBSERVABILITY_CACHE_BACKEND=memory          # memory | gptcache | off
OBSERVABILITY_CACHE_SIMILARITY_THRESHOLD=0.92
OBSERVABILITY_CACHE_MAX_ENTRIES=1000
OBSERVABILITY_GPTCACHE_DIR=./.data/gptcache
```

## Logging
Structured logs carry the `request_id` correlation id (set by the request-context
middleware), so logs, spans, and responses can be stitched together.
