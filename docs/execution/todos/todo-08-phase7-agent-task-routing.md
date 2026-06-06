# TODO-08 - Phase7 agent task routing

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-08",
  "title": "Phase7 agent task routing",
  "phase": "7",
  "parallel_group": "P7",
  "depends_on": [
    "TODO-07"
  ],
  "status": "pending",
  "agents": [
    "orchestrator-agent",
    "agile-business-mathematics-expert",
    "context-engineering-agent",
    "prompt-generation-expert",
    "hallucination-detector",
    "context-faithfulness-engineer",
    "reliability-auditor",
    "security-testing-engineer",
    "consensus-agent"
  ],
  "produces": [
    "docs/phase-7-routing/implementation_execution_plan.json",
    "docs/phase-7-routing/ar2_dag_proof.json",
    "docs/phase-7-routing/ar3_context_windows.json"
  ],
  "gate": "ROUTING APPROVED; RS=1.0; STOP 7",
  "stop_point": "STOP 7 user review",
  "context_file": "todos/todo-08-phase7-agent-task-routing.md",
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

| **7 — Agent-Task Routing (Mode A)** | `pipelines/agent-task-routing-pipeline/GREENFIELD_GUIDE.md` | `orchestrator-agent`, `agile-business-mathematics-expert`, `context-engineering-agent`, `prompt-generation-expert`, `hallucination-detector`, `context-faithfulness-engineer`, `reliability-auditor`, `security-testing-engineer`, `consensus-agent` | ROUTING APPROVED; RS=1.0; STOP 7 | `implementation_execution_plan.json`, `ar2_dag_proof.json`, `ar3_context_windows.json`, `ar1_assignments.json` → `docs/phase-7-routing/` |

Follow the pipeline spec: `pipelines/agent-task-routing-pipeline/GREENFIELD_GUIDE.md`
Run the listed lead agents per that spec; enforce the gate and STOP point above.
This phase has no standalone agent block in the bundle by design - it is a
self-contained sub-pipeline launched from its spec file.

## Predecessor artifacts to load as input
- TODO-07 -> docs/phase-6-sprint-planning/sprint_verdict.json, docs/phase-6-sprint-planning/sprint_agent_briefs.json
