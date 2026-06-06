# Deploy Runbook — RAG Refinement System (Phase G)

> Gate satisfied: **RS = 1.0** (reliability), **security APPROVED** (0 unresolved),
> QA coverage 100% (286 passed / 1 skipped including Phase-G additions). Deploy is
> authorized. **A live cloud deploy requires the operator's cloud credentials and a
> secret manager** — the steps below are the production procedure; the commands that
> touch a real cloud are marked `[requires user cloud creds]`.

This runbook covers both supported targets:

- **Compose target** — `deploy/docker-compose.prod.yml` (single host / VM).
- **Kubernetes target** — `deploy/k8s/*` (managed cluster).

---

## 0. Pre-flight (local, no cloud creds)

```bash
# From the repo root. Confirm the gates locally before shipping.
python -m pytest -q                 # expect: 286 passed, 1 skipped
python -m ruff check .              # expect: All checks passed!
docker build -t rag-refinement-api:local .   # backend image builds
```

The single skipped test is the opt-in live-Postgres migration test (needs a real
`DATABASE_URL`); it does not affect application coverage.

---

## 1. Build the images

```bash
VERSION=1.0.0
REGISTRY=registry.example.com           # your container registry

# Backend API (non-root, multi-stage; see ../../Dockerfile)
docker build -t $REGISTRY/rag-refinement-api:$VERSION .

# Static SPA (Vite build -> non-root nginx; see ../../deploy/frontend.Dockerfile)
docker build \
  -f deploy/frontend.Dockerfile \
  --build-arg VITE_API_BASE_URL=https://app.example.com/api \
  -t $REGISTRY/rag-refinement-frontend:$VERSION .
```

Optional but recommended: scan the image before pushing.

```bash
trivy image $REGISTRY/rag-refinement-api:$VERSION
```

---

## 2. Push the images  `[requires user cloud creds]`

```bash
docker login $REGISTRY                  # uses operator credentials
docker push $REGISTRY/rag-refinement-api:$VERSION
docker push $REGISTRY/rag-refinement-frontend:$VERSION
```

---

## 3. Provision data stores (production Postgres + Qdrant)

Two options:

**A. Managed services (recommended).** Provision a managed PostgreSQL 16
instance and a managed/dedicated Qdrant. Capture: Postgres user/password/db and
the Qdrant URL + API key. Restrict network access to the API's subnet/security
group only (no public ingress to the data stores).

**B. Self-hosted via the prod compose.** `deploy/docker-compose.prod.yml`
already runs auth'd Postgres and an API-key-protected Qdrant on an internal-only
network with no published ports.

Run the schema migration against the production Postgres:

```bash
# migrations/001_documents_sections.sql defines documents + sections (ADR-10).
psql "$DATABASE_URL" -f migrations/001_documents_sections.sql
```

---

## 4. Set secrets (secret manager — never a committed file)

Populate these in your secret manager (AWS Secrets Manager / GCP Secret Manager /
Vault / Doppler). Template of required keys: `deploy/.env.prod.example` (compose)
or `deploy/k8s/secret.example.yaml` (k8s). **Required:** `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `POSTGRES_USER/PASSWORD/DB`, `QDRANT_API_KEY`, `JWT_SECRET`,
`API_KEY_SALT`. **Optional:** `COHERE_API_KEY`, `LANGSMITH_API_KEY`.

```bash
# Kubernetes (generated from a runtime-only env file that never enters Git):
kubectl create secret generic rag-secrets --from-env-file=./rag.runtime.env
rm -f ./rag.runtime.env
```

The prod compose uses `${VAR:?...}`, so a missing/empty required secret **aborts
the deploy** instead of starting an insecure stack.

---

## 5. Deploy  `[requires user cloud creds]`

### Compose target

```bash
export $(grep -v '^#' /run/secrets/rag.env | xargs)   # injected by secret manager
docker compose -f deploy/docker-compose.prod.yml up -d
```

### Kubernetes target

```bash
kubectl apply -f deploy/k8s/api-deployment.yaml
kubectl apply -f deploy/k8s/ingress.yaml
# (frontend Deployment/Service follow the same pattern as api-deployment.yaml)
kubectl rollout status deployment/rag-api
```

TLS terminates at the reverse proxy (Caddy example:
`deploy/reverse-proxy/Caddyfile.example`) or the Ingress
(`deploy/k8s/ingress.yaml`, cert-manager). The data stores stay internal.

---

## 6. Healthcheck (verify green before serving traffic)

```bash
# Liveness — 200 once the process is up.
curl -fsS https://app.example.com/api/health

# Readiness — 200 only when Postgres AND Qdrant are reachable; 503 otherwise.
curl -fsS https://app.example.com/api/ready

# KPI metrics surface (Prometheus exposition).
curl -fsS https://app.example.com/api/metrics | head
```

Kubernetes: `kubectl get pods -l app=rag-api` should show `Running` + `READY 1/1`
(readiness probe hits `/ready`). Confirm LangSmith traces appear under the
configured project if `LANGSMITH_API_KEY` is set (see `observability.md`).

---

## 7. Smoke test (post-deploy)

```bash
# Enterprise routing-only path (API key).
curl -fsS -X POST https://app.example.com/api/v1/route \
  -H "X-API-Key: $TEST_API_KEY" -H "Content-Type: application/json" \
  -d '{"document_id":"doc_smoke01","query":"warranty terms?"}'

# Ingest a sample PDF (multipart). Expect 201 (or 200 if deduplicated).
curl -fsS -X POST https://app.example.com/api/v1/documents \
  -H "X-API-Key: $TEST_API_KEY" -F "file=@sample.pdf;type=application/pdf"
```

---

## 8. Rollback

### Kubernetes

```bash
kubectl rollout undo deployment/rag-api        # revert to previous ReplicaSet
kubectl rollout status deployment/rag-api
```

### Compose

```bash
# Re-pin API_IMAGE/FRONTEND_IMAGE to the previous known-good tag, then:
docker compose -f deploy/docker-compose.prod.yml up -d
```

**Data-store rollback:** schema migrations ship with a paired `.down.sql`
(`migrations/001_documents_sections.down.sql`). Apply the down migration only if
a release introduced an incompatible schema change; vector data in Qdrant is
not migration-managed and should be restored from a snapshot if needed.

**Rollback trigger criteria:** `/ready` flapping to 503, error rate spike on
`/v1/route` or `/v1/answer`, `rag_fallback_rate` jumping above 0.20 sustained, or
a failed smoke test.

---

## 9. Live-deploy honesty note

This environment has **no cloud credentials**, so steps 2, 5, and any managed-
service provisioning (step 3A) cannot be executed here. Everything that can be
verified offline has been: the backend image builds, the test suite is green
(286/1), ruff is clean, and the compose/k8s manifests are production-shaped with
no baked secrets. The remaining live steps are the operator's to run with their
own cloud account and secret manager.
