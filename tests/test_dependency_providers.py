"""Tests for the API dependency providers (composition root).

``backend.app.api.dependencies`` builds the live ``DocumentStore`` / ``Router`` /
``Ingestor`` / ``GenerationLLM`` adapters as process-wide singletons. These tests
verify the 503-on-unconfigured-store guard, the lazy singleton caching, and that
each provider returns an object implementing the right surface, without contacting
a real database, Qdrant, or LLM.
"""

from __future__ import annotations

import pytest

from backend.app import settings as settings_module
from backend.app.api import dependencies as deps
from backend.app.errors import ProblemException


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear all cached provider singletons and settings around each test."""
    settings_module.get_settings.cache_clear()
    monkeypatch.setattr(deps, "_document_store_cache", None)
    monkeypatch.setattr(deps, "_router_cache", None)
    monkeypatch.setattr(deps, "_ingestor_cache", None)
    monkeypatch.setattr(deps, "_generation_llm_cache", None)
    yield
    settings_module.get_settings.cache_clear()
    monkeypatch.setattr(deps, "_document_store_cache", None)
    monkeypatch.setattr(deps, "_router_cache", None)
    monkeypatch.setattr(deps, "_ingestor_cache", None)
    monkeypatch.setattr(deps, "_generation_llm_cache", None)


def test_document_store_unconfigured_raises_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no DATABASE_URL the document-store provider raises a 503 problem."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ProblemException) as excinfo:
        deps.get_document_store()
    assert excinfo.value.status_code == 503
    assert excinfo.value.code == "SERVICE_UNAVAILABLE"


def test_document_store_configured_builds_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured DATABASE_URL yields a cached document-store singleton."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    first = deps.get_document_store()
    second = deps.get_document_store()
    assert first is second


def test_router_provider_builds_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The router provider builds a cached adapter over the live router package."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    first = deps.get_router()
    second = deps.get_router()
    assert first is second
    assert hasattr(first, "route")


def test_ingestor_provider_builds_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ingestor provider builds a cached pipeline-backed adapter."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("DATABASE_SYNC_URL", "sqlite:///:memory:")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    first = deps.get_ingestor()
    second = deps.get_ingestor()
    assert first is second
    assert hasattr(first, "ingest_document")


def test_generation_llm_provider_builds_singleton() -> None:
    """The generation provider builds a cached lazy Claude adapter."""
    first = deps.get_generation_llm()
    second = deps.get_generation_llm()
    assert first is second
    assert hasattr(first, "stream_answer")
