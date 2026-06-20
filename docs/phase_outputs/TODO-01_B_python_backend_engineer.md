# Python Backend Engineer — Code-Review Fix Summary
## Branch: build/rag-refinement-product
## Date: 2026-06-07
## Spec: docs/code-review-fix-requirements.md

---

## Executive Summary

All 10 findings from the code-review spec were applied in severity order (F-01 through
F-10). Two findings (F-01, F-02) were discovered to have been pre-applied in a previous
fix round and required no new edits. The remaining eight were implemented from scratch.
Three test fixture files were also updated to keep the test suite compatible with the
now-required `JWT_ISSUER` field.

---

## Fix Log

### F-01: JWT Claim Truthiness vs Key-Presence (IDOR) — PRE-APPLIED
**File:** `backend/app/security/auth.py`
**Status:** Already applied. `_resolve_jwt_principal` uses key-presence checks
(`"tenant_id" in claims and claims["tenant_id"]`) not truthiness-only tests.
No edit needed.

### F-02: JWT Issuer Validation Silent Skip — PRE-APPLIED
**File:** `backend/app/settings.py`, `backend/app/security/auth.py`
**Status:** Already applied. `jwt_issuer: str = Field(alias="JWT_ISSUER")` has no
default, making it a required env-var that causes startup failure if absent. The
`_decode_jwt` function already passes `issuer=settings.jwt_issuer` unconditionally.
No edit needed.

### F-03: Extended-Thinking Budget Hardcoded to "adaptive"
**Files edited:**
- `backend/app/adapters/generation.py`
- `backend/app/api/dependencies.py`
- `backend/app/settings.py`

**Changes:**
- Added `generation_thinking_budget_tokens: int = Field(default=5000, alias="GENERATION_THINKING_BUDGET_TOKENS")` to `Settings`.
- Added `DEFAULT_THINKING_BUDGET_TOKENS = 5000` constant and updated `ClaudeGenerationLLM.__init__` to accept `thinking_budget_tokens: int` stored as `self._thinking_budget_tokens`.
- Changed `stream_answer` to use `thinking={"type": "enabled", "budget_tokens": self._thinking_budget_tokens}` (was `{"type": "adaptive"}`).
- Updated `_generation_llm_singleton()` in `dependencies.py` to pass `thinking_budget_tokens=settings.generation_thinking_budget_tokens`.

### F-04: `_total_pages()` Reads from Empty TOC (Scenario C Returns 0)
**Files edited:**
- `ingestion/pipeline.py`
- `backend/app/adapters/ingestor.py`

**Changes:**
- Added `total_pages: int = 0` and `pre_existing: bool = False` fields to the `IngestResult` dataclass.
- Updated `as_dict()` to include both new fields.
- Updated `ingest_document()` return to pass `total_pages=parsed.page_count, pre_existing=existing is not None`.
- Removed `_total_pages()` helper from `ingestor.py` entirely.
- Updated `ingest_document` in the adapter to read: `total_pages=int(result.get("total_pages") or 0)`.

### F-05: `EmbedderDimensionError` Surfaced as Generic 503
**File edited:** `backend/app/adapters/ingestor.py`

**Changes:**
- Added `from ingestion.embedder import EmbedderDimensionError` at module level.
- Added a dedicated `except EmbedderDimensionError` block (before `except Exception`) that raises `ProblemException(status_code=500, code="EMBEDDER_MISCONFIGURATION", ...)` with a local import of `ProblemException` to avoid circular-import risk.

### F-06: TOCTOU Race in Pre-Ingest Hash Dedup
**Files edited:**
- `ingestion/pipeline.py` (F-04 changes serve this too: `pre_existing` added)
- `backend/app/adapters/ingestor.py`

**Changes:**
- Removed the pre-ingest `content_hash` lookup from `_run_pipeline` in `ingestor.py`. The TOCTOU window (two concurrent uploads both seeing `existing=None`) is eliminated.
- `_run_pipeline` now reads `deduplicated = bool(result.get("pre_existing", False))` from the pipeline result, which runs the hash check inside a single synchronous call-stack context.
- Removed unused `content_hash` from the import in `ingestor.py`.

### F-07: Fallback-Only Document Routed Without Error
**File edited:** `backend/app/api/answer.py`

**Changes:**
- Added a `fallback_only` guard in `answer_query` immediately after the `get_document` call:
  ```python
  if document.fallback_only:
      raise validation_error(
          detail="This document was indexed in fallback mode and does not support section-level routing.",
          errors=[{"field": "document_id", "message": "fallback-only document"}],
      )
  ```
