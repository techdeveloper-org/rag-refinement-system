"""Shared fixtures for router tests: a golden TOC and a JSON reply helper.

All tests run offline against ``FakeRouterLLM`` -- no network access is performed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest

from router.graph import clear_toc_cache


@pytest.fixture(autouse=True)
def _reset_toc_cache() -> None:
    """Clear the per-document TOC cache before each test for isolation."""
    clear_toc_cache()


@pytest.fixture
def golden_toc() -> list[dict[str, Any]]:
    """A deterministic golden TOC spanning three sections with page ranges."""
    return [
        {
            "section_id": "sec_intro",
            "level": 1,
            "title": "Introduction",
            "page_start": 1,
            "page_end": 3,
        },
        {
            "section_id": "sec_warranty",
            "level": 1,
            "title": "Warranty Terms",
            "page_start": 4,
            "page_end": 9,
            "summary": "Duration and coverage of the product warranty.",
        },
        {
            "section_id": "sec_returns",
            "level": 1,
            "title": "Returns and Refunds",
            "page_start": 10,
            "page_end": 12,
        },
    ]


def make_reply(
    ranked: list[Mapping[str, Any]],
    rationale: str = "Routed by relevance.",
) -> str:
    """Serialize a well-formed router LLM reply for the fake.

    Args:
        ranked: A list of ``{"section_id": ..., "confidence": ...}`` mappings.
        rationale: The rationale string to include.

    Returns:
        A JSON string in the strict router-reply shape.
    """
    return json.dumps({"ranked_sections": list(ranked), "rationale": rationale})
