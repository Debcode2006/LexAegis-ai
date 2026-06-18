"""
Context compression.

After fusion the candidate set often contains exact duplicates and near-
duplicates (overlapping chunk windows, repeated boilerplate clauses). Feeding
these to the LLM wastes context budget and biases reasoning toward repeated
text. This stage removes them with a Jaccard-similarity pass over token shingles,
keeping the highest-ranked representative of each near-duplicate group.
"""

from __future__ import annotations

import re
from typing import List, Set

from app.core.config import get_settings
from app.retrieval.models import ScoredChunk

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _shingles(text: str, size: int = 3) -> Set[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    if len(tokens) < size:
        return set(tokens)
    return {" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def compress(
    chunks: List[ScoredChunk],
    *,
    threshold: float | None = None,
) -> List[ScoredChunk]:
    """Drop near-duplicate chunks, preserving input order (highest rank first)."""

    if threshold is None:
        threshold = get_settings().retrieval.dedup_threshold

    kept: List[ScoredChunk] = []
    kept_shingles: List[Set[str]] = []

    for scored in chunks:
        shingles = _shingles(scored.chunk.text)
        if any(_jaccard(shingles, prev) >= threshold for prev in kept_shingles):
            continue
        kept.append(scored)
        kept_shingles.append(shingles)

    return kept
