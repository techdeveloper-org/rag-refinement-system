"""Ingestion pipeline orchestration (STORY-003/008/009/011).

Implements the data-engineer-owned ``ingest_document`` entry point that backend
calls: parse -> TOC -> section-aware chunk -> embed -> upsert, writing section
rows to Postgres (via ``db.models``) and chunk points to Qdrant (payload
``{chunk_id, section_id, doc_id, tenant_id, page}``, AGREED CONTRACT).

Invariants enforced here:
    * Idempotent on content hash - a re-upload of identical bytes reuses the same
      ``doc_id`` and produces the same deterministic chunk point ids, so no
      duplicate points are created (OAQ-1, STORY-003).
    * No chunk crosses a section boundary - delegated to and asserted by
      ``chunker.chunk_document`` (STORY-011 P0 invariant).
    * Scenario C documents are returned ``fallback_only=True`` and persist no
      sections (whole-document RAG path).
    * ``no_retention`` purges raw bytes and skips persistence so nothing is
      retained (DPDP no-retention mode).

The Postgres section store and the Qdrant vector store are accessed through the
``SectionStore`` and ``VectorStore`` Protocols so tests inject in-memory fakes
with no network, no real key, and no live database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ingestion.chunker import Chunk, chunk_document
from ingestion.embedder import EMBEDDING_DIM, Embedder, EmbedderDimensionError
from ingestion.ids import doc_id_for, section_id_for
from ingestion.parser import Parser, content_hash
from ingestion.toc_extractor import LlmRefiner, TocEntry, extract_toc

_DOC_ID_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
"""Stable namespace so a content hash maps to a deterministic doc_id (idempotency).

Retained for backward-compatible imports; the authoritative id format now lives in
``ingestion.ids`` (the single source of truth shared with the backend adapter).
"""


@dataclass(frozen=True)
class IngestInput:
    """Input to ``ingest_document``.

    Attributes:
        data: Raw PDF bytes (runtime data, never prompt context).
        tenant_id: Owning tenant; stamped on the document, sections, and every
            chunk payload (mandatory IDOR isolation key).
        title: Optional document title (structural metadata).
        domain: Optional domain tag.
        no_retention: When True, no raw bytes are retained and no rows/points are
            persisted (DPDP no-retention mode); the toc is still returned.
    """

    data: bytes
    tenant_id: str
    title: str | None = None
    domain: str | None = None
    no_retention: bool = False


@dataclass
class SectionRow:
    """A section row to persist in Postgres (mirrors ``db.models.Section``).

    Attributes:
        section_id: Universal key (deterministic from doc + ordinal).
        doc_id: Owning document id.
        tenant_id: Owning tenant id (IDOR guard).
        title: Section title.
        level: Hierarchy level.
        page_start: Inclusive first page.
        page_end: Inclusive last page.
    """

    section_id: str
    doc_id: str
    tenant_id: str
    title: str
    level: int
    page_start: int
    page_end: int


@runtime_checkable
class SectionStore(Protocol):
    """Postgres-facing port for documents + sections (idempotent on hash).

    A fake implementing this Protocol lets the pipeline be tested without a live
    database. Production wiring is a thin SQLAlchemy adapter over ``db.models``.
    """

    def find_doc_id_by_hash(self, tenant_id: str, content_hash_value: str) -> str | None:
        """Return an existing ``doc_id`` for this tenant + content hash, or None.

        Args:
            tenant_id: Owning tenant.
            content_hash_value: SHA-256 content hash of the upload.

        Returns:
            The existing document id for an identical prior upload, else None.
        """
        ...

    def upsert_document(
        self,
        doc_id: str,
        tenant_id: str,
        title: str | None,
        domain: str | None,
        total_pages: int,
        content_hash_value: str | None,
        ingest_status: str,
        fallback_only: bool,
    ) -> None:
        """Create or update the document row (tenant-scoped).

        Args:
            doc_id: Document primary key.
            tenant_id: Owning tenant.
            title: Optional title.
            domain: Optional domain.
            total_pages: Page count.
            content_hash_value: Content hash (None in no-retention mode).
            ingest_status: One of ``db.models.INGEST_STATUS_VALUES``.
            fallback_only: True when no structure was detected (Scenario C).
        """
        ...

    def replace_sections(self, tenant_id: str, doc_id: str, rows: list[SectionRow]) -> int:
        """Replace all sections for ``doc_id`` with ``rows`` (idempotent).

        Args:
            tenant_id: Owning tenant (cross-tenant delete guard).
            doc_id: Document whose sections are replaced.
            rows: New section rows.

        Returns:
            The number of section rows written.
        """
        ...

    def upsert_document_and_replace_sections(
        self,
        doc_id: str,
        tenant_id: str,
        title: str | None,
        domain: str | None,
        total_pages: int,
        content_hash_value: str | None,
        ingest_status: str,
        fallback_only: bool,
        rows: list[SectionRow],
    ) -> int:
        """Atomically upsert the document row and replace its sections.

        Args:
            doc_id: Document primary key.
            tenant_id: Owning tenant.
            title: Optional title.
            domain: Optional domain.
            total_pages: Page count.
            content_hash_value: Content hash (None in no-retention mode).
            ingest_status: One of the INGEST_STATUS_VALUES constants.
            fallback_only: True when no structure was detected (Scenario C).
            rows: New section rows to persist.

        Returns:
            The number of section rows written.
        """
        ...


@runtime_checkable
class VectorStore(Protocol):
    """Qdrant-facing port for idempotent chunk-point upsert.

    A fake implementing this Protocol lets the pipeline be tested without a live
    Qdrant. Production wiring upserts ``PointStruct`` records keyed by the
    deterministic chunk point id.
    """

    def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Upsert chunk points (deterministic ids make this idempotent).

        Args:
            points: Each a dict with ``id``, ``vector`` and ``payload`` keys; the
                payload is exactly ``{chunk_id, section_id, doc_id, tenant_id, page}``.

        Returns:
            The number of points upserted.
        """
        ...


