"""
Temporary retrieval-debugging endpoint.

`POST /api/v1/debug/retrieval` runs the *exact* production retrieval pipeline for
a query and returns every intermediate stage (dense, BM25, fused, reranked,
selected context) plus the classified intent/workflow and store-population
counts. It exists to answer one question precisely: **at which stage does the
retrieved context drop to zero?**

This module is intentionally self-contained and easy to delete once the
retrieval regression is resolved — remove this file and its line in
`app/api/router.py`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.agents.planner import PlannerAgent
from app.agents.query_understanding import QueryUnderstandingAgent
from app.agents.state import AgentState
from app.api.deps import enforce_rate_limit, get_current_tenant
from app.core.config import get_settings
from app.core.logging import get_logger
from app.retrieval.pipeline import RetrievalStages, _summarize_chunk, get_retriever

logger = get_logger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


class RetrievalDebugRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4000)
    document_ids: Optional[List[str]] = Field(
        default=None, description="Optional retrieval scope (same as /chat)."
    )


def _stage_rows(chunks) -> List[Dict[str, Any]]:
    return [_summarize_chunk(s) for s in chunks]


@router.post(
    "/retrieval",
    summary="[debug] Inspect every stage of the retrieval pipeline",
    dependencies=[Depends(enforce_rate_limit)],
)
async def debug_retrieval(
    payload: RetrievalDebugRequest,
    tenant_id: str = Depends(get_current_tenant),
) -> Dict[str, Any]:
    settings = get_settings()

    # --- Intent / workflow (mirror the real graph nodes) --------------------
    # Build the LLM provider only when understanding is configured to use it, so
    # this endpoint exercises the *same* code path as production. A provider
    # failure must not break the debug call — fall back to the heuristic.
    provider = None
    llm_attempted = settings.use_llm_for_understanding
    llm_error: Optional[str] = None
    if settings.use_llm_for_understanding:
        try:
            from app.llm.provider import get_llm_provider

            provider = get_llm_provider()
        except Exception as exc:  # pragma: no cover - environment dependent
            llm_error = f"{type(exc).__name__}: {exc}"
            logger.warning("debug/retrieval: LLM provider unavailable: %s", exc)

    state = AgentState(
        query=payload.query, tenant_id=tenant_id, document_ids=payload.document_ids or None
    )
    understanding = QueryUnderstandingAgent(provider=provider)
    qu_result = understanding.run(state)
    state.intent = qu_result["intent"]
    state.legal_task = qu_result["legal_task"]
    state.entities = qu_result["entities"]

    plan = PlannerAgent().run(state)["plan"]

    # --- Retrieval (full instrumented pipeline) -----------------------------
    retriever = get_retriever()
    stages: RetrievalStages = retriever.run_stages(
        state.query_for_retrieval(),
        tenant_id=tenant_id,
        document_ids=payload.document_ids or None,
    )

    return {
        "query": payload.query,
        "query_for_retrieval": state.query_for_retrieval(),
        "tenant_id": tenant_id,
        "document_scope": payload.document_ids or "all",
        "intent": state.intent.value,
        "legal_task": state.legal_task,
        "entities": state.entities,
        "workflow": plan.workflow,
        "retrieval_strategy": plan.retrieval_strategy,
        # Where, exactly, did context vanish? ("ok" if it survived.)
        "first_empty_stage": stages.first_empty_stage(),
        # Store population — proves whether the index even holds this tenant's data.
        "vector_store_count": stages.vector_store_count,
        "bm25_count": stages.bm25_count,
        # Per-stage counts + full rows.
        "counts": {
            "dense": len(stages.dense),
            "bm25": len(stages.sparse),
            "fused": len(stages.fused),
            "compressed": len(stages.compressed),
            "reranked": len(stages.reranked),
            "selected": len(stages.selected),
        },
        "dense_results": _stage_rows(stages.dense),
        "bm25_results": _stage_rows(stages.sparse),
        "fused_results": _stage_rows(stages.fused),
        "reranked_results": _stage_rows(stages.reranked),
        "selected_context": _stage_rows(stages.selected),
        # Config/wiring snapshot — explains false-vs-true behaviour at a glance.
        "config": {
            "embedding_backend": settings.embedding.backend,
            "vector_store": settings.retrieval.vector_store,
            "reranker_backend": settings.retrieval.reranker_backend,
            "enable_reranker": settings.retrieval.enable_reranker,
            "enable_compression": settings.retrieval.enable_compression,
            "use_llm_for_understanding": settings.use_llm_for_understanding,
            "use_llm_for_reasoning": settings.use_llm_for_reasoning,
            "reranker_applied": stages.reranker_applied,
            "llm_understanding_attempted": llm_attempted,
            "llm_understanding_active": provider is not None,
            "llm_provider_error": llm_error,
        },
    }
