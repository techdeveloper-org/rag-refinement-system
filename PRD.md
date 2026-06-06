# Product Requirements Document (PRD)
## RAG Refinement System — Smart Context RAG Optimizer

**Version:** 2.0
**Date:** 2026-06-06
**Status:** Active — Phase 0 refreshed, awaiting user review before Phase 1 (Architecture)
**Author:** techdeveloper-org
**Supersedes:** v1.0 (2026-03-21, archived at `docs/phase-0-requirements/PRD_v1_archived.md`)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Market Opportunity](#3-market-opportunity)
4. [Competitive Landscape](#4-competitive-landscape)
5. [Product Vision, Goals & OKRs](#5-product-vision-goals--okrs)
6. [Target Users & Personas](#6-target-users--personas)
7. [Product Scope — Two Angles](#7-product-scope--two-angles)
8. [Core Concept & Architecture](#8-core-concept--architecture)
9. [Functional Requirements (FR)](#9-functional-requirements-fr)
10. [Non-Functional Requirements (NFR)](#10-non-functional-requirements-nfr)
11. [WSJF Prioritization & Kano Classification](#11-wsjf-prioritization--kano-classification)
12. [BDD Acceptance Criteria (Top Features)](#12-bdd-acceptance-criteria-top-features)
13. [Requirements Traceability Matrix (RTM)](#13-requirements-traceability-matrix-rtm)
14. [Technical Stack (ADR-Aligned)](#14-technical-stack-adr-aligned)
15. [Performance Benchmarks & Goals](#15-performance-benchmarks--goals)
16. [Compliance, Privacy & Security](#16-compliance-privacy--security)
17. [Business Model](#17-business-model)
18. [Go-To-Market Strategy](#18-go-to-market-strategy)
19. [Risks & Mitigations](#19-risks--mitigations)
20. [Roadmap](#20-roadmap)
21. [Success Metrics](#21-success-metrics)
22. [Appendices](#22-appendices)
23. [Change Log](#23-change-log)

---

## 1. Executive Summary

**RAG Refinement System** is a document-structure-aware retrieval layer that improves the accuracy, speed, and cost of Retrieval-Augmented Generation (RAG) systems.

Standard RAG searches an entire document corpus for every query — wasting tokens, increasing costs, and causing hallucinations when irrelevant content pollutes the context window. Our system solves this by introducing a **TOC-based Router Agent** that first identifies *which sections* of a document are relevant to a query, then performs targeted retrieval *only from those sections*.

**The result:** 40-70% fewer tokens sent to the LLM, materially reduced hallucinations, and faster responses on large documents.

**Two product angles:**
1. **Personal/Developer Tool** — Upload any PDF and get a smart Q&A interface that knows exactly where in the document to look, with cited sections and a routing-confidence explanation.
2. **Enterprise Refinement API** — A plug-in layer that companies integrate over their existing RAG systems to improve them without rebuilding the stack.

**What is new in v2.0 (vs v1.0):** structured FR/NFR with IDs, WSJF + Kano prioritization, OKRs, BDD acceptance criteria, an RTM skeleton, a dedicated DPDP Act 2023 compliance section + SOC2-readiness note, and a tech stack reconciled to the 10 locked Architecture Decision Records (ADRs). Market and efficacy figures have been re-verified; figures that could not be re-sourced are flagged inline as `(unverified - needs source)`.

---

## 2. Problem Statement

### 2.1 How Standard RAG Works (and Why It Fails)

```
User Query
    |
[Vector Search across ALL chunks of ALL documents]
    |
Top-K chunks retrieved (often from wrong sections)
    |
All chunks stuffed into LLM context window
    |
LLM generates answer (often hallucinated or inaccurate)
```

### 2.2 The Core Problems

| Problem | Impact | Current Solutions |
|---------|--------|-------------------|
| **Fixed-size chunking breaks semantics** | Chunks cut mid-sentence/concept, losing context | None — it is the default approach |
| **"Lost in the middle" problem** | LLMs ignore relevant info buried in long contexts | Reranking (post-retrieval, not pre) |
| **No structural awareness** | System does not know a query is about Chapter 3, not Chapter 7 | None exist |
| **Token waste at scale** | A meaningful share of enterprise RAG tokens are irrelevant noise | Context compression (partial) |
| **Hallucination from noise** | Poorly retrieved RAG hallucinates in a significant fraction of responses (error rates reaching up to 40% in critical tasks) | Guard rails (expensive) |
| **Latency from large context** | Larger context = slower response + higher cost | None |

### 2.3 Real-World Example

Imagine a 200-page product manual. A user asks: *"What is the warranty period for the motor?"*

**Standard RAG:**
- Searches all 200 pages
- Retrieves 10 random chunks including introduction, marketing copy, unrelated specs
- LLM gets confused by noise -> hallucinated answer or misses the actual warranty section

**RAG Refinement System:**
- Router looks at TOC -> identifies "Section 8: Warranty & Support" (pages 142-148)
- Retrieves only ~7 pages worth of chunks
- LLM gets clean, relevant context -> accurate answer in less time, at a fraction of the token cost

---

## 3. Market Opportunity

### 3.1 Market Size

| Market | 2025 Value | Projected | CAGR | Source |
|--------|-----------|-----------|------|--------|
| RAG Market | $2.33 Billion | $81.51B by 2035 | 42.7% | NextMSC (re-verified 2026-06-06) |
| Enterprise LLM Market | $6.5 Billion | $49.8B by 2034 | 25.9% | (unverified - needs source) |
| Document AI Market | $14.66 Billion | $27.62B by 2030 | 13.5% | (unverified - needs source) |

> **Re-verification note (2026-06-06):** The RAG market figure ($2.33B -> $81.51B, 42.7% CAGR) was confirmed against NextMSC. Note that other research firms report materially different RAG sizings (e.g., MarketsandMarkets: $1.94B (2025) -> $9.86B (2030) at 38.4% CAGR; ResearchAndMarkets: $1.96B (2025) -> $40.34B (2035) at 35.31% CAGR). We retain the NextMSC figure as the headline but acknowledge the range. The Enterprise LLM and Document AI rows are carried from v1.0 and are flagged unverified pending a primary source.

**Key signals:**
- A large share of organizations report productivity gains from RAG deployments `(unverified - needs source)`.
- RAG is used across a broad range of enterprise AI use cases `(unverified - needs source)`.
- LLM API costs continued to fall through 2025-2026, but token efficiency remains critical for both cost and accuracy (noise reduction).

### 3.2 Why Now?

- Enterprises have deployed RAG but are disappointed with accuracy — they need optimization, not rebuilding.
- LangGraph 1.0 (stable, Oct 2025) makes agentic conditional routing practical and production-ready (see ADR-3).
- No mainstream production tool currently uses a document's native TOC structure as the primary routing signal — this is a genuine whitespace.

---

## 4. Competitive Landscape

### 4.1 Existing Solutions

| Product | What It Does | Gap |
|---------|-------------|-----|
| **LlamaIndex HierarchicalNodeParser** | Size-based parent-child chunks | Not structure-aware; searches all chunks equally |
| **LangChain Parent Document Retriever** | Two-level size chunks | No routing; no TOC; still searches full corpus |
| **RAPTOR (Stanford)** | Recursive summarization tree | Unsupervised clustering; not document-structure-faithful |
| **Microsoft GraphRAG** | Entity knowledge graph | Expensive indexing; for entity queries, not page-range routing |
| **Cohere Rerank API** | Post-retrieval reranking | Operates after retrieval; still searches everything first |
| **Vectara** | Enterprise RAG platform | No structural routing; "RAG sprawl" problem remains |
| **LlamaCloud** | Managed RAG SaaS | No TOC-based routing; requires full stack migration |
| **Unstructured.io** | Document parsing ETL | Parsing layer only; no routing or retrieval |

### 4.2 Unique Differentiation

| Capability | RAPTOR | LlamaIndex | LangChain | GraphRAG | **Ours** |
|-----------|--------|-----------|----------|---------|---------|
| Uses document's native structure | No | No | No | No | **Yes** |
| TOC-based routing before retrieval | No | No | No | No | **Yes** |
| Skips irrelevant sections entirely | No | No | No | Partial | **Yes** |
| Works as a layer over existing RAG | No | No | No | No | **Yes** |
| Interpretable routing decisions | No | No | No | No | **Yes** |
| No full stack migration needed | No | No | No | No | **Yes** |

**The key insight:** Every existing solution either (a) requires you to rebuild your RAG on their stack, or (b) improves retrieval after you have already searched everything. We are the only solution that narrows the search scope *before* vector retrieval using the document's own structure.

---

## 5. Product Vision, Goals & OKRs

### Vision
> *"Make every RAG system as smart as the document it searches."*

### Goals
1. **Accuracy**: Materially reduce hallucination rate vs. standard RAG on structured documents.
2. **Efficiency**: Reduce token consumption by 40-70% per query (verified range).
3. **Simplicity**: Integrate with any existing RAG in under one hour (Enterprise API).
4. **Interpretability**: Always show users *why* the system looked where it did (core differentiator).

### OKRs

**O1 — Prove the accuracy/efficiency thesis on real documents.**
- KR1.1: Achieve >= 85% router correct-section recall on a >= 20-document eval set spanning TOC scenarios A/B/C (MVP).
- KR1.2: Demonstrate 40-70% average token reduction vs. standard RAG across the eval set.
- KR1.3: Keep MVP answer hallucination rate < 15% on the eval set.

**O2 — Ship a usable, interpretable personal tool.**
- KR2.1: End-to-end PDF-upload-to-cited-answer flow working for scenarios A and B.
- KR2.2: Every answer shows selected section(s), page range(s), and a routing-confidence value.
- KR2.3: Median total query overhead vs. standard RAG <= +200ms.

**O3 — Establish enterprise readiness signals.**
- KR3.1: Ship `/v1/route` request/response API with OpenAPI 3.1 contract and >= 0.85 API test coverage.
- KR3.2: Implement DPDP erasure + access endpoints and a no-retention mode.
- KR3.3: Produce SOC2-readiness evidence format and a control-mapping draft.

---

## 6. Target Users & Personas

### 6.1 Personal/Developer Tool Users

| User Type | Use Case | Documents |
|-----------|----------|-----------|
| Developers & Engineers | Technical documentation Q&A | Product manuals, API docs, specs |
| Researchers | Academic paper analysis | Research papers, textbooks |
| Law students / Junior lawyers | Case law research | Legal contracts, judgments |
| Finance professionals | Report analysis | Annual reports, prospectus |
| Students | Study assistance | Textbooks, course notes |

**Pain:** Existing tools (ChatPDF, AskYourPDF) use naive chunking — they often answer incorrectly or miss exact locations.

### 6.2 Enterprise API Users

| User Type | Scale | Current RAG Setup |
|-----------|-------|-------------------|
| Mid-size tech companies | 10K-500K queries/month | Self-built on LangChain/LlamaIndex |
| Enterprise SaaS companies | 500K+ queries/month | Custom or vendor (Vectara, OpenAI) |
| Consulting firms | 1K-50K queries/month | Basic RAG, looking to improve |
| Domain-specific verticals | Variable | Legal, medical, financial RAG |

**Pain:** Existing RAG gives inaccurate answers; LLM costs unpredictable; they do not want to rebuild from scratch.

### 6.3 Primary Personas

- **"Priya the RAG Engineer"** (Enterprise API buyer): owns a production RAG pipeline, measured on answer quality and LLM spend. Wants a drop-in scope-narrowing layer with an interpretable, testable contract and clear data-handling guarantees (DPDP, no-retention).
- **"Arjun the Power Researcher"** (Personal tool): reads dense 100-400 page PDFs daily, needs exact-section citations he can trust and an explanation of where the answer came from.

---

## 7. Product Scope — Two Angles

### Angle 1: Smart Document Q&A (Personal/Developer Tool)

A web application where users upload PDFs and get a smart chat interface. Behind the scenes, the TOC-based router ensures every answer comes from exactly the right part of the document.

**Core User Journey:**
```
Upload PDF -> System extracts/generates TOC -> User asks question
-> Router identifies relevant sections -> Targeted retrieval
-> Accurate answer streamed with source citations (section + page number)
```

**Key differentiator from ChatPDF/Humata:**
- Shows users exactly which section was consulted
- Confidence value for the routing decision
- "Why did you look here?" explainability panel

### Angle 2: RAG Refinement API (Enterprise Layer)

A REST API that enterprise customers integrate as a middleware layer over their existing RAG. Their RAG sends a query + document reference; our API returns the optimal retrieval scope *before* they do their vector search. Per the team-alignment contract, `/v1/route` is **routing-only and request/response** — it performs no generation and never calls the generation LLM.

**Integration Pattern:**
```
[Company's Existing RAG]
         |
         POST /v1/route
         {document_id, query}
         |
[RAG Refinement API]
         |
         Returns: {relevant_sections[], page_ranges[], confidence[], fallback, routing_time_ms}
         |
[Company's Existing RAG — now searches only targeted sections]
         |
LLM -> Accurate Answer
```

**Why enterprises will pay:** immediate ROI — token costs drop, accuracy improves, no stack migration needed.

---

## 8. Core Concept & Architecture

### 8.1 The Three-Stage Pipeline

```
+-------------------------------------------------------------+
|                    STAGE 1: INGESTION                        |
|                                                             |
|  PDF Input -> Parser -> TOC Extraction -> 3-Level Hierarchy |
|                            |                                |
|              Document -> Section -> Chunk                   |
|              (Level 1)   (Level 2)  (Level 3)               |
|                            |                                |
|     Qdrant (chunk vectors) + PostgreSQL (section metadata)  |
+-------------------------------------------------------------+
                             |
+-------------------------------------------------------------+
|                    STAGE 2: ROUTING                         |
|                                                             |
|  User Query -> Router Agent (Claude 3 Haiku) -> TOC Match   |
|                    |                                        |
|  Section A: 0.92 OK   Section B: 0.85 OK                   |
|  Section C: 0.23 no   Section D: 0.18 no                  |
|                    |                                        |
|  Targeted Page Ranges: [45-52, 78-83]                       |
+-------------------------------------------------------------+
                             |
+-------------------------------------------------------------+
|                 STAGE 3: TARGETED RETRIEVAL                 |
|                                                             |
|  Qdrant search filtered by section_id IN (router-selected)  |
|       |                                                     |
|  Optional: Cohere Rerank-3 on retrieved chunks              |
|       |                                                     |
|  Clean, relevant context -> Generation LLM -> Answer        |
+-------------------------------------------------------------+
```

### 8.2 TOC Extraction — Three Scenarios (ADR-4)

**Scenario A: PDF with Embedded Bookmarks (Best Case)**
- PyMuPDF `doc.get_toc()` returns a structured list with page numbers.
- Direct mapping: `[level, title, page_start]` -> section ranges.

**Scenario B: Visual Headers, No Bookmarks (Most Common)**
- Extract text with font properties (size, bold, position).
- Rule-based header detection + LLM refinement (Claude 3 Haiku).
- Generate pseudo-TOC: `{section_title -> page_range}`.

**Scenario C: No Detectable Structure (Worst Case)**
- LLM reads first N pages to generate a semantic map; or topic-labeled sliding-window chunking.
- Fallback to standard full-document RAG (graceful degradation).

**TOC Data Structure:**
```json
{
  "document_id": "doc_abc123",
  "toc": [
    {"level": 1, "title": "Introduction", "page_start": 1, "page_end": 3},
    {"level": 1, "title": "Methodology", "page_start": 4, "page_end": 15},
    {"level": 2, "title": "Data Collection", "page_start": 4, "page_end": 8},
    {"level": 2, "title": "Analysis Methods", "page_start": 9, "page_end": 15},
    {"level": 1, "title": "Results", "page_start": 16, "page_end": 28},
    {"level": 1, "title": "Warranty & Support", "page_start": 142, "page_end": 148}
  ]
}
```

### 8.3 Router Agent Design (ADR-1, ADR-3)

**Input:** User query + Document TOC.
**Output:** A structured JSON object the backend consumes as an in-process async call:
`{relevant_sections[], page_ranges[], confidence[], fallback: bool, routing_time_ms}` (per the ai-engineer <-> python-backend-engineer contract). The router **never** calls the generation LLM.

**Router Prompt Pattern (Claude 3 Haiku):**
```
Given this document TOC and user query, identify which sections
are most likely to contain the answer.

TOC: [...]
Query: "What is the warranty period for the motor?"

Return: strict JSON with section IDs and confidence scores (0.0 - 1.0).
```

The router prompt enforces strict system/role separation and rejects non-JSON output (prompt-injection mitigation, per threat-modeling-specialist <-> ai-engineer contract / OWASP LLM Top-10).

**Confidence Thresholding:**
- Score >= 0.7 -> Include in targeted retrieval.
- Score 0.5-0.7 -> Include if no high-confidence sections found.
- Score < 0.5 -> Exclude (noise).
- If ALL sections < 0.5 -> Fallback to full-document RAG.

### 8.4 3-Level Hierarchy (ADR-2, ADR-10)

```
Level 1 — Document (PostgreSQL: documents)
  Metadata: doc_id, title, total_pages, domain

  Level 2 — Section / TOC entry (PostgreSQL: sections)
    Metadata: section_id, doc_id, title, level, page_start, page_end, summary

    Level 3 — Chunk (Qdrant point)
      Payload: {chunk_id, section_id, doc_id, page}
      Vector: embedding of chunk text
```

Only Level 3 chunks are embedded and stored in Qdrant. Section/document structure lives in PostgreSQL and feeds the router + the Qdrant payload filter. No chunk crosses a section boundary mid-sentence (per python-backend-engineer <-> database-engineer contract).

### 8.5 Ingestion Ownership

The data-engineer owns `parse -> TOC -> section-aware chunk -> embed -> Qdrant upsert + Postgres section rows`, exposed as `ingest_document(doc) -> {doc_id, toc}`. Ingestion is idempotent on content hash; re-upload reuses `doc_id` (per python-backend-engineer <-> data-engineer contract).

---

## 9. Functional Requirements (FR)

> Priority column is P0/P1/P2 (MVP/Should/Nice). WSJF scores and Kano class are in Section 11.

### 9.1 Must-Have (MVP — Phase 1)

| ID | Requirement | Priority |
|----|-------------|----------|
| **FR-001** | The system SHALL accept PDF upload and extract text + structure. | P0 |
| **FR-002** | The system SHALL extract a native TOC from bookmarks (Scenario A) and generate an LLM pseudo-TOC fallback (Scenarios B/C). | P0 |
| **FR-003** | The system SHALL build a 3-level Document -> Section -> Chunk hierarchy with no chunk crossing a section boundary. | P0 |
| **FR-004** | The system SHALL embed chunks and store them in the vector DB with `section_id`/`doc_id`/`page` payload. | P0 |
| **FR-005** | The system SHALL route a query to relevant sections using a LangGraph router emitting `{relevant_sections[], page_ranges[], confidence[], fallback, routing_time_ms}`. | P0 |
| **FR-006** | The system SHALL perform targeted retrieval filtered to router-selected `section_id`s. | P0 |
| **FR-007** | The system SHALL provide a Q&A chat interface for the personal tool. | P0 |
| **FR-008** | The system SHALL display source citations (section title + page range) for every answer. | P0 |
| **FR-009** | The system SHALL fall back to full-document RAG when all section confidences are below threshold. | P0 |

### 9.2 Should-Have (Phase 2)

| ID | Requirement | Priority |
|----|-------------|----------|
| **FR-010** | The system SHALL expose a routing-only REST endpoint `POST /v1/route` (request/response, no generation). | P1 |
| **FR-011** | The system SHALL display routing confidence values to users. | P1 |
| **FR-012** | The system SHALL provide a "why did you look here?" routing-explainability panel listing selected sections, scores, page ranges, and rationale. | P1 |
| **FR-013** | The system SHALL support hybrid search (TOC routing + BM25 keyword + vector). | P1 |
| **FR-014** | The system SHALL support querying across multiple related documents. | P1 |
| **FR-015** | The system SHALL rewrite vague queries before routing. | P1 |
| **FR-016** | The system SHALL optionally apply Cohere Rerank-3 post-route, toggleable per request. | P1 |
| **FR-017** | The system SHALL support scanned/image PDFs via OCR fallback (Azure Document Intelligence). | P1 |
| **FR-018** | The system SHALL stream answers token-by-token to the personal tool via SSE, ending with a final event carrying `{answer, citations[], routing{}}`. | P1 |

### 9.3 Nice-to-Have (Phase 3+)

| ID | Requirement | Priority |
|----|-------------|----------|
| **FR-019** | The system SHALL capture user like/dislike feedback to improve routing. | P2 |
| **FR-020** | The system SHALL provide a dashboard of token savings, accuracy, and usage analytics. | P2 |
| **FR-021** | The system SHALL provide Python/JavaScript SDKs and published API docs. | P2 |
| **FR-022** | The system SHALL support domain-specific router fine-tuning. | P2 |
| **FR-023** | The system SHALL support multilingual documents via a multilingual embedding fallback (BGE-M3). | P2 |
| **FR-024** | The system SHALL provide a user document library / management surface. | P2 |

### 9.4 Compliance & Data-Handling FRs

| ID | Requirement | Priority |
|----|-------------|----------|
| **FR-025** | The system SHALL provide `DELETE /v1/documents/{id}` to erase a document and all derived chunks/sections (DPDP erasure). | P1 |
| **FR-026** | The system SHALL provide `GET /v1/documents/{id}/data` returning the personal data held for a document (DPDP access). | P1 |
| **FR-027** | The system SHALL support a no-retention mode that purges chunks, sections, and raw upload after the answer is returned. | P1 |
| **FR-028** | The system SHALL support an India data-residency configuration for tenant data. | P1 |
| **FR-029** | The system SHALL flag PII fields with `x-pii` in the OpenAPI schema and access responses. | P1 |

### 9.5 Non-Goals (Explicitly Out of Scope)

- Building a full LLM or foundation model.
- Replacing LangChain or LlamaIndex entirely.
- Real-time streaming document ingestion.
- Image/video/audio content analysis.
- Full enterprise CRM/DMS integration in Phase 1.
- No financial/health *regulatory certification* scope in MVP (though legal/healthcare/finance are named target verticals -> answer faithfulness is treated as safety-critical).

---

## 10. Non-Functional Requirements (NFR)

| ID | Category | Requirement |
|----|----------|-------------|
| **NFR-001** | Performance — Routing | Router LLM call SHALL complete in 100-300ms; cached TOC lookup < 10ms. |
| **NFR-002** | Performance — Overhead | Total added overhead vs. standard RAG SHALL be <= +200ms median. |
| **NFR-003** | Accuracy | Router correct-section recall SHALL be >= 85% (MVP) / >= 95% (6-mo). |
| **NFR-004** | Accuracy | Answer hallucination rate SHALL be < 15% (MVP). |
| **NFR-005** | Reliability | Router fallback rate SHALL be < 20% (MVP) / < 10% (6-mo). |
| **NFR-006** | Scalability | Routing path SHALL be designed for horizontal scale to 10K-500K+ calls/month; MVP ships at low scale. |
| **NFR-007** | Security | User documents (PII), provider API keys, and tenant data SHALL be protected; all secrets via 12-factor env / secret manager, never in code/repo. |
| **NFR-008** | Security — LLM | The router/answer path SHALL be hardened against the OWASP LLM Top-10 (prompt injection, corpus poisoning, embedding inversion). |
| **NFR-009** | Observability | All routing/generation runs SHALL be traced in LangSmith; each service exposes `/health` and `/ready`. |
| **NFR-010** | API Contract | Every endpoint SHALL conform to the Phase 1.5 OpenAPI 3.1 spec; errors SHALL use RFC-7807 problem+json. |
| **NFR-011** | Interpretability | Every answer SHALL be explainable (selected sections, scores, page ranges, rationale) — mandatory differentiator. |
| **NFR-012** | Internationalization | Non-English documents SHALL be supported via the BGE-M3 multilingual embedding fallback. |
| **NFR-013** | Availability | Each service SHALL support graceful degradation to full-doc RAG on router/dependency failure. |
| **NFR-014** | Compliance | The system SHALL meet DPDP Act 2023 obligations (see Section 16) and produce SOC2-readiness evidence. |
| **NFR-015** | Auth | Enterprise API SHALL authenticate via API keys (with rotation); personal tool via OAuth2/JWT bearer. |

---

## 11. WSJF Prioritization & Kano Classification

WSJF = (User-Business Value + Time Criticality + Risk Reduction/Opportunity Enablement) / Job Size. Each component scored 1-10 (relative); higher WSJF = do sooner. Scores are relative planning estimates, not measured.

| FR | Value | Time-Crit | RR/OE | Job Size | **WSJF** | Kano |
|----|------:|----------:|------:|---------:|---------:|------|
| FR-005 Router Agent | 10 | 9 | 10 | 5 | **5.8** | Performance |
| FR-002 TOC Extraction | 9 | 9 | 9 | 5 | **5.4** | Must-be |
| FR-006 Targeted Retrieval | 10 | 8 | 8 | 5 | **5.2** | Performance |
| FR-008 Source Citations | 8 | 7 | 7 | 3 | **7.3** | Must-be |
| FR-009 Fallback Mode | 7 | 7 | 9 | 3 | **7.7** | Must-be |
| FR-001 PDF Upload & Parse | 8 | 8 | 5 | 3 | **7.0** | Must-be |
| FR-003 3-Level Chunking | 8 | 7 | 7 | 4 | **5.5** | Must-be |
| FR-004 Vector Indexing | 8 | 7 | 6 | 4 | **5.3** | Must-be |
| FR-012 Routing Explainability | 8 | 6 | 6 | 3 | **6.7** | Delighter |
| FR-010 `/v1/route` API | 9 | 6 | 6 | 5 | **4.2** | Performance |
| FR-018 Streaming Answers | 6 | 5 | 4 | 3 | **5.0** | Delighter |
| FR-016 Cohere Rerank | 6 | 4 | 6 | 3 | **5.3** | Performance |
| FR-025 DPDP Erasure | 7 | 7 | 9 | 3 | **7.7** | Must-be (enterprise) |
| FR-027 No-Retention Mode | 7 | 6 | 9 | 4 | **5.5** | Must-be (enterprise) |
| FR-007 Q&A Interface | 7 | 7 | 4 | 4 | **4.5** | Must-be |
| FR-011 Confidence Display | 6 | 5 | 5 | 2 | **8.0** | Delighter |

**Top WSJF cluster (build first):** FR-011, FR-009, FR-025, FR-008, FR-001, FR-012 — note that several high-WSJF items are small-job-size enablers/differentiators. The P0 *foundation* (FR-001 -> FR-006) must still land first as a dependency chain; WSJF guides sequencing *within* feasible sets, not dependency order.

**Kano summary:**
- **Must-be** (absence kills the product): FR-001, FR-002, FR-003, FR-004, FR-006, FR-008, FR-009, FR-025, FR-027.
- **Performance** (more is better — the core thesis): FR-005, FR-010, FR-016 (token reduction & routing accuracy scale with these).
- **Delighters** (differentiation): FR-011, FR-012, FR-018 (interpretability + streaming).

---

## 12. BDD Acceptance Criteria (Top Features)

### FR-005 — Router Agent
```gherkin
Feature: TOC-based query routing
  Scenario: High-confidence single-section route
    Given a document with an extracted TOC containing "Warranty & Support" (pages 142-148)
    When the user asks "What is the warranty period for the motor?"
    Then the router returns "Warranty & Support" with confidence >= 0.7
    And page_ranges includes [142, 148]
    And fallback is false
    And routing_time_ms is between 100 and 300

  Scenario: Low-confidence triggers fallback
    Given a document whose TOC has no section matching the query intent
    When the user asks an off-topic question
    Then every section confidence is < 0.5
    And fallback is true
    And the system retrieves over the full document
```

### FR-002 — TOC Extraction
```gherkin
Feature: TOC extraction across scenarios
  Scenario: Native bookmarks (Scenario A)
    Given a PDF with embedded bookmarks
    When the document is ingested
    Then a TOC is produced directly from get_toc() with level, title, page_start, page_end

  Scenario: Visual headers, no bookmarks (Scenario B)
    Given a PDF with heading-styled text but no bookmarks
    When the document is ingested
    Then a pseudo-TOC is generated mapping section_title to page_range
```

### FR-008 — Source Citations
```gherkin
Feature: Cited answers
  Scenario: Answer carries section + page citation
    Given a successfully routed query
    When the answer is generated
    Then the response includes citations with section_title, page_start, page_end
    And each cited page falls within a router-selected section
```

### FR-009 — Fallback Mode
```gherkin
Feature: Graceful degradation
  Scenario: Router uncertainty falls back to full-doc RAG
    Given all section confidences are below the threshold
    When the query is processed
    Then the system performs standard full-document retrieval
    And the response indicates fallback was used
```

### FR-025 — DPDP Erasure
```gherkin
Feature: Right to erasure (DPDP Act 2023)
  Scenario: Delete document purges all derived data
    Given an ingested document with chunks in Qdrant and sections in PostgreSQL
    When a DELETE /v1/documents/{id} request is authorized and made
    Then the document, its sections, and its chunk vectors are removed
    And a subsequent GET /v1/documents/{id} returns 404
```

### FR-027 — No-Retention Mode
```gherkin
Feature: No-retention processing
  Scenario: Ephemeral answer leaves no stored data
    Given no-retention mode is enabled for the request
    When the query is answered
    Then the raw upload, chunks, and sections are purged after the response
    And no document data persists in Qdrant or PostgreSQL
```

---

## 13. Requirements Traceability Matrix (RTM)

> Skeleton. Architecture/design/test IDs are filled in subsequent phases (HLD = Phase 1, API = Phase 1.5, SRS/UML = Phase 5, tests = Phase D).

| FR/NFR | OKR | ADR(s) | Architecture (HLD) | API Contract | Test Case(s) | Status |
|--------|-----|--------|--------------------|--------------|--------------|--------|
| FR-001 | O2.KR2.1 | ADR-4, ADR-5 | TBD | upload endpoint | TBD | Specified |
| FR-002 | O1.KR1.1 | ADR-4, ADR-1 | TBD | (ingest) | TBD | Specified |
| FR-003 | O1.KR1.2 | ADR-10, ADR-2 | TBD | (ingest) | TBD | Specified |
| FR-004 | O1.KR1.2 | ADR-2, ADR-6 | TBD | (ingest) | TBD | Specified |
| FR-005 | O1.KR1.1 | ADR-1, ADR-3 | TBD | /v1/route | TBD | Specified |
| FR-006 | O1.KR1.2 | ADR-2, ADR-10 | TBD | (internal) | TBD | Specified |
| FR-007 | O2.KR2.1 | ADR-9 | TBD | /v1/answer | TBD | Specified |
| FR-008 | O2.KR2.2 | ADR-10 | TBD | /v1/answer | TBD | Specified |
| FR-009 | O1.KR1.3 | ADR-3 | TBD | /v1/route | TBD | Specified |
| FR-010 | O3.KR3.1 | ADR-5, ADR-7 | TBD | /v1/route | TBD | Specified |
| FR-011 | O2.KR2.2 | ADR-9 | TBD | /v1/answer | TBD | Specified |
| FR-012 | O2.KR2.2 | ADR-9 | TBD | /v1/answer | TBD | Specified |
| FR-016 | O1.KR1.1 | ADR-8 | TBD | /v1/route | TBD | Specified |
| FR-018 | O2.KR2.2 | ADR-9, ADR-5 | TBD | /v1/answer (SSE) | TBD | Specified |
| FR-025 | O3.KR3.2 | ADR-5, ADR-10 | TBD | /v1/documents/{id} | TBD | Specified |
| FR-026 | O3.KR3.2 | ADR-5, ADR-10 | TBD | /v1/documents/{id}/data | TBD | Specified |
| FR-027 | O3.KR3.2 | ADR-2, ADR-10 | TBD | request flag | TBD | Specified |
| FR-028 | O3.KR3.2 | ADR-2, ADR-10 | TBD | tenant config | TBD | Specified |
| NFR-008 | O1 | ADR-1, ADR-2 | TBD | n/a | TBD | Specified |
| NFR-010 | O3.KR3.1 | ADR-5 | TBD | all | TBD | Specified |
| NFR-014 | O3.KR3.2 | ADR-5, ADR-10 | TBD | compliance endpoints | TBD | Specified |

---

## 14. Technical Stack (ADR-Aligned)

> This stack is locked to the 10 ADRs in `docs/execution/_common_context.md`. Where v1.0 left a vendor "or" choice, v2.0 resolves it per ADR.

| Component | Technology | ADR | Reason |
|-----------|-----------|-----|--------|
| **Document Parsing / TOC** | PyMuPDF + PyMuPDF4LLM | ADR-4 | Native `get_toc()`, fast, free (Scenario A) |
| **Complex Docs Fallback** | Unstructured.io | ADR-4 | Tiered fallback for Scenario B |
| **Scanned PDFs (OCR)** | Azure Document Intelligence | ADR-4 | Scenario C / scanned layouts |
| **Pseudo-TOC + Router LLM** | **Claude 3 Haiku** | ADR-1 | Sub-300ms, strong structured-JSON; same vendor as generation (one key/SLA) |
| **Agent Orchestration** | **LangGraph 1.0** | ADR-3 | Conditional routing + checkpointing for Router->Retrieve->Generate with fallback branch |
| **Embeddings** | **OpenAI text-embedding-3-small** (primary) + **BGE-M3** (multilingual fallback) | ADR-6 | Best cost/quality; multilingual without a second paid vendor |
| **Vector DB (Dev)** | ChromaDB | ADR-2 | Local-first, near-zero dev friction |
| **Vector DB (Prod)** | **Qdrant** | ADR-2 | Rich payload metadata filtering (the "scope before search" mechanism); Rust perf |
| **Metadata Store** | **PostgreSQL** | ADR-10 | Relational L1/L2 hierarchy + ACID; structure store separate from vector store |
| **Reranker (optional)** | Cohere Rerank-3 | ADR-8 | ~20-35% precision lift, per-request toggle |
| **API Framework** | **FastAPI** (async) | ADR-5 | Async I/O; auto OpenAPI 3.1; Pydantic validation |
| **Generation LLM** | Claude / GPT-4o | — | Streamed to personal tool; never invoked by `/v1/route` |
| **Authentication** | API keys (enterprise) + OAuth2/JWT (personal) | ADR-7 | Standard enterprise contract + SPA session model |
| **Frontend (Personal Tool)** | **React + TailwindCSS + Vite** | ADR-9 | Mature streaming-UI ecosystem; Tailwind maps to Phase 3 design tokens |
| **Observability** | LangSmith | — | RAG eval + tracing |
| **Packaging / CI** | Docker + CI/CD (lint+type+test gates) | — | 12-factor, `/health` + `/ready` per service |

### 14.1 Enterprise API Contract (Routing-Only)

**Endpoint:** `POST /v1/route` (request/response; no generation)

**Request:**
```json
{
  "document_id": "doc_abc123",
  "query": "What is the warranty period for the motor?",
  "confidence_threshold": 0.7,
  "max_sections": 3
}
```

**Response:**
```json
{
  "query_id": "qry_xyz789",
  "relevant_sections": [
    {"section_id": "sec_warranty", "title": "Warranty & Support",
     "page_start": 142, "page_end": 148, "confidence": 0.94}
  ],
  "page_ranges": [[142, 148]],
  "confidence": [0.94],
  "routing_time_ms": 210,
  "fallback": false,
  "estimated_token_reduction": "87%"
}
```

The `/v1/answer` endpoint (personal tool) streams tokens via SSE, then emits a final event:
`{answer, citations[{section_title, page_start, page_end}], routing{sections[], confidence[], fallback}}`.

---

## 15. Performance Benchmarks & Goals

### 15.1 Token Reduction (illustrative)

| Document Size | Standard RAG Tokens | With Refinement | Reduction |
|--------------|--------------------:|----------------:|----------:|
| 50-page doc, single-section query | ~40,000 | ~4,000 | **90%** |
| 200-page doc, multi-section query | ~160,000 | ~32,000 | **80%** |
| 500-page doc, specific query | ~400,000 | ~20,000 | **95%** |

*The above are best-case illustrations. Conservative real-world target after routing uncertainty: **40-70% average reduction** (verified achievable range for context-narrowing techniques).*

### 15.2 Accuracy Goals

| Metric | Standard RAG Baseline | Target (Phase 1) | Target (Phase 2) |
|--------|----------------------|-----------------|-----------------|
| Hallucination rate | Up to ~40% in critical tasks (range varies by domain; legal RAG studies report up to ~33%) | < 15% | < 5% |
| Answer accuracy (structured docs) | ~65% `(unverified - needs source)` | > 85% | > 92% |
| Retrieval precision | ~60% `(unverified - needs source)` | > 80% | > 90% |

### 15.3 Latency Goals

| Stage | Time Budget |
|-------|-------------|
| TOC lookup (cached) | < 10ms |
| Router LLM call | 100-300ms |
| Targeted vector search | 50-150ms |
| Total overhead vs. standard RAG | +100-200ms |
| Net effect (large docs) | **Faster** (reduced retrieval scope offsets routing overhead) |

> **Superseded claim (from v1.0):** v1.0 headlined "up to 78% reduction in hallucinations" as a verified figure citing "LangGraph Research." This specific 78% adaptive-routing figure could **not** be re-sourced (the literature reports a range — e.g., RAG grounding reducing hallucinations by 40%+, self-reflective RAG ~5.8% residual — but not a 78% adaptive-routing result). v2.0 reframes the hallucination claim qualitatively ("materially reduced") and flags the 78% figure as `(unverified - needs source)`; it is retained only in the Change Log and Appendix for traceability, not as a headline metric.

---

## 16. Compliance, Privacy & Security

### 16.1 DPDP Act 2023 (India) — Data Handling

The product ingests user-uploaded documents that may contain personal data, so it is treated as a Data Fiduciary surface under India's Digital Personal Data Protection (DPDP) Act, 2023.

| Obligation | Mechanism | FR/NFR |
|------------|-----------|--------|
| **PII identification** | PII fields flagged `x-pii` in OpenAPI schema and access responses (DPDP §4 lawful processing). | FR-029 |
| **Right to erasure** | `DELETE /v1/documents/{id}` purges document + sections (PostgreSQL) + chunk vectors (Qdrant) (DPDP §8). | FR-025 |
| **Right to access** | `GET /v1/documents/{id}/data` returns the personal data held for a document (DPDP §8). | FR-026 |
| **No-retention mode** | Per-request flag purges raw upload + chunks + sections after the answer is returned. | FR-027 |
| **Data residency** | Configurable India-region storage for tenant data. | FR-028 |
| **Incident reporting** | CERT-In 6-hour incident-reporting hook on security events. | NFR-007 |

### 16.2 SOC2 Readiness (Enterprise Sales)

SOC2 Type II is on the enterprise-sales roadmap (not an MVP certification gate). MVP work produces evidence in a SOC2-ready format:
- **Security:** secrets in a secret manager (never in code/repo); SAST + secrets scan on every CI run; SCA/CVE + SBOM on dependency changes; DAST against staging before launch.
- **Availability:** `/health` + `/ready` probes; graceful degradation to full-doc RAG.
- **Confidentiality:** tenant isolation; Qdrant access control to mitigate embedding-inversion; API-key rotation.
- **Processing integrity:** OpenAPI-validated request/response; RFC-7807 error contract; LangSmith trace evidence.
- **Privacy:** the DPDP controls in 16.1 double as SOC2 privacy-criteria evidence.

GDPR-readiness is a follow-on if EU customers are onboarded (the DPDP erasure/access endpoints map closely to GDPR Articles 15/17).

### 16.3 LLM & Application Security (Summary)

Full Phase F security audit (canonical roster) applies. The threat model extends STRIDE with the **OWASP LLM Top-10**: prompt injection on the router prompt (system/role separation + strict JSON validation + reject non-JSON), RAG corpus poisoning at ingestion (content checks), and embedding inversion on stored chunks (Qdrant access control). API surface gets IDOR/mass-assignment review on `/v1/documents/{id}`, OAuth2/JWT validation, API-key rotation, rate-limit-bypass, and CORS audit.

---

## 17. Business Model

### 17.1 Personal / Developer Tool

| Tier | Price | Limits |
|------|-------|--------|
| **Free** | $0/month | 3 documents, 50 queries/month |
| **Pro** | $12/month | 50 documents, 1,000 queries/month, API access |
| **Power** | $29/month | Unlimited documents, 10,000 queries/month, priority support |

### 17.2 Enterprise API

| Tier | Price | Includes |
|------|-------|---------|
| **Starter** | $299/month | 50,000 routing calls/month, 5 GB document storage |
| **Growth** | $999/month | 250,000 routing calls/month, 25 GB storage, SLA |
| **Enterprise** | Custom | Unlimited, dedicated infra, on-premise option, custom SLA, DPDP residency |

**Per-usage add-ons:** routing calls beyond plan $0.003/call; document indexing $0.01/page (one-time per document).

*Pricing is a hypothesis to be validated against willingness-to-pay during Phase 1/2 design-partner conversations.*

### 17.3 Revenue Projections (Conservative, illustrative)

| Month | Personal Users | Enterprise Clients | MRR |
|-------|---------------|-------------------|-----|
| M3 (POC done) | 50 | 0 | $300 |
| M6 | 200 | 2 | $2,400 |
| M12 | 1,000 | 10 | $15,000 |
| M18 | 3,000 | 25 | $45,000 |

---

## 18. Go-To-Market Strategy

### 18.1 Phase 1: Dogfooding & Validation
- Build the personal tool for own use; document real metrics (token reduction %, accuracy lift).
- Create before/after demos with real PDFs (research papers, legal docs, manuals).

### 18.2 Phase 2: Developer Community
- Open-source the core library (Apache 2.0) to build trust.
- Publish to GitHub with README, demos, benchmarks; write "how we cut RAG token cost 40-70%" posts.
- Share on HN, Reddit r/MachineLearning, r/LangChain; engage LangChain/LlamaIndex discussions.

### 18.3 Phase 3: Enterprise Sales
- **ROI Calculator** on the website (current LLM spend -> projected savings).
- Case studies from Phase 1/2; target companies with active RAG deployments.
- Offer a free trial to the first design-partner enterprises in exchange for testimonials.

### 18.4 Target Verticals (Enterprise)

| Vertical | Document Type | Pain |
|----------|--------------|------|
| **Legal** | Contracts, case files, regulations | Hallucinated citations are legally dangerous |
| **Healthcare** | Clinical guidelines, records | Accuracy is safety-critical |
| **Financial** | Annual reports, prospectus, regulations | Compliance requires exact sourcing |
| **Manufacturing** | Technical manuals, SOPs | Field engineers need fast, precise answers |
| **Education** | Textbooks, course materials | Scale + accuracy for student Q&A |

---

## 19. Risks & Mitigations

| Risk | Severity | Likelihood | Mitigation |
|------|----------|-----------|------------|
| PDFs without embedded TOC | High | High | LLM pseudo-TOC (Scenario B/C); header heuristics (ADR-4) |
| Router wrong-section prediction | High | Medium | Top-K + confidence threshold + full-doc fallback (FR-009) |
| Routing adds unacceptable latency | Medium | Low | Cache TOC; Claude 3 Haiku fast router; parallelism (NFR-001/002) |
| Scanned/image PDFs fail parsing | Medium | Medium | Azure Document Intelligence OCR (FR-017, ADR-4) |
| Prompt injection / corpus poisoning | High | Medium | OWASP LLM Top-10 hardening; strict JSON router contract (NFR-008) |
| Embedding inversion on stored chunks | Medium | Low | Qdrant access control; tenant isolation (NFR-008) |
| DPDP / data-privacy non-compliance | High | Medium | Erasure/access endpoints, no-retention, residency (Section 16) |
| Large competitors copy the idea | High | Medium | Move fast; community; open-source core; interpretability moat |
| LangGraph API changes break routing | Low | Low | Pin versions; abstract router interface (ADR-3) |
| Multi-language documents | Medium | Medium | BGE-M3 multilingual fallback (FR-023, ADR-6) |

---

## 20. Roadmap

### Phase 0: Research & PRD (DONE)
- [x] Idea definition; market + competitive analysis
- [x] PRD v1.0 created (2026-03-21)
- [x] PRD v2.0 refresh — structured FR/NFR, WSJF/Kano/OKRs, BDD, RTM, DPDP/SOC2, ADR alignment (2026-06-06)

### Phase 1: MVP — Personal Tool
- [ ] PDF parsing pipeline (PyMuPDF + pseudo-TOC) — FR-001, FR-002
- [ ] 3-level chunking + indexing (ChromaDB dev / Qdrant prod) — FR-003, FR-004
- [ ] Router Agent (LangGraph 1.0, Claude 3 Haiku) — FR-005
- [ ] Targeted retrieval + fallback — FR-006, FR-009
- [ ] Q&A UI (React + Tailwind + Vite) + citations — FR-007, FR-008

### Phase 2: Refinement & Metrics
- [ ] Benchmark vs. standard RAG on 20+ docs (scenarios A/B/C)
- [ ] Token-reduction measurement + reporting
- [ ] Hybrid search; query rewriting; Cohere Rerank — FR-013, FR-015, FR-016
- [ ] Confidence display + explainability panel — FR-011, FR-012

### Phase 3: Enterprise API + Compliance
- [ ] `/v1/route` + document management API — FR-010
- [ ] DPDP erasure/access, no-retention, residency — FR-025..FR-029
- [ ] Auth (API keys + JWT, rotation, rate limiting) — NFR-015
- [ ] LangSmith monitoring; SOC2-readiness evidence

### Phase 4: Product & Growth
- [ ] Scanned PDF OCR — FR-017
- [ ] Multi-document queries; feedback loop; dashboard; SDKs — FR-014, FR-019, FR-020, FR-021
- [ ] Open-source core; community building; (fine-tuned router deferred per ADR-1)

---

## 21. Success Metrics

### Technical KPIs

| Metric | MVP Target | 6-Month Target |
|--------|-----------|---------------|
| Token reduction vs. standard RAG | > 40% | > 60% |
| Answer accuracy (structured docs) | > 80% | > 90% |
| Routing latency | < 400ms | < 200ms |
| Router correct-section recall | > 85% | > 95% |
| Fallback rate (router uncertainty) | < 20% | < 10% |

### Business KPIs

| Metric | 3-Month | 6-Month | 12-Month |
|--------|--------|--------|---------|
| GitHub stars | 200 | 1,000 | 5,000 |
| Personal tool users | 100 | 500 | 3,000 |
| Enterprise API clients | 0 | 3 | 15 |
| MRR | $500 | $3,000 | $20,000 |

---

## 22. Appendices

### Appendix A: Key Research References

| Topic | Finding | Source | Verification (2026-06-06) |
|-------|---------|--------|---------------------------|
| RAG Market 2025 | $2.33B -> $81.51B by 2035, 42.7% CAGR | NextMSC | Re-verified (NextMSC confirms; other firms report lower) |
| Hallucination in poor RAG | Error rates up to ~40% in critical tasks; legal RAG up to ~33% | cmarix / Stanford legal-RAG study | Re-verified (range, not single study) |
| Token reduction | 40-70%+ achievable via context narrowing/compression | Multiple (RecoAgent, ragaboutit, SitePoint) | Re-verified |
| Adaptive routing hallucination cut | "up to 78%" | LangGraph Research (v1.0 claim) | **(unverified - needs source)** |
| Reranking accuracy boost | 20-35% improvement | Cohere (ADR-8) | Carried from ADR; cited |
| RAPTOR accuracy gain | +20% absolute on QuALITY | Stanford ICLR 2024 | Carried from v1.0 |
| LinkedIn RAG case study | 28.6% support resolution time reduction | LangChain | (unverified - needs source) |
| European bank ROI | EUR 20M saved over 3 years | Squirro | (unverified - needs source) |
| LangGraph stable release | October 2025 | LangChain Blog (ADR-3) | Consistent with ADR-3 |

### Appendix B: Glossary

| Term | Definition |
|------|------------|
| **RAG** | Retrieval-Augmented Generation — LLM answers queries by retrieving relevant documents |
| **TOC** | Table of Contents — structured document index (chapters, sections, pages) |
| **Router Agent** | AI agent that decides which document sections to search for a given query |
| **Hierarchical RAG** | RAG with multi-level document structure (document -> section -> chunk) |
| **Agentic RAG** | RAG where AI agents make dynamic retrieval decisions |
| **Hallucination** | When an LLM generates false information not supported by retrieved context |
| **Chunk** | Small text unit (100-512 tokens) embedded and stored in the vector DB |
| **Confidence Score** | Router's certainty (0.0-1.0) that a section is relevant to a query |
| **Pseudo-TOC** | LLM-generated table of contents for documents without embedded structure |
| **WSJF** | Weighted Shortest Job First — (value + time-crit + risk/opportunity) / job size |
| **Kano** | Model classifying features as Must-be / Performance / Delighter |
| **DPDP** | India's Digital Personal Data Protection Act, 2023 |
| **RTM** | Requirements Traceability Matrix |

### Appendix C: ADR Cross-Reference

The locked technical decisions live in `docs/execution/_common_context.md` (ADR-1 through ADR-10). Section 14 of this PRD reflects those decisions; any change to the stack must update the ADR first, then this PRD.

---

## 23. Change Log

| Date | Version | Change Summary | Status |
|------|---------|----------------|--------|
| 2026-03-21 | 1.0 | Initial PRD: problem, market, competitive landscape, two-angle scope, three-stage pipeline, feature tables, tech stack, business model, roadmap. Archived at `docs/phase-0-requirements/PRD_v1_archived.md`. | Superseded |
| 2026-06-06 | 2.0 | **Refreshed from v1.0** (same product idea). Added: structured FR-001..FR-029 and NFR-001..NFR-015; WSJF + Kano (Section 11); OKRs (Section 5); BDD Gherkin acceptance for top FRs (Section 12); RTM skeleton (Section 13); dedicated DPDP Act 2023 + SOC2-readiness section (Section 16); tech stack reconciled to the 10 ADRs (Section 14); personas (Section 6). Re-verified market/efficacy figures; flagged unverified figures inline. **Superseded claim:** the v1.0 headline "up to 78% hallucination reduction" could not be re-sourced and is reframed qualitatively (see Section 15.3). Resolved v1.0 vendor "or" choices to ADR picks (Claude 3 Haiku router; Qdrant prod / ChromaDB dev; PostgreSQL metadata store; React+Tailwind+Vite). | Active |

---

*PRD Version 2.0 | RAG Refinement System | techdeveloper-org | 2026-06-06 | Refreshed from v1.0 (2026-03-21)*
