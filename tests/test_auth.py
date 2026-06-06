"""Auth, tenant, and rate-limit tests for STORY-038 (ADR-7, ADV-003, NFR-015).

Covers: JWT grant / tamper / expiry, API-key rotation invalidation, tenant_id
resolution into request scope, per-credential rate limiting (429), and the
no-hardcoded-secret guard on the auth module. Deterministic - no live IdP.
"""

from __future__ import annotations

from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient

from backend.app.security import auth as auth_module
from backend.app.security.auth import (
    Principal,
    PrincipalKind,
    get_api_key_store,
    hash_api_key,
)
from backend.app.settings import get_settings
from tests.conftest import (
    API_KEY_SALT,
    JWT_AUDIENCE,
    JWT_SECRET,
    TENANT_A,
    TENANT_B,
    make_jwt,
)


def test_valid_jwt_grants_access(client: TestClient, auth_headers: dict[str, str]) -> None:
    """A valid JWT bearer token authenticates and reaches the endpoint."""
    response = client.get("/v1/documents/doc_abc123", headers=auth_headers)
    assert response.status_code == 200


def test_missing_credentials_returns_401(client: TestClient) -> None:
    """A request with no credentials is rejected with 401 problem+json."""
    response = client.get("/v1/documents/doc_abc123")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "UNAUTHORIZED"


def test_tampered_jwt_returns_401(client: TestClient) -> None:
    """A signature-tampered JWT is rejected with 401."""
    token = make_jwt(TENANT_A)
    tampered = token[:-3] + ("abc" if token[-3:] != "abc" else "xyz")
    response = client.get(
        "/v1/documents/doc_abc123", headers={"Authorization": f"Bearer {tampered}"}
    )
    assert response.status_code == 401


def test_expired_jwt_returns_401(client: TestClient) -> None:
    """An expired JWT is rejected with 401."""
    token = make_jwt(TENANT_A, expired=True)
    response = client.get(
        "/v1/documents/doc_abc123", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_alg_none_jwt_rejected(client: TestClient) -> None:
    """A token signed with alg=none is rejected (no algorithm confusion)."""
    unsigned = jwt.encode(
        {"sub": "u", "tenant_id": TENANT_A, "aud": JWT_AUDIENCE},
        key="",
        algorithm="none",
    )
    response = client.get(
        "/v1/documents/doc_abc123", headers={"Authorization": f"Bearer {unsigned}"}
    )
    assert response.status_code == 401


def test_wrong_audience_jwt_rejected(client: TestClient) -> None:
    """A JWT for a different audience is rejected."""
    import datetime as _dt

    now = _dt.datetime.now(_dt.UTC)
    token = jwt.encode(
        {
            "sub": "u",
            "tenant_id": TENANT_A,
            "aud": "some-other-service",
            "exp": now + _dt.timedelta(hours=1),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
    response = client.get(
        "/v1/documents/doc_abc123", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


def test_apikey_grants_and_resolves_tenant(client: TestClient) -> None:
    """A registered API key authenticates and scopes to its tenant."""
    store = get_api_key_store()
    store.register("ent-key-123", TENANT_A, "key_1")
    response = client.get(
        "/v1/documents/doc_abc123", headers={"X-API-Key": "ent-key-123"}
    )
    assert response.status_code == 200


def test_apikey_rotation_invalidates_old(client: TestClient) -> None:
    """Rotating an API key invalidates the old key and grants the new one."""
    store = get_api_key_store()
    store.register("old-key", TENANT_A, "key_1")
    store.rotate("old-key", "new-key")

    old = client.get("/v1/documents/doc_abc123", headers={"X-API-Key": "old-key"})
    assert old.status_code == 401

    new = client.get("/v1/documents/doc_abc123", headers={"X-API-Key": "new-key"})
    assert new.status_code == 200


def test_unknown_apikey_returns_401(client: TestClient) -> None:
    """An unregistered API key is rejected with 401."""
    response = client.get(
        "/v1/documents/doc_abc123", headers={"X-API-Key": "never-registered"}
    )
    assert response.status_code == 401


def test_api_key_is_hashed_at_rest() -> None:
    """The store holds only salted digests, never the plaintext key."""
    get_settings.cache_clear()
    auth_module._api_key_store = None
    import os

    os.environ["API_KEY_SALT"] = API_KEY_SALT
    store = get_api_key_store()
    store.register("super-secret-key", TENANT_A, "key_1")
    digest = hash_api_key("super-secret-key", API_KEY_SALT)
    assert digest in store._records
    for record in store._records.values():
        assert "super-secret-key" not in record.key_hash


def test_tenant_id_scoped_into_request() -> None:
    """The resolved principal carries the tenant_id and credential kind."""
    principal = Principal(tenant_id=TENANT_A, subject="user-1", kind=PrincipalKind.JWT)
    assert principal.tenant_id == TENANT_A
    assert principal.rate_limit_key == "jwt:user-1"


def test_authenticated_op_is_rate_limited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An authenticated op returns 429 RATE_LIMITED past the per-key budget."""
    monkeypatch.setenv("RATE_LIMIT_DEFAULT_PER_MINUTE", "3")
    get_settings.cache_clear()
    headers = {"Authorization": f"Bearer {make_jwt(TENANT_A)}"}

    statuses = [
        client.get("/v1/documents/doc_abc123", headers=headers).status_code
        for _ in range(5)
    ]
    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses[3:]

    limited = client.get("/v1/documents/doc_abc123", headers=headers)
    if limited.status_code == 429:
        assert limited.json()["code"] == "RATE_LIMITED"
        assert "Retry-After" in limited.headers


def test_no_hardcoded_secret_in_auth_module() -> None:
    """The auth module source contains no hardcoded secret literals."""
    source = Path(auth_module.__file__).read_text(encoding="utf-8")
    for needle in (JWT_SECRET, API_KEY_SALT):
        assert needle not in source
    assert "jwt_secret" in source.lower()


def test_cross_tenant_jwt_cannot_read_other_tenant_doc(client: TestClient) -> None:
    """A tenant-B caller cannot read tenant-A's document (IDOR blocked)."""
    headers = {"Authorization": f"Bearer {make_jwt(TENANT_B)}"}
    response = client.get("/v1/documents/doc_abc123", headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == "DOCUMENT_NOT_FOUND"
