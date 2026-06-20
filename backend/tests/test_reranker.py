"""LexicalReranker quality tests.

Locks down the production regression where the lexical reranker demoted the
payment clause below unrelated boilerplate clauses, because it scored raw token
overlap dominated by stopwords + ubiquitous terms ('agreement', 'specified').
The reranker must (a) not let stopword-rich distractors override the semantic
(RRF) order, and (b) still boost a chunk that genuinely matches a discriminative
query term.
"""

from __future__ import annotations

from app.ingestion.models import Chunk, ChunkMetadata
from app.retrieval.models import ScoredChunk
from app.retrieval.reranker import LexicalReranker


def _mk(section: str, text: str) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(
            chunk_id=section,
            text=text,
            metadata=ChunkMetadata(
                document_id="d", document_name="agreement", tenant_id="public", section=section
            ),
        )
    )


def _sections(ranked):
    return [s.chunk.metadata.section for s in ranked]


# Input is in RRF order (dense + BM25). The payment clause is first because dense
# retrieval matched it semantically, even though it says "compensation/payable net
# thirty days" rather than the query's "amount/deadline".
def _candidates():
    return [
        _mk("3", "Compensation. The Client shall remit to the Provider a sum of fifty "
                 "thousand dollars, payable net thirty (30) days from receipt of each invoice."),
        _mk("2", "Definitions. As used in this agreement, the terms specified below have "
                 "the meanings ascribed, and what is stated herein controls."),
        _mk("5", "Intellectual Property. All work product specified in this agreement is "
                 "the property of the Client; the Provider assigns all right and interest."),
        _mk("8", "Term and Termination. This agreement is effective as specified and may be "
                 "terminated by either party upon written notice set forth in this agreement."),
        _mk("9", "Governing Law. This agreement and any dispute is governed by and specified "
                 "under the laws of the State, and what jurisdiction applies is as stated."),
    ]


def test_vocabulary_gap_preserves_semantic_order():
    # No chunk literally contains 'payment/amount/deadline'; stopwords/boilerplate
    # must NOT let a distractor jump above the dense-ranked payment clause.
    q = "What is the payment amount and payment deadline specified in the agreement?"
    ranked = LexicalReranker().rerank(q, _candidates(), top_k=5)
    assert _sections(ranked)[0] == "3"


def test_discriminative_term_is_boosted():
    # 'termination' is a rare, discriminative term present only in section 8 — even
    # though it arrives LAST in RRF order, the reranker should surface it to the top.
    q = "What are the termination rights of either party?"
    ranked = LexicalReranker().rerank(q, _candidates(), top_k=5)
    assert _sections(ranked)[0] == "8"


def test_stopword_only_overlap_does_not_dominate():
    # A distractor sharing only stopwords must not outrank the RRF-leading chunk.
    q = "What is in the agreement?"
    ranked = LexicalReranker().rerank(q, _candidates(), top_k=3)
    assert _sections(ranked)[0] == "3"


def test_empty_candidates():
    assert LexicalReranker().rerank("anything", [], top_k=5) == []
