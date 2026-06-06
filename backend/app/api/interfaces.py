"""Service-boundary interfaces for cross-domain collaborators.

The API layer owns the HTTP surface only. Routing, ingestion, generation, and
the document/structure store are owned by other agents (ai-engineer,
data-engineer, database-engineer) and are reached exclusively through these
typed protocols. This keeps imports of ``router`` / ``ingestion`` lazy and
lets the test suite mock at the boundary while those modules are built in
parallel (team AGREED CONTRACTS, _common_context.md).

The dataclasses mirror the AGREED CONTRACT shapes:
    * ``RouterDecision`` is the in-process LangGraph router output
      ``{relevant_sections[], page_ranges[], confidence[], fallback,
      routing_time_ms}`` (ai-engineer <-> python-backend-engineer).
    * ``DocumentRecord`` / ``SectionRecord`` mirror the Postgres structure
      store rows (db.models.Document / Section) that carry ``tenant_id`` -
      the IDOR-guard key.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class RoutedSection:
    """One section selected by the router with its authoritative page range.

    Attributes:
        section_id: Universal join/filter key.
        title: Section title from the TOC.
        page_start: Inclusive first page (Postgres authority, OAQ-3).
        page_end: Inclusive last page.
        confidence: Router confidence in [0, 1].
        document_id: Owning document (multi-document routing, FR-014).
    """

    section_id: str
    title: str
    page_start: int
    page_end: int
    confidence: float
    document_id: str | None = None


@dataclass(frozen=True)
class RouterDecision:
    """In-process router output (AGREED CONTRACT ai-engineer <-> backend).

    Attributes:
        relevant_sections: Sections to retrieve from (may be empty on fallback).
        fallback: True when all confidences fell below the threshold (FR-009).
        routing_time_ms: Router latency in milliseconds (NFR-001).
        rationale: Interpretable "why did you look here?" text (FR-012).
    """

    relevant_sections: list[RoutedSection]
    fallback: bool
    routing_time_ms: int
    rationale: str | None = None


@dataclass(frozen=True)
class SectionRecord:
    """A structure-store section row projection (db.models.Section).

    Attributes:
        section_id: Universal key.
        tenant_id: Owning tenant (IDOR guard).
        title: Section title.
        level: Hierarchy level (1 = chapter).
        page_start: Inclusive first page.
        page_end: Inclusive last page.
        summary: Optional router summary.
        pii_flags: PII field-name annotations only (never PII values, FR-029).
    """

    section_id: str
    tenant_id: str
    title: str | None
    level: int
    page_start: int
    page_end: int
    summary: str | None = None
    pii_flags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DocumentRecord:
    """A structure-store document row projection (db.models.Document).

    Attributes:
        doc_id: Stable document identifier.
        tenant_id: Owning tenant (IDOR guard).
        title: Optional human title.
        total_pages: Page count.
        domain: Optional domain label.
        residency_region: Data-residency region (FR-028).
        fallback_only: True for Scenario-C documents (OAQ-6).
        created_at: ISO-8601 creation timestamp.
        pii_flags: PII field-name annotations only (FR-029).
    """

    doc_id: str
    tenant_id: str
    title: str | None
    total_pages: int
    domain: str | None
    residency_region: str
    fallback_only: bool
    created_at: str
    pii_flags: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestOutcome:
    """Result of ingestion.ingest_document (AGREED CONTRACT backend <-> data).

    Attributes:
        doc_id: The created or reused document id (idempotent on hash).
        title: Resolved document title.
        total_pages: Page count.
        toc: Table-of-contents entries.
        ingest_status: indexed | fallback_only | ephemeral.
        deduplicated: True when identical content already existed.
    """

    doc_id: str
    title: str | None
    total_pages: int
    toc: list[SectionRecord]
    ingest_status: str
    deduplicated: bool


@runtime_checkable
class DocumentStore(Protocol):
    """Tenant-scoped structure-store access (database-engineer-owned).

    Every read/write is parameterized by ``tenant_id`` so a query can never
    span tenants (row-level IDOR guard). ``get_document`` returns None for an
    unknown OR tombstoned document so erasure is immediately invisible.
    """

    async def get_document(self, tenant_id: str, doc_id: str) -> DocumentRecord | None:
        """Fetch a document the tenant owns, or None if absent/tombstoned."""
        ...

    async def list_documents(
        self, tenant_id: str, page: int, page_size: int, domain: str | None
    ) -> tuple[list[DocumentRecord], int]:
        """Return a page of the tenant's documents and the total count."""
        ...

    async def get_sections(self, tenant_id: str, doc_id: str) -> list[SectionRecord]:
        """Return the tenant's sections (TOC) for a document."""
        ...

    async def tombstone_document(self, tenant_id: str, doc_id: str) -> bool:
        """Tombstone the document + enqueue erasure outbox; True if erased.

        Returns False if the document does not exist for the tenant.

        Raises:
            DependencyUnavailable: When the structure store is unreachable
                (surfaced as 503 per ADV-002).
        """
        ...


@runtime_checkable
class Router(Protocol):
    """In-process routing interface (ai-engineer-owned, router.route)."""

    async def route(
        self,
        tenant_id: str,
        document_ids: list[str],
        query: str,
        confidence_threshold: float,
        max_sections: int,
    ) -> RouterDecision:
        """Select relevant sections; never invokes the generation LLM."""
        ...


@runtime_checkable
class Ingestor(Protocol):
    """Ingestion interface (data-engineer-owned, ingestion.ingest_document)."""

    async def ingest_document(
        self,
        tenant_id: str,
        content: bytes,
        filename: str,
        title: str | None,
        domain: str | None,
        no_retention: bool,
        residency_region: str,
        ocr: bool,
    ) -> IngestOutcome:
        """Run parse -> TOC -> chunk -> embed -> upsert; idempotent on hash."""
        ...


@runtime_checkable
class GenerationLLM(Protocol):
    """Streaming generation interface (ai-engineer-owned; faked in tests)."""

    def stream_answer(
        self,
        query: str,
        sections: list[RoutedSection],
    ) -> AsyncIterator[str]:
        """Yield answer token fragments for the routed sections."""
        ...


class DependencyUnavailable(Exception):  # noqa: N818 - maps to SERVICE_UNAVAILABLE, not an *Error
    """Raised by a collaborator when a backing dependency is unreachable.

    The API layer maps this to a retryable 503 SERVICE_UNAVAILABLE problem
    (ADV-002 for deleteDocument; HLD graceful-degradation contract).
    """
