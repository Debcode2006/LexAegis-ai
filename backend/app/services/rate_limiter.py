"""
Rate limiting service.

Implements a token-bucket limiter behind an abstract `RateLimiter` interface so
the storage backend can be swapped (in-memory now, Redis later) without touching
call sites. The limiter is consulted for two independent buckets per request:

- a per-user bucket, and
- a per-tenant bucket.

A request is admitted only when *both* buckets have capacity. The result carries
metadata used to populate standard `X-RateLimit-*` / `Retry-After` headers.

Token-bucket semantics:
- Each bucket has a capacity (`requests * burst_multiplier`) and refills at
  `requests / window_seconds` tokens per second.
- Admitting a request consumes one token.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Protocol

from app.core.config import RateLimitSettings, get_settings


@dataclass(frozen=True)
class RateLimitResult:
    """Outcome of a rate-limit check for a single bucket."""

    allowed: bool
    limit: int
    remaining: int
    reset_after: float  # seconds until the bucket is full again
    retry_after: float  # seconds the caller should wait before retrying


class RateLimiter(Protocol):
    """Storage-agnostic rate limiter contract."""

    def check(self, key: str, limit: int, window_seconds: int, burst_multiplier: float) -> RateLimitResult:
        ...


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class InMemoryRateLimiter:
    """Thread-safe in-process token-bucket limiter.

    Suitable for single-process local development. For multi-replica
    deployments, swap in a Redis-backed implementation conforming to the same
    `RateLimiter` protocol.
    """

    def __init__(self) -> None:
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        limit: int,
        window_seconds: int,
        burst_multiplier: float,
    ) -> RateLimitResult:
        capacity = max(1.0, float(limit) * burst_multiplier)
        refill_rate = float(limit) / float(window_seconds)  # tokens per second
        now = time.monotonic()

        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=capacity, last_refill=now)
                self._buckets[key] = bucket

            # Refill based on elapsed time.
            elapsed = now - bucket.last_refill
            bucket.tokens = min(capacity, bucket.tokens + elapsed * refill_rate)
            bucket.last_refill = now

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                remaining = int(bucket.tokens)
                reset_after = (capacity - bucket.tokens) / refill_rate if refill_rate else 0.0
                return RateLimitResult(
                    allowed=True,
                    limit=limit,
                    remaining=remaining,
                    reset_after=reset_after,
                    retry_after=0.0,
                )

            # Not enough tokens: compute wait time for one token.
            deficit = 1.0 - bucket.tokens
            retry_after = deficit / refill_rate if refill_rate else float(window_seconds)
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_after=retry_after,
                retry_after=retry_after,
            )

    def reset(self) -> None:
        """Clear all buckets (primarily for tests)."""

        with self._lock:
            self._buckets.clear()


def build_rate_limiter(settings: RateLimitSettings) -> RateLimiter:
    """Factory selecting a limiter implementation from configuration."""

    if settings.backend == "redis":
        # Redis backend is introduced in a later phase; fail loudly rather than
        # silently degrading isolation guarantees.
        raise NotImplementedError(
            "Redis rate-limit backend is not yet implemented. Use backend=memory."
        )
    return InMemoryRateLimiter()


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Return the process-wide rate limiter instance."""

    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = build_rate_limiter(get_settings().rate_limit)
    return _rate_limiter
