"""
Cross-encoder reranking.

Reranking re-scores the fused candidates against the query with a model that
sees query and passage *together* (cross-encoder), yielding far sharper ordering
than the bi-encoder retrieval scores.

- `BGEReranker`      — production: BAAI/bge-reranker-large via FlagEmbedding.
- `LexicalReranker`  — light/test fallback: token-overlap (coverage-weighted)
                       scoring. Deterministic, no model download.

Selected via `RETRIEVAL_RERANKER_BACKEND` (bge | lexical).
"""

from __future__ import annotations

import math
import re
from typing import List, Optional, Protocol

from app.core.config import get_settings
from app.core.logging import get_logger
from app.retrieval.models import ScoredChunk

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Reranker(Protocol):
    def rerank(self, query: str, chunks: List[ScoredChunk], top_k: int) -> List[ScoredChunk]:
        ...


class LexicalReranker(Reranker):
    """Token-overlap reranker (query coverage * idf-ish weighting)."""

    def rerank(self, query: str, chunks: List[ScoredChunk], top_k: int) -> List[ScoredChunk]:
        q_tokens = _TOKEN_RE.findall(query.lower())
        q_set = set(q_tokens)
        if not q_set:
            return chunks[:top_k]

        for scored in chunks:
            doc_tokens = _TOKEN_RE.findall(scored.chunk.text.lower())
            doc_set = set(doc_tokens)
            overlap = q_set & doc_set
            coverage = len(overlap) / len(q_set)
            # Reward density of matches, dampened by length.
            density = sum(doc_tokens.count(t) for t in overlap) / (1 + math.log1p(len(doc_tokens)))
            scored.rerank_score = coverage * 0.7 + min(density, 1.0) * 0.3

        ranked = sorted(chunks, key=lambda s: s.rerank_score or 0.0, reverse=True)
        return ranked[:top_k]


class BGEReranker(Reranker):
    """Production cross-encoder reranker (FlagEmbedding, lazy-loaded)."""

    def __init__(self) -> None:
        self._cfg = get_settings().embedding
        self._model = None

    def _ensure_model(self):
        if self._model is None:
            from FlagEmbedding import FlagReranker

            logger.info("Loading reranker model: %s", self._cfg.reranker_model)
            self._model = FlagReranker(self._cfg.reranker_model, use_fp16=False)
        return self._model

    def rerank(self, query: str, chunks: List[ScoredChunk], top_k: int) -> List[ScoredChunk]:
        if not chunks:
            return []
        model = self._ensure_model()
        pairs = [[query, s.chunk.text] for s in chunks]
        scores = model.compute_score(pairs, normalize=True)
        if not isinstance(scores, list):
            scores = [scores]
        for scored, score in zip(chunks, scores):
            scored.rerank_score = float(score)
        ranked = sorted(chunks, key=lambda s: s.rerank_score or 0.0, reverse=True)
        return ranked[:top_k]


def build_reranker() -> Reranker:
    backend = get_settings().retrieval.reranker_backend.lower()
    if backend == "lexical":
        return LexicalReranker()
    return BGEReranker()


_reranker: Optional[Reranker] = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        _reranker = build_reranker()
    return _reranker
