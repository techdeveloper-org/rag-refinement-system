-- ============================================================================
-- Migration 001 (rollback / down): drop documents + sections structure store
-- ----------------------------------------------------------------------------
-- Reverses 001_documents_sections.sql cleanly. Drops dependent objects in
-- reverse dependency order (sections -> documents -> enums) so the schema
-- returns to the pre-001 baseline. Idempotent: every DROP is guarded by
-- IF EXISTS, so re-running the rollback is a no-op.
-- ============================================================================

BEGIN;

DROP INDEX IF EXISTS idx_erasure_outbox_doc_id;
DROP INDEX IF EXISTS idx_erasure_outbox_status;
DROP INDEX IF EXISTS idx_sections_tenant_id;
DROP INDEX IF EXISTS idx_sections_doc_id_page_start;
DROP INDEX IF EXISTS idx_documents_content_hash;
DROP INDEX IF EXISTS idx_documents_domain;
DROP INDEX IF EXISTS idx_documents_tenant_id;

DROP TABLE IF EXISTS erasure_outbox;
DROP TABLE IF EXISTS sections;
DROP TABLE IF EXISTS documents;

DROP TYPE IF EXISTS residency_region;
DROP TYPE IF EXISTS ingest_status;

COMMIT;
