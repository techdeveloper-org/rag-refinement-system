# TODO-10 - PhaseB1 foundation schema and ops

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-10",
  "title": "PhaseB1 foundation schema and ops",
  "phase": "B1",
  "parallel_group": "B1",
  "depends_on": [
    "TODO-09"
  ],
  "status": "pending",
  "agents": [
    "database-engineer",
    "devops-engineer"
  ],
  "produces": [
    "migrations/",
    "infra/",
    "Dockerfile",
    "docker-compose.yml",
    "CI workflow"
  ],
  "gate": "unit tests pass per component",
  "stop_point": null,
  "context_file": "todos/todo-10-phaseb1-foundation-schema-and-ops.md",
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
AGENT: database-engineer
Phase: B (Group B1 — foundation)
Parallel With: devops-engineer
Depends On: solution-architect (Phase 1/4 HLD)
Context Budget: 10,000 tokens | Sources: [pg-schema-delta, qdrant-payload-delta, hld_v3.md-data-model]
Thinking Level: HIGH | budget_tokens: 10,000
Thinking Override: Rule 3 (vector + relational hybrid schema design)
Hallucination Risk: LOW — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 10,000 tokens. Do not request or reference context outside this budget.
Thinking configured at HIGH (budget_tokens: 10,000). Set because you design a hybrid Postgres (relational L1/L2) + Qdrant (vector L3) model whose payload-filter performance is core to the product. Reason within this budget.

OBJECTIVE: Implement the storage layer (C2) — Postgres schema for documents + sections, Qdrant collection for chunk vectors with a payload index on section_id.

AGREED CONTRACTS:
- Postgres: documents(doc_id PK, title, total_pages, domain, created_at); sections(section_id PK, doc_id FK, title, level, page_start, page_end, summary). Migrations for ALL schema changes (snake_case tables/columns).
- Qdrant: chunk points payload {chunk_id, section_id, doc_id, page}; payload index on section_id for filtered search.
- section_id is the universal join/filter key. No chunk vectors in Postgres; no section relations living only in Qdrant.

INSTRUCTIONS:
1. Write migration files (e.g., migrations/001_documents_sections.sql).
2. Define Qdrant collection config (vector size matching text-embedding-3-small = 1536; cosine; payload index on section_id).
3. Provide a section↔chunk metadata-filter query example feeding the router.
4. Parameterized queries only; indexes on documents(domain), sections(doc_id, page_start).

OUTPUT FORMAT: Migration files + Qdrant collection bootstrap + a short data-model README section. Docstrings only — no inline narration (rule 12).

CONSTRAINTS: ACID for multi-step ingestion writes. No ORM-entity dataclass equals traps. Targeted retrieval MUST be expressible as a single Qdrant filtered search. Re-state: section_id is the universal key; hybrid store, never collapse the two.
===================================================================

===================================================================
AGENT: devops-engineer
Phase: B (Group B1 — foundation) [also Phase G]
Parallel With: database-engineer
Depends On: solution-architect (Phase 1/4 HLD)
Context Budget: 5,000 tokens | Sources: [repo-scaffold-delta, ci-pipeline-delta, env-secrets-delta]
Thinking Level: MEDIUM | budget_tokens: 5,000
Thinking Override: Role default
Hallucination Risk: LOW — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 5,000 tokens. Do not request or reference context outside this budget.
Thinking configured at MEDIUM (budget_tokens: 5,000). Set because infra scaffolding + CI config is standard multi-step work. Reason within this budget.

OBJECTIVE: Scaffold the repo and ship the ops baseline (C7) — monorepo or service layout, Dockerfiles, docker-compose (Postgres + Qdrant + API + frontend), CI (lint + type + test gates), 12-factor env + secret handling.

AGREED CONTRACTS:
- 12-factor env vars: OPENAI_API_KEY, ANTHROPIC_API_KEY, COHERE_API_KEY, QDRANT_URL, DATABASE_URL, LANGSMITH_API_KEY — never committed; injected via secret manager.
- Each service: Dockerfile + /health (liveness) + /ready (deps reachable).
- CI runs SAST + secrets scan on every run and blocks on any hardcoded key.

INSTRUCTIONS:
1. Repo layout (backend/, ingestion/, frontend/, infra/, tests/). Respect documentation governance (only the 5 permitted root docs).
2. docker-compose for local dev (Chroma optional swap for Qdrant in dev per ADR-2).
3. CI workflow with lint (ruff), type (mypy), test, coverage gate placeholders.
4. .env.example (no real secrets), secret-manager wiring notes.

OUTPUT FORMAT: Dockerfiles, compose, CI workflow, env scaffolding, repo README skeleton.

CONSTRAINTS: No secrets in repo/history. Hooks synchronous. UTF-8 / ASCII-safe Python. Healthchecks mandatory before Phase G sign-off.
===================================================================

## Predecessor artifacts to load as input
- TODO-09 -> docs/phase-8-alignment/implementation_execution_plan_v2.json, docs/phase-8-alignment/ir5_alignment_verdict.json
