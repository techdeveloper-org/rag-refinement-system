WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library. You must read all skills, agent definitions, examples, and references from this absolute path. Do NOT use ~/.claude/ or any default Claude install location.

# Orchestration Prompt — RAG Refinement System Bug-Fix Sprint
<!-- Generated: 2026-06-07 | Mode: Brownfield | Entry: Phase 7 | Library: v29.10.0 | KG: 254 agents, 451 skills, 49 domains, 23 math masters, 4296 edges -->

---

## YOUR TASK

Fix 10 pre-triaged bugs across the RAG Refinement System (Python/FastAPI/LangGraph/Anthropic SDK/Qdrant/PostgreSQL). The bugs are production-blocking or security-critical; they must be fixed in WSJF priority order. No new features. No refactoring beyond the stated fix. No file modifications outside the listed paths.

**Priority order (WSJF descending):**
BUG-001 → BUG-002 → BUG-005 → BUG-009 → BUG-003 → BUG-004 → BUG-006 → BUG-007 → BUG-008 → BUG-010

---

### BUG-001 · CRITICAL — Answer Endpoint Permanently Broken (Anthropic API budget_tokens > max_tokens)
- **File:** `backend/app/adapters/generation.py` lines 28–31
- **Problem:** `DEFAULT_THINKING_BUDGET_TOKENS = 5000` exceeds `DEFAULT_MAX_TOKENS = 4096`. Anthropic API contract requires `budget_tokens < max_tokens`. Every POST /v1/answer fails with 400 Bad Request from the API.
- **Fix:** Raise `DEFAULT_MAX_TOKENS` to `8192`. Update `Settings.generation_thinking_budget_tokens` default in `backend/app/settings.py` to remain 5000 (now valid since 5000 < 8192). Verify both constants are consistent.
- **Acceptance Criteria:** POST /v1/answer with valid credentials and a known document succeeds and streams tokens.

---

### BUG-002 · CRITICAL — Qdrant Returns All Tenant Chunks on Empty Section List (IDOR Risk)
- **File:** `db/qdrant_bootstrap.py` line 182
- **Problem:** `tenant_section_filter(tenant_id, section_ids)` builds `MatchAny(any=list(section_ids))`. When `section_ids=[]` (router returned no sections — fallback mode), Qdrant receives `MatchAny(any=[])` which may be treated as "no filter", returning every chunk for that tenant. This is a cross-section IDOR within a tenant.
- **Fix:** Add guard before building the filter:
  ```python
  if not section_ids:
      return None  # callers must check for None and return []
  ```
  Update all callers: if `tenant_section_filter` returns `None`, skip the Qdrant query and return an empty result list immediately (do NOT call `qdrant.search()` with a None filter).
- **AGREED CONTRACT (database-engineer ↔ python-backend-engineer):** Callers pattern: `if tenant_filter is None: return []`
- **Acceptance Criteria:** Retrieval with zero routed sections returns an empty result list, not the tenant's entire corpus.

---

### BUG-003 · HIGH — replace_sections with Empty List Permanently Deletes All Sections
- **File:** `backend/app/adapters/stores.py` line 120
- **Problem:** `replace_sections(doc_id, rows=[])` executes `DELETE FROM sections WHERE doc_id = ?` and commits without inserting anything. A TOC extraction failure silently erases all section data.
- **Fix:** Add pre-condition guard at the top of the function:
  ```python
  if not rows:
      return 0  # nothing to replace; do not DELETE
  ```
- **Acceptance Criteria:** Calling `replace_sections(doc_id, [])` leaves existing sections untouched and returns 0.

---

### BUG-004 · HIGH — Ingestion Crashes on PDF Sections with Blank Titles
- **File:** `ingestion/toc_extractor.py` line 203
- **Problem:** Expression `int(title and level)` short-circuits to `int("")` when `title` is an empty string, raising `ValueError`. Any PDF with a blank-title TOC section is completely unindexable.
- **Fix:** Replace the expression with:
  ```python
  level=max(1, level),
  ```
- **Acceptance Criteria:** A PDF with one or more blank-title sections ingests successfully. The blank title is preserved as an empty string in the TOC output.

---

### BUG-005 · HIGH — Service Fails to Start When JWT_ISSUER Env Var Is Not Set
- **File:** `backend/app/settings.py` line 58
- **Problem:** `jwt_issuer: str = Field(alias="JWT_ISSUER")` has no default and is not Optional. pydantic-settings raises `ValidationError` at startup when JWT_ISSUER is absent — even for API-key-only deployments.
- **Fix:**
  ```python
  jwt_issuer: str | None = Field(default=None, alias="JWT_ISSUER")
  ```
  Update `_decode_jwt` to conditionally validate issuer:
  ```python
  if settings.jwt_issuer is not None:
      # validate 'iss' claim against settings.jwt_issuer
  ```
- **AGREED CONTRACT (python-backend-engineer ↔ auth-security-specialist):** `_decode_jwt` options dict: `{"verify_iss": settings.jwt_issuer is not None}`. JWT library call signature stays the same.
- **Acceptance Criteria:** Service starts without JWT_ISSUER in environment. JWT auth with issuer claim still validates correctly when JWT_ISSUER is set.

---

### BUG-006 · HIGH — Router LLM Errors Bypass the Deterministic Fallback Path
- **File:** `router/llm.py` line 111
- **Problem:** `await client.messages.create(...)` has no exception handling. Anthropic SDK errors (`RateLimitError`, `APIConnectionError`, `AuthenticationError`) are not `ValueError` subclasses, so they escape `_node_route`'s `except ValueError` block without setting `state['fallback'] = True`, crashing the router.
- **Fix:** Define `RouterLLMError` exception. Wrap the API call:
  ```python
  try:
      response = await client.messages.create(...)
  except Exception as exc:
      raise RouterLLMError("LLM call failed") from exc
  ```
  In `_node_route`, catch `RouterLLMError` alongside `ValueError` and set `state['fallback'] = True`.
- **Acceptance Criteria:** Simulated Anthropic API rate-limit error causes the router to return a fallback `RouterDecision` (not a crash). Caller receives 200 with `fallback=true`.

---

### BUG-007 · MEDIUM — DB Outages Return 500 Instead of 503 on Read Endpoints
- **Files:** `backend/app/api/documents.py` lines 262, 307, 338, 341, 422, 425 · `backend/app/api/routing.py` line 80 · `backend/app/api/answer.py` line 199
- **Problem:** Six read endpoints (`listDocuments`, `getDocument`, `getDocumentToc`, `exportDocumentData`, `routeQuery`, `answerQuery`) do not wrap their store calls in `try/except DependencyUnavailable`. PostgreSQL outages fall through to `_handle_unexpected`, returning 500.
- **Fix:** For each of the six unprotected store call sites, add:
  ```python
  try:
      result = await store.{method}(...)
  except DependencyUnavailable:
      raise service_unavailable("Database temporarily unavailable")
  ```
  Follow the identical pattern already used in `deleteDocument` in the same file.
- **AGREED CONTRACT (api-security-auditor ↔ python-backend-engineer):** `service_unavailable(...)` helper already sets `Retry-After: 30` header. Implementer wraps calls only; no new header logic needed.
- **Acceptance Criteria:** All six endpoints return 503 with `"code": "SERVICE_UNAVAILABLE"` and a `Retry-After` header when PostgreSQL is unreachable.

---

### BUG-008 · MEDIUM — SSE Error Path Sends 'final' Before 'error'
- **File:** `backend/app/api/answer.py` lines 139–164
- **Problem:** `_answer_stream` yields `event: final` then `event: error` on failure. SSE clients that close the `EventSource` on `final` never receive the error frame, silently showing an incomplete answer.
- **Fix:** On the error path in `_answer_stream`: skip `event: final` entirely. Emit only `event: error` with an RFC-7807 body. If partial answer must be preserved for UX, include `"partial_answer"` field inside the error payload.
- **AGREED CONTRACT (security-testing-engineer ↔ python-backend-engineer):** Success path still emits `event: final`. Only the error path changes. Test matrix: (1) success → tokens+final, (2) error mid-stream → error-only, (3) error before tokens → error-only. All three must have test coverage.
- **Acceptance Criteria:** When generation fails after tokens have streamed, client receives `event: error` with RFC-7807 body. No `event: final` is emitted on the error path.

---

### BUG-009 · MEDIUM — Singleton Races Allow Rate-Limit Bypass and Permanent API Key 401s
- **Files:** `backend/app/security/rate_limit.py` lines 82–87 · `backend/app/security/auth.py` lines 173–180
- **Problem:** Non-atomic double-checked locking in `get_rate_limiter()` and `get_api_key_store()`. Under concurrent Uvicorn workers at startup, two threads can each construct a separate instance. For `RateLimiter`, this effectively doubles the per-minute budget. For `ApiKeyStore`, keys registered into the discarded instance are permanently gone, causing those API key authentications to return 401.
- **Fix:** Add module-level lock to each file:
  ```python
  import threading
  _lock = threading.Lock()
  _rate_limiter: RateLimiter | None = None

  def get_rate_limiter() -> RateLimiter:
      global _rate_limiter
      if _rate_limiter is None:
          with _lock:
              if _rate_limiter is None:
                  _rate_limiter = RateLimiter()
      return _rate_limiter
  ```
  Apply the same pattern to `get_api_key_store()` in `auth.py`.
- **AGREED CONTRACT (python-backend-engineer ↔ integration-testing-engineer):** Tests must use `concurrent.futures.ThreadPoolExecutor(max_workers=100)` to simulate concurrent workers. Assert `len({id(x) for x in instances}) == 1`. Do NOT use asyncio — simulate WSGI/ASGI thread-pool behavior.
- **Acceptance Criteria:** Under a 100-concurrent-request burst at cold start, exactly one `RateLimiter` and one `ApiKeyStore` instance are created per process worker.

