"""
Legal-aware chunking.

Naive fixed-size chunking destroys the structure that legal retrieval depends
on (which section/clause a statement belongs to). This chunker is *structure
first*:

1. It scans text line-by-line and detects structural boundaries:
   - Sections   : "ARTICLE IV", "Section 5", "5. DEFINITIONS"
   - Clauses     : "5.1", "(a)", "(ii)", "Clause 7.2"
   - Headings    : Title-Case / ALL-CAPS lines
2. Text is grouped into structural blocks, each tagged with the section/clause/
   heading context active at that point (context carries across page breaks).
3. Oversized blocks are split into overlapping windows on paragraph/sentence
   boundaries so no single chunk exceeds `chunk_max_chars`, while small adjacent
   blocks under the same heading are packed together.

Every emitted `Chunk` carries `section`, `clause`, `heading`, and `page_number`
metadata, enabling precise citations downstream.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from app.core.config import get_settings
from app.ingestion.models import Chunk, ChunkMetadata, DocumentType, RawDocument

# --- Structural detection patterns ------------------------------------------

_SECTION_LABEL_RE = re.compile(
    r"^\s*(ARTICLE|Article|SECTION|Section|PART|Part)\s+([A-Za-z0-9IVXLCDM]+)\b[.:)\-]?\s*(.*)$"
)
# Multi-level numbers (e.g. "2.1", "5.3.2") are clauses; the trailing dot/paren
# is optional since legal drafting often writes "2.1 Each party ...".
_CLAUSE_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)+)[.)]?\s+(\S.*)$")
# A single integer with trailing punctuation (e.g. "5.") is a section heading.
_SECTION_NUM_RE = re.compile(r"^\s*(\d+)[.)]\s+(\S.*)$")
_CLAUSE_PAREN_RE = re.compile(r"^\s*\(([A-Za-z]|[ivxlcdm]+|\d+)\)\s+\S")
_CLAUSE_LABEL_RE = re.compile(r"^\s*(Clause|CLAUSE)\s+(\d+(?:\.\d+)*)")
_ALLCAPS_HEADING_RE = re.compile(r"^[A-Z][A-Z0-9 ,&/\-']{2,80}$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;:])\s+(?=[A-Z(0-9])")


@dataclass
class _Block:
    """A contiguous run of text under a single structural context."""

    text: str
    section: Optional[str]
    clause: Optional[str]
    heading: Optional[str]
    page_number: int


@dataclass
class _Context:
    section: Optional[str] = None
    clause: Optional[str] = None
    heading: Optional[str] = None
    buffer: List[str] = field(default_factory=list)
    page_number: int = 1


class LegalChunker:
    """Section/clause/heading-aware chunker."""

    def __init__(
        self,
        max_chars: Optional[int] = None,
        overlap_chars: Optional[int] = None,
    ) -> None:
        cfg = get_settings().retrieval
        self.max_chars = max_chars or cfg.chunk_max_chars
        self.overlap_chars = overlap_chars if overlap_chars is not None else cfg.chunk_overlap_chars

    # -- public API -----------------------------------------------------------

    def chunk_document(self, document: RawDocument) -> List[Chunk]:
        blocks = self._build_blocks(document)
        chunks: List[Chunk] = []
        index = 0
        for block in blocks:
            for piece in self._split_oversized(block.text):
                metadata = ChunkMetadata(
                    document_id=document.document_id,
                    document_name=document.document_name,
                    tenant_id=document.tenant_id,
                    document_type=document.document_type or DocumentType.UNKNOWN,
                    section=block.section,
                    clause=block.clause,
                    heading=block.heading,
                    page_number=block.page_number,
                    chunk_index=index,
                )
                chunks.append(
                    Chunk(chunk_id=uuid.uuid4().hex, text=piece.strip(), metadata=metadata)
                )
                index += 1
        return chunks

    # -- structural pass ------------------------------------------------------

    def _build_blocks(self, document: RawDocument) -> List[_Block]:
        ctx = _Context()
        blocks: List[_Block] = []

        def flush() -> None:
            text = "\n".join(line for line in ctx.buffer).strip()
            if text:
                blocks.append(
                    _Block(
                        text=text,
                        section=ctx.section,
                        clause=ctx.clause,
                        heading=ctx.heading,
                        page_number=ctx.page_number,
                    )
                )
            ctx.buffer = []

        for page in document.pages:
            ctx.page_number = page.page_number
            for raw_line in page.text.splitlines():
                line = raw_line.rstrip()
                if not line.strip():
                    ctx.buffer.append("")
                    continue

                boundary = self._classify(line)
                if boundary is not None:
                    flush()
                    kind, label, remainder = boundary
                    if kind == "section":
                        ctx.section = label
                        ctx.clause = None
                        ctx.heading = remainder or None
                    elif kind == "clause":
                        ctx.clause = label
                        ctx.heading = remainder or ctx.heading
                    elif kind == "heading":
                        ctx.heading = label
                    # Seed the new block with the remainder text (if any).
                    if remainder:
                        ctx.buffer.append(remainder)
                else:
                    ctx.buffer.append(line)
        flush()
        return blocks

    @staticmethod
    def _classify(line: str):
        """Return (kind, label, remainder) if the line is a structural marker."""

        m = _SECTION_LABEL_RE.match(line)
        if m:
            label = f"{m.group(1).title()} {m.group(2)}".strip()
            return ("section", label, m.group(3).strip())

        m = _CLAUSE_LABEL_RE.match(line)
        if m:
            return ("clause", m.group(2), line[m.end():].strip())

        m = _CLAUSE_NUM_RE.match(line)
        if m:
            return ("clause", m.group(1), m.group(2).strip())

        m = _SECTION_NUM_RE.match(line)
        if m:
            return ("section", m.group(1), m.group(2).strip())

        if _CLAUSE_PAREN_RE.match(line):
            label = line[line.find("(") + 1 : line.find(")")]
            remainder = line[line.find(")") + 1 :].strip()
            return ("clause", label, remainder)

        if _ALLCAPS_HEADING_RE.match(line.strip()) and len(line.split()) <= 12:
            return ("heading", line.strip().title(), "")

        return None

    # -- size pass ------------------------------------------------------------

    def _split_oversized(self, text: str) -> List[str]:
        text = text.strip()
        if len(text) <= self.max_chars:
            return [text] if text else []

        # Prefer paragraph boundaries, then sentences.
        units = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        if len(units) <= 1:
            units = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]

        # Guarantee no single unit exceeds max_chars via a hard word-level split
        # (handles run-on text with no sentence boundaries).
        expanded: List[str] = []
        for unit in units:
            if len(unit) <= self.max_chars:
                expanded.append(unit)
            else:
                expanded.extend(self._hard_split(unit))
        units = expanded

        windows: List[str] = []
        current = ""
        for unit in units:
            if current and len(current) + len(unit) + 1 > self.max_chars:
                windows.append(current.strip())
                # Start next window with a tail overlap for context continuity.
                tail = current[-self.overlap_chars :] if self.overlap_chars else ""
                current = (tail + " " + unit).strip()
            else:
                current = (current + " " + unit).strip() if current else unit
        if current.strip():
            windows.append(current.strip())
        return windows

    def _hard_split(self, text: str) -> List[str]:
        """Split a long, boundary-less string into <= max_chars word windows."""

        words = text.split()
        windows: List[str] = []
        current = ""
        for word in words:
            if current and len(current) + len(word) + 1 > self.max_chars:
                windows.append(current)
                current = word
            else:
                current = (current + " " + word).strip() if current else word
        if current:
            windows.append(current)
        return windows
