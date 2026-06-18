"""
Output safety validation.

The final guard before an answer is released. It checks:

- Citation presence    : does the answer reference sources at all?
- Citation coverage    : fraction of answer sentences that map to retrieved
                         context (lexical grounding signal).
- Unsupported claims   : sentences with no support in any context chunk.
- PII leakage          : did any PII survive into the answer?

This is intentionally model-light (deterministic lexical grounding) so it always
runs cheaply on the critical path. The dedicated Groundedness Agent (Phase 3) can
add an LLM-based check on top; this layer is the always-on backstop.
"""

from __future__ import annotations

import re
from typing import List, Optional

from app.core.config import get_settings
from app.retrieval.models import ScoredChunk
from app.safety.models import OutputValidation
from app.safety.pii import PIIDetector, get_pii_detector

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")
_CITATION_RE = re.compile(r"\[(?:source|doc|p\.?|page|clause|section)[^\]]*\]", re.I)


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


class OutputSafetyValidator:
    def __init__(self, detector: Optional[PIIDetector] = None) -> None:
        self._detector = detector or get_pii_detector()
        cfg = get_settings().safety
        self._min_coverage = cfg.min_citation_coverage
        self._block_on_pii = cfg.block_on_pii_leak

    def validate(self, answer: str, context_chunks: List[ScoredChunk]) -> OutputValidation:
        issues: List[str] = []

        context_tokens = [_tokens(c.chunk.text) for c in context_chunks]

        # --- Grounding: per-sentence support against context ----------------
        sentences = [s.strip() for s in _SENTENCE_RE.split(answer.strip()) if s.strip()]
        supported = 0
        unsupported: List[str] = []
        for sentence in sentences:
            s_tokens = _tokens(sentence)
            if not s_tokens:
                continue
            best = 0.0
            for ctx in context_tokens:
                if not ctx:
                    continue
                overlap = len(s_tokens & ctx) / len(s_tokens)
                best = max(best, overlap)
            if best >= 0.3:
                supported += 1
            else:
                unsupported.append(sentence)

        total = max(1, len(sentences))
        groundedness = supported / total
        coverage = supported / total

        if unsupported:
            issues.append(f"{len(unsupported)} sentence(s) lack support in retrieved context.")

        # --- Citations ------------------------------------------------------
        has_citations = bool(_CITATION_RE.search(answer))
        if not has_citations:
            issues.append("Answer contains no inline citations.")

        # --- PII leakage ----------------------------------------------------
        pii_entities = self._detector.analyze(answer)
        pii_leaked = len(pii_entities) > 0
        if pii_leaked:
            issues.append(f"Answer leaked {len(pii_entities)} PII entity(ies).")

        allowed = True
        if coverage < self._min_coverage:
            allowed = False
        if pii_leaked and self._block_on_pii:
            allowed = False

        return OutputValidation(
            allowed=allowed,
            groundedness=round(groundedness, 4),
            citation_coverage=round(coverage, 4),
            has_citations=has_citations,
            pii_leaked=pii_leaked,
            unsupported_claims=unsupported,
            issues=issues,
        )


_validator: Optional[OutputSafetyValidator] = None


def get_output_validator() -> OutputSafetyValidator:
    global _validator
    if _validator is None:
        _validator = OutputSafetyValidator()
    return _validator
