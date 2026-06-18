"""
Reciprocal Rank Fusion (RRF).

RRF merges dense and sparse result lists by rank rather than raw score, which
sidesteps the incompatible score scales of cosine similarity vs. BM25. Each
result contributes 1 / (k + rank) to its chunk's fused score; chunks retrieved
by both methods accumulate contributions and rise to the top.
"""

from __future__ import annotations

from typing import Dict, List

from app.retrieval.models import ScoredChunk


def reciprocal_rank_fusion(
    dense: List[ScoredChunk],
    sparse: List[ScoredChunk],
    *,
    k: int = 60,
) -> List[ScoredChunk]:
    """Fuse two ranked lists into one ordered by RRF score.

    Chunk identity is keyed on `chunk_id`. The merged `ScoredChunk` preserves the
    original dense/sparse scores for observability and downstream confidence.
    """

    fused: Dict[str, ScoredChunk] = {}

    def _accumulate(results: List[ScoredChunk], score_field: str) -> None:
        for rank, scored in enumerate(results):
            chunk_id = scored.chunk.chunk_id
            entry = fused.get(chunk_id)
            if entry is None:
                entry = ScoredChunk(chunk=scored.chunk, rrf_score=0.0)
                fused[chunk_id] = entry
            entry.rrf_score = (entry.rrf_score or 0.0) + 1.0 / (k + rank + 1)
            # Carry the source scores through for transparency.
            source_value = getattr(scored, score_field)
            if source_value is not None:
                setattr(entry, score_field, source_value)

    _accumulate(dense, "dense_score")
    _accumulate(sparse, "sparse_score")

    return sorted(fused.values(), key=lambda s: s.rrf_score or 0.0, reverse=True)
