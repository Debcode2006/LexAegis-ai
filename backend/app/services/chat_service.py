"""
Chat service.

Bridges the HTTP layer and the agent workflow: runs the graph for a tenant-scoped
query and maps the resulting `AgentState` into the API `ChatResponse`.
"""

from __future__ import annotations

from typing import Optional

from app.agents.graph import LegalAgentWorkflow, get_workflow
from app.agents.state import AgentState
from app.schemas.chat import ChatResponse, GroundednessInfo


class ChatService:
    def __init__(self, workflow: Optional[LegalAgentWorkflow] = None) -> None:
        self._workflow = workflow or get_workflow()

    def answer(self, query: str, tenant_id: str, *, include_trace: bool = False) -> ChatResponse:
        state: AgentState = self._workflow.run(query, tenant_id)
        return self._to_response(state, include_trace=include_trace)

    @staticmethod
    def _to_response(state: AgentState, *, include_trace: bool) -> ChatResponse:
        groundedness = None
        if state.output_validation is not None:
            v = state.output_validation
            groundedness = GroundednessInfo(
                groundedness=v.groundedness,
                citation_coverage=v.citation_coverage,
                has_citations=v.has_citations,
                unsupported_claims=v.unsupported_claims,
            )
        return ChatResponse(
            query=state.query,
            answer=state.final_answer or state.answer or "",
            intent=state.intent.value,
            confidence=state.confidence,
            confidence_breakdown=state.confidence_breakdown,
            citations=state.citations,
            groundedness=groundedness,
            blocked=state.blocked,
            block_reason=state.block_reason,
            trace=state.trace if include_trace else None,
        )


_service: Optional[ChatService] = None


def get_chat_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService()
    return _service
