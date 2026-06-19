"""
Tracing and observability.

Two layers, both always available:

1. An **OpenTelemetry / Arize Phoenix** exporter (production). When
   `arize-phoenix` + OTel are installed and tracing is enabled, spans are
   exported to Phoenix via OTLP and follow OpenInference semantic conventions.

2. An always-on **in-process span recorder**. Every `span()` is also recorded in
   a bounded ring buffer with its duration and attributes, so latency, reranker
   scores, confidence, and agent timings are inspectable locally via
   `/api/v1/observability/traces` even without Phoenix running.

The `span(name, attributes)` context manager is the single instrumentation
primitive used across the codebase; it degrades gracefully to the recorder-only
path if OTel is unavailable.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any, Deque, Dict, Iterator, List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger, request_id_ctx

logger = get_logger(__name__)


class TraceRecorder:
    """Bounded in-memory store of recent spans for local inspection."""

    def __init__(self, maxlen: int) -> None:
        self._spans: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def record(self, span: Dict[str, Any]) -> None:
        with self._lock:
            self._spans.append(span)

    def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._spans)[-limit:][::-1]

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            spans = list(self._spans)
        if not spans:
            return {"count": 0, "avg_latency_ms": 0.0, "by_name": {}}
        by_name: Dict[str, List[float]] = {}
        for s in spans:
            by_name.setdefault(s["name"], []).append(s["duration_ms"])
        return {
            "count": len(spans),
            "avg_latency_ms": round(sum(s["duration_ms"] for s in spans) / len(spans), 2),
            "by_name": {
                name: {
                    "count": len(values),
                    "avg_ms": round(sum(values) / len(values), 2),
                    "max_ms": round(max(values), 2),
                }
                for name, values in by_name.items()
            },
        }

    def reset(self) -> None:
        with self._lock:
            self._spans.clear()


_recorder: Optional[TraceRecorder] = None
_otel_tracer = None
_otel_initialized = False


def get_trace_recorder() -> TraceRecorder:
    global _recorder
    if _recorder is None:
        _recorder = TraceRecorder(get_settings().observability.trace_buffer_size)
    return _recorder


def init_observability() -> bool:
    """Initialize the OTel/Phoenix exporter if available. Returns True if active."""

    global _otel_tracer, _otel_initialized
    if _otel_initialized:
        return _otel_tracer is not None

    _otel_initialized = True
    cfg = get_settings().observability
    if not cfg.enable_tracing:
        logger.info("Tracing disabled by configuration.")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.info("OpenTelemetry not installed; using in-process recorder only.")
        return False

    try:
        provider = TracerProvider(resource=Resource.create({"service.name": cfg.service_name}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=cfg.otlp_endpoint))
        )
        trace.set_tracer_provider(provider)
        _otel_tracer = trace.get_tracer(cfg.service_name)
        logger.info("Tracing exporting to Phoenix at %s", cfg.otlp_endpoint)
        return True
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.warning("Failed to initialize OTel exporter: %s", exc)
        _otel_tracer = None
        return False


@contextmanager
def span(name: str, attributes: Optional[Dict[str, Any]] = None) -> Iterator[Dict[str, Any]]:
    """Context manager that times a unit of work and records it.

    Yields a mutable dict; set extra attributes on it inside the block.
    """

    attrs: Dict[str, Any] = dict(attributes or {})
    start = time.perf_counter()
    otel_span_cm = None
    otel_span = None
    if _otel_tracer is not None:
        otel_span_cm = _otel_tracer.start_as_current_span(name)
        otel_span = otel_span_cm.__enter__()

    try:
        yield attrs
    finally:
        duration_ms = (time.perf_counter() - start) * 1000.0
        if otel_span is not None:
            try:
                for key, value in attrs.items():
                    otel_span.set_attribute(key, value)
            except Exception:  # pragma: no cover
                pass
            otel_span_cm.__exit__(None, None, None)
        get_trace_recorder().record(
            {
                "name": name,
                "duration_ms": round(duration_ms, 2),
                "request_id": request_id_ctx.get(),
                "attributes": attrs,
            }
        )
