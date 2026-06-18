"""
Document loaders for PDF, DOCX, and TXT.

Each loader returns a list of `PageText` so page numbers survive into chunk
metadata (critical for legal citations). PDF/DOCX parsers are imported lazily so
the module is importable without the optional dependencies installed.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List

from app.core.exceptions import ValidationAppError
from app.ingestion.models import PageText

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def load_txt(data: bytes) -> List[PageText]:
    text = data.decode("utf-8", errors="replace")
    return [PageText(page_number=1, text=text)]


def load_pdf(data: bytes) -> List[PageText]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ValidationAppError("PDF support requires the 'pypdf' package.") from exc

    reader = PdfReader(io.BytesIO(data))
    pages: List[PageText] = []
    for idx, page in enumerate(reader.pages, start=1):
        pages.append(PageText(page_number=idx, text=page.extract_text() or ""))
    return pages


def load_docx(data: bytes) -> List[PageText]:
    try:
        import docx  # python-docx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ValidationAppError("DOCX support requires the 'python-docx' package.") from exc

    document = docx.Document(io.BytesIO(data))
    # DOCX has no intrinsic pages; treat the whole document as page 1 but keep
    # paragraph structure (double newlines) so the chunker can detect headings.
    paragraphs = [p.text for p in document.paragraphs]
    return [PageText(page_number=1, text="\n".join(paragraphs))]


def load_bytes(filename: str, data: bytes) -> List[PageText]:
    """Dispatch to the correct loader based on file extension."""

    suffix = Path(filename).suffix.lower()
    if suffix == ".txt":
        return load_txt(data)
    if suffix == ".pdf":
        return load_pdf(data)
    if suffix == ".docx":
        return load_docx(data)
    raise ValidationAppError(
        f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}."
    )
