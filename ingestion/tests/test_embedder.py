"""Embedder adapter tests for STORY-003 (ADR-6).

Asserts the fake embedder satisfies the Embedder Protocol with the collection's
1536 dimension, that the OpenAI adapter refuses to run without an env key (no
hardcoded key), and that the FallbackEmbedder switches to the secondary adapter
when the primary raises.
"""

from __future__ import annotations

import logging

import pytest

from ingestion.embedder import (
    EMBEDDING_DIM,
    Embedder,
    EmbedderDimensionError,
    FallbackEmbedder,
    OpenAIEmbedder,
)
from ingestion.tests.conftest import FakeEmbedder


class _FailingPrimary:
    """Primary embedder that always raises RuntimeError (forces the fallback)."""

    @property
    def dimension(self) -> int:
        """Return the required dimension."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Always fail to trigger the fallback path."""
        raise RuntimeError("primary unavailable")


class _NonRuntimeErrorPrimary:
    """Primary embedder that raises a non-RuntimeError (e.g. a library/connection error).

    Models exceptions like ``openai.APIConnectionError`` or ``ValueError`` that are not
    ``RuntimeError`` and previously skipped the fallback path.
    """

    def __init__(self, exc: Exception | None = None) -> None:
        """Store the exception to raise (defaults to a plain ValueError)."""
        self._exc = exc or ValueError("transient library error")

    @property
    def dimension(self) -> int:
        """Return the required dimension."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Raise the configured non-RuntimeError to exercise the broadened fallback."""
        raise self._exc


class _DimErrorPrimary:
    """Primary embedder that returns wrong-dim vectors, tripping the dimension guard."""

    @property
    def dimension(self) -> int:
        """Report EMBEDDING_DIM though embed() returns a wrong length."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return wrong-length vectors so _validate_dimension raises."""
        return [[0.0] * (EMBEDDING_DIM + 1) for _ in texts]


class _WrongDimEmbedder:
    """Embedder that returns vectors of a non-EMBEDDING_DIM length (e.g. BGE 1024)."""

    def __init__(self, dim: int = 1024) -> None:
        """Store the (wrong) output dimension to emit."""
        self._dim = dim

    @property
    def dimension(self) -> int:
        """Report EMBEDDING_DIM even though embed() returns a wrong length."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return wrong-length vectors to exercise the dimension guard."""
        return [[0.0] * self._dim for _ in texts]


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
    fallback = FallbackEmbedder(primary=_FailingPrimary(), fallback=FakeEmbedder())

    vectors = fallback.embed(["only"])

    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIM


def test_fallback_with_correct_dim_passes() -> None:
    """A fallback that returns EMBEDDING_DIM vectors passes the dimension guard."""
    fallback = FallbackEmbedder(primary=_FailingPrimary(), fallback=FakeEmbedder())

    vectors = fallback.embed(["a", "b"])

    assert all(len(vector) == EMBEDDING_DIM for vector in vectors)


def test_fallback_with_wrong_dim_raises() -> None:
    """A fallback returning a non-EMBEDDING_DIM vector raises EmbedderDimensionError.

    FIX-2: BGE-M3 is natively 1024-dim; silently upserting its vectors into the
    1536-dim Qdrant collection corrupts it. The mismatch is now a typed error.
    """
    fallback = FallbackEmbedder(
        primary=_FailingPrimary(), fallback=_WrongDimEmbedder(dim=1024)
    )

    with pytest.raises(EmbedderDimensionError, match="1024-dim"):
        fallback.embed(["only"])


def test_primary_with_wrong_dim_raises() -> None:
    """A primary returning a non-EMBEDDING_DIM vector also raises (both paths guarded)."""
    fallback = FallbackEmbedder(
        primary=_WrongDimEmbedder(dim=512), fallback=FakeEmbedder()
    )

    with pytest.raises(EmbedderDimensionError, match="512-dim"):
        fallback.embed(["only"])


def test_fallback_on_non_runtime_error_from_primary() -> None:
    """A non-RuntimeError from the primary still degrades to the secondary.

    FIX-7: FallbackEmbedder previously caught only RuntimeError, so a library or
    connection error (e.g. openai.APIConnectionError, ValueError) propagated and
    skipped the BGE-M3 fallback. Catching Exception now degrades gracefully.
    """
    fallback = FallbackEmbedder(
        primary=_NonRuntimeErrorPrimary(ValueError("library blew up")),
        fallback=FakeEmbedder(),
    )

    vectors = fallback.embed(["only"])

    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIM


def test_primary_dimension_error_not_swallowed_into_silent_fallback() -> None:
    """A primary dimension mismatch propagates rather than masking a misconfiguration.

    FIX-7: broadening the catch to Exception must NOT hide a real dimension
    misconfiguration behind a silent fallback; EmbedderDimensionError is re-raised.
    """
    fallback = FallbackEmbedder(primary=_DimErrorPrimary(), fallback=FakeEmbedder())

    with pytest.raises(EmbedderDimensionError):
        fallback.embed(["only"])


def test_fallback_activation_is_logged_at_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The fallback swap is logged at WARNING so the model change is auditable."""
    fallback = FallbackEmbedder(primary=_FailingPrimary(), fallback=FakeEmbedder())

    with caplog.at_level(logging.WARNING, logger="ingestion.embedder"):
        fallback.embed(["only"])

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("fallback" in r.getMessage().lower() for r in warnings)
