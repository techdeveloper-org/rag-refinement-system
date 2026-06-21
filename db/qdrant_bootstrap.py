"""Idempotent Qdrant collection bootstrap for the RAG vector store (ADR-2).

Creates the chunk-vector collection and the payload indexes that power the
"scope before search" mechanism: a payload filter on ``section_id`` (router
selection) AND ``tenant_id`` (the IDOR isolation guard from GRC). Vector size is
1536 to match ``text-embedding-3-small`` (ADR-6); distance is Cosine.

Hard invariants (STORY-002 / AC-004):
    * Point payload is exactly ``{chunk_id, section_id, doc_id, page, tenant_id}``
      (AGREED CONTRACT python-backend-engineer <-> database-engineer, HLD 4.3).
    * Payload indexes exist on ``section_id``, ``doc_id`` and ``tenant_id`` for
      fast filtered search; ``tenant_id`` is the mandatory isolation filter.
    * Bootstrap is idempotent - it skips creation when the collection already
      exists and never overwrites existing data.

Configuration is read from ``QDRANT_URL`` (12-factor env, devops AGREED
CONTRACT); no credentials are hardcoded. No PII values are handled here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client import models as qm
from qdrant_client.http.exceptions import UnexpectedResponse

logger = logging.getLogger(__name__)

COLLECTION_NAME: str = "rag_chunks"
"""Name of the Qdrant collection holding Level-3 chunk vectors."""

VECTOR_SIZE: int = 1536
"""Embedding dimensionality for OpenAI text-embedding-3-small (ADR-6)."""

DISTANCE: qm.Distance = qm.Distance.COSINE
"""Similarity metric for chunk vectors."""

PAYLOAD_INDEX_FIELDS: tuple[str, ...] = ("section_id", "doc_id", "tenant_id")
"""Payload fields indexed for filtered search. ``tenant_id`` is the IDOR guard."""

PAYLOAD_KEYS: tuple[str, ...] = (
    "chunk_id",
    "section_id",
    "doc_id",
    "page",
    "tenant_id",
)
"""Exact payload shape of every chunk point (AGREED CONTRACT)."""


@dataclass(frozen=True)
class BootstrapResult:
    """Outcome of a bootstrap call.

    Attributes:
        created: True when the collection was newly created, False when an
            existing collection was found and creation was skipped.
        indexed_fields: Payload fields for which a payload index was ensured.
    """

    created: bool
    indexed_fields: tuple[str, ...]


def vectors_config() -> qm.VectorParams:
    """Return the vector configuration for the chunk collection.

    Returns:
        VectorParams with size 1536 (text-embedding-3-small) and Cosine
        distance.
    """
    return qm.VectorParams(size=VECTOR_SIZE, distance=DISTANCE)


def get_client(url: str | None = None) -> QdrantClient:
    """Build a Qdrant client from an explicit URL or the ``QDRANT_URL`` env var.

    Args:
        url: Optional explicit Qdrant endpoint. When omitted, ``QDRANT_URL`` is
            read from the environment (12-factor; no hardcoded credentials).

    Returns:
        A configured QdrantClient.

    Raises:
        RuntimeError: When neither ``url`` nor ``QDRANT_URL`` is provided.
    """
    resolved = url or os.environ.get("QDRANT_URL")
    if not resolved:
        raise RuntimeError(
            "QDRANT_URL is not set; provide a url argument or the env var."
        )
    return QdrantClient(url=resolved)


def ensure_payload_indexes(
    client: QdrantClient, collection_name: str = COLLECTION_NAME
) -> tuple[str, ...]:
    """Ensure a keyword payload index exists for each isolation/filter field.

    Idempotent: an already-present index raises a benign error that is treated
    as success, so re-running never fails.

    Args:
        client: Qdrant client to operate on.
        collection_name: Target collection name.

    Returns:
        The tuple of payload fields that now have an index.
    """
    for field in PAYLOAD_INDEX_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=qm.PayloadSchemaType.KEYWORD,
            )
        except UnexpectedResponse as exc:
            if exc.status_code in (400, 409):
                logger.debug(
                    "payload index for %r already present (idempotent ensure): %s",
                    field,
                    exc,
                )
            else:
                raise
    return PAYLOAD_INDEX_FIELDS


def _verify_vector_size(client: QdrantClient, collection_name: str) -> None:
    """Verify that an existing collection's vector size matches VECTOR_SIZE.

    Args:
        client: Qdrant client to query.
        collection_name: Name of the collection to inspect.

    Raises:
        RuntimeError: When the collection's configured vector size differs from
            VECTOR_SIZE, indicating a schema mismatch that requires manual
            intervention (delete the collection and restart).
    """
    collection_info = client.get_collection(collection_name)
    actual_size = collection_info.config.params.vectors.size
    if actual_size != VECTOR_SIZE:
        raise RuntimeError(
            f"Qdrant collection '{collection_name}' has vector size {actual_size} "
            f"but VECTOR_SIZE={VECTOR_SIZE}. Delete the collection and restart."
        )


def bootstrap_collection(
    client: QdrantClient, collection_name: str = COLLECTION_NAME
) -> BootstrapResult:
    """Create the chunk collection and payload indexes if they are absent.

    Skips creation when the collection already exists (idempotent), then ensures
    the ``section_id`` / ``doc_id`` / ``tenant_id`` payload indexes either way.
    When connecting to an existing collection, verifies that the configured vector
    size equals VECTOR_SIZE to catch schema mismatches early (issue #202).

    Args:
        client: Qdrant client to operate on.
        collection_name: Target collection name.

    Returns:
        A BootstrapResult recording whether the collection was created and which
        payload fields were indexed.

    Raises:
        RuntimeError: When an existing collection has a vector size that does not
            match VECTOR_SIZE.
    """
    exists = client.collection_exists(collection_name=collection_name)
    if not exists:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=vectors_config(),
        )
    _verify_vector_size(client, collection_name)
    indexed = ensure_payload_indexes(client, collection_name=collection_name)
    return BootstrapResult(created=not exists, indexed_fields=indexed)


def tenant_section_filter(
    tenant_id: str, section_ids: list[str]
) -> qm.Filter:
    """Build the mandatory targeted-retrieval filter.

    Encodes tenant_id = caller AND section_id IN (router-selected) - the
    isolation + scope filter every retrieval must apply (HLD 4.3, OAQ-3/OAQ-5).
    tenant_id is required and never optional: it is the IDOR guard.

    Args:
        tenant_id: Owning tenant; mandatory isolation key.
        section_ids: Router-selected section ids to scope the ANN search to.
            Must be non-empty; calling with an empty list is a programming error
            since there is no valid retrieval scope with zero sections.

    Returns:
        A Qdrant Filter combining the tenant guard and the section scope.

    Raises:
        ValueError: When tenant_id is empty or whitespace-only, or when
            section_ids is empty (would expose all tenant chunks).
    """
    if not tenant_id or not tenant_id.strip():
        raise ValueError("tenant_id is mandatory and must not be blank (IDOR guard).")
    if not section_ids:
        raise ValueError(
            "section_ids must be non-empty; retrieving with zero sections "
            "would expose all tenant chunks (IDOR violation)."
        )
    return qm.Filter(
        must=[
            qm.FieldCondition(
                key="tenant_id", match=qm.MatchValue(value=tenant_id)
            ),
            qm.FieldCondition(
                key="section_id", match=qm.MatchAny(any=list(section_ids))
            ),
        ]
    )


def main() -> None:
    """CLI entry point: bootstrap the collection against ``QDRANT_URL``.

    Intended for one-shot provisioning. Prints whether the collection was
    created or already existed.
    """
    client = get_client()
    result = bootstrap_collection(client)
    state = "created" if result.created else "already existed"
    print(
        f"Qdrant collection '{COLLECTION_NAME}' {state}; "
        f"payload indexes ensured on {', '.join(result.indexed_fields)}."
    )


if __name__ == "__main__":
    main()
