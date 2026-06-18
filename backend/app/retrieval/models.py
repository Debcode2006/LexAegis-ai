"""Retrieval result models shared across the pipeline."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.ingestion.models import Chunk


class ScoredChunk(BaseModel):
    """A chunk with the scores accumulated through the retrieval pipeline."""

    chunk: Chunk
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    rrf_score: Optional[float] = None
    rerank_score: Optional[float] = None

    @property
    def best_score(self) -> float:
        for value in (self.rerank_score, self.rrf_score, self.dense_score, self.sparse_score):
            if value is not None:
                return value
        return 0.0


class RetrievalResult(BaseModel):
    """Final retrieval output handed to the reasoning layer."""

    query: str
    tenant_id: str
    chunks: List[ScoredChunk] = Field(default_factory=list)
    dense_count: int = 0
    sparse_count: int = 0
    fused_count: int = 0
    reranked: bool = False
