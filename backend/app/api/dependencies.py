"""Dependency providers for the API collaborators.

These FastAPI dependency callables return the live :class:`DocumentStore`,
:class:`Router`, :class:`Ingestor`, and :class:`GenerationLLM` in production.
The concrete implementations are owned by other agents and are still being
built in parallel; until they are wired, the providers raise a retryable 503
SERVICE_UNAVAILABLE. The test suite overrides each provider with a fake via
``app.dependency_overrides`` so the HTTP contract is exercised in isolation.
"""

from __future__ import annotations

from backend.app.api.interfaces import (
    DocumentStore,
    GenerationLLM,
    Ingestor,
    Router,
)
from backend.app.errors import service_unavailable


def get_document_store() -> DocumentStore:
    """Provide the live structure-store accessor.

    Returns:
        A :class:`DocumentStore` implementation.

    Raises:
        ProblemException: 503 until the database-engineer store is wired.
    """
    raise service_unavailable("The document store is not yet available.")


def get_router() -> Router:
    """Provide the live in-process router.

    Returns:
        A :class:`Router` implementation.

    Raises:
        ProblemException: 503 until the ai-engineer router is wired.
    """
    raise service_unavailable("The routing service is not yet available.")


def get_ingestor() -> Ingestor:
    """Provide the live ingestion pipeline.

    Returns:
        An :class:`Ingestor` implementation.

    Raises:
        ProblemException: 503 until the data-engineer pipeline is wired.
    """
    raise service_unavailable("The ingestion pipeline is not yet available.")


def get_generation_llm() -> GenerationLLM:
    """Provide the live streaming generation LLM.

    Returns:
        A :class:`GenerationLLM` implementation.

    Raises:
        ProblemException: 503 until the ai-engineer generator is wired.
    """
    raise service_unavailable("The generation service is not yet available.")
