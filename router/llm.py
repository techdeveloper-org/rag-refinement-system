"""Router LLM abstraction: a Protocol plus a Claude 3 Haiku adapter and a fake.

The router depends on an injectable ``RouterLLM`` Protocol so that tests run
fully offline against ``FakeRouterLLM`` with no network calls, while production
uses ``ClaudeHaikuRouterLLM`` (ADR-1: Claude 3 Haiku). The Protocol exposes a
single async ``complete`` method that takes a system prompt plus a message list
and returns the model's raw text reply -- the caller is responsible for strict
parsing and validation (see ``router.schema``).
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

DEFAULT_ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "claude-3-haiku")
DEFAULT_MAX_TOKENS = 1024


@runtime_checkable
class RouterLLM(Protocol):
    """Minimal async interface the router needs from a routing LLM.

    Implementations MUST perform exactly one model call per ``complete`` and MUST
    NOT call any generation model. The return value is the raw, unparsed text of
    the model's reply; validation happens in ``router.schema``.
    """

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
    ) -> str:
        """Return the model's raw text reply for the given prompt.

        Args:
            system: The system prompt establishing role/security separation.
            messages: The Messages-API-style message list (user/assistant turns).

        Returns:
            The model's raw text output, to be parsed by the caller.
        """
        ...


class ClaudeHaikuRouterLLM:
    """Claude 3 Haiku adapter for the router (ADR-1).

    Wraps the async Anthropic client. The model id defaults to ``claude-3-haiku``
    (overridable via the ``ROUTER_MODEL`` env var or the ``model`` argument). The
    API key is read from the environment by the Anthropic SDK -- it is never
    accepted as a constructor literal, satisfying the no-hardcoded-secrets rule.

    This adapter performs exactly one ``messages.create`` per ``complete`` call
    and only ever targets the routing model; it has no path to a generation model.
    """

    def __init__(
        self,
        model: str = DEFAULT_ROUTER_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: object | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            model: Routing model id (defaults to Claude 3 Haiku).
            max_tokens: Output token ceiling for the routing reply.
            client: Optional pre-built ``anthropic.AsyncAnthropic`` instance. When
                omitted, one is constructed lazily on first use so importing this
                module never requires credentials.
        """
        self._model = model
        self._max_tokens = max_tokens
        self._client = client

    def _ensure_client(self) -> object:
        """Lazily construct the async Anthropic client (env-resolved credentials).

        Returns:
            The async Anthropic client instance.

        Raises:
            RuntimeError: If the ``anthropic`` package is not installed.
        """
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:
                raise RuntimeError(
                    "anthropic package is required for ClaudeHaikuRouterLLM"
                ) from exc
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
    ) -> str:
        """Issue exactly one routing call to Claude 3 Haiku and return its text.

        Args:
            system: The system prompt (role/security separation).
            messages: The user/assistant message list.

        Returns:
            The concatenated text content of the model's reply.
        """
        client = self._ensure_client()
        response = await client.messages.create(  # type: ignore[attr-defined]
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
        )
        parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts)


class FakeRouterLLM:
    """Deterministic in-memory router LLM for offline tests.

    Returns a caller-supplied canned reply and records every ``complete`` call so
    tests can assert that exactly one routing call was made per query. No network
    access occurs.
    """

    def __init__(self, reply: str) -> None:
        """Initialize the fake.

        Args:
            reply: The exact raw text to return from every ``complete`` call.
        """
        self._reply = reply
        self.calls: list[dict[str, object]] = []

    @property
    def call_count(self) -> int:
        """Number of ``complete`` invocations recorded so far."""
        return len(self.calls)

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
    ) -> str:
        """Record the call and return the canned reply.

        Args:
            system: The system prompt (recorded for assertions).
            messages: The message list (recorded for assertions).

        Returns:
            The canned reply text supplied at construction.
        """
        self.calls.append({"system": system, "messages": messages})
        return self._reply
