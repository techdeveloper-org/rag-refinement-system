"""Tests for POST /v1/answer (answerQuery) - SSE streaming.

Covers: auth required, tenant IDOR guard (pre-stream 404), the SSE contract
(token events then a final event with {answer, citations[], routing{}}), and
the mid-stream error event after the 200 (AC-ADV-002).
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from tests.conftest import TENANT_B, make_jwt


def _parse_sse(text: str) -> list[tuple[str, dict[str, object]]]:
    """Parse a raw SSE body into a list of (event, data) tuples.

    Args:
        text: The raw text/event-stream body.

    Returns:
        Ordered (event-name, parsed-data) pairs.
    """
    events: list[tuple[str, dict[str, object]]] = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_name = ""
        data_line = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data_line = line[len("data: ") :]
        events.append((event_name, json.loads(data_line) if data_line else {}))
    return events


def test_answer_requires_auth(client: TestClient) -> None:
    """An unauthenticated /v1/answer request returns 401 before streaming."""
    response = client.post("/v1/answer", json={"document_id": "doc_abc123", "query": "q"})
    assert response.status_code == 401


def test_answer_cross_tenant_returns_404(client: TestClient) -> None:
    """Answering over another tenant's document is blocked (IDOR -> 404)."""
    headers = {"Authorization": f"Bearer {make_jwt(TENANT_B)}"}
    response = client.post(
        "/v1/answer", headers=headers, json={"document_id": "doc_abc123", "query": "q"}
    )
    assert response.status_code == 404


def test_answer_streams_tokens_then_final(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The stream emits token events then a terminal final event."""
    response = client.post(
        "/v1/answer",
        headers=auth_headers,
        json={"document_id": "doc_abc123", "query": "warranty?"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert names[:2] == ["token", "token"]
    assert names[-1] == "final"

    final_data = events[-1][1]
    assert final_data["answer"] == "Hello world"
    assert final_data["citations"][0]["section_title"] == "Warranty"
    assert final_data["routing"]["sections"] == ["sec_warranty"]
    assert final_data["routing"]["fallback"] is False


def test_answer_midstream_failure_emits_error_event(
    client: TestClient, auth_headers: dict[str, str], fakes: dict[str, object]
) -> None:
    """A mid-stream failure is delivered as an SSE error event (AC-ADV-002)."""
    fakes["llm"].fail_midstream = True
    response = client.post(
        "/v1/answer",
        headers=auth_headers,
        json={"document_id": "doc_abc123", "query": "q"},
    )
    assert response.status_code == 200

    events = _parse_sse(response.text)
    names = [name for name, _ in events]
    assert "error" in names
    assert names[-1] == "error"

    error_data = events[-1][1]
    assert error_data["code"] == "INTERNAL_ERROR"
    assert error_data["query_id"].startswith("qry_")


def test_answer_invokes_generation(
    client: TestClient, auth_headers: dict[str, str], fakes: dict[str, object]
) -> None:
    """The answer path does invoke generation (contrast with /v1/route)."""
    client.post(
        "/v1/answer",
        headers=auth_headers,
        json={"document_id": "doc_abc123", "query": "q"},
    )
    assert fakes["llm"].stream_answer_calls == 1


def test_answer_rejects_document_ids_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """AnswerRequest is single-document; document_ids is an unknown field (422)."""
    response = client.post(
        "/v1/answer",
        headers=auth_headers,
        json={"document_ids": ["doc_abc123"], "query": "q"},
    )
    assert response.status_code == 422
