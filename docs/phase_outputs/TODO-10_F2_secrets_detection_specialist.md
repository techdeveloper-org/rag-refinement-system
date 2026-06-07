# TODO-10 — Phase F.2: Secrets Detection Specialist Report

**Agent:** secrets-detection-specialist
**Phase:** F.2 (Parallel security review alongside sast-engineer and dependency-vulnerability-analyst)
**Date:** 2026-06-07
**Sprint:** RAG Refinement System brownfield fix sprint (10 fixes)

---

## 1. Files Scanned

| # | File Path | Fix(es) Covered |
|---|-----------|-----------------|
| 1 | `backend/app/security/auth.py` | F-01, F-02 |
| 2 | `backend/app/settings.py` | F-02 (jwt_issuer field) |
| 3 | `backend/app/adapters/generation.py` | F-03 (thinking budget) |
| 4 | `ingestion/pipeline.py` | F-04, F-06 |
| 5 | `backend/app/adapters/ingestor.py` | F-05 |
| 6 | `backend/app/adapters/router.py` | F-08, F-09 |
| 7 | `backend/app/api/documents.py` | F-09 (content-type fix) |
| 8 | `backend/app/api/answer.py` | F-07, F-10 |
| 9 | `ingestion/embedder.py` | F-05 related |
| 10 | `.env.example` | Configuration template |
| 11 | `tests/conftest.py` | Test fixture values |
| 12 | `tests/test_backend_internals.py` | Test fixture values |
| 13 | `tests/test_health.py` | Test fixture values |
| 14 | `tests/test_health_internals.py` | Test fixture values |
| 15 | `.gitignore` | .env exclusion verification |

---

## 2. Pattern Matching Results Per File

### 2.1 `backend/app/security/auth.py`

**Patterns checked:**
- `(password|secret|key|token|api_key)\s*=\s*["'][^"']+["']` — **NO MATCHES**
- JWT-like base64 strings — **NO MATCHES**
- API key patterns (`sk-*`, `ghp_*`) — **NO MATCHES**
- PEM blocks — **NO MATCHES**
- Connection strings with embedded credentials — **NO MATCHES**

**Findings:** NONE. All secret values are consumed via `settings.jwt_secret`, `settings.jwt_algorithm`, `settings.jwt_audience`, `settings.jwt_issuer`, and `settings.api_key_salt` — all of which are read from the environment by `Settings`. The module contains no string literals for secrets. The only string constants are enum values (`"api_key"`, `"jwt"`) which are not secrets.

---

### 2.2 `backend/app/settings.py`

**Patterns checked:**
- `(secret|key|token)\s*=\s*["'][^"']+["']` — **NO MATCHES**
- Default values for sensitive fields — **EXAMINED** (see F-02 verification below)
- JWT-like strings — **NO MATCHES**

**Findings:** NONE. All sensitive fields use `Field(alias="ENV_VAR_NAME")` without hardcoded defaults for secrets:

```python
jwt_secret: str | None = Field(default=None, alias="JWT_SECRET")     # safe: None default
jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")    # safe: algorithm name, not a secret
jwt_audience: str = Field(default="rag-refinement-personal", alias="JWT_AUDIENCE")  # safe: non-secret audience
jwt_issuer: str = Field(alias="JWT_ISSUER")                           # safe: NO default — required env var
api_key_salt: str | None = Field(default=None, alias="API_KEY_SALT")  # safe: None default
```

The `jwt_algorithm` and `jwt_audience` defaults are configuration values, not secrets. `HS256` is an algorithm name; `rag-refinement-personal` is an audience string — neither is a cryptographic secret.

---

### 2.3 `backend/app/adapters/generation.py`

**Patterns checked:**
- `ANTHROPIC_API_KEY` or similar hardcoded — **NO MATCHES**
- `sk-*` pattern — **NO MATCHES**
- Integer literals as secrets — **NOT APPLICABLE** (integers are not secrets)

**Findings:** NONE. The module comment explicitly states: *"the API key is resolved from the environment by the SDK — it is never accepted as a constructor literal (no hardcoded secret)."* The `DEFAULT_THINKING_BUDGET_TOKENS = 5000` constant is an integer configuration value — confirmed NOT a secret per the agreed contracts. The Anthropic client is constructed as `anthropic.AsyncAnthropic()` with no key argument, relying on `ANTHROPIC_API_KEY` from the environment (SDK convention).

---

### 2.4 `ingestion/pipeline.py`

**Patterns checked:**
- Credential patterns — **NO MATCHES**
- Database connection strings with credentials — **NO MATCHES**
- API key literals — **NO MATCHES**

**Findings:** NONE. The only constant is `_DOC_ID_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")` — this is a public RFC 4122 UUID namespace, not a secret. All external dependencies (stores, embedders) are injected via Protocol interfaces.

---

### 2.5 `backend/app/adapters/ingestor.py`

