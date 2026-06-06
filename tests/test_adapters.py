"""Unit tests for the live dependency adapters (Phase C FIX-C-01..03).

Each test mocks the db session or the underlying ``router`` / ``ingestion`` /
generation module - no real network, database, or LLM is contacted. The tests
assert the adapters translate between the in-module contracts and the backend
AGREED CONTRACT shapes (:class:`RouterDecision` / :class:`IngestOutcome` /
:class:`DocumentRecord`) without changing observable behavior.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import AsyncIterator
from typing import Any

import pytest

from backend.app.adapters.document_store import SqlAlchemyDocumentStore
from backend.app.adapters.generation import ClaudeGenerationLLM, _build_context
from backend.app.adapters.ingestor import (
    PipelineIngestor,
    _ingest_status,
    _section_id,
    _total_pages,
)
from backend.app.adapters.router import RouterModuleAdapter
from backend.app.api.interfaces import (
    DependencyUnavailable,
    IngestOutcome,
    RoutedSection,
    SectionRecord,
)
from ingestion.pipeline import _DOC_ID_NAMESPACE  # noqa: F401 - parity reference

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only (no trio dependency)."""
    return "asyncio"


def _section(
    section_id: str, tenant_id: str, page_start: int = 1, page_end: int = 5
) -> SectionRecord:
    """Build a section record fixture.

    Args:
        section_id: The section id.
        tenant_id: The owning tenant.
        page_start: Inclusive first page.
        page_end: Inclusive last page.

    Returns:
        A :class:`SectionRecord`.
    """
    return SectionRecord(
        section_id=section_id,
        tenant_id=tenant_id,
        title="Warranty",
        level=1,
        page_start=page_start,
        page_end=page_end,
    )


class _StubStore:
    """Minimal document store exposing only ``get_sections`` for the router."""

    def __init__(self, sections_by_doc: dict[str, list[SectionRecord]]) -> None:
        """Seed the stub with sections keyed by doc id."""
        self._sections = sections_by_doc
        self.section_calls: list[tuple[str, str]] = []

    async def get_sections(self, tenant_id: str, doc_id: str) -> list[SectionRecord]:
        """Return the seeded sections for an owned document (records the call)."""
        self.section_calls.append((tenant_id, doc_id))
        return self._sections.get(doc_id, [])


# --- FIX-C-01: RouterModuleAdapter ------------------------------------------


