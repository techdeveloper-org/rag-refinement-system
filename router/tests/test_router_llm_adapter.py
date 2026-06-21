"""Tests for the router LLM adapters in ``router.llm``.

Covers the ``ClaudeHaikuRouterLLM`` Anthropic adapter (injected fake client,
single-call contract, text-block concatenation, and the missing-package error
on lazy client construction) plus the ``FakeRouterLLM`` call recorder. No real
Anthropic client or key is used.
"""

from __future__ import annotations

import sys

import pytest

from router.llm import (
    DEFAULT_ROUTER_MODEL,
    ClaudeHaikuRouterLLM,
    FakeRouterLLM,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    """Run anyio-based async tests on asyncio only."""
    return "asyncio"


class _TextBlock:
    """Stub Anthropic content block of type ``text``."""

    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _NonTextBlock:
    """Stub Anthropic content block of a non-text type (must be ignored)."""

    def __init__(self) -> None:
        self.type = "tool_use"


class _Reply:
    """Stub Anthropic message reply carrying a content block list."""

    def __init__(self, blocks: list[object]) -> None:
        self.content = blocks


class _Messages:
    """Stub Anthropic ``messages`` namespace recording create calls."""

    def __init__(self, reply: _Reply) -> None:
        self._reply = reply
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: object) -> _Reply:
        self.calls.append(kwargs)
        return self._reply


class _FakeAnthropic:
    """Stub async Anthropic client exposing ``messages.create``."""

    def __init__(self, reply: _Reply) -> None:
        self.messages = _Messages(reply)


class TestClaudeHaikuRouterLLM:
    """The Claude 3 Haiku routing adapter."""

    async def test_complete_concatenates_text_blocks_only(self) -> None:
        """Only text blocks are concatenated; non-text blocks are ignored."""
        reply = _Reply([_TextBlock("{\"ranked_"), _NonTextBlock(), _TextBlock("sections\":[]}")])
        client = _FakeAnthropic(reply)
        adapter = ClaudeHaikuRouterLLM(client=client)
        out = await adapter.complete("system", [{"role": "user", "content": "q"}])
        assert out == '{"ranked_sections":[]}'

    async def test_complete_makes_exactly_one_call(self) -> None:
        """Exactly one routing call is issued per ``complete`` (one-call invariant)."""
        client = _FakeAnthropic(_Reply([_TextBlock("{}")]))
        adapter = ClaudeHaikuRouterLLM(client=client)
        await adapter.complete("system", [{"role": "user", "content": "q"}])
        assert len(client.messages.calls) == 1
        assert client.messages.calls[0]["model"] == DEFAULT_ROUTER_MODEL

    async def test_ensure_client_raises_when_anthropic_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing ``anthropic`` package raises a clear RuntimeError."""
        monkeypatch.setitem(sys.modules, "anthropic", None)
        adapter = ClaudeHaikuRouterLLM()
        with pytest.raises(RuntimeError, match="anthropic package is required"):
            adapter._ensure_client()

    async def test_ensure_client_builds_and_caches_real_client(self) -> None:
        """With anthropic importable, the lazy client is built once and cached."""
        pytest.importorskip("anthropic")
        adapter = ClaudeHaikuRouterLLM()
        client = adapter._ensure_client()
        assert client is not None
        assert adapter._ensure_client() is client


class TestFakeRouterLLM:
    """The deterministic offline router LLM fake."""

    async def test_records_calls_and_returns_reply(self) -> None:
        """The fake returns its canned reply and records each call."""
        fake = FakeRouterLLM('{"ranked_sections":[]}')
        out = await fake.complete("sys", [{"role": "user", "content": "q"}])
        assert out == '{"ranked_sections":[]}'
        assert fake.call_count == 1
        assert fake.calls[0]["system"] == "sys"
