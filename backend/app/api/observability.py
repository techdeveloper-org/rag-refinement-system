"""Observability surface: the ``/metrics`` scrape endpoint (PRD §21, NFR-009).

Exposes the four product KPIs (token reduction %, answer accuracy, routing
latency, fallback rate) in Prometheus text exposition format. LangSmith
tracing is wired separately at process start via
``backend.app.productization.tracing``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from backend.app.productization.metrics import get_metrics
from backend.app.security.auth import Principal
from backend.app.security.rate_limit import rate_limit

router = APIRouter(tags=["Operations"])

_PROMETHEUS_MEDIA_TYPE = "text/plain; version=0.0.4; charset=utf-8"


@router.get("/metrics", operation_id="getMetrics")
async def get_metrics_endpoint(
    _principal: Principal = Depends(rate_limit()),
) -> Response:
    """Return the product KPIs in Prometheus text exposition format.

    Requires a valid credential (API key or JWT) to prevent anonymous callers
    from extracting operational intelligence (routing behavior, fallback rates,
    query volumes) without authentication.

    Args:
        _principal: The authenticated caller (unused; enforces authentication).

    Returns:
        A plain-text response carrying the aggregate KPI counters/gauges for a
        scrape-based monitor.
    """
    body = get_metrics().render_prometheus()
    return Response(content=body, media_type=_PROMETHEUS_MEDIA_TYPE)