**Patterns checked:**
- Credential patterns — **NO MATCHES**
- Hardcoded status strings — **EXAMINED** (safe: `"fallback_only"`, `"ephemeral"`, `"indexed"` are status labels, not secrets)

**Findings:** NONE. The module uses status string constants (`_INGEST_STATUS_FALLBACK`, `_INGEST_STATUS_EPHEMERAL`, `_INGEST_STATUS_INDEXED`) which are domain status labels, not credentials.

---

### 2.6 `backend/app/adapters/router.py`

**Patterns checked:**
- Credential patterns — **NO MATCHES**
- Sentinel values — **EXAMINED** (safe: `_NO_DOCUMENT_GROUP = object()` and `_NO_DOCUMENT_SORT_KEY = ""` are sorting sentinels, not secrets)

**Findings:** NONE. No credentials or sensitive data in any constant or string literal.

---

### 2.7 `backend/app/api/documents.py`

**Patterns checked:**
- Credential patterns — **NO MATCHES**
- Hardcoded content types — **EXAMINED** (`_PDF_CONTENT_TYPE = "application/pdf"` — safe, MIME type)
- Residency regions — **EXAMINED** (`{"IN", "EU", "US", "GLOBAL"}` — safe, configuration values)

**Findings:** NONE. All constants are MIME types, region codes, and size constants — no credentials.

---

### 2.8 `backend/app/api/answer.py`

**Patterns checked:**
- Credential patterns — **NO MATCHES**
- SSE media type — **EXAMINED** (`_SSE_MEDIA_TYPE = "text/event-stream"` — safe, MIME type)

**Findings:** NONE. Only MIME type constant present.

---

### 2.9 `ingestion/embedder.py`

**Patterns checked:**
- `OPENAI_API_KEY` hardcoded value — **NO MATCHES**
- `sk-*` pattern — **NO MATCHES** (only found in test files — see Section 3)
- Model name strings — **EXAMINED** (`"text-embedding-3-small"`, `"BAAI/bge-m3"` — safe, model identifiers, not secrets)

**Findings:** NONE. The `OpenAIEmbedder.embed()` method reads the key at call time via `os.environ.get("OPENAI_API_KEY")` and raises `RuntimeError` if absent. The module comment explicitly states: *"API keys are read from the environment only — never hardcoded."*

---

### 2.10 `.env.example`

**Content examined:** Template file with placeholder values:
- `OPENAI_API_KEY=replace-with-openai-key` — placeholder, not a real key
- `ANTHROPIC_API_KEY=replace-with-anthropic-key` — placeholder, not a real key
- `JWT_SECRET=replace-with-jwt-signing-secret` — placeholder, not a real secret
- `API_KEY_SALT=replace-with-api-key-salt` — placeholder, not a real salt

**Findings:** NONE. The file header states: *"All values below are placeholders only — no real secrets belong in this file."* These are documentation-only placeholder strings with no cryptographic value.

---

## 3. Finding Classification

| Location | Finding | Classification | Verdict |
|----------|---------|----------------|---------|
| `tests/conftest.py:40` | `JWT_SECRET = "test-jwt-secret-not-a-real-key-padded-32b"` | Test fixture value; annotated with `# noqa: S105 - test-only literal` | **SAFE — test context** |
| `tests/conftest.py:41` | `API_KEY_SALT = "test-api-key-salt"` | Test fixture value; annotated with `# noqa: S105 - test-only literal` | **SAFE — test context** |
| `tests/conftest.py:43` | `JWT_ISSUER = "test-issuer"` | Test fixture value | **SAFE — test context** |
| `tests/test_backend_internals.py:160` | `Settings(JWT_SECRET="x" * 32, JWT_ISSUER="test-issuer")` | Test Settings constructor with dummy 32-char string for unit testing | **SAFE — test context** |
| `tests/test_backend_internals.py:180` | `Settings(JWT_SECRET="x" * 32, JWT_ISSUER="test-issuer")` | Same pattern | **SAFE — test context** |
| `tests/test_health.py:75` | `Settings(JWT_ISSUER="test-issuer")` | Test Settings constructor | **SAFE — test context** |
| `tests/test_health_internals.py:156,177,199` | `JWT_ISSUER="test-issuer"` | Test Settings constructors | **SAFE — test context** |
| `ingestion/tests/test_embedder_adapters.py:60,92` | `monkeypatch.setenv("OPENAI_API_KEY", "sk-test")` | Monkeypatched test env var; `sk-test` is not a valid OpenAI key | **SAFE — test context** |
| `backend/app/settings.py:57` | `jwt_audience: str = Field(default="rag-refinement-personal")` | Service identifier string, not a cryptographic secret | **SAFE — non-secret config** |
| `backend/app/settings.py:56` | `jwt_algorithm: str = Field(default="HS256")` | Algorithm name, not a secret | **SAFE — non-secret config** |
| `backend/app/adapters/generation.py:31` | `DEFAULT_THINKING_BUDGET_TOKENS = 5000` | Integer literal, explicitly confirmed NOT a secret by agreed contracts | **SAFE — integer config** |