class TestRouterAdapter:
    """RouterModuleAdapter loads the tenant TOC and delegates to router.route."""

    async def test_loads_toc_and_calls_router_with_section_ids(self) -> None:
        """Adapter builds the TOC from sections and passes it to router.route."""
        store = _StubStore({"doc_abc123": [_section("sec_warranty", "tenant_a", 1, 5)]})
        captured: dict[str, Any] = {}

        async def fake_route(query: str, doc_id: str, toc: list[dict], **kwargs: Any) -> dict:
            captured["doc_id"] = doc_id
            captured["toc"] = toc
            captured["tenant_id"] = kwargs.get("tenant_id")
            return {
                "relevant_sections": ["sec_warranty"],
                "page_ranges": [[1, 5]],
                "confidence": [0.91],
                "fallback": False,
                "routing_time_ms": 42,
                "rationale": "Matched the warranty section.",
            }

        adapter = RouterModuleAdapter(store, fake_route)
        decision = await adapter.route(
            tenant_id="tenant_a",
            document_ids=["doc_abc123"],
            query="warranty?",
            confidence_threshold=0.7,
            max_sections=3,
        )

        assert captured["doc_id"] == "doc_abc123"
        assert captured["tenant_id"] == "tenant_a"
        assert captured["toc"][0]["section_id"] == "sec_warranty"
        assert captured["toc"][0]["page_start"] == 1
        assert decision.fallback is False
        assert decision.relevant_sections[0].section_id == "sec_warranty"
        assert decision.relevant_sections[0].document_id == "doc_abc123"
        assert decision.relevant_sections[0].confidence == 0.91
        assert decision.routing_time_ms == 42

    async def test_drops_ids_absent_from_toc(self) -> None:
        """A returned id not present in the TOC is dropped (no fabrication)."""
        store = _StubStore({"doc_abc123": [_section("sec_real", "tenant_a")]})

        async def fake_route(query: str, doc_id: str, toc: list[dict], **kwargs: Any) -> dict:
            return {
                "relevant_sections": ["sec_ghost"],
                "page_ranges": [[1, 5]],
                "confidence": [0.95],
                "fallback": False,
                "routing_time_ms": 10,
                "rationale": "",
            }

        adapter = RouterModuleAdapter(store, fake_route)
        decision = await adapter.route(
            tenant_id="tenant_a",
            document_ids=["doc_abc123"],
            query="q",
            confidence_threshold=0.7,
            max_sections=3,
        )

        assert decision.relevant_sections == []
        assert decision.fallback is True

    async def test_multi_document_fan_out_and_merge(self) -> None:
        """Multiple documents fan out per-doc and merge by descending confidence."""
        store = _StubStore(
            {
                "doc_aaaaaa": [_section("sec_a", "tenant_a", 1, 3)],
                "doc_bbbbbb": [_section("sec_b", "tenant_a", 4, 6)],
            }
        )
        confidences = {"doc_aaaaaa": 0.6, "doc_bbbbbb": 0.9}

        async def fake_route(query: str, doc_id: str, toc: list[dict], **kwargs: Any) -> dict:
            section_id = toc[0]["section_id"]
            return {
                "relevant_sections": [section_id],
                "page_ranges": [[toc[0]["page_start"], toc[0]["page_end"]]],
                "confidence": [confidences[doc_id]],
                "fallback": False,
                "routing_time_ms": 5,
                "rationale": f"doc {doc_id}",
            }

        adapter = RouterModuleAdapter(store, fake_route)
        decision = await adapter.route(
            tenant_id="tenant_a",
            document_ids=["doc_aaaaaa", "doc_bbbbbb"],
            query="q",
            confidence_threshold=0.5,
            max_sections=3,
        )

        assert [s.section_id for s in decision.relevant_sections] == ["sec_b", "sec_a"]
        assert decision.relevant_sections[0].document_id == "doc_bbbbbb"
        assert decision.routing_time_ms == 10
        assert store.section_calls == [
            ("tenant_a", "doc_aaaaaa"),
            ("tenant_a", "doc_bbbbbb"),
        ]

    async def test_max_sections_caps_merged_result(self) -> None:
        """The merged multi-document result is capped at max_sections."""
        store = _StubStore(
            {
                "doc_aaaaaa": [_section("sec_a", "tenant_a")],
                "doc_bbbbbb": [_section("sec_b", "tenant_a")],
            }
        )

        async def fake_route(query: str, doc_id: str, toc: list[dict], **kwargs: Any) -> dict:
            section_id = toc[0]["section_id"]
            return {
                "relevant_sections": [section_id],
                "page_ranges": [[1, 5]],
                "confidence": [0.8],
                "fallback": False,
                "routing_time_ms": 1,
                "rationale": "",
            }

        adapter = RouterModuleAdapter(store, fake_route)
        decision = await adapter.route(
            tenant_id="tenant_a",
            document_ids=["doc_aaaaaa", "doc_bbbbbb"],
            query="q",
            confidence_threshold=0.5,
            max_sections=1,
        )

        assert len(decision.relevant_sections) == 1


# --- FIX-C-02: PipelineIngestor ---------------------------------------------


class _StubSectionStore:
    """Records the hash lookup so dedup detection can be asserted."""

    def __init__(self, existing_doc_id: str | None = None) -> None:
        """Seed the stub with an optional pre-existing doc id for the hash."""
        self._existing = existing_doc_id
        self.hash_lookups = 0

    def find_doc_id_by_hash(self, tenant_id: str, content_hash_value: str) -> str | None:
        """Return the seeded existing doc id (records the lookup)."""
        self.hash_lookups += 1
        return self._existing


