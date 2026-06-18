"""Hybrid legal retrieval: dense + sparse + RRF + compression + reranking."""

from app.retrieval.models import RetrievalResult, ScoredChunk

__all__ = ["RetrievalResult", "ScoredChunk"]
