"""Pytest configuration + shared fakes/golden fixtures for ingestion tests.

Puts the project root on ``sys.path`` for ``import db`` / ``import ingestion``,
then provides deterministic, network-free test doubles: a fake parser that emits
golden ParsedDocuments for Scenarios A/B/C, a fake 1536-dim embedder, and
in-memory section + vector stores. No real PDF, OpenAI key, or database is used.
"""

from __future__ import annotations

import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ingestion.embedder import EMBEDDING_DIM  # noqa: E402
from ingestion.parser import Page, ParsedDocument, TextBlock, content_hash  # noqa: E402
from ingestion.pipeline import SectionRow  # noqa: E402


def _page(number: int, words: int, *, blocks: tuple[TextBlock, ...] = ()) -> Page:
    """Build a synthetic page with a fixed number of body words.

    Args:
        number: One-based page number.
        words: Body word count (drives chunk sizing deterministically).
        blocks: Optional layout blocks (used for Scenario B heuristics).

    Returns:
        A Page whose text has ``words`` whitespace-delimited tokens.
    """
    body = " ".join(f"w{number}_{i}" for i in range(words))
    text = body if not blocks else "\n".join([b.text for b in blocks] + [body])
    return Page(number=number, text=text, blocks=blocks)


class FakeParser:
    """Deterministic parser returning a preset ParsedDocument per scenario.

    Computes a real content hash over the input bytes so idempotency tests
    exercise the same hash path as production without needing PyMuPDF.
    """

    def __init__(self, template: ParsedDocument) -> None:
        """Store the template document the parser will return.

        Args:
            template: The ParsedDocument to emit (hash is recomputed per call).
        """
        self._template = template
        self.calls = 0

    def parse(self, data: bytes) -> ParsedDocument:
        """Return the template document with a hash derived from ``data``.

        Args:
            data: Raw bytes (hashed for idempotency).

        Returns:
            The preset ParsedDocument carrying the computed content hash.
        """
        self.calls += 1
        return ParsedDocument(
            page_count=self._template.page_count,
            pages=self._template.pages,
            native_toc=self._template.native_toc,
            content_hash=content_hash(data),
        )


