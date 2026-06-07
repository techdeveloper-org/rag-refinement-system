# IEEE 829 Test Plan — RAG Refinement System Code-Review Fix Sprint

**Test Plan ID:** TP-RAG-REVIEW-v1
**Date:** 2026-06-07
**Branch:** `build/rag-refinement-product`
**Prepared by:** test-management-agent (TODO-04, Phase D.1)
**Specification Authority:** `docs/code-review-fix-requirements.md`
**Phase C Gate Status:** PASSED (NLI=1.0 · FactScore=0.997)

---

## 1. Scope

### 1.1 In Scope

This test plan covers the ten code-review findings (F-01 through F-10) identified in the RAG Refinement System review dated 2026-06-06. Testing targets all acceptance criteria (ACs) defined in `docs/code-review-fix-requirements.md`, which is the definitive test specification for this sprint. The following source files are under test:

| File | Findings Covered |
|------|-----------------|
| `backend/app/security/auth.py` | F-01, F-02 |
| `backend/app/settings.py` | F-02 |
| `backend/app/adapters/generation.py` | F-03 |
| `ingestion/pipeline.py` | F-04, F-06 |
| `backend/app/adapters/ingestor.py` | F-04, F-05, F-06 |
| `backend/app/adapters/router.py` | F-07, F-08 |
| `backend/app/api/documents.py` | F-09 |
| `backend/app/api/answer.py` | F-07, F-10 |

### 1.2 Out of Scope

- Findings not listed in `docs/code-review-fix-requirements.md`
- Performance benchmarking beyond the OFFSET amplification guard (F-09)
- Frontend rendering behaviour beyond the SSE contract assertions (F-10)
- Database schema migration validation (index creation for F-09 is a deployment concern)
- Operator runbook for `JWT_ISSUER` (F-02 deployment artefact, not a test artefact)

### 1.3 Test Objectives

1. Verify that all security vulnerabilities (F-01, F-02) are fully remediated with no regression.
2. Confirm that the operational blocker (F-03) is resolved and `/v1/answer` streams tokens successfully.
3. Validate correctness fixes (F-04, F-05, F-06, F-07) under both normal and adversarial inputs.
4. Confirm resource-safety fix (F-08) prevents SQLAlchemy session leaks under concurrent DB failures.
5. Validate efficiency guard (F-09) blocks expensive OFFSET scans at the parameter layer.
6. Confirm UX fix (F-10) preserves citation panel data when the generation adapter fails mid-stream.

---

## 2. Risk Prioritization Matrix

| Finding | Title (abbreviated) | Risk Tier | Test Types | Assigned Agent | Coverage Gate |
|---------|---------------------|-----------|-----------|----------------|---------------|
| F-01 | Cross-tenant IDOR via `or` truthiness | **P0 — Critical** | Unit · Security | unit-testing-specialist + security-testing-engineer | Merge gate (100% AC) |
| F-02 | `JWT_ISSUER=None` disables issuer validation | **P0 — Critical** | Unit · Security · Integration | unit-testing-specialist + security-testing-engineer | Merge gate (100% AC) |
| F-03 | `thinking` param missing `budget_tokens` | **P1 — High** | Integration | integration-testing-engineer | Production gate (100% AC) |
| F-04 | `total_pages` omitted from `IngestResult` | **P1 — High** | Unit | unit-testing-specialist | Production gate (100% AC) |
| F-05 | Permanent errors wrapped as retryable 503 | **P2 — Medium** | Unit | unit-testing-specialist | Production gate (100% AC) |
| F-06 | TOCTOU race on concurrent identical uploads | **P2 — Medium** | Integration · Concurrency | integration-testing-engineer | Production gate (100% AC) |
| F-07 | Fallback-only docs trigger hallucinated answer | **P2 — Medium** | Integration | integration-testing-engineer | Production gate (100% AC) |
| F-08 | `gather` without `return_exceptions` leaks sessions | **P2 — Medium** | Integration · Concurrency | integration-testing-engineer | Production gate (100% AC) |
| F-09 | Over-page guard fires after expensive DB queries | **P3 — Low** | Unit | unit-testing-specialist | Next-sprint gate (100% AC) |
| F-10 | `event: final` missing before `event: error` | **P3 — Low** | Unit | unit-testing-specialist | Next-sprint gate (100% AC) |

