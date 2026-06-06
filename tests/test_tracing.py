"""Unit tests for LangSmith tracing configuration."""

from __future__ import annotations

from backend.app.productization.tracing import configure_tracing


def test_tracing_disabled_when_no_api_key() -> None:
    env: dict[str, str] = {}

    status = configure_tracing(environ=env)

    assert status.enabled is False
    assert "LANGCHAIN_TRACING_V2" not in env
    assert status.project == "rag-refinement-system"


def test_tracing_enabled_when_api_key_present() -> None:
    env = {"LANGSMITH_API_KEY": "lsk-not-a-real-key"}

    status = configure_tracing(environ=env)

    assert status.enabled is True
    assert env["LANGCHAIN_TRACING_V2"] == "true"
    assert env["LANGSMITH_PROJECT"] == "rag-refinement-system"


def test_explicit_project_is_honored() -> None:
    env = {
        "LANGSMITH_API_KEY": "lsk-not-a-real-key",
        "LANGSMITH_PROJECT": "rag-staging",
    }

    status = configure_tracing(environ=env)

    assert status.enabled is True
    assert status.project == "rag-staging"
    assert env["LANGSMITH_PROJECT"] == "rag-staging"


def test_api_key_value_is_never_returned() -> None:
    env = {"LANGSMITH_API_KEY": "lsk-secret-value"}

    status = configure_tracing(environ=env)

    assert "lsk-secret-value" not in repr(status)
