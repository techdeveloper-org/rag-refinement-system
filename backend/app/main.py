"""FastAPI application factory for the RAG Refinement System backend.

Builds the real ASGI application: the liveness/readiness probe router
(NFR-009, ADR-5), the /v1 routing, answer, and document/compliance routers
(openapi.yaml), the ``/metrics`` observability surface (PRD §21), and the
RFC-7807 exception handlers. LangSmith tracing is configured from the
environment at construction time. The factory is side-effect free with respect
to external dependencies so it can be imported by the test suite and run
without credentials.

Notes on test isolation: ``configure_tracing()`` accepts an injectable
``environ`` dict so tests can pass their own environment without mutating
``os.environ`` as a side effect of ``create_app()`` (issue #219).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.answer import router as answer_router
from backend.app.api.documents import router as documents_router
from backend.app.api.observability import router as observability_router
from backend.app.api.routing import router as routing_router
from backend.app.errors import register_exception_handlers
from backend.app.health import router as health_router
from backend.app.productization.tracing import configure_tracing
from backend.app.settings import get_settings

_logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Manage application startup and shutdown lifecycle.

    On startup no eager initialisation is performed — heavyweight singletons
    (SQLAlchemy engine, Qdrant client, etc.) are created lazily on first
    request so the process starts quickly and without requiring credentials in
    the test environment.

    On shutdown, the SQLAlchemy async engine pool is disposed so that all
    pooled connections are cleanly closed before the process exits (issues
    #157, #203).

    Args:
        _app: The FastAPI application instance (unused).

    Yields:
        Control to the running application.
    """
    yield
    try:
        from backend.app.api.dependencies import _dispose_engines

        await _dispose_engines()
    except Exception:
        _logger.debug("Engine disposal skipped (engines may not have been initialised).")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns:
        A FastAPI app with the health/readiness, routing, answer, and document
        routers mounted and the RFC-7807 exception handlers registered.
    """
    settings = get_settings()
    configure_tracing()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="TOC-routed retrieval layer backend.",
        lifespan=_lifespan,
    )
    # When CORS is configured with a wildcard origin ("*"), modern browsers
    # reject responses that also carry Access-Control-Allow-Credentials: true
    # (the combination is forbidden by the Fetch spec).  Disable the
    # credentials header automatically when the wildcard is present so that
    # development environments work without manual configuration (issue #147).
    allow_credentials = "*" not in settings.cors_allowed_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(observability_router)
    app.include_router(routing_router)
    app.include_router(answer_router)
    app.include_router(documents_router)
    return app


app = create_app()
