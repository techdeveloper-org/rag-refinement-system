"""Tests for the streaming generation adapter ``ClaudeGenerationLLM``.

Covers ``stream_answer`` over an injected fake Anthropic streaming client (token
fan-out), the ``_ensure_client`` missing-package path that surfaces as
``DependencyUnavailable`` (mid-stream SSE error / 503), and the empty-sections
context branch. No real Anthropic client or key is used.
"""

from __future__ import annotations

import sys

import pytest

from backend.app.adapters.generation import ClaudeGenerationLLM, _build_context
from backend.app.api.interfaces import DependencyUnavailable, RoutedSection

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only."""
    return "asyncio"


def _section() -> RoutedSection:
    """Build a routed-section fixture."""
    return RoutedSection(
        section_id="sec_1",
        title="Warranty",
        page_start=1,
        page_end=5,
        confidence=0.9,
        document_id="doc_1",
    )


class _TextStream:
    """Async iterator over canned answer fragments."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens

    def __aiter__(self) -> _TextStream:
        self._index = 0
        return self

    async def __anext__(self) -> str:
        if self._index >= len(self._tokens):
            raise StopAsyncIteration
        token = self._tokens[self._index]
        self._index += 1
        return token


class _StreamContext:
    """Async context manager mimicking ``messages.stream``."""

    def __init__(self, tokens: list[str]) -> None:
        self.text_stream = _TextStream(tokens)

    async def __aenter__(self) -> _StreamContext:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Messages:
    """Stub Anthropic ``messages`` namespace exposing ``stream``."""

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self.calls: list[dict[str, object]] = []

    def stream(self, **kwargs: object) -> _StreamContext:
        self.calls.append(kwargs)
        return _StreamContext(self._tokens)


class _FakeAnthropic:
    """Stub async Anthropic client exposing ``messages.stream``."""

    def __init__(self, tokens: list[str]) -> None:
        self.messages = _Messages(tokens)


class TestBuildContext:
    """The routed-section context renderer."""

    @pytest.mark.anyio
    async def test_sections_render_to_lines(self) -> None:
        """Each routed section renders as a titled, page-ranged context line."""
        context = _build_context([_section()])
        assert "Warranty" in context
        assert "pages 1-5" in context

    @pytest.mark.anyio
    async def test_empty_sections_render_sentinel(self) -> None:
        """No routed sections render a general-scope sentinel (fallback path)."""
        context = _build_context([])
        assert "No section met the routing threshold" in context


class TestStreamAnswer:
    """The streaming answer synthesis path."""

    async def test_stream_yields_each_token(self) -> None:
        """The adapter yields each fragment from the streaming client in order."""
        adapter = ClaudeGenerationLLM(client=_FakeAnthropic(["Hello", " world"]))
        tokens = [tok async for tok in adapter.stream_answer("q", [_section()])]
        assert tokens == ["Hello", " world"]

    async def test_missing_anthropic_raises_dependency_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing ``anthropic`` package surfaces as DependencyUnavailable (503)."""
        monkeypatch.setitem(sys.modules, "anthropic", None)
        adapter = ClaudeGenerationLLM()
        with pytest.raises(DependencyUnavailable):
            async for _ in adapter.stream_answer("q", [_section()]):
                pass
