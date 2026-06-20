# TODO-11 - PhaseB2 ingestion router api

> Self-contained execution packet. All context below is sliced from
> docs/orchestration_prompt.md ONLY. Shared context (KG, constraints, ADRs,
> team alignment, enforcement rules) is in ../_common_context.md.

## Metadata
```json
{
  "id": "TODO-11",
  "title": "PhaseB2 ingestion router api",
  "phase": "B2",
  "parallel_group": "B2",
  "depends_on": [
    "TODO-10"
  ],
  "status": "pending",
  "agents": [
    "data-engineer",
    "ai-engineer",
    "prompt-generation-expert",
    "python-backend-engineer"
  ],
  "produces": [
    "ingestion module",
    "LangGraph router module",
    "FastAPI services"
  ],
  "gate": "unit tests pass per component",
  "stop_point": null,
  "context_file": "todos/todo-11-phaseb2-ingestion-router-api.md",
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
AGENT: data-engineer
Phase: B (Group B2 — ingestion)
Parallel With: ai-engineer, python-backend-engineer
Depends On: database-engineer (B1)
Context Budget: 5,000 tokens | Sources: [ingestion-schema-delta, toc-scenarios-delta]
Thinking Level: MEDIUM | budget_tokens: 5,000
Thinking Override: Role default
Hallucination Risk: LOW — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 5,000 tokens. Do not request or reference context outside this budget.
Thinking configured at MEDIUM (budget_tokens: 5,000). Set because the ingestion pipeline is standard ETL with three branch scenarios. Reason within this budget.

OBJECTIVE: Build the ingestion pipeline (C1) — parse → TOC extraction (3 scenarios) → section-aware 3-level chunking → embed → upsert.

AGREED CONTRACTS:
- ingest_document(doc) → {doc_id, toc[], section_rows_written, chunks_upserted}; idempotent on content hash (re-upload reuses doc_id).
- No chunk crosses a section boundary. No raw PDF retained in no-retention mode.
- Writes Postgres section rows + Qdrant chunk points (section_id payload).

INSTRUCTIONS:
1. Scenario A: PyMuPDF doc.get_toc() → section ranges.
2. Scenario B: font/position header detection + LLM (Claude 3 Haiku) refinement → pseudo-TOC.
3. Scenario C: LLM semantic map over first N pages OR topic-labeled sliding window; if still none → mark fallback=true for full-doc RAG.
4. Section-aware chunking (100–512 token chunks tagged with section_id + page).
5. Embed with text-embedding-3-small (BGE-M3 fallback for non-English); upsert to Qdrant; write sections to Postgres.

OUTPUT FORMAT: ingestion module + a fixtures note (golden TOC for scenarios A/B/C for downstream tests).

CONSTRAINTS: Graceful degradation across A→B→C. Cache the TOC. Parameterized DB writes. Docstrings only. Re-state: never chunk across a section boundary; idempotent on content hash.
===================================================================

===================================================================
AGENT: ai-engineer (paired with prompt-generation-expert)
Phase: B (Group B2 — core router)
Parallel With: data-engineer, python-backend-engineer
Depends On: database-engineer (B1), data-engineer (TOC available)
Context Budget: 10,000 tokens | Sources: [router-contract-delta, confidence-threshold-delta, router-prompt-delta]
Thinking Level: HIGH | budget_tokens: 10,000
Thinking Override: Rule 4 (HIGH hallucination risk)
Hallucination Risk: HIGH — verified by hallucination-detector + context-faithfulness-engineer

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 10,000 tokens. Do not request or reference context outside this budget.
Thinking configured at HIGH (budget_tokens: 10,000). Set because the LangGraph routing state machine + confidence thresholding + fallback branch is the product's core differentiator and HIGH-risk. Reason within this budget.
Your output will be verified by hallucination-detector. The router must never invent section IDs not present in the supplied TOC — cite the TOC as the only allowed section source.

OBJECTIVE: Build the LangGraph 1.0 Router Agent (C3) + the targeted-retrieval + generation glue (C4). prompt-generation-expert supplies the router + generation prompts FIRST; you consume them.

AGREED CONTRACTS:
- route(query, doc_id) → {relevant_sections[], page_ranges[], confidence[], fallback, routing_time_ms, rationale}. In-process async function. Never calls the generation LLM. Emits strict JSON only.
- Confidence thresholds: ≥0.7 include; 0.5–0.7 conditional (include only if no ≥0.7 found); <0.5 exclude; ALL <0.5 → fallback=true (full-doc RAG).
- Exactly one routing LLM call per query (TOC cached). Router LLM = Claude 3 Haiku.
- Targeted retrieval = Qdrant filtered search on section_id IN selected; optional Cohere Rerank-3.

INSTRUCTIONS:
1. prompt-generation-expert: author the router prompt (TOC + query → ranked sections with confidence, strict JSON schema, injection-resistant role separation) and the generation prompt (clean context → answer with section+page citations). Apply CoT + few-shot; validate output schema.
2. ai-engineer: implement the LangGraph graph: extract_query → route(LLM) → threshold → [targeted_retrieve | fallback_full_doc] → optional rerank → generate → cite. Checkpointing on.
3. Validate router JSON against schema; reject/repair non-JSON (prompt-injection guard).
4. Wire LangSmith tracing on every node.

OUTPUT FORMAT: router module (LangGraph graph) + prompt files + a routing-contract doc matching the AGREED CONTRACT shape.

CONSTRAINTS: One routing LLM call; cache TOC. Router never fabricates a section_id absent from the TOC. Strict-JSON output with schema validation. Re-state at end: never call generation LLM from the router; fallback when all confidences <0.5.
===================================================================

===================================================================
AGENT: python-backend-engineer
Phase: B (Group B2 — API)
Parallel With: data-engineer, ai-engineer
Depends On: database-engineer (B1), ai-engineer (router contract), Phase 1.5 openapi.yaml
Context Budget: 10,000 tokens | Sources: [api-contract-delta, sse-streaming-delta, auth-ratelimit-delta]
Thinking Level: HIGH | budget_tokens: 10,000
Thinking Override: Rule 3 (async / streaming / public API surface)
Hallucination Risk: MEDIUM — verified by hallucination-detector

PROMPT:
Master KG loaded: 250 agents (deduped), 428 skills, 48 domains, 23 math masters (source: knowledge-graph/_master/, built: 2026-06-06). You are one of 250 available agents.
Context Budget: 10,000 tokens. Do not request or reference context outside this budget.
Thinking configured at HIGH (budget_tokens: 10,000). Set because async FastAPI services with SSE streaming, auth, rate limiting, and a public enterprise API need extended reasoning. Reason within this budget.

OBJECTIVE: Build the FastAPI services (C5) — endpoints, auth, rate limiting, OpenAPI — over the ingestion + router cores.

AGREED CONTRACTS (bind to Phase 1.5 openapi.yaml):
- POST /v1/route (routing-only) → relevant_sections/page_ranges/confidence/fallback/routing_time_ms/estimated_token_reduction.
- POST /v1/answer (personal tool, SSE token stream, final event = {answer, citations[{section_title, page_start, page_end}], routing{...}}).
- POST /v1/documents (ingest) + GET/DELETE /v1/documents/{id} + GET /v1/documents/{id}/data (DPDP access) + DELETE = erasure.
- Auth: API keys (enterprise) + OAuth2/JWT (personal tool). Rate limiting. Errors = RFC-7807 problem+json. Pagination on list endpoints.

INSTRUCTIONS:
1. Implement endpoints calling ingest_document() and route(); stream generation via SSE.
2. API-key + JWT auth dependencies; per-key rate limits; CORS policy.
3. DPDP: x-pii annotations, erasure + access endpoints, no-retention mode flag.
4. Auto-generated OpenAPI must match the Phase 1.5 contract; standard envelope + status codes (200/201/204/400/401/403/404/409/500).

OUTPUT FORMAT: FastAPI app (routers, deps, schemas) + matching OpenAPI. Docstrings only.

CONSTRAINTS: Validate ALL external input. Parameterized DB. No secrets in code. Never change response schema without updating openapi.yaml + notifying react-engineer. Re-state: /v1/route is routing-only; /v1/answer streams; DPDP erasure/access endpoints are mandatory.
===================================================================

## Predecessor artifacts to load as input
- TODO-10 -> migrations/, infra/, Dockerfile, docker-compose.yml, CI workflow
