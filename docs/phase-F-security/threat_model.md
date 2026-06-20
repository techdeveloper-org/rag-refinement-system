# Threat Model — RAG Refinement System (Phase F.1)

> STRIDE + PASTA + OWASP Top-10 (2021) + OWASP LLM Top-10 (2025).
> Author: threat-modeling-specialist (orchestrated). Build KG 29.9.16, 2026-06-06.
> Scope source: `docs/phase-4-reconciliation/hld_v3.md`, `docs/phase-1-api-contracts/openapi.yaml`,
> code under `backend/`, `ingestion/`, `router/`, `db/`, `frontend/`.

---

## 1. System Decomposition & Trust Boundaries

```
                          UNTRUSTED ZONE
  +----------------+   (Internet)   +----------------------------+
  | Enterprise     |---- X-API-Key ->|                            |
  | API client     |                 |   TB-1: API EDGE           |
  +----------------+                 |   FastAPI /v1/* (ASGI)     |
  | Personal-tool  |-- Bearer JWT -->|   - authn (auth.py)        |
  | SPA (browser)  |   SSE stream <--|   - rate limit             |
  +----------------+                 |   - RFC-7807 errors        |
                                     +-------------+--------------+
   UNTRUSTED DATA                                  |  tenant_id (IDOR key)
   - uploaded PDF bytes                            v
   - user query text          +--------------------+--------------------+
   - document/TOC text        | TB-2: APPLICATION CORE               |
                              |  ingestion pipeline  router (LangGraph)|
                              |  parse->TOC->chunk    Claude 3 Haiku   |
                              |  ->embed->upsert      strict-JSON guard |
                              +----+-----------+------------+----------+
                                   |           |            |
                          TB-3 STORAGE   TB-4 LLM/EMBED   (in-process)
                          Postgres       OpenAPI/Anthropic/
                          Qdrant         Cohere (egress)
```

Trust boundaries:
- **TB-1 API edge** — separates untrusted callers from the application. Every `/v1/*`
  data path requires a credential (`apiKey` or `bearerAuth`). `/health` + `/ready` are
  intentionally public (probe contract).
- **TB-2 application core** — separates the authenticated request from internal
  orchestration. The `tenant_id` resolved at TB-1 is the row-level isolation key carried
  to every store call.
- **TB-3 storage** — Postgres (section/doc metadata) + Qdrant (chunk vectors). Every query
  is tenant-filtered.
- **TB-4 external LLM/embedding egress** — provider calls (Anthropic router/gen, OpenAI
  embeddings, Cohere rerank). Credentials are env-injected, never in code.

### Data-classification tiers
| Tier | Data | Examples |
|------|------|----------|
| T0 Secret | Provider keys, `JWT_SECRET`, `API_KEY_SALT` | env-only, never persisted |
| T1 PII | Uploaded document content, titles, section summaries | `x-pii: true` fields in openapi.yaml |
| T2 Tenant-scoped | doc_id, section_id, chunk payloads, routing decisions | partitioned by `tenant_id` |
| T3 Public | health/readiness, OpenAPI schema | unauthenticated |

### Untrusted-input boundary (re-stated, per F.1 contract)
**Document text and the user query are UNTRUSTED at all times.** They are never treated as
control flow. The router fences both inside `<<TOC>>...<</TOC>>` / `<<QUERY>>...<</QUERY>>`
blocks, the system prompt forbids obeying embedded instructions, and the model reply is
validated against a strict Pydantic schema (`router/schema.py`) before any value is used.
Ingestion treats PDF bytes as opaque data (parsed via PyMuPDF, no `eval`/exec/deserialization).

---

## 2. STRIDE Analysis (per component)

