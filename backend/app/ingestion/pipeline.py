"""
Ingestion pipeline.

End-to-end document onboarding:

    bytes
      → load (PDF/DOCX/TXT)
      → ingestion-time PII masking
      → legal-aware chunking (section/clause/heading metadata)
      → embed + index (dense vector store + BM25)

Returns an `IngestionReport` summarizing what was stored, including how much PII
was redacted before persistence.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ingestion.chunking import LegalChunker
from app.ingestion.loaders import load_bytes
from app.ingestion.models import DocumentType, PageText, RawDocument
from app.retrieval.pipeline import HybridRetriever, get_retriever
from app.safety.pii import PIIDetector, get_pii_detector, mask_text

logger = get_logger(__name__)


class IngestionReport(BaseModel):
    document_id: str
    document_name: str
    tenant_id: str
    document_type: DocumentType
    pages: int
    chunks_indexed: int
    pii_entities_masked: int


class IngestionPipeline:
    def __init__(
        self,
        retriever: Optional[HybridRetriever] = None,
        chunker: Optional[LegalChunker] = None,
        detector: Optional[PIIDetector] = None,
    ) -> None:
        self._retriever = retriever or get_retriever()
        self._chunker = chunker or LegalChunker()
        self._detector = detector or get_pii_detector()
        self._mask_enabled = get_settings().safety.enable_pii_masking

    def ingest(
        self,
        *,
        filename: str,
        data: bytes,
        tenant_id: str,
        document_type: DocumentType = DocumentType.UNKNOWN,
        document_id: Optional[str] = None,
        document_name: Optional[str] = None,
    ) -> IngestionReport:
        document_id = document_id or uuid.uuid4().hex
        document_name = document_name or filename

        pages = load_bytes(filename, data)

        # Ingestion-time PII masking (page by page so offsets stay local).
        masked_count = 0
        if self._mask_enabled:
            masked_pages: List[PageText] = []
            for page in pages:
                result = mask_text(page.text, self._detector)
                masked_count += len(result.entities)
                masked_pages.append(PageText(page_number=page.page_number, text=result.masked_text))
            pages = masked_pages

        raw = RawDocument(
            document_id=document_id,
            document_name=document_name,
            tenant_id=tenant_id,
            document_type=document_type,
            pages=pages,
        )

        chunks = self._chunker.chunk_document(raw)
        indexed = self._retriever.index_chunks(chunks)

        logger.info(
            "Ingested document_id=%s name=%s chunks=%d pii_masked=%d",
            document_id,
            document_name,
            indexed,
            masked_count,
        )
        return IngestionReport(
            document_id=document_id,
            document_name=document_name,
            tenant_id=tenant_id,
            document_type=document_type,
            pages=len(pages),
            chunks_indexed=indexed,
            pii_entities_masked=masked_count,
        )


_pipeline: Optional[IngestionPipeline] = None


def get_ingestion_pipeline() -> IngestionPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = IngestionPipeline()
    return _pipeline
