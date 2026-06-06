# Phase E - Reliability Gate Report

**System:** RAG Refinement System
**Gate:** Composite Reliability Score RS = (NLI x FactScore x DRE x Coverage)^(1/4)
**Gate target:** RS = 1.0 exactly
**Auditor:** reliability-auditor (audit/compute only; modified nothing except the two files under docs/phase-E-reliability/)
**Date:** 2026-06-06

---

## 1. Verified Components

Each component was independently re-verified against reality, not merely read from the prior phase JSON.

| Component | Value | Source (verified) | Independent verification |
|-----------|-------|-------------------|--------------------------|
| NLI | 1.0 | docs/phase-C-hallucination/faithfulness_scorecard.json (`nli`) | 32/32 entailed checks; verdict PASS; 0 contradictions; 0 unverifiable. Cited evidence resolves to live adapter code (backend/app/adapters/*) wired through backend/app/api/dependencies.py. |
| FactScore | 1.0 | docs/phase-C-hallucination/faithfulness_scorecard.json (`factscore`) | 32/32 referenced entities (endpoints, schema fields, agents, functions, section_id semantics) verifiably resolvable; verdict PASS. |
| DRE | 1.0 | docs/phase-D-qa/qa_verdict.json (`dre`) | defects_found_in_test=0, defects_escaped=0; 0/(0+0) reported as 1.0 by the no-escape convention; defects_logged=0. |
| Coverage | 1.0 (100%) | docs/phase-D-qa/qa_verdict.json (`coverage_pct_python`) AND independent re-run (below) | Re-ran the exact coverage command; ACTUAL TOTAL coverage matches the JSON at 100% statement and 100% branch. |

### 1.1 Independent coverage re-run (the load-bearing re-verification)

Command executed by this auditor:

```
python -m pytest --cov=backend --cov=ingestion --cov=router --cov=db --cov-report=term
```

ACTUAL terminal output (the REAL number used in the RS computation):

```
TOTAL   1631   0   228   0   100%
265 passed, 1 skipped, 10 warnings in 8.16s
```

- **Actual TOTAL coverage: 100%** (statements 1631 total / 0 missed; branches 228 total / 0 partial)
- **Actual pytest result: 265 passed, 1 skipped** (matches the expected 265 passed / 1 skipped)
- Every one of the 37 measured modules across backend, ingestion, router, db reports 100%.
- The single skipped test is `test_forward_then_rollback_restores_baseline`, an opt-in live-Postgres migration test out of scope offline; it does not touch application-module coverage.

The REAL re-run number equals the prior Phase D JSON (100% / 265 passed / 1 skipped). No discrepancy; the verified Coverage component is 1.0.

---

## 2. RS Computation

Using the verified component values:

```
RS = (NLI x FactScore x DRE x Coverage)^(1/4)
   = (1.0 x 1.0 x 1.0 x 1.0)^(1/4)
   = (1.0)^(0.25)
   = 1.0
```

**RS = 1.0** -- meets the gate target (RS = 1.0 exactly).

Components below 1.0: **none.**

---

## 3. Security Factor

Source: docs/phase-F-security/security_verdict.json

| Metric | Value |
|--------|-------|
| Verdict | APPROVED |
| unresolved_total | 0 |
| Unresolved Critical | 0 |
| Unresolved High | 0 |
| Status totals | open=0, fixed=4, accepted_exception=4 |
| Production-code SAST findings | 0 |
| Real secrets committed | 0 |

The 4 genuine dependency CVEs (F-001..F-004) are FIXED via secure version pins in pyproject.toml (PyJWT 2.13.0, starlette, python-multipart, python-dotenv), re-audited clean with the suite green (265 passed / 1 skipped, zero regression). The remaining items are justified ACCEPTED_EXCEPTION (test-only false positives and dev-tooling-only frontend CVEs absent from the production bundle) or verification-only confirmations (auth alg-pinning, tenant IDOR guard, prompt-injection fencing, non-root container, DPDP controls).

**Security factor: unresolved_total = 0, no unresolved Critical/High.** The security gate does NOT force an RS FAIL.

---

## 4. Cascading-Failure Analysis

The deploy block is gated by a cascade across phases C (faithfulness), D (QA/coverage), and F (security). The block conditions are:

- ANY of {NLI, FactScore, DRE, Coverage} < 1.0 -> RS gate FAIL, deploy BLOCKED.
- ANY unresolved Critical/High security finding > 0 -> RS gate FAIL regardless of the formula.

Evaluation against verified inputs:

- NLI = 1.0, FactScore = 1.0, DRE = 1.0, Coverage = 1.0 -> no component below 1.0.
- unresolved Critical = 0, unresolved High = 0, unresolved_total = 0 -> no security override.

**With all four gate components at exactly 1.0 and zero unresolved security findings, every deploy-block condition is CLEARED.** There is no cascading failure: no component routes back to an earlier phase for remediation (C for NLI/FactScore, D for DRE/Coverage, F for security). The chain is fully green end to end.

---

## 5. Output-Contract Compliance

API <-> OpenAPI faithfulness was established in Phase C and is cited here without re-audit, per scope.

- Source: docs/phase-C-hallucination/faithfulness_scorecard.json (ground truth includes docs/phase-1-api-contracts/openapi.yaml; confirmed present on disk).
- The Phase C verdict_reason records: "No endpoint, schema field, or invariant changed - openapi stays authoritative." The IngestOutcome mapping (FIX-C-02), the /v1/route routing-only contract (FIX-C-01), and the live store/generation paths (FIX-C-03) are all ENTAILED against the OpenAPI contract at FactScore = 1.0 (32/32).
- The openapi.yaml ground-truth file is present at docs/phase-1-api-contracts/openapi.yaml.

Output-contract compliance: **CONFIRMED** (cited from Phase C; no re-audit performed).

---

## 6. Final Deploy Decision

| Item | Result |
|------|--------|
| NLI | 1.0 |
| FactScore | 1.0 |
| DRE | 1.0 |
| Coverage (re-run) | 1.0 (100% statement + 100% branch) |
| Pytest (re-run) | 265 passed, 1 skipped |
| RS | 1.0 |
| Gate target | RS = 1.0 |
| security_unresolved | 0 |
| Components below 1.0 | none |
| **Gate verdict** | **PASS** |
| **Deploy authorized** | **true** |

All four reliability components are exactly 1.0, the composite RS = 1.0 meets the gate target precisely, and security has zero unresolved findings (zero Critical/High). All deploy-block conditions are cleared. **The Phase E Reliability Gate PASSES and deployment is AUTHORIZED.**
