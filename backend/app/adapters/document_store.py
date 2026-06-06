"""SQLAlchemy DocumentStore adapter over ``db.models`` (database-engineer-owned).

Implements the backend :class:`DocumentStore` Protocol against the PostgreSQL
structure store (``db.models.Document`` / ``Section`` / ``ErasureOutbox``). Every
query is parameterized by ``tenant_id`` so a read can never span tenants - the
row-level IDOR guard. ``get_document`` returns ``None`` for an unknown OR
tombstoned document so a DPDP erasure is immediately invisible.

The store uses the async SQLAlchemy engine; a session factory is built lazily
from ``Settings.database_url`` (12-factor, no hardcoded DSN) and reused across
calls. The DELETE path writes the erasure outbox inside the same transaction as
the tombstone (OAQ-2) so the reconciliation sweep can clean Qdrant. When the
database is unreachable the adapter raises :class:`DependencyUnavailable`, which
the API layer maps to a retryable 503 (ADV-002).
"""

from __future__ import annotations

import datetime as _dt

from db.models import Document, ErasureOutbox, Section
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.api.interfaces import (
    DependencyUnavailable,
    DocumentRecord,
    SectionRecord,
)

_ERASURE_STORES: tuple[str, ...] = ("qdrant", "object_store", "postgres")
"""Downstream stores a tombstone targets in the OAQ-2 outbox."""


def _to_document_record(row: Document) -> DocumentRecord:
    """Project a ``db.models.Document`` row onto the backend DocumentRecord.

    Args:
        row: The persisted document row.

    Returns:
        The boundary :class:`DocumentRecord` the API layer consumes.
    """
    return DocumentRecord(
        doc_id=row.doc_id,
        tenant_id=row.tenant_id,
        title=row.title,
        total_pages=row.total_pages,
        domain=row.domain,
        residency_region=row.residency_region,
        fallback_only=row.fallback_only,
        created_at=row.created_at.isoformat() if row.created_at else "",
        pii_flags=dict(row.pii_flags or {}),
    )


def _to_section_record(row: Section) -> SectionRecord:
    """Project a ``db.models.Section`` row onto the backend SectionRecord.

    Args:
        row: The persisted section row.

    Returns:
        The boundary :class:`SectionRecord` (TOC entry) for the API layer.
    """
    return SectionRecord(
        section_id=row.section_id,
        tenant_id=row.tenant_id,
        title=row.title,
        level=row.level,
        page_start=row.page_start,
        page_end=row.page_end,
        summary=row.summary,
        pii_flags=dict(row.pii_flags or {}),
    )


class SqlAlchemyDocumentStore:
    """Tenant-scoped structure-store accessor backed by SQLAlchemy 2.0 async.

    Wraps an async session factory over ``db.models``. The factory is supplied by
    the composition root or constructed lazily from ``Settings.database_url`` so
    importing this module never opens a connection. Each public method runs in
    its own short-lived session; the tombstone path is transactional.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Bind the store to an async session factory.

        Args:
            session_factory: Factory yielding tenant-agnostic async sessions; the
                tenant filter is applied per query, not per session.
        """
        self._session_factory = session_factory

    @classmethod
    def from_database_url(cls, database_url: str) -> SqlAlchemyDocumentStore:
        """Build a store from a PostgreSQL DSN (composition-root helper).

        Args:
            database_url: SQLAlchemy async DSN (e.g. ``postgresql+asyncpg://...``).

        Returns:
            A store bound to a freshly created async engine/session factory.
        """
        engine = create_async_engine(database_url, pool_pre_ping=True)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        return cls(factory)

    async def get_document(self, tenant_id: str, doc_id: str) -> DocumentRecord | None:
        """Fetch a document the tenant owns, or None if absent/tombstoned.

        Args:
            tenant_id: Owning tenant (IDOR guard).
            doc_id: Document identifier.

        Returns:
            The :class:`DocumentRecord`, or None when the tenant does not own a
            live (non-tombstoned) document with this id.

        Raises:
            DependencyUnavailable: When the structure store is unreachable.
        """
        stmt = select(Document).where(
            Document.doc_id == doc_id,
            Document.tenant_id == tenant_id,
            Document.tombstoned_at.is_(None),
        )
        try:
            async with self._session_factory() as session:
                row = (await session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc
        return _to_document_record(row) if row is not None else None

    async def list_documents(
        self, tenant_id: str, page: int, page_size: int, domain: str | None
    ) -> tuple[list[DocumentRecord], int]:
        """Return a page of the tenant's documents and the total count.

        Args:
            tenant_id: Owning tenant (IDOR guard).
            page: 1-based page number.
            page_size: Items per page.
            domain: Optional domain filter.

        Returns:
            A tuple of (page of records, total count) for live documents only.

        Raises:
            DependencyUnavailable: When the structure store is unreachable.
        """
        base = (
            Document.tenant_id == tenant_id,
            Document.tombstoned_at.is_(None),
        )
        filters = (*base, Document.domain == domain) if domain is not None else base
        count_stmt = select(func.count()).select_from(Document).where(*filters)
        page_stmt = (
            select(Document)
            .where(*filters)
            .order_by(Document.created_at, Document.doc_id)
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        )
        try:
            async with self._session_factory() as session:
                total = (await session.execute(count_stmt)).scalar_one()
                rows = (await session.execute(page_stmt)).scalars().all()
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc
        return [_to_document_record(row) for row in rows], int(total)

    async def get_sections(self, tenant_id: str, doc_id: str) -> list[SectionRecord]:
        """Return the tenant's sections (TOC) for a document, ordered by page.

        Args:
            tenant_id: Owning tenant (IDOR guard).
            doc_id: Document identifier.

        Returns:
            The section records in page order, or an empty list when the tenant
            does not own a live document with this id.

        Raises:
            DependencyUnavailable: When the structure store is unreachable.
        """
        owns = await self.get_document(tenant_id, doc_id)
        if owns is None:
            return []
        stmt = (
            select(Section)
            .where(Section.doc_id == doc_id, Section.tenant_id == tenant_id)
            .order_by(Section.page_start, Section.section_id)
        )
        try:
            async with self._session_factory() as session:
                rows = (await session.execute(stmt)).scalars().all()
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc
        return [_to_section_record(row) for row in rows]

    async def tombstone_document(self, tenant_id: str, doc_id: str) -> bool:
        """Tombstone the document and enqueue the erasure outbox (OAQ-2).

        Sets ``tombstoned_at`` (making the row immediately invisible to reads)
        and inserts one ``ErasureOutbox`` row per downstream store inside a single
        transaction so the reconciliation sweep can clean Qdrant/object storage.

        Args:
            tenant_id: Owning tenant (IDOR guard).
            doc_id: Document identifier.

        Returns:
            True when an owned, live document was tombstoned; False when no such
            document exists for the tenant (idempotent second delete -> 404).

        Raises:
            DependencyUnavailable: When the structure store is unreachable.
        """
        stmt = select(Document).where(
            Document.doc_id == doc_id,
            Document.tenant_id == tenant_id,
            Document.tombstoned_at.is_(None),
        )
        try:
            async with self._session_factory() as session:
                async with session.begin():
                    row = (await session.execute(stmt)).scalar_one_or_none()
                    if row is None:
                        return False
                    row.tombstoned_at = _dt.datetime.now(_dt.UTC)
                    for store in _ERASURE_STORES:
                        session.add(
                            ErasureOutbox(
                                doc_id=doc_id,
                                tenant_id=tenant_id,
                                store=store,
                                status="pending",
                            )
                        )
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc
        return True
