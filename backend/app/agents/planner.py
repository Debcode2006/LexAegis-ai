"""
Planner Agent.

Maps the classified intent to a concrete workflow: which retrieval strategy and
tools to use. Deterministic and rule-based — planning policy lives here so the
rest of the graph stays mechanical.
"""

from __future__ import annotations

from typing import Any, Dict

from app.agents.state import AgentState, Intent, Plan

# Per-intent execution plan. `retrieval_strategy` and `tools` are advisory hints
# consumed by the retrieval agent / future tool-routing.
_PLANS: Dict[Intent, Plan] = {
    Intent.CONTRACT_REVIEW: Plan(
        workflow="contract_review",
        retrieval_strategy="hybrid",
        tools=["hybrid_retrieval", "reranker"],
        notes="Review obligations, terms, and clause-level detail.",
    ),
    Intent.CLAUSE_COMPARISON: Plan(
        workflow="clause_comparison",
        retrieval_strategy="hybrid_broad",
        tools=["hybrid_retrieval", "reranker", "compression"],
        notes="Retrieve clauses from multiple documents for side-by-side compare.",
    ),
    Intent.COMPLIANCE_CHECK: Plan(
        workflow="compliance_check",
        retrieval_strategy="hybrid",
        tools=["hybrid_retrieval", "reranker"],
        notes="Match obligations against compliance manuals/regulations.",
    ),
    Intent.POLICY_LOOKUP: Plan(
        workflow="policy_lookup",
        retrieval_strategy="sparse_first",
        tools=["hybrid_retrieval"],
        notes="Exact policy lookups favour lexical matching.",
    ),
    Intent.REGULATION_SEARCH: Plan(
        workflow="regulation_search",
        retrieval_strategy="hybrid",
        tools=["hybrid_retrieval", "reranker"],
    ),
    Intent.LEGAL_RISK_ANALYSIS: Plan(
        workflow="legal_risk_analysis",
        retrieval_strategy="hybrid_broad",
        tools=["hybrid_retrieval", "reranker", "compression"],
        notes="Surface liability/indemnity/penalty clauses for risk reasoning.",
    ),
    Intent.DOCUMENT_SUMMARY: Plan(
        workflow="document_summary",
        retrieval_strategy="hybrid_broad",
        tools=["hybrid_retrieval"],
        notes="Broad recall to summarise across the document.",
    ),
}

_DEFAULT_PLAN = Plan()


class PlannerAgent:
    def run(self, state: AgentState) -> Dict[str, Any]:
        plan = _PLANS.get(state.intent, _DEFAULT_PLAN)
        state.log("planner", workflow=plan.workflow, strategy=plan.retrieval_strategy)
        return {"plan": plan, "trace": state.trace}
