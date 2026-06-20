"""TOC extraction tests for STORY-009 (Scenarios A/B/C, AC-002).

Asserts native-bookmark extraction (A), heuristic header detection with the
injectable LLM-refine hook (B), no-structure fallback (C), and that page ranges
are contiguous, non-overlapping, and end at total_pages.
"""

from __future__ import annotations

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


def test_distinct_titles_sharing_one_start_page_degrade_to_fallback() -> None:
    """Distinct titles that all collapse onto one start page degrade to fallback (ING-A2).

    Two distinct titles both anchored at page 2 carry no usable structure: only one
    section would survive, so emitting it as one giant range spanning the whole
    document would destroy section-level routing granularity and mislead the router.
    Per ING-A2 the page-range derivation reports the degenerate structure by returning
    no entries, so the extractor falls back to whole-document search rather than
    emitting a single misleading section. No inverted/zero range is ever produced.
    """
    raw = [(1, "A", 2), (1, "B", 2)]
    entries = _derive_page_ranges(raw, total_pages=3)

    assert entries == (), "degenerate same-start structure must yield no sections"


def test_cover_and_chapter_both_on_page_one_degrade_to_fallback() -> None:
    """Cover + chapter both on page 1 degrade to fallback, never a zero page_end (ING-A2).

    Two distinct titles both anchored at page 1 are structurally useless: rather than
    drop one and emit the survivor as a single whole-document section (which would
    mislead the router), the derivation reports the degenerate structure by returning
    no entries so the caller takes the no-structure path. No entry with
    ``page_end == 0`` or any other invalid range is ever emitted.
    """
    raw = [(1, "Cover", 1), (1, "Chapter 1", 1)]
    entries = _derive_page_ranges(raw, total_pages=5)

    assert entries == (), "degenerate single-page structure must yield no sections"


def test_all_entries_anchored_page_one_yield_fallback_only() -> None:
    """A native TOC whose entries all anchor page 1 yields fallback_only (ING-A2).

    A mis-paginated PDF whose bookmarks all point at page 1 carries multiple distinct
    titles but no usable page structure. The extractor must degrade to the
    no-structure path (Scenario C, ``fallback_only=True``) so the router falls back to
    full-document search, rather than emitting one giant section spanning the whole
    document and destroying routing granularity.
    """
    pages = tuple(
        Page(number=n, text=" ".join(f"w{n}_{i}" for i in range(120)), blocks=())
        for n in range(1, 4)
    )
    native_toc = ((1, "Cover", 1), (1, "Chapter 1", 1), (1, "Chapter 2", 1))
    doc = ParsedDocument(
        page_count=3, pages=pages, native_toc=native_toc, content_hash=""
    )

    result = extract_toc(doc)

    assert result.fallback_only is True
    assert result.scenario == "C"
    assert result.entries == ()


def test_out_of_order_raw_toc_keeps_content_and_leaves_no_gap() -> None:
    """An out-of-order raw TOC keeps every distinct-start section with no coverage gap.

    ING-A1: a legitimately earlier-page section appearing after a later-page one
    (``[(1, "A", 5), (1, "B", 2)]``) must be reordered by the stable-sort survivor
    filter, not dropped. All distinct-start sections survive with valid, strictly
    disjoint ranges; coverage is contiguous from page 1 to ``total_pages`` so no page
    is left uncovered. This is a genuinely multi-section document (distinct start
    pages), so it does NOT degrade to fallback.
    """
    raw = [(1, "A", 5), (1, "B", 2)]
    entries = _derive_page_ranges(raw, total_pages=8)

    titles = {entry.title for entry in entries}
    assert titles == {"A", "B"}, "no distinct-start section may be dropped"

    starts = [entry.page_start for entry in entries]
    assert starts == sorted(starts), "sections must be reordered by start page"

    covered: list[int] = []
    for entry in entries:
        assert entry.page_start >= 1
        assert entry.page_start <= entry.page_end
        assert entry.page_end <= 8
        covered.extend(range(entry.page_start, entry.page_end + 1))

    assert covered == sorted(set(covered)), "ranges overlap across sections"
    assert covered == list(range(2, 9)), "coverage must be contiguous with no gap"
    assert entries[-1].page_end == 8, "last section must end at total_pages"
