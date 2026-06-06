"""Live PyMuPDF parser test for STORY-008 (skipped when fitz is unavailable).

Builds a small synthetic PDF in memory with native bookmarks and multi-page
text, then asserts the PyMuPDFParser extracts page text, the native TOC, and a
stable content hash. Skipped (with reason) when PyMuPDF cannot be imported so
the rest of the suite still runs behind the Parser interface.
"""

from __future__ import annotations

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF (fitz) not installed")

from ingestion.parser import PyMuPDFParser, content_hash  # noqa: E402


def _build_synthetic_pdf() -> bytes:
    """Build a 3-page PDF with a two-entry native bookmark TOC.

    Returns:
        Raw PDF bytes with bookmarks and per-page text.
    """
    doc = fitz.open()
    for index in range(3):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {index + 1} synthetic body text content")
    doc.set_toc([[1, "Section One", 1], [1, "Section Two", 3]])
    data: bytes = doc.tobytes()
    doc.close()
    return data


def test_pymupdf_parser_extracts_text_toc_and_hash() -> None:
    """PyMuPDFParser yields pages, the native TOC, and a stable content hash."""
    data = _build_synthetic_pdf()

    parsed = PyMuPDFParser().parse(data)

    assert parsed.page_count == 3
    assert parsed.content_hash == content_hash(data)
    assert len(parsed.native_toc) == 2
    titles = [title for _, title, _ in parsed.native_toc]
    assert titles == ["Section One", "Section Two"]
    assert any("synthetic body text" in page.text for page in parsed.pages)


def test_pymupdf_parser_blocks_carry_typography() -> None:
    """Parsed blocks expose font size and position for heuristic detection."""
    data = _build_synthetic_pdf()

    parsed = PyMuPDFParser().parse(data)

    blocks = [block for page in parsed.pages for block in page.blocks]
    assert blocks
    assert all(block.font_size > 0 for block in blocks)
