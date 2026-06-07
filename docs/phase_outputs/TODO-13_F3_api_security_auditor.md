# TODO-13 Phase F.3 — API Security Audit Report

**Agent:** api-security-auditor
**Date:** 2026-06-07
**Sprint:** RAG Refinement System brownfield fix sprint
**Scope:** F-01 IDOR, F-07 fallback gate, F-08 session gather, F-09 OFFSET amplification

---

## Methodology

All findings are based on direct source-code inspection of the following files:

| File | Purpose |
|------|---------|
| `backend/app/security/auth.py` | JWT/API-key resolution, `_resolve_jwt_principal()` |
| `backend/app/api/documents.py` | `list_documents`, `get_document`, CRUD endpoints |
| `backend/app/api/answer.py` | F-07 fallback gate, SSE streaming |
| `backend/app/adapters/router.py` | F-08 `asyncio.gather` session routing |
| `backend/app/adapters/document_store.py` | Raw SQL queries, tenant scoping |
| `backend/app/errors.py` | RFC-7807 problem formatting |
| `backend/app/main.py` | App factory, middleware registration |
| `backend/app/settings.py` | Rate-limit configuration |
| `backend/app/api/interfaces.py` | Protocol contracts |
| `backend/app/security/rate_limit.py` | Rate-limit enforcement |

---

## 1. F-01 IDOR at API Level — Full Request Path Trace

### 1.1 Authentication Layer (`auth.py`)

The F-01 fix in `_resolve_jwt_principal()` applies a key-presence AND truthiness check (lines 232–238):

```python
if "tenant_id" in claims and claims["tenant_id"]:
    tenant_id: object = claims["tenant_id"]
elif "tid" in claims and claims["tid"]:
    tenant_id = claims["tid"]
else:
    tenant_id = None
if not subject or not tenant_id:
    raise unauthorized("Bearer token is missing required claims.")
```

**IDOR attack vector traced:** JWT with `{"tenant_id": "", "tid": "victim-tenant"}`:
- Step 1: `"tenant_id" in claims` → True, but `claims["tenant_id"]` is `""` (falsy) → branch not taken.
- Step 2: `"tid" in claims` → True, `claims["tid"]` is `"victim-tenant"` (truthy) → `tenant_id = "victim-tenant"`.
- Step 3: `not tenant_id` → `not "victim-tenant"` → False. Authentication SUCCEEDS. Principal resolved as tenant `"victim-tenant"`.

**Finding:** SEC-F01-001 RESIDUAL IS CONFIRMED AT THE API LEVEL. The auth fix is **not** a complete IDOR block — it correctly rejects `{"tenant_id": "", "tid": ""}` (both empty) but authenticates as tenant `"victim-tenant"` when `tid` contains a valid non-empty value. This was the known residual finding from TODO-07 (threat-modeling-specialist).

### 1.2 Cross-Tenant Data Isolation (the critical second layer)

**The key security question is:** even if an attacker can impersonate tenant X via the `tid` fallback, do the data store queries prevent cross-tenant access to a DIFFERENT tenant's data?

Tracing `GET /v1/documents/{doc_id}` (`documents.py` line 307):
```python
record = await store.get_document(principal.tenant_id, doc_id)
if record is None:
    raise document_not_found()
```

The `store.get_document` call in `document_store.py` (lines 125–135):
```python
stmt = select(Document).where(
    Document.doc_id == doc_id,
    Document.tenant_id == tenant_id,   # ← always uses principal.tenant_id
    Document.tombstoned_at.is_(None),
)
```

**Assessment:** The tenant_id used in every SQL WHERE clause is `principal.tenant_id` — the value extracted from the JWT during authentication. In the IDOR scenario, the attacker authenticates as `"victim-tenant"` (using `tid`). The SQL query then correctly filters on `tenant_id = "victim-tenant"`. The attacker only sees victim-tenant's own documents (which they are now authenticated as). They cannot reach another tenant's data because the SQL filter uses their resolved principal — not a client-supplied parameter.

**All endpoints verified for consistent principal-scoped queries:**

