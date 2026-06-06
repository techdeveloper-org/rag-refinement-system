"""Router adapter binding the ``router`` package to the backend Router Protocol.

The backend :class:`Router` Protocol takes ``(tenant_id, document_ids, query,
confidence_threshold, max_sections)`` and returns a :class:`RouterDecision`. The
``router`` package exposes ``route(query, doc_id, toc, *, tenant_id, ...)``
returning a serialized ``RouterOutput`` dict keyed by ``relevant_sections``,
``page_ranges``, ``confidence``, ``fallback``, ``routing_time_ms``, ``rationale``.

This adapter is the join the Phase C gate flagged as missing (FIX-C-01). For each
target document it loads the AUTHORITATIVE TOC from the structure store
(tenant-scoped via :class:`DocumentStore`), shapes it into the ``section_id`` +
page-range entries the router expects, and calls ``router.route`` so the router's
TOC-membership filter runs on the live path. Per ADV-006 multi-document routing is
routing-only: when ``document_ids`` has more than one entry the adapter fans out
one ``route`` call per document and merges the selected sections by descending
confidence, stamping each :class:`RoutedSection` with its owning ``document_id``.
The router never invokes the generation LLM.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

from backend.app.api.interfaces import (
    DocumentStore,
    RoutedSection,
    RouterDecision,
    SectionRecord,
)

RouteCallable = Callable[..., Awaitable[Mapping[str, Any]]]
"""Signature of ``router.route`` (kept injectable for offline tests)."""


def _merge_fairly(
    sections: list[RoutedSection], max_sections: int
) -> list[RoutedSection]:
    """Merge per-document routed sections fairly and deterministically (FIX-9).

    Every contributing document is represented before any document receives a
    second slot, then the remaining slots are filled by descending confidence.
    Ordering is fully deterministic (confidence desc, then ``document_id``, then
    ``section_id``) so the result never depends on the input document order, and a
    single saturating document cannot crowd out the others. Single-document
    routing is unchanged (plain confidence order).

    Args:
        sections: All routed sections across the target documents.
        max_sections: Maximum number of sections to return.

    Returns:
        The fairly merged, capped section list.
    """
    by_doc: dict[str, list[RoutedSection]] = {}
    for section in sections:
        by_doc.setdefault(section.document_id, []).append(section)
    for grouped in by_doc.values():
        grouped.sort(key=lambda s: (-s.confidence, s.section_id))
    representatives = [grouped[0] for grouped in by_doc.values()]
    remainder = [section for grouped in by_doc.values() for section in grouped[1:]]
    representatives.sort(key=lambda s: (-s.confidence, s.document_id, s.section_id))
    remainder.sort(key=lambda s: (-s.confidence, s.document_id, s.section_id))
    return (representatives + remainder)[:max_sections]


def _toc_from_sections(sections: Sequence[SectionRecord]) -> list[dict[str, Any]]:
    """Shape structure-store sections into the router's TOC entry list.

    Each entry carries the ``section_id`` (the universal join/filter key) and the
    authoritative page range plus title/level the router prompt uses.

    Args:
        sections: Tenant-scoped section records for one document.

    Returns:
        TOC entries as ``{section_id, title, level, page_start, page_end}`` dicts.
    """
    return [
        {
            "section_id": section.section_id,
            "title": section.title or "",
            "level": section.level,
            "page_start": section.page_start,
            "page_end": section.page_end,
        }
        for section in sections
    ]


def _routed_sections_from_output(
    output: Mapping[str, Any],
    toc_by_id: Mapping[str, SectionRecord],
    doc_id: str,
) -> list[RoutedSection]:
    """Build RoutedSection objects from one router output, joined to the TOC.

    The router returns selected ``relevant_sections`` (ids), ``page_ranges`` and
    ``confidence`` index-aligned. Titles/pages are read back from the authoritative
    TOC by ``section_id`` so the page range is the structure-store authority.

    Args:
        output: One serialized ``RouterOutput`` dict.
        toc_by_id: Lookup from section_id to its authoritative section record.
        doc_id: The document the sections belong to.

    Returns:
        The selected sections as :class:`RoutedSection` (empty on fallback).
    """
    relevant = output.get("relevant_sections") or []
    confidences = output.get("confidence") or []
    routed: list[RoutedSection] = []
    for index, section_id in enumerate(relevant):
        record = toc_by_id.get(str(section_id))
        if record is None:
            continue
        confidence = float(confidences[index]) if index < len(confidences) else 0.0
        routed.append(
            RoutedSection(
                section_id=record.section_id,
                title=record.title or "",
                page_start=record.page_start,
                page_end=record.page_end,
                confidence=confidence,
                document_id=doc_id,
            )
        )
    return routed


class RouterModuleAdapter:
    """Adapts ``router.route`` to the backend Router Protocol (FIX-C-01).

    Loads the authoritative, tenant-scoped TOC from the structure store for each
    target document and delegates section selection to the ``router`` package so
    the TOC-membership filter runs on the live ``/v1/route`` and ``/v1/answer``
    paths. Multi-document requests fan out per document (routing-only, ADV-006).
    """

    def __init__(
        self,
        store: DocumentStore,
        route: RouteCallable,
    ) -> None:
        """Bind the adapter to a document store and the router entrypoint.

        Args:
            store: Tenant-scoped structure store used to load each TOC.
            route: The ``router.route`` coroutine (injected for testability).
        """
        self._store = store
        self._route = route

    async def _route_one(
        self,
        tenant_id: str,
        doc_id: str,
        query: str,
        confidence_threshold: float,
        max_sections: int,
    ) -> tuple[list[RoutedSection], Mapping[str, Any]]:
        """Route a single document, loading its TOC from the structure store.

        Args:
            tenant_id: Owning tenant (IDOR guard).
            doc_id: Target document id.
            query: The untrusted user query.
            confidence_threshold: Inclusion threshold for routed sections.
            max_sections: Maximum number of sections to select.

        Returns:
            A tuple of (routed sections, raw router output) for this document.
        """
        sections = await self._store.get_sections(tenant_id, doc_id)
        toc = _toc_from_sections(sections)
        toc_by_id = {section.section_id: section for section in sections}
        output = await self._route(
            query,
            doc_id,
            toc,
            tenant_id=tenant_id,
            confidence_threshold=confidence_threshold,
            max_sections=max_sections,
        )
        return _routed_sections_from_output(output, toc_by_id, doc_id), output

    async def route(
        self,
        tenant_id: str,
        document_ids: list[str],
        query: str,
        confidence_threshold: float,
        max_sections: int,
    ) -> RouterDecision:
        """Select relevant sections across the target documents (routing-only).

        For a single document this is one ``router.route`` call against its
        authoritative TOC. For multiple documents (ADV-006) it fans out one call
        per document and merges the selected sections fairly: every contributing
        document is represented before any document receives a second slot, then
        the remaining slots are filled by descending confidence with a
        deterministic tiebreak, capped at ``max_sections``. Fallback is reported
        when no document produced a section. The generation LLM is never invoked.

        Args:
            tenant_id: Owning tenant (IDOR guard).
            document_ids: One or more target document ids.
            query: The untrusted user query.
            confidence_threshold: Inclusion threshold for routed sections.
            max_sections: Maximum number of sections to return.

        Returns:
            A :class:`RouterDecision` with the merged routed sections.
        """
        all_sections: list[RoutedSection] = []
        total_time_ms = 0
        rationales: list[str] = []
        for doc_id in document_ids:
            routed, output = await self._route_one(
                tenant_id, doc_id, query, confidence_threshold, max_sections
            )
            all_sections.extend(routed)
            total_time_ms += int(output.get("routing_time_ms") or 0)
            rationale = output.get("rationale")
            if rationale:
                rationales.append(str(rationale))

        merged = _merge_fairly(all_sections, max_sections)
        fallback = not merged
        rationale = " ".join(rationales) if rationales else None
        return RouterDecision(
            relevant_sections=merged,
            fallback=fallback,
            routing_time_ms=total_time_ms,
            rationale=rationale,
        )
