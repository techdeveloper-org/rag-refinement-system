"""PDF parsing for the ingestion pipeline (ADR-4, STORY-008).

Extracts page text and per-block layout features (font name, font size, position)
from a PDF using PyMuPDF (``import fitz``). The block-level font/size/position
features feed the heuristic header detection in ``toc_extractor`` for Scenario B.

The concrete parser is hidden behind the ``Parser`` Protocol so the rest of the
pipeline (TOC, chunking, embedding, upsert) can be exercised with a fake parser
when PyMuPDF is unavailable or when deterministic golden fixtures are required.
No PDF bytes are retained beyond parsing; the caller decides retention.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TextBlock:
    """A single layout block on a page with its dominant typography.

    Attributes:
        text: The block's concatenated text.
        font_size: Dominant font size in points for the block.
        font_name: Dominant font face name for the block.
        x0: Left coordinate of the block bounding box.
        y0: Top coordinate of the block bounding box.
        is_bold: True when the dominant span is bold (heuristic header signal).
    """

    text: str
    font_size: float
    font_name: str
    x0: float
    y0: float
    is_bold: bool = False


@dataclass(frozen=True)
class Page:
    """A parsed page: ordered text blocks plus the flattened page text.

    Attributes:
        number: One-based page number.
        text: Full page text (block order preserved).
        blocks: Layout blocks carrying font/size/position features.
    """

    number: int
    text: str
    blocks: tuple[TextBlock, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ParsedDocument:
    """The structural result of parsing a PDF.

    Attributes:
        page_count: Total number of pages.
        pages: Parsed pages in order.
        native_toc: Native bookmark TOC as ``(level, title, page)`` triples from
            PyMuPDF ``get_toc()``; empty when the PDF has no bookmarks.
        content_hash: Stable SHA-256 of the source bytes for idempotency.
    """

    page_count: int
    pages: tuple[Page, ...]
    native_toc: tuple[tuple[int, str, int], ...]
    content_hash: str


@runtime_checkable
class Parser(Protocol):
    """Parser interface consumed by the pipeline.

    Implementations turn raw PDF bytes into a ``ParsedDocument``. The Protocol
    lets tests inject a deterministic fake without PyMuPDF or real files.
    """

    def parse(self, data: bytes) -> ParsedDocument:
        """Parse raw PDF bytes into a structural document.

        Args:
            data: Raw PDF file bytes.

        Returns:
            A ParsedDocument with pages, layout blocks, native TOC, and hash.
        """
        ...


def content_hash(data: bytes) -> str:
    """Compute the stable content hash used for idempotent re-upload dedup.

    Args:
        data: Raw document bytes.

    Returns:
        Hex SHA-256 digest of the bytes (OAQ-1 idempotency key).
    """
    return hashlib.sha256(data).hexdigest()


class PyMuPDFParser:
    """PyMuPDF-backed parser extracting text + font/size/position (ADR-4).

    Imports ``fitz`` lazily so the surrounding pipeline and its tests load even
    in environments where PyMuPDF is not installed.
    """

    def parse(self, data: bytes) -> ParsedDocument:
        """Parse PDF bytes into pages, blocks, and the native bookmark TOC.

        Args:
            data: Raw PDF file bytes.

        Returns:
            A ParsedDocument with per-block typography features and the native
            ``get_toc()`` bookmark list (empty when absent).

        Raises:
            RuntimeError: When PyMuPDF (``fitz``) is not importable.
        """
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF (fitz) is required for PyMuPDFParser; install pymupdf."
            ) from exc

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            pages = tuple(self._parse_page(doc, index) for index in range(doc.page_count))
            native_toc = tuple(
                (int(level), str(title), int(page))
                for level, title, page in doc.get_toc(simple=True)
            )
            return ParsedDocument(
                page_count=doc.page_count,
                pages=pages,
                native_toc=native_toc,
                content_hash=content_hash(data),
            )
        finally:
            doc.close()

    def _parse_page(self, doc: object, index: int) -> Page:
        """Extract one page's blocks with dominant typography per block.

        Args:
            doc: An open ``fitz.Document``.
            index: Zero-based page index.

        Returns:
            A Page with ordered TextBlocks and the flattened page text.
        """
        page = doc[index]  # type: ignore[index]
        layout = page.get_text("dict")
        blocks: list[TextBlock] = []
        page_texts: list[str] = []
        for block in layout.get("blocks", []):
            if "lines" not in block:
                continue
            parsed = self._parse_block(block)
            if parsed is None:
                continue
            blocks.append(parsed)
            page_texts.append(parsed.text)
        return Page(
            number=index + 1,
            text="\n".join(page_texts),
            blocks=tuple(blocks),
        )

    @staticmethod
    def _parse_block(block: dict) -> TextBlock | None:
        """Reduce a PyMuPDF dict block to a single TextBlock or ``None``.

        Picks the dominant span typography (largest span text wins) so heuristic
        header detection sees a representative font size / face per block.

        Args:
            block: A PyMuPDF ``get_text('dict')`` block.

        Returns:
            A TextBlock, or None when the block holds no text.
        """
        spans = [span for line in block.get("lines", []) for span in line.get("spans", [])]
        text = "".join(span.get("text", "") for span in spans).strip()
        if not text:
            return None
        dominant = max(spans, key=lambda span: len(span.get("text", "")), default=None)
        if dominant is None:  # pragma: no cover - defensive: unreachable once text is non-empty
            return None
        font_name = str(dominant.get("font", ""))
        bbox = block.get("bbox", (0.0, 0.0, 0.0, 0.0))
        return TextBlock(
            text=text,
            font_size=float(dominant.get("size", 0.0)),
            font_name=font_name,
            x0=float(bbox[0]),
            y0=float(bbox[1]),
            is_bold="bold" in font_name.lower() or bool(int(dominant.get("flags", 0)) & 16),
        )
