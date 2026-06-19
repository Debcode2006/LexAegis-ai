"""Legal chat endpoint — runs the agentic RAG workflow."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import enforce_rate_limit, get_current_tenant
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import ChatService, get_chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "",
    response_model=ChatResponse,
    summary="Ask a grounded legal question",
    dependencies=[Depends(enforce_rate_limit)],
)
async def chat(
    payload: ChatRequest,
    tenant_id: str = Depends(get_current_tenant),
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return service.answer(
        payload.query,
        tenant_id,
        include_trace=payload.include_trace,
        document_ids=payload.document_ids,
    )
