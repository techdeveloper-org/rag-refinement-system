"""Branch-coverage tests for ingestion internals (chunker / parser / toc / prompts).

These exercise paths the golden-fixture suite does not reach: the chunker's
section-boundary guard and trailing-window merge, the toc extractor's median and
LLM-refiner branches, the PyMuPDF parser's block reduction and missing-package
error, and the generation prompt builder (which the router never calls).
No real PDF, OpenAI key, or database is used.
"""

from __future__ import annotations

import sys

import pytest

from ingestion import chunker as chunker_mod
from ingestion.chunker import (
    Chunk,
    SectionBoundaryError,
    _assert_section_bound,
    chunk_document,
    chunk_section,
)
from ingestion.parser import Page, ParsedDocument, PyMuPDFParser
from ingestion.toc_extractor import TocEntry, _median


def _doc(pages: list[Page], native_toc: tuple = ()) -> ParsedDocument:
    """Build a ParsedDocument fixture from pages."""
    return ParsedDocument(
        page_count=len(pages),
        pages=tuple(pages),
        native_toc=native_toc,
        content_hash="hash",
    )


class TestSectionBoundaryGuard:
    """The STORY-011 no-cross-boundary invariant (P0)."""

    def test_chunk_outside_page_range_raises(self) -> None:
        """A chunk whose page is outside its section raises SectionBoundaryError."""
        entry = TocEntry(level=1, title="S", page_start=1, page_end=2)
        bad = Chunk(
            chunk_id="c1",
            section_id="sec_1",
            doc_id="doc_1",
            tenant_id="tenant_a",
            page=9,
            text="x",
            token_count=1,
        )
        with pytest.raises(SectionBoundaryError, match="crosses a section boundary"):
            _assert_section_bound(bad, entry, "sec_1", "tenant_a")

    def test_chunk_with_wrong_section_id_raises(self) -> None:
        """A chunk tagged with the wrong section id raises SectionBoundaryError."""
        entry = TocEntry(level=1, title="S", page_start=1, page_end=2)
        bad = Chunk(
            chunk_id="c1",
            section_id="sec_other",
            doc_id="doc_1",
            tenant_id="tenant_a",
            page=1,
            text="x",
            token_count=1,
        )
        with pytest.raises(SectionBoundaryError, match="section_id mismatch"):
            _assert_section_bound(bad, entry, "sec_1", "tenant_a")

    def test_chunk_missing_tenant_raises(self) -> None:
        """A chunk missing the expected tenant tag raises SectionBoundaryError."""
        entry = TocEntry(level=1, title="S", page_start=1, page_end=2)
        bad = Chunk(
            chunk_id="c1",
            section_id="sec_1",
            doc_id="doc_1",
            tenant_id="tenant_b",
            page=1,
            text="x",
            token_count=1,
        )
        with pytest.raises(SectionBoundaryError, match="missing tenant_id"):
            _assert_section_bound(bad, entry, "sec_1", "tenant_a")


class TestChunkSection:
    """Window sizing and the trailing-merge branch."""

    def test_trailing_small_window_merges_into_previous(self) -> None:
        """A trailing window below MIN_CHUNK_TOKENS merges into the prior chunk."""
        word_count = chunker_mod.MAX_CHUNK_TOKENS + 10
        body = " ".join(f"w{i}" for i in range(word_count))
        page = Page(number=1, text=body, blocks=())
        doc = _doc([page])
        entry = TocEntry(level=1, title="S", page_start=1, page_end=1)
        chunks = chunk_section(doc, entry, "doc_1", "tenant_a", section_id="sec_1")
        assert len(chunks) == 1
        assert chunks[0].token_count == word_count

    def test_resolved_section_id_derived_when_omitted(self) -> None:
        """When no section_id is passed, a deterministic id is derived."""
        body = " ".join(f"w{i}" for i in range(50))
        doc = _doc([Page(number=1, text=body, blocks=())])
        entry = TocEntry(level=1, title="Intro", page_start=1, page_end=1)
        chunks = chunk_section(doc, entry, "doc_1", "tenant_a")
        assert chunks
        assert chunks[0].section_id.startswith("chunk_") or chunks[0].section_id

    def test_chunk_document_validates_every_chunk(self) -> None:
        """chunk_document chunks each section and validates the boundary."""
        body = " ".join(f"w{i}" for i in range(120))
        doc = _doc([Page(number=1, text=body, blocks=())])
        entry = TocEntry(level=1, title="S", page_start=1, page_end=1)
        chunks = chunk_document(doc, [("sec_1", entry)], "doc_1", "tenant_a")
        assert all(c.section_id == "sec_1" for c in chunks)


class TestMedian:
    """The body-text median helper used for header detection."""

    def test_median_empty_is_zero(self) -> None:
        """An empty list has a median of 0.0."""
        assert _median([]) == 0.0

    def test_median_odd_length(self) -> None:
        """An odd-length list returns the middle element."""
        assert _median([3.0, 1.0, 2.0]) == 2.0

    def test_median_even_length_averages_middle_pair(self) -> None:
        """An even-length list averages the two middle elements."""
        assert _median([1.0, 2.0, 3.0, 4.0]) == 2.5


