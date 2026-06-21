"""Shared fakes and fixtures for the /v1 API and auth test suites.

Provides in-memory fakes for the four service-boundary collaborators
(:class:`DocumentStore`, :class:`Router`, :class:`Ingestor`,
:class:`GenerationLLM`) and a configured TestClient that authenticates as a
known tenant. No network, no database, no real LLM (team AGREED CONTRACT:
mock at the boundary).
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import AsyncIterator

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import (
    get_document_store,
    get_generation_llm,
    get_ingestor,
    get_router,
)
from backend.app.api.interfaces import (
    DependencyUnavailable,
    DocumentRecord,
    IngestOutcome,
    RoutedSection,
    RouterDecision,
    SectionRecord,
)
from backend.app.main import create_app
from backend.app.security import auth as auth_module
from backend.app.security.rate_limit import get_rate_limiter
from backend.app.settings import get_settings

TENANT_A = "tenant_a"
TENANT_B = "tenant_b"
JWT_SECRET = "test-jwt-secret-not-a-real-key-padded-32b"  # noqa: S105 - test-only literal
API_KEY_SALT = "test-api-key-salt"  # noqa: S105 - test-only literal
JWT_AUDIENCE = "rag-refinement-personal"
JWT_ISSUER = "test-issuer"


def _doc(doc_id: str, tenant_id: str, *, total_pages: int = 10, title: str = "T") -> DocumentRecord:
    """Build a fake document record for tests.

    Args:
        doc_id: The document id.
        tenant_id: The owning tenant.
        total_pages: Page count.
        title: Document title.

    Returns:
        A :class:`DocumentRecord`.
    """
    return DocumentRecord(
        doc_id=doc_id,
        tenant_id=tenant_id,
        title=title,
        total_pages=total_pages,
        domain="legal",
        residency_region="IN",
        fallback_only=False,
        created_at=_dt.datetime(2026, 6, 6, tzinfo=_dt.UTC).isoformat(),
        pii_flags={},
    )


def _section(section_id: str, tenant_id: str) -> SectionRecord:
    """Build a fake section record for tests.

    Args:
        section_id: The section id.
        tenant_id: The owning tenant.

    Returns:
        A :class:`SectionRecord` with a PII-bearing title and summary.
    """
    return SectionRecord(
        section_id=section_id,
        tenant_id=tenant_id,
        title="Warranty",
        level=1,
        page_start=1,
        page_end=5,
        summary="Covers the warranty terms.",
        pii_flags={},
    )


class FakeDocumentStore:
    """In-memory tenant-scoped document store fake."""

    def __init__(self) -> None:
        """Seed the store with one document per tenant and a tombstone set."""
        self._docs: dict[str, DocumentRecord] = {
            "doc_abc123": _doc("doc_abc123", TENANT_A),
            "doc_other9": _doc("doc_other9", TENANT_B),
        }
        self._sections: dict[str, list[SectionRecord]] = {
            "doc_abc123": [_section("sec_warranty", TENANT_A)],
            "doc_other9": [_section("sec_other", TENANT_B)],
        }
        self.fail_tombstone = False

    async def get_document(self, tenant_id: str, doc_id: str) -> DocumentRecord | None:
        """Return the document only when the tenant owns it (IDOR guard)."""
        record = self._docs.get(doc_id)
        if record is None or record.tenant_id != tenant_id:
            return None
        return record

    async def list_documents(
        self, tenant_id: str, page: int, page_size: int, domain: str | None
    ) -> tuple[list[DocumentRecord], int]:
        """Return the tenant's documents filtered by optional domain."""
        owned = [d for d in self._docs.values() if d.tenant_id == tenant_id]
        if domain is not None:
            owned = [d for d in owned if d.domain == domain]
        start = (page - 1) * page_size
        return owned[start : start + page_size], len(owned)

    async def get_sections(self, tenant_id: str, doc_id: str) -> list[SectionRecord]:
        """Return the tenant's sections for an owned document."""
        record = self._docs.get(doc_id)
        if record is None or record.tenant_id != tenant_id:
            return []
        return self._sections.get(doc_id, [])

    async def tombstone_document(self, tenant_id: str, doc_id: str) -> bool:
        """Tombstone an owned document; raise when the store is 'down'."""
        if self.fail_tombstone:
            raise DependencyUnavailable("postgres down")
        record = self._docs.get(doc_id)
        if record is None or record.tenant_id != tenant_id:
            return False
        del self._docs[doc_id]
        return True


