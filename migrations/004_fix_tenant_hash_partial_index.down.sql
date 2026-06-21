-- ============================================================================
-- Migration 004 (rollback / down): restore uq_documents_tenant_hash without
-- the tombstoned_at exclusion predicate.
-- ============================================================================

BEGIN;

-- Drop the index added by migration 004.
DROP INDEX IF EXISTS uq_documents_tenant_hash;

-- Restore the original index from migration 002 (partial on content_hash only).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_class c
        JOIN   pg_namespace n ON n.oid = c.relnamespace
        WHERE  c.relname = 'uq_documents_tenant_hash'
          AND  n.nspname = current_schema()
    ) THEN
        CREATE UNIQUE INDEX uq_documents_tenant_hash
            ON documents (tenant_id, content_hash)
            WHERE content_hash IS NOT NULL;
    END IF;
END
$$;

COMMIT;