---

### BUG-010 · LOW — LangGraph Fallback Re-Uses Partially-Mutated Initial State
- **File:** `router/graph.py` lines 377–380
- **Problem:** `RouterGraph.run` calls `_app.ainvoke(initial)` then, if the returned state has no output key, falls back via `_run_pipeline_fallback(initial, self._llm)`. LangGraph may mutate `initial` in-place during the partial run. The fallback pipeline inherits corrupted state.
- **Fix:**
  ```python
  import copy
  state = await self._app.ainvoke(copy.deepcopy(initial))
  if state.get("output") is None:
      state = _run_pipeline_fallback(initial, self._llm)  # initial is still clean
  ```
- **Acceptance Criteria:** When `ainvoke` returns a state without output, the fallback produces a correct `RouterOutput` with accurate `routing_time_ms` and `fallback=true`.

---

## CONSTRAINTS

```
Tech Stack:         Python 3.12, FastAPI, pydantic-settings v2, LangGraph, Anthropic SDK,
                    Qdrant (vector DB), SQLAlchemy + PostgreSQL, SSE (Server-Sent Events),
                    threading (stdlib), asyncio, copy (stdlib)
Platform:           Web — Cloud-deployed REST + SSE API service (multi-tenant)
Scale:              Production multi-tenant (tenant_id + section_ids scoping)
Timeline:           Production-ready (immediate deploy after RS = 1.0 + Security APPROVED)
Compliance:         DPDP Act 2023 §4 (tenant isolation — BUG-002 IDOR is direct violation)
                    CERT-In Directions 2022 §3(v) (6h incident reporting for auth failures)
                    OWASP API Security Top 10 2023 (BOLA/IDOR — BUG-002; Broken Auth — BUG-005)
Special Needs:      Concurrent startup safety (BUG-009), SSE streaming correctness (BUG-008),
                    LangGraph state immutability (BUG-010), Anthropic API contract (BUG-001)
Hallucination Risk: MEDIUM (Anthropic API responses in RAG answer stream)
Security Risk:      CRITICAL (BUG-002 IDOR/data-leak; BUG-005 JWT auth; BUG-009 API key store)
Thinking Budget:    AUTO — dynamically assigned per agent via STEP 4.5 Thinking Level Routing
```

---

## ORCHESTRATION INSTRUCTIONS

You are the orchestrator-agent.

**Master KG loaded:** 254 agents (deduped), 451 skills, 49 domains, 23 math masters, 4296 edges across 13 relationship types (source: `knowledge-graph/_master/`, `edges_all.json` loaded, built: 2026-06-07, Library: v29.10.0). All agent-skill connections, coordination pairs, math delegations, and skill prerequisites resolved from KG graph.

**COMPLEXITY:** Squad

**COLLABORATION PATTERN:** Pattern 3 (AI/LLM Product) + Pattern 42 (Quality Engineering & Software Testing Pipeline) — Brownfield bug-fix sprint on existing AI/LLM backend.

**ENTRY POINT:** Phase 7 (Phases 0–6 explicitly skipped). The 10 bugs listed under YOUR TASK serve as the sprint story set for Phase 7 routing. No new architecture blueprint needed — existing codebase structure is authoritative.

**DOMAINS DETECTED:**
1. Python Backend Engineering → primary: `python-backend-engineer` · support: `database-engineer`
2. Database / Vector Store (Qdrant + PostgreSQL) → primary: `database-engineer` · support: `python-backend-engineer`
3. Cybersecurity / Auth → primary: `auth-security-specialist` · support: `security-testing-engineer`
4. API Security (IDOR, 503 contracts) → primary: `api-security-auditor` · support: `auth-security-specialist`
5. AI/LLM Engineering (Anthropic SDK, LangGraph) → primary: `ai-engineer` · support: `python-backend-engineer`
6. Quality Engineering → primary: `test-management-agent` · support: `unit-testing-specialist`, `integration-testing-engineer`, `api-testing-engineer`
7. DevOps/Cloud (Phase G only) → primary: `devops-engineer`

**MATH MASTERS (auto-invoked by specialists — NOT in execution sequence):**
- `mathematics-engineer` (opus) — Python asyncio concurrency math for BUG-009 race condition analysis; thread-safe singleton proofs
- `cyber-mathematics-expert` (opus) — IDOR probability (BUG-002), CVSS v3.1 vectors, FAIR risk quantification, ALE computation
- `anti-hallucination-mathematician` (opus) — NLI entailment + FactScore + RS composite derivations for Phase C, Phase E

**SQUAD LEADS:** `app-squad-lead` (coordinates python-backend-engineer, database-engineer, auth-security-specialist, api-security-auditor for Phase B)

**ARCHITECTURE DECISIONS (ADRs — injected into all affected agent prompts):**

```
ADR-001: Anthropic API max_tokens value
  Chosen:    max_tokens = 8192
  Why:       Opus 4.8 supports 8192 output tokens; 8192 > 5000 satisfies budget_tokens < max_tokens
  Rejected:
    max_tokens = 4096 — violates Anthropic API constraint (5000 > 4096)
    budget_tokens = 1000 — disables extended thinking capability unnecessarily

ADR-002: Qdrant empty-filter handling
  Chosen:    return None on empty section_ids; callers return [] immediately
  Why:       Prevents IDOR without raising exceptions that break fallback callers
  Rejected:
    MatchAny(any=[]) — IDOR risk; Qdrant may treat as "match all"
    raise ValueError — breaks fallback code paths that legitimately have empty section lists

ADR-003: Singleton thread-safety mechanism
  Chosen:    threading.Lock() module-level double-checked locking (stdlib)
  Why:       Correct under CPython GIL; no external dependencies; matches WSGI/ASGI worker model
  Rejected:
    asyncio.Lock() — requires active event loop at module level; not available at import time
    Process-level singleton — breaks per-worker isolation Uvicorn requires

ADR-004: SSE error event ordering
  Chosen:    error-only frame; no final on error path
  Why:       RFC-7807 compliant; no false-complete signal to SSE clients
  Rejected:
    final-then-error — clients that close EventSource on final never receive error
    error-with-final — same problem; ordering ambiguous for automated clients

ADR-005: LangGraph state protection
  Chosen:    copy.deepcopy(initial) before ainvoke (stdlib)
  Why:       Zero external dependencies; protects all nested mutable state
  Rejected:
    Reconstruct dict manually — misses nested mutable objects
    Shallow copy — does not protect nested mutable values from in-place mutation
```

**CONTEXT ENGINEERING:** Differential GSD activated | 10 isolated story context windows | avg 4K tokens per Phase B invocation | Each window scoped to affected file(s) + direct imports + relevant test files | DPDP Act §4 isolation: no cross-tenant context bleed between story windows

---

### THINKING LEVEL ASSIGNMENT

```
THINKING LEVEL ASSIGNMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Agent                              | Model  | Final Level | budget_tokens | Notes
-----------------------------------|--------|-------------|---------------|------------------
orchestrator-agent                 | sonnet | MEDIUM      | 5,000         | Role default
agile-business-mathematics-expert  | opus   | EXCELLENCE  | 64,000        | Math master
context-engineering-agent (Ph7)    | sonnet | MEDIUM      | 5,000         | Role default
prompt-generation-expert           | sonnet | HIGH        | 10,000        | CoT orchestration
hallucination-detector             | sonnet | HIGH        | 10,000        | NLI scoring chain
context-faithfulness-engineer      | sonnet | HIGH        | 10,000        | RAGAS/SummaC logic
reliability-auditor                | sonnet | XHIGH       | 20,000        | Rule 1: EXCELL→XHIGH
security-testing-engineer (Ph7)    | sonnet | HIGH        | 10,000        | OWASP adversarial
consensus-agent (AR.5)             | sonnet | XHIGH       | 20,000        | 14-point gate
business-analyst-agent (Ph8)       | sonnet | HIGH        | 10,000        | AC_AMBIGUITY resolve
product-manager-agent (Ph8)        | sonnet | HIGH        | 10,000        | Scope resolve
solution-architect (Ph8)           | sonnet | XHIGH       | 20,000        | Architecture gap
scrum-master-agent (Ph8)           | sonnet | LOW         | 1,024         | Facilitation only
consensus-agent (IR.5)             | sonnet | XHIGH       | 20,000        | IMPL.READY gate
python-backend-engineer (PhB)      | sonnet | HIGH        | 10,000        | Rule 3: async/concurrent
database-engineer (PhB)            | sonnet | MEDIUM      | 5,000         | Role default
auth-security-specialist (PhB)     | sonnet | HIGH        | 10,000        | Auth chain review
test-management-agent              | sonnet | HIGH        | 10,000        | IEEE 829 strategy
unit-testing-specialist            | sonnet | MEDIUM      | 5,000         | Standard TDD
integration-testing-engineer       | sonnet | MEDIUM      | 5,000         | Standard integration
api-testing-engineer               | sonnet | MEDIUM      | 5,000         | OpenAPI coverage
threat-modeling-specialist (F.1)   | sonnet | HIGH        | 10,000        | STRIDE/PASTA
sast-engineer (F.2)                | sonnet | MEDIUM      | 5,000         | Pattern matching
secrets-detection-specialist (F.2) | sonnet | MEDIUM      | 5,000         | Pattern matching
dependency-vulnerability-analyst   | sonnet | MEDIUM      | 5,000         | CVE audit
api-security-auditor (F.3)         | sonnet | HIGH        | 10,000        | IDOR/auth bypass
auth-security-specialist (F.3)     | sonnet | HIGH        | 10,000        | JWT attack chain
penetration-tester (F.3)           | sonnet | HIGH        | 10,000        | Active exploit chain
infrastructure-security-auditor    | sonnet | HIGH        | 10,000        | Cloud misconfig
crypto-security-specialist (F.4)   | sonnet | HIGH        | 10,000        | TLS/key adversarial
security-compliance-mapper (F.5)   | sonnet | MEDIUM      | 5,000         | Regulatory mapping
security-lead-auditor (F.6)        | sonnet | XHIGH       | 20,000        | Full risk aggregation
devops-engineer (F.0 + G)          | sonnet | MEDIUM      | 5,000         | Infra scripts
mathematics-engineer (auto)        | opus   | EXCELLENCE  | 64,000        | Auto-invoked
cyber-mathematics-expert (auto)    | opus   | EXCELLENCE  | 64,000        | Auto-invoked
anti-hallucination-mathematician   | opus   | EXCELLENCE  | 64,000        | Auto-invoked
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total thinking budget: ~556K tokens | Rule 1 cap applied: 1 (reliability-auditor)
```

