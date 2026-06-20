"""API package: /v1 routers, schemas, and service-boundary interfaces.

Implements the operations declared in
``docs/phase-1-api-contracts/openapi.yaml`` (routeQuery, answerQuery,
ingestDocument, listDocuments, getDocument, getDocumentToc, deleteDocument,
exportDocumentData). Routing is request/response and never invokes generation
(HLD 7.2); answering streams over SSE (HLD 7.3). All cross-domain
collaborators (router, ingestion, generation LLM, document store) are reached
through injectable interfaces so this layer is testable in isolation.
"""

from __future__ import annotations
