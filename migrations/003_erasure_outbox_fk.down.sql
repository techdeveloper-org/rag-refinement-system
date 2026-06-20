-- Rollback migration 003: Remove FK constraint on erasure_outbox.doc_id

ALTER TABLE erasure_outbox
    DROP CONSTRAINT IF EXISTS fk_erasure_outbox_doc_id;
