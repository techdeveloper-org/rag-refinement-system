-- ============================================================================
-- Migration 004 (forward / up): fix uq_documents_tenant_hash partial index
-- ----------------------------------------------------------------------------
-- Fixes #206: the uq_documents_tenant_hash index created in migration 002 did
-- not exclude tombstoned rows from the uniqueness constraint. This caused a
-- UniqueViolation when re-uploading a file whose previous document row had been
-- soft-deleted (tombstoned_at IS NOT NULL) but not yet hard-deleted, because the
-- tombstoned row still occupied the (tenant_id, content_hash) slot in the index.
--
-- Fix: drop the old index and recreate it with an additional predicate:
--   WHERE content_hash IS NOT NULL AND tombstoned_at IS NULL
--
-- This ensures:
--   * Ephemeral rows with no hash are still excluded (content_hash IS NOT NULL).
--   * Tombstoned rows no longer block re-upload of the same content
--     (tombstoned_at IS NULL excludes soft-deleted rows).
--
-- This migration is idempotent: the DROP uses IF EXISTS and the CREATE uses a
-- DO $$ ... $$ guard against re-creation. The matching rollback is
-- 004_fix_tenant_hash_partial_index.down.sql.
-- ============================================================================

BEGIN;

-- Drop the old index (created without the tombstoned_at exclusion predicate).
DROP INDEX IF EXISTS uq_documents_tenant_hash;

-- Recreate with a partial index that excludes tombstoned rows.
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
            WHERE tombstoned_at IS NULL AND content_hash IS NOT NULL;
    END IF;
END
$$;

COMMIT;
