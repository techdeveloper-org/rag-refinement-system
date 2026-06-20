-- Migration 003: Add FK constraint on erasure_outbox.doc_id
-- Fixes #74: ErasureOutbox.doc_id had no foreign-key constraint, allowing
-- orphaned outbox rows after a document is hard-deleted outside of SQLAlchemy.
-- CASCADE delete ensures outbox rows are removed when their document is deleted.

ALTER TABLE erasure_outbox
    ADD CONSTRAINT fk_erasure_outbox_doc_id
    FOREIGN KEY (doc_id)
    REFERENCES documents(doc_id)
    ON DELETE CASCADE;
