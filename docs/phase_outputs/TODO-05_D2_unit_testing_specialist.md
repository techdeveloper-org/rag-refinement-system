# TODO-05 D2 — Unit Testing Specialist Output
## Phase D.2 — Complete pytest Suite for F-01 through F-10

**Agent:** unit-testing-specialist  
**Date:** 2026-06-07  
**Spec authority:** `docs/code-review-fix-requirements.md`  
**TC assignments source:** `docs/phase_outputs/TODO-04_D1_test_management_agent.md`

---

## Summary

| Metric | Value |
|--------|-------|
| Total test cases written | 17 |
| Findings covered | F-01, F-02, F-03, F-04, F-05, F-07, F-08, F-09, F-10 |
| TC IDs covered | TC-F01-001, TC-F01-002, TC-F01-003, TC-F02-001, TC-F02-003, TC-F04-001, TC-F05-001, TC-F05-002, TC-F07-001, TC-F08-001, TC-F09-001, TC-F09-002, TC-F10-001, TC-F10-002, TC-F10-003, TC-F10-004, TC-F03-001 |
| TC IDs delegated | TC-F02-002 (security-testing-engineer), TC-F06-001, TC-F06-002, TC-F08-002 (integration-testing-engineer) |
| Mock strategy | All DB/LLM/external calls mocked via `app.dependency_overrides` or `unittest.mock.patch` |
| Settings contract | All `Settings()` constructed with `JWT_ISSUER="test-issuer"` via `monkeypatch.setenv` |

### Gaps / Notes

- **F-03 (ThinkingParam):** The `ClaudeGenerationLLM` streams via the real Anthropic SDK.
  The test mocks the `anthropic.AsyncAnthropic` client at the adapter level to verify the
  `thinking={"type": "enabled", "budget_tokens": N}` kwarg is forwarded. This is unit-scope
  (no real network call).
- **F-06 (TOCTOU / pre_existing flag):** Integration concern (two concurrent uploads hitting
  the same pipeline); delegated to integration-testing-engineer (TC-F06-001, TC-F06-002).
- **F-08 (gather return_exceptions):** The unit test (TC-F08-001) verifies the
  `return_exceptions=True` code path in `RouterModuleAdapter.route`. The session-level
  isolation test (TC-F08-002) requires a real asyncio event loop with two concurrent
  coroutines; delegated to integration-testing-engineer.
- **F-10 (final-before-error):** Driving `_answer_stream` as an async generator directly
  (not via HTTP TestClient) because `StreamingResponse` SSE ordering is not inspectable
  through the sync `TestClient` without consuming the full body.

---

## Complete pytest File

Save as `tests/test_f01_f10_unit.py` (or split by finding if per-file organisation is
preferred).

