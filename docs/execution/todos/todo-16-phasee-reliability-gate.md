# TODO-16 - PhaseE reliability gate

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-16",
  "title": "PhaseE reliability gate",
  "phase": "E",
  "parallel_group": "E",
  "depends_on": [
    "TODO-13",
    "TODO-14",
    "TODO-15"
  ],
  "status": "pending",
  "agents": [
    "reliability-auditor"
  ],
  "produces": [
    "reliability report",
    "RS value"
  ],
  "gate": "RS = 1.0 (retry loop, no deploy below 1.0)",
  "stop_point": null,
  "context_file": "todos/todo-16-phasee-reliability-gate.md",
  "completed_artifacts": []
}
```

## Dispatch instruction (hand this packet to orchestrator-agent)

Act as **orchestrator-agent**. Execute this TODO using the embedded agent
prompt(s) below plus the shared context in ../_common_context.md. Honor the
dependencies, gate, and STOP point in Metadata. Produce every artifact listed
in Metadata.produces. Math masters are auto-invoked, never sequenced directly.

Checkpoint protocol (REQUIRED for resume):
1. Before starting: set this TODO status to "in_progress" in ../ledger.json.
2. After artifacts are verified on disk: set status to "done" and fill
   completed_artifacts.
3. If a STOP point is defined: set status "awaiting_user" and pause.
4. If interrupted/rate-limited mid-run: leave status "in_progress"; on resume
   this TODO re-runs from scratch (make writes idempotent).

## Embedded agent prompt(s) from the bundle

===================================================================
AGENT: reliability-auditor
Phase: E (final gate before deploy)
Parallel With: NONE
Depends On: Phase C, D, F all APPROVED
Context Budget: 20,000 tokens | Sources: [phase-c-scores, phase-d-dre-coverage, phase-f-findings, output-contracts]
Thinking Level: XHIGH | budget_tokens: 20,000
Thinking Override: Rule 1 cap (EXCELLENCE→XHIGH on sonnet)
Hallucination Risk: N/A (this IS the auditor)

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 20,000 tokens. Do not request or reference context outside this budget.
Thinking configured at XHIGH (budget_tokens: 20,000). EXCELLENCE was requested by role but Rule 1 caps sonnet at XHIGH; the final RS computation + cascading-failure DAG analysis fits within this budget. Reason within this budget.

OBJECTIVE: Compute composite RS = (NLI × FactScore × DRE × Coverage)^(1/4) once before deploy. (anti-hallucination-mathematician auto-invoked.)

INSTRUCTIONS:
1. Pull NLI + FactScore (Phase C), DRE + Coverage (Phase D), unresolved findings (Phase F).
2. Compute RS; run cascading-failure DAG + POMDP monitoring validation + output-contract compliance.
3. RETRY LOOP: if RS<1.0 → identify the <1.0 component → route to Phase C (NLI/FactScore) / Phase D (DRE/Coverage) / Phase F (findings) → fix → re-run → re-compute. No iteration limit.

OUTPUT FORMAT: reliability report + RS value. GATE: RS = 1.0 mandatory; Phase G blocked below 1.0.

CONSTRAINTS: 1.0 is the only acceptable score — no domain relaxation, no partial approval. Re-state: deploy is permanently blocked until RS = 1.0.
===================================================================

## Predecessor artifacts to load as input
- TODO-13 -> detection report, faithfulness scorecard
- TODO-14 -> IEEE 829 plan, test suites, coverage report
- TODO-15 -> docs/phase-F-security/security_audit_report.md
