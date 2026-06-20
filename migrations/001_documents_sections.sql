-- ============================================================================
-- Migration 001 (forward / up): documents + sections structure store
-- ----------------------------------------------------------------------------
-- RAG Refinement System - PostgreSQL structure store (ADR-10).
-- STORY-001 (FR-003, FR-024). Implements HLD section 4.1/4.2 and the AGREED
-- CONTRACT (python-backend-engineer <-> database-engineer): documents(doc_id PK,
-- title, total_pages, domain) and sections(section_id PK, doc_id FK, title,
-- level, page_start, page_end, summary).
--
-- Invariants enforced here:
--   * section_id is the universal join/filter key (HLD section 4.1, OAQ-3).
--   * NO chunk vectors live in PostgreSQL - vectors live ONLY in Qdrant (ADR-2).
--   * tenant_id is NOT NULL on every row (logical tenant isolation, OAQ-5;
--     Sprint-1 DoD item 4). It is the row-level IDOR guard for retrieval.
--   * sections.page_start/page_end are the single source of truth for page
--     ranges (OAQ-3); a CHECK enforces page_start <= page_end.
--   * pii_flags / residency_region columns satisfy dpdp-compliance-delta
--     (FR-028/FR-029); they store FIELD-NAME metadata only, never PII values.
--   * erasure_outbox + documents.tombstoned_at implement the OAQ-2 outbox +
--     reconciliation sweep so vector cleanup can reconcile orphan deletes.
--
-- This migration is idempotent: every object is created IF NOT EXISTS, and the
-- ingest_status enum is created guarded by a catalog check. Re-applying is a
-- no-op. The matching rollback is 001_documents_sections.down.sql.
-- ============================================================================

BEGIN;

-- ingest_status enum: indexed (Scenario A/B), fallback_only (Scenario C,
-- FR-009), ephemeral (no_retention, FR-027). Matches IngestResponse.ingest_status
-- and Document.fallback_only in openapi.yaml.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'ingest_status') THEN
        CREATE TYPE ingest_status AS ENUM ('indexed', 'fallback_only', 'ephemeral');
    END IF;
END
$$;

-- residency_region enum mirrors Document.residency_region (IN | EU | US | GLOBAL),
-- supporting India data-residency (FR-028, OAQ-5).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'residency_region') THEN
        CREATE TYPE residency_region AS ENUM ('IN', 'EU', 'US', 'GLOBAL');
    END IF;
END
$$;

-- ----------------------------------------------------------------------------
-- documents (Level 1)
-- ----------------------------------------------------------------------------
-- doc_id matches openapi DocumentId pattern ^doc_[A-Za-z0-9]{6,}$.
-- title is x-pii metadata (a NAME); no PII values are stored by this DDL.
-- content_hash supports idempotent re-upload (OAQ-1): a re-upload of identical
-- content reuses the existing doc_id. It is nullable because the no-retention /
-- ephemeral path computes an in-memory salted hash and persists nothing.
-- tombstoned_at implements the OAQ-2 erasure tombstone: a non-NULL value makes
-- the document immediately invisible to GET (404) while the sweep reconciles.
CREATE TABLE IF NOT EXISTS documents (
    doc_id           TEXT PRIMARY KEY,
    tenant_id        TEXT NOT NULL,
    title            TEXT,
    total_pages      INTEGER NOT NULL DEFAULT 0,
    domain           TEXT,
    ingest_status    ingest_status NOT NULL DEFAULT 'indexed',
    fallback_only    BOOLEAN NOT NULL DEFAULT FALSE,
    residency_region residency_region NOT NULL DEFAULT 'GLOBAL',
    content_hash     TEXT,
    pii_flags        JSONB NOT NULL DEFAULT '{}'::jsonb,
    tombstoned_at    TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT documents_total_pages_nonneg CHECK (total_pages >= 0)
);

-- ----------------------------------------------------------------------------
-- sections (Level 2) - page-range authority
-- ----------------------------------------------------------------------------
-- section_id matches openapi SectionId pattern ^sec_[A-Za-z0-9]{1,}$ and is the
-- universal join/filter key. No vector column exists here by design (vectors
-- live only in Qdrant). tenant_id is duplicated onto sections so every row is
-- tenant-scoped without a join (row-level IDOR guard on direct section reads).
-- ON DELETE CASCADE: removing a document removes its sections.
CREATE TABLE IF NOT EXISTS sections (
    section_id  TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES documents (doc_id) ON DELETE CASCADE,
    tenant_id   TEXT NOT NULL,
    title       TEXT,
    level       INTEGER NOT NULL DEFAULT 1,
    page_start  INTEGER NOT NULL,
    page_end    INTEGER NOT NULL,
    summary     TEXT,
    pii_flags   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT sections_level_positive CHECK (level >= 1),
    CONSTRAINT sections_page_start_positive CHECK (page_start >= 1),
    CONSTRAINT sections_page_range_valid CHECK (page_start <= page_end)
);

-- ----------------------------------------------------------------------------
-- erasure_outbox - OAQ-2 outbox + reconciliation sweep
-- ----------------------------------------------------------------------------
-- One row per (doc_id, store) tombstone written inside the DELETE transaction.
-- A worker deletes the target store's data; a periodic sweep removes any orphan
-- whose doc_id is tombstoned. status moves pending -> done (or error). This is
-- how Qdrant vector cleanup reconciles a Postgres-side erasure (DPDP FR-025).
CREATE TABLE IF NOT EXISTS erasure_outbox (
    outbox_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    doc_id       TEXT NOT NULL,
    tenant_id    TEXT NOT NULL,
    store        TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed_at TIMESTAMPTZ,
    CONSTRAINT erasure_outbox_store_valid CHECK (store IN ('qdrant', 'object_store', 'postgres')),
    CONSTRAINT erasure_outbox_status_valid CHECK (status IN ('pending', 'done', 'error'))
);

-- ----------------------------------------------------------------------------
-- Indexes
-- ----------------------------------------------------------------------------
-- documents(tenant_id): tenant-scoped list/IDOR queries (AC-024).
-- documents(domain): domain filtering for management queries.
-- documents(content_hash): idempotent re-upload dedup lookup (OAQ-1) - partial,
--   skipping NULL hashes (ephemeral path persists none).
-- sections(doc_id, page_start): TOC ordering + page-range lookups per document.
-- sections(tenant_id): tenant-scoped direct section reads (IDOR guard).
-- erasure_outbox(status): the sweep selects pending tombstones.
-- erasure_outbox(doc_id): reconcile orphan vectors by doc_id.
CREATE INDEX IF NOT EXISTS idx_documents_tenant_id ON documents (tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents (domain);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash
    ON documents (content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sections_doc_id_page_start
    ON sections (doc_id, page_start);
CREATE INDEX IF NOT EXISTS idx_sections_tenant_id ON sections (tenant_id);
CREATE INDEX IF NOT EXISTS idx_erasure_outbox_status ON erasure_outbox (status);
CREATE INDEX IF NOT EXISTS idx_erasure_outbox_doc_id ON erasure_outbox (doc_id);

COMMIT;
