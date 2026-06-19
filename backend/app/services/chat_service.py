"""
Chat service.

Bridges the HTTP layer and the agent workflow:
- runs the graph for a tenant-scoped query,
- wraps the turn in an observability span (latency + key attributes),
- caches the full response per (tenant, normalized query) for fast repeats,
- maps the resulting `AgentState` into the API `ChatResponse`.
"""

from __future__ import annotations

from typing import List, Optional

from app.agents.graph import LegalAgentWorkflow, get_workflow
from app.agents.state import AgentState
from app.cache.semantic_cache import SemanticCache, get_semantic_cache, normalize_key
from app.observability.tracing import span
from app.schemas.chat import ChatResponse, GroundednessInfo


class ChatService:
    def __init__(
        self,
        workflow: Optional[LegalAgentWorkflow] = None,
        cache: Optional[SemanticCache] = None,
    ) -> None:
        self._workflow = workflow or get_workflow()
        self._cache = cache or get_semantic_cache()

    def answer(
        self,
        query: str,
        tenant_id: str,
        *,
        include_trace: bool = False,
        document_ids: Optional[List[str]] = None,
    ) -> ChatResponse:
        # Normalize empty list -> None ("all documents"); keep responses for
        # different retrieval scopes from colliding in the cache.
        document_ids = document_ids or None
        scope_key = "all" if not document_ids else ",".join(sorted(document_ids))
        cache_key = normalize_key("chat", tenant_id, query, scope_key)
        cached = self._cache.get(cache_key)
        if cached is not None and not include_trace:
            return cached

        with span(
            "chat.turn",
            {"tenant_id": tenant_id, "query_len": len(query), "scoped": bool(document_ids)},
        ) as attrs:
            state: AgentState = self._workflow.run(query, tenant_id, document_ids=document_ids)
            attrs["intent"] = state.intent.value
            attrs["confidence"] = state.confidence
            attrs["blocked"] = state.blocked
            attrs["retrieved"] = len(state.retrieval.chunks) if state.retrieval else 0

        response = self._to_response(state, include_trace=include_trace)
        if not state.blocked:
            self._cache.set(cache_key, response)
        return response

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
