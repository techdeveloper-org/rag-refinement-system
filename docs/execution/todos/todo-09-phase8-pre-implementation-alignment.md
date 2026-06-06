# TODO-09 - Phase8 pre implementation alignment

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-09",
  "title": "Phase8 pre implementation alignment",
  "phase": "8",
  "parallel_group": "P8",
  "depends_on": [
    "TODO-08"
  ],
  "status": "pending",
  "agents": [
    "business-analyst-agent",
    "product-manager-agent",
    "solution-architect",
    "scrum-master-agent",
    "prompt-generation-expert",
    "context-engineering-agent",
    "hallucination-detector",
    "context-faithfulness-engineer",
    "reliability-auditor",
    "consensus-agent"
  ],
  "produces": [
    "docs/phase-8-alignment/implementation_execution_plan_v2.json",
    "docs/phase-8-alignment/ir5_alignment_verdict.json"
  ],
  "gate": "IMPLEMENTATION READY; RS=1.0; STOP 8",
  "stop_point": "STOP 8 user review",
  "context_file": "todos/todo-09-phase8-pre-implementation-alignment.md",
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

| **8 — Pre-Implementation Alignment (Mode A)** | `pipelines/pre-implementation-alignment-pipeline/GREENFIELD_GUIDE.md` | `business-analyst-agent`, `product-manager-agent`, `solution-architect`, `scrum-master-agent`, *assigned impl agents*, `prompt-generation-expert`, `context-engineering-agent`, `hallucination-detector`, `context-faithfulness-engineer`, `reliability-auditor`, `consensus-agent` | IMPLEMENTATION READY; RS=1.0; STOP 8 | `implementation_execution_plan_v2.json`, `ar3_context_windows_v2.json`, `ir2_resolution_log.json`, `ir5_alignment_verdict.json` → `docs/phase-8-alignment/` |

Follow the pipeline spec: `pipelines/pre-implementation-alignment-pipeline/GREENFIELD_GUIDE.md`
Run the listed lead agents per that spec; enforce the gate and STOP point above.
This phase has no standalone agent block in the bundle by design - it is a
self-contained sub-pipeline launched from its spec file.

## Predecessor artifacts to load as input
- TODO-08 -> docs/phase-7-routing/implementation_execution_plan.json, docs/phase-7-routing/ar2_dag_proof.json, docs/phase-7-routing/ar3_context_windows.json
