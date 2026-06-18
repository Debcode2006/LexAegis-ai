"""
Citation Agent.

Builds the structured citation list that backs the inline [S1], [S2], ... tags
emitted by the reasoning agent, attaching document, section, clause, and page
references. Only sources actually referenced in the answer are returned (with a
fallback to all retrieved sources if the answer used no explicit tags).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from app.agents.state import AgentState, Citation
from app.retrieval.models import ScoredChunk

_TAG_RE = re.compile(r"\[S(\d+)\]")


class CitationAgent:
    def run(self, state: AgentState) -> Dict[str, Any]:
        chunks = state.retrieval.chunks if state.retrieval else []
        answer = state.answer or ""

        referenced = {int(m.group(1)) for m in _TAG_RE.finditer(answer)}
        citations: List[Citation] = []
        for idx, scored in enumerate(chunks, start=1):
            if referenced and idx not in referenced:
                continue
            citations.append(self._to_citation(idx, scored))

        # If the answer used no tags, expose all retrieved sources for traceability.
        if not citations:
            citations = [self._to_citation(i, s) for i, s in enumerate(chunks, start=1)]

        state.log("citation", count=len(citations))
        return {"citations": citations, "trace": state.trace}

    @staticmethod
    def _to_citation(index: int, scored: ScoredChunk) -> Citation:
        md = scored.chunk.metadata
        snippet = scored.chunk.text.strip()
        if len(snippet) > 240:
            snippet = snippet[:240].rsplit(" ", 1)[0] + "…"
        return Citation(
            marker=f"S{index}",
            document_id=md.document_id,
            document_name=md.document_name,
            section=md.section,
            clause=md.clause,
            page_number=md.page_number,
            snippet=snippet,
        )