class TestPipelineIngestor:
    """PipelineIngestor maps the pipeline dict onto IngestOutcome."""

    async def test_maps_pipeline_result_to_outcome(self) -> None:
        """Pipeline dict is mapped to IngestOutcome with derived fields."""
        captured: dict[str, Any] = {}

        def fake_ingest(doc: Any, **kwargs: Any) -> dict:
            captured["tenant_id"] = doc.tenant_id
            captured["no_retention"] = doc.no_retention
            return {
                "doc_id": "doc_new123",
                "toc": [
                    {"level": 1, "title": "Intro", "page_start": 1, "page_end": 4},
                    {"level": 1, "title": "Body", "page_start": 5, "page_end": 12},
                ],
                "section_rows_written": 2,
                "chunks_upserted": 8,
                "fallback_only": False,
            }

        ingestor = PipelineIngestor(
            parser=object(),
            embedder=object(),
            section_store=_StubSectionStore(existing_doc_id=None),
            vector_store=object(),
            ingest=fake_ingest,
        )

        outcome = await ingestor.ingest_document(
            tenant_id="tenant_a",
            content=b"%PDF-1.4 fake",
            filename="x.pdf",
            title="My Title",
            domain="legal",
            no_retention=False,
            residency_region="IN",
            ocr=False,
        )

        assert isinstance(outcome, IngestOutcome)
        assert outcome.doc_id == "doc_new123"
        assert outcome.title == "My Title"
        assert outcome.total_pages == 12
        assert outcome.ingest_status == "indexed"
        assert outcome.deduplicated is False
        assert [s.title for s in outcome.toc] == ["Intro", "Body"]
        assert outcome.toc[0].section_id == _section_id("doc_new123", 0)
        assert captured["tenant_id"] == "tenant_a"

    async def test_dedup_detected_from_prior_hash(self) -> None:
        """deduplicated is True when the content hash already existed."""

        def fake_ingest(doc: Any, **kwargs: Any) -> dict:
            return {
                "doc_id": "doc_dup1234",
                "toc": [{"level": 1, "title": "T", "page_start": 1, "page_end": 2}],
                "section_rows_written": 1,
                "chunks_upserted": 1,
                "fallback_only": False,
            }

        ingestor = PipelineIngestor(
            parser=object(),
            embedder=object(),
            section_store=_StubSectionStore(existing_doc_id="doc_dup1234"),
            vector_store=object(),
            ingest=fake_ingest,
        )

        outcome = await ingestor.ingest_document(
            tenant_id="tenant_a",
            content=b"same bytes",
            filename="x.pdf",
            title=None,
            domain=None,
            no_retention=False,
            residency_region="GLOBAL",
            ocr=False,
        )

        assert outcome.deduplicated is True

    async def test_no_retention_maps_to_ephemeral(self) -> None:
        """no_retention uploads report the ephemeral ingest status."""

        def fake_ingest(doc: Any, **kwargs: Any) -> dict:
            return {
                "doc_id": "doc_eph1234",
                "toc": [],
                "section_rows_written": 0,
                "chunks_upserted": 0,
                "fallback_only": False,
            }

        ingestor = PipelineIngestor(
            parser=object(),
            embedder=object(),
            section_store=_StubSectionStore(),
            vector_store=object(),
            ingest=fake_ingest,
        )

        outcome = await ingestor.ingest_document(
            tenant_id="tenant_a",
            content=b"bytes",
            filename="x.pdf",
            title=None,
            domain=None,
            no_retention=True,
            residency_region="EU",
            ocr=False,
        )

        assert outcome.ingest_status == "ephemeral"
        assert outcome.total_pages == 0

    def test_ingest_status_mapping(self) -> None:
        """Status derivation covers ephemeral, fallback_only, and indexed."""
        assert _ingest_status(no_retention=True, fallback_only=False) == "ephemeral"
        assert _ingest_status(no_retention=False, fallback_only=True) == "fallback_only"
        assert _ingest_status(no_retention=False, fallback_only=False) == "indexed"

    def test_total_pages_from_toc(self) -> None:
        """total_pages is the max page_end across the TOC (0 when empty)."""
        assert _total_pages([{"page_end": 3}, {"page_end": 9}]) == 9
        assert _total_pages([]) == 0


# --- FIX-C-03: SqlAlchemyDocumentStore + ClaudeGenerationLLM -----------------


class _FakeResult:
    """Mimics the SQLAlchemy Result returned by ``session.execute``."""

    def __init__(self, *, scalar: Any = None, scalars: list[Any] | None = None) -> None:
        """Seed scalar / scalars return values."""
        self._scalar = scalar
        self._scalars = scalars or []

    def scalar_one_or_none(self) -> Any:
        """Return the seeded single scalar."""
        return self._scalar

    def scalar_one(self) -> Any:
        """Return the seeded single scalar (count path)."""
        return self._scalar

    def scalars(self) -> _FakeResult:
        """Return self so ``.all()`` can yield the seeded list."""
        return self

    def all(self) -> list[Any]:
        """Return the seeded list of rows."""
        return self._scalars


