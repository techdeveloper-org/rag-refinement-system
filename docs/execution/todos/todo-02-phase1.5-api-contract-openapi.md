# TODO-02 - Phase1.5 API contract OpenAPI

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-02",
  "title": "Phase1.5 API contract OpenAPI",
  "phase": "1.5",
  "parallel_group": "P1.5",
  "depends_on": [
    "TODO-01"
  ],
  "status": "pending",
  "agents": [
    "solution-architect",
    "python-backend-engineer",
    "api-testing-engineer",
    "integration-testing-engineer",
    "business-analyst-agent",
    "consensus-agent"
  ],
  "produces": [
    "docs/phase-1-api-contracts/openapi.yaml",
    "docs/phase-1-api-contracts/fr_api_traceability.json"
  ],
  "gate": "API CONTRACT APPROVED; 100% FR->operationId; DPDP x-pii/erasure",
  "stop_point": "User reviews openapi.yaml",
  "context_file": "todos/todo-02-phase1.5-api-contract-openapi.md",
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

| **1.5 — API Contract (Mode A)** | `pipelines/api-contract-pipeline/GREENFIELD_GUIDE.md` | `solution-architect`, `python-backend-engineer`, `api-testing-engineer`, `integration-testing-engineer`, `business-analyst-agent`, `consensus-agent` | API CONTRACT APPROVED; 100% FR→operationId; DPDP `x-pii`/erasure | `openapi.yaml` (full 3.1.0), `fr_api_traceability.json`, `error_catalog.json` → `docs/phase-1-api-contracts/` |

Follow the pipeline spec: `pipelines/api-contract-pipeline/GREENFIELD_GUIDE.md`
Run the listed lead agents per that spec; enforce the gate and STOP point above.
This phase has no standalone agent block in the bundle by design - it is a
self-contained sub-pipeline launched from its spec file.

## Predecessor artifacts to load as input
- TODO-01 -> docs/phase-1-architecture/hld.md
