"""
Lightweight in-process cost metering.

Aggregates token usage from real LLM calls and converts it to an estimated USD
cost using Gemini 2.5 Flash list pricing (configurable). Like `TraceRecorder`,
this is an always-on, process-local accumulator — no database, no Phoenix, no
external billing dependency. Values are exposed on `/observability/metrics`.

Only actual model invocations are metered; cache hits (which make no API call)
must not be recorded.
"""

from __future__ import annotations

import threading
from typing import Any, Dict

from app.core.config import get_settings


class CostMeter:
    """Thread-safe running total of tokens and estimated cost."""

    def __init__(self) -> None:
        cfg = get_settings().observability
        self._input_per_token = cfg.cost_input_per_million / 1_000_000.0
        self._output_per_token = cfg.cost_output_per_million / 1_000_000.0
        self._lock = threading.Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._cost_usd = 0.0
        self._calls = 0

    def record(self, prompt_tokens: int, completion_tokens: int) -> None:
        """Accumulate one real LLM call's usage into the running totals."""

        cost = (
            prompt_tokens * self._input_per_token
            + completion_tokens * self._output_per_token
        )
        with self._lock:
            self._prompt_tokens += prompt_tokens
            self._completion_tokens += completion_tokens
            self._cost_usd += cost
            self._calls += 1

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "calls": self._calls,
                "total_prompt_tokens": self._prompt_tokens,
                "total_completion_tokens": self._completion_tokens,
                "total_tokens": self._prompt_tokens + self._completion_tokens,
                "total_cost_usd": round(self._cost_usd, 6),
            }

    def reset(self) -> None:
        with self._lock:
            self._prompt_tokens = 0
            self._completion_tokens = 0
            self._cost_usd = 0.0
            self._calls = 0


_meter: "CostMeter | None" = None


def get_cost_meter() -> CostMeter:
    global _meter
    if _meter is None:
        _meter = CostMeter()
    return _meter
