"""Semantic caching for embeddings, retrieval outputs, and LLM outputs."""

from app.cache.semantic_cache import SemanticCache, get_semantic_cache

__all__ = ["SemanticCache", "get_semantic_cache"]
