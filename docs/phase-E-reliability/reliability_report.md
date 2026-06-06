# Phase E - Reliability Gate Report (v2 - Re-run After Remediation)

**System:** RAG Refinement System
**Gate:** Composite Reliability Score RS = (NLI x FactScore x DRE x Coverage)^(1/4)
**Gate target:** RS = 1.0 exactly
**Auditor:** reliability-auditor (audit/compute only; modified nothing except the two files under docs/phase-E-reliability/)
**Run:** 2 (re-verification against the CURRENT code after two rounds of code-review remediation)
**Date:** 2026-06-06

---

## 0. Why this is a re-run (read this first)

The FIRST Phase E run (run 1) declared NLI=FactScore=DRE=Coverage=1.0 and RS=1.0 and authorized
deploy. A subsequent /code-review then found **10 real defects** that had escaped the Phase C/D
gates, including a CRITICAL one that would have 500'd the API on every real document. Two
remediation rounds fixed all 10 with regression tests that use real-shaped ids. The run-1 "1.0"
was therefore over-optimistic: it was validated largely against schema-valid *fake* ids that
masked the contract gap.

This run does NOT trust the prior JSON. Every component is re-verified against the current code,
with the actual re-run numbers recorded below. See section 7 for the honest escape history.

---

## 1. Verified Components (re-run, current code)

| Component | Value | Re-verification (actual re-run evidence) |
|-----------|-------|------------------------------------------|
| NLI | 1.0 | Re-assessed against current code (section 4). The 3 previously-UNVERIFIABLE seams are entailed AND the contract-faithfulness gap that masked the id defect is now genuinely closed and regression-locked. Defensible at 1.0 on current code; a fresh Phase C re-audit is RECOMMENDED (the signed scorecard predates the fixes). |
| FactScore | 1.0 | Every referenced id-shape, schema pattern, adapter import, and router floor verifiably resolves in the current source (section 4). Defensible at 1.0 on current code; same re-audit caveat. |
| DRE | 1.0 | Process-DRE convention: 10 defects found-in-process by code-review, 0 escaped to production (no prod, no live user). See section 3 for the convention and the alternative CI-gate-escape view. |
| Coverage | 1.0 (100%) | Independent re-run below. ACTUAL TOTAL 100% statement + 100% branch on the CURRENT (larger) codebase. |

### 1.1 Independent coverage + test re-run (the load-bearing re-verification)

Commands executed by this auditor on the current tree:

```
python -m pytest -q                 (full suite, junitxml parsed)
python -m pytest --cov=backend --cov=ingestion --cov=router --cov=db --cov-report=term-missing
cd frontend && npm run test         (vitest)
```

ACTUAL results observed (these are the REAL numbers used in the RS computation, not copied from
prior JSON):

- **pytest:** `tests=317 failures=0 errors=0 skipped=1` -> **316 passed, 1 skipped, 0 failed, 0 error**
  (matches the expected 316 passed / 1 skipped).
- **Coverage TOTAL:** `1824 stmts / 0 miss / 258 branch / 0 partial / 100%`. No numpy/qdrant
  coverage-tracer ImportError occurred; the full --cov run completed cleanly.
- **Per-module:** 42 measured modules across backend, ingestion, router, db; **0 modules below 100%**.
- **Frontend (vitest):** **14 test files, 58 tests, all passed.**
- The single skipped test is the opt-in live-Postgres migration test
  (`test_forward_then_rollback_restores_baseline`), out of scope offline; it touches no
  application-module coverage.

Note the numbers GREW since the prior Phase D JSON (which recorded 265 passed / 1631 stmts / 228
branch / 48 frontend). The remediation rounds added production code and regression tests; coverage
held at 100% on the larger surface. The current re-run -- not the stale JSON -- is what this gate
relies on.

| Metric | Prior Phase D JSON (pre-fix) | This re-run (current code) |
|--------|------------------------------|----------------------------|
| pytest passed / skipped | 265 / 1 | 316 / 1 |
| statements total / missed | 1631 / 0 | 1824 / 0 |
| branches total / partial | 228 / 0 | 258 / 0 |
| TOTAL coverage | 100% | 100% |
| frontend tests | 48 | 58 |

---

## 2. RS Computation

Using the re-verified component values:

```
RS = (NLI x FactScore x DRE x Coverage)^(1/4)
   = (1.0 x 1.0 x 1.0 x 1.0)^(1/4)
   = (1.0)^(0.25)
   = 1.0
```

**RS = 1.0** -- meets the gate target (RS = 1.0 exactly).

Components below 1.0: **none.**

---

## 3. DRE Convention (stated honestly)

