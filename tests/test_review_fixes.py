"""Regression tests for the code-review remediation fixes.

Covers the endpoint-level fixes that lock the reviewed behavior:
- FIX-5: an upload with a missing Content-Type is rejected with 415, and an
  oversize body is rejected with 413 (no unbounded read into memory).
- FIX-6: default-read and sensitive-operation rate limits use separate buckets,
  so exhausting one does not block the other.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.security.rate_limit import get_rate_limiter
from backend.app.settings import get_settings


def test_missing_content_type_returns_415(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A multipart file part with no Content-Type header is rejected with 415."""
    boundary = "boundarytest123"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="a.pdf"\r\n'
        "\r\n"
        "%PDF-1.4 body\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    headers = {
        **auth_headers,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    response = client.post("/v1/documents", headers=headers, content=body)
    assert response.status_code == 415


def test_oversize_upload_returns_413(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An upload whose body exceeds max_upload_bytes is rejected with 413."""
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "16")
    get_settings.cache_clear()
    oversize = b"%PDF-1.4 " + b"x" * 64
    response = client.post(
        "/v1/documents",
        headers=auth_headers,
        files={"file": ("a.pdf", oversize, "application/pdf")},
    )
    assert response.status_code == 413


def test_default_and_sensitive_rate_limits_are_separate_buckets(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exhausting the default read budget does not block a sensitive operation."""
    monkeypatch.setenv("RATE_LIMIT_DEFAULT_PER_MINUTE", "1")
    monkeypatch.setenv("RATE_LIMIT_SENSITIVE_PER_MINUTE", "1")
    get_settings.cache_clear()
    get_rate_limiter().reset()

    assert client.get("/v1/documents", headers=auth_headers).status_code == 200
    assert client.get("/v1/documents", headers=auth_headers).status_code == 429

    erasure = client.delete("/v1/documents/doc_abc123", headers=auth_headers)
    assert erasure.status_code == 202
