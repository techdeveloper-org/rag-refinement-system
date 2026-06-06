"""TOC extraction tests for STORY-009 (Scenarios A/B/C, AC-002).

Asserts native-bookmark extraction (A), heuristic header detection with the
injectable LLM-refine hook (B), no-structure fallback (C), and that page ranges
are contiguous, non-overlapping, and end at total_pages.
"""

from __future__ import annotations

from ingestion.parser import ParsedDocument
from ingestion.toc_extractor import TocEntry, extract_toc


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
