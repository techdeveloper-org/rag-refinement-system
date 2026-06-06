"""LangGraph router package (STORY-014): TOC + query -> routing scope.

Public surface:
    ``route``        -- the async routing entrypoint (interface contract).
    ``RouterOutput`` -- the validated router output model (HLD 7.1).

The router maps a document Table of Contents and an untrusted user query to a
confidence-thresholded set of relevant sections via a single Claude 3 Haiku call
(ADR-1) inside an in-process async LangGraph state machine (ADR-3). It never
calls the generation LLM and never fabricates a section id absent from the TOC.
The routing LLM is injectable so tests run deterministically and offline.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from router.graph import RouterGraph
from router.llm import RouterLLM
from router.schema import RouterOutput

__all__ = ["route", "RouterOutput", "RouterLLM", "RouterGraph"]


async def route(
    query: str,
    doc_id: str,
    toc: Sequence[Mapping[str, Any]],
    *,
    tenant_id: str,
    llm: RouterLLM | None = None,
    confidence_threshold: float = 0.7,
    max_sections: int = 3,
) -> dict[str, Any]:
    """Route a query to the most relevant document sections.

    Runs the in-process async router graph: it builds an injection-resistant
    prompt from the TOC and query, issues EXACTLY ONE routing LLM call, validates
    the strict-JSON reply, applies confidence thresholding, and joins page ranges
    from the authoritative TOC by ``section_id``. On any non-conforming or
    injected LLM reply it returns a deterministic fallback result
    (``fallback=True``). The router never invokes the generation LLM and never
    returns a section id that is not present in ``toc``.

    Args:
        query: The user's natural-language query (untrusted input).
        doc_id: The document identifier (used as the TOC cache key).
        toc: The authoritative TOC entries. Each entry must provide
            ``section_id``, ``title``, ``page_start``, and ``page_end`` (``level``
            and ``summary`` are optional).
        tenant_id: Tenant scope for isolation and tracing (keyword-only).
        llm: The routing LLM implementation. Required in practice; when omitted a
            ``ClaudeHaikuRouterLLM`` is constructed (which resolves credentials
            from the environment). Tests pass a deterministic fake.
        confidence_threshold: Sections scoring below this are treated as
            low-confidence (default 0.7).
        max_sections: Maximum number of sections to return (default 3).

    Returns:
        A ``RouterOutput`` serialized to a dict with keys ``relevant_sections``,
        ``page_ranges``, ``confidence``, ``fallback``, ``routing_time_ms``, and
        ``rationale``.
    """
    if llm is None:
        from router.llm import ClaudeHaikuRouterLLM

        llm = ClaudeHaikuRouterLLM()
    graph = RouterGraph(llm)
    output = await graph.run(
        query=query,
        doc_id=doc_id,
        toc=toc,
        tenant_id=tenant_id,
        confidence_threshold=confidence_threshold,
        max_sections=max_sections,
    )
    return output.model_dump()
