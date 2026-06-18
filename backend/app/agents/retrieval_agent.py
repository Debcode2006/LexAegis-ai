"""
Retrieval Agent.

Thin orchestration wrapper that invokes the hybrid retrieval pipeline (dense +
sparse + RRF + compression + reranking) for the (masked) query within the
caller's tenant. The heavy lifting lives in `app.retrieval`; this agent adapts
it to the graph state and records observability data.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.retrieval.pipeline import HybridRetriever, get_retriever

logger = get_logger(__name__)


class RetrievalAgent:
    def __init__(self, retriever: Optional[HybridRetriever] = None) -> None:
        self._retriever = retriever or get_retriever()

    def run(self, state: AgentState) -> Dict[str, Any]:
        result = self._retriever.retrieve(state.query_for_retrieval(), tenant_id=state.tenant_id)
        state.log(
            "retrieval",
            dense=result.dense_count,
            sparse=result.sparse_count,
            fused=result.fused_count,
            returned=len(result.chunks),
            reranked=result.reranked,
        )
        return {"retrieval": result, "trace": state.trace}
