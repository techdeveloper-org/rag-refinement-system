# Shared Context (sliced from docs/orchestration_prompt.md)

Every TODO packet references this file. It carries the KG header, constraints,
ADRs, team-alignment AGREED CONTRACTS, and enforcement rules that apply to all agents.

---

## STEP 0 — MASTER KG LOAD (verified, real on disk)

| Metric | Value |
|--------|-------|
| Source | `knowledge-graph/_master/` |
| Library Version | 29.9.16 |
| Last Build | 2026-06-06 |
| Domain KGs | 48 |
| Agents (deduped) | 250 |
| Skills (deduped) | 428 |
| Edges (all KGs union) | 4210 |
| Math Masters | 23 |
| Regulations | 337 |

All agents named in this prompt were verified to exist in `agents_all.json`. Math masters verified in `math_masters_all.json`. Pipeline specs verified under `pipelines/`.

**PHASE-F UPDATE (build 29.9.16):** The canonical Phase-F security roster (`threat-modeling-specialist`, `sast-engineer`, `secrets-detection-specialist`, `dependency-vulnerability-analyst`, `api-security-auditor`, `auth-security-specialist`, `penetration-tester`, `infrastructure-security-auditor`, `crypto-security-specialist`, `security-compliance-mapper`, `security-lead-auditor`) **now exists** in the rebuilt KG and is used directly. The earlier remap to substitute agents is retired. For this RAG/LLM product, `threat-modeling-specialist` MUST extend its STRIDE/PASTA scope to the OWASP LLM Top-10 (prompt injection on the router prompt, RAG corpus poisoning at ingestion, embedding-inversion on stored chunks).

---

---

## CONSTRAINTS

```
Tech Stack:        Python 3.11+ / FastAPI (async) backend · LangGraph 1.0 orchestration ·
                   PyMuPDF + PyMuPDF4LLM (parse/TOC) · Unstructured.io + Azure Document
                   Intelligence (fallbacks/OCR) · Qdrant (prod) / ChromaDB (dev) vector DB ·
                   PostgreSQL (section/doc metadata) · OpenAI text-embedding-3-small (+ BGE-M3
                   multilingual fallback) · Claude 3 Haiku (router LLM) · Claude / GPT-4o
                   (generation) · Cohere Rerank-3 (optional) · React + TailwindCSS + Vite
                   (personal tool) · LangSmith (observability) · Docker + CI/CD.
Platform:          Web (personal tool SPA) + Cloud (enterprise REST API). Cloud-deployable;
                   on-premise option on the enterprise roadmap.
Scale:             MVP-first. Enterprise targets 10K–500K+ routing calls/month per the PRD;
                   design routing path for horizontal scale, ship MVP at low scale.
Timeline:          Production-ready, sellable. No artificial deadline ("shanti se" — calm,
                   thorough). Phase-gated; correctness over speed.
Compliance:        DPDP Act 2023 (India) — PII in uploaded docs, erasure + access endpoints,
                   data-residency/no-retention option. SOC2 (enterprise-sales roadmap).
                   GDPR-readiness if EU customers. No financial/health regulatory scope in MVP,
                   but legal/healthcare/finance are named target verticals → treat answer
                   faithfulness as safety-critical.
Special Needs:     Interpretable routing (mandatory — core differentiator) · streaming answers ·
                   multilingual fallback (BGE-M3) · graceful degradation to full-doc RAG ·
                   source-citation accuracy.
Hallucination Risk: HIGH — the product's entire value proposition is reducing RAG hallucination;
                   every user-facing answer is LLM-generated over retrieved context; target
                   verticals are accuracy-critical. Anti-Hallucination layer is MANDATORY.
Security Risk:     HIGH→CRITICAL — user-uploaded documents (PII), provider API keys, auth,
                   enterprise tenant data, public API surface. Full Phase F (canonical roster v29.9.16).
Thinking Budget:   AUTO — assigned per agent via STEP 4.5 table below.
```

---

## ARCHITECTURE DECISION RECORDS (injected into blueprint + consensus + every affected agent)

```
ADR-1: Router LLM
  Chosen:   Claude 3 Haiku
  Why:      Sub-300ms routing; strong structured-JSON adherence for {section_id, confidence};
            same vendor as generation LLM (one key, one SLA); ~$0.0001–0.001 / routing call.
  Rejected: GPT-4o-mini — splits vendor/billing, marginal cost parity, no quality edge for routing.
            Fine-tuned router — premature before benchmark data exists (defer to Phase 4 roadmap).

ADR-2: Vector database
  Chosen:   Qdrant (prod) / ChromaDB (dev)
  Why:      Rich payload metadata filtering on section_id/page (the core "scope before search"
            mechanism); Rust performance; local Chroma keeps dev friction near zero.
  Rejected: Pinecone — cost + vendor lock-in, weaker self-host story.
            pgvector — metadata-filter performance degrades at the scoped-search scale we need.
            Weaviate — heavier ops for MVP.

ADR-3: Agent orchestration
  Chosen:   LangGraph 1.0 (stable Oct 2025)
  Why:      First-class conditional routing + checkpointing for the Router→Retrieve→Generate
            state machine with a fallback branch; production-ready.
  Rejected: Raw LangChain — no native graph/branch model.
            Custom orchestration — reinvents checkpointing/observability.
            LlamaIndex agents — less control over explicit routing branches.

ADR-4: PDF parsing / TOC extraction
  Chosen:   PyMuPDF + PyMuPDF4LLM (primary) → Unstructured.io (fallback) → Azure Document
            Intelligence (scanned/OCR)
  Why:      get_toc() yields native bookmark TOC with page numbers (Scenario A) for free + fast;
            tiered fallbacks cover Scenarios B/C without over-paying on every document.
  Rejected: pdfplumber — no TOC primitive. PyPDF2 — weak structured extraction.

ADR-5: API framework
  Chosen:   FastAPI
  Why:      Async I/O for concurrent ingestion/routing; auto-generated OpenAPI 3.1 (drives
            Phase 1.5 contract); Pydantic validation at the boundary.
  Rejected: Flask — sync-first, manual schema. Django — ORM/admin weight unneeded for an API.

ADR-6: Embeddings
  Chosen:   OpenAI text-embedding-3-small (primary) + BGE-M3 (multilingual fallback)
  Why:      Best cost/quality at chunk scale; BGE-M3 covers non-English docs without a second
            paid provider.
  Rejected: text-embedding-ada-002 — superseded. Cohere embed — adds a third vendor for no gain.

ADR-7: Authentication
  Chosen:   API keys (enterprise) + OAuth2 / JWT (personal tool)
  Why:      API keys are the standard enterprise integration contract with simple rotation;
            OAuth2/JWT fits the SPA session model.
  Rejected: Session-only — no machine-to-machine API. mTLS — operationally heavy for MVP.

ADR-8: Reranker
  Chosen:   Cohere Rerank-3 (optional, post-route)
  Why:      Documented 20–35% precision lift, toggleable per request to control cost.
  Rejected: Self-hosted cross-encoder — GPU/ops burden for MVP. None — leaves accuracy on table.

ADR-9: Personal-tool frontend
  Chosen:   React + TailwindCSS + Vite
  Why:      Mature streaming-UI ecosystem for token-by-token answers; Tailwind maps cleanly to
            Phase 3 design tokens; Vite fast dev loop.
  Rejected: Next.js — SSR/routing weight unneeded for an authenticated SPA. Angular — heavier.

ADR-10: Section/document metadata store
  Chosen:   PostgreSQL (alongside Qdrant for chunk vectors)
  Why:      Relational L1/L2 hierarchy + ACID + metadata-filter joins feeding the router; clean
            separation of "structure store" (Postgres) from "vector store" (Qdrant).
  Rejected: Mongo — weaker relational section↔chunk joins. Qdrant-only — no relational queries
            for TOC/section management UI.
```

---

---

## TEAM ALIGNMENT REPORT (resolutions become `AGREED CONTRACTS:` in both agents)

```
TEAM ALIGNMENT REPORT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ai-engineer ↔ python-backend-engineer
  Q [ai-engineer]: How does the backend consume the Router Agent output — sync call or queue,
                   and is generation streamed or batched?
  A: Backend calls the LangGraph router as an in-process async function returning
     {relevant_sections[], page_ranges[], confidence[], fallback:bool, routing_time_ms}.
     Generation is streamed to the personal tool via SSE; the /v1/route enterprise endpoint is
     request/response (no generation — routing only). Router never calls the generation LLM.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
python-backend-engineer ↔ database-engineer
  Q: What is the section/chunk schema and how is targeted retrieval filtered?
  A: Postgres: documents(doc_id PK, title, total_pages, domain); sections(section_id PK,
     doc_id FK, title, level, page_start, page_end, summary). Qdrant: chunk points with payload
     {chunk_id, section_id, doc_id, page}. Targeted retrieval = Qdrant search with payload
     filter section_id IN (router-selected). No mid-sentence chunk crosses a section boundary.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
python-backend-engineer ↔ data-engineer
  Q: Where does the ingestion pipeline hand off, and who owns embedding + upsert?
  A: data-engineer owns parse→TOC→section-aware chunk→embed→Qdrant upsert + Postgres section
     rows, exposed as ingest_document(doc) returning doc_id + toc. Backend owns the HTTP upload
     endpoint and calls ingest_document. Idempotent on content hash; re-upload reuses doc_id.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
react-engineer ↔ python-backend-engineer
  Q: API contract for chat, streaming, and citation payload?
  A: Per Phase 1.5 openapi.yaml. Chat = POST /v1/answer (SSE stream of tokens, then a final
     event with {answer, citations[{section_title, page_start, page_end}], routing:
     {sections[], confidence[], fallback}}). Auth = JWT bearer. Errors = RFC-7807 problem+json.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ui-ux-designer ↔ react-engineer
  Q: How is the routing-confidence meter + "why did you look here?" panel specified?
  A: Phase 3 tokens + component_library.md. Confidence meter reads routing.confidence[]; panel
     lists selected sections with score, page range, and the router rationale string. APCA
     Lc≥60 on all meter/panel text.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
devops-engineer ↔ all implementers
  Q: Env vars, build, healthcheck, secrets?
  A: 12-factor env (OPENAI_API_KEY, ANTHROPIC_API_KEY, COHERE_API_KEY, QDRANT_URL, DATABASE_URL,
     LANGSMITH_API_KEY) injected via secret manager — never in code/repo. Each service ships a
     Dockerfile + /health (liveness) + /ready (deps reachable). CI runs lint+type+test gates.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
test-management-agent ↔ all implementers
  Q: Risk tier per component + what is testable?
  A: P0 risk: Router Agent (confidence thresholding + fallback), targeted retrieval filter,
     citation accuracy. P1: ingestion TOC scenarios A/B/C, API auth/rate-limit. Router and
     retrieval get deterministic fixtures (golden TOC + golden section sets).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
api-testing-engineer ↔ python-backend-engineer
  Q: API test scope + coverage target?
  A: OpenAPI triple coverage C_api ≥ 0.85 on /v1/route, /v1/answer, ingest, document mgmt.
     Every endpoint: request schema + all 2xx/4xx/5xx; ≥2 error codes each; pagination on list.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ai-model-testing-engineer ↔ ai-engineer
  Q: Router accuracy thresholds + drift detection?
  A: Router correct-section recall ≥ 0.85 (MVP) / ≥ 0.95 (6-mo); fallback rate < 20%/<10%;
     hallucination rate < 15% MVP. PSI drift on routing-score distribution; eval set ≥ 20 docs
     spanning scenarios A/B/C, tracked in LangSmith.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sast-engineer / secrets-detection-specialist ↔ devops-engineer
  Q: SAST/secrets/SCA gate placement?
  A: SAST + secrets scan on every CI run (block on any hardcoded key). SCA/CVE + SBOM on
     dependency changes. DAST (penetration-tester) against staging before Phase G. CERT-In-format
     audit artifacts retained. Scanner config: Python + TS stacks, exclusion patterns provided.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
threat-modeling-specialist ↔ ai-engineer
  Q: LLM-specific attack surface on the router/generation path (extend STRIDE with OWASP LLM Top-10)?
  A: Treat document text + user query as untrusted. Threat-model prompt injection in the router
     prompt (system/role separation, output schema validation, reject non-JSON), RAG corpus
     poisoning (ingestion content checks), and embedding-inversion on stored chunks (Qdrant access
     control). OWASP LLM Top-10 checklist folded into the threat model for the answer path.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
api-security-auditor / auth-security-specialist ↔ python-backend-engineer
  Q: API + auth attack surface?
  A: Full endpoint inventory from openapi.yaml. IDOR/mass-assignment on /v1/documents/{id};
     OAuth2/JWT validation + API-key rotation + session-fixation/privilege-escalation review;
     rate-limit-bypass + CORS policy audit on /v1/route and /v1/answer.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
security-compliance-mapper ↔ solution-architect
  Q: DPDP data-handling constraints on uploaded documents + regulatory mapping?
  A: DPDP Act 2023 §4 — PII fields flagged x-pii; §8 — DELETE /v1/documents/{id} (erasure) +
     GET /v1/documents/{id}/data (access) required; no-retention mode purges chunks+sections+raw
     after answer; data-residency config for India tenants; CERT-In 6h incident-reporting hook;
     SOC2-readiness evidence format. Findings from F.1–F.4 mapped to these regulations.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

---

## ENFORCEMENT RULES (apply throughout)

- **Model Fallback Protocol:** any sonnet agent hitting a rate limit → retry with opus override (per `~/.claude/rules/model-fallback.md`).
- **Consensus Loop:** `consensus-agent` is BINARY (`APPROVED`/`REJECTED`). Any issue → REJECTED → itemized list → `solution-architect` fixes ALL → resubmit. No partial states. No Phase B agent runs before APPROVED.
- **Context Budget:** every Phase B+ agent prompt carries `Context Budget: {N} tokens | Sources: [...]`. Missing = invalid prompt.
- **Hallucination Gate:** `hallucination-detector` runs after every agent. Phase C retry loop to NLI=1.0 AND FactScore=1.0.
- **QA Gate:** coverage = 100% + DRE = 1.0 hard blocks. Below 1.0 = REJECTED → back to implementers.
- **Security Gate:** Phase F all finding counts = 0 before Phase G. Retry loop, no override.
- **Reliability Gate:** RS = 1.0 mandatory before Phase G. No partial approval.
- **Thinking Level:** every agent invocation passes `budget_tokens` in the API config from the STEP 4.5 table. EXCELLENCE only for opus math masters; never re-assign EXCELLENCE to a Rule-1-capped sonnet agent.

---
