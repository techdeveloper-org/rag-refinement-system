"""Document management + DPDP compliance endpoints.

Implements ingestDocument, listDocuments, getDocument, getDocumentToc,
deleteDocument (DPDP erasure, STORY-034 sibling), and exportDocumentData
(DPDP access, STORY-034). Every read/write is tenant-scoped through the
document store so a caller can never reach another tenant's document (IDOR
guard; a cross-tenant id resolves to None -> 404). deleteDocument returns 202
on success and a retryable 503 when the structure store is down (ADV-002).
"""

from __future__ import annotations

import datetime as _dt
import math

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Path, Query, Response, UploadFile, status

from backend.app.api.dependencies import get_document_store, get_ingestor
from backend.app.api.helpers import build_pii_inventory
from backend.app.api.interfaces import (
    DependencyUnavailable,
    DocumentRecord,
    DocumentStore,
    Ingestor,
    SectionRecord,
)
from backend.app.api.schemas import (
    DataAccessExport,
    Document,
    DocumentListResponse,
    ErasureReceipt,
    IngestResponse,
    Pagination,
    TocEntry,
    TocResponse,
)
from backend.app.errors import (
    document_not_found,
    payload_too_large,
    service_unavailable,
    unsupported_media_type,
    validation_error,
)
from backend.app.security.auth import Principal
from backend.app.security.rate_limit import rate_limit
from backend.app.settings import get_settings

router = APIRouter(prefix="/v1/documents", tags=["Documents"])

_PDF_CONTENT_TYPE = "application/pdf"
_RESIDENCY_REGIONS = {"IN", "EU", "US", "GLOBAL"}
_UPLOAD_CHUNK_BYTES = 1 * 1024 * 1024
_DOC_ID_PATTERN = r"^doc_[A-Za-z0-9]{6,}$"

_DocumentIdPath = Annotated[str, Path(pattern=_DOC_ID_PATTERN)]


def _is_pdf_content_type(content_type: str | None) -> bool:
    """Return whether a request content type names the PDF media type (FIX-10).

    Normalizes the raw header before comparing: parameters after the first
    semicolon (for example ``charset=binary``) are stripped and the bare media
    type is trimmed and lowercased, so ``application/pdf; charset=utf-8`` and
    ``application/pdf;`` are accepted while a missing/empty header or a genuinely
    different type is rejected.

    Args:
        content_type: The raw request ``Content-Type`` header value, if any.

    Returns:
        True when the bare media type is ``application/pdf``; False otherwise.
    """
    if not content_type:
        return False
    bare_type = content_type.split(";", 1)[0].strip().lower()
    return bare_type == _PDF_CONTENT_TYPE


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string.

    Returns:
        The timezone-aware current UTC timestamp.
    """
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


async def _read_capped(file: UploadFile, max_bytes: int) -> bytes:
    """Read the upload body in chunks, rejecting once the cap is exceeded.

    Streams the body in fixed-size chunks rather than reading an unbounded body
    into memory, so a hostile or accidental oversize upload is rejected with 413
    after at most ``max_bytes`` (plus one chunk) have been buffered.

    Args:
        file: The incoming multipart upload.
        max_bytes: Maximum number of body bytes to accept.

    Returns:
        The fully read body bytes when within the cap.

    Raises:
        ProblemException: 413 when the body exceeds ``max_bytes``.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise payload_too_large()
        chunks.append(chunk)
    return b"".join(chunks)


def _to_document_schema(record: DocumentRecord) -> Document:
    """Map a structure-store document record to the API Document schema.

    Args:
        record: The structure-store document record.

    Returns:
        The corresponding :class:`Document` response model.
    """
    return Document(
        doc_id=record.doc_id,
        title=record.title,
        total_pages=record.total_pages,
        domain=record.domain,
        residency_region=record.residency_region,
        fallback_only=record.fallback_only,
        created_at=record.created_at,
    )


def _to_toc_entry(section: SectionRecord) -> TocEntry:
    """Map a structure-store section record to a TocEntry.

    Args:
        section: The structure-store section record.

    Returns:
        The corresponding :class:`TocEntry`.
    """
    return TocEntry(
        section_id=section.section_id,
        level=section.level,
        title=section.title or "",
        page_start=section.page_start,
        page_end=section.page_end,
        summary=section.summary,
    )


