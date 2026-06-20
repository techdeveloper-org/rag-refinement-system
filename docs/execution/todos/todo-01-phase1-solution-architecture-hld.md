# TODO-01 - Phase1 solution architecture HLD

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-01",
  "title": "Phase1 solution architecture HLD",
  "phase": "1",
  "parallel_group": "P1",
  "depends_on": [
    "TODO-00"
  ],
  "status": "pending",
  "agents": [
    "solution-architect",
    "consensus-agent",
    "context-engineering-agent"
  ],
  "produces": [
    "docs/phase-1-architecture/hld.md"
  ],
  "gate": "consensus BINARY APPROVED (zero open items)",
  "stop_point": "User APPROVED HLD",
  "context_file": "todos/todo-01-phase1-solution-architecture-hld.md",
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
AGENT: solution-architect (+ consensus-agent, context-engineering-agent)
Phase: 1 — Solution Architecture (Mode A) — also satisfies main-pipeline Phase A + A.5
Parallel With: NONE (consensus-agent loops with it)
Depends On: business-analyst-agent (Phase 0 — phase1_architect_brief.md)
Context Budget: 20,000 tokens | Sources: [phase1_architect_brief.md, refreshed-PRD.md, ADR-1..10]
Thinking Level: XHIGH | budget_tokens: 20,000
Thinking Override: Rule 2 role default (solution-architect XHIGH)
Hallucination Risk: HIGH — verified by hallucination-detector + context-faithfulness-engineer

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 20,000 tokens. Do not request or reference context outside this budget.
Thinking configured at XHIGH (budget_tokens: 20,000). This level was set because the blueprint spans the entire RAG system (ingestion, routing state machine, dual product surfaces, two data stores) with many cross-cutting trade-offs. Reason within this budget.
Your output will be verified by hallucination-detector. Cite every architectural claim against the PRD or an ADR.

OBJECTIVE: Produce the approved 12-section HLD for the RAG Refinement System via `pipelines/solution-architecture-pipeline/GREENFIELD_GUIDE.md`. Because this runs, main-pipeline Phase A + A.5 are skipped — this HLD is THE blueprint for Phase B.

AGREED CONTRACTS (from Team Alignment — bind these into the HLD):
- Router = in-process async LangGraph function returning {relevant_sections, page_ranges, confidence, fallback, routing_time_ms, rationale}; never calls the generation LLM.
- Postgres = L1/L2 structure store; Qdrant = L3 chunk vectors with section_id payload filter; section_id is the universal join/filter key.
- /v1/route = routing-only (no generation); /v1/answer = SSE-streamed generation for the personal tool.
- DPDP: erasure + access endpoints, no-retention mode purges chunks+sections+raw.

INSTRUCTIONS:
1. C4 Level 1 + Level 2 Mermaid diagrams of the ingestion pipeline + query pipeline.
2. Embed all 10 ADRs (Part 1) with Chosen/Why/Rejected + FR↔NFR traceability.
3. DSA choices per component (e.g., TOC interval tree for page-range lookup; confidence-thresholded top-K selection; LRU TOC cache).
4. STRIDE threat surface; NFR compliance map (latency, accuracy, fallback-rate targets); Little's-Law capacity estimate (delegate to mathematics-engineer — auto-invoked).
5. List Open Architectural Questions for user resolution (Stop 1).
6. Pass NLI=1.0 + FactScore=1.0 + Faithfulness=1.0, THEN consensus-agent BINARY gate (Stop 3). Loop with consensus-agent until APPROVED with zero open items.

OUTPUT FORMAT: HLD → `docs/phase-1-architecture/hld.md`. Artifacts for context-engineering-agent (which runs here in Phase 1.5 of the sub-pipeline and produces the Context Delivery Plan that replaces main-pipeline Phase A.5).

CONSTRAINTS: No implementation. Zero open items before APPROVED. Every tech choice has an ADR. Capacity math delegated, not hand-computed.
===================================================================

## Predecessor artifacts to load as input
- TODO-00 -> PRD.md, docs/phase-0-requirements/phase1_architect_brief.md
