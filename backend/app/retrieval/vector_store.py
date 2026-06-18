"""
Vector store backends.

`VectorStore` is the contract for dense add/search with tenant-scoped filtering.

- `ChromaVectorStore`   — production: persistent ChromaDB collection.
- `InMemoryVectorStore` — light/local/test: brute-force cosine over in-process
                          vectors. Same semantics, no external service.

Selected via `RETRIEVAL_VECTOR_STORE` (chroma | memory). Both enforce tenant
isolation by filtering on the `tenant_id` metadata field.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Protocol, Tuple

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingestion.models import Chunk, ChunkMetadata, DocumentType
from app.retrieval.models import ScoredChunk

logger = get_logger(__name__)


class VectorStore(Protocol):
    def add(self, chunks: List[Chunk], embeddings: List[List[float]]) -> None:
        ...

    def search(
        self, query_embedding: List[float], tenant_id: str, top_k: int
    ) -> List[ScoredChunk]:
        ...

    def count(self, tenant_id: Optional[str] = None) -> int:
        ...


def _metadata_from_store(meta: Dict) -> ChunkMetadata:
    page = meta.get("page_number", -1)
    return ChunkMetadata(
        document_id=meta.get("document_id", ""),
        document_name=meta.get("document_name", ""),
        tenant_id=meta.get("tenant_id", ""),
        document_type=DocumentType(meta.get("document_type", "unknown")),
        section=meta.get("section") or None,
        clause=meta.get("clause") or None,
        heading=meta.get("heading") or None,
        page_number=None if page in (-1, None) else int(page),
        chunk_index=int(meta.get("chunk_index", 0)),
    )


class InMemoryVectorStore(VectorStore):
    """Brute-force cosine similarity store (single process)."""

    def __init__(self) -> None:
        # chunk_id -> (vector, text, metadata-dict)
        self._items: Dict[str, Tuple[List[float], str, Dict]] = {}

    def add(self, chunks: List[Chunk], embeddings: List[List[float]]) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings length mismatch")
        for chunk, vec in zip(chunks, embeddings):
            self._items[chunk.chunk_id] = (vec, chunk.text, chunk.metadata.to_store_dict())

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def search(
        self, query_embedding: List[float], tenant_id: str, top_k: int
    ) -> List[ScoredChunk]:
        scored: List[Tuple[float, str]] = []
        for chunk_id, (vec, _text, meta) in self._items.items():
            if meta.get("tenant_id") != tenant_id:
                continue
            scored.append((self._cosine(query_embedding, vec), chunk_id))
        scored.sort(key=lambda x: x[0], reverse=True)

        results: List[ScoredChunk] = []
        for score, chunk_id in scored[:top_k]:
            vec, text, meta = self._items[chunk_id]
            results.append(
                ScoredChunk(
                    chunk=Chunk(chunk_id=chunk_id, text=text, metadata=_metadata_from_store(meta)),
                    dense_score=score,
                )
            )
        return results

    def count(self, tenant_id: Optional[str] = None) -> int:
        if tenant_id is None:
            return len(self._items)
        return sum(1 for _v, _t, m in self._items.values() if m.get("tenant_id") == tenant_id)

    def reset(self) -> None:
        self._items.clear()


class ChromaVectorStore(VectorStore):
    """Persistent ChromaDB-backed store (lazy client construction)."""

    def __init__(self) -> None:
        cfg = get_settings().chroma
        self._cfg = cfg
        self._client = None
        self._collection = None

    def _ensure_collection(self):
        if self._collection is not None:
            return self._collection
        import chromadb

        if self._cfg.use_http_client:
            self._client = chromadb.HttpClient(host=self._cfg.host, port=self._cfg.port)
        else:
            self._client = chromadb.PersistentClient(path=self._cfg.persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=self._cfg.collection, metadata={"hnsw:space": "cosine"}
        )
        return self._collection

    def add(self, chunks: List[Chunk], embeddings: List[List[float]]) -> None:
        collection = self._ensure_collection()
        collection.add(
            ids=[c.chunk_id for c in chunks],
            embeddings=embeddings,
            documents=[c.text for c in chunks],
            metadatas=[c.metadata.to_store_dict() for c in chunks],
        )

    def search(
        self, query_embedding: List[float], tenant_id: str, top_k: int
    ) -> List[ScoredChunk]:
        collection = self._ensure_collection()
        res = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where={"tenant_id": tenant_id},
        )
        results: List[ScoredChunk] = []
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        distances = (res.get("distances") or [[]])[0]
        for chunk_id, text, meta, dist in zip(ids, docs, metas, distances):
            # Chroma returns cosine distance; convert to similarity.
            results.append(
                ScoredChunk(
                    chunk=Chunk(chunk_id=chunk_id, text=text, metadata=_metadata_from_store(meta)),
                    dense_score=1.0 - float(dist),
                )
            )
        return results

    def count(self, tenant_id: Optional[str] = None) -> int:
        collection = self._ensure_collection()
        if tenant_id is None:
            return collection.count()
        return len(collection.get(where={"tenant_id": tenant_id}).get("ids", []))


def build_vector_store() -> VectorStore:
    backend = get_settings().retrieval.vector_store.lower()
    if backend == "memory":
        return InMemoryVectorStore()
    return ChromaVectorStore()


_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = build_vector_store()
    return _store