class FakeRouter:
    """In-memory router fake that never invokes generation."""

    def __init__(self) -> None:
        """Initialize call tracking and default decision shape."""
        self.calls = 0
        self.fallback = False

    async def route(
        self,
        tenant_id: str,
        document_ids: list[str],
        query: str,
        confidence_threshold: float,
        max_sections: int,
    ) -> RouterDecision:
        """Return a deterministic routing decision."""
        self.calls += 1
        sections = [
            RoutedSection(
                section_id="sec_warranty",
                title="Warranty",
                page_start=1,
                page_end=5,
                confidence=0.91,
                document_id=document_ids[0] if document_ids else None,
            )
        ]
        return RouterDecision(
            relevant_sections=[] if self.fallback else sections,
            fallback=self.fallback,
            routing_time_ms=42,
            rationale="Matched the warranty section.",
        )


class FakeIngestor:
    """In-memory ingestion fake."""

    def __init__(self) -> None:
        """Default to a fresh (non-deduplicated) ingest outcome."""
        self.deduplicated = False

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
        """Return a deterministic ingest outcome."""
        return IngestOutcome(
            doc_id="doc_new123",
            title=title or "Ingested",
            total_pages=12,
            toc=[_section("sec_intro", tenant_id)],
            ingest_status="ephemeral" if no_retention else "indexed",
            deduplicated=self.deduplicated,
        )


class FakeGenerationLLM:
    """Streaming generation fake that yields fixed tokens."""

    def __init__(self) -> None:
        """Default to a healthy two-token stream."""
        self.tokens = ["Hello", " world"]
        self.fail_midstream = False
        self.stream_answer_calls = 0

    async def stream_answer(
        self, query: str, sections: list[RoutedSection]
    ) -> AsyncIterator[str]:
        """Yield answer fragments, optionally failing mid-stream."""
        self.stream_answer_calls += 1
        for index, token in enumerate(self.tokens):
            if self.fail_midstream and index == 1:
                raise RuntimeError("generation crashed")
            yield token


def make_jwt(tenant_id: str, subject: str = "user-1", *, expired: bool = False) -> str:
    """Mint a signed JWT for tests.

    Args:
        tenant_id: The tenant claim to embed.
        subject: The subject claim.
        expired: When True, sets an expiry in the past.

    Returns:
        A signed JWT string.
    """
    now = _dt.datetime.now(_dt.UTC)
    exp = now - _dt.timedelta(hours=1) if expired else now + _dt.timedelta(hours=1)
    claims = {
        "sub": subject,
        "tenant_id": tenant_id,
        "aud": JWT_AUDIENCE,
        "iss": JWT_ISSUER,
        "exp": exp,
        "iat": now,
    }
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def _configure_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure auth secrets and reset cached singletons for each test."""
    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("JWT_AUDIENCE", JWT_AUDIENCE)
    monkeypatch.setenv("JWT_ISSUER", JWT_ISSUER)
    monkeypatch.setenv("API_KEY_SALT", API_KEY_SALT)
    auth_module._api_key_store = None
    get_rate_limiter().reset()
    yield
    get_settings.cache_clear()
    auth_module._api_key_store = None
    import backend.app.security.rate_limit as _rl_module
    _rl_module._rate_limiter = None


@pytest.fixture
def fakes() -> dict[str, object]:
    """Provide a fresh set of boundary fakes.

    Returns:
        A dict with ``store``, ``router``, ``ingestor``, and ``llm`` fakes.
    """
    return {
        "store": FakeDocumentStore(),
        "router": FakeRouter(),
        "ingestor": FakeIngestor(),
        "llm": FakeGenerationLLM(),
    }


@pytest.fixture
def client(fakes: dict[str, object]):
    """Provide a TestClient with all boundary collaborators overridden.

    Args:
        fakes: The boundary fakes to inject.

    Yields:
        A configured :class:`TestClient`.
    """
    app = create_app()
    app.dependency_overrides[get_document_store] = lambda: fakes["store"]
    app.dependency_overrides[get_router] = lambda: fakes["router"]
    app.dependency_overrides[get_ingestor] = lambda: fakes["ingestor"]
    app.dependency_overrides[get_generation_llm] = lambda: fakes["llm"]
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Provide bearer auth headers for tenant A.

    Returns:
        A headers dict carrying a valid JWT for tenant A.
    """
    return {"Authorization": f"Bearer {make_jwt(TENANT_A)}"}
