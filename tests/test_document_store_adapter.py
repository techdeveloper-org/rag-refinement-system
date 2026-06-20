"""Integration tests for the production SQLAlchemy document-store adapter.

These exercise ``backend.app.adapters.document_store.SqlAlchemyDocumentStore``
against a real in-memory SQLite async engine (aiosqlite). They cover the IDOR
tenant guard, tombstone invisibility, the erasure-outbox cascade (OAQ-2), the
list pagination path, and the ``DependencyUnavailable`` (503) error path that
ADV-002 requires. No live Postgres is needed.
"""

from __future__ import annotations

import asyncio
import datetime as _dt

import pytest
from db.models import Base, Document, ErasureOutbox, Section
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.adapters.document_store import (
    SqlAlchemyDocumentStore,
    _to_document_record,
    _to_section_record,
)
from backend.app.api.interfaces import DependencyUnavailable

pytestmark = pytest.mark.anyio

TENANT_A = "tenant_a"
TENANT_B = "tenant_b"


def _enable_jsonb_on_sqlite() -> None:
    """Render the Postgres ``JSONB`` type as ``JSON`` under the SQLite dialect.

    The production models target Postgres (``JSONB``). SQLite has no JSONB
    compiler, so this registers a one-line dialect override that lets the same
    metadata create the in-memory test schema. It is a test-time compiler hook
    only and does not alter the production type.
    """
    from sqlalchemy import BigInteger
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles

    @compiles(JSONB, "sqlite")
    def _compile_jsonb_as_json(type_: object, compiler: object, **kw: object) -> str:
        return "JSON"

    @compiles(BigInteger, "sqlite")
    def _compile_bigint_as_integer(
        type_: object, compiler: object, **kw: object
    ) -> str:
        return "INTEGER"


