"""Unit tests for pure API helpers and schema validation.

Exercises token-reduction estimation, the PII inventory builder (FR-029), and
the RouteRequest oneOf validator without any HTTP round-trip.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.api.helpers import build_pii_inventory, estimate_token_reduction
from backend.app.api.interfaces import DocumentRecord, RoutedSection, SectionRecord
from backend.app.api.schemas import RouteRequest


def _routed(page_start: int, page_end: int) -> RoutedSection:
    """Build a routed section spanning the given page range.

    Args:
        page_start: Inclusive first page.
        page_end: Inclusive last page.

    Returns:
        A :class:`RoutedSection`.
    """
    return RoutedSection(
        section_id="sec_x",
        title="X",
        page_start=page_start,
        page_end=page_end,
        confidence=0.9,
    )


def test_estimate_token_reduction_typical() -> None:
    """A small selected span yields a high reduction percentage."""
    result = estimate_token_reduction([_routed(1, 5)], total_pages=100)
    assert result.endswith("%")
    assert int(result[:-1]) >= 90


def test_estimate_token_reduction_empty_selection() -> None:
    """No selected sections yields 0%."""
    assert estimate_token_reduction([], total_pages=100) == "0%"


def test_estimate_token_reduction_zero_pages() -> None:
    """A zero-page document yields 0% (no division by zero)."""
    assert estimate_token_reduction([_routed(1, 5)], total_pages=0) == "0%"


def test_build_pii_inventory_lists_field_names_only() -> None:
    """The inventory enumerates x-pii field names, never PII values."""
    document = DocumentRecord(
        doc_id="doc_abc123",
        tenant_id="t",
        title="Owner Name",
        total_pages=10,
        domain=None,
        residency_region="IN",
        fallback_only=False,
        created_at="2026-06-06T00:00:00+00:00",
    )
    sections = [
        SectionRecord(
            section_id="sec_1",
            tenant_id="t",
            title="Personal Details",
            level=1,
            page_start=1,
            page_end=2,
            summary="A summary.",
        )
    ]
    inventory = build_pii_inventory(document, sections)
    fields = {(entry.field, entry.location) for entry in inventory}
    assert ("title", "document") in fields
    assert ("title", "sec_1") in fields
    assert ("summary", "sec_1") in fields
    for entry in inventory:
        assert entry.field in {"title", "summary"}


def test_route_request_both_selectors_rejected() -> None:
    """RouteRequest rejects both document_id and document_ids."""
    with pytest.raises(ValidationError):
        RouteRequest(document_id="doc_abc123", document_ids=["doc_abc123"], query="q")


def test_route_request_neither_selector_rejected() -> None:
    """RouteRequest rejects a body with neither document selector."""
    with pytest.raises(ValidationError):
        RouteRequest(query="q")


def test_route_request_single_selector_accepted() -> None:
    """RouteRequest accepts document_id alone."""
    body = RouteRequest(document_id="doc_abc123", query="q")
    assert body.document_id == "doc_abc123"


def test_route_request_rejects_unknown_field() -> None:
    """RouteRequest forbids unknown fields (additionalProperties: false)."""
    with pytest.raises(ValidationError):
        RouteRequest(document_id="doc_abc123", query="q", surprise=True)
