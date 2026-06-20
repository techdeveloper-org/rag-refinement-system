"""Tests for document management + DPDP endpoints.

Covers ingestDocument, listDocuments, getDocument, getDocumentToc,
deleteDocument (202 + 503-on-DB-down per ADV-002), and exportDocumentData
(DPDP access, PII field metadata only, STORY-034). Auth and tenant IDOR guards
are asserted throughout.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import TENANT_B, make_jwt


def _tenant_b_headers() -> dict[str, str]:
    """Return bearer headers for tenant B.

    Returns:
        A headers dict carrying a valid JWT for tenant B.
    """
    return {"Authorization": f"Bearer {make_jwt(TENANT_B)}"}


def test_ingest_requires_auth(client: TestClient) -> None:
    """An unauthenticated ingest request returns 401."""
    response = client.post(
        "/v1/documents", files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")}
    )
    assert response.status_code == 401


def test_ingest_new_document_returns_201(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A first-time ingest returns 201 with a Location header and IngestResponse."""
    response = client.post(
        "/v1/documents",
        headers=auth_headers,
        files={"file": ("a.pdf", b"%PDF-1.4 body", "application/pdf")},
        data={"title": "Manual"},
    )
    assert response.status_code == 201
    assert "Location" in response.headers
    body = response.json()
    assert body["doc_id"] == "doc_new123"
    assert body["deduplicated"] is False
    assert body["ingest_status"] == "indexed"


def test_ingest_deduplicated_returns_200(
    client: TestClient, auth_headers: dict[str, str], fakes: dict[str, object]
) -> None:
    """An idempotent re-upload of identical content returns 200 (dedup)."""
    fakes["ingestor"].deduplicated = True
    response = client.post(
        "/v1/documents",
        headers=auth_headers,
        files={"file": ("a.pdf", b"%PDF-1.4 body", "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["deduplicated"] is True


def test_ingest_non_pdf_returns_415(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A non-PDF upload is rejected with 415 UNSUPPORTED_MEDIA_TYPE."""
    response = client.post(
        "/v1/documents",
        headers=auth_headers,
        files={"file": ("a.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_ingest_accepts_bare_pdf_content_type(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A bare ``application/pdf`` content type is accepted (FIX-10)."""
    response = client.post(
        "/v1/documents",
        headers=auth_headers,
        files={"file": ("a.pdf", b"%PDF-1.4 body", "application/pdf")},
    )
    assert response.status_code == 201


def test_ingest_accepts_parameterized_pdf_content_type(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A parameterized ``application/pdf; charset=utf-8`` type is accepted (FIX-10)."""
    response = client.post(
        "/v1/documents",
        headers=auth_headers,
        files={"file": ("a.pdf", b"%PDF-1.4 body", "application/pdf; charset=utf-8")},
    )
    assert response.status_code == 201


def test_ingest_missing_content_type_returns_415(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A missing/empty content type is rejected with 415 (FIX-10)."""
    response = client.post(
        "/v1/documents",
        headers=auth_headers,
        files={"file": ("a.pdf", b"%PDF-1.4 body", "")},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_ingest_invalid_residency_returns_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """An invalid residency_region is rejected with 422."""
    response = client.post(
        "/v1/documents",
        headers=auth_headers,
        files={"file": ("a.pdf", b"%PDF-1.4", "application/pdf")},
        data={"residency_region": "MARS"},
    )
    assert response.status_code == 422


def test_list_documents_paginated(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Listing returns the tenant's documents with pagination metadata."""
    response = client.get("/v1/documents?page=1&page_size=20", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["page"] == 1
    assert body["pagination"]["total_count"] == 1
    assert all(doc["doc_id"] == "doc_abc123" for doc in body["data"])


def test_list_documents_is_tenant_scoped(client: TestClient) -> None:
    """Tenant B's listing never includes tenant A's document (IDOR)."""
    response = client.get("/v1/documents", headers=_tenant_b_headers())
    assert response.status_code == 200
    doc_ids = {doc["doc_id"] for doc in response.json()["data"]}
    assert "doc_abc123" not in doc_ids
    assert doc_ids == {"doc_other9"}


def test_get_document_returns_metadata(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Getting an owned document returns its metadata."""
    response = client.get("/v1/documents/doc_abc123", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["doc_id"] == "doc_abc123"


def test_get_document_cross_tenant_returns_404(client: TestClient) -> None:
    """Getting another tenant's document is blocked (IDOR -> 404)."""
    response = client.get("/v1/documents/doc_abc123", headers=_tenant_b_headers())
    assert response.status_code == 404


def test_get_toc_returns_entries(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The TOC endpoint returns the document's sections."""
    response = client.get("/v1/documents/doc_abc123/toc", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == "doc_abc123"
    assert body["fallback_only"] is False
    assert body["toc"][0]["section_id"] == "sec_warranty"


def test_get_toc_cross_tenant_returns_404(client: TestClient) -> None:
    """Another tenant cannot read the TOC (IDOR -> 404)."""
    response = client.get("/v1/documents/doc_abc123/toc", headers=_tenant_b_headers())
    assert response.status_code == 404


def test_delete_document_returns_202(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Erasure of an owned document returns a 202 ErasureReceipt."""
    response = client.delete("/v1/documents/doc_abc123", headers=auth_headers)
    assert response.status_code == 202
    body = response.json()
    assert body["doc_id"] == "doc_abc123"
    assert body["erased"] is True


def test_delete_document_idempotent_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """A second delete of an already-erased document returns 404."""
    client.delete("/v1/documents/doc_abc123", headers=auth_headers)
    second = client.delete("/v1/documents/doc_abc123", headers=auth_headers)
    assert second.status_code == 404


def test_delete_document_db_down_returns_503(
    client: TestClient, auth_headers: dict[str, str], fakes: dict[str, object]
) -> None:
    """Erasure returns a retryable 503 when Postgres is down (ADV-002)."""
    fakes["store"].fail_tombstone = True
    response = client.delete("/v1/documents/doc_abc123", headers=auth_headers)
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "Retry-After" in response.headers


def test_delete_cross_tenant_returns_404(client: TestClient) -> None:
    """Erasing another tenant's document is blocked (IDOR -> 404)."""
    response = client.delete("/v1/documents/doc_abc123", headers=_tenant_b_headers())
    assert response.status_code == 404


def test_export_data_returns_pii_field_metadata_only(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The DPDP access export lists x-pii field names, not PII values."""
    response = client.get("/v1/documents/doc_abc123/data", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["doc_id"] == "doc_abc123"

    field_names = {entry["field"] for entry in body["pii_fields"]}
    assert "title" in field_names
    assert "summary" in field_names

    for entry in body["pii_fields"]:
        assert entry["field"] in {"title", "summary"}
        assert "Warranty" not in entry["field"]


def test_export_data_scoped_to_tenant(client: TestClient) -> None:
    """Another tenant cannot export tenant A's document data (IDOR -> 404)."""
    response = client.get("/v1/documents/doc_abc123/data", headers=_tenant_b_headers())
    assert response.status_code == 404


def test_export_data_shape_matches_openapi(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """The export body carries the DataAccessExport required fields."""
    response = client.get("/v1/documents/doc_abc123/data", headers=auth_headers)
    body = response.json()
    for required in ("doc_id", "generated_at", "document", "sections", "pii_fields"):
        assert required in body
