"""
Document registry.

Lightweight in-process catalog of ingested documents per tenant, powering the
Document Explorer. The vector store and BM25 index are optimized for retrieval,
not enumeration, so this registry keeps the document-level metadata needed to
list what a tenant has uploaded.

For local/single-process use this lives in memory; a production deployment would
back it with the application database (e.g. a Supabase/Postgres table).
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from app.ingestion.pipeline import IngestionReport


class DocumentRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # tenant_id -> {document_id -> report}
        self._docs: Dict[str, Dict[str, IngestionReport]] = {}

    def register(self, report: IngestionReport) -> None:
        with self._lock:
            self._docs.setdefault(report.tenant_id, {})[report.document_id] = report

    def list(self, tenant_id: str) -> List[IngestionReport]:
        with self._lock:
            return list(self._docs.get(tenant_id, {}).values())

    def get(self, tenant_id: str, document_id: str) -> Optional[IngestionReport]:
        with self._lock:
            return self._docs.get(tenant_id, {}).get(document_id)

    def reset(self) -> None:
        with self._lock:
            self._docs.clear()


_registry: Optional[DocumentRegistry] = None


def get_document_registry() -> DocumentRegistry:
    global _registry
    if _registry is None:
        _registry = DocumentRegistry()
    return _registry
