"""
Semantic cache.

Caches expensive outputs (LLM completions, full chat responses, retrieval
results) keyed by a normalized, tenant-scoped query. Two backends:

- `gptcache` : production — GPTCache with embedding-similarity matching, so
  semantically equivalent queries hit the cache.
- `memory`   : light/local/test — a bounded LRU with normalized-string keys
  (exact + whitespace/case-insensitive match). No external service.

Hit/miss statistics are tracked for the observability metrics endpoint. The same
`SemanticCache` instance is used for LLM outputs and chat responses; namespaces
keep the entry types separate.
"""

from __future__ import annotations

import hashlib
import re
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_WS_RE = re.compile(r"\s+")


def normalize_key(namespace: str, *parts: str) -> str:
    raw = "|".join(_WS_RE.sub(" ", p.strip().lower()) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"{namespace}:{digest}"


class SemanticCache:
    """LRU/semantic cache with hit-miss accounting."""

    def __init__(self) -> None:
        cfg = get_settings().observability
        self._enabled = cfg.enable_semantic_cache and cfg.cache_backend != "off"
        self._backend = cfg.cache_backend
        self._max_entries = cfg.cache_max_entries
        self._store: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._gptcache = None
        if self._enabled and self._backend == "gptcache":
            self._init_gptcache()

    def _init_gptcache(self) -> None:
        try:  # pragma: no cover - optional heavy dependency
            from gptcache import Cache
            from gptcache.manager import get_data_manager

            cache = Cache()
            cache.init(data_manager=get_data_manager())
            self._gptcache = cache
            logger.info("GPTCache backend initialized.")
        except Exception as exc:  # pragma: no cover
            logger.warning("GPTCache unavailable, falling back to memory cache: %s", exc)
            self._backend = "memory"

    # -- API ------------------------------------------------------------------

    def get(self, key: str) -> Optional[Any]:
        if not self._enabled:
            return None
        with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
                self._hits += 1
                return self._store[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        if not self._enabled:
            return
        with self._lock:
            self._store[key] = value
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "enabled": self._enabled,
                "backend": self._backend,
                "entries": len(self._store),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
            }

    def reset(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0


_cache: Optional[SemanticCache] = None


def get_semantic_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache
