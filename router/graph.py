"""LangGraph router state machine: TOC + query -> RouterOutput.

Pipeline (HLD 3.2 / 7.1):

    extract_query -> route (single LLM call) -> threshold
                  -> [select_sections | fallback] -> build RouterOutput

Hard invariants enforced here:

- EXACTLY ONE routing LLM call per query. The projected TOC is serialized and
  cached per ``doc_id`` so repeated queries against the same document re-use the
  cached TOC projection (the LLM call itself is always one per ``route``).
- The router NEVER calls the generation LLM. The graph terminates after the
  confidence gate and returns routing JSON only.
- No fabricated ``section_id``: any id returned by the LLM that is not present in
  the supplied TOC is dropped before selection.
- Strict-JSON + injection guard: a malformed or injected LLM reply that fails
  ``parse_router_llm_json`` triggers a deterministic fallback (no crash, no
  passthrough of attacker-controlled content).
- Confidence thresholding (PRD 8.3): score >= 0.7 included; 0.5-0.7 included only
  if no >= 0.7 section exists; < 0.5 excluded; ALL < 0.5 -> fallback.

The graph is importable without a running LLM. If LangGraph is unavailable, an
equivalent async pipeline fallback is used so tests still run offline; the
selected backend is recorded in ``ROUTER_BACKEND``.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from router.llm import RouterLLM
from router.prompts import _coerce_toc_for_prompt, build_router_messages
from router.schema import RankedSection, RouterOutput, parse_router_llm_json

HIGH_CONFIDENCE = 0.7
LOW_CONFIDENCE_FLOOR = 0.5

_TOC_JSON_CACHE: OrderedDict[str, str] = OrderedDict()
_TOC_CACHE_MAXSIZE = 256


class RouterState(TypedDict, total=False):
    """Mutable state threaded through the router graph.

    Attributes:
        query: The untrusted user query.
        doc_id: Document identifier (TOC cache key).
        toc: Authoritative TOC entries.
        tenant_id: Tenant scope for isolation/tracing.
        confidence_threshold: Inclusion threshold for high-confidence sections.
        max_sections: Maximum number of sections to select.
        toc_by_id: Lookup from section_id to TOC entry.
        toc_json: Cached projected-TOC JSON string for the prompt.
        ranked: Parsed, TOC-validated ranked sections from the LLM.
        rationale: Rationale text (from the LLM or the fallback).
        fallback: Whether the deterministic fallback path was taken.
        selected: Final selected ranked sections (post-threshold).
        started_at: Monotonic start time for latency measurement.
        output: The assembled RouterOutput.
    """

    query: str
    doc_id: str
    toc: Sequence[Mapping[str, Any]]
    tenant_id: str
    confidence_threshold: float
    max_sections: int
    toc_by_id: dict[str, Mapping[str, Any]]
    toc_json: str
    ranked: list[RankedSection]
    rationale: str
    fallback: bool
    selected: list[RankedSection]
    started_at: float
    output: RouterOutput


def _cached_toc_json(doc_id: str, toc: Sequence[Mapping[str, Any]]) -> str:
    """Return the projected-TOC JSON for a document, caching by ``doc_id``.

    Caching the serialized TOC keeps prompt construction cheap on repeated
    queries against the same document. It does not affect the one-call-per-query
    invariant (the LLM is always called exactly once per ``route``).

    Args:
        doc_id: Document identifier used as the cache key.
        toc: Authoritative TOC entries.

    Returns:
        A deterministic JSON string of the projected TOC.
    """
    cached = _TOC_JSON_CACHE.get(doc_id)
    if cached is not None:
        _TOC_JSON_CACHE.move_to_end(doc_id)
        return cached
    projected = _coerce_toc_for_prompt(toc)
    serialized = json.dumps(projected, ensure_ascii=True, sort_keys=True)
    _TOC_JSON_CACHE[doc_id] = serialized
    _TOC_JSON_CACHE.move_to_end(doc_id)
    if len(_TOC_JSON_CACHE) > _TOC_CACHE_MAXSIZE:
        _TOC_JSON_CACHE.popitem(last=False)
    return serialized


def clear_toc_cache() -> None:
    """Clear the per-document TOC projection cache (test/maintenance hook)."""
    _TOC_JSON_CACHE.clear()


def _node_extract_query(state: RouterState) -> RouterState:
    """Initialize derived state: TOC lookup, cached TOC JSON, and the timer.

    Args:
        state: The incoming router state.

    Returns:
        The state augmented with ``toc_by_id``, ``toc_json``, and ``started_at``.
    """
    toc = state["toc"]
    state["toc_by_id"] = {
        str(entry["section_id"]): entry for entry in toc if entry.get("section_id")
    }
    state["toc_json"] = _cached_toc_json(state["doc_id"], toc)
    state["started_at"] = time.monotonic()
    return state


async def _node_route(state: RouterState, llm: RouterLLM) -> RouterState:
    """Perform the single routing LLM call and strictly validate the reply.

    On any parse/validation failure (malformed JSON, schema violation, injected
    output), the deterministic fallback is engaged: ``ranked`` is emptied and
    ``fallback`` is set. Fabricated section ids -- those absent from the TOC --
    are dropped here so they can never reach selection.

    Args:
        state: The router state (must contain ``toc_json`` and ``toc_by_id``).
        llm: The injected routing LLM.

    Returns:
        The state with ``ranked``, ``rationale``, and ``fallback`` populated.
    """
    allowed_ids = list(state["toc_by_id"].keys())
    system, messages = build_router_messages(
        query=state["query"],
        toc=state["toc"],
        allowed_section_ids=allowed_ids,
        toc_json=state["toc_json"],
    )
    raw = await llm.complete(system, messages)
    try:
        parsed = parse_router_llm_json(raw)
    except ValueError:
        state["ranked"] = []
        state["rationale"] = (
            "Routing could not be validated; falling back to full-document search."
        )
        state["fallback"] = True
        return state

    toc_by_id = state["toc_by_id"]
    validated: list[RankedSection] = [
        item for item in parsed.ranked_sections if item.section_id in toc_by_id
    ]
    state["ranked"] = validated
    state["rationale"] = parsed.rationale
    state["fallback"] = False
    return state


def _apply_threshold(
    ranked: Sequence[RankedSection],
    confidence_threshold: float,
    max_sections: int,
) -> list[RankedSection]:
    """Select sections per the confidence-thresholding rules (PRD 8.3 / HLD 6).

    Rules:
        - Sections below ``LOW_CONFIDENCE_FLOOR`` are always excluded first,
          regardless of the caller-supplied ``confidence_threshold``.
        - Among the eligible (>= floor) survivors, sections scoring
          >= ``confidence_threshold`` are included.
        - If none of the survivors reach that threshold, the remaining eligible
          sections in ``[LOW_CONFIDENCE_FLOOR, confidence_threshold)`` are
          included instead.
        - The result is sorted by descending confidence and capped at
          ``max_sections``. The effective high-band cutoff is therefore
          ``max(confidence_threshold, LOW_CONFIDENCE_FLOOR)``.

    Args:
        ranked: TOC-validated ranked sections.
        confidence_threshold: The high-confidence inclusion threshold.
        max_sections: Maximum number of sections to return.

    Returns:
        The selected sections (possibly empty, which signals fallback upstream).
    """
    ordered = sorted(ranked, key=lambda item: item.confidence, reverse=True)
    eligible = [item for item in ordered if item.confidence >= LOW_CONFIDENCE_FLOOR]
    high = [item for item in eligible if item.confidence >= confidence_threshold]
    if high:
        return high[:max_sections]
    mid = [item for item in eligible if item.confidence < confidence_threshold]
    return mid[:max_sections]


def _node_threshold(state: RouterState) -> RouterState:
    """Apply confidence thresholding and decide whether to fall back.

    Args:
        state: The router state with ``ranked`` populated.

    Returns:
        The state with ``selected`` set and ``fallback`` finalized.
    """
    if state.get("fallback"):
        state["selected"] = []
        return state
    selected = _apply_threshold(
        state["ranked"],
        state["confidence_threshold"],
        state["max_sections"],
    )
    state["selected"] = selected
    if not selected:
        state["fallback"] = True
    return state


def _node_build_output(state: RouterState) -> RouterState:
    """Assemble the final ``RouterOutput``, joining page ranges from the TOC.

    Page ranges are looked up from the authoritative TOC by ``section_id`` (GRC-001
    / HLD 7.5); they are display-only. Latency is computed from the monotonic
    start time captured in ``extract_query``.

    Args:
        state: The router state with ``selected`` and ``fallback`` finalized.

    Returns:
        The state with ``output`` populated.
    """
    elapsed_ms = int((time.monotonic() - state["started_at"]) * 1000)
    toc_by_id = state["toc_by_id"]

    relevant_sections: list[str] = []
    page_ranges: list[list[int]] = []
    confidence: list[float] = []

    if not state["fallback"]:
        for item in state["selected"]:
            entry = toc_by_id[item.section_id]
            relevant_sections.append(item.section_id)
            page_ranges.append([int(entry["page_start"]), int(entry["page_end"])])
            confidence.append(item.confidence)

    rationale = state.get("rationale") or (
        "No section met the confidence threshold; using full-document search."
        if state["fallback"]
        else ""
    )

    state["output"] = RouterOutput(
        relevant_sections=relevant_sections,
        page_ranges=page_ranges,
        confidence=confidence,
        fallback=state["fallback"],
        routing_time_ms=elapsed_ms,
        rationale=rationale,
    )
    return state


def _build_langgraph(llm: RouterLLM) -> object | None:
    """Compile the LangGraph state machine, or return None if unavailable.

    Args:
        llm: The injected routing LLM (bound into the route node).

    Returns:
        A compiled LangGraph app, or ``None`` when LangGraph cannot be imported.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    async def route_node(state: RouterState) -> RouterState:
        return await _node_route(state, llm)

    builder: Any = StateGraph(RouterState)
    builder.add_node("extract_query", _node_extract_query)
    builder.add_node("route", route_node)
    builder.add_node("threshold", _node_threshold)
    builder.add_node("build_output", _node_build_output)
    builder.add_edge(START, "extract_query")
    builder.add_edge("extract_query", "route")
    builder.add_edge("route", "threshold")
    builder.add_edge("threshold", "build_output")
    builder.add_edge("build_output", END)
    return builder.compile()