**Risk tier definitions:**
- **P0 — Critical:** Security vulnerabilities or data integrity failures. Blocks merge to `main`.
- **P1 — High:** Operational blockers or incorrect data surfaced to users. Blocks production deployment.
- **P2 — Medium:** Correctness defects under specific conditions or resource leaks. Blocks external user onboarding.
- **P3 — Low:** Efficiency and UX regressions with no data loss or security impact. Addressed in next sprint.

---

## 3. Test Case Catalogue

> Convention: **TC-FNN-NNN** = Test Case, Finding NN, Case NNN.
> AC reference uses the bullet number within the finding's Acceptance Criteria section.

---

### F-01 — Cross-tenant IDOR (P0 · Security + Unit)

#### TC-F01-001

| Field | Value |
|-------|-------|
| **ID** | TC-F01-001 |
| **AC Reference** | F-01 AC-1: `{"tenant_id": "", "tid": "other-tenant"}` must raise `unauthorized` |
| **Title** | Empty `tenant_id` with populated `tid` must not authenticate as `tid` tenant |
| **Description** | Verifies that the `or`-truthiness fix correctly rejects a JWT where `tenant_id` is an empty string. The pre-fix code would fall through to `tid` and grant access to `"other-tenant"`. The post-fix code must detect that `tenant_id` key is present but falsy and not fall back to `tid`. |
| **Inputs** | JWT payload: `{"sub": "user-1", "tenant_id": "", "tid": "other-tenant", "iss": "<valid-issuer>"}` |
| **Expected Output** | `HTTPException` / `unauthorized` raised; HTTP 401 returned; no principal object constructed |
| **Assigned Agent** | unit-testing-specialist + security-testing-engineer |
| **Priority** | P0 — Merge gate |

#### TC-F01-002

| Field | Value |
|-------|-------|
| **ID** | TC-F01-002 |
| **AC Reference** | F-01 AC-2: `{"tenant_id": "correct-tenant"}` must authenticate as `"correct-tenant"` |
| **Title** | Valid `tenant_id` claim authenticates correctly |
| **Description** | Verifies the normal happy path: a JWT with a non-empty `tenant_id` key authenticates as that tenant. Confirms the fix does not break the standard flow. |
| **Inputs** | JWT payload: `{"sub": "user-1", "tenant_id": "correct-tenant", "iss": "<valid-issuer>"}` |
| **Expected Output** | Principal constructed with `tenant_id="correct-tenant"`; no exception raised |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P0 — Merge gate |

#### TC-F01-003

| Field | Value |
|-------|-------|
| **ID** | TC-F01-003 |
| **AC Reference** | F-01 AC-3: JWT with only `{"tid": "correct-tenant"}` (no `tenant_id` key) must authenticate as `"correct-tenant"` |
| **Title** | `tid`-only JWT (no `tenant_id` key present) authenticates via `tid` fallback |
| **Description** | Verifies that when `tenant_id` key is absent entirely, the fix correctly falls back to `tid`. This is the legitimate fallback scenario and must not be broken by the key-presence check. |
| **Inputs** | JWT payload: `{"sub": "user-1", "tid": "correct-tenant", "iss": "<valid-issuer>"}` — no `tenant_id` key |
| **Expected Output** | Principal constructed with `tenant_id="correct-tenant"`; no exception raised |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P0 — Merge gate |

---

### F-02 — `JWT_ISSUER=None` Disables Issuer Validation (P0 · Security + Integration)

#### TC-F02-001

