# Ingestion Pipeline

Document onboarding lives in `app/ingestion`. The pipeline
(`IngestionPipeline.ingest`) turns an uploaded file into indexed, retrievable
chunks with legal metadata.

## Flow

```
bytes
  → load (PDF / DOCX / TXT)        loaders.py    → page-preserving PageText[]
  → ingestion-time PII masking     safety/pii.py → mask_text per page
  → legal-aware chunking           chunking.py   → Chunk[] with metadata
  → embed + index                  retrieval/pipeline.py → dense + BM25
  → IngestionReport
```

## Loaders (`loaders.py`)

| Type | Library | Pages |
|---|---|---|
| `.txt` | builtin | single page |
| `.pdf` | pypdf | one `PageText` per PDF page (page numbers preserved) |
| `.docx` | python-docx | single page (paragraph structure preserved) |

PDF/DOCX parsers are imported lazily, so the module imports without the optional
dependencies.

## Legal-aware chunking (`chunking.py`)

Naive fixed-size chunking destroys the structure legal retrieval depends on. The
`LegalChunker` is **structure-first**:

1. **Detect boundaries** line-by-line:
   - Sections: `ARTICLE IV`, `Section 5`, `5. DEFINITIONS`
   - Clauses: `5.1`, `(a)`, `(ii)`, `Clause 7.2`
   - Headings: Title-Case / ALL-CAPS lines
2. **Group into blocks**, each tagged with the active section/clause/heading
   context (context carries across page breaks).
3. **Split oversized blocks** into overlapping windows on paragraph/sentence
   boundaries, with a hard word-level split fallback so no chunk exceeds
   `RETRIEVAL_CHUNK_MAX_CHARS` (overlap = `RETRIEVAL_CHUNK_OVERLAP_CHARS`).

### Chunk metadata
`document_id`, `document_name`, `tenant_id`, `document_type`, `section`,
`clause`, `heading`, `page_number`, `chunk_index`.

## PII masking at ingestion

Before chunking, each page is passed through `mask_text`, replacing detected PII
with typed placeholders (e.g. `<EMAIL_ADDRESS>`, `<IN_PAN>`). This guarantees PII
never reaches the vector store, BM25 index, or the LLM. Controlled by
`SAFETY_ENABLE_PII_MASKING`. See [SECURITY_GUIDE](SECURITY_GUIDE.md).

## API

```
POST /api/v1/documents/upload   (multipart: file, document_type)
→ DocumentSummary { document_id, document_name, document_type,
                    pages, chunks_indexed, pii_entities_masked }
```

Limits: 25 MB max; extensions restricted to `.pdf`, `.docx`, `.txt`. Ingested
documents are recorded in the `DocumentRegistry` and listed by `GET /documents`.

## Document types
`contract`, `compliance_manual`, `regulation`, `policy`, `legal_document`,
`unknown`.
