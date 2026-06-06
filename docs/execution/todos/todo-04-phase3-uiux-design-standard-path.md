# TODO-04 - Phase3 UIUX design standard path

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-04",
  "title": "Phase3 UIUX design standard path",
  "phase": "3",
  "parallel_group": "P3",
  "depends_on": [
    "TODO-03"
  ],
  "status": "pending",
  "agents": [
    "ui-ux-designer",
    "consensus-agent",
    "hallucination-detector"
  ],
  "produces": [
    "docs/phase-3-design/wireframes",
    "docs/phase-3-design/tokens_css.css",
    "docs/phase-3-design/accessibility_report.json"
  ],
  "gate": "DESIGN APPROVED; APCA Lc>=60 body",
  "stop_point": "User reviews design",
  "context_file": "todos/todo-04-phase3-uiux-design-standard-path.md",
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

| **3 — UI/UX Design (Standard Path 📄, Mode A)** | `pipelines/ui-ux-design-pipeline/STANDARD_PATH.md` | `ui-ux-designer`, `consensus-agent`, `hallucination-detector` | DESIGN APPROVED; APCA Lc≥60 body (RPwD Act §40) | `wireframes/`, design tokens (`tokens_css.css`), `component_library.md`, `screen_inventory.md`, `accessibility_report.json` → `docs/phase-3-design/` (Standard path — no Figma account assumed) |

Follow the pipeline spec: `pipelines/ui-ux-design-pipeline/STANDARD_PATH.md`
Run the listed lead agents per that spec; enforce the gate and STOP point above.
This phase has no standalone agent block in the bundle by design - it is a
self-contained sub-pipeline launched from its spec file.

## Predecessor artifacts to load as input
- TODO-03 -> docs/phase-2-validation/advisory_items.json
