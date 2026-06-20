# RAG Refinement System

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

### Project status — real current state (2026-06-06)

This is a **built, gated, deploy-authorized MVP**, not a concept:

| Area | Status |
|------|--------|
| Pre-implementation (PRD → architecture → API contract → design → SRS/UML → sprint plan → alignment, phases 0–8) | Complete |
| Backend implementation (Phase B: ingestion, LangGraph router, FastAPI API, auth, rate limiting) | Implemented |
| Frontend personal tool (React + Vite SPA, 48 vitest tests) | Implemented |
| Hallucination gate (Phase C) | NLI = 1.0, FactScore = 1.0 |
| QA pipeline (Phase D) | **100% statement + branch coverage**; 286 Python tests pass / 1 skipped; DRE = 1.0 |
| Security audit (Phase F) | **APPROVED** — 0 unresolved findings |
| Reliability gate (Phase E) | **RS = 1.0** — deploy authorized |
| Production deploy config (Phase G) | Production-ready compose + k8s manifests + runbook |
| **Live cloud deployment** | **Not yet performed** — requires the operator's cloud credentials and a secret manager (see the [deploy runbook](docs/phase-G-deploy/deploy_runbook.md)) |

Full product context: **[PRD.md](./PRD.md)** (v2.0). Requirements: **[SRS.md](./SRS.md)**.

> Note on metrics: token-reduction figures (40–70%) are the PRD-verified range
> for context-narrowing techniques. A specific "78% hallucination reduction"
> claim from an earlier draft could not be re-sourced and has been removed from
> headline claims (see PRD §15.3); accuracy/hallucination targets are tracked as
> goals, not as measured production figures.

---

## Prerequisites / Requirements

**To run the backend and tests**

- Python **3.11+**
- (For the full stack) **Docker** + Docker Compose
- PostgreSQL 16 and Qdrant — provided by `docker-compose.yml` for local dev
  (ChromaDB is the documented dev alternative per ADR-2)

**To run the personal-tool frontend**

- Node.js **20+** and npm

**Provider credentials (optional for local dev; required for real answers)**

Copy `.env.example` → `.env` and fill in values. The process starts without
credentials (probes report which dependencies are configured), but routing and
generation need real keys:

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Embeddings (text-embedding-3-small, ADR-6) |
| `ANTHROPIC_API_KEY` | Router LLM (Claude 3 Haiku) + generation (ADR-1) |
| `COHERE_API_KEY` | Optional reranking (Cohere Rerank-3, ADR-8) |
| `LANGSMITH_API_KEY` | Optional tracing/observability |
| `DATABASE_URL` | PostgreSQL DSN (structure store, ADR-10) |
| `QDRANT_URL` | Qdrant base URL (vector store, ADR-2) |
| `JWT_SECRET`, `API_KEY_SALT` | Auth (OAuth2/JWT + API keys, ADR-7) |

Secrets are injected from the environment (12-factor). **Never commit a
populated `.env`** — it is gitignored.

---

## Installation / Setup

### Option A — Full stack with Docker Compose (recommended)

```bash
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

You can bring up just the data stores with `docker compose up -d postgres qdrant`
and point `DATABASE_URL` / `QDRANT_URL` at them.

### Frontend (personal tool)

```bash
cd frontend
npm install
npm run dev      # Vite dev server (hot reload)
npm run build    # production build → frontend/dist
npm run preview  # serve the production build locally
```

A `Makefile` provides shortcuts: `make install`, `make lint`, `make type`,
`make test`, `make up`, `make down`.

---

## Usage

### API endpoints

The full contract is **[docs/phase-1-api-contracts/openapi.yaml](docs/phase-1-api-contracts/openapi.yaml)**
(OpenAPI 3.1; also served live at `/docs`). Key operations:

| Method & path | Auth | Purpose |
|---------------|------|---------|
| `POST /v1/route` | API key | Routing-only: return relevant sections + confidence + rationale (no generation) |
| `POST /v1/answer` | JWT bearer | Stream a cited answer over Server-Sent Events (personal tool) |
| `POST /v1/documents` | API key or JWT | Upload + ingest a PDF (parse → TOC → chunk → embed → index); idempotent on content hash |
| `GET /v1/documents` | API key or JWT | List ingested documents (paginated) |
| `GET /v1/documents/{id}` | API key or JWT | Document metadata (tenant-scoped, IDOR-guarded) |
| `GET /v1/documents/{id}/toc` | API key or JWT | Extracted (or pseudo) table of contents |
| `DELETE /v1/documents/{id}` | API key or JWT | DPDP Act erasure cascade (right to erasure) |
| `GET /v1/documents/{id}/data` | API key or JWT | DPDP Act personal-data export (right to access) |
| `GET /health` | none | Liveness probe |
| `GET /ready` | none | Readiness probe (503 if Postgres/Qdrant unreachable) |
| `GET /metrics` | none | Product KPIs in Prometheus exposition format |

All errors use RFC 7807 `application/problem+json`. Example routing call:

```bash
curl -X POST http://localhost:8000/v1/route \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"document_id":"doc_abc123","query":"What are the warranty terms?"}'
```

### Running the tests

```bash
# Python: full suite (expect 286 passed, 1 skipped — the skip is the opt-in
# live-Postgres migration test).
python -m pytest -q

