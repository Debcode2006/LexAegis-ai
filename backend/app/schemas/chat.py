"""Chat request/response schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.agents.state import Citation, ConfidenceBreakdown


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    include_trace: bool = Field(default=False, description="Return the agent trace.")
    document_ids: Optional[List[str]] = Field(
        default=None,
        description=(
            "Optional retrieval scope. When omitted or empty, search all of the "
            "tenant's documents. When provided, restrict hybrid retrieval (dense "
            "+ sparse) to these document_ids only."
        ),
    )


class GroundednessInfo(BaseModel):
    groundedness: float
    citation_coverage: float
    has_citations: bool
    unsupported_claims: List[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    query: str
    answer: str
    intent: str
    confidence: float
    confidence_breakdown: Optional[ConfidenceBreakdown] = None
    citations: List[Citation] = Field(default_factory=list)
    groundedness: Optional[GroundednessInfo] = None
    blocked: bool = False
    block_reason: Optional[str] = None
    trace: Optional[List[Dict[str, Any]]] = None