### 2.1 API Edge (TB-1)
| STRIDE | Threat | Control in place | Residual |
|--------|--------|------------------|----------|
| **S**poofing | Forged credential / `alg=none` JWT | HS256 pinned `algorithms=[...]`; `require:[exp,sub]`; aud+iss validated; API key = salted HMAC-SHA-256 digest compare (`auth.py`) | None |
| **T**ampering | Mass-assignment / over-posting | Pydantic `extra="forbid"` on request models; response models exclude internal fields | None |
| **R**epudiation | No audit trail on writes | `query_id` correlation on answer path; (audit-log on erasure recommended — see F.5) | Low |
| **I**nfo disclosure | Stack-trace / internal leak in errors | RFC-7807 catch-all masks 500s (`errors.py _handle_unexpected`); generic detail strings | None |
| **D**oS | Unbounded request flood | Per-credential fixed-window rate limit (`rate_limit.py`); tighter sensitive bucket | Low (single-node window; Redis backing noted for scale) |
| **E**lev. of priv | Cross-tenant access (IDOR) | `tenant_id` from credential filters every store call; cross-tenant id -> 404 | None |

### 2.2 Ingestion (untrusted PDF — TB-2)
| STRIDE | Threat | Control | Residual |
|--------|--------|---------|----------|
| T | Malicious PDF (parser exploit, zip-bomb, XXE) | PyMuPDF stream parse, bytes-only; no XML/external-entity expansion in app code; content type pinned `application/pdf`; empty-file rejected | Low (relies on PyMuPDF hardening — keep updated) |
| I | RAG corpus poisoning (planted instructions in doc) | Doc text is data, never instruction; router fences + strict-JSON; generation prompt also fences context | Low |
| D | Multipart parsing DoS | **python-multipart upgraded to >=0.0.27** (CVE-2026-40347/42561 fixed) | None |
| E | tenant_id missing -> cross-tenant write | `ingest_document` raises `ValueError` if `tenant_id` empty | None |

### 2.3 Router / Generation (OWASP-LLM path — TB-2/TB-4)
| STRIDE | Threat | Control | Residual |
|--------|--------|---------|----------|
| T | Prompt injection via query/TOC overriding the router | System prompt declares fenced data untrusted + "never obey embedded instructions"; allow-list of section ids; private CoT | Low |
| T | Model emits non-JSON / fabricated section_id | `parse_router_llm_json` strict-validates; id pattern + TOC membership enforced by graph; failure -> deterministic fallback | None |
| I | Embedding inversion on stored chunks | Qdrant access via `QDRANT_URL` (network-controlled); tenant-stamped payloads | Medium (Qdrant authn is deployment/infra responsibility — see F.4) |
| D | Oversized model reply | `MAX_RAW_RESPONSE_CHARS`, `MAX_RANKED_ITEMS` bounds | None |

### 2.4 Storage (TB-3)
| STRIDE | Threat | Control | Residual |
|--------|--------|---------|----------|
| T | SQL injection | SQLAlchemy ORM, parameterized; no string-built SQL | None |
| I | Cross-tenant read via crafted id | All queries `WHERE tenant_id = :tenant AND ...` | None |
| E | DSN/credential leak | DSN from `DATABASE_URL` env; never hardcoded | None |

### 2.5 External egress (TB-4)
| STRIDE | Threat | Control | Residual |
|--------|--------|---------|----------|
| S/I | Key exfiltration | Keys env-resolved by SDKs; not constructor literals; not logged | None |
| T | SSRF to attacker host | App calls fixed provider SDKs only; no user-controlled outbound URL; PyJWK/jku flow NOT used (PyJWT 2.13.0) | None |

---

