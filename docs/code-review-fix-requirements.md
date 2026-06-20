# Code Review — Fix Requirements

**Branch:** `build/rag-refinement-product`
**Review Date:** 2026-06-06
**Total Findings:** 10 (3 Security · 4 Correctness · 2 Resource/Efficiency · 1 UX)

Findings are ranked most-severe first. Each entry includes the exact file + line, a description of the defect, and a concrete fix specification. Implement and test each fix before merging to `main`.

---

## F-01 · SECURITY · CRITICAL

**File:** `backend/app/security/auth.py:232`
**Title:** Cross-tenant IDOR via truthiness check on `tenant_id` JWT claim

### Defect

```python
# CURRENT — WRONG
tenant_id = claims.get("tenant_id") or claims.get("tid")
```

When a JWT carries `"tenant_id": ""` (empty string) alongside `"tid": "tenant-B"`, Python's `or` discards the explicit empty value and substitutes `"tenant-B"`. The caller is authenticated as Tenant B even though their token declared an empty `tenant_id`. The `if not tenant_id` guard on the next line does not catch this because `"tenant-B"` is truthy.

### Fix

Use key-presence checks instead of truthiness:

```python
# FIX — check key presence, not value truthiness
if "tenant_id" in claims and claims["tenant_id"]:
    tenant_id: object = claims["tenant_id"]
elif "tid" in claims and claims["tid"]:
    tenant_id = claims["tid"]
else:
    tenant_id = None

if not subject or not tenant_id:
    raise unauthorized("Bearer token is missing required claims.")
```

### Acceptance Criteria

- A JWT with `{"tenant_id": "", "tid": "other-tenant"}` must raise `unauthorized`, not authenticate as `"other-tenant"`.
- A JWT with `{"tenant_id": "correct-tenant"}` must authenticate as `"correct-tenant"`.
- A JWT with only `{"tid": "correct-tenant"}` (no `tenant_id` key) must authenticate as `"correct-tenant"`.
- Unit test covering all three cases.

---

## F-02 · SECURITY · HIGH

**File:** `backend/app/security/auth.py:209` · `backend/app/settings.py:58`
**Title:** `JWT_ISSUER` defaults to `None`, disabling issuer validation in PyJWT 2.x

### Defect

```python
# settings.py
jwt_issuer: str | None = Field(default=None, alias="JWT_ISSUER")

# auth.py — issuer=None skips iss validation entirely in PyJWT >=2.13
claims = jwt.decode(
    token, settings.jwt_secret, algorithms=[settings.jwt_algorithm],
    audience=settings.jwt_audience,
    issuer=settings.jwt_issuer,   # None → no validation
    options=options,
)
```

PyJWT 2.x (pinned `>=2.13.0,<3.0`) silently skips `iss` claim validation when `issuer=None`. A JWT from any other service sharing the same `JWT_SECRET` (e.g., an internal SSO service) is accepted.

### Fix

**Option A (preferred):** Make `JWT_ISSUER` required at startup; fail fast if unset.

```python
# settings.py
jwt_issuer: str = Field(alias="JWT_ISSUER")  # no default — must be set
```

**Option B (defensive):** Guard before decode so an unconfigured issuer is treated as disabled JWT auth:

```python
# auth.py
if settings.jwt_issuer is None:
    raise unauthorized("JWT issuer is not configured; bearer auth is disabled.")
```

Either option must be deployed alongside an operator runbook update documenting the required `JWT_ISSUER` environment variable.

### Acceptance Criteria

- Without `JWT_ISSUER` set, the service must refuse to start (Option A) or reject all bearer tokens (Option B).
- A JWT with a wrong or missing `iss` claim must raise `unauthorized` when `JWT_ISSUER` is set.
- A JWT with the correct `iss` claim must authenticate successfully.

---

## F-03 · CORRECTNESS · HIGH (Operational Blocker)

