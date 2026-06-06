# Phase 1 Architect Brief — RAG Refinement System

**Prepared by:** Phase 0 (BA/PM + R&D)
**For:** solution-architect (Phase 1 — HLD)
**Date:** 2026-06-06
**Source of truth:** `PRD.md` v2.0 + `docs/execution/_common_context.md` (ADR-1..ADR-10, team-alignment contracts)
**Gate to clear before handoff:** NLI = 1.0 + FactScore = 1.0 (hallucination-detector)

> Chain-of-thought framing: this brief tells the architect *what must be true* of the HLD, *why* (traced to FR/NFR/ADR), and *which decisions are still open*. The product concept is fixed — do not redesign it. Two angles (personal PDF Q&A tool + enterprise routing API), a three-stage pipeline (ingestion -> routing -> targeted retrieval), and a TOC-based router are all locked.

---

## 1. Product in One Paragraph

A document-structure-aware retrieval layer. On ingestion it extracts a document's TOC and builds a Document -> Section -> Chunk hierarchy. On query, a TOC-based **Router Agent** (Claude 3 Haiku via LangGraph) selects the relevant sections *before* vector search, so retrieval is scoped to those sections only. This cuts tokens 40-70% and reduces hallucination from context noise, while staying interpretable ("why did you look here?"). It ships as a personal SPA (streamed, cited answers) and an enterprise **routing-only** REST API (`/v1/route`, request/response, no generation).

---

## 2. Top-WSJF Functional Requirements (build-order signal)

The architect should ensure the HLD makes the following first-class. The P0 foundation chain (FR-001 -> FR-006) is a hard dependency prerequisite; WSJF sequences work *within* feasible sets.

| FR | What | Why it leads | ADRs |
|----|------|--------------|------|
| **FR-005** Router Agent | LangGraph router -> `{relevant_sections[], page_ranges[], confidence[], fallback, routing_time_ms}` | The core differentiator and P0 risk item; everything else hangs off the routing contract | ADR-1, ADR-3 |
| **FR-002** TOC Extraction | Native `get_toc()` + pseudo-TOC fallback (Scenarios A/B/C) | Without a reliable TOC there is nothing to route over | ADR-4, ADR-1 |
| **FR-006** Targeted Retrieval | Qdrant search filtered `section_id IN (...)` | The mechanism that realizes the token/accuracy win | ADR-2, ADR-10 |
| **FR-009** Fallback Mode | Full-doc RAG when all confidences < threshold | Safety net; high risk-reduction, small job | ADR-3 |
| **FR-008** Source Citations | section_title + page range on every answer | Must-be for trust; small job | ADR-10 |
| **FR-001** PDF Upload & Parse | Upload -> text + structure | Entry point of the whole pipeline | ADR-4, ADR-5 |
| **FR-012 / FR-011** Explainability + Confidence | "why here?" panel + confidence meter | Delighters that are the interpretability moat; cheap to add | ADR-9 |
| **FR-025 / FR-027** DPDP Erasure + No-Retention | Delete purges chunks+sections; ephemeral mode | Enterprise must-be; gating for regulated verticals | ADR-5, ADR-10, ADR-2 |

Full FR/NFR set: PRD Sections 9-10. WSJF table: PRD Section 11. RTM skeleton: PRD Section 13.

---

## 3. Locked Architecture Signals (do not re-litigate — these are ADRs)

- **Router LLM:** Claude 3 Haiku (ADR-1). Sub-300ms, strict JSON. Generation LLM (Claude/GPT-4o) is **separate** and never called by the router.
- **Orchestration:** LangGraph 1.0 conditional graph: Router -> Retrieve -> Generate, with a fallback branch + checkpointing (ADR-3).
- **Vector DB:** Qdrant (prod) / ChromaDB (dev), payload `{chunk_id, section_id, doc_id, page}`; targeted retrieval = payload filter on `section_id` (ADR-2).
- **Metadata store:** PostgreSQL — `documents(doc_id PK, title, total_pages, domain)`, `sections(section_id PK, doc_id FK, title, level, page_start, page_end, summary)` (ADR-10). Structure store (Postgres) is deliberately separate from vector store (Qdrant).
- **Parsing:** PyMuPDF + PyMuPDF4LLM -> Unstructured.io -> Azure Document Intelligence (OCR), tiered (ADR-4).
- **Embeddings:** OpenAI text-embedding-3-small + BGE-M3 multilingual fallback (ADR-6).
- **API:** FastAPI async, OpenAPI 3.1, Pydantic, RFC-7807 errors (ADR-5). `/v1/route` is request/response; `/v1/answer` is SSE streaming with a final structured event.
- **Auth:** API keys + rotation (enterprise) / OAuth2-JWT bearer (personal) (ADR-7).
- **Reranker:** Cohere Rerank-3, optional, post-route, per-request toggle (ADR-8).
- **Frontend:** React + TailwindCSS + Vite (ADR-9).
- **Ingestion ownership:** `ingest_document(doc) -> {doc_id, toc}`, idempotent on content hash; re-upload reuses `doc_id`. Backend owns the HTTP upload endpoint.