| Field | Value |
|-------|-------|
| **ID** | TC-F02-001 |
| **AC Reference** | F-02 AC-1: Without `JWT_ISSUER` set, the service must refuse to start (Option A) or reject all bearer tokens (Option B) |
| **Title** | Missing `JWT_ISSUER` env var causes service startup failure or universal token rejection |
| **Description** | Verifies that the absence of `JWT_ISSUER` in the environment is caught at startup (Option A: `ValidationError` from Pydantic during `Settings` construction) or at decode-time (Option B: `unauthorized` raised before PyJWT `decode` is called). Both branches must be covered by at least one assertion. |
| **Inputs** | Environment: `JWT_ISSUER` variable unset or removed; any valid JWT presented to `decode_bearer` |
| **Expected Output** | Option A: `ValidationError` / service startup exception at `Settings()` construction. Option B: HTTP 401 `unauthorized` returned before PyJWT `decode` is invoked. |
| **Assigned Agent** | unit-testing-specialist + security-testing-engineer |
| **Priority** | P0 — Merge gate |

#### TC-F02-002

| Field | Value |
|-------|-------|
| **ID** | TC-F02-002 |
| **AC Reference** | F-02 AC-2: A JWT with a wrong or missing `iss` claim must raise `unauthorized` when `JWT_ISSUER` is set |
| **Title** | JWT with incorrect `iss` claim is rejected when `JWT_ISSUER` is configured |
| **Description** | Verifies that PyJWT issuer validation is active when `JWT_ISSUER` is set. A token signed with the correct secret but carrying a mismatched `iss` must be rejected. Also covers the case where `iss` is absent from the token. |
| **Inputs** | `JWT_ISSUER=https://auth.example.com`; JWT payload: `{"sub": "user-1", "tenant_id": "t1", "iss": "https://attacker.example.com"}` |
| **Expected Output** | `HTTPException` / `unauthorized` raised; HTTP 401 returned |
| **Assigned Agent** | unit-testing-specialist + security-testing-engineer |
| **Priority** | P0 — Merge gate |

#### TC-F02-003

| Field | Value |
|-------|-------|
| **ID** | TC-F02-003 |
| **AC Reference** | F-02 AC-3: A JWT with the correct `iss` claim must authenticate successfully |
| **Title** | JWT with correct `iss` claim authenticates when `JWT_ISSUER` is configured |
| **Description** | Verifies the happy path after the fix: a properly-issued JWT with matching `iss` passes validation end-to-end. Confirms the fix does not over-block legitimate tokens. |
| **Inputs** | `JWT_ISSUER=https://auth.example.com`; JWT payload: `{"sub": "user-1", "tenant_id": "t1", "iss": "https://auth.example.com"}` |
| **Expected Output** | Principal constructed successfully; no exception raised; HTTP 200 on a protected endpoint |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P0 — Merge gate |

---

### F-03 — `thinking` Parameter Missing `budget_tokens` (P1 · Integration)

#### TC-F03-001

| Field | Value |
|-------|-------|
| **ID** | TC-F03-001 |
| **AC Reference** | F-03 AC-1+2: `/v1/answer` must stream at least one `event: token`; must not raise `BadRequestError` |
| **Title** | Valid query streams `event: token` without `BadRequestError` from Anthropic client |
| **Description** | Verifies that the corrected `thinking={"type": "enabled", "budget_tokens": N}` parameter form is accepted by the Anthropic client (real or stubbed). The SSE stream must produce at least one `event: token` event before `event: final`. No `event: error` with `code=INTERNAL_ERROR` may appear as a result of a `BadRequestError`. The test uses a stubbed Anthropic client that validates the `thinking` dict shape and raises `BadRequestError` if the legacy `{"type": "adaptive"}` form is presented. |
| **Inputs** | Query: `{"query": "What is the main topic?", "document_ids": ["<valid-doc>"]}` with `thinking={"type": "enabled", "budget_tokens": 5000}` injected into generation adapter |
| **Expected Output** | SSE stream contains at least one `event: token` line; no `BadRequestError` raised; no `event: error` emitted |
| **Assigned Agent** | integration-testing-engineer |
| **Priority** | P1 — Production gate |

---

### F-04 — `total_pages` Omitted from `IngestResult` (P1 · Unit)

#### TC-F04-001