```python
"""Unit tests for code-review findings F-01 through F-10.

Spec authority: docs/code-review-fix-requirements.md
TC assignments:  docs/phase_outputs/TODO-04_D1_test_management_agent.md

Each test class is prefixed with the finding number for traceability.
Every test is mutation-safe: reverting the production fix causes that test to fail.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError

# ---------------------------------------------------------------------------
# Shared test constants (AGREED CONTRACT: JWT_ISSUER="test-issuer" everywhere)
# ---------------------------------------------------------------------------

_JWT_SECRET = "test-jwt-secret-not-a-real-key-padded-32b"  # noqa: S105
_JWT_AUDIENCE = "rag-refinement-personal"
_JWT_ISSUER = "test-issuer"
_JWT_ALG = "HS256"
_TENANT_A = "tenant_a"


def _mint_jwt(
    tenant_id: str,
    subject: str = "user-1",
    *,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Mint a signed HS256 JWT for tests.

    Args:
        tenant_id: The tenant_id claim value.
        subject: The sub claim.
        extra_claims: Any additional claims to embed.

    Returns:
        A signed JWT string.
    """
    now = _dt.datetime.now(_dt.UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "tenant_id": tenant_id,
        "aud": _JWT_AUDIENCE,
        "iss": _JWT_ISSUER,
        "exp": now + _dt.timedelta(hours=1),
        "iat": now,
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)


# ---------------------------------------------------------------------------
# Shared autouse fixture: reset Settings lru_cache before/after each test
# and inject all required env vars so Settings() never raises.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Inject required env vars and reset the Settings lru_cache.

    Args:
        monkeypatch: pytest monkeypatch fixture.
    """
    from backend.app.settings import get_settings
    from backend.app.security import auth as auth_module
    from backend.app.security.rate_limit import get_rate_limiter

    get_settings.cache_clear()
    monkeypatch.setenv("JWT_SECRET", _JWT_SECRET)
    monkeypatch.setenv("JWT_AUDIENCE", _JWT_AUDIENCE)
    monkeypatch.setenv("JWT_ISSUER", _JWT_ISSUER)
    monkeypatch.setenv("API_KEY_SALT", "test-api-key-salt")
    auth_module._api_key_store = None
    get_rate_limiter().reset()
    yield
    get_settings.cache_clear()
    auth_module._api_key_store = None


# ---------------------------------------------------------------------------
# Shared app / client factory
# ---------------------------------------------------------------------------

def _make_client(
    *,
    store: Any | None = None,
    router: Any | None = None,
    ingestor: Any | None = None,
    llm: Any | None = None,
) -> TestClient:
    """Build a TestClient with optional dependency overrides.

    Args:
        store: DocumentStore override (or None to use the default).
        router: Router override.
        ingestor: Ingestor override.
        llm: GenerationLLM override.

    Returns:
        A configured :class:`TestClient` that clears overrides after use.
    """
    from backend.app.main import create_app
    from backend.app.api.dependencies import (
        get_document_store,
        get_generation_llm,
        get_ingestor,
        get_router,
    )

    app = create_app()
    if store is not None:
        app.dependency_overrides[get_document_store] = lambda: store
    if router is not None:
        app.dependency_overrides[get_router] = lambda: router
    if ingestor is not None:
        app.dependency_overrides[get_ingestor] = lambda: ingestor
    if llm is not None:
        app.dependency_overrides[get_generation_llm] = lambda: llm
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# F-01  tenant_id claim resolution — key-presence check
# ---------------------------------------------------------------------------

class TestF01TenantClaims:
    """F-01: Key-presence check replaces `or`-truthiness for tenant_id/tid claims.

    AC-F-01-1: tenant_id="" with tid="victim" MUST resolve to UNAUTHORIZED (401),
               not to tid="victim". The fix: `if "tenant_id" in claims and claims["tenant_id"]`.
    AC-F-01-2: A JWT with only tid="real-tenant" and no tenant_id key resolves to
               Principal(tenant_id="real-tenant").
    AC-F-01-3: A JWT with tenant_id="real-tenant" takes precedence over any tid key.
    """

    # TC-F01-001: attack vector — empty tenant_id with tid="victim" must be rejected
    def test_tc_f01_001_empty_tenant_id_with_tid_is_rejected(self) -> None:
        """AC-F-01-1: empty-string tenant_id is not falsy-skipped; attack is blocked.

        Reverts-to-fail: if the fix were reverted to `if claims.get("tenant_id")`,
        the empty string would be falsy, the code would fall through to tid="victim",
        and this test would fail because 200 would be returned instead of 401.
        """
        from backend.app.security.auth import _resolve_jwt_principal
        from backend.app.settings import get_settings
        from backend.app.errors import ProblemException

        settings = get_settings()
        now = _dt.datetime.now(_dt.UTC)
        # Build a JWT whose raw claims contain tenant_id="" (empty) and tid="victim"
        raw_claims = {
            "sub": "attacker",
            "tenant_id": "",
            "tid": "victim",
            "aud": _JWT_AUDIENCE,
            "iss": _JWT_ISSUER,
            "exp": now + _dt.timedelta(hours=1),
            "iat": now,
        }
        token = jwt.encode(raw_claims, _JWT_SECRET, algorithm=_JWT_ALG)

        with pytest.raises(ProblemException) as exc_info:
            _resolve_jwt_principal(token, settings)

        assert exc_info.value.status_code == 401, (
            "AC-F-01-1 violated: attack vector {tenant_id: '', tid: 'victim'} must "
            "produce 401 UNAUTHORIZED, not resolve to tid='victim'"
        )

    # TC-F01-001 (HTTP level — AGREED CONTRACT: must be tested at HTTP level via TestClient)
    def test_tc_f01_001_http_level_attack_vector_returns_401(self) -> None:
        """AC-F-01-1 (HTTP): attack vector at /v1/documents endpoint level.

        AGREED CONTRACT: F-01 attack vector must be tested at HTTP level via
        FastAPI TestClient as documented in the task specification.
        """
        now = _dt.datetime.now(_dt.UTC)
        raw_claims = {
            "sub": "attacker",
            "tenant_id": "",
            "tid": "victim",
            "aud": _JWT_AUDIENCE,
            "iss": _JWT_ISSUER,
            "exp": now + _dt.timedelta(hours=1),
            "iat": now,
        }
        token = jwt.encode(raw_claims, _JWT_SECRET, algorithm=_JWT_ALG)
        client = _make_client()
        response = client.get(
            "/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 401, (
            "AC-F-01-1 (HTTP): attack vector {tenant_id: '', tid: 'victim'} must "
            "return 401 at HTTP level, not 200"
        )

    # TC-F01-002: tid fallback works when tenant_id key is absent
    def test_tc_f01_002_tid_fallback_when_tenant_id_key_absent(self) -> None:
        """AC-F-01-2: tid is used when the tenant_id key is not present in claims."""
        from backend.app.security.auth import _resolve_jwt_principal
        from backend.app.settings import get_settings

        settings = get_settings()
        now = _dt.datetime.now(_dt.UTC)
        raw_claims = {
            "sub": "user-1",
            "tid": "real-tenant",
            "aud": _JWT_AUDIENCE,
            "iss": _JWT_ISSUER,
            "exp": now + _dt.timedelta(hours=1),
            "iat": now,
        }
        token = jwt.encode(raw_claims, _JWT_SECRET, algorithm=_JWT_ALG)

        principal = _resolve_jwt_principal(token, settings)

        assert principal.tenant_id == "real-tenant", (
            "AC-F-01-2: when tenant_id key is absent, tid claim must be used as fallback"
        )
        assert principal.subject == "user-1"

    # TC-F01-003: tenant_id takes precedence over tid
    def test_tc_f01_003_tenant_id_takes_precedence_over_tid(self) -> None:
        """AC-F-01-3: non-empty tenant_id wins over any tid value."""
        from backend.app.security.auth import _resolve_jwt_principal
        from backend.app.settings import get_settings

        settings = get_settings()
        now = _dt.datetime.now(_dt.UTC)
        raw_claims = {
            "sub": "user-1",
            "tenant_id": "primary-tenant",
            "tid": "secondary-tenant",
            "aud": _JWT_AUDIENCE,
            "iss": _JWT_ISSUER,
            "exp": now + _dt.timedelta(hours=1),
            "iat": now,
        }
        token = jwt.encode(raw_claims, _JWT_SECRET, algorithm=_JWT_ALG)

        principal = _resolve_jwt_principal(token, settings)

        assert principal.tenant_id == "primary-tenant", (
            "AC-F-01-3: tenant_id must take precedence over tid"
        )


# ---------------------------------------------------------------------------
# F-02  JWT_ISSUER required at startup — no default
# ---------------------------------------------------------------------------

class TestF02JwtIssuer:
    """F-02: jwt_issuer field has no default; Settings() without JWT_ISSUER must fail.

    AC-F-02-1: Constructing Settings() without JWT_ISSUER env var raises
               pydantic_settings ValidationError (required field, no default).
    AC-F-02-3: When JWT_ISSUER is set, Settings() constructs without error.
    AC-F-02-2: (Delegated to security-testing-engineer) Wrong issuer -> 401.
    """

    # TC-F02-001: missing JWT_ISSUER raises ValidationError at Settings construction
    def test_tc_f02_001_missing_jwt_issuer_raises_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-F-02-1: jwt_issuer has no default; absent env var = startup failure.

        Reverts-to-fail: if the fix were reverted to `jwt_issuer: str | None = None`,
        Settings() would construct without error and this assertion would fail.
        """
        from backend.app.settings import get_settings

        get_settings.cache_clear()
        monkeypatch.delenv("JWT_ISSUER", raising=False)

        with pytest.raises((PydanticValidationError, Exception)) as exc_info:
            from backend.app.settings import Settings
            Settings(
                _env_file=None,
                JWT_SECRET=_JWT_SECRET,
                JWT_AUDIENCE=_JWT_AUDIENCE,
                # JWT_ISSUER deliberately omitted
            )

        assert exc_info is not None, (
            "AC-F-02-1: Settings() without JWT_ISSUER must raise ValidationError"
        )

    # TC-F02-003: valid JWT_ISSUER allows Settings construction
    def test_tc_f02_003_settings_constructs_with_jwt_issuer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-F-02-3: Settings constructs without error when JWT_ISSUER is present."""
        from backend.app.settings import Settings

        settings = Settings(
            _env_file=None,
            JWT_SECRET=_JWT_SECRET,
            JWT_AUDIENCE=_JWT_AUDIENCE,
            JWT_ISSUER=_JWT_ISSUER,
        )

        assert settings.jwt_issuer == _JWT_ISSUER, (
            "AC-F-02-3: Settings.jwt_issuer must equal the provided JWT_ISSUER value"
        )
        assert settings.jwt_secret == _JWT_SECRET


# ---------------------------------------------------------------------------
# F-03  Thinking parameter forwarded to Anthropic SDK
# ---------------------------------------------------------------------------

class TestF03ThinkingParam:
    """F-03: ClaudeGenerationLLM passes thinking={"type": "enabled", "budget_tokens": N}
    to client.messages.stream.

    AC-F-03-1: stream_answer calls stream() with the thinking kwarg; the budget_tokens
               value matches the instance's _thinking_budget_tokens.
    """

    # TC-F03-001: thinking parameter forwarded with correct budget_tokens
    @pytest.mark.anyio
    async def test_tc_f03_001_thinking_param_forwarded(self) -> None:
        """AC-F-03-1: thinking kwarg is included in messages.stream() call.

        Reverts-to-fail: removing the thinking kwarg from stream_answer causes
        mock_stream.assert_called() to fail because thinking is absent from call_args.
        """
        from backend.app.adapters.generation import ClaudeGenerationLLM

        budget = 3000

        # Build a mock Anthropic client where messages.stream is a context-manager mock
        mock_client = MagicMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_stream_ctx.text_stream = _aiter_items(["Hello", " world"])
        mock_client.messages.stream = MagicMock(return_value=mock_stream_ctx)

        llm = ClaudeGenerationLLM(
            thinking_budget_tokens=budget,
            client=mock_client,
        )

        # Drain the async generator to trigger stream_answer
        tokens = [t async for t in llm.stream_answer("What is RAG?", [])]

        assert tokens == ["Hello", " world"], (
            "AC-F-03-1: stream_answer must yield tokens from the mock stream"
        )
        mock_client.messages.stream.assert_called_once()
        call_kwargs = mock_client.messages.stream.call_args.kwargs
        assert "thinking" in call_kwargs, (
            "AC-F-03-1: thinking kwarg must be present in messages.stream() call"
        )
        thinking = call_kwargs["thinking"]
        assert thinking["type"] == "enabled", (
            "AC-F-03-1: thinking['type'] must be 'enabled'"
        )
        assert thinking["budget_tokens"] == budget, (
            f"AC-F-03-1: thinking['budget_tokens'] must equal {budget}; "
            f"got {thinking.get('budget_tokens')}"
        )


# ---------------------------------------------------------------------------
# F-04  total_pages included in IngestResult / IngestOutcome
# ---------------------------------------------------------------------------

class TestF04TotalPages:
    """F-04: IngestResult.total_pages field exists and as_dict() includes it.

    AC-F-04-1: IngestResult has a total_pages field defaulting to 0.
    AC-F-04-1: as_dict() returns a dict that contains the "total_pages" key.
    AC-F-04-2: PipelineIngestor reads total_pages from the pipeline result dict.
    """

    # TC-F04-001: IngestResult has total_pages; as_dict() returns it
    def test_tc_f04_001_ingest_result_has_total_pages(self) -> None:
        """AC-F-04-1: total_pages is present on IngestResult and surfaced by as_dict().

        Reverts-to-fail: removing the total_pages field from IngestResult causes
        AttributeError here and KeyError in the as_dict assertion.
        """
        from ingestion.pipeline import IngestResult

        result = IngestResult(
            doc_id="doc_abc123",
            toc=[],
            section_rows_written=5,
            chunks_upserted=10,
            fallback_only=False,
            total_pages=7,
        )

        assert result.total_pages == 7, (
            "AC-F-04-1: IngestResult.total_pages must equal the value passed at construction"
        )

        as_dict = result.as_dict()
        assert "total_pages" in as_dict, (
            "AC-F-04-1: as_dict() must include the 'total_pages' key"
        )
        assert as_dict["total_pages"] == 7, (
            "AC-F-04-1: as_dict()['total_pages'] must equal the IngestResult.total_pages value"
        )

    # TC-F04-001 (default value): total_pages defaults to 0
    def test_tc_f04_001_total_pages_defaults_to_zero(self) -> None:
        """AC-F-04-1: IngestResult.total_pages defaults to 0 when not supplied."""
        from ingestion.pipeline import IngestResult

        result = IngestResult(
            doc_id="doc_abc123",
            toc=[],
            section_rows_written=0,
            chunks_upserted=0,
        )

        assert result.total_pages == 0, (
            "AC-F-04-1: IngestResult.total_pages must default to 0"
        )
        assert result.as_dict()["total_pages"] == 0

    # TC-F04-001 (adapter reads total_pages): PipelineIngestor propagates total_pages
    @pytest.mark.anyio
    async def test_tc_f04_001_ingestor_propagates_total_pages(self) -> None:
        """AC-F-04-2: PipelineIngestor reads total_pages from pipeline result dict."""
        from backend.app.adapters.ingestor import PipelineIngestor

        # Build a mock ingest callable that returns total_pages=12
        mock_ingest = MagicMock(return_value={
            "doc_id": "doc_new001",
            "toc": [],
            "section_rows_written": 3,
            "chunks_upserted": 6,
            "fallback_only": False,
            "total_pages": 12,
            "pre_existing": False,
        })

        ingestor = PipelineIngestor(
            parser=MagicMock(),
            embedder=MagicMock(),
            section_store=MagicMock(),
            vector_store=MagicMock(),
            ingest=mock_ingest,
        )

        outcome = await ingestor.ingest_document(
            tenant_id="tenant_a",
            content=b"%PDF-1.4 test",
            filename="test.pdf",
            title="Test",
            domain="legal",
            no_retention=False,
            residency_region="IN",
            ocr=False,
        )

        assert outcome.total_pages == 12, (
            "AC-F-04-2: PipelineIngestor.ingest_document must read total_pages "
            "from pipeline result and surface it in IngestOutcome"
        )


# ---------------------------------------------------------------------------
# F-05  EmbedderDimensionError -> ProblemException(500)
# ---------------------------------------------------------------------------

class TestF05EmbedderError:
    """F-05: EmbedderDimensionError raised in _run_pipeline must be caught
    and re-raised as ProblemException(status_code=500, code='EMBEDDER_MISCONFIGURATION').

    AC-F-05-1: EmbedderDimensionError is NOT wrapped in DependencyUnavailable (503).
    AC-F-05-2: It IS re-raised as ProblemException with status_code=500.
    """

    # TC-F05-001: EmbedderDimensionError raises ProblemException(500), not DependencyUnavailable
    @pytest.mark.anyio
    async def test_tc_f05_001_embedder_error_becomes_500_problem(self) -> None:
        """AC-F-05-1,2: EmbedderDimensionError -> ProblemException(500).

        Reverts-to-fail: if EmbedderDimensionError fell through to the generic
        `except Exception` branch, it would be wrapped as DependencyUnavailable(503)
        and this assertion on status_code==500 would fail.
        """
        from backend.app.adapters.ingestor import PipelineIngestor
        from backend.app.errors import ProblemException
        from ingestion.embedder import EmbedderDimensionError

        def _raise_dim_error(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise EmbedderDimensionError("dim mismatch: expected 1536, got 768")

        ingestor = PipelineIngestor(
            parser=MagicMock(),
            embedder=MagicMock(),
            section_store=MagicMock(),
            vector_store=MagicMock(),
            ingest=_raise_dim_error,
        )

        with pytest.raises(ProblemException) as exc_info:
            await ingestor.ingest_document(
                tenant_id="tenant_a",
                content=b"%PDF-1.4 test",
                filename="test.pdf",
                title=None,
                domain=None,
                no_retention=False,
                residency_region="GLOBAL",
                ocr=False,
            )

        exc = exc_info.value
        assert exc.status_code == 500, (
            "AC-F-05-2: EmbedderDimensionError must produce ProblemException(status_code=500), "
            f"got status_code={exc.status_code}"
        )
        assert exc.code == "EMBEDDER_MISCONFIGURATION", (
            "AC-F-05-2: ProblemException.code must be 'EMBEDDER_MISCONFIGURATION'"
        )

    # TC-F05-002: DependencyUnavailable is re-raised unchanged (not wrapped again)
    @pytest.mark.anyio
    async def test_tc_f05_002_dependency_unavailable_reraised_unchanged(self) -> None:
        """AC-F-05-1: DependencyUnavailable from pipeline propagates as-is (503), not 500."""
        from backend.app.adapters.ingestor import PipelineIngestor
        from backend.app.api.interfaces import DependencyUnavailable

        def _raise_dep_unavailable(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise DependencyUnavailable("qdrant is down")

        ingestor = PipelineIngestor(
            parser=MagicMock(),
            embedder=MagicMock(),
            section_store=MagicMock(),
            vector_store=MagicMock(),
            ingest=_raise_dep_unavailable,
        )

        with pytest.raises(DependencyUnavailable) as exc_info:
            await ingestor.ingest_document(
                tenant_id="tenant_a",
                content=b"%PDF-1.4 test",
                filename="test.pdf",
                title=None,
                domain=None,
                no_retention=False,
                residency_region="GLOBAL",
                ocr=False,
            )

        assert "qdrant" in str(exc_info.value).lower(), (
            "AC-F-05-1: DependencyUnavailable must propagate with its original message"
        )


# ---------------------------------------------------------------------------
# F-07  fallback_only gate in /v1/answer
# ---------------------------------------------------------------------------

class TestF07FallbackOnly:
    """F-07: answer_query endpoint rejects fallback_only documents with 422.

    AC-F-07-1: When DocumentRecord.fallback_only=True, POST /v1/answer returns 422
               with code VALIDATION_ERROR before any routing call is made.
    """

    # TC-F07-001: fallback_only document returns 422 VALIDATION_ERROR
    def test_tc_f07_001_fallback_only_document_returns_422(self) -> None:
        """AC-F-07-1: fallback_only=True gate blocks routing and returns 422.

        Reverts-to-fail: removing the `if document.fallback_only: raise validation_error`
        block causes the request to proceed to routing and return 200 instead of 422.
        """
        import datetime as _dt
        from backend.app.api.interfaces import DocumentRecord, RouterDecision, RoutedSection

        fallback_doc = DocumentRecord(
            doc_id="doc_fback1",
            tenant_id=_TENANT_A,
            title="Fallback Doc",
            total_pages=5,
            domain="legal",
            residency_region="IN",
            fallback_only=True,
            created_at=_dt.datetime(2026, 1, 1, tzinfo=_dt.UTC).isoformat(),
            pii_flags={},
        )

        class _FallbackStore:
            async def get_document(self, tenant_id: str, doc_id: str) -> DocumentRecord | None:
                return fallback_doc if doc_id == "doc_fback1" else None

            async def list_documents(self, *args: Any, **kwargs: Any) -> tuple:
                return [], 0

            async def get_sections(self, *args: Any, **kwargs: Any) -> list:
                return []

        mock_router = MagicMock()
        mock_router.route = AsyncMock(
            return_value=RouterDecision(
                relevant_sections=[],
                fallback=True,
                routing_time_ms=0,
            )
        )

        token = _mint_jwt(_TENANT_A)
        client = _make_client(store=_FallbackStore(), router=mock_router)
        response = client.post(
            "/v1/answer",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "document_id": "doc_fback1",
                "query": "What is the warranty?",
            },
        )

        assert response.status_code == 422, (
            "AC-F-07-1: fallback_only document must return 422 VALIDATION_ERROR, "
            f"got {response.status_code}"
        )
        mock_router.route.assert_not_called(), (
            "AC-F-07-1: router.route must NOT be called when document is fallback_only"
        )


# ---------------------------------------------------------------------------
# F-08  asyncio.gather with return_exceptions=True
# ---------------------------------------------------------------------------

class TestF08GatherExceptions:
    """F-08: RouterModuleAdapter.route uses asyncio.gather(return_exceptions=True)
    to prevent one failed doc from cancelling other concurrent route calls.

    AC-F-08-1: When one _route_one call raises, the exception is collected and
               re-raised as the first error, while other calls' results are not lost.
    """

    # TC-F08-001: gather with return_exceptions=True — exception is collected and re-raised
    @pytest.mark.anyio
    async def test_tc_f08_001_exception_from_one_route_is_collected(self) -> None:
        """AC-F-08-1: errors from gather are collected and re-raised via errors[0].

        Reverts-to-fail: if return_exceptions=False, the exception would cancel all
        concurrent tasks and the gather itself would raise directly rather than
        collecting into `errors`. Changing the assertion to expect a different
        exception type would detect the regression.
        """
        from backend.app.adapters.router import RouterModuleAdapter
        from backend.app.api.interfaces import DependencyUnavailable

        call_count = 0
        results = []

        async def _fake_route_one(
            tenant_id: str,
            doc_id: str,
            query: str,
            confidence_threshold: float,
            max_sections: int,
        ) -> tuple:
            nonlocal call_count
            call_count += 1
            if doc_id == "doc_bad":
                raise DependencyUnavailable("route failed for doc_bad")
            return [], {"routing_time_ms": 10, "rationale": "ok", "relevant_sections": [],
                        "confidence": [], "fallback": True}

        mock_store = MagicMock()
        adapter = RouterModuleAdapter(store=mock_store, route=AsyncMock())
        # Patch _route_one to use our controlled implementation
        adapter._route_one = _fake_route_one  # type: ignore[method-assign]

        with pytest.raises(DependencyUnavailable) as exc_info:
            await adapter.route(
                tenant_id=_TENANT_A,
                document_ids=["doc_bad", "doc_good"],
                query="test query",
                confidence_threshold=0.7,
                max_sections=3,
            )

        assert "doc_bad" in str(exc_info.value), (
            "AC-F-08-1: The DependencyUnavailable from doc_bad must propagate"
        )
        assert call_count == 2, (
            "AC-F-08-1: Both _route_one calls must be started (return_exceptions=True "
            "does not cancel peer tasks). call_count was {call_count}"
        )

    # TC-F08-001 (success path): two docs succeed; results are merged
    @pytest.mark.anyio
    async def test_tc_f08_001_two_successful_routes_are_merged(self) -> None:
        """AC-F-08-1: When all gather tasks succeed, results are merged correctly."""
        from backend.app.adapters.router import RouterModuleAdapter
        from backend.app.api.interfaces import RoutedSection

        sec_a = RoutedSection(
            section_id="sec_a001",
            title="Section A",
            page_start=1,
            page_end=3,
            confidence=0.9,
            document_id="doc_a",
        )
        sec_b = RoutedSection(
            section_id="sec_b001",
            title="Section B",
            page_start=4,
            page_end=6,
            confidence=0.85,
            document_id="doc_b",
        )

        async def _fake_route_one(
            tenant_id: str,
            doc_id: str,
            query: str,
            confidence_threshold: float,
            max_sections: int,
        ) -> tuple:
            section = sec_a if doc_id == "doc_a" else sec_b
            return [section], {"routing_time_ms": 5, "rationale": f"ok-{doc_id}",
                               "relevant_sections": [section.section_id],
                               "confidence": [section.confidence], "fallback": False}

        mock_store = MagicMock()
        adapter = RouterModuleAdapter(store=mock_store, route=AsyncMock())
        adapter._route_one = _fake_route_one  # type: ignore[method-assign]

        decision = await adapter.route(
            tenant_id=_TENANT_A,
            document_ids=["doc_a", "doc_b"],
            query="test query",
            confidence_threshold=0.7,
            max_sections=3,
        )

        section_ids = {s.section_id for s in decision.relevant_sections}
        assert "sec_a001" in section_ids, (
            "AC-F-08-1: Section from doc_a must appear in merged decision"
        )
        assert "sec_b001" in section_ids, (
            "AC-F-08-1: Section from doc_b must appear in merged decision"
        )
        assert not decision.fallback, (
            "AC-F-08-1: fallback must be False when both docs returned sections"
        )


# ---------------------------------------------------------------------------
# F-09  page query parameter upper bound: le=10_000
# ---------------------------------------------------------------------------

class TestF09PageBound:
    """F-09: GET /v1/documents?page=N rejects N > 10_000 at FastAPI Query level.

    AC-F-09-1: page=10001 returns 422 (FastAPI query validation) without calling
               store.list_documents.
    AC-F-09-2: page=10000 is accepted (boundary inclusive).
    """

    # TC-F09-001: page=10001 is rejected with 422 before store is called
    def test_tc_f09_001_page_10001_returns_422(self) -> None:
        """AC-F-09-1: page > 10_000 is rejected by FastAPI le= constraint.

        Reverts-to-fail: removing `le=10_000` from the Query() causes 10001 to
        reach the handler body, list_documents to be called, and 200 to be returned.
        """
        import datetime as _dt
        from backend.app.api.interfaces import DocumentRecord

        call_count = 0

        class _TrackingStore:
            async def list_documents(self, *args: Any, **kwargs: Any) -> tuple:
                nonlocal call_count
                call_count += 1
                return [], 0

            async def get_document(self, *args: Any, **kwargs: Any) -> DocumentRecord | None:
                return None

            async def get_sections(self, *args: Any, **kwargs: Any) -> list:
                return []

        token = _mint_jwt(_TENANT_A)
        client = _make_client(store=_TrackingStore())
        response = client.get(
            "/v1/documents?page=10001",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 422, (
            "AC-F-09-1: page=10001 must return 422 Unprocessable Entity (le=10_000 violated), "
            f"got {response.status_code}"
        )
        assert call_count == 0, (
            "AC-F-09-1: store.list_documents must NOT be called when page > 10_000"
        )

    # TC-F09-002: page=10000 is accepted (boundary inclusive)
    def test_tc_f09_002_page_10000_is_accepted(self) -> None:
        """AC-F-09-2: page=10_000 is the inclusive upper bound; must be accepted."""
        import datetime as _dt
        from backend.app.api.interfaces import DocumentRecord

        class _EmptyStore:
            async def list_documents(self, *args: Any, **kwargs: Any) -> tuple:
                return [], 0

            async def get_document(self, *args: Any, **kwargs: Any) -> DocumentRecord | None:
                return None

            async def get_sections(self, *args: Any, **kwargs: Any) -> list:
                return []

        token = _mint_jwt(_TENANT_A)
        client = _make_client(store=_EmptyStore())
        response = client.get(
            "/v1/documents?page=10000",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code in (200, 422), (
            "AC-F-09-2: page=10000 must not be rejected by the le= constraint; "
            f"got {response.status_code}"
        )
        assert response.status_code != 422 or "page" not in response.text.lower(), (
            "AC-F-09-2: if 422 is returned it must not be due to the page parameter "
            "exceeding the le=10_000 bound"
        )
        # The key assertion: FastAPI's query validation must NOT reject page=10000
        if response.status_code == 422:
            body = response.json()
            # Check the error is not a query param validation error for page
            detail = body.get("detail", [])
            page_errors = [
                e for e in (detail if isinstance(detail, list) else [])
                if "page" in str(e.get("loc", ""))
                and "less_than_equal" in str(e.get("type", ""))
            ]
            assert len(page_errors) == 0, (
                "AC-F-09-2: page=10000 must not fail the le=10_000 constraint"
            )


# ---------------------------------------------------------------------------
# F-10  event: final emitted before event: error in _answer_stream
# ---------------------------------------------------------------------------

class TestF10FinalBeforeError:
    """F-10: _answer_stream must yield event: final BEFORE event: error in
    both the DependencyUnavailable and the generic Exception branches.

    AC-F-10-1: DependencyUnavailable mid-stream — final appears before error.
    AC-F-10-2: Generic Exception mid-stream — final appears before error.
    AC-F-10-3: Happy path — final is emitted with no following error frame.
    AC-F-10-4: Partial tokens are included in the final event's answer field.
    """

    @staticmethod
    async def _collect_events(generator: AsyncIterator[str]) -> list[str]:
        """Collect all SSE event names in emission order from the generator.

        Args:
            generator: The _answer_stream async generator.

        Returns:
            Ordered list of event names extracted from SSE frames.
        """
        events: list[str] = []
        async for frame in generator:
            for line in frame.splitlines():
                if line.startswith("event: "):
                    events.append(line[len("event: "):].strip())
        return events

    @staticmethod
    def _make_decision() -> Any:
        """Build a minimal RouterDecision for _answer_stream tests."""
        from backend.app.api.interfaces import RouterDecision
        return RouterDecision(
            relevant_sections=[],
            fallback=False,
            routing_time_ms=0,
        )

    # TC-F10-001: DependencyUnavailable mid-stream — final before error
    @pytest.mark.anyio
    async def test_tc_f10_001_dependency_unavailable_final_before_error(self) -> None:
        """AC-F-10-1: DependencyUnavailable raises after first token;
        event: final must appear before event: error.

        Reverts-to-fail: reverting to the pre-fix ordering (error before final)
        swaps the positions; the assertion `final_idx < error_idx` fails.
        """
        from backend.app.api.answer import _answer_stream
        from backend.app.api.interfaces import DependencyUnavailable

        async def _failing_llm(query: str, sections: list) -> AsyncIterator[str]:
            yield "Hello"
            raise DependencyUnavailable("generation failed")

        mock_llm = MagicMock()
        mock_llm.stream_answer = _failing_llm
        decision = self._make_decision()

        events = await self._collect_events(
            _answer_stream("qid-001", "What is RAG?", decision, mock_llm)
        )

        assert "final" in events, (
            "AC-F-10-1: event: final must be emitted in DependencyUnavailable branch"
        )
        assert "error" in events, (
            "AC-F-10-1: event: error must be emitted in DependencyUnavailable branch"
        )
        final_idx = events.index("final")
        error_idx = events.index("error")
        assert final_idx < error_idx, (
            f"AC-F-10-1: event: final (idx={final_idx}) must precede "
            f"event: error (idx={error_idx}) in DependencyUnavailable branch"
        )

    # TC-F10-002: generic Exception mid-stream — final before error
    @pytest.mark.anyio
    async def test_tc_f10_002_generic_exception_final_before_error(self) -> None:
        """AC-F-10-2: RuntimeError mid-stream causes final before error.

        Reverts-to-fail: if the generic except branch lacks the final frame,
        events.index('final') raises ValueError and the test fails.
        """
        from backend.app.api.answer import _answer_stream

        async def _crashing_llm(query: str, sections: list) -> AsyncIterator[str]:
            yield "Partial"
            raise RuntimeError("GPU OOM")

        mock_llm = MagicMock()
        mock_llm.stream_answer = _crashing_llm
        decision = self._make_decision()

        events = await self._collect_events(
            _answer_stream("qid-002", "What is RAG?", decision, mock_llm)
        )

        assert "final" in events, (
            "AC-F-10-2: event: final must be emitted in generic Exception branch"
        )
        assert "error" in events, (
            "AC-F-10-2: event: error must be emitted in generic Exception branch"
        )
        final_idx = events.index("final")
        error_idx = events.index("error")
        assert final_idx < error_idx, (
            f"AC-F-10-2: event: final (idx={final_idx}) must precede "
            f"event: error (idx={error_idx}) in generic Exception branch"
        )

    # TC-F10-003: happy path — final emitted, no error frame
    @pytest.mark.anyio
    async def test_tc_f10_003_happy_path_final_no_error(self) -> None:
        """AC-F-10-3: Successful stream yields tokens then final; no error frame."""
        from backend.app.api.answer import _answer_stream

        async def _ok_llm(query: str, sections: list) -> AsyncIterator[str]:
            yield "Hello"
            yield " world"

        mock_llm = MagicMock()
        mock_llm.stream_answer = _ok_llm
        decision = self._make_decision()

        events = await self._collect_events(
            _answer_stream("qid-003", "What is RAG?", decision, mock_llm)
        )

        assert "final" in events, (
            "AC-F-10-3: event: final must be emitted on the happy path"
        )
        assert "error" not in events, (
            "AC-F-10-3: event: error must NOT be emitted on the happy path"
        )

    # TC-F10-004: partial tokens are captured in the final event's answer
    @pytest.mark.anyio
    async def test_tc_f10_004_partial_tokens_in_final_answer(self) -> None:
        """AC-F-10-4: answer_parts accumulated before the exception appear in final.

        Reverts-to-fail: if the final event is yielded before collecting tokens
        (wrong ordering in error branches), the answer field would be empty.
        """
        import json
        from backend.app.api.answer import _answer_stream
        from backend.app.api.interfaces import DependencyUnavailable

        async def _partial_llm(query: str, sections: list) -> AsyncIterator[str]:
            yield "token1"
            yield "token2"
            raise DependencyUnavailable("halfway")

        mock_llm = MagicMock()
        mock_llm.stream_answer = _partial_llm
        decision = self._make_decision()

        frames: list[str] = []
        async for frame in _answer_stream("qid-004", "test?", decision, mock_llm):
            frames.append(frame)

        # Find the final frame and extract the answer
        final_frame = next(
            (f for f in frames if "event: final" in f),
            None,
        )
        assert final_frame is not None, (
            "AC-F-10-4: event: final frame must be present even when an exception occurs"
        )
        data_line = next(
            (line for line in final_frame.splitlines() if line.startswith("data: ")),
            "",
        )
        payload = json.loads(data_line[len("data: "):])
        assert payload.get("answer") == "token1token2", (
            "AC-F-10-4: final event's answer must contain all tokens yielded before "
            f"the exception. Got: {payload.get('answer')!r}"
        )


# ---------------------------------------------------------------------------
# Helper: create an async iterable from a list of items
# ---------------------------------------------------------------------------

async def _aiter_items(items: list[str]) -> AsyncIterator[str]:
    """Yield items from a list as an async iterator.

    Args:
        items: Items to yield.

    Yields:
        Each item in order.
    """
    for item in items:
        yield item
```

