"""RAG Refinement System backend application package.

Exposes the FastAPI application factory used by the ASGI server and the
test suite. Keeping the factory importable without side effects lets the
health-probe tests run without any external dependency.
"""

from backend.app.main import create_app

__all__ = ["create_app"]
