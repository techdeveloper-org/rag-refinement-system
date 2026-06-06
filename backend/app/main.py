"""FastAPI application factory for the RAG Refinement System backend.

Builds a minimal but real ASGI application that mounts the liveness and
readiness probe router (NFR-009, ADR-5). The factory is side-effect free so
it can be imported by the test suite and run without external dependencies.
"""

from __future__ import annotations

from fastapi import FastAPI

from backend.app.health import router as health_router
from backend.app.settings import get_settings


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance.

    Returns:
        A FastAPI app with the health/readiness router mounted.
    """
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="TOC-routed retrieval layer backend (operations surface).",
    )
    app.include_router(health_router)
    return app


app = create_app()
