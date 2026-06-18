"""Document upload / explorer schemas."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel

from app.ingestion.models import DocumentType


class DocumentSummary(BaseModel):
    document_id: str
    document_name: str
    tenant_id: str
    document_type: DocumentType
    pages: int
    chunks_indexed: int
    pii_entities_masked: int


class DocumentListResponse(BaseModel):
    tenant_id: str
    count: int
    documents: List[DocumentSummary]