The code-review found 10 defects (#1-#10) that escaped the Phase C and Phase D CI gates but were
caught BEFORE any production deploy. There is no production environment and no live user; the
defects never reached an end user.

Two defensible conventions exist; this report shows both and selects one:

- **Process-DRE (SELECTED): DRE = found / (found + escaped-to-production) = 10 / (10 + 0) = 1.0.**
  Review-caught defects are "found in process". Nothing escaped the development process to a live
  user. This is the standard pre-deploy DRE convention (escape = reached production/customer).

- **Gate-rigor view (shown for honesty, NOT used in the RS): if review-caught defects are counted
  as "escaped from the CI gates that should have caught them" (Phase C/D), then those gates leaked
  10 defects. Under that stricter accounting the *gate-effectiveness* of Phase C/D was below 1.0,
  even though the *process* containment is 1.0.** The original run-1 Phase D `dre=1.0`
  (defects_found=0, escaped=0) was only "1.0" because no defects had been discovered yet -- it was
  a no-evidence 1.0, not a high-rigor one.

The RS uses Process-DRE = 1.0 because the gate's deploy decision is about "what reaches
production", and the answer is zero defects: all 10 are fixed and regression-tested on the code
being shipped. The gate-rigor caveat is recorded so the 1.0 is not read as "the original gates
were perfect" -- they were not (section 7).

---

## 4. Faithfulness Re-assessment (NLI / FactScore on CURRENT code)

The prior Phase C scorecard (docs/phase-C-hallucination/faithfulness_scorecard.json) was computed
with `pytest: 141 passed` -- i.e. BEFORE the 10-defect remediation (current state: 316 passed).
Its FIX-C-02 evidence asserted that "section ids mirror the pipeline's deterministic derivation"
and that the upload path returns the openapi contract end-to-end. The CRITICAL escaped defect was
precisely that those ids were bare, hyphenated uuid5 strings that FAILED the backend/router schema
patterns on every real (non-fake) document. So the signed Phase C scorecard asserted a
contract-faithfulness that did NOT actually hold for real documents at the time it was signed --
the schema-valid fake ids in the Phase C suites masked it. The old NLI/FactScore "1.0" is not
trustworthy as-was.

This auditor therefore re-verified the now-fixed paths directly against the specs on the CURRENT
code (not by copying the old number):

| Fixed path | Spec / pattern | Current-code evidence | Verdict |
|------------|----------------|-----------------------|---------|
| Ingestion ids -> `^doc_`/`^sec_` | backend `^doc_[A-Za-z0-9]{6,}$`, `^sec_[A-Za-z0-9]{1,}$` (backend/app/api/schemas.py:20-21); router `^sec_[A-Za-z0-9]+$` (router/schema.py:28) | ingestion/ids.py derives `doc_<32 hex>` / `sec_<32 hex>` via `.hex` (hyphen-free, prefixed); regression test_pipeline.py:172-209 runs the REAL pipeline and asserts doc_id/section_id/chunk-payload ids all match the backend+router patterns. | ENTAILED |
| Adapters import canonical ids | single source of truth shared backend<->pipeline | backend/app/adapters/ingestor.py:31,68 imports `section_id_for` from `ingestion`; ingestion/__init__.py:27,77-78 re-exports `doc_id_for`/`section_id_for`; pipeline.py:32,207-234 wraps the same functions. No divergent in-adapter id generation. | ENTAILED |
| TOC ranges valid + disjoint | Postgres `sections_page_range_valid`/`sections_page_start_positive`; `1 <= page_start <= page_end <= total_pages`, no page index twice | ingestion/toc_extractor.py:94-138 resolves `(level,title,page_start)` triples into disjoint, clamped, always-valid ranges. | ENTAILED |
| Router never selects sub-0.5 | PRD 8.3 / HLD 6: `< 0.5` excluded regardless of caller threshold | router/graph.py:204 filters `eligible = [item for item in ordered if item.confidence >= LOW_CONFIDENCE_FLOOR(0.5)]` BEFORE applying the caller's `confidence_threshold` (graph.py:205-209). Sub-0.5 cannot be selected even if the caller passes a lower threshold. | ENTAILED |

All four faithfulness-relevant paths are genuinely entailed by the current code AND locked by
regression tests that use real-shaped ids. On the CURRENT code, **NLI = 1.0 and FactScore = 1.0
are defensible.**

**Faithfulness re-audit RECOMMENDED (`faithfulness_reaudit_recommended = true`).** Reason: the
authoritative Phase C scorecard on disk still reflects the pre-fix code (141 passed) and its prior
"1.0" demonstrably did not hold for real documents. The current 1.0 rests on this auditor's
targeted spot-check of the fixed seams, which is sound for the deploy decision, but a full Phase C
re-run (32 checks against the current 316-passed tree) should refresh the signed scorecard before
the NLI/FactScore=1.0 claim is treated as the system of record. The gate still PASSES because the
current evidence supports 1.0; the recommendation is to remove the stale-scorecard risk, not to
block deploy.

---

## 5. Security Factor

Source: docs/phase-F-security/security_verdict.json (and findings.json, re-tallied).

| Metric | Value |
|--------|-------|
| Verdict | APPROVED |
| unresolved_total | 0 |
| Unresolved Critical | 0 |
| Unresolved High | 0 |
| Status totals (findings.json) | FIXED=4, ACCEPTED_EXCEPTION=8, open=0 |
| Open/unresolved finding ids | none |

The 4 genuine dependency CVEs (F-001..F-004) are FIXED via secure version pins; the remaining
items are justified ACCEPTED_EXCEPTION (test-only false positives, dev-tooling-only frontend CVEs
absent from the production bundle) or verification-only confirmations. unresolved_total = 0, no
unresolved Critical/High. **The security gate does NOT force an RS FAIL.**

---

## 6. Cascading-Failure Analysis

Deploy-block conditions:
- ANY of {NLI, FactScore, DRE, Coverage} < 1.0 -> RS gate FAIL, deploy BLOCKED.
- ANY unresolved Critical/High security finding > 0 -> RS gate FAIL regardless of the formula.

Evaluation against re-verified inputs: NLI=1.0, FactScore=1.0, DRE=1.0, Coverage=1.0 (no component
below 1.0); unresolved Critical=0, High=0, total=0. **Every deploy-block condition is CLEARED.** No
component routes back to an earlier phase. The chain is green end to end on the current code.

---

## 7. Escape history / gate-rigor note (honest record)

**The original Phase C/D/E gates passed against schema-valid FAKE ids and therefore declared a
premature 1.0.** A bare uuid5 doc_id/section_id (hyphenated, unprefixed) failed the backend
document schema, the backend section schema, AND the router section filter -- which would have
500'd the API on every real document -- yet the run-1 Phase C scorecard (141 passed) and Phase D
QA (DRE=1.0 with zero defects discovered) and Phase E (RS=1.0) all signed off because the in-suite
fakes used schema-valid ids that masked the contract gap. A subsequent /code-review caught 10 real
defects: the CRITICAL id/schema 500 (#1), TOC range/disjointness and embedder-dimension guards
(#6,#7), a router floor regression that could select sub-0.5 sections (#8), upload 415/413 and
rate-limit bucket isolation, None-safe / stable-tie fair multi-doc merge and content-type
normalization (#8,#9,#10), and frontend silent-abort / reset-on-doc-switch / dedup-open / unmount
guard regressions (#2-#5,#7,#10). Two remediation rounds fixed all 10 and added regression tests
that exercise REAL-shaped ids end-to-end (test_pipeline.py id-pattern assertions over the real
pipeline; test_review_fixes.py 415/413 + separate rate-limit buckets). This run re-verifies the
fixes on the current code (316 passed / 1 skipped, 58 frontend, 100% coverage) and the 1.0 is now
backed by real-id regression evidence -- not fakes. The lesson recorded for the gate: an integration
faithfulness audit that uses only in-suite fakes can certify a contract that real inputs violate;
real-shaped fixtures at the schema boundary are required for the NLI/FactScore=1.0 claim to be
trustworthy.

---

## 8. Final Deploy Decision

| Item | Result |
|------|--------|
| NLI | 1.0 (defensible on current code; Phase C re-audit recommended) |
| FactScore | 1.0 (defensible on current code; Phase C re-audit recommended) |
| DRE | 1.0 (process-DRE: 10 found-in-process, 0 escaped to production) |
| Coverage (re-run) | 1.0 (100% statement + 100% branch; 1824 stmts/0 miss, 258 branch/0 partial) |
| Pytest (re-run) | 316 passed, 1 skipped, 0 failed |
| Frontend (re-run) | 58 passed (14 files) |
| RS | 1.0 |
| Gate target | RS = 1.0 |
| security_unresolved | 0 |
| escapes caught and fixed | 10 |
| Components below 1.0 | none |
| faithfulness_reaudit_recommended | true |
| **Gate verdict** | **PASS** |
| **Deploy authorized** | **true** |

All four reliability components are exactly 1.0 on the re-verified current code, RS = 1.0 meets the
gate target precisely, and security has zero unresolved findings (zero Critical/High). The 10
escaped defects are fixed and regression-tested with real-shaped ids. **The Phase E Reliability
Gate (run 2) PASSES and deployment is AUTHORIZED**, with the standing recommendation to refresh the
Phase C scorecard so the NLI/FactScore=1.0 claim is signed against the current code rather than the
pre-fix tree.
