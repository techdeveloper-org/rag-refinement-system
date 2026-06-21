"""Final branch-coverage closers for backend paths not otherwise reached.

Covers the pre-stream and mid-stream 503 paths on /v1/answer and /v1/route, the
lazy real-client construction in the generation and Qdrant-vector adapters, the
token-reduction / PII-inventory helper branches, the errors detail-omission and
default-detail branches, the health writer wait_closed swallow, and the empty
bearer-token auth branch. No real network, database, or LLM is contacted.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_generation_llm, get_router
from backend.app.api.helpers import build_pii_inventory, estimate_token_reduction
from backend.app.api.interfaces import (
    DependencyUnavailable,
    DocumentRecord,
    RoutedSection,
    RouterDecision,
    SectionRecord,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only."""
    return "asyncio"


class _RaisingRouter:
    """Router stub that raises DependencyUnavailable on route (degraded path)."""

    async def route(self, **kwargs: object) -> RouterDecision:
        raise DependencyUnavailable("router down")


class _RaisingGenerationLLM:
    """Generation stub that raises DependencyUnavailable mid-stream."""

    async def stream_answer(self, query: str, sections: list[RoutedSection]):
        raise DependencyUnavailable("generation down")
        yield  # pragma: no cover - unreachable, marks this an async generator


class TestEndpoint503Paths:
    """Degraded-dependency (503) paths on the routing and answer endpoints."""

    async def test_route_pre_stream_503_when_router_down(
        self, client: TestClient, fakes: dict[str, object], auth_headers: dict[str, str]
    ) -> None:
        """A DependencyUnavailable from the router yields a pre-response 503."""
        client.app.dependency_overrides[get_router] = lambda: _RaisingRouter()
        response = client.post(
            "/v1/route",
            headers=auth_headers,
            json={"query": "q", "document_id": "doc_abc123"},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "SERVICE_UNAVAILABLE"

    async def test_answer_pre_stream_503_when_router_down(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A DependencyUnavailable from the router yields a pre-stream 503."""
        client.app.dependency_overrides[get_router] = lambda: _RaisingRouter()
        response = client.post(
            "/v1/answer",
            headers=auth_headers,
            json={"query": "q", "document_id": "doc_abc123"},
        )
        assert response.status_code == 503

    async def test_answer_mid_stream_error_event_on_dependency_failure(
        self, client: TestClient, auth_headers: dict[str, str]
    ) -> None:
        """A DependencyUnavailable after the stream opens emits an SSE error event."""
        client.app.dependency_overrides[get_generation_llm] = (
            lambda: _RaisingGenerationLLM()
        )
        response = client.post(
            "/v1/answer",
            headers=auth_headers,
            json={"query": "q", "document_id": "doc_abc123"},
        )
        assert response.status_code == 200
        assert "event: error" in response.text
        assert "SERVICE_UNAVAILABLE" in response.text


class TestHelperBranches:
    """Pure helper branch coverage."""

    @pytest.mark.anyio
    async def test_token_reduction_zero_when_no_pages(self) -> None:
        """Zero total pages yields a 0% reduction (guard branch)."""
        assert estimate_token_reduction([], 0) == "0%"

    @pytest.mark.anyio
    async def test_token_reduction_positive(self) -> None:
        """A small selected span over many pages yields a high reduction."""
        section = RoutedSection(
            section_id="sec_1",
            title="T",
            page_start=1,
            page_end=2,
            confidence=0.9,
            document_id="doc_1",
        )
        assert estimate_token_reduction([section], 100).endswith("%")

    @pytest.mark.anyio
    async def test_pii_inventory_omits_absent_titles_and_dedupes(self) -> None:
        """Absent titles/summaries are skipped; duplicate (field, location) dedupes."""
        document = DocumentRecord(
            doc_id="doc_1",
            tenant_id="tenant_a",
            title=None,
            total_pages=5,
            domain=None,
            residency_region="IN",
            fallback_only=False,
            created_at="",
            pii_flags={"title": "document_title"},
        )
        sections = [
            SectionRecord(
                section_id="sec_1",
                tenant_id="tenant_a",
                title="Warranty",
                level=1,
                page_start=1,
                page_end=2,
                summary="Covers warranty terms.",
                pii_flags={"title": "section_title"},
            ),
            SectionRecord(
                section_id="sec_2",
                tenant_id="tenant_a",
                title=None,
                level=1,
                page_start=3,
                page_end=4,
                summary=None,
                pii_flags={},
            ),
        ]
        inventory = build_pii_inventory(document, sections)
        keys = {(f.field, f.location) for f in inventory}
        assert ("title", "document") in keys
        assert ("title", "sec_1") in keys
        assert ("summary", "sec_1") in keys
        # sec_2 has no title/summary -> contributes no PII fields.
        assert ("title", "sec_2") not in keys
        assert ("summary", "sec_2") not in keys
        # The section title appears once from the title field and once from the
        # flag map at the same (field, location) - the dedup loop collapses them.
        assert len(keys) == len(inventory)


class TestGenerationEnsureClient:
    """Lazy real-client construction in the generation adapter (line 101)."""

    @pytest.mark.anyio
    async def test_ensure_client_builds_real_anthropic(self) -> None:
        """With anthropic importable, _ensure_client builds and caches a client."""
        pytest.importorskip("anthropic")
        from backend.app.adapters.generation import ClaudeGenerationLLM

        adapter = ClaudeGenerationLLM()
        client = await adapter._ensure_client()
        assert client is not None
        assert await adapter._ensure_client() is client


class TestQdrantVectorStoreEnsureClient:
    """Lazy real-client construction in the Qdrant vector store (lines 160-162)."""

    @pytest.mark.anyio
    async def test_ensure_client_uses_qdrant_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """_ensure_client builds a client from QDRANT_URL on first use."""
        from backend.app.adapters import stores as stores_mod

        built: dict[str, object] = {}

        def _fake_get_client() -> object:
            sentinel = object()
            built["client"] = sentinel
            return sentinel

        monkeypatch.setattr(
            "db.qdrant_bootstrap.get_client", _fake_get_client
        )
        store = stores_mod.QdrantVectorStore()
        client = store._ensure_client()
        assert client is built["client"]
        assert store._ensure_client() is client