| Endpoint | Document Store Call | Tenant Source |
|----------|--------------------|-|
| `GET /v1/documents` (`list_documents`) | `store.list_documents(principal.tenant_id, ...)` | `principal.tenant_id` |
| `GET /v1/documents/{doc_id}` | `store.get_document(principal.tenant_id, doc_id)` | `principal.tenant_id` |
| `GET /v1/documents/{doc_id}/toc` | `store.get_document(principal.tenant_id, ...)` | `principal.tenant_id` |
| `DELETE /v1/documents/{doc_id}` | `store.tombstone_document(principal.tenant_id, ...)` | `principal.tenant_id` |
| `GET /v1/documents/{doc_id}/data` | `store.get_document(principal.tenant_id, ...)` | `principal.tenant_id` |
| `POST /v1/answer` | `store.get_document(principal.tenant_id, ...)` | `principal.tenant_id` |
| `POST /v1/route` | `store.get_document(principal.tenant_id, ...)` | `principal.tenant_id` |
| `RouterModuleAdapter._route_one` | `store.get_sections(tenant_id, doc_id)` where `tenant_id` comes from `route()` → `principal.tenant_id` | `principal.tenant_id` |
| `ingest_document` | `ingestor.ingest_document(tenant_id=principal.tenant_id, ...)` | `principal.tenant_id` |

**No endpoint accepts `tenant_id` as a client-supplied request body/query parameter.** The tenant is always derived exclusively from the authenticated principal.

### 1.3 IDOR Verdict

**IDOR at the API/data layer: BLOCKED.** Even when SEC-F01-001 residual allows authentication as `victim-tenant` (via `tid` fallback), the attacker can only access documents that belong to `victim-tenant`. They cannot pivot to any other tenant's data because:
1. The SQL WHERE clauses universally bind to `principal.tenant_id`.
2. `tenant_id` is never a client-supplied parameter in any endpoint.
3. Cross-tenant `doc_id` lookup resolves to `None` → 404 (information disclosure neutralized).

**ESCALATION FLAG (SEC-F01-001 residual):** The `tid` fallback path is a lateral movement vector if an attacker can forge or guess a valid `victim-tenant` value and sign a JWT with the system secret. The auth fix prevents ONLY the empty-string bypass. A complete mitigation would require removing the `tid` fallback entirely or documenting it as an intentional tenant alias. This should be reviewed by **security-lead-auditor** as a medium-severity residual requiring a product decision.

---

## 2. F-07 Error Response Privacy Audit

### 2.1 Fallback Gate Code (`answer.py` lines 203–208)

```python
if document.fallback_only:
    raise validation_error(
        detail="This document was indexed in fallback mode and does not support section-level routing.",
        errors=[{"field": "document_id", "message": "fallback-only document"}],
    )
```

The `validation_error()` function in `errors.py` (lines 154–174):

```python
def validation_error(
    detail: str = "One or more fields failed validation.",
    errors: list[dict[str, str]] | None = None,
) -> ProblemException:
    return ProblemException(
        status_code=422,
        code="VALIDATION_ERROR",
        title="Unprocessable Entity",
        detail=detail,
        problem_type="validation-error",
        errors=errors or [],
    )
```

The `to_problem()` serializer (lines 78–96) produces:

```json
{
  "type": "https://api.rag-refinement.example.com/problems/validation-error",
  "title": "Unprocessable Entity",
  "status": 422,
  "code": "VALIDATION_ERROR",
  "detail": "This document was indexed in fallback mode and does not support section-level routing.",
  "errors": [
    {"field": "document_id", "message": "fallback-only document"}
  ]
}
```

### 2.2 Privacy Check

| Information category | Present in response? | Verdict |
|---------------------|---------------------|---------|
| Table names (`documents`, `sections`) | No | PASS |
| Column names (`fallback_only`, `tenant_id`) | No | PASS |
| Python exception type strings | No | PASS |
| Internal file paths | No | PASS |
| Stack frames | No | PASS |
| Database DSN or connection info | No | PASS |
| Qdrant endpoint or vector store info | No | PASS |
| Other tenant's data | No | PASS |
| Schema version or internal model names | No | PASS |

**F-07 verdict: PASS.** The 422 error response is fully sanitized. The `detail` message references only the business-domain concept ("indexed in fallback mode", "section-level routing") — no internal schema, Python types, or infrastructure details. The `errors` array carries only `field` and `message` string pairs with no internal leakage.

**Additional observation:** The `router.route` call does NOT execute when `document.fallback_only` is True — the `raise validation_error(...)` occurs on line 205, before the `routing.route(...)` call on line 211. This matches TC-F07-001 from TODO-05.

---