**File:** `backend/app/adapters/generation.py:127`
**Title:** `thinking={"type": "adaptive"}` is missing `budget_tokens`; every `/v1/answer` request fails

### Defect

```python
# CURRENT — API rejects this form
async with client.messages.stream(
    model=self._model,
    max_tokens=self._max_tokens,
    thinking={"type": "adaptive"},   # missing required budget_tokens
    ...
) as stream:
```

The Anthropic extended-thinking API requires `{"type": "enabled", "budget_tokens": N}`. The bare `{"type": "adaptive"}` form is rejected with a `400 BadRequestError` at runtime. This exception is not `DependencyUnavailable`, so it falls into the bare `except Exception` branch in `_answer_stream`, causing every `/v1/answer` SSE stream to immediately yield `event: error` with `code=INTERNAL_ERROR`.

### Fix

```python
# generation.py — use the documented thinking parameter form
async with client.messages.stream(
    model=self._model,
    max_tokens=self._max_tokens,
    thinking={"type": "enabled", "budget_tokens": self._thinking_budget_tokens},
    ...
) as stream:
```

Add `thinking_budget_tokens: int` to `ClaudeGenerationLLM.__init__` (default: `5000`), sourced from `Settings.generation_thinking_budget_tokens`.

If extended thinking is not desired, remove the `thinking` parameter entirely.

### Acceptance Criteria

- `/v1/answer` must stream at least one `event: token` for a valid query.
- Integration test with a real (or stubbed) Anthropic client must not raise `BadRequestError`.

---

## F-04 · CORRECTNESS · HIGH

**File:** `ingestion/pipeline.py:189` + `backend/app/adapters/ingestor.py:215`
**Title:** `IngestResult.as_dict()` omits `total_pages`; Scenario C documents always report `total_pages=0`

### Defect

```python
# pipeline.py — IngestResult.as_dict() returns 5 keys, no total_pages
def as_dict(self) -> dict[str, Any]:
    return {
        "doc_id": self.doc_id,
        "toc": self.toc,
        "section_rows_written": self.section_rows_written,
        "chunks_upserted": self.chunks_upserted,
        "fallback_only": self.fallback_only,
        # total_pages is NOT here
    }

# ingestor.py — derives total_pages from toc (empty for Scenario C)
def _total_pages(toc: list[dict[str, Any]]) -> int:
    return max((int(entry.get("page_end", 0)) for entry in toc), default=0)
    # returns 0 when toc is []
```

For Scenario C (fallback-only), `toc=[]` so `_total_pages([])` returns `0`. The pipeline writes the correct `parsed.page_count` to the DB but does not surface it in the result dict. The `IngestResponse` and all downstream reads carry `total_pages=0`.

### Fix

**Step 1** — Add `total_pages` to `IngestResult` and `as_dict()`:

```python
# pipeline.py
@dataclass
class IngestResult:
    doc_id: str
    toc: list[dict[str, Any]] = field(default_factory=list)
    section_rows_written: int = 0
    chunks_upserted: int = 0
    fallback_only: bool = False
    total_pages: int = 0          # ADD THIS

    def as_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "toc": self.toc,
            "section_rows_written": self.section_rows_written,
            "chunks_upserted": self.chunks_upserted,
            "fallback_only": self.fallback_only,
            "total_pages": self.total_pages,   # ADD THIS
        }
```

**Step 2** — Pass `parsed.page_count` into `IngestResult` at both call sites in `ingest_document`:

```python
# pipeline.py — both the fallback_only branch and the normal branch
return IngestResult(
    doc_id=doc_id,
    toc=toc_dicts,
    section_rows_written=section_rows_written,
    chunks_upserted=chunks_upserted,
    fallback_only=fallback_only_flag,
    total_pages=parsed.page_count,   # ADD THIS
).as_dict()
```

**Step 3** — Update `ingestor.py` to read `total_pages` from the result dict instead of `_total_pages(toc)`:

