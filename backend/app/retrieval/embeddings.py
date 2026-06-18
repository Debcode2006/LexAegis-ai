"""
Dense embedding backends.

`Embedder` is the contract. Two implementations:

- `BGEEmbedder`     — production: BAAI/bge-large-en-v1.5 via sentence-transformers.
                      Applies the BGE query instruction prefix for retrieval.
- `HashingEmbedder` — deterministic, dependency-light hashing-trick embeddings.
                      Used for local/light mode and tests so the full pipeline
                      runs without downloading multi-GB models. Identical text
                      maps to identical vectors and lexical overlap drives
                      cosine similarity.

Selected via `EMBEDDING_BACKEND` (bge | hashing).
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import List, Optional, Protocol

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text.lower())


class Embedder(Protocol):
    dimension: int

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        ...

    def embed_query(self, text: str) -> List[float]:
        ...


class HashingEmbedder(Embedder):
    """Deterministic hashing-trick embedder (no external model required)."""

    def __init__(self, dimension: Optional[int] = None) -> None:
        self.dimension = dimension or get_settings().embedding.dimension

    def _embed(self, text: str) -> List[float]:
        vec = [0.0] * self.dimension
        for token in _tokenize(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed(text)


class BGEEmbedder(Embedder):
    """Production BGE embedder (sentence-transformers, lazy-loaded)."""

    def __init__(self) -> None:
        cfg = get_settings().embedding
        self._cfg = cfg
        self._query_instruction = cfg.query_instruction
        self._model = None  # lazy
        self.dimension = cfg.dimension  # refined after model load

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading dense embedding model: %s", self._cfg.dense_model)
            self._model = SentenceTransformer(self._cfg.dense_model, device=self._cfg.device)
            self.dimension = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        model = self._ensure_model()
        vectors = model.encode(
            texts,
            batch_size=self._cfg.batch_size,
            normalize_embeddings=self._cfg.normalize,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> List[float]:
        model = self._ensure_model()
        vector = model.encode(
            self._query_instruction + text,
            normalize_embeddings=self._cfg.normalize,
            show_progress_bar=False,
        )
        return vector.tolist()


def build_embedder() -> Embedder:
    backend = get_settings().embedding.backend.lower()
    if backend == "hashing":
        return HashingEmbedder()
    return BGEEmbedder()


_embedder: Optional[Embedder] = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        _embedder = build_embedder()
    return _embedder
