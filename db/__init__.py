"""Database package for the RAG Refinement structure + vector stores.

Exposes the SQLAlchemy structure-store models (PostgreSQL, ADR-10) and the
idempotent Qdrant vector-store bootstrap (ADR-2). ``section_id`` is the universal
join/filter key across both stores; chunk vectors live only in Qdrant.
"""

from __future__ import annotations

from db.models import (
    INGEST_STATUS_VALUES,
    RESIDENCY_REGION_VALUES,
    Base,
    Document,
    ErasureOutbox,
    Section,
)
from db.qdrant_bootstrap import (
    COLLECTION_NAME,
    VECTOR_SIZE,
    BootstrapResult,
    bootstrap_collection,
    tenant_section_filter,
)

__all__ = [
    "Base",
    "Document",
    "Section",
    "ErasureOutbox",
    "INGEST_STATUS_VALUES",
    "RESIDENCY_REGION_VALUES",
    "COLLECTION_NAME",
    "VECTOR_SIZE",
    "BootstrapResult",
    "bootstrap_collection",
    "tenant_section_filter",
]
