"""Embedding adapters behind a Protocol (STORY-003, ADR-6).

Defines the ``Embedder`` Protocol the pipeline embeds chunks through, plus two
adapters: an OpenAI ``text-embedding-3-small`` primary (1536-dim) and a BGE-M3
multilingual fallback. The Protocol lets tests inject a deterministic fake so no
network call or real API key is needed; every adapter's output dimension must
match the Qdrant collection vector size (``db.qdrant_bootstrap.VECTOR_SIZE``,
1536). API keys are read from the environment only - never hardcoded.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Protocol, runtime_checkable

from db.qdrant_bootstrap import VECTOR_SIZE

logger = logging.getLogger(__name__)
"""Module logger; fallback activation is logged here at WARNING for auditability."""

EMBEDDING_DIM: int = VECTOR_SIZE
"""Required embedding dimensionality (matches the Qdrant collection, ADR-6)."""

OPENAI_MODEL: str = "text-embedding-3-small"
"""Primary embedding model id (ADR-6)."""

BGE_M3_MODEL: str = "BAAI/bge-m3"
"""Multilingual fallback embedding model id (ADR-6)."""


class EmbedderDimensionError(ValueError):
    """Raised when an embedder returns vectors whose length is not ``EMBEDDING_DIM``.

    Guards the AGREED CONTRACT that every vector upserted into Qdrant matches the
    collection's 1536-dim size (ADR-6). BGE-M3 is natively 1024-dim, so a fallback
    that silently returned its vectors would corrupt the 1536-dim collection; this
    typed error makes the mismatch loud instead of silently wrong.
    """


def _primary_unavailability_errors() -> tuple[type[BaseException], ...]:
    """Return the curated exception types that mean the primary embedder is unavailable.

    Only errors that represent primary UNAVAILABILITY or transience trigger the BGE-M3
    fallback (ING-A4): ``RuntimeError`` (missing key / missing client library),
    ``ConnectionError`` and ``TimeoutError`` (network), ``OSError`` (socket / file), and
    the OpenAI SDK ``APIError`` base when it is importable. Programming bugs
    (``TypeError``, ``AttributeError``, ``KeyError``, ``ValueError``) are deliberately
    excluded so they propagate instead of being masked as a silent permanent fallback.
    ``EmbedderDimensionError`` is a ``ValueError`` subclass and is likewise excluded, so
    a dimension misconfiguration is never swallowed into a silent fallback.

    Returns:
        A tuple of exception classes treated as primary-unavailability signals.
    """
    transient: list[type[BaseException]] = [
        RuntimeError,
        ConnectionError,
        TimeoutError,
        OSError,
    ]
    try:
        from openai import APIError
    except ImportError:
        return tuple(transient)
    transient.append(APIError)
    return tuple(transient)


_PRIMARY_UNAVAILABILITY_ERRORS: tuple[type[BaseException], ...] = (
    _primary_unavailability_errors()
)
"""Curated primary-unavailability exception types caught by ``FallbackEmbedder`` (ING-A4)."""


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

    Imports the ``openai`` client and reads ``OPENAI_API_KEY`` lazily on the
    first ``embed()`` call so the module and constructor work without the
    dependency or a key present at import/init time.
    """

    def __init__(self, model: str = OPENAI_MODEL) -> None:
        """Initialize the adapter without building the client (lazy-load).

        The heavyweight OpenAI HTTP client is deferred to the first ``embed()``
        call so that importing or constructing this adapter does not require
        ``OPENAI_API_KEY`` or the ``openai`` package at init time.

        Args:
            model: OpenAI embedding model id (defaults to text-embedding-3-small).
        """
        self._model = model
        self._client: object | None = None
        self._client_lock = __import__("threading").Lock()

    def _ensure_client(self) -> object:
        """Return the shared OpenAI client, building it on first call.

        Returns:
            The reusable ``OpenAI`` client instance.

        Raises:
            RuntimeError: When ``OPENAI_API_KEY`` is unset or ``openai`` is not
                importable.
        """
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    api_key = os.environ.get("OPENAI_API_KEY")
                    if not api_key:
                        raise RuntimeError(
                            "OPENAI_API_KEY is not set (env-only, no hardcoded key)."
                        )
                    try:
                        from openai import OpenAI
                    except ImportError as exc:
                        raise RuntimeError(
                            "openai package is required for OpenAIEmbedder."
                        ) from exc
                    self._client = OpenAI(api_key=api_key)
        return self._client

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
        """
        client = self._ensure_client()
        response = client.embeddings.create(model=self._model, input=texts)  # type: ignore[attr-defined]
        return [list(item.embedding) for item in response.data]


class BgeM3Embedder:
    """BGE-M3 multilingual fallback adapter (ADR-6 fallback).

    Imports ``FlagEmbedding`` lazily; used when the primary provider is
    unavailable or the document is non-English. Produces ``EMBEDDING_DIM`` vectors.
    """

    def __init__(self, model: str = BGE_M3_MODEL) -> None:
        """Initialize the adapter without loading the model (#260 lazy-load).

        The heavyweight BGE-M3 model is deferred to first ``embed()`` call so
        that importing this module does not pay the load cost up front. A
        double-checked lock ensures the model is loaded exactly once under
        concurrent access.

        Args:
            model: BGE-M3 model id.
        """
        self._model_name = model
        self._flag_model = None
        self._load_lock = threading.Lock()

    BGE_M3_OUTPUT_DIM: int = 1024
    """Actual dense-vector output dimension of the BGE-M3 model."""

    def _ensure_model(self) -> object:
        """Return the loaded BGEM3FlagModel, loading it on first call.

        Uses a double-checked lock so concurrent callers never load the model
        more than once. Raises ``RuntimeError`` if ``FlagEmbedding`` is absent.

        Returns:
            The ready-to-use ``BGEM3FlagModel`` instance.

        Raises:
            RuntimeError: When ``FlagEmbedding`` is not importable.
        """
        if self._flag_model is None:
            with self._load_lock:
                if self._flag_model is None:
                    try:
                        from FlagEmbedding import BGEM3FlagModel
                    except ImportError as exc:
                        raise RuntimeError(
                            "FlagEmbedding package is required for BgeM3Embedder."
                        ) from exc
                    self._flag_model = BGEM3FlagModel(
                        self._model_name, use_fp16=True
                    )
        return self._flag_model

    @property
    def dimension(self) -> int:
        """Return the required Qdrant collection dimension (``EMBEDDING_DIM``)."""
        return EMBEDDING_DIM

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts via the lazily-loaded local BGE-M3 model.

        Accepts whichever dense-vector key FlagEmbedding returns across
        versions (``dense_vecs``, ``dense``, or ``embeddings``). Raises
        ``RuntimeError`` when none of the expected keys are present (#245).

        Args:
            texts: Chunk texts to embed.

        Returns:
            One vector per input text.

        Raises:
            RuntimeError: When FlagEmbedding returns an unrecognised output
                structure (none of the expected dense-vector keys present).
        """
        model = self._ensure_model()
        result = model.encode(texts, return_dense=True)  # type: ignore[attr-defined]
        dense = next(
            (v for k in ("dense_vecs", "dense", "embeddings") if (v := result.get(k)) is not None),
            None,
        )
        if dense is None:
            raise RuntimeError(
                f"FlagEmbedding returned unexpected output keys: {list(result.keys())}. "
                f"Expected 'dense_vecs', 'dense', or 'embeddings'."
            )
        return [[float(x) for x in vec] for vec in dense]


class FallbackEmbedder:
    """Primary embedder with an automatic fallback on primary failure.

    Tries the primary adapter (OpenAI) first; only a CURATED set of primary
    UNAVAILABILITY / transient errors (missing key, provider/network error, client
    library error - see ``_primary_unavailability_errors``) degrades to the secondary
    adapter (BGE-M3), realizing the ADR-6 primary-plus-multilingual-fallback policy.
    Programming bugs (``TypeError``, ``AttributeError``, ``KeyError``, ``ValueError``)
    are NOT caught (ING-A4): they propagate so a genuine defect is not masked as a
    silent permanent fallback. A dimension mismatch (``EmbedderDimensionError``, a
    ``ValueError`` subclass) likewise propagates. Vector dimensions are NOT validated
    here: the single authoritative dimension guard lives at the pipeline embed ->
    upsert boundary, which validates ANY embedder including bare adapters, so
    validating again here would be a redundant O(n) second pass (ING-A6).
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
        """Embed via the primary, falling back to the secondary on primary unavailability.

        Only a curated set of primary UNAVAILABILITY / transient errors (missing key,
        provider/network error, client library error) degrades to the fallback, logged
        at WARNING so the model swap is auditable. Programming bugs (``TypeError``,
        ``AttributeError``, ``KeyError``, ``ValueError``) and dimension mismatches
        (``EmbedderDimensionError``) are NOT caught - they propagate rather than being
        masked as a silent permanent fallback (ING-A4). Vector dimensions are not
        validated here; the authoritative guard is the pipeline embed -> upsert
        boundary, so this method does not duplicate that O(n) pass (ING-A6).

        Args:
            texts: Chunk texts to embed.

        Returns:
            One vector per input text from whichever embedder served the request.

        Raises:
            TypeError, AttributeError, KeyError, ValueError, EmbedderDimensionError:
                Propagated from the primary - never masked by a silent fallback.
        """
        try:
            return self._primary.embed(texts)
        except _PRIMARY_UNAVAILABILITY_ERRORS as exc:
            logger.warning(
                "Primary embedder unavailable (%s); activating fallback embedder.",
                exc,
            )
            return self._fallback.embed(texts)
