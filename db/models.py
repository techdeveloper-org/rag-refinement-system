"""SQLAlchemy 2.0 typed models for the RAG Refinement structure store.

These models mirror ``migrations/001_documents_sections.sql`` one-to-one. They
are the relational Level-1 (Document) and Level-2 (Section) hierarchy that feeds
the router and the Qdrant payload filter (HLD section 4.1/4.2, ADR-10).

Design invariants (kept identical to the DDL):
    * ``section_id`` is the universal join/filter key across Document -> Section
      -> Qdrant chunk (HLD section 4.1, OAQ-3).
    * No chunk vectors are stored here. Vectors live ONLY in Qdrant (ADR-2);
      there is deliberately no vector / embedding column on any model.
    * ``tenant_id`` is NOT NULL on every row - the row-level IDOR guard that
      makes cross-tenant reads impossible without an explicit tenant filter
      (OAQ-5; AGREED CONTRACT python-backend-engineer <-> database-engineer).
    * ``page_start <= page_end`` is enforced by a table CHECK; Postgres sections
      are the single source of truth for page ranges (OAQ-3).
    * ``pii_flags`` / ``residency_region`` carry DPDP metadata (FR-028/FR-029)
      as field-name annotations only - never PII values.
    * ``ErasureOutbox`` + ``Document.tombstoned_at`` implement the OAQ-2 outbox
      + reconciliation sweep that lets Qdrant cleanup reconcile a deletion.

All access through these models uses SQLAlchemy's parameter binding, so queries
are parameterized by construction (no string-concatenated SQL).
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

INGEST_STATUS_VALUES: tuple[str, ...] = ("indexed", "fallback_only", "ephemeral")
"""Allowed ``documents.ingest_status`` values (matches IngestResponse enum)."""

RESIDENCY_REGION_VALUES: tuple[str, ...] = ("IN", "EU", "US", "GLOBAL")
"""Allowed ``documents.residency_region`` values (matches Document enum)."""

ERASURE_STORE_VALUES: tuple[str, ...] = ("qdrant", "object_store", "postgres")
"""Stores a tombstone can target in the OAQ-2 outbox."""

ERASURE_STATUS_VALUES: tuple[str, ...] = ("pending", "done", "error")
"""Lifecycle states of an erasure-outbox tombstone row."""


class Base(DeclarativeBase):
    """Declarative base for all structure-store models."""


class Document(Base):
    """Level-1 document metadata (PostgreSQL ``documents`` table, ADR-10).

    Holds document management metadata (AC-024) plus the DPDP residency / PII
    annotations. ``content_hash`` backs idempotent re-upload dedup (OAQ-1) and is
    nullable because the ephemeral no-retention path persists no hash.
    ``tombstoned_at`` is the OAQ-2 erasure tombstone making the row invisible to
    ``GET`` while the reconciliation sweep removes downstream vectors.
    """

    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    ingest_status: Mapped[str] = mapped_column(
        Enum(*INGEST_STATUS_VALUES, name="ingest_status"),
        nullable=False,
        default="indexed",
    )
    fallback_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    residency_region: Mapped[str] = mapped_column(
        Enum(*RESIDENCY_REGION_VALUES, name="residency_region"),
        nullable=False,
        default="GLOBAL",
    )
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    pii_flags: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    tombstoned_at: Mapped[_dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sections: Mapped[list[Section]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint("total_pages >= 0", name="documents_total_pages_nonneg"),
        Index("idx_documents_tenant_id", "tenant_id"),
        Index("idx_documents_domain", "domain"),
        Index(
            "idx_documents_content_hash",
            "content_hash",
            postgresql_where=content_hash.isnot(None),
        ),
    )


class Section(Base):
    """Level-2 section with authoritative page range (``sections`` table).

    ``section_id`` is the universal key. ``tenant_id`` is duplicated here so a
    direct section read is tenant-scoped without a join (IDOR guard). The
    ``ON DELETE CASCADE`` foreign key removes sections with their document. There
    is intentionally no vector column - chunk vectors live only in Qdrant.
    """

    __tablename__ = "sections"

    section_id: Mapped[str] = mapped_column(Text, primary_key=True)
    doc_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.doc_id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    page_start: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pii_flags: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    document: Mapped[Document] = relationship(back_populates="sections")

    __table_args__ = (
        CheckConstraint("level >= 1", name="sections_level_positive"),
        CheckConstraint("page_start >= 1", name="sections_page_start_positive"),
        CheckConstraint(
            "page_start <= page_end", name="sections_page_range_valid"
        ),
        Index("idx_sections_doc_id_page_start", "doc_id", "page_start"),
        Index("idx_sections_tenant_id", "tenant_id"),
    )


class ErasureOutbox(Base):
    """OAQ-2 erasure outbox row - one tombstone per ``(doc_id, store)``.

    Written inside the ``DELETE /v1/documents/{id}`` transaction. A worker
    deletes the target store's data and a periodic sweep reconciles any orphan
    whose ``doc_id`` is tombstoned, so Qdrant vector cleanup stays consistent
    with the Postgres erasure (DPDP FR-025, HLD OAQ-2).
    """

    __tablename__ = "erasure_outbox"

    outbox_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    doc_id: Mapped[str] = mapped_column(Text, nullable=False)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    store: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"
    )
    created_at: Mapped[_dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[_dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "store IN ('qdrant', 'object_store', 'postgres')",
            name="erasure_outbox_store_valid",
        ),
        CheckConstraint(
            "status IN ('pending', 'done', 'error')",
            name="erasure_outbox_status_valid",
        ),
        Index("idx_erasure_outbox_status", "status"),
        Index("idx_erasure_outbox_doc_id", "doc_id"),
    )
