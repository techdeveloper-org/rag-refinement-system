"""Probe tests for STORY-004 health and readiness endpoints (NFR-009).

These tests run without any external service: liveness is dependency-free,
and readiness behavior is exercised by overriding the settings so that
dependency reachability is deterministic.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import health as health_module
from backend.app.main import create_app
from backend.app.settings import Settings


@pytest.fixture
def client() -> TestClient:
    """Provide a TestClient over a freshly built application.

    Returns:
        A FastAPI TestClient bound to a new app instance.
    """
    return TestClient(create_app())


def test_health_returns_200(client: TestClient) -> None:
    """Liveness must return 200 with status 'ok' and no external deps."""
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_ready_returns_503_when_dependency_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness must return 503 when a configured dependency is down.

    Sends an API-key header so the dependency breakdown is included in the
    response (authenticated callers receive the full ``dependencies`` map per
    the auth-gating logic in ``get_readiness``).
    """

    async def fake_evaluate(settings: Settings) -> health_module.ReadinessStatus:
        return health_module.ReadinessStatus(
            status="degraded",
            dependencies={"postgres": "down", "qdrant": "up"},
        )

    monkeypatch.setattr(health_module, "evaluate_readiness", fake_evaluate)
    response = client.get("/ready", headers={"X-API-Key": "probe-key"})
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["postgres"] == "down"


def test_ready_returns_200_when_deps_up(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness must return 200 when all dependencies report up."""

    async def fake_evaluate(settings: Settings) -> health_module.ReadinessStatus:
        return health_module.ReadinessStatus(
            status="ready",
            dependencies={"postgres": "up", "qdrant": "up"},
        )

    monkeypatch.setattr(health_module, "evaluate_readiness", fake_evaluate)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


@pytest.mark.anyio
async def test_unconfigured_deps_report_down() -> None:
    """With no DATABASE_URL/QDRANT_URL set, readiness is degraded."""
    settings = Settings(DATABASE_URL=None, QDRANT_URL=None, JWT_ISSUER="test-issuer")
    readiness = await health_module.evaluate_readiness(settings)
    assert readiness.status == "degraded"
    assert readiness.dependencies["postgres"] == "down"
    assert readiness.dependencies["qdrant"] == "down"


@pytest.fixture
def anyio_backend() -> str:
    """Restrict anyio-driven async tests to the asyncio backend."""
    return "asyncio"
