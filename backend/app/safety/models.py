"""Safety domain models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PIIEntity(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float
    text: str


class PIIMaskResult(BaseModel):
    """Outcome of a PII masking pass."""

    masked_text: str
    entities: List[PIIEntity] = Field(default_factory=list)

    @property
    def has_pii(self) -> bool:
        return len(self.entities) > 0


class SafetyVerdict(BaseModel):
    """Input-safety decision from a guard model."""

    safe: bool
    categories: List[str] = Field(default_factory=list)
    reason: Optional[str] = None
    raw: Optional[str] = None


class OutputValidation(BaseModel):
    """Aggregated output-safety result before answer release."""

    allowed: bool
    groundedness: float = 0.0
    citation_coverage: float = 0.0
    has_citations: bool = False
    pii_leaked: bool = False
    unsupported_claims: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
