# TODO-13 - PhaseC hallucination gate

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-13",
  "title": "PhaseC hallucination gate",
  "phase": "C",
  "parallel_group": "C",
  "depends_on": [
    "TODO-11",
    "TODO-12"
  ],
  "status": "pending",
  "agents": [
    "hallucination-detector",
    "context-faithfulness-engineer"
  ],
  "produces": [
    "detection report",
    "faithfulness scorecard"
  ],
  "gate": "NLI=1.0 AND FactScore=1.0 (retry loop)",
  "stop_point": null,
  "context_file": "todos/todo-13-phasec-hallucination-gate.md",
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
AGENT: hallucination-detector
Phase: C
Parallel With: context-faithfulness-engineer
Depends On: ALL Phase B agents
Context Budget: 10,000 tokens | Sources: [phase-b-outputs, router-eval-set, citation-claims]
Thinking Level: HIGH | budget_tokens: 10,000
Thinking Override: Rule 4 (HIGH risk)
Hallucination Risk: N/A (this IS the detector)

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 10,000 tokens. Do not request or reference context outside this budget.
Thinking configured at HIGH (budget_tokens: 10,000). Set because NLI scoring + entailment-chain reasoning on the router + answer outputs requires extended reasoning. Reason within this budget.

OBJECTIVE: After every Phase B agent output (especially router + generated answers + refreshed PRD claims), compute NLI faithfulness, SelfCheckGPT consistency, semantic entropy SE(q), FactScore, per-claim severity. (anti-hallucination-mathematician auto-invoked for formulas.)

INSTRUCTIONS:
1. Verify generated answers are entailed by the retrieved section chunks (no claim beyond context).
2. Verify the router never selected a section_id absent from the TOC.
3. Flag every HIGH + MEDIUM claim; produce a detection report.
4. RETRY LOOP: if NLI<1.0 OR FactScore<1.0 → return ALL flagged items to Phase B implementers → re-run → repeat until NLI=1.0 AND FactScore=1.0.

OUTPUT FORMAT: detection report + pass/fail per output. Gate APPROVED only at NLI=1.0 AND FactScore=1.0.

CONSTRAINTS: No proceed to Phase D below 1.0. Re-state: any fabricated citation or non-entailed answer = automatic fail + return to implementers.
===================================================================

## Predecessor artifacts to load as input
- TODO-11 -> ingestion module, LangGraph router module, FastAPI services
- TODO-12 -> frontend/ React SPA
