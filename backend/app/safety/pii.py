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
        # Set once if Presidio cannot be loaded, so we degrade to regex instead of
        # re-attempting (and re-logging) a failing engine build on every page.
        self._fallback: Optional[RegexPIIDetector] = None

    def _ensure_analyzer(self):
        if self._analyzer is not None:
            return self._analyzer
        from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
        from presidio_analyzer.nlp_engine import NlpEngineProvider

        # Pin the spaCy model EXPLICITLY. Presidio's default AnalyzerEngine() loads
        # `en_core_web_lg` and, if it is absent, runs `spacy download` AT RUNTIME —
        # which on Railway pip-installs into the root-owned /opt/venv while running
        # as non-root `appuser`, fails with "Permission denied", and kills the
        # worker. By naming a model that was installed at build time (requirements
        # .txt) we both control accuracy/size and guarantee no runtime download.
        lang = self._cfg.presidio_language
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": lang, "model_name": self._cfg.presidio_spacy_model}],
            }
        )
        nlp_engine = provider.create_engine()
        analyzer = AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=[lang])
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
        if self._fallback is not None:
            return self._fallback.analyze(text)
        try:
            analyzer = self._ensure_analyzer()
        except (Exception, SystemExit) as exc:
            # SystemExit because spacy.cli.download() calls sys.exit() on failure.
            # Whatever the cause (missing model, read-only venv, network), PII
            # masking must never crash an upload — degrade to the regex detector.
            logger.warning(
                "Presidio PII engine unavailable (%s). Falling back to the regex PII "
                "detector so ingestion is not blocked. Install the spaCy model %r at "
                "build time to restore full NER-based detection.",
                exc,
                self._cfg.presidio_spacy_model,
            )
            self._fallback = RegexPIIDetector(threshold=self._cfg.pii_score_threshold)
            return self._fallback.analyze(text)

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
