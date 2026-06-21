# RAG Refinement System

[![CI](https://github.com/techdeveloper-org/rag-refinement-system/actions/workflows/ci.yml/badge.svg)](https://github.com/techdeveloper-org/rag-refinement-system/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Coverage: 100%](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/techdeveloper-org/rag-refinement-system)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> **Smart Context RAG Optimizer** — a document-structure-aware retrieval layer
> that routes each query to the relevant document sections *before* vector
> search, cutting context tokens by a verified **40–70%** while improving answer
> accuracy and interpretability.

Standard RAG searches the whole document for every query, drowning the model in
noise. This system reads the document's structure (Table of Contents) first,
routes the query to the sections that actually matter, and retrieves only from
there. Less noise, fewer tokens, more accurate and *explainable* answers.

```
Standard RAG:    Query → search 200 pages → noise → hallucination
RAG Refinement:  Query → TOC Router → 7 relevant pages → cited, explainable answer
```

---

## Overview

The system ships as **two product surfaces over one API contract**:

1. **Personal Tool (SPA)** — a React + Vite single-page app: upload a PDF, ask
   questions, and get streamed answers that cite exact sections, with a
   confidence meter and a "why did you look here?" explainability panel.
2. **Enterprise Refinement API** — `POST /v1/route` is **routing-only**: it
   returns the optimal retrieval scope (`relevant_sections`, `page_ranges`,
   per-section `confidence`, `fallback`, `routing_time_ms`, and an interpretable
   rationale) and **never calls the generation LLM**. Drop it in front of an
   existing RAG stack — no migration required.

The differentiators are **interpretable routing** (mandatory — you always see
why the router scoped where it did) and **graceful degradation**: when no
section clears the confidence threshold, the router sets `fallback: true` so the
caller can fall back to full-document retrieval.

### Project status

| Area | Status |
|------|--------|
| Pre-implementation (PRD → architecture → API contract → design → SRS/UML → sprint plan → alignment) | Complete |
| Backend implementation (ingestion, LangGraph router, FastAPI API, auth, rate limiting) | Implemented |
| Frontend personal tool (React + Vite SPA, 48 vitest tests) | Implemented |
| Hallucination gate | NLI = 1.0, FactScore = 1.0 |
| QA pipeline | **100% statement + branch coverage**; 286 Python tests pass; DRE = 1.0 |
| Security audit | **APPROVED** — 0 unresolved findings |
| Reliability gate | **RS = 1.0** — deploy authorized |
| Production deploy config | Production-ready compose + k8s manifests + runbook |
| **Live cloud deployment** | **Not yet performed** — requires operator's cloud credentials (see the [deploy runbook](docs/phase-G-deploy/deploy_runbook.md)) |

Full product context: **[PRD.md](./PRD.md)** · Requirements: **[SRS.md](./SRS.md)**

---

## Table of Contents

- [Prerequisites](#prerequisites--requirements)
- [Installation / Setup](#installation--setup)
- [Usage](#usage)
- [Architecture](#architecture)
- [Contributing](#contributing)
- [Code of Conduct](#code-of-conduct)
- [License](#license)

---

## Prerequisites / Requirements

**Backend and tests**

- Python **3.11+**
- **Docker** + Docker Compose (for the full stack)
- PostgreSQL 16 and Qdrant — provided by `docker-compose.yml` for local dev

**Frontend (personal tool)**

- Node.js **20+** and npm

**Provider credentials (optional for local dev; required for real answers)**

Copy `.env.example` → `.env` and fill in values:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Embeddings (text-embedding-3-small) |
| `ANTHROPIC_API_KEY` | Router LLM (Claude 3 Haiku) + generation |
| `COHERE_API_KEY` | Optional reranking (Cohere Rerank-3) |
| `LANGSMITH_API_KEY` | Optional tracing/observability |
| `DATABASE_URL` | PostgreSQL DSN (structure store) |
| `QDRANT_URL` | Qdrant base URL (vector store) |
| `JWT_SECRET`, `API_KEY_SALT` | Auth (OAuth2/JWT + API keys) |

Secrets are injected from the environment (12-factor). **Never commit a populated `.env`** — it is gitignored.

---

## Installation / Setup

### Option A — Full stack with Docker Compose (recommended)

```bash
git clone https://github.com/techdeveloper-org/rag-refinement-system.git
cd rag-refinement-system
cp .env.example .env          # fill in provider keys for real answers
docker compose up -d --build  # starts postgres + qdrant + api on :8000
```

The API is then at `http://localhost:8000` (OpenAPI docs at `/docs`).

### Option B — Backend only (local Python)

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install ".[dev]"                                # installs runtime + dev tooling
uvicorn backend.app.main:app --reload --port 8000   # http://localhost:8000
```

Bring up just the data stores with:

```bash
docker compose up -d postgres qdrant
```

Then set `DATABASE_URL` and `QDRANT_URL` in your `.env`.

### Frontend (personal tool)

```bash
cd frontend
npm install
npm run dev      # Vite dev server (hot reload) → http://localhost:5173
npm run build    # production build → frontend/dist
npm run preview  # serve the production build locally
```

A `Makefile` provides shortcuts: `make install`, `make lint`, `make type`, `make test`, `make up`, `make down`.

---

## Usage

### API endpoints

The full contract is in **[docs/phase-1-api-contracts/openapi.yaml](docs/phase-1-api-contracts/openapi.yaml)**
(OpenAPI 3.1; also served live at `/docs`).

| Method & path | Auth | Purpose |
|---------------|------|---------|
| `POST /v1/route` | API key | Routing-only: return relevant sections + confidence + rationale (no generation) |
| `POST /v1/answer` | JWT bearer | Stream a cited answer over Server-Sent Events |
| `POST /v1/documents` | API key or JWT | Upload + ingest a PDF (parse → TOC → chunk → embed → index); idempotent on content hash |
| `GET /v1/documents` | API key or JWT | List ingested documents (paginated) |
| `GET /v1/documents/{id}` | API key or JWT | Document metadata (tenant-scoped, IDOR-guarded) |
| `GET /v1/documents/{id}/toc` | API key or JWT | Extracted table of contents |
| `DELETE /v1/documents/{id}` | API key or JWT | DPDP Act erasure cascade (right to erasure) |
| `GET /v1/documents/{id}/data` | API key or JWT | DPDP Act personal-data export (right to access) |
| `GET /health` | none | Liveness probe |
| `GET /ready` | none | Readiness probe (503 if Postgres/Qdrant unreachable) |
| `GET /metrics` | none | Product KPIs in Prometheus exposition format |

All errors use RFC 7807 `application/problem+json`. Example routing call:

```bash
curl -X POST http://localhost:8000/v1/route \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"document_id":"doc_abc123","query":"What are the warranty terms?"}'
```

### Running the tests

```bash
# Full Python suite (286 passed, 1 skipped)
python -m pytest -q

# With coverage (100% statement + branch)
python -m pytest --cov=backend --cov=ingestion --cov=router --cov=db --cov-report=term-missing

# Lint + type-check
python -m ruff check backend ingestion tests
python -m mypy backend ingestion router db

# Frontend (Vitest — 48 tests)
cd frontend && npm run test
```

### ROI calculator

```python
from backend.app.productization.roi_calculator import calculate_roi

report = calculate_roi(current_monthly_spend_usd=10_000, context_spend_fraction=0.7)
print(report.expected.monthly_savings_usd)   # expected-case monthly saving (USD)
print(report.annual_savings_expected_usd)    # projected annual saving (USD)
```

Reduces the context-driven slice of spend across conservative (40%) / expected (55%) / optimistic (70%) bands.

---

## Architecture

**Scope-before-search**: ingestion extracts a document's TOC and section hierarchy; the LangGraph Router Agent scores sections for a query and selects a retrieval scope; targeted retrieval queries Qdrant *filtered to the selected sections*; generation streams a cited answer.

```
PDF → parse + TOC (PyMuPDF / Unstructured / Azure DI)
    → section-aware chunking → embeddings → Qdrant + Postgres sections

Query → Router Agent (Claude 3 Haiku, scope + confidence + rationale)
      → targeted retrieval (Qdrant, filtered by section_id)
      → [optional rerank (Cohere Rerank-3)]
      → streamed, cited answer  ·  OR fallback to full-document RAG
```

### Directory layout

```
rag-refinement-system/
├── backend/          # FastAPI app (API, auth, rate limiting, adapters)
├── ingestion/        # Parse → TOC → chunk → embed → upsert pipeline
├── router/           # LangGraph router agent (scope + confidence + rationale)
├── db/               # SQLAlchemy async models + migrations
├── frontend/         # React + Vite + TailwindCSS personal tool SPA
├── deploy/           # Docker Compose (prod), Kubernetes manifests, runbook
├── tests/            # Pytest suite (286 tests, 100% coverage)
├── docs/             # Architecture, API contract, phase-gated delivery docs
├── uml/              # 13 Mermaid UML diagrams (auto-generated)
└── drawio/           # Draw.io diagrams (auto-generated)
```

### Tech stack

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI (async) + Pydantic v2 |
| Orchestration | LangGraph (Router → Retrieve → Generate) |
| PDF parsing | PyMuPDF + PyMuPDF4LLM, Unstructured.io, Azure Document Intelligence |
| Vector store | Qdrant (prod) / ChromaDB (dev) |
| Structure store | PostgreSQL 16 + SQLAlchemy async + asyncpg |
| Embeddings | OpenAI text-embedding-3-small + BGE-M3 fallback |
| Router LLM | Claude 3 Haiku (Anthropic) |
| Reranking | Cohere Rerank-3 (optional) |
| Frontend | React + TailwindCSS + Vite |
| Observability | LangSmith tracing, Prometheus metrics |
| CI/CD | GitHub Actions |
| Containers | Docker + Docker Compose + Kubernetes |

The ten architecture decisions behind these choices are in the HLD as ADR-1…ADR-10:
**[docs/phase-1-architecture/hld.md](docs/phase-1-architecture/hld.md)**

### Key documents

- **API contract:** [docs/phase-1-api-contracts/openapi.yaml](docs/phase-1-api-contracts/openapi.yaml)
- **High-Level Design:** [docs/phase-1-architecture/hld.md](docs/phase-1-architecture/hld.md)
- **Requirements (SRS):** [SRS.md](./SRS.md)
- **Product (PRD):** [PRD.md](./PRD.md)
- **UML diagrams:** [uml/](uml/) (13 Mermaid)
- **Draw.io diagrams:** [drawio/](drawio/)
- **Deploy runbook:** [docs/phase-G-deploy/deploy_runbook.md](docs/phase-G-deploy/deploy_runbook.md)
- **Observability:** [docs/phase-G-deploy/observability.md](docs/phase-G-deploy/observability.md)

---

## Contributing

Contributions are welcome — bug reports, feature requests, documentation improvements, and code.

Please read **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full guide, including:

- How to open issues and pull requests
- The quality gates CI enforces (100% coverage, 0 security findings)
- Commit message conventions
- Code style and docstring requirements

By contributing you agree that your contributions will be licensed under the Apache-2.0 License.

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md).
By participating you agree to uphold it. Report unacceptable behavior to [techdeveloper28@outlook.com](mailto:techdeveloper28@outlook.com).

---

## License

Copyright 2026 Piyush Makhija

Licensed under the **Apache License, Version 2.0**.
See the [LICENSE](LICENSE) file for the full text.
