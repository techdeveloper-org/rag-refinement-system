"""Production ingestion ports: SQLAlchemy section store + Qdrant vector store.

The ``ingestion`` pipeline reaches Postgres and Qdrant through its own synchronous
``SectionStore`` and ``VectorStore`` Protocols. These are the thin production
adapters the pipeline's docstrings reference: ``SqlAlchemySectionStore`` persists
documents + sections via ``db.models`` (idempotent on content hash), and
``QdrantVectorStore`` upserts chunk points keyed by their deterministic id.

Both are synchronous because the pipeline is synchronous; the backend runs the
pipeline in a worker thread (see ``PipelineIngestor``). Connection details resolve
from the environment (``DATABASE_URL`` / ``QDRANT_URL``); no DSN or key is
hardcoded. These adapters only touch the network when the live ingestor provider
is actually invoked, so importing this module requires no live services.
"""

from __future__ import annotations

import threading
from typing import Any

from db.models import Document, Section
from sqlalchemy import create_engine, delete, insert, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.interfaces import DependencyUnavailable
from backend.app.errors import ProblemException
from ingestion.pipeline import SectionRow


class SqlAlchemySectionStore:
    """Synchronous Postgres section store over ``db.models`` (idempotent).

    Implements the pipeline's ``SectionStore`` Protocol: content-hash dedup lookup,
    document upsert, and full section replacement, all tenant-stamped. Each method
    runs in its own short-lived session.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        """Bind the store to a synchronous session factory.

        Args:
            session_factory: Factory yielding synchronous ORM sessions.
        """
        self._session_factory = session_factory

    @classmethod
    def from_database_url(cls, database_url: str) -> SqlAlchemySectionStore:
        """Build a section store from a synchronous PostgreSQL DSN.

        Args:
            database_url: SQLAlchemy DSN (e.g. ``postgresql+psycopg://...``).

        Returns:
            A store bound to a freshly created engine/session factory.
        """
        engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
        if not database_url.startswith("sqlite"):
            engine_kwargs.update(
                pool_size=2,
                max_overflow=3,
                pool_timeout=30,
                pool_recycle=3600,
            )
        engine = create_engine(database_url, **engine_kwargs)
        factory = sessionmaker(engine, expire_on_commit=False)
        return cls(factory)

    def find_doc_id_by_hash(self, tenant_id: str, content_hash_value: str) -> str | None:
        """Return an existing ``doc_id`` for this tenant + content hash, or None.

        Args:
            tenant_id: Owning tenant.
            content_hash_value: SHA-256 content hash of the upload.

        Returns:
            The existing document id for an identical prior upload, else None.
        """
        stmt = select(Document.doc_id).where(
            Document.tenant_id == tenant_id,
            Document.content_hash == content_hash_value,
            Document.tombstoned_at.is_(None),
        )
        try:
            with self._session_factory() as session:
                return session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc

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
        residency_region: str = "GLOBAL",
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
            residency_region: DPDP data-residency region (FR-028); defaults to GLOBAL.
        """
        try:
            with self._session_factory() as session, session.begin():
                row = session.scalar(
                    select(Document).where(
                        Document.doc_id == doc_id, Document.tenant_id == tenant_id
                    ).with_for_update()
                )
                if row is None:
                    row = Document(doc_id=doc_id, tenant_id=tenant_id)
                    session.add(row)
                if row.tombstoned_at is not None:
                    raise ProblemException(
                        status_code=409,
                        code="DOCUMENT_CONFLICT",
                        title="Conflict",
                        detail=f"Cannot resurrect tombstoned document doc_id={doc_id!r}",
                        problem_type="document-conflict",
                    )
                row.title = title
                row.domain = domain
                row.total_pages = total_pages
                row.content_hash = content_hash_value
                row.ingest_status = ingest_status
                row.fallback_only = fallback_only
                row.residency_region = residency_region
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc

    def replace_sections(self, tenant_id: str, doc_id: str, rows: list[SectionRow]) -> int:
        """Replace all sections for ``doc_id`` with ``rows`` (idempotent).

        **Caller contract:** When ``rows`` is empty this method returns 0
        without deleting existing sections. Callers that need to clear
        sections as part of a re-ingest cycle must use
        :meth:`upsert_document_and_replace_sections`, which unconditionally
        deletes before inserting.

        Args:
            tenant_id: Owning tenant (cross-tenant delete guard).
            doc_id: Document whose sections are replaced.
            rows: New section rows.

        Returns:
            The number of section rows written.

        Raises:
            DependencyUnavailable: When the structure store is unreachable.
        """
        if not rows:
            return 0
        try:
            with self._session_factory() as session, session.begin():
                session.execute(
                    delete(Section).where(
                        Section.doc_id == doc_id,
                        Section.tenant_id == tenant_id,
                    )
                )
                session.execute(
                    insert(Section),
                    [
                        {
                            "section_id": row.section_id,
                            "doc_id": row.doc_id,
                            "tenant_id": row.tenant_id,
                            "title": row.title,
                            "level": row.level,
                            "page_start": row.page_start,
                            "page_end": row.page_end,
                            "summary": None,
                            "pii_flags": {},
                        }
                        for row in rows
                    ],
                )
                return len(rows)
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc

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
        residency_region: str = "GLOBAL",
    ) -> int:
        """Atomically upsert the document row and replace its sections in one transaction.

        Combines :meth:`upsert_document` and :meth:`replace_sections` in a single
        database transaction so a partial failure cannot leave a document row without
        matching section rows (or vice versa).

        Args:
            doc_id: Document primary key.
            tenant_id: Owning tenant (IDOR guard on both document and section delete).
            title: Optional title.
            domain: Optional domain.
            total_pages: Page count.
            content_hash_value: Content hash (None in no-retention mode).
            ingest_status: One of ``db.models.INGEST_STATUS_VALUES``.
            fallback_only: True when no structure was detected (Scenario C).
            rows: New section rows to persist (may be empty for fallback-only docs).
            residency_region: DPDP data-residency region (FR-028); defaults to GLOBAL.

        Returns:
            The number of section rows written.

        Raises:
            DependencyUnavailable: When the structure store is unreachable.
        """
        try:
            with self._session_factory() as session, session.begin():
                doc_row = session.scalar(
                    select(Document).where(
                        Document.doc_id == doc_id, Document.tenant_id == tenant_id
                    ).with_for_update()
                )
                if doc_row is None:
                    doc_row = Document(doc_id=doc_id, tenant_id=tenant_id)
                    session.add(doc_row)
                if doc_row.tombstoned_at is not None:
                    raise ProblemException(
                        status_code=409,
                        code="DOCUMENT_CONFLICT",
                        title="Conflict",
                        detail=f"Cannot resurrect tombstoned document doc_id={doc_id!r}",
                        problem_type="document-conflict",
                    )
                doc_row.title = title
                doc_row.domain = domain
                doc_row.total_pages = total_pages
                doc_row.content_hash = content_hash_value
                doc_row.ingest_status = ingest_status
                doc_row.fallback_only = fallback_only
                doc_row.residency_region = residency_region

                session.execute(
                    delete(Section).where(
                        Section.doc_id == doc_id,
                        Section.tenant_id == tenant_id,
                    )
                )
                if rows:
                    session.execute(
                        insert(Section),
                        [
                            {
                                "section_id": row.section_id,
                                "doc_id": row.doc_id,
                                "tenant_id": row.tenant_id,
                                "title": row.title,
                                "level": row.level,
                                "page_start": row.page_start,
                                "page_end": row.page_end,
                                "summary": None,
                                "pii_flags": {},
                            }
                            for row in rows
                        ],
                    )
                return len(rows)
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc

    def update_residency_region(self, doc_id: str, tenant_id: str, residency_region: str) -> None:
        """Update the residency_region for a document (DPDP FR-028).

        Called after ingestion completes to stamp the DPDP data-residency region
        requested by the caller, which the synchronous pipeline cannot persist
        because IngestInput has no residency field.

        Args:
            doc_id: Document primary key.
            tenant_id: Owning tenant (IDOR guard).
            residency_region: One of IN, EU, US, GLOBAL.

        Raises:
            DependencyUnavailable: When the structure store is unreachable.
        """
        stmt = select(Document).where(
            Document.doc_id == doc_id,
            Document.tenant_id == tenant_id,
            Document.tombstoned_at.is_(None),
        )
        try:
            with self._session_factory() as session, session.begin():
                row = session.scalar(stmt)
                if row is not None:
                    row.residency_region = residency_region
        except SQLAlchemyError as exc:
            raise DependencyUnavailable("structure store unreachable") from exc


