"""Section-aware chunking (STORY-011, FR-003, P0-risk).

Splits each section's text into chunks of roughly 100-512 tokens, where every
chunk is bounded strictly within a single section's page range. The hard
invariant - enforced by an assertion and a boundary check - is that NO chunk
crosses a section boundary, because the router's ``section_id IN (...)`` scope
filter is only sound when each chunk belongs to exactly one section.

Chunking is deterministic: the same section text yields the same chunk ids
(stable SHA-256 over ``doc_id|section_id|page|ordinal|text``), so the STORY-011
golden fixtures reproduce exactly. Every chunk carries the universal
``section_id`` plus ``doc_id``, ``page`` and ``tenant_id`` so the downstream
Qdrant payload is complete. Chunk text is runtime data, never PII in fixtures.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ingestion.parser import ParsedDocument
from ingestion.toc_extractor import TocEntry

MIN_CHUNK_TOKENS: int = 100
"""Soft lower bound on chunk size; a sub-MIN remainder is allowed only as the final
chunk at a section end (the MAX upper bound is always hard, never the MIN)."""

MAX_CHUNK_TOKENS: int = 512
"""Upper bound on chunk size (token budget per chunk)."""

_WORD_RE = re.compile(r"\S+")
"""Whitespace-delimited token approximation used for sizing (no model tokenizer)."""


@dataclass(frozen=True)
class Chunk:
    """A section-bounded chunk ready for embedding and Qdrant upsert.

    Attributes:
        chunk_id: Stable, content-derived id (idempotency + golden fixtures).
        section_id: Owning section's universal key (never spans two sections).
        doc_id: Owning document id.
        tenant_id: Owning tenant; the IDOR isolation key on every chunk.
        page: One-based page the chunk's text starts on (within the section).
        text: The chunk text (runtime data).
        token_count: Approximate token count for the chunk.
    """

    chunk_id: str
    section_id: str
    doc_id: str
    tenant_id: str
    page: int
    text: str
    token_count: int


def _chunk_id(doc_id: str, section_id: str, page: int, ordinal: int, text: str) -> str:
    """Compute a stable chunk id from its identity and content.

    Deterministic over ``doc_id|section_id|page|ordinal|text`` so re-running the
    pipeline on identical input reproduces identical ids (idempotent upsert,
    STORY-003; reproducible golden fixtures, STORY-011).

    Args:
        doc_id: Owning document id.
        section_id: Owning section id.
        page: Page the chunk starts on.
        ordinal: Zero-based chunk ordinal within the section.
        text: Chunk text.

    Returns:
        Hex SHA-256 digest serving as the chunk id.
    """
    key = f"{doc_id}|{section_id}|{page}|{ordinal}|{text}".encode()
    return hashlib.sha256(key).hexdigest()


def _section_page_text(doc: ParsedDocument, entry: TocEntry) -> list[tuple[int, str]]:
    """Collect ``(page_number, page_text)`` for the section's page range.

    Only pages inside ``[page_start, page_end]`` are returned, which is what
    keeps a chunk from ever reaching another section's pages.

    Args:
        doc: Parsed document.
        entry: The section whose pages are collected.

    Returns:
        Ordered ``(page_number, page_text)`` pairs for the section.
    """
    pages: list[tuple[int, str]] = []
    for page in doc.pages:
        if entry.page_start <= page.number <= entry.page_end and page.text.strip():
            pages.append((page.number, page.text))
    return pages


def _split_words(text: str) -> list[str]:
    """Tokenize text into whitespace-delimited words.

    Args:
        text: Text to split.

    Returns:
        List of word tokens (order preserved).
    """
    return _WORD_RE.findall(text)


def chunk_section(
    doc: ParsedDocument,
    entry: TocEntry,
    doc_id: str,
    tenant_id: str,
    section_id: str | None = None,
) -> list[Chunk]:
    """Chunk a single section's text within its page range only.

    Words are grouped into windows of at most ``MAX_CHUNK_TOKENS`` tokens. The hard
    invariant is that no emitted chunk ever exceeds ``MAX_CHUNK_TOKENS``; a trailing
    remainder below ``MIN_CHUNK_TOKENS`` is emitted as its own short final chunk at
    the section end rather than extending the prior window past the maximum. Page
    attribution uses the page on which the window's first word lies, and is always
    within the section's range.

    Args:
        doc: Parsed document.
        entry: Section to chunk.
        doc_id: Owning document id.
        tenant_id: Owning tenant id (stamped on every produced chunk).
        section_id: Owning section's universal key bound onto every chunk; when
            omitted a deterministic id is derived from the document and page
            range so standalone chunking still tags each chunk.

    Returns:
        Section-bounded chunks (possibly empty when the section has no text).
    """
    resolved_section_id = section_id or _chunk_id(
        doc_id, "section", entry.page_start, entry.page_end, entry.title
    )
    page_words: list[tuple[int, str]] = []
    for page_number, page_text in _section_page_text(doc, entry):
        for word in _split_words(page_text):
            page_words.append((page_number, word))

    chunks: list[Chunk] = []
    ordinal = 0
    cursor = 0
    total = len(page_words)
    while cursor < total:
        window = page_words[cursor : cursor + MAX_CHUNK_TOKENS]
        start_page = window[0][0]
        text = " ".join(word for _, word in window)
        chunk_id = _chunk_id(doc_id, resolved_section_id, start_page, ordinal, text)
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                section_id=resolved_section_id,
                doc_id=doc_id,
                tenant_id=tenant_id,
                page=start_page,
                text=text,
                token_count=len(window),
            )
        )
        cursor += len(window)
        ordinal += 1
    return chunks


class SectionBoundaryError(AssertionError):
    """Raised when a produced chunk would cross a section boundary (P0 invariant).

    Subclasses ``AssertionError`` so existing assert-based callers and tests still
    catch it, while the check itself runs unconditionally (not stripped under
    ``python -O``), keeping the STORY-011 no-cross-boundary guarantee hard.
    """


def _assert_section_bound(
    chunk: Chunk, entry: TocEntry, section_id: str, tenant_id: str
) -> None:
    """Verify a chunk stays inside its section and carries its keys.

    Args:
        chunk: The produced chunk to validate.
        entry: The owning section's TOC entry (page range source of truth).
        section_id: Expected owning section id.
        tenant_id: Expected owning tenant id.

    Raises:
        SectionBoundaryError: If the chunk's section/tenant tag is wrong or its
            page falls outside the section's inclusive page range.
    """
    if chunk.section_id != section_id:
        raise SectionBoundaryError("chunk section_id mismatch")
    if chunk.tenant_id != tenant_id:
        raise SectionBoundaryError("chunk missing tenant_id")
    if not (entry.page_start <= chunk.page <= entry.page_end):
        raise SectionBoundaryError("chunk crosses a section boundary")


def chunk_document(
    doc: ParsedDocument,
    sections: list[tuple[str, TocEntry]],
    doc_id: str,
    tenant_id: str,
) -> list[Chunk]:
    """Chunk every section, asserting no chunk crosses a section boundary.

    Args:
        doc: Parsed document.
        sections: ``(section_id, TocEntry)`` pairs to chunk; the ``section_id``
            is the persisted universal key bound onto every chunk of that entry.
        doc_id: Owning document id.
        tenant_id: Owning tenant id, stamped on every chunk.

    Returns:
        All section-bounded chunks across the document, in section order.

    Raises:
        SectionBoundaryError: If any produced chunk's page falls outside its
            section page range (a cross-boundary chunk), or lacks section/tenant
            tags. Subclasses ``AssertionError`` for assert-style callers.
    """
    all_chunks: list[Chunk] = []
    for section_id, entry in sections:
        section_chunks = chunk_section(
            doc, entry, doc_id, tenant_id, section_id=section_id
        )
        for chunk in section_chunks:
            _assert_section_bound(chunk, entry, section_id, tenant_id)
        all_chunks.extend(section_chunks)
    return all_chunks
