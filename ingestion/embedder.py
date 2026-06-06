"""Embedding adapters behind a Protocol (STORY-003, ADR-6).

Defines the ``Embedder`` Protocol the pipeline embeds chunks through, plus two
adapters: an OpenAI ``text-embedding-3-small`` primary (1536-dim) and a BGE-M3
multilingual fallback. The Protocol lets tests inject a deterministic fake so no
network call or real API key is needed; every adapter's output dimension must
match the Qdrant collection vector size (``db.qdrant_bootstrap.VECTOR_SIZE``,
1536). API keys are read from the environment only - never hardcoded.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from db.qdrant_bootstrap import VECTOR_SIZE

EMBEDDING_DIM: int = VECTOR_SIZE
"""Required embedding dimensionality (matches the Qdrant collection, ADR-6)."""

OPENAI_MODEL: str = "text-embedding-3-small"
"""Primary embedding model id (ADR-6)."""

BGE_M3_MODEL: str = "BAAI/bge-m3"
"""Multilingual fallback embedding model id (ADR-6)."""


@runtime_checkable
class Embedder(Protocol):
    """Embedding interface used by the ingestion pipeline.

    Implementations turn chunk texts into fixed-dimension vectors. The Protocol
    decouples the pipeline from any provider so tests inject a fake embedder.
    """

    @property
    def dimension(self) -> int:
        """Output vector dimensionality (must equal ``EMBEDDING_DIM``)."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into vectors.

        Args:
            texts: Chunk texts to embed.

        Returns:
            One vector per input text, each of length ``dimension``.
        """
        ...


class OpenAIEmbedder:
    """OpenAI ``text-embedding-3-small`` adapter (1536-dim, ADR-6 primary).

    Reads ``OPENAI_API_KEY`` from the environment and imports the ``openai``
    client lazily so the module loads without the dependency or a key present.
    """

    def __init__(self, model: str = OPENAI_MODEL) -> None:
        """Initialize the adapter.

        Args:
            model: OpenAI embedding model id (defaults to text-embedding-3-small).
        """
        self._model = model

    @property
    def dimension(self) -> int:
        """Return the fixed 1536 output dimension."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts via the OpenAI embeddings API.

        Args:
            texts: Chunk texts to embed.

        Returns:
            One 1536-dim vector per input text.

        Raises:
            RuntimeError: When ``OPENAI_API_KEY`` is unset or ``openai`` is not
                importable.
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not set (env-only, no hardcoded key).")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is required for OpenAIEmbedder.") from exc
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(model=self._model, input=texts)
        return [list(item.embedding) for item in response.data]


class BgeM3Embedder:
    """BGE-M3 multilingual fallback adapter (ADR-6 fallback).

    Imports ``FlagEmbedding`` lazily; used when the primary provider is
    unavailable or the document is non-English. Produces ``EMBEDDING_DIM`` vectors.
    """

    def __init__(self, model: str = BGE_M3_MODEL) -> None:
        """Initialize the adapter.

        Args:
            model: BGE-M3 model id.
        """
        self._model = model

    @property
    def dimension(self) -> int:
        """Return the fixed output dimension (aligned to the collection)."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts via the local BGE-M3 model.

        Args:
            texts: Chunk texts to embed.

        Returns:
            One vector per input text.

        Raises:
            RuntimeError: When ``FlagEmbedding`` is not importable.
        """
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            raise RuntimeError(
                "FlagEmbedding package is required for BgeM3Embedder."
            ) from exc
        model = BGEM3FlagModel(self._model, use_fp16=False)
        result = model.encode(texts, return_dense=True)
        return [list(vector) for vector in result["dense_vecs"]]


class FallbackEmbedder:
    """Primary embedder with an automatic fallback on primary failure.

    Tries the primary adapter (OpenAI) first; on any ``RuntimeError`` (missing
    key, provider error) it falls back to the secondary adapter (BGE-M3),
    realizing the ADR-6 primary-plus-multilingual-fallback policy.
    """

    def __init__(self, primary: Embedder, fallback: Embedder) -> None:
        """Initialize with a primary and a fallback embedder.

        Args:
            primary: Preferred embedder (e.g., OpenAIEmbedder).
            fallback: Used when the primary raises.
        """
        self._primary = primary
        self._fallback = fallback

    @property
    def dimension(self) -> int:
        """Return the shared output dimension of both embedders."""
        return self._primary.dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed via the primary, falling back to the secondary on failure.

        Args:
            texts: Chunk texts to embed.

        Returns:
            One vector per input text from whichever embedder succeeded.
        """
        try:
            return self._primary.embed(texts)
        except RuntimeError:
            return self._fallback.embed(texts)
