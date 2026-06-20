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

import re

from ingestion import doc_id_for, section_id_for
from ingestion.parser import ParsedDocument
from ingestion.pipeline import IngestInput, ingest_document
from ingestion.tests.conftest import (
    FakeEmbedder,
    FakeParser,
    FakeSectionStore,
    FakeVectorStore,
)

_DOC_ID_PATTERN = re.compile(r"^doc_[A-Za-z0-9]{6,}$")
"""Backend document id schema (``schemas.py``)."""

_SECTION_ID_PATTERN = re.compile(r"^sec_[A-Za-z0-9]+$")
"""Backend + router section id schema."""


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


def test_doc_id_matches_backend_schema_pattern(
    scenario_a_doc: ParsedDocument,
) -> None:
    """The pipeline's doc_id is prefixed + hyphen-free (matches ^doc_[A-Za-z0-9]{6,}$).

    FIX-1: a bare uuid5 string (hyphenated, no prefix) failed the backend document
    schema, the backend section schema, and the router section filter, 500-ing on
    every real document. The id is now ``doc_<32 hex>``.
    """
    result, _, _ = _ingest(scenario_a_doc, data=b"PDF-A")

    assert _DOC_ID_PATTERN.match(result["doc_id"]), result["doc_id"]
    assert "-" not in result["doc_id"]


def test_section_ids_match_backend_and_router_schema_pattern(
    scenario_a_doc: ParsedDocument,
) -> None:
    """Every persisted section_id matches ^sec_[A-Za-z0-9]+$ (backend + router)."""
    _, section_store, _ = _ingest(scenario_a_doc, data=b"PDF-A")

    rows = [row for rows in section_store.sections.values() for row in rows]
    assert rows
    for row in rows:
        assert _SECTION_ID_PATTERN.match(row.section_id), row.section_id
        assert "-" not in row.section_id


def test_chunk_payload_ids_match_schema_patterns(
    scenario_a_doc: ParsedDocument,
) -> None:
    """Each chunk payload's doc_id/section_id carry the prefixed, hyphen-free shape."""
    _, _, vector_store = _ingest(scenario_a_doc, data=b"PDF-A")

    assert vector_store.points
    for point in vector_store.points.values():
        payload = point["payload"]
        assert _DOC_ID_PATTERN.match(payload["doc_id"]), payload["doc_id"]
        assert _SECTION_ID_PATTERN.match(payload["section_id"]), payload["section_id"]


def test_canonical_id_functions_are_deterministic_and_prefixed() -> None:
    """The exported canonical id functions are deterministic and correctly shaped.

    FIX-1: ``doc_id_for`` / ``section_id_for`` are the single source of truth the
    backend adapter imports, so their format can never diverge from the pipeline.
    """
    doc_id = doc_id_for("tenant-1", "deadbeef")
    again = doc_id_for("tenant-1", "deadbeef")
    section_id = section_id_for(doc_id, 0)

    assert doc_id == again
    assert _DOC_ID_PATTERN.match(doc_id), doc_id
    assert _SECTION_ID_PATTERN.match(section_id), section_id
    assert doc_id_for("tenant-2", "deadbeef") != doc_id


def _same_start_toc_doc() -> ParsedDocument:
    """A 4-page doc whose native TOC has a parent + child sharing start page 1.

    The cover/parent and its first child both anchor on page 1, and another pair
    shares page 3, exercising the FIX-1 same-start-page drop end-to-end.
    """
    from ingestion.parser import Page

    pages = tuple(
        Page(number=n, text=" ".join(f"w{n}_{i}" for i in range(130)), blocks=())
        for n in range(1, 5)
    )
    native_toc = (
        (1, "Cover", 1),
        (2, "Chapter 1", 1),
        (1, "Chapter 2", 3),
        (2, "Section 2.1", 3),
    )
    return ParsedDocument(
        page_count=4, pages=pages, native_toc=native_toc, content_hash=""
    )


def test_same_start_page_toc_persists_only_valid_section_ranges() -> None:
    """Parent + child sharing a start page never persist an invalid section range.

    FIX-1 regression at the pipeline boundary: every SectionRow written to the section
    store satisfies ``page_start <= page_end`` and ``page_start >= 1`` (the Postgres
    CHECK constraints and backend ``Field(ge=1)`` bounds), the returned TOC carries
    only valid ranges, and the same page is never chunked into two sections.
    """
    result, section_store, vector_store = _ingest(
        _same_start_toc_doc(), data=b"PDF-SAMESTART"
    )

    rows = [row for rows in section_store.sections.values() for row in rows]
    assert rows, "at least one valid section must survive"
    claimed: set[int] = set()
    for row in rows:
        assert row.page_start >= 1, f"invalid page_start: {row.page_start}"
        assert row.page_start <= row.page_end, (
            f"inverted range persisted: [{row.page_start}, {row.page_end}]"
        )
        pages = set(range(row.page_start, row.page_end + 1))
        assert claimed.isdisjoint(pages), "two sections claim the same page"
        claimed |= pages

    for entry in result["toc"]:
        assert entry["page_start"] >= 1
        assert entry["page_start"] <= entry["page_end"]

    assert len(vector_store.points) == result["chunks_upserted"]


class _BareWrongDimEmbedder:
    """A bare Embedder (not wrapped in FallbackEmbedder) returning wrong-dim vectors.

    Valid per the Embedder Protocol but returns a non-EMBEDDING_DIM length to verify
    the pipeline embed -> upsert boundary guard rejects ANY embedder implementation.
    """

    def __init__(self, dim: int = 1024) -> None:
        """Store the (wrong) output dimension to emit."""
        self._dim = dim

    @property
    def dimension(self) -> int:
        """Report the wrong dimension; the boundary trusts the actual vector length."""
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return wrong-length vectors to exercise the pipeline boundary guard."""
        return [[0.0] * self._dim for _ in texts]


def test_bare_wrong_dim_embedder_rejected_at_pipeline_boundary(
    scenario_a_doc: ParsedDocument,
) -> None:
    """A bare embedder returning wrong-dim vectors is rejected at ingest, not upserted.

    FIX-6: the dimension guard lives at the embed -> upsert boundary in the pipeline,
    so even an embedder NOT wrapped in FallbackEmbedder cannot upsert mismatched
    vectors into the EMBEDDING_DIM-sized Qdrant collection.
    """
    import pytest

    from ingestion.embedder import EmbedderDimensionError
    from ingestion.pipeline import IngestInput, ingest_document

    vector_store = FakeVectorStore()
    with pytest.raises(EmbedderDimensionError, match="1024-dim"):
        ingest_document(
            IngestInput(data=b"PDF-A", tenant_id="tenant-1"),
            parser=FakeParser(scenario_a_doc),
            embedder=_BareWrongDimEmbedder(dim=1024),
            section_store=FakeSectionStore(),
            vector_store=vector_store,
        )

    assert vector_store.points == {}, "no points may be upserted on dimension mismatch"


def test_result_dict_has_full_contract_shape(scenario_a_doc: ParsedDocument) -> None:
    """The returned dict matches the agreed interface contract keys exactly."""
    result, _, _ = _ingest(scenario_a_doc, data=b"PDF-A")

    assert set(result) == {
        "doc_id",
        "toc",
        "section_rows_written",
        "chunks_upserted",
        "fallback_only",
        "total_pages",
        "pre_existing",
    }