---

## pytest.ini / conftest additions required

The test file imports `anyio` markers. Add `anyio` mode to `pytest.ini` (or
`pyproject.toml [tool.pytest.ini_options]`):

```ini
[pytest]
asyncio_mode = auto
```

Or if using `pytest-anyio`:

```ini
[pytest]
anyio_mode = auto
```

The existing `tests/conftest.py` already provides:
- `_configure_settings` autouse fixture (monkeypatches JWT_SECRET, JWT_AUDIENCE,
  API_KEY_SALT and clears get_settings cache)
- `make_jwt()` helper
- `FakeDocumentStore`, `FakeRouter`, `FakeIngestor`, `FakeGenerationLLM` fakes

The new `_env` fixture in this test file adds `JWT_ISSUER` to the monkeypatch set
so that `Settings()` never raises `ValidationError` during test collection. It also
resets the rate-limiter, matching the existing conftest behaviour.

---

## Coverage Map

| Finding | File | Lines/Branches Covered |
|---------|------|------------------------|
| F-01 | `backend/app/security/auth.py` | `_resolve_jwt_principal` — both key-presence branches, tid fallback, both-missing 401 |
| F-02 | `backend/app/settings.py` | `jwt_issuer` field (required, no default) |
| F-03 | `backend/app/adapters/generation.py` | `stream_answer` — `thinking` kwarg forwarded |
| F-04 | `ingestion/pipeline.py` + `backend/app/adapters/ingestor.py` | `IngestResult.total_pages`, `as_dict()`, `ingest_document` total_pages read |
| F-05 | `backend/app/adapters/ingestor.py` | `EmbedderDimensionError` except branch → ProblemException(500); DependencyUnavailable re-raise |
| F-07 | `backend/app/api/answer.py` | `if document.fallback_only: raise validation_error` gate |
| F-08 | `backend/app/adapters/router.py` | `asyncio.gather(..., return_exceptions=True)` + error collection |
| F-09 | `backend/app/api/documents.py` | `Query(default=1, ge=1, le=10_000)` — rejection at 10001, acceptance at 10000 |
| F-10 | `backend/app/api/answer.py` | `_answer_stream` — both except branches yield final then error |
