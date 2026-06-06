"""Tests for the embedding adapters in ``ingestion.embedder``.

Covers the ``OpenAIEmbedder`` happy path (injected client), its missing-key and
missing-package error paths, the ``BgeM3Embedder`` happy path and missing-package
error, the ``FallbackEmbedder`` primary-then-fallback policy (ADR-6), and the
dimension contract. No real OpenAI/BGE network call or key is used.
"""

from __future__ import annotations

import sys

import pytest

from ingestion.embedder import (
    EMBEDDING_DIM,
    BgeM3Embedder,
    Embedder,
    FallbackEmbedder,
    OpenAIEmbedder,
)


class _FakeEmbedder:
    """Minimal deterministic embedder used to drive FallbackEmbedder branches."""

    def __init__(self, *, fail: bool = False, fill: float = 0.0) -> None:
        self._fail = fail
        self._fill = fill

    @property
    def dimension(self) -> int:
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._fail:
            raise RuntimeError("primary unavailable")
        return [[self._fill] * EMBEDDING_DIM for _ in texts]


class TestOpenAIEmbedder:
    """OpenAI primary embedder paths."""

    def test_dimension_is_collection_size(self) -> None:
        """The OpenAI adapter reports the Qdrant collection dimension."""
        assert OpenAIEmbedder().dimension == EMBEDDING_DIM

    def test_embed_raises_without_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Embedding without OPENAI_API_KEY raises (env-only, no hardcoded key)."""
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
            OpenAIEmbedder().embed(["text"])

    def test_embed_uses_injected_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With a key and a stubbed ``openai`` client the adapter returns vectors."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        class _Item:
            def __init__(self, vec: list[float]) -> None:
                self.embedding = vec

        class _Response:
            def __init__(self) -> None:
                self.data = [_Item([0.1] * EMBEDDING_DIM)]

        class _Embeddings:
            def create(self, model: str, input: list[str]) -> _Response:  # noqa: A002
                return _Response()

        class _Client:
            def __init__(self, api_key: str) -> None:
                self.embeddings = _Embeddings()

        import types

        fake_openai = types.ModuleType("openai")
        fake_openai.OpenAI = _Client  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "openai", fake_openai)

        vectors = OpenAIEmbedder().embed(["a"])
        assert len(vectors) == 1
        assert len(vectors[0]) == EMBEDDING_DIM

    def test_embed_raises_when_openai_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing ``openai`` package raises a clear RuntimeError."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setitem(sys.modules, "openai", None)
        with pytest.raises(RuntimeError, match="openai package is required"):
            OpenAIEmbedder().embed(["a"])


class TestBgeM3Embedder:
    """BGE-M3 multilingual fallback embedder paths."""

    def test_dimension_is_collection_size(self) -> None:
        """The BGE-M3 adapter reports the Qdrant collection dimension."""
        assert BgeM3Embedder().dimension == EMBEDDING_DIM

    def test_embed_uses_stubbed_flag_model(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With a stubbed ``FlagEmbedding`` the adapter returns dense vectors."""

        class _Model:
            def __init__(self, model: str, use_fp16: bool) -> None:
                pass

            def encode(self, texts: list[str], return_dense: bool) -> dict[str, object]:
                return {"dense_vecs": [[0.2] * EMBEDDING_DIM for _ in texts]}

        import types

        fake_flag = types.ModuleType("FlagEmbedding")
        fake_flag.BGEM3FlagModel = _Model  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "FlagEmbedding", fake_flag)

        vectors = BgeM3Embedder().embed(["a", "b"])
        assert len(vectors) == 2

    def test_embed_raises_when_flagembedding_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing ``FlagEmbedding`` package raises a clear RuntimeError."""
        monkeypatch.setitem(sys.modules, "FlagEmbedding", None)
        with pytest.raises(RuntimeError, match="FlagEmbedding package is required"):
            BgeM3Embedder().embed(["a"])


class TestFallbackEmbedder:
    """The primary-then-fallback policy (ADR-6)."""

    def test_uses_primary_when_it_succeeds(self) -> None:
        """When the primary succeeds, its result is returned (no fallback)."""
        embedder: Embedder = FallbackEmbedder(
            _FakeEmbedder(fill=0.5), _FakeEmbedder(fill=0.9)
        )
        result = embedder.embed(["a"])
        assert result[0][0] == 0.5

    def test_falls_back_when_primary_raises(self) -> None:
        """When the primary raises RuntimeError, the fallback is used."""
        embedder = FallbackEmbedder(
            _FakeEmbedder(fail=True), _FakeEmbedder(fill=0.9)
        )
        result = embedder.embed(["a"])
        assert result[0][0] == 0.9

    def test_dimension_delegates_to_primary(self) -> None:
        """The fallback reports the shared (primary) dimension."""
        embedder = FallbackEmbedder(_FakeEmbedder(), _FakeEmbedder())
        assert embedder.dimension == EMBEDDING_DIM
