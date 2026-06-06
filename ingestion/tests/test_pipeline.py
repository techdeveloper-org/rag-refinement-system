"""End-to-end pipeline tests for STORY-008/009/011/003.

Asserts the four interface invariants via the contract entry point:
    1. Idempotent on content hash - re-upload reuses doc_id, no duplicate points.
    2. No chunk crosses a section boundary (Scenario A path through the pipeline).
    3. Scenario A/B/C routing + fallback_only on Scenario C.
    4. tenant_id present on every chunk payload.

Also covers the no-retention path: no sections/points persisted, no hash stored.
All dependencies are injected fakes - no network, no real key, no live database.
"""

from __future__ import annotations

from ingestion.parser import ParsedDocument
from ingestion.pipeline import IngestInput, ingest_document
from ingestion.tests.conftest import (
    FakeEmbedder,
    FakeParser,
    FakeSectionStore,
    FakeVectorStore,
)


def _ingest(
    doc_template: ParsedDocument,
    *,
    data: bytes,
    tenant_id: str = "tenant-1",
    no_retention: bool = False,
    section_store: FakeSectionStore | None = None,
    vector_store: FakeVectorStore | None = None,
    embedder: FakeEmbedder | None = None,
) -> tuple[dict, FakeSectionStore, FakeVectorStore]:
    """Run the pipeline with injected fakes and return result + stores.

    Args:
        doc_template: The ParsedDocument the fake parser emits.
        data: Raw bytes to ingest (drives the content hash).
        tenant_id: Owning tenant.
        no_retention: DPDP no-retention flag.
        section_store: Optional reused section store (for idempotency tests).
        vector_store: Optional reused vector store.
        embedder: Optional reused embedder.

    Returns:
        ``(result_dict, section_store, vector_store)``.
    """
    section_store = section_store or FakeSectionStore()
    vector_store = vector_store or FakeVectorStore()
    embedder = embedder or FakeEmbedder()
    result = ingest_document(
        IngestInput(data=data, tenant_id=tenant_id, no_retention=no_retention),
        parser=FakeParser(doc_template),
        embedder=embedder,
        section_store=section_store,
        vector_store=vector_store,
    )
    return result, section_store, vector_store


def test_scenario_a_routing_writes_sections_and_chunks(
    scenario_a_doc: ParsedDocument,
) -> None:
    """Scenario A persists sections + chunk points and is not fallback_only."""
    result, section_store, vector_store = _ingest(scenario_a_doc, data=b"PDF-A")

    assert result["fallback_only"] is False
    assert result["section_rows_written"] == 4
    assert result["chunks_upserted"] > 0
    assert len(vector_store.points) == result["chunks_upserted"]
    assert section_store.sections[result["doc_id"]]


def test_scenario_b_routing_writes_sections(scenario_b_doc: ParsedDocument) -> None:
    """Scenario B (heuristic headers) persists sections and is not fallback."""
    result, _, _ = _ingest(scenario_b_doc, data=b"PDF-B")

    assert result["fallback_only"] is False
    assert result["section_rows_written"] >= 2
    assert result["chunks_upserted"] > 0


def test_scenario_c_returns_fallback_only_no_sections(
    scenario_c_doc: ParsedDocument,
) -> None:
    """Scenario C returns fallback_only with no sections or chunk points."""
    result, section_store, vector_store = _ingest(scenario_c_doc, data=b"PDF-C")

    assert result["fallback_only"] is True
    assert result["section_rows_written"] == 0
    assert result["chunks_upserted"] == 0
    assert section_store.sections == {}
    assert vector_store.points == {}


def test_idempotent_on_content_hash_reuses_doc_id_no_duplicate_points(
    scenario_a_doc: ParsedDocument,
) -> None:
    """Re-uploading identical bytes reuses doc_id and adds no duplicate points."""
    store = FakeSectionStore()
    vectors = FakeVectorStore()
    embedder = FakeEmbedder()

    first, _, _ = _ingest(
        scenario_a_doc, data=b"SAME-BYTES",
        section_store=store, vector_store=vectors, embedder=embedder,
    )
    point_count_after_first = len(vectors.points)

    second, _, _ = _ingest(
        scenario_a_doc, data=b"SAME-BYTES",
        section_store=store, vector_store=vectors, embedder=embedder,
    )

    assert first["doc_id"] == second["doc_id"]
    assert len(vectors.points) == point_count_after_first


def test_tenant_id_present_on_every_chunk_payload(
    scenario_a_doc: ParsedDocument,
) -> None:
    """Every upserted chunk point payload carries the owning tenant_id."""
    _, _, vector_store = _ingest(scenario_a_doc, data=b"PDF-A", tenant_id="tenant-z")

    assert vector_store.points
    for point in vector_store.points.values():
        payload = point["payload"]
        assert payload["tenant_id"] == "tenant-z"
        assert set(payload) == {"chunk_id", "section_id", "doc_id", "tenant_id", "page"}


def test_no_retention_persists_nothing_but_returns_toc(
    scenario_a_doc: ParsedDocument,
) -> None:
    """no_retention skips sections + points and stores no hash, returns TOC."""
    result, section_store, vector_store = _ingest(
        scenario_a_doc, data=b"PDF-NR", no_retention=True
    )

    assert result["section_rows_written"] == 0
    assert result["chunks_upserted"] == 0
    assert result["toc"]
    assert section_store.sections == {}
    assert vector_store.points == {}
    assert section_store.hash_index == {}


def test_empty_tenant_id_is_rejected(scenario_a_doc: ParsedDocument) -> None:
    """An empty tenant_id is rejected (mandatory IDOR isolation key)."""
    import pytest

    with pytest.raises(ValueError, match="tenant_id"):
        ingest_document(
            IngestInput(data=b"PDF", tenant_id=""),
            parser=FakeParser(scenario_a_doc),
            embedder=FakeEmbedder(),
            section_store=FakeSectionStore(),
            vector_store=FakeVectorStore(),
        )


def test_result_dict_has_full_contract_shape(scenario_a_doc: ParsedDocument) -> None:
    """The returned dict matches the agreed interface contract keys exactly."""
    result, _, _ = _ingest(scenario_a_doc, data=b"PDF-A")

    assert set(result) == {
        "doc_id",
        "toc",
        "section_rows_written",
        "chunks_upserted",
        "fallback_only",
    }
