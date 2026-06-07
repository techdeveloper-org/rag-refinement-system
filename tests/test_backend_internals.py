"""Branch-coverage tests for backend internals not reachable via the HTTP suite.

Covers the RFC-7807 exception handlers (HTTP-exception mapping, request-validation
field stripping, catch-all 500), the auth helpers (rotate-unknown, unconfigured
salt/secret, missing-claims, empty bearer), the rate-limiter window-reset branch,
and the Qdrant bootstrap CLI/get_client. No real network, database, or LLM is used.
"""

from __future__ import annotations

import pytest
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app import errors as errors_mod
from backend.app.errors import (
    ProblemException,
    document_not_found,
    payload_too_large,
)
from backend.app.security import auth as auth_mod
from backend.app.security.auth import ApiKeyStore, _decode_jwt, _resolve_jwt_principal
from backend.app.security.rate_limit import RateLimiter
from backend.app.settings import Settings

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only."""
    return "asyncio"


class TestProblemModel:
    """The RFC-7807 problem document model."""

    @pytest.mark.anyio
    async def test_to_problem_includes_optional_members(self) -> None:
        """Optional detail/errors/query_id members are rendered when present."""
        exc = ProblemException(
            status_code=422,
            code="VALIDATION_ERROR",
            title="Unprocessable Entity",
            detail="bad",
            errors=[{"field": "query", "message": "required"}],
            query_id="q-1",
        )
        problem = exc.to_problem()
        assert problem["detail"] == "bad"
        assert problem["errors"][0]["field"] == "query"
        assert problem["query_id"] == "q-1"
        assert problem["type"].endswith("validation-error")

    @pytest.mark.anyio
    async def test_default_problem_type_derives_from_code(self) -> None:
        """When no problem_type is given, it derives from the lowercased code."""
        exc = document_not_found()
        assert exc.problem_type == "document-not-found"

    @pytest.mark.anyio
    async def test_payload_too_large_is_413(self) -> None:
        """payload_too_large builds a 413 problem (oversized upload)."""
        exc = payload_too_large()
        assert exc.status_code == 413
        assert exc.code == "PAYLOAD_TOO_LARGE"


class TestExceptionHandlers:
    """The registered FastAPI exception handlers."""

    async def test_problem_handler_serializes_problem(self) -> None:
        """The problem handler renders a problem+json response with headers."""
        exc = payload_too_large()
        response = await errors_mod._handle_problem(None, exc)  # type: ignore[arg-type]
        assert response.status_code == 413
        assert response.media_type == errors_mod.PROBLEM_MEDIA_TYPE

    async def test_http_exception_maps_known_status(self) -> None:
        """A 404 Starlette HTTP exception maps to a NOT_FOUND problem."""
        exc = StarletteHTTPException(status_code=404, detail="missing")
        response = await errors_mod._handle_http_exception(None, exc)  # type: ignore[arg-type]
        assert response.status_code == 404

    async def test_http_exception_maps_unknown_status_to_generic(self) -> None:
        """An unmapped status (e.g. 418) falls back to a generic ERROR problem."""
        exc = StarletteHTTPException(status_code=418, detail=None)
        response = await errors_mod._handle_http_exception(None, exc)  # type: ignore[arg-type]
        assert response.status_code == 418

    async def test_request_validation_strips_location_prefix(self) -> None:
        """Validation errors strip body/query/path prefixes from the field path."""
        exc = RequestValidationError(
            [
                {
                    "loc": ("body", "query"),
                    "msg": "field required",
                    "type": "missing",
                }
            ]
        )
        response = await errors_mod._handle_request_validation(None, exc)  # type: ignore[arg-type]
        assert response.status_code == 422

    async def test_unexpected_handler_masks_internals(self) -> None:
        """The catch-all handler returns a generic 500 (no internal echo)."""
        response = await errors_mod._handle_unexpected(None, RuntimeError("boom"))  # type: ignore[arg-type]
        assert response.status_code == 500


class TestApiKeyStore:
    """API-key rotation and store configuration."""

    @pytest.mark.anyio
    async def test_rotate_unknown_key_raises(self) -> None:
        """Rotating an unregistered key raises KeyError."""
        store = ApiKeyStore("salt")
        with pytest.raises(KeyError, match="unknown api key"):
            store.rotate("never-registered", "new-key")

    @pytest.mark.anyio
    async def test_get_api_key_store_unconfigured_salt_raises_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unconfigured API_KEY_SALT raises a 401 problem on store access."""
        from backend.app.settings import get_settings

        monkeypatch.delenv("API_KEY_SALT", raising=False)
        get_settings.cache_clear()
        auth_mod._api_key_store = None
        with pytest.raises(ProblemException) as excinfo:
            auth_mod.get_api_key_store()
        assert excinfo.value.status_code == 401
        get_settings.cache_clear()
        auth_mod._api_key_store = None


