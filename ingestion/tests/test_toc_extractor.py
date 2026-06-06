"""TOC extraction tests for STORY-009 (Scenarios A/B/C, AC-002).

Asserts native-bookmark extraction (A), heuristic header detection with the
injectable LLM-refine hook (B), no-structure fallback (C), and that page ranges
are contiguous, non-overlapping, and end at total_pages.
"""

from __future__ import annotations

from ingestion.chunker import chunk_document
from ingestion.parser import Page, ParsedDocument
from ingestion.toc_extractor import TocEntry, _derive_page_ranges, extract_toc


def test_scenario_a_uses_native_bookmarks(scenario_a_doc: ParsedDocument) -> None:
    """Native bookmarks route to Scenario A with correct level/title/pages."""
    result = extract_toc(scenario_a_doc)

    assert result.scenario == "A"
    assert result.fallback_only is False
    titles = [entry.title for entry in result.entries]
    assert titles == ["Introduction", "Methods", "Data Collection", "Conclusion"]


def test_scenario_a_page_ranges_contiguous_and_end_at_total(
    scenario_a_doc: ParsedDocument,
) -> None:
    """Scenario A page ranges are contiguous and the last ends at total_pages."""
    result = extract_toc(scenario_a_doc)
    entries = result.entries

    for current, following in zip(entries, entries[1:], strict=False):
        assert current.page_end == following.page_start - 1
    assert entries[-1].page_end == scenario_a_doc.page_count
    for entry in entries:
        assert entry.page_start <= entry.page_end


def test_scenario_b_detects_heuristic_headers(scenario_b_doc: ParsedDocument) -> None:
    """No bookmarks but large/bold headers route to Scenario B with sections."""
    result = extract_toc(scenario_b_doc)

    assert result.scenario == "B"
    assert result.fallback_only is False
    assert len(result.entries) >= 2
    assert result.entries[-1].page_end == scenario_b_doc.page_count


def test_scenario_b_llm_refiner_hook_is_applied(scenario_b_doc: ParsedDocument) -> None:
    """The injectable LLM refiner can rewrite Scenario B candidate titles."""

    class UppercasingRefiner:
        """Test refiner that uppercases each candidate title."""

        def refine(self, candidates: tuple[TocEntry, ...]) -> tuple[TocEntry, ...]:
            """Return candidates with uppercased titles, ranges unchanged."""
            return tuple(
                TocEntry(
                    level=entry.level,
                    title=entry.title.upper(),
                    page_start=entry.page_start,
                    page_end=entry.page_end,
                )
                for entry in candidates
            )

    result = extract_toc(scenario_b_doc, llm_refiner=UppercasingRefiner())

    assert result.scenario == "B"
    assert all(entry.title == entry.title.upper() for entry in result.entries)


def test_scenario_c_returns_fallback_only(scenario_c_doc: ParsedDocument) -> None:
    """No bookmarks and no header signal route to Scenario C fallback_only."""
    result = extract_toc(scenario_c_doc)

    assert result.scenario == "C"
    assert result.fallback_only is True
    assert result.entries == ()


def test_same_start_page_siblings_yield_disjoint_ranges() -> None:
    """Two entries sharing a start page produce strictly non-overlapping ranges.

    FIX-4: ``page_end = max(start, next_start - 1)`` previously let entry A=[2,2]
    and B=[2,3] both include page 2 (duplicate content). With disjoint ranges, the
    shared-start entry claims no exclusive page (inverted/empty range) so no page
    index appears in two sections.
    """
    raw = [(1, "A", 2), (1, "B", 2)]
    entries = _derive_page_ranges(raw, total_pages=3)

    a_pages = set(range(entries[0].page_start, entries[0].page_end + 1))
    b_pages = set(range(entries[1].page_start, entries[1].page_end + 1))
    assert a_pages.isdisjoint(b_pages), (
        f"ranges overlap: A={a_pages}, B={b_pages}"
    )
    assert entries[1].page_start == 2
    assert entries[1].page_end == 3


def test_same_start_page_siblings_produce_no_duplicate_chunks() -> None:
    """Same-start-page siblings do not chunk the shared page into two sections.

    FIX-4: end-to-end check that the inverted (empty) range of the shared-start
    sibling yields zero chunks, so page 2's content is chunked under exactly one
    section -- no duplicate chunk text across the two sections.
    """
    pages = tuple(
        Page(number=n, text=" ".join(f"w{n}_{i}" for i in range(120)), blocks=())
        for n in range(1, 4)
    )
    doc = ParsedDocument(page_count=3, pages=pages, native_toc=(), content_hash="")
    entries = _derive_page_ranges([(1, "A", 2), (1, "B", 2)], total_pages=3)
    sections = [(f"sec_{i}", entry) for i, entry in enumerate(entries)]

    chunks = chunk_document(doc, sections, doc_id="doc_x", tenant_id="t1")

    texts_by_section: dict[str, list[str]] = {}
    for chunk in chunks:
        texts_by_section.setdefault(chunk.section_id, []).append(chunk.text)
    all_texts = [t for texts in texts_by_section.values() for t in texts]
    assert len(all_texts) == len(set(all_texts)), "duplicate chunk text across sections"
