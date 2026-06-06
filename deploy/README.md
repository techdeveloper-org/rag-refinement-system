# Deployment artifacts

Production-shaped deploy configuration for the RAG Refinement System. A live
cloud deploy requires the operator's cloud credentials and a secret manager;
these files are the production-ready reference and are driven by the
step-by-step [deploy runbook](../docs/phase-G-deploy/deploy_runbook.md).

| File | Purpose |
|------|---------|
| `docker-compose.prod.yml` | Production compose: api + static frontend + auth'd Postgres + auth'd Qdrant, internal-only data network, runtime-injected secrets, resource limits, restart policies, non-root hardening. |
| `frontend.Dockerfile` | Multi-stage Vite build served by a non-root nginx (port 8080). No secrets baked. |
| `.env.prod.example` | Placeholder-only list of the variables the prod stack needs (inject from a secret manager — never a committed `.env`). |
| `reverse-proxy/Caddyfile.example` | TLS-terminating reverse proxy example (the only internet-facing component). Routes `/api/*` to the backend (SSE-safe) and everything else to the SPA. |
| `k8s/api-deployment.yaml` | Alternative target: hardened Deployment + Service (non-root, read-only FS, dropped caps, liveness `/health`, readiness `/ready`, resource limits). |
| `k8s/secret.example.yaml` | Template documenting the `rag-secrets` keys. Generate from a secret manager (External Secrets / Sealed Secrets) — do not commit real values. |
| `k8s/ingress.yaml` | TLS-terminating Ingress (cert-manager), SSE-safe annotations. |

## Security posture (cloud-security-architect sign-off)

- **TLS enforced** at the reverse proxy / Ingress; HTTP redirects to HTTPS; HSTS set.
- **No secrets baked** into any image or committed file. Compose uses `${VAR:?...}`
  so the deploy aborts on a missing secret; k8s pulls from `rag-secrets`.
- **Non-root** everywhere: the API image runs as `app`; nginx runs unprivileged;
  k8s enforces `runAsNonRoot`, `readOnlyRootFilesystem`, and dropped capabilities.
- **Network segmentation**: Postgres and Qdrant publish no host ports and live on an
  internal-only network; only the proxy is internet-facing.
- **Data-store auth**: production Postgres requires credentials; Qdrant requires an
  API key (anonymous access disabled).

See [`../docs/phase-G-deploy/deploy_runbook.md`](../docs/phase-G-deploy/deploy_runbook.md)
for build/push/provision/deploy/healthcheck/rollback steps and
[`../docs/phase-G-deploy/observability.md`](../docs/phase-G-deploy/observability.md)
for LangSmith tracing and the KPI metrics plan.