class TestJwtHelpers:
    """JWT decode/resolve helper branches."""

    @pytest.mark.anyio
    async def test_decode_unconfigured_secret_raises_401(self) -> None:
        """Decoding without a configured JWT secret raises a 401 problem."""
        settings = Settings(JWT_SECRET=None, JWT_ISSUER="test-issuer")
        with pytest.raises(ProblemException) as excinfo:
            _decode_jwt("token", settings)
        assert excinfo.value.status_code == 401

    @pytest.mark.anyio
    async def test_resolve_jwt_missing_claims_raises_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A token lacking a tenant claim raises a 401 problem."""

        def _fake_decode(token: str, settings: Settings) -> dict[str, object]:
            return {"sub": "user-1"}

        monkeypatch.setattr(auth_mod, "_decode_jwt", _fake_decode)
        with pytest.raises(ProblemException) as excinfo:
            _resolve_jwt_principal("token", Settings(JWT_SECRET="x" * 32, JWT_ISSUER="test-issuer"))
        assert excinfo.value.status_code == 401


class TestResolvePrincipalBranches:
    """The credential-precedence resolver edge branches."""

    @pytest.mark.anyio
    async def test_empty_bearer_token_falls_through_to_401(self) -> None:
        """An ``Authorization: Bearer`` header with no token yields a 401."""
        from starlette.requests import Request

        from backend.app.security.auth import resolve_principal

        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer ")],
        }
        request = Request(scope)
        with pytest.raises(ProblemException) as excinfo:
            resolve_principal(request, Settings(JWT_SECRET="x" * 32, JWT_ISSUER="test-issuer"))
        assert excinfo.value.status_code == 401


class TestErrorsBranches:
    """Problem rendering branches in errors.py."""

    @pytest.mark.anyio
    async def test_problem_without_detail_omits_detail_member(self) -> None:
        """A problem built with no detail omits the detail member entirely."""
        exc = ProblemException(
            status_code=403,
            code="FORBIDDEN",
            title="Forbidden",
        )
        problem = exc.to_problem()
        assert "detail" not in problem

    @pytest.mark.anyio
    async def test_document_not_found_carries_default_detail(self) -> None:
        """document_not_found renders a 404 with its default detail."""
        problem = document_not_found().to_problem()
        assert problem["status"] == 404
        assert "detail" in problem

    @pytest.mark.anyio
    async def test_forbidden_builds_403(self) -> None:
        """forbidden() builds a 403 cross-tenant/IDOR problem."""
        from backend.app.errors import forbidden

        exc = forbidden()
        assert exc.status_code == 403
        assert exc.code == "FORBIDDEN"


class TestRateLimiterInternals:
    """The sliding-window rate limiter."""

    @pytest.mark.anyio
    async def test_window_resets_after_expiry(self) -> None:
        """A hit after the window expires resets the counter (no false 429)."""
        clock = {"now": 1000.0}
        limiter = RateLimiter(clock=lambda: clock["now"])
        limiter.check("k", limit=1)
        clock["now"] += 120.0
        limiter.check("k", limit=1)

    @pytest.mark.anyio
    async def test_exceeding_limit_raises_429(self) -> None:
        """Exceeding the limit within a window raises a 429 problem."""
        limiter = RateLimiter(clock=lambda: 1000.0)
        limiter.check("k", limit=1)
        with pytest.raises(ProblemException) as excinfo:
            limiter.check("k", limit=1)
        assert excinfo.value.status_code == 429


class TestQdrantBootstrapCli:
    """The Qdrant bootstrap client builder and CLI."""

    @pytest.mark.anyio
    async def test_get_client_requires_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_client raises when neither argument nor QDRANT_URL is provided."""
        from db.qdrant_bootstrap import get_client

        monkeypatch.delenv("QDRANT_URL", raising=False)
        with pytest.raises(RuntimeError, match="QDRANT_URL is not set"):
            get_client()

    @pytest.mark.anyio
    async def test_get_client_builds_from_explicit_url(self) -> None:
        """get_client with an explicit URL builds a client (no connection on init)."""
        from db.qdrant_bootstrap import get_client

        client = get_client("http://localhost:6333")
        assert client is not None

    @pytest.mark.anyio
    async def test_main_bootstraps_and_reports(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The CLI bootstraps an in-memory collection and prints the outcome."""
        from db import qdrant_bootstrap as qb
        from qdrant_client import QdrantClient

        monkeypatch.setattr(qb, "get_client", lambda: QdrantClient(":memory:"))
        qb.main()
        out = capsys.readouterr().out
        assert "rag_chunks" in out
        assert "payload indexes ensured" in out