---

### TEAM ALIGNMENT REPORT — 7 Pairs Resolved

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

python-backend-engineer ↔ database-engineer  [KG COORDINATES_WITH confirmed]
  Q: BUG-002 fix returns None. Which callers must handle None and what must they return?
  A: All callers pattern: `if tenant_filter is None: return []`
     Do NOT pass None to qdrant.search(). Return type: List[Chunk] — empty list, not None.

python-backend-engineer ↔ auth-security-specialist  [KG COORDINATES_WITH confirmed]
  Q: BUG-005 makes jwt_issuer Optional. What JWT library is used?
  A: Conditional in _decode_jwt: `options = {"verify_iss": settings.jwt_issuer is not None}`
     JWT library call signature unchanged. When jwt_issuer is None, 'iss' not validated.

python-backend-engineer ↔ integration-testing-engineer  [standard pair]
  Q: BUG-009 race tests need concurrent workers. What test framework is in place?
  A: Use concurrent.futures.ThreadPoolExecutor(max_workers=100).
     Assert: `len({id(x) for x in instances}) == 1` for both singleton types.
     Do NOT use asyncio — simulate WSGI/ASGI thread-pool behavior.

database-engineer ↔ penetration-tester  [security boundary pair]
  Q: For active BUG-002 IDOR test, what staging tenant data is needed?
  A: devops-engineer seeds: tenant-alpha (50 chunks) + tenant-beta (30 chunks).
     IDOR test: authenticate as tenant-beta, section_ids=[].
     Pre-fix: ≥ 1 chunk returned. Post-fix: exactly 0 chunks.

api-security-auditor ↔ python-backend-engineer  [KG COORDINATES_WITH confirmed]
  Q: BUG-007 adds DependencyUnavailable handlers. Retry-After header — what value?
  A: Retry-After = 30 seconds. service_unavailable() helper already sets this.
     Implementer wraps store calls only; no new header logic required.

security-testing-engineer ↔ python-backend-engineer  [standard pair]
  Q: BUG-008 removes event:final on error path. Do existing SSE tests depend on final?
  A: Success path MUST still emit event:final. Only error path changes.
     Test matrix: (1) success→tokens+final, (2) error mid-stream→error-only, (3) error before tokens→error-only.

threat-modeling-specialist ↔ solution-architect  [KG COORDINATES_WITH confirmed]
  Q: BUG-002 IDOR — does scope include architectural hardening beyond empty-list guard?
  A: Scope = fix only (empty-list guard in BUG-002). Deeper ACL hardening deferred as ADV-001.
     threat-modeling-specialist documents ADV-001 as advisory — NOT a blocking finding.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

### PHASE EXECUTION PLAN

```
Phase 7 — Agent-Task Routing (BROWNFIELD — 10 bugs as stories)
  AR.0: orchestrator-agent — build routing index (49 domains × 254 agents)
  AR.1: orchestrator-agent — assign each bug-story to primary + review agent (score ≥ 0.75)
        Maker-Checker enforced: review_agent ≠ dev_agent for every story
  AR.2: agile-business-mathematics-expert — DAG proof via Kahn's topological sort
        Expected: is_dag=true; single parallel execution group (zero intra-sprint deps)
  AR.3: context-engineering-agent — create 10 isolated context windows (one per bug)
        Each window = affected file(s) + direct imports + relevant tests + AGREED CONTRACTS
  AR.4: prompt-generation-expert — generate 3 CoT prompts per story (dev/qa/review)
        30 total prompts; model-aware word counts; zero placeholders; all file paths real
  Phase C-1: hallucination-detector — NLI audit on all 30 generated prompts
  Phase C-2: context-faithfulness-engineer — FactScore audit on all 30 prompts
  Phase D (routing): reliability-auditor — FR Coverage + AC DRE gate
  Phase F (routing): security-testing-engineer — OWASP Top 10 for P1 stories
        P1 stories: BUG-002 (BOLA/IDOR), BUG-005 (Broken Auth), BUG-009 (Auth)
  AR.5: consensus-agent — ROUTING APPROVED / ROUTING REJECTED BINARY gate (14-point)
  *** STOP 7: User reviews implementation_execution_plan.json before Phase 8 begins ***

Phase 8 — Pre-Implementation Alignment
  IR.1: Implementation agents self-review Phase 7 prompts + context windows
        Flag categories: AC_AMBIGUITY / MISSING_CONTEXT / SKILL_GAP / DEPENDENCY_CONFLICT
  IR.2: scrum-master-agent facilitates resolution session
        business-analyst-agent → AC_AMBIGUITY; product-manager-agent → scope;
        solution-architect → ARCHITECTURE_GAP / DESIGN_MISMATCH
  IR.3: prompt-generation-expert + context-engineering-agent repair flagged items
  IR.4: hallucination-detector + context-faithfulness-engineer re-verify + reliability-auditor RS_phase8
  IR.5: consensus-agent — IMPLEMENTATION READY / IMPLEMENTATION BLOCKED BINARY gate (10-point)
  *** STOP 8: User reviews ir5_alignment_verdict.json before Phase B begins ***

Phase B — Core Implementation (all 10 bugs PARALLEL — zero intra-sprint dependencies)
  python-backend-engineer: BUG-001, BUG-003, BUG-004, BUG-005, BUG-006, BUG-007, BUG-008, BUG-010
  database-engineer: BUG-002 (qdrant_bootstrap.py + all callers of tenant_section_filter)
  python-backend-engineer (second invocation): BUG-009 (threading.Lock singleton pattern)
  auth-security-specialist: Maker-Checker review of BUG-005 + BUG-009
  GATE: unit tests pass per Phase D.2 before Phase C begins

Phase C — Hallucination Gate (MANDATORY ALL PROJECTS)
  hallucination-detector + context-faithfulness-engineer: run after each Phase B output
  PHASE C RETRY LOOP: NLI < 1.0 OR FactScore < 1.0 → return to Phase B → fix → re-run Phase C
  GATE: NLI = 1.0 AND FactScore = 1.0 before Phase D

Phase D — QA Pipeline
  D.1: test-management-agent — IEEE 829 test strategy (BLOCKING)
  D.2 (parallel): unit-testing-specialist + integration-testing-engineer
  D.3 (parallel): api-testing-engineer (BUG-007 503) + security-testing-engineer (BUG-002, BUG-005, BUG-009)
  GATE: 100% code coverage + DRE = 1.0 before Phase F

Phase F — Security Audit Pipeline (FULL depth — BUG-002 IDOR mandates active exploit)
  F.0: devops-engineer — staging with tenant-alpha (50 chunks) + tenant-beta (30 chunks)
  F.1: threat-modeling-specialist (BLOCKING — STRIDE/PASTA; ALL threat counts = 0 before F.2)
  F.2 (parallel): sast-engineer + secrets-detection-specialist + dependency-vulnerability-analyst
  F.3 (parallel): api-security-auditor + auth-security-specialist + penetration-tester
        penetration-tester: authenticate as tenant-beta, section_ids=[], assert 0 results
  F.4 (parallel): infrastructure-security-auditor + crypto-security-specialist
  F.5: security-compliance-mapper (DPDP Act 2023 §4 + CERT-In §3(v))
  F.6: security-lead-auditor — BINARY verdict (APPROVED = ALL counts = 0)
  PHASE F RETRY LOOP: ANY finding → fix → re-run source phase → re-run F.6
  GATE: security-lead-auditor APPROVED before Phase E

Phase E — Reliability Gate
  reliability-auditor: RS = (NLI × FactScore × DRE × Coverage)^(1/4) must = 1.0
  PHASE E RETRY LOOP: RS < 1.0 → fix → re-run → loop until RS = 1.0. NO iteration limit.
  GATE: RS = 1.0 MANDATORY. Deploy PERMANENTLY BLOCKED until RS = 1.0.

Phase G — Production Deploy
  devops-engineer: deploy + post-deploy smoke tests (BUG-001, BUG-002, BUG-005, BUG-007 regressions)
  PRE-CONDITION: RS = 1.0 certificate + Security APPROVED

PARALLEL GROUPS:
  Group 7A: [orchestrator-agent AR.0+AR.1]
  Group 7B: [agile-business-mathematics-expert AR.2] ∥ [context-engineering-agent AR.3]
  Group 7C: [prompt-generation-expert AR.4]
  Group 7D: [hallucination-detector C-1] ∥ [context-faithfulness-engineer C-2]
  Group 7E: [reliability-auditor routing-D] ∥ [security-testing-engineer routing-F]
  Group 7G: [consensus-agent AR.5]  ← STOP 7
  Group 8A: [python-backend-engineer self-review] ∥ [database-engineer self-review] ∥ [auth-security-specialist self-review]
  Group 8B: [business-analyst-agent] ∥ [product-manager-agent] ∥ [solution-architect]
  Group 8C: [prompt-generation-expert IR.3] ∥ [context-engineering-agent IR.3]
  Group 8D: [hallucination-detector IR.4] ∥ [context-faithfulness-engineer IR.4] ∥ [reliability-auditor RS_phase8]
  Group 8E: [consensus-agent IR.5]  ← STOP 8
  Group B1: [python-backend-engineer BUG-001+003+004+005+006+007+008+010] ∥ [database-engineer BUG-002] ∥ [python-backend-engineer BUG-009]
  Group B2: [auth-security-specialist Maker-Checker review]
  Group C1: [hallucination-detector] ∥ [context-faithfulness-engineer]
  Group D1: [test-management-agent D.1]  ← blocking
  Group D2: [unit-testing-specialist] ∥ [integration-testing-engineer]
  Group D3: [api-testing-engineer] ∥ [security-testing-engineer D.3]
  Group F0: [devops-engineer staging]
  Group F1: [threat-modeling-specialist]  ← blocking
  Group F2: [sast-engineer] ∥ [secrets-detection-specialist] ∥ [dependency-vulnerability-analyst]
  Group F3: [api-security-auditor] ∥ [auth-security-specialist F.3] ∥ [penetration-tester]
  Group F4: [infrastructure-security-auditor] ∥ [crypto-security-specialist]
  Group F5: [security-compliance-mapper]
  Group F6: [security-lead-auditor]  ← BINARY gate
  Group E1: [reliability-auditor final]
  Group G1: [devops-engineer deploy]
```