# Python with coverage (expect 100% statement + branch coverage).
python -m pytest --cov=backend --cov=ingestion --cov=router --cov=db --cov-report=term-missing

# Lint (expect: All checks passed!) and type-check.
python -m ruff check .
python -m mypy backend ingestion

# Frontend (Vitest — 48 tests).
cd frontend && npm run test
```

### ROI calculator (GTM asset)

A tested utility projects monthly LLM-spend savings from the documented
token-reduction range
(`backend/app/productization/roi_calculator.py`):

```python
from backend.app.productization.roi_calculator import calculate_roi

report = calculate_roi(current_monthly_spend_usd=10_000, context_spend_fraction=0.7)
print(report.expected.monthly_savings_usd)   # expected-case monthly saving (USD)
print(report.annual_savings_expected_usd)    # projected annual saving (USD)
```

It reduces only the context-driven slice of spend across a conservative (40%) /
expected (55%) / optimistic (70%) band — projections for modeling, not billing.

---

## Architecture

**Scope-before-search**: ingestion extracts a document's TOC and section
hierarchy; the LangGraph Router Agent scores sections for a query and selects a
scope; targeted retrieval queries Qdrant *filtered to the selected sections*;
generation streams a cited answer. PostgreSQL holds the document/section
structure (the router's join key is `section_id`); Qdrant holds chunk vectors.

```
PDF → parse + TOC (PyMuPDF/Unstructured/Azure DI)
    → section-aware chunking → embeddings → Qdrant + Postgres sections
Query → Router Agent (Claude 3 Haiku, scope + confidence + rationale)
      → targeted retrieval (Qdrant, filtered by section_id) → [optional rerank]
      → streamed, cited answer  ·  or fallback to full-document RAG
```

- **High-Level Design:** [docs/phase-1-architecture/hld.md](docs/phase-1-architecture/hld.md)
  (reconciled v3: [docs/phase-4-reconciliation/hld_v3.md](docs/phase-4-reconciliation/hld_v3.md))
- **API contract:** [docs/phase-1-api-contracts/openapi.yaml](docs/phase-1-api-contracts/openapi.yaml)
- **Requirements (SRS):** [SRS.md](./SRS.md) · **Product (PRD):** [PRD.md](./PRD.md)
- **UML diagrams:** [uml/](uml/) (13 Mermaid) · **Draw.io:** [drawio/](drawio/)
- **Deploy config + runbook:** [deploy/](deploy/) · [docs/phase-G-deploy/deploy_runbook.md](docs/phase-G-deploy/deploy_runbook.md)
- **Observability:** [docs/phase-G-deploy/observability.md](docs/phase-G-deploy/observability.md)

### Tech stack (as built)

Python 3.11 / FastAPI (async) · LangGraph (Router→Retrieve→Generate) · PyMuPDF +
PyMuPDF4LLM (parse/TOC) with Unstructured.io / Azure Document Intelligence
fallbacks · Qdrant (prod) / ChromaDB (dev) · PostgreSQL · OpenAI
text-embedding-3-small (+ BGE-M3 multilingual fallback) · Claude 3 Haiku (router)
· Cohere Rerank-3 (optional) · React + TailwindCSS + Vite (personal tool) ·
LangSmith (observability) · Docker + GitHub Actions CI. The ten architecture
decisions behind these choices are recorded as ADR-1…ADR-10 in the HLD.

### Deployment

Production-shaped config lives in [`deploy/`](deploy/): a hardened production
compose (`docker-compose.prod.yml`), a static-SPA build image
(`frontend.Dockerfile`), Kubernetes manifests (`k8s/`), and a TLS-terminating
reverse-proxy example. TLS is enforced at the proxy/Ingress; data stores are
internal-only with auth; images run non-root; secrets are injected at runtime
from a secret manager (never baked). **A live cloud deploy has not been
performed** — it requires the operator's cloud credentials; follow the
[deploy runbook](docs/phase-G-deploy/deploy_runbook.md).

---

## Contributing

This project follows a phase-gated SDLC with hard quality gates: 100% test
coverage + DRE = 1.0 (QA), 0 unresolved security findings, and RS = 1.0
(reliability) before deploy. To contribute:

1. Create a feature branch off `main`.
2. Keep the gates green: `python -m pytest -q`, `python -m ruff check .`,
   `python -m mypy backend ingestion`, and `cd frontend && npm run test`.
3. Public functions/classes/modules carry docstrings; avoid inline narration
   comments. New code adds tests (the suite holds at 100% coverage).
4. CI runs lint → typecheck → test → security (Bandit SAST, pip-audit SCA,
   detect-secrets, frontend `npm audit`) and **hard-blocks** on any finding or
   hardcoded secret.
5. Conventional Commit messages (`feat:`, `fix:`, `docs:`, …); one logical
   change per commit.

---

## License

The API contract declares **Apache-2.0** (`openapi.yaml` `info.license`), while
the Python package metadata currently marks the distribution **Proprietary**
(`pyproject.toml`). These differ; treat the licensing as **not yet finalized**
and confirm with the project owner before redistribution. A single
`LICENSE` file should be added to settle this.
