"""Liveness and readiness probe router (NFR-009).

Implements the ``getHealth`` (liveness) and ``getReadiness`` (readiness)
operations declared in ``docs/phase-1-api-contracts/openapi.yaml``. Liveness
reports only that the process is running. Readiness checks that the backing
dependencies (PostgreSQL via ``DATABASE_URL`` and Qdrant via ``QDRANT_URL``)
are reachable and returns HTTP 503 when any configured dependency is down.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from backend.app.settings import Settings, get_settings

router = APIRouter(tags=["Operations"])

_DEP_UP = "up"
_DEP_DOWN = "down"


class HealthStatus(BaseModel):
    """Liveness response body matching the HealthStatus schema.

    Attributes:
        status: Always ``ok`` when the process is alive.
        version: Service version string.
    """

    status: str = "ok"
    version: str | None = None


class ReadinessStatus(BaseModel):
    """Readiness response body matching the ReadinessStatus schema.

    Attributes:
        status: ``ready`` when all dependencies are up, else ``degraded``.
        dependencies: Per-dependency reachability map (``up``/``down``).
    """

    status: str
    dependencies: dict[str, str]


async def _check_postgres(database_url: str, timeout_seconds: float) -> bool:
    """Check PostgreSQL reachability by performing a real authenticated query.

    Opens a genuine asyncpg connection and executes SELECT 1 so that a
    healthy result requires valid credentials, not just an open TCP port.
    The connection is closed immediately after the probe query succeeds.

    Args:
        database_url: PostgreSQL DSN (supports host-based and Unix socket URLs).
        timeout_seconds: Connection timeout budget in seconds.

    Returns:
        True if the authenticated query succeeded, otherwise False.
    """
    import asyncpg

    try:
        conn = await asyncpg.connect(database_url, timeout=timeout_seconds)
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()
        return True
    except asyncio.CancelledError:
        raise
    except BaseException:
        return False


async def _check_qdrant(qdrant_url: str, timeout_seconds: float) -> bool:
    """Check Qdrant reachability via its HTTP readiness endpoint.

    Args:
        qdrant_url: Qdrant base URL.
        timeout_seconds: Request timeout budget in seconds.

    Returns:
        True if Qdrant answered with a 2xx status, otherwise False.
    """
    probe_url = qdrant_url.rstrip("/") + "/readyz"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(probe_url)
        return response.is_success
    except (httpx.HTTPError, OSError):
        return False


async def _never_ready() -> bool:
    """Return False immediately for an unconfigured dependency."""
    return False


async def evaluate_readiness(settings: Settings) -> ReadinessStatus:
    """Probe all configured dependencies and build a readiness report.

    A dependency that has no configured URL is reported as ``down`` so that an
    unconfigured deployment is surfaced as not-ready rather than silently
    passing.

    Args:
        settings: Resolved application settings.

    Returns:
        A ReadinessStatus aggregating each dependency's reachability.
    """
    timeout_seconds = settings.readiness_timeout_seconds
    dependencies: dict[str, str] = {}

    postgres_coro = (
        _check_postgres(settings.database_url, timeout_seconds)
        if settings.database_url
        else _never_ready()
    )
    qdrant_coro = (
        _check_qdrant(settings.qdrant_url, timeout_seconds)
        if settings.qdrant_url
        else _never_ready()
    )
    postgres_up, qdrant_up = await asyncio.gather(postgres_coro, qdrant_coro)
    dependencies["postgres"] = _DEP_UP if postgres_up else _DEP_DOWN
    dependencies["qdrant"] = _DEP_UP if qdrant_up else _DEP_DOWN

    all_up = all(state == _DEP_UP for state in dependencies.values())
    return ReadinessStatus(
        status="ready" if all_up else "degraded",
        dependencies=dependencies,
    )


@router.get("/health", operation_id="getHealth", response_model=HealthStatus)
async def get_health() -> HealthStatus:
    """Return liveness with HTTP 200 whenever the process is running.

    Returns:
        A HealthStatus with ``status='ok'`` and the service version.
    """
    settings = get_settings()
    return HealthStatus(status="ok", version=settings.app_version)


@router.get(
    "/ready",
    operation_id="getReadiness",
    response_model=ReadinessStatus,
)
async def get_readiness(response: Response) -> ReadinessStatus:
    """Return readiness, setting HTTP 503 when any dependency is down.

    Args:
        response: The response object whose status code is set to 503 on a
            degraded result.

    Returns:
        A ReadinessStatus describing each dependency's reachability.
    """
    settings = get_settings()
    readiness = await evaluate_readiness(settings)
    if readiness.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness
