"""Bootstrap tests for STORY-002 - no live Qdrant required.

A lightweight fake Qdrant client records the create/index calls so the tests can
assert: idempotent create-if-absent, vector size 1536 + Cosine (ADR-6), payload
indexes on section_id / doc_id / tenant_id, the exact payload shape, and the
mandatory tenant_id isolation filter (IDOR guard).
"""

from __future__ import annotations

import pytest
from qdrant_client import models as qm

from db.qdrant_bootstrap import (
    COLLECTION_NAME,
    PAYLOAD_INDEX_FIELDS,
    PAYLOAD_KEYS,
    VECTOR_SIZE,
    bootstrap_collection,
    tenant_section_filter,
    vectors_config,
)


class FakeQdrantClient:
    """Minimal in-memory stand-in for QdrantClient used in bootstrap tests.

    Records collection creation and payload-index calls and simulates an already
    existing collection so idempotency can be asserted without a live service.
    """

    def __init__(self, existing: bool = False) -> None:
        """Initialise the fake.

        Args:
            existing: When True, ``collection_exists`` reports the collection as
                already present so creation is skipped.
        """
        self._existing = existing
        self.created_collections: list[dict] = []
        self.payload_indexes: list[str] = []

    def collection_exists(self, collection_name: str) -> bool:
        """Return whether the collection is considered to already exist."""
        return self._existing

    def create_collection(
        self, collection_name: str, vectors_config: qm.VectorParams
    ) -> None:
        """Record a create-collection call and mark the collection present."""
        self.created_collections.append(
            {"name": collection_name, "vectors_config": vectors_config}
        )
        self._existing = True

    def create_payload_index(
        self,
        collection_name: str,
        field_name: str,
        field_schema: qm.PayloadSchemaType,
    ) -> None:
        """Record a payload-index call for ``field_name``."""
        self.payload_indexes.append(field_name)


def test_vector_size_matches_embedding_model() -> None:
    """Vector size is 1536 and distance is Cosine (text-embedding-3-small)."""
    cfg = vectors_config()
    assert VECTOR_SIZE == 1536
    assert cfg.size == 1536
    assert cfg.distance == qm.Distance.COSINE


def test_collection_created_when_absent() -> None:
    """Bootstrap creates the collection with the correct config when absent."""
    client = FakeQdrantClient(existing=False)
    result = bootstrap_collection(client)  # type: ignore[arg-type]
    assert result.created is True
    assert len(client.created_collections) == 1
    created = client.created_collections[0]
    assert created["name"] == COLLECTION_NAME
    assert created["vectors_config"].size == 1536
    assert created["vectors_config"].distance == qm.Distance.COSINE


def test_collection_created_idempotent() -> None:
    """Bootstrap skips creation when the collection already exists."""
    client = FakeQdrantClient(existing=True)
    result = bootstrap_collection(client)  # type: ignore[arg-type]
    assert result.created is False
    assert client.created_collections == []


def test_payload_index_on_section_id_doc_id_and_tenant_id() -> None:
    """Payload indexes are ensured on section_id, doc_id and tenant_id."""
    client = FakeQdrantClient(existing=False)
    bootstrap_collection(client)  # type: ignore[arg-type]
    assert set(client.payload_indexes) == set(PAYLOAD_INDEX_FIELDS)
    assert "tenant_id" in client.payload_indexes
    assert "section_id" in client.payload_indexes
    assert "doc_id" in client.payload_indexes


def test_payload_shape_matches_agreed_contract() -> None:
    """The declared payload keys are exactly the AGREED CONTRACT set."""
    assert set(PAYLOAD_KEYS) == {
        "chunk_id",
        "section_id",
        "doc_id",
        "page",
        "tenant_id",
    }


def test_tenant_filter_is_mandatory() -> None:
    """An empty tenant_id is rejected - tenant scoping is never optional."""
    with pytest.raises(ValueError):
        tenant_section_filter("", ["sec_a"])


def test_tenant_section_filter_encodes_tenant_and_sections() -> None:
    """The retrieval filter ANDs tenant_id equality with section_id IN (...)."""
    flt = tenant_section_filter("tenant_42", ["sec_a", "sec_b"])
    keys = {cond.key for cond in flt.must}  # type: ignore[union-attr]
    assert keys == {"tenant_id", "section_id"}

    tenant_cond = next(c for c in flt.must if c.key == "tenant_id")  # type: ignore[union-attr]
    assert tenant_cond.match.value == "tenant_42"  # type: ignore[union-attr]

    section_cond = next(c for c in flt.must if c.key == "section_id")  # type: ignore[union-attr]
    assert set(section_cond.match.any) == {"sec_a", "sec_b"}  # type: ignore[union-attr]


def test_filter_isolates_by_tenant_id() -> None:
    """Two tenants produce distinct, non-overlapping tenant guards."""
    a = tenant_section_filter("tenant_a", ["sec_x"])
    b = tenant_section_filter("tenant_b", ["sec_x"])
    a_tenant = next(c for c in a.must if c.key == "tenant_id").match.value  # type: ignore[union-attr]
    b_tenant = next(c for c in b.must if c.key == "tenant_id").match.value  # type: ignore[union-attr]
    assert a_tenant != b_tenant
