"""RFC-7807 problem+json error model and FastAPI exception handlers.

Every error surfaced by the ``/v1`` API uses the ``application/problem+json``
media type and the ``Problem`` schema from
``docs/phase-1-api-contracts/openapi.yaml`` (Error model section). The machine
readable ``code`` extension member is cataloged here and mirrors
``error_catalog.json`` (e.g. SERVICE_UNAVAILABLE covers deleteDocument per
ADV-002).

Domain code raises :class:`ProblemException`; the registered handlers convert
it (and FastAPI's own validation / HTTP errors) into a uniform problem
document so no endpoint leaks internal detail (NFR-008, common-standards Rule
2 - never expose internals).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"
_PROBLEM_BASE_URI = "https://api.rag-refinement.example.com/problems/"


class ProblemException(Exception):  # noqa: N818 - "Problem" mirrors the RFC-7807 schema name
    """Domain exception that carries an RFC-7807 problem document.

    Attributes:
        status_code: HTTP status code for the response.
        code: Machine-readable error code (error_catalog.json).
        title: Short human-readable summary of the problem type.
        detail: Human-readable explanation specific to this occurrence.
        problem_type: Slug appended to the problem base URI.
        headers: Optional response headers (e.g. Retry-After on 429/503).
        errors: Optional per-field validation errors (ValidationProblem).
        query_id: Optional correlation id surfaced to the caller.
    """

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        title: str,
        detail: str | None = None,
        problem_type: str | None = None,
        headers: dict[str, str] | None = None,
        errors: list[dict[str, str]] | None = None,
        query_id: str | None = None,
    ) -> None:
        """Initialize a problem exception.

        Args:
            status_code: HTTP status code for the response.
            code: Machine-readable error code.
            title: Short human-readable summary.
            detail: Occurrence-specific explanation.
            problem_type: Slug for the problem ``type`` URI; defaults to the
                lower-kebab form of ``code``.
            headers: Optional response headers.
            errors: Optional field-level validation errors.
            query_id: Optional correlation id.
        """
        super().__init__(detail or title)
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail
        self.problem_type = problem_type or code.lower().replace("_", "-")
        self.headers = headers
        self.errors = errors
        self.query_id = query_id

    def to_problem(self) -> dict[str, Any]:
        """Render this exception as an RFC-7807 problem dictionary.

        Returns:
            A JSON-serializable problem document.
        """
        problem: dict[str, Any] = {
            "type": _PROBLEM_BASE_URI + self.problem_type,
            "title": self.title,
            "status": self.status_code,
            "code": self.code,
        }
        if self.detail is not None:
            problem["detail"] = self.detail
        if self.errors is not None:
            problem["errors"] = self.errors
        if self.query_id is not None:
            problem["query_id"] = self.query_id
        return problem


def unauthorized(
    detail: str = "API key or bearer token is missing or invalid.",
) -> ProblemException:
    """Build a 401 UNAUTHORIZED problem.

    The ``WWW-Authenticate: Bearer`` header is included on every 401 response
    per RFC 6750 §3 so that HTTP clients and API gateways can identify the
    accepted credential scheme.  This is intentional even when only API-key
    auth is configured: the header is informational and harmless, and omitting
    it would require threading settings through every error-raise site (issue
    #183 — accepted as RFC-compliant behaviour).

    Args:
        detail: Occurrence-specific explanation.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        code="UNAUTHORIZED",
        title="Unauthorized",
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def forbidden(detail: str = "The caller does not own this document.") -> ProblemException:
    """Build a 403 FORBIDDEN problem (cross-tenant / IDOR).

    Args:
        detail: Occurrence-specific explanation.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=status.HTTP_403_FORBIDDEN,
        code="FORBIDDEN",
        title="Forbidden",
        detail=detail,
    )


def document_not_found(detail: str = "No document with the given id exists.") -> ProblemException:
    """Build a 404 DOCUMENT_NOT_FOUND problem.

    Args:
        detail: Occurrence-specific explanation.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=status.HTTP_404_NOT_FOUND,
        code="DOCUMENT_NOT_FOUND",
        title="Not Found",
        detail=detail,
        problem_type="document-not-found",
    )


