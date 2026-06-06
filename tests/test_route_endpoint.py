"""Tests for POST /v1/route (routeQuery) - routing-only, oneOf 422.

Covers: auth required, tenant IDOR guard, the oneOf(document_id |
document_ids) both/neither -> 422 contract (AC-ADV-001), the routing-only
invariant (generation never invoked), and the RouteResponse shape.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TENANT_B, make_jwt


def test_route_requires_auth(client: TestClient) -> None:
    """An unauthenticated /v1/route request returns 401."""
    response = client.post("/v1/route", json={"document_id": "doc_abc123", "query": "q"})
    assert response.status_code == 401


def test_route_single_document_returns_200(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """document_id alone yields a 200 RouteResponse with routed sections."""
    response = client.post(
        "/v1/route",
        headers=auth_headers,
        json={"document_id": "doc_abc123", "query": "warranty period?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["query_id"].startswith("qry_")
    assert body["fallback"] is False
    assert len(body["relevant_sections"]) == 1
    assert body["relevant_sections"][0]["section_id"] == "sec_warranty"
    assert body["estimated_token_reduction"].endswith("%")


def test_route_document_ids_returns_200(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """document_ids alone yields a 200 RouteResponse."""
    response = client.post(
        "/v1/route",
        headers=auth_headers,
        json={"document_ids": ["doc_abc123"], "query": "warranty?"},
    )
    assert response.status_code == 200


def test_route_both_selectors_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Providing both document_id and document_ids is a 422 (AC-ADV-001)."""
    response = client.post(
        "/v1/route",
        headers=auth_headers,
        json={
            "document_id": "doc_abc123",
            "document_ids": ["doc_abc123"],
            "query": "q",
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_route_neither_selector_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Providing neither document selector is a 422 (AC-ADV-001)."""
    response = client.post("/v1/route", headers=auth_headers, json={"query": "q"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_route_cross_tenant_document_returns_404(client: TestClient) -> None:
    """Routing against another tenant's document is blocked (IDOR -> 404)."""
    headers = {"Authorization": f"Bearer {make_jwt(TENANT_B)}"}
    response = client.post(
        "/v1/route",
        headers=headers,
        json={"document_id": "doc_abc123", "query": "q"},
    )
    assert response.status_code == 404


def test_route_never_triggers_generation(
    client: TestClient, auth_headers: dict[str, str], fakes: dict[str, object]
) -> None:
    """The routing-only endpoint never invokes the generation LLM (HLD 7.2)."""
    client.post(
        "/v1/route",
        headers=auth_headers,
        json={"document_id": "doc_abc123", "query": "q"},
    )
    llm = fakes["llm"]
    assert getattr(llm, "stream_answer_calls", 0) == 0
    assert fakes["router"].calls == 1


def test_route_fallback_true_when_router_falls_back(
    client: TestClient, auth_headers: dict[str, str], fakes: dict[str, object]
) -> None:
    """The response reports fallback=true when the router falls back (FR-009)."""
    fakes["router"].fallback = True
    response = client.post(
        "/v1/route",
        headers=auth_headers,
        json={"document_id": "doc_abc123", "query": "q"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fallback"] is True
    assert body["relevant_sections"] == []


def test_route_query_too_long_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A query exceeding 4000 chars fails schema validation with 422."""
    response = client.post(
        "/v1/route",
        headers=auth_headers,
        json={"document_id": "doc_abc123", "query": "x" * 4001},
    )
    assert response.status_code == 422


def test_route_problem_media_type_on_error(client: TestClient) -> None:
    """Errors use application/problem+json (RFC-7807)."""
    response = client.post("/v1/route", json={"document_id": "doc_abc123", "query": "q"})
    assert response.headers["content-type"].startswith("application/problem+json")
