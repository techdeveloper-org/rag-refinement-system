"""Ingestion pipeline package (data-engineer-owned, STORY-003/008/009/011).

Exposes the parse -> TOC -> section-aware chunk -> embed -> Qdrant upsert + Postgres
section-row pipeline as ``ingest_document(doc, ...)`` returning
``{doc_id, toc, section_rows_written, chunks_upserted, fallback_only}``. The
pipeline is idempotent on content hash, never lets a chunk cross a section
boundary, and stamps ``tenant_id`` on every chunk payload (AGREED CONTRACT
python-backend-engineer <-> data-engineer).

``section_id`` is the universal key bridging Postgres sections and Qdrant chunk
points. Concrete PDF parsing, embedding, and store access are injected through
Protocols (``Parser``, ``Embedder``, ``SectionStore``, ``VectorStore``) so the
pipeline is testable without network, a real OpenAI key, or a live database.
"""

from __future__ import annotations

from ingestion.chunker import Chunk, chunk_document, chunk_section
from ingestion.embedder import (
    EMBEDDING_DIM,
    BgeM3Embedder,
    Embedder,
    FallbackEmbedder,
    OpenAIEmbedder,
)
from ingestion.parser import (
    Page,
    ParsedDocument,
    Parser,
    PyMuPDFParser,
    TextBlock,
    content_hash,
)
from ingestion.pipeline import (
    IngestInput,
    IngestResult,
    SectionRow,
    SectionStore,
    VectorStore,
    ingest_document,
)
from ingestion.toc_extractor import (
    LlmRefiner,
    TocEntry,
    TocResult,
    extract_toc,
)

__all__ = [
    "ingest_document",
    "IngestInput",
    "IngestResult",
    "SectionRow",
    "SectionStore",
    "VectorStore",
    "Parser",
    "ParsedDocument",
    "Page",
    "TextBlock",
    "PyMuPDFParser",
    "content_hash",
    "extract_toc",
    "TocEntry",
    "TocResult",
    "LlmRefiner",
    "Chunk",
    "chunk_document",
    "chunk_section",
    "Embedder",
    "EMBEDDING_DIM",
    "OpenAIEmbedder",
    "BgeM3Embedder",
    "FallbackEmbedder",
]
