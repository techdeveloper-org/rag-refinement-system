"""Ingestor adapter binding ``ingestion.ingest_document`` to the backend Protocol.

The backend :class:`Ingestor` Protocol is ``ingest_document(tenant_id, content,
filename, title, domain, no_retention, residency_region, ocr) -> IngestOutcome``.
The ``ingestion`` package exposes ``ingest_document(doc: IngestInput, *, parser,
embedder, section_store, vector_store, llm_refiner=None) -> dict`` returning
``{doc_id, toc, section_rows_written, chunks_upserted, fallback_only}``.

This adapter (FIX-C-02) translates the backend kwargs into an ``IngestInput`` and
the injected collaborators, runs the synchronous pipeline in a worker thread (so
the async event loop is never blocked), and maps the result dict onto
:class:`IngestOutcome`. ``ingest_status`` is derived from the retention flag and
the pipeline's ``fallback_only``; ``deduplicated`` is detected by a pre-call hash
lookup on the section store; ``total_pages`` is read from the resolved TOC. The
pipeline's TOC dicts (``{level, title, page_start, page_end}``) are shaped into
:class:`SectionRecord` entries whose section ids are derived through
``ingestion.section_id_for`` - the single source of truth shared with the
pipeline (FIX-1) - so the adapter's TOC ids exactly match the prefixed, hyphen-free
ids the pipeline persisted to Postgres and stamped on Qdrant payloads, and so they
satisfy the backend ``SectionId`` schema pattern.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio

from backend.app.api.interfaces import DependencyUnavailable, IngestOutcome, SectionRecord
from ingestion import section_id_for
from ingestion.embedder import EmbedderDimensionError
from ingestion.parser import Parser
from ingestion.pipeline import (
    IngestInput,
    SectionStore,
    VectorStore,
)
from ingestion.toc_extractor import LlmRefiner

IngestCallable = Callable[..., dict[str, Any]]
"""Signature of ``ingestion.ingest_document`` (kept injectable for tests)."""

_INGEST_STATUS_FALLBACK = "fallback_only"
_INGEST_STATUS_EPHEMERAL = "ephemeral"
_INGEST_STATUS_INDEXED = "indexed"


def _toc_to_records(
    doc_id: str, tenant_id: str, toc: list[dict[str, Any]]
) -> list[SectionRecord]:
    """Shape the pipeline's TOC dicts into backend SectionRecord entries.

    Section ids are derived through ``ingestion.section_id_for`` (FIX-1), the
    single source of truth shared with the pipeline, so the adapter's TOC ids are
    byte-for-byte identical to the prefixed, hyphen-free ids the pipeline persisted
    and so they satisfy the backend ``SectionId`` schema pattern.

    Args:
        doc_id: Owning document id (seed for the canonical section ids).
        tenant_id: Owning tenant (IDOR guard).
        toc: Pipeline TOC dicts ``{level, title, page_start, page_end}`` in order.

    Returns:
        One :class:`SectionRecord` per TOC entry, with canonical section ids.
    """
    return [
        SectionRecord(
            section_id=section_id_for(doc_id, ordinal),
            tenant_id=tenant_id,
            title=entry.get("title"),
            level=int(entry.get("level", 1)),
            page_start=int(entry.get("page_start", 1)),
            page_end=int(entry.get("page_end", 1)),
        )
        for ordinal, entry in enumerate(toc)
    ]



def _ingest_status(*, no_retention: bool, fallback_only: bool) -> str:
    """Map retention + structure flags onto the IngestResponse status enum.

    Args:
        no_retention: True when the no-retention (ephemeral) path was used.
        fallback_only: True when no structure was detected (Scenario C).

    Returns:
        One of ``ephemeral`` | ``fallback_only`` | ``indexed``.
    """
    if no_retention:
        return _INGEST_STATUS_EPHEMERAL
    if fallback_only:
        return _INGEST_STATUS_FALLBACK
    return _INGEST_STATUS_INDEXED


class PipelineIngestor:
    """Adapts ``ingestion.ingest_document`` to the backend Ingestor Protocol.

    Composes the synchronous parse -> TOC -> chunk -> embed -> upsert pipeline with
    the injected collaborators (parser, embedder, section store, vector store) and
    runs it off the event loop, then maps the result onto :class:`IngestOutcome`.
    The ``residency_region`` and ``ocr`` backend kwargs are accepted for contract
    parity; the pipeline derives structure from content, so ``ocr`` does not change
    the call shape and ``residency_region`` is document metadata recorded upstream.
    """

    def __init__(
        self,
        *,
        parser: Parser,
        embedder: Any,
        section_store: SectionStore,
        vector_store: VectorStore,
        ingest: IngestCallable,
        llm_refiner: LlmRefiner | None = None,
    ) -> None:
        """Bind the adapter to the pipeline and its collaborators.

        Args:
            parser: Injected PDF parser (Protocol).
            embedder: Injected embedding adapter (1536-dim).
            section_store: Injected Postgres-facing section store (Protocol).
            vector_store: Injected Qdrant-facing vector store (Protocol).
            ingest: The ``ingestion.ingest_document`` callable.
            llm_refiner: Optional Scenario-B header refiner hook.
        """
        self._parser = parser
        self._embedder = embedder
        self._section_store = section_store
        self._vector_store = vector_store
        self._ingest = ingest
        self._llm_refiner = llm_refiner

    def _run_pipeline(self, doc: IngestInput) -> tuple[dict[str, Any], bool]:
        """Run the synchronous pipeline and detect prior-existence for dedup.

        The ``pre_existing`` flag is read from the pipeline result dict rather than
        from a pre-ingest hash lookup, eliminating the TOCTOU race where two
        concurrent identical uploads both see ``existing=None`` before either ingest
        completes (F-06).

        Args:
            doc: The composed ingest input.

        Returns:
            A tuple of (pipeline result dict, deduplicated flag). The dedup flag is
            True when the pipeline reports the content hash was already present.
        """
        result = self._ingest(
            doc,
            parser=self._parser,
            embedder=self._embedder,
            section_store=self._section_store,
            vector_store=self._vector_store,
            llm_refiner=self._llm_refiner,
        )
        deduplicated = bool(result.get("pre_existing", False))
        return result, deduplicated

    async def ingest_document(
        self,
        tenant_id: str,
        content: bytes,
        filename: str,
        title: str | None,
        domain: str | None,
        no_retention: bool,
        residency_region: str,
        ocr: bool,
    ) -> IngestOutcome:
        """Run the real ingestion pipeline and map its result to IngestOutcome.

        Args:
            tenant_id: Owning tenant (IDOR isolation key).
            content: Raw uploaded PDF bytes.
            filename: Original filename (recorded; not part of the pipeline input).
            title: Optional document title.
            domain: Optional domain label.
            no_retention: When True, persist nothing (DPDP no-retention mode).
            residency_region: Data-residency region (document metadata, FR-028).
            ocr: OCR-fallback flag (contract parity; structure is content-derived).

        Returns:
            An :class:`IngestOutcome` mirroring the openapi IngestResponse.
        """
        doc = IngestInput(
            data=content,
            tenant_id=tenant_id,
            title=title,
            domain=domain,
            no_retention=no_retention,
        )
        try:
            result, deduplicated = await anyio.to_thread.run_sync(self._run_pipeline, doc)
        except DependencyUnavailable:
            raise
        except EmbedderDimensionError as exc:
            from backend.app.errors import ProblemException
            raise ProblemException(
                status_code=500,
                code="EMBEDDER_MISCONFIGURATION",
                title="Embedder misconfiguration",
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise DependencyUnavailable(f"Ingestion pipeline failed: {exc}") from exc

        toc = list(result.get("toc") or [])
        doc_id = str(result["doc_id"])
        fallback_only = bool(result.get("fallback_only", False))
        return IngestOutcome(
            doc_id=doc_id,
            title=title,
            total_pages=int(result.get("total_pages") or 0),
            toc=_toc_to_records(doc_id, tenant_id, toc),
            ingest_status=_ingest_status(
                no_retention=no_retention, fallback_only=fallback_only
            ),
            deduplicated=deduplicated,
        )