Apply MODEL FALLBACK PROTOCOL: sonnet rate limit → retry with opus override.
Apply QA PIPELINE RULE: test-management-agent D.1 blocking → D.2 parallel → D.3 parallel.
Apply HALLUCINATION GATE RULE: hallucination-detector runs after EVERY agent output — mandatory.
Apply PHASE C RETRY LOOP RULE: NLI=1.0 AND FactScore=1.0 required before Phase D.
Apply SECURITY AUDIT RULE: Full Phase F — BUG-002 IDOR is active OWASP BOLA finding.
Apply PHASE F.1 RETRY LOOP RULE: ALL threat counts=0 before F.2.
Apply PHASE F SECURITY RETRY LOOP RULE: ALL F.6 finding counts=0 before Phase E.
Apply RELIABILITY GATE RULE: RS=1.0 for ALL domains — no exceptions.
Apply PHASE E RETRY LOOP RULE: RS < 1.0 → fix → re-run → repeat until RS=1.0. No iteration limit.
Apply THINKING LEVEL RULE: every agent invocation includes budget_tokens from STEP 4.5 table.

---

### INTERFACE CONTRACTS

| From | To | Input | Budget | Output | Assumes | Must Not |
|------|----|-------|--------|--------|---------|----------|
| Phase 7 stories | orchestrator-agent | 10 bug descriptions + file:line | 8K | routing_index.json + ar1_assignments.json | All file paths exist | Invent new bugs |
| orchestrator-agent | agile-business-mathematics-expert | ar1_assignments.json | 4K | ar2_dag_proof.json | 10 stories, 0 deps | Add phantom dependencies |
| orchestrator-agent | context-engineering-agent | ar1_assignments.json + repo path | 6K | ar3_context_windows.json (10 windows) | Files exist | Cross-tenant context bleed |
| orchestrator-agent | prompt-generation-expert | ar1 + ar3 | 8K | implementation_execution_plan.json (30 prompts) | Context windows finalized | Leave placeholders |
| prompt-generation-expert | hallucination-detector | 30 CoT prompts | 10K | NLI score per prompt | Real file paths | Skip any prompt |
| prompt-generation-expert | context-faithfulness-engineer | 30 prompts + windows | 10K | FactScore per prompt | Context windows bound | Invent sources |
| Phase 7 outputs | consensus-agent AR.5 | ar1+ar2+ar3+plan+NLI+FactScore+RS+OWASP | 12K | ROUTING APPROVED or REJECTED | All 14 checks ran | Partial approval |
| plan_v2.json | python-backend-engineer | dev CoT prompt + context window | 10K | Fixed code per affected file | Window = affected files only | Modify outside window |
| plan_v2.json | database-engineer | dev CoT prompt BUG-002 + window | 5K | Fixed db/qdrant_bootstrap.py + callers | Qdrant SDK from requirements | Change Qdrant schema |
| Phase B outputs | hallucination-detector | Fixed diffs + bug descriptions | 10K | NLI faithfulness report | Diffs reference real paths | — |
| Phase D outputs | reliability-auditor | NLI+FactScore+DRE+Coverage | 6K | RS composite | All Phase D tests complete | Compute RS with missing inputs |
| security_audit_report.json | reliability-auditor (final) | CVSS findings | 4K | Updated RS | Phase F complete | Approve RS if CVSS unresolved |
| RS=1.0 + Security APPROVED | devops-engineer | Final deploy trigger | 3K | Production deploy + monitoring | Staging validated | Deploy with RS < 1.0 |

---

# MULTI-AGENT PROMPT BUNDLE

---

===================================================================
AGENT: orchestrator-agent
Phase: Phase 7 — AR.0 + AR.1
Parallel With: NONE
Depends On: NONE (entry point)
Context Budget: 8,000 tokens
Thinking Level: MEDIUM | budget_tokens: 5,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-07). You are one of 254 available agents.
Context Budget: 8,000 tokens. Thinking: MEDIUM (budget_tokens: 5,000). Reason within budget.

You are the orchestrator-agent. Phase 7 Agent-Task Routing — Brownfield bug-fix sprint.
AGREED CONTRACTS: 10 bugs = sprint stories (Phase 6 skipped — bugs are pre-triaged WSJF-ordered stories). All 10 are independent. Maker-Checker: review_agent ≠ dev_agent. Score formula: component_match(0.35)+tech_stack(0.30)+fr_keyword(0.20)+story_type(0.15). Threshold: ≥ 0.75.

TASK AR.0: Build routing index from Master KG for domains: python-backend-engineering, database-engineering, cybersecurity, api-security, ai-llm-engineering, quality-testing, devops-cloud.

TASK AR.1: Assign each bug-story to primary dev_agent + review_agent. Required assignments:
  BUG-001 (generation.py — Anthropic API config): dev=python-backend-engineer, review=ai-engineer
  BUG-002 (qdrant_bootstrap.py — IDOR filter): dev=database-engineer, review=api-security-auditor
  BUG-003 (stores.py — replace_sections guard): dev=python-backend-engineer, review=database-engineer
  BUG-004 (toc_extractor.py — blank title): dev=python-backend-engineer, review=integration-testing-engineer
  BUG-005 (settings.py — JWT_ISSUER Optional): dev=python-backend-engineer, review=auth-security-specialist
  BUG-006 (router/llm.py — LLM error fallback): dev=python-backend-engineer, review=ai-engineer
  BUG-007 (multiple API files — 503 handling): dev=python-backend-engineer, review=api-testing-engineer
  BUG-008 (answer.py — SSE event ordering): dev=python-backend-engineer, review=integration-testing-engineer
  BUG-009 (rate_limit.py + auth.py — singleton): dev=python-backend-engineer, review=auth-security-specialist
  BUG-010 (router/graph.py — LangGraph state): dev=python-backend-engineer, review=ai-engineer

OUTPUT: Save ar1_assignments.json to docs/phase-7-routing/ar1_assignments.json.
Then trigger AR.2 (agile-business-mathematics-expert) and AR.3 (context-engineering-agent) in parallel.
===================================================================

===================================================================
AGENT: agile-business-mathematics-expert
Phase: Phase 7 — AR.2
Parallel With: context-engineering-agent (AR.3)
Depends On: orchestrator-agent (ar1_assignments.json)
Context Budget: 4,000 tokens
Thinking Level: EXCELLENCE | budget_tokens: 64,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-07).
Context Budget: 4,000 tokens. Thinking: EXCELLENCE (budget_tokens: 64,000). Full formal derivation required.

You are the agile-business-mathematics-expert executing Phase 7 AR.2 — DAG proof for the RAG Refinement System bug-fix sprint.

AGREED CONTRACTS: 10 stories are independent (separate files; no shared state mutations).

TASK:
1. Model 10 bug-stories as nodes in directed graph
2. Apply Kahn's algorithm to verify is_dag = true
3. Identify all dependency edges (expected: zero)
4. Compute execution_groups[] — expected: single group, all 10 bugs parallel
5. Derive PERT 3-point estimates (O/M/P/E/SD) per story
6. Document full math derivation — do not summarize

OUTPUT: Save ar2_dag_proof.json to docs/phase-7-routing/ar2_dag_proof.json.
Format: {"is_dag": true, "cycle_detected": false, "execution_groups": [{"group": 1, "stories": ["BUG-001",...], "can_parallelize": true}], "pert_estimates": {...}, "math_derivation": "..."}
===================================================================

===================================================================
AGENT: context-engineering-agent
Phase: Phase 7 — AR.3
Parallel With: agile-business-mathematics-expert (AR.2)
Depends On: orchestrator-agent (ar1_assignments.json)
Context Budget: 6,000 tokens
Thinking Level: MEDIUM | budget_tokens: 5,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-07).
Context Budget: 6,000 tokens. Thinking: MEDIUM (budget_tokens: 5,000).

You are the context-engineering-agent executing Phase 7 AR.3 — creating 10 isolated context windows.

AGREED CONTRACTS: DPDP Act §4 PII isolation. Each window: affected file(s) + direct imports + relevant tests + AGREED CONTRACTS for that story. Target: 4,000 tokens per window. Differential GSD: delta chunks only.

