-- ============================================================================
-- Migration 002 (rollback / down): drop composite index + uniqueness constraints
-- ----------------------------------------------------------------------------
-- Reverses 002_indexes_constraints.sql cleanly. Drops objects in reverse
-- creation order. Idempotent: every DROP uses IF EXISTS guards.
-- ============================================================================

BEGIN;

DROP INDEX IF EXISTS uq_documents_tenant_hash;
DROP INDEX IF EXISTS uq_erasure_outbox_doc_store;
DROP INDEX IF EXISTS idx_documents_tenant_tombstoned;

COMMIT;
