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
Raw triples are STABLE-sorted by clamped page_start ascending before survivor
selection (ING-A1), so an out-of-order raw TOC (a legitimately earlier-page section
appearing after a later-page one) is reordered rather than dropped; only true
same-start duplicates are dropped. An entry whose computed span would be non-positive
is never emitted, so every resolved range is both disjoint and valid
(``1 <= page_start <= page_end <= total_pages``). The shared page's content is still
chunked under the sibling that actually spans it, so dropping loses no content.

When the page anchors carry no usable structure - more than one distinct raw title
but every entry collapses onto a single surviving start page (ING-A2, e.g. a
mis-paginated PDF whose bookmarks all anchor page 1) - emitting one giant section
would destroy section-level routing granularity and mislead the router. In that
degenerate case the extractor degrades to the no-structure path (Scenario C,
``fallback_only=True``) instead of emitting a single misleading section. TOC entries
are structural metadata (titles + page numbers), never PII.
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


def _select_survivors(
    raw: list[tuple[int, str, int]], bounded_total: int
) -> list[tuple[int, str, int]]:
    """Stable-sort raw triples by clamped start, then drop same-start duplicates.

    Clamps each start to ``1 <= start <= bounded_total``, then STABLE-sorts by the
    clamped start ascending (preserving original order for equal starts) so an
    out-of-order raw TOC is reordered rather than having legitimately earlier-page
    sections dropped (ING-A1). Only the first entry at each distinct start page
    survives; later same-start entries (true duplicates) are dropped because they
    would receive a non-positive span.

    Args:
        raw: ``(level, title, page_start)`` triples (any order).
        bounded_total: Page count clamped to at least 1.

    Returns:
        Survivor triples with clamped, strictly-increasing start pages.
    """
    clamped = [
        (level, title, max(1, min(page_start, bounded_total)))
        for level, title, page_start in raw
    ]
    ordered = sorted(clamped, key=lambda triple: triple[2])
    survivors: list[tuple[int, str, int]] = []
    last_start: int | None = None
    for level, title, start in ordered:
        if last_start is None or start > last_start:
            survivors.append((level, title, start))
            last_start = start
    return survivors


def _is_degenerate_structure(
    raw: list[tuple[int, str, int]], survivors: list[tuple[int, str, int]]
) -> bool:
    """Report whether the page anchors carry no usable section structure (ING-A2).

    The structure is degenerate when the raw TOC names more than one distinct title
    yet every entry collapses onto a single surviving start page (e.g. a mis-paginated
    PDF whose bookmarks all anchor page 1). Emitting one section spanning the whole
    document would destroy routing granularity, so the caller degrades to the
    no-structure path (Scenario C) instead.

    Args:
        raw: The original ``(level, title, page_start)`` triples.
        survivors: The survivor triples from ``_select_survivors``.

    Returns:
        True when exactly one section would survive but the raw TOC carried multiple
        distinct titles, signalling the anchors are structurally useless.
    """
    distinct_titles = {str(title).strip() for _, title, _ in raw}
    return len(survivors) <= 1 and len(distinct_titles) > 1


def _derive_page_ranges(
    raw: list[tuple[int, str, int]], total_pages: int
) -> tuple[TocEntry, ...]:
    """Turn ``(level, title, page_start)`` triples into disjoint, valid page ranges.

    Each surviving section ends one page before the next surviving section's start;
    the final surviving section ends at ``total_pages`` (toc-dsa-delta). Triples are
    STABLE-sorted by clamped start before survivor selection, so out-of-order raw
    entries are reordered rather than dropped (ING-A1); each start is clamped so
    ``1 <= page_start <= total_pages``.

    An entry whose start page is not strictly greater than the previous surviving
    entry's start page (a same-start duplicate) would receive a non-positive span.
    Rather than emit such an inverted or zero range - which would violate the Postgres
    ``sections_page_range_valid`` / ``sections_page_start_positive`` CHECK constraints
    and the backend ``Field(ge=1)`` page bounds - the entry is dropped. The shared
    page's content is still chunked under the surviving sibling that spans it, so
    dropping loses no content while guaranteeing every emitted range satisfies
    ``1 <= page_start <= page_end <= total_pages`` and no page index appears twice.

    Args:
        raw: ``(level, title, page_start)`` triples (any order; reordered internally).
        total_pages: Total page count (used for the last section's end).

    Returns:
        Resolved TocEntry tuple with disjoint, always-valid page ranges. Empty when
        the structure is degenerate (ING-A2): more than one distinct raw title yet
        every entry collapses onto a single surviving start page. Emitting one giant
        section would destroy routing granularity, so the caller treats an empty
        result here as the no-structure path (Scenario C).
    """
    bounded_total = max(1, total_pages)
    survivors = _select_survivors(raw, bounded_total)

    if _is_degenerate_structure(raw, survivors):
        return ()

    entries: list[TocEntry] = []
    count = len(survivors)
    for index, (level, title, start) in enumerate(survivors):
        if index + 1 < count:
            page_end = survivors[index + 1][2] - 1
        else:
            page_end = bounded_total
        level_val = level if level else 1
        entries.append(
            TocEntry(
                level=max(1, int(level_val)),
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
            if body_median == 0.0:
                break
            is_large = body_median > 0 and block.font_size >= threshold
            is_short_bold = (
                block.is_bold and body_median > 0 and len(block.text) <= 80
            )
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