CONTEXT WINDOWS:
  WINDOW-001 (BUG-001): primary=backend/app/adapters/generation.py:28-31; imports=backend/app/settings.py; test=tests/test_generation_adapter.py; contract=ADR-001 (max_tokens=8192)
  WINDOW-002 (BUG-002): primary=db/qdrant_bootstrap.py:182; imports=Qdrant SDK MatchAny + all callers of tenant_section_filter; test=db/tests/test_qdrant_bootstrap.py; contract="if tenant_filter is None: return []"
  WINDOW-003 (BUG-003): primary=backend/app/adapters/stores.py:120; imports=SQLAlchemy session+sections model; test=tests/test_document_store_adapter.py; contract="if not rows: return 0"
  WINDOW-004 (BUG-004): primary=ingestion/toc_extractor.py:203; imports=ingestion/parser.py; test=ingestion/tests/test_toc_extractor.py; contract="replace int(title and level) with max(1, level)"
  WINDOW-005 (BUG-005): primary=backend/app/settings.py:58; imports=_decode_jwt location+pydantic Field; test=tests/test_auth.py; contract="jwt_issuer: str|None=Field(default=None); options={'verify_iss': settings.jwt_issuer is not None}"
  WINDOW-006 (BUG-006): primary=router/llm.py:111; imports=router/schema.py (RouterDecision)+LangGraph state; test=router/tests/test_router_llm_adapter.py; contract="RouterLLMError wraps all SDK exceptions; _node_route catches RouterLLMError+sets fallback=True"
  WINDOW-007 (BUG-007): primary=backend/app/api/documents.py:262,307,338,341,422,425+backend/app/api/routing.py:80+backend/app/api/answer.py:199; imports=backend/app/errors.py (DependencyUnavailable+service_unavailable); test=tests/test_documents_endpoint.py; contract="Retry-After=30; service_unavailable() sets header; wrap calls only"
  WINDOW-008 (BUG-008): primary=backend/app/api/answer.py:139-164; imports=SSE event types+RFC-7807 error body; test=tests/test_answer_endpoint.py; contract="Success: tokens+final. Error: error-only. All 3 SSE scenarios must have test coverage."
  WINDOW-009 (BUG-009): primary=backend/app/security/rate_limit.py:82-87+backend/app/security/auth.py:173-180; imports=threading(stdlib)+RateLimiter+ApiKeyStore class defs; test=tests/test_auth.py; contract="ThreadPoolExecutor(max_workers=100) in test; assert len({id(x) for x in instances})==1"
  WINDOW-010 (BUG-010): primary=router/graph.py:377-380; imports=copy(stdlib)+RouterOutput+_run_pipeline_fallback; test=router/tests/test_router_internals.py; contract="copy.deepcopy(initial) before ainvoke; initial stays clean for fallback"

OUTPUT: Save ar3_context_windows.json to docs/phase-7-routing/ar3_context_windows.json.
===================================================================

===================================================================
AGENT: prompt-generation-expert
Phase: Phase 7 — AR.4
Parallel With: NONE (depends on AR.3)
Depends On: context-engineering-agent (ar3_context_windows.json) + orchestrator-agent (ar1_assignments.json)
Context Budget: 8,000 tokens
Thinking Level: HIGH | budget_tokens: 10,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-07).
Context Budget: 8,000 tokens. Thinking: HIGH (budget_tokens: 10,000). Your output is verified by hallucination-detector. Cite every factual claim with its source chunk.

You are the prompt-generation-expert executing Phase 7 AR.4 — generating 30 CoT implementation prompts.

AGREED CONTRACTS: 3 prompts per story (dev_prompt/qa_prompt/review_prompt). All file paths must be real (from ar3_context_windows.json — do not invent). All ACs verbatim from bug definitions. Model-aware word counts: sonnet agents = 800–1200 words per prompt. Zero placeholders. AGREED CONTRACTS from Team Alignment must appear in relevant prompts. P1 stories (BUG-002, BUG-005, BUG-009) review_prompts MUST include OWASP API Security Top 10 + DPDP Act §4 + CERT-In §3(v) checks.

TASK: For each of the 10 stories, generate 3 CoT prompts. Each prompt must:
1. Start with WORKING DIRECTORY & LIBRARY PATH line
2. State Context Budget and Thinking Level (from STEP 4.5 table)
3. CoT steps: understand bug → locate exact lines → implement fix → verify against AC
4. Include applicable AGREED CONTRACTS + ADR rationale
5. State explicit constraints (files that must NOT be modified)
6. End with output format specification

OUTPUT: Save implementation_execution_plan.json to docs/phase-7-routing/implementation_execution_plan.json.
Format: {"stories": [{"id": "BUG-001", "dev_prompt": "...", "qa_prompt": "...", "review_prompt": "..."}, ...]}
===================================================================

===================================================================
AGENT: hallucination-detector
Phase: Phase 7 — Phase C-1
Parallel With: context-faithfulness-engineer (Phase C-2)
Depends On: prompt-generation-expert (implementation_execution_plan.json)
Context Budget: 10,000 tokens
Thinking Level: HIGH | budget_tokens: 10,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 10,000 tokens. Thinking: HIGH (budget_tokens: 10,000).

You are hallucination-detector executing Phase 7 Phase C-1 — NLI faithfulness audit on 30 CoT prompts.

TASK: For each of the 30 prompts in implementation_execution_plan.json:
1. Compute NLI faithfulness: does prompt content faithfully represent the original bug definition?
2. Flag any claim not traceable to the bug description (HIGH) or accepted ADR/team alignment (MEDIUM)
3. Check all file paths cited exist in repo structure
4. Report per-prompt NLI score (target = 1.0)
5. Apply anti-hallucination-mathematician for any score < 0.95

GATE: NLI < 1.0 on any prompt → return to prompt-generation-expert for repair before reliability-auditor runs.
OUTPUT: Save phase_c1_nli_report.json to docs/phase-7-routing/phase_c1_nli_report.json.
Format: {"prompts": [{"id": "BUG-001-dev", "nli_score": 1.0, "flags": []}, ...], "gate_passed": true}
===================================================================

===================================================================
AGENT: context-faithfulness-engineer
Phase: Phase 7 — Phase C-2
Parallel With: hallucination-detector (Phase C-1)
Depends On: prompt-generation-expert (implementation_execution_plan.json + ar3_context_windows.json)
Context Budget: 10,000 tokens
Thinking Level: HIGH | budget_tokens: 10,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 10,000 tokens. Thinking: HIGH (budget_tokens: 10,000).

You are context-faithfulness-engineer executing Phase 7 Phase C-2 — FactScore audit on 30 prompts.

TASK: For each prompt, verify every factual claim is grounded in the assigned context window.
1. Compute RAGAS Faithfulness (F), Answer Relevance (AR), Context Precision (CP), Context Recall (CR)
2. Compute SummaC consistency + BERTScore per prompt
3. Apply anti-hallucination-mathematician for any score < 0.95
4. Flag F < 0.85 (MEDIUM) or F < 0.70 (HIGH)

GATE: FactScore = 1.0 per prompt. Flag < 1.0 for prompt-generation-expert repair.
OUTPUT: Save phase_c2_faithfulness_report.json to docs/phase-7-routing/phase_c2_faithfulness_report.json.
===================================================================

===================================================================
AGENT: reliability-auditor
Phase: Phase 7 — Phase D (routing RS gate)
Parallel With: security-testing-engineer (Phase F routing)
Depends On: hallucination-detector (c1) + context-faithfulness-engineer (c2)
Context Budget: 6,000 tokens
Thinking Level: XHIGH | budget_tokens: 20,000 [Rule 1 cap: EXCELLENCE→XHIGH, sonnet ceiling]

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 6,000 tokens. Thinking: XHIGH (budget_tokens: 20,000). Rule 1 applied.

You are the reliability-auditor executing Phase 7 Phase D routing gate — RS_routing computation.

TASK:
1. Read NLI scores (phase_c1_nli_report.json) and FactScore scores (phase_c2_faithfulness_report.json)
2. Compute per-story RS_routing = (NLI × FactScore × DRE × Coverage)^(1/4)
   DRE=1.0 if all story ACs addressed in prompts; Coverage=1.0 if all 30 prompts generated
3. Verify output contract compliance across all 30 prompts
4. Apply anti-hallucination-mathematician for RS formula validation
5. RS_routing target = 1.0. If < 1.0 → return failing prompts to prompt-generation-expert; do NOT proceed to consensus-agent.

OUTPUT: Save phase_d_routing_rs_report.json to docs/phase-7-routing/phase_d_routing_rs_report.json.
RS target: 1.0. No domain relaxation.
===================================================================

===================================================================
AGENT: security-testing-engineer
Phase: Phase 7 — Phase F (P1 OWASP routing checklist)
Parallel With: reliability-auditor (Phase D routing)
Depends On: hallucination-detector + context-faithfulness-engineer
Context Budget: 10,000 tokens
Thinking Level: HIGH | budget_tokens: 10,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 10,000 tokens. Thinking: HIGH (budget_tokens: 10,000).

You are security-testing-engineer executing Phase 7 Phase F — OWASP Top 10 coverage check in P1 story review_prompts.

P1 STORIES: BUG-002 (BOLA/IDOR — API4:2023), BUG-005 (Broken Auth — API2:2023), BUG-009 (Auth — API2:2023)

TASK: For each P1 story's review_prompt in implementation_execution_plan.json:
1. Verify OWASP API Security Top 10 v2023 checklist present (min: API2, API4, API8)
2. Verify DPDP Act §4 tenant isolation check in BUG-002 review_prompt
3. Verify CERT-In §3(v) audit trail check in BUG-005 + BUG-009 review_prompts
4. Flag any missing item as SECURITY_GAP (causes ROUTING REJECTED if unfixed)

