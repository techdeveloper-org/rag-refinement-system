# TODO-12 - PhaseB3 frontend personal tool

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-12",
  "title": "PhaseB3 frontend personal tool",
  "phase": "B3",
  "parallel_group": "B3",
  "depends_on": [
    "TODO-11"
  ],
  "status": "pending",
  "agents": [
    "react-engineer",
    "ui-ux-designer"
  ],
  "produces": [
    "frontend/ React SPA"
  ],
  "gate": "unit tests pass; UI renders citations + confidence + explainability",
  "stop_point": null,
  "context_file": "todos/todo-12-phaseb3-frontend-personal-tool.md",
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
AGENT: react-engineer (paired with ui-ux-designer)
Phase: B (Group B3 — frontend)
Parallel With: NONE (starts after API contract stub stable)
Depends On: python-backend-engineer (API), ui-ux-designer (Phase 3 tokens)
Context Budget: 5,000 tokens | Sources: [api-contract-delta, design-tokens-delta, explainability-panel-delta]
Thinking Level: MEDIUM | budget_tokens: 5,000
Thinking Override: Rule 3 (SSE streaming state machine)
Hallucination Risk: LOW — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 5,000 tokens. Do not request or reference context outside this budget.
Thinking configured at MEDIUM (budget_tokens: 5,000). Set because the streaming-answer + citation/explainability UI has a non-trivial client state machine. Reason within this budget.

OBJECTIVE: Build the personal-tool SPA (C6) — React + TailwindCSS + Vite: upload, chat with streaming answers, citation cards, routing-confidence meter, "why did you look here?" explainability panel, document library.

AGREED CONTRACTS:
- Consume /v1/answer SSE: render tokens live; on final event show citations[{section_title, page_start, page_end}] + confidence meter from routing.confidence[] + panel listing selected sections (score, page range, rationale).
- Import Phase 3 design tokens (tokens_css.css) + component_library.md — do NOT recreate the design system. APCA Lc≥60 on meter/panel text.
- JWT bearer auth; RFC-7807 error handling.

INSTRUCTIONS:
1. Upload flow → POST /v1/documents → show extracted TOC.
2. Chat → SSE stream → streamed answer + citation cards + confidence meter + explainability panel.
3. Document library (list/delete with DPDP erasure).
4. Function components with explicit return types; precise event-handler types; no `any` (TS standards rules).

OUTPUT FORMAT: React app (components, hooks, api client). TypeScript strict.

CONSTRAINTS: Import tokens, don't reinvent. Accessibility (keyboard nav, APCA). No `any`; `import type` for type-only imports. Re-state: explainability panel + confidence meter are core differentiators — render them on every answer.
===================================================================

## Predecessor artifacts to load as input
- TODO-11 -> ingestion module, LangGraph router module, FastAPI services
