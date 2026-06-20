"""Personal-tool streaming endpoint: POST /v1/answer (answerQuery).

Routes the query, performs the routed retrieval, then streams the generated
answer token-by-token over Server-Sent Events (HLD 7.3). The stream emits
repeated ``event: token`` messages (TokenEvent), a terminal ``event: final``
message (AnswerFinalEvent with ``{answer, citations[], routing{}}``), and -
when a failure occurs after the 200 has been sent - an ``event: error``
message carrying an RFC-7807 Problem (AC-ADV-002).

Non-streaming errors (auth, validation, not-found) are returned as a normal
problem+json response **before** the stream opens.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

_logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.app.api.dependencies import (
    get_document_store,
    get_generation_llm,
    get_router,
)
from backend.app.api.helpers import new_query_id
from backend.app.api.interfaces import (
    DependencyUnavailable,
    DocumentStore,
    GenerationLLM,
    Router,
    RouterDecision,
)
from backend.app.api.schemas import (
    AnswerFinalEvent,
    AnswerRequest,
    Citation,
    RoutingSummary,
)
from backend.app.errors import (
    document_not_found,
    internal_error,
    service_unavailable,
    validation_error,
)
from backend.app.security.auth import Principal
from backend.app.security.rate_limit import rate_limit

router = APIRouter(prefix="/v1", tags=["Answers"])

_SSE_MEDIA_TYPE = "text/event-stream"


def _sse_event(event: str, data: dict[str, object]) -> str:
    """Format a single Server-Sent Event frame.

    Args:
        event: The SSE event name (``token``, ``final``, or ``error``).
        data: The JSON-serializable data payload.

    Returns:
        A wire-format SSE frame terminated by a blank line.
    """
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _build_routing_summary(decision: RouterDecision) -> RoutingSummary:
    """Project a router decision into the SSE routing summary.

    Args:
        decision: The in-process router decision.

    Returns:
        A :class:`RoutingSummary` with index-aligned sections and confidences.
    """
    return RoutingSummary(
        sections=[section.section_id for section in decision.relevant_sections],
        confidence=[section.confidence for section in decision.relevant_sections],
        fallback=decision.fallback,
        rationale=decision.rationale,
    )


def _build_citations(decision: RouterDecision) -> list[Citation]:
    """Build the answer citations from the routed sections.

    Args:
        decision: The in-process router decision.

    Returns:
        A list of :class:`Citation` for each routed section.
    """
    return [
        Citation(
            section_id=section.section_id,
            section_title=section.title,
            page_start=section.page_start,
            page_end=section.page_end,
        )
        for section in decision.relevant_sections
    ]


async def _answer_stream(
    query_id: str,
    query: str,
    decision: RouterDecision,
    generator: GenerationLLM,
) -> AsyncIterator[str]:
    """Yield the SSE frames for one answer: tokens, then final (or error).

    A failure that occurs after streaming has begun is delivered as an
    ``event: error`` frame carrying a Problem (AC-ADV-002) - the 200 status
    has already been sent, so the error cannot change the HTTP status.

    Args:
        query_id: The correlation id for this answer.
        query: The user's question.
        decision: The router decision driving retrieval scope.
        generator: The streaming generation LLM.

    Yields:
        Wire-format SSE frames.
    """
    answer_parts: list[str] = []
    try:
        async for token in generator.stream_answer(query, decision.relevant_sections):
            answer_parts.append(token)
            yield _sse_event("token", {"query_id": query_id, "token": token})

        final = AnswerFinalEvent(
            query_id=query_id,
            answer="".join(answer_parts),
            citations=_build_citations(decision),
            routing=_build_routing_summary(decision),
        )
        yield _sse_event("final", final.model_dump(exclude_none=True))
    except DependencyUnavailable as exc:
        problem = service_unavailable(
            exc.args[0] if exc.args and exc.args[0] else "Generation dependency unavailable."
        )
        problem.query_id = query_id
        yield _sse_event("error", problem.to_problem())
    except asyncio.CancelledError:
        _logger.info("answer stream cancelled (client disconnect); query_id=%s", query_id)
        raise
    except Exception:  # noqa: BLE001 - mid-stream failures become an SSE error event
        _logger.exception("unhandled error in answer stream; query_id=%s", query_id)
        problem = internal_error()
        problem.query_id = query_id
        yield _sse_event("error", problem.to_problem())


@router.post(
    "/answer",
    operation_id="answerQuery",
    responses={200: {"content": {_SSE_MEDIA_TYPE: {}}}},
)
async def answer_query(
    body: AnswerRequest,
    principal: Principal = Depends(rate_limit()),
    store: DocumentStore = Depends(get_document_store),
    routing: Router = Depends(get_router),
    generator: GenerationLLM = Depends(get_generation_llm),
) -> StreamingResponse:
    """Stream a generated, cited answer over Server-Sent Events.

    Auth, validation, ownership, and routing failures are returned as a normal
    RFC-7807 response **before** the stream opens. Once the 200 SSE stream is
    open, a mid-stream failure is delivered as an ``event: error`` frame.

    Args:
        body: The validated answer request (single document, ADV-006).
        principal: The authenticated, rate-limited caller.
        store: Tenant-scoped document store (IDOR guard).
        routing: The in-process router.
        generator: The streaming generation LLM.

    Returns:
        A :class:`StreamingResponse` of ``text/event-stream`` frames.

    Raises:
        ProblemException: 404 when the document is not owned by the caller;
            503 when routing is unreachable (pre-stream).
    """
    try:
        document = await store.get_document(principal.tenant_id, body.document_id)
    except DependencyUnavailable as exc:
        raise service_unavailable(
            exc.args[0] if exc.args and exc.args[0] else "Document store unavailable."
        ) from exc
    if document is None:
        raise document_not_found()

    if document.fallback_only:
        # TODO: product owner to confirm — Option B (whole-document RAG) may replace this
        raise validation_error(
            detail="This document was indexed in fallback mode and does not support section-level routing.",
            errors=[{"field": "document_id", "message": "fallback-only document"}],
        )

    try:
        decision = await routing.route(
            tenant_id=principal.tenant_id,
            document_ids=[body.document_id],
            query=body.query,
            confidence_threshold=body.confidence_threshold,
            max_sections=body.max_sections,
        )
    except DependencyUnavailable as exc:
        raise service_unavailable(str(exc) or "Routing dependency unavailable.") from exc

    query_id = new_query_id()
    return StreamingResponse(
        _answer_stream(query_id, body.query, decision, generator),
        media_type=_SSE_MEDIA_TYPE,
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