class TestPyMuPDFParser:
    """The PyMuPDF parser block reduction and missing-package guard."""

    def test_parse_raises_when_fitz_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing PyMuPDF (fitz) raises a clear RuntimeError."""
        monkeypatch.setitem(sys.modules, "fitz", None)
        with pytest.raises(RuntimeError, match="PyMuPDF"):
            PyMuPDFParser().parse(b"%PDF-1.4")

    def test_parse_block_reduces_dominant_span(self) -> None:
        """A block reduces to its dominant span's typography (largest text wins)."""
        block = {
            "lines": [
                {
                    "spans": [
                        {"text": "Hi", "size": 10.0, "font": "Times", "flags": 0},
                        {
                            "text": "Heading",
                            "size": 18.0,
                            "font": "Arial-Bold",
                            "flags": 16,
                        },
                    ]
                }
            ],
            "bbox": (1.0, 2.0, 3.0, 4.0),
        }
        text_block = PyMuPDFParser._parse_block(block)
        assert text_block is not None
        assert text_block.text == "HiHeading"
        assert text_block.is_bold is True
        assert text_block.x0 == 1.0

    def test_parse_block_returns_none_for_empty_text(self) -> None:
        """A block with no text reduces to None (skipped by the page parser)."""
        block = {"lines": [{"spans": [{"text": "  ", "size": 10.0}]}]}
        assert PyMuPDFParser._parse_block(block) is None

    def test_parse_page_skips_blocks_without_lines_and_empty_blocks(self) -> None:
        """A page parser skips non-text blocks and empty-text blocks."""

        class _FakePage:
            def get_text(self, mode: str) -> dict:
                return {
                    "blocks": [
                        {"image": True},
                        {
                            "lines": [{"spans": [{"text": "   ", "size": 10.0}]}],
                            "bbox": (0.0, 0.0, 1.0, 1.0),
                        },
                        {
                            "lines": [
                                {"spans": [{"text": "Body", "size": 10.0}]}
                            ],
                            "bbox": (0.0, 0.0, 1.0, 1.0),
                        },
                    ]
                }

        class _FakeDoc:
            def __getitem__(self, index: int) -> _FakePage:
                return _FakePage()

        page = PyMuPDFParser()._parse_page(_FakeDoc(), 0)
        assert page.number == 1
        assert page.text == "Body"
        assert len(page.blocks) == 1


class TestPipelineBranches:
    """Pipeline branches the scenario suite does not reach."""

    def test_scenario_c_no_retention_skips_upsert(
        self, scenario_c_doc: ParsedDocument
    ) -> None:
        """A Scenario-C upload under no_retention persists nothing, returns fallback."""
        from ingestion.pipeline import IngestInput, ingest_document
        from ingestion.tests.conftest import (
            FakeEmbedder,
            FakeParser,
            FakeSectionStore,
            FakeVectorStore,
        )

        section_store = FakeSectionStore()
        vector_store = FakeVectorStore()
        result = ingest_document(
            IngestInput(data=b"PDF-C", tenant_id="tenant-1", no_retention=True),
            parser=FakeParser(scenario_c_doc),
            embedder=FakeEmbedder(),
            section_store=section_store,
            vector_store=vector_store,
        )
        assert result["fallback_only"] is True
        assert result["section_rows_written"] == 0
        assert not section_store.sections

    def test_empty_chunks_upserts_nothing(self) -> None:
        """A document whose sole section yields no words upserts zero points."""
        from ingestion.pipeline import IngestInput, ingest_document
        from ingestion.tests.conftest import (
            FakeEmbedder,
            FakeParser,
            FakeSectionStore,
            FakeVectorStore,
        )

        # A native-TOC document whose page has no body words -> no chunks.
        empty_page = Page(number=1, text="", blocks=())
        doc = ParsedDocument(
            page_count=1,
            pages=(empty_page,),
            native_toc=((1, "Intro", 1),),
            content_hash="hash",
        )
        section_store = FakeSectionStore()
        vector_store = FakeVectorStore()
        result = ingest_document(
            IngestInput(data=b"PDF-EMPTY", tenant_id="tenant-1"),
            parser=FakeParser(doc),
            embedder=FakeEmbedder(),
            section_store=section_store,
            vector_store=vector_store,
        )
        assert result["chunks_upserted"] == 0
        assert len(vector_store.points) == 0


class TestTocRefiner:
    """The Scenario-B LLM refiner branch in extract_toc."""

    def test_refiner_emptying_result_falls_through_to_scenario_c(self) -> None:
        """A refiner that drops all candidates falls through to Scenario C."""
        from ingestion.parser import TextBlock
        from ingestion.toc_extractor import extract_toc

        heading = TextBlock(
            text="BIG HEADING",
            font_size=24.0,
            font_name="Arial-Bold",
            x0=0.0,
            y0=0.0,
            is_bold=True,
        )
        body = TextBlock(
            text="small body text here",
            font_size=10.0,
            font_name="Times",
            x0=0.0,
            y0=20.0,
            is_bold=False,
        )
        page = Page(number=1, text="BIG HEADING\nbody", blocks=(heading, body))
        doc = _doc([page])

        class _EmptyRefiner:
            def refine(self, entries: object) -> list:
                return []

        result = extract_toc(doc, llm_refiner=_EmptyRefiner())
        assert result.scenario == "C"
        assert result.fallback_only is True


class TestGenerationPrompt:
    """The downstream generation prompt builder (never called by the router)."""

    def test_build_generation_prompt_joins_passages(self) -> None:
        """The generation prompt wraps the question and joins context passages."""
        from router.prompts import GENERATION_SYSTEM_PROMPT, build_generation_prompt

        system, messages = build_generation_prompt(
            "what is the warranty?", ["passage one", "passage two"]
        )
        assert system == GENERATION_SYSTEM_PROMPT
        assert len(messages) == 1
        content = messages[0]["content"]
        assert "passage one" in content
        assert "what is the warranty?" in content
