"""Unit tests for the product-KPI metrics registry and /metrics endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.productization.metrics import ProductMetrics, get_metrics


def test_record_routing_tracks_latency_and_fallback() -> None:
    metrics = ProductMetrics()
    metrics.record_routing(latency_ms=120.0, fallback=False, token_reduction=0.6)
    metrics.record_routing(latency_ms=80.0, fallback=True)

    assert metrics.routing_total == 2
    assert metrics.fallback_total == 1
    assert metrics.routing_latency_ms.average == 100.0
    assert metrics.fallback_rate == 0.5
    assert metrics.token_reduction.average == 0.6


def test_fallback_rate_is_zero_with_no_routing() -> None:
    metrics = ProductMetrics()

    assert metrics.fallback_rate == 0.0
    assert metrics.token_reduction.average == 0.0


def test_record_answer_accuracy_averages() -> None:
    metrics = ProductMetrics()
    metrics.record_answer_accuracy(0.9)
    metrics.record_answer_accuracy(0.7)

    assert metrics.answer_accuracy.average == 0.8


def test_reset_clears_all_counters() -> None:
    metrics = ProductMetrics()
    metrics.record_routing(latency_ms=50.0, fallback=True, token_reduction=0.4)
    metrics.record_answer_accuracy(0.5)

    metrics.reset()

    assert metrics.routing_total == 0
    assert metrics.fallback_total == 0
    assert metrics.answer_accuracy.average == 0.0
    assert metrics.token_reduction.average == 0.0


def test_render_prometheus_exposition_contains_all_kpis() -> None:
    metrics = ProductMetrics()
    metrics.record_routing(latency_ms=200.0, fallback=False, token_reduction=0.55)
    metrics.record_answer_accuracy(0.92)

    body = metrics.render_prometheus()

    assert "rag_token_reduction_ratio 0.55" in body
    assert "rag_answer_accuracy_ratio 0.92" in body
    assert "rag_routing_latency_ms_sum 200.0" in body
    assert "rag_routing_total 1" in body
    assert "rag_fallback_total 0" in body
    assert "rag_routing_latency_ms_count 1" in body
    assert body.endswith("\n")


def test_metrics_endpoint_returns_prometheus_text() -> None:
    get_metrics().reset()
    client = TestClient(create_app())

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "rag_routing_total" in response.text