**No production secrets found in any file.**

---

## 4. F-02 Environment Variable Verification

**Requirement:** `jwt_issuer` must use `Field(alias="JWT_ISSUER")` with NO default value, reading exclusively from the environment.

**Verification result — CONFIRMED COMPLIANT:**

`backend/app/settings.py` line 58:
```python
jwt_issuer: str = Field(alias="JWT_ISSUER")
```

- Type annotation: `str` (not `str | None`) — the field is required
- Default: **ABSENT** — no `default=` argument means pydantic-settings will raise `ValidationError` if `JWT_ISSUER` is not set in the environment
- Alias: `"JWT_ISSUER"` — reads from the `JWT_ISSUER` environment variable
- **No hardcoded value, no fallback string** — the service fails to start if `JWT_ISSUER` is missing (fail-fast startup, Option A from the fix requirements)

Usage in `backend/app/security/auth.py` line 209:
```python
claims = jwt.decode(
    token,
    settings.jwt_secret,
    algorithms=[settings.jwt_algorithm],
    audience=settings.jwt_audience,
    issuer=settings.jwt_issuer,   # <-- always passed; never None
    options=options,
)
```

The `issuer` parameter is passed unconditionally on every JWT decode operation. No conditional check (`if settings.jwt_issuer`) exists — issuer validation is always enforced. F-02 **PASS**.

---

## 5. .env File Check Result

**Tracked `.env` files in git:**

```
.env.example    ← template file with placeholders ONLY
```

**`.env` (populated secrets file):** NOT tracked by git.

**`.gitignore` verification:**
```
.env
.env.*
!.env.example
```

The `.gitignore` correctly:
1. Excludes `.env` (the populated secrets file)
2. Excludes `.env.*` (all environment-specific variants like `.env.prod`, `.env.local`)
3. Explicitly re-includes `.env.example` (the safe placeholder template)

No actual secrets are tracked in version control. **PASS.**

---

## 6. Summary of Pattern Scan Results

| Pattern | Source Files | Test Files | Verdict |
|---------|-------------|-----------|---------|
| `(password\|secret\|key\|token\|api_key)\s*=\s*["'][^"']{8,}["']` in production code | 0 matches | N/A | CLEAN |
| JWT-like base64 strings (`eyJ...`) | 0 matches | 0 matches | CLEAN |
| OpenAI key pattern (`sk-`) | 0 matches (prod) | `sk-test` in monkeypatch (safe) | CLEAN |
| GitHub token pattern (`ghp_`) | 0 matches | 0 matches | CLEAN |
| AWS key pattern (`AKIA`) | 0 matches | 0 matches | CLEAN |
| Google API key (`AIza`) | 0 matches | 0 matches | CLEAN |
| PEM private key blocks | 0 matches | 0 matches | CLEAN |
| Database connection strings with passwords | 0 matches (prod) | `postgresql://rag:rag@localhost` in `.env.example` (placeholder) | CLEAN |
| Hardcoded JWT secret in settings | 0 matches | test fixture only | CLEAN |
| `jwt_issuer` without env var alias | 0 matches | N/A | CLEAN |

---

## 7. Final Verdict

### ZERO CREDENTIAL LEAKS — PASS

No hardcoded credentials, API keys, JWT secrets, or sensitive values were found in any production source file modified by the 10 fixes. Every finding is either:

- A **test fixture value** in a test file (e.g., `"test-jwt-secret-not-a-real-key-padded-32b"` in `tests/conftest.py`) — these are dummy values with no production validity and are annotated with `# noqa: S105 - test-only literal`
- A **non-secret configuration default** (e.g., `"HS256"` algorithm name, `5000` integer budget, `"rag-refinement-personal"` audience identifier)
- A **template placeholder** in `.env.example` (`replace-with-*` strings with no cryptographic value)

**F-02 specifically:** `jwt_issuer: str = Field(alias="JWT_ISSUER")` is confirmed to have NO default value. The service fails at startup if `JWT_ISSUER` is absent from the environment. The issuer is validated unconditionally on every JWT decode. F-02 env var contract is fully honoured.

**Committed `.env` files:** Only `.env.example` (placeholder template) is tracked in git. The actual `.env` secrets file is excluded by `.gitignore` entries `.env` and `.env.*`.

| Check | Result |
|-------|--------|
| Production source files: zero hardcoded secrets | PASS |
| F-02: jwt_issuer reads from JWT_ISSUER env var, no default | PASS |
| F-03: thinking_budget_tokens=5000 is integer, not a secret | PASS |
| Embedder: OPENAI_API_KEY reads from environment only | PASS |
| Generation LLM: Anthropic key from SDK env resolution | PASS |
| Test fixtures: test values are clearly marked and non-production | PASS |
| .env file committed to git | PASS (only .env.example with placeholders) |
| .gitignore excludes populated .env files | PASS |

**OVERALL VERDICT: ZERO CREDENTIAL LEAKS — PASS**