@router.post(
    "",
    operation_id="ingestDocument",
    response_model=IngestResponse,
    response_model_exclude_none=True,
)
async def ingest_document(
    response: Response,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    domain: str | None = Form(default=None),
    no_retention: bool = Form(default=False),
    residency_region: str = Form(default="GLOBAL"),
    ocr: bool = Form(default=False),
    principal: Principal = Depends(rate_limit()),
    ingestor: Ingestor = Depends(get_ingestor),
) -> IngestResponse:
    """Upload and ingest a PDF (parse -> TOC -> chunk -> embed -> index).

    Idempotent on content hash: identical content reuses the existing doc_id
    and returns 200 instead of 201 (AGREED CONTRACT backend <-> data-engineer).

    Args:
        response: The response whose status is set to 201/200.
        file: The uploaded PDF (must be application/pdf).
        title: Optional human title.
        domain: Optional domain label.
        no_retention: Purge artifacts after processing (FR-027).
        residency_region: Data-residency region (FR-028).
        ocr: Force OCR fallback (Scenario C, FR-017).
        principal: The authenticated, rate-limited caller.
        ingestor: The ingestion pipeline.

    Returns:
        An :class:`IngestResponse` with the doc_id, TOC, and dedup flag.

    Raises:
        ProblemException: 415 for a non-PDF upload; 422 for an invalid
            residency region; 503 when ingestion is unreachable.
    """
    if not _is_pdf_content_type(file.content_type):
        raise unsupported_media_type()
    if residency_region not in _RESIDENCY_REGIONS:
        raise validation_error(
            errors=[{"field": "residency_region", "message": "must be IN, EU, US, or GLOBAL"}]
        )

    content = await _read_capped(file, get_settings().max_upload_bytes)
    if not content:
        raise validation_error(errors=[{"field": "file", "message": "file is empty"}])

    try:
        outcome = await ingestor.ingest_document(
            tenant_id=principal.tenant_id,
            content=content,
            filename=file.filename or "upload.pdf",
            title=title,
            domain=domain,
            no_retention=no_retention,
            residency_region=residency_region,
            ocr=ocr,
        )
    except DependencyUnavailable as exc:
        raise service_unavailable(str(exc) or "Ingestion dependency unavailable.") from exc

    response.status_code = (
        status.HTTP_200_OK if outcome.deduplicated else status.HTTP_201_CREATED
    )
    if not outcome.deduplicated:
        response.headers["Location"] = f"/v1/documents/{outcome.doc_id}"

    return IngestResponse(
        doc_id=outcome.doc_id,
        title=outcome.title,
        total_pages=outcome.total_pages,
        toc=[_to_toc_entry(section) for section in outcome.toc],
        ingest_status=outcome.ingest_status,
        deduplicated=outcome.deduplicated,
    )


@router.get(
    "",
    operation_id="listDocuments",
    response_model=DocumentListResponse,
    response_model_exclude_none=True,
)
async def list_documents(
    # le=10_000 prevents OFFSET amplification attacks
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=20, ge=1, le=100),
    domain: str | None = Query(default=None, max_length=64),
    principal: Principal = Depends(rate_limit()),
    store: DocumentStore = Depends(get_document_store),
) -> DocumentListResponse:
    """List the caller's documents (tenant-scoped, paginated).

    Args:
        page: 1-based page number.
        page_size: Items per page (1..100).
        domain: Optional domain filter.
        principal: The authenticated, rate-limited caller.
        store: Tenant-scoped document store.

    Returns:
        A :class:`DocumentListResponse` page plus pagination metadata.
    """
    try:
        records, total_count = await store.list_documents(
            principal.tenant_id, page, page_size, domain
        )
    except DependencyUnavailable as exc:
        raise service_unavailable(
            str(exc) or "Document store unavailable."
        ) from exc
    total_pages = math.ceil(total_count / page_size) if page_size else 0
    if page > max(1, total_pages):
        raise validation_error(
            detail="Requested page exceeds total pages.",
            errors=[{"field": "page", "message": f"must be <= {total_pages}"}],
        )
    return DocumentListResponse(
        data=[_to_document_schema(record) for record in records],
        pagination=Pagination(
            page=page,
            page_size=page_size,
            total_count=total_count,
            total_pages=total_pages,
        ),
    )


@router.get(
    "/{doc_id}",
    operation_id="getDocument",
    response_model=Document,
    response_model_exclude_none=True,
)
async def get_document(
    doc_id: _DocumentIdPath,
    principal: Principal = Depends(rate_limit()),
    store: DocumentStore = Depends(get_document_store),
) -> Document:
    """Retrieve metadata for a document the caller owns (IDOR-guarded).

    Args:
        doc_id: The document identifier.
        principal: The authenticated, rate-limited caller.
        store: Tenant-scoped document store.

    Returns:
        The :class:`Document` metadata.

    Raises:
        ProblemException: 404 when the document is absent for the tenant
            (cross-tenant access resolves to not-found, not a leak).
    """
    try:
        record = await store.get_document(principal.tenant_id, doc_id)
    except DependencyUnavailable as exc:
        raise service_unavailable(
            str(exc) or "Document store unavailable."
        ) from exc
    if record is None:
        raise document_not_found()
    return _to_document_schema(record)


