# TODO-05 - Phase4 fullstack reconciliation

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-05",
  "title": "Phase4 fullstack reconciliation",
  "phase": "4",
  "parallel_group": "P4",
  "depends_on": [
    "TODO-04"
  ],
  "status": "pending",
  "agents": [
    "business-analyst-agent",
    "product-manager-agent",
    "solution-architect",
    "ui-ux-designer",
    "consensus-agent",
    "hallucination-detector",
    "context-faithfulness-engineer"
  ],
  "produces": [
    "docs/phase-4-reconciliation/hld_v3.md",
    "docs/phase-4-reconciliation/grand_advisory_items.json"
  ],
  "gate": "GRAND BLUEPRINT APPROVED",
  "stop_point": "User reviews grand blueprint",
  "context_file": "todos/todo-05-phase4-fullstack-reconciliation.md",
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

## Phase roster + pipeline spec (from Part 1 pre-processing table)

| **4 — Full-Stack Reconciliation (Mode A)** | `pipelines/fullstack-validation-pipeline/FULLSTACK_VALIDATION_PIPELINE.md` | `business-analyst-agent`, `product-manager-agent`, `solution-architect`, `ui-ux-designer`, `consensus-agent`, `hallucination-detector`, `context-faithfulness-engineer` | GRAND BLUEPRINT APPROVED | `hld_v3.md`, `design_spec_v2.json`, `grand_advisory_items.json` → `docs/phase-4-reconciliation/` |

Follow the pipeline spec: `pipelines/fullstack-validation-pipeline/FULLSTACK_VALIDATION_PIPELINE.md`
Run the listed lead agents per that spec; enforce the gate and STOP point above.
This phase has no standalone agent block in the bundle by design - it is a
self-contained sub-pipeline launched from its spec file.

## Predecessor artifacts to load as input
- TODO-04 -> docs/phase-3-design/wireframes, docs/phase-3-design/tokens_css.css, docs/phase-3-design/accessibility_report.json