| Field | Value |
|-------|-------|
| **ID** | TC-F04-001 |
| **AC Reference** | F-04 AC-2: Scenario C ingest returns `total_pages > 0` when the PDF has pages |
| **Title** | Scenario C (fallback-only) ingest returns correct non-zero `total_pages` |
| **Description** | Verifies that when a PDF is ingested in Scenario C (fallback-only path, `toc=[]`), the `IngestResponse.total_pages` equals the PDF's actual page count rather than `0`. The test mocks the PDF parser to return `page_count=5` and the section store to produce no TOC entries, then asserts `IngestResult.as_dict()["total_pages"] == 5`. Also implicitly covers the AC-1 assertion that `_total_pages(toc=[])` is no longer the source of `total_pages`. |
| **Inputs** | `IngestInput` with a 5-page PDF; mock section store returns `toc=[]`; mock PDF parser returns `page_count=5` |
| **Expected Output** | `IngestResult.as_dict()["total_pages"] == 5`; `IngestResponse.total_pages == 5` from endpoint |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P1 — Production gate |

---

### F-05 — Permanent Errors Wrapped as Retryable 503 (P2 · Unit)

#### TC-F05-001

| Field | Value |
|-------|-------|
| **ID** | TC-F05-001 |
| **AC Reference** | F-05 AC-1: Ingest with misconfigured embedder (wrong dimension) returns HTTP 500, not 503 |
| **Title** | `EmbedderDimensionError` surfaces as HTTP 500 with `Embedder misconfiguration` title |
| **Description** | Verifies that when `_run_pipeline` raises `EmbedderDimensionError` (a permanent misconfiguration), the ingestor catches it as a distinct branch and re-raises it as `ProblemException(status_code=500)` rather than `DependencyUnavailable` (503). The test mocks `anyio.to_thread.run_sync` to raise `EmbedderDimensionError`. |
| **Inputs** | `POST /v1/ingest` with valid document; mock pipeline raises `EmbedderDimensionError("dimension mismatch: expected 1536, got 768")` |
| **Expected Output** | HTTP 500 response; response body contains `"title": "Embedder misconfiguration"`; no `Retry-After` header |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P2 — Production gate |

#### TC-F05-002

| Field | Value |
|-------|-------|
| **ID** | TC-F05-002 |
| **AC Reference** | F-05 AC-2: Ingest with a DB connection failure returns HTTP 503 with `Retry-After` |
| **Title** | Transient DB failure during ingest surfaces as HTTP 503 with `Retry-After` header |
| **Description** | Verifies that the general `except Exception` branch (non-`EmbedderDimensionError`) still produces `DependencyUnavailable` → HTTP 503 with `Retry-After`. Confirms the guard for `EmbedderDimensionError` did not accidentally swallow or re-route transient failures. |
| **Inputs** | `POST /v1/ingest` with valid document; mock pipeline raises generic `OSError("DB connection refused")` |
| **Expected Output** | HTTP 503 response; `Retry-After` header present; response body indicates transient failure |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P2 — Production gate |

---

### F-06 — TOCTOU Race on Concurrent Identical Uploads (P2 · Concurrency · Integration)

#### TC-F06-001

| Field | Value |
|-------|-------|
| **ID** | TC-F06-001 |
| **AC Reference** | F-06 AC-1: Two simultaneous uploads of identical bytes: exactly one receives HTTP 201, the second receives HTTP 200 |
| **Title** | Two concurrent identical uploads produce exactly one 201 and one 200 |
| **Description** | Verifies the TOCTOU fix: when two coroutines upload the same document bytes concurrently, the post-ingest dedup check (reading `result["pre_existing"]`) ensures exactly one caller sees the document as new. The test uses `asyncio.gather` to fire two concurrent ingest requests and asserts the status code multiset is `{200, 201}`. The idempotent upsert in the pipeline must produce the same `doc_id` for both. |
| **Inputs** | Two concurrent `POST /v1/ingest` calls with identical PDF bytes under the same tenant; no artificial delays introduced |
| **Expected Output** | Status codes: exactly one `201 Created` and exactly one `200 OK`; both responses carry the same `doc_id` |
| **Assigned Agent** | integration-testing-engineer |
| **Priority** | P2 — Production gate |

#### TC-F06-002

