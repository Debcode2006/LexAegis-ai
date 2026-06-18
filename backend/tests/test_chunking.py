"""Legal-aware chunking tests."""

from __future__ import annotations

from app.ingestion.chunking import LegalChunker
from app.ingestion.models import DocumentType, PageText, RawDocument

SAMPLE = """MASTER SERVICES AGREEMENT

Section 1. DEFINITIONS
This agreement defines the terms used herein.

Section 2. CONFIDENTIALITY
2.1 Each party shall keep confidential information secret.
2.2 The obligations survive termination for five years.

Section 3. LIABILITY
3.1 Neither party shall be liable for indirect damages.
"""


def _doc(text: str, doc_type=DocumentType.CONTRACT) -> RawDocument:
    return RawDocument(
        document_id="doc-1",
        document_name="MSA.txt",
        tenant_id="acme",
        document_type=doc_type,
        pages=[PageText(page_number=1, text=text)],
    )


def test_chunks_carry_section_metadata():
    chunks = LegalChunker(max_chars=2000).chunk_document(_doc(SAMPLE))
    assert chunks
    sections = {c.metadata.section for c in chunks if c.metadata.section}
    # Section labels should be captured.
    assert any("Section 1" in s or s == "1" for s in sections) or "Section 1" in sections
    assert any("confidential" in c.text.lower() for c in chunks)


def test_clause_detection():
    chunks = LegalChunker(max_chars=2000).chunk_document(_doc(SAMPLE))
    clauses = {c.metadata.clause for c in chunks if c.metadata.clause}
    assert "2.1" in clauses or "2.2" in clauses


def test_metadata_propagation():
    chunks = LegalChunker(max_chars=2000).chunk_document(_doc(SAMPLE))
    for c in chunks:
        assert c.metadata.document_id == "doc-1"
        assert c.metadata.tenant_id == "acme"
        assert c.metadata.document_type == DocumentType.CONTRACT
        assert c.metadata.page_number == 1


def test_oversized_block_is_split_with_overlap():
    long_text = "Section 9. SCOPE\n" + (" ".join(f"sentence{i}." for i in range(400)))
    chunks = LegalChunker(max_chars=400, overlap_chars=50).chunk_document(_doc(long_text))
    assert len(chunks) > 1
    assert all(len(c.text) <= 600 for c in chunks)  # max + overlap slack
