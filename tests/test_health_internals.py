"""Tests for the readiness-probe internals in ``backend.app.health``.

These exercise ``_check_postgres`` (asyncpg real-auth probe), ``_check_qdrant``
(HTTP probe), and ``evaluate_readiness`` (aggregation + degraded status).
All network I/O is stubbed so no real PostgreSQL or Qdrant is contacted.
"""

from __future__ import annotations

import pytest

from backend.app import health
from backend.app.settings import Settings

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only."""
    return "asyncio"


class _FakeConn:
    """Minimal asyncpg connection stub that succeeds the SELECT 1 probe."""

    async def execute(self, sql: str) -> None:
        """Accept any SQL without error."""

    async def close(self) -> None:
        """No-op close."""


class TestCheckPostgres:
    """``_check_postgres`` asyncpg-connect branches."""

    async def test_returns_false_when_host_missing(self) -> None:
        """A DSN that asyncpg cannot parse or connect to is reported as down."""
        result = await health._check_postgres("postgresql:///db", 0.1)
        assert result is False

    async def test_returns_true_on_successful_authenticated_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A successful asyncpg connect + SELECT 1 reports postgres up."""

        async def _fake_connect(url: str, **kwargs: object) -> _FakeConn:
            return _FakeConn()

        import asyncpg

        monkeypatch.setattr(asyncpg, "connect", _fake_connect)
        result = await health._check_postgres("postgresql://h:5432/db", 0.5)
        assert result is True

    async def test_returns_false_on_authentication_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Wrong credentials report postgres down even when the host is reachable.

        This distinguishes the TCP-open but bad-credentials case from a network
        failure, verifying that the probe requires a real authenticated query.
        """

        class _BadCredsConn:
            async def execute(self, sql: str) -> None:
                raise Exception("FATAL: password authentication failed for user")

            async def close(self) -> None:
                pass

        async def _fake_connect(url: str, **kwargs: object) -> _BadCredsConn:
            return _BadCredsConn()

        import asyncpg

        monkeypatch.setattr(asyncpg, "connect", _fake_connect)
        result = await health._check_postgres("postgresql://h:5432/db", 0.5)
        assert result is False

    async def test_returns_false_on_connect_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A refused/failed TCP connect reports postgres down."""

        async def _raise(url: str, **kwargs: object) -> object:
            raise OSError("connection refused")

        import asyncpg

        monkeypatch.setattr(asyncpg, "connect", _raise)
        result = await health._check_postgres("postgresql://h:5432/db", 0.5)
        assert result is False


class TestCheckQdrant:
    """``_check_qdrant`` HTTP-probe branches."""

    async def test_returns_true_on_2xx(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 2xx from /readyz reports Qdrant up."""

        class _Resp:
            is_success = True

        class _Client:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *a: object) -> None:
                return None

            async def get(self, url: str) -> _Resp:
                assert url.endswith("/readyz")
                return _Resp()

        monkeypatch.setattr(health.httpx, "AsyncClient", _Client)
        result = await health._check_qdrant("http://qdrant:6333", 0.5)
        assert result is True

    async def test_returns_false_on_http_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A transport error reports Qdrant down."""

        class _Client:
            def __init__(self, *a: object, **k: object) -> None:
                pass

            async def __aenter__(self) -> _Client:
                return self

            async def __aexit__(self, *a: object) -> None:
                return None

            async def get(self, url: str) -> object:
                raise health.httpx.ConnectError("down")

        monkeypatch.setattr(health.httpx, "AsyncClient", _Client)
        result = await health._check_qdrant("http://qdrant:6333", 0.5)
        assert result is False


class TestEvaluateReadiness:
    """``evaluate_readiness`` aggregation and degraded status."""

    async def test_unconfigured_dependencies_report_degraded(self) -> None:
        """Unconfigured DATABASE_URL/QDRANT_URL surface as degraded + down."""
        settings = Settings(database_url=None, qdrant_url=None, JWT_ISSUER="test-issuer")
        readiness = await health.evaluate_readiness(settings)
        assert readiness.status == "degraded"
        assert readiness.dependencies == {"postgres": "down", "qdrant": "down"}

    async def test_all_up_reports_ready(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When both probes pass, readiness is 'ready' with both up."""

        async def _pg_up(url: str, t: float) -> bool:
            return True

        async def _qd_up(url: str, t: float) -> bool:
            return True

        monkeypatch.setattr(health, "_check_postgres", _pg_up)
        monkeypatch.setattr(health, "_check_qdrant", _qd_up)
        settings = Settings(
            DATABASE_URL="postgresql://h:5432/db",
            QDRANT_URL="http://q:6333",
            JWT_ISSUER="test-issuer",
        )
        readiness = await health.evaluate_readiness(settings)
        assert readiness.status == "ready"
        assert readiness.dependencies == {"postgres": "up", "qdrant": "up"}

    async def test_one_down_reports_degraded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A single down dependency degrades the overall status."""

        async def _pg_up(url: str, t: float) -> bool:
            return True

        async def _qd_down(url: str, t: float) -> bool:
            return False

        monkeypatch.setattr(health, "_check_postgres", _pg_up)
        monkeypatch.setattr(health, "_check_qdrant", _qd_down)
        settings = Settings(
            DATABASE_URL="postgresql://h:5432/db",
            QDRANT_URL="http://q:6333",
            JWT_ISSUER="test-issuer",
        )
        readiness = await health.evaluate_readiness(settings)
        assert readiness.status == "degraded"
        assert readiness.dependencies["postgres"] == "up"
        assert readiness.dependencies["qdrant"] == "down"
