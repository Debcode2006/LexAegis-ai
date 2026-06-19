# Retrieval Pipeline

Hybrid legal retrieval lives in `app/retrieval`. The orchestrator is
`HybridRetriever` (`pipeline.py`), which exposes a write path (`index_chunks`)
and a read path (`retrieve`).

## Read path

```
query
  → dense retrieval     embeddings.py + vector_store.py   (top dense_top_k)
  → sparse retrieval    sparse.py (BM25)                  (top sparse_top_k)
  → RRF fusion          fusion.py                         (rank-based merge)
  → compression         compression.py                    (near-dup removal)
  → reranking           reranker.py (cross-encoder)        (top rerank_top_k)
  → top-K context       final_top_k
```

All stages are tenant-scoped. Tuning knobs (`RETRIEVAL_*`) are in `.env.example`.

## Components

### Embeddings (`embeddings.py`)
- `BGEEmbedder` — BAAI/bge-large-en-v1.5 via sentence-transformers; applies the
  BGE query-instruction prefix for queries.
- `HashingEmbedder` — deterministic hashing-trick vectors; identical text → same
  vector, lexical overlap drives cosine similarity. Used for light/local/test.

### Vector store (`vector_store.py`)
- `ChromaVectorStore` — persistent ChromaDB collection, cosine space, filtered by
  `tenant_id`.
- `InMemoryVectorStore` — brute-force cosine over in-process vectors.

### Sparse (`sparse.py`)
Per-tenant BM25 (rank_bm25). Complements dense retrieval by matching exact legal
terms, defined terms, statute numbers, and citations. Models rebuild lazily when
new chunks are added.

### Fusion — RRF (`fusion.py`)
Merges dense and sparse lists by rank: each contributes `1 / (k + rank)`. This
avoids the incompatible score scales of cosine vs. BM25; chunks found by both
methods rise to the top. `k = RETRIEVAL_RRF_K` (default 60).

### Compression (`compression.py`)
Removes exact and near-duplicate chunks using Jaccard similarity over 3-token
shingles, keeping the highest-ranked representative. Threshold =
`RETRIEVAL_DEDUP_THRESHOLD`.

### Reranker (`reranker.py`)
- `BGEReranker` — BAAI/bge-reranker-large cross-encoder (query+passage together).
- `LexicalReranker` — token-overlap (coverage + density) fallback.

## Write path

`index_chunks(chunks)`:
1. embeds chunk texts (`embedder.embed_documents`),
2. adds vectors + metadata to the vector store,
3. adds chunks to the BM25 index.

This is the single write path; the ingestion pipeline calls it so dense and
sparse stores stay in lock-step.

## Metadata for citations

Every chunk carries `document_id`, `document_name`, `tenant_id`, `document_type`,
`section`, `clause`, `heading`, `page_number`, `chunk_index` — powering tenant
isolation and precise citations (see [INGESTION_PIPELINE](INGESTION_PIPELINE.md)).
