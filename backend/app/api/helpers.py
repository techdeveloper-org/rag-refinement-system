"""Pure helpers shared across the /v1 routers.

Holds correlation-id generation, the display-only token-reduction estimate,
and the x-pii field inventory used by the DPDP access export (STORY-034,
FR-029). None of these touch I/O, so they are unit-testable in isolation.
"""

from __future__ import annotations

import secrets

from backend.app.api.interfaces import DocumentRecord, RoutedSection, SectionRecord
from backend.app.api.schemas import PiiField

_PII_TOKEN_BUDGET = 100


def new_query_id() -> str:
    """Generate a correlation id matching the ``qry_`` pattern (NFR-009).

    Fix #199: use secrets.token_urlsafe(16) to produce an unpredictable,
    cryptographically random id (128 bits of entropy) that prevents cross-stream
    correlation attacks where a low-entropy query_id could be guessed.

    Returns:
        A unique, URL-safe query id (e.g. ``qry_<22 url-safe chars>``).
    """
    return "qry_" + secrets.token_urlsafe(16)


def estimate_token_reduction(selected: list[RoutedSection], total_pages: int) -> str:
    """Estimate token saving vs. full-document RAG as a display string.

    The estimate is intentionally coarse and display-only (ADV-005): it
    compares the selected page span against the document's total pages.

    Args:
        selected: The routed sections.
        total_pages: The document's total page count.

    Returns:
        A percentage string matching ``^[0-9]{1,3}%$`` (e.g. ``87%``).
    """
    if total_pages <= 0 or not selected:
        return "0%"
    selected_pages = sum(
        max(0, section.page_end - section.page_start + 1) for section in selected
    )
    selected_pages = min(selected_pages, total_pages)
    reduction = int(round((1 - selected_pages / total_pages) * 100))
    reduction = max(0, min(99, reduction))
    return f"{reduction}%"


def _pii_fields_from_flags(flags: dict[str, str], location: str) -> list[PiiField]:
    """Project a row's ``pii_flags`` annotation map into PiiField entries.

    Args:
        flags: Field-name -> category map (never PII values, FR-029).
        location: Where the fields occur (e.g. a section_id or ``document``).

    Returns:
        A list of :class:`PiiField` carrying field names only.
    """
    return [
        PiiField(field=name, location=location, category=category if category is not None else None)
        for name, category in flags.items()
    ]


def build_pii_inventory(
    document: DocumentRecord, sections: list[SectionRecord]
) -> list[PiiField]:
    """Enumerate the x-pii-annotated fields held for a document (FR-029).

    The inventory lists field NAMES (and their categories) sourced from the
    schema's ``x-pii`` annotations as recorded in each row's ``pii_flags`` -
    never the PII values themselves (DPDP, STORY-034 self-check). The known
    x-pii document/section fields from openapi.yaml (``title``, ``summary``)
    are always reported when present so the inventory matches the annotated
    contract even if the flag map is empty.

    Args:
        document: The document record being exported.
        sections: The document's section records.

    Returns:
        A deduplicated inventory of PII fields held for the document.
    """
    inventory: list[PiiField] = []

    if document.title is not None:
        inventory.append(
            PiiField(field="title", location="document", category="document_title")
        )
    inventory.extend(_pii_fields_from_flags(document.pii_flags, "document"))

    for section in sections:
        if section.title is not None:
            inventory.append(
                PiiField(
                    field="title",
                    location=section.section_id,
                    category="section_title",
                )
            )
        if section.summary is not None:
            inventory.append(
                PiiField(
                    field="summary",
                    location=section.section_id,
                    category="section_summary",
                )
            )
        inventory.extend(_pii_fields_from_flags(section.pii_flags, section.section_id))

    seen: set[tuple[str, str]] = set()
    deduped: list[PiiField] = []
    for entry in inventory:
        key = (entry.field, entry.location)
        if key not in seen:
            seen.add(key)
            deduped.append(entry)
    return deduped
