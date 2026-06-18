"""Ingestion domain models: raw documents and chunks with legal metadata."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    CONTRACT = "contract"
    COMPLIANCE_MANUAL = "compliance_manual"
    REGULATION = "regulation"
    POLICY = "policy"
    LEGAL_DOCUMENT = "legal_document"
    UNKNOWN = "unknown"


class PageText(BaseModel):
    """Text content for a single source page (1-indexed)."""

    page_number: int
    text: str


class RawDocument(BaseModel):
    """A loaded, pre-chunk document."""

    document_id: str
    document_name: str
    tenant_id: str
    document_type: DocumentType = DocumentType.UNKNOWN
    pages: List[PageText] = Field(default_factory=list)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)


class ChunkMetadata(BaseModel):
    """Per-chunk metadata stored alongside the vector + sparse indexes.

    These fields power tenant isolation, citations (section/clause/page), and
    filtering during retrieval.
    """

    document_id: str
    document_name: str
    tenant_id: str
    document_type: DocumentType = DocumentType.UNKNOWN
    section: Optional[str] = None
    clause: Optional[str] = None
    heading: Optional[str] = None
    page_number: Optional[int] = None
    chunk_index: int = 0

    def to_store_dict(self) -> Dict[str, Any]:
        """Flat, JSON-scalar metadata for vector-store persistence."""

        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "tenant_id": self.tenant_id,
            "document_type": self.document_type.value,
            "section": self.section or "",
            "clause": self.clause or "",
            "heading": self.heading or "",
            "page_number": self.page_number if self.page_number is not None else -1,
            "chunk_index": self.chunk_index,
        }


class Chunk(BaseModel):
    """A retrievable unit of text plus its metadata."""

    chunk_id: str
    text: str
    metadata: ChunkMetadata
