"""GenerationLLM adapter: streaming answer synthesis via Anthropic Claude.

Implements the backend :class:`GenerationLLM` Protocol (FIX-C-03) used by the SSE
``/v1/answer`` path. ``stream_answer`` yields answer token fragments synthesized
from the routed sections by Claude (Opus 4.8). The async Anthropic client is
constructed lazily on first use and the API key is resolved from the environment
by the SDK - it is never accepted as a constructor literal (no hardcoded secret).
Because construction is lazy, importing this module and wiring the provider never
requires credentials; the adapter only contacts Anthropic when a stream is
actually requested with a key present.

The router decides scope; this adapter only synthesizes prose over the routed
section titles/pages and never performs routing or retrieval. Answer streaming
uses the SDK's ``messages.stream`` helper so long answers do not hit request
timeouts.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

from backend.app.api.interfaces import DependencyUnavailable, RoutedSection

DEFAULT_GENERATION_MODEL = os.environ.get("GENERATION_MODEL", "claude-opus-4-8")
"""Answer-synthesis model id (overridable via the GENERATION_MODEL env var)."""

DEFAULT_MAX_TOKENS = int(os.environ.get("GENERATION_MAX_TOKENS", "16000"))
"""Output token ceiling for a synthesized answer (must exceed DEFAULT_THINKING_BUDGET_TOKENS)."""

DEFAULT_THINKING_BUDGET_TOKENS = 5000
"""Default extended-thinking budget in tokens."""

DEFAULT_STREAM_TIMEOUT = 300.0
"""Total timeout in seconds for a streaming answer generation call."""

_SYSTEM_PROMPT = (
    "You are a retrieval-augmented answer assistant. Answer the user's question "
    "using only the routed document sections provided as context. Cite section "
    "titles where relevant and do not fabricate facts beyond the supplied scope."
)


def _build_context(sections: list[RoutedSection]) -> str:
    """Render the routed sections into a compact textual context block.

    Args:
        sections: The router-selected sections (titles + authoritative pages).

    Returns:
        A newline-delimited context string; a sentinel when no section routed.
    """
    if not sections:
        return "(No section met the routing threshold; answer from general scope.)"
    lines = [
        f"- {section.title} (pages {section.page_start}-{section.page_end})"
        for section in sections
    ]
    return "\n".join(lines)


class ClaudeGenerationLLM:
    """Anthropic Claude streaming adapter for answer synthesis (FIX-C-03).

    Wraps the async Anthropic client. The model id defaults to Claude Opus 4.8
    (overridable via ``GENERATION_MODEL`` or the ``model`` argument). The client is
    built lazily and resolves its key from the environment, so the provider can be
    wired without credentials and only runs live when a key is present.
    """

    def __init__(
        self,
        model: str = DEFAULT_GENERATION_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        thinking_budget_tokens: int = DEFAULT_THINKING_BUDGET_TOKENS,
        client: object | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            model: Generation model id (defaults to Claude Opus 4.8).
            max_tokens: Output token ceiling for the synthesized answer.
            thinking_budget_tokens: Extended-thinking budget in tokens passed to
                the Anthropic ``thinking`` parameter.
            client: Optional pre-built ``anthropic.AsyncAnthropic`` instance. When
                omitted, one is constructed lazily on first use so importing this
                module never requires credentials.
        """
        self._model = model
        self._max_tokens = max_tokens
        self._thinking_budget_tokens = thinking_budget_tokens
        self._client = client
        self._client_lock = asyncio.Lock()

    async def _ensure_client(self) -> object:
        """Lazily construct the async Anthropic client (env-resolved credentials).

        Uses a double-checked lock so concurrent first requests do not race to
        build multiple client instances.

        Returns:
            The async Anthropic client instance.

        Raises:
            DependencyUnavailable: When the ``anthropic`` package is not installed
                (surfaced as a mid-stream SSE error / 503 per the answer contract).
        """
        if self._client is None:
            async with self._client_lock:
                if self._client is None:
                    try:
                        import anthropic
                    except ImportError as exc:
                        raise DependencyUnavailable(
                            "anthropic package is required for answer generation"
                        ) from exc
                    self._client = anthropic.AsyncAnthropic(max_retries=0)
        return self._client

    async def stream_answer(
        self,
        query: str,
        sections: list[RoutedSection],
    ) -> AsyncIterator[str]:
        """Yield answer token fragments synthesized over the routed sections.

        Args:
            query: The user's question.
            sections: The router-selected sections that scope the answer.

        Yields:
            Answer text fragments as they stream from Claude.

        Raises:
            DependencyUnavailable: When the generation client cannot be built or
                when the Anthropic API is unreachable / returns an auth or rate-limit
                error.
        """
        client = await self._ensure_client()
        context = _build_context(sections)
        user_message = (
            "<question>\n"
            f"{query}\n"
            "</question>\n\n"
            "<routed_sections>\n"
            f"{context}\n"
            "</routed_sections>\n\n"
            "Answer the question using only the information in the routed sections above."
        )
        try:
            async with client.messages.stream(  # type: ignore[attr-defined]
                model=self._model,
                max_tokens=self._max_tokens,
                thinking={"type": "enabled", "budget_tokens": self._thinking_budget_tokens},
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
                timeout=DEFAULT_STREAM_TIMEOUT,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except DependencyUnavailable:
            raise
        except Exception as exc:
            try:
                import anthropic as _anthropic
                if isinstance(
                    exc,
                    (
                        _anthropic.RateLimitError,
                        _anthropic.AuthenticationError,
                        _anthropic.APIConnectionError,
                    ),
                ):
                    raise DependencyUnavailable(
                        f"Anthropic API unavailable: {type(exc).__name__}"
                    ) from exc
            except ImportError:
                pass
            raise DependencyUnavailable(
                f"Generation dependency error: {type(exc).__name__}"
            ) from exc
