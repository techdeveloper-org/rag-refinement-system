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

All singleton builders share a single ``_singleton_lock`` (issue #222). Using
separate locks per singleton created a deadlock window: ``_router_singleton``
held ``_router_lock`` while calling ``_document_store_singleton()``, which
attempted to acquire ``_document_store_lock``. The single lock eliminates this
without loss of concurrency, since singletons are only built once on cold start.
"""

from __future__ import annotations

import threading

from backend.app.api.interfaces import (
    DocumentStore,
    GenerationLLM,
    Ingestor,
    Router,
)
from backend.app.errors import service_unavailable
from backend.app.settings import get_settings

_singleton_lock = threading.RLock()
"""Single re-entrant process-wide lock for all singleton builders (issue #222).

An RLock allows the same thread to call nested singleton builders without
deadlocking (e.g. ``_router_singleton`` calls ``_document_store_singleton``
while already holding the lock).
"""

_document_store_cache: DocumentStore | None = None


def _document_store_singleton() -> DocumentStore:
    """Build the process-wide SQLAlchemy document store from settings.

    Returns:
        A live SqlAlchemyDocumentStore bound to DATABASE_URL.

    Raises:
        ProblemException: 503 when DATABASE_URL is not configured.
    """
    global _document_store_cache
    with _singleton_lock:
        if _document_store_cache is None:
            from backend.app.adapters.document_store import SqlAlchemyDocumentStore
            settings = get_settings()
            if not settings.database_url:
                raise service_unavailable("The document store is not configured.")
            _document_store_cache = SqlAlchemyDocumentStore.from_database_url(settings.database_url)
    return _document_store_cache


_router_cache: Router | None = None


def _router_singleton() -> Router:
    """Build the process-wide router adapter over the live ``router`` package.

    Calls ``_document_store_singleton`` while holding ``_singleton_lock``.
    Using ``threading.RLock`` prevents the deadlock that would occur with a
    plain ``Lock`` when the router and document-store singletons are first
    constructed concurrently (issue #222).

    Returns:
        A live RouterModuleAdapter joined to the document store.
    """
    global _router_cache
    with _singleton_lock:
        if _router_cache is None:
            from router import route as router_route

            from backend.app.adapters.router import RouterModuleAdapter

            _router_cache = RouterModuleAdapter(_document_store_singleton(), router_route)
    return _router_cache


_ingestor_cache: Ingestor | None = None


def _ingestor_singleton() -> Ingestor:
    """Build the process-wide ingestor adapter over the live pipeline.

    Returns:
        A live PipelineIngestor composed with the production collaborators
        (PyMuPDF parser, OpenAI/BGE embedder, db + Qdrant stores).

    Raises:
        ProblemException: 503 when neither DATABASE_SYNC_URL nor
            DATABASE_URL is configured.
    """
    global _ingestor_cache
    with _singleton_lock:
        if _ingestor_cache is None:
            from backend.app.adapters.ingestor import PipelineIngestor
            from backend.app.adapters.stores import QdrantVectorStore, SqlAlchemySectionStore
            from ingestion.embedder import BgeM3Embedder, FallbackEmbedder, OpenAIEmbedder
            from ingestion.parser import PyMuPDFParser
            from ingestion.pipeline import ingest_document

            settings = get_settings()
            sync_url = settings.database_sync_url
            if not sync_url and settings.database_url:
                from sqlalchemy.engine.url import make_url as _make_url
                _parsed = _make_url(settings.database_url)
                sync_url = str(_parsed.set(drivername="postgresql+psycopg"))
            if not sync_url:
                raise service_unavailable("The ingestion section store is not configured.")
            _ingestor_cache = PipelineIngestor(
                parser=PyMuPDFParser(),
                embedder=FallbackEmbedder(OpenAIEmbedder(), BgeM3Embedder()),
                section_store=SqlAlchemySectionStore.from_database_url(sync_url),
                vector_store=QdrantVectorStore(),
                ingest=ingest_document,
            )
    return _ingestor_cache


_generation_llm_cache: GenerationLLM | None = None


def _generation_llm_singleton() -> GenerationLLM:
    """Build the process-wide Claude generation adapter (lazy client).

    Returns:
        A live ClaudeGenerationLLM; its client is built on first stream.
    """
    global _generation_llm_cache
    with _singleton_lock:
        if _generation_llm_cache is None:
            from backend.app.adapters.generation import ClaudeGenerationLLM
            from backend.app.settings import get_settings

            settings = get_settings()
            _generation_llm_cache = ClaudeGenerationLLM(  # type: ignore[assignment]
                thinking_budget_tokens=settings.generation_thinking_budget_tokens
            )
    return _generation_llm_cache  # type: ignore[return-value]


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


async def _dispose_engines() -> None:
    """Dispose all SQLAlchemy engine connection pools on application shutdown.

    Called by the application lifespan handler so that pooled database
    connections are cleanly closed before the process exits (issues #157,
    #203).  Engines that were never initialised (e.g. in tests that do not
    reach the database) are silently skipped.
    """
    global _document_store_cache

    with _singleton_lock:
        store = _document_store_cache

    if store is not None:
        try:
            engine = getattr(store, "_engine", None)
            if engine is not None:
                await engine.dispose()
        except Exception:
            pass
