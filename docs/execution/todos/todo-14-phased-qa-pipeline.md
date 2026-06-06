# TODO-14 - PhaseD QA pipeline

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-14",
  "title": "PhaseD QA pipeline",
  "phase": "D",
  "parallel_group": "D",
  "depends_on": [
    "TODO-13"
  ],
  "status": "pending",
  "agents": [
    "test-management-agent",
    "unit-testing-specialist",
    "integration-testing-engineer",
    "e2e-testing-engineer",
    "api-testing-engineer",
    "performance-testing-engineer",
    "ai-model-testing-engineer",
    "data-quality-testing-engineer"
  ],
  "produces": [
    "IEEE 829 plan",
    "test suites",
    "coverage report"
  ],
  "gate": "coverage=100% AND DRE=1.0",
  "stop_point": null,
  "context_file": "todos/todo-14-phased-qa-pipeline.md",
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
AGENT: test-management-agent
Phase: D.1 (BLOCKING — runs before D.2)
Parallel With: NONE
Depends On: Phase C APPROVED
Context Budget: 10,000 tokens | Sources: [hld_v3.md, risk-tier-delta, component-inventory]
Thinking Level: HIGH | budget_tokens: 10,000
Thinking Override: Role default (test-management-agent HIGH)
Hallucination Risk: MEDIUM — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 10,000 tokens. Do not request or reference context outside this budget.
Thinking configured at HIGH (budget_tokens: 10,000). Set because IEEE 829 strategy + risk-based prioritization needs deep reasoning. Reason within this budget.

OBJECTIVE: Produce the IEEE 829 test plan + risk matrix for the RAG system. BLOCKING — no D.2 without an approved strategy.

AGREED CONTRACTS:
- P0 risk: Router confidence thresholding + fallback, targeted-retrieval section filter, citation accuracy.
- P1 risk: ingestion TOC scenarios A/B/C, API auth/rate-limit, DPDP erasure/access.
- Router + retrieval tested with deterministic fixtures (golden TOC + golden section sets).

INSTRUCTIONS: Define scope, risk tiers, test layers (unit/integration/e2e/api/perf/ai-model/data-quality), entry/exit criteria, coverage target = 100%, DRE target = 1.0. Map each component to its test layers and owners.

OUTPUT FORMAT: IEEE 829 plan + risk matrix. GATE: approved strategy before D.2.

CONSTRAINTS: 100% coverage + DRE=1.0 are hard exit gates. Re-state risk tiers at end.
===================================================================

## Predecessor artifacts to load as input
- TODO-13 -> detection report, faithfulness scorecard
