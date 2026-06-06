"""Canonical, prefixed identifier derivation for the ingestion pipeline (FIX-1).

Single source of truth for ``doc_id`` and ``section_id`` formats so the ingestion
pipeline and the backend adapter cannot diverge. Ids are deterministic (a given
input always maps to the same id) and prefixed + hyphen-free so they satisfy every
downstream schema:

    * backend document schema: ``^doc_[A-Za-z0-9]{6,}$``
    * backend section schema:  ``^sec_[A-Za-z0-9]{1,}$``
    * router section filter:   ``^sec_[A-Za-z0-9]+$``

A bare ``uuid5`` string (hyphenated, no prefix) fails all three, which is the bug
this module fixes. Using ``.hex`` yields 32 lowercase hex characters with no
hyphens, and the ``doc_``/``sec_`` prefixes make the ids match the patterns above.
"""

from __future__ import annotations

import uuid

_ID_NAMESPACE = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
"""Stable namespace so a content hash maps to a deterministic id (idempotency)."""

DOC_ID_PREFIX = "doc_"
"""Prefix required by the backend document id pattern ``^doc_[A-Za-z0-9]{6,}$``."""

SECTION_ID_PREFIX = "sec_"
"""Prefix required by the section id patterns ``^sec_[A-Za-z0-9]+$``."""


def doc_id_for(tenant_id: str, content_hash: str) -> str:
    """Derive the canonical, prefixed ``doc_id`` for a tenant + content hash.

    Deterministic and hyphen-free: a re-upload of identical content for the same
    tenant maps to the same id (idempotency, OAQ-1), and the ``doc_`` prefix plus
    32 lowercase hex characters satisfy ``^doc_[A-Za-z0-9]{6,}$``.

    Args:
        tenant_id: Owning tenant (part of the id seed, IDOR isolation key).
        content_hash: SHA-256 content hash of the upload.

    Returns:
        A canonical document id of the form ``doc_<32 hex chars>``.
    """
    digest = uuid.uuid5(_ID_NAMESPACE, f"{tenant_id}:{content_hash}").hex
    return f"{DOC_ID_PREFIX}{digest}"


def section_id_for(doc_id: str, ordinal: int) -> str:
    """Derive the canonical, prefixed ``section_id`` for a document's nth section.

    Deterministic and hyphen-free: the ``sec_`` prefix plus 32 lowercase hex
    characters satisfy ``^sec_[A-Za-z0-9]+$``. ``section_id`` is the universal key
    bridging Postgres sections and Qdrant chunk points, so this is the only place
    its format is defined.

    Args:
        doc_id: Owning document id (part of the id seed).
        ordinal: Zero-based section ordinal within the document.

    Returns:
        A canonical section id of the form ``sec_<32 hex chars>``.
    """
    digest = uuid.uuid5(_ID_NAMESPACE, f"{doc_id}:section:{ordinal}").hex
    return f"{SECTION_ID_PREFIX}{digest}"
