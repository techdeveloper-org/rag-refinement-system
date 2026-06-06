# TODO-03 - Phase2 joint blueprint validation

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-03",
  "title": "Phase2 joint blueprint validation",
  "phase": "2",
  "parallel_group": "P2",
  "depends_on": [
    "TODO-02"
  ],
  "status": "pending",
  "agents": [
    "business-analyst-agent",
    "product-manager-agent",
    "solution-architect",
    "consensus-agent",
    "hallucination-detector"
  ],
  "produces": [
    "docs/phase-2-validation/advisory_items.json"
  ],
  "gate": "JOINT APPROVED",
  "stop_point": "User reviews advisory items",
  "context_file": "todos/todo-03-phase2-joint-blueprint-validation.md",
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

| **2 — Joint Blueprint Validation (Mode A)** | `pipelines/joint-blueprint-validation-pipeline/GREENFIELD_GUIDE.md` | `business-analyst-agent`, `product-manager-agent`, `solution-architect`, `consensus-agent`, `hallucination-detector` | JOINT APPROVED | `hld_v2.md` (if fixes), `advisory_items.json` → `docs/phase-2-validation/` |

Follow the pipeline spec: `pipelines/joint-blueprint-validation-pipeline/GREENFIELD_GUIDE.md`
Run the listed lead agents per that spec; enforce the gate and STOP point above.
This phase has no standalone agent block in the bundle by design - it is a
self-contained sub-pipeline launched from its spec file.

## Predecessor artifacts to load as input
- TODO-02 -> docs/phase-1-api-contracts/openapi.yaml, docs/phase-1-api-contracts/fr_api_traceability.json