| Field | Value |
|-------|-------|
| **ID** | TC-F06-002 |
| **AC Reference** | F-06 AC-2: Load test with 10 concurrent identical uploads: all return either 200 or 201, with exactly 1 returning 201 |
| **Title** | Ten concurrent identical uploads produce exactly one 201 and nine 200 responses |
| **Description** | Extends TC-F06-001 to higher concurrency (10 goroutines) to stress-test the dedup path. Asserts that status code distribution is exactly `{201: 1, 200: 9}`, confirming no race permits more than one 201. |
| **Inputs** | Ten concurrent `POST /v1/ingest` calls with identical PDF bytes under the same tenant |
| **Expected Output** | Status codes: exactly one `201 Created`; nine `200 OK`; all responses carry the same `doc_id` |
| **Assigned Agent** | integration-testing-engineer |
| **Priority** | P2 — Production gate |

---

### F-07 — Fallback-only Document Triggers Hallucinated Answer (P2 · Integration)

#### TC-F07-001

| Field | Value |
|-------|-------|
| **ID** | TC-F07-001 |
| **AC Reference** | F-07 AC-1+2: A `/v1/answer` request targeting a `fallback_only=True` document must NOT return a hallucinated answer; either a clear 422 error or a whole-document RAG response is returned |
| **Title** | `/v1/answer` on a fallback-only document returns 422 (not a hallucinated answer) |
| **Description** | Verifies that when `doc_record.fallback_only=True`, the answer endpoint raises `validation_error` (HTTP 422) before invoking the router or generation adapter. The test inserts a document record with `fallback_only=True` and issues a `/v1/answer` request targeting that document. The generation adapter must not be called (assert call count == 0). |
| **Inputs** | `POST /v1/answer` with `document_ids=["<fallback-only-doc>"]`; document record has `fallback_only=True` in the DB |
| **Expected Output** | HTTP 422; response body contains `"field": "document_id"` and `"message": "fallback-only document"`; generation adapter is never invoked |
| **Assigned Agent** | integration-testing-engineer |
| **Priority** | P2 — Production gate |

---

### F-08 — `gather` Without `return_exceptions=True` Leaks Sessions (P2 · Concurrency · Integration)

#### TC-F08-001

| Field | Value |
|-------|-------|
| **ID** | TC-F08-001 |
| **AC Reference** | F-08 AC-1+2: DB error on one `_route_one` call allows other coroutines to complete and close sessions; integration test verifies no session leak |
| **Title** | DB error on one `_route_one` sibling does not leak SQLAlchemy sessions from other siblings |
| **Description** | Verifies `asyncio.gather(..., return_exceptions=True)` in the router. The test mocks `get_sections` for one document to raise `SQLAlchemyError` while the other two complete normally. After the request, the test asserts that the async session pool connection count is identical to before the request (no leaked connections). Also asserts that the exception from the failing document is surfaced to the caller. |
| **Inputs** | `POST /v1/answer` with `document_ids=["doc-good-1", "doc-fail", "doc-good-2"]`; mock `get_sections("doc-fail")` raises `SQLAlchemyError`; track pool connection count before and after |
| **Expected Output** | Session pool connection count unchanged after request; exactly one `SQLAlchemyError` surfaced; "doc-good-1" and "doc-good-2" coroutines complete their `__aexit__` paths |
| **Assigned Agent** | integration-testing-engineer |
| **Priority** | P2 — Production gate |

---

### F-09 — Over-page Guard Fires After Expensive DB Queries (P3 · Unit)

#### TC-F09-001

| Field | Value |
|-------|-------|
| **ID** | TC-F09-001 |
| **AC Reference** | F-09 AC-1: `GET /v1/documents?page=10001` returns 422 without executing any DB query |
| **Title** | `page=10001` is rejected at query-parameter validation before any DB call |
| **Description** | Verifies the `Query(ge=1, le=10_000)` constraint rejects `page=10001` via FastAPI/Pydantic parameter validation before the request handler body executes. The test mocks `store.list_documents` and asserts it is never called. |
| **Inputs** | `GET /v1/documents?page=10001` with valid authentication headers |
| **Expected Output** | HTTP 422; `store.list_documents` not called (mock call count == 0) |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P3 — Next-sprint gate |