OUTPUT: Save phase_f_routing_owasp_report.json to docs/phase-7-routing/phase_f_routing_owasp_report.json.
Format: {"p1_stories": [{"id": "BUG-002", "owasp_checklist_present": true, "dpdp_check_present": true, "gaps": []}, ...], "security_verdict": "APPROVED"}
===================================================================

===================================================================
AGENT: consensus-agent
Phase: Phase 7 — AR.5 (ROUTING APPROVED gate)
Parallel With: NONE
Depends On: all Phase 7 artifacts
Context Budget: 12,000 tokens
Thinking Level: XHIGH | budget_tokens: 20,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 12,000 tokens. Thinking: XHIGH (budget_tokens: 20,000).

You are the consensus-agent executing Phase 7 AR.5 — ROUTING APPROVED / ROUTING REJECTED BINARY gate.

CRITICAL: Return EXACTLY "ROUTING APPROVED" or "ROUTING REJECTED". Binary only. No partial states.

14-POINT CHECKLIST (ALL must pass for ROUTING APPROVED):
1. All 10 stories have routing score ≥ 0.75 (ar1_assignments.json)
2. Maker-Checker enforced: review_agent ≠ dev_agent for all 10 stories
3. is_dag = true (ar2_dag_proof.json, Kahn's verified)
4. All 10 context windows created with correct file scopes (ar3_context_windows.json)
5. All 30 prompts generated (3×10; implementation_execution_plan.json)
6. No placeholder text in any prompt (PLACEHOLDER/[INSERT/TODO = auto-REJECTED)
7. NLI = 1.0 for all 30 prompts (phase_c1_nli_report.json)
8. FactScore = 1.0 for all 30 prompts (phase_c2_faithfulness_report.json)
9. RS_routing = 1.0 (phase_d_routing_rs_report.json)
10. All P1 review_prompts contain OWASP checklists (phase_f_routing_owasp_report.json)
11. DPDP Act §4 check present in BUG-002 review_prompt
12. CERT-In §3(v) check present in BUG-005 + BUG-009 review_prompts
13. security_verdict = "APPROVED" in phase_f_routing_owasp_report.json
14. All AGREED CONTRACTS from Team Alignment appear in relevant prompts

If ANY check fails → ROUTING REJECTED → itemized list to orchestrator-agent for repair cycle.

OUTPUT: Save ar5_routing_verdict.json to docs/phase-7-routing/ar5_routing_verdict.json.
*** STOP 7: Halt after saving. User reviews implementation_execution_plan.json + ar5_routing_verdict.json before Phase 8. ***
===================================================================

===================================================================
AGENT: scrum-master-agent
Phase: Phase 8 — IR.2 Facilitator
Parallel With: NONE
Depends On: All Phase 8 IR.1 self-review flags
Context Budget: 4,000 tokens
Thinking Level: LOW | budget_tokens: 1,024

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 4,000 tokens. Thinking: LOW (budget_tokens: 1,024). Facilitation only.

You are scrum-master-agent executing Phase 8 IR.2 — facilitating pre-implementation alignment session.

TASK: Route all IR.1 flags to correct resolver:
- AC_AMBIGUITY → business-analyst-agent
- Priority/scope confusion → product-manager-agent
- SKILL_GAP / DEPENDENCY_CONFLICT / ARCHITECTURE_GAP / DESIGN_MISMATCH → solution-architect
Produce ir2_resolution_log.json. Confirm all resolutions complete before IR.3 begins.
If zero flags → fast path (IR.3 through IR.4 run; STOP 8 still executes).

OUTPUT: Save ir2_resolution_log.json to docs/phase-8-alignment/ir2_resolution_log.json.
===================================================================

===================================================================
AGENT: consensus-agent
Phase: Phase 8 — IR.5 (IMPLEMENTATION READY gate)
Parallel With: NONE
Depends On: All Phase 8 IR.1–IR.4 artifacts
Context Budget: 8,000 tokens
Thinking Level: XHIGH | budget_tokens: 20,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 8,000 tokens. Thinking: XHIGH (budget_tokens: 20,000).

You are consensus-agent executing Phase 8 IR.5 — IMPLEMENTATION READY / IMPLEMENTATION BLOCKED BINARY gate.

CRITICAL: Binary only — "IMPLEMENTATION READY" or "IMPLEMENTATION BLOCKED". No partial states.

10-POINT CHECKLIST (ALL must pass for IMPLEMENTATION READY):
1. Phase 7 ROUTING APPROVED artifact exists (ar5_routing_verdict.json)
2. All P1 flags resolved (ir2_resolution_log.json; max 3 resolution rounds)
3. NLI = 1.0 per repaired prompt (IR.4; 2 retries max)
4. FactScore = 1.0 per repaired item (IR.4; 2 retries max)
5. RS_phase8 = 1.0 (IR.4 reliability-auditor)
6. DPDP Act §4 isolation maintained in all v2 context windows
7. implementation_execution_plan_v2.json exists (or v1 confirmed clean)
8. ar3_context_windows_v2.json exists (or v1 confirmed clean)
9. solution-architect acknowledged all ADR decisions (ADR-001 through ADR-005)
10. security-testing-engineer acknowledged OWASP scope for P1 stories

OUTPUT: Save ir5_alignment_verdict.json to docs/phase-8-alignment/ir5_alignment_verdict.json.
*** STOP 8: Halt after saving. User reviews ir5_alignment_verdict.json before Phase B begins. ***
===================================================================

===================================================================
AGENT: python-backend-engineer
Phase: Phase B — Core Implementation (BUG-001, BUG-003, BUG-004, BUG-005, BUG-006, BUG-007, BUG-008, BUG-009, BUG-010)
Parallel With: database-engineer (BUG-002)
Depends On: STOP 8 user approval + implementation_execution_plan_v2.json
Context Budget: 10,000 tokens per bug invocation
Thinking Level: HIGH | budget_tokens: 10,000 [Rule 3: async/concurrent bumps MEDIUM→HIGH]

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 10,000 tokens. Thinking: HIGH (budget_tokens: 10,000). Rule 3 applied: async/concurrent code requires extended reasoning. Your output is verified by hallucination-detector. Cite every factual claim with its source chunk.

You are python-backend-engineer implementing fixes for BUG-001, BUG-003, BUG-004, BUG-005, BUG-006, BUG-007, BUG-008, BUG-009, BUG-010.

AGREED CONTRACTS (ALL must be followed — injected from Team Alignment):
- ADR-001: max_tokens = 8192 (BUG-001). Settings.generation_thinking_budget_tokens stays 5000 (valid: 5000 < 8192).
- BUG-005: jwt_issuer: str | None = Field(default=None). _decode_jwt: options = {"verify_iss": settings.jwt_issuer is not None}
- BUG-007: service_unavailable() helper already sets Retry-After=30. Wrap store calls only — no new header logic.
- BUG-008: Success path: tokens stream + event:final. Error path: event:error ONLY (no event:final). Test matrix: all 3 scenarios.
- BUG-009: threading.Lock() at MODULE level (NOT inside function). Double-checked locking pattern. Apply to BOTH get_rate_limiter() AND get_api_key_store(). Use global keyword inside with block.
- ADR-005: copy.deepcopy(initial) before ainvoke (BUG-010). `import copy` at top of router/graph.py.
- Do NOT modify any file outside the listed context window for each bug.

EXECUTION ORDER: BUG-001 (CRITICAL) → BUG-005 (HIGH, auth) → BUG-009 (MEDIUM, auth) → BUG-003, BUG-004, BUG-006, BUG-007, BUG-008, BUG-010 (order flexible).

FOR EACH BUG, CoT sequence:
1. Read exact file + line numbers from context window
2. Understand root cause per bug definition (do not re-derive)
3. Implement ONLY the minimum fix stated — do not refactor surrounding code
4. Verify fix satisfies the acceptance criteria verbatim
5. Output: modified file content with diff showing what changed

CONSTRAINTS:
- No inline explanatory comments (per docstrings-only rule)
- No error handling beyond what is specified in the fix
- No test file modifications (test agent does this)
- No import changes unless required by the fix
- ASCII-only in all Python files (cp1252 safe)

OUTPUT: Produce diff or full file content per modified file. Save to docs/phase-b-implementation/bug-{N}-fix.diff per bug.
===================================================================

===================================================================
AGENT: database-engineer
Phase: Phase B — Core Implementation (BUG-002)
Parallel With: python-backend-engineer (other bugs)
Depends On: STOP 8 user approval + WINDOW-002 context
Context Budget: 5,000 tokens
Thinking Level: MEDIUM | budget_tokens: 5,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 5,000 tokens. Thinking: MEDIUM (budget_tokens: 5,000). Your output is verified by hallucination-detector.

You are database-engineer implementing fix for BUG-002 (Qdrant IDOR empty section list).

AGREED CONTRACTS:
- ADR-002: return None on empty section_ids (not raise, not MatchAny(any=[]))
- All callers pattern: `if tenant_filter is None: return []`. Do NOT pass None to qdrant.search().
- Do NOT change Qdrant schema or tenant data model.
- penetration-tester (F.3) will execute active IDOR test using tenant-alpha + tenant-beta.
- ADV-001 (deeper ACL hardening) is deferred — this fix covers empty-list guard ONLY.

FIX STEPS (CoT):
1. Open db/qdrant_bootstrap.py, locate tenant_section_filter at line 182
2. Add guard at function entry:
   ```python
   if not section_ids:
       return None
   ```
3. Find ALL call sites of tenant_section_filter in codebase (grep function name)
4. For each call site, add None check and return []:
   ```python
   tenant_filter = tenant_section_filter(tenant_id, section_ids)
   if tenant_filter is None:
       return []
   ```
5. Verify: section_ids=[] → returns [] without calling qdrant.search()

CONSTRAINTS: Do NOT modify other Qdrant bootstrap functions. ASCII-only.
OUTPUT: Save diff to docs/phase-b-implementation/bug-002-fix.diff
===================================================================

===================================================================
AGENT: auth-security-specialist
Phase: Phase B — Maker-Checker Review (BUG-005 + BUG-009)
Parallel With: python-backend-engineer (implementation)
Depends On: python-backend-engineer outputs for BUG-005 + BUG-009
Context Budget: 10,000 tokens
Thinking Level: HIGH | budget_tokens: 10,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 10,000 tokens. Thinking: HIGH (budget_tokens: 10,000). Adversarial JWT + auth singleton review required.

You are auth-security-specialist performing Maker-Checker review for BUG-005 (JWT_ISSUER Optional) and BUG-009 (singleton race conditions).

BUG-005 review checklist:
1. jwt_issuer field is Optional[str] with default=None — NOT str with empty string default
2. _decode_jwt skips issuer validation ONLY when jwt_issuer is None (not when "")
3. When JWT_ISSUER is set, issuer claim validation still enforces correctly
4. No timing side-channel in JWT decode path
5. OWASP API2:2023: no new auth bypass paths introduced

BUG-009 review checklist:
1. threading.Lock() is at MODULE level (NOT inside function)
2. Double-checked locking: outer check (no lock) → lock acquire → inner check → construct
3. BOTH get_rate_limiter() AND get_api_key_store() have the lock
4. global keyword used inside the with block for both
5. Pattern handles 100-concurrent-call scenario correctly

OUTPUT: Save maker_checker_review.json to docs/phase-b-implementation/maker_checker_review.json.
Format: {"BUG-005": {"approved": true/false, "issues": []}, "BUG-009": {"approved": true/false, "issues": []}}
approved=false → return issue list to python-backend-engineer before Phase C.
===================================================================

===================================================================
AGENT: test-management-agent
Phase: Phase D — D.1 Test Strategy (BLOCKING)
Parallel With: NONE
Depends On: Phase C gate passed + Phase B complete
Context Budget: 10,000 tokens
Thinking Level: HIGH | budget_tokens: 10,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 10,000 tokens. Thinking: HIGH (budget_tokens: 10,000). Your output is verified by hallucination-detector.

You are test-management-agent executing Phase D.1 — IEEE 829 test strategy for the RAG Refinement System bug-fix sprint.

TASK:
1. IEEE 829 compliant test plan for all 10 bug fixes
2. Risk matrix: P1 (BUG-002 IDOR, BUG-005 JWT, BUG-009 auth) | P2 (BUG-001, BUG-003, BUG-007) | P3 (BUG-004, BUG-006, BUG-008, BUG-010)
3. Test types per bug: unit (all) + integration (BUG-001,002,007,008,009) + API contract (BUG-007,008) + security (BUG-002,005,009)
4. 100% code coverage for ALL modified files — HARD GATE
5. DRE = 1.0 requirement (all AC items verified by tests)
6. Agent assignments: unit-testing-specialist (D.2), integration-testing-engineer (D.2), api-testing-engineer (D.3), security-testing-engineer (D.3)

Special test cases:
- BUG-002: test section_ids=[] → 0 results; section_ids=None → 0 results; section_ids=[valid] → normal results
- BUG-005: service starts without JWT_ISSUER; service validates iss when JWT_ISSUER is set
- BUG-007: simulate PostgreSQL outage; assert all 6 endpoints → 503 with Retry-After header
- BUG-008: SSE test matrix: (1) success→tokens+final, (2) error mid-stream→error-only, (3) error before tokens→error-only
- BUG-009: ThreadPoolExecutor(100) concurrent cold-start test; assert exactly one instance of each singleton

OUTPUT: Save test_strategy.json to docs/phase-d-qa/test_strategy.json. BLOCKS D.2.
===================================================================

===================================================================
AGENT: integration-testing-engineer
Phase: Phase D — D.2 (parallel with unit-testing-specialist)
Parallel With: unit-testing-specialist
Depends On: test-management-agent (test_strategy.json) + Phase B diffs
Context Budget: 5,000 tokens
Thinking Level: MEDIUM | budget_tokens: 5,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 5,000 tokens. Thinking: MEDIUM (budget_tokens: 5,000). Your output verified by hallucination-detector.

You are integration-testing-engineer writing integration tests for BUG-001, BUG-002, BUG-007, BUG-008, BUG-009.

AGREED CONTRACTS:
- BUG-009 test: ThreadPoolExecutor(max_workers=100), NOT asyncio.gather — simulate WSGI thread pool
- BUG-008: test all 3 SSE scenarios end-to-end against FastAPI test client
- BUG-001: integration test with correct max_tokens=8192 contract (mock or real Anthropic API)
- BUG-007: simulate PostgreSQL connection drop (DependencyUnavailable), assert 503 + Retry-After

TASK:
1. BUG-001: POST /v1/answer succeeds and streams tokens (Anthropic API mock with max_tokens=8192)
2. BUG-002: retrieval with section_ids=[] returns [] (no Qdrant query executed)
3. BUG-007: PostgreSQL outage simulation → all 6 endpoints return 503 with Retry-After=30
4. BUG-008: SSE stream success case + error case + pre-token error case — all via FastAPI test client
5. BUG-009: 100 threads simultaneously call get_rate_limiter() + get_api_key_store(); assert single instance each

OUTPUT: Integration test files. Save report to docs/phase-d-qa/integration_test_report.json.
===================================================================

===================================================================
AGENT: threat-modeling-specialist
Phase: Phase F — F.1 (BLOCKING)
Parallel With: NONE (F.1 blocks F.2)
Depends On: Phase D fully complete + devops-engineer staging ready
Context Budget: 10,000 tokens
Thinking Level: HIGH | budget_tokens: 10,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 10,000 tokens. Thinking: HIGH (budget_tokens: 10,000). Your output verified by hallucination-detector.

You are threat-modeling-specialist executing Phase F.1 — STRIDE/PASTA threat model for the RAG Refinement System bug-fix sprint.

AGREED CONTRACTS:
- Scope = fix only. ADV-001 (deeper Qdrant ACL hardening) is advisory — NOT a blocking finding.
- cyber-mathematics-expert (opus) is auto-invoked for attack-tree min-cut costs + CVSS MacroVectors.
- ALL blocking threat counts must = 0 before F.2 begins.

TASK:
1. STRIDE analysis: which STRIDE categories each fix addresses (BUG-002 IDOR=Elevation of Privilege; BUG-005 JWT=Spoofing; BUG-009 singleton=Tampering+DoS)
2. PASTA threat analysis on BUG-002: model attacker capabilities for IDOR
3. CVSS v3.1 vector string + score for each threat
4. Assess if any fix creates NEW threats (regression threat analysis)
5. Document ADV-001 as advisory — not in blocking counts

GATE: ALL blocking threat counts = 0 before F.2. Advisory items documented separately.
OUTPUT: Save f1_threat_model.json to docs/phase-f-security/f1_threat_model.json.
Format: {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "advisory_items": ["ADV-001: ..."], "verdict": "F1_APPROVED"}
===================================================================

===================================================================
AGENT: penetration-tester
Phase: Phase F — F.3 (parallel with api-security-auditor + auth-security-specialist)
Parallel With: api-security-auditor, auth-security-specialist
Depends On: Phase F.2 complete + devops-engineer staging seeded
Context Budget: 10,000 tokens
Thinking Level: HIGH | budget_tokens: 10,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 10,000 tokens. Thinking: HIGH (budget_tokens: 10,000). Active exploit chain reasoning.

You are penetration-tester executing Phase F.3 active exploitation testing on staging.

AGREED CONTRACTS:
- Two test tenants: tenant-alpha (50 chunks, 3 sections) + tenant-beta (30 chunks, 2 sections)
- IDOR test: authenticate as tenant-beta, section_ids=[], assert exactly 0 chunks in response
- Blast radius: tenant-alpha + tenant-beta test data only; NOT production tenant IDs

ACTIVE TEST SCENARIOS:
1. IDOR (BUG-002): auth as tenant-beta + section_ids=[] → assert 0 chunks; try section_ids=None; try section_ids omitted
2. JWT bypass (BUG-005): service starts without JWT_ISSUER; iss validated when JWT_ISSUER set; wrong iss → 401
3. Rate limiter bypass (BUG-009): 100 concurrent requests at startup; verify rate limit budget not doubled
4. API key store (BUG-009): register key; verify valid on subsequent request; test under cold-start concurrency

OUTPUT: Save f3_pentest_report.json to docs/phase-f-security/f3_pentest_report.json. Zero-tolerance for hidden findings.
===================================================================

===================================================================
AGENT: security-compliance-mapper
Phase: Phase F — F.5
Parallel With: NONE (after F.4)
Depends On: F.1 + F.2 + F.3 + F.4 reports
Context Budget: 5,000 tokens
Thinking Level: MEDIUM | budget_tokens: 5,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 5,000 tokens. Thinking: MEDIUM (budget_tokens: 5,000). Regulatory mapping.

You are security-compliance-mapper executing Phase F.5 — regulatory compliance mapping.

Applicable regulations:
- DPDP Act 2023 §4: tenant isolation (BUG-002 IDOR direct violation; ADV-001 residual gap)
- DPDP Act 2023 §8: data subject rights (verify fix doesn't break access/erasure endpoints)
- CERT-In Directions 2022 §3(v): 6h incident reporting for auth/security incidents (BUG-005, BUG-009)
- OWASP API Security Top 10 v2023: BOLA (BUG-002), Broken Auth (BUG-005, BUG-009)
- IT Act 2000 §43A: reasonable security practices (all fixes collectively)

TASK:
1. Map each F.1–F.4 finding to applicable regulation(s)
2. Assign regulatory breach severity per finding
3. Document evidence gaps (where fix doesn't fully satisfy regulation)
4. Note ADV-001 under DPDP §4 as residual gap requiring next sprint
5. Verify CERT-In 6h reporting requirement is documented in incident runbook

OUTPUT: Save f5_compliance_map.json to docs/phase-f-security/f5_compliance_map.json.
===================================================================

===================================================================
AGENT: security-lead-auditor
Phase: Phase F — F.6 (BINARY verdict gate)
Parallel With: NONE
Depends On: F.1 + F.2 + F.3 + F.4 + F.5 complete
Context Budget: 12,000 tokens
Thinking Level: XHIGH | budget_tokens: 20,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 12,000 tokens. Thinking: XHIGH (budget_tokens: 20,000). Full risk aggregation.

You are security-lead-auditor executing Phase F.6 — final Security Audit BINARY verdict.

CRITICAL: Return EXACTLY "SECURITY APPROVED" or "SECURITY REJECTED". Binary only.

APPROVED: ALL finding counts = 0 (Critical=0, High=0, Medium=0, Low=0, Info=0)
ADV-001 (Qdrant ACL hardening) is advisory — does NOT count toward totals. MUST be documented.
REJECTED: ANY finding of ANY severity → itemized list to Phase B implementers → fix → re-run F-phase → re-run F.6.

TASK:
1. Aggregate all F.1–F.5 findings
2. CVSS v3.1 vector + score for each finding (auto-invoke cyber-mathematics-expert for FAIR+ALE)
3. Build risk matrix: severity × likelihood grid
4. If ANY count > 0 → REJECTED with itemized list

OUTPUT: Save security_audit_report.json to docs/phase-f-security/security_audit_report.json.
Phase G (deploy) PERMANENTLY BLOCKED until SECURITY APPROVED.
===================================================================

===================================================================
AGENT: reliability-auditor
Phase: Phase E — Final Reliability Gate
Parallel With: NONE
Depends On: Phase C (NLI=1.0, FactScore=1.0) + Phase D (DRE=1.0, Coverage=100%) + Phase F (Security APPROVED)
Context Budget: 6,000 tokens
Thinking Level: XHIGH | budget_tokens: 20,000 [Rule 1: EXCELLENCE→XHIGH, sonnet ceiling]

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 6,000 tokens. Thinking: XHIGH (budget_tokens: 20,000). Rule 1 applied.

You are reliability-auditor executing Phase E — final RS computation.

TASK:
1. NLI from Phase C (must = 1.0)
2. FactScore from Phase C (must = 1.0)
3. DRE from Phase D (must = 1.0)
4. Coverage from Phase D (must = 100% = 1.0)
5. CVSS findings from security_audit_report.json (must = Security APPROVED / all counts = 0)
6. RS = (NLI × FactScore × DRE × Coverage)^(1/4)
   If CVSS findings exist → reduce RS (auto-invoke anti-hallucination-mathematician + cyber-mathematics-expert for RS formula with CVSS term)
7. RS target = 1.0 MANDATORY. No exceptions. No rounding.

PHASE E RETRY LOOP: RS < 1.0 → identify failing component → return to appropriate phase:
  NLI/FactScore < 1.0 → Phase C retry loop
  DRE/Coverage < 1.0 → Phase D retry loop
  CVSS unresolved → Phase F retry loop
  Then re-run Phase E. NO iteration limit. Phase G NEVER executes while RS < 1.0.

OUTPUT: Save phase_e_rs_report.json to docs/phase-e-reliability/phase_e_rs_report.json.
Format: {"nli": 1.0, "factScore": 1.0, "dre": 1.0, "coverage": 1.0, "rs": 1.0, "verdict": "RS_APPROVED"}
===================================================================

===================================================================
AGENT: devops-engineer
Phase: Phase G — Production Deploy
Parallel With: NONE
Depends On: RS = 1.0 (RS_APPROVED) + Security APPROVED
Context Budget: 3,000 tokens
Thinking Level: MEDIUM | budget_tokens: 5,000

PROMPT:
WORKING DIRECTORY & LIBRARY PATH: C:\Users\techd\Documents\workspace-spring-tool-suite-4-4.27.0-new\claude-global-library
Master KG loaded: 254 agents (deduped), 451 skills, 49 domains, 23 math masters.
Context Budget: 3,000 tokens. Thinking: MEDIUM (budget_tokens: 5,000).

You are devops-engineer executing Phase G — production deployment.

PRE-CONDITIONS (HARD — HALT if any not met):
1. phase_e_rs_report.json verdict = "RS_APPROVED" and rs = 1.0
2. security_audit_report.json verdict = "SECURITY APPROVED"
3. All 10 bug fix diffs merged to build/rag-refinement-product branch
4. CI green (all Phase D tests passing)

TASK:
1. Verify all pre-conditions — HALT and report blocker if any fail
2. Deploy via existing CI/CD pipeline
3. Post-deploy smoke tests (regression verification):
   - POST /v1/answer → verify 200 + streaming (BUG-001 regression)
   - Retrieval with section_ids=[] → verify 0 results (BUG-002 regression)
   - Restart service without JWT_ISSUER → verify service starts (BUG-005 regression)
   - Simulate DB outage → verify read endpoints return 503 not 500 (BUG-007 regression)
4. Update CHANGELOG.md: add entry for 10-bug WSJF sprint
5. Bump VERSION: patch increment (x.y.Z → x.y.Z+1)

OUTPUT: Save deploy_report.json to docs/phase-g-deploy/deploy_report.json.
===================================================================

---

# EXECUTION SUMMARY

```
Master KG: 254 agents (deduped), 451 skills, 49 domains, 23 math masters, 4296 edges
Source: knowledge-graph/_master/ | Built: 2026-06-07 | Library: v29.10.0

KG Graph Queries Used:
  AGENT_USES_SKILL   — resolved for 11 active agents
  COORDINATES_WITH   — 7 pairs → Team Alignment resolved
  DELEGATES_MATH_TO  — 3 math master routings (mathematics-engineer, cyber-mathematics-expert, anti-hallucination-mathematician)
  SKILL_REQUIRES_SKILL — prereqs checked for python-backend-engineer, database-engineer, auth-security-specialist
  REGULATED_BY       — DPDP Act 2023 + CERT-In Directions 2022 (2 compliance links confirmed)
  shared_agents.json — 4 cross-domain agents identified (consensus-agent, hallucination-detector, context-faithfulness-engineer, reliability-auditor)

Context Engineering: Differential GSD activated | 10 story windows | avg 4K tokens | Phase 7 AR.3 creates windows

Consensus Gates:
  AR.5 (Phase 7): BINARY ROUTING APPROVED/REJECTED | 14-point | loops until APPROVED
  IR.5 (Phase 8): BINARY IMPLEMENTATION READY/BLOCKED | 10-point | loops until READY
  F.6 (Phase F): BINARY SECURITY APPROVED/REJECTED | zero-finding threshold | loops until APPROVED

Hallucination Gates: mandatory after every agent output across ALL phases

Security Audit: Phase F pipeline | Depth: FULL (BUG-002 IDOR mandates F.3 active exploit)
  F.1: threat-modeling-specialist (blocking) | F.2: sast-engineer ∥ secrets-detection-specialist ∥ dependency-vulnerability-analyst
  F.3: api-security-auditor ∥ auth-security-specialist ∥ penetration-tester
  F.4: infrastructure-security-auditor ∥ crypto-security-specialist
  F.5: security-compliance-mapper (DPDP + CERT-In) | F.6: security-lead-auditor (BINARY gate)
  Verdict: SECURITY APPROVED required before Phase E | Blocks Phase G

Reliability Score Target: RS = 1.0 MANDATORY (ALL domains — no exceptions)
  Inputs: NLI=1.0 (Phase C) + FactScore=1.0 (Phase C) + DRE=1.0 (Phase D) + Coverage=100% (Phase D) + CVSS clean (Phase F)
  Deploy permanently blocked until RS = 1.0

Team Alignment: 7 pairs resolved | Contracts injected into all affected agent prompts

ADRs: ADR-001 (max_tokens=8192) | ADR-002 (None guard on empty section_ids) | ADR-003 (threading.Lock DCL) | ADR-004 (error-only SSE) | ADR-005 (deepcopy before ainvoke)

Thinking Budget Summary:
  EXCELLENCE (opus, 64K): agile-business-mathematics-expert, mathematics-engineer, cyber-mathematics-expert, anti-hallucination-mathematician
  XHIGH (sonnet, 20K): consensus-agent ×2, solution-architect, security-lead-auditor, reliability-auditor
  HIGH (sonnet, 10K): python-backend-engineer, auth-security-specialist ×2, test-management-agent, prompt-generation-expert, hallucination-detector, context-faithfulness-engineer, security-testing-engineer ×2, threat-modeling-specialist, api-security-auditor, penetration-tester, infrastructure-security-auditor, crypto-security-specialist, business-analyst-agent, product-manager-agent
  MEDIUM (sonnet, 5K): orchestrator-agent, context-engineering-agent, database-engineer, unit-testing-specialist, integration-testing-engineer, api-testing-engineer, sast-engineer, secrets-detection-specialist, dependency-vulnerability-analyst, security-compliance-mapper, devops-engineer
  LOW (sonnet, 1K): scrum-master-agent
  Rule 1 cap: 1 agent (reliability-auditor: EXCELLENCE→XHIGH)
  Total thinking budget: ~556,048 tokens across 35+ agent invocations

Stop Points: STOP 7 (ar5_routing_verdict.json) | STOP 8 (ir5_alignment_verdict.json)
Mode: Brownfield | Entry: Phase 7 | Phases skipped: 0–6
Total Agent Calls: 35+ (phased execution with retry loops)

Status: READY FOR EXECUTION
```