def validation_error(
    detail: str = "One or more fields failed validation.",
    errors: list[dict[str, str]] | None = None,
) -> ProblemException:
    """Build a 422 VALIDATION_ERROR problem.

    Args:
        detail: Occurrence-specific explanation.
        errors: Per-field validation error list.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=422,
        code="VALIDATION_ERROR",
        title="Unprocessable Entity",
        detail=detail,
        problem_type="validation-error",
        errors=errors or [],
    )


def unsupported_media_type(
    detail: str = "Only application/pdf uploads are accepted.",
) -> ProblemException:
    """Build a 415 UNSUPPORTED_MEDIA_TYPE problem.

    Args:
        detail: Occurrence-specific explanation.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        code="UNSUPPORTED_MEDIA_TYPE",
        title="Unsupported Media Type",
        detail=detail,
        problem_type="unsupported-media-type",
    )


def payload_too_large(
    detail: str = "The uploaded PDF exceeds the maximum allowed size.",
) -> ProblemException:
    """Build a 413 PAYLOAD_TOO_LARGE problem.

    Args:
        detail: Occurrence-specific explanation.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        code="PAYLOAD_TOO_LARGE",
        title="Payload Too Large",
        detail=detail,
        problem_type="payload-too-large",
    )


def rate_limited(
    retry_after_seconds: int,
    detail: str = "The rate limit for this credential has been exceeded.",
) -> ProblemException:
    """Build a 429 RATE_LIMITED problem with a Retry-After header.

    Args:
        retry_after_seconds: Seconds until the caller may retry.
        detail: Occurrence-specific explanation.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="RATE_LIMITED",
        title="Too Many Requests",
        detail=detail,
        problem_type="rate-limited",
        headers={"Retry-After": str(retry_after_seconds)},
    )


def service_unavailable(
    detail: str = "A required dependency is unreachable.",
    retry_after_seconds: int = 5,
    query_id: str | None = None,
) -> ProblemException:
    """Build a 503 SERVICE_UNAVAILABLE problem (ADV-002 deleteDocument).

    Args:
        detail: Occurrence-specific explanation.
        retry_after_seconds: Seconds until the caller may retry.
        query_id: Optional correlation id for mid-stream error frames.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        code="SERVICE_UNAVAILABLE",
        title="Service Unavailable",
        detail=detail,
        problem_type="service-unavailable",
        headers={"Retry-After": str(retry_after_seconds)},
        query_id=query_id,
    )


def internal_error(
    detail: str = "An unexpected error occurred. The incident has been logged.",
    query_id: str | None = None,
) -> ProblemException:
    """Build a 500 INTERNAL_ERROR problem.

    Args:
        detail: Generic explanation that never exposes internals.
        query_id: Optional correlation id for mid-stream error frames.

    Returns:
        A configured :class:`ProblemException`.
    """
    return ProblemException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        title="Internal Server Error",
        detail=detail,
        problem_type="internal-error",
        query_id=query_id,
    )


def _problem_response(exc: ProblemException) -> JSONResponse:
    """Serialize a problem exception into a problem+json response.

    Args:
        exc: The problem exception to render.

    Returns:
        A JSONResponse with the RFC-7807 media type and any headers.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_problem(),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=exc.headers,
    )


async def _handle_problem(_request: Request, exc: ProblemException) -> JSONResponse:
    """FastAPI handler for :class:`ProblemException`.

    Args:
        _request: The incoming request (unused).
        exc: The raised problem exception.

    Returns:
        The serialized problem response.
    """
    return _problem_response(exc)


