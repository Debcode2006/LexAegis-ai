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


# Common English + legal-boilerplate words that carry no retrieval signal. Without
# removing these, a query like "what is the payment amount ... in the agreement?" is
# dominated by stopwords + ubiquitous terms ("agreement"), so unrelated clauses that
# happen to share them outrank the actual payment clause.
_STOPWORDS = frozenset(
    """a an the of to in on at by for and or nor but is are was were be been being this
    that these those it its as with within without into from out over under what which
    who whom whose how when where why shall will would should may might can could must
    any all each both either neither such per via herein hereof thereof hereto thereto
    do does did has have had not no yes if then else than so very about specified set
    forth pursuant accordance agreement""".split()
)


class LexicalReranker(Reranker):
    """Token-overlap reranker, IDF-weighted and blended with the retrieval prior.

    Pure surface overlap cannot bridge vocabulary gaps (query "payment amount /
    deadline" vs clause "compensation … payable net thirty days"), and on its own it
    lets stopword-rich distractors bury the right clause. Two guards fix that:

    1. Stopword removal + IDF over the candidate set, so ubiquitous/boilerplate
       terms contribute ~0 and only discriminative terms move the score.
    2. A blend with the *retrieval prior* — chunks arrive already ordered by RRF
       (dense + BM25). When lexical overlap is weak or empty (the vocabulary-gap
       case), the semantic order is preserved instead of being overridden.
    """

    def rerank(self, query: str, chunks: List[ScoredChunk], top_k: int) -> List[ScoredChunk]:
        if not chunks:
            return []
        q_set = {t for t in _TOKEN_RE.findall(query.lower()) if t not in _STOPWORDS}

        doc_token_lists = [_TOKEN_RE.findall(s.chunk.text.lower()) for s in chunks]
        n = len(chunks)
        df = {t: 0 for t in q_set}
        for tokens in doc_token_lists:
            present = q_set & set(tokens)
            for t in present:
                df[t] += 1

        def _idf(term: str) -> float:
            # Smoothed IDF: a term in every candidate -> ~0; a rare term -> high.
            return math.log((n + 1) / (df.get(term, 0) + 1)) + 1.0

        q_weight = sum(_idf(t) for t in q_set) or 1.0

        for idx, (scored, tokens) in enumerate(zip(chunks, doc_token_lists)):
            token_set = set(tokens)
            overlap = q_set & token_set
            # IDF-weighted query coverage in [0, 1].
            lexical = sum(_idf(t) for t in overlap) / q_weight
            # Retrieval prior from the incoming (RRF) order, also in [0, 1].
            prior = 1.0 - (idx / n) if n > 1 else 1.0
            scored.rerank_score = 0.5 * prior + 0.5 * lexical

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