_enable_jsonb_on_sqlite()


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only (no trio dependency)."""
    return "asyncio"


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    """Build an in-memory SQLite async session factory with the schema created.

    A StaticPool keeps the single in-memory SQLite database alive across the
    connections opened by the adapter's short-lived sessions. The schema is
    created synchronously so this works as a plain (non-async) fixture.
    """
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    return async_sessionmaker(engine, expire_on_commit=False)


class _FailingFactory:
    """Async session factory that raises a SQLAlchemyError on use.

    Used to drive the ``DependencyUnavailable`` (503) error path deterministically
    without a real database connection or DNS lookup.
    """

    def __call__(self) -> AsyncSession:
        raise OperationalError("stmt", {}, Exception("structure store down"))


async def _seed_document(
    factory: async_sessionmaker[AsyncSession],
    doc_id: str,
    tenant_id: str,
    *,
    domain: str = "legal",
    sections: int = 1,
    tombstoned: bool = False,
) -> None:
    """Insert one document (and optional sections) for a tenant."""
    async with factory() as session, session.begin():
        session.add(
            Document(
                doc_id=doc_id,
                tenant_id=tenant_id,
                title="Title",
                total_pages=10,
                domain=domain,
                ingest_status="indexed",
                fallback_only=False,
                residency_region="IN",
                content_hash="hash_" + doc_id,
                pii_flags={},
                tombstoned_at=_dt.datetime.now(_dt.UTC) if tombstoned else None,
                created_at=_dt.datetime(2026, 6, 6, tzinfo=_dt.UTC),
                updated_at=_dt.datetime(2026, 6, 6, tzinfo=_dt.UTC),
            )
        )
        for index in range(sections):
            session.add(
                Section(
                    section_id=f"sec_{doc_id}_{index}",
                    doc_id=doc_id,
                    tenant_id=tenant_id,
                    title="Warranty",
                    level=1,
                    page_start=index + 1,
                    page_end=index + 2,
                    summary="Summary.",
                    pii_flags={},
                )
            )


class TestRecordProjections:
    """Boundary projections from ORM rows to backend records (sync, no I/O)."""

    @pytest.mark.anyio
    async def test_document_record_projection_handles_null_created_at(self) -> None:
        """A row with no created_at projects an empty string, not a crash."""
        row = Document(
            doc_id="doc_x",
            tenant_id=TENANT_A,
            title=None,
            total_pages=3,
            domain=None,
            residency_region="GLOBAL",
            fallback_only=True,
            pii_flags=None,
        )
        record = _to_document_record(row)
        assert record.created_at == ""
        assert record.pii_flags == {}
        assert record.fallback_only is True

    @pytest.mark.anyio
    async def test_section_record_projection_copies_pii_flags(self) -> None:
        """The section projection copies pii_flags into a plain dict."""
        row = Section(
            section_id="sec_1",
            doc_id="doc_x",
            tenant_id=TENANT_A,
            title="T",
            level=2,
            page_start=1,
            page_end=4,
            summary=None,
            pii_flags={"title": True},
        )
        record = _to_section_record(row)
        assert record.pii_flags == {"title": True}
        assert record.level == 2


class TestGetDocument:
    """get_document tenant guard and tombstone visibility."""

    async def test_get_owned_document_returns_record(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """An owned, live document is returned as a DocumentRecord."""
        await _seed_document(session_factory, "doc_1", TENANT_A)
        store = SqlAlchemyDocumentStore(session_factory)
        record = await store.get_document(TENANT_A, "doc_1")
        assert record is not None
        assert record.doc_id == "doc_1"
        assert record.created_at != ""

    async def test_cross_tenant_document_is_invisible(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """A document owned by tenant A is invisible to tenant B (IDOR guard)."""
        await _seed_document(session_factory, "doc_1", TENANT_A)
        store = SqlAlchemyDocumentStore(session_factory)
        assert await store.get_document(TENANT_B, "doc_1") is None

    async def test_tombstoned_document_is_invisible(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """A tombstoned document is invisible to its own tenant (DPDP erasure)."""
        await _seed_document(session_factory, "doc_1", TENANT_A, tombstoned=True)
        store = SqlAlchemyDocumentStore(session_factory)
        assert await store.get_document(TENANT_A, "doc_1") is None


class TestListDocuments:
    """list_documents pagination, domain filter, and count."""

    async def test_list_returns_owned_documents_with_count(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """The list returns only the tenant's live documents with a total."""
        await _seed_document(session_factory, "doc_a", TENANT_A)
        await _seed_document(session_factory, "doc_b", TENANT_A)
        await _seed_document(session_factory, "doc_c", TENANT_B)
        store = SqlAlchemyDocumentStore(session_factory)
        rows, total = await store.list_documents(TENANT_A, 1, 50, None)
        assert total == 2
        assert {r.doc_id for r in rows} == {"doc_a", "doc_b"}

    async def test_list_filters_by_domain(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """A domain filter narrows the result set and count."""
        await _seed_document(session_factory, "doc_a", TENANT_A, domain="legal")
        await _seed_document(session_factory, "doc_b", TENANT_A, domain="finance")
        store = SqlAlchemyDocumentStore(session_factory)
        rows, total = await store.list_documents(TENANT_A, 1, 50, "finance")
        assert total == 1
        assert rows[0].doc_id == "doc_b"

    async def test_list_paginates(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Pagination offsets the result while reporting the full count."""
        for index in range(3):
            await _seed_document(session_factory, f"doc_{index}", TENANT_A)
        store = SqlAlchemyDocumentStore(session_factory)
        page1, total = await store.list_documents(TENANT_A, 1, 2, None)
        page2, _ = await store.list_documents(TENANT_A, 2, 2, None)
        assert total == 3
        assert len(page1) == 2
        assert len(page2) == 1


class TestGetSections:
    """get_sections ownership gate and ordering."""

    async def test_sections_returned_for_owned_document(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Sections of an owned document are returned in page order."""
        await _seed_document(session_factory, "doc_1", TENANT_A, sections=2)
        store = SqlAlchemyDocumentStore(session_factory)
        sections = await store.get_sections(TENANT_A, "doc_1")
        assert len(sections) == 2
        assert sections[0].page_start <= sections[1].page_start

    async def test_sections_empty_for_unowned_document(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """A cross-tenant section read returns an empty list (IDOR guard)."""
        await _seed_document(session_factory, "doc_1", TENANT_A, sections=2)
        store = SqlAlchemyDocumentStore(session_factory)
        assert await store.get_sections(TENANT_B, "doc_1") == []


class TestTombstoneDocument:
    """tombstone_document erasure cascade (OAQ-2)."""

    async def test_tombstone_marks_row_and_enqueues_outbox(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Tombstoning sets tombstoned_at and enqueues one outbox row per store."""
        await _seed_document(session_factory, "doc_1", TENANT_A)
        store = SqlAlchemyDocumentStore(session_factory)
        result = await store.tombstone_document(TENANT_A, "doc_1")
        assert result is True
        assert await store.get_document(TENANT_A, "doc_1") is None
        async with session_factory() as session:
            outbox = (await session.execute(select(ErasureOutbox))).scalars().all()
        stores = {row.store for row in outbox}
        assert stores == {"qdrant", "object_store", "postgres"}

    async def test_tombstone_unowned_document_returns_false(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """Deleting a document the tenant does not own returns False (-> 404)."""
        await _seed_document(session_factory, "doc_1", TENANT_A)
        store = SqlAlchemyDocumentStore(session_factory)
        assert await store.tombstone_document(TENANT_B, "doc_1") is False

    async def test_second_tombstone_is_idempotent_false(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """A second delete of an already-tombstoned doc returns False (idempotent)."""
        await _seed_document(session_factory, "doc_1", TENANT_A)
        store = SqlAlchemyDocumentStore(session_factory)
        assert await store.tombstone_document(TENANT_A, "doc_1") is True
        assert await store.tombstone_document(TENANT_A, "doc_1") is False


class TestDependencyUnavailable:
    """Every read/write path maps an engine failure to DependencyUnavailable (503)."""

    async def test_get_document_maps_engine_failure_to_503(self) -> None:
        """A structure-store failure surfaces as DependencyUnavailable on get."""
        store = SqlAlchemyDocumentStore(_FailingFactory())  # type: ignore[arg-type]
        with pytest.raises(DependencyUnavailable):
            await store.get_document(TENANT_A, "doc_1")

    async def test_list_documents_maps_engine_failure_to_503(self) -> None:
        """A structure-store failure surfaces as DependencyUnavailable on list."""
        store = SqlAlchemyDocumentStore(_FailingFactory())  # type: ignore[arg-type]
        with pytest.raises(DependencyUnavailable):
            await store.list_documents(TENANT_A, 1, 10, None)

    async def test_from_database_url_builds_a_store(self) -> None:
        """from_database_url constructs a store without opening a connection."""
        store = SqlAlchemyDocumentStore.from_database_url(
            "sqlite+aiosqlite:///:memory:"
        )
        assert isinstance(store, SqlAlchemyDocumentStore)

    async def test_get_sections_maps_engine_failure_to_503(
        self, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """A failure during the sections query surfaces as DependencyUnavailable.

        The owning document exists (so the ownership pre-check passes), but the
        section query is forced to fail by a factory that raises on its second
        invocation (the sections session, after the ownership session).
        """
        await _seed_document(session_factory, "doc_1", TENANT_A)

        class _BrokenFactory:
            def __init__(self, inner: async_sessionmaker[AsyncSession]) -> None:
                self._inner = inner
                self._calls = 0

            def __call__(self) -> AsyncSession:
                self._calls += 1
                if self._calls >= 2:
                    raise OperationalError("stmt", {}, Exception("down"))
                return self._inner()

        store = SqlAlchemyDocumentStore(_BrokenFactory(session_factory))  # type: ignore[arg-type]
        with pytest.raises(DependencyUnavailable):
            await store.get_sections(TENANT_A, "doc_1")

    async def test_tombstone_maps_engine_failure_to_503(self) -> None:
        """A structure-store failure surfaces as DependencyUnavailable (ADV-002)."""
        store = SqlAlchemyDocumentStore(_FailingFactory())  # type: ignore[arg-type]
        with pytest.raises(DependencyUnavailable):
            await store.tombstone_document(TENANT_A, "doc_1")