#### TC-F09-002

| Field | Value |
|-------|-------|
| **ID** | TC-F09-002 |
| **AC Reference** | F-09 AC-2: `GET /v1/documents?page=10000` executes the DB query normally |
| **Title** | `page=10000` (boundary value) passes validation and executes the DB query |
| **Description** | Verifies that the upper bound is inclusive at 10,000: a request with `page=10000` passes parameter validation and reaches `store.list_documents`. This is the boundary value test for the `le=10_000` constraint. |
| **Inputs** | `GET /v1/documents?page=10000` with valid authentication headers; mock `store.list_documents` returns empty result set |
| **Expected Output** | HTTP 200 (or 200 with empty list); `store.list_documents` called exactly once with `page=10000` |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P3 — Next-sprint gate |

---

### F-10 — `event: final` Missing Before `event: error` (P3 · Unit)

#### TC-F10-001

| Field | Value |
|-------|-------|
| **ID** | TC-F10-001 |
| **AC Reference** | F-10 AC-1+2+3: Citation panel rendered when generation fails mid-stream; `event: final` always before `event: error`; unit test asserts event order |
| **Title** | Mid-stream generation failure emits `event: final` (with routing data) before `event: error` |
| **Description** | Verifies that when the generation adapter raises an exception after routing has completed (but during the token-streaming loop), the `_answer_stream` function yields `event: final` (containing `relevant_sections`, `fallback`, `routing_time_ms`, `rationale`, `answer=""`) before yielding `event: error`. The `event: final` payload must include the `relevant_sections` captured before streaming began. The test mocks the generation adapter's `stream()` method to yield two tokens then raise `RuntimeError("connection dropped")`. |
| **Inputs** | `POST /v1/answer` with valid query and document; mock generation adapter yields two `event: token` then raises `RuntimeError`; routing mock returns 3 sections with metadata |
| **Expected Output** | SSE event sequence (in order): `event: token` (×2), `event: final` (with `relevant_sections` length == 3, `answer=""`), `event: error`; no `event: final` after `event: error` |
| **Assigned Agent** | unit-testing-specialist |
| **Priority** | P3 — Next-sprint gate |

---

## 4. Agent Assignment Summary

| Agent | Assigned Test Cases | Total TCs | Finding Coverage |
|-------|--------------------|-----------|--------------------|
| **unit-testing-specialist** | TC-F01-001, TC-F01-002, TC-F01-003, TC-F02-001 (partial), TC-F02-003, TC-F04-001, TC-F05-001, TC-F05-002, TC-F09-001, TC-F09-002, TC-F10-001 | 11 | F-01, F-02 (partial), F-04, F-05, F-09, F-10 |
| **integration-testing-engineer** | TC-F02-001 (Option B path), TC-F03-001, TC-F06-001, TC-F06-002, TC-F07-001, TC-F08-001 | 6 | F-02 (Option B), F-03, F-06, F-07, F-08 |
| **security-testing-engineer** | TC-F01-001 (adversarial validation), TC-F02-001 (boundary), TC-F02-002 | 3 | F-01, F-02 |

> **Note on shared ownership:** TC-F01-001 and TC-F02-001 are listed under both `unit-testing-specialist` (for the functional assertion) and `security-testing-engineer` (for adversarial input validation). Each agent writes independent test implementations. The security-testing-engineer tests use adversarially crafted tokens; the unit-testing-specialist tests use synthetic mock JWTs.

**Total unique test cases: 17**

| Risk Tier | TC Count | Findings |
|-----------|---------|---------|
| P0 — Critical | 6 (TC-F01-001 → TC-F02-003) | F-01, F-02 |
| P1 — High | 2 (TC-F03-001, TC-F04-001) | F-03, F-04 |
| P2 — Medium | 7 (TC-F05-001 → TC-F08-001) | F-05, F-06, F-07, F-08 |
| P3 — Low | 3 (TC-F09-001, TC-F09-002, TC-F10-001) | F-09, F-10 |

---

## 5. Pass/Fail Gates

### 5.1 Merge Gate (P0 — blocks merge to `main`)