---

## 4. DPDP / Compliance Constraints the HLD Must Satisfy

These are architectural, not bolt-on — design them into the data model and request flow (PRD Section 16):

1. **Erasure (FR-025, DPDP §8):** `DELETE /v1/documents/{id}` must cascade across **both** stores — Postgres sections/document rows **and** Qdrant chunk vectors — atomically enough that a later `GET` returns 404 and no orphan vectors remain.
2. **Access (FR-026, DPDP §8):** `GET /v1/documents/{id}/data` returns the personal data held for that document.
3. **No-retention mode (FR-027):** a per-request flag that purges raw upload + chunks + sections after the answer returns — implies an ephemeral ingestion path that never persists, or a guaranteed post-answer purge.
4. **Data residency (FR-028):** India-region storage selectable per tenant — affects deployment topology and where Qdrant/Postgres/object storage live.
5. **PII flagging (FR-029):** `x-pii` markers in OpenAPI schema + access responses.
6. **LLM security (NFR-008):** OWASP LLM Top-10 — router prompt injection (system/role separation, strict JSON, reject non-JSON), corpus poisoning at ingestion, embedding inversion (Qdrant access control).
7. **SOC2-readiness:** evidence-friendly design — `/health` + `/ready`, secret manager, LangSmith traces, API-key rotation (PRD 16.2).

---

## 5. Tech-Stack Currency Notes (R&D)

- **LangGraph 1.0** stable since Oct 2025 — production conditional routing + checkpointing confirmed appropriate (ADR-3).
- **Embedding models:** text-embedding-3-small remains the cost/quality pick at chunk scale; BGE-M3 is the multilingual fallback (ADR-6). No change recommended for MVP.
- **Market:** $2.33B -> $81.51B (42.7% CAGR) re-verified against NextMSC; note other firms publish lower RAG sizings (range $9.86B-$81.51B by horizon) — not a blocker for architecture.
- **Efficacy:** 40-70% token reduction re-verified as an achievable range; the v1.0 "78% hallucination reduction" headline is **unverified** and has been reframed qualitatively — do not design KPIs around the 78% number.

---

## 6. Open Architectural Questions (for solution-architect)

1. **No-retention vs. idempotent re-upload:** idempotency keys on content hash imply persisting a hash; no-retention mode implies persisting nothing. How do these reconcile — is no-retention simply incompatible with the content-hash dedup path, or is a salted/ephemeral hash acceptable?
2. **Erasure atomicity across two stores:** what is the consistency contract for `DELETE` spanning Postgres + Qdrant (and object storage for raw files)? Saga/outbox, two-phase, or best-effort-with-reconciliation sweep? What is the guaranteed state if one store fails mid-delete?
3. **Router output authority:** the router returns `page_ranges[]` and `section_id[]`. Is the Qdrant filter keyed on `section_id` only (Postgres is the page-range authority) or also on page? Define the single source of truth for page ranges to avoid drift between TOC table and vector payload.
4. **Multi-document routing (FR-014):** does the router operate per-document (one TOC at a time) or can a single query fan out across multiple documents' TOCs? This changes the router prompt shape, the `/v1/route` contract, and the retrieval filter.
5. **Tenant isolation & residency topology:** is isolation per-namespace/collection in shared Qdrant + row-level in shared Postgres, or fully separate per-tenant instances? How does India data-residency (FR-028) map onto that — region-pinned collections vs. region-pinned deployments?
6. **Scenario-C degradation boundary:** when TOC extraction yields nothing usable, where exactly does the graph branch to standard full-doc RAG — at ingestion (no sections created) or at query time (router emits `fallback: true`)? Define which component owns the Scenario-C decision and how it is signaled downstream.

---

## 7. Handoff Checklist

- [ ] HLD honors all 10 ADRs (Section 3) without re-opening them.
- [ ] Data model covers the two-store split (Postgres structure / Qdrant vectors) and the erasure cascade.
- [ ] Router contract matches `{relevant_sections[], page_ranges[], confidence[], fallback, routing_time_ms}`.
- [ ] DPDP constraints (Section 4) are designed in, not deferred.
- [ ] The six open questions (Section 6) are answered or explicitly logged as ADR candidates.
- [ ] Targets: router recall >= 85% MVP, fallback < 20%, overhead <= +200ms median (NFR-002/003/005).
