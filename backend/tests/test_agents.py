"""Unit tests for individual agents."""

from __future__ import annotations

import pytest

from app.agents.citation import CitationAgent
from app.agents.confidence import ConfidenceAgent
from app.agents.output_safety_agent import OutputSafetyAgent
from app.agents.planner import PlannerAgent
from app.agents.query_understanding import QueryUnderstandingAgent
from app.agents.state import AgentState, ConfidenceBreakdown, Intent
from app.ingestion.models import Chunk, ChunkMetadata, DocumentType
from app.retrieval.models import RetrievalResult, ScoredChunk
from app.safety.models import OutputValidation


def _state(query="What are the liability and risk exposure terms?") -> AgentState:
    return AgentState(query=query, tenant_id="acme", masked_query=query)


def _scored(cid, doc, text):
    return ScoredChunk(
        chunk=Chunk(
            chunk_id=cid,
            text=text,
            metadata=ChunkMetadata(
                document_id=doc, document_name=f"{doc}.txt", tenant_id="acme",
                document_type=DocumentType.CONTRACT, page_number=2, clause="5.1",
            ),
        ),
        dense_score=0.8,
        rerank_score=0.7,
    )


def test_query_understanding_heuristic_intent():
    out = QueryUnderstandingAgent(provider=None).run(_state())
    assert out["intent"] == Intent.LEGAL_RISK_ANALYSIS


@pytest.mark.parametrize(
    "query, expected_ref",
    [
        ("What does Section 3 PAYMENT say?", "Section 3"),
        ("What does Section 6 TERMINATION say?", "Section 6"),
        ("What does Section 9 GOVERNING LAW say?", "Section 9"),
        ("What does Clause 4.2 say?", "Clause 4.2"),
    ],
)
def test_query_understanding_extracts_clause_reference(query, expected_ref):
    # Regression: _CLAUSE_REF_RE previously had no capturing group, so the
    # heuristic path raised "IndexError: no such group" -> HTTP 500.
    out = QueryUnderstandingAgent(provider=None).run(_state(query))
    entities = out["entities"]
    assert any(e.lower() == expected_ref.lower() for e in entities), entities


def test_extract_entities_never_raises_on_group_less_regex():
    # The defensive helper must tolerate a group-less pattern without raising.
    for query in (
        "What does Section 3 PAYMENT say?",
        "Section. Article. Clause.",  # references with no number
        "",  # empty query
    ):
        # Must not raise; returns a (possibly empty) list.
        assert isinstance(QueryUnderstandingAgent._extract_entities(query), list)


def test_planner_maps_intent_to_workflow():
    state = _state()
    state.intent = Intent.CLAUSE_COMPARISON
    out = PlannerAgent().run(state)
    assert out["plan"].workflow == "clause_comparison"
    assert "compression" in out["plan"].tools


def test_citation_agent_extracts_referenced_sources():
    state = _state()
    state.retrieval = RetrievalResult(
        query=state.query, tenant_id="acme",
        chunks=[_scored("c1", "d1", "Liability is capped."), _scored("c2", "d2", "Risk is shared.")],
    )
    state.answer = "Liability is capped [S1]."
    out = CitationAgent().run(state)
    citations = out["citations"]
    assert len(citations) == 1
    assert citations[0].marker == "S1"
    assert citations[0].clause == "5.1"
    assert citations[0].page_number == 2


def test_confidence_agent_blends_signals():
    state = _state()
    state.retrieval = RetrievalResult(
        query=state.query, tenant_id="acme",
        chunks=[_scored("c1", "d1", "x"), _scored("c2", "d2", "y"), _scored("c3", "d3", "z")],
    )
    state.output_validation = OutputValidation(
        allowed=True, groundedness=0.9, citation_coverage=0.8, has_citations=True
    )
    out = ConfidenceAgent().run(state)
    assert 0.0 < out["confidence"] <= 1.0
    assert out["confidence_breakdown"].source_agreement == 1.0  # 3 distinct docs


def test_output_safety_agent_blocks_ungrounded():
    state = _state()
    state.answer = "Some ungrounded claim."
    state.confidence = 0.8
    state.output_validation = OutputValidation(allowed=False, groundedness=0.1, issues=["ungrounded"])
    out = OutputSafetyAgent().run(state)
    assert out["final_answer"] != state.answer
    assert out["confidence"] <= 0.2


def test_output_safety_agent_releases_grounded():
    state = _state()
    state.answer = "Grounded answer [S1]."
    state.output_validation = OutputValidation(allowed=True, groundedness=0.9)
    out = OutputSafetyAgent().run(state)
    assert out["final_answer"] == "Grounded answer [S1]."
