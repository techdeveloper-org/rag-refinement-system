# TODO-17 - PhaseG deploy and README refresh

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-17",
  "title": "PhaseG deploy and README refresh",
  "phase": "G",
  "parallel_group": "G",
  "depends_on": [
    "TODO-16"
  ],
  "status": "pending",
  "agents": [
    "devops-engineer",
    "cloud-security-architect"
  ],
  "produces": [
    "prod deploy config",
    "LangSmith monitoring",
    "README.md"
  ],
  "gate": "RS=1.0 satisfied; healthchecks green",
  "stop_point": "User reviews live deploy",
  "context_file": "todos/todo-17-phaseg-deploy-and-readme-refresh.md",
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
AGENT: devops-engineer (paired with cloud-security-architect)
Phase: G
Parallel With: NONE
Depends On: Phase E (RS = 1.0)
Context Budget: 5,000 tokens | Sources: [prod-config-delta, monitoring-delta, readme-refresh-delta]
Thinking Level: MEDIUM | budget_tokens: 5,000
Thinking Override: Role default
Hallucination Risk: LOW — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 5,000 tokens. Do not request or reference context outside this budget.
Thinking configured at MEDIUM (budget_tokens: 5,000). Set because production config + monitoring is standard ops work. Reason within this budget.

OBJECTIVE: Production deploy + observability (C7) and finalize productization wiring (C8). Only runs after RS = 1.0.

INSTRUCTIONS:
1. Production config (Qdrant + Postgres + API + frontend), secret-manager-backed env.
2. LangSmith monitoring; dashboards for token savings, accuracy, latency, fallback rate.
3. Wire the ROI calculator + benchmark harness outputs.
4. Refresh README.md: accurate status, real setup/run for both angles, architecture link, contributing, license (rule 11 — only the 5 permitted root docs).

OUTPUT FORMAT: prod deploy config + monitoring + refreshed README.md.

CONSTRAINTS: No deploy if RS<1.0. Healthchecks green. cloud-security-architect signs off TLS + secrets in prod. Re-state: README must reflect real, runnable instructions — no aspirational status.
===================================================================

## Predecessor artifacts to load as input
- TODO-16 -> reliability report, RS value
