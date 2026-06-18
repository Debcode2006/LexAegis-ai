"""
Legal Reasoning Agent.

Generates the answer strictly from retrieved context. The prompt forbids
unsupported claims and requires inline source tags ([S1], [S2], ...). When the
LLM is disabled/unavailable, a deterministic extractive fallback composes an
answer from the top context chunks so the pipeline remains functional and
grounded.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.base import ChatMessage, LLMError, Role
from app.llm.provider import LLMProvider
from app.retrieval.models import ScoredChunk

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are LexAegis, a meticulous legal analysis assistant. Answer the user's "
    "question using ONLY the provided context. Rules:\n"
    "- Never introduce facts that are not in the context.\n"
    "- If the context is insufficient, say so explicitly.\n"
    "- Cite every supported statement inline using its source tag, e.g. [S1].\n"
    "- Be precise, neutral, and concise."
)

_INSUFFICIENT = (
    "I could not find sufficient grounded evidence in the provided documents to "
    "answer this question reliably."
)


def build_context_block(chunks: List[ScoredChunk]) -> str:
    lines = []
    for i, scored in enumerate(chunks, start=1):
        md = scored.chunk.metadata
        locus = []
        if md.section:
            locus.append(f"section {md.section}")
        if md.clause:
            locus.append(f"clause {md.clause}")
        if md.page_number:
            locus.append(f"p.{md.page_number}")
        locus_str = f" ({', '.join(locus)})" if locus else ""
        lines.append(f"[S{i}] {md.document_name}{locus_str}:\n{scored.chunk.text}")
    return "\n\n".join(lines)


class LegalReasoningAgent:
    def __init__(self, provider: Optional[LLMProvider] = None) -> None:
        self._provider = provider
        self._use_llm = get_settings().use_llm_for_reasoning and provider is not None

    def run(self, state: AgentState) -> Dict[str, Any]:
        chunks = state.retrieval.chunks if state.retrieval else []
        if not chunks:
            state.log("reasoning", mode="no_context")
            return {"answer": _INSUFFICIENT, "trace": state.trace}

        context = build_context_block(chunks)
        if self._use_llm:
            answer = self._reason_with_llm(state.query, context)
            if answer:
                state.log("reasoning", mode="llm", length=len(answer))
                return {"answer": answer, "trace": state.trace}

        answer = self._extractive_fallback(chunks)
        state.log("reasoning", mode="extractive", length=len(answer))
        return {"answer": answer, "trace": state.trace}

    def _reason_with_llm(self, query: str, context: str) -> Optional[str]:
        messages = [
            ChatMessage(role=Role.SYSTEM, content=_SYSTEM_PROMPT),
            ChatMessage(role=Role.USER, content=f"Context:\n{context}\n\nQuestion: {query}"),
        ]
        try:
            response = self._provider.chat(messages, temperature=0.1)
        except LLMError as exc:
            logger.warning("Reasoning LLM failed: %s", exc)
            return None
        return response.content.strip() or None

    @staticmethod
    def _extractive_fallback(chunks: List[ScoredChunk]) -> str:
        top = chunks[0]
        snippet = top.chunk.text.strip()
        if len(snippet) > 600:
            snippet = snippet[:600].rsplit(" ", 1)[0] + "…"
        return f"Based on the retrieved documents: {snippet} [S1]"
