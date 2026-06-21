"""Pydantic schemas and strict-JSON validation/repair for the LangGraph router.

This module defines two surfaces:

1. The raw LLM response contract (``RawRouterLLMResponse``) that the Claude 3 Haiku
   router prompt is required to emit, plus a strict parser/repair function
   (``parse_router_llm_json``) that rejects or repairs any non-conforming output.
   This is the OWASP-LLM01 (prompt-injection) guard: document text and the user
   query are untrusted, so the model's reply is never trusted as control flow --
   it is validated against this schema before any value is used.
2. The public router output contract (``RouterOutput``) returned by ``route()``,
   matching the HLD 7.1 / openapi.yaml ``RouteResponse`` shape.

A core invariant enforced here and by the graph: the router MUST NOT surface a
``section_id`` that is absent from the supplied TOC. The parser keeps only the
ranked items; section-id membership is enforced by the caller (``graph.py``)
against the authoritative TOC.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

SECTION_ID_PATTERN = re.compile(r"^sec_[A-Za-z0-9]+$")

MAX_RAW_RESPONSE_CHARS = 20000
MAX_RANKED_ITEMS = 200


class RankedSection(BaseModel):
    """A single ranked section as emitted by the router LLM.

    Attributes:
        section_id: Candidate section identifier. Validated against the TOC by
            the caller; the pattern check here only rejects structurally invalid
            ids (a cheap first-pass injection guard).
        confidence: Router confidence in [0.0, 1.0] that the section is relevant.
    """

    model_config = ConfigDict(extra="ignore")

    section_id: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("section_id")
    @classmethod
    def _section_id_shape(cls, value: str) -> str:
        """Reject section ids that do not match the universal SectionId pattern."""
        if not SECTION_ID_PATTERN.match(value):
            raise ValueError("section_id does not match required pattern")
        return value


class RawRouterLLMResponse(BaseModel):
    """Strict contract for the router LLM's JSON reply.

    The model is instructed to emit exactly this object. Any deviation (missing
    keys, extra keys, wrong types, out-of-range confidence) is a validation
    failure that triggers the deterministic fallback rather than passing
    attacker-influenced content downstream.
    """

    model_config = ConfigDict(extra="forbid")

    ranked_sections: list[RankedSection] = Field(default_factory=list)
    rationale: str = Field(default="", max_length=2000)

    @field_validator("ranked_sections")
    @classmethod
    def _bound_ranked_items(cls, value: list[RankedSection]) -> list[RankedSection]:
        """Reject pathologically large rankings (resource-exhaustion guard)."""
        if len(value) > MAX_RANKED_ITEMS:
            raise ValueError("ranked_sections exceeds maximum length")
        return value


class RouterOutput(BaseModel):
    """Public router output contract (HLD 7.1 / openapi RouteResponse subset).

    Returned by ``route()`` as a validated object; callers typically consume the
    ``model_dump()`` dict. ``page_ranges`` are joined from the authoritative TOC
    by ``section_id`` (per GRC-001 / HLD 7.5) and are display-only.

    Attributes:
        relevant_sections: Selected section ids, in ranked order.
        page_ranges: Per-section ``[page_start, page_end]`` intervals joined from
            the TOC; parallel to ``relevant_sections``.
        confidence: Per-section confidence scores; parallel to
            ``relevant_sections``.
        fallback: True when no section met the inclusion threshold and the
            full-document path must be used.
        routing_time_ms: Wall-clock router latency in milliseconds.
        rationale: Interpretable "why did you look here?" explanation
            (FR-012, NFR-011).
    """

    model_config = ConfigDict(extra="forbid")

    relevant_sections: list[str] = Field(default_factory=list)
    page_ranges: list[list[int]] = Field(default_factory=list)
    confidence: list[float] = Field(default_factory=list)
    fallback: bool = False
    routing_time_ms: int = Field(ge=0)
    rationale: str = ""


def _extract_json_object(text: str) -> str:
    """Extract the first balanced top-level JSON object from text.

    Repairs the common, benign case where the model wraps its JSON in prose or a
    markdown code fence. It does NOT attempt to interpret or execute any content;
    it only locates a brace-balanced substring to hand to ``json.loads``. Strings
    are tracked so braces inside string literals do not affect nesting depth.

    Args:
        text: Raw model output.

    Returns:
        The substring spanning the first balanced ``{...}`` object.

    Raises:
        ValueError: If no balanced JSON object is present.
    """
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in router response")

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError("unbalanced JSON object in router response")


def parse_router_llm_json(raw: str) -> RawRouterLLMResponse:
    """Parse and validate the router LLM's reply with strict-JSON enforcement.

    This is the OWASP-LLM01 boundary. The reply is treated as untrusted text:
    it is size-bounded, parsed as JSON (with a single benign code-fence/prose
    repair attempt), and validated against ``RawRouterLLMResponse``. Any failure
    raises ``ValueError`` so the graph can take the deterministic fallback rather
    than acting on malformed or injected output.

    Args:
        raw: The model's raw text reply.

    Returns:
        A validated ``RawRouterLLMResponse``.

    Raises:
        ValueError: If the reply is too large, is not valid JSON, or does not
            conform to the strict schema.
    """
    if not isinstance(raw, str):
        raise ValueError("router response is not text")
    if len(raw) > MAX_RAW_RESPONSE_CHARS:
        raise ValueError("router response exceeds maximum size")

    candidate = raw.strip()
    try:
        payload: Any = json.loads(candidate)
    except json.JSONDecodeError:
        repaired = _extract_json_object(candidate)
        payload = json.loads(repaired)

    if not isinstance(payload, dict):
        raise ValueError("router response JSON is not an object")

    try:
        return RawRouterLLMResponse.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"router response failed schema validation: {exc}") from exc
