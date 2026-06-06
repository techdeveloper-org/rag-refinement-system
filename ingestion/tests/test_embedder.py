"""Embedder adapter tests for STORY-003 (ADR-6).

Asserts the fake embedder satisfies the Embedder Protocol with the collection's
1536 dimension, that the OpenAI adapter refuses to run without an env key (no
hardcoded key), and that the FallbackEmbedder switches to the secondary adapter
only on a CURATED primary-unavailability error (ING-A4) while programming bugs and
dimension mismatches propagate. Dimension validation is the pipeline boundary's
sole responsibility (ING-A6), so the dimension-guard tests exercise the boundary
guard ``_validate_embed_dimension`` rather than the FallbackEmbedder.
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
from ingestion.pipeline import _validate_embed_dimension
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


class _RaisingPrimary:
    """Primary embedder that raises a configured exception (parametrizes the catch test).

    Models both a curated primary-unavailability error (e.g. ``ConnectionError``) that
    should trigger the fallback and a programming bug (e.g. ``TypeError``) that should
    propagate unmasked (ING-A4).
    """

    def __init__(self, exc: Exception) -> None:
        """Store the exception this primary raises on every embed call."""
        self._exc = exc

    @property
    def dimension(self) -> int:
        """Return the required dimension."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Raise the configured exception to exercise the curated-catch boundary."""
        raise self._exc


class _DimErrorPrimary:
    """Primary embedder that returns wrong-dim vectors, tripping the boundary guard."""

    @property
    def dimension(self) -> int:
        """Report EMBEDDING_DIM though embed() returns a wrong length."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return wrong-length vectors so the boundary guard rejects them."""
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


def test_boundary_guard_raises_on_wrong_dim_fallback_vectors() -> None:
    """Wrong-dim fallback vectors are rejected by the pipeline boundary guard (ING-A6).

    FIX-2 / ING-A6: BGE-M3 is natively 1024-dim; silently upserting its vectors into
    the 1536-dim Qdrant collection corrupts it. The FallbackEmbedder no longer
    validates internally; the single authoritative guard is the pipeline boundary,
    which rejects the 1024-dim vectors with a typed error.
    """
    fallback = FallbackEmbedder(
        primary=_FailingPrimary(), fallback=_WrongDimEmbedder(dim=1024)
    )

    with pytest.raises(EmbedderDimensionError, match="1024-dim"):
        _validate_embed_dimension(fallback.embed(["only"]))


def test_boundary_guard_raises_on_wrong_dim_primary_vectors() -> None:
    """Wrong-dim primary vectors are also rejected by the boundary guard (ING-A6)."""
    fallback = FallbackEmbedder(
        primary=_WrongDimEmbedder(dim=512), fallback=FakeEmbedder()
    )

    with pytest.raises(EmbedderDimensionError, match="512-dim"):
        _validate_embed_dimension(fallback.embed(["only"]))


def test_transient_connection_error_from_primary_falls_back() -> None:
    """A transient ConnectionError from the primary degrades to the BGE-M3 fallback.

    ING-A4: ConnectionError is a curated primary-UNAVAILABILITY signal, so the
    FallbackEmbedder swaps to the secondary embedder rather than propagating.
    """
    fallback = FallbackEmbedder(
        primary=_RaisingPrimary(ConnectionError("provider unreachable")),
        fallback=FakeEmbedder(),
    )

    vectors = fallback.embed(["only"])

    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIM


def test_type_error_from_primary_propagates_not_silently_fell_back() -> None:
    """A TypeError (programming bug) from the primary propagates, never masked (ING-A4).

    ING-A4: broadening the catch to ``Exception`` masked genuine defects as a silent
    permanent BGE-M3 fallback. The curated catch excludes ``TypeError`` so a bug
    surfaces loudly instead of degrading the whole pipeline to the fallback model.
    """
    fallback = FallbackEmbedder(
        primary=_RaisingPrimary(TypeError("embed() got an unexpected keyword")),
        fallback=FakeEmbedder(),
    )

    with pytest.raises(TypeError):
        fallback.embed(["only"])


def test_primary_dimension_error_propagates_without_silent_fallback() -> None:
    """A primary dimension mismatch is not swallowed into a silent fallback (ING-A4/A6).

    The FallbackEmbedder no longer validates dimensions (ING-A6), so wrong-dim primary
    vectors pass straight through WITHOUT triggering a fallback - the dimension issue
    is not treated as a transient unavailability. The authoritative boundary guard
    then rejects them with a typed error (ING-A4: never masked).
    """
    fake_fallback = FakeEmbedder()
    fallback = FallbackEmbedder(primary=_DimErrorPrimary(), fallback=fake_fallback)

    vectors = fallback.embed(["only"])

    assert fake_fallback.embed_calls == 0, "a dimension issue must not trigger fallback"
    assert all(len(vector) != EMBEDDING_DIM for vector in vectors)
    with pytest.raises(EmbedderDimensionError):
        _validate_embed_dimension(vectors)


def test_fallback_activation_is_logged_at_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The fallback swap is logged at WARNING so the model change is auditable."""
    fallback = FallbackEmbedder(primary=_FailingPrimary(), fallback=FakeEmbedder())

    with caplog.at_level(logging.WARNING, logger="ingestion.embedder"):
        fallback.embed(["only"])

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("fallback" in r.getMessage().lower() for r in warnings)
