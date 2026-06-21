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

Imports are intentionally lazy (issue #221): the heavy sub-modules pull in
SQLAlchemy engines, the Qdrant client, and the Anthropic SDK. Importing them
at module level would slow every worker startup even when only one adapter is
needed. Consumers should import directly from the sub-module or rely on the
dependency providers in ``backend.app.api.dependencies``.
"""

from __future__ import annotations

__all__ = [
    "RouterModuleAdapter",
    "PipelineIngestor",
    "SqlAlchemyDocumentStore",
    "SqlAlchemySectionStore",
    "QdrantVectorStore",
    "ClaudeGenerationLLM",
]


def __getattr__(name: str) -> object:
    """Lazily import adapter classes on first attribute access.

    Args:
        name: The adapter class name being accessed.

    Returns:
        The requested adapter class.

    Raises:
        AttributeError: When ``name`` is not a known adapter.
    """
    _lazy_map = {
        "SqlAlchemyDocumentStore": ("backend.app.adapters.document_store", "SqlAlchemyDocumentStore"),
        "ClaudeGenerationLLM": ("backend.app.adapters.generation", "ClaudeGenerationLLM"),
        "PipelineIngestor": ("backend.app.adapters.ingestor", "PipelineIngestor"),
        "RouterModuleAdapter": ("backend.app.adapters.router", "RouterModuleAdapter"),
        "QdrantVectorStore": ("backend.app.adapters.stores", "QdrantVectorStore"),
        "SqlAlchemySectionStore": ("backend.app.adapters.stores", "SqlAlchemySectionStore"),
    }
    if name in _lazy_map:
        import importlib
        module_path, attr = _lazy_map[name]
        module = importlib.import_module(module_path)
        return getattr(module, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