```python
# ingestor.py
total_pages = int(result.get("total_pages") or 0)
# Remove _total_pages() helper — it is no longer needed
```

### Acceptance Criteria

- `IngestResponse.total_pages` must equal the PDF's actual page count for Scenario A, B, and C documents.
- Unit test: a Scenario C ingest returns `total_pages > 0` when the PDF has pages.

---

## F-05 · CORRECTNESS · MEDIUM

**File:** `backend/app/adapters/ingestor.py:202`
**Title:** Permanent pipeline errors (e.g. `EmbedderDimensionError`) are wrapped as retryable 503

### Defect

```python
# ingestor.py
try:
    result, deduplicated = await anyio.to_thread.run_sync(self._run_pipeline, doc)
except DependencyUnavailable:
    raise
except Exception as exc:
    raise DependencyUnavailable(f"Ingestion pipeline failed: {exc}") from exc
    # EmbedderDimensionError (ValueError) → DependencyUnavailable → 503 Retry-After:5
```

`EmbedderDimensionError` signals a permanent misconfiguration (wrong embedding dimension). Wrapping it as `DependencyUnavailable` causes clients to retry indefinitely and hides the misconfiguration from monitoring (503s look like transient outages, not permanent failures).

### Fix

Distinguish permanent pipeline errors from transient dependency failures:

```python
# ingestor.py
from ingestion.embedder import EmbedderDimensionError

try:
    result, deduplicated = await anyio.to_thread.run_sync(self._run_pipeline, doc)
except DependencyUnavailable:
    raise
except EmbedderDimensionError as exc:
    # Permanent misconfiguration — not retryable
    raise ProblemException(
        status_code=500,
        title="Embedder misconfiguration",
        detail=str(exc),
    ) from exc
except Exception as exc:
    raise DependencyUnavailable(f"Ingestion pipeline failed: {exc}") from exc
```

Add a similar guard for `ValueError` (empty `tenant_id`) and `AssertionError` (chunker cross-section violation) if those should also surface as 500 rather than 503.

### Acceptance Criteria

- Ingest with a misconfigured embedder (wrong dimension) returns HTTP 500, not 503.
- Ingest with a DB connection failure returns HTTP 503 with `Retry-After`.
- Unit test for each branch.

---

## F-06 · CORRECTNESS · MEDIUM

**File:** `backend/app/adapters/ingestor.py:156`
**Title:** TOCTOU race in `_run_pipeline`: concurrent identical uploads both receive `deduplicated=False` / HTTP 201

### Defect

```python
# ingestor.py — _run_pipeline runs in a worker thread (no capacity limit)
def _run_pipeline(self, doc: IngestInput) -> tuple[dict[str, Any], bool]:
    existing = self._section_store.find_doc_id_by_hash(doc.tenant_id, content_hash(doc.data))
    result = self._ingest(doc, ...)   # separate DB transaction
    return result, existing is not None   # deduplicated based on pre-ingest state
```

Two concurrent uploads of identical bytes both call `find_doc_id_by_hash` before either's `_ingest` completes. Both see `existing=None`, both return `deduplicated=False`, both get HTTP 201. The DB state is correct (idempotent upsert), but the HTTP contract is violated: re-uploading identical content must return HTTP 200 per the agreed contract.

### Fix

Move the dedup check to **after** the ingest call, reading the deterministic `doc_id` from the result to determine if the upload was new or pre-existing:

```python
# ingestor.py
def _run_pipeline(self, doc: IngestInput) -> tuple[dict[str, Any], bool]:
    result = self._ingest(doc, ...)
    # doc_id is deterministic from (tenant_id, content_hash)
    # If the doc already existed before this ingest, upsert_document will have
    # returned the same doc_id — the pipeline already performs its own dedup check
    # and sets result["pre_existing"] when applicable.
    deduplicated = bool(result.get("pre_existing", False))
    return result, deduplicated
```

