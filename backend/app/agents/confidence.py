"""
Confidence Agent.

Produces a 0.0–1.0 confidence score from five signals:

- retrieval_similarity : mean dense/RRF similarity of the used chunks,
- reranker_score        : mean cross-encoder rerank score,
- source_agreement      : how many distinct documents corroborate the answer,
- citation_coverage     : fraction of answer sentences grounded in context,
- groundedness          : lexical grounding score.

The weighted blend is intentionally transparent (the breakdown is returned) so
the score is explainable to legal users rather than a black box.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app.agents.state import AgentState, ConfidenceBreakdown
from app.retrieval.models import ScoredChunk

_WEIGHTS = {
    "retrieval_similarity": 0.20,
    "reranker_score": 0.25,
    "source_agreement": 0.15,
    "citation_coverage": 0.20,
    "groundedness": 0.20,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mean(values: List[float]) -> float:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0


class ConfidenceAgent:
    def run(self, state: AgentState) -> Dict[str, Any]:
        chunks: List[ScoredChunk] = state.retrieval.chunks if state.retrieval else []
        validation = state.output_validation

        retrieval_similarity = _clamp(
            _mean([c.dense_score if c.dense_score is not None else c.rrf_score or 0.0 for c in chunks])
        )
        reranker_score = _clamp(_mean([c.rerank_score or 0.0 for c in chunks]))

        distinct_docs = len({c.chunk.metadata.document_id for c in chunks})
        source_agreement = _clamp(distinct_docs / 3.0) if chunks else 0.0

        citation_coverage = validation.citation_coverage if validation else 0.0
        groundedness = validation.groundedness if validation else 0.0

        breakdown = ConfidenceBreakdown(
            retrieval_similarity=round(retrieval_similarity, 4),
            reranker_score=round(reranker_score, 4),
            source_agreement=round(source_agreement, 4),
            citation_coverage=round(citation_coverage, 4),
            groundedness=round(groundedness, 4),
        )
        overall = (
            _WEIGHTS["retrieval_similarity"] * retrieval_similarity
            + _WEIGHTS["reranker_score"] * reranker_score
            + _WEIGHTS["source_agreement"] * source_agreement
            + _WEIGHTS["citation_coverage"] * citation_coverage
            + _WEIGHTS["groundedness"] * groundedness
        )
        breakdown.overall = round(_clamp(overall), 4)

        state.log("confidence", overall=breakdown.overall)
        return {
            "confidence": breakdown.overall,
            "confidence_breakdown": breakdown,
            "trace": state.trace,
        }