All of the following test cases must **PASS** with no failures or errors before a pull request from `build/rag-refinement-product` may be merged to `main`:

| TC ID | Finding | AC |
|-------|---------|-----|
| TC-F01-001 | F-01 | Empty `tenant_id` + wrong `tid` → unauthorized |
| TC-F01-002 | F-01 | Correct `tenant_id` → authenticated |
| TC-F01-003 | F-01 | `tid`-only → authenticated |
| TC-F02-001 | F-02 | No `JWT_ISSUER` → service fails/rejects |
| TC-F02-002 | F-02 | Wrong `iss` → unauthorized |
| TC-F02-003 | F-02 | Correct `iss` → authenticated |

**Merge gate criterion:** All 6 P0 test cases PASS (0 failures, 0 errors, 0 skips).

### 5.2 Production Gate (P0 + P1 — blocks production deployment)

All P0 test cases (above) **plus** all of the following must **PASS** before deployment to any environment receiving real user traffic:

| TC ID | Finding | AC |
|-------|---------|-----|
| TC-F03-001 | F-03 | `event: token` streamed; no `BadRequestError` |
| TC-F04-001 | F-04 | Scenario C ingest → `total_pages > 0` |

**Production gate criterion:** All 8 P0 + P1 test cases PASS (0 failures, 0 errors, 0 skips).

### 5.3 External Onboarding Gate (P0 + P1 + P2 — blocks first external user onboarding)

All P0 and P1 test cases (above) **plus** all of the following must **PASS** before any external users are onboarded:

| TC ID | Finding | AC |
|-------|---------|-----|
| TC-F05-001 | F-05 | Wrong dimension → HTTP 500 |
| TC-F05-002 | F-05 | DB failure → HTTP 503 |
| TC-F06-001 | F-06 | 2 concurrent identical → 1×201 + 1×200 |
| TC-F06-002 | F-06 | 10 concurrent identical → exactly 1×201 |
| TC-F07-001 | F-07 | Fallback-only doc → 422; no hallucinated answer |
| TC-F08-001 | F-08 | One `_route_one` raises SQLAlchemyError → siblings complete + sessions closed |

**External onboarding gate criterion:** All 14 P0 + P1 + P2 test cases PASS.

### 5.4 Next-Sprint Gate (P3 — informational; does not block current sprint)

| TC ID | Finding | AC |
|-------|---------|-----|
| TC-F09-001 | F-09 | `page=10001` → 422; no DB query |
| TC-F09-002 | F-09 | `page=10000` → normal response |
| TC-F10-001 | F-10 | Mid-stream failure → `event: final` before `event: error` |

**Next-sprint gate criterion:** All 3 P3 test cases PASS before end of next sprint.

### 5.5 Regression Definition

A regression is defined as any test case that **PASSED** in a previous CI run and **FAILS** or **ERRORS** in a subsequent run after a code change. Regressions on P0 or P1 test cases immediately revert to blocking merge/production gates regardless of the sprint in which the original fix was applied.

---

## 6. Coverage Targets

### 6.1 Branch Coverage

**Target: 100% branch coverage on all 10 changed files** (as listed in Section 1.1).

| File | Minimum Branch Coverage | Rationale |
|------|------------------------|-----------|
| `backend/app/security/auth.py` | 100% | P0 security — every decision path must be exercised |
| `backend/app/settings.py` | 100% | P0 security — `JWT_ISSUER` absence branch must fire |
| `backend/app/adapters/generation.py` | 100% | P1 operational — `thinking` parameter path must be exercised |
| `ingestion/pipeline.py` | 100% | P1 correctness — fallback and normal branches must both fire |
| `backend/app/adapters/ingestor.py` | 100% | P1/P2 — `EmbedderDimensionError` branch + TOCTOU fix paths |
| `backend/app/adapters/router.py` | 100% | P2 — `return_exceptions=True` path + fallback detection |
| `backend/app/api/documents.py` | 100% | P3 — `le=10_000` validation path |
| `backend/app/api/answer.py` | 100% | P2/P3 — fallback-only detection + `event: final` before `event: error` |

### 6.2 Statement Coverage

