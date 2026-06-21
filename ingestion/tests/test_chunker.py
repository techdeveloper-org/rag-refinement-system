"""Section-aware chunking tests for STORY-011 (P0-risk, AC-003).

Asserts the hard invariants: no chunk crosses a section boundary, chunking is
deterministic (stable chunk ids), chunk sizes respect the token bounds, and
every chunk carries section_id + tenant_id.
"""

from __future__ import annotations

from ingestion.chunker import (
    MAX_CHUNK_TOKENS,
    chunk_document,
    chunk_section,
)
from ingestion.parser import ParsedDocument
from ingestion.toc_extractor import TocEntry, extract_toc


def _sections(doc: ParsedDocument) -> list[tuple[str, TocEntry]]:
    """Build ``(section_id, entry)`` pairs from a document's TOC.

    Args:
        doc: Parsed document with detectable structure.

    Returns:
        Section-id-to-entry pairs for chunking.
    """
    result = extract_toc(doc)
    return [(f"sec-{i}", entry) for i, entry in enumerate(result.entries)]


def test_no_chunk_crosses_a_section_boundary(scenario_a_doc: ParsedDocument) -> None:
    """Every chunk's page lies inside exactly one section's page range."""
    sections = _sections(scenario_a_doc)
    section_by_id = {sid: entry for sid, entry in sections}

    chunks = chunk_document(scenario_a_doc, sections, doc_id="doc-1", tenant_id="t1")

    assert chunks
    for chunk in chunks:
        entry = section_by_id[chunk.section_id]
        assert entry.page_start <= chunk.page <= entry.page_end


def test_chunking_is_deterministic_stable_ids(scenario_a_doc: ParsedDocument) -> None:
    """Re-chunking identical input yields identical ordered chunk ids."""
    sections = _sections(scenario_a_doc)

    first = chunk_document(scenario_a_doc, sections, doc_id="doc-1", tenant_id="t1")
    second = chunk_document(scenario_a_doc, sections, doc_id="doc-1", tenant_id="t1")

    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]


def test_every_chunk_has_section_id_and_tenant_id(scenario_a_doc: ParsedDocument) -> None:
    """Every chunk carries a non-empty section_id and the owning tenant_id."""
    sections = _sections(scenario_a_doc)

    chunks = chunk_document(scenario_a_doc, sections, doc_id="doc-1", tenant_id="tenant-x")

    assert chunks
    for chunk in chunks:
        assert chunk.section_id
        assert chunk.tenant_id == "tenant-x"


def test_chunk_size_respects_max_token_bound(scenario_a_doc: ParsedDocument) -> None:
    """No chunk exceeds the maximum token budget."""
    sections = _sections(scenario_a_doc)

    chunks = chunk_document(scenario_a_doc, sections, doc_id="doc-1", tenant_id="t1")

    for chunk in chunks:
        assert chunk.token_count <= MAX_CHUNK_TOKENS


def test_section_with_no_pages_produces_no_chunks(scenario_a_doc: ParsedDocument) -> None:
    """A section pointing at an empty page range yields zero chunks, no error."""
    result = extract_toc(scenario_a_doc)
    entry = result.entries[0]
    empty = type(entry)(level=entry.level, title=entry.title, page_start=99, page_end=99)

    chunks = chunk_section(scenario_a_doc, empty, doc_id="doc-1", tenant_id="t1")

    assert chunks == []