class _FakeAsyncSession:
    """Minimal async session stand-in for the document store unit tests."""

    def __init__(self, result: _FakeResult) -> None:
        """Seed the single result every execute returns."""
        self._result = result

    async def __aenter__(self) -> _FakeAsyncSession:
        """Enter the async context."""
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Exit the async context (no-op)."""

    async def execute(self, _stmt: Any) -> _FakeResult:
        """Return the seeded result for any statement."""
        return self._result


class _FakeDocumentRow:
    """Stands in for a ``db.models.Document`` row."""

    def __init__(self) -> None:
        """Populate a representative live document row."""
        self.doc_id = "doc_abc123"
        self.tenant_id = "tenant_a"
        self.title = "T"
        self.total_pages = 10
        self.domain = "legal"
        self.residency_region = "IN"
        self.fallback_only = False
        self.created_at = _dt.datetime(2026, 6, 6, tzinfo=_dt.UTC)
        self.pii_flags = {}


class TestDocumentStoreAdapter:
    """SqlAlchemyDocumentStore projects rows and guards on DB failure."""

    async def test_get_document_projects_row(self) -> None:
        """A live row is projected onto a DocumentRecord."""
        result = _FakeResult(scalar=_FakeDocumentRow())
        store = SqlAlchemyDocumentStore(lambda: _FakeAsyncSession(result))

        record = await store.get_document("tenant_a", "doc_abc123")

        assert record is not None
        assert record.doc_id == "doc_abc123"
        assert record.tenant_id == "tenant_a"
        assert record.residency_region == "IN"

    async def test_get_document_returns_none_when_absent(self) -> None:
        """An absent/tombstoned document resolves to None."""
        result = _FakeResult(scalar=None)
        store = SqlAlchemyDocumentStore(lambda: _FakeAsyncSession(result))

        record = await store.get_document("tenant_a", "doc_missing")

        assert record is None

    async def test_db_error_maps_to_dependency_unavailable(self) -> None:
        """A SQLAlchemy error surfaces as DependencyUnavailable (-> 503)."""
        from sqlalchemy.exc import OperationalError

        class _BrokenSession(_FakeAsyncSession):
            async def execute(self, _stmt: Any) -> _FakeResult:
                raise OperationalError("stmt", {}, Exception("down"))

        store = SqlAlchemyDocumentStore(
            lambda: _BrokenSession(_FakeResult(scalar=None))
        )

        with pytest.raises(DependencyUnavailable):
            await store.get_document("tenant_a", "doc_abc123")


class _FakeStreamManager:
    """Async context manager mimicking ``client.messages.stream(...)``."""

    def __init__(self, tokens: list[str]) -> None:
        """Seed the fixed tokens the stream yields."""
        self._tokens = tokens

    async def __aenter__(self) -> _FakeStreamManager:
        """Enter the streaming context."""
        return self

    async def __aexit__(self, *exc: object) -> None:
        """Exit the streaming context (no-op)."""

    @property
    def text_stream(self) -> AsyncIterator[str]:
        """Yield the seeded answer fragments."""

        async def _gen() -> AsyncIterator[str]:
            for token in self._tokens:
                yield token

        return _gen()


class _FakeMessages:
    """Stub exposing ``stream`` like the Anthropic client."""

    def __init__(self, tokens: list[str]) -> None:
        """Seed the tokens the stream yields."""
        self._tokens = tokens
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> _FakeStreamManager:
        """Record the call and return a fake stream manager."""
        self.calls.append(kwargs)
        return _FakeStreamManager(self._tokens)


class _FakeAnthropicClient:
    """Stub Anthropic async client with a ``messages.stream`` surface."""

    def __init__(self, tokens: list[str]) -> None:
        """Seed the tokens the messages stream yields."""
        self.messages = _FakeMessages(tokens)


class TestGenerationAdapter:
    """ClaudeGenerationLLM streams over an injected client (no network)."""

    async def test_stream_answer_yields_tokens(self) -> None:
        """The adapter yields the client's streamed text fragments in order."""
        client = _FakeAnthropicClient(["Hello", " world"])
        adapter = ClaudeGenerationLLM(client=client)
        sections = [RoutedSection("sec_a", "Warranty", 1, 5, 0.9, "doc_abc123")]

        tokens = [token async for token in adapter.stream_answer("q?", sections)]

        assert tokens == ["Hello", " world"]
        assert client.messages.calls[0]["model"] == adapter._model
        assert client.messages.calls[0]["thinking"] == {"type": "adaptive"}

    async def test_missing_package_maps_to_dependency_unavailable(self) -> None:
        """A missing anthropic package surfaces as DependencyUnavailable."""
        import builtins

        adapter = ClaudeGenerationLLM(client=None)
        real_import = builtins.__import__

        def _blocked_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "anthropic":
                raise ImportError("no anthropic")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = _blocked_import
        try:
            with pytest.raises(DependencyUnavailable):
                async for _ in adapter.stream_answer("q", []):
                    pass
        finally:
            builtins.__import__ = real_import

    def test_build_context_handles_empty_sections(self) -> None:
        """Context rendering returns a sentinel when no section routed."""
        assert "No section" in _build_context([])
        rendered = _build_context(
            [RoutedSection("sec_a", "Warranty", 1, 5, 0.9, "doc_abc123")]
        )
        assert "Warranty" in rendered
        assert "1-5" in rendered