100% statement coverage is required on all 10 changed files. This is a floor; branch coverage is the primary metric.

### 6.3 Security-Specific Coverage

In addition to branch/statement coverage, the security-testing-engineer must verify:

- All three IDOR attack vectors from F-01 are exercised with real (non-mocked) PyJWT token decoding.
- The `JWT_ISSUER=None` bypass is confirmed against PyJWT >= 2.13 and < 3.0 (the pinned range).
- Token forgery with a valid secret but wrong issuer is exercised (TC-F02-002).

### 6.4 Concurrency Coverage

The integration-testing-engineer must verify:

- Both TC-F06-001 (2 goroutines) and TC-F06-002 (10 goroutines) run under `asyncio` with no artificial serialization (`asyncio.sleep(0)` yields between requests to maximize interleaving).
- TC-F08-001 exercises the `return_exceptions=True` branch with at least 3 concurrent `_route_one` calls.

### 6.5 Measurement Tools

| Tool | Scope |
|------|-------|
| `pytest-cov` with `--cov-branch` | All 10 changed files |
| `coverage.py` HTML report | Reviewed by test-management-agent before gate sign-off |
| `pytest-asyncio` | All async/concurrency test cases |
| `pytest-anyio` | Integration with anyio-based code paths in `ingestor.py` |

---

## 7. Test Environment Requirements

| Requirement | Detail |
|------------|--------|
| Python version | Match project pinning (see `pyproject.toml`) |
| PyJWT version | `>=2.13.0,<3.0` (pinned range — must not test with PyJWT 3.x) |
| Anthropic SDK | Stubbed for F-03; real client optional if API key present in CI |
| SQLAlchemy async | In-memory SQLite with `aiosqlite` for unit/integration tests |
| FastAPI TestClient | `httpx.AsyncClient` with `ASGITransport` for all HTTP-level assertions |
| `anyio` backend | `asyncio` (default) |

---

## 8. Test Deliverables

| Deliverable | Owner | Gate |
|------------|-------|------|
| Unit test file for F-01, F-02, F-04, F-05, F-09, F-10 | unit-testing-specialist | Merge gate |
| Integration test file for F-03, F-06, F-07, F-08 | integration-testing-engineer | Production gate |
| Security test file (adversarial JWT vectors) for F-01, F-02 | security-testing-engineer | Merge gate |
| Coverage report (HTML + XML) for all 10 files | unit-testing-specialist | All gates |
| Defect report for any AC not met by the implementation | test-management-agent | All gates |

---

## 9. Schedule and Dependencies

| Phase | Activity | Dependency |
|-------|----------|-----------|
| D.1 (current) | Test plan authored and approved | Phase C gate PASSED |
| D.2 | Unit tests written (F-01, F-02, F-04, F-05, F-09, F-10) | TODO-04 approved |
| D.3 | Integration + concurrency tests written (F-03, F-06, F-07, F-08) | TODO-04 approved |
| D.4 | Security adversarial tests written (F-01, F-02) | TODO-04 approved |
| D.5 | All tests executed; coverage reports generated | D.2, D.3, D.4 complete |
| D.6 | Gate sign-off by test-management-agent | D.5 complete, all gates met |

---

## 10. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Anthropic API unavailable in CI for F-03 | Medium | High | Provide a deterministic stub that validates `thinking` dict shape and returns mocked token stream |
| Concurrency tests flaky due to `asyncio` scheduling non-determinism | Medium | Medium | Use `asyncio.gather` with controlled mock delays; run F-06 suite 10 times in CI and require 100% pass rate |
| PyJWT version drift in CI installs different version outside pinned range | Low | High | Pin `PyJWT>=2.13.0,<3.0` in test requirements; assert `jwt.__version__` at test session start |
| Session pool leak detection unreliable if pool is shared across tests | Medium | Medium | Isolate F-08 in a dedicated test session with a fresh engine; assert `engine.pool.checkedout() == 0` after teardown |
| `EmbedderDimensionError` not importable if embedder module is not installed | Low | Medium | Add `ingestion.embedder` to test dependencies; mock the import in unit test if package not available |
