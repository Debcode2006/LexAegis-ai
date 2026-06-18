"""Document upload + explorer endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.deps import enforce_rate_limit, get_current_tenant
from app.core.exceptions import ValidationAppError
from app.ingestion.loaders import SUPPORTED_EXTENSIONS
from app.ingestion.models import DocumentType
from app.ingestion.pipeline import IngestionPipeline, get_ingestion_pipeline
from app.schemas.documents import DocumentListResponse, DocumentSummary
from app.services.document_registry import DocumentRegistry, get_document_registry

router = APIRouter(prefix="/documents", tags=["documents"])

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


@router.post(
    "/upload",
    response_model=DocumentSummary,
    summary="Upload and ingest a legal document",
    dependencies=[Depends(enforce_rate_limit)],
)
async def upload_document(
    file: UploadFile = File(...),
    document_type: DocumentType = Form(default=DocumentType.UNKNOWN),
    tenant_id: str = Depends(get_current_tenant),
    pipeline: IngestionPipeline = Depends(get_ingestion_pipeline),
    registry: DocumentRegistry = Depends(get_document_registry),
) -> DocumentSummary:
    filename = file.filename or "upload"
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValidationAppError(
            f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}."
        )

    data = await file.read()
    if not data:
        raise ValidationAppError("Uploaded file is empty.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise ValidationAppError("Uploaded file exceeds the 25 MB limit.")

    report = pipeline.ingest(
        filename=filename,
        data=data,
        tenant_id=tenant_id,
        document_type=document_type,
    )
    registry.register(report)
    return DocumentSummary(**report.model_dump())


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents ingested for the tenant",
    dependencies=[Depends(enforce_rate_limit)],
)
async def list_documents(
    tenant_id: str = Depends(get_current_tenant),
    registry: DocumentRegistry = Depends(get_document_registry),
) -> DocumentListResponse:
    reports = registry.list(tenant_id)
    return DocumentListResponse(
        tenant_id=tenant_id,
        count=len(reports),
        documents=[DocumentSummary(**r.model_dump()) for r in reports],
    )
