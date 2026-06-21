"""Tests for the production ingestion stores (SqlAlchemy + Qdrant adapters).

``backend.app.adapters.stores`` holds the synchronous ports the ingestion
pipeline persists through: ``SqlAlchemySectionStore`` (documents + sections over
``db.models``) and ``QdrantVectorStore`` (chunk points). These tests run the
section store against an in-memory SQLite engine and the vector store against an
in-memory Qdrant client, so no live Postgres or Qdrant is required.
"""

from __future__ import annotations

import pytest
from db.models import Base, Document, Section
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from backend.app.adapters.stores import QdrantVectorStore, SqlAlchemySectionStore
from ingestion.pipeline import SectionRow


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json(type_: object, compiler: object, **kw: object) -> str:
    """Render the Postgres ``JSONB`` type as ``JSON`` for the SQLite test schema."""
    return "JSON"


@compiles(BigInteger, "sqlite")
def _compile_bigint_as_integer(type_: object, compiler: object, **kw: object) -> str:
    """Render ``BIGINT`` as ``INTEGER`` so the SQLite PK autoincrements."""
    return "INTEGER"


@pytest.fixture
def sync_session_factory() -> sessionmaker[Session]:
    """Build a synchronous in-memory SQLite session factory with the schema."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _section_row(doc_id: str, ordinal: int, tenant_id: str) -> SectionRow:
    """Build a section row fixture."""
    return SectionRow(
        section_id=f"sec_{doc_id}_{ordinal}",
        doc_id=doc_id,
        tenant_id=tenant_id,
        title=f"Section {ordinal}",
        level=1,
        page_start=ordinal + 1,
        page_end=ordinal + 2,
    )


class TestSqlAlchemySectionStore:
    """The synchronous Postgres section store (idempotent on content hash)."""

    def test_upsert_creates_then_updates_document(
        self, sync_session_factory: sessionmaker[Session]
    ) -> None:
        """An upsert creates the row, and a second upsert updates it in place."""
        store = SqlAlchemySectionStore(sync_session_factory)
        store.upsert_document(
            doc_id="doc_1",
            tenant_id="tenant_a",
            title="First",
            domain="legal",
            total_pages=10,
            content_hash_value="hash_1",
            ingest_status="indexed",
            fallback_only=False,
        )
        store.upsert_document(
            doc_id="doc_1",
            tenant_id="tenant_a",
            title="Updated",
            domain="finance",
            total_pages=12,
            content_hash_value="hash_1",
            ingest_status="indexed",
            fallback_only=True,
        )
        with sync_session_factory() as session:
            row = session.get(Document, "doc_1")
        assert row is not None
        assert row.title == "Updated"
        assert row.total_pages == 12
        assert row.fallback_only is True

    def test_find_doc_id_by_hash_returns_existing(
        self, sync_session_factory: sessionmaker[Session]
    ) -> None:
        """A prior upload with the same content hash is found by hash (OAQ-1)."""
        store = SqlAlchemySectionStore(sync_session_factory)
        store.upsert_document(
            doc_id="doc_1",
            tenant_id="tenant_a",
            title="T",
            domain=None,
            total_pages=3,
            content_hash_value="hash_1",
            ingest_status="indexed",
            fallback_only=False,
        )
        found = store.find_doc_id_by_hash("tenant_a", "hash_1")
        assert found == "doc_1"

    def test_find_doc_id_by_hash_returns_none_for_unknown(
        self, sync_session_factory: sessionmaker[Session]
    ) -> None:
        """An unknown content hash yields None (a fresh upload)."""
        store = SqlAlchemySectionStore(sync_session_factory)
        assert store.find_doc_id_by_hash("tenant_a", "missing") is None

    def test_find_doc_id_by_hash_is_tenant_scoped(
        self, sync_session_factory: sessionmaker[Session]
    ) -> None:
        """The same hash for another tenant is not matched (IDOR guard)."""
        store = SqlAlchemySectionStore(sync_session_factory)
        store.upsert_document(
            doc_id="doc_1",
            tenant_id="tenant_a",
            title="T",
            domain=None,
            total_pages=3,
            content_hash_value="shared_hash",
            ingest_status="indexed",
            fallback_only=False,
        )
        assert store.find_doc_id_by_hash("tenant_b", "shared_hash") is None

    def test_replace_sections_is_idempotent(
        self, sync_session_factory: sessionmaker[Session]
    ) -> None:
        """Replacing sections deletes the old set and writes the new one."""
        store = SqlAlchemySectionStore(sync_session_factory)
        store.upsert_document(
            doc_id="doc_1",
            tenant_id="tenant_a",
            title="T",
            domain=None,
            total_pages=10,
            content_hash_value="hash_1",
            ingest_status="indexed",
            fallback_only=False,
        )
        first = [_section_row("doc_1", i, "tenant_a") for i in range(3)]
        written = store.replace_sections("tenant_a", "doc_1", first)
        assert written == 3
        second = [_section_row("doc_1", i, "tenant_a") for i in range(2)]
        store.replace_sections("tenant_a", "doc_1", second)
        with sync_session_factory() as session:
            rows = (
                session.execute(select(Section).where(Section.doc_id == "doc_1"))
                .scalars()
                .all()
            )
        assert len(rows) == 2

    def test_replace_sections_empty_list_is_noop(
        self, sync_session_factory: sessionmaker[Session]
    ) -> None:
        """replace_sections([]) returns 0 and does NOT delete existing sections."""
        store = SqlAlchemySectionStore(sync_session_factory)
        store.upsert_document(
            doc_id="doc_1",
            tenant_id="tenant_a",
            title="T",
            domain=None,
            total_pages=10,
            content_hash_value="hash_1",
            ingest_status="indexed",
            fallback_only=False,
        )
        initial = [_section_row("doc_1", i, "tenant_a") for i in range(3)]
        store.replace_sections("tenant_a", "doc_1", initial)
        result = store.replace_sections("tenant_a", "doc_1", [])
        assert result == 0
        with sync_session_factory() as session:
            rows = (
                session.execute(select(Section).where(Section.doc_id == "doc_1"))
                .scalars()
                .all()
            )
        assert len(rows) == 3

    def test_from_database_url_builds_store(self) -> None:
        """from_database_url builds a store without opening a connection."""
        store = SqlAlchemySectionStore.from_database_url("sqlite:///:memory:")
        assert isinstance(store, SqlAlchemySectionStore)


def _point(chunk_id: str, vector_size: int = 1536) -> dict[str, object]:
    """Build a chunk point dict with the AGREED CONTRACT payload shape."""
    import uuid

    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id)),
        "vector": [0.0] * vector_size,
        "payload": {
            "chunk_id": chunk_id,
            "section_id": "sec_1",
            "doc_id": "doc_1",
            "page": 1,
            "tenant_id": "tenant_a",
        },
    }


class TestQdrantVectorStore:
    """The synchronous Qdrant chunk-point store (idempotent on deterministic ids)."""

    def test_upsert_empty_points_returns_zero(self) -> None:
        """Upserting no points is a no-op returning 0 (never touches the client)."""
        store = QdrantVectorStore(client=object())
        assert store.upsert_points([]) == 0

    def test_upsert_points_into_in_memory_qdrant(self) -> None:
        """Points are upserted into an in-memory Qdrant collection."""
        from db.qdrant_bootstrap import (
            COLLECTION_NAME,
            VECTOR_SIZE,
            bootstrap_collection,
        )
        from qdrant_client import QdrantClient

        client = QdrantClient(":memory:")
        bootstrap_collection(client)
        store = QdrantVectorStore(client=client)
        count = store.upsert_points([_point("chunk_1", VECTOR_SIZE)])
        assert count == 1
        stored = client.count(collection_name=COLLECTION_NAME).count
        assert stored == 1

    def test_upsert_points_is_idempotent_on_id(self) -> None:
        """Re-upserting the same id does not duplicate the point (idempotency)."""
        from db.qdrant_bootstrap import (
            COLLECTION_NAME,
            VECTOR_SIZE,
            bootstrap_collection,
        )
        from qdrant_client import QdrantClient

        client = QdrantClient(":memory:")
        bootstrap_collection(client)
        store = QdrantVectorStore(client=client)
        store.upsert_points([_point("chunk_1", VECTOR_SIZE)])
        store.upsert_points([_point("chunk_1", VECTOR_SIZE)])
        assert client.count(collection_name=COLLECTION_NAME).count == 1
