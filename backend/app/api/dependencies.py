"""Dependency providers for the API collaborators.

These FastAPI dependency callables return the live :class:`DocumentStore`,
:class:`Router`, :class:`Ingestor`, and :class:`GenerationLLM` adapters in
production. Each provider constructs a thin adapter (``backend.app.adapters``)
that binds the backend service-boundary Protocols to the real ``router`` /
``ingestion`` / ``db`` modules and the Anthropic generation client - the live
composition root. Adapters are built once per process and cached so the heavy
collaborators (the SQLAlchemy engine, the pipeline collaborators) are created
lazily on first request rather than at import time.

The test suite continues to override each provider with a fake via
``app.dependency_overrides`` so the HTTP contract is exercised in isolation; the
fakes satisfy the same Protocols these adapters implement.
"""

from __future__ import annotations

from functools import lru_cache

from backend.app.api.interfaces import (
    DocumentStore,
    GenerationLLM,
    Ingestor,
    Router,
)
from backend.app.errors import service_unavailable
from backend.app.settings import get_settings


@lru_cache
def _document_store_singleton() -> DocumentStore:
    """Build the process-wide SQLAlchemy document store from settings.

    Returns:
        A live :class:`SqlAlchemyDocumentStore` bound to ``DATABASE_URL``.

    Raises:
        ProblemException: 503 when ``DATABASE_URL`` is not configured.
    """
    from backend.app.adapters.document_store import SqlAlchemyDocumentStore

    settings = get_settings()
    if not settings.database_url:
        raise service_unavailable("The document store is not configured.")
    return SqlAlchemyDocumentStore.from_database_url(settings.database_url)


@lru_cache
def _router_singleton() -> Router:
    """Build the process-wide router adapter over the live ``router`` package.

    Returns:
        A live :class:`RouterModuleAdapter` joined to the document store.
    """
    from router import route as router_route

    from backend.app.adapters.router import RouterModuleAdapter

    return RouterModuleAdapter(_document_store_singleton(), router_route)


@lru_cache
def _ingestor_singleton() -> Ingestor:
    """Build the process-wide ingestor adapter over the live pipeline.

    Returns:
        A live :class:`PipelineIngestor` composed with the production
        collaborators (PyMuPDF parser, OpenAI/BGE embedder, db + Qdrant stores).

    Raises:
        ProblemException: 503 when neither ``DATABASE_SYNC_URL`` nor
            ``DATABASE_URL`` is configured.
    """
    from backend.app.adapters.ingestor import PipelineIngestor
    from backend.app.adapters.stores import QdrantVectorStore, SqlAlchemySectionStore
    from ingestion.embedder import BgeM3Embedder, FallbackEmbedder, OpenAIEmbedder
    from ingestion.parser import PyMuPDFParser
    from ingestion.pipeline import ingest_document

    settings = get_settings()
    sync_url = settings.database_sync_url or settings.database_url
    if not sync_url:
        raise service_unavailable("The ingestion section store is not configured.")
    return PipelineIngestor(
        parser=PyMuPDFParser(),
        embedder=FallbackEmbedder(OpenAIEmbedder(), BgeM3Embedder()),
        section_store=SqlAlchemySectionStore.from_database_url(sync_url),
        vector_store=QdrantVectorStore(),
        ingest=ingest_document,
    )


@lru_cache
def _generation_llm_singleton() -> GenerationLLM:
    """Build the process-wide Claude generation adapter (lazy client).

    Returns:
        A live :class:`ClaudeGenerationLLM`; its client is built on first stream.
    """
    from backend.app.adapters.generation import ClaudeGenerationLLM

    return ClaudeGenerationLLM()


def get_document_store() -> DocumentStore:
    """Provide the live structure-store accessor.

    Returns:
        A :class:`DocumentStore` implementation backed by ``db.models``.
    """
    return _document_store_singleton()


def get_router() -> Router:
    """Provide the live in-process router.

    Returns:
        A :class:`Router` implementation backed by the ``router`` package.
    """
    return _router_singleton()


def get_ingestor() -> Ingestor:
    """Provide the live ingestion pipeline.

    Returns:
        An :class:`Ingestor` implementation backed by ``ingestion.ingest_document``.
    """
    return _ingestor_singleton()


def get_generation_llm() -> GenerationLLM:
    """Provide the live streaming generation LLM.

    Returns:
        A :class:`GenerationLLM` implementation backed by Anthropic Claude.
    """
    return _generation_llm_singleton()
