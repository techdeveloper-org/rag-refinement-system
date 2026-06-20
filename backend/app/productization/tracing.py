"""LangSmith tracing wiring (observability, AGREED CONTRACT devops <-> all).

Configures LangSmith tracing for the LangGraph router and generation paths from
the 12-factor environment. ``LANGSMITH_API_KEY`` is read from the secret-manager
-injected environment (already declared in ``.env.example``); when it is absent
the application runs with tracing disabled and never fails to start. No secret
value is logged or defaulted here.

LangChain/LangSmith read their own ``LANGCHAIN_*`` / ``LANGSMITH_*`` environment
variables at import time inside those libraries; this module's job is to make the
operator's intent explicit and to report, without leaking the key, whether
tracing is active for a deployment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_TRACING_FLAG = "LANGCHAIN_TRACING_V2"
_API_KEY_ENV = "LANGSMITH_API_KEY"
_PROJECT_ENV = "LANGSMITH_PROJECT"
_DEFAULT_PROJECT = "rag-refinement-system"


@dataclass(frozen=True)
class TracingStatus:
    """Resolved tracing configuration for a deployment.

    Attributes:
        enabled: True when a LangSmith API key is present and tracing is on.
        project: The LangSmith project traces are grouped under.
    """

    enabled: bool
    project: str


def configure_tracing(environ: dict[str, str] | None = None) -> TracingStatus:
    """Resolve and apply LangSmith tracing configuration from the environment.

    When ``LANGSMITH_API_KEY`` is present, sets ``LANGCHAIN_TRACING_V2=true`` and
    a project name so LangChain/LangGraph emit traces. When the key is absent,
    tracing is left disabled and the process continues normally.

    Args:
        environ: Optional environment mapping to read/update; defaults to the
            live ``os.environ``. Injected in tests to avoid global mutation.

    Returns:
        A :class:`TracingStatus` describing whether tracing is enabled and the
        project traces are filed under. The API key value is never returned.
    """
    env = os.environ if environ is None else environ
    api_key = env.get(_API_KEY_ENV)
    project = env.get(_PROJECT_ENV, _DEFAULT_PROJECT)

    if not api_key:
        return TracingStatus(enabled=False, project=project)

    env[_TRACING_FLAG] = "true"
    env.setdefault(_PROJECT_ENV, project)
    return TracingStatus(enabled=True, project=project)