## 3. F-09 OFFSET Amplification — Boundary Value Analysis

### 3.1 Constraint Definition (`documents.py` line 244)

```python
page: int = Query(default=1, ge=1, le=10_000),
```

### 3.2 Boundary Value Table

| Input | FastAPI Query constraint fires? | Handler body reached? | DB query issued? | HTTP response |
|-------|--------------------------------|----------------------|-----------------|---------------|
| `page=-1` | YES (ge=1 violated) | NO | NO | 422 VALIDATION_ERROR |
| `page=0` | YES (ge=1 violated) | NO | NO | 422 VALIDATION_ERROR |
| `page=1` | NO (within bounds) | YES | YES | 200 |
| `page=10000` | NO (within bounds, le=10_000 inclusive) | YES | YES | 200 |
| `page=10001` | YES (le=10_000 violated) | NO | NO | 422 VALIDATION_ERROR |

### 3.3 FastAPI Architecture Guarantee

FastAPI evaluates `Query(ge=1, le=10_000)` during request parameter parsing, before the endpoint handler body executes. This is a Pydantic validation phase — the handler function is never called on constraint violation. The 422 response is returned immediately by `_handle_request_validation()` in `errors.py` (lines 313–330), which converts `RequestValidationError` to a safe VALIDATION_ERROR problem.

### 3.4 Worst-Case OFFSET Calculation

With `le=10_000` on `page` and `le=100` on `page_size`, the maximum DB OFFSET is:

```
OFFSET = max(page - 1, 0) * page_size = (10000 - 1) * 100 = 999,900 rows
```

This is bounded. With PostgreSQL MVCC, a 999,900-row OFFSET still requires scanning the index up to that point, which is expensive but deterministic and not unbounded. Combined with the per-credential rate limiter (default 60 req/min, sensitive 20 req/min), a sustained OFFSET amplification attack is further mitigated.

**F-09 verdict: PASS.** The `le=10_000` constraint is correctly placed on the `Query()` parameter. FastAPI validation fires before handler execution, ensuring no DB query is issued for out-of-bounds page values. TC-F09-001 (page=10001 → 422, store.list_documents call_count == 0) and TC-F09-002 (page=10000 → 200) are consistent with the code.

---

## 4. F-08 Error Disclosure Check

### 4.1 `asyncio.gather` Pattern (`router.py` lines 274–285)

```python
raw = await asyncio.gather(
    *[
        self._route_one(
            tenant_id, doc_id, query, confidence_threshold, max_sections
        )
        for doc_id in document_ids
    ],
    return_exceptions=True,
)
errors = [r for r in raw if isinstance(r, BaseException)]
if errors:
    raise errors[0]
```

### 4.2 Exception Propagation Path

`errors[0]` is the first exception raised by any `_route_one()` coroutine. These are:
- `DependencyUnavailable` — raised by `store.get_sections()` on `SQLAlchemyError`
- Any exception from `self._route()` (the router package callable)

When `raise errors[0]` executes in `RouterModuleAdapter.route()`, the exception propagates to the caller in `answer.py`:

```python
try:
    decision = await routing.route(...)
except DependencyUnavailable as exc:
    raise service_unavailable(str(exc) or "Routing dependency unavailable.") from exc
```

Or to `routing.py`:

```python
try:
    decision = await routing.route(...)
except DependencyUnavailable as exc:
    raise service_unavailable(str(exc) or "Routing dependency unavailable.") from exc
```

The `service_unavailable()` function in `errors.py` (lines 240–260) produces:

```json
{
  "type": "https://api.rag-refinement.example.com/problems/service-unavailable",
  "title": "Service Unavailable",
  "status": 503,
  "code": "SERVICE_UNAVAILABLE",
  "detail": "Routing dependency unavailable."
}
```

### 4.3 Unexpected Exception Path

If `_route_one` raises any non-`DependencyUnavailable` exception (e.g., `ValueError`, internal router error), it is NOT caught by the `DependencyUnavailable` handler. It propagates to the catch-all handler in `errors.py` (lines 365–375):

```python
async def _handle_unexpected(_request: Request, _exc: Exception) -> JSONResponse:
    return _problem_response(internal_error())
```

Which returns:

```json
{
  "status": 500,
  "code": "INTERNAL_ERROR",
  "detail": "An unexpected error occurred. The incident has been logged."
}
```

