"""Retrieval pipeline tests: fusion, compression, and end-to-end hybrid search."""

from __future__ import annotations

import pytest

from app.ingestion.models import Chunk, ChunkMetadata, DocumentType
from app.retrieval.compression import compress
from app.retrieval.embeddings import HashingEmbedder
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.models import ScoredChunk
from app.retrieval.pipeline import HybridRetriever
from app.retrieval.reranker import LexicalReranker
from app.retrieval.sparse import BM25Index
from app.retrieval.vector_store import InMemoryVectorStore


def _chunk(cid: str, text: str, tenant: str = "acme") -> Chunk:
    return Chunk(
        chunk_id=cid,
        text=text,
        metadata=ChunkMetadata(
            document_id="d1",
            document_name="d1.txt",
            tenant_id=tenant,
            document_type=DocumentType.CONTRACT,
            chunk_index=0,
        ),
    )


def test_rrf_rewards_agreement():
    a, b, c = _chunk("a", "x"), _chunk("b", "y"), _chunk("c", "z")
    dense = [ScoredChunk(chunk=a, dense_score=0.9), ScoredChunk(chunk=b, dense_score=0.8)]
    sparse = [ScoredChunk(chunk=b, sparse_score=5.0), ScoredChunk(chunk=c, sparse_score=4.0)]
    fused = reciprocal_rank_fusion(dense, sparse, k=60)
    # b appears in both lists -> should rank first.
    assert fused[0].chunk.chunk_id == "b"
    assert fused[0].dense_score == 0.8
    assert fused[0].sparse_score == 5.0


def test_compression_removes_near_duplicates():
    dup_text = "The parties agree to keep all confidential information secret at all times."
    items = [
        ScoredChunk(chunk=_chunk("a", dup_text), rrf_score=0.9),
        ScoredChunk(chunk=_chunk("b", dup_text + " "), rrf_score=0.8),
        ScoredChunk(chunk=_chunk("c", "Termination requires thirty days notice."), rrf_score=0.7),
    ]
    kept = compress(items, threshold=0.9)
    ids = [s.chunk.chunk_id for s in kept]
    assert "a" in ids and "c" in ids
    assert "b" not in ids


@pytest.fixture
def retriever():
    return HybridRetriever(
        embedder=HashingEmbedder(dimension=256),
        vector_store=InMemoryVectorStore(),
        bm25=BM25Index(),
        reranker=LexicalReranker(),
    )


def test_hybrid_retrieve_end_to_end(retriever):
    chunks = [
        _chunk("c1", "The confidentiality clause requires secrecy for five years."),
        _chunk("c2", "The limitation of liability excludes indirect damages."),
        _chunk("c3", "Termination for convenience requires thirty days written notice."),
        _chunk("c4", "Governing law shall be the laws of Delaware."),
    ]
    indexed = retriever.index_chunks(chunks)
    assert indexed == 4

    result = retriever.retrieve("What does the confidentiality clause require?", tenant_id="acme")
    assert result.chunks
    assert result.reranked is True
    # The confidentiality chunk should surface as the top result.
    assert result.chunks[0].chunk.chunk_id == "c1"


def test_tenant_isolation_in_retrieval(retriever):
    retriever.index_chunks([_chunk("a", "Acme secret data", tenant="acme")])
    retriever.index_chunks([_chunk("b", "Globex secret data", tenant="globex")])
    result = retriever.retrieve("secret data", tenant_id="acme")
    ids = [s.chunk.chunk_id for s in result.chunks]
    assert "b" not in ids


def _doc_chunk(cid: str, text: str, doc: str, tenant: str = "acme") -> Chunk:
    return Chunk(
        chunk_id=cid,
        text=text,
        metadata=ChunkMetadata(
            document_id=doc,
            document_name=f"{doc}.txt",
            tenant_id=tenant,
            document_type=DocumentType.CONTRACT,
            chunk_index=0,
        ),
    )


@pytest.fixture
def scoped_retriever():
    r = HybridRetriever(
        embedder=HashingEmbedder(dimension=256),
        vector_store=InMemoryVectorStore(),
        bm25=BM25Index(),
        reranker=LexicalReranker(),
    )
    r.index_chunks([
        _doc_chunk("c1", "The confidentiality clause requires secrecy for five years.", "docA"),
        _doc_chunk("c2", "The limitation of liability excludes indirect damages.", "docB"),
        _doc_chunk("c3", "Termination requires thirty days written notice.", "docC"),
    ])
    return r


def test_retrieval_scope_restricts_to_selected_documents(scoped_retriever):
    # Scope to docB only — results must never include chunks from other docs.
    result = scoped_retriever.retrieve(
        "liability clause", tenant_id="acme", document_ids=["docB"]
    )
    assert result.chunks
    assert {s.chunk.metadata.document_id for s in result.chunks} == {"docB"}


def test_retrieval_scope_multiple_documents(scoped_retriever):
    result = scoped_retriever.retrieve(
        "clause notice damages", tenant_id="acme", document_ids=["docA", "docC"]
    )
    docs = {s.chunk.metadata.document_id for s in result.chunks}
    assert docs <= {"docA", "docC"}
    assert "docB" not in docs


def test_retrieval_scope_none_searches_all_documents(scoped_retriever):
    # Backward compatibility: omitting document_ids searches everything.
    result = scoped_retriever.retrieve("clause notice damages", tenant_id="acme")
    docs = {s.chunk.metadata.document_id for s in result.chunks}
    assert len(docs) >= 2


def test_retrieval_scope_unknown_document_returns_empty(scoped_retriever):
    result = scoped_retriever.retrieve(
        "confidentiality", tenant_id="acme", document_ids=["does-not-exist"]
    )
    assert result.chunks == []


def test_bm25_and_vector_store_respect_document_scope(scoped_retriever):
    # Filtering is applied to BOTH dense and sparse legs (counts reflect scope).
    result = scoped_retriever.retrieve(
        "confidentiality", tenant_id="acme", document_ids=["docA"]
    )
    assert result.dense_count >= 1
    assert all(s.chunk.metadata.document_id == "docA" for s in result.chunks)
