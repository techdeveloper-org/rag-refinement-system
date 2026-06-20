-- ============================================================================
-- Migration 002 (forward / up): composite index + uniqueness constraints
-- ----------------------------------------------------------------------------
-- RAG Refinement System - supplemental DDL for performance and integrity.
--
-- Fixes applied:
--   #120  Composite index on documents(tenant_id, tombstoned_at) for the
--         reconciliation sweep that selects active-per-tenant rows efficiently.
--   #103  UNIQUE(doc_id, store) on erasure_outbox prevents duplicate tombstone
--         rows from being written inside the DELETE transaction (OAQ-2).
--   #104  UNIQUE(tenant_id, content_hash) on documents enforces idempotent
--         re-upload dedup at the database level (OAQ-1); partial on non-NULL
--         hashes only because the ephemeral path stores no hash.
--
-- This migration is idempotent: all objects use IF NOT EXISTS guards and
-- DO $$ ... $$ blocks so re-applying is a no-op. The matching rollback is
-- 002_indexes_constraints.down.sql.
-- ============================================================================

BEGIN;

-- ----------------------------------------------------------------------------
-- #120: composite index on documents(tenant_id, tombstoned_at)
-- ----------------------------------------------------------------------------
-- Used by the OAQ-2 reconciliation sweep to find tombstoned rows scoped to a
-- tenant without a full table scan. Also accelerates tenant-scoped document
-- list queries that filter on tombstone state.
CREATE INDEX IF NOT EXISTS idx_documents_tenant_tombstoned
    ON documents (tenant_id, tombstoned_at);

-- ----------------------------------------------------------------------------
-- #103: UNIQUE(doc_id, store) on erasure_outbox
-- ----------------------------------------------------------------------------
-- Guarantees at most one outbox row per (doc_id, store) pair so the DELETE
-- transaction is idempotent and the sweep worker never processes duplicates.
-- Implemented as a unique index so it applies only if the constraint does not
-- already exist (idempotent).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM   pg_class c
        JOIN   pg_namespace n ON n.oid = c.relnamespace
        WHERE  c.relname = 'uq_erasure_outbox_doc_store'
          AND  n.nspname = current_schema()
    ) THEN
        CREATE UNIQUE INDEX uq_erasure_outbox_doc_store
            ON erasure_outbox (doc_id, store);
    END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- #104: UNIQUE(tenant_id, content_hash) on documents (partial, non-NULL only)
-- ----------------------------------------------------------------------------
-- Enforces the OAQ-1 dedup invariant at the database level: no two rows for
-- the same tenant may share a content_hash. The partial predicate
-- (content_hash IS NOT NULL) excludes ephemeral rows that have no hash,
-- matching the existing partial index on content_hash alone.
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
