"""Adapters binding the backend service-boundary Protocols to live modules.

The API layer (``backend.app.api``) depends only on the typed Protocols in
``backend.app.api.interfaces``. These adapters are the production composition
root: each one wraps a real collaborator owned by another domain
(``router`` / ``ingestion`` / ``db``) or an external provider (Anthropic Claude)
and presents it through the backend Protocol the endpoints expect.

The adapters carry no business logic of their own - they are thin translators
that map the in-module contracts onto the AGREED CONTRACT shapes
(``RouterDecision`` / ``IngestOutcome`` / ``DocumentRecord`` etc.). Observable
endpoint behavior is unchanged; the only difference is that the live
dependency providers now construct these instead of raising a 503.
"""

from __future__ import annotations

from backend.app.adapters.document_store import SqlAlchemyDocumentStore
from backend.app.adapters.generation import ClaudeGenerationLLM
from backend.app.adapters.ingestor import PipelineIngestor
from backend.app.adapters.router import RouterModuleAdapter
from backend.app.adapters.stores import QdrantVectorStore, SqlAlchemySectionStore

__all__ = [
    "RouterModuleAdapter",
    "PipelineIngestor",
    "SqlAlchemyDocumentStore",
    "SqlAlchemySectionStore",
    "QdrantVectorStore",
    "ClaudeGenerationLLM",
]
