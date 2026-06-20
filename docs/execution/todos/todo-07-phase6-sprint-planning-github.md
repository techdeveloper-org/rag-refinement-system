# TODO-07 - Phase6 sprint planning github

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-07",
  "title": "Phase6 sprint planning github",
  "phase": "6",
  "parallel_group": "P6",
  "depends_on": [
    "TODO-06"
  ],
  "status": "pending",
  "agents": [
    "scrum-master-agent",
    "agile-tooling-specialist",
    "business-analyst-agent",
    "product-manager-agent",
    "solution-architect",
    "ui-ux-designer",
    "consensus-agent"
  ],
  "produces": [
    "docs/phase-6-sprint-planning/sprint_verdict.json",
    "docs/phase-6-sprint-planning/sprint_agent_briefs.json"
  ],
  "gate": "SPRINT READY; 100% FR->story",
  "stop_point": "User reviews sprint board",
  "context_file": "todos/todo-07-phase6-sprint-planning-github.md",
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

| **6 — Sprint Planning (GitHub Issues Path, Mode A)** | `pipelines/sprint-planning-pipeline/GREENFIELD_GUIDE.md` | `scrum-master-agent`, `agile-tooling-specialist`, `business-analyst-agent`, `product-manager-agent`, `solution-architect`, `ui-ux-designer`, `consensus-agent` | SPRINT READY; 100% FR→story | Sprint-1 GitHub milestone + issues (existing `techdeveloper-org` repo), `sprint_verdict.json`, `sprint_agent_briefs.json` → `docs/phase-6-sprint-planning/` (GitHub path — no Jira assumed) |

Follow the pipeline spec: `pipelines/sprint-planning-pipeline/GREENFIELD_GUIDE.md`
Run the listed lead agents per that spec; enforce the gate and STOP point above.
This phase has no standalone agent block in the bundle by design - it is a
self-contained sub-pipeline launched from its spec file.

## Predecessor artifacts to load as input
- TODO-06 -> SRS.md, uml/, drawio/, docs/phase-5-documentation/drawio_urls.json
