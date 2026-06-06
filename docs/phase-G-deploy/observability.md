# Observability — RAG Refinement System (Phase G)

Two complementary layers: **LangSmith tracing** for the LLM/LangGraph paths, and
a lightweight **`/metrics` KPI surface** for the four product KPIs the PRD
measures the system against (PRD §21).

---

## 1. LangSmith tracing

`LANGSMITH_API_KEY` is already declared in `.env.example` and the production env
template. Wiring lives in `backend/app/productization/tracing.py` and is invoked
from the app factory (`create_app`). Behavior:

- When `LANGSMITH_API_KEY` is **set**, `LANGCHAIN_TRACING_V2=true` is exported and
  traces are filed under the `LANGSMITH_PROJECT` project
  (default `rag-refinement-system`; override per environment, e.g.
  `rag-refinement-prod`).
- When the key is **absent**, tracing is disabled and the app still starts — no
  hard dependency on LangSmith for liveness.
- The API key value is never logged or returned.

What to trace: the LangGraph Router -> Retrieve -> Generate state machine
(ADR-3). Each routing decision and each streamed answer becomes a trace, giving
per-request visibility into routing confidence, fallback branches, retrieval
scope, and generation latency. This is the same eval surface the QA contract
references for router accuracy / drift (PSI on routing-score distribution,
AGREED CONTRACT ai-model-testing-engineer <-> ai-engineer).

### Enabling in a deployment

```bash
# Injected by the secret manager at runtime (never committed):
export LANGSMITH_API_KEY=...        # from secret manager
export LANGSMITH_PROJECT=rag-refinement-prod
```

---

## 2. Product-KPI metrics (`/metrics`)

A dependency-free, in-process registry
(`backend/app/productization/metrics.py`) exposes the four PRD KPIs in
Prometheus text exposition format at **`GET /metrics`** (unauthenticated, like
`/health` and `/ready` — aggregate counters only, no document content or PII).

| PRD KPI (PRD §21) | Metric | Type | PRD target (MVP / 6-mo) |
|-------------------|--------|------|--------------------------|
| Token reduction % vs standard RAG | `rag_token_reduction_ratio` | gauge (avg) | > 40% / > 60% |
| Answer accuracy (structured docs) | `rag_answer_accuracy_ratio` | gauge (avg) | > 80% / > 90% |
| Routing latency | `rag_routing_latency_ms` | gauge (avg) | < 400 ms / < 200 ms |
| Fallback rate (router uncertainty) | `rag_fallback_rate` | gauge | < 20% / < 10% |

Supporting counters: `rag_routing_total`, `rag_fallback_total`.

### How values are produced

- `record_routing(latency_ms, fallback, token_reduction)` — call once per routing
  decision (`/v1/route`, and the routing leg of `/v1/answer`). Updates latency,
  fallback rate, and token-reduction average.
- `record_answer_accuracy(score)` — call from the offline/online eval loop when an
  answer is scored against the golden set (AGREED CONTRACT: eval set >= 20 docs
  spanning Scenarios A/B/C).

The registry is thread-safe and best-effort: recording never raises into a
request path. It is intentionally minimal — a full Prometheus client or
OpenTelemetry exporter can replace it without changing the endpoint contract.

### Scrape config (Prometheus example)

```yaml
scrape_configs:
  - job_name: rag-refinement-api
    metrics_path: /metrics
    static_configs:
      - targets: ["rag-api:80"]   # ClusterIP service / internal address
```

### Dashboards & alerts (recommended)

Build four panels (one per KPI) plus fallback-rate and latency alerts:

- **Alert** `routing_latency_high`: `rag_routing_latency_ms > 400` for 10m (NFR-001).
- **Alert** `fallback_rate_high`: `rag_fallback_rate > 0.20` for 15m (NFR-005).
- **Alert** `accuracy_regression`: `rag_answer_accuracy_ratio < 0.80` (NFR-003).
- Token-reduction trend panel for the ROI/GTM story (PRD §15, §21).

---

## 3. Health & readiness (already shipped)

- `GET /health` — liveness (200 when the process is up; NFR-009).
- `GET /ready` — readiness; returns 503 when Postgres or Qdrant is unreachable,
  so orchestrators hold traffic until dependencies are up.

These are the probes wired into the Dockerfile HEALTHCHECK, the prod compose
healthchecks, and the k8s liveness/readiness probes.
