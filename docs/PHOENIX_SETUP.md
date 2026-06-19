# Phoenix Setup

Arize Phoenix is the tracing UI. LexAegis exports OpenTelemetry spans
(OpenInference conventions) to Phoenix. Without Phoenix, the in-process span
recorder still gives you latency and attributes via the API.

## 1. Install & run Phoenix

```bash
pip install arize-phoenix \
            opentelemetry-sdk \
            opentelemetry-exporter-otlp \
            openinference-instrumentation

# Launch the Phoenix UI + collector
python -m phoenix.server.main serve
# UI at http://localhost:6006
```

(Phoenix can also be started in-process via `phoenix.launch_app()` in a notebook.)

## 2. Backend `.env`

```
OBSERVABILITY_ENABLE_TRACING=true
OBSERVABILITY_PHOENIX_ENDPOINT=http://localhost:6006
OBSERVABILITY_OTLP_ENDPOINT=http://localhost:6006/v1/traces
OBSERVABILITY_SERVICE_NAME=lexaegis-ai
```

## 3. How it works

- On startup (`app/main.py` lifespan), `init_observability()` registers a
  `TracerProvider` with a `BatchSpanProcessor` → `OTLPSpanExporter` pointed at
  `OBSERVABILITY_OTLP_ENDPOINT`. If OTel/Phoenix aren't installed, it logs and
  continues with the recorder only.
- The `span()` context manager (`app/observability/tracing.py`) creates a real
  OTel span **and** records it locally.
- Traced units: `chat.turn` and each `agent.<name>` node.

## 4. What you'll see in Phoenix
- Per-turn traces with child spans for every agent.
- Latency for retrieval, reasoning, reranking, etc.
- Span attributes: tenant, intent, confidence, retrieved count.

## 5. Local inspection without Phoenix

```
GET /api/v1/observability/traces?limit=50
GET /api/v1/observability/metrics
```

These return recent spans and a summary (count, avg latency, per-span stats) plus
cache hit/miss metrics — handy in CI and quick local checks.

## 6. OpenInference
Install `openinference-instrumentation` (and framework-specific packages) to
enrich spans with standardized GenAI attributes. The exporter and conventions are
compatible with Phoenix's LLM trace views.

See [OBSERVABILITY_GUIDE](OBSERVABILITY_GUIDE.md) for the full picture.