@router.get(
    "/{doc_id}/toc",
    operation_id="getDocumentToc",
    response_model=TocResponse,
    response_model_exclude_none=True,
)
async def get_document_toc(
    doc_id: _DocumentIdPath,
    principal: Principal = Depends(rate_limit()),
    store: DocumentStore = Depends(get_document_store),
) -> TocResponse:
    """Return the document's table of contents (tenant-scoped).

    Args:
        doc_id: The document identifier.
        principal: The authenticated, rate-limited caller.
        store: Tenant-scoped document store.

    Returns:
        A :class:`TocResponse`; ``toc`` is empty and ``fallback_only`` is True
        for Scenario-C documents with no usable structure.

    Raises:
        ProblemException: 404 when the document is absent for the tenant.
    """
    try:
        record = await store.get_document(principal.tenant_id, doc_id)
    except DependencyUnavailable as exc:
        raise service_unavailable(
            str(exc) or "Document store unavailable."
        ) from exc
    if record is None:
        raise document_not_found()
    try:
        sections = await store.get_sections(principal.tenant_id, doc_id)
    except DependencyUnavailable as exc:
        raise service_unavailable(
            str(exc) or "Document store unavailable."
        ) from exc
    return TocResponse(
        document_id=doc_id,
        fallback_only=record.fallback_only,
        toc=[_to_toc_entry(section) for section in sections],
    )


@router.delete(
    "/{doc_id}",
    operation_id="deleteDocument",
    tags=["Compliance"],
    response_model=ErasureReceipt,
    status_code=status.HTTP_202_ACCEPTED,
    response_model_exclude_none=True,
)
async def delete_document(
    doc_id: _DocumentIdPath,
    principal: Principal = Depends(rate_limit(sensitive=True)),
    store: DocumentStore = Depends(get_document_store),
) -> ErasureReceipt:
    """Erase a document and all derived data (DPDP right to erasure, FR-025).

    Tombstones the document (immediately invisible) and enqueues the erasure
    outbox for the reconciliation sweep (OAQ-2). Idempotent: a second delete of
    an already-erased document returns 404.

    Args:
        doc_id: The document identifier.
        principal: The authenticated caller (tighter sensitive rate limit).
        store: Tenant-scoped document store.

    Returns:
        A 202 :class:`ErasureReceipt`.

    Raises:
        ProblemException: 404 when the document is absent for the tenant;
            503 (retryable) when the structure store is down (ADV-002).
    """
    try:
        erased = await store.tombstone_document(principal.tenant_id, doc_id)
    except DependencyUnavailable as exc:
        raise service_unavailable(
            str(exc) or "The structure store is unreachable; retry the erasure."
        ) from exc

    if not erased:
        raise document_not_found()

    return ErasureReceipt(doc_id=doc_id, erased=True, accepted_at=_now_iso())


@router.get(
    "/{doc_id}/data",
    operation_id="exportDocumentData",
    tags=["Compliance"],
    response_model=DataAccessExport,
    response_model_exclude_none=True,
)
async def export_document_data(
    doc_id: _DocumentIdPath,
    principal: Principal = Depends(rate_limit(sensitive=True)),
    store: DocumentStore = Depends(get_document_store),
) -> DataAccessExport:
    """Export the personal data held for a document (DPDP access, STORY-034).

    Returns the caller's own document data plus an inventory of the x-pii
    annotated FIELD NAMES held for the document (FR-029) - never PII values
    baked into code, and never another tenant's data (IDOR-guarded).

    Args:
        doc_id: The document identifier.
        principal: The authenticated caller (tighter sensitive rate limit).
        store: Tenant-scoped document store.

    Returns:
        A :class:`DataAccessExport` with document, sections, and pii_fields.

    Raises:
        ProblemException: 404 when the document is absent for the tenant.
    """
    try:
        record = await store.get_document(principal.tenant_id, doc_id)
    except DependencyUnavailable as exc:
        raise service_unavailable(
            str(exc) or "Document store unavailable."
        ) from exc
    if record is None:
        raise document_not_found()
    try:
        sections = await store.get_sections(principal.tenant_id, doc_id)
    except DependencyUnavailable as exc:
        raise service_unavailable(
            str(exc) or "Document store unavailable."
        ) from exc
    return DataAccessExport(
        doc_id=doc_id,
        generated_at=_now_iso(),
        document=_to_document_schema(record),
        sections=[_to_toc_entry(section) for section in sections],
        pii_fields=build_pii_inventory(record, sections),
    )