class QdrantVectorStore:
    """Synchronous Qdrant chunk-point store (idempotent on deterministic ids).

    Implements the pipeline's ``VectorStore`` Protocol. The Qdrant client is built
    lazily from ``QDRANT_URL`` so importing this module needs no live Qdrant.
    """

    def __init__(self, client: object | None = None) -> None:
        """Initialize the vector store.

        Args:
            client: Optional pre-built ``qdrant_client.QdrantClient``; constructed
                lazily from ``QDRANT_URL`` when omitted.
        """
        self._client = client
        self._client_lock = threading.Lock()

    def _ensure_client(self) -> object:
        """Lazily construct the Qdrant client from ``QDRANT_URL`` (thread-safe).

        Uses double-checked locking so concurrent ingestion threads do not race
        to create multiple client instances.

        Returns:
            The Qdrant client instance.
        """
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    from db.qdrant_bootstrap import get_client

                    self._client = get_client()
        return self._client

    def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Upsert chunk points (deterministic ids make this idempotent).

        Args:
            points: Each a dict with ``id``, ``vector`` and ``payload`` keys.

        Returns:
            The number of points upserted.
        """
        if not points:
            return 0
        from db.qdrant_bootstrap import COLLECTION_NAME
        from qdrant_client import models as qm

        client = self._ensure_client()
        structs = [
            qm.PointStruct(id=point["id"], vector=point["vector"], payload=point["payload"])
            for point in points
        ]
        result = client.upsert(collection_name=COLLECTION_NAME, points=structs)  # type: ignore[attr-defined]
        if hasattr(result, "status") and result.status != qm.UpdateStatus.COMPLETED:
            raise DependencyUnavailable(
                f"Qdrant upsert did not complete; status={result.status}"
            )
        return len(points)

    def delete_points_for_doc(self, doc_id: str) -> None:
        """Delete all Qdrant points whose payload ``doc_id`` matches ``doc_id``.

        Used as a compensating rollback when a Postgres commit succeeds but a
        subsequent Qdrant upsert fails, to prevent orphaned vectors (issue #208).
        The deletion is best-effort; callers must not rely on it for correctness
        since re-ingest via deterministic point ids is idempotent.

        Args:
            doc_id: The document id whose chunk points should be deleted.
        """
        from db.qdrant_bootstrap import COLLECTION_NAME
        from qdrant_client import models as qm

        client = self._ensure_client()
        client.delete(  # type: ignore[attr-defined]
            collection_name=COLLECTION_NAME,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))]
                )
            ),
        )
