"""Embedder adapter tests for STORY-003 (ADR-6).

Asserts the fake embedder satisfies the Embedder Protocol with the collection's
1536 dimension, that the OpenAI adapter refuses to run without an env key (no
hardcoded key), and that the FallbackEmbedder switches to the secondary adapter
when the primary raises.
"""

from __future__ import annotations

import pytest

from ingestion.embedder import (
    EMBEDDING_DIM,
    Embedder,
    FallbackEmbedder,
    OpenAIEmbedder,
)
from ingestion.tests.conftest import FakeEmbedder


def test_fake_embedder_satisfies_protocol_and_dimension() -> None:
    """The fake embedder is a structural Embedder with EMBEDDING_DIM vectors."""
    embedder = FakeEmbedder()

    assert isinstance(embedder, Embedder)
    assert embedder.dimension == EMBEDDING_DIM
    vectors = embedder.embed(["alpha", "beta"])
    assert len(vectors) == 2
    assert all(len(vector) == EMBEDDING_DIM for vector in vectors)


def test_openai_embedder_requires_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """OpenAIEmbedder raises when OPENAI_API_KEY is absent (env-only policy)."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        OpenAIEmbedder().embed(["text"])


def test_fallback_embedder_uses_secondary_when_primary_fails() -> None:
    """FallbackEmbedder returns the secondary's vectors when the primary raises."""

    class FailingPrimary:
        """Primary embedder that always raises RuntimeError."""

        @property
        def dimension(self) -> int:
            """Return the required dimension."""
            return EMBEDDING_DIM

        def embed(self, texts: list[str]) -> list[list[float]]:
            """Always fail to trigger the fallback path."""
            raise RuntimeError("primary unavailable")

    fallback = FallbackEmbedder(primary=FailingPrimary(), fallback=FakeEmbedder())

    vectors = fallback.embed(["only"])

    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIM
