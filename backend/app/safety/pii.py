"""
PII detection and masking.

`PIIDetector` finds sensitive entities; `mask` replaces them with typed
placeholders (e.g. `<EMAIL_ADDRESS>`). Masking is applied at three points:

- ingestion time : before chunks are embedded/stored,
- query time      : before the user query is logged/embedded,
- output time     : as a final guard before the answer is returned.

Backends:
- `PresidioPIIDetector` — production: Microsoft Presidio (spaCy NER + recognizers),
  including Indian identifiers (PAN, Aadhaar, Passport) via custom patterns.
- `RegexPIIDetector`    — light/test fallback: high-precision regexes for email,
  phone, PAN, Aadhaar, passport. No spaCy model download required.

Selected via `SAFETY_PII_BACKEND` (presidio | regex).
"""

from __future__ import annotations

import re
from typing import List, Optional, Protocol

from app.core.config import get_settings
from app.core.logging import get_logger
from app.safety.models import PIIEntity, PIIMaskResult

logger = get_logger(__name__)

# --- Regex patterns for the fallback detector --------------------------------
_PATTERNS = {
    "EMAIL_ADDRESS": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "PHONE_NUMBER": re.compile(r"\b(?:\+?\d{1,3}[\s-]?)?(?:\d{10}|\d{3}[\s-]\d{3}[\s-]\d{4})\b"),
    # Indian PAN: 5 letters, 4 digits, 1 letter.
    "IN_PAN": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    # Indian Aadhaar: 12 digits, optionally space/hyphen grouped.
    "IN_AADHAAR": re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
    # Indian Passport: 1 letter + 7 digits.
    "IN_PASSPORT": re.compile(r"\b[A-PR-WYa-pr-wy]\d{7}\b"),
}


class PIIDetector(Protocol):
    def analyze(self, text: str) -> List[PIIEntity]:
        ...


class RegexPIIDetector(PIIDetector):
    """Dependency-light regex detector for common + Indian identifiers."""

    def __init__(self, threshold: Optional[float] = None) -> None:
        self._threshold = threshold if threshold is not None else get_settings().safety.pii_score_threshold

    def analyze(self, text: str) -> List[PIIEntity]:
        entities: List[PIIEntity] = []
        for entity_type, pattern in _PATTERNS.items():
            for match in pattern.finditer(text):
                entities.append(
                    PIIEntity(
                        entity_type=entity_type,
                        start=match.start(),
                        end=match.end(),
                        score=0.85,
                        text=match.group(0),
                    )
                )
        return entities


class PresidioPIIDetector(PIIDetector):
    """Production Presidio-based detector (lazy-loaded)."""

    def __init__(self) -> None:
        self._cfg = get_settings().safety
        self._analyzer = None

    def _ensure_analyzer(self):
        if self._analyzer is not None:
            return self._analyzer
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer

        analyzer = AnalyzerEngine()
        # Register Indian identifier recognizers absent from Presidio defaults.
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="IN_PAN",
                patterns=[Pattern("pan", r"\b[A-Z]{5}\d{4}[A-Z]\b", 0.85)],
            )
        )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="IN_AADHAAR",
                patterns=[Pattern("aadhaar", r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", 0.7)],
            )
        )
        analyzer.registry.add_recognizer(
            PatternRecognizer(
                supported_entity="IN_PASSPORT",
                patterns=[Pattern("passport", r"\b[A-PR-WY]\d{7}\b", 0.7)],
            )
        )
        self._analyzer = analyzer
        return analyzer

    def analyze(self, text: str) -> List[PIIEntity]:
        analyzer = self._ensure_analyzer()
        results = analyzer.analyze(
            text=text,
            entities=self._cfg.pii_entities,
            language=self._cfg.presidio_language,
            score_threshold=self._cfg.pii_score_threshold,
        )
        return [
            PIIEntity(
                entity_type=r.entity_type,
                start=r.start,
                end=r.end,
                score=r.score,
                text=text[r.start : r.end],
            )
            for r in results
        ]


def mask_text(text: str, detector: PIIDetector) -> PIIMaskResult:
    """Replace detected PII spans with typed placeholders.

    Overlapping spans are resolved by preferring higher-score, longer matches,
    and replacement proceeds right-to-left so indices stay valid.
    """

    entities = detector.analyze(text)
    if not entities:
        return PIIMaskResult(masked_text=text, entities=[])

    # Resolve overlaps: sort by score desc then length desc, greedily accept.
    entities_sorted = sorted(entities, key=lambda e: (e.score, e.end - e.start), reverse=True)
    accepted: List[PIIEntity] = []
    for ent in entities_sorted:
        if any(not (ent.end <= a.start or ent.start >= a.end) for a in accepted):
            continue
        accepted.append(ent)

    # Apply right-to-left.
    masked = text
    for ent in sorted(accepted, key=lambda e: e.start, reverse=True):
        masked = masked[: ent.start] + f"<{ent.entity_type}>" + masked[ent.end :]

    return PIIMaskResult(masked_text=masked, entities=accepted)


def build_detector() -> PIIDetector:
    backend = get_settings().safety.pii_backend.lower()
    if backend == "regex":
        return RegexPIIDetector()
    return PresidioPIIDetector()


_detector: Optional[PIIDetector] = None


def get_pii_detector() -> PIIDetector:
    global _detector
    if _detector is None:
        _detector = build_detector()
    return _detector
