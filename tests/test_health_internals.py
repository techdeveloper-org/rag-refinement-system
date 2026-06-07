"""Tests for the readiness-probe internals in ``backend.app.health``.

These exercise ``_check_postgres`` (TCP connect), ``_check_qdrant`` (HTTP probe),
and ``evaluate_readiness`` (aggregation + degraded status), which the endpoint
tests cannot reach without real dependencies. Sockets and HTTP are stubbed so no
real PostgreSQL or Qdrant is contacted.
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


class _FakeWriter:
    """Minimal asyncio StreamWriter stub for the postgres TCP probe."""

    def close(self) -> None:
        """No-op close."""

    async def wait_closed(self) -> None:
        """No-op async close."""


class TestCheckPostgres:
    """``_check_postgres`` TCP-connect branches."""

    async def test_returns_false_when_host_missing(self) -> None:
        """A DSN with no host is reported as down."""
        result = await health._check_postgres("postgresql:///db", 0.1)
        assert result is False

    async def test_returns_true_on_successful_connect(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A successful TCP connect reports the dependency up."""

        async def _fake_open_connection(host: str, port: int):
            return (object(), _FakeWriter())

        import asyncio

        monkeypatch.setattr(asyncio, "open_connection", _fake_open_connection)
        result = await health._check_postgres(
            "postgresql://db-host:5432/db", 0.5
        )
        assert result is True

    async def test_returns_true_when_wait_closed_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A wait_closed failure after a successful connect is swallowed (still up)."""

        class _RaisingWriter:
            def close(self) -> None:
                pass

            async def wait_closed(self) -> None:
                raise OSError("already closed")

        async def _fake_open_connection(host: str, port: int):
            return (object(), _RaisingWriter())

        import asyncio

        monkeypatch.setattr(asyncio, "open_connection", _fake_open_connection)
        result = await health._check_postgres(
            "postgresql://db-host:5432/db", 0.5
        )
        assert result is True

    async def test_returns_false_on_connect_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A refused/failed TCP connect reports the dependency down."""

        async def _raise(host: str, port: int):
            raise OSError("connection refused")

        import asyncio

        monkeypatch.setattr(asyncio, "open_connection", _raise)
        result = await health._check_postgres(
            "postgresql://db-host:5432/db", 0.5
        )
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