@dataclass
class IngestResult:
    """Return shape of ``ingest_document`` (interface contract).

    Attributes:
        doc_id: Document id (reused on idempotent re-upload).
        toc: Resolved TOC entries serialized as ``{level, title, page_start,
            page_end}`` dicts.
        section_rows_written: Number of section rows persisted (0 in fallback /
            no-retention).
        chunks_upserted: Number of chunk points upserted (0 in fallback /
            no-retention).
        fallback_only: True for Scenario C (whole-document RAG path).
        total_pages: Actual page count from the parsed document (correct for all
            scenarios including Scenario C where toc is empty).
        pre_existing: True when the content hash was already present in the store
            before this ingest run (used to determine the dedup response code).
    """

    doc_id: str
    toc: list[dict[str, Any]] = field(default_factory=list)
    section_rows_written: int = 0
    chunks_upserted: int = 0
    fallback_only: bool = False
    total_pages: int = 0
    pre_existing: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Return the result as the plain dict the contract specifies.

        Returns:
            ``{doc_id, toc, section_rows_written, chunks_upserted, fallback_only,
            total_pages, pre_existing}``.
        """
        return {
            "doc_id": self.doc_id,
            "toc": self.toc,
            "section_rows_written": self.section_rows_written,
            "chunks_upserted": self.chunks_upserted,
            "fallback_only": self.fallback_only,
            "total_pages": self.total_pages,
            "pre_existing": self.pre_existing,
        }


def _deterministic_doc_id(tenant_id: str, content_hash_value: str) -> str:
    """Derive the canonical, prefixed ``doc_id`` from tenant + content hash.

    Thin wrapper over the single source of truth ``ingestion.ids.doc_id_for`` so
    the pipeline and backend adapter never diverge. Ensures a re-upload of
    identical content for the same tenant maps to the same document id even before
    the store dedup lookup (defense in depth, OAQ-1).

    Args:
        tenant_id: Owning tenant.
        content_hash_value: SHA-256 content hash.

    Returns:
        A deterministic ``doc_<32 hex>`` id matching ``^doc_[A-Za-z0-9]{6,}$``.
    """
    return doc_id_for(tenant_id, content_hash_value)


def _section_id(doc_id: str, ordinal: int) -> str:
    """Derive the canonical, prefixed ``section_id`` for the nth section.

    Thin wrapper over the single source of truth ``ingestion.ids.section_id_for``.

    Args:
        doc_id: Owning document id.
        ordinal: Zero-based section ordinal.

    Returns:
        A deterministic ``sec_<32 hex>`` id matching ``^sec_[A-Za-z0-9]+$``.
    """
    return section_id_for(doc_id, ordinal)


def _toc_to_dicts(entries: tuple[TocEntry, ...]) -> list[dict[str, Any]]:
    """Serialize TOC entries to the contract's dict shape.

    Args:
        entries: Resolved TOC entries.

    Returns:
        ``{level, title, page_start, page_end}`` dicts in order.
    """
    return [
        {
            "level": entry.level,
            "title": entry.title,
            "page_start": entry.page_start,
            "page_end": entry.page_end,
        }
        for entry in entries
    ]


def _build_section_rows(
    doc_id: str, tenant_id: str, entries: tuple[TocEntry, ...]
) -> list[tuple[SectionRow, TocEntry]]:
    """Pair each TOC entry with its persistable section row.

    Args:
        doc_id: Owning document id.
        tenant_id: Owning tenant id.
        entries: Resolved TOC entries.

    Returns:
        ``(SectionRow, TocEntry)`` pairs sharing a deterministic ``section_id``.
    """
    pairs: list[tuple[SectionRow, TocEntry]] = []
    for ordinal, entry in enumerate(entries):
        section_id = _section_id(doc_id, ordinal)
        row = SectionRow(
            section_id=section_id,
            doc_id=doc_id,
            tenant_id=tenant_id,
            title=entry.title,
            level=entry.level,
            page_start=entry.page_start,
            page_end=entry.page_end,
        )
        pairs.append((row, entry))
    return pairs


def _validate_embed_dimension(vectors: list[list[float]]) -> list[list[float]]:
    """Validate every embedding vector at the embed -> upsert boundary.

    This is the authoritative dimension guard: every vector produced by ANY embedder
    implementation converges here before points are built, so a bare adapter (one not
    wrapped in ``FallbackEmbedder``) that returns wrong-dimension vectors is rejected
    rather than silently upserted into the ``EMBEDDING_DIM``-sized Qdrant collection.

    Args:
        vectors: Vectors returned by ``embedder.embed(...)``.

    Returns:
        The same vectors unchanged when every length equals ``EMBEDDING_DIM``.

    Raises:
        EmbedderDimensionError: If any vector's length differs from ``EMBEDDING_DIM``.
    """
    for vector in vectors:
        if len(vector) != EMBEDDING_DIM:
            raise EmbedderDimensionError(
                f"embedder returned a {len(vector)}-dim vector; "
                f"expected {EMBEDDING_DIM} (Qdrant collection size)."
            )
    return vectors


def _chunk_point(chunk: Chunk, vector: list[float]) -> dict[str, Any]:
    """Build a Qdrant point dict from a chunk and its embedding.

    The point id is the deterministic ``chunk_id`` so re-upsert is idempotent;
    the payload is exactly the AGREED CONTRACT shape including ``tenant_id``.

    Args:
        chunk: The section-bounded chunk.
        vector: Its embedding vector.

    Returns:
        A point dict ``{id, vector, payload}``.
    """
    return {
        "id": chunk.chunk_id,
        "vector": vector,
        "payload": {
            "chunk_id": chunk.chunk_id,
            "section_id": chunk.section_id,
            "doc_id": chunk.doc_id,
            "tenant_id": chunk.tenant_id,
            "page": chunk.page,
        },
    }


def ingest_document(
    doc: IngestInput,
    *,
    parser: Parser,
    embedder: Embedder,
    section_store: SectionStore,
    vector_store: VectorStore,
    llm_refiner: LlmRefiner | None = None,
) -> dict[str, Any]:
    """Ingest a document end-to-end and return the contract result dict.

    Pipeline: hash + dedup -> parse -> TOC (Scenario A/B/C) -> on A/B persist
    sections + section-aware chunk + embed + upsert; on C return
    ``fallback_only=True`` with no persistence. ``no_retention`` skips all
    persistence and retains no bytes while still returning the resolved TOC.

    Args:
        doc: The upload (bytes, tenant, metadata, retention flag).
        parser: Injected PDF parser (Protocol).
        embedder: Injected embedding adapter (Protocol; 1536-dim).
        section_store: Injected Postgres-facing section store (Protocol).
        vector_store: Injected Qdrant-facing vector store (Protocol).
        llm_refiner: Optional Scenario-B header refiner hook.

    Returns:
        ``{doc_id, toc, section_rows_written, chunks_upserted, fallback_only}``.

    Raises:
        ValueError: When ``tenant_id`` is empty (mandatory IDOR key).
        EmbedderDimensionError: If the embedder returns any vector whose length is
            not ``EMBEDDING_DIM`` (authoritative embed -> upsert boundary guard).
        AssertionError: If chunking produces a cross-section chunk (STORY-011).
    """
    if not doc.tenant_id:
        raise ValueError("tenant_id is mandatory (IDOR isolation key).")
    if not doc.data:
        raise ValueError("Document content is empty; cannot ingest zero-byte file.")

    hash_value = content_hash(doc.data)
    if not doc.no_retention:
        existing = section_store.find_doc_id_by_hash(doc.tenant_id, hash_value)
    else:
        existing = None
    doc_id = existing or _deterministic_doc_id(doc.tenant_id, hash_value)

    parsed = parser.parse(doc.data)
    toc = extract_toc(parsed, llm_refiner=llm_refiner)
    toc_dicts = _toc_to_dicts(toc.entries)

    fallback_only_flag = toc.fallback_only
    section_rows_written = 0
    chunks_upserted = 0

    ingest_status = (
        "ephemeral" if doc.no_retention
        else ("fallback_only" if fallback_only_flag else "indexed")
    )

    if not doc.no_retention and not fallback_only_flag:
        pairs = _build_section_rows(doc_id, doc.tenant_id, toc.entries)
        section_rows_written = section_store.upsert_document_and_replace_sections(
            doc_id=doc_id,
            tenant_id=doc.tenant_id,
            title=doc.title,
            domain=doc.domain,
            total_pages=parsed.page_count,
            content_hash_value=hash_value,
            ingest_status=ingest_status,
            fallback_only=False,
            rows=[row for row, _ in pairs],
        )

        sections = [(row.section_id, entry) for row, entry in pairs]
        chunks = chunk_document(parsed, sections, doc_id, doc.tenant_id)

        if chunks:
            vectors = _validate_embed_dimension(
                embedder.embed([chunk.text for chunk in chunks])
            )
            points = [
                _chunk_point(chunk, vector)
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
            chunks_upserted = vector_store.upsert_points(points)
    else:
        section_store.upsert_document(
            doc_id=doc_id,
            tenant_id=doc.tenant_id,
            title=doc.title,
            domain=doc.domain,
            total_pages=parsed.page_count,
            content_hash_value=None if doc.no_retention else hash_value,
            ingest_status=ingest_status,
            fallback_only=fallback_only_flag,
        )

    return IngestResult(
        doc_id=doc_id,
        toc=toc_dicts,
        section_rows_written=section_rows_written,
        chunks_upserted=chunks_upserted,
        fallback_only=fallback_only_flag,
        total_pages=parsed.page_count,
        pre_existing=existing is not None,
    ).as_dict()
