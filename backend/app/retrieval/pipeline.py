"""
Hybrid retrieval orchestration.

Implements the full legal retrieval pipeline:

    query
      → dense retrieval   (BGE + vector store)
      → sparse retrieval  (BM25)
      → RRF fusion
      → context compression (near-duplicate removal)
      → cross-encoder reranking
      → top-K context

`HybridRetriever` also exposes `index_chunks`, the single write path shared by
the ingestion pipeline (keeps the dense store and BM25 index in lock-step).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingestion.models import Chunk
from app.retrieval.compression import compress
from app.retrieval.embeddings import Embedder, get_embedder
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.models import RetrievalResult, ScoredChunk
from app.retrieval.reranker import Reranker, get_reranker
from app.retrieval.sparse import BM25Index, get_bm25_index
from app.retrieval.vector_store import VectorStore, get_vector_store

logger = get_logger(__name__)


def _summarize_chunk(scored: ScoredChunk) -> Dict[str, Any]:
    """Compact per-chunk diagnostic row (safe to log / return as JSON)."""

    md = scored.chunk.metadata
    return {
        "chunk_id": scored.chunk.chunk_id,
        "document_id": md.document_id,
        "document_name": md.document_name,
        "section": md.section,
        "clause": md.clause,
        "page_number": md.page_number,
        "dense_score": scored.dense_score,
        "bm25_score": scored.sparse_score,
        "rrf_score": scored.rrf_score,
        "reranker_score": scored.rerank_score,
        "text_preview": scored.chunk.text[:160],
    }


@dataclass
class RetrievalStages:
    """Every intermediate list produced by one retrieval call.

    This is the single source of truth shared by `retrieve()` (which logs it and
    collapses it into a `RetrievalResult`) and the debug endpoint (which returns
    it verbatim). Keeping both on the same structure guarantees the diagnostics
    describe exactly what production retrieval did.
    """

    query: str
    tenant_id: str
    document_ids: Optional[List[str]]
    # Store population (answers "is the index even populated?").
    vector_store_count: int = 0
    bm25_count: int = 0
    # Per-stage candidate lists.
    dense: List[ScoredChunk] = field(default_factory=list)
    sparse: List[ScoredChunk] = field(default_factory=list)
    fused: List[ScoredChunk] = field(default_factory=list)
    compressed: List[ScoredChunk] = field(default_factory=list)
    reranked: List[ScoredChunk] = field(default_factory=list)
    selected: List[ScoredChunk] = field(default_factory=list)
    reranker_applied: bool = False

    def first_empty_stage(self) -> str:
        """Name the earliest stage at which the candidate set became empty.

        Returns "ok" when context survives all the way to `selected`.
        """

        if self.vector_store_count == 0 and self.bm25_count == 0:
            return "index_empty"
        if not self.dense and not self.sparse:
            return "retrieval"  # both dense + sparse returned nothing
        if not self.fused:
            return "fusion"
        if not self.compressed:
            return "compression"
        if self.reranker_applied and not self.reranked:
            return "reranker"
        if not self.selected:
            return "selection"
        return "ok"


class HybridRetriever:
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        vector_store: Optional[VectorStore] = None,
        bm25: Optional[BM25Index] = None,
        reranker: Optional[Reranker] = None,
    ) -> None:
        self._embedder = embedder or get_embedder()
        self._store = vector_store or get_vector_store()
        self._bm25 = bm25 or get_bm25_index()
        self._reranker = reranker or get_reranker()

    # -- write path -----------------------------------------------------------

    def index_chunks(self, chunks: List[Chunk]) -> int:
        """Embed and index chunks into both dense and sparse stores."""

        if not chunks:
            return 0
        embeddings = self._embedder.embed_documents([c.text for c in chunks])
        self._store.add(chunks, embeddings)
        self._bm25.add(chunks)
        logger.info("Indexed %d chunks", len(chunks))
        return len(chunks)

    # -- read path ------------------------------------------------------------

    def run_stages(
        self,
        query: str,
        tenant_id: str,
        document_ids: Optional[List[str]] = None,
    ) -> RetrievalStages:
        """Execute the full pipeline, capturing every intermediate stage.

        This is the instrumented core. `retrieve()` wraps it for the production
        read path; the debug endpoint consumes the full `RetrievalStages`.
        """

        cfg = get_settings().retrieval
        stages = RetrievalStages(
            query=query, tenant_id=tenant_id, document_ids=document_ids
        )

        # 0. Store population — answers "is the index even populated for this
        #    tenant?" before we blame query/fusion/reranking.
        try:
            stages.vector_store_count = self._store.count(tenant_id)
        except Exception as exc:  # pragma: no cover - backend-specific failure
            logger.warning("vector_store.count(%s) failed: %s", tenant_id, exc)
        stages.bm25_count = self._bm25.count(tenant_id)

        # 1. Dense retrieval (scoped to document_ids when provided).
        query_vec = self._embedder.embed_query(query)
        stages.dense = self._store.search(
            query_vec, tenant_id=tenant_id, top_k=cfg.dense_top_k, document_ids=document_ids
        )

        # 2. Sparse retrieval (same document scope).
        stages.sparse = self._bm25.search(
            query, tenant_id=tenant_id, top_k=cfg.sparse_top_k, document_ids=document_ids
        )

        # 3. Reciprocal Rank Fusion.
        stages.fused = reciprocal_rank_fusion(stages.dense, stages.sparse, k=cfg.rrf_k)

        # 4. Context compression (near-duplicate removal).
        if cfg.enable_compression:
            stages.compressed = compress(stages.fused, threshold=cfg.dedup_threshold)
        else:
            stages.compressed = list(stages.fused)

        # 5. Reranking.
        candidates = stages.compressed[: cfg.rerank_top_k]
        if cfg.enable_reranker and candidates:
            candidates = self._reranker.rerank(query, candidates, top_k=cfg.final_top_k)
            stages.reranker_applied = True
            stages.reranked = candidates
        else:
            candidates = candidates[: cfg.final_top_k]
            stages.reranked = candidates
        stages.selected = candidates

        self._log_stages(stages, cfg)
        return stages

    @staticmethod
    def _log_stages(stages: RetrievalStages, cfg) -> None:
        """Emit the full retrieval diagnostic for one query."""

        ranked = stages.reranked if stages.reranker_applied else stages.selected
        top5 = [_summarize_chunk(s) for s in (ranked or stages.fused)[:5]]
        logger.info(
            "[RETRIEVAL] query=%r tenant=%s scope=%s | store_count=%d bm25_count=%d "
            "| dense=%d bm25=%d fused=%d compressed=%d reranked=%d selected=%d "
            "| reranker_applied=%s first_empty_stage=%s",
            stages.query,
            stages.tenant_id,
            stages.document_ids or "all",
            stages.vector_store_count,
            stages.bm25_count,
            len(stages.dense),
            len(stages.sparse),
            len(stages.fused),
            len(stages.compressed),
            len(stages.reranked),
            len(stages.selected),
            stages.reranker_applied,
            stages.first_empty_stage(),
        )
        for i, row in enumerate(top5, start=1):
            logger.info(
                "[RETRIEVAL]   #%d doc=%s section=%s dense=%s bm25=%s rrf=%s rerank=%s",
                i,
                row["document_id"],
                row["section"],
                row["dense_score"],
                row["bm25_score"],
                row["rrf_score"],
                row["reranker_score"],
            )
        if stages.first_empty_stage() != "ok":
            logger.warning(
                "[RETRIEVAL] context disappeared at stage=%s (query=%r tenant=%s). "
                "store_count=%d bm25_count=%d — see stage counts above.",
                stages.first_empty_stage(),
                stages.query,
                stages.tenant_id,
                stages.vector_store_count,
                stages.bm25_count,
            )

    def retrieve(
        self,
        query: str,
        tenant_id: str,
        document_ids: Optional[List[str]] = None,
    ) -> RetrievalResult:
        stages = self.run_stages(query, tenant_id, document_ids=document_ids)
        return RetrievalResult(
            query=query,
            tenant_id=tenant_id,
            chunks=stages.selected,
            dense_count=len(stages.dense),
            sparse_count=len(stages.sparse),
            fused_count=len(stages.fused),
            reranked=stages.reranker_applied,
        )


_retriever: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