**Preferred alternative:** Add a `pre_existing: bool` field to `IngestResult` that `ingest_document` in `pipeline.py` sets based on the `existing` check at **line 375** (which already has the correct pre-ingest value). The pipeline-level check runs inside a single synchronous call, is not subject to the race, and can be trusted.

### Acceptance Criteria

- Two simultaneous uploads of identical bytes: exactly one receives HTTP 201, the second receives HTTP 200.
- Load test with 10 concurrent identical uploads: all return either 200 or 201, with exactly 1 returning 201.

---

## F-07 · CORRECTNESS · MEDIUM

**File:** `backend/app/adapters/router.py:229`
**Title:** Fallback-only (Scenario C) documents have no section rows; router is called with empty TOC and LLM generates an answer from the empty-context sentinel

### Defect

For `fallback_only=True` documents, `replace_sections` writes zero rows. `_route_one` calls `get_sections` → `[]`, builds `toc=[]`, then invokes `router.route` with an empty TOC. The router returns `relevant_sections=[]`, `fallback=True`. `stream_answer` is called with `sections=[]` and the generation LLM receives only the empty-context sentinel string (`"(No section met the routing threshold…)"`), not the document's actual content. The endpoint returns HTTP 200 with a hallucinated or non-committal answer.

### Fix

Detect `fallback_only=True` documents before routing and return a clear error (or activate the whole-document RAG path if that is the intended design):

```python
# answer.py — after get_document, before calling router.route
if doc_record.fallback_only:
    # Option A: Return a 422 so the caller knows section routing is unavailable
    raise validation_error(
        detail="This document was indexed in fallback mode and does not support section-level routing.",
        errors=[{"field": "document_id", "message": "fallback-only document"}],
    )
    # Option B: Route to a whole-document RAG path (if implemented)
```

The design decision (Option A vs B) must be confirmed with the product owner before implementation.

### Acceptance Criteria

- A `/v1/answer` request targeting a `fallback_only=True` document must NOT return a hallucinated answer.
- Either a clear 422 error or a whole-document RAG response is returned, as agreed.

---

## F-08 · RESOURCE · MEDIUM

**File:** `backend/app/adapters/router.py:274`
**Title:** `asyncio.gather` without `return_exceptions=True` cancels sibling coroutines on first failure, leaking SQLAlchemy async sessions

### Defect

```python
# router.py
results = await asyncio.gather(
    *[self._route_one(...) for doc_id in document_ids]
)
# Default return_exceptions=False: first DependencyUnavailable cancels siblings.
# Cancelled _route_one coroutines may not complete async with session_factory().__aexit__,
# leaking connections from the async pool.
```

Under intermittent DB errors with multi-document requests, pool connections are leaked until GC collects the cancelled coroutines. Sustained load can exhaust the pool.

### Fix

```python
# router.py
raw = await asyncio.gather(
    *[self._route_one(...) for doc_id in document_ids],
    return_exceptions=True,
)
# Surface the first exception if any; all coroutines complete their cleanup.
errors = [r for r in raw if isinstance(r, BaseException)]
if errors:
    raise errors[0]
results = raw  # all are (list[RoutedSection], Mapping) tuples
```

### Acceptance Criteria

- A DB error on one `_route_one` call must still allow the other coroutines to complete and close their sessions.
- Integration test: mock one `get_sections` call to raise `SQLAlchemyError`; verify no session leak (pool count unchanged after the request).

---

## F-09 · EFFICIENCY · LOW

**File:** `backend/app/api/documents.py:261`
**Title:** Over-page guard fires after `list_documents` executes both COUNT and OFFSET SELECT queries

### Defect

```python
# documents.py
records, total_count = await store.list_documents(   # runs COUNT + OFFSET SELECT
    principal.tenant_id, page, page_size, domain
)
total_pages = math.ceil(total_count / page_size)
if total_count > 0 and page > total_pages:           # guard after DB work
    raise validation_error(...)
```

