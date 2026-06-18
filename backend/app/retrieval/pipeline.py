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

from typing import List, Optional

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

    def retrieve(self, query: str, tenant_id: str) -> RetrievalResult:
        cfg = get_settings().retrieval

        # 1. Dense retrieval.
        query_vec = self._embedder.embed_query(query)
        dense = self._store.search(query_vec, tenant_id=tenant_id, top_k=cfg.dense_top_k)

        # 2. Sparse retrieval.
        sparse = self._bm25.search(query, tenant_id=tenant_id, top_k=cfg.sparse_top_k)

        # 3. Reciprocal Rank Fusion.
        fused = reciprocal_rank_fusion(dense, sparse, k=cfg.rrf_k)

        # 4. Context compression (near-duplicate removal).
        if cfg.enable_compression:
            fused = compress(fused, threshold=cfg.dedup_threshold)

        # 5. Reranking.
        reranked = False
        candidates = fused[: cfg.rerank_top_k]
        if cfg.enable_reranker and candidates:
            candidates = self._reranker.rerank(query, candidates, top_k=cfg.final_top_k)
            reranked = True
        else:
            candidates = candidates[: cfg.final_top_k]

        return RetrievalResult(
            query=query,
            tenant_id=tenant_id,
            chunks=candidates,
            dense_count=len(dense),
            sparse_count=len(sparse),
            fused_count=len(fused),
            reranked=reranked,
        )


_retriever: Optional[HybridRetriever] = None


def get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever()
    return _retriever
