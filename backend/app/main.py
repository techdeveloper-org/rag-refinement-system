"""FastAPI application factory for the RAG Refinement System backend.

Builds the real ASGI application: the liveness/readiness probe router
(NFR-009, ADR-5), the /v1 routing, answer, and document/compliance routers
(openapi.yaml), and the RFC-7807 exception handlers. The factory is
side-effect free so it can be imported by the test suite and run without
external dependencies.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.app.api.answer import router as answer_router
from backend.app.api.documents import router as documents_router
from backend.app.api.routing import router as routing_router
from backend.app.errors import register_exception_handlers
from backend.app.health import router as health_router
from backend.app.settings import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns:
        A FastAPI app with the health/readiness, routing, answer, and document
        routers mounted and the RFC-7807 exception handlers registered.
    """
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="TOC-routed retrieval layer backend.",
    )
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(routing_router)
    app.include_router(answer_router)
    app.include_router(documents_router)
    return app


app = create_app()
