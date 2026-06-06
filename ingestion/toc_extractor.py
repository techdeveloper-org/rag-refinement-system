"""TOC extraction across the three ingestion scenarios (STORY-009, FR-002).

Resolves a document's table of contents into authoritative, contiguous,
non-overlapping page ranges - the section interval map the chunker and router
depend on (toc-dsa-delta, AC-002). Three scenarios are supported:

    * Scenario A - native bookmarks: PyMuPDF ``get_toc()`` yields ``(level,
      title, page)`` triples directly (ADR-4, highest coverage, lowest risk).
    * Scenario B - heuristic headers: when there are no bookmarks, detect headers
      from per-block font size / weight / position, optionally refined by a
      pluggable LLM hook, producing a pseudo-TOC.
    * Scenario C - none detected: neither bookmarks nor confident headers exist;
      the document is returned ``fallback_only=True`` (whole-document RAG path).

Page-end derivation is identical in A and B: a section ends one page before the
next sibling's start, and the last section ends at ``total_pages`` (toc-dsa-delta).
TOC entries are structural metadata (titles + page numbers), never PII.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ingestion.parser import ParsedDocument


@dataclass(frozen=True)
class TocEntry:
    """A resolved TOC entry with an authoritative inclusive page range.

    Attributes:
        level: Hierarchy level (1 = top, 2 = sub, ...).
        title: Section heading text (structural metadata, not PII).
        page_start: One-based first page of the section (inclusive).
        page_end: One-based last page of the section (inclusive).
    """

    level: int
    title: str
    page_start: int
    page_end: int


@dataclass(frozen=True)
class TocResult:
    """Outcome of TOC extraction for one document.

    Attributes:
        entries: Resolved TOC entries (empty when ``fallback_only``).
        scenario: One of ``"A"``, ``"B"``, ``"C"`` recording the route taken.
        fallback_only: True when no structure was found (Scenario C); the
            document must use whole-document RAG and persist no sections.
    """

    entries: tuple[TocEntry, ...]
    scenario: str
    fallback_only: bool


@runtime_checkable
class LlmRefiner(Protocol):
    """Injectable LLM-refine hook for Scenario B heuristic headers.

    A refiner receives the candidate heuristic entries and returns a possibly
    improved set (de-noised titles, corrected levels). The interface only is
    specified here; production wiring and tests inject concrete implementations.
    """

    def refine(self, candidates: tuple[TocEntry, ...]) -> tuple[TocEntry, ...]:
        """Refine candidate heuristic TOC entries.

        Args:
            candidates: Heuristically detected entries (page ranges already set).

        Returns:
            A refined tuple of entries; page ranges are re-derived by the caller
            so a refiner need not keep them contiguous.
        """
        ...


_MIN_HEADER_SIZE_RATIO: float = 1.15
"""A block is a header candidate when its font size exceeds the body median by this ratio."""


def _derive_page_ranges(
    raw: list[tuple[int, str, int]], total_pages: int
) -> tuple[TocEntry, ...]:
    """Turn ``(level, title, page_start)`` triples into contiguous page ranges.

    Each section ends one page before the next entry's start; the final section
    ends at ``total_pages`` (toc-dsa-delta). Triples are assumed in document
    order and clamped so ``1 <= page_start <= page_end <= total_pages``.

    Args:
        raw: Ordered ``(level, title, page_start)`` triples.
        total_pages: Total page count (used for the last section's end).

    Returns:
        Resolved TocEntry tuple with non-overlapping, contiguous page ranges.
    """
    entries: list[TocEntry] = []
    count = len(raw)
    for index, (level, title, page_start) in enumerate(raw):
        start = max(1, min(page_start, total_pages))
        if index + 1 < count:
            next_start = max(1, min(raw[index + 1][2], total_pages))
            page_end = max(start, next_start - 1)
        else:
            page_end = total_pages
        entries.append(
            TocEntry(
                level=max(1, int(level)),
                title=str(title).strip(),
                page_start=start,
                page_end=page_end,
            )
        )
    return tuple(entries)


def _extract_native(doc: ParsedDocument) -> tuple[TocEntry, ...]:
    """Resolve Scenario A entries from the native bookmark TOC.

    Args:
        doc: Parsed document carrying ``native_toc`` bookmark triples.

    Returns:
        Resolved TocEntry tuple, or empty when there are no bookmarks.
    """
    if not doc.native_toc:
        return ()
    raw = [(level, title, page) for level, title, page in doc.native_toc]
    return _derive_page_ranges(raw, doc.page_count)


def _median(values: list[float]) -> float:
    """Return the median of a non-empty list of floats.

    Args:
        values: Numeric values.

    Returns:
        Median value, or 0.0 when the list is empty.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _detect_headers(doc: ParsedDocument) -> tuple[TocEntry, ...]:
    """Heuristically detect headers from block typography (Scenario B).

    A block is treated as a header when its font size meaningfully exceeds the
    document's body-text median size, or when it is bold and short. The first
    detected header per page anchors a pseudo-section starting at that page.

    Args:
        doc: Parsed document with per-block font/size/position features.

    Returns:
        Resolved heuristic TocEntry tuple (page ranges derived), or empty when
        no confident header is found.
    """
    sizes = [block.font_size for page in doc.pages for block in page.blocks]
    body_median = _median(sizes)
    threshold = body_median * _MIN_HEADER_SIZE_RATIO
    raw: list[tuple[int, str, int]] = []
    for page in doc.pages:
        for block in page.blocks:
            is_large = body_median > 0 and block.font_size >= threshold
            is_short_bold = block.is_bold and len(block.text) <= 80
            if is_large or is_short_bold:
                level = 1 if (body_median > 0 and block.font_size >= body_median * 1.4) else 2
                raw.append((level, block.text, page.number))
                break
    if not raw:
        return ()
    return _derive_page_ranges(raw, doc.page_count)


def extract_toc(
    doc: ParsedDocument, llm_refiner: LlmRefiner | None = None
) -> TocResult:
    """Extract a TOC for a parsed document across Scenarios A / B / C.

    Routing:
        1. Native bookmarks present -> Scenario A.
        2. Else heuristic headers (optionally LLM-refined) -> Scenario B.
        3. Else nothing detected -> Scenario C (``fallback_only=True``).

    Args:
        doc: Parsed document.
        llm_refiner: Optional injectable hook applied to Scenario B candidates
            before page ranges are re-derived.

    Returns:
        A TocResult with resolved entries and the chosen scenario.
    """
    native = _extract_native(doc)
    if native:
        return TocResult(entries=native, scenario="A", fallback_only=False)

    heuristic = _detect_headers(doc)
    if heuristic:
        if llm_refiner is not None:
            refined = llm_refiner.refine(heuristic)
            raw = [(e.level, e.title, e.page_start) for e in refined]
            heuristic = _derive_page_ranges(raw, doc.page_count)
        if heuristic:
            return TocResult(entries=heuristic, scenario="B", fallback_only=False)

    return TocResult(entries=(), scenario="C", fallback_only=True)
