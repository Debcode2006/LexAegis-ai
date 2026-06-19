"""
Sparse (lexical) retrieval via BM25.

`BM25Index` maintains an in-memory BM25 model over chunk texts, scoped per
tenant so lexical search respects isolation. BM25 complements dense retrieval by
matching exact legal terms, defined terms, statute numbers, and citations that
embeddings can blur.

The index is rebuilt incrementally as chunks are added. For the local single
process this lives in memory; a production deployment would persist the corpus
and rebuild on startup (or back it with an inverted-index service).
"""

from __future__ import annotations

import re
import threading
from typing import Dict, List, Optional

from app.ingestion.models import Chunk
from app.retrieval.models import ScoredChunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


class BM25Index:
    """Per-tenant BM25 index built on rank_bm25."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # tenant_id -> list of chunks (corpus order)
        self._corpus: Dict[str, List[Chunk]] = {}
        self._models: Dict[str, object] = {}

    def add(self, chunks: List[Chunk]) -> None:
        with self._lock:
            for chunk in chunks:
                self._corpus.setdefault(chunk.metadata.tenant_id, []).append(chunk)
            # Invalidate affected tenant models so they rebuild on next search.
            for tenant_id in {c.metadata.tenant_id for c in chunks}:
                self._models.pop(tenant_id, None)

    def _model_for(self, tenant_id: str):
        model = self._models.get(tenant_id)
        if model is not None:
            return model
        corpus = self._corpus.get(tenant_id, [])
        if not corpus:
            return None
        from rank_bm25 import BM25Okapi

        model = BM25Okapi([_tokenize(c.text) for c in corpus])
        self._models[tenant_id] = model
        return model

    def search(
        self,
        query: str,
        tenant_id: str,
        top_k: int,
        document_ids: Optional[List[str]] = None,
    ) -> List[ScoredChunk]:
        with self._lock:
            model = self._model_for(tenant_id)
            corpus = self._corpus.get(tenant_id, [])
        if model is None or not corpus:
            return []

        doc_filter = set(document_ids) if document_ids else None
        scores = model.get_scores(_tokenize(query))
        # Rank over the full tenant corpus (BM25 statistics stay intact), then
        # keep the top_k that fall within the requested document scope.
        order = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)
        results: List[ScoredChunk] = []
        for i in order:
            if scores[i] <= 0:
                continue
            if doc_filter is not None and corpus[i].metadata.document_id not in doc_filter:
                continue
            results.append(ScoredChunk(chunk=corpus[i], sparse_score=float(scores[i])))
            if len(results) >= top_k:
                break
        return results

    def count(self, tenant_id: Optional[str] = None) -> int:
        if tenant_id is None:
            return sum(len(v) for v in self._corpus.values())
        return len(self._corpus.get(tenant_id, []))

    def reset(self) -> None:
        with self._lock:
            self._corpus.clear()
            self._models.clear()


_index: Optional[BM25Index] = None


def get_bm25_index() -> BM25Index:
    global _index
    if _index is None:
        _index = BM25Index()
    return _index