`page` cannot be validated without the total count, so a pre-DB check is impossible. However, the OFFSET query with an adversarial `page=1000000` performs an expensive sequential scan. An authenticated caller at the 60 req/min rate limit can sustain 60 high-OFFSET DB scans per minute.

### Fix

Add a hard upper bound on `page` at the query parameter level so Pydantic/FastAPI rejects obviously invalid values before hitting the DB:

```python
# documents.py
page: int = Query(default=1, ge=1, le=10_000)   # upper bound prevents OFFSET amplification
```

Additionally, ensure the `(tenant_id, tombstoned_at, created_at, doc_id)` index exists in the DB migration so the OFFSET query can use an index scan rather than a heap scan.

### Acceptance Criteria

- `GET /v1/documents?page=10001` returns 422 without executing any DB query.
- `GET /v1/documents?page=10000` executes the DB query normally.

---

## F-10 · UX · LOW

**File:** `backend/app/api/answer.py:142`
**Title:** Error path in `_answer_stream` yields `event: error` but not `event: final`; routing citations are lost on mid-stream failures

### Defect

```python
# answer.py — _answer_stream
except Exception:
    problem = internal_error()
    problem.query_id = query_id
    yield _sse_event("error", problem.to_problem())
    # No event: final is yielded — turn.final remains null in the frontend.
    # AnswerInsights (CitationCards, ConfidenceMeter) are gated on turn.final !== null
    # and are never rendered, even when routing succeeded before the failure.
```

### Fix

Emit `event: final` with an empty/partial payload before the error so the frontend can render whatever routing information was collected:

```python
# answer.py — _answer_stream
except Exception:
    problem = internal_error()
    problem.query_id = query_id
    # Emit a minimal final so citation panel renders what routing found
    yield _sse_event("final", AnswerFinalEvent(
        query_id=query_id,
        relevant_sections=sections,   # sections captured before streaming started
        fallback=decision.fallback,
        routing_time_ms=decision.routing_time_ms,
        rationale=decision.rationale,
        answer="",
    ).model_dump())
    yield _sse_event("error", problem.to_problem())
```

This requires `decision` and `sections` to be in scope at the `except` block. Restructure `_answer_stream` to capture them before entering the token loop.

### Acceptance Criteria

- When the Anthropic API drops the connection mid-stream, the frontend renders the citation panel with the sections that were routed before the error.
- `event: final` is always emitted before `event: error`, never after.
- Unit test: mock the generation adapter to raise mid-stream; assert both `final` and `error` events are emitted in that order.

---

## Summary Table

| ID | File | Line | Severity | Category | Status |
|----|------|------|----------|----------|--------|
| F-01 | `backend/app/security/auth.py` | 232 | 🔴 CRITICAL | Security | Open |
| F-02 | `backend/app/security/auth.py` | 209 | 🔴 HIGH | Security | Open |
| F-03 | `backend/app/adapters/generation.py` | 127 | 🔴 HIGH | Operational | Open |
| F-04 | `ingestion/pipeline.py` + `ingestor.py` | 189 | 🟠 HIGH | Correctness | Open |
| F-05 | `backend/app/adapters/ingestor.py` | 202 | 🟡 MEDIUM | Correctness | Open |
| F-06 | `backend/app/adapters/ingestor.py` | 156 | 🟡 MEDIUM | Correctness | Open |
| F-07 | `backend/app/adapters/router.py` | 229 | 🟡 MEDIUM | Correctness | Open |
| F-08 | `backend/app/adapters/router.py` | 274 | 🟡 MEDIUM | Resource | Open |
| F-09 | `backend/app/api/documents.py` | 261 | 🟢 LOW | Efficiency | Open |
| F-10 | `backend/app/api/answer.py` | 142 | 🟢 LOW | UX | Open |

**Merge gate:** F-01, F-02, F-03 must be fixed before any production deployment. F-04 through F-08 must be fixed before the first external user is onboarded. F-09 and F-10 can be addressed in the next sprint.
