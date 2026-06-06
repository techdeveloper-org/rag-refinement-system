"""Schema tests for STORY-001 - no live database required.

These tests parse the forward DDL textually and validate it against the
SQLAlchemy models, asserting the STORY-001 hard invariants: tenant_id NOT NULL
on every table (IDOR guard), section_id as the universal PK, no vector column in
PostgreSQL, the page-range CHECK, the erasure outbox (OAQ-2), DPDP residency/PII
columns, and the content_hash dedup index.

A live-DB integration test (forward-then-rollback against a real Postgres) is
included but skipped when ``DATABASE_URL`` is not set, so the suite is green
offline.
"""

from __future__ import annotations

import os
import pathlib
import re

import pytest

from db.models import (
    Base,
    Document,
    ErasureOutbox,
    Section,
    INGEST_STATUS_VALUES,
)

_MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parents[2] / "migrations"
_FORWARD_SQL = _MIGRATIONS_DIR / "001_documents_sections.sql"
_DOWN_SQL = _MIGRATIONS_DIR / "001_documents_sections.down.sql"


def _read(path: pathlib.Path) -> str:
    """Read a migration file as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def _table_block(ddl: str, table: str) -> str:
    """Return the ``CREATE TABLE`` body for ``table`` from the DDL text.

    Args:
        ddl: Full forward-migration SQL.
        table: Table name to extract.

    Returns:
        The text between the opening paren and the matching close of the
        CREATE TABLE statement for ``table``.
    """
    pattern = re.compile(
        r"CREATE TABLE IF NOT EXISTS\s+" + re.escape(table) + r"\s*\((.*?)\n\);",
        re.DOTALL | re.IGNORECASE,
    )
    match = pattern.search(ddl)
    assert match is not None, f"CREATE TABLE for {table} not found in DDL"
    return match.group(1)


def test_forward_migration_file_exists() -> None:
    """The forward and rollback migration files are present."""
    assert _FORWARD_SQL.is_file()
    assert _DOWN_SQL.is_file()


def test_every_table_has_tenant_id_not_null_in_ddl() -> None:
    """Every domain table declares ``tenant_id TEXT NOT NULL`` (IDOR guard)."""
    ddl = _read(_FORWARD_SQL)
    for table in ("documents", "sections", "erasure_outbox"):
        block = _table_block(ddl, table)
        assert re.search(
            r"tenant_id\s+TEXT\s+NOT\s+NULL", block, re.IGNORECASE
        ), f"{table} is missing tenant_id NOT NULL"


def test_every_model_has_tenant_id_not_null() -> None:
    """Every mapped table has a non-nullable ``tenant_id`` column."""
    for model in (Document, Section, ErasureOutbox):
        col = model.__table__.columns["tenant_id"]
        assert col.nullable is False, f"{model.__name__}.tenant_id must be NOT NULL"


def test_section_id_is_primary_key_and_universal() -> None:
    """``section_id`` is the single-column PK of ``sections``."""
    pk_cols = [c.name for c in Section.__table__.primary_key.columns]
    assert pk_cols == ["section_id"]


def test_doc_id_is_primary_key() -> None:
    """``doc_id`` is the single-column PK of ``documents``."""
    pk_cols = [c.name for c in Document.__table__.primary_key.columns]
    assert pk_cols == ["doc_id"]


def test_no_vector_column_in_postgres() -> None:
    """No table carries a vector/embedding column - vectors live only in Qdrant."""
    banned = {"vector", "embedding", "vectors", "embeddings"}
    for model in (Document, Section, ErasureOutbox):
        names = {c.name.lower() for c in model.__table__.columns}
        assert not (names & banned), (
            f"{model.__name__} must not store vectors in PostgreSQL"
        )
    ddl = _read(_FORWARD_SQL).lower()
    assert "vector(" not in ddl, "DDL must not declare a pgvector column"


def test_sections_fk_cascade_on_documents() -> None:
    """``sections.doc_id`` is an FK to documents with ON DELETE CASCADE."""
    fks = list(Section.__table__.columns["doc_id"].foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.column.table.name == "documents"
    assert fk.ondelete == "CASCADE"

    ddl = _read(_FORWARD_SQL)
    assert re.search(
        r"REFERENCES\s+documents\s*\(\s*doc_id\s*\)\s+ON\s+DELETE\s+CASCADE",
        ddl,
        re.IGNORECASE,
    )


def test_page_range_check_constraint() -> None:
    """A ``page_start <= page_end`` CHECK guards section page ranges (OAQ-3)."""
    check_texts = [
        str(c.sqltext)
        for c in Section.__table__.constraints
        if c.__class__.__name__ == "CheckConstraint"
    ]
    assert any("page_start <= page_end" in t for t in check_texts)

    ddl = _read(_FORWARD_SQL)
    assert "page_start <= page_end" in ddl


def test_ingest_status_enum_values_match_contract() -> None:
    """``ingest_status`` enum is exactly indexed | fallback_only | ephemeral."""
    assert INGEST_STATUS_VALUES == ("indexed", "fallback_only", "ephemeral")
    ddl = _read(_FORWARD_SQL)
    assert "CREATE TYPE ingest_status AS ENUM" in ddl
    for value in INGEST_STATUS_VALUES:
        assert f"'{value}'" in ddl


def test_dpdp_residency_and_pii_columns_present() -> None:
    """DPDP residency_region + pii_flags columns exist (FR-028/FR-029)."""
    doc_cols = {c.name for c in Document.__table__.columns}
    assert "residency_region" in doc_cols
    assert "pii_flags" in doc_cols
    assert "fallback_only" in doc_cols
    sec_cols = {c.name for c in Section.__table__.columns}
    assert "pii_flags" in sec_cols


def test_erasure_outbox_supports_oaq2_cascade() -> None:
    """The erasure outbox carries the fields needed to reconcile vector cleanup."""
    cols = {c.name for c in ErasureOutbox.__table__.columns}
    assert {"doc_id", "tenant_id", "store", "status"} <= cols
    ddl = _read(_FORWARD_SQL)
    assert "CREATE TABLE IF NOT EXISTS erasure_outbox" in ddl
    assert "tombstoned_at" in ddl


def test_content_hash_index_for_idempotent_reupload() -> None:
    """A content_hash index backs idempotent re-upload dedup (OAQ-1)."""
    ddl = _read(_FORWARD_SQL)
    assert "idx_documents_content_hash" in ddl
    assert re.search(
        r"idx_documents_content_hash[\s\S]*content_hash", ddl, re.IGNORECASE
    )


def test_required_indexes_declared() -> None:
    """tenant_id, domain and (doc_id, page_start) indexes are declared."""
    ddl = _read(_FORWARD_SQL)
    for idx in (
        "idx_documents_tenant_id",
        "idx_documents_domain",
        "idx_sections_doc_id_page_start",
        "idx_sections_tenant_id",
    ):
        assert idx in ddl, f"missing index {idx}"


def test_model_columns_match_ddl_columns() -> None:
    """Each model's column set matches the columns declared in its DDL block."""
    ddl = _read(_FORWARD_SQL)
    column_line = re.compile(r"^\s{4}([a-z_]+)\s+\S", re.MULTILINE)
    for model, table in (
        (Document, "documents"),
        (Section, "sections"),
        (ErasureOutbox, "erasure_outbox"),
    ):
        block = _table_block(ddl, table)
        ddl_cols = set(column_line.findall(block))
        reserved = {
            "constraint",
            "primary",
            "references",
            "check",
            "foreign",
            "begin",
            "commit",
        }
        ddl_cols -= reserved
        model_cols = {c.name for c in model.__table__.columns}
        assert model_cols == ddl_cols, (
            f"{table}: model {sorted(model_cols)} != ddl {sorted(ddl_cols)}"
        )


def test_metadata_registers_all_three_tables() -> None:
    """SQLAlchemy metadata knows exactly the three structure-store tables."""
    assert set(Base.metadata.tables) == {
        "documents",
        "sections",
        "erasure_outbox",
    }


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; live forward+rollback migration test skipped.",
)
def test_forward_then_rollback_restores_baseline() -> None:
    """Apply forward DDL then rollback against a live Postgres; expect clean state.

    Skipped without ``DATABASE_URL`` so the suite stays offline-green.
    """
    from sqlalchemy import create_engine, inspect, text

    engine = create_engine(os.environ["DATABASE_URL"])
    forward = _read(_FORWARD_SQL)
    down = _read(_DOWN_SQL)
    with engine.begin() as conn:
        conn.execute(text(forward))
    inspector = inspect(engine)
    assert inspector.has_table("documents")
    assert inspector.has_table("sections")
    with engine.begin() as conn:
        conn.execute(text(down))
    inspector = inspect(engine)
    assert not inspector.has_table("sections")
    assert not inspector.has_table("documents")
