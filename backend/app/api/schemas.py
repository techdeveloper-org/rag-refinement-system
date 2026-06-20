"""Pydantic v2 request/response models mirroring openapi.yaml.

Each model maps one-to-one to a schema in
``docs/phase-1-api-contracts/openapi.yaml`` with identical field names,
constraints, and ``additionalProperties: false`` semantics (enforced via
``model_config = {"extra": "forbid"}``). Validation at this boundary is the
first line of input defence (common-standards Rule 2; NFR-008).

The ``RouteRequest`` model encodes the ``oneOf(document_id | document_ids)``
contract: providing both or neither is a validation error surfaced as 422
VALIDATION_ERROR (AC-ADV-001).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_DOC_ID_PATTERN = r"^doc_[A-Za-z0-9]{6,}$"
_SECTION_ID_PATTERN = r"^sec_[A-Za-z0-9]{1,}$"
_QUERY_ID_PATTERN = r"^qry_[A-Za-z0-9]{1,}$"
_TOKEN_REDUCTION_PATTERN = r"^[0-9]{1,3}%$"  # noqa: S105 - regex, not a secret

DocumentId = Annotated[str, Field(pattern=_DOC_ID_PATTERN)]
SectionId = Annotated[str, Field(pattern=_SECTION_ID_PATTERN)]
QueryId = Annotated[str, Field(pattern=_QUERY_ID_PATTERN)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
ResidencyRegion = Literal["IN", "EU", "US", "GLOBAL"]
_PageNumber = Annotated[int, Field(ge=1)]
PageRange = Annotated[list[_PageNumber], Field(min_length=2, max_length=2)]


class _Strict(BaseModel):
    """Base model that forbids unknown fields (additionalProperties: false)."""

    model_config = ConfigDict(extra="forbid")


class RouteRequest(_Strict):
    """Body of POST /v1/route (routeQuery).

    Exactly one of ``document_id`` or ``document_ids`` must be supplied
    (oneOf); both or neither is a 422 validation error (AC-ADV-001).
    """

    document_id: DocumentId | None = None
    document_ids: Annotated[list[DocumentId], Field(min_length=1, max_length=25)] | None = None
    query: Annotated[str, Field(min_length=1, max_length=4000)]
    confidence_threshold: Confidence = 0.7
    max_sections: Annotated[int, Field(ge=1, le=20)] = 3
    rerank: bool = False

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, v: str) -> str:
        """Reject whitespace-only queries that pass min_length=1.

        Args:
            v: The raw query string.

        Returns:
            The stripped query string.

        Raises:
            ValueError: When the query is blank after stripping.
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("query must not be blank or whitespace-only")
        return stripped

    @model_validator(mode="after")
    def _exactly_one_target(self) -> RouteRequest:
        """Enforce the oneOf(document_id | document_ids) contract.

        Returns:
            The validated model.

        Raises:
            ValueError: When both or neither document selector is provided.
        """
        has_single = self.document_id is not None
        has_multi = self.document_ids is not None
        if has_single == has_multi:
            raise ValueError(
                "exactly one of document_id or document_ids must be provided"
            )
        return self


class RelevantSection(_Strict):
    """A routed section with its authoritative page range and confidence."""

    section_id: SectionId
    document_id: DocumentId | None = None
    title: str
    page_start: Annotated[int, Field(ge=1)]
    page_end: Annotated[int, Field(ge=1)]
    confidence: Confidence


class RouteResponse(_Strict):
    """Body of a successful routeQuery (RouteResponse schema)."""

    query_id: QueryId
    relevant_sections: list[RelevantSection]
    page_ranges: list[PageRange]
    confidence: list[Confidence]
    fallback: bool
    routing_time_ms: Annotated[int, Field(ge=0)]
    rationale: str | None = None
    estimated_token_reduction: Annotated[str, Field(pattern=_TOKEN_REDUCTION_PATTERN)] | None = None


class AnswerRequest(_Strict):
    """Body of POST /v1/answer (answerQuery) - single document only (ADV-006)."""

    document_id: DocumentId
    query: Annotated[str, Field(min_length=1, max_length=4000)]
    confidence_threshold: Confidence = 0.7
    max_sections: Annotated[int, Field(ge=1, le=20)] = 3
    rerank: bool = False
    no_retention: bool = False

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, v: str) -> str:
        """Reject whitespace-only queries that pass min_length=1.

        Args:
            v: The raw query string.

        Returns:
            The stripped query string.

        Raises:
            ValueError: When the query is blank after stripping.
        """
        stripped = v.strip()
        if not stripped:
            raise ValueError("query must not be blank or whitespace-only")
        return stripped


class Citation(_Strict):
    """A cited section in an answer (Citation schema)."""

    section_id: SectionId | None = None
    section_title: str
    page_start: Annotated[int, Field(ge=1)]
    page_end: Annotated[int, Field(ge=1)]


class RoutingSummary(_Strict):
    """The routing projection carried on the SSE final event (RoutingSummary)."""

    sections: list[SectionId]
    confidence: list[Confidence]
    fallback: bool
    rationale: str | None = None


class TokenEvent(_Strict):
    """SSE ``event: token`` data payload (TokenEvent schema)."""

    query_id: QueryId | None = None
    token: str


class AnswerFinalEvent(_Strict):
    """SSE ``event: final`` data payload (AnswerFinalEvent schema)."""

    query_id: QueryId | None = None
    answer: str
    citations: list[Citation]
    routing: RoutingSummary


class TocEntry(_Strict):
    """A single table-of-contents entry (TocEntry schema)."""

    section_id: SectionId
    level: Annotated[int, Field(ge=1)]
    title: str
    page_start: Annotated[int, Field(ge=1)]
    page_end: Annotated[int, Field(ge=1)]
    summary: str | None = None


class IngestResponse(_Strict):
    """Body of a successful ingestDocument (IngestResponse schema)."""

    doc_id: DocumentId
    title: str | None = None
    total_pages: Annotated[int, Field(ge=0)] | None = None
    toc: list[TocEntry]
    ingest_status: Literal["indexed", "fallback_only", "ephemeral"]
    deduplicated: bool


class TocResponse(_Strict):
    """Body of getDocumentToc (TocResponse schema)."""

    document_id: DocumentId
    fallback_only: bool
    toc: list[TocEntry]


class Document(_Strict):
    """Document metadata (Document schema)."""

    doc_id: DocumentId
    title: str | None = None
    total_pages: Annotated[int, Field(ge=0)]
    domain: str | None = None
    tenant_id: str | None = None
    residency_region: ResidencyRegion
    fallback_only: bool
    created_at: str


class Pagination(_Strict):
    """Pagination envelope (Pagination schema)."""

    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1)]
    total_count: Annotated[int, Field(ge=0)]
    total_pages: Annotated[int, Field(ge=0)]


class DocumentListResponse(_Strict):
    """Body of listDocuments (DocumentListResponse schema)."""

    data: list[Document]
    pagination: Pagination


class PiiField(_Strict):
    """A PII field located in a document's stored data (PiiField schema)."""

    field: str
    location: str
    category: str | None = None


class DataAccessExport(_Strict):
    """Body of exportDocumentData (DataAccessExport schema, DPDP access)."""

    doc_id: DocumentId
    generated_at: str
    document: Document
    sections: list[TocEntry]
    pii_fields: list[PiiField]


class ErasureReceipt(_Strict):
    """Body of a successful deleteDocument (ErasureReceipt schema)."""

    doc_id: DocumentId
    erased: bool
    accepted_at: str