class FakeEmbedder:
    """Deterministic 1536-dim embedder (no network, no key).

    Produces a stable vector per text so tests are reproducible and the
    dimension matches the Qdrant collection (EMBEDDING_DIM).
    """

    def __init__(self, dimension: int = EMBEDDING_DIM) -> None:
        """Initialize with the required output dimension.

        Args:
            dimension: Output vector length (defaults to EMBEDDING_DIM = 1536).
        """
        self._dimension = dimension
        self.embed_calls = 0

    @property
    def dimension(self) -> int:
        """Return the fixed output dimension."""
        return self._dimension

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one deterministic vector per text.

        Args:
            texts: Texts to embed.

        Returns:
            One ``dimension``-length vector per input text.
        """
        self.embed_calls += 1
        return [[float(len(text) % 7)] * self._dimension for text in texts]


@dataclass
class FakeSectionStore:
    """In-memory section store mirroring the idempotent Postgres contract."""

    documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    sections: dict[str, list[SectionRow]] = field(default_factory=dict)
    hash_index: dict[tuple[str, str], str] = field(default_factory=dict)

    def find_doc_id_by_hash(self, tenant_id: str, content_hash_value: str) -> str | None:
        """Return a prior ``doc_id`` for this tenant + hash, or None.

        Args:
            tenant_id: Owning tenant.
            content_hash_value: Content hash of the upload.

        Returns:
            The existing document id, or None on first upload.
        """
        return self.hash_index.get((tenant_id, content_hash_value))

    def upsert_document(
        self,
        doc_id: str,
        tenant_id: str,
        title: str | None,
        domain: str | None,
        total_pages: int,
        content_hash_value: str | None,
        ingest_status: str,
        fallback_only: bool,
    ) -> None:
        """Create or update a document row and index its content hash.

        Args:
            doc_id: Document id.
            tenant_id: Owning tenant.
            title: Optional title.
            domain: Optional domain.
            total_pages: Page count.
            content_hash_value: Content hash (None in no-retention).
            ingest_status: Ingest status enum value.
            fallback_only: Scenario C flag.
        """
        self.documents[doc_id] = {
            "doc_id": doc_id,
            "tenant_id": tenant_id,
            "title": title,
            "domain": domain,
            "total_pages": total_pages,
            "content_hash": content_hash_value,
            "ingest_status": ingest_status,
            "fallback_only": fallback_only,
        }
        if content_hash_value is not None:
            self.hash_index[(tenant_id, content_hash_value)] = doc_id

    def replace_sections(self, doc_id: str, rows: list[SectionRow]) -> int:
        """Replace the document's sections with ``rows`` (idempotent).

        Args:
            doc_id: Document whose sections are replaced.
            rows: New section rows.

        Returns:
            Number of rows written.
        """
        self.sections[doc_id] = list(rows)
        return len(rows)


@dataclass
class FakeVectorStore:
    """In-memory Qdrant stand-in keyed by point id for idempotency checks."""

    points: dict[str, dict[str, Any]] = field(default_factory=dict)
    upsert_calls: int = 0

    def upsert_points(self, points: list[dict[str, Any]]) -> int:
        """Upsert points by id; re-upserting the same id does not duplicate.

        Args:
            points: Point dicts ``{id, vector, payload}``.

        Returns:
            Number of points in this upsert batch.
        """
        self.upsert_calls += 1
        for point in points:
            self.points[point["id"]] = point
        return len(points)


def _scenario_a_doc() -> ParsedDocument:
    """Golden Scenario A document: native bookmarks present.

    Returns:
        A 6-page ParsedDocument with a two-level native TOC.
    """
    pages = tuple(_page(n, words=140) for n in range(1, 7))
    native_toc = (
        (1, "Introduction", 1),
        (1, "Methods", 3),
        (2, "Data Collection", 4),
        (1, "Conclusion", 6),
    )
    return ParsedDocument(page_count=6, pages=pages, native_toc=native_toc, content_hash="")


def _scenario_b_doc() -> ParsedDocument:
    """Golden Scenario B document: no bookmarks, detectable large/bold headers.

    Returns:
        A 4-page ParsedDocument whose first block per header page is a large
        font heading and whose body blocks are body-size.
    """
    body_size = 10.0
    head_size = 16.0

    def header(text: str) -> TextBlock:
        return TextBlock(text=text, font_size=head_size, font_name="Helvetica-Bold",
                         x0=72.0, y0=72.0, is_bold=True)

    def body(text: str) -> TextBlock:
        return TextBlock(text=text, font_size=body_size, font_name="Helvetica",
                         x0=72.0, y0=200.0, is_bold=False)

    pages = (
        _page(1, 130, blocks=(header("Chapter One"), body("intro body text here"))),
        _page(2, 130, blocks=(body("more body text continues"),)),
        _page(3, 130, blocks=(header("Chapter Two"), body("second chapter body"))),
        _page(4, 130, blocks=(body("final body text here"),)),
    )
    return ParsedDocument(page_count=4, pages=pages, native_toc=(), content_hash="")


def _scenario_c_doc() -> ParsedDocument:
    """Golden Scenario C document: no bookmarks and no header signal.

    Returns:
        A 3-page ParsedDocument with uniform body-size blocks only, so neither
        native nor heuristic extraction finds structure.
    """
    uniform = TextBlock(text="uniform body line", font_size=10.0,
                        font_name="Times", x0=72.0, y0=100.0, is_bold=False)
    pages = tuple(
        _page(n, 120, blocks=(uniform, uniform)) for n in range(1, 4)
    )
    return ParsedDocument(page_count=3, pages=pages, native_toc=(), content_hash="")


@pytest.fixture
def scenario_a_doc() -> ParsedDocument:
    """Golden Scenario A (native bookmarks) parsed document."""
    return _scenario_a_doc()


@pytest.fixture
def scenario_b_doc() -> ParsedDocument:
    """Golden Scenario B (heuristic headers) parsed document."""
    return _scenario_b_doc()


@pytest.fixture
def scenario_c_doc() -> ParsedDocument:
    """Golden Scenario C (no structure) parsed document."""
    return _scenario_c_doc()


@pytest.fixture
def fake_embedder() -> FakeEmbedder:
    """Deterministic 1536-dim embedder."""
    return FakeEmbedder()


@pytest.fixture
def section_store() -> FakeSectionStore:
    """Fresh in-memory section store."""
    return FakeSectionStore()


@pytest.fixture
def vector_store() -> FakeVectorStore:
    """Fresh in-memory vector store."""
    return FakeVectorStore()