- This raises HTTP 422 (Option A per agreed contracts) before the router is called.
- Added `validation_error` to the imports from `backend.app.errors`.

### F-08: `asyncio.gather` Session Leak on Partial Failure
**File edited:** `backend/app/adapters/router.py`

**Changes:**
- Changed the `asyncio.gather` call in `RouterModuleAdapter.route` to use `return_exceptions=True`.
- Added post-gather error inspection:
  ```python
  errors = [r for r in raw if isinstance(r, BaseException)]
  if errors:
      raise errors[0]
  results = raw
  ```
- This prevents session leaks: all coroutines complete before any exception is re-raised.

### F-09: OFFSET Amplification via Unbounded `page` Parameter
**File edited:** `backend/app/api/documents.py`

**Changes:**
- Changed `page: int = Query(default=1, ge=1)` to `page: int = Query(default=1, ge=1, le=10_000)`.
- Added comment: `# le=10_000 prevents OFFSET amplification attacks`.

### F-10: SSE Stream Emits `event: error` Without Prior `event: final`
**File edited:** `backend/app/api/answer.py`

**Changes:**
- Restructured both `except DependencyUnavailable` and `except Exception` branches in `_answer_stream` to yield an `event: final` frame (using the actual `AnswerFinalEvent` schema with `_build_citations(decision)` and `_build_routing_summary(decision)`) before yielding `event: error`.
- The `answer_parts` list is initialized before the `try` block, so partial tokens accumulated before the error are included in the partial answer on the `final` event.
- Correct schema fields used: `citations=_build_citations(decision)`, `routing=_build_routing_summary(decision)` — not the spec's sample field names which differ from the actual `AnswerFinalEvent` model.

---

## Test Fixture Updates (F-02 Compatibility)

Because `jwt_issuer` is now required (no default), three `Settings(` call sites in
health tests were updated to supply `JWT_ISSUER="test-issuer"`:

- `tests/test_health.py` line 75: `Settings(DATABASE_URL=None, QDRANT_URL=None, JWT_ISSUER="test-issuer")`
- `tests/test_health_internals.py` line 156: `Settings(database_url=None, qdrant_url=None, JWT_ISSUER="test-issuer")`
- `tests/test_health_internals.py` lines 174, 194: both `Settings(DATABASE_URL=..., QDRANT_URL=..., JWT_ISSUER="test-issuer")`

The `tests/test_backend_internals.py` file already had `JWT_ISSUER="test-issuer"` in all
`Settings(` calls and required no changes.

---

## Files Modified

| File | Findings |
|------|----------|
| `backend/app/adapters/generation.py` | F-03 |
| `backend/app/adapters/ingestor.py` | F-04, F-05, F-06 |
| `backend/app/adapters/router.py` | F-08 |
| `backend/app/api/answer.py` | F-07, F-10 |
| `backend/app/api/dependencies.py` | F-03 |
| `backend/app/api/documents.py` | F-09 |
| `backend/app/settings.py` | F-03 |
| `ingestion/pipeline.py` | F-04, F-06 |
| `tests/test_health.py` | F-02 fixture compat |
| `tests/test_health_internals.py` | F-02 fixture compat |

---

## Key Design Decisions

1. **F-01 attack vector confirmed:** `{"tenant_id": "", "tid": "victim"}` — the empty
   string truthiness check was the vulnerability; key-presence + non-empty is the fix.

2. **F-02 Option A:** `JWT_ISSUER` is a required field with no default. The service
   refuses to start without it, preventing silent issuer-bypass.

3. **F-06 TOCTOU:** Dedup signal moved to the pipeline result dict (`pre_existing` field)
   rather than a pre-ingest adapter-level hash lookup. The pipeline runs the check inside
   a single synchronous context where the database transaction prevents the race.

4. **F-07 Option A:** Fallback-only documents return HTTP 422 with a structured
   `validation_error` problem. The TODO comment notes Option B (whole-document RAG) as a
   future product decision.

5. **F-10 schema:** The spec code sample uses non-existent field names (`relevant_sections`,
   `fallback`, `routing_time_ms`, `rationale`). The actual `AnswerFinalEvent` schema uses
   `citations: list[Citation]` and `routing: RoutingSummary`. The fix uses the existing
   `_build_citations()` and `_build_routing_summary()` helpers correctly.

6. **F-05 circular import:** `ProblemException` is imported locally inside the
   `except EmbedderDimensionError` block, matching the codebase pattern for avoiding
   import-time circular dependencies between `adapters` and `errors`.