**No internal detail is disclosed in either path.** The `str(exc)` on `DependencyUnavailable` only produces `"structure store unreachable"` (the hardcoded string in `document_store.py` line 134) — no SQL query text, no connection pool internals, no stack frames.

### 4.4 Sibling Coroutine Completion

With `return_exceptions=True`, when one `_route_one` coroutine fails, the remaining coroutines continue to completion (or fail independently). Their results/exceptions are all collected before `errors[0]` is raised. This means a partial failure does not leave dangling coroutines — no goroutine-style leak.

**F-08 verdict: PASS.** The `asyncio.gather(return_exceptions=True)` + `raise errors[0]` pattern does not create new error disclosure vectors. All exception paths lead to either a safe 503 (known dependency failures) or a generic 500 (unexpected exceptions). No internal details are surface to callers.

---

## 5. CORS and Rate Limit Review

### 5.1 CORS Policy

No `CORSMiddleware` is registered in `main.py`. The `create_app()` function registers:
- `register_exception_handlers(app)` — RFC-7807 error handlers only
- Routers: `health_router`, `observability_router`, `routing_router`, `answer_router`, `documents_router`

**No CORS middleware is configured.** This means:
- Browser cross-origin requests will be blocked by default (no `Access-Control-Allow-Origin` header).
- This is appropriate for an API backend (not a public browser-facing CDN endpoint).
- The fixes in the 10-finding sprint did NOT add or remove CORS configuration — the policy is unchanged.

If the API is intended to be called from browser-based personal tools, CORS would need to be added explicitly. This is outside the scope of the 10 fixes but noted as a deployment consideration.

### 5.2 Rate Limit Bounds

The rate limiter (`rate_limit.py`) uses `Settings.rate_limit_default_per_minute` (default: 60) and `rate_limit_sensitive_per_minute` (default: 20). These defaults are applied per `rate_limit_key`, which is `"{kind}:{subject}"` — per credential, not per IP. Key observations:

- The rate limiter fires **after** authentication. An unauthenticated caller gets 401, not 429 (correct order per `rate_limit.py` lines 104–130: authentication is a dependency of rate limiting).
- The in-memory window is process-local. In a multi-process deployment (e.g., multiple gunicorn workers), each process has an independent counter. Production should swap to Redis, as noted in the docstring.
- With `le=10_000` on `page` and 60 req/min default rate limit, worst-case data exfiltration from `listDocuments` is `60 * 10000 * 100 = 60,000,000 rows/min` if the DB contains that many records. This is bounded by the DB performance, not the API layer. A tighter per-IP rate limit at the load balancer layer (nginx/CloudFlare) is advisable for production but is outside the scope of this audit.

---

## 6. Cross-Tenant Data Isolation Assessment

### 6.1 Summary of Isolation Mechanisms

Two independent layers enforce cross-tenant isolation:

**Layer 1 — Authentication (auth.py):** The JWT resolution always extracts `tenant_id` or `tid` from the validated token payload. No client-supplied HTTP header/body parameter overrides the resolved `tenant_id`. The `sub` claim is also required; an empty subject → 401.

**Layer 2 — Database Query Scoping (document_store.py):** Every SQL statement unconditionally includes `WHERE tenant_id = :principal_tenant_id`. This is visible in all four methods:
- `get_document`: `Document.tenant_id == tenant_id`
- `list_documents`: `Document.tenant_id == tenant_id` in both count and page queries
- `get_sections`: `Section.tenant_id == tenant_id`
- `tombstone_document`: `Document.tenant_id == tenant_id`

### 6.2 SEC-F01-001 Residual in the Context of Data Isolation

When an attacker uses the `tid` fallback to authenticate as `victim-tenant`:
- They get a `Principal(tenant_id="victim-tenant", ...)`.
- All DB queries filter by `tenant_id = "victim-tenant"`.
- They can access `victim-tenant`'s documents — but this is the expected behavior if they legitimately hold `victim-tenant`'s JWT secret (since the signature is validated by `jwt.decode` before `_resolve_jwt_principal` is called).

The real risk is: if a multi-tenant JWT issuer populates `tenant_id` for some tokens and `tid` for others (e.g., different token formats for different enterprise tiers), the fallback `tid` path could be used by a tenant whose `tenant_id` is legitimately empty to impersonate any other tenant whose `tid` value they can discover. This is an issuer-level trust misconfiguration, not an application-level IDOR.

