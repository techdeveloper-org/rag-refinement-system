"""Routing-only enterprise endpoint: POST /v1/route (routeQuery).

Implements the HLD 7.2 invariant: this endpoint returns the optimal retrieval
scope and **never calls the generation LLM** (AGREED CONTRACT ai-engineer <->
python-backend-engineer). It validates the ``oneOf(document_id |
document_ids)`` contract (AC-ADV-001), enforces the per-credential rate limit
(ADV-003), resolves the tenant from the credential, and returns the routed
sections with a display-only token-reduction estimate.
"""

from __future__ import annotations

import asyncio as _asyncio
import logging

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_document_store, get_router

_logger = logging.getLogger(__name__)
from backend.app.api.helpers import estimate_token_reduction, new_query_id
from backend.app.api.interfaces import (
    DependencyUnavailable,
    DocumentStore,
    Router,
)
from backend.app.api.schemas import (
    RelevantSection,
    RouteRequest,
    RouteResponse,
)
from backend.app.errors import (
    ProblemException,
    document_not_found,
    service_unavailable,
    validation_error,
)
from backend.app.security.auth import Principal
from backend.app.security.rate_limit import rate_limit

router = APIRouter(prefix="/v1", tags=["Routing"])


def _target_document_ids(body: RouteRequest) -> list[str]:
    """Normalize the request's document selector into a list of ids.

    Args:
        body: The validated route request.

    Returns:
        The single document id wrapped in a list, or the multi-document list.
    """
    if body.document_id is not None:
        return [body.document_id]
    return list(body.document_ids or [])


@router.post(
    "/route",
    operation_id="routeQuery",
    response_model=RouteResponse,
    response_model_exclude_none=True,
)
async def route_query(
    body: RouteRequest,
    principal: Principal = Depends(rate_limit()),
    store: DocumentStore = Depends(get_document_store),
    routing: Router = Depends(get_router),
) -> RouteResponse:
    """Route a query to relevant sections without generating an answer.

    Args:
        body: The validated route request (oneOf document selector enforced).
        principal: The authenticated, rate-limited caller.
        store: Tenant-scoped document store for ownership/IDOR checks.
        routing: The in-process router (never invokes generation).

    Returns:
        A :class:`RouteResponse` with routed sections, confidences, fallback
        flag, and a display-only token-reduction estimate.

    Raises:
        ProblemException: 404 when a target document is not owned by the
            caller (IDOR guard); 422 when rerank is requested; 503 when a
            dependency is unreachable.
    """
    document_ids = list(dict.fromkeys(_target_document_ids(body)))

    # Fix #262: rerank=True is not supported — reject with 422 instead of
    # silently downgrading and returning HTTP 200.
    if body.rerank:
        raise validation_error(
            detail="Reranking is not yet supported. Set 'rerank: false' or omit the field.",
            errors=[{"field": "rerank", "message": "FEATURE_UNAVAILABLE"}],
        )

    async def _fetch_doc(doc_id: str):
        try:
            return await store.get_document(principal.tenant_id, doc_id)
        except DependencyUnavailable as exc:
            raise service_unavailable(str(exc) or "Document store unavailable.") from exc

    # Fix #251: pass return_exceptions=True so that a failure in one coroutine
    # does not silently cancel the remaining coroutines.  Each result is
    # inspected individually so the correct domain error is raised.
    fetch_coros = [_fetch_doc(did) for did in document_ids]
    results = await _asyncio.gather(*fetch_coros, return_exceptions=True)

    # Fix #251 + #277: re-raise domain exceptions and identify the specific
    # doc_id that was not found rather than raising a generic 404.
    docs = []
    for doc_id, result in zip(document_ids, results):
        if isinstance(result, Exception):
            raise result
        if result is None:
            raise document_not_found(f"Document '{doc_id}' not found.")
        docs.append(result)

    total_pages = sum(d.total_pages for d in docs)

    for document in docs:
        if document.fallback_only:
            raise validation_error(
                detail="One or more documents were indexed in fallback mode and do not support section-level routing.",
                errors=[{"field": "document_ids", "message": "fallback-only document"}],
            )

    # Fix #279: reject documents that have not finished indexing (total_pages=0
    # means the ingestor has not yet written any pages).
    for doc in docs:
        if doc.total_pages == 0:
            raise ProblemException(
                status_code=409,
                code="DOCUMENT_NOT_READY",
                title="Conflict",
                detail=(
                    f"Document '{doc.doc_id}' is still being indexed. "
                    "Please retry in a few seconds."
                ),
                problem_type="document-not-ready",
            )

    try:
        decision = await routing.route(
            tenant_id=principal.tenant_id,
            document_ids=document_ids,
            query=body.query,
            confidence_threshold=body.confidence_threshold,
            max_sections=body.max_sections,
        )
    except DependencyUnavailable as exc:
        raise service_unavailable(str(exc) or "Routing dependency unavailable.") from exc

    # Fix #252: generate query_id before constructing RelevantSection objects
    # so it can be included in the error detail if Pydantic validation fails.
    query_id = new_query_id()

    try:
        relevant_sections = [
            RelevantSection(
                section_id=section.section_id,
                document_id=section.document_id,
                title=section.title,
                page_start=section.page_start,
                page_end=section.page_end,
                confidence=section.confidence,
            )
            for section in decision.relevant_sections
        ]
    except Exception as exc:
        _logger.error(
            "Router returned invalid section data: %s",
            exc,
            extra={"query_id": query_id},
        )
        raise ProblemException(
            status_code=502,
            code="ROUTER_OUTPUT_INVALID",
            title="Bad Gateway",
            detail=str(exc),
            problem_type="router-output-invalid",
            query_id=query_id,
        ) from exc

    page_ranges = [
        [section.page_start, section.page_end] for section in decision.relevant_sections
    ]
    confidences = [section.confidence for section in decision.relevant_sections]

    return RouteResponse(
        query_id=query_id,
        relevant_sections=relevant_sections,
        page_ranges=page_ranges,
        confidence=confidences,
        fallback=decision.fallback,
        rerank_applied=False,
        routing_time_ms=decision.routing_time_ms,
        rationale=decision.rationale,
        estimated_token_reduction=estimate_token_reduction(
            decision.relevant_sections, total_pages
        ),
    )
