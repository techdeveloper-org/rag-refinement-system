# Database Migrations

PostgreSQL structure-store migrations for the RAG Refinement System
(STORY-001, FR-003 / FR-024). These create the Level-1 `documents` and Level-2
`sections` hierarchy plus the OAQ-2 `erasure_outbox`. Chunk **vectors are not
stored here** - they live only in Qdrant (ADR-2); see `db/qdrant_bootstrap.py`.

## Files

| File | Purpose |
|------|---------|
| `001_documents_sections.sql` | Forward migration: enums, `documents`, `sections`, `erasure_outbox`, indexes. |
| `001_documents_sections.down.sql` | Rollback: drops the above in reverse dependency order. |

Both scripts are idempotent (`IF NOT EXISTS` / `IF EXISTS` guards), so they can
be re-applied safely.

## Prerequisites

- PostgreSQL 14+ (uses `GENERATED ALWAYS AS IDENTITY` and `JSONB`).
- A connection string in the `DATABASE_URL` environment variable
  (12-factor; never hardcode credentials - devops AGREED CONTRACT).

```bash
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/rag"
```

## Apply (forward)

Using `psql`:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_documents_sections.sql
```

## Roll back (down)

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/001_documents_sections.down.sql
```

## Verify

```sql
-- Tables present
\dt documents sections erasure_outbox

-- tenant_id is NOT NULL on every domain table (tenant isolation / IDOR guard)
SELECT table_name, column_name, is_nullable
FROM information_schema.columns
WHERE column_name = 'tenant_id'
ORDER BY table_name;
```

## Notes on tenant isolation

`tenant_id` is `NOT NULL` on `documents`, `sections`, and `erasure_outbox`. It is
the row-level IDOR guard: every retrieval and management query MUST filter on
`tenant_id = caller` (AC-024). Use parameterized queries only.

## Schema parity & tests

`db/models.py` mirrors `001_documents_sections.sql` exactly. The test suite
(`db/tests/`) parses the DDL and asserts model<->DDL field parity without a live
database, and validates the Qdrant bootstrap config against a mocked client.

```bash
python -m pytest db/tests -q
```