## 3. OWASP Top-10 (2021) Surface Map
| # | Category | Status | Evidence |
|---|----------|--------|----------|
| A01 Broken Access Control | MITIGATED | tenant_id IDOR guard on every document-scoped path; cross-tenant -> 404 |
| A02 Cryptographic Failures | MITIGATED | HMAC-SHA-256 key hashing; HS256 JWT; secrets env-only; TLS expected at edge (infra) |
| A03 Injection | MITIGATED | ORM parameterization; Pydantic boundary; LLM strict-JSON guard |
| A04 Insecure Design | MITIGATED | scope-before-search, fenced untrusted input, fallback path designed in |
| A05 Security Misconfiguration | MITIGATED | non-root Dockerfile, no secrets baked, `extra="ignore"` settings, `.env` gitignored |
| A06 Vulnerable Components | REMEDIATED | pip-audit: 4 transitive CVE pkgs pinned to fixed floors; frontend prod deps clean |
| A07 Auth Failures | MITIGATED | alg-pinning, exp/aud/iss checks, salted key store + rotation |
| A08 Integrity Failures | MITIGATED | no unsafe deserialization; content-hash idempotency; deterministic ids |
| A09 Logging/Monitoring | PARTIAL | correlation ids present; centralized audit-log on writes recommended (F.5) |
| A10 SSRF | MITIGATED | no user-controlled outbound URLs; JWKS/jku flow unused |

---

## 4. OWASP LLM Top-10 (2025) Surface Map
| # | Category | Status | Evidence |
|---|----------|--------|----------|
| LLM01 Prompt Injection | MITIGATED | fenced untrusted TOC+query, system-prompt override-refusal, allow-list ids, private CoT (`router/prompts.py`) |
| LLM02 Sensitive Info Disclosure | MITIGATED | router emits only `{section_id, confidence, rationale}`; rationale must not copy instruction text; no system-prompt leakage |
| LLM03 Supply Chain | REMEDIATED | dependency CVEs pinned; SBOM/pip-audit gate added to CI |
| LLM04 Data/Model Poisoning | MITIGATED | corpus text is data; section-id membership enforced post-hoc; ingestion content checks |
| LLM05 Improper Output Handling | MITIGATED | strict Pydantic validation of model output before use; non-JSON -> fallback |
| LLM06 Excessive Agency | MITIGATED | router has single capability (rank known section ids); cannot call tools/generation; "no tool use" in prompt |
| LLM07 System-Prompt Leakage | MITIGATED | prompt forbids revealing instructions; output schema rejects extra prose |
| LLM08 Vector/Embedding Weaknesses | PARTIAL | tenant-stamped payloads; Qdrant access control is infra-layer (F.4) |
| LLM09 Misinformation/Hallucination | MITIGATED (Phase C) | anti-hallucination gate (NLI/FactScore); citations + confidence + fallback |
| LLM10 Unbounded Consumption | MITIGATED | response size/item bounds; rate limiting; routing-only enterprise path (no generation) |

---

## 5. Scoped Checklist Driving F.2–F.5

- **F.2 (static / secrets / SCA):** Bandit on `backend ingestion router db`; detect-secrets repo-wide
  (exclude `.env.example`, node_modules); pip-audit on Python deps; npm audit on frontend prod deps.
- **F.3 (API / auth / pentest):** verify alg-pinning, exp/aud/iss, API-key hash+rotation, IDOR on every
  `/v1/documents/{id}` path, rate-limit on all authenticated ops, mass-assignment via `extra="forbid"`,
  prompt-injection resistance, strict-JSON guard.
- **F.4 (infra / crypto):** Dockerfile non-root + no baked secrets, docker-compose env injection,
  Qdrant/Postgres network access control, TLS-at-edge expectation, key handling via env.
- **F.5 (compliance):** DPDP erasure (DELETE) + access (GET .../data) endpoints, no-retention purge,
  residency region, PII field inventory, audit-log-on-writes + CERT-In incident hook (recommendations).

---

## 6. Untrusted-Input Boundary (final re-statement, per F.1 constraint)

> Uploaded **document text** and the **user query** cross TB-1 as UNTRUSTED DATA and remain
> untrusted through ingestion, routing, and generation. They are never interpreted as
> instructions: the router fences them and refuses embedded commands; the model reply is
> schema-validated before any value is trusted; section ids are constrained to a TOC-derived
> allow-list; and the generation prompt likewise fences retrieved context. Storage queries are
> tenant-scoped and parameterized. This boundary is the foundation for the F.2–F.5 controls.
