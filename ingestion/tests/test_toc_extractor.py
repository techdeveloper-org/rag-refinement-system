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


def test_same_start_page_siblings_yield_valid_disjoint_ranges() -> None:
    """Two entries sharing a start page yield only valid, strictly disjoint ranges.

    FIX-1 regression: ``page_end = next_start - 1`` previously emitted an inverted
    range (``page_end < page_start``) for the earlier same-start sibling, violating
    the Postgres ``sections_page_range_valid`` CHECK and the backend ``Field(ge=1)``
    page bounds. The shared-start sibling is now dropped, so every emitted range is
    valid (``page_start <= page_end`` and ``page_start >= 1``) and disjoint -- no page
    index appears in two sections, and no inverted/zero range is produced.
    """
    raw = [(1, "A", 2), (1, "B", 2)]
    entries = _derive_page_ranges(raw, total_pages=3)

    assert len(entries) == 1, "the shared-start sibling must be dropped, not emitted"
    for entry in entries:
        assert entry.page_start >= 1
        assert entry.page_start <= entry.page_end
        assert entry.page_end <= 3

    claimed: set[int] = set()
    for entry in entries:
        pages = set(range(entry.page_start, entry.page_end + 1))
        assert claimed.isdisjoint(pages), "ranges overlap across sections"
        claimed |= pages

    assert entries[-1].page_end == 3, "last surviving entry must end at total_pages"


def test_cover_and_chapter_both_on_page_one_no_zero_page_end() -> None:
    """Cover + chapter both starting on page 1 never yield ``page_end = 0``.

    FIX-1 regression: when two consecutive entries both start on page 1, the earlier
    one previously received ``page_end = 1 - 1 = 0``, violating both page CHECK
    constraints. The earlier same-start entry is dropped, so no zero/invalid range
    is emitted and the surviving entry still ends at total_pages.
    """
    raw = [(1, "Cover", 1), (1, "Chapter 1", 1)]
    entries = _derive_page_ranges(raw, total_pages=5)

    assert len(entries) == 1
    for entry in entries:
        assert entry.page_end >= 1, "no entry may have page_end == 0"
        assert entry.page_start >= 1
        assert entry.page_start <= entry.page_end
    assert entries[-1].page_end == 5


def test_same_start_page_siblings_produce_no_duplicate_chunks() -> None:
    """Same-start-page siblings do not chunk the shared page into two sections.

    FIX-1 end-to-end: with the shared-start sibling dropped, no section carries an
    invalid range and page 2's content is chunked under exactly one section, so there
    is no duplicate chunk text across sections and nothing invalid would be persisted.
    """
    pages = tuple(
        Page(number=n, text=" ".join(f"w{n}_{i}" for i in range(120)), blocks=())
        for n in range(1, 4)
    )
    doc = ParsedDocument(page_count=3, pages=pages, native_toc=(), content_hash="")
    entries = _derive_page_ranges([(1, "A", 2), (1, "B", 2)], total_pages=3)
    sections = [(f"sec_{i}", entry) for i, entry in enumerate(entries)]

    for entry in entries:
        assert entry.page_start <= entry.page_end
        assert entry.page_start >= 1

    chunks = chunk_document(doc, sections, doc_id="doc_x", tenant_id="t1")

    texts_by_section: dict[str, list[str]] = {}
    for chunk in chunks:
        texts_by_section.setdefault(chunk.section_id, []).append(chunk.text)
    all_texts = [t for texts in texts_by_section.values() for t in texts]
    assert len(all_texts) == len(set(all_texts)), "duplicate chunk text across sections"