async def _handle_request_validation(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert FastAPI request-validation errors into a 422 problem.

    Args:
        _request: The incoming request (unused).
        exc: The validation error raised by FastAPI/Pydantic.

    Returns:
        A 422 VALIDATION_ERROR problem response.
    """
    field_errors: list[dict[str, str]] = []
    for raw in exc.errors():
        location = raw.get("loc", ())
        field = ".".join(str(part) for part in location if part not in ("body", "query", "path"))
        field_errors.append({"field": field or "body", "message": str(raw.get("msg", "invalid"))})
    return _problem_response(validation_error(errors=field_errors))


async def _handle_http_exception(
    _request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Convert Starlette/FastAPI HTTP exceptions into problem documents.

    The mapping covers all common HTTP status codes so that every HTTPException
    raised by FastAPI (e.g. 405 from route matching, 400 from parameter
    validation) produces a well-formed RFC-7807 problem type URI instead of
    the fallback ``problems/error`` slug (issue #220).

    Args:
        _request: The incoming request (unused).
        exc: The raised HTTP exception.

    Returns:
        A problem response mapped from the HTTP status code.
    """
    mapping = {
        status.HTTP_400_BAD_REQUEST: ("BAD_REQUEST", "Bad Request"),
        status.HTTP_401_UNAUTHORIZED: ("UNAUTHORIZED", "Unauthorized"),
        status.HTTP_403_FORBIDDEN: ("FORBIDDEN", "Forbidden"),
        status.HTTP_404_NOT_FOUND: ("NOT_FOUND", "Not Found"),
        status.HTTP_405_METHOD_NOT_ALLOWED: ("METHOD_NOT_ALLOWED", "Method Not Allowed"),
        status.HTTP_408_REQUEST_TIMEOUT: ("REQUEST_TIMEOUT", "Request Timeout"),
        status.HTTP_409_CONFLICT: ("CONFLICT", "Conflict"),
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: ("PAYLOAD_TOO_LARGE", "Payload Too Large"),
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: (
            "UNSUPPORTED_MEDIA_TYPE",
            "Unsupported Media Type",
        ),
        status.HTTP_422_UNPROCESSABLE_ENTITY: ("VALIDATION_ERROR", "Unprocessable Entity"),
        status.HTTP_429_TOO_MANY_REQUESTS: ("RATE_LIMITED", "Too Many Requests"),
        status.HTTP_500_INTERNAL_SERVER_ERROR: ("INTERNAL_ERROR", "Internal Server Error"),
        status.HTTP_502_BAD_GATEWAY: ("BAD_GATEWAY", "Bad Gateway"),
        status.HTTP_503_SERVICE_UNAVAILABLE: ("SERVICE_UNAVAILABLE", "Service Unavailable"),
    }
    code, title = mapping.get(exc.status_code, ("ERROR", "Error"))
    problem = ProblemException(
        status_code=exc.status_code,
        code=code,
        title=title,
        detail=str(exc.detail) if exc.detail else None,
    )
    return _problem_response(problem)


async def _handle_unexpected(_request: Request, _exc: Exception) -> JSONResponse:
    """Catch-all handler that masks unexpected errors as a 500 problem.

    Logs the full traceback server-side so the incident can be investigated
    without leaking any internal detail to the caller (NFR-008).

    Args:
        _request: The incoming request (unused).
        _exc: The unexpected exception (never echoed to the client).

    Returns:
        A generic 500 INTERNAL_ERROR problem response.
    """
    if _request is not None:
        _logger.exception(
            "Unhandled exception on %s %s", _request.method, _request.url.path
        )
    else:
        _logger.exception("Unhandled exception (request unavailable)")
    return _problem_response(internal_error())


def register_exception_handlers(app: FastAPI) -> None:
    """Register all RFC-7807 exception handlers on the application.

    Args:
        app: The FastAPI application to configure.
    """
    app.add_exception_handler(ProblemException, _handle_problem)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _handle_request_validation)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _handle_unexpected)