**Verdict:** Cross-tenant data isolation is EFFECTIVE at the database layer for all 10 fix scenarios. The SEC-F01-001 residual does not allow cross-tenant pivot — it only allows authentication AS the tenant named in `tid`.

---

## 7. Additional Findings and Escalations

### Finding API-01: `_handle_http_exception` Echoes `exc.detail` (Low Severity)

In `errors.py` lines 355–362:

```python
detail=str(exc.detail) if exc.detail else None,
```

`StarletteHTTPException.detail` is typically a string set by FastAPI itself (e.g., `"Not Found"`, `"Method Not Allowed"`). However, if any middleware or upstream component raises `HTTPException` with a custom `detail` that contains internal state, this would be echoed verbatim. The current routing code does not raise `HTTPException` directly — it uses `ProblemException` — so the practical risk is low. Recommend replacing with a static safe message for each status code.

**Escalation target:** security-lead-auditor for awareness. Severity: Low.

### Finding API-02: `str(exc)` in `DependencyUnavailable` Handler (Informational)

In `answer.py` line 140: `service_unavailable(str(exc) or "Generation dependency unavailable.")` and `routing.py` line 94: `service_unavailable(str(exc) or "Routing dependency unavailable.")`.

The `DependencyUnavailable` exception message originates from `document_store.py`: `"structure store unreachable"`. This string is hardcoded and safe. If any collaborator raises `DependencyUnavailable` with a message containing internal detail (e.g., a connection string), it would be surfaced in the 503 response. The current codebase only raises `DependencyUnavailable("structure store unreachable")`.

**Recommendation:** Add a test asserting that the 503 `detail` field matches the expected safe string. Severity: Informational.

### Finding API-03: No CSRF Protection (Informational)

The API uses JWT bearer tokens and API keys (not cookies), so CSRF is not applicable. Noted for completeness.

### Finding API-04: `jwt_issuer` Has No Default (`settings.py` line 58)

```python
jwt_issuer: str = Field(alias="JWT_ISSUER")
```

Unlike other settings, `jwt_issuer` has no `default=` value. If `JWT_ISSUER` is not set in the environment, `pydantic_settings` will raise a `ValidationError` at startup, preventing the service from starting. This is a fail-safe behavior (misconfigured service won't accept JWTs), but it could cause operational confusion. Not a security finding, noted for completeness.

---

## 8. Summary Verdict

| Finding | Result | Notes |
|---------|--------|-------|
| F-01 IDOR at auth layer | PARTIAL FIX — residual SEC-F01-001 confirmed | `tid` fallback authenticates as that tenant; not a cross-tenant data leak |
| F-01 IDOR at data isolation layer | PASS | All DB queries unconditionally scope by `principal.tenant_id` |
| F-07 422 error response privacy | PASS | No internal schema, Python types, or paths in response |
| F-07 `router.route` not called on fallback_only | PASS | `raise validation_error` fires before `routing.route()` call |
| F-09 page=10001 → 422, no DB query | PASS | FastAPI Query constraint fires in parameter parsing phase |
| F-09 page=10000 → 200 (boundary inclusive) | PASS | `le=10_000` is inclusive |
| F-09 page=-1 / page=0 → 422 | PASS | `ge=1` rejects both |
| F-08 `asyncio.gather` no error disclosure | PASS | `DependencyUnavailable` → safe 503; unexpected → generic 500 |
| F-08 sibling coroutine completion | PASS | `return_exceptions=True` completes all coroutines before re-raise |
| CORS policy unchanged | CONFIRMED | No CORSMiddleware registered; policy unaffected by fixes |
| Cross-tenant data isolation | PASS — effective | SQL WHERE always uses `principal.tenant_id`, not client-supplied value |

**Overall API Security Audit Verdict: PASS with one residual escalation.**

The 10 fixes do not introduce new API-level attack vectors. The SEC-F01-001 residual (authenticated `tid` fallback) is a pre-existing design question requiring a product owner decision on whether the `tid` fallback claim is intentional. Cross-tenant data isolation is robust and independent of the authentication residual.

**Escalation to security-lead-auditor:**
1. SEC-F01-001 residual: `tid` fallback path — determine if it is an intentional alias or should be removed (Medium severity).
2. API-01: `_handle_http_exception` echoes `exc.detail` — review for middleware-injected exception detail strings (Low severity).
