"""
Shared agent state.

`AgentState` is the single object threaded through the LangGraph workflow. Each
agent reads the fields it needs and writes its own outputs, so the graph stays
declarative and every step is independently testable. Nodes return *partial*
dict updates which the orchestrator merges into the state — this keeps the same
node functions usable by both the LangGraph engine and the sequential fallback.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.retrieval.models import RetrievalResult
from app.safety.models import OutputValidation, SafetyVerdict


class Intent(str, Enum):
    CONTRACT_REVIEW = "contract_review"
    CLAUSE_COMPARISON = "clause_comparison"
    COMPLIANCE_CHECK = "compliance_check"
    POLICY_LOOKUP = "policy_lookup"
    REGULATION_SEARCH = "regulation_search"
    LEGAL_RISK_ANALYSIS = "legal_risk_analysis"
    DOCUMENT_SUMMARY = "document_summary"
    UNKNOWN = "unknown"


class Plan(BaseModel):
    workflow: str = "standard_rag"
    retrieval_strategy: str = "hybrid"
    tools: List[str] = Field(default_factory=lambda: ["hybrid_retrieval", "reranker"])
    notes: Optional[str] = None


class Citation(BaseModel):
    marker: str
    document_id: str
    document_name: str
    section: Optional[str] = None
    clause: Optional[str] = None
    page_number: Optional[int] = None
    snippet: str = ""


class ConfidenceBreakdown(BaseModel):
    retrieval_similarity: float = 0.0
    reranker_score: float = 0.0
    source_agreement: float = 0.0
    citation_coverage: float = 0.0
    groundedness: float = 0.0
    overall: float = 0.0


class AgentState(BaseModel):
    """End-to-end state for one chat turn."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Inputs
    query: str
    tenant_id: str
    masked_query: Optional[str] = None
    # Optional retrieval scope: restrict retrieval to these document_ids. None or
    # empty means "all documents for the tenant".
    document_ids: Optional[List[str]] = None

    # Layer 2 — input safety
    input_safety: Optional[SafetyVerdict] = None
    blocked: bool = False
    block_reason: Optional[str] = None

    # Query understanding
    intent: Intent = Intent.UNKNOWN
    legal_task: Optional[str] = None
    entities: List[str] = Field(default_factory=list)

    # Planning
    plan: Optional[Plan] = None

    # Retrieval
    retrieval: Optional[RetrievalResult] = None

    # Reasoning
    answer: Optional[str] = None

    # Citation
    citations: List[Citation] = Field(default_factory=list)

    # Groundedness / output safety
    output_validation: Optional[OutputValidation] = None

    # Confidence
    confidence: float = 0.0
    confidence_breakdown: Optional[ConfidenceBreakdown] = None

    # Final
    final_answer: Optional[str] = None

    # Observability
    trace: List[Dict[str, Any]] = Field(default_factory=list)

    def log(self, step: str, **fields: Any) -> None:
        self.trace.append({"step": step, **fields})

    def query_for_retrieval(self) -> str:
        return self.masked_query or self.query
