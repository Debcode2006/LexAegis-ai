"""
Structured logging setup.

Provides JSON-structured logs (production) or human-readable logs (local dev),
both enriched with a per-request correlation id pulled from a contextvar. This
gives every log line a `request_id` so traces can be stitched together across
middleware, services, and (later) agent steps.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.config import get_settings

# Correlation id propagated through the request lifecycle.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Merge any structured extras attached via `logger.info(..., extra={...})`.
        for key, value in record.__dict__.items():
            if key.startswith("ctx_"):
                payload[key[4:]] = value

        return json.dumps(payload, default=str)


class HumanFormatter(logging.Formatter):
    """Readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_ctx.get()
        base = f"{datetime.now(timezone.utc).strftime('%H:%M:%S')} | {record.levelname:<8} | {rid} | {record.name} | {record.getMessage()}"
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def configure_logging() -> None:
    """Configure the root logger according to application settings.

    Idempotent: safe to call multiple times (handlers are reset each call).
    """

    settings = get_settings()
    root = logging.getLogger()
    root.setLevel(settings.log_level.value)

    # Reset existing handlers so reloads don't duplicate output.
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_json else HumanFormatter())
    root.addHandler(handler)

    # Tame noisy third-party loggers.
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger."""

    return logging.getLogger(name)
