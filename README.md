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

Standard RAG searches the whole document for every query, drowning the model in noise. This system reads the document's structure (Table of Contents) first, routes the query to the sections that actually matter, and retrieves only from there — less noise, fewer tokens, more accurate and *explainable* answers.

```
Standard RAG:    Query → search 200 pages → noise → hallucination
RAG Refinement:  Query → TOC Router → 7 relevant pages → cited, explainable answer
```

---

## Table of Contents

- [What Is This?](#what-is-this)
- [Project Status](#project-status)
- [Prerequisites / Requirements](#prerequisites--requirements)
- [Installation / Setup](#installation--setup)
  - [Option A — Full Stack with Docker Compose](#option-a--full-stack-with-docker-compose-recommended)
  - [Option B — Backend Only (Local Python)](#option-b--backend-only-local-python)
  - [Frontend (Personal Tool SPA)](#frontend-personal-tool-spa)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Personal Tool (SPA)](#personal-tool-spa)
  - [Enterprise Routing API](#enterprise-routing-api)
  - [All API Endpoints](#all-api-endpoints)
  - [Running Tests](#running-tests)
  - [ROI Calculator](#roi-calculator)
- [Using with Different RAG Databases](#using-with-different-rag-databases)
  - [How the Vector Store Abstraction Works](#how-the-vector-store-abstraction-works)
  - [Default: Qdrant (Production)](#default-qdrant-production)
  - [ChromaDB (Development / Local)](#chromadb-development--local)
  - [Pinecone](#pinecone)
  - [Weaviate](#weaviate)
  - [PGVector (PostgreSQL)](#pgvector-postgresql)
  - [Milvus / Zilliz](#milvus--zilliz)
  - [Drop-in Front of Your Existing RAG Stack (No DB Change)](#drop-in-front-of-your-existing-rag-stack-no-db-change)
- [Architecture](#architecture)
  - [How It Works](#how-it-works)
  - [Directory Layout](#directory-layout)
  - [Tech Stack](#tech-stack)
  - [Key Documents](#key-documents)
- [Contributing](#contributing)
- [Code of Conduct](#code-of-conduct)
- [License](#license)

---

## What Is This?

The system ships as **two product surfaces over one API contract**:

1. **Personal Tool (SPA)** — a React + Vite single-page app: upload a PDF, ask questions, and get streamed answers that cite exact sections, with a confidence meter and a "why did you look here?" explainability panel.

2. **Enterprise Refinement API** — `POST /v1/route` is **routing-only**: it returns the optimal retrieval scope (`relevant_sections`, `page_ranges`, per-section `confidence`, `fallback`, `routing_time_ms`, and an interpretable rationale) and **never calls the generation LLM**. Drop it in front of an existing RAG stack — no migration required.

The two differentiators are:

- **Interpretable routing** (mandatory — you always see why the router scoped where it did)
- **Graceful degradation** — when no section clears the confidence threshold, the router sets `fallback: true` so the caller falls back to full-document retrieval automatically

Full product context: **[PRD.md](./PRD.md)** · Requirements: **[SRS.md](./SRS.md)**

---

## Project Status

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

---

## Prerequisites / Requirements

**Backend and tests**

- Python **3.11+**
- **Docker** + Docker Compose (for the full stack)
- PostgreSQL 16 and Qdrant — provided by `docker-compose.yml` for local dev

**Frontend (personal tool)**

- Node.js **20+** and npm

**Provider credentials** (optional for local dev; required for real answers)

See [Configuration](#configuration) for details on environment variables.

---

## Installation / Setup

### Option A — Full Stack with Docker Compose (Recommended)

```bash
git clone https://github.com/techdeveloper-org/rag-refinement-system.git
cd rag-refinement-system
cp .env.example .env          # fill in provider keys for real answers
docker compose up -d --build  # starts postgres + qdrant + api on :8000
```

The API is then at `http://localhost:8000` (OpenAPI docs at `/docs`).

### Option B — Backend Only (Local Python)

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

### Frontend (Personal Tool SPA)

```bash
cd frontend
npm install
npm run dev      # Vite dev server (hot reload) → http://localhost:5173
npm run build    # production build → frontend/dist
npm run preview  # serve the production build locally
```

A `Makefile` provides shortcuts: `make install`, `make lint`, `make type`, `make test`, `make up`, `make down`.

---

## Configuration

Copy `.env.example` → `.env` and fill in values:

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes (for embeddings) | Embeddings via `text-embedding-3-small` (1536-dim) |
| `ANTHROPIC_API_KEY` | Yes (for routing + answers) | Router LLM (Claude 3 Haiku) + generation |
| `DATABASE_URL` | Yes | Async PostgreSQL DSN (`postgresql+asyncpg://...`) |
| `DATABASE_SYNC_URL` | No | Sync DSN for ingestion worker (defaults to `DATABASE_URL`) |
| `QDRANT_URL` | Yes | Qdrant base URL (e.g. `http://localhost:6333`) |
| `JWT_SECRET` | Yes (for JWT auth) | HMAC-SHA JWT signing secret |
| `API_KEY_SALT` | Yes (for API keys) | Salt for API key hashing |
| `COHERE_API_KEY` | No | Optional reranking via Cohere Rerank-3 |
| `LANGSMITH_API_KEY` | No | Optional LangSmith tracing/observability |
| `CORS_ALLOWED_ORIGINS` | No | Restrict CORS in production (default `["*"]`) |
| `RATE_LIMIT_DEFAULT_PER_MINUTE` | No | Default rate limit (default: 60) |
| `MAX_UPLOAD_BYTES` | No | Max PDF upload size (default: 50 MiB) |

Secrets are injected from the environment (12-factor). **Never commit a populated `.env`** — it is gitignored.

---

## Usage

### Personal Tool (SPA)

1. Start the full stack (`docker compose up -d --build`)
2. Open `http://localhost:5173` in your browser
3. Upload a PDF using the upload panel
4. Ask any question — the answer streams back with section citations and a confidence meter
5. The explainability panel shows *which sections* the router selected and *why*

### Enterprise Routing API

Call `POST /v1/route` to get a routing scope for any query without triggering generation. This endpoint is designed to be inserted in front of your existing RAG pipeline:

```bash
curl -X POST http://localhost:8000/v1/route \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc_abc123",
    "query": "What are the warranty terms?"
  }'
```

**Response:**
```json
{
  "relevant_sections": [
    {"section_id": "sec_a1b2", "title": "Warranty and Returns", "confidence": 0.94},
    {"section_id": "sec_c3d4", "title": "Product Liability", "confidence": 0.71}
  ],
  "page_ranges": [[42, 47], [88, 90]],
  "fallback": false,
  "routing_time_ms": 312,
  "rationale": "Query targets warranty clauses; sections 5.2 and 7.1 contain the relevant terms."
}
```

Your retriever then queries *only those page ranges* in Qdrant (or whichever vector DB you use) — see [Using with Different RAG Databases](#using-with-different-rag-databases).

### All API Endpoints

The full contract is in **[docs/phase-1-api-contracts/openapi.yaml](docs/phase-1-api-contracts/openapi.yaml)** (OpenAPI 3.1; also served live at `/docs`).

| Method & Path | Auth | Purpose |
|---------------|------|---------|
| `POST /v1/route` | API key | **Routing-only**: return relevant sections + confidence + rationale (no generation) |
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

All errors use RFC 7807 `application/problem+json`.

### Running Tests

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

### ROI Calculator

```python
from backend.app.productization.roi_calculator import calculate_roi

report = calculate_roi(current_monthly_spend_usd=10_000, context_spend_fraction=0.7)
print(report.expected.monthly_savings_usd)   # expected-case monthly saving (USD)
print(report.annual_savings_expected_usd)    # projected annual saving (USD)
```

Reduces the context-driven slice of spend across conservative (40%) / expected (55%) / optimistic (70%) bands.

---

## Using with Different RAG Databases

### How the Vector Store Abstraction Works

The ingestion pipeline and the retrieval layer talk to the vector database through a clean **Protocol interface** (`ingestion/pipeline.py::VectorStore`). Any object that implements `upsert_points(points)` and returns the count is a valid vector store — you never change the pipeline or API code, only the adapter.

```python
# ingestion/pipeline.py — the Protocol any vector DB must satisfy
class VectorStore(Protocol):
    def upsert_points(self, points: list[dict]) -> int:
        """Upsert chunk points; return count upserted.

        Each point is: {"id": str, "vector": list[float], "payload": dict}
        Payload shape: {chunk_id, section_id, doc_id, tenant_id, page}
        """
        ...
```

The embedded vectors are always **1536-dimensional** (OpenAI `text-embedding-3-small`, with BGE-M3 as local fallback — both produce 1536-dim output). Your collection/index must be created with `dim=1536`.

---

### Default: Qdrant (Production)

Out of the box the system uses **Qdrant** as the vector store. No extra code is needed.

**.env**
```env
QDRANT_URL=http://localhost:6333   # or your cloud Qdrant endpoint
```

**docker-compose.yml** already includes a Qdrant service. For Qdrant Cloud, set `QDRANT_URL` to your cluster URL and add `QDRANT_API_KEY`:

```env
QDRANT_URL=https://<your-cluster>.qdrant.io
QDRANT_API_KEY=<your-key>
```

Then update `db/qdrant_bootstrap.py` to pass `api_key` when building the client:

```python
from qdrant_client import QdrantClient
import os

def get_client() -> QdrantClient:
    return QdrantClient(
        url=os.environ["QDRANT_URL"],
        api_key=os.environ.get("QDRANT_API_KEY"),
    )
```

---

### ChromaDB (Development / Local)

ChromaDB is ideal for local development — no Docker service needed.

**Install:**
```bash
pip install chromadb
```

**Write a ChromaDB adapter** (`backend/app/adapters/chroma_store.py`):

```python
import chromadb
from typing import Any


class ChromaVectorStore:
    """ChromaDB adapter satisfying the VectorStore Protocol."""

    def __init__(self, collection_name: str = "rag_chunks", persist_dir: str = ".chroma"):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Upsert chunk points into ChromaDB."""
        if not points:
            return 0
        self._collection.upsert(
            ids=[str(p["id"]) for p in points],
            embeddings=[p["vector"] for p in points],
            metadatas=[p["payload"] for p in points],
        )
        return len(points)
```

**Wire it in** (`backend/app/adapters/ingestor.py`) by replacing `QdrantVectorStore` with `ChromaVectorStore` in the composition root when `VECTOR_STORE=chroma` is set.

**Filtering by section during retrieval** — pass Chroma's `where` filter:

```python
results = collection.query(
    query_embeddings=[query_vector],
    n_results=10,
    where={"section_id": {"$in": relevant_section_ids}},  # from /v1/route response
)
```

---

### Pinecone

**Install:**
```bash
pip install pinecone-client
```

**Adapter** (`backend/app/adapters/pinecone_store.py`):

```python
import os
from pinecone import Pinecone
from typing import Any


class PineconeVectorStore:
    """Pinecone adapter satisfying the VectorStore Protocol."""

    def __init__(self, index_name: str = "rag-chunks"):
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        self._index = pc.Index(index_name)

    def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Upsert chunk points into Pinecone."""
        if not points:
            return 0
        vectors = [
            {
                "id": str(p["id"]),
                "values": p["vector"],
                "metadata": p["payload"],
            }
            for p in points
        ]
        self._index.upsert(vectors=vectors)
        return len(vectors)
```

**Create the index** with `dimension=1536` and `metric="cosine"` before first use.

**Filtering during retrieval** — use Pinecone's metadata filter:

```python
results = index.query(
    vector=query_vector,
    top_k=10,
    filter={"section_id": {"$in": relevant_section_ids}},  # from /v1/route
    include_metadata=True,
)
```

**.env addition:**
```env
PINECONE_API_KEY=<your-key>
```

---

### Weaviate

**Install:**
```bash
pip install weaviate-client
```

**Adapter** (`backend/app/adapters/weaviate_store.py`):

```python
import os
import weaviate
from typing import Any


class WeaviateVectorStore:
    """Weaviate adapter satisfying the VectorStore Protocol."""

    def __init__(self, class_name: str = "RagChunk"):
        self._client = weaviate.connect_to_local(
            host=os.environ.get("WEAVIATE_HOST", "localhost"),
            port=int(os.environ.get("WEAVIATE_PORT", "8080")),
        )
        self._class_name = class_name

    def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Upsert chunk points into Weaviate."""
        if not points:
            return 0
        collection = self._client.collections.get(self._class_name)
        with collection.batch.dynamic() as batch:
            for p in points:
                batch.add_object(
                    properties=p["payload"],
                    vector=p["vector"],
                    uuid=str(p["id"]),
                )
        return len(points)
```

**Filtering during retrieval:**

```python
from weaviate.classes.query import Filter

results = collection.query.near_vector(
    near_vector=query_vector,
    limit=10,
    filters=Filter.by_property("section_id").contains_any(relevant_section_ids),
)
```

**.env addition:**
```env
WEAVIATE_HOST=localhost
WEAVIATE_PORT=8080
```

---

### PGVector (PostgreSQL)

Keep everything in one database — useful if you already run PostgreSQL.

**Install:**
```bash
pip install pgvector sqlalchemy asyncpg
```

**Migration** — add the vector column to your schema:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE chunks (
    id          UUID PRIMARY KEY,
    embedding   vector(1536),
    chunk_id    TEXT,
    section_id  TEXT,
    doc_id      TEXT,
    tenant_id   TEXT,
    page        INTEGER
);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON chunks (section_id);
```

**Adapter** (`backend/app/adapters/pgvector_store.py`):

```python
from sqlalchemy import create_engine, text
from typing import Any


class PGVectorStore:
    """PGVector adapter satisfying the VectorStore Protocol."""

    def __init__(self, database_url: str):
        self._engine = create_engine(database_url)

    def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Upsert chunk points into PGVector."""
        if not points:
            return 0
        rows = [
            {
                "id": p["id"],
                "embedding": p["vector"],
                **p["payload"],
            }
            for p in points
        ]
        with self._engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO chunks (id, embedding, chunk_id, section_id, doc_id, tenant_id, page)
                    VALUES (:id, :embedding, :chunk_id, :section_id, :doc_id, :tenant_id, :page)
                    ON CONFLICT (id) DO UPDATE SET embedding = EXCLUDED.embedding
                """),
                rows,
            )
        return len(rows)
```

**Filtering during retrieval:**

```python
results = conn.execute(text("""
    SELECT chunk_id, section_id, page,
           1 - (embedding <=> :query_vec) AS score
    FROM chunks
    WHERE section_id = ANY(:section_ids)
      AND tenant_id = :tenant_id
    ORDER BY embedding <=> :query_vec
    LIMIT 10
"""), {"query_vec": query_vector, "section_ids": relevant_section_ids, "tenant_id": tenant_id})
```

---

### Milvus / Zilliz

**Install:**
```bash
pip install pymilvus
```

**Adapter** (`backend/app/adapters/milvus_store.py`):

```python
import os
from pymilvus import MilvusClient
from typing import Any


class MilvusVectorStore:
    """Milvus / Zilliz adapter satisfying the VectorStore Protocol."""

    def __init__(self, collection_name: str = "rag_chunks"):
        self._client = MilvusClient(
            uri=os.environ.get("MILVUS_URI", "http://localhost:19530"),
            token=os.environ.get("MILVUS_TOKEN", ""),
        )
        self._collection = collection_name

    def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Upsert chunk points into Milvus."""
        if not points:
            return 0
        data = [
            {"id": p["id"], "vector": p["vector"], **p["payload"]}
            for p in points
        ]
        self._client.upsert(collection_name=self._collection, data=data)
        return len(data)
```

**Create the collection** with `dim=1536` and a `section_id` scalar field for filtering before first use.

**.env addition:**
```env
MILVUS_URI=http://localhost:19530
MILVUS_TOKEN=          # leave empty for open Milvus; set for Zilliz Cloud
```

---

### Drop-in Front of Your Existing RAG Stack (No DB Change)

If you already have a working RAG pipeline (LangChain + Pinecone, LlamaIndex + Weaviate, custom Chroma stack, etc.), you can use **only the routing endpoint** without touching your vector database at all.

**How it works:**

```
Your app:
  1. Ingest documents → your existing vector DB (no change)
  2. At query time → call POST /v1/route first
  3. Use the returned section_ids / page_ranges to filter your own retrieval
  4. Pass filtered chunks to your LLM as usual
```

**Step-by-step integration:**

1. **Ingest documents into RAG Refinement System** (for TOC extraction only):
   ```bash
   curl -X POST http://localhost:8000/v1/documents \
     -H "X-API-Key: $API_KEY" \
     -F "file=@my_document.pdf" \
     -F "title=My Document"
   # Save the returned doc_id
   ```

2. **At query time, get the routing scope:**
   ```python
   import httpx

   response = httpx.post(
       "http://localhost:8000/v1/route",
       headers={"X-API-Key": api_key},
       json={"document_id": doc_id, "query": user_query},
   )
   route = response.json()

   if route["fallback"]:
       # No confident section found — use full-document retrieval in your stack
       chunks = your_retriever.retrieve(user_query, filter=None)
   else:
       # Filter your own vector DB to these page ranges
       page_ranges = route["page_ranges"]  # e.g. [[12, 18], [42, 47]]
       chunks = your_retriever.retrieve(user_query, page_ranges=page_ranges)
   ```

3. **Pass the filtered chunks to your generation layer** as normal — no other changes.

The routing call adds ~300ms (LLM call to Claude 3 Haiku) but saves 40–70% of the retrieval and generation context, yielding a net latency reduction on any question that maps to a clear document section.

---

## Architecture

### How It Works

**Scope-before-search**: ingestion extracts a document's TOC and section hierarchy; the LangGraph Router Agent scores sections for a query and selects a retrieval scope; targeted retrieval queries the vector store filtered to the selected sections; generation streams a cited answer.

```
PDF → parse + TOC (PyMuPDF / Unstructured / Azure DI)
    → section-aware chunking → embeddings → Vector Store + Postgres sections

Query → Router Agent (Claude 3 Haiku → scope + confidence + rationale)
      → targeted retrieval (Vector Store, filtered by section_id)
      → [optional rerank (Cohere Rerank-3)]
      → streamed, cited answer  ·  OR fallback to full-document RAG
```

**Three ingestion scenarios:**

| Scenario | When | Result |
|----------|------|--------|
| A — Structured PDF | TOC found natively | Full section-aware indexing |
| B — Headers only | No TOC, but headings detected | LLM-refined TOC from headers |
| C — Unstructured PDF | No detectable structure | `fallback_only=true`; full-document RAG path |

### Directory Layout

```
rag-refinement-system/
├── backend/          # FastAPI app (API, auth, rate limiting, adapters)
│   └── app/
│       ├── adapters/ # Vector store + document store adapters (swap here for new DB)
│       ├── api/      # Route handlers, schemas, SSE answer streaming
│       ├── security/ # JWT auth + API key validation + rate limiting
│       └── settings.py
├── ingestion/        # Parse → TOC → chunk → embed → upsert pipeline
│   ├── pipeline.py   # VectorStore + SectionStore Protocols (the adapter contracts)
│   ├── embedder.py   # OpenAI primary + BGE-M3 fallback embedders
│   └── chunker.py    # Section-bounded chunking
├── router/           # LangGraph router agent (scope + confidence + rationale)
│   └── graph.py      # Router graph with TOC cache
├── db/               # SQLAlchemy async models + Qdrant bootstrap
├── frontend/         # React + Vite + TailwindCSS personal tool SPA
├── deploy/           # Docker Compose (prod), Kubernetes manifests, runbook
├── tests/            # Pytest suite (286 tests, 100% coverage)
├── docs/             # Architecture, API contract, phase-gated delivery docs
├── uml/              # 13 Mermaid UML diagrams (auto-generated)
└── drawio/           # Draw.io diagrams (auto-generated)
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| API framework | FastAPI (async) + Pydantic v2 |
| Orchestration | LangGraph (Router → Retrieve → Generate) |
| PDF parsing | PyMuPDF + PyMuPDF4LLM, Unstructured.io, Azure Document Intelligence |
| Vector store | **Qdrant** (prod default) / **ChromaDB** (dev) / pluggable via Protocol |
| Structure store | PostgreSQL 16 + SQLAlchemy async + asyncpg |
| Embeddings | OpenAI `text-embedding-3-small` (1536-dim) + BGE-M3 local fallback |
| Router LLM | Claude 3 Haiku (Anthropic) |
| Reranking | Cohere Rerank-3 (optional) |
| Frontend | React + TailwindCSS + Vite |
| Observability | LangSmith tracing, Prometheus metrics |
| CI/CD | GitHub Actions |
| Containers | Docker + Docker Compose + Kubernetes |

The ten architecture decisions behind these choices are documented as ADR-1…ADR-10:
**[docs/phase-1-architecture/hld.md](docs/phase-1-architecture/hld.md)**

### Key Documents

| Document | Purpose |
|----------|---------|
| [docs/phase-1-api-contracts/openapi.yaml](docs/phase-1-api-contracts/openapi.yaml) | Full OpenAPI 3.1 contract |
| [docs/phase-1-architecture/hld.md](docs/phase-1-architecture/hld.md) | High-Level Design + ADRs |
| [SRS.md](./SRS.md) | Software Requirements Specification |
| [PRD.md](./PRD.md) | Product Requirements Document |
| [uml/](uml/) | 13 Mermaid UML diagrams |
| [drawio/](drawio/) | Draw.io diagrams |
| [docs/phase-G-deploy/deploy_runbook.md](docs/phase-G-deploy/deploy_runbook.md) | Production deployment runbook |
| [docs/phase-G-deploy/observability.md](docs/phase-G-deploy/observability.md) | Prometheus + LangSmith observability |
| [docs/phase-F-security/security_audit_report.md](docs/phase-F-security/security_audit_report.md) | Security audit report |

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
