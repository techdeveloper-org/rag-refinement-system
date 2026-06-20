# TODO-06 - Phase5 SRS and UML documentation

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-06",
  "title": "Phase5 SRS and UML documentation",
  "phase": "5",
  "parallel_group": "P5",
  "depends_on": [
    "TODO-05"
  ],
  "status": "pending",
  "agents": [
    "business-analyst-agent",
    "product-manager-agent",
    "uml-structural-diagram-engineer",
    "uml-behavioral-diagram-engineer",
    "uml-interaction-diagram-engineer",
    "drawio-diagram-architect",
    "mermaid-diagram-engineer",
    "hallucination-detector",
    "context-faithfulness-engineer",
    "consensus-agent"
  ],
  "produces": [
    "SRS.md",
    "uml/",
    "drawio/",
    "docs/phase-5-documentation/drawio_urls.json"
  ],
  "gate": "DOCUMENTATION APPROVED; SRS FR->PRD traceable",
  "stop_point": "User reviews SRS + UML",
  "context_file": "todos/todo-06-phase5-srs-and-uml-documentation.md",
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

| **5 — Blueprint Documentation (Mode A)** | `pipelines/blueprint-documentation-pipeline/BLUEPRINT_DOCUMENTATION_PIPELINE.md` | `business-analyst-agent`, `product-manager-agent`, `uml-structural-diagram-engineer`, `uml-behavioral-diagram-engineer`, `uml-interaction-diagram-engineer`, `drawio-diagram-architect`, `mermaid-diagram-engineer`, `hallucination-detector`, `context-faithfulness-engineer`, `consensus-agent` | DOCUMENTATION APPROVED; SRS FR→PRD traceable | `SRS.md` (root), `uml/` (13 Mermaid), `drawio/` (13), `drawio_urls.json` → `docs/phase-5-documentation/` |

Follow the pipeline spec: `pipelines/blueprint-documentation-pipeline/BLUEPRINT_DOCUMENTATION_PIPELINE.md`
Run the listed lead agents per that spec; enforce the gate and STOP point above.
This phase has no standalone agent block in the bundle by design - it is a
self-contained sub-pipeline launched from its spec file.

## Predecessor artifacts to load as input
- TODO-05 -> docs/phase-4-reconciliation/hld_v3.md, docs/phase-4-reconciliation/grand_advisory_items.json