async def _run_pipeline_fallback(state: RouterState, llm: RouterLLM) -> RouterState:
    """Run the equivalent async pipeline when LangGraph is unavailable (offline).

    This mirrors the graph edges exactly so behavior is identical with or without
    LangGraph installed.

    Args:
        state: The initial router state.
        llm: The injected routing LLM.

    Returns:
        The final state with ``output`` populated.
    """
    state = _node_extract_query(state)
    state = await _node_route(state, llm)
    state = _node_threshold(state)
    state = _node_build_output(state)
    return state


class RouterGraph:
    """Compiled router pipeline bound to a single injected ``RouterLLM``.

    Uses LangGraph when available and an equivalent async pipeline otherwise. The
    chosen backend is exposed via ``backend`` for diagnostics and tests.
    """

    def __init__(self, llm: RouterLLM) -> None:
        """Bind the router pipeline to a routing LLM.

        Args:
            llm: The injected routing LLM (deterministic fake in tests).
        """
        self._llm = llm
        self._app = _build_langgraph(llm)
        self.backend = "langgraph" if self._app is not None else "async-pipeline"

    async def run(
        self,
        query: str,
        doc_id: str,
        toc: Sequence[Mapping[str, Any]],
        tenant_id: str,
        confidence_threshold: float,
        max_sections: int,
    ) -> RouterOutput:
        """Execute the router pipeline for one query.

        Args:
            query: The untrusted user query.
            doc_id: Document identifier (TOC cache key).
            toc: Authoritative TOC entries.
            tenant_id: Tenant scope for isolation/tracing.
            confidence_threshold: High-confidence inclusion threshold.
            max_sections: Maximum number of sections to select.

        Returns:
            The validated ``RouterOutput``.
        """
        initial: RouterState = {
            "query": query,
            "doc_id": doc_id,
            "toc": toc,
            "tenant_id": tenant_id,
            "confidence_threshold": confidence_threshold,
            "max_sections": max_sections,
        }
        if self._app is not None:
            final: RouterState = await self._app.ainvoke(initial)  # type: ignore[attr-defined]
        else:
            final = await _run_pipeline_fallback(initial, self._llm)
        return final["output"]


ROUTER_BACKEND = "langgraph"
try:  # pragma: no cover - import probe only
    import langgraph as _langgraph_probe  # noqa: F401
except ImportError:  # pragma: no cover
    ROUTER_BACKEND = "async-pipeline"
